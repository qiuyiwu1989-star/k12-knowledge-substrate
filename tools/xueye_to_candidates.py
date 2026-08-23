#!/usr/bin/env python3
"""
xueye_to_candidates.py — 把高中课标【学业要求】的 120 段模块级描述拆成候选锚点。

这批料抽出来之后一直没人动过：`gaozhong_commit.py` 只吃 `section == "内容要求"`，
【学业要求】整段落在 `tools/out/gaozhong/*.jsonl` 里没有下游。本工具补上这一段，
**只产候选，不落 anchors/** —— 落库仍然是 gaozhong_commit.py 那道工序的事。

## 继承的那条核心决定：不改写，只筛

和 `gaozhong_commit.py` 一字不差：**拆句，然后只留原样就能过闸的**。
根因见 `docs/rewrite.md` —— 不是模型笨，是**只要允许改写，就存在一条比忠实更省力
的过闸路径**（那次是「能说出 <名词> 是 <名词>」，把 93 条动手能力削成了常识问答）。

所以本工具**零模型调用**。全部逻辑是正则切分 + 闭合词表比对 + 调 scripts/lib 的现成闸。
拆句直接 `from gaozhong_commit import split_reqs, clean, opener_ok, ensure_neng` ——
**不复制一份**。复制的那一份一定会漂移，而漂移的表现是「两边产出不一样但都不报错」。
同理，归一 / 可判定闸 / 去重签名一律走 `scripts/lib/*-stdin.mjs`，Python 侧一行都不重写。

## 这批料和【内容要求】的三点不同

### 1. 它是模块级达成描述，粒度更粗

【内容要求】是条目（「1.1.1 了解近代实验科学产生的背景」），【学业要求】是一整段
（「学习本模块之后，学生能够运用地理信息技术……（地理实践力）。能够运用地球科学的
基础知识，说明一些自然现象之间的关系和变化过程（综合思维）。」）。

一段拆出来的条，**仍然可能比现有锚点粗**。本工具**不为了好看硬拆** ——
拆到 `split_reqs` 的规则为止，然后给每条打上 `coarse` / `charLen` / `seriesCount`，
让人按自己的阈值重新筛。硬拆需要补主语、换动词，那就是改写，就是 docs/rewrite.md 的坑。

### 2. 括号里标着学科核心素养 —— 那是白拿的官方对应

「……变化过程（综合思维）」里的「综合思维」是**课标自己给的**素养归属，
比我们事后打的标签可靠得多。剥掉它是为了让断言干净，但**必须单独记下来**。

判据是**闭合词表**：只有当括号内用「、」分开的每一项都落在
`mappings/literacy.json` 对应学科的取值里，才认定这是素养标注并剥掉。
否则一律当正文留着 —— 「（如计算机、智能手机和平板电脑等）」不能被误剥。
艺术课标写成「（素养2"创意表达"）」，剥掉「素养N」和引号后再比对。

**归属精度只到句号级。** 一个「。」结尾的句子里可能有几个分号小句共用一个素养标注，
拆开之后无法判断标注管哪几条 —— 那种判断只能靠读，靠读就是靠模型。所以本工具的做法是：
同一句拆出的所有条**共享**该句的素养标注，并在 `literacyShared` 里如实标出来
「这句拆出了 N 条，标注是句级的不是条级的」。**宁可标成共享，也不猜。**

### 3. 抽取时串了小节 —— 120 段里有一大半不是学业要求

实测：化学 5 段全是【教学建议】，西班牙语 11 段全是教学/考试/教材编写，
历史 18 段里 12 段是【教学与评价建议】。抽取阶段的小节归属漏了。

预筛判据必须**可判定**，不能靠读：**段首是列表编号（（1） / 1. / 例 1）的，一律拒**。
真正的学业要求段在这批料里无一例外以「学习本模块之后 / 通过本模块的学习 /
完成本模块学习后 / 学生 / 能」起头；教学建议、教材编写、案例题一律以编号起头
（艺术的「学生学习本模块之后能做到：（1）……」编号在套话之后，不受影响）。
被预筛掉的整段进 rejected，带上拒因等人看 —— **不硬凑，也不静默丢**。

## 段尾串进了下一节 —— 在标题标记处截断

实测：艺术 p38 的学业要求后面直接跟着整节「五、学业质量（一）学业质量内涵……」，
生物学 p25 后面跟着「模块2 遗传与进化本模块包括……」。抽取按页取文本，
小节边界没识别出来。不截断的后果是「能评价内容评价内容参照"学业质量水平"」
这种句子照样过闸 —— 它可判定、开头完整、长度合规，**长得完全合规**，
正是 docs/rewrite.md 那句「可判定但被削平的东西更危险」的同一类。

判据必须可判定：**在第一个章节标题标记处截断**，标记是
「〈中文数字〉、」「模块N」「必修N / 选择性必修N」「附录N」。这些是课标的编号体系，
出现即意味着当前小节已经结束。截掉的部分记在 `tailCut` 里备查，不静默丢。

## 状语被切飞了 —— 同句内合回去

`split_reqs` 的 docstring 说「通过实验，了解 A」不该切开，切开就丢了「通过实验」
这个条件。但它的代码在「，」后见到 `了解`（在 REQ_VERB 里）就切 —— **代码和自己的
docstring 不一致**。后果实测可见：「能通过分析简单的信息系统」「能在解决生活和学习中
的问题时」这种只剩状语、主句跑到下一条去了的残句，照样过闸。

本工具在 `split_reqs` 之后加一道**合并**：一条如果以纯状语引导词起头（通过 / 根据 /
在 / 结合 / 借助 / 针对 …）且以「，」结尾，就并进同句的下一条。

**这不是改写，也不是「跨句拼」**：合并只在同一个「。」之内进行，而且合出来的字符串
必须是原句的**连续子串** —— 代码里 assert 了这一点。它做的事是「撤销一次过度切分」，
不是造句。改 `gaozhong_commit.py` 才是正解，但那个文件不归本工序动。

## 剥前缀不是改写

「学习本模块之后，学生能够……」这个前缀要剥。剥完的句子**每个字都还是原文的** ——
去掉的是套话，不是内容。同理剥掉的还有 `学生` 后面的情态词（应 / 应该 / 要），
因为课标全篇是同一个情态，留不留不带信息量；以及 `●`、`（N）` 这类项目符号。
补「能」前缀沿用 `ensure_neng` —— 仓库现有锚点一律「能 + 动词 + 对象」，
统一句式家长向问句才能机械生成。**加前缀不是改写，一个字不动原文语义。**

## 未闭合的括号一律剥掉

实测 7 处：「（生命观念、科学● 建构并使用细胞模型……」「（唯物史观、历史解释、家国模块3
文化交流与传播」。这是抽取时的跨页/跨栏截断，括号后面接的是**下一节的正文**。
留着它就等于把别的小节的字塞进候选断言里。判据可判定：一个「（」在遇到「●」或文末
之前没有闭合，即是截断。剥掉，只把其中**精确命中词表**的项记为素养，
并置 `literacyTruncated: true`、把原始残片留在 `truncatedTail` 里备查。

## 顺序不能反

归一 → 过闸 → 算签名。**闸检查的必须就是要落盘的字符串**，
签名算的也必须是同一个字符串。挑着过就一定漏（gaozhong_commit.py 的 topic 字段
就是这么漏的，CI 报了 22 处未规范化）。归一还要二次核对幂等 —— `normalizeText`
单次调用不幂等，见 normalize-stdin.mjs 的注释。

    python3 tools/xueye_to_candidates.py
    python3 tools/xueye_to_candidates.py --only 地理 --dry-run
"""
import argparse
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# ★ 拆句规则只有一份。不许在这里复制 split_reqs —— 复制必漂移，且漂移不报错。
from gaozhong_commit import (  # noqa: E402
    clean, ensure_neng, node_call, opener_ok, split_reqs,
)

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'tools/out/gaozhong'
OUT_OK = ROOT / 'tools/out/xueye-candidates.jsonl'
OUT_NO = ROOT / 'tools/out/xueye-rejected.jsonl'
LITERACY = ROOT / 'mappings/literacy.json'

