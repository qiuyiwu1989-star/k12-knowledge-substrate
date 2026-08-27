#!/usr/bin/env python3
"""
gaozhong_commit.py — 把 tools/out/gaozhong/ 的抽取结果落成 anchors/。

## 一条核心决定：**不改写，只筛**

义务教育那批栽在改写上：可判定闸要一个可判定动词，流水线就找了最省力的
「能说出 <名词> 是 <名词>」，把 93 条动手能力削成了常识问答（见 docs/rewrite.md）。
根因不是模型笨，是**只要允许改写，就存在一条比忠实更省力的过闸路径**。

所以这里的规则是：**拆句，然后只留原样就能过闸的**。不调模型，不改一个字。
过不了闸的不硬凑，进 candidates/ 等人看。代价是产出少，收益是**没有一条是编的**。

## 拆句

一个条目常含两三条要求：

    1.1.1 了解近代实验科学产生的背景，认识实验对物理学发展的推动作用。
          → 「了解近代实验科学产生的背景」 + 「认识实验对物理学发展的推动作用」

按句末标点和「，+ 要求动词」切。**不跨句拼、不补主语、不换动词。**

## 学段与课程类型

高中课标**按模块给内容，不按年级**。所以 stageHint 一律 G10–G12，
真实区分放在 `courseType`（必修 / 选择性必修 / 选修）上。

**不要发明年级精度。** 「必修 1 就是高一」是教学惯例，不是课标条文 ——
那正是 Marble「4–15 岁逐岁」的毛病：发明出来的精度看着专业，实际是假的。

    python3 tools/gaozhong_commit.py --dry-run
    python3 tools/gaozhong_commit.py --only 物理
    python3 tools/gaozhong_commit.py
"""
import argparse, collections, json, re, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mint_py import load_used_ids, mint_id          # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'tools/out/gaozhong'   # --src 可换（gaozhong2 是五科补抽的产物）

# 高中课标里 DAG 档只给这三科 —— 和义务教育一致。其余走 MATRIX。
# LIST 档是清单覆盖模型（字表词表篇目），高中课标没有这种东西。
DAG_SUBJECTS = {'数学', '物理', '化学'}

# 认知层级：从课标自己的动词读，不猜。
COGNITIVE_MAP = [
    (['运用', '应用', '设计', '论证', '解决', '制作', '创作', '评价'], '应用'),
    (['掌握', '会', '能'], '掌握'),
    (['理解', '认识', '说明', '解释', '分析', '比较'], '理解'),
    (['了解', '知道', '感受', '体会', '初步'], '了解'),
]

# 标签粘连：英语等科把课程类型和分类标签粘在句首
# （「选择性必修理解性技能1. 区分、分析和概括语篇中的主要观点」）。
LABEL_LEAD = re.compile(
    r'^(选择性必修|选修|必修)?\s*'
    r'(理解性技能|表达性技能|元认知策略|认知策略|交际策略|情感管理策略|资源策略|'
    r'语言知识|文化知识|学习策略|语言技能|主题|语篇|听|说|读|写|译|看)*\s*'
    r'(\d+\s*[.．、]\s*)?')

# 要求动词。用来判断「，」之后是不是新的一条要求。
REQ_VERB = ('了解', '知道', '理解', '认识', '掌握', '会', '能', '运用', '应用',
            '说明', '解释', '描述', '分析', '比较', '判断', '设计', '制作',
            '操作', '探究', '计算', '测量', '表达', '交流', '评价', '举例',
            '列举', '识别', '归纳', '论证', '感受', '体会', '说出', '指出')


# 兜底证据模板。识别它是为了不把它标成课标来源。
FALLBACK_EV = re.compile(r'^能在.{1,8}(课堂|作业).{0,6}情境中完成：|^能完成：')


def clean(text):
    """去掉粘在句首的课程类型和分类标签。只削句首，不动内容。"""
    prev = None
    while prev != text:
        prev = text
        text = LABEL_LEAD.sub('', text, count=1).lstrip('：:，、 ')
    return text.strip()


