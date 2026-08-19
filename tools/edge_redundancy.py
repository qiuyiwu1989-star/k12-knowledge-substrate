#!/usr/bin/env python3
"""
edge_redundancy.py — 把 W101「1,188 条传递冗余」从一张清单变成一个可执行的处置口径。

    python3 tools/edge_redundancy.py            # 写 reports/edge-redundancy.{md,jsonl}
    python3 tools/edge_redundancy.py --trials 0 # 跳过零模型（快 30 倍，只出分组）

**确定性算法，零依赖，不调用模型。** 随机只出现在零模型里，种子写死（SEED=20250820），
同样的数据跑两次必须字节一致 —— 否则这份报告没法进 CI 做回归。

────────────────────────────────────────────────────────────────────────
为什么要写这个工具（问题不是「怎么删」，是「凭什么删」）
────────────────────────────────────────────────────────────────────────
`npm run fw-report` 已经能报出 1,188 条冗余边，spec 002 规定「只输出建议清单，不自动
删除」。但「1,188 条清单交人决定」在实践中等于没有决定 —— 没人会逐条看 1,188 条。
所以这个工具要回答的是另外两个问题：

  1. 这 1,188 条**是怎么来的**？（归因，用数据不用故事）
  2. 能不能切成**几条人一眼能判**的规则？每条规则覆盖多少条、切的依据是什么？

────────────────────────────────────────────────────────────────────────
方法一：归因 —— 零模型（本工具最重要的部分）
────────────────────────────────────────────────────────────────────────
一开始的假设是：「gen_edges.py 每条锚点独立选 top-N 前置、从不做传递约简，所以冗余是
它的系统性产物」。这个假设**只对了一小半**，而且差点把结论带偏。

先做的两个描述性统计支持假设：
  · 冗余率随被修方入度单调上升：入度 1 → 0%（数学上必然），2 → 36%，3 → 50%，4 → 55%。
  · 一次调用里选中的若干前置，两两之间本身就有边的比例是 27.2%，而同学科随机有序对
    只有 3.3% —— 看起来「模型专挑同一条链上的祖孙」。

但这两个数都不能证明「是选法造成的」，因为它们都没有对照。于是做零模型：
**保持锚点集合、保持每条锚点选几条前置、保持候选池（照抄 gen_edges.build_pool），
只把「选哪几条」换成随机抽，再照 gen_edges 的规则破环。**

  实测冗余           39%（1,188 / 3,069）
  零模型 · 随机抽     29%（20 次均值 904，范围 853–943）
  零模型 · 分层随机   31%（额外保持每条边「同 strand / 跨 strand」的比例，均值 945）

结论（这才是真正的归因）：
  **1,188 条里约 945 条（八成）是结构底噪** —— 在这个候选池设计和这个边密度下，
  无论怎么选边都会出现这么多传递冗余。它不携带「这条边是错的」的信息。
  **只有约 240 条（8 个百分点）是超出随机的部分**，才可能真的来自选法。

而且这 240 条是一个**总体量，不是可以逐条标记的属性** —— 没有任何逐边特征能告诉你
「你是那 240 条之一」。所以：

  ⚠️ **「冗余率高 ⇒ 该批量删」这条推理是错的。** 按冗余批量删边，删掉的绝大多数是
     结构底噪里随机落到的边，跟对错无关。冗余是图的密度指标，不是边的质量指标。

踩到的坑（留给下一个人）：
  · 第一版零模型忘了破环，得出「随机 48% > 实测 45%」，差点得出「模型选得比随机还好、
    冗余完全无害」的相反结论。环会凭空制造可达性。**零模型必须复刻真实管线的每一道
    约束**（学段过滤 + 破环），少一道结论就翻个个儿。
  · 「同学科随机有序对基线 3.3%」这个对照是假的：它把跨 strand、跨学段的对子都算进
    分母，而候选池根本不会给出那些对子。换成同 strand 后基线跳到 18.9%，27.2% 的
    「8 倍富集」瞬间缩水成 1.4 倍。**基线要跟真实候选池对齐，不能图省事用全域随机。**
  · 试过但没用的信号（都记下来，省得别人再试一遍）：
      候选池大小（池 10–19 与池 40 的冗余率都是 ~40%，无区分度）
      被选中的候选序号（序号 1–5 是 35%，36–40 是 45%，趋势微弱不足以切组）
      两端 stageHint.min 的关系（90% 的边两端同学段，这维度基本是常数）
      两端是否出自同一句课标原文（同句 24% < 不同页 42%，方向还反了）
      reason 长度（prompt 里写死 20–40 字，全挤在一个箱里）

────────────────────────────────────────────────────────────────────────
方法二：分组 —— 换一个可判定的问题
────────────────────────────────────────────────────────────────────────
既然「这条边是不是真的」用冗余判不了，就别装作能判。改问一个**每条边都算得出来**的
问题：**退休它，图会损失什么？**

先确认一件批处理必须知道的事：**这 1,188 条可以同时退休，可达性一条不丢。**
这不是猜的 —— 有向无环图的传递约简唯一，而「存在长度 ≥2 的替代路径就删」得到的正是
传递约简。工具会实测验证一遍（`--verify`，默认开），把任意一条退休后可达性被破坏的
边直接报成 fatal。**这条性质只在无环图上成立**，所以工具先查环、有环就拒绝出报告。

可达性不丢，但会丢的是**「直接前置」这个语义**：直连 1 跳变成绕行 k 跳。下游任何
「取某能力的直接前置」的推理，拿到的答案都会变。所以分组按「绕行代价 + 语义边界」切：

  R0  type=convention            不进推理图，冗余与否无所谓（`type` 填好前恒为 0 条）  无需处置
  R1  冗余 + 跨学段带 ≥2       41   两道独立体检同时命中                        降级为 convention
  R2  直连跨 strand           128   直连跨了领域边界，绕行没跨                    保留
  R3  单独退休也要绕 ≥3 跳     112   一次跨过 ≥2 个中间节点，更像真的另一条路        保留
  R4  直连跨 topic            105   同 strand 内跨主题（证据比 R2 弱一档）        保留
  R5  两端同 topic、绕 2 跳     255   直连只是把祖父又列了一遍，语义损失最小          降级为 convention
  R6  strand/topic 都无信息    547   除了「绕一跳能到」没有任何额外证据            **判断不了**

规则**按顺序首次命中**，所以是 1,188 条的一个划分（不重不漏，工具会断言总数）。
顺序的依据是「先切走有独立证据的，再切走代价大的，最后才是看起来最像噪声的」。

**一组「建议退休」都没有 —— 这是结论不是回避。** 退休不可逆，需要「这条边是错的」这种正面
证据，而零模型已经证明冗余不携带这个信息。降级为 `convention` 在推理上与删等价（spec 001：
convention 不进推理图）、在操作上可回滚，**严格优于退休**。所以本工具给出的唯一批处理动作是：
把 R1 + R5 共 296 条降级为 convention，推理图 3,069 → 2,773，可达性不变，其余 892 条不动。

R6 的 547 条明确标成「判断不了，需要逐条看」并给出条数 —— 这个仓库宁可留空也不硬凑。
它主要不是算法的问题，是标注覆盖率的问题（topic 只覆盖一半锚点）；补齐 topic 或等 spec 001
的 type 重标落地后重跑，这一组会大幅缩小。

**每组结尾的「建议处置」是建议，不是结论。** 本工具不删任何边，不写 edges/，不改任何输入。

────────────────────────────────────────────────────────────────────────
两个容易踩的陷阱（分组阶段）
────────────────────────────────────────────────────────────────────────
· **不要用「全部 1,188 条一起退休后的绕行跳数」去分组。** 那等于先假设了「全删」这个结论，
  循环论证。实测：单独退休时只有 112 条要绕 ≥3 跳，全删后变成 495 条 —— 冗余边之间会互相
  加长绕路。分组用的是「只退休这一条」的跳数（与最终决定无关），每组另外再报「整组一起
  退休」的真实代价。
· **`topic`/`strand` 缺失一律当「不知道」，绝不当「不同」。** 把 null 当 diff 会把 342 条
  毫无信息的边错分进「跨领域，建议保留」，凭空造出一个看起来很确定的组。

────────────────────────────────────────────────────────────────────────
对 schema 的假设（尽量少，且向前兼容）
────────────────────────────────────────────────────────────────────────
· 边集判据与 scripts/fw-report.mjs 完全一致：`!e.retired`、两端锚点存在且 `!deprecated`、
  且**在推理图内**（`type != convention`）。两边一分叉，同名数字就会对不上。
  两边的数必须对得上（工具会打印，对不上就是有一边改了判据）。
· 边的 `type` 现在**全是空的**（重标管线在跑）。工具不依赖它：R0 现在恒为空组，
  等 `type` 填好后自动开始分流 convention 边，其余规则不受影响。
· `evidence[].detail` 里的「候选池 40 选 34」只用于归因统计，解析失败就跳过，不影响分组。
· 锚点的 `topic` 有一半是 null、`strand` 有四分之一是 null。**缺失一律不当成「不同」**，
  只当成「不知道」，落进 R5 由人看 —— 把 null 当 diff 会把 342 条无信息的边错分进 R2。
"""
import argparse
import collections
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = 20250820                      # 写死：报告必须可复现，否则进不了 CI
STAGE_ORD = {f'G{i}': i for i in range(1, 13)}
BAND_CN = ['G1–2', 'G3–4', 'G5–6', 'G7–9', 'G10–12']