# ── 段级预筛 ────────────────────────────────────────────────────────────────
# 段首是列表编号 / 例题标号 → 不是学业要求正文，是教学建议·教材编写·案例。
NOT_XUEYE_LEAD = re.compile(r'^\s*(?:[（(]\s*\d+\s*[)）]|\d+\s*[.．、]\s|例\s*\d+\s)')

# ── 套话前缀。逐个剥，剥到不动为止。剥掉的是套话，剩下的每个字都是原文。 ──────
BOILERPLATE = [
    '学生学习本模块之后', '学习本模块之后', '通过本模块的学习', '完成本模块学习后',
    '学完本模块之后', '学完本模块后', '本模块学习之后', '学习本模块后',
    '学生', '应该能做到', '能做到', '应该', '应', '要',
]
LEAD_PUNCT = '：:，,、；;。.  　'

# 项目符号 / 条目编号：既是要剥的噪声，也是切分边界。
ENUM = re.compile(r'[●·•▲■]|[（(]\s*\d+\s*[)）]')

# 闭合括号（含内容不含嵌套）。半角全角都吃。
PAREN = re.compile(r'[（(]([^（()）]{1,60})[)）]')
# 未闭合括号：一路吃到「●」或文末都没有闭合 —— 抽取截断的特征。
PAREN_TRUNC = re.compile(r'[（(]([^（()）]*?)(?=[●·•]|$)')
# 艺术写成「素养2"创意表达"」，比对前先脱掉编号和引号。
LIT_ITEM_STRIP = re.compile(r'^素养\s*\d*\s*|[“”"\'‘’《》\s　]')

