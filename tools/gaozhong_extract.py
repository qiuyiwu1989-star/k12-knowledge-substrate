#!/usr/bin/env python3
"""
gaozhong_extract.py — 从高中课标 PDF 里结构化抽取内容要求。**纯文本解析，零模型调用。**

## 和义务教育那套完全不同的一条路

义务教育 15 份是 150 DPI 扫描图、零文字层，只能逐页喂多模态模型，代价是
识读幻觉、串页、模型污染，为此建了接地校验和污染闸。

高中 21 份**全部带文字层**（2,276 页实测）。对这批用 VLM 是白花钱，而且
**凭空引入本来不存在的幻觉风险**。所以这个工具一次模型都不调。

## 这批比义务教育多拿到三样东西

1. **官方层级编号**（`1.1.1`）—— 义务教育那批只有 27 条保留了编号，因为当时的
   抽取提示词没要求过。这里编号就在文本里，白拿。它是可机械校验的锚：
   编号连续性一断，就说明漏页或串页了。
2. **课程类型**（必修 / 选择性必修 / 选修）—— 义务教育没有这个维度。
   **对个人档案是本质区别**：必修是所有学生都该有的，选修不是。
   不记这一维，档案里「他没掌握 X」就分不清是没学过还是学了没会。
3. **例题**（`例 1 …`）—— 课标自带的具体情境，正好是判定证据的天然来源，
   比模型编的证据可靠。

## 结构

    2.1 机械能及其守恒定律          ← 主题
    【内容要求】
    2.1.1 理解功和功率。了解生产生活中常见机械的功率大小及其意义。
    例 1 分析物体移动的方向与所受力的…
    2.1.2 ...
      必修 2 的学业要求
    能对常见的机械运动进行分类。会用运动与相互作用的知识分析…

## 不做的事

**不在这一步拆句、不判可判定性、不写锚点。** 一个编号项常常含两三条要求
（「理解功和功率。了解…的意义。」），拆分是下一步的事。这一步只负责
**忠实地把结构和原文取出来**，取错了后面全错。

    python3 tools/gaozhong_extract.py                    # 全部 20 科
    python3 tools/gaozhong_extract.py --only 物理        # 单科
    python3 tools/gaozhong_extract.py --report           # 只看统计，不写盘
"""
import argparse, collections, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'sources/standards-gaozhong'
OUT = ROOT / 'tools/out/gaozhong'

# 课程类型。顺序要紧：先匹配长的，否则「选择性必修」会被「必修」截断。
COURSE_PAT = re.compile(r'(选择性必修|选修|必修)\s*([一二三四五六七八九\d]*)')
# 模块级学业要求的标题行，如「  必修 1 的学业要求  」「 选择性必修 2 的学业要求 」
XUEYE_HEAD = re.compile(r'^\s*(选择性必修|选修|必修)\s*([\d一二三四五六七八九]*)\s*的学业要求\s*$')
# 模块标题：「1. 必修 1」「2. 选择性必修 2」「3. 选修 3」。
# **它在内容之前**，是课程类型的唯一可靠来源 —— 靠段末的「必修 1 的学业要求」
# 拿课程类型就晚了，那时内容早就抽完了（实测 137 条全部标成「未标」）。
MODULE_HEAD = re.compile(r'^\d+\.\s*(选择性必修|选修|必修)\s*([\d一二三四五六七八九]*)\s*$')
# 主题标题：「1.1 机械运动与物理模型」/「2.1 磁场」（名字可能只有两个字）
TOPIC_HEAD = re.compile(r'^(\d+\.\d+)\s{1,3}([^\d\s][^\n]{1,30})$')
# 内容要求条目：「1.1.1 了解…」
ITEM = re.compile(r'^(\d+\.\d+\.\d+)\s*(.+)$')
# 例题：「例 1 …」「例1 …」
EXAMPLE = re.compile(r'^例\s*(\d+)\s*(.*)$')
# **不带【】的裸栏目名**。课标里「活动建议」「教学提示」有时不加书名号，
# 不识别它，后面整段活动建议会被吞进上一条例题里
#（实测：「例：…重大贡献。活动建议（1）查阅资料…」）。
BARE_SECTION = re.compile(r'^(活动建议|教学提示|学业要求|教学与评价案例|学业质量|'
                          r'实验及实践活动|学生必做实验|教学与评价建议)\s*$')
