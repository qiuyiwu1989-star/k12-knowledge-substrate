#!/usr/bin/env python3
"""
mapper.py — 把别人的内容映射到底座的锚点 ID。

## 这是产品的核心，也是最容易做坏的一件

别人拿一节课、一道题、一份教案过来，问「这对应课标哪几条能力」。
底座给候选，**但有一条不可退让的规矩**：

  **映射结果不写回底座。**

别人的标注是别人的判断。混进来，底座就不再是「每条都能翻回教育部文件某一页」，
而那是它唯一的护城河。所以这个工具**只读**锚点，产出留在调用方那边。

## 两段式：字面粗召回 + 模型精排

原本只做了前半截，排序不可信。理由是设计前提错了 ——
我写「锚点用的是课标的词，对方的内容多半也在用同一套术语」，
**那对教研文档成立，对课堂语言不成立**：

    老师写的：用竖式计算 300 减 198，讲退位怎么发生，个位不够减要向十位借
    课标写的：能计算两位数和三位数的加减法
    字面只共享「计算」两个字 —— 真正的对应是 减法≈减、三位数≈个位/十位，那是语义。

为此换过四种切法，每种换来一种新失败（都记在 common_runs 上方）。
最后一种（最长公共子串）解决了噪声，但解决不了「根本没有字面重合」。

所以分两段：

  **粗召回**（离线、零依赖、0.15 秒）—— 最长公共子串，宁可多收。
    实测正确答案基本都在前 60 条里。这一段**不做判断**。
  **精排**（`--rerank`，一次模型调用）—— 把候选连同原文一起给模型，让它挑并排序。

精排只发**一次**调用，不是逐条问：候选池已经把范围收到几十条，
逐条问贵 20 倍而收益有限。代价是**候选池外的漏了就漏了** —— 这是明摆着的取舍，
所以粗召回那一段的门槛故意放得很松。

**模型只能从给定列表里挑，不许自由生成 ID。** 这条抄 gen_edges ——
Marble 的 3,221 条边全是模型自由生成的，结果社区提了
「抗逆力成长依赖 20 以内加减法」这种 issue。返回的 ID 逐个核对，
不在候选池里的当场丢掉并计数。

## 打分

  **IDF 加权重合**              主信号 —— 「计算」出现在 386 条锚点里，
                                「退位」只出现在 3 条，两者的分量差着两个数量级
  × 学科匹配                   不同学科直接排除，不是降权
  × 学段接近                   给了学段就按距离衰减
  + 动词命中                   「计算」对上「计算」比对上「说出」强

**分数只用来排序，不叫置信度。** 叫置信度会让人以为 0.8 有概率含义，它没有。

## 输出

每条候选带：锚点全文、命中的词、为什么排这个名次、**复核成色**。
成色必须给 —— 对方拿一条 `disputed` 的锚点去标注自己的教材，得知道它是存疑的。

    python3 tools/mapper.py --text "用竖式计算 300-198，说明退位发生在哪一位"
    python3 tools/mapper.py --text "…" --discipline 数学 --stage G3 --top 5
    python3 tools/mapper.py --file lesson.txt --json
"""
import argparse, collections, json, math, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from citable import CITABLE, HUMAN_CONFIRMED     # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# 虚词：这些字在任何教育文本里都高频，单独匹上不算信号
STOP = set('的了和与及等对在中是这那有为把被就都也还很更最不没所以其之则而且或者'
           '一二三四五六七八九十个条种些以能会可要能够进行使用通过根据基于结合各'
           '上下前后内外时间地方问题情况方面内容方法过程结果学生老师学习')

