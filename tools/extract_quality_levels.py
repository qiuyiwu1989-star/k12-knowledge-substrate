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

## 「水平3」在不同学科不是一回事 —— 所以每科都带 scale

20 科用的刻度不止一套，硬映射成 1–5 会让同一个数字在不同学科指不同的东西，
**那比缺着更糟**。所以每个学科落一个 `scale`：

  · `水平`  多数学科：水平 1…N，学科自有分级（语文 5 级、化学 4 级、数学 3 级…）
  · `级`    日语（四/五/六级）、法语（三/四/五级）—— 外语「级」体系里高中占的那一段，
            数字**不从 1 起**，1–3 级属义务教育阶段，课标里没有或不作规定
  · `C/G`   德语：初中 C1–C5、高中 G1–G5 **两条并行的轨**。
            如实记成两条轨，不压平成 1–5（G2 = 毕业合格，G4 = 高考命题依据）
  · 西班牙语虽然叫「水平 1–5」，但它是**中学贯通**的（水平2 = 初中毕业合格，
    水平3 = 高中毕业合格），和只覆盖高中的那些「水平 1–5」不是一把尺，也标出来

## 一个学科可能有好几张表 —— 所以有 groups / competencies

艺术、音乐、美术、体育与健康、德语，正文里都是**多张小表**：
按模块（音乐 12 个模块、美术 12 个、体育 12 个）、按素养 × 模块（艺术）、
按学段轨（德语 C/G）各来一张，每张表里的水平号都从头编。
把它们压平会造出「音乐水平2 有 6 条 2-1」这种**互相矛盾又无法归属**的东西。
所以：

  · shape=flat     一张表           → `levels`
  · shape=grouped  多张表（模块/轨） → `groups[].levels`
  · shape=nested   艺术：素养 × 模块 → `competencies[].moduleGroups[].levels`

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

# 刻度说明。数字是从正文「（三）学业质量水平与考试评价的关系」里逐字读出来的，
# 不是推的 —— 谁是毕业合格线、谁是高考依据，课标自己写着。
SCALE_NOTES = {
    '日语': {'naming': '级', 'levelNames': {4: '四级', 5: '五级', 6: '六级'},
             'covers': '高中段只占「级」体系的四—六级，一—三级不在本课标内',
             'benchmarks': {'四级': '高中毕业合格要求', '五级': '高考命题依据',
                            '六级': '高校招收与日语相关专业学生的参考依据'}},
    '法语': {'naming': '级', 'levelNames': {3: '三级', 4: '四级', 5: '五级'},
             'covers': '高中段为三—五级；预备级—二级属义务教育阶段，'
                       '本课标明确「不作具体规定」，由学校自行制定',
             'benchmarks': {'三级': '高中毕业合格要求（学业水平考试）',
                            '四级': '高考命题依据',
                            '五级': '为高等教育作准备的拓展与提升性学习'}},
    '德语': {'naming': 'C/G 双轨', 'covers': '初中 C1—C5 与高中 G1—G5 两条并行的轨，'
                                             '两轨的水平号各自从 1 起，不可合并',
             'benchmarks': {'G2': '高中毕业合格要求（学业水平合格考试依据）',
                            'G4': '高考命题依据'}},
    '西班牙语': {'naming': '水平', 'covers': '中学贯通的五个水平（初中 + 高中共用一把尺），'
                                             '不是只覆盖高中',
                 'benchmarks': {'水平2': '初中毕业合格要求', '水平3': '高中毕业合格要求',
                                '水平4': '高考命题依据', '水平5': '学有余力/赴西语国家学习参考'}},
    '艺术': {'naming': '水平', 'covers': '每个「素养 × 模块组」各有一张 1—3 级的小表，'
                                         '水平号只在本模块组内有意义',
             'benchmarks': {'水平1': '学习相应模块的合格要求（达到即可获得模块学分）',
                            '水平3': '高校艺术人才招生命题依据'}},
    '音乐': {'naming': '水平', 'covers': '每个模块（必修 6 + 选择性必修 6）各有一张 1—3 级小表'},
    '美术': {'naming': '水平', 'covers': '每个模块各一张小表；选修课程的模块只有 2—3 级'},
    '体育与健康': {'naming': '水平',
                   'covers': '必修必学 2 个模块 + 必修选学 10 个运动技能模块，各一张 1—5 级小表',
                   'benchmarks': {'水平2': '合格要求'}},
}


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


