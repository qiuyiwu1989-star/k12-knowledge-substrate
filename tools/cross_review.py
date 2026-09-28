#!/usr/bin/env python3
"""
cross_review.py — 给「只被 DeepSeek 看过」的可引用锚点补一个别家模型的复审。

## 为什么

v1.5–v1.10 里有一批锚点，证据起草和复审是同一个模型（DeepSeek V4.1 Flash）—— mimo 额度用完时的权宜。
CHANGELOG 每次都照实记了这个弱点：同一个模型审自己写的东西偏宽。
2026-09-28 发现火山方舟 key 上能用豆包 Seed 2.0 Pro（另一家），这一轮用它复审。

## 对象

在用、可引用、reviewedBy 里有 deepseek、没有 doubao 的锚点。

## 处置（按异议的性质分，不是一律降档）

  · 没挑出问题 → reviewedBy 记上豆包，照旧可引用
  · 挑出**断言本身**的问题（not-a-capability / undecidable / truncated）→ disputed。
    两个模型意见冲突，留给人；在可引用这一侧宁可保守
  · 只挑了**字段**问题（evidence-weak，或课标没定学段时的 stage）→ 照旧可引用，挂 fieldIssues
    —— 断言不替字段背锅（schema 里 fieldIssues 那段话）
  · stage 异议课标已定学段的 → 按课标撤销（doc_stage）

    LLM_BASE=… LLM_KEY=… LLM_ENDPOINT=/chat/completions python3 tools/cross_review.py
    … python3 tools/cross_review.py --write
"""
import sys
sys.dont_write_bytecode = True

import argparse, collections, hashlib, json, os, re, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
from ai_review import SYS as REVIEW, OPEN_AT      # noqa: E402
from repair import call                           # noqa: E402
from doc_stage import split_stage_issues          # noqa: E402

