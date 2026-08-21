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
import argparse, collections, hashlib, itertools, json, os, random, re, sys, time
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


def build_pool(target, all_in_disc, cap=40):
    """候选前置池：同学科、学段不晚于自己、同领域优先，**但给跨学段留名额**。"""
    tmin, _ = stage_of(target)
    same, earlier = [], []
    for a in all_in_disc:
        if a['id'] == target['id']:
            continue
        amin, amax = stage_of(a)
        if amin > tmin:              # 学段整体晚于目标 → 不可能是前置
            continue
        same_strand = (a.get('strand') and a.get('strand') == target.get('strand'))
        key = (0 if same_strand else 1, tmin - amin)
        # 「更早学段」的判据：跨了至少一个学段档（1-2/3-4/5-6/7-9/高中）
        (earlier if tmin - amin >= 3 else same).append((key, a))
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
    """跨学科候选池：别的学科、学段不晚于自己、被依赖多的优先。

    **按学科均摊配额，不能全局排序取前 N。** 第一版按 ENABLERS 排序取前 36，
    结果数学把池子占满了，语文一条都进不去 —— 产出 44 条边全是「数学 → X」，
    连「撰写实验报告 ← 语文表达」这种明显的都出不来。池子里没有的，模型选不出来。
    """
    tmin, _ = stage_of(target)
    td = target['discipline']
    by_d = collections.defaultdict(list)
    for a in all_anchors:
        if a['discipline'] == td or stage_of(a)[0] > tmin:
            continue
        by_d[a['discipline']].append(a)
    for d in by_d:
        by_d[d].sort(key=lambda a: -outdeg.get(a['id'], 0))
    # 工具型学科多给名额，其余每科至少 2 个，轮转直到填满
    quota = {d: (10 if d in ENABLERS else 2) for d in by_d}
    pool, i = [], 0
    while len(pool) < cap and any(quota[d] > 0 and len(by_d[d]) > i for d in by_d):
        for d in sorted(by_d, key=lambda d: ENABLERS.get(d, 9)):
            if quota[d] > 0 and len(by_d[d]) > i and len(pool) < cap:
                pool.append(by_d[d][i]); quota[d] -= 1
        i += 1
    return pool


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--discipline', default=None)
    ap.add_argument('--src', default='anchors')
    ap.add_argument('--concurrency', type=int, default=14)
    ap.add_argument('--cross', action='store_true', help='只跑跨学科边（判据更严，最多 2 条/锚点）')
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

    jobs = []
    for disc, group in by_disc.items():
        # LIST 档不建图（语文字词篇目、英语词表是覆盖模型）——跨学科时它们可以当前置，
        # 但不能当被修方（覆盖模型没有「学完这个才能学那个」的语义）
        if group[0].get('track') == 'LIST':
            print(f"  跳过 {disc}（LIST 档不作为被修方）")
            continue
        for t in group:
            # --split-only：只给这批建，但池子照样是整个学科的，
            # 否则原子只能在原子之间找前置，那是凭空造出来的小圈子。
            if a.split_only and not (t.get('provenance') or {}).get('splitFrom'):
                continue
            if t.get('deprecated'):
                continue
            pool = (build_cross_pool(t, anchors, outdeg_seed) if a.cross
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