# 版式，实测出来的：
#   A「N-M」编号：1-1 / 1-2 / 2-1 …  水平号**编在条目号里**，最结实。化学语文英语等。
#   B 裸水平号 +（M）：单独一行「1」，后面跟（1）（2）（3）（4）。物理等。
#   C「水平一/二/三」中文数字 + 整段，无条目编号。数学。
#   D 裸水平号 + 阿拉伯「N.」条目：单独一行「1」，后面跟 1. 2. 3. 4.。西班牙语。
#   E 艺术专用：素养 × 模块组，一科七八张小表，见 split_art。
# 先试 A，A 一条都切不出来才往下退 —— A 不依赖版面上的换行位置，跨页也不会断。
ITEM_A = re.compile(r'(?:^|\n)\s*([1-9])[-－—]([0-9]{1,2})\s*([^\n].{6,})')
# A 的松版：条目号后面那一行**很短**（法语「3-1  听力」，正文在下面的（1）（2）里）。
# 只在严版一条都不中时才用，免得放进假阳性。
ITEM_A_LOOSE = re.compile(r'(?:^|\n)\s*([1-9])[-－—]([0-9]{1,2})\s+([^\n\s].*)')
LEVEL_B = re.compile(r'(?:^|\n)\s*([1-9])\s*(?=\n\s*（1）)')
CN = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6}
LEVEL_C = re.compile(r'水平([一二三四五六])(?![）\d])')
LEVEL_D = re.compile(r'(?:^|\n)\s*([1-9])\s*(?=\n\s*1\s*[.．]\s)')
ITEM_D = re.compile(r'(?:^|\n)\s*([1-9])\s*[.．]\s*([^\n].*)')
ART_SIG = re.compile(r'（\d）\s*(?:必修模块|选择性必修模块)[：:]')

# 版面家具：页眉、页码、表头、续表。这些会插在句子中间，
# **句中污染比截断更糟** —— 截断看得出来，这个看不出来。
FURNITURE = [
    re.compile(r'^普通高中[^\n]{0,12}课程标准'),
    re.compile(r'^│.*│$'),
    re.compile(r'^\d{1,3}$'),
    re.compile(r'^水平\s*质量描述$'),
    re.compile(r'^质量描述$'),
    re.compile(r'^续表$'),
    re.compile(r'^表\s*\d+\s*[^\n]{0,40}$'),
    re.compile(r'^$'),
]
# 一张新表开头的「章」标题：【必修课程】【选择性必修课程】/ 1. 必修必学内容学业质量水平
SECTION = re.compile(r'(?:^|\n)[ \t]*(?:【([^】\n]{2,20})】|\d\s*[.．]\s*([^\n]{2,24}学业质量水平))[ \t]*(?=\n)')


def _is_furniture(line, keep_level_marks=False):
    """keep_level_marks：艺术的水平号是**单独一行的 1/2/3**，
    跟页码（两三位数）长得一样。清家具时必须放过 1–3，否则整张表的水平号被扫掉。"""
    s = line.strip()
    if keep_level_marks and re.fullmatch(r'[1-3]', s):
        return False
    return any(p.match(s) for p in FURNITURE)


def _clean(t):
    """拼回跨行的一条。"""
    t = re.sub(r'普通高中[^\n]{0,12}课程标准[^\n]*', '', t)
    t = re.sub(r'水平\s*质量描述', '', t)
    t = re.sub(r'│[^│\n]*│', '', t)
    t = re.sub(r'续表', '', t)
    t = re.sub(r'\s+', '', t)
    return t.strip()


def _header_before(joined, pos, max_lines=8):
    """从 pos 往回走，收「表头区」：版面家具 + 短标题行，遇到正文句子就停。

    返回 (表头区起点, 标题文字)。表头区起点用来**切掉上一条被粘上的表头**
    —— 不切的话「…（素养4）」后面就跟着「1（G1）高中阶段」，看不出来的那种脏。
    """
    head = joined[:pos]
    lines = head.split('\n')
    take = 0
    titles = []
    for line in reversed(lines[-max_lines:] if len(lines) > max_lines else lines):
        s = line.strip()
        if _is_furniture(s):
            take += 1
            continue
        # 正文句子的特征：带句号/分号，或者太长，或者本身就是一个条目号
        if ('。' in s or '；' in s or len(s) > 30
                or re.match(r'^\d[-－—]\d', s) or re.match(r'^（\d）', s)):
            break
        take += 1
        titles.insert(0, s)
    if take == 0:
        return pos, ''
    start = pos - sum(len(x) + 1 for x in lines[len(lines) - take:])
    return max(start, 0), ' '.join(t for t in titles if t).strip()


