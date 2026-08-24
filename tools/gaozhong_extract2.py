#!/usr/bin/env python3
"""
gaozhong_extract2.py — 补抽高中课标里 gaozhong_extract.py 抽不动的五科。**纯规则，零模型调用。**

    地理 / 思想政治 / 音乐 / 美术 / 德语

## 为什么第一版对这五科几乎无效

课标前言写着「**原则上**每个模块或主题由『内容要求』『教学提示』『学业要求』组成」。
第一版靠「内容要求」这四个字定位课程内容，于是「原则上」三个字要了命：

    德语   163 页「内容要求」只出现 5 次   →  抽出  23 条（且全是段落，不是条目）
    地理   19 次                          →  抽出  10 条
    音乐   22 次                          →  抽出  13 条
    思想政治 20 次                        →  抽出  20 条
    美术   14 次                          →  抽出  51 条
    （对照：通用技术 185 条）

真实原因逐科不同，见下面「五科版式」。**「内容要求」出现次数根本不是产出的上限**——
地理 19 次里每一次底下都挂着 9~12 个编号条目，第一版是条目正则不匹配（它认三段式
`1.1.1`，这五科全是两段式 `1.1` 或一段式 `1.`）；思想政治则是压根有一半模块没有
「内容要求」这四个字。

## 五科版式（踩坑记录）

### 地理 —— 最规矩的一科
    地理1                       ← 必修模块，模块名就是编号，没有独立名字
    【内容要求】
    1.1 运用资料，描述地球所处的宇宙环境，说明太阳对地球的影响。
    ...
    【教学提示】 / 【学业要求】
选择性必修写成「选择性必修1 自然地理基础」，选修写成「选修2 海洋地理」。
**坑：编号每换一个模块就从 1.1 重来**（必修地理1 是 1.x、地理2 是 2.x，
但选择性必修1 又回到 1.x）。所以 code 单独不唯一，必须配 course+courseNo 才能定位。
选修 9 个模块没有【学业要求】。

### 音乐 —— 和地理同构
    模块1 ：音乐鉴赏   ← 注意「1」和「：」之间有个空格，是排版不是错字
    【内容要求】 1.1 … 1.8
选修课程整章只有一句「内容要求由各校根据育人要求和教学实际情况自行制订」，
**没有任何条目，抽出 0 条是对的，不是漏抽**。

### 美术 —— 同一本书里三种条目编号
    必修「模块 美术鉴赏」（模块二字后面没有编号）→ 条目是一段式  `1.` … `10.`
    选择性必修「模块1 绘画」                      → 条目是两段式  `1.1` … `1.6`
    选修「模块1 美术史论基础」                    → **完全没有编号条目**，
        【内容要求】底下只有一段「速写基础由速写方法、人物速写和风景速写等
        学习内容组成」这种内容构成描述。5 个选修模块全是这样，抽出 0 条。
另一个坑：【内容要求】开头往往先有两段定义性散文（「美术鉴赏是运用感知、经验和
知识对……的美术活动。」「本模块学习内容由鉴赏基础和鉴赏内容等组成。」），
它们不是能力断言，本工具**只收编号条目**，散文计入 skipped_prose 统计。

### 思想政治 —— 一本书三种版式，且有一种没有「内容要求」四个字
    必修（模块1~4）：**双栏表格**
        ┌──────────┬────────────────────────┐
        │ 内容要求  │ 教学提示                │
        │ 1.1 描述  │ ◆ 以「怎样揭示……」为议题 │
        └──────────┴────────────────────────┘
        pypdf 线性抽取会把左栏整块吐完再吐右栏，但**右栏的跨页续接段没有任何
        标记**（上一页的「◆」段落在本页顶部直接续「本主义生产关系的形成与
        发展，揭示……」），纯文本状态下无法判断它属于右栏，会被并进左栏条目里。
        → 必须用 x 坐标切栏。
    选择性必修（模块1~3）：单栏，有【内容要求】，条目 `1. 主题` + `1.1 条目`
    选修（模块1~3）：单栏，**根本没有【内容要求】四个字**，模块简介之后
        直接就是 `1. 货币与市场` / `1.1 描述货币形态的变迁…`。
        第一版靠「内容要求」定位，这三个模块 100% 漏掉。

### 德语 —— 吃不透的一科，如实说明
「四、课程内容」这一章里**没有可判定的能力断言**。它写的是主题范围与语料规格：
    必修：初中/高中各一张「主题内容」表（个人生活 / 日常生活 / …）
          + 一张「篇章类别」表 + 一句词汇量要求
    选择性必修 / 选修：`1.1 建筑与市容`、`1.1 水与石（C1）` 这类主题条目，
          正文是「这个主题围绕……展开跨文化比较」式的教学说明
真正的能力断言在**五、学业质量**的表 6（初中 C1~C5、高中 G1~G5，每级 4 条，
共 40 条 `1-1`/`2-3` 形式的编号断言）和**附录 1 核心素养水平划分**（表 7~14）。
本工具抽了课程内容里能抽的（section=内容要求）**以及**表 6（section=学业质量），
后者是德语唯一成规模的能力断言来源，且 tools/out/xueye-raw.jsonl 里没有德语。
**附录 1 没抽**（水平划分是素养 × 水平的矩阵，语义上不是课程内容条目）。

## 三个共用的工程决定

1. **文本用 pypdf，坐标用 pypdf 的 visitor**。
   PyMuPDF 的坐标更好用，但它的取字结果和现有产物对不上：
   同一行 MuPDF 给「掌握2—3种美术鉴赏」，pypdf 给「掌握 2—3 种美术鉴赏」，
   仓库里已有的 美术.jsonl 是后者。中西文之间那个空格是排版 tracking，不是
   真空格字符，两个库的补空格策略不同，**换库等于悄悄改写全部已有产物的正文**。
   所以坚持 pypdf，用 `extract_text(visitor_text=...)` 拿每个文本块的 tm[4]（x）。
   实测 visitor 各块文本拼接结果与 `extract_text()` **逐字节相等**，可以安全地
   把 x 贴回行上。tm[5]（y）在这批 PDF 上是坏的（同一页出现 -1191.9），不要用。
2. **页眉页脚按「模式 + x」剜，不按 y 剜**。y 不可信（见上）。页码是裸数字，
   而德语学业质量表的「水平」单元格也是裸数字「1」「5」，只能靠 x 区分：
   页码在 x≈85（偶页）或 x≈443（奇页），表格单元格在 x≈109~118。
3. **不改写**。行内空格原样保留，跨行只做无分隔符拼接（中文换行不补空格），
   全角字母数字归一为半角，各种异体空格（U+2002/U+3000/NBSP）归一为普通空格，
   全角标点**不动**（它们是正文的一部分）。

## 用法

    python3 tools/gaozhong_extract2.py              # 五科全抽，写 tools/out/gaozhong2/
    python3 tools/gaozhong_extract2.py --only 地理
    python3 tools/gaozhong_extract2.py --report     # 只看统计，不写盘

输出字段与 tools/out/gaozhong/*.jsonl 完全一致：
    subject course courseNo topic topicName code subTopic text page section examples
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'sources/standards-gaozhong'
OUT = ROOT / 'tools/out/gaozhong2'

PDFS = {
    '地理': '06-地理.pdf',
    '思想政治': '04-思想政治.pdf',
    '音乐': '13-音乐.pdf',
    '美术': '14-美术.pdf',
    '德语': '18-德语.pdf',
}

# ─────────────────────────── 取字与清洗 ───────────────────────────

# 异体空格 → 普通空格。EN SPACE 出现在页眉「│ 四、课程内容 │」里，
# IDEOGRAPHIC SPACE 出现在条目缩进里。
_SPACES = {' ': ' ', ' ': ' ', ' ': ' ', ' ': ' ',
           '　': ' ', ' ': ' ', '﻿': ''}
# 全角字母数字 → 半角。全角标点不动。
_FULLWIDTH = {chr(c): chr(c - 0xFEE0) for c in range(0xFF10, 0xFF1A)}
_FULLWIDTH.update({chr(c): chr(c - 0xFEE0) for c in range(0xFF21, 0xFF3B)})
_FULLWIDTH.update({chr(c): chr(c - 0xFEE0) for c in range(0xFF41, 0xFF5B)})
_TRANS = str.maketrans({**_SPACES, **_FULLWIDTH})


def norm(s):
    return s.translate(_TRANS).strip()


# 页眉：「│ 四、课程内容 │」「普通高中地理课程标准（2017 年版 2020 年修订）」
# **坑**：偶数页的书名页眉在内容流里被写了两遍且中间没有换行，抽出来长这样：
#   「普通高中地理课程标准（2017 年版 2020 年修订）普通高中地理课程标准（2017 年版 2020 年修订）」
# 用 `^…$` 整行匹配会漏掉，漏掉的后果不是截断而是**句中污染**——这一行会被
# 当成上一条内容要求的续行，直接嵌进句子中间。所以按「出现即剜」处理，
# 剜完若整行为空就丢弃；若剜完还剩正文，说明页眉和正文粘在一行，剩下的留着并计数。
RUNNING_HEAD = re.compile(
    r'│[^│]*│|普通高中.{1,10}课程标准（\s*2017\s*年版\s*2020\s*年修订\s*）')
PAGE_NO = re.compile(r'^\d{1,3}$')
STUCK_HEAD = Counter()


def page_lines(page):
    """把一页拆成 [(x0, text), ...]，保持 pypdf 的阅读顺序，已剜掉页眉页脚。

    x0 取该行第一个非空文本块的 tm[4]。visitor 的各块文本拼接 == extract_text()，
    所以这样切出来的行和 extract_text() 的行是同一批行，只是多带了一个 x。
    """
    chunks = []

    def visit(text, cm, tm, font_dict, font_size):
        chunks.append((tm[4], text))

    page.extract_text(visitor_text=visit)

    lines, buf, x0 = [], '', None
    for x, text in chunks:
        parts = text.split('\n')
        for i, part in enumerate(parts):
            if i > 0:
                lines.append((x0, buf))
                buf, x0 = '', None
            if part:
                if x0 is None and part.strip():
                    x0 = x
                buf += part
    if buf.strip():
        lines.append((x0, buf))

    out = []
    for x, raw in lines:
        t = norm(raw)
        if not t or t == '续表':
            continue
        if RUNNING_HEAD.search(t):
            cleaned = norm(RUNNING_HEAD.sub('', t))
            if not cleaned:
                continue
            STUCK_HEAD[cleaned[:30]] += 1
            t = cleaned
        # 裸页码。只在版心外的 x 上剜 —— 德语学业质量表的「水平」格也是裸数字。
        if PAGE_NO.match(t) and (x is None or x <= 100 or x >= 430):
            continue
        out.append((x if x is not None else 0.0, t))
    return out


def doc_lines(pdf_name, start_pat, end_pat):
    """取 [start_pat 所在页 … end_pat 所在页) 的所有行，带页码（1 起）。

    返回 [(page, x0, text), ...]。start/end 用「独占一行的标题」判定，
    避免命中目录页和正文里的引用（目录行长这样：「四、课程内容....8」）。
    """
    reader = PdfReader(SRC / pdf_name)
    pages = [page_lines(p) for p in reader.pages]

    def find(pat, frm=0):
        for i in range(frm, len(pages)):
            for _, t in pages[i]:
                if pat.fullmatch(t):
                    return i
        return None

    # 目录页也有「四、课程内容」，但它带页码点线，fullmatch 不中。
    start = find(start_pat)
    end = find(end_pat, (start or 0) + 1)
    if start is None:
        raise SystemExit(f'{pdf_name}: 找不到起始标题 {start_pat.pattern}')
    if end is None:
        end = len(pages)
    # **坑**：结束标题常常和本章最后几条正文同页（德语 G5 的 5-2/5-3/5-4 就和
    # 「（三）学业质量水平与考试评价的关系」挤在同一页）。整页丢掉会静默漏 3 条，
    # 所以结束页也要收，只在标题那一行截断。
    out, started = [], False
    for i in range(start, min(end + 1, len(pages))):
        for x, t in pages[i]:
            if not started:
                if not start_pat.fullmatch(t):
                    continue
                started = True
            if i == end and end_pat.fullmatch(t):
                return out, start + 1, end + 1
            out.append((i + 1, x, t))
    return out, start + 1, min(end + 1, len(pages))


CONTENT_HEAD = re.compile(r'四、\s*课程内容')
QUALITY_HEAD = re.compile(r'五、\s*学业质量')

COURSE_HEAD = re.compile(r'^（[一二三]）\s*(必修|选择性必修|选修)课程$')
SEC_MARK = re.compile(r'^【(内容要求|教学提示|学业要求)】$')


def right_column_x(page_rows):
    """一页里如果存在双栏表格的右栏，返回右栏的 x，否则 None。

    右栏（教学提示）在这批 PDF 里稳定落在 x≈214~223，且一页至少 3 行；
    单栏页最大 x 也就 128 左右，不会误判。居中的主题标题行（如
    「2. 中国特色社会主义的开创与发展」x=189.1）行数只有 1，也不会误判。
    """
    c = Counter(round(x, 1) for x, _ in page_rows if x >= 205)
    if not c:
        return None
    x, n = c.most_common(1)[0]
    return x if n >= 3 else None


def drop_right_column(rows, keep):
    """rows: [(page, x, text)] → 去掉双栏表格右栏（教学提示）的行。

    **坑**：右栏每个「◆」段落的首行比正文行右缩进 20pt（x≈244 而正文 x≈224），
    只按 x 聚类的众数 ±4.5 剜会把这些首行漏在外面，于是「◆ 以“如何增强政府的
    公信力和执行力”为……」会接到上一条内容要求的尾巴上。所以改成「x 落在右栏
    起点及其右侧一律剜」，唯一例外是跨栏居中的主题标题行（如「3. 依法治国」，
    x=247.6），用 keep 回调（即主题行正则）把它捞回来。
    """
    by_page = {}
    for page, x, t in rows:
        by_page.setdefault(page, []).append((x, t))
    rx = {p: right_column_x(v) for p, v in by_page.items()}
    out = []
    for page, x, t in rows:
        r = rx.get(page)
        if r is not None and x >= r - 4.5 and not keep(t):
            continue
        # 表头单元格「内容要求」「教学提示」在同一行被 pypdf 合成一行
        if t in ('内容要求 教学提示', '内容要求', '教学提示'):
            continue
        out.append((page, x, t))
    return out


def row(subject, course, course_no, topic, topic_name, code, sub_topic, text, page, section):
    return {
        'subject': subject,
        'course': course,
        'courseNo': course_no,
        'topic': topic,
        'topicName': topic_name,
        'code': code,
        'subTopic': sub_topic,
        'text': text,
        'page': page,
        'section': section,
        'examples': [],
    }


class ItemSink:
    """条目累加器：开一条、续行、收尾。跨行拼接不加分隔符（中文换行）。"""

    def __init__(self):
        self.rows = []
        self.cur = None

    def open(self, meta, text):
        self.close()
        self.cur = (meta, [text])

    def feed(self, text):
        if self.cur:
            self.cur[1].append(text)

    def close(self):
        if self.cur:
            meta, parts = self.cur
            meta['text'] = ''.join(parts).strip()
            if meta['text']:
                self.rows.append(meta)
            self.cur = None


# ─────────────────────────── 地理 / 音乐 ───────────────────────────

ITEM_2 = re.compile(r'^(\d{1,2}\.\d{1,2})\s+(\S.*)$')     # 1.1 运用资料，…
ITEM_1 = re.compile(r'^(\d{1,2})\.\s+(\S.*)$')            # 1. 从材料、工具…

DILI_MODS = [
    (re.compile(r'^地理(\d)$'), '必修'),
    (re.compile(r'^选择性必修(\d)\s+(\S.{1,20})$'), '选择性必修'),
    (re.compile(r'^选修(\d)\s+(\S.{1,20})$'), '选修'),
]
YINYUE_MOD = re.compile(r'^模块\s*(\d)\s*[：:]\s*(\S.{1,20})$')


def extract_dili_yinyue(subject, pdf, module_pats, want_xueye):
    rows, first, last = doc_lines(pdf, CONTENT_HEAD, QUALITY_HEAD)
    sink = ItemSink()
    stats = Counter()
    course = course_no = topic = topic_name = None
    section = None
    xueye = None  # (meta, [lines])

    def flush_xueye():
        nonlocal xueye
        if xueye:
            meta, parts = xueye
            meta['text'] = ''.join(parts).strip()
            if meta['text']:
                sink.rows.append(meta)
            xueye = None

    for page, _x, t in rows:
        m = COURSE_HEAD.match(t)
        if m:
            sink.close()
            flush_xueye()
            course, course_no, topic, topic_name, section = m.group(1), '', None, None, None
            continue

        hit = None
        for pat, kind in module_pats:
            mm = pat.match(t)
            if mm:
                hit = (kind, mm)
                break
        if hit:
            kind, mm = hit
            sink.close()
            flush_xueye()
            if kind == '必修' and subject == '地理':
                course_no, topic, topic_name = mm.group(1), f'地理{mm.group(1)}', None
            elif subject == '地理':
                course_no = mm.group(1)
                topic = f'{kind}{mm.group(1)}'
                topic_name = mm.group(2)
            else:  # 音乐：模块N ：名字
                course_no = mm.group(1)
                topic = f'模块{mm.group(1)}'
                topic_name = mm.group(2)
            if course is None:
                course = kind
            section = None
            continue

        m = SEC_MARK.match(t)
        if m:
            sink.close()
            flush_xueye()
            section = m.group(1) if m.group(1) != '教学提示' else None
            if section == '学业要求' and want_xueye:
                xueye = (row(subject, course, course_no, topic, topic_name,
                             None, None, '', page, '学业要求'), [])
            continue

        if section == '内容要求':
            m = ITEM_2.match(t)
            if m:
                sink.open(row(subject, course, course_no, topic, topic_name,
                              m.group(1), None, '', page, '内容要求'), m.group(2))
            elif sink.cur:
                sink.feed(t)
            else:
                stats['skipped_prose'] += 1
        elif section == '学业要求' and xueye:
            xueye[1].append(t)

    sink.close()
    flush_xueye()
    return sink.rows, stats, (first, last)


# ─────────────────────────── 美术 ───────────────────────────

MEISHU_MOD = re.compile(r'^模块\s*(\d?)\s*(\S.{0,14})$')


def extract_meishu():
    rows, first, last = doc_lines(PDFS['美术'], CONTENT_HEAD, QUALITY_HEAD)
    sink = ItemSink()
    stats = Counter()
    course = course_no = topic = topic_name = None
    section = None

    for page, _x, t in rows:
        m = COURSE_HEAD.match(t)
        if m:
            sink.close()
            course, course_no, topic, topic_name, section = m.group(1), '', None, None, None
            continue

        # 模块标题一定短且不含句读；「模块，也允许学生……」这种正文句子排除掉
        m = MEISHU_MOD.match(t)
        if m and len(t) <= 18 and not re.search(r'[，。；、：]', t):
            sink.close()
            course_no = m.group(1) or ''
            topic = f'模块{course_no}' if course_no else '模块'
            topic_name = m.group(2)
            section = None
            continue

        m = SEC_MARK.match(t)
        if m:
            sink.close()
            section = m.group(1) if m.group(1) == '内容要求' else None
            continue

        if section == '内容要求':
            # 必修「模块 美术鉴赏」用一段式 1.…10.，选择性必修用两段式 1.1…
            m2 = ITEM_2.match(t)
            m1 = ITEM_1.match(t)
            if m2:
                sink.open(row('美术', course, course_no, topic, topic_name,
                              m2.group(1), None, '', page, '内容要求'), m2.group(2))
            elif m1:
                sink.open(row('美术', course, course_no, topic, topic_name,
                              m1.group(1), None, '', page, '内容要求'), m1.group(2))
            elif sink.cur:
                sink.feed(t)
            else:
                stats['skipped_prose'] += 1

    sink.close()
    return sink.rows, stats, (first, last)


# ─────────────────────────── 思想政治 ───────────────────────────

SZ_MOD = re.compile(r'^模块\s*(\d)\s*[：:]\s*(\S.{1,20})$')
# 主题行「1. 各具特色的国家」「2. 中国特色社会主义的开创与发展」。
# 必修表格里它是跨栏居中行，选择性必修/选修里它是左对齐行，两处正则相同。
SZ_TOPIC = re.compile(r'^(\d{1,2})\.\s*([^\d\s][^，。；]{1,24})$')


def extract_sizheng():
    rows, first, last = doc_lines(PDFS['思想政治'], CONTENT_HEAD, QUALITY_HEAD)
    rows = drop_right_column(rows, keep=lambda t: bool(SZ_TOPIC.match(t)))
    sink = ItemSink()
    stats = Counter()
    course = course_no = topic = topic_name = sub_topic = None
    section = None
    xueye = None

    def flush_xueye():
        nonlocal xueye
        if xueye:
            meta, parts = xueye
            meta['text'] = ''.join(parts).strip()
            if meta['text']:
                sink.rows.append(meta)
            xueye = None

    for page, _x, t in rows:
        m = COURSE_HEAD.match(t)
        if m:
            sink.close()
            flush_xueye()
            course, course_no = m.group(1), ''
            topic = topic_name = sub_topic = None
            section = None
            continue

        m = SZ_MOD.match(t)
        if m:
            sink.close()
            flush_xueye()
            course_no, topic, topic_name = m.group(1), f'模块{m.group(1)}', m.group(2)
            sub_topic = None
            # 选修课程整章没有【内容要求】四个字，模块简介之后直接是条目，
            # 所以模块标题本身就把 section 打开。必修表格同理（表头已被剜掉）。
            section = '内容要求'
            continue

        m = SEC_MARK.match(t)
        if m:
            sink.close()
            flush_xueye()
            section = m.group(1) if m.group(1) != '教学提示' else None
            if section == '学业要求':
                xueye = (row('思想政治', course, course_no, topic, topic_name,
                             None, None, '', page, '学业要求'), [])
            continue

        if section == '内容要求':
            m = ITEM_2.match(t)
            if m:
                sink.open(row('思想政治', course, course_no, topic, topic_name,
                              m.group(1), sub_topic, '', page, '内容要求'), m.group(2))
                continue
            m = SZ_TOPIC.match(t)
            if m:
                sink.close()
                sub_topic = m.group(2)
                continue
            if sink.cur:
                sink.feed(t)
            else:
                stats['skipped_prose'] += 1
        elif section == '学业要求' and xueye:
            xueye[1].append(t)

    sink.close()
    flush_xueye()
    return sink.rows, stats, (first, last)


# ─────────────────────────── 德语 ───────────────────────────

DE_STAGE = re.compile(r'^(初中|高中)阶段$')
DE_SUBHEAD = re.compile(r'^(\d)\.\s*(主题|篇章|词汇)$')
# 选择性必修 / 选修把条目分组成「1. G3 主题范围」「2. 高中阶段主题范围」。
# 它是分组标题不是条目，但**必须当成终止符**，否则它会被当作上一条主题的
# 续行粘在句尾（实测 1.3 结尾变成「…创新思维。2. G4 主题范围」）。
DE_GROUP = re.compile(r'^\d\.\s*\S[^，。；]{0,24}范围$')
DE_TABLE_CAP = re.compile(r'^表\s*\d+\s+\S+')
DE_LEVEL = re.compile(r'^（([CG]\d)）$')
DE_QUALITY_ITEM = re.compile(r'^(\d-\d)\s*(\S.*)$')
DE_QUALITY_HEAD = re.compile(r'^（二）\s*学业质量水平$')
DE_QUALITY_END = re.compile(r'^（三）\s*学业质量水平与考试评价的关系$')
# 主题内容表的表头单元格 / 篇章类别表的表头
DE_TH = {'主题', '内容', '篇章类型', '篇章类别', '水平', '质量描述'}


def extract_deyu():
    out = []
    stats = Counter()

    # ── 四、课程内容 ──
    rows, first, last = doc_lines(PDFS['德语'], CONTENT_HEAD, QUALITY_HEAD)
    course = None
    stage = None
    section = None
    sub_head = None
    in_theme_table = False
    theme_name, theme_buf = None, []
    cur = None            # 选择性必修 / 选修的 N.M 主题条目
    vocab = None

    def flush_theme(page):
        nonlocal theme_name, theme_buf
        if theme_name and theme_buf:
            out.append(row('德语', course, '', stage, None, None, theme_name,
                           ''.join(theme_buf).strip(), page, '内容要求'))
        theme_name, theme_buf = None, []

    def flush_cur():
        nonlocal cur
        if cur:
            meta, parts = cur
            meta['text'] = ''.join(parts).strip()
            if meta['text']:
                out.append(meta)
            cur = None

    def flush_vocab(page):
        nonlocal vocab
        if vocab:
            meta, parts = vocab
            meta['text'] = ''.join(parts).strip()
            if meta['text']:
                out.append(meta)
            vocab = None

    for page, x, t in rows:
        m = COURSE_HEAD.match(t)
        if m:
            flush_theme(page); flush_cur(); flush_vocab(page)
            course, stage, section, sub_head = m.group(1), None, None, None
            in_theme_table = False
            continue

        m = SEC_MARK.match(t)
        if m:
            flush_theme(page); flush_cur(); flush_vocab(page)
            section = m.group(1) if m.group(1) == '内容要求' else None
            in_theme_table = False
            continue

        if section != '内容要求':
            continue

        m = DE_STAGE.match(t)
        if m:
            flush_theme(page); flush_cur(); flush_vocab(page)
            stage = t
            in_theme_table = False
            continue

        m = DE_SUBHEAD.match(t)
        if m:
            flush_theme(page); flush_cur(); flush_vocab(page)
            sub_head = m.group(2)
            in_theme_table = False
            continue

        if DE_GROUP.match(t):
            flush_theme(page); flush_cur(); flush_vocab(page)
            in_theme_table = False
            continue

        if DE_TABLE_CAP.match(t):
            flush_theme(page)
            # 「表 2 初中必修课程主题内容」开主题表；「表 3 …篇章类别」不收
            in_theme_table = '主题内容' in t
            continue

        # 表头行。pypdf 会把同一视觉行上的两个表头单元格合成一行「主题 内容」，
        # 只比对单个词会漏掉，漏掉的后果是它被当成主题名粘到下一行主题上
        # （出现过 subTopic="主题 内容个人生活"）。所以按「整行的词全是表头词」判。
        if t.split() and all(w in DE_TH for w in t.split()):
            continue

        # 必修：主题内容表。左栏（主题名，x≈92）竖排两行，右栏（描述，x≈125/145）
        if in_theme_table:
            if x < 120:
                if theme_buf:          # 上一行的描述已经结束
                    flush_theme(page)
                theme_name = (theme_name or '') + t
            else:
                theme_buf.append(t)
            continue

        # 必修：词汇量要求（「3. 词汇」底下的整段）
        if sub_head == '词汇':
            if vocab is None:
                vocab = (row('德语', course, '', stage, None, '3', '词汇',
                             '', page, '内容要求'), [])
            vocab[1].append(t)
            continue

        # 选择性必修 / 选修：`1.1 建筑与市容`、`1.1 水与石（C1）`
        m = ITEM_2.match(t)
        if m:
            flush_cur()
            name = m.group(2)
            lvl = None
            lm = re.search(r'（([CG]\d)）$', name)
            if lm:
                lvl, name = lm.group(1), name[:lm.start()]
            cur = (row('德语', course, '', lvl, None, m.group(1), name,
                       '', page, '内容要求'), [])
            continue
        if cur:
            cur[1].append(t)
        else:
            stats['skipped_prose'] += 1

    flush_theme(last); flush_cur(); flush_vocab(last)

    # ── 五、学业质量（二）学业质量水平 表 6 ──
    # 德语课程内容一章没有能力断言，成规模的断言只在这张表里（C1~C5 / G1~G5，
    # 每级 4 条，共 40 条）。单独标 section=学业质量，下游要不要用自己决定。
    qrows, qfirst, qlast = doc_lines(PDFS['德语'], DE_QUALITY_HEAD, DE_QUALITY_END)
    qsink = ItemSink()
    stage, level = None, None
    for page, x, t in qrows:
        if t.split() and all(w in DE_TH for w in t.split()):
            continue
        m = DE_STAGE.match(t)
        if m:
            qsink.close()
            stage = t
            continue
        m = DE_LEVEL.match(t)
        if m:
            qsink.close()
            level = m.group(1)
            continue
        if PAGE_NO.match(t) and x < 140:      # 「水平」栏的裸级别数字
            continue
        m = DE_QUALITY_ITEM.match(t)
        if m:
            qsink.open(row('德语', None, '', stage, None, m.group(1), level,
                           '', page, '学业质量'), m.group(2))
            continue
        if qsink.cur:
            qsink.feed(t)
        else:
            stats['skipped_prose_quality'] += 1
    qsink.close()
    out.extend(qsink.rows)
    return out, stats, (first, last, qfirst, qlast)


# ─────────────────────────── 驱动 ───────────────────────────

EXTRACTORS = {
    '地理': lambda: extract_dili_yinyue('地理', PDFS['地理'], DILI_MODS, True),
    '音乐': lambda: extract_dili_yinyue('音乐', PDFS['音乐'],
                                        [(YINYUE_MOD, '模块')], False),
    '美术': extract_meishu,
    '思想政治': extract_sizheng,
    '德语': extract_deyu,
}


def sanity(subject, rows):
    """抽完自查：编号是否连续、正文是否混进页眉页脚、是否有超短/超长条目。"""
    warn = []
    # 编号在每个「模块 + 主题前缀」内部重新从 1 开始（地理换模块归零、
    # 思想政治每个主题归零），所以分组键必须带上前缀，否则全是假警报。
    groups = {}
    for r in rows:
        if not r['code'] or not re.fullmatch(r'\d+(\.\d+)?', r['code']):
            continue
        prefix = r['code'].rsplit('.', 1)[0] if '.' in r['code'] else ''
        key = (r['section'], r['course'], r['courseNo'], r['topic'], r['subTopic'], prefix)
        groups.setdefault(key, []).append(int(r['code'].rsplit('.', 1)[-1]))
    for key, nums in groups.items():
        if len(nums) < 2:
            continue
        if nums != sorted(nums) or len(set(nums)) != len(nums) \
                or max(nums) - min(nums) + 1 != len(nums):
            warn.append(f'{subject} {key} 编号有跳号/重号: {nums}')
    for r in rows:
        t = r['text']
        if re.search(r'普通高中.{1,10}课程标准|│|◆|续表', t):
            warn.append(f"{subject} p{r['page']} 正文混入版式噪声: {t[:40]}")
        if r['section'] == '内容要求' and len(t) < 6:
            warn.append(f"{subject} p{r['page']} 条目过短: {t!r}")
        if len(t) > 900:
            warn.append(f"{subject} p{r['page']} 条目过长({len(t)}): {t[:40]}")
    return warn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', help='只抽一科')
    ap.add_argument('--report', action='store_true', help='只统计，不写盘')
    args = ap.parse_args()

    targets = [args.only] if args.only else list(EXTRACTORS)
    for s in targets:
        if s not in EXTRACTORS:
            raise SystemExit(f'未知学科 {s}，可选：{"/".join(EXTRACTORS)}')

    if not args.report:
        OUT.mkdir(parents=True, exist_ok=True)

    all_warn = []
    for subject in targets:
        STUCK_HEAD.clear()
        rows, stats, span = EXTRACTORS[subject]()
        warn = sanity(subject, rows)
        all_warn += warn
        by_sec = Counter(r['section'] for r in rows)
        by_course = Counter(r['course'] for r in rows)
        print(f'── {subject}  共 {len(rows)} 条  页范围 {span}')
        print(f'   section: {dict(by_sec)}')
        print(f'   course : {dict(by_course)}')
        if stats:
            print(f'   跳过的无编号散文行: {dict(stats)}')
        if STUCK_HEAD:
            print(f'   页眉与正文粘连行(已剜掉页眉): {dict(STUCK_HEAD)}')
        for w in warn:
            print(f'   ! {w}')
        if not args.report:
            path = OUT / f'{subject}.jsonl'
            with path.open('w', encoding='utf-8') as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + '\n')
            print(f'   → {path.relative_to(ROOT)}')

    if not args.report and all_warn:
        (OUT / 'warnings.txt').write_text('\n'.join(all_warn) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