# ── 第二套版式（化学 / 生物学 / 思想政治 等）──
# 课程类型写成「（一）必修课程」「（二）选择性必修课程」
COURSE_CN = re.compile(r'^（[一二三四五六七八九]）\s*(必修|选择性必修|选修)课程\s*$')
# 主题写成「主题 1 ：化学科学与实验探究」「专题 2：xxx」
TOPIC_CN = re.compile(r'^(主题|专题|模块)\s*([\d一二三四五六七八九]+)\s*[：:]\s*(.{2,30})$')
# 二级编号小标题「1.1 化学科学的主要特征」—— 它下面才是无编号的要求段
SUBHEAD = re.compile(r'^(\d+\.\d+)\s{1,3}(.{2,30})$')

# ── 第三套版式（语文）：学习任务群 ──
# 「学习任务群1 整本书阅读与研讨」当主题，「1. 学习目标与内容」开内容段，
# 「（1）…」是条目。语文不按主题organize，按任务群。
TASKGROUP = re.compile(r'^学习任务群\s*(\d+)\s*(.{2,30})$')
XUEXI_SEC = re.compile(r'^\d+\.\s*(学习目标与内容|教学提示)\s*$')
PAREN_ITEM = re.compile(r'^（(\d+)）\s*(.+)$')

# ── 第四套版式（外语类：日/俄/德/法/西）：表格 ──
# 「表 6 语音知识内容要求」开表，「课程类别 内容要求」是表头，
# 裸行「必修」「选择性必修」「选修 — 提高类」切换课程类别，「1. …」是条目。
TABLE_HEAD = re.compile(r'^表\s*\d+\s*(.{2,24}?)(内容要求|要求)\s*$')
TABLE_COLS = re.compile(r'^课程类别\s+(内容要求|要求)\s*$')
# 裸课程类别行。可能后面直接跟着第一个条目（「选修 — 提高类 1. 能分辨…」）
BARE_COURSE = re.compile(r'^(选择性必修|选修|必修)\s*(?:[—–-]\s*(\S{2,6})类?)?\s*(?:(\d+)\.\s*(.+))?$')
NUM_ITEM = re.compile(r'^(\d+)\.\s{0,2}(.{6,})$')
# 页眉页脚噪声：页码、书名、章节名
# 页眉页脚。**不能只匹配行首** —— 数学等科的文字层把页码和页眉粘在一行
# （「0 2普通高中数学课程标准 （2 0 1 7年版…」），而且 CID 字体抽取会在数字间插空格
# （2 0 1 7）。行首锚定的正则漏掉它，结果页眉被并进句子中间：
#   「能用描点法或借助计0 2普通高中数学课程标准（2 0 1 7年版…算工具画出具」
# 这比截断更糟 —— 截断看得出来，句中污染看不出来。
NOISE = re.compile(r'^\s*(\d{1,3}|[│|]\s*.{0,20}\s*[│|])\s*$')
HEADER_ANY = re.compile(r'普\s*通\s*高\s*中[^）]{0,24}课\s*程\s*标\s*准\s*（?\s*2\s*0?\s*1?\s*7?[^）]{0,20}）?')