SENT_END = re.compile(r'(?<=[。？！])')

# 章节标题标记：出现即说明当前小节已经结束，后面是串进来的下一节正文。
TAIL_CUT = re.compile(
    r'[一二三四五六七八九十]{1,3}、(?=[\u4e00-\u9fff])'
    r'|模块\s*\d'
    r'|(?:选择性)?必修\s*[\dⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]'
    r'|附录\s*\d')

# 被切飞的状语，判据分两类，都要求「整条就是一个介词短语」：
#   A 类：纯介词起头。这些词在汉语里**不能作谓语**，所以整条一定没有主句。
#   B 类：「在 / 从」起头 **且** 以方位·时间后置词收尾（「……过程中」「……的基础上」）。
#     「在」「从」本身太泛（「在实验中记录数据」是完整要求），必须再看收尾。
ADV_PREP = ('通过', '借助', '根据', '依据', '结合', '基于', '按照', '围绕',
            '针对', '随着', '面对')
ADV_TAIL = ('中', '时', '后', '下', '上', '里', '内', '际', '视角', '角度',
            '基础上', '过程中', '情况下', '前提下', '条件下', '背景下')


def is_dangling_adv(p):
    if p.startswith(ADV_PREP):
        return True
    return p.startswith(('在', '从')) and p.endswith(ADV_TAIL)


def load_literacy():
    """24 科核心素养闭合词表。高中优先用 gaozhong 档，没有就退回 values。"""
    d = json.loads(LITERACY.read_text(encoding='utf-8'))['disciplines']
    out = {}
    for subj, v in d.items():
        vals = (v.get('gaozhong') or []) + (v.get('values') or [])
        out[subj] = set(vals)
    return out


def strip_boilerplate(text):
    """剥掉段首套话。返回 (剩余文本, 剥掉的原文)。"""
    s = text.lstrip(LEAD_PUNCT)
    stripped = []
    changed = True
    while changed:
        changed = False
        s = s.lstrip(LEAD_PUNCT)
        for b in BOILERPLATE:
            if s.startswith(b):
                stripped.append(b)
                s = s[len(b):]
                changed = True
                break
    return s.lstrip(LEAD_PUNCT), ''.join(stripped)


