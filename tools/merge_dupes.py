#!/usr/bin/env python3
"""
merge_dupes.py — 合并「同一事实、不同语序」的重复锚点。

**为什么去重签名抓不到。** 签名是 (学科, 动词, 对象)，而这类重复的对象字面不同：

    能说出已知最早的汉字是甲骨文
    能说出甲骨文是已知最早的汉字      ← 同一个事实，主宾对调

签名不同 → 两条都入库 → 同一件事有了两个 ID。这正是底座最该避免的：
档案引用了其中一个，另一个就成了同一件事的第二个坐标。
（Marble 就死在同名冲突上 —— 21 组完全同名、75 组基名冲突。）

**判据：实词集合完全相同（Jaccard = 1.00）。**
差一个字就到不了 1.00 —— 「制作**植物**细胞临时装片」和「制作**动物**细胞临时装片」
是 0.94，不会被误合。这个严格性是有意的：合错比不合更坏。

弃用的一方填 supersededBy 而不是 dropReason —— 这是**有替代者**的弃用，
已有的档案引用必须能解析到留下的那一条。

    python3 tools/merge_dupes.py [--write]
"""
import argparse, collections, glob, itertools, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STOP = set('的了和与及或在中对能会把被为是有个之其等这那所以并且但')


def content(s):
    return {c for c in s.replace('能说出', '', 1) if '一' <= c <= '鿿'} - STOP


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--write', action='store_true')
    a = ap.parse_args()

    files = {}
    live = []
    for f in sorted((ROOT / 'anchors').glob('*.jsonl')):
        arr = [json.loads(l) for l in f.open(encoding='utf-8') if l.strip()]
        files[f.name] = arr
        live += [x for x in arr if not x.get('deprecated')]

    bysub = collections.defaultdict(list)
    for x in live:
        bysub[x['discipline']].append(x)

    # 并查集：A≡B、B≡C 时三条要归成一组
    parent = {}
    def find(i):
        parent.setdefault(i, i)
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    pairs = 0
    for v in bysub.values():
        for x, y in itertools.combinations(v, 2):
            cx, cy = content(x['statement']), content(y['statement'])
            if not cx or not cy:
                continue
            if cx == cy:                      # Jaccard 恰好 1.00
                union(x['id'], y['id']); pairs += 1

    groups = collections.defaultdict(list)
    byid = {x['id']: x for x in live}
    for i in parent:
        groups[find(i)].append(byid[i])

    print(f"实词集合完全相同的锚点对 {pairs} 组 → 归并成 {len(groups)} 簇")
    plan = {}
    for g in groups.values():
        # 留最长的那条 —— 它通常信息最全；平手时留 ID 字典序小的，结果可复现
        keep = sorted(g, key=lambda x: (-len(x['statement']), x['id']))[0]
        for x in g:
            if x['id'] != keep['id']:
                plan[x['id']] = keep['id']
        print(f"\n  留：{keep['statement'][:46]}")
        for x in g:
            if x['id'] != keep['id']:
                print(f"  并：{x['statement'][:46]}")

    print(f"\n合计弃用 {len(plan)} 条，全部填 supersededBy")
    if not a.write:
        print("（未落盘。确认无误后加 --write）")
        return

    n = 0
    for fname, arr in files.items():
        touched = False
        for x in arr:
            if x['id'] in plan:
                x['deprecated'] = True
                x['supersededBy'] = plan[x['id']]
                x['dropReason'] = '与保留的那条表达同一事实（实词集合完全相同，仅语序/标点不同）'
                touched = True; n += 1
        if touched:
            with (ROOT / 'anchors' / fname).open('w', encoding='utf-8') as f:
                for x in arr:
                    f.write(json.dumps(x, ensure_ascii=False) + '\n')

    # 边要迁移到保留的那一端，不是删掉 —— 关系还在，只是端点换了个 ID
    moved = 0
    for f in sorted((ROOT / 'edges').glob('*.jsonl')):
        arr = [json.loads(l) for l in f.open(encoding='utf-8') if l.strip()]
        seen, keep = set(), []
        for e in arr:
            for k in ('anchorId', 'prerequisiteId'):
                if e[k] in plan:
                    e[k] = plan[e[k]]; moved += 1
            if e['anchorId'] == e['prerequisiteId']:      # 合并后自环，丢掉
                continue
            sig = (e['prerequisiteId'], e['anchorId'])
            if sig in seen:                               # 合并后重边，丢掉
                continue
            seen.add(sig); keep.append(e)
        with f.open('w', encoding='utf-8') as fh:
            for e in keep:
                fh.write(json.dumps(e, ensure_ascii=False) + '\n')

    # 清单的 anchorIds 也要跟着迁
    for f in sorted(ROOT.glob('lists/**/*.jsonl')):
        arr = [json.loads(l) for l in f.open(encoding='utf-8') if l.strip()]
        t = False
        for x in arr:
            ids = x.get('anchorIds') or []
            new = [plan.get(i, i) for i in ids]
            if new != ids:
                x['anchorIds'] = list(dict.fromkeys(new)); t = True
        if t:
            with f.open('w', encoding='utf-8') as fh:
                for x in arr:
                    fh.write(json.dumps(x, ensure_ascii=False) + '\n')

    print(f"✓ 弃用 {n} 条并填 supersededBy；边端点迁移 {moved} 处（不是删边 —— 关系还在）")


if __name__ == '__main__':
    main()