# 介词性动词：既能当状语标记，又能当谓语。**判「还是不是纯状语」时必须把它们排除**，
# 否则「运用示意图，」会被当成「已经有谓语了」—— 见 split_reqs 里 2026-08-25 那段。
PREP_VERBS = ('通过', '借助', '根据', '依据', '结合', '基于', '按照',
              '围绕', '针对', '经过', '运用', '利用')
# 认哪些章节。改这里要同步 DECISIONS.md —— 它决定了整个库的来源边界。
SECTIONS = ('内容要求', '学业质量')

PREP_ONLY = re.compile(r'^(能|会)?(' + '|'.join(PREP_VERBS) + r')')
# 砍段尾状语时用宽表：句首白名单里的介词（以/在/从）也算状语标记
PREP_WIDE = re.compile(r'^(能|会)?(' + '|'.join(PREP_VERBS) + r'|以|在|从)')
# 判谓语用的动词表 = 要求动词表减去介词性动词
PRED_VERB = tuple(v for v in REQ_VERB if v not in PREP_VERBS)
# 护栏里判谓语要用**宽表**：REQ_VERB 没收「进行/完成/学会/选择…」，
# 只用它的话「根据物质的组成和性质可以对物质进行分类」「结合当地学生的学习情况进行命题」
# 会被当成纯状语砍掉 —— 砍掉的正是能力本身。宽表**只用于判谓语，不作为切点**，
# 切点仍旧只认 REQ_VERB，免得动到 20 科的切法。
PRED_VERB_WIDE = PRED_VERB + (
    '学会', '尝试', '选择', '确定', '完成', '创作', '制作', '绘制', '拍摄',
    '临摹', '区分', '辨析', '认知', '知晓', '搜集', '收集', '进行')


def has_predicate(text, verbs=PRED_VERB):
    """text 里有没有一个**当谓语用**的能力动词。「…的分析…」里那种不算。"""
    for v in verbs:
        i = text.find(v)
        while i >= 0:
            if text[i + len(v):i + len(v) + 1] != '的':
                return True
            i = text.find(v, i + 1)
    return False


def is_pure_adverbial(text, prep=PREP_ONLY, verbs=PRED_VERB):
    """text 整个还只是个状语：介词标记起头，**剥掉标记之后没有谓语**。"""
    m = prep.match(text.strip())
    return bool(m) and not has_predicate(text.strip()[m.end():], verbs)


