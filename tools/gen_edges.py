#!/usr/bin/env python3
"""
gen_edges.py — 生成先修依赖边。

**模型只能从给定列表里挑，不能自由生成 ID。** 这是杜绝幻觉边的唯一办法：
Marble 的 3,221 条边全是模型自由生成的，结果社区提了「抗逆力成长依赖 20 以内加减法」
这种 issue。这里每条边的两个端点都来自我们自己的锚点表，模型只做「选哪几个」。

候选池的构造本身就带着一层结构约束（这层是免费的、可信的）：
  · 只在同学科内部找（跨学科边另外单跑，量小且需要更强证据）
  · 只找学段不晚于自己的（学段序是课标给的硬结构）
  · 同领域优先，其次跨领域
  · 池子上限 40 条，超了按「同领域 + 学段最近」截断

产出全部 reviewStatus=llm-proposed，strength 一律 soft ——
拿不到教材共识偏序或错题共现之前，没有资格断言 hard。
（参考 cn-primary-math-knowledge-graph：111 条边全部只敢标 soft。）

  python3 tools/gen_edges.py --discipline 数学
"""
import argparse, collections, hashlib, itertools, json, math, os, random, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib import request, error

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(__file__).parent / '.cache-edges'

# ★ 必须含 G10–G12。少了它们，891 条高中锚点的学段是 None，
#   「只找学段不晚于自己的」这条约束就失效 —— 而那是候选池里唯一免费且可信的结构。
#   同一个 bug 在 make_graph 里出现过一次（高中被画在五年级位置）。
#   **凡是硬编码学段表的地方都要一起改，漏一处就静默失效。**
STAGE_ORD = {f'G{i}': i for i in range(1, 13)}

CROSS_PROMPT = """你在为一个 K12 能力图谱标注**跨学科**先修依赖。给你一条【目标能力】和一份**别的学科**的【候选前置列表】。

跨学科前置是罕见的。绝大多数情况下正确答案是空数组。只有下面这种才算：
**学这条目标能力时，学生必须现场用到那条别科能力，用不出来就卡住。**

✅ 算：物理「计算速度」← 数学「两位数除法」（不会除就算不出速度）
✅ 算：化学「根据化学方程式计算」← 数学「解一元一次方程」
✅ 算：地理「读地图比例尺」← 数学「比与比例」
❌ 不算：历史「分析史料」← 语文「阅读理解」（都是读，但没有具体依赖的技能点）
❌ 不算：任何「都需要观察力/表达力/思维能力」这类泛泛的关联
❌ 不算：主题相似、都出现在同一个情境里

最多挑 2 条，宁可一条不挑。挑之前先问自己：**不会那条，这条是不是真的做不了？**
reason 必须写清「用在哪一步」，写不出具体那一步就不要挑。

只输出一行 JSON，不要代码块、不要解释：
{"prereqs":[{"n":3,"reason":"算速度要做路程÷时间，不会两位数除法这一步就卡住"}]}"""

PROMPT = """你在为一个 K12 能力图谱标注先修依赖。给你一条【目标能力】和一份【候选前置列表】。

任务：从候选列表里挑出**真正必须先掌握**的前置能力，最多 3 条。

判据（严格）：
- 只有「不先会 A 就学不了 B」才算前置。**主题相关、领域相同都不算**。
- 宁可少挑，也不要凑数。一条都不合适就返回空数组。
- 只能返回候选列表里出现过的编号，不许编造。

只输出一行 JSON，不要代码块、不要解释：
{"prereqs":[{"n":3,"reason":"不先会…就无法…"},{"n":7,"reason":"…"}]}
reason 用一句话说清为什么，20-40 字，写不出具体理由的就不要挑。"""

ENDPOINTS = [("/v1/chat/completions", "openai"), ("/anthropic/v1/messages", "anthropic")]
_rr = itertools.count()


