#!/usr/bin/env python3
"""
ai_review.py — 让 AI 把明显错的锚点挑出来。**这不是教师复核。**

产出状态是 `ai-reviewed`（没挑出问题）或 `disputed`（挑出了问题）。
两者都不进 `usableAnchors` —— AI 审查是**筛子，不是合格证**。
它的全部价值是：把明显错的降下去，并给剩下的排优先级。

## 2026-08-19：从 enrich_review.py 改名，并砍掉两件事

原来它一次干三件：打核心素养标签 + 补 MATRIX 维度 + 挑错。前两件现在都不该由它干：

- **核心素养**已由 `tag_literacy.py` + `mappings/literacy.json` 做到 100%，
  那是从 24 科课标原文抄下来的闭合词表。这里原本另抄了一份 14 科的硬编码词表 ——
  **同一个概念在仓库里有两份定义，迟早发散**，而且缺 10 个高中科目。删掉。
- **topic 不许由模型写。** 624 条缺 topic 已经查到源头（通用技术/西班牙语的高中版式
  没有主题层级，义教那些页面本身没标注），结论是**留空**。让模型现编一个主题名，
  就是把「查过、确实没有」偷换成「有，且来路不明」。见 docs/gaozhong.md。

## 修好的一处静默失效

`OPEN_AT`（各科开设年级，用来判学段是否放错）原来只到 9 年级，且缺省 (1,9)。
高中那 883 条锚点标的是 G10–G12，模型会被告知「该学科 1–9 年级开设」，
于是**每一条都会被判 stage 错**。跑下去就是 883 条集体降级 disputed。

这和 `gen_edges` 的 `STAGE_ORD` 只到 G9 是同一个错，第三次了：
**义务教育时代写的常量表，高中数据进来时没有一个会报错，只会静默给出错误答案。**

    python3 tools/ai_review.py                    # 默认只审从没审过的（llm-proposed）
    python3 tools/ai_review.py --status ai-reviewed --only 数学
    python3 tools/ai_review.py --dry-run
"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
from citable import HUMAN_CONFIRMED   # noqa: E402
import argparse, collections, hashlib, itertools, json, os, random, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib import request, error

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(__file__).parent / '.cache-ai-review'

# 各科开设年级，用来判「学段是否可能错」。**必须覆盖到 12 年级** ——
# 缺省值给 (1,9) 会让全部高中锚点被判 stage 错（见文件头）。
# 没在表里的学科直接报错，不再静默走缺省。
OPEN_AT = {
    '语文': (1, 12), '数学': (1, 12), '英语': (3, 12), '体育与健康': (1, 12),
    '道德与法治': (1, 9), '思想政治': (10, 12),
    # ★ 2026-08-29：艺术从 (1,9) 改成 (1,12)。
    #   《普通高中艺术课程标准》是真实存在的独立文档 —— 库里有
    #   anchors/gaozhong-艺术.jsonl，61 条标 G10–G12，srcCourse 是必修/选择性必修。
    #   常量表说「艺术只开到 9 年级」，于是复核时 34 条里 32 条被误判成学段错。
    #   音乐/美术保持 (10,12) 是对的：义务教育只有综合的「艺术」，高中才分科。
    #   这是同一类错的第四次（文件头第 22 行记着前几次），根子都是
    #   **常量表是按义务教育写的，加高中之后没人回头对**。
    '艺术': (1, 12), '音乐': (10, 12), '美术': (10, 12),
    '劳动': (1, 9), '科学': (1, 9),
    '信息科技': (3, 9), '信息技术': (10, 12),
    '历史': (7, 12), '地理': (7, 12), '生物学': (7, 12),
    '物理': (8, 12), '化学': (9, 12),
    '通用技术': (10, 12),
    '日语': (10, 12), '俄语': (10, 12), '德语': (10, 12),
    '法语': (10, 12), '西班牙语': (10, 12),
}

SYS = """你是一位有二十年经验的{disc}教研员，正在审一份由 AI 从课标抽取的能力图谱。

**你是来找问题的，不是来盖章的。** 逐项检查这条能力断言，有问题才报，没问题返回空数组：

- `stage`：学段放错了吗？（{disc}在**{open_at}**开设；内容难度与标注年级是否匹配）
- `undecidable`：这条能对一个具体孩子答「会 / 不会」吗？还是一句口号、一个章节名？
- `not-a-capability`：这根本不是学生能力，而是教学建议、编写说明、课程目标、办学要求？
- `truncated`：句子被截断了、缺主干、或明显是从长句里切坏的？
- `evidence-weak`：给的掌握证据证明不了这条能力？