REVIEWER = 'doubao-seed-2-0-pro-260215'
CACHE = TOOLS / 'out' / '.cache-xreview'
from citable import CITABLE as CIT                # noqa: E402  可引用集合只有一份定义（mappings/citable.json）
STATEMENT_LEVEL = {'not-a-capability', 'undecidable', 'truncated'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--concurrency', type=int, default=12)
    ap.add_argument('--reviewer', default=REVIEWER, help='复审模型，默认豆包')
    ap.add_argument('--both', action='store_true',
                    help='双签：配 --ids，给「另一个模型已放行」的一批再过这个模型；这边有任何异议就回 disputed（两家冲突留给人）')
    ap.add_argument('--ids', default=None, help='只复审这个文件里列的 ID（一行一个），不管 reviewedBy —— 证据刚被换过的用这个')
    ap.add_argument('--tiebreak', action='store_true',
                    help='第三判官：disputed 里只挂 undecidable、但可判定闸放行的（原审 vs 闸 冲突）。'
                         '豆包也没挑出问题 → 二比一，回 ai-reviewed；否则留 disputed')
    a = ap.parse_args()
    base, key = os.environ['LLM_BASE'], os.environ['LLM_KEY']
    REV = a.reviewer
    by = f'ai:{REV.rsplit("-", 1)[0]}-{time.strftime("%Y-%m-%d")}'
    CACHE.mkdir(exist_ok=True)

    files = {f: [json.loads(l) for l in f.read_text(encoding='utf-8').splitlines() if l.strip()]
             for f in sorted((ROOT / 'anchors').glob('*.jsonl'))}
    byid = {r['id']: r for rows in files.values() for r in rows}
    fileof = {r['id']: f.name for f, rows in files.items() for r in rows}
    edges_in = collections.defaultdict(list)
    for f in sorted((ROOT / 'edges').rglob('*.jsonl')):
        for l in f.open(encoding='utf-8'):
            e = json.loads(l)
            edges_in[e['anchorId']].append(e['prerequisiteId'])
    if a.ids:
        want = set(Path(a.ids).read_text().split())
        todo = [r for r in byid.values() if r['id'] in want and not r.get('deprecated') and r['reviewStatus'] in CIT]
    elif a.tiebreak:
        import subprocess
        cand = [r for r in byid.values() if not r.get('deprecated') and r['reviewStatus'] == 'disputed'
                and {x['type'] for x in r.get('aiIssues') or [] if x['type'] != 'resolved'} == {'undecidable'}
                and not any(str(x.get('by', '')).startswith('rule:') for x in r.get('aiIssues') or [])]
        p = subprocess.run(['node', str(ROOT / 'scripts/lib/check-stdin.mjs')],
                           input='\n'.join(r['statement'] for r in cand), capture_output=True, text=True)
        vs = [json.loads(l) for l in p.stdout.splitlines()]
        assert len(vs) == len(cand)
        todo = [r for r, v in zip(cand, vs) if v.get('ok')]
    else:
      todo = [r for r in byid.values()
            if not r.get('deprecated') and r['reviewStatus'] in CIT
            and any('deepseek' in x for x in r.get('reviewedBy') or [])
            and not any('doubao' in x for x in r.get('reviewedBy') or [])]
    print(f'复审 {len(todo)} 条')

    def work(r):
        d = r['discipline']
        lo, hi = OPEN_AT[d]
        sysp = REVIEW.format(disc=d, open_at=f'{lo}–{hi} 年级')
        pres = [byid[p]['statement'] for p in edges_in.get(r['id'], [])[:5] if p in byid]
        user = (f"能力断言：{r['statement']}\n"
                f"领域：{r.get('strand') or '未标注'}\n"
                f"标注学段：{(r.get('stageHint') or {}).get('min','?')}–{(r.get('stageHint') or {}).get('max','?')}\n"
                f"掌握证据：{' / '.join((r.get('evidence') or [])[:3]) or '（无）'}\n"
                f"已标的直接前置：{' / '.join(pres) if pres else '（无）'}\n"
                f"来源：{d}课标 第 {(r.get('provenance') or {}).get('srcPage','?')} 页")
        h = hashlib.sha256((REV + sysp + user).encode()).hexdigest()[:24]
        cf = CACHE / f'{h}.json'
        if cf.exists():
            return r, json.loads(cf.read_text(encoding='utf-8'))
        for _ in range(3):
            try:
                txt = call(sysp, user, base, key, REV)
            except Exception as e:
                return r, {'error': str(e)[:60]}
            m = re.search(r'\{.*\}', txt or '', re.S)
            try:
                o = json.loads(m.group(0)) if m else None
            except Exception:
                o = None
            if isinstance(o, dict) and isinstance(o.get('issues'), list):
                cf.write_text(json.dumps(o, ensure_ascii=False), encoding='utf-8')
                return r, o
        return r, {'error': '解析失败'}

    stat, kinds, samples = collections.Counter(), collections.Counter(), collections.defaultdict(list)
    with ThreadPoolExecutor(a.concurrency) as ex:
        res = list(ex.map(work, todo))
    for r, o in res:
        if o.get('error'):
            stat['复审调用失败 → 不动'] += 1
            continue
        iss = [x for x in o['issues'] if isinstance(x, dict) and x.get('type')]
        iss, wd, why = split_stage_issues(r, fileof[r['id']], iss)
        types = {x['type'] for x in iss}
        for t in types:
            kinds[t] += 1
        if types & STATEMENT_LEVEL:
            k = '断言本身有异议 → disputed'
        elif types:
            k = '只有字段异议（' + '、'.join(sorted(types)) + '）→ 仍可引用，挂 fieldIssues'
        else:
            k = '没挑出问题 → 记上豆包'
        if a.both:
            k = '双签通过' if not types else '双签不过（' + '、'.join(sorted(types)) + '）→ 回 disputed'
            stat[k] += 1
            samples[k].append((r, iss))
            if a.write and types:
                r['reviewStatus'] = 'disputed'
                r['aiIssues'] = [dict(x, by=by) for x in iss[:5]] + \
                    [x for x in (r.get('aiIssues') or []) if x['type'] == 'resolved']
            if a.write and not types:
                r['reviewedBy'] = sorted(set((r.get('reviewedBy') or []) + [by]))
            continue
        if a.tiebreak:
            k = '第三判官也没挑出问题 → 二比一，回 ai-reviewed' if not types else \
                '第三判官只说证据弱 → 断言异议二比一撤销，换挂 evidence-weak（交给 evfix_round2）' \
                if types == {'evidence-weak'} else \
                '第三判官也有异议（' + '、'.join(sorted(types)) + '）→ 留 disputed'
        stat[k] += 1
        samples[k].append((r, iss))
        if not a.write:
            continue
        if a.tiebreak:
            r['reviewedBy'] = sorted(set((r.get('reviewedBy') or []) + [by]))
            ev = r.get('evidence') or []
            weak_ev = (not ev) or bool(re.match(r'^能在.{1,10}课堂或作业情境中完成', str(ev[0]))) or not r.get('assessment')
            if not types and weak_ev:
                types = {'evidence-weak'}      # 断言没问题，但证据是兜底模板 / 缺问句：可引用的硬条件（F202/F206）不满足
                iss = [{'type': 'evidence-weak', 'detail': '证据是兜底模板或缺家长问句'}]
            if not types:
                old = next((x for x in r['aiIssues'] if x['type'] == 'undecidable'), {})
                r['aiIssues'] = [x for x in r['aiIssues'] if x['type'] == 'resolved'] + [{
                    'type': 'resolved', 'by': by,
                    'detail': f"原异议 undecidable（{old.get('detail', '')[:50]}）：可判定闸放行、"
                              f"第三个判官（豆包）也没挑出问题，二比一撤销"}]
                r['reviewStatus'] = 'ai-reviewed'
            elif types == {'evidence-weak'}:
                old = next((x for x in r['aiIssues'] if x['type'] == 'undecidable'), {})
                r['aiIssues'] = [dict(iss[0], by=by)] + [x for x in r['aiIssues'] if x['type'] == 'resolved'] + [{
                    'type': 'resolved', 'by': by,
                    'detail': f"原异议 undecidable（{old.get('detail', '')[:50]}）：可判定闸放行、第三个判官（豆包）"
                              f"对断言没有异议，二比一撤销；它只说证据弱，换挂 evidence-weak"}]
            continue
        r['reviewedBy'] = sorted(set((r.get('reviewedBy') or []) + [by]))
        if types & STATEMENT_LEVEL:
            r['reviewStatus'] = 'disputed'
            r['aiIssues'] = [dict(x, by=by) for x in iss[:5]] + \
                [x for x in (r.get('aiIssues') or []) if x['type'] == 'resolved']
        elif types:
            fi = set(r.get('fieldIssues') or []) | {t for t in types if t in ('evidence-weak', 'stage')}
            r['fieldIssues'] = sorted(fi)
    for k, n in sorted(stat.items(), key=lambda t: -t[1]):
        print(f'  {n:>4}  {k}')
    print('  异议类型：', dict(kinds.most_common()))
    for r, iss in (samples['断言本身有异议 → disputed'] + [y for k, v in samples.items() if '留 disputed' in k for y in v])[:6]:
        print(f"    {r['id']} [{r['discipline']}] {r['statement'][:34]} ← {iss[0]['type']}：{iss[0].get('detail','')[:60]}")
    if not a.write:
        print('（没写盘；加 --write 写回）')
        return
    for f, rows in files.items():
        f.write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in rows), encoding='utf-8')
    print(f'已写回，reviewedBy 记为 {by}')


if __name__ == '__main__':
    main()
