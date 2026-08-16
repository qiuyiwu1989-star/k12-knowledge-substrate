#!/usr/bin/env python3
"""
stage_by_page.py — 建「学科 + 页码 → 学段」映射，用前向填充。

课程内容一节是按学段分块排的：「第一学段（1～2年级）」这个标题之后的所有页，
一直到下一个学段标题为止，都属于第一学段。页索引里已经有 86 个这样的标题，
之前完全没用上 —— 162 条内容要求锚点里 139 条落成了 G1-G9 默认值，
把源文本明明给了的学段信息白白丢了。

模型自报的学段优先（它看得到本页的小标题），页码映射兜底。

    python3 tools/stage_by_page.py            # 打印覆盖率
    from stage_by_page import build           # 给流水线用
"""
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STAGE_PAT = re.compile(r'第([一二三四])学段|(\d)\s*[~～-]\s*(\d)\s*年级')
CN = {'一': 'G1-2', '二': 'G3-4', '三': 'G5-6', '四': 'G7-9'}


def norm_stage(s):
    """把各种写法归一成 G1-2 / G3-4 / G5-6 / G7-9，认不出返回 None"""
    if not s:
        return None
    s = str(s).strip()
    m = re.fullmatch(r'G?(\d)\s*[-~～]\s*G?(\d)', s)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        for k, v in [('G1-2', (1, 2)), ('G3-4', (3, 4)), ('G5-6', (5, 6)), ('G7-9', (7, 9))]:
            if (a, b) == v:
                return k
        # 跨学段的写法（如 G3-5）落到覆盖它的最小学段区间上，取起点所属学段
        return {1: 'G1-2', 2: 'G1-2', 3: 'G3-4', 4: 'G3-4',
                5: 'G5-6', 6: 'G5-6', 7: 'G7-9', 8: 'G7-9', 9: 'G7-9'}.get(a)
    m = STAGE_PAT.search(s)
    if m:
        if m.group(1):
            return CN[m.group(1)]
        a = int(m.group(2))
        return {1: 'G1-2', 3: 'G3-4', 5: 'G5-6', 7: 'G7-9'}.get(a)
    return None


def build():
    """→ {(学科, 页码): 学段}，前向填充"""
    idx = [json.loads(l) for l in (ROOT / 'tools/out/page-index.jsonl')
           .open(encoding='utf-8') if l.strip()]
    by_sub = {}
    for r in idx:
        by_sub.setdefault(r['subject'], []).append(r)

    out = {}
    for sub, rows in by_sub.items():
        rows.sort(key=lambda r: r['page'])
        cur = None
        for r in rows:
            st = norm_stage(r.get('heading') or '')
            # 只在「课程内容」一节里认学段标题 —— 课程目标一节也有「学段目标」，
            # 那是目标不是内容，跟着填会把内容要求的学段串到别处
            if st and r.get('section') == '课程内容':
                cur = st
            if cur:
                out[(sub, r['page'])] = cur
    return out


def main():
    m = build()
    idx = [json.loads(l) for l in (ROOT / 'tools/out/page-index.jsonl')
           .open(encoding='utf-8') if l.strip()]
    import collections
    tot = collections.Counter()
    got = collections.Counter()
    for r in idx:
        if r.get('section') != '课程内容':
            continue
        tot[r['subject']] += 1
        if (r['subject'], r['page']) in m:
            got[r['subject']] += 1
    print(f"{'学科':<12}{'课程内容页':>10}{'能定学段':>10}  覆盖率")
    for s in sorted(tot, key=lambda x: -tot[x]):
        print(f"{s:<12}{tot[s]:>10}{got[s]:>10}  {got[s]/tot[s]:.0%}")


if __name__ == '__main__':
    main()