def _sections(joined):
    return [(m.start(), (m.group(1) or m.group(2) or '').strip())
            for m in SECTION.finditer(joined)]


def _page_locator(pages):
    page_of, pos = {}, 0
    for pg, t in pages:
        page_of[pos] = pg
        pos += len(t) + 1
    return lambda p: page_of.get(max((k for k in page_of if k <= p), default=0))


def split_A(joined, page_at):
    """N-M 编号版式。**水平号回退 = 换了一张表**（换模块 / 换学段轨），
    这是唯一可靠的分表信号：模块标题长什么样各科不一样，水平号回退不会骗人。"""
    hits = list(ITEM_A.finditer(joined))
    loose = False
    if not hits:
        hits = list(ITEM_A_LOOSE.finditer(joined))
        loose = True
    if not hits:
        return None
    secs = _sections(joined)

    # 1) 按水平号回退切表
    bounds, prev = [], None
    for i, m in enumerate(hits):
        lv, idx = int(m.group(1)), int(m.group(2))
        if prev and (lv < prev[0] or (lv == prev[0] and idx <= prev[1])):
            bounds.append(i)
        prev = (lv, idx)
    starts = [0] + bounds
    ends = bounds + [len(hits)]

    groups = []
    for gi, (a, b) in enumerate(zip(starts, ends)):
        chunk = hits[a:b]
        head_start, title = _header_before(joined, chunk[0].start())
        sec = ''
        for p, name in secs:
            if p < chunk[0].start():
                sec = name
        levels = {}
        for j, m in enumerate(chunk):
            lv = int(m.group(1))
            if j + 1 < len(chunk):
                end = chunk[j + 1].start()
            elif b < len(hits):
                end, _ = _header_before(joined, hits[b].start())
            else:
                end = len(joined)
            body = _clean(joined[m.start(3):end])
            if len(body) < 12:
                continue
            d = levels.setdefault(lv, {'level': lv, 'srcPage': page_at(m.start()),
                                       'items': []})
            d['items'].append(f"{m.group(1)}-{m.group(2)} {body}")
        if not levels:
            continue
        groups.append({'title': title or f'表 {gi + 1}', 'section': sec or None,
                       'levels': [levels[k] for k in sorted(levels)]})
    return {'format': 'A-loose' if loose else 'A', 'groups': groups}


def split_C(joined, page_at):
    marks = [(m.start(), CN[m.group(1)]) for m in LEVEL_C.finditer(joined)]
    levels = {}
    for i, (p0, lv) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(joined)
        body = _clean(joined[p0:end])
        body = re.sub(r'^水平[一二三四五六]', '', body)
        if len(body) < 40:
            continue
        # 整段不切条 —— 这一版式本来就没有条目编号，硬切成条要靠语义判断，
        # 那正是这个项目栽过的地方。
        levels.setdefault(lv, {'level': lv, 'srcPage': page_at(p0), 'items': [body]})
    if not levels:
        return None
    return {'format': 'C', 'groups': [{'title': '', 'section': None,
                                       'levels': [levels[k] for k in sorted(levels)]}]}


def split_B(joined, page_at):
    marks = [(m.start(), int(m.group(1))) for m in LEVEL_B.finditer(joined)]
    levels = {}
    for i, (p0, lv) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(joined)
        items = [_clean(x) for x in re.findall(r'（\d）([^（]{10,600})', joined[p0:end])]
        items = [x for x in items if len(x) >= 12]
        if items:
            levels.setdefault(lv, {'level': lv, 'srcPage': page_at(p0), 'items': items})
    if not levels:
        return None
    return {'format': 'B', 'groups': [{'title': '', 'section': None,
                                       'levels': [levels[k] for k in sorted(levels)]}]}


