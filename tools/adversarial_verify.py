#!/usr/bin/env python3
"""
adversarial_verify.py — 对 ai-adjudicated 锚点做**独立**验证。

**为什么不是「再审一遍」。**

696 条可用锚点里 550 条是「AI 生成 + AI 裁定」——同一条流水线、同一个模型、
同一套 prompt。让它再审一遍自己的产物，只会确认。换个 prompt 说「找茬」也不够：
模型看着已经写好的断言，会被它锚定，倾向于替它找理由。

所以这里改变的是**信息流**，不是措辞：

    生成时：原文 ──→ 断言
    验证时：原文 ──→（模型看不到断言）──→ 它自己会抽出哪些事实
                                        ↓
                              机械比对：原断言在不在里面

模型没见过断言就无法被它牵着走。凭空造出来的关系在这条路径上会现形 ——
「能说出略读的目的是粗知文章大意」这种，独立读原文的模型不会抽出
「目的是」这个判断，因为原文里没有。

比对是**机械**的（实词覆盖率），不是又一次模型判断 —— 否则又绕回同一条链。

    python3 tools/adversarial_verify.py [--limit N] [--only 历史]
"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
from citable import CITABLE as CITABLE_SET   # noqa: E402
import argparse, hashlib, json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib import request, error

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(__file__).parent / '.cache-verify'

PROMPT = """下面是《义务教育课程标准（2022年版）》里的一段原文。

请列出这段原文**直接支持**的事实陈述 —— 也就是那些「问一个问题、有标准答案」的命题。

规则：
- 只写原文明确说了的。原文没说的一律不写，**宁可少写，绝不推断**。
- 每条形如「X 是 Y」「X 的 A 是 B」这种可问可答的命题。
- 原文如果只是要求学生做某个动作（「使用放大镜观察植物」），而没有陈述任何事实，
  就**一条都不要写**，输出 NONE。
- 最多 5 条。

每行一条，不编号，不解释。没有可写的就只输出 NONE。

