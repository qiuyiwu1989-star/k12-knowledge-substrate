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

STAGE_ORD = {'G1': 1, 'G2': 2, 'G3': 3, 'G4': 4, 'G5': 5, 'G6': 6, 'G7': 7, 'G8': 8, 'G9': 9}

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


def call(user_text, base, key, model, timeout=120):
    last = None
    for attempt in range(7):
        suffix, style = ENDPOINTS[next(_rr) % len(ENDPOINTS)]
        if style == "anthropic":
            body = {"model": model, "max_tokens": 600, "thinking": {"type": "disabled"},
                    "system": PROMPT, "messages": [{"role": "user", "content": user_text}]}
            hdr = {"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
        else:
            body = {"model": model, "temperature": 0, "max_completion_tokens": 600,
                    "thinking": {"type": "disabled"},
                    "messages": [{"role": "system", "content": PROMPT},
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
    return STAGE_ORD.get(sh.get('min'), 5), STAGE_ORD.get(sh.get('max'), 9)


def build_pool(target, all_in_disc, cap=40):
    """候选前置池：同学科、学段不晚于自己、同领域优先。"""
    tmin, _ = stage_of(target)
    pool = []
    for a in all_in_disc:
        if a['id'] == target['id']:
            continue
        amin, amax = stage_of(a)
        if amin > tmin:              # 学段整体晚于目标 → 不可能是前置
            continue
        same_strand = (a.get('strand') and a.get('strand') == target.get('strand'))
        pool.append((0 if same_strand else 1, tmin - amin if tmin >= amin else 99, a))
    pool.sort(key=lambda x: (x[0], x[1]))
    return [a for _, _, a in pool[:cap]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--discipline', default=None)
    ap.add_argument('--src', default='anchors')
    ap.add_argument('--concurrency', type=int, default=14)
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

    jobs = []
    for disc, group in by_disc.items():
        # LIST 档不建图（语文字词篇目、英语词表是覆盖模型）
        if group[0].get('track') == 'LIST':
            print(f"  跳过 {disc}（LIST 档不建先修图）")
            continue
        for t in group:
            pool = build_pool(t, group)
            if pool:
                jobs.append((t, pool))
    print(f"待标注 {len(jobs)} 条（平均候选池 {sum(len(p) for _, p in jobs)/max(1,len(jobs)):.0f}）")

    def work(job):
        t, pool = job
        lines = [f"{i+1}. {p['statement']}（{(p.get('stageHint') or {}).get('min','?')}，{p.get('strand') or '未标注'}）"
                 for i, p in enumerate(pool)]
        user = (f"【目标能力】{t['statement']}\n"
                f"（学科 {t['discipline']}，领域 {t.get('strand') or '未标注'}，"
                f"学段 {(t.get('stageHint') or {}).get('min','?')}）\n\n"
                f"【候选前置列表】\n" + "\n".join(lines))
        h = hashlib.sha256((PROMPT + user).encode()).hexdigest()[:24]
        cf = CACHE / f"{h}.json"
        if cf.exists():
            return t, pool, json.loads(cf.read_text())
        try:
            txt = call(user, base, key, model)
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
            for p in (obj.get('prereqs') or [])[:3]:
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
                            'evidence': [{'kind': 'llm', 'detail': f"候选池 {len(pool)} 选 {idx+1}，模型提议未复核"},
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
