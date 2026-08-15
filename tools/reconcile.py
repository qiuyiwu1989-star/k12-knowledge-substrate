#!/usr/bin/env python3
"""
reconcile.py — 机械闸与 AI 判断冲突时，机械闸赢。

AI 审查是主观判断，可判定性过滤器是确定性规则且在 CI 里真正执行。
两者冲突时（AI 说没问题、过滤器说不可判定），以过滤器为准降级为 disputed ——
否则会出现「数据在库里、CI 却红着」的僵局，最后必然有人去删规则而不是修数据。

跑在 enrich_review 之后，让流水线自愈。
"""
import json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
files = {f: [json.loads(l) for l in f.open(encoding='utf-8')]
         for f in sorted((ROOT / 'anchors').rglob('*.jsonl'))}
rows = [(f, r) for f, rs in files.items() for r in rs]

payload = '\n'.join(json.dumps({'statement': r['statement'], 'discipline': r['discipline'],
                                'id': r['id']}, ensure_ascii=False) for _, r in rows)
out = subprocess.run(['node', str(ROOT / 'scripts/decide.mjs')], input=payload,
                     capture_output=True, text=True)
if out.returncode != 0:
    sys.exit(out.stderr[:300])
verdict = {}
for l in out.stdout.split('\n'):
    if l.strip():
        j = json.loads(l)
        verdict[j['id']] = j

n = 0
for f, r in rows:
    v = verdict.get(r['id'])
    if not v or v['ok'] or r['reviewStatus'] == 'disputed':
        continue
    r['reviewStatus'] = 'disputed'
    r.setdefault('aiIssues', []).insert(0, {
        'type': 'undecidable', 'detail': '可判定性过滤器：' + '；'.join(v['reasons'])[:120],
        'by': 'decidability-gate'})
    n += 1
for f, rs in files.items():
    with f.open('w', encoding='utf-8') as fh:
        for r in rs:
            fh.write(json.dumps(r, ensure_ascii=False) + '\n')
print(f"✓ {n} 条因不过可判定性闸被降级为 disputed（AI 曾判其无问题，机械闸优先）")

# ── 弃用锚点的边要一起退休 ──────────────────────────────────
# 一条边的两端有一端被弃用，这条边就没有意义了。但不能直接删：
# 得留档，否则「这条依赖当初为什么在、为什么没了」就查不到了。
dead = {r['id'] for _, r in rows if r.get('deprecated')}
byid = {r['id']: r for _, r in rows}
G = lambda a, k: int(((a.get('stageHint') or {}).get(k) or 'G5')[1:])
retired, kept_total = [], 0
for f in sorted((ROOT / 'edges').rglob('*.jsonl')):
    es = [json.loads(l) for l in f.open(encoding='utf-8')]
    keep = []
    for e in es:
        A, P = byid.get(e['anchorId']), byid.get(e['prerequisiteId'])
        if e['anchorId'] in dead or e['prerequisiteId'] in dead:
            e['retiredBecause'] = '端点锚点已弃用'
            retired.append(e)
        # 修复会改学段，改完可能让原本合法的边变成倒挂。
        # 这不是边错了，是它依据的学段变了 —— 一样得退休，等重跑 gen_edges。
        elif A and P and G(P, 'min') > G(A, 'max'):
            e['retiredBecause'] = f"学段倒挂（修复后前置 {(P.get('stageHint') or {}).get('min')} 晚于被修 {(A.get('stageHint') or {}).get('max')}）"
            retired.append(e)
        else:
            keep.append(e)
    kept_total += len(keep)
    with f.open('w', encoding='utf-8') as fh:
        for e in keep:
            fh.write(json.dumps(e, ensure_ascii=False) + '\n')
if retired:
    rp = ROOT / 'retired'
    rp.mkdir(exist_ok=True)
    with (rp / 'edges.jsonl').open('a', encoding='utf-8') as fh:
        for e in retired:
            fh.write(json.dumps(e, ensure_ascii=False) + '\n')
print(f"✓ {len(retired)} 条边随端点弃用一起退休 → retired/edges.jsonl（留档不删档），剩 {kept_total} 条")
