#!/usr/bin/env python3
"""
fix_srctext.py — 修高中锚点里挂错/吞整段的 provenance.srcText。

## 这不是「引文太长」，是引文挂错了

    断言：能分析人们进行技术选择的原因
    引文：3,684 字，开头是「完善课程评价，不断探索通用技术多元评价体系建设…」

那段是课程评价建议，跟这条断言毫无关系。**溯源链在这 122 条上是断的** ——
而「每条都能翻回教育部文件某一页」是这个底座唯一比 Marble 强的地方。

## 根因

`gaozhong_extract.py` 对无编号版式用「一段即一条要求」，遇到大段散文时
`flush_prose()` 把整块正文当成了一条的出处。落库时 srcText 原样带过来，
一条断言就挂上了一整页文本。

## 修法：从那段里找回真正的那一句

`gaozhong_commit.py` 是**从 srcText 拆句得到 statement 的**，所以那一句
必然还在 srcText 里。按字面覆盖率把它找回来即可 —— **纯机械，不调模型**：

  1. 把 srcText 按句末标点切成句子
  2. 找与 statement 实义字重合最高的那一句（statement 前面可能补过「能」字）
  3. 覆盖率够高才替换，不够就**保留原样并标记**，不硬凑

不够高的宁可留着长引文：**挂错的引文至少能看出错，挂上一句像模像样
但其实不对的引文，看不出来。**

    python3 tools/fix_srctext.py --dry-run
    python3 tools/fix_srctext.py
"""
import argparse, collections, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIMIT = 300          # 超过这个长度就认为吞了整段
STOP = set('的了和与或在是有能会对为以及等这那其中一个可以进行并且或者通过根据')


def chars(s):
    return {c for c in s if '一' <= c <= '鿿'} - STOP


def best_sentence(stmt, src):
    """从 src 里挑与 stmt 重合最高的一句。返回 (句子, 覆盖率)。"""
    sents = [x.strip() for x in re.split(r'(?<=[。？！；])', src) if len(x.strip()) >= 8]
    if not sents:
        return None, 0.0
    a = chars(stmt)
    if not a:
        return None, 0.0
    best, score = None, 0.0
    for s in sents:
        r = len(a & chars(s)) / len(a)
        if r > score:
            best, score = s, r
    # 相邻两句合起来更完整的情况：断言可能横跨一个句号
    for i in range(len(sents) - 1):
        pair = sents[i] + sents[i + 1]
        if len(pair) > 220:
            continue
        r = len(a & chars(pair)) / len(a)
        if r > score:
            best, score = pair, r
    return best, score


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--threshold', type=float, default=0.75)
    a = ap.parse_args()

    files = {f: [json.loads(l) for l in f.open(encoding='utf-8') if l.strip()]
             for f in sorted((ROOT / 'anchors').glob('*.jsonl'))}
    targets = [(f, i, x) for f, arr in files.items() for i, x in enumerate(arr)
               if not x.get('deprecated')
               and len((x.get('provenance') or {}).get('srcText') or '') > LIMIT]
    print(f"引文 >{LIMIT} 字的 {len(targets)} 条")
    print(f"  {dict(collections.Counter(x['discipline'] for _, _, x in targets).most_common(6))}")

    fixed, kept = [], []
    for f, i, x in targets:
        src = x['provenance']['srcText']
        s, r = best_sentence(x['statement'], src)
        (fixed if (s and r >= a.threshold) else kept).append((f, i, x, s, r))

    print(f"\n找回原句 {len(fixed)} 条 · 覆盖率不足保留原样 {len(kept)} 条")
    print(f"  阈值 {a.threshold}。不够就留着长引文 —— "
          f"挂错的引文看得出错，挂上一句似是而非的看不出来。")

    print("\n─── 修好的样本 ───")
    for f, i, x, s, r in fixed[:5]:
        print(f"  断言：{x['statement'][:46]}")
        print(f"  原引文 {len(x['provenance']['srcText'])} 字 → {len(s)} 字（覆盖 {r:.2f}）")
        print(f"    {s[:76]}")
        print()
    if kept:
        print("─── 没修的样本（覆盖率不足）───")
        for f, i, x, s, r in kept[:3]:
            print(f"  断言：{x['statement'][:44]}")
            print(f"  最佳候选覆盖率仅 {r:.2f}：{(s or '')[:56]}")

    if a.dry_run:
        print("\n（--dry-run：没有写盘）")
        return

    for f, i, x, s, r in fixed:
        p = files[f][i]['provenance']
        p['srcTextFull'] = len(p['srcText'])      # 留个痕：原来吞了多少字
        p['srcText'] = s
        p['srcTextFix'] = {'method': 'best-sentence', 'coverage': round(r, 2)}
    for f, i, x, s, r in kept:
        # 标出来，别让它静悄悄留着
        files[f][i]['provenance']['srcTextOversized'] = True
    for f, arr in files.items():
        with f.open('w', encoding='utf-8') as fh:
            for x in arr:
                fh.write(json.dumps(x, ensure_ascii=False) + '\n')
    print(f"\n已修 {len(fixed)} 条 · 标记 {len(kept)} 条为 srcTextOversized（待复核时人工挑出）")
    print("下一步：npm run check")


if __name__ == '__main__':
    main()