原文："""


def call(text, base, key, model, timeout=120):
    body = {"model": model, "temperature": 0, "max_completion_tokens": 500,
            "thinking": {"type": "disabled"},
            "messages": [{"role": "user", "content": PROMPT + text}]}
    req = request.Request(base + "/v1/chat/completions", data=json.dumps(body).encode(),
                          headers={"Authorization": "Bearer " + key,
                                   "Content-Type": "application/json"})
    delay = 3.0
    for attempt in range(9):
        try:
            d = json.load(request.urlopen(req, timeout=timeout))
            return d['choices'][0]['message'].get('content') or ''
        except error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < 8:
                time.sleep(delay); delay *= 1.7; continue
            raise RuntimeError(f"HTTP {e.code}")
        except Exception:
            if attempt < 8:
                time.sleep(delay); delay *= 1.7; continue
            raise
    raise RuntimeError("重试耗尽")


STOP = set('的了和与及或在中对能会把被为是有个之其等这那所以并且但可以一二三四五六七八九十')


def content_chars(s):
    return {c for c in s if '一' <= c <= '鿿'} - STOP


def best_overlap(stmt, facts):
    """断言的实词，被独立抽出的事实**整体**覆盖了多少。纯机械，不再问模型。

    比**并集**不比单条 —— 试跑时按单条最佳算，误报很严重：
      断言「人体的运动是在神经系统支配下，由肌肉牵拉着骨围绕关节进行的」
      （与课标原文一字不差）只得 0.54，因为独立路径把它拆成了两条短句
      「…在神经系统支配下进行的」「…由肌肉牵拉着骨进行的」，
      任何单条都覆盖不了整个长句。拆分是正常行为，不该判成存疑。
    """
    a = content_chars(stmt.replace('能说出', '', 1))
    if not a:
        return 0.0, ''
    union = set()
    for f in facts:
        union |= content_chars(f)
    r = len(a & union) / len(a)
    # closest 只用于人工复核时看得方便，不参与判定
    best, which = 0.0, ''
    for f in facts:
        b = content_chars(f)
        x = len(a & b) / len(a)
        if x > best:
            best, which = x, f
    return r, which


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default=None)
    ap.add_argument('--recheck', action='store_true', help='连已验过的也重验')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--concurrency', type=int, default=10)
    ap.add_argument('--threshold', type=float, default=0.55,
                    help='覆盖率低于此值 = 独立路径没抽出这条，判为存疑')
    a = ap.parse_args()

    base, key = os.environ['MIMO_BASE'], os.environ['MIMO_KEY']
    model = os.environ.get('MIMO_MODEL', 'mimo-v2.5')
    CACHE.mkdir(exist_ok=True)

    targets = []
    for f in sorted((ROOT / 'anchors').glob('*.jsonl')):
        for l in f.open(encoding='utf-8'):
            if not l.strip():
                continue
            x = json.loads(l)
            # **2026-08-20：从「只验 ai-adjudicated」改成「验全部可引用的」。**
            # 可引用线放宽到 ai-reviewed 之后，1,401 条锚点里有近千条从没被
            # 独立路径验过 —— 而独立验证正是没有人参与时唯一能动摇既有结论的手段。
            # 已经验过的跳过（幂等，可反复跑）。
            if x.get('deprecated') or x['reviewStatus'] not in CITABLE_SET:
                continue
            if x.get('independentCheck') and not a.recheck:
                continue
            if a.only and x['discipline'] != a.only:
                continue
            if (x.get('provenance') or {}).get('srcText'):
                targets.append(x)
    if a.limit:
        targets = targets[:a.limit]

    # 同一段原文只调一次 —— 多条锚点常来自同一句
    by_src = {}
    for x in targets:
        by_src.setdefault(x['provenance']['srcText'], []).append(x)
    print(f"待验 {len(targets)} 条锚点，去重后 {len(by_src)} 段原文")

    def work(src):
        h = hashlib.sha256((src + PROMPT).encode()).hexdigest()[:24]
        cf = CACHE / f"{h}.json"
        if cf.exists():
            return src, json.loads(cf.read_text())['facts'], True, False
        try:
            txt = call(src, base, key, model)
        except Exception:
            return src, None, False, True
        facts = [l.strip() for l in txt.split('\n')
                 if l.strip() and l.strip().upper() != 'NONE'
                 and not l.strip().startswith(('原文', '规则', '说明'))]
        cf.write_text(json.dumps({'facts': facts}, ensure_ascii=False))
        return src, facts, False, False

    t0, done, hit, failed = time.time(), 0, 0, 0
    facts_by_src = {}
    with ThreadPoolExecutor(a.concurrency) as ex:
        for src, facts, cached, bad in ex.map(work, list(by_src)):
            if bad:
                failed += 1
            else:
                facts_by_src[src] = facts
            done += 1; hit += cached
            if done % 100 == 0:
                print(f"  {done}/{len(by_src)}（缓存 {hit}，失败 {failed}，{time.time()-t0:.0f}s）", flush=True)

    rows = []
    for src, anchors in by_src.items():
        facts = facts_by_src.get(src)
        if facts is None:
            continue
        for x in anchors:
            r, which = best_overlap(x['statement'], facts)
            rows.append({'id': x['id'], 'discipline': x['discipline'],
                         'statement': x['statement'], 'srcText': src,
                         'independentFacts': facts, 'overlap': round(r, 3),
                         'closest': which, 'suspect': r < a.threshold})

    # ── 判定改成三值。**「方法不适用」不是「没通过」。** ─────────────
    #
    # 2026-08-20 把覆盖面从 ai-adjudicated 扩到全部可引用锚点之后，存疑率 74%。
    # 逐条看下来几乎全是方法误报：
    #
    #   原文「能列举常见的化学电源，并能利用相关信息分析其工作原理。」
    #     → 原文本身是**动作要求**，不是事实命题。提示词明写这种情况输出 NONE。
    #       抽不出事实 ≠ 锚点有问题，是这个方法**没有可查的东西**。
    #
    #   断言「能描述四则运算的含义」／原文「能描述四则运算的含义，知道减法是…」
    #     → 断言是原文的**逐字前缀**，忠实性本来就成立；覆盖率 0.286 是因为
    #       独立路径抽的是同一句里另一个分句的事实。
    #
    # 照 74% 降级会砸掉 606 条锚点。**指标误判比没有指标更糟** —— 这个项目
    # 在「不以句号结尾算碎片」上栽过一次，那次是一个学科，这次是六百条。
    def content(t):
        return {c for c in t if '\u4e00' <= c <= '\u9fff'}

    for r in rows:
        st, src = content(r['statement']), content(r['srcText'])
        verbatim = len(st & src) / max(1, len(st))
        if verbatim >= 0.9:
            r['verdict'] = 'grounded-verbatim'   # 断言的字几乎全来自原文，忠实性直接成立
        elif not r['independentFacts']:
            r['verdict'] = 'not-applicable'      # 原文是动作要求，抽不出事实命题
        elif r['suspect']:
            r['verdict'] = 'suspect'             # 真存疑：原文有事实，但独立路径没抽出这条
        else:
            r['verdict'] = 'passed'
        r['verbatimCoverage'] = round(verbatim, 3)

    out = ROOT / 'tools/out/verify-report.json'
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')

    # 写回锚点。**只记录，不改 reviewStatus** —— 降级是人的决定，
    # 而这一轮恰恰证明了这个方法的误报率高到不能直接驱动降级。
    if not a.dry_run:
        by_id = {r['id']: r for r in rows}
        for f in sorted((ROOT / 'anchors').glob('*.jsonl')):
            arr = [json.loads(l) for l in f.read_text(encoding='utf-8').splitlines() if l.strip()]
            hit = False
            for x in arr:
                r = by_id.get(x['id'])
                if not r:
                    continue
                x['independentCheck'] = {
                    'method': '模型只读原文（看不到本断言）自行抽事实，再机械比对实词覆盖',
                    'verdict': r['verdict'],
                    'overlap': r['overlap'],
                    'verbatimCoverage': r['verbatimCoverage'],
                    'facts': r['independentFacts'][:5],
                }
                hit = True
            if hit:
                f.write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in arr), encoding='utf-8')


    import collections
    V = collections.Counter(r['verdict'] for r in rows)
    print(f"\n验完 {len(rows)} 条　失败 {failed} 段（重跑走缓存补）")
    CN = {'grounded-verbatim': '断言的字几乎全来自原文，忠实性直接成立（这个方法无须再查）',
          'not-applicable':    '原文是动作要求、抽不出事实命题 —— **方法不适用，不是没通过**',
          'passed':            '独立路径抽出了同一条事实',
          'suspect':           '**真存疑**：原文有事实，但独立路径没抽出这条'}
    for k in ('grounded-verbatim', 'passed', 'not-applicable', 'suspect'):
        if V[k]:
            print(f"  {V[k]:>4}  {k:18} {CN[k]}")
    sus = [r for r in rows if r['verdict'] == 'suspect']
    if sus:
        print("  真存疑按学科：", dict(collections.Counter(r['discipline'] for r in sus).most_common(8)))
    print(f"\n→ {out}")


if __name__ == '__main__':
    main()