def split_reqs(text):
    """把一个条目拆成若干条要求。**只切，不补、不改。**

    两级：先按句末标点切，再看「，」后面是不是接着一个要求动词。
    「，」后接要求动词说明是并列的另一条要求（「了解 A，认识 B」）；
    不接就是同一条要求的成分（「通过实验，了解 A」）—— 那种不能切开，
    切开就丢了「通过实验」这个条件。
    """
    out = []
    for sent in re.split(r'(?<=[。？！；])', text):
        sent = sent.strip()
        if not sent:
            continue
        # 「，」后紧跟要求动词 → 并列要求，切；否则保留整句
        #
        # ★ 2026-08-24 修：**这段代码和上面的 docstring 说反了。**
        #   docstring 写着「通过实验，了解 A」不能切开，切开就丢了「通过实验」这个条件；
        #   而「了解」在 REQ_VERB 里，代码见到就切 —— 实测「通过实验，了解光的折射规律」
        #   被切成「通过实验」（不足 8 字丢弃）+「了解光的折射规律」，**条件静默消失**。
        #
        #   两种后果，第二种更糟：
        #     · 只剩状语的残句（「能在对都城繁荣的分析过程中」）—— 看得出来，可判定闸后来拦住了 7 条
        #     · 条件被丢、断言看着完全正常 —— **看不出来**，全库中招 65 条
        #
        #   修法：前一段若本身就是纯状语（介词起头、没有可判定的谓语），不切，并回去。
        #
        # ★ 2026-08-25 再修：上面那一版**只看了 buf 的开头**，判据写成
        #   `PREP_ONLY.match(buf)` —— 于是整句一旦以 通过/运用/根据 起头，
        #   该句后面**所有**切点被永久抑制，哪怕 buf 里早已装进一整条要求。
        #   实测被抑制的切点：地理 87/120、美术 16/30、物理 53/96、通用技术 54/167、
        #   化学 39/186，全库 245/1039 = 24%。粘成的长句再被可判定闸以「过长：超过 60 字」
        #   拒掉 —— 美术 65 条候选里 28 条死在这上面，是第一大拒因。
        #
        #   两处要一起改，缺一个就换一种错法：
        #     1) 判据看的是 **buf 当前是不是还只是个状语**，不是 buf 开头长什么样；
        #     2) 判谓语时要**排除介词性动词本身**。运用/利用 既在 PREP_VERBS 也在
        #        REQ_VERB，不排除的话「运用示意图，」自带「谓语」，照切 ——
        #        「运用示意图，说明地球的圈层结构」当场变成「说明地球的圈层结构」，
        #        **条件又没了**，正好绕回 2026-08-24 要防的那个错。地理全科都是这个句式。
        parts, buf = [], ''
        for seg in re.split(r'(?<=，)', sent):
            starts_req = any(seg.lstrip().startswith(v) for v in REQ_VERB)
            # buf 还是纯状语时不切 —— 切开这一刀丢的是课标写明的条件
            if buf and starts_req and not is_pure_adverbial(buf):
                parts.append(buf); buf = seg
            else:
                buf += seg
        if buf:
            parts.append(buf)

        # 反向护栏：防「留下条件、丢了断言」这个镜像错误。
        # **判据同样是「有没有谓语」，不是「开头长什么样」** ——
        # 按开头判会把「能运用变量控制的方法探究影响化学反应速率的因素」
        # 「能根据物质的性质分析…某些常见问题」这种真能力整条删掉（实测化学、
        # 信息技术、物理各有中招）。有谓语的一律留。
        for idx, p in enumerate(parts):
            # 段尾光秃秃的状语小句砍掉 —— 它是下一条的引子，粘在这儿只会把句子撑过 60 字
            segs = [x for x in re.split(r'(?<=，)', p) if x.strip()]
            while len(segs) > 1 and is_pure_adverbial(
                    segs[-1].strip().strip('，。；'), PREP_WIDE, PRED_VERB_WIDE):
                segs = segs[:-1]
            p = ''.join(segs).strip().strip('，；')
            # 整段只是个条件、后面还有别的段 → 丢。
            # 「如油画、版画和年画等」是同位语不算独立小句，不剔掉它，
            # 「能选择某一画种，如…等」就会被当成两段而躲过这一条。
            body = [x for x in re.split(r'(?<=，)', p)
                    if x.strip() and not x.lstrip().startswith(('如', '例如', '包括'))]
            if (idx != len(parts) - 1 and len(body) == 1
                    and is_pure_adverbial(re.sub(r'^(能够|能|会)', '', p),
                                          PREP_WIDE, PRED_VERB_WIDE)):
                continue
            if len(p) >= 8:
                out.append(p)
    return out


# ── 碎片过滤：**测截断，不测开头** ────────────────────────────────────────
#
# ★ 2026-08-25 重写。原先这里是一张句首白名单（GOOD_OPENER = 要求动词 + 状语引导
#   词），注释写着「碎片过滤器」，实际干的是「凡不以我认识的词起头的一律当碎片」。
#   两件事不是一回事，而白名单里一个艺术类动词都没有，于是高中音乐 76 条分句里
#   23 条完整句子被当碎片丢掉 —— 包括「学唱我国戏曲唱段及中外歌剧选段。」
#   「识读和运用乐谱，包括简谱或五线谱。」。表里有「根据」「借助」，没有「依据」，
#   也纯属漏词。**开头长什么样，和它是不是截断残片，本来就是两个问题。**
#
# 现在测真正的那个：**这一条是不是跨页截断留下的下半截。**
#
# 截断长什么样（实测，tools/out/gaozhong/体育与健康.jsonl）：抽取把条目的第一行
# 误当成了主题标题，于是 topicName 收走上半截、text 里剩下半截，从半个词开始 ——
#
#     topicName = '了解任意球、罚球点球、掷界外球、球门球和角球等足球比'
#     text      = '赛的基本规则，并能够在比赛中遵守规则，服从裁判。'
#                  ↑ 「比赛」被劈成两半，「赛的基本规则」就是那半个词
#
# 判据两条，都可判定，不靠读句子：
#
#   1. 条目认出了自己的编号（code）→ 抽取是从条目起点开始收的，不可能是下半截。
#      gaozhong2 的 370/380 条都有 code —— 它们**根本不需要过这道过滤**。
#   2. 没有 code 时看 topicName：真标题短（全库实测最长 22 字：「化学科学在材料
#      科学、人类健康等方面的重要作用」），被误当标题的正文折行**顶到抽取的折行
#      宽度**，全部落在 25~29 字。24 是这两堆之间的空档，取它当界。
#
# 命中之后**只砍第一个小句** —— 截断只伤到接缝处那一句。接缝后面的
# 「知道心理健康的内容和特征」是完整要求，砍整句就又是一次误杀。
LINE_WIDTH = 24        # 抽取折行宽度的下界。判据见上；改之前先跑 fragment_selftest()