def split_D(joined, page_at):
    """裸水平号 + 阿拉伯「N.」条目（西班牙语）。"""
    marks = [(m.start(), m.end(), int(m.group(1))) for m in LEVEL_D.finditer(joined)]
    levels = {}
    for i, (p0, p1, lv) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(joined)
        block = joined[p1:end]
        hits = list(ITEM_D.finditer(block))
        items = []
        for j, m in enumerate(hits):
            stop = hits[j + 1].start() if j + 1 < len(hits) else len(block)
            body = _clean(block[m.start(2):stop])
            if len(body) >= 12:
                items.append(f"{m.group(1)}. {body}")
        if items:
            levels.setdefault(lv, {'level': lv, 'srcPage': page_at(p0), 'items': items})
    if not levels:
        return None
    return {'format': 'D', 'groups': [{'title': '', 'section': None,
                                       'levels': [levels[k] for k in sorted(levels)]}]}


# ── 艺术：素养 × 模块组，一科七八张小表 ────────────────────────────────
ART_COMP = re.compile(r'(?:^|\n)[ \t]*([1-9])\s*[.．]\s*([一-龥]{2,8})[ \t]*\n'
                      r'(?=[ \t]*（1）\s*必修模块)')
ART_GROUP = re.compile(r'(?:^|\n)[ \t]*（([12])）\s*(必修模块|选择性必修模块)[：:]')
ART_LEVEL = re.compile(r'(?:^|\n)[ \t]*([1-3])[ \t]*(?=\n|[ \t])')


def split_art(joined, page_at):
    """艺术：4 个素养 ×（必修模块组 / 选择性必修模块组）× 3 级。

    **不压平。**「艺术感知·选择性必修·水平1」下面 5 条，每条属于一个具体模块
    （美术创意实践 / 音乐情境表演 / …）；跟「创意表达·必修·水平1」不是一回事，
    合并会造出无法归属的条目。
    """
    end_all = joined.find('（三）学业质量水平与考试评价')
    if end_all < 0:
        end_all = len(joined)
    comps = [(m.start(), int(m.group(1)), m.group(2)) for m in ART_COMP.finditer(joined)
             if m.start() < end_all]
    if not comps:
        return None
    out = []
    for ci, (p0, idx, name) in enumerate(comps):
        cend = comps[ci + 1][0] if ci + 1 < len(comps) else end_all
        block = joined[p0:cend]
        gm = list(ART_GROUP.finditer(block))
        module_groups = []
        for gi, m in enumerate(gm):
            gend = gm[gi + 1].start() if gi + 1 < len(gm) else len(block)
            gblock = block[m.end():gend]
            # 模块清单：冒号后一直到表头「水平 质量描述」为止
            hdr_end = gblock.find('质量描述')
            head = gblock[:hdr_end] if hdr_end > 0 else gblock[:120]
            head = re.sub(r'水平\s*$', '', re.sub(r'\s+', '', head))
            modules = [x for x in re.split(r'[、，,]', head) if len(x) >= 2]
            body = gblock[hdr_end + len('质量描述'):] if hdr_end > 0 else gblock
            # 去掉版面家具行，再切水平
            body = '\n'.join(l for l in body.split('\n')
                             if not _is_furniture(l, keep_level_marks=True))
            lm = list(ART_LEVEL.finditer(body))
            levels = {}
            for li, x in enumerate(lm):
                lend = lm[li + 1].start() if li + 1 < len(lm) else len(body)
                seg = body[x.end():lend]
                lv = int(x.group(1))
                d = levels.setdefault(lv, {'level': lv,
                                           'srcPage': page_at(p0 + m.end() + hdr_end),
                                           'items': []})
                if m.group(2) == '选择性必修模块':
                    # 每个模块一条：「美术创意实践：能了解…」
                    pat = re.compile(r'(' + '|'.join(re.escape(x) for x in modules) +
                                     r')\s*[：:]')
                    ms = list(pat.finditer(seg))
                    for k, mm in enumerate(ms):
                        stop = ms[k + 1].start() if k + 1 < len(ms) else len(seg)
                        txt = _clean(seg[mm.end():stop])
                        if len(txt) >= 6:
                            d['items'].append({'module': mm.group(1), 'text': txt})
                else:
                    txt = _clean(seg)
                    if len(txt) >= 6:
                        d['items'].append({'module': None, 'text': txt})
            levels = {k: v for k, v in levels.items() if v['items']}
            if levels:
                module_groups.append({'group': m.group(2), 'modules': modules,
                                      'levels': [levels[k] for k in sorted(levels)]})
        if module_groups:
            out.append({'competency': name, 'moduleGroups': module_groups})
    return out


