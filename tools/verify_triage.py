#!/usr/bin/env python3
"""
verify_triage.py — 把独立验证的结果分级处理。

**为什么不能按存疑直接删。**

独立验证标出 244 条存疑。我亲自判了 12 条，误报率：
  硬存疑（独立路径一条事实都抽不出）235 条 → 约 17% 误报
  软存疑（抽出了但对不上）           9 条 → 约 67% 误报（公式没汉字、长句被拆）

按存疑直接删 235 条，会错杀约 40 条好数据。所以分三级：

  ① 能写出机械判据的坏模式  → **弃用**（留档）
  ② 其余硬存疑              → **降级** ai-adjudicated → ai-reviewed
                              退出可用集合，但不弃用 —— 它们可能是对的，
                              只是没通过独立验证，该由人来判
  ③ 软存疑                  → 只进复核队列，不动状态（误报率太高）

判据来自我实际判错的那几条，不是想象出来的：

  循环定义   「X 的方式和习惯是养成 X 的方式和习惯」—— 主宾高度重叠
  无标准答案 「能说出蜗牛的家应该是什么样的」—— 原文是「讨论…」，本就没答案
  工具变定义 「在线课堂是进行线上学习与交流的平台」← 原文「利用在线课堂进行学习交流」
  编造关系   「平等待人的意义是懂得谦让」← 原文是并列「理解意义，懂得谦让」

    python3 tools/verify_triage.py [--write]
"""
import argparse, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

NO_ANSWER = re.compile(r'(是什么样的|有哪些|怎么样|如何[^，。]{0,6}$|应该是)')
DISCUSS_SRC = re.compile(r'讨论|探讨|交流|说一说|想一想|议一议')
TOOL_DEF = re.compile(r'是(进行|用于|用来|开展)[^，。]{2,}的(平台|工具|方式|方法|途径|手段)')
ARRANGE2 = re.compile(r'\d\s*[~～-]\s*\d\s*年级(注重|主要|侧重)|注重让学生|经历一系列')


def content_chars(s):
    stop = set('的了和与及或在中对能会把被为是有个之其等这那所以并且但')
    return {c for c in s if '一' <= c <= '鿿'} - stop


def circular(stmt):
    """主宾高度重叠 = 循环定义，问了等于没问"""
    body = stmt.replace('能说出', '', 1)
    m = re.search(r'^(.{4,}?)是(.{4,})$', body)
    if not m:
        return False
    a, b = content_chars(m.group(1)), content_chars(m.group(2))
    if not a or not b:
        return False
    return len(a & b) / min(len(a), len(b)) >= 0.75


def invented_relation(stmt, src):
    """断言声称「X的A是B」，但原文里 X 和 B 是并列关系不是判断关系"""
    m = re.search(r'的(意义|作用|目的|价值|危害|好处|特点)是(.{3,})', stmt)
    if not m:
        return False
    # 原文里那个抽象名词后面紧跟的是逗号顿号（并列），不是「是」
    kw = m.group(1)
    return bool(re.search(kw + r'[，,、]', src))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--write', action='store_true')
    a = ap.parse_args()

    rows = json.loads((ROOT / 'tools/out/verify-report.json').read_text(encoding='utf-8'))
    hard = {r['id']: r for r in rows if r['suspect'] and not r['independentFacts']}
    soft = {r['id']: r for r in rows if r['suspect'] and r['independentFacts']}

    drop, reasons = {}, {}
    for rid, r in hard.items():
        st, src = r['statement'], r['srcText']
        why = None
        if circular(st):
            why = '循环定义：主语和宾语高度重叠，问了等于没问'
        elif NO_ANSWER.search(st) or DISCUSS_SRC.search(src):
            why = '没有标准答案：原文是「讨论/探讨」类活动，不是可判定的事实'
        elif TOOL_DEF.search(st):
            why = '把工具用法编成了定义：原文是「利用X做Y」，断言写成「X是做Y的平台/工具」'
        elif invented_relation(st, src):
            why = '编造关系：原文里是并列（「理解意义，懂得谦让」），断言写成了判断（「意义就是谦让」）'
        elif ARRANGE2.search(st):
            why = '课程编排说明，不是学生能力（抽取阶段过滤漏网）'
        if why:
            drop[rid] = why

    downgrade = {rid for rid in hard if rid not in drop}

    print(f"独立验证存疑 {len(hard) + len(soft)} 条")
    print(f"  ① 弃用（有机械判据的坏模式）  {len(drop)}")
    import collections
    for w, n in collections.Counter(drop.values()).most_common():
        print(f"      {n:>4}  {w[:44]}")
    print(f"  ② 降级 ai-adjudicated → ai-reviewed（退出可用，不弃用）  {len(downgrade)}")
    print(f"  ③ 只进复核队列，不动状态（软存疑，误报率 ~67%）  {len(soft)}")

    if not a.write:
        print("\n（未落盘。确认无误后加 --write）")
        return

    n_drop = n_down = 0
    for f in sorted((ROOT / 'anchors').glob('*.jsonl')):
        arr = [json.loads(l) for l in f.open(encoding='utf-8') if l.strip()]
        touched = False
        for x in arr:
            if x['id'] in drop:
                x['deprecated'] = True
                x['dropReason'] = '独立验证不通过 —— ' + drop[x['id']]
                touched = True; n_drop += 1
            elif x['id'] in downgrade:
                x['reviewStatus'] = 'ai-reviewed'
                x.setdefault('adjudication', {})['downgradedBy'] = (
                    '独立验证：模型只读原文（看不到本断言）时，抽不出任何支持它的事实。'
                    '可能只是角度不同（实测误报率约 17%），所以降级而不是弃用，交由人判。')
                touched = True; n_down += 1
        if touched:
            with f.open('w', encoding='utf-8') as fh:
                for x in arr:
                    fh.write(json.dumps(x, ensure_ascii=False) + '\n')
    print(f"\n✓ 弃用 {n_drop} 条（留档），降级 {n_down} 条")


if __name__ == '__main__':
    main()
