#!/usr/bin/env python3
"""
section_range.py — 求某一科某个章节的真实页码范围。

**为什么不能用 min..max。** 劳动课标的 p2 是目录页，里面「第三学段（5～6年级）」
这行目录条目被分类器当成了正文标题，于是 p2 被标成「课程内容」。
用 min..max 取范围就得到 2–48，而真正的课程内容从 p19（「四、课程内容」）才开始。
按 2–48 抽，抽出来的是目录和前言——实测抽到了「能说出课程资源开发与利用建议
的页码是 57」。

正确做法：找**包含章节起始标题的那一段连续页**。起始标题形如「四、课程内容」，
是带中文序号的一级标题；目录页里的条目不会长这样。

    python3 tools/section_range.py            # 全科体检
    python3 tools/section_range.py 劳动 课程内容
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 一级标题：中文数字 + 顿号 + 章节名。目录页里的条目是「（一）xxx …… 12」这种形态，
# 不会命中这个模式。
TOP_HEADING = re.compile(r'^[一二三四五六七八九十]+、\s*(.+)$')


def load_index():
    p = ROOT / 'tools/out/page-index.jsonl'
    return [json.loads(l) for l in p.open(encoding='utf-8') if l.strip()]


def runs(pages):
    """连续页码段 → [(起, 止)]"""
    out, s, prev = [], None, None
    for p in sorted(pages):
        if s is None:
            s = prev = p; continue
        if p == prev + 1:
            prev = p; continue
        out.append((s, prev)); s = prev = p
    if s is not None:
        out.append((s, prev))
    return out


def resolve(idx, subject, section, gap=2):
    """→ (起, 止, 依据)。找不到起始标题时退回最长连续段，并说明。"""
    rows = [r for r in idx if r['subject'] == subject]
    sec = [r for r in rows if r['section'] == section]
    if not sec:
        return None

    # 1) 优先：带一级标题的那一页当起点
    anchors = [r['page'] for r in sec
               if TOP_HEADING.match((r.get('heading') or '').strip())
               and section.lstrip('课程') in (r.get('heading') or '')]
    pages = [r['page'] for r in sec]

    # 允许段内有 gap 页断档（个别页被误分到别的 section 很常见）
    merged, cur = [], None
    for a, b in runs(pages):
        if cur and a - cur[1] <= gap + 1:
            cur = (cur[0], b)
        else:
            if cur: merged.append(cur)
            cur = (a, b)
    if cur: merged.append(cur)

    if anchors:
        start = min(anchors)
        for a, b in merged:
            if a <= start <= b:
                return a if a == start else start, b, f'起始标题在 p{start}'
        return start, max(pages), f'起始标题在 p{start}（未落在任何连续段内）'

    # 2) 退回：最长连续段
    a, b = max(merged, key=lambda x: x[1] - x[0])
    return a, b, f'无一级标题，取最长连续段（{len(merged)} 段候选）'


def main():
    idx = load_index()
    if len(sys.argv) >= 3:
        r = resolve(idx, sys.argv[1], sys.argv[2])
        print(r); return

    subs = sorted({r['subject'] for r in idx})
    print(f"{'学科':<12}{'min..max':>12}{'真实范围':>12}  依据")
    for s in subs:
        r = resolve(idx, s, '课程内容')
        if not r: continue
        pages = [x['page'] for x in idx if x['subject'] == s and x['section'] == '课程内容']
        naive = f"{min(pages)}-{max(pages)}"
        real = f"{r[0]}-{r[1]}"
        flag = '  ← 差别大' if r[0] - min(pages) > 3 else ''
        print(f"{s:<12}{naive:>12}{real:>12}  {r[2]}{flag}")


if __name__ == '__main__':
    main()
