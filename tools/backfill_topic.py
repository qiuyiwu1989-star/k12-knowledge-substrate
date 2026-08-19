#!/usr/bin/env python3
"""
backfill_topic.py — 从课标页级目录补 MATRIX 的 topic（内容主题）。

## topic 不是我们编的，是课标目录里的

961 条 MATRIX 缺 topic。我一度以为只能靠模型按学科主题体系归类 ——
**那样编出来的主题名会污染「每条都能翻回课标」这条链**。

后来在 `tools/out/page-index.jsonl` 里找到了真东西：抽取时逐页记过
`domain` 字段，取值就是课标自己的主题（球类运动 / 物质的组成与结构 /
中国古代史 / 认识中国）。373 页有 domain。

锚点已经 100% 带 `srcPage`（上一步刚补完），**按 (学科, 页码) join 即可**。

## 只 join，不外推

- 该页没有 domain → 留空。**不往前/往后找最近的一页** ——
  那等于假设主题在页间连续，而课标里一页可能跨两个主题。
  猜错的主题比空着更糟：它看起来像课标说的。
- 转写层从 `derivedFrom` 的源锚点继承（同一处课标的两种说法）。
- 补上的都标 `topicFrom`，来源可查、可单独撤。

    python3 tools/backfill_topic.py --dry-run
    python3 tools/backfill_topic.py
"""
import argparse, collections, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IDX = ROOT / 'tools/out/page-index.jsonl'

# domain 里混着「学科名本身」这类无信息量的值，当主题没意义
def useless(d, subject):
    return (not d) or d == subject or len(d) < 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    if not IDX.exists():
        raise SystemExit(f'缺 {IDX} —— 那是抽取时的页级目录，主题从它来')
    idx = {}
    for l in IDX.open(encoding='utf-8'):
        if not l.strip():
            continue
        r = json.loads(l)
        d, s, p = r.get('domain'), r.get('subject'), r.get('page')
        if s and p and not useless(d, s):
            idx[(s, p)] = d
    print(f"页级目录里 {len(idx)} 个 (学科, 页码) → 主题")

    files = {f: [json.loads(l) for l in f.open(encoding='utf-8') if l.strip()]
             for f in sorted((ROOT / 'anchors').glob('*.jsonl'))}
    live = [x for arr in files.values() for x in arr if not x.get('deprecated')]
    byid = {x['id']: x for x in live}

    hit, inherit, miss = [], [], []
    for f, arr in files.items():
        for i, x in enumerate(arr):
            if x.get('deprecated') or x['track'] != 'MATRIX' or x.get('topic'):
                continue
            p = x.get('provenance') or {}
            t = idx.get((x['discipline'], p.get('srcPage')))
            if t:
                hit.append((f, i, t))
                continue
            df = p.get('derivedFrom')
            st = (byid.get(df) or {}).get('topic') if df else None
            if st:
                inherit.append((f, i, st, df))
            else:
                miss.append(x)

    print(f"\n  按页码命中课标目录  {len(hit)} 条")
    print(f"  转写层从源锚点继承  {len(inherit)} 条")
    print(f"  该页没有主题，留空  {len(miss)} 条")
    if miss:
        print("    " + str(dict(collections.Counter(x['discipline'] for x in miss).most_common(6))))
    if hit:
        print("\n  ─── 样本 ───")
        for f, i, t in hit[:6]:
            x = files[f][i]
            print(f"    [{x['discipline']}] p{x['provenance']['srcPage']} → 《{t}》")
            print(f"      {x['statement'][:50]}")

    if a.dry_run:
        print("\n（--dry-run：没有写盘）")
        return
    for f, i, t in hit:
        files[f][i]['topic'] = t
        files[f][i]['topicFrom'] = 'curriculum-page-index'
    for f, i, t, df in inherit:
        files[f][i]['topic'] = t
        files[f][i]['topicFrom'] = f'inherit:{df}'
    if hit or inherit:
        for f, arr in files.items():
            with f.open('w', encoding='utf-8') as fh:
                for x in arr:
                    fh.write(json.dumps(x, ensure_ascii=False) + '\n')
    print(f"\n已补 {len(hit) + len(inherit)} 条 topic")
    print("下一步：npm run check")


if __name__ == '__main__':
    main()
