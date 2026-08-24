#!/usr/bin/env python3
"""mapper_test.py — 映射器的固定用例。**不调模型**，只验粗召回。

精排要 API，不能进 CI；但粗召回是纯计算的，必须锁住 ——
它的门槛一松一紧都出过事：
  · 门槛紧：把「能计算两位数和三位数的加减法」（与查询只共享「计算」）直接丢掉，
    而它正是正确答案。
  · 门槛松：对 3,086 条全跑 O(L×len) 子串搜索，600 秒没出来。

所以这里验两件事：**正确答案必须在候选池里**，且**跑得够快**。

    python3 tools/mapper_test.py
"""
import subprocess, sys, time, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES = [
    # (查询, 学科, 学段, 必须出现在候选池里的锚点断言片段)
    ('用竖式计算 300 减 198，讲退位怎么发生，说说为什么个位不够减要向十位借',
     '数学', 'G3', '两位数和三位数的加减法'),
    ('带学生认一认万以内的数，读出来再写下来',
     '数学', None, '万以内的数'),
    ('今天带孩子去公园放风筝，风很大，孩子特别开心', '数学', None, None),   # 该 0 条
]


def run(q, disc, stage):
    cmd = [sys.executable, str(ROOT / 'tools/mapper.py'), '--file', '/dev/stdin',
           '--top', '80', '--json']
    if disc:
        cmd += ['--discipline', disc]
    if stage:
        cmd += ['--stage', stage]
    t0 = time.time()
    p = subprocess.run(cmd, input=q, capture_output=True, text=True, timeout=60)
    return json.loads(p.stdout), time.time() - t0


ok = bad = 0
for q, disc, stage, must in CASES:
    d, dt = run(q, disc, stage)
    cands = d['candidates']
    if must is None:
        good = len(cands) == 0
        desc = f'应召回 0 条，实际 {len(cands)}'
    else:
        good = any(must in c['statement'] for c in cands)
        desc = f'候选 {len(cands)} 条，{"含" if good else "**不含**"}「{must}」'
    slow = dt > 3
    if good and not slow:
        ok += 1
        print(f'  ✓ {desc}　{dt:.2f}s')
    else:
        bad += 1
        print(f'  ✗ {q[:28]}…　{desc}' + ('　**超时 %.1fs**' % dt if slow else ''))
print(f'\n{"✓" if not bad else "✗"} 映射器粗召回: {ok} 通过 / {bad} 失败')
sys.exit(1 if bad else 0)
