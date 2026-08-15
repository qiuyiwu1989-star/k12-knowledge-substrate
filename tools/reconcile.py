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