# ★ 20 科的版式**不是一套**。按物理一科写死，另外 18 科全返回 0（实测）。
#   两大差异：
#     · 数学等科的文字层是全角数字与拉丁字母（「Ａ类课程」「２学分」），
#       外加私用区字符 \ue000-\uf8ff。ASCII 数字正则一个都匹配不上。
#     · 化学等科用「（一）必修课程」标课程类型、「主题 1 ：xxx」标主题，
#       且**内容要求正文根本没有编号** —— 一段就是一条要求。
FULLWIDTH = {ord('０') + i: ord('0') + i for i in range(10)}
FULLWIDTH.update({ord('Ａ') + i: ord('A') + i for i in range(26)})
FULLWIDTH.update({ord('ａ') + i: ord('a') + i for i in range(26)})
FULLWIDTH.update({ord('．'): ord('.'), ord('　'): ord(' '), 0x2003: ord(' ')})
PUA = re.compile(r'[\ue000-\uf8ff]')


def normalize_line(s):
    """全角→半角、去私用区。不做这一步，数学/语文等科整份抽不出东西。"""
    return PUA.sub('', s.translate(FULLWIDTH))


def clean_lines(txt):
    """按行切并去掉页眉页脚。文字层 PDF 的噪声是**确定性**的，用规则清干净就行。"""
    out = []
    for l in txt.split('\n'):
        s = normalize_line(l)
        s = HEADER_ANY.sub('', s).strip()      # 先剜掉页眉，再判是否整行是噪声
        if not s or NOISE.match(s):
            continue
        out.append(s)
    return out


# 标题类行**永不吸收续行**。栏目名和模块名本身就是完整的一行。
# 不区分这一点，「必修 1 的学业要求」会和后面的正文粘成一行，
# 正则就不再匹配 —— 实测导致 学业要求 抽出 0 条。
STANDALONE = (MODULE_HEAD, XUEYE_HEAD, TOPIC_HEAD, BARE_SECTION,
              COURSE_CN, TOPIC_CN, TASKGROUP, XUEXI_SEC, TABLE_HEAD, TABLE_COLS)
# 这两类是「带正文的头」，后续行是它们的续行
ABSORBING = (ITEM, EXAMPLE, PAREN_ITEM, NUM_ITEM)


def unwrap(stream):
    """把被 PDF 换行切断的句子接回去。**跨页做，不能按页做。**

    文字层 PDF 每行 20–30 字硬换行，一条要求常被切成三四行；而**页尾那一条
    十有八九跨到下一页**。按页 unwrap 的后果实测很明显：
      「通过实验，了解自感现象和涡流现象。能举例说明自感现」← 就这么断在这里
    所以接收的是整份文档的 (行, 页码) 流，页码取该条**第一行**所在页
    —— 那才是它在书上的位置。

    接的判据：下一行不是新的结构标记，就说明它是续行。这比按标点接可靠 ——
    课标里一条要求内部就有句号（「理解功和功率。了解…意义。」）。
    """
    merged, buf, buf_page = [], '', None
    def flush():
        nonlocal buf, buf_page
        if buf:
            merged.append((buf, buf_page)); buf, buf_page = '', None
    for s, pno in stream:
        if any(p.match(s) for p in STANDALONE) or s.startswith('【'):
            flush(); merged.append((s, pno))
            continue
        if any(p.match(s) for p in ABSORBING):
            flush(); buf, buf_page = s, pno
            continue
        if buf:
            buf += s
        else:
            merged.append((s, pno))
    flush()
    return merged