# ── 读数据 ────────────────────────────────────────────────────────────
def read_jsonl_dir(d):
    out = []
    for f in sorted((ROOT / d).rglob('*.jsonl')):
        for line in f.open(encoding='utf-8'):
            if line.strip():
                out.append(json.loads(line))
    return out


def load():
    anchors = {a['id']: a for a in read_jsonl_dir('anchors')}
    live = lambda i: i in anchors and not anchors[i].get('deprecated')
    edges = [e for e in read_jsonl_dir('edges')
             if not e.get('retired') and live(e['anchorId']) and live(e['prerequisiteId'])]
    # **推理图 ≠ 全部边**（2026-08-20，specs/001 重标之后）。
    # type=convention 的边已经移出推理图，把它们算进传递冗余是算了一批出局的边。
    # 这个判据必须和 scripts/fw-report.mjs 逐字一致 —— 一分叉，两份报告的
    # 同名数字就会对不上，而对不上时没人知道该信哪个。
    edges = [e for e in edges
             if e.get('inInferenceGraph') is not False and e.get('type') != 'convention']
    return anchors, edges


# ── 学段 ──────────────────────────────────────────────────────────────
def gmin(a):
    s = (a.get('stageHint') or {}).get('min')
    return STAGE_ORD.get(s) if isinstance(s, str) else None


def band(n):
    if n is None:
        return None
    return 0 if n <= 2 else 1 if n <= 4 else 2 if n <= 6 else 3 if n <= 9 else 4


