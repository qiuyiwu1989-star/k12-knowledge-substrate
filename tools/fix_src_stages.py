#!/usr/bin/env python3
"""
fix_src_stages.py — 用课标自己印的学段划分修正 stageHint。

## 这个 bug 是查 disputed 时撞出来的

`stage_by_page.py` 的 `norm_stage()` 把**所有学科**都套数学那套四段划分
（1–2 / 3–4 / 5–6 / 7–9），还写了一行「跨学段的写法（如 G3-5）落到覆盖它的
最小学段区间上」。而**艺术课标根本不是这么分的**：

    艺术：第一学段 1～2 · 第二学段 3～5 · 第三学段 6～7 · 第四学段 8～9

于是艺术「第三学段（6～7年级）」被折成 G5–G6，**整整错开一到两个年级**；
「第四学段（8～9年级）」被摊成 G7–G9。实测 38 条艺术锚点学段是错的。

这是同一类错第三次了（`gen_edges` 的 STAGE_ORD 只到 G9、`ai_review` 的
OPEN_AT 只到 9 年级）：**为一个学科写的常量表，换个学科不会报错，只会静默给出错误答案。**

所以这次不硬编码 —— 学段划分**从 `tools/out/page-index.jsonl` 的标题里读**
（「第二学段（3～5年级）」这种字样课标自己印着）。读不到的学科才落回义务教育
课程方案的标准四段，且加一道断言：**某学科只要有一个学段范围偏离标准，
就必须四个学段全都读到，否则拒绝处理该学科。**

## 顺带修掉「发明精度」

课标写「第二学段」（G3–G4），库里不少条标成 G3–G3 —— 抽取时模型自报的学段
比课标窄，而流水线是「模型自报优先」。**那是发明精度**，和高中「必修 1 就是高一」
一个毛病。一律还原成课标写的学段范围。

    python3 tools/fix_src_stages.py --dry-run
    python3 tools/fix_src_stages.py
"""
import argparse, collections, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IDX = ROOT / 'tools/out/page-index.jsonl'
CN = ['一', '二', '三', '四']
STD = {'一': (1, 2), '二': (3, 4), '三': (5, 6), '四': (7, 9)}
PAT = re.compile(r'第([一二三四])学段\s*[（(]\s*(\d)\s*[~～-]\s*(\d)\s*年级')


def read_bands():
    """从页索引标题里读各科真实的学段划分。读不到的落回标准四段。"""
    if not IDX.exists():
        sys.exit(f'缺 {IDX} —— 学段划分必须从源头读，不接受硬编码')
    found = collections.defaultdict(dict)
    for l in IDX.open(encoding='utf-8'):
        if not l.strip():
            continue
        r = json.loads(l)
        for m in PAT.finditer(str(r.get('heading') or '')):
            found[r['subject']][m.group(1)] = (int(m.group(2)), int(m.group(3)))

    bands, notes = {}, []
    for sub, got in found.items():
        odd = {k: v for k, v in got.items() if STD[k] != v}
        if not odd:
            continue                              # 和标准一致，不必特殊对待
        if len(got) != 4:
            notes.append(f'⚠ {sub} 学段划分偏离标准（{odd}）但只读到 {len(got)}/4 个，'
                         f'不敢补全，跳过该学科')
            continue
        bands[sub] = got
        notes.append(f'· {sub} 用课标自己的划分：' +
                     '／'.join(f'第{k}学段 {got[k][0]}-{got[k][1]}' for k in CN))
    return bands, notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    bands, notes = read_bands()
    print('学段划分（只列偏离标准的）：')
    for n in notes:
        print('  ' + n)
    print('  其余学科用义务教育课程方案标准四段 1-2／3-4／5-6／7-9')

    files = {f: [json.loads(l) for l in f.open(encoding='utf-8') if l.strip()]
             for f in sorted((ROOT / 'anchors').glob('*.jsonl'))}
    stat = collections.Counter()
    changes = collections.defaultdict(list)
    conflicts = []

    for rows in files.values():
        for r in rows:
            if r.get('deprecated'):
                continue
            ss = (r.get('provenance') or {}).get('srcStage') or ''
            m = re.fullmatch(r'第([一二三四])学段', ss.strip())
            if not m:
                stat['课标没写学段，不动'] += 1
                continue
            lo, hi = bands.get(r['discipline'], STD)[m.group(1)]
            want = {'min': f'G{lo}', 'max': f'G{hi}'}
            cur = r.get('stageHint') or {}
            if cur == want:
                stat['本来就对'] += 1
                continue
            cl, ch = (int(cur['min'][1:]) if cur.get('min') else None,
                      int(cur['max'][1:]) if cur.get('max') else None)
            if r['discipline'] in bands:
                # 这个学科的学段划分表本身是错的 —— 旧值是用错表算出来的，重算
                kind = '学段划分套错了学科'
            elif cl and ch and lo <= cl and ch <= hi:
                kind = '还原被窄化的'          # 落在课标学段内，只是被窄化了
            else:
                # 当前学段整个落在课标学段之外 —— 这不是窄化，是**冲突**。
                # 实测：数学「比例尺」标 G6 而 srcStage 说第二学段（G3–G4），
                # 比例尺本来就是六年级内容，是页面归属错了。改它会把对的改错。
                stat['与课标学段冲突 → 不动，留给人判'] += 1
                conflicts.append((r['discipline'], f"{cur.get('min')}-{cur.get('max')}",
                                  ss, r['statement'][:34]))
                continue
            changes[f"{r['discipline']}｜{kind}"].append(
                (f"{cur.get('min')}-{cur.get('max')}", f"G{lo}-G{hi}", r['statement'][:30]))
            r['stageHint'] = want
            stat[kind] += 1

    print()
    for k in sorted(changes):
        v = changes[k]
        print(f"  {len(v):>4}  {k}")
        for old, new, s in v[:2]:
            print(f"          {old} → {new}   {s}")
    if conflicts:
        print(f"\n  ⚠ {len(conflicts)} 条与课标学段冲突，**没有动**（页面归属可能错了，需要人判）：")
        for d, cur, ss, st in conflicts:
            print(f"      {d} 标 {cur} 但课标页说 {ss}   {st}")
    print(f"\n  {dict(stat)}")

    if a.dry_run:
        print("（--dry-run：没有写盘）")
        return
    for f, rows in files.items():
        with f.open('w', encoding='utf-8') as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + '\n')
    print("已写盘。stageHint 变了 → 必须重跑 gen_edges 的学段约束校验与 manifest")


if __name__ == '__main__':
    main()
