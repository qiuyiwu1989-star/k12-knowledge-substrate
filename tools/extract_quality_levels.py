#!/usr/bin/env python3
"""
extract_quality_levels.py — 抽高中 20 科的「学业质量水平」量表。

## 这是什么，不是什么

课标前言写着：「研制了学业质量标准。各学科明确学生完成本学科学习任务后，
学科核心素养应该达到的水平，**各水平的关键表现构成评价学业质量的标准**。」

**它不是逐条锚点的掌握判据。** 我一度以为它能填上 assessmentSpec
（做对几次算会、隔多久还算会），抽出来一看不是 —— 它是**学科级的量表**，
每一级下面按该学科的几个核心素养分条描述，措辞是整体性的：

    水平 1（2）能说出一些所学的简单的物理模型；知道得出结论需要科学推理
    水平 5（2）能将较复杂的实际问题中的对象和过程转换成物理模型；
              能在新的情境中对综合性物理问题进行分析和推理

**「几次算会」课标里没有。** 这一条记在这里，免得下次又去翻。

## 那它有什么用

量表本身是底座缺的一个**官方维度**，而且里面藏着两个真正的掌握条件轴：

  · **情境复杂度**：熟悉的问题情境 → 常见情境 → 新的情境 → 真实复杂情境
  · **独立程度**：在他人指导下 → 在他人帮助下 → 独立 → 有一定新意地

这两轴是课标自己的话，不是我们发明的。将来做 mastery 时，
它们是**有出处的**那部分。

## 落成什么

`mappings/quality-levels.json`，一个学科一段，逐级逐条留原文与页码。
**不给锚点打水平标签** —— 那是判断，而这个项目对「没有可判定答案的东西
不机器打标」有过明确结论（见 mappings/crosscutting.json 的 coreCompetencyStatus）。

    python3 tools/extract_quality_levels.py
"""
import json, re
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'sources/standards-gaozhong'

# 情境复杂度 / 独立程度：量表里反复出现的两组梯度词，逐字从原文里拣的
CONTEXT_LADDER = ['熟悉的问题情境', '熟悉的情境', '常见的', '新的情境', '真实情境',
                  '较复杂的实际问题', '综合性', '复杂']
AUTONOMY_LADDER = ['在他人指导下', '在他人帮助下', '独立', '自主', '有一定新意', '创造性']


def norm(t):
    t = re.sub(r'[ \t]+', ' ', t or '')
    return t


def grab(pdf):
    r = PdfReader(str(pdf))
    pages = [(i + 1, norm(p.extract_text())) for i, p in enumerate(r.pages)]
    # 正文页的标志**只认表头「质量描述」**。
    # 第一版还 OR 了「（二）学业质量水平」，结果目录页「（二）学业质量水平／ 46」
    # 先命中，20 科全部定位到目录去了 —— 目录和正文长得像，这是必须防的一类。
    body = [(pg, t) for pg, t in pages if '质量描述' in t]
    if not body:
        # 少数科不用表格版式，退回找「（一）学业质量内涵」的**正文**
        # （目录里那一行后面跟着「／页码」，用它排除）
        body = [(pg, t) for pg, t in pages
                if re.search(r'（一）\s*学业质量内涵(?!\s*／)', t)]
    if not body:
        return None
    start = body[0][0]
    # 一直取到「六、实施建议」或「教师应把握学业质量要求」为止
    out = []
    for pg, t in pages:
        if pg < start:
            continue
        if re.search(r'六、\s*实施建议', t) and out:
            break
        out.append((pg, t))
        if len(out) > 10:
            break
    return out


# 两种版式，实测出来的：
#   A「N-M」编号：1-1 / 1-2 / 2-1 …  水平号**编在条目号里**，最结实。化学语文英语等 18 科。
#   B 裸水平号 +（M）：单独一行「1」，后面跟（1）（2）（3）（4）。物理等。
# 先试 A，A 一条都切不出来才退到 B —— A 不依赖版面上的换行位置，跨页也不会断。
ITEM_A = re.compile(r'(?:^|\n)\s*([1-9])[-－—]([0-9]{1,2})\s*([^\n].{6,})')
LEVEL_B = re.compile(r'(?:^|\n)\s*([1-9])\s*(?=\n\s*（1）)')
# C「水平一/二/三」中文数字 + 整段，无条目编号。数学等。
CN = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6}
LEVEL_C = re.compile(r'水平([一二三四五六])(?![）\d])')


