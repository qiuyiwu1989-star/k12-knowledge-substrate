#!/usr/bin/env python3
"""
check_gold.py — 映射基准的金标还指得对吗。**离线、不需要题目原文**，进 npm run check。

金标是「这道题考的是这几条锚点」。锚点以后会被弃用、会降成 disputed ——
那时候金标还指着它，eval 就会拿一条不可引用的锚点当标准答案，
命中率悄悄变成对着一张作废的考卷打分。这道闸让它当场响，逼人重标那几题。
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
sys.dont_write_bytecode = True
from citable import CITABLE          # noqa: E402

A = {}
for f in (ROOT / 'anchors').glob('*.jsonl'):
    for l in f.open(encoding='utf-8'):
        if l.strip():
            x = json.loads(l)
            A[x['id']] = x
items = [json.loads(l) for l in (ROOT / 'bench' / 'mapping-100.jsonl').open(encoding='utf-8')]
bad = []
for it in items:
    if it['gold'] is None:
        bad.append(f"{it['qid']} 还没标")
        continue
    for g in it['gold']:
        x = A.get(g)
        if not x:
            bad.append(f"{it['qid']} → {g} 不存在")
        elif x.get('deprecated'):
            bad.append(f"{it['qid']} → {g} 已弃用")
        elif x['reviewStatus'] not in CITABLE:
            bad.append(f"{it['qid']} → {g} 已不可引用（{x['reviewStatus']}）")
        elif x['discipline'] != it['discipline']:
            bad.append(f"{it['qid']} → {g} 学科对不上（{x['discipline']} ≠ {it['discipline']}）")
if bad:
    print('✗ 映射基准的金标指向失效了，这几题要重标：')
    for b in bad[:20]:
        print('  ', b)
    sys.exit(1)
n = sum(len(it['gold']) for it in items)
print(f"✓ 映射基准 {len(items)} 题的 {n} 个金标锚点都还在、都可引用")