# ── 为什么不切词 ───────────────────────────────────────────────────
# 试了三轮切词，每轮暴露下一个问题，而且都是同一个地基上的漏：
#   1. 单字 + 双字滑窗 —— 「计算」同时产出「计」「算」「计算」，一次命中算三遍，
#      把「能借助计算器进行计算」这种又短又泛的断言顶到第一。
#   2. 只留双字 —— 查询与断言常常只共享一个双字词，凑不满门槛，召回 0。
#   3. 双字 + IDF —— 滑窗噪声（「式计」来自「竖式计算」、「算减」来自「计算减法」）
#      **因为罕见反而得了高分**。**罕见 ≠ 有意义**：当 token 本身是切割 artifact 时，
#      IDF 会奖励它。
#
# 中文没有词边界，而这台机器上 jieba / pkuseg / thulac 都没有，
# 底座又是零依赖分发的。所以换地基：**不切词，直接找最长公共子串。**
#
# 中文里「共享一段长子串」本身就等于「共享一个术语」——「三位数」「退位」「加减法」
# 都会作为整段被匹上，而「式计」这种跨词碎片只有 2 字，
# 在按长度平方加权时被真正的长匹配压过去。
# 顺带解决了「为什么是这条」：命中的就是那几段字，原样打给人看。


def common_runs(q, t, minlen=2):
    """q 与 t 的极大公共子串（长度 ≥ minlen）。从长到短找，被更长的段包住的不重复计。"""
    out = {}
    n, m = len(q), len(t)
    for L in range(min(n, m), minlen - 1, -1):
        for i in range(n - L + 1):
            sub = q[i:i + L]
            if sub in t and not any(sub in k for k in out):
                out[sub] = L
    return [(k, v) for k, v in out.items() if not all(c in STOP for c in k)]


G = lambda s: int(s[1:]) if isinstance(s, str) and s.startswith('G') else None


def load():
    out = []
    for f in sorted((ROOT / 'anchors').glob('*.jsonl')):
        for l in f.open(encoding='utf-8'):
            if l.strip():
                a = json.loads(l)
                if not a.get('deprecated'):
                    out.append(a)
    return out


def build_df(anchors):
    """每个 2 字片段出现在多少条锚点里 —— 给命中的段降权用：
    「计算」在几百条里出现，「退位」只在几条，分量不该一样。"""
    df = collections.Counter()
    for a in anchors:
        t = a['statement']
        for w in {t[k:k + 2] for k in range(len(t) - 1)}:
            df[w] += 1
    return df, len(anchors)


def score(q, a, disc, stage, df, n):
    """⚠️ 这个打分**只够粗召回**，排出来的名次不可信，理由见文件头。"""
    if disc and a['discipline'] != disc:
        return None                                  # 不同学科直接排除，不是降权
    runs = common_runs(q, a['statement'])
    if not runs:
        return None
    # **召回优先**：只要有一段非标点的公共子串就收进候选池。
    # 上一版加了「长度 <3 且段数 <2 就丢」的门槛，结果把
    # 「能计算两位数和三位数的加减法」（与查询只共享「计算」）直接丢掉了 ——
    # 而它正是正确答案。粗召回阶段宁可多收，别在这里做判断。
    runs = [(w, L) for w, L in runs if any('一' <= c <= '鿿' for c in w)]
    if not runs:
        return None
    tot = 0.0
    for sub, L in runs:
        rarity = math.log(n / (1 + df.get(sub[:2], 0)))
        tot += L * L * max(0.4, rarity)              # 长度平方：4 字的抵得过四个 2 字的
    s = tot / (len(a['statement']) ** 0.5 + 4)       # 按断言长度归一，长断言别靠体量取胜
    if a.get('verb') and a['verb'] in q:
        s *= 1.3
    if stage:
        sh = a.get('stageHint') or {}
        lo, hi = G(sh.get('min')), G(sh.get('max'))
        if lo:
            d = 0 if lo <= stage <= (hi or lo) else min(abs(stage - lo), abs(stage - (hi or lo)))
            s *= max(0.25, 1 - d * 0.18)
    return s, sorted(runs, key=lambda t: -t[1])