# 连词起头的小句不可能是条目的开头 —— 它接的是被砍掉的那半句，一起砍。
CONT_LEAD = ('并', '且', '以及', '和', '或', '也', '还', '同时', '进而', '从而')


def head_truncated(item):
    """源条目本身是不是跨页截断留下的**下半截**。"""
    if item.get('code'):
        return False
    return len((item.get('topicName') or '').strip()) >= LINE_WIDTH


# 接缝落在小句边界上（上半截正好以「，」「；」收尾）→ 下半截从一个完整小句起头，
# 一个字都不用砍。不判这一条就是过砍：实测信息技术 p39「…作品开发方案，」+
# 「描述作品各组成部分及其功能作用，…」——「描述…」是完整的一条要求，砍掉是误杀。
SEAM_CLEAN = ('，', '；', '。', '、', '：', '？', '！')


def strip_truncated_head(text, topic_name=''):
    """砍掉接缝处那半句。返回 (剩下的正文, 砍掉的残片列表)。

    **只砍到小句为止，不砍整句。** 砍掉的是「赛的基本规则」这种半个词起头的
    残片，以及紧跟其后、以连词起头的续句 —— 那些续的也是上一页那半句。
    """
    if (topic_name or '').rstrip().endswith(SEAM_CLEAN):
        return text, []
    segs = [x for x in re.split(r'(?<=[，；。？！])', text) if x.strip()]
    cut = []
    while segs:
        cut.append(segs.pop(0).strip().strip('，；'))
        if not segs or not segs[0].lstrip().startswith(CONT_LEAD):
            break
    return ''.join(segs), [c for c in cut if c]


# 碎片过滤的自测用例。**全部抄自真实抽取产物**，不是想出来的
# （文件名见每条的注释）。改 LINE_WIDTH / SEAM_CLEAN / CONT_LEAD 之前先跑：
#
#     python3 tools/gaozhong_commit.py --selftest
FRAGMENT_FIXTURES = [
    # (topicName, code, text, 期望砍掉的残片)
    # ↓ gaozhong/体育与健康 p33：「足球比|赛」被劈成两半
    ('了解任意球、罚球点球、掷界外球、球门球和角球等足球比', None,
     '赛的基本规则，并能够在比赛中遵守规则，服从裁判。',
     ['赛的基本规则', '并能够在比赛中遵守规则']),
    # ↓ gaozhong/体育与健康 p25：接缝在「身体健康|同等重要」，只砍这一小句；
    #   后面「知道心理健康的内容和特征」是完整要求，砍整句就是误杀
    ('提高增进心理健康的意识和能力，理解心理健康与身体健康', None,
     '同等重要，知道心理健康的内容和特征，掌握和运用提高心理健康水平的方法；',
     ['同等重要']),
    # ↓ gaozhong/信息技术 p39：上半截以「，」收尾 = 接缝落在小句边界，一个字都不砍
    ('基于事物特征的分析，设计基于开源硬件的作品开发方案，', None,
     '描述作品各组成部分及其功能作用，明确各组成部分之间的调用关系。', []),
    # ↓ gaozhong/生物学：大概念标题本来就是整句，但条目认出了自己的编号 → 不是下半截
    ('各种细胞具有相似的基本结构，但在形态与功能上有所差异', '1.1',
     '说明细胞的结构。', []),
    # ↓ gaozhong/化学 p20：真标题短，text 从条目开头起
    ('化学实验', None,
     '初步学会物质检验、分离、提纯和溶液配制等化学实验基础知识和基本技能。', []),
    # ↓ gaozhong/地理 p20：24 字，全库真标题最长 22 字 —— 界就画在这两堆之间
    ('结合近些年发生的海洋争端事件，了解钓鱼岛及其附属', None,
     '岛屿、南海诸岛属于中国的立场和依据，说明维护国家领土主权和海洋权益的重要性。',
     ['岛屿、南海诸岛属于中国的立场和依据']),
]


