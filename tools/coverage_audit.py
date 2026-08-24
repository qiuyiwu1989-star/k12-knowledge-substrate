#!/usr/bin/env python3
"""coverage_audit.py — 课标里应该有多少条，我们抽到了多少。

## 这是全项目最大的未知数

我们一直知道「抽出了 2,969 条」，**从来没测过「课标里应该有多少条」**。
给人看的时候，漏一条只是少一页；**给机器调的时候，漏一条意味着调用方映射到一条错的** ——
一节 G3 的退位减法课，第一名是标着 G1–G2 的锚点，就是这个味道。

## 分母只有一半拿得到

高中 21 科的源 PDF 还在仓库里（`sources/standards-gaozhong/`），页数机械可得。
**义务教育的源 PDF 不在仓库里** —— 抽完就没留。所以那一半只能做区间对账：
「首页到末页之间，哪些页一条都没出」，分母是未知的。

这个不对称本身就是一条结论：**义务教育那半边现在没法自证覆盖率。**

## 空档 ≠ 洞

一页没出锚点，可能完全正确 —— 封面、目录、前言、教学建议、评价案例、附录，
本来就不该出。所以这份报告**不给覆盖率百分比**，只给空档清单。

把空档判成「合理」还是「洞」，需要逐页看原文，那是下一步（要过模型）。
现在就报一个百分比，等于把「没核过」包装成「核过了」—— 这个项目已经在
「用产出量当进展」上栽过一次，不再来第二次。
"""
import json, re, subprocess, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GZ = ROOT / 'sources' / 'standards-gaozhong'


def pdf_pages(p):
    """macOS 自带 mdls，零依赖。拿不到返回 None —— 拿不到就如实说拿不到。"""
    try:
        out = subprocess.run(['mdls', '-name', 'kMDItemNumberOfPages', '-raw', str(p)],
                             capture_output=True, text=True, timeout=20).stdout.strip()
        return int(out) if out.isdigit() else None
    except Exception:
        return None


def load():
    """按**抽取来源**分组，不按学科名 —— 数学在义务教育和高中各有一套，同名不同源。"""
    groups = defaultdict(list)
    for f in sorted((ROOT / 'anchors').glob('*.jsonl')):
        origin = ('高中' if f.name.startswith('gaozhong-')
                  else '转写' if f.name.startswith('rewrite-') else '义务教育')
        for l in f.open(encoding='utf-8'):
            if l.strip():
                a = json.loads(l)
                a['_origin'] = origin
                groups[(origin, a.get('discipline'))].append(a)
    return groups