def parse(subject, pdf):
    from pypdf import PdfReader
    r = PdfReader(str(pdf))
    rows, warn = [], []
    course, course_no, topic, topic_name, section = None, '', None, None, None
    xy_buf, xy_key, xy_page = [], None, None
    sub_code, sub_name = None, None
    pr_buf, pr_page = [], None

    def _emit_item(text, pno, code=None):
        rows.append({'subject': subject, 'course': course, 'courseNo': course_no,
                     'topic': topic, 'topicName': topic_name,
                     'code': code or sub_code, 'subTopic': sub_name,
                     'text': text, 'page': pno, 'section': '内容要求',
                     'examples': []})

    def flush_prose():
        """落一段无编号的内容要求。

        判据比「长度 > 14」严得多 —— 那条宽规则把「内容包括：数列、一元函数导数
        及其应用。」这类**内容清单**也当成了能力要求（实测数学 408 条里一堆）。
        真要求必须有对学生的动作要求，且不是指示语。
        """
        nonlocal pr_buf, pr_page
        text = ''.join(pr_buf).strip()
        pr_buf, pr_page_local, pr_page = [], pr_page, None
        if len(text) < 16:
            return
        # 指示语 / 内容清单 / 表格指针：不是能力要求
        if re.match(r'^(本|该|这|以上|如下|下表|参见|内容包括|包括|其中|例如)', text):
            return
        if re.search(r'(如表\s*\d|见表\s*\d|所示[：:]?$|如下[：:]$)', text):
            return
        # 必须含对学生的动作要求
        if not re.search(r'(能|会|了解|理解|认识|掌握|运用|应用|说明|描述|分析|'
                         r'比较|判断|设计|制作|操作|探究|计算|表达|评价|体会|感受|'
                         r'知道|学会|尝试|识别|归纳|论证)', text):
            return
        rows.append({'subject': subject, 'course': course, 'courseNo': course_no,
                     'topic': topic, 'topicName': topic_name,
                     'code': sub_code, 'subTopic': sub_name,
                     'text': text, 'page': pr_page_local, 'section': '内容要求',
                     'examples': []})

    def flush_xueye():
        nonlocal xy_buf, xy_key, xy_page
        if xy_buf and xy_key:
            rows.append({'subject': subject, 'course': xy_key[0], 'courseNo': xy_key[1],
                         'topic': None, 'topicName': None, 'code': None,
                         'text': ''.join(xy_buf), 'page': xy_page,
                         'section': '学业要求', 'examples': []})
        xy_buf, xy_key, xy_page = [], None, None

    # 先把整份文档摊成 (行, 页码) 流，再一次性 unwrap —— 跨页续行必须在这里接上
    stream = [(l, pno) for pno, page in enumerate(r.pages, 1)
              for l in clean_lines(page.extract_text() or '')]
    if True:
        for s, pno in unwrap(stream):
            # ── 第三套（语文）：学习任务群 ──
            m = TASKGROUP.match(s)
            if m:
                flush_xueye(); flush_prose()
                topic, topic_name = m.group(1), m.group(2).strip()
                section = None
                continue
            m = XUEXI_SEC.match(s)
            if m:
                flush_xueye(); flush_prose()
                section = '内容要求' if m.group(1) == '学习目标与内容' else m.group(1)
                continue

            # ── 第四套（外语类）：表格 ──
            m = TABLE_HEAD.match(s)
            if m:
                flush_xueye(); flush_prose()
                topic, topic_name, section = None, m.group(1).strip(), '内容要求'
                continue
            if TABLE_COLS.match(s):
                continue
            # 裸课程类别行。可能同行带着第一个条目
            m = BARE_COURSE.match(s)
            if m and section == '内容要求' and not ITEM.match(s):
                flush_prose()
                course = m.group(1)
                course_no = (m.group(2) or '')
                if m.group(4):                      # 「选修 — 提高类 1. 能分辨…」
                    _emit_item(m.group(4).strip(), pno, m.group(3))
                continue

            # 第二套版式的课程类型：（一）必修课程
            m = COURSE_CN.match(s)
            if m:
                flush_xueye(); flush_prose()
                course, course_no = m.group(1), ''
                topic, topic_name, section = None, None, None
                continue
            # 第二套版式的主题：主题 1 ：化学科学与实验探究
            m = TOPIC_CN.match(s)
            if m:
                flush_xueye(); flush_prose()
                topic, topic_name = m.group(2), m.group(3).strip()
                section = None
                continue
            # 模块标题在内容之前，这才是课程类型的可靠来源
            m = MODULE_HEAD.match(s)
            if m:
                flush_xueye(); flush_prose()
                course, course_no = m.group(1), m.group(2)
                topic, topic_name, section = None, None, None
                continue
            # 模块级学业要求标题
            m = XUEYE_HEAD.match(s)
            if m:
                course, course_no, section = m.group(1), m.group(2), '学业要求'
                continue
            if BARE_SECTION.match(s):
                flush_xueye(); flush_prose()
                section = s.strip()
                continue
            if s.startswith('【内容要求】'):
                flush_xueye(); flush_prose()
                section = '内容要求'
                s = s[len('【内容要求】'):].strip()
                if not s:
                    continue
            elif s.startswith('【'):
                # 【教学提示】【学业要求】等 —— 内容要求段到此结束
                section = re.sub(r'[【】]', '', s.split('】')[0] + '】').strip('】【')
                continue

            m = TOPIC_HEAD.match(s)
            if m and section != '学业要求':
                topic, topic_name = m.group(1), m.group(2).strip()
                continue

            m = ITEM.match(s)
            if m and section == '内容要求':
                code, text = m.group(1), m.group(2).strip()
                if not topic or not code.startswith(topic + '.'):
                    warn.append(f'p{pno} 条目 {code} 的主题上下文缺失或不匹配（当前主题 {topic}）')
                rows.append({'subject': subject, 'course': course, 'courseNo': course_no,
                             'topic': topic, 'topicName': topic_name, 'code': code,
                             'text': text, 'page': pno, 'section': '内容要求',
                             'examples': []})
                continue

            # （1）… 和 1. … 型条目
            if section == '内容要求':
                m = PAREN_ITEM.match(s) or NUM_ITEM.match(s)
                if m and len(m.group(2)) > 10:
                    flush_prose()
                    _emit_item(m.group(2).strip(), pno, m.group(1))
                    continue

            m = EXAMPLE.match(s)
            if m and rows and section == '内容要求':
                rows[-1]['examples'].append(m.group(2).strip())
                continue

            # 第二套版式：内容要求段里的无编号正文。**必须按段累积再落。**
            # 和学业要求同一个坑：散文行没有结构头，unwrap 接不起来，
            # 每行单独成条 —— 实测抽出来的是「用，形成对新材料的敏感性」这种半句。
            # 累积到句末标点才算一段，遇到下一个结构标记强制落。
            if section == '内容要求':
                m = SUBHEAD.match(s)
                if m:
                    flush_prose()
                    sub_code, sub_name = m.group(1), m.group(2).strip()
                    continue
                pr_buf.append(s)
                if pr_page is None:
                    pr_page = pno
                if s.endswith(('。', '？', '！', '；')):
                    flush_prose()
                continue

            # 模块学业要求：它是**每模块一整段散文**，不是条目列表。
            # 散文行没有结构头，unwrap 接不起来（实测 85% 是碎片），
            # 所以在这里按模块累积，遇到下一个结构标记再落。拆句是下一步的事。
            if section == '学业要求' and course and len(s) > 6:
                key = (course, course_no)
                if xy_key != key:
                    flush_xueye()
                    xy_key, xy_page = key, pno
                xy_buf.append(s)
    flush_xueye(); flush_prose()
    return rows, warn