def call(user_text, base, key, model, timeout=120, sys_prompt=None):
    last = None
    for attempt in range(7):
        suffix, style = ENDPOINTS[next(_rr) % len(ENDPOINTS)]
        if style == "anthropic":
            body = {"model": model, "max_tokens": 600, "thinking": {"type": "disabled"},
                    "system": sys_prompt or PROMPT, "messages": [{"role": "user", "content": user_text}]}
            hdr = {"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
        else:
            body = {"model": model, "temperature": 0, "max_completion_tokens": 600,
                    "thinking": {"type": "disabled"},
                    "messages": [{"role": "system", "content": sys_prompt or PROMPT},
                                 {"role": "user", "content": user_text}]}
            hdr = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
        req = request.Request(base + suffix, data=json.dumps(body).encode(), headers=hdr)
        try:
            d = json.load(request.urlopen(req, timeout=timeout))
            if style == "anthropic":
                return "".join(b.get("text", "") for b in d.get("content", []))
            return d['choices'][0]['message'].get('content') or ''
        except error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code not in (429, 500, 502, 503, 504):
                raise RuntimeError(f"HTTP {e.code}: {e.read().decode()[:150]}")
        except Exception as e:
            last = type(e).__name__
        time.sleep(min(25.0, 1.5 * (1.9 ** attempt)) * (0.6 + random.random() * 0.8))
    raise RuntimeError(f"重试耗尽（{last}）")


def stage_of(a):
    sh = a.get('stageHint') or {}
    # 默认值不能写死 5/9 —— 那是「只有 9 个学段」时代的遗留。
    # 学段缺失时给一个**不会误导排序**的中位，而不是假装它是九年级。
    return STAGE_ORD.get(sh.get('min'), 6), STAGE_ORD.get(sh.get('max'), 12)


# 高中锚点的学段是 G10，初中是 G7–G9。按「学段最近」排，同为 G10 的
# 高中锚点全排在前面，40 条的池子在到达初中之前就满了 ——
# 结果**跨学段的边一条都建不出来**（实测高中物理 243 条边里 0 条来自初中）。
# 而初中物理→高中物理恰恰是最真实的一类先修关系。
# 所以给「跨学段」留一个保底名额：池子里至少留 1/3 给更早学段的锚点。
CROSS_STAGE_QUOTA = 1 / 3


def band(g):
    """学段档。课标就是按这个分的：1-2 / 3-4 / 5-6 / 7-9 / 高中。
    **跨没跨学段要按档比，不能按年级差比。**"""
    return 0 if g <= 2 else 1 if g <= 4 else 2 if g <= 6 else 3 if g <= 9 else 4


def build_bridge_pool(target, all_in_disc, cap=40):
    """跨学段专用候选池：**只放更早学段档的锚点**，同档的一条都不放。

    普通池子里同档候选永远更「近」，模型自然优先选它们 ——
    加配额也没用，因为配额判据本身是错的（见 build_pool 里那段注释）。
    要拿到跨学段的边，只能给一个**同档候选完全不存在**的池子。

    被依赖多的优先：跨学段的真前置多半是那些「底层能力」
    （能观察比较、能读懂图表、能列举性质），它们的出度天然高。
    """
    tmin, _ = stage_of(target)
    tb = band(tmin)
    if tb == 0:
        return []                       # G1-2 没有更早的学段
    pool = []
    for a in all_in_disc:
        if a['id'] == target['id'] or a.get('track') == 'LIST':
            continue
        amin, _ = stage_of(a)
        if band(amin) >= tb:            # ★ 同档或更晚的一律不要
            continue
        same_strand = (a.get('strand') and a.get('strand') == target.get('strand'))
        pool.append(((0 if same_strand else 1, -(tb - band(amin))), a))
    pool.sort(key=lambda x: x[0])
    return [a for _, a in pool[:cap]]


# ── 候选池的字面相似度索引（char-bigram TF-IDF，纯标准库）─────────────
# 2026-09-28 合入（修法由 08-28 的子 Agent 做出、主进程复核后合并）。
#
# 同学科池原来的排序键是 (是否同 strand, 学段差)。通用技术 260 条锚点全是 G10、
# strand/topic 全为 None → 键对每个目标恒为 (1, 0) → Python 稳定排序等于没排 →
# **260 个目标里 225 个拿到的是同一份池子**（学科文件里的前 40 条）。
# 实测「有资格出现在任何候选池里的锚点」：通用技术 41/260 · 西班牙语 41/142 ·
# 信息技术 41/99 —— 三科都恰好 41，因为那就是「文件前 40 条 + 被剔掉的目标自己补进来的那条」。
# **模型不是判断错，是根本没看见。**
_PUNC = re.compile(r'[\s，。、；：？！“”‘’（）《》()\[\]{}<>,.;:?!"\'`~@#$%^&*_+=|\\/-]+')


def _sim_text(a):
    parts = [a.get('statement') or '']
    for k in ('dimension', 'topic', 'strand'):
        if a.get(k):
            parts.append(str(a[k]))
    return _PUNC.sub('', ''.join(parts))


def _grams(s):
    """char-bigram + unigram。加 unigram 是为了短断言不至于向量全空。"""
    g = collections.Counter(s[i:i + 2] for i in range(len(s) - 1))
    g.update(s)
    return g


class SimIndex:
    """一组锚点上的 TF-IDF 索引，O(N) 内存。"""

    def __init__(self, anchors):
        self.vec, docs, df = {}, {}, collections.Counter()
        for a in anchors:
            g = _grams(_sim_text(a)); docs[a['id']] = g; df.update(g.keys())
        n = max(1, len(docs))
        idf = {t: math.log(1 + n / (1 + c)) for t, c in df.items()}
        for aid, g in docs.items():
            v = {t: (1 + math.log(c)) * idf.get(t, 0.0) for t, c in g.items()}
            norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
            self.vec[aid] = {t: x / norm for t, x in v.items()}

    def cos(self, a_id, b_id):
        va, vb = self.vec.get(a_id), self.vec.get(b_id)
        if not va or not vb:
            return 0.0
        if len(va) > len(vb):
            va, vb = vb, va
        return sum(x * vb.get(t, 0.0) for t, x in va.items())


_SIM_CACHE = {}


def _sim_for(anchors):
    k = id(anchors)
    if k not in _SIM_CACHE:
        _SIM_CACHE[k] = SimIndex(anchors)
    return _SIM_CACHE[k]


def build_pool(target, all_in_disc, cap=40, sim=None):
    """候选前置池：同学科、学段不晚于自己、同领域优先，**但给跨学段留名额**。"""
    sim = sim or _sim_for(all_in_disc)
    tmin, _ = stage_of(target)
    same, earlier = [], []
    for a in all_in_disc:
        if a['id'] == target['id']:
            continue
        # 已废弃的锚点不能当前置。原先没这一条 —— 恒等池的 41 条里有 5 条是废弃的，
        # 照样被当成候选喂给模型。第二个独立的 bug，和排序键无关，一起修。
        if a.get('deprecated'):
            continue
        # 同学科的 LIST 档不能当前置 —— 字表词表篇目是覆盖模型，
        # 「学完这个才能学那个」的语义它没有（validate 里有对应的硬闸）。
        # 跨学科时它们可以当前置，那条路走 build_cross_pool。
        if a.get('track') == 'LIST':
            continue
        amin, amax = stage_of(a)
        if amin > tmin:              # 学段整体晚于目标 → 不可能是前置
            continue
        same_strand = (a.get('strand') and a.get('strand') == target.get('strand'))
        # 第三项 -sim 是**严格细化**：前两项不同的候选相对次序和原来完全一致，
        # 只有原本平手的才按字面相似度重排。所以数学这类有区分度的学科几乎无损，
        # strand/学段全空的学科直接从恒等池变成按目标定制的池。
        key = (0 if same_strand else 1, tmin - amin, -sim.cos(target['id'], a['id']))
        # 「更早学段」的判据：**按学段档比，不按年级差比**。
        # 原先写的是 `tmin - amin >= 3`（年级差 ≥3），而学段档是
        # 1-2 / 3-4 / 5-6 / 7-9 / 10-12 —— G4→G5 跨了档但差只有 1，
        # 于是相邻档的候选一条也进不了跨学段配额池。
        # 实测后果：全库先修边 92% 在同一学段内，跨学段只有 7%，
        # 「十二年成长路径」这个承诺撑不住。
        (earlier if band(amin) < band(tmin) else same).append((key, a))
    same.sort(key=lambda x: x[0])
    earlier.sort(key=lambda x: x[0])
    quota = int(cap * CROSS_STAGE_QUOTA)
    picked = [a for _, a in same[:cap - quota]] + [a for _, a in earlier[:quota]]
    # 一侧不足时用另一侧补满，不浪费池子
    if len(picked) < cap:
        rest = [a for _, a in same[cap - quota:]] + [a for _, a in earlier[quota:]]
        picked += rest[:cap - len(picked)]
    return picked[:cap]


# 工具型学科：它们的能力会被别的学科现场调用。反过来极少见
#（没有哪条数学能力是「必须先会某条历史能力」才学得了的）。
ENABLERS = {'数学': 0, '语文': 1, '信息科技': 2}


def build_cross_pool(target, all_anchors, outdeg, cap=40):
    """跨学科候选池：别的学科、学段不晚于自己。

    **按学科均摊配额，不能全局排序取前 N。** 第一版按 ENABLERS 排序取前 36，
    结果数学把池子占满了，语文一条都进不去 —— 产出 44 条边全是「数学 → X」，
    连「撰写实验报告 ← 语文表达」这种明显的都出不来。池子里没有的，模型选不出来。

    ★ 2026-09-28 再修两处，都是 08-28 两个子 Agent 各自独立查出来的：

    1. **排序依据错了。** 原来按 outdeg（被依赖次数）排，而 outdeg 高低反映的是
       「在自己学科内被依赖多」，跟「对这个目标有没有用」不是一回事。实测 900 个目标的
       候选池并集只有 **102 条锚点（全库 2.8%）** —— 其余 97% 从来没有机会被提议当前置。
       现在先按和目标的字面相似度排，outdeg 只做平手时的次序。

    2. **工具科名额从没兑现过。** 注释写「工具科 10 个名额」，但轮转是每科每轮放 1 条：
       高中目标有 23 个可选前科，第一轮放满 23、第二轮到 40 就截断 —— 数学永远只拿到 2 条。
       实测高中 G10 目标 **400/400 的池子里数学 ≤ 2 条**，同时小语种和英语占 8 条以上。
       「会计算算法的时空复杂度」的池子里，数学只有「20 以内口算」和「四则运算的含义」。
       现在分两段：工具科先按名额取，剩下的名额再在其余学科间轮转。
    """
    tmin, _ = stage_of(target)
    td = target['discipline']
    sim = _sim_for(all_anchors)
    by_d = collections.defaultdict(list)
    for a in all_anchors:
        if a['discipline'] == td or a.get('deprecated') or stage_of(a)[0] > tmin:
            continue
        by_d[a['discipline']].append(a)
    for d in by_d:
        by_d[d].sort(key=lambda a: (-sim.cos(target['id'], a['id']), -outdeg.get(a['id'], 0)))
    pool = []
    # 第一段：工具科按名额取。名额按 cap 缩放，给其余学科留出至少一半的位置。
    per_enabler = max(2, (cap // 2) // max(1, sum(1 for d in by_d if d in ENABLERS)))
    for d in sorted((d for d in by_d if d in ENABLERS), key=lambda d: ENABLERS[d]):
        pool += by_d[d][:per_enabler]
    # 第二段：其余学科轮转，每科每轮一条，直到填满
    others = [d for d in by_d if d not in ENABLERS]
    others.sort(key=lambda d: -max((sim.cos(target['id'], a['id']) for a in by_d[d][:1]), default=0))
    i = 0
    while len(pool) < cap and any(len(by_d[d]) > i for d in others):
        for d in others:
            if len(by_d[d]) > i and len(pool) < cap:
                pool.append(by_d[d][i])
        i += 1
    # 工具科如果还有富余而池子没满，补进来
    if len(pool) < cap:
        seen = {a['id'] for a in pool}
        for d in (d for d in by_d if d in ENABLERS):
            for a in by_d[d][per_enabler:]:
                if len(pool) >= cap: break
                if a['id'] not in seen: pool.append(a); seen.add(a['id'])
    return pool[:cap]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--discipline', default=None)
    ap.add_argument('--src', default='anchors')
    ap.add_argument('--concurrency', type=int, default=14)
    ap.add_argument('--cross', action='store_true', help='只跑跨学科边（判据更严，最多 2 条/锚点）')
    ap.add_argument('--stage-bridge', action='store_true',
                    help='只建**跨学段**的边：候选池里同档锚点一条都不放。'
                         '普通模式下同档候选永远更近，跨学段边只占 7%。')
    ap.add_argument('--missing-only', action='store_true',
                    help='只给「一条前置边都没有」的锚点建边。**候选池仍取整个学科** —— '
                         '新锚点的前置本来就该来自已有的那些。'
                         '比 --split-only 通用：新落库的、原本就孤立的，一次都覆盖。')
    ap.add_argument('--split-only', action='store_true',
                    help='只给拆原子新建的那批（provenance.splitFrom）建边。'
                         '**候选池仍取整个学科** —— 原子的前置本来就可能来自别处。')
    ap.add_argument('--out', default=str(ROOT / 'tools/out/edges-generated.jsonl'))
    a = ap.parse_args()

    base, key, model = os.environ['MIMO_BASE'], os.environ['MIMO_KEY'], os.environ.get('MIMO_MODEL', 'mimo-v2.5')
    CACHE.mkdir(exist_ok=True)

    anchors = []
    for f in sorted((ROOT / a.src).rglob('*.jsonl')):
        for l in f.open(encoding='utf-8'):
            anchors.append(json.loads(l))
    # --cross 的候选池必须看全库：--discipline 只限定「后继是哪一科」，不能先把候选删光。
    # 原来这里直接过滤 anchors，而 build_cross_pool 又会剔掉同学科的 ——
    # 于是 `--cross --discipline X` 的池子必然是空的。三个子 Agent 各自撞到过，
    # 这大概也是跨学科那条路从 08-15 之后一直没重跑的原因之一。
    all_anchors = anchors
    if a.discipline:
        anchors = [x for x in anchors if x['discipline'] == a.discipline]
    by_disc = collections.defaultdict(list)
    for x in anchors:
        by_disc[x['discipline']].append(x)
    print(f"锚点 {len(anchors)} 条，{len(by_disc)} 个学科 · 并发 {a.concurrency}")

    outdeg_seed = collections.Counter()
    for f in sorted((ROOT / 'edges').rglob('*.jsonl')):
        for l in f.open(encoding='utf-8'):
            outdeg_seed[json.loads(l)['prerequisiteId']] += 1

    # 谁已经有前置边了 —— --missing-only 用它跳过。
    # 退休的边不算数：那条关系已经作废，锚点等于又没有前置了。
    has_incoming = collections.Counter()
    for f in sorted((ROOT / 'edges').rglob('*.jsonl')):
        for l in f.open(encoding='utf-8'):
            e = json.loads(l)
            if not e.get('retired'):
                has_incoming[e['anchorId']] += 1

    jobs = []
    for disc, group in by_disc.items():
        # LIST 档不建图（语文字词篇目、英语词表是覆盖模型）——跨学科时它们可以当前置，
        # 但不能当被修方（覆盖模型没有「学完这个才能学那个」的语义）。
        #
        # ⚠️ 2026-08-22 修：这里原先是 `group[0].get('track') == 'LIST'` ——
        #    **拿这一科的第一条锚点去判断整个学科**。而 anchors/ 里
        #    英语的第一条、语文的第一条恰好都是 LIST（词表/字表排在前面），
        #    于是这两科**整科被跳过**，它们的 183 + 94 = 277 条 MATRIX 锚点
        #    历次建边全部漏掉，一条边都没建过。
        #    这不是这一轮引入的，是一直如此，直到 --missing-only
        #    报出「552 条缺前置但只跑了 334 条」才露出来。
        #    **一条锚点的档位是它自己的属性，不是学科的属性。**
        for t in group:
            if t.get('track') == 'LIST':
                continue
            # --split-only：只给这批建，但池子照样是整个学科的，
            # 否则原子只能在原子之间找前置，那是凭空造出来的小圈子。
            if a.split_only and not (t.get('provenance') or {}).get('splitFrom'):
                continue
            if a.missing_only and has_incoming.get(t['id']):
                continue
            if t.get('deprecated'):
                continue
            pool = (build_cross_pool(t, all_anchors, outdeg_seed) if a.cross
                    else build_bridge_pool(t, group) if a.stage_bridge
                    else build_pool(t, group))
            if pool:
                jobs.append((t, pool))
    print(f"待标注 {len(jobs)} 条（{'跨学科' if a.cross else '同学科'}，"
          f"平均候选池 {sum(len(p) for _, p in jobs)/max(1,len(jobs)):.0f}）")

    def work(job):
        t, pool = job
        lines = [f"{i+1}. [{p['discipline']}] {p['statement']}（{(p.get('stageHint') or {}).get('min','?')}）"
                 if a.cross else
                 f"{i+1}. {p['statement']}（{(p.get('stageHint') or {}).get('min','?')}，{p.get('strand') or '未标注'}）"
                 for i, p in enumerate(pool)]
        user = (f"【目标能力】{t['statement']}\n"
                f"（学科 {t['discipline']}，领域 {t.get('strand') or '未标注'}，"
                f"学段 {(t.get('stageHint') or {}).get('min','?')}）\n\n"
                f"【候选前置列表】\n" + "\n".join(lines))
        sp = CROSS_PROMPT if a.cross else PROMPT
        h = hashlib.sha256((sp + user).encode()).hexdigest()[:24]
        cf = CACHE / f"{h}.json"
        if cf.exists():
            return t, pool, json.loads(cf.read_text())
        try:
            txt = call(user, base, key, model, sys_prompt=sp)
        except Exception as e:
            return t, pool, {'error': str(e)[:60]}
        m = re.search(r'\{.*\}', txt, re.S)
        obj = {}
        if m:
            try:
                obj = json.loads(m.group(0))
            except Exception:
                obj = {'error': '解析失败'}
        cf.write_text(json.dumps(obj, ensure_ascii=False))
        return t, pool, obj

    t0 = time.time()
    raw, errs = [], 0
    with ThreadPoolExecutor(a.concurrency) as ex:
        for n, (t, pool, obj) in enumerate(ex.map(work, jobs), 1):
            if obj.get('error'):
                errs += 1
            for p in (obj.get('prereqs') or [])[:(2 if a.cross else 3)]:
                try:
                    idx = int(p['n']) - 1
                except Exception:
                    continue
                if not (0 <= idx < len(pool)):
                    continue                      # 编号越界 = 幻觉，直接丢
                reason = str(p.get('reason') or '').strip()
                if len(reason) < 6:
                    continue                      # 说不出理由的边不要
                raw.append({'anchorId': t['id'], 'prerequisiteId': pool[idx]['id'],
                            'strength': 'soft', 'reason': reason[:80],
                            'crossDiscipline': a.cross or None,
                            'evidence': [{'kind': 'llm', 'detail': f"候选池 {len(pool)} 选 {idx+1}，模型提议未复核"
                                          + ('（跨学科，判据更严）' if a.cross else '')},
                                         {'kind': 'standard-hierarchy',
                                          'detail': f"课标学段序：{(pool[idx].get('stageHint') or {}).get('min','?')} → {(t.get('stageHint') or {}).get('min','?')}"}],
                            'reviewStatus': 'llm-proposed', 'reviewedBy': [],
                            'schemaVersion': '0.1.0'})
            if n % 100 == 0 or n == len(jobs):
                print(f"  {n}/{len(jobs)}（边 {len(raw)}，{time.time()-t0:.0f}s）", flush=True)

    # ---- 去重 + 破环 ----
    seen, edges = set(), []
    byid = {x['id']: x for x in anchors}
    for e in raw:
        k = (e['anchorId'], e['prerequisiteId'])
        if k in seen or (e['prerequisiteId'], e['anchorId']) in seen:
            continue
        seen.add(k)
        edges.append(e)

    # 破环。原先用 (学段, id) 排序判方向，同学段的边就按 id 大小任意丢——
    # 实测 36% 的边死在这条任意规则上。改成只丢两种：
    #   1) 前置的学段**严格晚于**被修的（方向确实反了）
    #   2) 加进去真的会成环（走一遍可达性）
    stage = {x['id']: stage_of(x)[0] for x in anchors}
    kept, drop_stage, drop_cycle = [], 0, 0
    adj = collections.defaultdict(set)      # A -> 它的前置们

    def reaches(src, dst):
        """沿前置链从 src 能否走到 dst（迭代，避免深图爆栈）"""
        stack, seen = [src], set()
        while stack:
            v = stack.pop()
            if v == dst:
                return True
            if v in seen:
                continue
            seen.add(v)
            stack.extend(adj[v])
        return False

    # 先排：学段跨度大的边优先保留（更可能是真先修），同跨度按原顺序
    edges.sort(key=lambda e: -(stage.get(e['anchorId'], 5) - stage.get(e['prerequisiteId'], 5)))
    for e in edges:
        A, P = e['anchorId'], e['prerequisiteId']
        if stage.get(P, 5) > stage.get(A, 5):
            drop_stage += 1
            continue
        if reaches(P, A):
            drop_cycle += 1
            continue
        adj[A].add(P)
        kept.append(e)
    dropped = drop_stage + drop_cycle

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, 'w', encoding='utf-8') as f:
        for e in kept:
            f.write(json.dumps(e, ensure_ascii=False) + '\n')
    deg = collections.Counter(e['anchorId'] for e in kept)
    print(f"\n用时 {time.time()-t0:.0f}s · 调用失败 {errs}")
    print(f"边 {len(kept)} 条（原始 {len(raw)}，去重后 {len(edges)}；"
          f"学段倒挂丢 {drop_stage}，成环丢 {drop_cycle}）→ {a.out}")
    print(f"  有前置的锚点 {len(deg)}/{len(anchors)} = {len(deg)/max(1,len(anchors)):.0%}"
          f"，平均入度 {len(kept)/max(1,len(deg)):.1f}")


if __name__ == '__main__':
    main()