def _clean(t):
    """拼回跨行的一条。页眉页脚（「普通高中X课程标准（2017 年版…」「水平 质量描述」）
    会插在句子中间 —— 句中污染比截断更糟，截断看得出来，这个看不出来。"""
    t = re.sub(r'普通高中[^\n]{0,12}课程标准[^\n]*', '', t)
    t = re.sub(r'水平\s*质量描述', '', t)
    t = re.sub(r'│[^│\n]*│', '', t)
    t = re.sub(r'\s+', '', t)
    return t.strip()


def split_levels(pages):
    joined = '\n'.join(t for _, t in pages)
    page_of = {}
    pos = 0
    for pg, t in pages:
        page_of[pos] = pg
        pos += len(t) + 1
    page_at = lambda p: page_of.get(max((k for k in page_of if k <= p), default=0))

    levels = {}
    hits = list(ITEM_A.finditer(joined))
    if hits:
        for i, m in enumerate(hits):
            lv = int(m.group(1))
            end = hits[i + 1].start() if i + 1 < len(hits) else len(joined)
            body = _clean(joined[m.start(3):end])
            if len(body) < 12:
                continue
            d = levels.setdefault(lv, {'level': lv, 'srcPage': page_at(m.start()), 'items': []})
            d['items'].append(f"{m.group(1)}-{m.group(2)} {body}")
    elif LEVEL_C.search(joined):
        marks = [(m.start(), CN[m.group(1)]) for m in LEVEL_C.finditer(joined)]
        for i, (p0, lv) in enumerate(marks):
            end = marks[i + 1][0] if i + 1 < len(marks) else len(joined)
            body = _clean(joined[p0:end])
            body = re.sub(r'^水平[一二三四五六]', '', body)
            if len(body) < 40:
                continue
            levels.setdefault(lv, {'level': lv, 'srcPage': page_at(p0),
                                   # 整段不切条 —— 数学这一版式本来就没有条目编号，
                                   # 硬切成条要靠语义判断，那正是这个项目栽过的地方。
                                   'items': [body]})
    else:
        marks = [(m.start(), int(m.group(1))) for m in LEVEL_B.finditer(joined)]
        for i, (p0, lv) in enumerate(marks):
            end = marks[i + 1][0] if i + 1 < len(marks) else len(joined)
            items = [_clean(x) for x in re.findall(r'（\d）([^（]{10,600})', joined[p0:end])]
            items = [x for x in items if len(x) >= 12]
            if items:
                levels.setdefault(lv, {'level': lv, 'srcPage': page_at(p0), 'items': items})
    return [levels[k] for k in sorted(levels)]


def main():
    out = {'schemaVersion': '0.1.0',
           'about': '《普通高中课程标准（2017年版2020年修订）》各科「学业质量水平」量表。'
                    '**这不是逐条锚点的掌握判据** —— 它是学科级的水平量表，'
                    '每级按该学科核心素养分条描述。「做对几次算会」课标里没有。',
           'useFor': ['给「达到哪一级」提供官方口径',
                      '量表里的两个梯度轴（情境复杂度 / 独立程度）是课标原话，'
                      '将来做 mastery 时它们是有出处的那部分'],
           'notFor': ['不给锚点打水平标签 —— 那是判断，而本项目对'
                      '「没有可判定答案的东西不机器打标」有明确结论'],
           'ladders': {'context': CONTEXT_LADDER, 'autonomy': AUTONOMY_LADDER},
           'disciplines': {}}
    for pdf in sorted(SRC.glob('*.pdf')):
        name = re.sub(r'^\d+-', '', pdf.stem)
        if name == '课程方案':
            continue
        pages = grab(pdf)
        if not pages:
            print(f'  {name:8} ✗ 没定位到学业质量正文')
            continue
        lv = split_levels(pages)
        nums = [x['level'] for x in lv]
        if lv and nums != list(range(1, len(nums) + 1)):
            print(f'  {name:8} ⚠ 水平不连续 {nums} —— 版式没吃透，先不落盘')
            lv = []
        if not lv:
            print(f'  {name:8} ✗ 定位到了但切不出水平')
            continue
        out['disciplines'][name] = {'levels': lv,
                                    'srcPages': [pages[0][0], pages[-1][0]]}
        n = sum(len(x['items']) for x in lv)
        print(f'  {name:8} ✓ {len(lv)} 级 · {n} 条描述 · p{pages[0][0]}–{pages[-1][0]}')
    (ROOT / 'mappings/quality-levels.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    d = out['disciplines']
    print(f"\n→ mappings/quality-levels.json　{len(d)}/20 科 · "
          f"{sum(len(v['levels']) for v in d.values())} 级 · "
          f"{sum(len(x['items']) for v in d.values() for x in v['levels'])} 条描述")


if __name__ == '__main__':
    main()