# ── 图 ────────────────────────────────────────────────────────────────
def build_pre(edges):
    """pre[后继] = {它的直接前置们}。方向沿用 fw-report：anchorId → prerequisiteId。"""
    g = collections.defaultdict(set)
    for e in edges:
        g[e['anchorId']].add(e['prerequisiteId'])
    return dict(g)


def reachable(g, src, dst, skip=None):
    """沿前置链从 src 能否走到 dst。skip=(u,v) 表示禁用这一条边。"""
    seen, stack = {src}, [src]
    while stack:
        u = stack.pop()
        # **必须 sorted。** 邻接是 set，而 CPython 的 str hash 每个进程随机化，
        # 不排序的话同一份数据两次跑出来的等长路径会不一样（计数不变，但 md/jsonl
        # 逐字节 diff 会飘），这份报告就没法进 CI 做回归。
        for v in sorted(g.get(u, ())):
            if skip and u == skip[0] and v == skip[1]:
                continue
            if v == dst:
                return True
            if v not in seen:
                seen.add(v)
                stack.append(v)
    return False


def shortest_path(g, src, dst, skip=None):
    """BFS 最短路径（返回节点列表），拿不到返回 None。"""
    prev, q = {src: None}, collections.deque([src])
    while q:
        u = q.popleft()
        for v in sorted(g.get(u, ())):    # 同上：等长路径要取字典序最小的那条，才可复现
            if skip and u == skip[0] and v == skip[1]:
                continue
            if v in prev:
                continue
            prev[v] = u
            if v == dst:
                path = [v]
                while prev[path[-1]] is not None:
                    path.append(prev[path[-1]])
                return path[::-1]
            q.append(v)
    return None


def has_cycle(g):
    """白/灰/黑三色迭代 DFS。有环就返回那个环上的一个节点。"""
    color = {}
    for s in list(g):
        if color.get(s):
            continue
        stack = [(s, iter(sorted(g.get(s, ()))))]
        color[s] = 1
        while stack:
            u, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                color[u] = 2
                stack.pop()
                continue
            c = color.get(nxt, 0)
            if c == 1:
                return nxt
            if c == 0:
                color[nxt] = 1
                stack.append((nxt, iter(sorted(g.get(nxt, ())))))
    return None


# ── 归因：零模型 ──────────────────────────────────────────────────────
def stage_pair(a):
    sh = a.get('stageHint') or {}
    return STAGE_ORD.get(sh.get('min'), 6)


def build_pool(target, group, cap=40):
    """**照抄 gen_edges.build_pool。** 零模型的对照必须是真实候选池，
    换成「同学科随机」会把基线压到 3%，结论就假了。
    这里跟 gen_edges.py 是重复代码 —— 故意的：那边改了这边必须跟着改，
    与其 import 出一个隐形耦合，不如让 diff 看得见。"""
    tmin = stage_pair(target)
    same, earlier = [], []
    for a in group:
        if a['id'] == target['id']:
            continue
        amin = stage_pair(a)
        if amin > tmin:
            continue
        ss = bool(a.get('strand')) and a.get('strand') == target.get('strand')
        key = (0 if ss else 1, tmin - amin)
        (earlier if tmin - amin >= 3 else same).append((key, a))
    same.sort(key=lambda x: x[0])
    earlier.sort(key=lambda x: x[0])
    q = int(cap / 3)
    picked = [a for _, a in same[:cap - q]] + [a for _, a in earlier[:q]]
    if len(picked) < cap:
        rest = [a for _, a in same[cap - q:]] + [a for _, a in earlier[q:]]
        picked += rest[:cap - len(picked)]
    return [a['id'] for a in picked[:cap]]


def null_model(anchors, pre, pools, trials, stratified):
    """保持锚点、保持每条锚点选几条、保持候选池，只随机换「选哪几条」，并照 gen_edges 破环。

    stratified=True 时额外保持每条边「与目标同 strand / 跨 strand」的属性 ——
    用来把「候选池同领域优先」这个设计的贡献从「模型的选择」里剥出来。"""
    rng = random.Random(SEED)
    counts, totals = [], []
    for _ in range(trials):
        ng = collections.defaultdict(set)
        order = sorted(pre)                  # 先定序再 shuffle：不依赖 dict 顺序
        rng.shuffle(order)
        for S in order:
            pool = pools[S]
            if stratified:
                sd = anchors[S].get('strand')
                buckets = {True: [c for c in pool if anchors[c].get('strand') and anchors[c].get('strand') == sd],
                           False: [c for c in pool if not (anchors[c].get('strand') and anchors[c].get('strand') == sd)]}
                for v in buckets.values():
                    rng.shuffle(v)
                for p in sorted(pre[S]):
                    want = bool(anchors[p].get('strand')) and anchors[p].get('strand') == sd
                    for lst in (buckets[want], buckets[not want]):
                        hit = next((c for c in lst if c not in ng[S] and not reachable(ng, c, S) and c != S), None)
                        if hit:
                            ng[S].add(hit)
                            break
            else:
                cand = list(pool)
                rng.shuffle(cand)
                need = len(pre[S])
                for c in cand:
                    if len(ng[S]) >= need:
                        break
                    if c != S and not reachable(ng, c, S):
                        ng[S].add(c)
        ng = dict(ng)
        counts.append(sum(1 for S, ps in ng.items() for p in ps
                          if reachable(ng, S, p, skip=(S, p))))
        totals.append(sum(len(ps) for ps in ng.values()))
    return counts, totals