def check_codes(rows):
    """编号连续性机械校验 —— 免费的漏抽检测。

    义务教育那批没有编号，漏一条永远发现不了。这里 1.1.1 之后如果直接是 1.1.3，
    就说明中间那条丢了（十有八九是跨页断了）。
    """
    holes = []
    by = collections.defaultdict(list)
    for r in rows:
        # 只对三级编号（1.1.1）做连续性校验。其他版式的编号是纯数字或二级，
        # 在不同课程类别下会重新从 1 开始，「不连续」是正常的，不是缺口。
        if r['code'] and r['code'].count('.') == 2:
            by[(r['subject'], r['topic'])].append(r['code'])
    for k, codes in by.items():
        nums = sorted(int(c.rsplit('.', 1)[1]) for c in codes)
        if nums and nums != list(range(1, len(nums) + 1)):
            miss = sorted(set(range(1, max(nums) + 1)) - set(nums))
            if miss:
                holes.append((k, miss))
    return holes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default=None)
    ap.add_argument('--report', action='store_true', help='只统计，不写盘')
    a = ap.parse_args()

    pdfs = sorted(SRC.glob('*.pdf'))
    if not pdfs:
        sys.exit(f'没有课标 PDF。先跑 bash scripts/fetch-standards-gaozhong.sh')

    all_rows, all_warn = [], []
    # 碎片率是这一步唯一有意义的质量指标。条数上去了不等于对 ——
    # 实测宽规则能抽出 2,598 条，一半是内容清单和半句话。
    def frag_rate(items):
        if not items:
            return 0.0
        # ★ 「不以句号结尾」**不能**单独当碎片信号。生物学的内容要求整栏都不带
        #   句号（「说出细胞主要由 C、H、O、N、P、S 等元素构成」），按那个规则
        #   算出 100% 碎片率 —— 而它其实是全表最干净的一科。指标误判比没指标更糟：
        #   它会让人去修没坏的东西。
        #   真碎片的三个信号：从标点/连词起头、句中夹着编号（多条糊在一起）、
        #   混进了表头文字。
        bad = sum(1 for r in items
                  if re.match(r'^[，、；。等和与或）]', r['text'])
                  or re.search(r'[^0-9]\d\.\s*\S.{4,}\d\.', r['text'])
                  or re.search(r'课程类别|普通高中|课程标准', r['text']))
        return bad / len(items) * 100

    print(f"{'学科':<10}{'内容要求':>8}{'学业要求':>8}{'例题':>6}{'碎片率':>7}{'编号缺口':>8}")
    print('─' * 50)
    for p in pdfs:
        subject = p.stem.split('-', 1)[1]
        if subject == '课程方案':
            continue
        if a.only and subject != a.only:
            continue
        rows, warn = parse(subject, p)
        holes = check_codes(rows)
        nc = sum(1 for r in rows if r['section'] == '内容要求')
        nx = sum(1 for r in rows if r['section'] == '学业要求')
        ne = sum(len(r['examples']) for r in rows)
        fr = frag_rate([r for r in rows if r['section'] == '内容要求'])
        flag = '  ⚠' if fr > 12 else ''
        print(f"{subject:<10}{nc:>8}{nx:>8}{ne:>6}{fr:>6.0f}%{len(holes):>8}{flag}")
        all_rows += rows
        all_warn += [f'[{subject}] {w}' for w in warn]
        if holes:
            all_warn += [f'[{subject}] 主题 {k[1]} 编号缺 {m}' for k, m in holes[:6]]

    print('─' * 50)
    nc = sum(1 for r in all_rows if r['section'] == '内容要求')
    print(f"{'合计':<10}{nc:>8}{sum(1 for r in all_rows if r['section']=='学业要求'):>8}"
          f"{sum(len(r['examples']) for r in all_rows):>6}"
          f"{frag_rate([r for r in all_rows if r['section']=='内容要求']):>6.0f}%")
    print("\n⚠ = 碎片率 >12%，这一科的版式还没适配好，不要往 anchors/ 推")
    print(f"\n课程类型分布: {dict(collections.Counter((r['course'] or '未标') for r in all_rows))}")
    if all_warn:
        print(f"\n⚠ {len(all_warn)} 条告警（前 8 条）：")
        for w in all_warn[:8]:
            print('  ' + w)

    if a.report:
        print('\n（--report：没有写盘）')
        return
    OUT.mkdir(parents=True, exist_ok=True)
    for subject in sorted({r['subject'] for r in all_rows}):
        f = OUT / f'{subject}.jsonl'
        with f.open('w', encoding='utf-8') as fh:
            for r in all_rows:
                if r['subject'] == subject:
                    fh.write(json.dumps(r, ensure_ascii=False) + '\n')
    (OUT / 'warnings.txt').write_text('\n'.join(all_warn), encoding='utf-8')
    print(f"\n→ {OUT}/  （{len({r['subject'] for r in all_rows})} 科）")


if __name__ == '__main__':
    main()
