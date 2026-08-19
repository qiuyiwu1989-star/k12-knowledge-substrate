#!/usr/bin/env python3
"""
resolve_disputed.py — 给 disputed 一个下落。

## 为什么要做这件事

`disputed` 本来是「AI 挑出了问题，退出可用集合，等人判」。但没人来判，
它就变成了**终态垃圾桶** —— 144 条进去之后再没有任何动作，而且里面混着
三种性质完全不同的东西。不分开，人来了也无从下手。

## 分四类，每类的处置理由不同

1. **模型在跟课标较劲** —— 异议是 `stage`，而锚点的 `provenance.srcStage`
   （课标正文里印的「第二学段（3～4年级）」这种小标题）与标注学段完全一致。
   **课标写了学段，模型的意见不能盖过课标。** 撤销异议。

2. **是我们自己窄化的** —— 课标写「第二学段」（G3–G4），我们标成了 G3–G3。
   这不是异议，是**发明精度**：抽取时模型自报的学段比课标窄，而流水线
   「模型自报优先」把它收了下来（见 stage_by_page.py）。
   还原成课标学段范围，撤销异议。**这个项目反复栽在发明精度上。**

3. **闸也拦得住** —— 模型说不可判定，而 `check-stdin.mjs` 也拦（都是
   「一条塞了三条以上并列」）。两个判官一致，不需要人：弃用。
   **不硬拆** —— 拆句需要教学判断，硬拆就是又造一批假锚点。

4. **两个判官冲突 / 无据可依** —— 其余全部保留 disputed。
   模型说不可判定但闸放行、或课标压根没写学段。**这些才是真正该给人看的**，
   而且现在它们不再被前三类淹没。

    python3 tools/resolve_disputed.py --dry-run
    python3 tools/resolve_disputed.py
"""
import argparse, collections, json, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fix_src_stages import read_bands, STD          # noqa: E402  —— 学段划分只有一份定义
G = lambda s: int(s[1:]) if isinstance(s, str) and s.startswith('G') else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    files = {f: [json.loads(l) for l in f.open(encoding='utf-8') if l.strip()]
             for f in sorted((ROOT / 'anchors').glob('*.jsonl'))}
    BANDS, _ = read_bands()
    disp = [r for rows in files.values() for r in rows
            if not r.get('deprecated') and r['reviewStatus'] == 'disputed']
    print(f"disputed {len(disp)} 条")

    # 闸：一次批量过，和 CI 用的是同一个
    p = subprocess.run(['node', str(ROOT / 'scripts/lib/check-stdin.mjs')],
                       input='\n'.join(r['statement'] for r in disp),
                       capture_output=True, text=True, timeout=300)
    if p.returncode != 0:
        sys.exit(f'闸调用失败：{(p.stderr or "")[:200]}')
    verdicts = [json.loads(l) for l in p.stdout.splitlines() if l.strip()]
    if len(verdicts) != len(disp):
        sys.exit(f'闸返回 {len(verdicts)} 条，期望 {len(disp)} —— 对齐坏了，不敢往下走')

    stat = collections.Counter()
    samples = collections.defaultdict(list)

    for r, v in zip(disp, verdicts):
        issues = r.get('aiIssues') or []
        types = {i['type'] for i in issues}

        # ── 3. 闸也拦得住 → 弃用 ─────────────────────────────────
        if not v.get('ok') and types & {'undecidable', 'not-a-capability'}:
            r['deprecated'] = True
            r['dropReason'] = ('模型判「不可判定」，可判定闸也拦（' +
                               '；'.join(v.get('reasons', []))[:50] + '）。'
                               '两个判官一致，不需要人。不硬拆 —— 拆句需要教学判断')
            r['aiIssues'] = issues + [{'type': 'resolved',
                                       'detail': '模型与可判定闸判断一致（' +
                                                 '；'.join(v.get('reasons', []))[:60] + '）→ 弃用。'
                                                 '不硬拆：拆句需要教学判断'}]
            stat['① 闸也拦得住 → 弃用'] += 1
            samples['① 闸也拦得住 → 弃用'].append(r)
            continue

        # 撤销异议之前必须先过我们自己的闸。
        # 实测：一条只被挑了 stage 的英语锚点，撤销 stage 后回到 ai-reviewed，
        # 立刻被 validate 的可判定闸抓住（≥3 个顿号）—— 它本来就不该出 disputed。
        # **模型没挑出的问题，不等于没问题。**
        if not v.get('ok'):
            stat['⑦ 异议可撤但过不了闸 → 留在 disputed'] += 1
            samples['⑦ 异议可撤但过不了闸 → 留在 disputed'].append(r)
            continue

        # ── 1 / 2. stage 异议，拿课标学段当裁判 ──────────────────
        if 'stage' in types:
            m = re.fullmatch(r'第([一二三四])学段',
                             ((r.get('provenance') or {}).get('srcStage') or '').strip())
            ss = BANDS.get(r['discipline'], STD)[m.group(1)] if m else None
            h = r.get('stageHint') or {}
            lo, hi = G(h.get('min')), G(h.get('max'))
            if ss and lo and hi:
                if (lo, hi) == ss:
                    why = '课标正文标了学段且与标注一致 —— 模型的意见不能盖过课标'
                    key = '② 模型在跟课标较劲 → 撤销异议'
                elif ss[0] <= lo and hi <= ss[1]:
                    r['stageHint'] = {'min': f'G{ss[0]}', 'max': f'G{ss[1]}'}
                    why = (f'标注 G{lo}–G{hi} 比课标窄，已还原成课标学段 '
                           f'G{ss[0]}–G{ss[1]} —— 发明精度是我们自己的毛病，不是异议')
                    key = '③ 我们窄化的 → 还原学段'
                else:
                    stat['④ 学段与课标冲突 → 保留'] += 1
                    samples['④ 学段与课标冲突 → 保留'].append(r)
                    continue
                issues = [i for i in issues if i['type'] != 'stage']
                issues.append({'type': 'resolved', 'detail': why})
                r['aiIssues'] = issues
                if not {i['type'] for i in issues} & {'undecidable', 'not-a-capability',
                                                      'evidence-weak', 'truncated'}:
                    r['reviewStatus'] = 'ai-reviewed'
                    stat[key] += 1
                    samples[key].append(r)
                else:
                    stat['⑤ 撤了 stage 但还有别的异议 → 保留'] += 1
                continue

        stat['⑥ 两个判官冲突 / 无据可依 → 保留待人判'] += 1
        samples['⑥ 两个判官冲突 / 无据可依 → 保留待人判'].append(r)

    print()
    for k, n in sorted(stat.items()):
        print(f"  {n:>4}  {k}")
        for r in samples[k][:2]:
            print(f"          {r['discipline']} {r['statement'][:38]}")

    still = sum(n for k, n in stat.items() if '保留' in k or 'disputed' in k)
    print(f"\n落定后：disputed 剩 {still} 条（原 {len(disp)}），"
          f"其中 {stat['⑥ 两个判官冲突 / 无据可依 → 保留待人判']} 条是真正需要人判的")

    if a.dry_run:
        print("（--dry-run：没有写盘）")
        return
    for f, rows in files.items():
        with f.open('w', encoding='utf-8') as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + '\n')
    print("已写盘。记得 npm run check + node scripts/manifest.mjs")


if __name__ == '__main__':
    main()