def lit_items(inner, vocab):
    """括号内容切成项，脱掉「素养N」和引号。返回 (命中项, 未命中项)。"""
    hit, miss = [], []
    for x in re.split(r'[、,，/；;]', inner):
        t = LIT_ITEM_STRIP.sub('', x).strip()
        if not t:
            continue
        (hit if t in vocab else miss).append(t)
    return hit, miss


def pull_literacy(sent, vocab):
    """从一句里剥出素养标注。

    只有**括号内每一项都在闭合词表里**才认定是素养标注并剥掉 ——
    「（如计算机、智能手机和平板电脑等）」不能被误剥。
    未闭合的括号是抽取截断，一律剥掉，只把精确命中词表的项记为素养。

    返回 (剥完的句子, 素养列表, 是否截断, 截断残片)。
    """
    found, truncated, tail = [], False, None

    def repl(m):
        hit, miss = lit_items(m.group(1), vocab)
        if hit and not miss:
            found.extend(hit)
            return ''
        return m.group(0)

    s = PAREN.sub(repl, sent)

    m = PAREN_TRUNC.search(s)
    if m:
        hit, _ = lit_items(m.group(1), vocab)
        found.extend(hit)
        truncated = True
        tail = m.group(0)
        s = s[:m.start()] + s[m.end():]

    # 去重保序
    seen, lits = set(), []
    for x in found:
        if x not in seen:
            seen.add(x)
            lits.append(x)
    return s, lits, truncated, tail


def remerge_adverbial(parts, sent, stat):
    """把被切飞的状语合回同句的下一条。

    只**撤销一次过度切分**，不造句。两道自检保证这一点：
      1. 合并只在同一个「。」之内（`sent` 就是那一句）；
      2. 合出来的字符串（忽略空白）必须是 `sent` 的**连续子串** ——
         `split_reqs` 把切点上的「，」剥掉了，这里按原样补回一个「，」，
         补不回原句的（比如切点其实是「；」）就**不合并**，让闸去拒，不硬凑。
    """
    flat = re.sub(r'\s', '', sent)
    out, pend = [], []
    for p in parts:
        if is_dangling_adv(p):
            pend.append(p)
            continue
        while pend:
            merged = pend[-1] + '，' + p
            if re.sub(r'\s', '', merged) not in flat:
                break            # 切点不是「，」→ 不是同一条要求，不合
            p = merged
            pend.pop()
            stat['merged'] += 1
        out.append(p)
    out += pend                   # 整句以状语收尾 → 原样留着，让闸拒
    return out


def is_coarse(s):
    """粒度指标。**只标不筛** —— 模块级描述拆出来本来就可能粗，粗就标出来。"""
    series = s.count('、')
    return (len(s) >= 30 or series >= 2), len(s), series


