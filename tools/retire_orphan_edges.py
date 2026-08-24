#!/usr/bin/env python3
"""
retire_orphan_edges.py — 退休端点已弃用的边，并清理合并留下的环与倒挂。

**为什么要有这个工具。** 弃用锚点必然留下悬空边，这是弃用操作的固有副作用。
我在一次会话里手工写了四遍同样的退休逻辑 —— 每次都是校验器先报错、再回头补。
第四次之后写成工具：任何弃用/合并之后跑一次，不必再想着它。

三件事一起做，顺序不能换：
  1. 退休端点已弃用的边
  2. 退休学段倒挂的边（合并可能让先修变得晚于被修）
  3. 退休成环的边（两条锚点合并成一条后，各自的边可能首尾相接）

全部**退休留档**而不是删除 —— 关系当初为什么建立，得查得到。

    python3 tools/retire_orphan_edges.py
"""
import collections, glob, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    A = {}
    for f in sorted((ROOT / 'anchors').glob('*.jsonl')):
        for l in f.open(encoding='utf-8'):
            if l.strip():
                a = json.loads(l); A[a['id']] = a
    dead = {k for k, v in A.items() if v.get('deprecated')}

    def grade(i, k):
        h = (A.get(i, {}).get('stageHint') or {})
        try:
            return int(str(h.get(k, ''))[1:])
        except Exception:
            return None

    files = {f: [json.loads(l) for l in open(f, encoding='utf-8') if l.strip()]
             for f in sorted(glob.glob(str(ROOT / 'edges/*.jsonl')))}
    allE = [e for arr in files.values() for e in arr]

    drop = {}
    for e in allE:
        a, b = e['prerequisiteId'], e['anchorId']
        if a in dead or b in dead:
            drop[(a, b)] = '端点锚点已弃用'
            continue
        if a not in A or b not in A:
            drop[(a, b)] = '端点锚点不存在'
            continue
        pmin, bmax = grade(a, 'min'), grade(b, 'max')
        if pmin and bmax and pmin > bmax:
            drop[(a, b)] = f'学段倒挂：先修 G{pmin}+ 晚于被修 G{bmax}'
        # 同学科内 LIST 档不能当前置 —— 字表词表篇目是覆盖模型，
        # 没有「学完这个才能学那个」的语义（validate 里有对应硬闸）。
        # 2026-08-22 加：修好 gen_edges 「拿第一条锚点判整个学科」的 bug 之后，
        # 英语/语文第一次进入建边流程，候选池里的 LIST 锚点当场撞上这条闸。
        # 退休归它管 —— 我一度在 edges/ 里原地标 retired，而 validate 根本不看那个字段，
        # **这个仓库的退休约定是搬进 retired/，不是原地打标**。
        if (A.get(a, {}).get('track') == 'LIST'
                and A.get(a, {}).get('discipline') == A.get(b, {}).get('discipline')
                and not any(v.get('kind') == 'set-containment' for v in (e.get('evidence') or []))):
            drop[(a, b)] = '同学科内 LIST 档当前置（覆盖模型没有先后语义）'

    # 去环要在前两步之后 —— 前面丢掉的边可能本来就把环拆开了
    adj = collections.defaultdict(list)
    for e in allE:
        k = (e['prerequisiteId'], e['anchorId'])
        if k not in drop:
            adj[k[0]].append(k[1])
    color = collections.defaultdict(int)
    sys.setrecursionlimit(50000)

    def dfs(u):
        color[u] = 1
        for v in adj[u]:
            if color[v] == 1:
                drop[(u, v)] = '成环'
            elif color[v] == 0:
                dfs(v)
        color[u] = 2

    for n in list(adj):
        if color[n] == 0:
            dfs(n)

    retired = []
    for f, arr in files.items():
        keep = []
        for e in arr:
            k = (e['prerequisiteId'], e['anchorId'])
            if k in drop:
                e['retiredReason'] = drop[k]; retired.append(e)
            else:
                keep.append(e)
        with open(f, 'w', encoding='utf-8') as fh:
            for e in keep:
                fh.write(json.dumps(e, ensure_ascii=False) + '\n')

    p = ROOT / 'retired/edges.jsonl'
    p.parent.mkdir(exist_ok=True)
    old = [json.loads(l) for l in p.open(encoding='utf-8')] if p.exists() else []
    with p.open('w', encoding='utf-8') as fh:
        for e in old + retired:
            fh.write(json.dumps(e, ensure_ascii=False) + '\n')

    n = sum(1 for f in files for l in open(f, encoding='utf-8') if l.strip())
    by = collections.Counter(drop.values())
    print(f"退休 {len(retired)} 条 → 存活边 {n}（留档 {len(old) + len(retired)} 条）")
    for k, v in by.most_common():
        print(f"  {v:>4}  {k}")


if __name__ == '__main__':
    main()