def split_levels(pages):
    joined = '\n'.join(t for _, t in pages)
    page_at = _page_locator(pages)
    if ART_SIG.search(joined):
        return {'format': 'E-art', 'competencies': split_art(joined, page_at)}
    for fn in (split_A, split_C, split_D, split_B):
        r = fn(joined, page_at)
        if r:
            return r
    return None


# ── 自检 ──────────────────────────────────────────────────────────────
def check(levels, where):
    """水平必须连续。**起点不必是 1** —— 日语四—六级、法语三—五级、
    美术选修 2—3 级都是课标自己的编号，从 1 起是假设不是事实。
    但中间断号 / 重号一定是版式没吃透，当场拦下（这道自检拦下过日语的 [4,5,6]，
    拦得对不对是另一回事，规则改成「连续」而不是删掉）。"""
    nums = [x['level'] for x in levels]
    if not nums:
        return f'{where} 一条也没切出来'
    if nums != list(range(nums[0], nums[0] + len(nums))):
        return f'{where} 水平不连续 {nums}'
    for lv in levels:
        if not lv['items']:
            return f"{where} 水平{lv['level']} 空"
    return None


def count_items(rec):
    if rec.get('shape') == 'nested':
        return sum(len(l['items']) for c in rec['competencies']
                   for g in c['moduleGroups'] for l in g['levels'])
    if rec.get('shape') == 'grouped':
        return sum(len(l['items']) for g in rec['groups'] for l in g['levels'])
    return sum(len(l['items']) for l in rec['levels'])


def count_levels(rec):
    if rec.get('shape') == 'nested':
        return sum(len(g['levels']) for c in rec['competencies'] for g in c['moduleGroups'])
    if rec.get('shape') == 'grouped':
        return sum(len(g['levels']) for g in rec['groups'])
    return len(rec['levels'])


def scale_of(name, rec):
    """刻度。id 是给人看一眼就知道「这科的水平3 是哪套刻度里的 3」。"""
    extra = SCALE_NOTES.get(name, {})
    naming = extra.get('naming', '水平')
    if rec.get('shape') == 'nested':
        lo = hi = None
        for c in rec['competencies']:
            for g in c['moduleGroups']:
                ns = [l['level'] for l in g['levels']]
                lo = min(ns) if lo is None else min(lo, min(ns))
                hi = max(ns) if hi is None else max(hi, max(ns))
    elif rec.get('shape') == 'grouped':
        ns = [l['level'] for g in rec['groups'] for l in g['levels']]
        lo, hi = min(ns), max(ns)
    else:
        ns = [l['level'] for l in rec['levels']]
        lo, hi = min(ns), max(ns)
    if name == '德语':
        sid = 'C1–C5 / G1–G5'
    elif naming == '级':
        sid = f'{naming}{lo}–{hi}'
    else:
        sid = f'水平{lo}–{hi}'
    out = {'id': sid, 'naming': naming, 'min': lo, 'max': hi}
    out.update({k: v for k, v in extra.items() if k != 'naming'})
    if name != '德语' and naming == '水平' and 'covers' not in out:
        out['covers'] = '高中段学科自有分级'
    return out


NOT_EXTRACTED_WHY = ('**没吃透的不落盘。** 宁可缺着，也不放半懂的进去 —— '
                     '这个项目在「指标误判比没有指标更糟」上栽过不止一次。')