def read_segments(only=None):
    rows = []
    for f in sorted(SRC.glob('*.jsonl')):
        if f.stem == 'warnings':
            continue
        for l in f.open(encoding='utf-8'):
            if not l.strip():
                continue
            r = json.loads(l)
            if r.get('section') == '学业要求' and (not only or r['subject'] == only):
                rows.append(r)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default=None)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    vocab_all = load_literacy()
    segs = read_segments(a.only)
    if not segs:
        sys.exit('没有【学业要求】记录。先跑 python3 tools/gaozhong_extract.py')
    print(f"读入 {len(segs)} 段学业要求（{len({r['subject'] for r in segs})} 科）")
    print(f"  分布：{dict(collections.Counter(r['subject'] for r in segs).most_common())}")

    stat = collections.Counter()
    rejected = []          # 统一的拒绝出口，带 stage + reasons
    cand = []
    seg_used = 0
    lit_miss = collections.Counter()   # 括号里没命中词表的内容，用来核对词表覆盖

    for seg in segs:
        subj = seg['subject']
        vocab = vocab_all.get(subj, set())

        # 1) 段级预筛
        if NOT_XUEYE_LEAD.match(seg['text']):
            rejected.append({
                'stage': 'segment', 'discipline': subj, 'page': seg['page'],
                'course': seg.get('course'), 'text': seg['text'],
                'reasons': ['非学业要求正文：段首是列表编号/例题标号，'
                            '属教学建议·教材编写·案例，抽取时串了小节'],
            })
            continue
        seg_used += 1

        # 2) 剥套话前缀
        body, lead = strip_boilerplate(seg['text'])

        # 2b) 段尾串进了下一节 → 在第一个章节标题标记处截断
        tail_cut = None
        mt = TAIL_CUT.search(body)
        if mt:
            tail_cut = body[mt.start():]
            body = body[:mt.start()]
            rejected.append({
                'stage': 'tail-cut', 'discipline': subj, 'page': seg['page'],
                'course': seg.get('course'), 'text': tail_cut,
                'reasons': [f'段尾截断：遇到章节标题标记「{mt.group(0)}」，'
                            f'后面是串进来的下一节正文，不属于本段学业要求'],
            })

        # 3) 项目符号 / 条目编号既是噪声也是切分边界
        for chunk in ENUM.split(body):
            if not chunk or not chunk.strip():
                continue
            # 4) 切到「句」为止 —— 素养标注的归属精度就到这里
            for sent in SENT_END.split(chunk):
                sent = sent.strip().strip(LEAD_PUNCT)
                if not sent:
                    continue
                sent, lits, trunc, tail = pull_literacy(sent, vocab)
                for m in PAREN.finditer(sent):
                    _, miss = lit_items(m.group(1), vocab)
                    if miss:
                        lit_miss[(subj, m.group(1)[:24])] += 1
                sent = sent.strip().strip(LEAD_PUNCT)
                if not sent:
                    continue
                # 5) 句 → 条。规则从 gaozhong_commit 直接拿，不重写。
                reqs = []
                for s in remerge_adverbial(split_reqs(sent), sent, stat):
                    s = clean(s).strip().strip(LEAD_PUNCT)
                    if not s:
                        continue
                    if not opener_ok(s):
                        rejected.append({
                            'stage': 'split', 'discipline': subj, 'page': seg['page'],
                            'course': seg.get('course'), 'statement': s,
                            'literacy': lits, 'srcText': seg['text'],
                            'reasons': ['开头不完整：不以要求动词或状语引导词起头，'
                                        '多半是跨页截断留下的半句'],
                        })
                        continue
                    reqs.append(s)
                for s in reqs:
                    cand.append({
                        'seg': seg, 'statement': ensure_neng(s),
                        'literacy': lits, 'literacyShared': len(reqs) > 1,
                        'literacyTruncated': trunc, 'truncatedTail': tail,
                        'leadStripped': lead, 'sentence': sent,
                        'tailCut': tail_cut,
                    })

    print(f"段级预筛：留下 {seg_used} 段，拒 {len(segs) - seg_used} 段（非学业要求正文）")
    print(f"段尾截断：{sum(1 for r in rejected if r['stage'] == 'tail-cut')} 段串进了下一节，已在标题标记处截掉")
    print(f"状语合并：{stat['merged']} 处被 split_reqs 切飞的状语合回了同句的下一条")
    frag = sum(1 for r in rejected if r['stage'] == 'split')
    print(f"拆成 {len(cand)} 条候选（另丢弃 {frag} 条开头不完整的碎片）")

    if not cand:
        sys.exit('没有候选，不写盘。')

    # 6) 归一 —— 必须在过闸之前，闸检查的必须就是要落盘的字符串
    def norm(items):
        return node_call('normalize-stdin.mjs', [
            json.dumps({'text': c['statement'], 'discipline': c['seg']['subject']},
                       ensure_ascii=False) for c in items])

    n1 = norm(cand)
    if len(n1) != len(cand):
        sys.exit(f'归一返回 {len(n1)} 条，期望 {len(cand)} 条 —— 对齐坏了，不敢往下走')
    changed = 0
    for c, n in zip(cand, n1):
        if n != c['statement']:
            changed += 1
        c['statement'] = n
    n2 = norm(cand)
    bad = [(c['statement'], g) for c, g in zip(cand, n2) if g != c['statement']]
    if bad:
        sys.exit(f'归一不幂等，{len(bad)} 条：{bad[:2]}')
    print(f"归一改动 {changed} 条（已核对幂等）")

    # 7) 可判定闸
    verdicts = node_call('check-stdin.mjs', [c['statement'] for c in cand])
    passed = []
    reason_hist = collections.Counter()
    for c, v in zip(cand, verdicts):
        if v.get('ok'):
            c['verb'] = v.get('verb')
            passed.append(c)
        else:
            for r in (v.get('reasons') or ['?']):
                reason_hist[r.split('：')[0]] += 1
            rejected.append({
                'stage': 'gate', 'discipline': c['seg']['subject'],
                'page': c['seg']['page'], 'course': c['seg'].get('course'),
                'statement': c['statement'], 'literacy': c['literacy'],
                'verb': v.get('verb'), 'reasons': v.get('reasons') or [],
                'srcText': c['seg']['text'],
            })
    print(f"过可判定闸 {len(passed)} / {len(cand)} = {len(passed) / len(cand) * 100:.0f}%")
    for k, n in reason_hist.most_common(10):
        print(f"    拒 {n:>4}  {k}")

    # 8) 去重签名 —— **调 scripts/lib/signature-stdin.mjs，不许自己算**
    existing = []
    for f in sorted((ROOT / 'anchors').glob('*.jsonl')):
        for l in f.open(encoding='utf-8'):
            if l.strip():
                x = json.loads(l)
                if not x.get('deprecated'):
                    existing.append({'discipline': x.get('discipline'),
                                     'verb': x.get('verb'),
                                     'statement': x.get('statement')})
    used_sig = set(node_call2('signature-stdin.mjs', existing))
    print(f"已有活跃锚点 {len(existing)} 条 → {len(used_sig)} 个签名")

    sigs = node_call2('signature-stdin.mjs', [
        {'discipline': c['seg']['subject'], 'verb': c['verb'],
         'statement': c['statement']} for c in passed])
    if len(sigs) != len(passed):
        sys.exit(f'签名返回 {len(sigs)} 条，期望 {len(passed)} 条 —— 对齐坏了')
    kept, dup_lib, dup_self = [], 0, 0
    batch_sig = set()
    for c, sig in zip(passed, sigs):
        if sig in used_sig:
            dup_lib += 1
            rejected.append({'stage': 'dedupe', 'discipline': c['seg']['subject'],
                             'page': c['seg']['page'], 'statement': c['statement'],
                             'literacy': c['literacy'], 'verb': c['verb'],
                             'signature': sig,
                             'reasons': ['撞已有锚点签名（同学科）']})
            continue
        if sig in batch_sig:
            dup_self += 1
            rejected.append({'stage': 'dedupe', 'discipline': c['seg']['subject'],
                             'page': c['seg']['page'], 'statement': c['statement'],
                             'literacy': c['literacy'], 'verb': c['verb'],
                             'signature': sig,
                             'reasons': ['本批内重复签名']})
            continue
        batch_sig.add(sig)
        c['signature'] = sig
        kept.append(c)
    print(f"去重后 {len(kept)}（撞已有锚点 {dup_lib}，本批内重复 {dup_self}）")

    # ── 素养标注核对 ────────────────────────────────────────────────────
    tagged = [c for c in kept if c['literacy']]
    all_tags = collections.Counter(x for c in kept for x in c['literacy'])
    print(f"\n带官方素养标注的候选 {len(tagged)} / {len(kept)}"
          f"（标注共 {sum(all_tags.values())} 次，{len(all_tags)} 个不同取值）")
    print(f"  取值分布：{dict(all_tags.most_common(12))}")
    print(f"  **全部落在 mappings/literacy.json 闭合词表内**（判据即词表比对，不在表内不认）")
    if lit_miss:
        print(f"  未认定为素养、按正文保留的括号内容 {sum(lit_miss.values())} 处，"
              f"样本：{[k[1] for k in list(lit_miss)[:3]]}")

    coarse_n = sum(1 for c in kept if is_coarse(c['statement'])[0])
    print(f"粒度：{coarse_n} / {len(kept)} 条标为 coarse（≥30 字 或 ≥2 个顿号）—— **只标不筛**")

    print("\n─── 样本 5 条 ───")
    for c in kept[:5]:
        s = c['seg']
        print(f"  [{s['subject']}·{s.get('course') or '?'}] p{s['page']}  "
              f"素养={c['literacy'] or '-'}{' (句级共享)' if c['literacyShared'] else ''}")
        print(f"    {c['statement']}")

    if a.dry_run:
        print("\n（--dry-run：没有写盘）")
        return

    with OUT_OK.open('w', encoding='utf-8') as fh:
        for c in kept:
            s = c['seg']
            coarse, ln, series = is_coarse(c['statement'])
            fh.write(json.dumps({
                'statement': c['statement'],
                'discipline': s['subject'],
                'verb': c['verb'],
                'signature': c['signature'],
                # 课标自己给的官方素养对应。空表示这一科/这一句没标。
                'literacy': c['literacy'],
                # True = 这条素养标注是**句级**的，同句还有别的条共享它，不是这条独有
                'literacyShared': c['literacyShared'],
                'literacyTruncated': c['literacyTruncated'],
                # 粒度：模块级描述拆出来可能比现有锚点粗。**标出来，不筛。**
                'granularity': 'coarse' if coarse else 'fine',
                'charLen': ln, 'seriesCount': series,
                'courseType': s.get('course'),
                # 高中按模块给内容，不按年级。**不发明年级精度。**
                'stageHint': {'min': 'G10', 'max': 'G12'},
                'reviewStatus': 'llm-proposed',   # 无人看过（也非 llm 生成）
                'provenance': {
                    'srcSubject': s['subject'], 'srcPage': s['page'],
                    'srcSection': '学业要求', 'srcCourse': s.get('course'),
                    'srcCourseNo': s.get('courseNo'), 'srcTopic': s.get('topicName'),
                    'srcSentence': c['sentence'],
                    'srcText': s['text'],
                    'leadStripped': c['leadStripped'],
                    'truncatedTail': c['truncatedTail'],
                    'tailCut': c['tailCut'],
                    'method': 'gaozhong-xueye-split',
                },
                'schemaVersion': '0.1.0',
            }, ensure_ascii=False) + '\n')

    with OUT_NO.open('w', encoding='utf-8') as fh:
        for r in rejected:
            fh.write(json.dumps(r, ensure_ascii=False) + '\n')

    print(f"\n已写 {len(kept)} 条 → {OUT_OK.relative_to(ROOT)}")
    print(f"     {len(rejected)} 条 → {OUT_NO.relative_to(ROOT)}"
          f"（{dict(collections.Counter(r['stage'] for r in rejected))}）")
    print("候选文件不进 anchors/ —— 落库是 gaozhong_commit.py 那道工序的事，先等人看。")


def node_call2(script, objs):
    """signature-stdin.mjs 吃的是每行一个 JSON 对象，和 node_call 的用法不同。"""
    if not objs:
        return []
    import subprocess
    p = subprocess.run(['node', str(ROOT / 'scripts/lib' / script)],
                       input='\n'.join(json.dumps(o, ensure_ascii=False) for o in objs),
                       capture_output=True, text=True, timeout=300)
    if p.returncode != 0:
        raise RuntimeError(f'{script} 失败：{(p.stderr or "")[:200]}')
    return [l for l in p.stdout.split('\n') if l.strip()]


if __name__ == '__main__':
    main()