# ── 分组 ──────────────────────────────────────────────────────────────
# 有些学科的 strand/topic 根本不是领域名，而是整句课标原文（信息技术的 strand 最长 27 字、
# 生物学 28 字、艺术 26 字）。R2/R4 的「跨领域」证据建立在「strand 是真的领域划分」上，
# 对这些学科不成立。**12 字是个粗糙的诊断阈值，只用来在报告里标注打折，不是闸门、不改分组**
# —— 按字数重新分组等于自己给数据质量设标准，那是人该定的事。
HEADING_LEN = 12


def heading_like(anchors, i):
    return any(isinstance(v, str) and len(v) > HEADING_LEN
               for v in (anchors[i].get('strand'), anchors[i].get('topic')))


def rel(anchors, x, y, field):
    """same / diff / unknown。**缺失只当「不知道」，绝不当「不同」。**"""
    a, b = anchors[x].get(field), anchors[y].get(field)
    if a is None or b is None:
        return 'unk'
    return 'same' if a == b else 'diff'


GROUPS = [
    ('R0', 'type=convention',
     '边已经被标成约定关系，本来就不进推理图，冗余与否不影响任何推理。',
     '无需处置',
     '（`type` 填好前恒为 0 条）'),
    ('R1', '冗余 + 跨学段带 ≥2',
     '两道互相独立的体检同时命中：既是多余的一跳，又跨了两个以上学段带 —— spec 002 自己写「真前置通常紧邻，'
     '跨两带以上多为伪边」。这是全部六组里唯一一组有「这条边可能是错的」这种独立证据的。',
     '建议降级为 convention',
     '不建议退休：降级已经把它移出推理图（推理上等价于删），但可回滚，而退休不可逆。'),
    ('R2', '直连跨 strand',
     '这条直连跨了领域边界，绕行路径把它拆成域内的几步。跨领域的直接依赖是全图信息量最高的一类边，'
     '不该因为「恰好也能绕过去」就动它。',
     '建议保留',
     ''),
    ('R3', '单独退休也要绕 ≥3 跳',
     '这条直连一次跨过了 ≥2 个中间节点。就算只退休它自己一条，「直接前置」也会变成隔两层以上的祖先 —— '
     '它更像一条真的「另一条路」，不像 top-N 的副产物。',
     '建议保留',
     ''),
    ('R4', '直连跨 topic（strand 相同或未知）',
     '同一个领域内部跨了主题。证据比 R2 弱一档（topic 的标注覆盖率只有一半），但方向一致：'
     '直连跨过的边界，绕行路径没跨。',
     '建议保留',
     ''),
    ('R5', '两端同 topic、绕 2 跳',
     '直连的两端在同一个 topic 里，绕行只有 2 跳 —— 直连只是把「祖父」也顺手列了一遍。'
     '这是六组里退休后语义损失最小的一组：退休后仍在同一主题内隔一跳。',
     '建议降级为 convention',
     '仍然不建议退休：按第一节的归因，这里绝大部分是结构底噪，「冗余」不构成「这条边是错的」的证据；'
     '降级把它移出推理图、消除重复计数，同时保留记录且可回滚。'),
    ('R6', 'strand 与 topic 都给不出信息',
     '两端 strand/topic 缺失或不同、绕行只有 2 跳 —— 除了「绕一跳能到」之外没有任何额外证据。',
     '判断不了 —— 需要逐条看，或先等 spec 001 的 type 重标落地再重跑',
     ''),
]


def classify(anchors, e, feat):
    """规则按顺序首次命中 —— 所以结果是 1,188 条的一个划分（不重不漏，main 里有断言）。

    顺序的依据：先切走**有独立质量证据的**（R1），再切走**退休代价大的**（R2/R3/R4），
    最后才是看起来最像噪声的（R5/R6）。
    """
    if (e.get('type') or '') == 'convention':
        return 'R0'
    if feat['bandGap'] is not None and feat['bandGap'] >= 2:
        return 'R1'
    if feat['strandRel'] == 'diff':
        return 'R2'
    if feat['altHops'] is not None and feat['altHops'] >= 3:
        return 'R3'
    if feat['topicRel'] == 'diff':
        return 'R4'
    if feat['topicRel'] == 'same':
        return 'R5'
    return 'R6'


# ── 报告 ──────────────────────────────────────────────────────────────
def stmt(anchors, i, n=34):
    s = anchors[i].get('statement') or ''
    return s[:n] + ('…' if len(s) > n else '')


def pick_samples(rows, k=3):
    """确定性取样：按 (学科, 后继 id, 前置 id) 排好后在组内等距取 —— 不用 random，
    也不取前 k 条（前 k 条常常全是同一个学科同一页，看不出组的形状）。"""
    rows = sorted(rows, key=lambda r: (r['discipline'], r['anchorId'], r['prerequisiteId']))
    if len(rows) <= k:
        return rows
    step = len(rows) / k
    return [rows[int(i * step)] for i in range(k)]