def main():
    out = {'schemaVersion': '0.2.0',
           'about': '《普通高中课程标准（2017年版2020年修订）》各科「学业质量水平」量表。'
                    '**这不是逐条锚点的掌握判据** —— 它是学科级的水平量表，'
                    '每级按该学科核心素养分条描述。「做对几次算会」课标里没有。',
           'useFor': ['给「达到哪一级」提供官方口径',
                      '量表里的两个梯度轴（情境复杂度 / 独立程度）是课标原话，'
                      '将来做 mastery 时它们是有出处的那部分'],
           'notFor': ['不给锚点打水平标签 —— 那是判断，而本项目对'
                      '「没有可判定答案的东西不机器打标」有明确结论',
                      '**不要跨学科比较水平号。** 每科的 scale 不是同一把尺：'
                      '日语「四级」、法语「三级」、德语「G2」、化学「水平2」互不等价'],
           'ladders': {'context': CONTEXT_LADDER, 'autonomy': AUTONOMY_LADDER},
           'shapes': {
               'flat': '一张表：`levels[]`',
               'grouped': '多张表（按模块 / 按学段轨），每张表的水平号各自从头编：`groups[].levels[]`',
               'nested': '艺术专用：素养 × 模块组 × 水平：`competencies[].moduleGroups[].levels[]`'},
           'formats': [
               'A「N-M」编号（化学语文英语等，最结实）',
               'A-loose 同上，但条目号那行很短、正文在下面的（1）（2）里（法语）',
               'B 裸水平号 +（M）（物理等）',
               'C「水平一/二/三」中文数字 + 整段，无条目编号（数学）',
               'D 裸水平号 + 阿拉伯「N.」条目（西班牙语）',
               'E 艺术：素养 × 模块组，一科八张小表'],
           'disciplines': {},
           'notExtracted': {}}

    for pdf in sorted(SRC.glob('*.pdf')):
        name = re.sub(r'^\d+-', '', pdf.stem)
        if name == '课程方案':
            continue
        pages = grab(pdf)
        if not pages:
            out['notExtracted'][name] = '没定位到学业质量正文'
            print(f'  {name:8} ✗ 没定位到学业质量正文')
            continue
        parsed = split_levels(pages)
        if not parsed:
            out['notExtracted'][name] = '定位到了正文但一条水平也切不出来，版式没吃透'
            print(f'  {name:8} ✗ 定位到了但切不出水平')
            continue

        if parsed['format'] == 'E-art':
            comps = parsed.get('competencies') or []
            errs = [e for c in comps for g in c['moduleGroups']
                    for e in [check(g['levels'], f"{c['competency']}·{g['group']}")] if e]
            if not comps or errs:
                out['notExtracted'][name] = '；'.join(errs) or '素养 × 模块结构没切出来'
                print(f'  {name:8} ⚠ {out["notExtracted"][name]} —— 先不落盘')
                continue
            rec = {'shape': 'nested', 'competencies': comps}
        else:
            groups = parsed['groups']
            errs = [e for g in groups
                    for e in [check(g['levels'], g['title'] or '正文')] if e]
            if errs:
                out['notExtracted'][name] = '；'.join(errs) + ' —— 版式没吃透'
                print(f'  {name:8} ⚠ {out["notExtracted"][name]} —— 先不落盘')
                continue
            if len(groups) == 1:
                rec = {'shape': 'flat', 'levels': groups[0]['levels']}
            else:
                rec = {'shape': 'grouped',
                       'groups': [{'title': g['title'], 'section': g['section'],
                                   'levels': g['levels']} for g in groups]}
        rec['format'] = parsed['format']
        rec['scale'] = scale_of(name, rec)
        rec['srcPages'] = [pages[0][0], pages[-1][0]]
        out['disciplines'][name] = rec
        n, ln = count_items(rec), count_levels(rec)
        if rec['shape'] == 'grouped':
            tag = f" · {len(rec['groups'])} 张表"
        elif rec['shape'] == 'nested':
            tag = (f" · {len(rec['competencies'])} 素养 ×"
                   f"{sum(len(c['moduleGroups']) for c in rec['competencies'])} 模块组")
        else:
            tag = ''
        print(f"  {name:8} ✓ {rec['scale']['id']:14} {ln} 级 · {n} 条{tag}"
              f" · p{pages[0][0]}–{pages[-1][0]}")

    if out['notExtracted']:
        out['notExtracted']['_why'] = NOT_EXTRACTED_WHY
    else:
        out['notExtracted'] = {'_none': '20 科全部抽出。' + NOT_EXTRACTED_WHY}
    d = out['disciplines']
    out['coverage'] = {'extracted': len(d), 'total': 20,
                       'levels': sum(count_levels(v) for v in d.values()),
                       'items': sum(count_items(v) for v in d.values())}
    (ROOT / 'mappings/quality-levels.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    c = out['coverage']
    print(f"\n→ mappings/quality-levels.json　{c['extracted']}/20 科 · "
          f"{c['levels']} 级 · {c['items']} 条描述")


if __name__ == '__main__':
    main()