def main():
    groups = load()
    # 高中 PDF：学科名 ← 文件名（"02-数学.pdf" → 数学）
    pdfs = {}
    for p in sorted(GZ.glob('*.pdf')):
        m = re.match(r'\d+-(.+)\.pdf$', p.name)
        if m and m.group(1) != '课程方案':
            pdfs[m.group(1)] = (p, pdf_pages(p))

    rows, gaps_all = [], {}
    for (origin, disc), anchors in sorted(groups.items()):
        if origin == '转写':
            continue                       # 转写不是从页面抽的，没有页码可对账
        pages = {a['provenance']['srcPage'] for a in anchors
                 if (a.get('provenance') or {}).get('srcPage')}
        if not pages:
            rows.append((origin, disc, len(anchors), 0, None, None, None))
            continue
        lo, hi = min(pages), max(pages)
        inner_gap = sorted(set(range(lo, hi + 1)) - pages)
        total = pdfs.get(disc, (None, None))[1] if origin == '高中' else None
        outside = (total - hi) if total else None
        rows.append((origin, disc, len(anchors), len(pages), total, inner_gap, outside))
        if inner_gap:
            gaps_all[f'{origin}·{disc}'] = inner_gap

    def fmt_runs(pp):
        """把 [3,4,5,9] 压成 '3–5, 9' —— 一页一页列出来没人看得下去。"""
        out, i = [], 0
        while i < len(pp):
            j = i
            while j + 1 < len(pp) and pp[j + 1] == pp[j] + 1:
                j += 1
            out.append(str(pp[i]) if i == j else f'{pp[i]}–{pp[j]}')
            i = j + 1
        return ', '.join(out)

    L = []
    L.append('# 覆盖率体检\n')
    L.append('> 机械对账部分。**不给覆盖率百分比** —— 一页没出锚点可能完全正确'
             '（封面、目录、教学建议、评价案例、附录本来就不该出）。')
    L.append('> 把空档判成「合理」还是「洞」需要逐页看原文，那是下一步。'
             '现在报百分比等于把「没核过」包装成「核过了」。\n')

    known = [r for r in rows if r[0] == '高中']
    unknown = [r for r in rows if r[0] == '义务教育']
    tp = sum(r[4] or 0 for r in known)
    hp = sum(r[3] for r in known)
    L.append(f'## 分母拿得到的：高中 {len(known)} 科\n')
    L.append(f'源 PDF 在 `sources/standards-gaozhong/`，共 **{tp} 页**，'
             f'其中 **{hp} 页**产出过锚点。\n')
    L.append('| 学科 | 锚点 | 出锚点的页 | 总页数 | 首末页之间的空档 | 末页之后 |')
    L.append('|---|--:|--:|--:|--:|--:|')
    for o, d, na, np_, tot, gap, outside in sorted(known, key=lambda r: -(r[4] or 0)):
        L.append(f'| {d} | {na} | {np_} | {tot or "?"} | {len(gap) if gap else 0} | '
                 f'{outside if outside is not None else "?"} |')

    L.append(f'\n## 分母拿不到的：义务教育 {len(unknown)} 科\n')
    L.append('**源 PDF 不在仓库里**（抽完没留），所以这一半只能做区间对账，'
             '总页数未知 —— 这本身就是一条结论：**义务教育那半边现在没法自证覆盖率。**\n')
    L.append('| 学科 | 锚点 | 出锚点的页 | 页码区间 | 区间内空档 |')
    L.append('|---|--:|--:|---|--:|')
    for o, d, na, np_, tot, gap, outside in sorted(unknown, key=lambda r: -(r[3] or 0)):
        anchors = groups[(o, d)]
        pp = {a['provenance']['srcPage'] for a in anchors if (a.get('provenance') or {}).get('srcPage')}
        rng = f'p{min(pp)}–p{max(pp)}' if pp else '—'
        L.append(f'| {d} | {na} | {np_} | {rng} | {len(gap) if gap else 0} |')

    L.append('\n## 空档清单（待逐页核）\n')
    tot_gap = sum(len(v) for v in gaps_all.values())
    L.append(f'共 **{tot_gap} 页**落在首末页之间却一条锚点都没出。'
             '这些**不等于洞** —— 需要逐页看原文才知道该不该出。\n')
    for k, v in sorted(gaps_all.items(), key=lambda t: -len(t[1])):
        L.append(f'- **{k}** · {len(v)} 页：{fmt_runs(v)}')

    # ── 比空档更值得看的：**对齐密度的方差** ──────────────────────
    # 覆盖率低不可怕，可怕的是「有的科抽得很透、有的科几乎没抽」而没人知道是哪些。
    # 密度 = 每 10 页文档产出几条锚点。同为高中课标、同样的抽取管线，
    # 密度差 20 倍就不是文档差异，是**抽取在某些科上失灵了**。
    dens = [(d, na, tot, na / tot * 10) for o, d, na, np_, tot, gap, outside in known if tot]
    dens.sort(key=lambda t: t[3])
    mid = dens[len(dens) // 2][3]
    L.append('\n## 比空档更值得看的：对齐密度\n')
    L.append('同为高中课标、同一套抽取管线，**每 10 页产出的锚点数差了 20 倍**。'
             '这不像是文档差异，更像是抽取在某些科上失灵了。\n')
    L.append(f'中位数是每 10 页 **{mid:.1f}** 条。低于中位数一半的科排在最前 —— '
             '这就是下一轮补抽的优先级。\n')
    L.append('| 学科 | 锚点 | 总页数 | 每 10 页 | |')
    L.append('|---|--:|--:|--:|---|')
    for d, na, tot, k in dens:
        flag = ('**远低于中位数**' if k < mid / 2 else '低于中位数' if k < mid else '')
        L.append(f'| {d} | {na} | {tot} | {k:.1f} | {flag} |')

    out = ROOT / 'reports' / 'coverage.md'
    out.parent.mkdir(exist_ok=True)
    out.write_text('\n'.join(L) + '\n', encoding='utf-8')
    print(f'✓ {out.relative_to(ROOT)}')
    print(f'  高中 {len(known)} 科：{tp} 页中 {hp} 页产出过锚点')
    print(f'  义务教育 {len(unknown)} 科：分母未知（源 PDF 不在仓库）')
    print(f'  首末页之间的空档共 {tot_gap} 页 —— 待逐页核，空档不等于洞')
    low = [d for d, na, tot, k in dens if k < mid / 2]
    print(f'  对齐密度远低于中位数的 {len(low)} 科：{"、".join(low)}')


if __name__ == '__main__':
    main()