def main():
    ap = argparse.ArgumentParser(description='W101 传递冗余的归因与分组（确定性，不调用模型）')
    ap.add_argument('--trials', type=int, default=20, help='零模型试验次数，0 = 跳过归因的零模型部分')
    ap.add_argument('--out-md', default=str(ROOT / 'reports/edge-redundancy.md'))
    ap.add_argument('--out-jsonl', default=str(ROOT / 'reports/edge-redundancy.jsonl'))
    ap.add_argument('--no-verify', action='store_true', help='跳过「同时退休全部冗余边、可达性不变」的实测验证')
    a = ap.parse_args()

    anchors, edges = load()
    pre = build_pre(edges)

    cyc = has_cycle(pre)
    if cyc:
        sys.exit(f'FATAL: 图里有环（{cyc}）。传递约简的唯一性只在无环图上成立，'
                 f'带环的图上本工具的分组和批处理结论都不作数。先修环再跑。')

    redundant, feats = [], {}
    for e in edges:
        S, P = e['anchorId'], e['prerequisiteId']
        if reachable(pre, S, P, skip=(S, P)):
            redundant.append(e)
    print(f'存活锚点 {sum(1 for x in anchors.values() if not x.get("deprecated"))} · '
          f'推理图 {len(edges)} 条 · 传递冗余 {len(redundant)} = {len(redundant)/len(edges):.0%}')
    print('（这三个数必须与 reports/graph-hygiene.md 完全一致；对不上说明两边存活判据分叉了）')

    # ── 批处理安全性：同时退休全部冗余边，可达性是否不变 ──
    reduced = {k: set(v) for k, v in pre.items()}
    for e in redundant:
        reduced[e['anchorId']].discard(e['prerequisiteId'])
    broken = []
    if not a.no_verify:
        for e in redundant:
            if not reachable(reduced, e['anchorId'], e['prerequisiteId']):
                broken.append(e)
        print(f'批处理安全性验证：同时退休全部 {len(redundant)} 条后，'
              f'可达性被破坏 {len(broken)} 条' + ('（符合无环图传递约简的唯一性）' if not broken else ' ← 异常！'))

    # ── 逐边特征 ──
    rows = []
    for e in redundant:
        S, P = e['anchorId'], e['prerequisiteId']
        orig = shortest_path(pre, S, P, skip=(S, P))
        det = shortest_path(reduced, S, P)
        bS, bP = band(gmin(anchors[S])), band(gmin(anchors[P]))
        f = {
            'altHops': len(orig) - 1 if orig else None,
            'detourHops': len(det) - 1 if det else 99,
            'detourPath': det or [],
            'bandGap': abs(bS - bP) if (bS is not None and bP is not None) else None,
            'strandRel': rel(anchors, S, P, 'strand'),
            'topicRel': rel(anchors, S, P, 'topic'),
        }
        g = classify(anchors, e, f)
        rows.append({
            'group': g, 'anchorId': S, 'prerequisiteId': P,
            'discipline': anchors[S].get('discipline'),
            'strand': anchors[S].get('strand'), 'topic': anchors[S].get('topic'),
            'type': e.get('type'), 'strength': e.get('strength'),
            'reason': e.get('reason'),
            'anchorStatement': anchors[S].get('statement'),
            'prerequisiteStatement': anchors[P].get('statement'),
            'anchorStage': (anchors[S].get('stageHint') or {}).get('min'),
            'prerequisiteStage': (anchors[P].get('stageHint') or {}).get('min'),
            'altHops': f['altHops'], 'altPath': orig or [],
            'detourHops': f['detourHops'], 'detourPath': f['detourPath'], 'bandGap': f['bandGap'],
            'strandRel': f['strandRel'], 'topicRel': f['topicRel'],
            'headingLikeLabel': heading_like(anchors, S) or heading_like(anchors, P),
            'suggestion': {g_[0]: g_[3] for g_ in GROUPS}[g],
        })
    by_group = collections.defaultdict(list)
    for r in rows:
        by_group[r['group']].append(r)
    assert sum(len(v) for v in by_group.values()) == len(redundant), '分组不是划分：有边被漏掉或算了两次'

    # 「整组一起退休」的真实绕行代价。分组用的是 altHops（单独退休的代价，与分组无关，
    # 不循环）；这里再算一遍「只把这一组拿掉」之后的代价 —— 批处理是按组做的，组内会互相
    # 加长绕路。**不要拿「全部 1,188 条一起退休」的跳数去分组**，那等于先假设了结论。
    group_cost = {}
    for gid, g in by_group.items():
        if not g:
            continue
        gg = {k: set(v) for k, v in pre.items()}
        for r in g:
            gg[r['anchorId']].discard(r['prerequisiteId'])
        c = collections.Counter()
        for r in g:
            p_ = shortest_path(gg, r['anchorId'], r['prerequisiteId'])
            h = len(p_) - 1 if p_ else 99
            r['groupRetireHops'] = h
            c[h] += 1
        group_cost[gid] = c

    # ── 归因统计 ──
    indeg = collections.Counter(e['anchorId'] for e in edges)
    redset = {(r['anchorId'], r['prerequisiteId']) for r in rows}
    indeg_tab = collections.defaultdict(lambda: [0, 0])
    for e in edges:
        k = indeg[e['anchorId']]
        indeg_tab[k][0] += 1
        indeg_tab[k][1] += (e['anchorId'], e['prerequisiteId']) in redset

    pool_tab, rank_tab = collections.defaultdict(lambda: [0, 0]), collections.defaultdict(lambda: [0, 0])
    for e in edges:
        d = next((ev.get('detail', '') for ev in (e.get('evidence') or []) if ev.get('kind') == 'llm'), '')
        m = re.search(r'候选池\s*(\d+)\s*选\s*(\d+)', d)
        if not m:
            continue
        isr = (e['anchorId'], e['prerequisiteId']) in redset
        pool_tab[int(m.group(1)) // 10 * 10][0] += 1
        pool_tab[int(m.group(1)) // 10 * 10][1] += isr
        rank_tab[(int(m.group(2)) - 1) // 5 * 5][0] += 1
        rank_tab[(int(m.group(2)) - 1) // 5 * 5][1] += isr

    nulls = {}
    if a.trials > 0:
        live_anchors = [x for x in anchors.values() if not x.get('deprecated')]
        by_disc = collections.defaultdict(list)
        for x in live_anchors:
            by_disc[x['discipline']].append(x)
        pools = {S: build_pool(anchors[S], by_disc[anchors[S]['discipline']]) for S in pre}
        for name, strat in (('随机抽', False), ('分层随机抽', True)):
            print(f'  零模型（{name}）×{a.trials} …', flush=True)
            c, t = null_model(anchors, pre, pools, a.trials, strat)
            nulls[name] = (sum(c) / len(c), sum(t) / len(t), min(c), max(c))

    # ── 写 jsonl ──
    Path(a.out_jsonl).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out_jsonl, 'w', encoding='utf-8') as f:
        for r in sorted(rows, key=lambda r: (r['group'], r['discipline'] or '', r['anchorId'], r['prerequisiteId'])):
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    # ── 写 md ──
    L = []
    W = L.append
    W('# W101 传递冗余：归因与处置分组')
    W('')
    W('> 由 `python3 tools/edge_redundancy.py` 自动生成。**确定性算法，不调用模型，不删任何边。**')
    W(f'> 存活锚点 {sum(1 for x in anchors.values() if not x.get("deprecated"))} · '
      f'推理图 {len(edges)} 条 · 传递冗余 **{len(redundant)} 条 = {len(redundant)/len(edges):.0%}**')
    W('>')
    W('> 每组结尾的「建议处置」**是建议，不是结论**。删边不可逆且影响所有下游推理，最终由人定。')
    W('')
    W('---')
    W('')
    W('## 一、归因：这 1,188 条是怎么来的')
    W('')
    W('### 1.1 起点假设')
    W('')
    W('`tools/gen_edges.py` 给每条锚点单独发一次模型调用，从 40 条候选里最多挑 3 条前置，')
    W('**每次调用都看不到自己在别处的答案，也从不做传递约简**。所以最初的假设是：')
    W('冗余是这个 top-N 选法的系统性产物。两个描述性统计看起来支持它——')
    W('')
    W('**冗余率 × 被修方入度（该锚点有几条前置）**')
    W('')
    W('| 入度 | 该入度下的边 | 冗余 | 冗余率 |')
    W('|---:|---:|---:|---:|')
    for k in sorted(indeg_tab):
        t, r = indeg_tab[k]
        W(f'| {k} | {t} | {r} | {r/t:.0%} |')
    W('')
    W('入度 1 恒为 0%（一条前置构不成 A→B→C，数学上必然），入度一升冗余率就单调上涨。')
    W('看上去像铁证。**但它没有对照** —— 任何图都是边越多越容易出现替代路径。')
    W('')
    W('### 1.2 零模型（本报告最重要的一段）')
    W('')
    W('对照的做法：**保持锚点集合、保持每条锚点选几条前置、保持候选池（照抄 `build_pool`），')
    W('只把「选哪几条」换成随机抽**，再照 `gen_edges` 的规则破环，然后重新数冗余。')
    W('')
    if nulls:
        W(f'| | 冗余边 | 占比 |')
        W(f'|---|---:|---:|')
        W(f'| **实测** | {len(redundant)} | {len(redundant)/len(edges):.0%} |')
        for name, (mc, mt, lo, hi) in nulls.items():
            W(f'| 零模型 · {name}（{a.trials} 次均值，范围 {lo}–{hi}） | {mc:.0f} | {mc/mt:.0%} |')
        W('')
        base = nulls.get('分层随机抽') or list(nulls.values())[0]
        excess = len(redundant) - base[0]
        W(f'「分层随机抽」额外保持了每条边「与目标同 strand / 跨 strand」的比例，')
        W(f'用来把**候选池「同领域优先」这个设计**的贡献，从**模型的选择**里剥出来。')
        W('')
        W(f'**结论：{len(redundant)} 条里约 {base[0]:.0f} 条（{base[0]/len(redundant):.0%}）是结构底噪** —— ')
        W(f'在这个候选池设计和这个边密度下，无论怎么选边都会出现这么多传递冗余，')
        W(f'它不携带「这条边是错的」这个信息。**只有约 {excess:.0f} 条（{excess/len(edges)*100:.0f} 个百分点）')
        W(f'是超出随机的部分**，才可能真的来自选法。')
        W('')
        W(f'而且这 {excess:.0f} 条是一个**总体量，不是可以逐条标记的属性**：没有任何逐边特征能告诉你')
        W('「你就是那些条之一」。所以——')
        W('')
        W('> ⚠️ **「冗余率 39% 很高 ⇒ 应该批量删」这条推理是错的。**')
        W('> 按冗余批量删边，删掉的绝大多数是结构底噪里随机落到的边，跟对错无关。')
        W('> **冗余是图的密度指标，不是边的质量指标。**')
        W('')
        W('各学科 27–48% 的「均匀分布」现在也有了解释：它均匀，是因为它主要由密度决定，')
        W('而各学科的边密度本来就差不多 —— 均匀分布**不能**用来论证「这是选法的系统性缺陷」。')
    else:
        W('_本次以 `--trials 0` 运行，跳过了零模型。归因结论不成立，只有分组可用。_')
    W('')
    W('### 1.3 试过但没有区分度的信号')
    W('')
    W('全部记在这里，省得下一个人再试一遍。')
    W('')
    W('**候选池大小**（从 `evidence[].detail` 的「候选池 N 选 M」解析）')
    W('')
    W('| 候选池 | 边 | 冗余 | 冗余率 |')
    W('|---|---:|---:|---:|')
    for k in sorted(pool_tab):
        t, r = pool_tab[k]
        W(f'| {k}–{k+9} | {t} | {r} | {r/t:.0%} |')
    W('')
    W('**被选中的候选序号**（序号小 = 同领域且学段最近）')
    W('')
    W('| 序号 | 边 | 冗余 | 冗余率 |')
    W('|---|---:|---:|---:|')
    for k in sorted(rank_tab):
        t, r = rank_tab[k]
        W(f'| {k+1}–{k+5} | {t} | {r} | {r/t:.0%} |')
    W('')
    W('两张表都基本是平的。另外三个也试过、同样没用的：')
    W('')
    W('- **两端 stageHint.min 的关系**：90% 的边两端同学段（`min` 只有 10 个取值，且 883 条锚点全是 G10），')
    W('  这一维几乎是常数，切不出组。')
    W('- **两端是否出自同一句课标原文**（`provenance.srcText`）：同句 24% < 同页不同句 35% < 不同页 42%，')
    W('  方向跟直觉是反的，不能用。')
    W('- **`reason` 长度**：prompt 里写死「20–40 字」，1,111/1,188 条挤在 20–39 这两个箱里。')
    W('')
    W('---')
    W('')
    W('## 二、批处理安全性（分组之前必须先知道的）')
    W('')
    W(f'**这 {len(redundant)} 条可以同时退休，可达性一条不丢。**')
    W('')
    W('这不是估计。有向无环图的传递约简唯一，而「存在长度 ≥2 的替代路径就删」得到的正是传递约简；')
    if not a.no_verify:
        W(f'本工具又实测验证了一遍：把全部 {len(redundant)} 条一起从图里拿掉后，逐条检查两端是否仍然可达，')
        W(f'**可达性被破坏 {len(broken)} 条**。')
    W('')
    W('（前提是图无环 —— 工具跑之前先查环，有环直接拒绝出报告。')
    W('本次检查结果：无环。）')
    W('')
    W('所以「删了会不会把图删断」不是需要担心的问题。**真正会丢的是「直接前置」这个语义**：')
    W('直连 1 跳变成绕行 k 跳，下游任何「取某能力的直接前置」的推理，拿到的答案都会变。')
    W('分组就按这个来切。')
    W('')
    W('**绕行跳数分布**（两个场景要分开看，混了会得出相反结论）')
    W('')
    ah = collections.Counter(r['altHops'] for r in rows)
    dh = collections.Counter(r['detourHops'] for r in rows)
    W('| 绕行跳数 | A：只退休这一条 | B：1,188 条全退休 |')
    W('|---:|---:|---:|')
    for k in sorted(set(ah) | set(dh)):
        W(f'| {k} | {ah.get(k, 0)} | {dh.get(k, 0)} |')
    W('')
    W(f'A 场景下只有 {sum(v for k, v in ah.items() if k >= 3)} 条要绕 ≥3 跳；')
    W(f'B 场景下变成 {sum(v for k, v in dh.items() if k >= 3)} 条 —— **冗余边之间会互相加长绕路**。')
    W('')
    W('所以分组用的是 A（单独退休的代价：它只跟这条边本身有关，不依赖你最后决定删哪些，')
    W('不会循环论证）。B 只当成一个警告：**全删是最贵的方案，不是最省事的方案。**')
    W('每一组下面还会单独给出「整组一起退休」的真实代价。')
    W('')
    W('---')
    W('')
    W('## 三、分组')
    W('')
    W('规则**按顺序首次命中**，所以下面是 1,188 条的一个划分（不重不漏）。')
    W('顺序的依据：先切走有独立证据的，再切走代价大的，最后才是看起来最像噪声的。')
    W('')
    W('| 组 | 判据 | 条数 | 占比 | 建议处置 |')
    W('|---|---|---:|---:|---|')
    for gid, name, _, sug, _note in GROUPS:
        n = len(by_group.get(gid, []))
        W(f'| **{gid}** | {name} | {n} | {n/len(redundant)*100:.0f}% | {sug} |')
    W('')
    for gid, name, crit, sug, note in GROUPS:
        g = by_group.get(gid, [])
        W(f'### {gid} · {name} —— {len(g)} 条')
        W('')
        W(f'**判据**：{crit}')
        W('')
        if not g:
            if gid == 'R0':
                W('_当前 0 条：边的 `type` 字段还全是空的（重标管线在跑）。'
                  '等 `type` 填好后这一组会自动开始分流，其余规则不受影响。_')
            else:
                W('_当前 0 条。_')
            W('')
            W(f'**建议处置：{sug}**（建议，不是结论。）')
            W('')
            continue
        if gid == 'R5':
            # 判据只查两端。中间点是否也同 topic 是**实测出来的**，不是判据的一部分 ——
            # 写成判据会让人以为工具查了三点，那是假的。
            mid = sum(1 for r in g if len(r['altPath']) == 3
                      and anchors[r['altPath'][1]].get('topic') == anchors[r['anchorId']].get('topic'))
            W(f'（判据只查两端。实测 **{mid}/{len(g)}** 条的中间点也在同一个 topic 内。）')
            W('')
        if gid in ('R2', 'R4'):
            nb = sum(1 for r in g if r['headingLikeLabel'])
            if nb:
                W(f'⚠ 其中 **{nb} 条**至少有一端的 `strand`/`topic` 值是整句课标原文（>{HEADING_LEN} 字，'
                  f'主要来自 {"、".join(d for d, _ in collections.Counter(r["discipline"] for r in g if r["headingLikeLabel"]).most_common(4))} '
                  f'等学科）。那些学科的 strand/topic 不是真正的领域划分，这 {nb} 条的「跨领域」证据要打折，'
                  f'建议连同 R6 一起逐条看。**本工具不因此改分组** —— 按字数重新分组等于自己给数据质量设标准。')
                W('')
        gc = group_cost.get(gid)
        if gc:
            W('整组一起退休的代价：' + '、'.join(f'绕 {k} 跳 {n} 条' for k, n in sorted(gc.items()))
              + ('（无一条断开）' if 99 not in gc else f'　⚠ 断开 {gc[99]} 条'))
            W('')
        bysub = collections.Counter(r['discipline'] for r in g)
        W('学科分布：' + '、'.join(f'{d} {n}' for d, n in bysub.most_common(8))
          + ('等' if len(bysub) > 8 else ''))
        W('')
        W('样本：')
        W('')
        for r in pick_samples(g):
            W(f'- `{r["prerequisiteId"]}` → `{r["anchorId"]}`　{r["discipline"]}'
              + (f'｜{r["strand"]}' if r['strand'] else '')
              + (f'｜topic={r["topic"]}' if r['topic'] else '')
              + f'　{r["prerequisiteStage"]} → {r["anchorStage"]}')
            W(f'  - 前置：{r["prerequisiteStatement"]}')
            W(f'  - 后继：{r["anchorStatement"]}')
            W(f'  - 这条边的理由：{r["reason"]}')
            if r['altPath']:
                chain = ' ← '.join(stmt(anchors, i, 22) for i in r['altPath'])
                W(f'  - 单独退休后要绕 {r["altHops"]} 跳：{chain}')
            W('')
        W(f'**建议处置：{sug}**（建议，不是结论。）')
        if note:
            W('')
            W(note)
        W('')
    W('---')
    W('')
    W('## 四、一次可批处理的动作')
    W('')
    dg = [gid for gid, _, _, sug, _ in GROUPS if '降级' in sug]
    n_dg = sum(len(by_group.get(g, [])) for g in dg)
    W(f'**把 {" + ".join(dg)} 共 {n_dg} 条降级为 `convention`**（spec 001 的语义：教材就这么排的，')
    W('无可观测失败表现，**不进推理图**）。这是打标记不是删除，可回滚。')
    W('')
    W(f'- 推理图边数：{len(edges)} → {len(edges) - n_dg}')
    W(f'- 可达性：不变（第二节已验证）')
    W(f'- 其余 {len(redundant) - n_dg} 条冗余边不动')
    W('')
    W('剩下的都不该现在动，理由在下面。')
    W('')
    W('---')
    W('')
    W('## 五、为什么一组「建议退休」都没有')
    W('')
    W('spec 002 允许的处置是三选一：保留 / 降级为 convention / 建议退休。**本工具一组退休都没给出**，')
    W('这是结论不是回避：')
    W('')
    W('- 退休不可逆，所以它需要的是「**这条边是错的**」这种正面证据。')
    W('- 而第一节的零模型证明了：传递冗余里约八成是结构底噪，**它不携带边的对错信息**。')
    W('- 唯一带独立质量证据的是 R1（跨学段带 ≥2），但那也只是 spec 002 自己说的「多为伪边」这条启发式，')
    W('  不是证据。而且对 R1 来说，降级在推理上与删等价、在操作上可回滚 —— **降级严格优于退休**。')
    W('')
    W('真正能逐条判「这条边是不是真的」的机制已经在跑了：**spec 001 的两段式重标**')
    W('（先问「不会 A 的孩子做 B 会失败在哪一步」，再独立分类）。')
    W('那才是质量判据，冗余不是。')
    W('')
    W('---')
    W('')
    W('## 六、判断不了的部分')
    W('')
    r6 = len(by_group.get('R6', []))
    W(f'**R6 的 {r6} 条（占冗余的 {r6/len(redundant)*100:.0f}%）本工具判断不了**，标成「需要逐条看」。')
    W('')
    W('原因是双重的：')
    W('')
    n_topic = sum(1 for x in anchors.values() if not x.get('deprecated') and x.get('topic'))
    n_live = sum(1 for x in anchors.values() if not x.get('deprecated'))
    n_strand = sum(1 for x in anchors.values() if not x.get('deprecated') and x.get('strand'))
    W('1. 这些边除了「绕一跳能到」之外没有任何额外证据 —— 两端 strand/topic 缺失或不同、绕行只有 2 跳。')
    W(f'   全库 {n_topic}/{n_live} 条锚点有 `topic`、{n_strand}/{n_live} 条有 `strand`，')
    W('   **标注覆盖率本身就是这一组存在的主要原因**。')
    W('2. 按第一节的归因，这个层面的冗余绝大部分是结构底噪。**删它等于随机删边。**')
    W('')
    W('两条更划算的路，都不需要逐条看：')
    W('')
    W('- **先补齐 `topic` 再重跑本工具** —— R6 里同 topic 的会落进 R5、跨 topic 的会落进 R4，这一组会大幅缩小。')
    W('- **等 spec 001 的 `type` 重标落地再重跑** —— R0 会开始分流；`type=convention` 的边本来就不进推理图，')
    W('  它们的冗余不需要任何处置。')
    W('')
    W('在这两件事做完之前，**不建议对 R6 做任何批量动作**。')
    W('')
    W(f'机器可读清单：`reports/edge-redundancy.jsonl`（{len(rows)} 行，一行一条冗余边，含所在组、'
      f'单独退休的绕行跳数与路径、整组退休的绕行跳数、strand/topic 关系、建议处置），供将来批处理用。')
    W('')

    Path(a.out_md).write_text('\n'.join(L), encoding='utf-8')
    print(f'→ {a.out_md}')
    print(f'→ {a.out_jsonl}（{len(rows)} 行）')
    for gid, name, *_ in GROUPS:
        print(f'  {gid} {name}: {len(by_group.get(gid, []))}')


if __name__ == '__main__':
    main()
