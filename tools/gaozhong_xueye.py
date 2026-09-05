#!/usr/bin/env python3
"""
gaozhong_xueye.py — 抽高中课标【五、学业质量】章的质量描述条目。**纯规则，零模型调用。**

## 为什么要抽这一章

现有高中管线只挖【四、课程内容 / 内容要求】。但对不少学科来说，
**可判定的能力断言集中在【五、学业质量】而不是【内容要求】**。音乐是最极端的例子：
内容要求抽出 62 条（多为"感受/体验/参与"这类不可判定的表述），
学业质量抽出 121 条，长成「能用所学乐器较完整地演奏短小乐曲（1~2首）」
「能对无升降号调内的自然音程……进行听辨，并用乐谱准确记录下来」——
带数量、带条件、带可观察行为，直接就是能力断言。

而且音乐/美术/德语的条目自带官方素养标注「（素养1、3）」，地理自带
「（综合思维）」——这是课标自己给的权威标签，不是我们贴的。

## 六种版式（踩坑记录）

所有学科的【五、学业质量】都是「（一）学业质量内涵 + （二）学业质量水平
+（三）学业质量水平与考试评价的关系」。可抽的只有（二），它是一张
`水平 × 质量描述` 的表。**表的行怎么编号，二十本书有六种做法：**

### A. `L-N` 编号，水平写在编号里（13 科）
    语文 英语 思想政治 历史 地理 化学 生物学 信息技术 通用技术 日语 俄语 法语 德语
        水平 质量描述
        1
        1-1 有主动积累的意识，……
        1-2 在理解语言时，……
    左侧「水平」格是个裸数字，和页码同形。**不能按「裸数字即噪声」剜**——
    页码在版心外（x≤100 或 x≥430），表格单元格在 x≈109~118，只能按 x 区分
    （沿用 gaozhong_extract2 的结论）。好在这一族的水平已经写进 code 的第一位，
    左侧格丢了也不影响，真正需要 x 判据的是下面 B、C 两族。
    **坑**：美术 p43 出现过「1 1-4 能选择自己所喜欢的艺术家作品……」——
    水平格和条目被 pypdf 合成了一行。所以条目正则要允许一个前导水平格。

### B. `（N）` 编号，水平只在左侧格里（1 科：物理）
        水平 质量描述
        1
        （1）初步了解所学的物理概念和规律，……
        （2）能说出一些所学的简单的物理模型；……
    左侧那个裸数字是**唯一**的水平来源，剜掉就再也拼不回来。

### C. `N.` 编号，水平只在左侧格里（1 科：西班牙语）
        1
        1. 能够通过学习西班牙语基础知识，……
    同 B，且条目编号每换一个水平就从 1 重来。

### D. 模块 × 水平（3 科：音乐 美术 体育与健康）
    音乐  模块1 ：音乐鉴赏          ← 「1」和「：」之间那个空格是排版
    美术  【选择性必修课程】/ 模块1 绘画
    体育  1. 必修必学内容学业质量水平 / （1）体能模块学业质量水平
    条目仍是 `L-N`，但 **code 单独不唯一**：必修模块1 和选择性必修模块1
    都从 1-1 开始。音乐的模块标题里没有课程类型，只有「模块1」，
    所以课程类型必须靠模块名去内容要求产物（tools/out/gaozhong2/*.jsonl）里查。
    美术和体育的章内自带【必修课程】/「1. 必修必学内容」这类标题，不必外查，
    但仍然拿内容要求的模块名做交叉核对。

### E. 素养维度 × 课程类型 × 水平（1 科：艺术）
        1. 艺术感知
        （1）必修模块：艺术与生活、艺术与文化、艺术与科学
        水平 质量描述
        1   能了解艺术的语言特征和形式法则，并举例说明。
        （2）选择性必修模块：美术创意实践、音乐情境表演、……
        水平 质量描述
        1
        美术创意实践：能了解美术的主要类型及表现形式。
        音乐情境表演：能了解音乐要素和形式的表现特点。
    选择性必修的每一格里按模块名再分行，一行一个模块——所以一格拆成 5 条。

### F. 无编号，靠段落缩进分块（1 科：数学）
        水平 质量描述
        水平一
        能够在熟悉的情境中，直接抽象出数学概念和规则；……
        能够在熟悉的数学情境中，解释数学概念和规则的含义，……
    每级水平 4 段，分别对应课标前面列的「情境与问题 / 知识与技能 /
    思维与表达 / 交流与反思」四个方面，但**页面上没有任何编号或小标题**，
    只有段首缩进。靠 pypdf visitor 的 x：段首行 x 比正文行大约一个字。
    数学 PDF 另有个已知毛病：正文里塞满排版空格（「形成简单 的 数 学 命 题」），
    这是 pypdf 在这本书上的真实取字结果，仓库既有产物（anchors/math.jsonl）
    也是这样，**不改**。

## 条目终结标记

音乐/美术/德语条目尾部有「（素养1、3）」，地理有「（综合思维）」。
**页尾条目会把下一页的页眉/表头吸进来**（实测音乐有 9 条粘上了
「（2017年版2020年修订）」「水平质量描述」）。两道防线：
  1. 行级剜噪声（页眉/页码/续表/表头），从源头就不让它们进条目；
  2. 有素养标记的学科，再断言标记必须落在条目末尾，不在末尾就报警。
只靠第 2 条不够（没有标记的 16 科用不上），只靠第 1 条也不敢（噪声可能有新花样），
两条都要。

## 逐字校验

写盘前每条都过一遍：把条目正文按来源页切段，去掉所有空白，
要求每一段是**该页 pypdf 原始取字**（只做全角数字归一，不剜任何东西）
的连续子串，且同一页内各段的位置严格递增。
这一步不依赖上面任何一条清洗规则——清洗只决定在哪里下刀，
校验保证刀口两侧的字一个没变、没重、没乱序。校验不过直接退出，不写盘。

## 用法

    python3 tools/gaozhong_xueye.py                 # 全抽，写 tools/out/gaozhong-xueye/
    python3 tools/gaozhong_xueye.py --only 音乐
    python3 tools/gaozhong_xueye.py --report        # 只统计，不写盘

输出字段在 tools/out/gaozhong*/ 的基础上加了三个：
    level（水平，整数） literacy（课标自带的素养标签，没有就是 []） pages（跨页条目的来源页）
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gaozhong_extract2 import norm  # noqa: E402  取字归一，与内容要求管线同源

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'sources/standards-gaozhong'
OUT = ROOT / 'tools/out/gaozhong-xueye'
NEIRONG = [ROOT / 'tools/out/gaozhong2', ROOT / 'tools/out/gaozhong']

# ─────────────────────────── 取字 ───────────────────────────

STUCK_HEAD = Counter()
# 数学那本书里有一批字形缺失的标题，抽出来是「/G3D/G25/G30/G3E/G29/G3F」。
GLYPH_JUNK = re.compile(r'^(?:/G[0-9A-Fa-f]{2,4})+$')
# 页眉。**坑**：数学那本书的页眉里每个数字之间都塞了空格
# （「普通高中数学课程标准 （2 0 1 7年版2 0 2 0年修订）」），
# gaozhong_extract2 里那条按 2017/2020 死抠的正则匹配不上，
# 于是整条页眉被当成正文续行接到 2-2 尾巴上。这里放宽成「字间可有空白」。
RUNNING_HEAD = re.compile(
    r'│[^│]*│|普\s*通\s*高\s*中[^（）]{1,12}课\s*程\s*标\s*准\s*（[^）]{0,40}）')
BARE_NUM = re.compile(r'^\d{1,3}$')


def page_number_offset(reader):
    """页码 = PDF 页序（0 起）+ offset。返回 (offset, 命中页数 / 总页数)。

    **为什么不能沿用 gaozhong_extract2 的「裸数字在版心外即页码」**：
    物理和西班牙语的水平格就是个裸数字，且落在版心边上（x≈91），
    按 x 剜会把水平剜掉——而这两科的水平**只写在这个格里**，没有第二处可取。
    改成按值剜：先投票定出页码偏移，然后只剜那个数值等于本页页码的裸数字行。
    **坑**：数学那本书的页码 pypdf 取出来是**倒着的**——第 75 页给的是「5 7」，
    第 76 页给的是「6 7」。所以候选值要连反串一起投票，剜的时候也认反串。
    """
    votes = defaultdict(set)
    for i, page in enumerate(reader.pages):
        for line in (page.extract_text() or '').split('\n'):
            t = re.sub(r'\s+', '', norm(line))
            if BARE_NUM.fullmatch(t):
                for v in {int(t), int(t[::-1])}:
                    votes[v - i].add(i)
    if not votes:
        return None, 0.0
    off, pages = max(votes.items(), key=lambda kv: len(kv[1]))
    return off, len(pages) / max(1, len(reader.pages))


def page_lines(page, pageno, offset):
    """一页 → [(x0, text)]，保持 pypdf 阅读顺序，已剜页眉/页码/续表/缺字形标题。

    x0 取该行第一个非空文本块的 tm[4]。visitor 各块文本拼接 == extract_text()，
    所以切出来的行和 extract_text() 的行是同一批，只是多带了一个 x。
    （做法沿用 gaozhong_extract2，那里有为什么用 pypdf 而不是 PyMuPDF 的记录。）
    """
    chunks = []
    page.extract_text(visitor_text=lambda text, cm, tm, fd, fs: chunks.append((tm[4], text)))

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

    pageno_str = str(pageno + offset) if offset is not None else None
    out = []
    for x, raw in lines:
        t = norm(raw)
        if not t or t == '续表' or GLYPH_JUNK.match(t):
            continue
        if RUNNING_HEAD.search(t):
            cleaned = norm(RUNNING_HEAD.sub('', t))
            if not cleaned:
                continue
            STUCK_HEAD[cleaned[:30]] += 1
            t = cleaned
        squashed = re.sub(r'\s+', '', t)
        if BARE_NUM.fullmatch(squashed) and pageno_str in (squashed, squashed[::-1]):
            continue
        out.append((x if x is not None else 0.0, t))
    return out


# ─────────────────────────── 章定位 ───────────────────────────

# 起止都用「独占一行的标题」判定，避开目录页（目录行带点线，fullmatch 不中）。
START_DEFAULT = re.compile(r'五、\s*学业质量')
# （三）是"学业质量水平与考试评价的关系"，是散文不是条目，抽到它为止。
END_PATS = [re.compile(r'（三）\s*学业质量水平与考试评价的关系'),
            re.compile(r'（三）\s*学业质量与考试评价的关系'),
            re.compile(r'六、\s*实施建议')]

# 数学这本书的章标题是缺字形的（抽出来是 /G3D/G25/G30/G3E/G29/G3F），
# 匹配不上「五、学业质量」，改用它下面那行小标题定位。
START_OVERRIDE = {'数学': re.compile(r'（一）\s*学业质量内涵')}

# ─────────────────────────── 行级噪声 ───────────────────────────

# page_lines 已经剜掉页眉、页码、续表。这里再剜表头单元格。
TABLE_HEAD = re.compile(r'^(水平|序号|等级)\s*质量描述$|^质量描述$|^水平$|^序号$')
SEC_HEAD = re.compile(r'^（[一二三四]）\s*学业质量(内涵|水平)?.*$')
CHAP_HEAD = re.compile(r'^五、\s*学业质量$')
# 表题：「表 8 日语课程的学业质量水平」「表 12 高中英语学业质量水平一」。
TABLE_CAPTION = re.compile(r'^表\s*\d+\s*[^。；]{0,26}(?:学业质量|水平)[^。；]{0,10}$')
# 水平标题行。**这三种写法都得认，而且它们在续页顶部会重印**：
#   英语「水平一」+「表 12 高中英语学业质量水平一」  日语「四级」  俄语「水平 1」
# 早先把它们当普通行，结果整行被接到上一条尾巴上（日语 4-3 末尾粘着「五级」）；
# 当噪声直接跳过又会把下一水平的前言散文接到上一条上。所以按「分组」处理：
# 水平变了就 flush，没变（续页重印）就跳过。
LEVEL_HEAD = re.compile(r'^(?:表\s*\d+\s*[^。；]{0,24}?水平\s*([一二三四五六])'
                        r'|水平\s*([一二三四五六]|\d)'
                        r'|([一二三四五六])级)$')
DE_STAGE_HEAD = re.compile(r'^(初中|高中)阶段$')
CN_LEVEL = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6}


def level_head(b, m, page):
    v = m.group(1) or m.group(2) or m.group(3)
    return dict(level=CN_LEVEL.get(v, v if not v.isdigit() else int(v)))


def de_stage_head(b, m, page):
    return dict(topic=f'{m.group(1)}阶段')


def furniture(t):
    return bool(TABLE_HEAD.match(t) or CHAP_HEAD.match(t) or TABLE_CAPTION.match(t))


# ─────────────────────────── 素养标签 ───────────────────────────

# 「（素养1、3）」里的数字 → 该科核心素养的官方名称。
# 名称取自各科课标「二、学科核心素养与课程目标」，装载时会回到 PDF 里核对。
LITERACY = {
    '音乐': ['审美感知', '艺术表现', '文化理解'],
    '美术': ['图像识读', '美术表现', '审美判断', '创意实践', '文化理解'],
    '德语': ['语言能力', '文化意识', '思维品质', '学习能力'],
}
LIT_NUM = re.compile(r'（\s*素养\s*([\d、，,\s]+)\s*）\s*$')
# 地理不写编号，直接写素养名。
DILI_LIT = ['人地协调观', '综合思维', '区域认知', '地理实践力']
LIT_NAME = re.compile(r'（\s*((?:%s)(?:[、，,\s]*(?:%s))*)\s*）\s*$'
                      % ('|'.join(DILI_LIT), '|'.join(DILI_LIT)))


def split_literacy(subject, text):
    """把条目尾部的官方素养标注拆出来。返回 (正文, [素养名])。"""
    m = LIT_NUM.search(text)
    if m and subject in LITERACY:
        names = LITERACY[subject]
        idx = [int(d) for d in re.findall(r'\d+', m.group(1))]
        bad = [i for i in idx if not 1 <= i <= len(names)]
        if bad:
            raise SystemExit(f'✗ {subject} 素养编号越界 {bad}：{text[:60]}')
        return text[:m.start()].rstrip(), [names[i - 1] for i in idx]
    m = LIT_NAME.search(text)
    if m and subject == '地理':
        return text[:m.start()].rstrip(), re.findall('|'.join(DILI_LIT), m.group(1))
    return text, []


# ─────────────────────────── 条目正则 ───────────────────────────

# 允许一个前导「水平」格：美术 p43「1 1-4 能选择自己所喜欢的……」是一行。
ITEM_CODE = re.compile(r'^(?:(\d)\s+)?(\d{1,2})\s*[-—–]\s*(\d{1,2})(?:\s+|$|(?=[^\d\s]))')
ITEM_PAREN = re.compile(r'^（(\d{1,2})）\s*')
ITEM_DOT = re.compile(r'^(\d{1,2})\s*[.．]\s*(?=\S)')
LEVEL_CELL = re.compile(r'^([1-9])$')


# ─────────────────────────── 抽取引擎 ───────────────────────────

class Chapter:
    """一科的【五、学业质量】章：清洗后的行 + 每页的原始取字（供逐字校验）。"""

    def __init__(self, subject, pdf_name):
        self.subject = subject
        reader = PdfReader(SRC / pdf_name)
        # 原始取字：只做全角归一，不剜任何东西。校验用的就是它。
        self.raw = {i + 1: (p.extract_text() or '').translate(_RAW_TRANS)
                    for i, p in enumerate(reader.pages)}
        self.offset, cover = page_number_offset(reader)
        if cover < 0.5:
            raise SystemExit(f'✗ {subject}: 页码偏移投票只覆盖 {cover:.0%} 的页，不敢按值剜页码')
        cleaned = [page_lines(p, i, self.offset) for i, p in enumerate(reader.pages)]

        start_pat = START_OVERRIDE.get(subject, START_DEFAULT)
        start = self._find(cleaned, start_pat, 0)
        if start is None:
            raise SystemExit(f'✗ {subject}: 找不到章头 {start_pat.pattern}')
        end, end_pat = None, None
        for pat in END_PATS:
            end = self._find(cleaned, pat, start + 1)
            if end is not None:
                end_pat = pat
                break
        if end is None:
            raise SystemExit(f'✗ {subject}: 找不到章尾')

        self.lines, started = [], False
        for i in range(start, end + 1):
            for x, t in cleaned[i]:
                if not started:
                    if not start_pat.fullmatch(t):
                        continue
                    started = True
                if i == end and end_pat.fullmatch(t):
                    self.span = (start + 1, end + 1)
                    return
                self.lines.append((i + 1, x, t))
        self.span = (start + 1, end + 1)

    @staticmethod
    def _find(cleaned, pat, frm):
        for i in range(frm, len(cleaned)):
            for _, t in cleaned[i]:
                if pat.fullmatch(t):
                    return i
        return None


_RAW_TRANS = str.maketrans({**{' ': ' ', ' ': ' ', ' ': ' ', ' ': ' ', '　': ' ',
                               ' ': ' ', '﻿': ''},
                            **{chr(c): chr(c - 0xFEE0) for c in range(0xFF10, 0xFF1A)},
                            **{chr(c): chr(c - 0xFEE0) for c in range(0xFF21, 0xFF3B)},
                            **{chr(c): chr(c - 0xFEE0) for c in range(0xFF41, 0xFF5B)}})


class Builder:
    """按行喂进来，攒出条目。每条记住它在各页上各占了哪一段，供逐字校验。"""

    def __init__(self, subject):
        self.subject = subject
        self.rows = []
        self.cur = None
        self.ctx = {}
        self.prose = Counter()
        self.unclaimed = []

    def context(self, **kw):
        self.flush()
        self.ctx.update(kw)

    def start(self, page, code, level, text):
        self.flush()
        self.cur = {'code': code, 'level': level, 'spans': [[page, text]],
                    'ctx': dict(self.ctx)}

    def cont(self, page, text):
        if self.cur is None:
            return False
        if self.cur['spans'][-1][0] == page:
            self.cur['spans'][-1][1] += text
        else:
            self.cur['spans'].append([page, text])
        return True

    def flush(self):
        if self.cur is None:
            return
        c = self.cur
        self.cur = None
        text = ''.join(s[1] for s in c['spans']).strip()
        text, lit = split_literacy(self.subject, text)
        # 标记必须落在末尾。落在中间说明尾部粘了下一页的东西。
        body = re.sub(r'\s+', '', text)
        if re.search(r'（\s*素养', body) and self.subject in LITERACY:
            self.unclaimed.append(f"素养标记不在条目末尾: {c['code']} {text[-50:]}")
        c['text'] = text
        # 艺术的素养标签不写在条目尾巴上，而是整张表的表头（「1. 艺术感知」），
        # 由分组塞进 ctx，这里兜底取出来。
        c['literacy'] = lit or list(c['ctx'].get('_literacy') or [])
        self.rows.append(c)


def emit(subject, b):
    """Builder 的内部行 → 落盘用的字典。"""
    out = []
    for c in b.rows:
        ctx = c['ctx']
        pages = sorted({p for p, _ in c['spans']})
        out.append({
            'subject': subject,
            'course': ctx.get('course'),
            'courseNo': ctx.get('courseNo', ''),
            'topic': ctx.get('topic'),
            'topicName': ctx.get('topicName'),
            'code': c['code'],
            'subTopic': ctx.get('subTopic'),
            'text': c['text'],
            'page': pages[0],
            'section': '学业质量',
            'examples': [],
            'level': c['level'],
            'literacy': c['literacy'],
            'pages': pages,
            '_spans': c['spans'],
        })
    return out


# ─────────────────────────── 走行器 ───────────────────────────

def _accept_code(b, lvl, n):
    """条目编号必须接得上，接不上就当续行。

    **坑**：正文里「掌握 2—3 种美术鉴赏方法」这类写法和条目编号同形。
    只靠正则会把它当成新条目，把上一条腰斩。加一道序号连续性判据：
    组内第一条必须是 L-1，之后要么同水平 +1，要么进位到下一水平的第 1 条。
    """
    e = b.ctx.get('_expect')
    if e is None:
        return n == 1
    el, en = e
    return (lvl == el and n == en + 1) or (lvl == el + 1 and n == 1)


def walk_code(ch, b, groups=()):
    """A 族（水平写在编号里）和 D 族（模块 × 水平）共用。"""
    for page, x, t in ch.lines:
        if furniture(t):
            # 表头「水平 质量描述」在每一张续页顶部都会重印。
            # **绝不能顺手 flush**——地理 4-2 跨 p37/p38，p38 顶上就是这行表头，
            # flush 会把条目砍在「分析岩」三个字上。当版式噪声跳过即可。
            continue
        if SEC_HEAD.match(t):
            b.flush()
            continue
        upd = None
        for pat, fn in groups:
            m = pat.match(t)
            if m:
                upd = fn(b, m, page)
                break
        if upd is not None:
            # **坑**：续页的表头会把分组标题再写一遍（德语每页顶部重印「（C3）」，
            # 数学重印「水平一」）。照单全收会 flush 掉跨页条目、并把编号序列重置，
            # 于是 3-3、3-4 全被判成「接不上」丢掉。分组没变就当版式噪声跳过。
            if all(b.ctx.get(k) == v for k, v in upd.items()):
                continue
            b.flush()
            b.ctx.update(upd)
            b.ctx['_expect'] = None
            continue
        if LEVEL_CELL.fullmatch(t):
            # 左侧「水平」格。水平已经写在 code 里，这格丢掉不可惜；
            # **但绝不能顺手 flush**——续页顶部会把这一格再印一遍
            # （地理 4-2 跨 p37/p38，p38 顶上就是「4」），flush 会把条目腰斩，
            # 实测地理 4-2 被砍在「分析岩」三个字上。
            continue
        m = ITEM_CODE.match(t)
        if m:
            cell, lvl, n = m.group(1), int(m.group(2)), int(m.group(3))
            if _accept_code(b, lvl, n):
                if cell is not None and int(cell) != lvl:
                    b.unclaimed.append(f'p{page} 前导水平格 {cell} 与编号 {lvl}-{n} 不符')
                b.start(page, f'{lvl}-{n}', lvl, t[m.end():])
                b.ctx['_expect'] = (lvl, n)
                continue
            if b.cur is None:
                b.unclaimed.append(f'p{page} 编号 {lvl}-{n} 接不上且无上文: {t[:40]}')
                continue
            b.unclaimed.append(f'p{page} 编号 {lvl}-{n} 接不上，按续行处理: {t[:40]}')
        if b.cont(page, t):
            continue
        b.prose[t[:28]] += 1


def walk_cell_level(ch, b, item_pat):
    """B 族（物理，条目是「（N）」）和 C 族（西班牙语，条目是「N.」）。

    这两族的水平只写在左侧那个裸数字格里，剜掉就拼不回来了。
    """
    for page, x, t in ch.lines:
        if furniture(t):
            # 表头「水平 质量描述」在每一张续页顶部都会重印。
            # **绝不能顺手 flush**——地理 4-2 跨 p37/p38，p38 顶上就是这行表头，
            # flush 会把条目砍在「分析岩」三个字上。当版式噪声跳过即可。
            continue
        if SEC_HEAD.match(t):
            b.flush()
            continue
        m = LEVEL_CELL.fullmatch(t)
        if m:
            lvl = int(m.group(1))
            if b.ctx.get('level') == lvl:    # 续页重印的水平格，不是新水平
                continue
            b.flush()
            b.ctx['level'] = lvl
            b.ctx['_expect'] = None
            continue
        m = item_pat.match(t)
        if m:
            lvl = b.ctx.get('level')
            n = int(m.group(1))
            if lvl is not None and _accept_code(b, lvl, n):
                b.start(page, f'{lvl}-{n}', lvl, t[m.end():])
                b.ctx['_expect'] = (lvl, n)
                continue
            if b.cur is None:
                b.unclaimed.append(f'p{page} 条目 {n} 无所属水平: {t[:40]}')
                continue
            b.unclaimed.append(f'p{page} 条目编号 {n} 接不上，按续行处理: {t[:40]}')
        if b.cont(page, t):
            continue
        b.prose[t[:28]] += 1


ART_DIM = re.compile(r'^(\d)\s*[.．]\s*(艺术感知|创意表达|审美情趣|文化理解)$')
ART_COURSE = re.compile(r'^（(\d)）\s*(必修|选择性必修)模块[：:]\s*(.*)$')
ART_MODULE = re.compile(r'^(美术创意实践|音乐情境表演|舞蹈创编与表演|戏剧创编与表演|影视与数字媒体艺术实践)\s*[：:]\s*(.*)$')
ART_LEVEL_TEXT = re.compile(r'^([1-3])\s+(?=\S)')


def walk_art(ch, b):
    """艺术：素养维度 × 课程类型 × 水平；选择性必修的一格里还按模块名分行。

    必修格是「1   能了解艺术的语言特征和形式法则，并举例说明。」——水平和正文同行；
    选择性必修格是裸数字水平 + 五行「模块名：正文」。两种都要认。
    """
    for page, x, t in ch.lines:
        if furniture(t):
            # 表头「水平 质量描述」在每一张续页顶部都会重印。
            # **绝不能顺手 flush**——地理 4-2 跨 p37/p38，p38 顶上就是这行表头，
            # flush 会把条目砍在「分析岩」三个字上。当版式噪声跳过即可。
            continue
        if SEC_HEAD.match(t):
            b.flush()
            continue
        m = ART_DIM.match(t)
        if m:
            b.flush()
            # 艺术的四个维度就是它的四个学科核心素养（课标 p12：
            # 「艺术学科核心素养主要包括四个方面：艺术感知、创意表达、审美情趣、文化理解」），
            # 所以维度即官方素养标签，不是我们贴的。
            b.ctx.update(topicName=m.group(2), _literacy=[m.group(2)], topic=None,
                         course=None, courseNo='', subTopic=None, level=None)
            continue
        m = ART_COURSE.match(t)
        if m:
            b.flush()
            # 注意别把 topicName（维度名）清掉——课程类型是维度下面的一层。
            b.ctx.update(course=m.group(2), courseNo='', subTopic=None, level=None)
            continue
        m = LEVEL_CELL.fullmatch(t)
        if m:
            lvl = int(m.group(1))
            if b.ctx.get('level') == lvl:    # 续页重印的水平格
                continue
            b.flush()
            b.ctx['level'] = lvl
            b.ctx['subTopic'] = None
            continue
        m = ART_MODULE.match(t)
        if m and b.ctx.get('course') == '选择性必修':
            lvl = b.ctx.get('level')
            b.ctx['subTopic'] = m.group(1)
            b.start(page, str(lvl), lvl, m.group(2))
            continue
        m = ART_LEVEL_TEXT.match(t)
        if m and b.ctx.get('course') == '必修':
            lvl = int(m.group(1))
            b.ctx['level'] = lvl
            b.ctx['subTopic'] = None
            b.start(page, str(lvl), lvl, t[m.end():])
            continue
        if b.cont(page, t):
            continue
        b.prose[t[:28]] += 1


MATH_LEVEL = re.compile(r'^水平([一二三])$')
CN_NUM = {'一': 1, '二': 2, '三': 3}


def walk_math(ch, b):
    """数学：每级水平 4 段，页面上没有任何编号，只有段首缩进。

    x 取自 pypdf visitor。段首行比正文行右移约两个字（p83 是 176.8 对 155.8）。
    **坑一**：版心 x 每页都不一样（p83 正文 155.8，p84 正文 147.1），
    基准必须按页取众数，拿全章的众数去卡会整页判错。
    **坑二**：续页顶部会把「水平一」再印一遍，照单全收会 flush 掉跨页的那一段
    并把段计数清零。分组没变就当版式噪声跳过。
    抽完断言每级恰好 4 段——对不上就说明缩进判据在这本书上失效，宁可报错不出货。
    """
    per_page = defaultdict(Counter)
    for page, x, t in ch.lines:
        if x:
            per_page[page][round(x)] += 1
    base = {p: c.most_common(1)[0][0] for p, c in per_page.items()}
    n = 0
    for page, x, t in ch.lines:
        if furniture(t):
            # 表头「水平 质量描述」在每一张续页顶部都会重印。
            # **绝不能顺手 flush**——地理 4-2 跨 p37/p38，p38 顶上就是这行表头，
            # flush 会把条目砍在「分析岩」三个字上。当版式噪声跳过即可。
            continue
        if SEC_HEAD.match(t):
            b.flush()
            continue
        m = MATH_LEVEL.fullmatch(t)
        if m:
            lvl = CN_NUM[m.group(1)]
            if b.ctx.get('level') == lvl:
                continue
            b.flush()
            b.ctx['level'] = lvl
            n = 0
            continue
        if t.startswith('（参见案例'):     # 每级水平末尾的案例索引，不是能力断言
            b.flush()
            b.prose[t[:28]] += 1
            continue
        lvl = b.ctx.get('level')
        if lvl is not None and x and round(x) >= base[page] + 12:
            n += 1
            b.start(page, f'{lvl}-{n}', lvl, t)
            continue
        if b.cont(page, t):
            continue
        b.prose[t[:28]] += 1
    b.flush()
    per_level = Counter(r['level'] for r in b.rows)
    if set(per_level.values()) != {4}:
        raise SystemExit(f'✗ 数学：每级水平应当是 4 段，实际 {dict(per_level)}——缩进判据失效，不出货')


# ─────────────────────────── 模块名交叉核对 ───────────────────────────

def load_modmap(subject):
    """从内容要求产物里取 {模块名: (课程类型, 模块号)}。

    **坑（沿用 gaozhong_extract2 的结论）**：模块号在必修和选择性必修之间会重头数，
    所以「模块1」单独不唯一。音乐的学业质量表里只写「模块 1 ：音乐鉴赏」，
    课程类型只能靠模块名回内容要求里查。
    """
    out = {}
    for d in NEIRONG:
        p = d / f'{subject}.jsonl'
        if not p.exists():
            continue
        for line in p.open(encoding='utf-8'):
            if not line.strip():
                continue
            r = json.loads(line)
            name = r.get('topicName')
            if name and len(name) <= 12 and r.get('course'):
                out.setdefault(name, (r['course'], r.get('courseNo', '')))
        if out:
            break
    return out


def module_group(subject, need_course):
    """造一个「模块 N ：名字」的分组处理器。need_course=True 时课程类型必须外查。"""
    modmap = load_modmap(subject)

    def fn(b, m, page):
        no, name = (m.group(1) or ''), m.group(2).strip()
        hit = modmap.get(name)
        if need_course:
            if hit is None:
                b.unclaimed.append(f'p{page} 模块「{name}」在内容要求产物里查不到，课程类型无法判定')
                course, cno = None, no
            else:
                course, cno = hit
                if no and cno and no != cno:
                    b.unclaimed.append(f'p{page} 模块「{name}」章内编号 {no} 与内容要求 {cno} 不符')
        else:
            course, cno = b.ctx.get('course'), no
            if hit and hit[0] != course:
                b.unclaimed.append(f'p{page} 模块「{name}」章内课程类型 {course} 与内容要求 {hit[0]} 不符')
            if hit is None:
                b.prose[f'模块「{name}」内容要求产物里没有（选修模块无编号条目，属正常）'] += 1
        return dict(course=course, courseNo=cno, topicName=name,
                    topic=f'模块{no}' if no else '模块', subTopic=None)

    return fn


def course_group(b, m, page):
    return dict(course=m.group(1), courseNo='', topicName=None, topic=None, subTopic=None)


# ─────────────────────────── 各科配置 ───────────────────────────

MODULE_MUSIC = re.compile(r'^模块\s*(\d+)\s*[：:]\s*(.+)$')
MODULE_ART = re.compile(r'^模块\s*(\d*)\s*[  ]*(\S.*)$')
COURSE_BRACKET = re.compile(r'^【(必修|选择性必修|选修)课程】$')
PE_PART = re.compile(r'^\d\s*[.．]\s*(必修必学|必修选学)内容学业质量水平$')
PE_MODULE = re.compile(r'^（(\d+)）\s*(.+?)模块(阶段性)?学业质量水平(?:（(第[一二三]学年)）)?$')
DE_STAGE = re.compile(r'^（([CG])([1-5])）$')


def pe_part(b, m, page):
    return dict(course=m.group(1), courseNo='', topicName=None, topic=None, subTopic=None)


def pe_module(b, m, page):
    return dict(courseNo=m.group(1), topicName=m.group(2), topic=f'模块{m.group(1)}',
                subTopic=m.group(4))


def de_stage(b, m, page):
    kind, n = m.group(1), m.group(2)
    return dict(topic='初中阶段' if kind == 'C' else '高中阶段',
                subTopic=f'{kind}{n}', course=None, courseNo='', topicName=None)


# kind: code=A族  paren=B族(物理)  dot=C族(西班牙语)  art=E族  math=F族
SPECS = {
    '语文':       ('01-语文.pdf', 'code', ()),
    '数学':       ('02-数学.pdf', 'math', ()),
    '英语':       ('03-英语.pdf', 'code', ()),
    '思想政治':   ('04-思想政治.pdf', 'code', ()),
    '历史':       ('05-历史.pdf', 'code', ()),
    '地理':       ('06-地理.pdf', 'code', ()),
    '物理':       ('07-物理.pdf', 'paren', ()),
    '化学':       ('08-化学.pdf', 'code', ()),
    '生物学':     ('09-生物学.pdf', 'code', ()),
    '信息技术':   ('10-信息技术.pdf', 'code', ()),
    '通用技术':   ('11-通用技术.pdf', 'code', ()),
    '艺术':       ('12-艺术.pdf', 'art', ()),
    '音乐':       ('13-音乐.pdf', 'code',
                   ((COURSE_BRACKET, course_group), (MODULE_MUSIC, 'module:need'))),
    '美术':       ('14-美术.pdf', 'code',
                   ((COURSE_BRACKET, course_group), (MODULE_ART, 'module:have'))),
    '体育与健康': ('15-体育与健康.pdf', 'code', ((PE_PART, pe_part), (PE_MODULE, pe_module))),
    '日语':       ('16-日语.pdf', 'code', ()),
    '俄语':       ('17-俄语.pdf', 'code', ()),
    '德语':       ('18-德语.pdf', 'code', ((DE_STAGE_HEAD, de_stage_head), (DE_STAGE, de_stage))),
    '法语':       ('19-法语.pdf', 'code', ()),
    '西班牙语':   ('20-西班牙语.pdf', 'dot', ()),
}


def build_groups(subject, groups):
    out = []
    for pat, fn in tuple(groups) + ((LEVEL_HEAD, level_head),):
        if fn == 'module:need':
            fn = module_group(subject, True)
        elif fn == 'module:have':
            fn = module_group(subject, False)
        out.append((pat, fn))
    return tuple(out)


def extract(subject):
    pdf, kind, groups = SPECS[subject]
    ch = Chapter(subject, pdf)
    b = Builder(subject)
    if kind == 'code':
        walk_code(ch, b, build_groups(subject, groups))
    elif kind == 'paren':
        walk_cell_level(ch, b, ITEM_PAREN)
    elif kind == 'dot':
        walk_cell_level(ch, b, ITEM_DOT)
    elif kind == 'art':
        walk_art(ch, b)
    elif kind == 'math':
        walk_math(ch, b)
    b.flush()
    return ch, b, emit(subject, b)


# ─────────────────────────── 逐字校验 ───────────────────────────

def verify(ch, rows):
    """每条正文按来源页切段，要求每段是该页 pypdf 原始取字的连续子串，且页内位置递增。

    校验用的 ch.raw 没有经过任何清洗（只做了全角数字归一），所以这一步
    不依赖上面任何一条剜噪声的规则——清洗只决定在哪儿下刀，
    校验保证刀口两侧的字一个没变、没重、没乱序。
    """
    bad, cursor = [], defaultdict(int)
    ws = lambda s: re.sub(r'\s+', '', s)
    for r in rows:
        joined = ''
        for page, part in r['_spans']:
            joined += part
            needle = ws(part)
            if not needle:
                continue
            hay = ws(ch.raw.get(page, ''))
            i = hay.find(needle, cursor[page])
            if i < 0:
                bad.append(f"{r['code']} p{page} 不是原页连续子串: {part[:50]!r}")
            else:
                cursor[page] = i + len(needle)
        if not ws(joined).startswith(ws(r['text'])):
            bad.append(f"{r['code']} 正文不是取字结果的前缀（拆素养标记时出错）")
    return bad


# ─────────────────────────── 体检 ───────────────────────────

NOISE_IN_TEXT = re.compile(r'普通高中.{1,10}课程标准|│|续表|水平\s*质量描述|序号\s*质量描述|2017\s*年版')


def sanity(subject, rows):
    warn = []
    groups = defaultdict(list)
    for r in rows:
        key = (r['course'], r['courseNo'], r['topicName'], r['subTopic'])
        groups[key].append(r['code'])
    for key, codes in groups.items():
        if len(set(codes)) != len(codes):
            warn.append(f'{subject} {key} 有重号: {[c for c, n in Counter(codes).items() if n > 1]}')
        seq = [tuple(int(x) for x in re.findall(r'\d+', c)) for c in codes if re.fullmatch(r'\d+-\d+', c)]
        for a, z in zip(seq, seq[1:]):
            if not ((z[0] == a[0] and z[1] == a[1] + 1) or (z[0] == a[0] + 1 and z[1] == 1)):
                warn.append(f'{subject} {key} 编号不连续: {a} → {z}')
    for r in rows:
        if NOISE_IN_TEXT.search(r['text']):
            warn.append(f"{subject} p{r['page']} {r['code']} 正文混入版式噪声: {r['text'][:50]}")
        if len(r['text']) < 8:
            warn.append(f"{subject} p{r['page']} {r['code']} 条目过短: {r['text']!r}")
        if not re.search(r'[。；？！）」』.]\s*$', r['text']):
            # 实测这一条抓出 4 个学科的截断：地理 4-2 被砍在「分析岩」，
            # 日语 4-3 尾巴上粘着下一格的「五级」。留着当常设闸门。
            warn.append(f"{subject} p{r['page']} {r['code']} 不以句末标点收尾（疑似截断或粘连）: …{r['text'][-30:]}")
        if len(r['text']) > 1000:
            warn.append(f"{subject} p{r['page']} {r['code']} 条目过长({len(r['text'])}): {r['text'][:40]}")
    return warn


# ─────────────────────────── 复核清单 ───────────────────────────

FAMILY = {'code': 'A 水平×编号 L-N', 'code+': 'D 模块×水平，编号 L-N',
          'paren': 'B 编号（N），水平在左格', 'dot': 'C 编号 N.，水平在左格',
          'art': 'E 维度×课程×水平', 'math': 'F 无编号，靠段首缩进'}
# 德语和体育的分组不是「模块」，单独标注，免得表里写错。
FAMILY_OVERRIDE = {'德语': 'A′ 阶段 C1~C5/G1~G5 × 水平',
                   '体育与健康': 'D 必修必学/必修选学 × 模块 × 水平'}


def write_readme(stats):
    """产物清单页。**表里的数字全部由本函数从产物现算**，不手打——
    手打的数字过半年一定是假的。"""
    lines = ['# 高中课标【五、学业质量】抽取候选',
             '',
             '`python3 tools/gaozhong_xueye.py` 生成。**这是候选，不是 anchors**，',
             '复核通过之前不要往 `anchors/` 里写。',
             '',
             '每条都过了逐字校验：正文按来源页切段，每段必须是该页 pypdf 原始取字',
             '（只做全角数字归一，不剜任何东西）的连续子串，且同一页内各段位置严格递增。',
             '校验不过就不写盘。',
             '',
             '## 一览',
             '',
             '| 学科 | 条数 | 源页 | 版式 | 水平 | 官方素养标注 | 课程类型 |',
             '| --- | ---: | --- | --- | --- | --- | --- |']
    for st in stats:
        levels = '/'.join(str(k) for k in sorted(st['levels']))
        lit = f"{st['lit']}/{st['n']}" if st['lit'] else '—'
        courses = '、'.join(str(c) for c in st['courses'] if c) or '—'
        lines.append(f"| {st['subject']} | {st['n']} | p{st['span'][0]}–p{st['span'][1]} | "
                     f"{FAMILY_OVERRIDE.get(st['subject'], FAMILY[st['kind']])} | "
                     f"{levels} | {lit} | {courses} |")
    lines += ['', f"合计 **{sum(st['n'] for st in stats)}** 条。", '',
              '## 复核时重点看什么',
              '',
              '1. **课程类型**：音乐的模块标题里没有课程类型，是拿模块名回',
              '   `tools/out/gaozhong2/音乐.jsonl` 查出来的；美术/体育/艺术是章内自带的标题。',
              '   美术的 5 个选修模块在内容要求里没有编号条目，只在学业质量里有，属正常。',
              '2. **素养标注**：音乐/美术/德语来自条目尾部的「（素养N）」，地理来自「（综合思维）」这类',
              '   直接写名字的括号，艺术来自表头的维度名——**都是课标自己标的，不是我们贴的**。',
              '   其余 15 科的条目上没有标注；但化学、物理、生物学等在「（一）学业质量内涵」里用散文',
              '   写了「序号 N 侧重对应素养 M」的对应关系，那是另一道工序，本工具没抽。',
              '3. **粒度**：语文/思想政治/化学这类一条 200~340 字、里面串着五六个分号的条目，',
              '   是一条还是该再切成能力断言，是下一道工序（切分）的事，本工具只负责逐字转写。',
              '4. **数学**：页面上没有任何编号，12 条是按段首缩进切的，每级水平 4 段。',
              '   这 4 段依次对应课标前面列的「情境与问题 / 知识与技能 / 思维与表达 / 交流与反思」，',
              '   但页面上**没有印这四个小标题**，所以产物里没有写 dimension——那是推断不是转写。',
              '5. **体育与健康**：必修选学只印了 6 个模块的第一学年要求（足球/跳远/健身健美操/',
              '   蛙泳/防身术/花样跳绳），课标正文说共 10 个模块分三个学年，其余没印在这一章里。',
              '',
              '## 字段',
              '',
              '在 `tools/out/gaozhong*/` 的字段基础上加了三个：',
              '',
              '- `level`：水平（整数）。',
              '- `literacy`：课标自带的素养标签，没有就是 `[]`。',
              '- `pages`：跨页条目的来源页列表（`page` 仍是首页，与既有产物一致）。',
              '']
    (OUT / 'README.md').write_text('\n'.join(lines), encoding='utf-8')


# ─────────────────────────── 主程序 ───────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', help='只抽一科')
    ap.add_argument('--report', action='store_true', help='只统计，不写盘')
    args = ap.parse_args()

    targets = [args.only] if args.only else list(SPECS)
    for s in targets:
        if s not in SPECS:
            raise SystemExit(f'未知学科 {s}，可选：{"/".join(SPECS)}')
    if not args.report:
        OUT.mkdir(parents=True, exist_ok=True)

    all_warn, failed, total, stats = [], [], 0, []
    for subject in targets:
        STUCK_HEAD.clear()
        ch, b, rows = extract(subject)
        bad = verify(ch, rows)
        warn = sanity(subject, rows) + [f'{subject} {u}' for u in b.unclaimed]
        all_warn += warn
        total += len(rows)
        print(f'── {subject}  {len(rows)} 条  页 {ch.span[0]}-{ch.span[1]}')
        print(f'   水平: {dict(sorted(Counter(r["level"] for r in rows).items(), key=lambda kv: (kv[0] is None, kv[0])))}'
              f'  课程: {dict(Counter(r["course"] for r in rows))}')
        lit = Counter(x for r in rows for x in r['literacy'])
        if lit:
            print(f'   素养标注: {dict(lit)}  带标注 {sum(1 for r in rows if r["literacy"])}/{len(rows)} 条')
        if b.prose:
            print(f'   跳过的散文/说明行: {sum(b.prose.values())} 行')
        if STUCK_HEAD:
            print(f'   页眉与正文粘连行(已剜页眉): {dict(STUCK_HEAD)}')
        for w in warn:
            print(f'   ! {w}')
        if bad:
            failed.append(subject)
            print(f'   ✗ 逐字校验不过 {len(bad)} 处：')
            for x in bad[:10]:
                print(f'      {x}')
            continue
        print('   ✓ 逐字校验通过')
        stats.append({'subject': subject, 'n': len(rows), 'span': ch.span,
                      'kind': SPECS[subject][1] + ('+' if SPECS[subject][2] else ''),
                      'levels': {r['level'] for r in rows},
                      'lit': sum(1 for r in rows if r['literacy']),
                      'courses': sorted({r['course'] for r in rows}, key=str)})
        if not args.report:
            path = OUT / f'{subject}.jsonl'
            with path.open('w', encoding='utf-8') as f:
                for r in rows:
                    f.write(json.dumps({k: v for k, v in r.items() if k != '_spans'},
                                       ensure_ascii=False) + '\n')
            print(f'   → {path.relative_to(ROOT)}')

    print(f'\n合计 {total} 条')
    if not args.report:
        (OUT / 'warnings.txt').write_text('\n'.join(all_warn) + '\n', encoding='utf-8')
        if len(stats) == len(SPECS):
            write_readme(stats)
    if failed:
        print(f'✗ 逐字校验未通过，未写盘：{"、".join(failed)}')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
