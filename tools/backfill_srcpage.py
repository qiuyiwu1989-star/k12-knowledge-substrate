#!/usr/bin/env python3
"""
backfill_srcpage.py — 把抽取时记了、落库时没带过去的 srcPage 补回来。

## 页码不是丢了，是没带过去

469 条义务教育锚点缺 `provenance.srcPage`，而抽取的中间产物
（`tools/out/*-neirong.jsonl`、`*-candidates.json`）里**每条都记着 page**。
落库工具当时只搬了 srcText，没搬页码。

页码是溯源链的最后一环 —— 有引文没页码，看的人得在 1,594 页里自己找那句话。

## 匹配方式：srcText 精确相等

**不做模糊匹配。** 页码错比页码空更糟：空着人知道要自己找，
错了人会翻到那一页发现对不上，然后开始怀疑整批数据。
所以只认 srcText 完全相同的，匹配不上就留空。

转写层（capability-rewrite）的页码从 `derivedFrom` 指向的源锚点继承 ——
它们本来就是同一处课标的两种说法。

    python3 tools/backfill_srcpage.py --dry-run
    python3 tools/backfill_srcpage.py
"""
import argparse, collections, glob, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_pages():
    """从中间产物建 srcText → page 的索引。同一句出现在多页则丢弃（歧义）。"""
    idx, dup = {}, set()
    def put(text, page, subj):
        # 中间产物的 value 有时是列表（一个 key 下多条）—— 摊平，别在这里崩。
        if isinstance(text, list):
            for t in text:
                put(t, page, subj)
            return
        if not isinstance(text, str) or not text.strip() or not page:
            return
        k = (subj, text.strip())
        if k in idx and idx[k] != page:
            dup.add(k)
        idx[k] = page
    for f in glob.glob(str(ROOT / 'tools/out/*-neirong.jsonl')):
        subj = Path(f).stem.replace('-neirong', '')
        for l in open(f, encoding='utf-8'):
            if l.strip():
                r = json.loads(l)
                put(r.get('value'), r.get('page'), subj)
    for f in glob.glob(str(ROOT / 'tools/out/*-candidates.json')):
        subj = Path(f).stem.replace('-candidates', '')
        try:
            d = json.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        for r in (d if isinstance(d, list) else d.get('items') or []):
            put(r.get('srcText'), r.get('page'), r.get('discipline') or subj)
    for k in dup:
        idx.pop(k, None)          # 同一句多页 → 歧义，宁可留空
    return idx, len(dup)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    idx, ndup = load_pages()
    print(f"中间产物里 {len(idx)} 条 (学科,原文) → 页码（丢弃 {ndup} 条歧义的）")

    files = {f: [json.loads(l) for l in f.open(encoding='utf-8') if l.strip()]
             for f in sorted((ROOT / 'anchors').glob('*.jsonl'))}
    live = [x for arr in files.values() for x in arr if not x.get('deprecated')]
    byid = {x['id']: x for x in live}

    direct, inherit, miss = [], [], []
    for f, arr in files.items():
        for i, x in enumerate(arr):
            if x.get('deprecated'):
                continue
            p = x.get('provenance') or {}
            if p.get('srcPage'):
                continue
            src = (p.get('srcText') or '').strip()
            hit = idx.get((x['discipline'], src)) if src else None
            if hit:
                direct.append((f, i, hit))
                continue
            # 转写层：从源锚点继承
            df = p.get('derivedFrom')
            sp = ((byid.get(df) or {}).get('provenance') or {}).get('srcPage') if df else None
            if sp:
                inherit.append((f, i, sp, df))
            else:
                miss.append(x)

    print(f"\n  原文精确命中中间产物  {len(direct)} 条")
    print(f"  转写层从源锚点继承    {len(inherit)} 条")
    print(f"  仍然补不上            {len(miss)} 条")
    if miss:
        print("    " + str(dict(collections.Counter(x['discipline'] for x in miss).most_common(5))))

    if a.dry_run:
        print("\n（--dry-run：没有写盘）")
        return

    for f, i, page in direct:
        files[f][i]['provenance']['srcPage'] = page
        files[f][i]['provenance']['srcPageFrom'] = 'extract-intermediate'
    for f, i, page, df in inherit:
        files[f][i]['provenance']['srcPage'] = page
        files[f][i]['provenance']['srcPageFrom'] = f'inherit:{df}'
    if direct or inherit:
        for f, arr in files.items():
            with f.open('w', encoding='utf-8') as fh:
                for x in arr:
                    fh.write(json.dumps(x, ensure_ascii=False) + '\n')
    print(f"\n已补 {len(direct) + len(inherit)} 条 srcPage")
    print("下一步：npm run check")


if __name__ == '__main__':
    main()