每条问题写清**具体哪里不对**，不要写「建议进一步完善」这种废话。

两条克制：
1. **拿不准就不报。** 误报会浪费老师的时间，而老师的时间是这个项目最稀缺的东西。
2. **断言短不是问题。**「能计算圆锥的体积」本来就该这么短，硬拉长是注水。
   唯一的判据是能不能对一个具体孩子答「会 / 不会」。

只输出一行 JSON，不要代码块、不要解释：
{{"issues":[{{"type":"stage","detail":"实验室制取气体是九年级内容，这里标成一年级"}}]}}
{{"issues":[]}}"""

ENDPOINTS = [("/v1/chat/completions", "openai"), ("/anthropic/v1/messages", "anthropic")]
_rr = itertools.count()


def call(sys_prompt, user, base, key, model, timeout=120):
    last = None
    for attempt in range(7):
        suffix, style = ENDPOINTS[next(_rr) % len(ENDPOINTS)]
        if style == "anthropic":
            body = {"model": model, "max_tokens": 700, "thinking": {"type": "disabled"},
                    "system": sys_prompt, "messages": [{"role": "user", "content": user}]}
            hdr = {"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
        else:
            body = {"model": model, "temperature": 0, "max_completion_tokens": 700,
                    "thinking": {"type": "disabled"},
                    "messages": [{"role": "system", "content": sys_prompt},
                                 {"role": "user", "content": user}]}
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
        time.sleep(min(25.0, 1.4 * (1.9 ** attempt)) * (0.6 + random.random() * 0.8))
    raise RuntimeError(f"重试耗尽（{last}）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default=None)
    ap.add_argument('--status', default='llm-proposed',
                    help='审哪一档。默认只审从没审过的；传 all 审全部未确认的')
    ap.add_argument('--concurrency', type=int, default=12)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    base, key, model = os.environ['MIMO_BASE'], os.environ['MIMO_KEY'], os.environ.get('MIMO_MODEL', 'mimo-v2.5')
    CACHE.mkdir(exist_ok=True)

    files = {}
    for f in sorted((ROOT / 'anchors').rglob('*.jsonl')):
        files[f] = [json.loads(l) for l in f.open(encoding='utf-8')]
    # **AI 复审不许碰已确认的锚点。** 课标附录那批是 auto-confirmed（证据强度最高：
    # 官方来源 + 机械校验 + 判定客观），让主观的 AI 判断去覆盖它，等于自己把分级拆了。
    # 实测教训：第一次没加这条，138 条 auto-confirmed 被重判到只剩 23 条。
    # **AI 复审不许碰已确认的锚点。** 课标附录那批是 auto-confirmed（证据强度最高：
    # 官方来源 + 机械校验 + 判定客观），让主观的 AI 判断去覆盖它，等于自己把分级拆了。
    # 实测教训：第一次没加这条，138 条 auto-confirmed 被重判到只剩 23 条。
    # 不重审「已经确认过」的：机械可判定的（auto）和人签过字的（expert）。
    # **这不是「可引用集合」** —— ai-reviewed / ai-adjudicated 都在可引用里，
    # 但它们该被重审。所以这里用 HUMAN_CONFIRMED 加上机械那一档，
    # 而不是抄一份 CITABLE。判据不同，集合就该不同 —— 但两者都从一处来。
    SKIP = HUMAN_CONFIRMED | {'auto-confirmed'}
    want = None if a.status == 'all' else set(a.status.split(','))
    if want and (want & SKIP):
        sys.exit(f'不许审已确认的档位：{sorted(want & SKIP)}')
    targets = [(f, i, r) for f, rows in files.items() for i, r in enumerate(rows)
               if r['reviewStatus'] not in SKIP and not r.get('deprecated')
               and (want is None or r['reviewStatus'] in want)
               and (not a.only or r['discipline'] == a.only)]
    missing = sorted({r['discipline'] for _, _, r in targets} - set(OPEN_AT))
    if missing:
        sys.exit(f'OPEN_AT 缺这些学科，补上再跑（缺省值会让它们全部被判学段错）：{missing}')
    print(f"待审 {len(targets)} 条 · 并发 {a.concurrency}")

    edges_in = collections.defaultdict(list)
    byid = {r['id']: r for rows in files.values() for r in rows}
    for f in sorted((ROOT / 'edges').rglob('*.jsonl')):
        for l in f.open(encoding='utf-8'):
            e = json.loads(l)
            edges_in[e['anchorId']].append(e['prerequisiteId'])

    def work(job):
        f, i, r = job
        d = r['discipline']
        lo, hi = OPEN_AT[d]          # 缺表就崩 —— 静默走缺省正是上一版的 bug
        sysp = SYS.format(disc=d, open_at=f'{lo}–{hi} 年级')
        pres = [byid[p]['statement'] for p in edges_in.get(r['id'], [])[:5] if p in byid]
        user = (f"能力断言：{r['statement']}\n"
                f"领域：{r.get('strand') or '未标注'}\n"
                f"标注学段：{(r.get('stageHint') or {}).get('min','?')}–{(r.get('stageHint') or {}).get('max','?')}\n"
                f"掌握证据：{' / '.join((r.get('evidence') or [])[:3]) or '（无）'}\n"
                f"已标的直接前置：{' / '.join(pres) if pres else '（无）'}\n"
                f"来源：{d}课标 第 {(r.get('provenance') or {}).get('srcPage','?')} 页")
        h = hashlib.sha256((sysp + user).encode()).hexdigest()[:24]
        cf = CACHE / f"{h}.json"
        if cf.exists():
            return f, i, json.loads(cf.read_text())
        try:
            txt = call(sysp, user, base, key, model)
        except Exception as e:
            return f, i, {'error': str(e)[:50]}
        m = re.search(r'\{.*\}', txt, re.S)
        # ★ 2026-08-29 修两个洞，第二个能凭空造出一条「AI 看过」。
        #
        # 洞一：原来 `obj = {}` 在 if 之前初始化，回复里找不到 '{' 时 obj 保持空。
        #   空对象既没有 error 也没有 issues → 主循环走 else 分支 → iss 为空
        #   → **静默升成 ai-reviewed**。一次网络截断就伪造出一条「AI 看过」，
        #   而整个项目对外的说法就压在这个状态上（「AI 看过、没挑出毛病」）。
        #   现在：没吐 JSON 一律记成 error，绝不当成「没挑出问题」。
        #
        # 洞二：失败也写进缓存。缓存里躺着 10 条 {"error":"解析失败"}，
        #   每次重跑都被当成「调用失败」重放，那 10 条永远审不到。
        #   和 fix_fallback_evidence.py 是同一个病（2026-08-25 修过一次）——
        #   **缓存是为了省钱，不是为了固化错误。**
        if not m:
            obj = {'error': '没吐 JSON'}
        else:
            try:
                obj = json.loads(m.group(0))
            except Exception:
                obj = {'error': '解析失败'}
        # 结构完整才算数：**「没挑出问题」必须来自一个有 issues 键的回答**，
        # 不能来自一个碰巧没有 error 的残缺对象。
        if 'error' not in obj and not isinstance(obj.get('issues'), list):
            obj = {'error': '回答里没有 issues 字段'}
        if 'error' not in obj:
            cf.write_text(json.dumps(obj, ensure_ascii=False))
        return f, i, obj

    t0 = time.time()
    stat = collections.Counter()
    issue_kind = collections.Counter()
    with ThreadPoolExecutor(a.concurrency) as ex:
        for n, (f, i, o) in enumerate(ex.map(work, targets), 1):
            r = files[f][i]
            if o.get('error'):
                stat['调用失败'] += 1
            else:
                iss = [x for x in (o.get('issues') or []) if isinstance(x, dict) and x.get('type')]
                if iss:
                    r['aiIssues'] = iss[:5]
                    r['reviewStatus'] = 'disputed'
                    stat['挑出问题'] += 1
                    for x in iss:
                        issue_kind[x['type']] += 1
                elif r['reviewStatus'] == 'llm-proposed':
                    r['reviewStatus'] = 'ai-reviewed'   # 过了 AI 这关，但**不是**教师复核
                    stat['AI 过审'] += 1
            if n % 100 == 0 or n == len(targets):
                print(f"  {n}/{len(targets)}（{time.time()-t0:.0f}s）", flush=True)

    if not a.dry_run:
        for f, rows in files.items():
            with f.open('w', encoding='utf-8') as fh:
                for r in rows:
                    fh.write(json.dumps(r, ensure_ascii=False) + '\n')

    print(f"\n用时 {time.time()-t0:.0f}s")
    print("  ", dict(stat))
    print("  挑出的问题类型:", dict(issue_kind.most_common()))
    print("\n  注意：ai-reviewed **不是** expert-confirmed，usableAnchors 依然不算它。")
    print("        它的作用是把明显错的降级为 disputed，并给剩下的排优先级。")


if __name__ == '__main__':
    main()