RERANK_SYS = """你在把一段教学内容对应到课标的能力点上。

下面给你一段内容，和一批**候选能力点**（已经按字面相似度粗筛过）。
从候选里挑出**真正对应**的，按对应程度排序。

判据：这段内容如果做完了，能不能作为「这个孩子会了这条能力」的证据？

  ✅ 内容：用竖式计算 300-198，讲退位
     候选：能计算两位数和三位数的加减法        → 对应。这就是在练这条
  ❌ 候选：能借助计算器进行计算                → 不对应。用的是另一种手段
  ❌ 候选：会计算长方形的面积                  → 不对应。只是都含「计算」两个字

规则：
1. **只能从候选里挑，编号必须是给定的那些。** 编不存在的编号 = 整条作废。
2. 挑不出对应的就返回空数组 —— 硬凑一条比不给更糟。
3. 最多挑 6 条。真正对应的通常只有 1–3 条。
4. 每条写一句「为什么对应」，说具体：说清这段内容的哪个动作对上了这条能力的哪个要求。
   ❌ 内容相关       ❌ 都涉及计算
   ✅ 竖式退位减法正是「三位数减法」的具体做法

只输出一行 JSON，不要代码块：
{{"picks":[{{"n":3,"why":"…"}},{{"n":7,"why":"…"}}]}}
{{"picks":[]}}"""