def fragment_selftest():
    bad = 0
    for tn, code, text, want in FRAGMENT_FIXTURES:
        item = {'topicName': tn, 'code': code}
        got = strip_truncated_head(text, tn)[1] if head_truncated(item) else []
        flag = '✓' if got == want else '✗'
        if got != want:
            bad += 1
        print(f"  {flag} 截断={head_truncated(item)!s:<5} 砍={got}")
        if got != want:
            print(f"      期望={want}")
    print('\n✗ %d 个用例不符' % bad if bad else '\n✓ 碎片过滤自测全部通过')
    return bad


def ensure_neng(s):
    """补「能」前缀。仓库里现有锚点一律是「能 + 动词 + 对象」，句式统一了，
    家长向问句才能机械生成。**这是加前缀，不是改写** —— 一个字不动原文语义。"""
    if s.startswith(('能', '会')):
        return s
    return '能' + s


def cognitive_of(s):
    for verbs, level in COGNITIVE_MAP:
        if any(v in s for v in verbs):
            return level
    return '了解'


def node_call(script, payload_lines, raw=False):
    """raw=True 时按原样返回每行（signature-stdin.mjs 吐的是裸字符串，不是 JSON）。

    **行数必须对齐**：这些脚本都会跳过空行，掉一行就是整批错位，
    而错位不报错 —— 表现成「张三的判定安到了李四头上」。归一那一步早就在
    对齐上栽过一次，这里索性所有 node 调用统一断言。
    """
    p = subprocess.run(['node', str(ROOT / 'scripts/lib' / script)],
                       input='\n'.join(payload_lines), capture_output=True,
                       text=True, timeout=300)
    if p.returncode != 0:
        raise RuntimeError(f'{script} 失败：{(p.stderr or "")[:200]}')
    lines = p.stdout.splitlines()
    if len(lines) != len(payload_lines):
        raise RuntimeError(f'{script} 返回 {len(lines)} 行，送进去 {len(payload_lines)} 行'
                           f'—— 对齐坏了，不敢往下走')
    return lines if raw else [json.loads(l) for l in lines]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default=None)
    ap.add_argument('--src', default=None, help='换抽取产物目录，如 gaozhong2')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--selftest', action='store_true', help='只跑碎片过滤自测')
    a = ap.parse_args()

    if a.selftest:
        sys.exit(1 if fragment_selftest() else 0)

    src = (ROOT / 'tools/out' / a.src) if a.src else SRC
    files = sorted(src.glob('*.jsonl'))
    if not files:
        sys.exit(f'{src} 没有抽取结果')

    raw = []
    for f in files:
        if f.stem == 'warnings':
            continue
        for l in f.open(encoding='utf-8'):
            if l.strip():
                r = json.loads(l)
                # 【五、学业质量】也是合法来源 —— 2026-08-27 邱懿武明示确认（原话：「确认」），
                # 见 DECISIONS.md。此前这里只收「内容要求」，导致 20 科里 17 科
                # 从没碰过那一章：德语的真断言全在那儿（它的课程内容章是教学设计散文）、
                # 美术整本没有【学业要求】、音乐的内容要求 62 条只出得了 4 条锚点
                # 而学业质量 121 条出得了 86 条。**过滤器的形状一直在替课标说话。**
                if r['section'] in SECTIONS and (not a.only or r['subject'] == a.only):
                    raw.append(r)
    print(f"读入 {len(raw)} 条内容要求（{len({r['subject'] for r in raw})} 科）")

    # 拆句。碎片过滤在**拆之前**：截断伤的是条目正文的接缝，不是某一条分句的开头。
    cand, frag_drop, trunc_items = [], [], 0
    for r in raw:
        base = clean(r['text'])
        if head_truncated(r):
            trunc_items += 1
            base, cut = strip_truncated_head(base, r.get('topicName') or '')
            frag_drop.extend(cut)
            if not base.strip():
                continue
        for s in split_reqs(base):
            cand.append({'src': r, 'statement': ensure_neng(s)})
    print(f"拆成 {len(cand)} 条候选"
          f"（{trunc_items} 个条目是跨页截断的下半截，砍掉接缝处 {len(frag_drop)} 条残片）")
    if frag_drop:
        print("    残片样本：" + ' ／ '.join(x[:22] for x in frag_drop[:3]))

    # 归一（必须在过闸之前 —— 闸检查的必须就是要落盘的字符串）
    norm = node_call('normalize-stdin.mjs',
                     [json.dumps({'text': c['statement'], 'discipline': c['src']['subject']},
                                 ensure_ascii=False) for c in cand])
    if len(norm) != len(cand):
        sys.exit(f'归一返回 {len(norm)} 条，期望 {len(cand)} 条 —— 对齐坏了，不敢往下走')
    changed = 0
    for c, n in zip(cand, norm):
        if n != c['statement']:
            changed += 1
        c['statement'] = n
    print(f"  归一改动 {changed} 条")
    # 二次核对：归一必须是幂等的。不核对，就会像第一次那样把带尾空格的句子写进库，
    # 等 CI 报「未规范化」才发现 —— 而那时已经铸了 494 个 ID。
    again = node_call('normalize-stdin.mjs',
                      [json.dumps({'text': c['statement'], 'discipline': c['src']['subject']},
                                  ensure_ascii=False) for c in cand])
    bad = [(c['statement'], g) for c, g in zip(cand, again) if g != c['statement']]
    if bad:
        sys.exit(f'归一不幂等，{len(bad)} 条：{bad[:2]}')

    # 可判定闸
    verdicts = node_call('check-stdin.mjs', [c['statement'] for c in cand])
    passed, rejected = [], collections.Counter()
    for c, v in zip(cand, verdicts):
        if v.get('ok'):
            c['verb'] = v.get('verb')
            passed.append(c)
        else:
            rejected[(v.get('reasons') or ['?'])[0].split('：')[0]] += 1
    print(f"过可判定闸 {len(passed)} / {len(cand)} = {len(passed)/max(1,len(cand))*100:.0f}%")
    for k, n in rejected.most_common(6):
        print(f"    拒 {n:>4}  {k}")

    # 去重：签名**一律问 scripts/lib/signature-stdin.mjs 要**，不在这儿自己搭一套。
    #
    # ★ 2026-08-25 修：这里原先自建 (discipline, verb, object) 元组，而
    #   normalize.mjs 的 dedupeSignature 看的是 statement 剜掉动词之后的**整句**。
    #   两套确实不一样，signature-stdin.mjs 的开头就写着「Python 工具不许自己再实现一遍」。
    #   分歧方向实测是**误杀**：object 只取动词之后那一截，遇到
    #   「能理解软件在信息系统中的作用，借助软件工具与平台开发网络应用软件」
    #   会退化成 object='软件'，于是同科所有 verb 相同、object 也退化成「软件」的
    #   条目互撞。拿现有 2969 条在册锚点回测：python 元组判出 11 条「重复」，
    #   而 js 签名判定它们互不相同 —— 那 11 条是被白白丢掉的真锚点。
    #   反方向（python 漏拦、js 拦得住）0 条。
    #
    #   object 字段照旧要落盘（schema 里有），只是**不再拿它当签名**。
    def object_of(stmt, verb):
        i = stmt.find(verb)
        o = stmt[i + len(verb):].strip('，。；、 ') if i >= 0 else stmt
        return o[:60] or stmt[:60]

    existing = []
    for f in sorted((ROOT / 'anchors').glob('*.jsonl')):
        for l in f.open(encoding='utf-8'):
            if l.strip():
                x = json.loads(l)
                if not x.get('deprecated'):
                    existing.append({'discipline': x['discipline'], 'verb': x.get('verb'),
                                     'statement': x.get('statement')})
    used_sig = set(node_call('signature-stdin.mjs',
                             [json.dumps(x, ensure_ascii=False) for x in existing],
                             raw=True)) if existing else set()
    new_sig = node_call('signature-stdin.mjs',
                        [json.dumps({'discipline': c['src']['subject'], 'verb': c['verb'],
                                     'statement': c['statement']}, ensure_ascii=False)
                         for c in passed], raw=True) if passed else []
    kept, dup = [], 0
    for c, sig in zip(passed, new_sig):
        if sig in used_sig:
            dup += 1
            continue
        used_sig.add(sig)
        c['object'] = object_of(c['statement'], c['verb'])
        kept.append(c)
    print(f"去重后 {len(kept)}（撞签名丢弃 {dup}）")

    by_subj = collections.Counter(c['src']['subject'] for c in kept)
    by_course = collections.Counter(c['src'].get('course') or '未标' for c in kept)
    print(f"\n学科分布：{dict(by_subj.most_common())}")
    print(f"课程类型：{dict(by_course)}")

    print("\n─── 样本 ───")
    for c in kept[:6]:
        s = c['src']
        print(f"  [{s['subject']}·{s.get('course') or '?'}] {s.get('code') or '-'} p{s['page']}")
        print(f"    {c['statement']}")

    if a.dry_run:
        print("\n（--dry-run：没有写盘）")
        return

    # ★ topic / strand 也必须归一。第一版只归一了 statement，
    #   结果法语的「法语Ⅰ」（罗马数字）落进 topic，CI 报 22 处未规范化。
    #   **凡是要落盘的文本字段，都得过同一道归一** —— 挑着过就一定漏。
    topics = sorted({(c['src'].get('topicName') or '') for c in kept} - {''})
    if topics:
        tn = node_call('normalize-stdin.mjs',
                       [json.dumps({'text': t, 'discipline': ''}, ensure_ascii=False) for t in topics])
        topic_fix = dict(zip(topics, tn))
        nfix = sum(1 for k, v in topic_fix.items() if k != v)
        if nfix:
            print(f"  主题名归一 {nfix} 个（如 {[f'{k}→{v}' for k, v in topic_fix.items() if k != v][:2]}）")
    else:
        topic_fix = {}

    used = load_used_ids(ROOT)
    rows = []
    for c in kept:
        s = c['src']
        subj = s['subject']
        # 先算 evidence —— 下面 evidenceSource 要看它是不是兜底模板。
        ev = ([s['examples'][0]] if s.get('examples') else
              [f"能在{subj}课堂或作业情境中完成：{c['statement'][:40]}"])
        rows.append({
            'id': mint_id(used), 'discipline': subj,
            'track': 'DAG' if subj in DAG_SUBJECTS else 'MATRIX',
            'strand': topic_fix.get(s.get('topicName') or '', s.get('topicName')),
            'topic': topic_fix.get(s.get('topicName') or '', s.get('topicName')),
            'dimension': None,
            'statement': c['statement'], 'verb': c['verb'], 'object': c['object'],
            'type': 'KNOWLEDGE' if cognitive_of(c['statement']) == '了解' else 'CONCEPTUAL',
            # literacy 用课标自己标的（音乐/美术/德语的「（素养N）」、地理的「（综合思维）」），
            # 没标就空着 —— **不替课标贴标签**。
            # 课标标了 ≥4 个素养时视为「全标」——**全标等于没标**，
            # 这正是 validate 那条规则的原话，只不过这次是课标自己这么标的
            # （美术 p50 三条被标了全部 5 个核心素养）。
            # 处理：provenance.srcLiteracy 忠实留下课标标了什么，
            # 锚点的 literacy 置空 —— 一个不构成区分度的标签不该当属性用。
            'literacy': ([] if len(s.get('literacy') or []) >= 4
                         else list(s.get('literacy') or [])),
            'cognitive': cognitive_of(c['statement']),
            # 高中课标按模块给内容，不按年级。**不发明年级精度。**
            'stageHint': {'min': 'G10', 'max': 'G12'},
            'courseType': s.get('course'),
            'evidence': ([s['examples'][0]] if s.get('examples') else
                         [f"能在{subj}课堂或作业情境中完成：{c['statement'][:40]}"]),
            'assessment': None,
            # **证据是兜底模板时不许声称来自课标。** promote.py 当年就是对的：
            # 用兜底证据就标 fallback。这里没照做，结果 860 条一边复读断言、
            # 一边声称 evidenceSource=curriculum-content-gaozhong ——
            # 断言确实来自课标（provenance.method/srcText/srcPage 都在），
            # 但**证据不是**，而 evidenceSource 说的正是证据。
            'evidenceSource': ('curriculum-content-gaozhong'
                               if ev and not FALLBACK_EV.match(ev[0]) else 'fallback'),
            'reviewStatus': 'llm-proposed',      # 无人看过。不是 llm 生成，但也没人复核
            'reviewedBy': [], 'deprecated': False, 'supersededBy': None,
            'crosscutting': [], 'practice': [],
            'provenance': {
                'srcSubject': subj, 'srcPage': s['page'],
                'srcCode': s.get('code'), 'srcTopic': s.get('topicName'),
                'srcCourse': s.get('course'), 'srcCourseNo': s.get('courseNo'),
                'srcText': s['text'],
                # 水平号只作**出处坐标**放在 provenance，不做锚点属性 ——
                # 跨学科的水平号互不等价（日语「四级」/法语「三级」/德语「G2」/化学「水平2」），
                # 见 mappings/quality-levels.json 的文件头。放这里是为了能翻回那一格表，
                # 不是为了比较。
                **({'srcLevel': s['level']} if s.get('level') is not None else {}),
                # 标明这批素养标签是**课标自己标的**（条目尾部的「（素养N）」、
                # 地理的「（综合思维）」、艺术的表头维度名），不是我们贴的。
                # validate 的「literacy 最多 2 个」是防我们乱贴，对课标原标不适用。
                **({'srcLiteracy': list(s['literacy'])} if s.get('literacy') else {}),
                'method': ('gaozhong-xueye-split' if s.get('section') == '学业质量'
                           else 'gaozhong-textlayer-split'),
            },
            'schemaVersion': '0.1.0',
        })

    # 按学科分文件写。**追加**到 anchors/gaozhong-<学科>.jsonl，
    # 不混进义务教育的文件 —— 两份课标是两个来源，分开才查得清。
    #
    # ⚠️ 2026-08-22 修：这里原先是 `open('w')` —— **注释写着「追加」，代码在覆盖**。
    #    补抽五科那次跑完，德语原有的 5 条、美术 8 条、思想政治 10 条被静默冲掉，
    #    共 29 条，是靠 validate 报「边引用不存在的 anchorId」才发现的。
    #    注释和代码说反的 bug 今天撞到第三个（另两个：split_reqs 的条件切分、
    #    evidenceSource 引用未定义的 ev）。**光看注释不算读过代码。**
    #    写完加一道自检：文件行数只许涨不许缩。
    n = 0
    before = {}
    for subj in sorted({r['discipline'] for r in rows}):
        f = ROOT / f'anchors/gaozhong-{subj}.jsonl'
        before[subj] = sum(1 for l in f.open(encoding='utf-8') if l.strip()) if f.exists() else 0
        with f.open('a', encoding='utf-8') as fh:
            for r in rows:
                if r['discipline'] == subj:
                    fh.write(json.dumps(r, ensure_ascii=False) + '\n'); n += 1
    for subj, b in before.items():
        f = ROOT / f'anchors/gaozhong-{subj}.jsonl'
        after = sum(1 for l in f.open(encoding='utf-8') if l.strip())
        if after < b:
            sys.exit(f'✗ {f.name} 从 {b} 行缩到 {after} 行 —— 有数据被覆盖，立刻停')
    print(f"\n已写 {n} 条 → anchors/gaozhong-*.jsonl（{len({r['discipline'] for r in rows})} 个文件）")
    print("全部 reviewStatus=llm-proposed —— 无人看过，不计入 usableAnchors。")
    print("下一步：npm run check")


if __name__ == '__main__':
    main()