def rerank(q, cands, base, key, model):
    """把候选连同原文一起给模型，让它挑并排序。**一次调用，不是逐条问。**

    返回 (排好的候选列表, 诊断信息)。任何一步出问题都退回粗召回的顺序 ——
    精排失败不该让整个工具不可用。
    """
    import sys as _s
    _s.path.insert(0, str(Path(__file__).resolve().parent))
    from repair import call
    lines = []
    for i, (_, _, x) in enumerate(cands, 1):
        sh = x.get('stageHint') or {}
        lines.append(f"{i}. [{x['discipline']} {sh.get('min','?')}–{sh.get('max','?')}] {x['statement']}")
    user = f"教学内容：\n{q[:600]}\n\n候选能力点：\n" + '\n'.join(lines)
    try:
        raw = call(RERANK_SYS, user, base, key, model)
    except Exception as e:
        return None, f'精排调用失败（{type(e).__name__}），退回粗召回顺序'
    m = re.search(r'\{.*\}', raw or '', re.S)
    if not m:
        return None, '精排没吐 JSON，退回粗召回顺序'
    try:
        d = json.loads(m.group(0))
    except Exception:
        return None, '精排 JSON 解析失败，退回粗召回顺序'
    picks, bogus = [], 0
    seen = set()
    for p in (d.get('picks') or []):
        n = p.get('n')
        # ★ 逐个核对：不在候选池里的当场丢掉。模型不许自由生成 ID
        if not isinstance(n, int) or not (1 <= n <= len(cands)) or n in seen:
            bogus += 1
            continue
        seen.add(n)
        picks.append((cands[n - 1], str(p.get('why') or '')[:120]))
    note = f'精排从 {len(cands)} 条候选里挑出 {len(picks)} 条'
    if bogus:
        note += f'（丢弃 {bogus} 个不在候选池里的编号）'
    return picks, note


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--text', default=None)
    ap.add_argument('--file', default=None)
    ap.add_argument('--discipline', default=None, help='限定学科（强烈建议给 —— 不给会跨科召回）')
    ap.add_argument('--stage', default=None, help='孩子所在年级，如 G3')
    ap.add_argument('--top', type=int, default=8)
    ap.add_argument('--citable-only', action='store_true', help='只召回可被档案引用的')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--rerank', action='store_true',
                    help='开精排：把粗召回的候选交给模型挑并排序（一次调用）。'
                         '不开就只有粗召回，排序不可信。')
    ap.add_argument('--pool', type=int, default=25, help='送去精排的候选数，默认 25')
    a = ap.parse_args()

    q = a.text or (Path(a.file).read_text(encoding='utf-8') if a.file else None)
    if not q:
        sys.exit('要么 --text 要么 --file')
    stage = G(a.stage) if a.stage else None
    anchors = load()
    df, corpus_n = build_df(anchors)
    cands = []
    for x in anchors:
        if a.citable_only and x['reviewStatus'] not in CITABLE:
            continue
        r = score(q, x, a.discipline, stage, df, corpus_n)
        if r:
            cands.append((r[0], r[1], x))
    cands.sort(key=lambda t: -t[0])

    reranked, note = None, None
    if a.rerank:
        import os
        base, key = os.environ.get('MIMO_BASE'), os.environ.get('MIMO_KEY')
        if not base or not key:
            note = '要精排得先设 MIMO_BASE / MIMO_KEY，现在只有粗召回'
        else:
            reranked, note = rerank(q, cands[:a.pool], base, key,
                                    os.environ.get('MIMO_MODEL', 'mimo-v2.5'))
    top = ([c for c, _ in reranked] if reranked is not None else cands)[:a.top]
    why_of = {id(c): w for c, w in (reranked or [])}

    out = []
    for cand in top:
        s, hit, x = cand
        sh = x.get('stageHint') or {}
        why = []
        # 按 IDF 排，先说最有区分力的那几个词
        # 精排给了理由就先说它 —— 那是「为什么对应」，字面命中只是「为什么被捞进来」
        rw = why_of.get(id(cand))
        if rw:
            why.append(rw)
        why.append('字面命中 ' + '、'.join(f'「{w}」' for w, _ in hit[:5]))
        if x.get('verb') and x['verb'] in q:
            why.append(f'动词「{x["verb"]}」对上了')
        if stage and G(sh.get('min')):
            lo, hi = G(sh.get('min')), G(sh.get('max')) or G(sh.get('min'))
            why.append('学段吻合' if lo <= stage <= hi else f'学段是 {sh.get("min")}–{sh.get("max")}，与 G{stage} 不同')
        out.append({
            'id': x['id'], 'rank': len(out) + 1, 'sortScore': round(s, 4),
            'statement': x['statement'], 'discipline': x['discipline'],
            'stage': {'min': sh.get('min'), 'max': sh.get('max')},
            'reviewStatus': x['reviewStatus'],
            'citable': x['reviewStatus'] in CITABLE,
            'humanConfirmed': x['reviewStatus'] in HUMAN_CONFIRMED,
            'fieldIssues': x.get('fieldIssues') or [],
            'why': why,
            'srcPage': (x.get('provenance') or {}).get('srcPage'),
        })

    if a.json:
        print(json.dumps({
            'query': q[:200], 'discipline': a.discipline, 'stage': a.stage,
            'candidates': out,
            'status': 'reranked' if reranked is not None else 'recall-only',
            'rerankNote': note,
            'disclaimer': ('已过模型精排：候选是从粗召回池里挑的，**模型只能从池里选，不许自由生成 ID**，'
                           '池外的漏了就漏了。sortScore 是粗召回的分，排名以精排为准。'
                           if reranked is not None else
                           '⚠️ **排序不可信**：只有字面粗召回。加 --rerank 开精排。'
                           '现在请把 candidates 当候选池用，别用 rank 做自动映射。')
                          + '映射结果不写回底座 —— 这是你的判断，留在你那边。'
                            'humanConfirmed 全库目前为 0：「可引用」的含义是「AI 看过、没挑出毛病」。',
        }, ensure_ascii=False, indent=1))
        return

    print(f'查询：{q[:70]}{"…" if len(q) > 70 else ""}')
    print(f'粗召回 {len(cands)} 条' + (f' · {note}' if note else '') + f' · 取前 {len(out)}\n')
    for c in out:
        tag = '✅可引用' if c['citable'] else '⚠不可引用'
        if c['reviewStatus'] == 'disputed':
            tag = '⛔存疑'
        print(f"  {c['rank']}. [{tag} {c['reviewStatus']}] {c['discipline']}｜{c['statement'][:52]}")
        print(f"     {c['id']} · 课标 p{c['srcPage']} · {' · '.join(c['why'])}")
        if c['fieldIssues']:
            print(f"     字段缺陷：{'、'.join(c['fieldIssues'])}")
        print()
    if reranked is None:
        print('  ⚠️ 排序不可信 —— 只有字面粗召回。加 --rerank 开精排。')
    else:
        print('  已过精排。模型只能从候选池里挑，池外的漏了就漏了 —— 粗召回门槛故意放得很松。')
    print('  映射结果不写回底座 —— 这是你的判断，留在你那边。')
    print(f'  教师签字数全库为 0：「可引用」= AI 看过没挑出毛病，不是有人签过字。')


if __name__ == '__main__':
    main()
