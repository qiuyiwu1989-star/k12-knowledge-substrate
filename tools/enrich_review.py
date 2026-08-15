#!/usr/bin/env python3
"""
enrich_review.py — 一次调用干三件事：打核心素养标签 + 补 MATRIX 维度 + 学科挑错。

**AI 复核不是教师复核。** 产出的状态是 `ai-reviewed`，不是 `expert-confirmed`，
`usableAnchors` 依然不算它。它的价值只有两个：
  1. 把明显错的挑出来（降级为 disputed，退出可用集合）
  2. 给剩下的排优先级，让老师的 20 小时花在最可能有问题的条目上

为什么三件事合成一次调用：模型看同一条锚点时，判断「属于哪个素养」和
「这条有没有问题」用的是同一份理解。拆成三次不会更准，只会贵三倍。

核心素养是**查表不是猜** —— 2022 课标每个学科都印着官方的素养清单，
提示词里把该学科的清单给全，模型只能从里面选。

  python3 tools/enrich_review.py [--only 数学] [--dry-run]
"""
import argparse, collections, hashlib, itertools, json, os, random, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib import request, error

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(__file__).parent / '.cache-enrich'

# 《义务教育课程标准（2022年版）》各科核心素养。逐字照抄，不是归纳。
LITERACY = {
    '语文': ['文化自信', '语言运用', '思维能力', '审美创造'],
    '数学': ['数感', '量感', '符号意识', '运算能力', '几何直观', '空间观念', '推理意识',
             '数据意识', '模型意识', '应用意识', '创新意识', '抽象能力', '推理能力',
             '数据观念', '模型观念'],
    '英语': ['语言能力', '文化意识', '思维品质', '学习能力'],
    '物理': ['物理观念', '科学思维', '科学探究', '科学态度与责任'],
    '化学': ['化学观念', '科学思维', '科学探究与实践', '科学态度与责任'],
    '生物学': ['生命观念', '科学思维', '探究实践', '态度责任'],
    '科学': ['科学观念', '科学思维', '探究实践', '态度责任'],
    '历史': ['唯物史观', '时空观念', '史料实证', '历史解释', '家国情怀'],
    '地理': ['人地协调观', '综合思维', '区域认知', '地理实践力'],
    '道德与法治': ['政治认同', '道德修养', '法治观念', '健全人格', '责任意识'],
    '信息科技': ['信息意识', '计算思维', '数字化学习与创新', '信息社会责任'],
    '劳动': ['劳动观念', '劳动能力', '劳动习惯和品质', '劳动精神'],
    '艺术': ['审美感知', '艺术表现', '创意实践', '文化理解'],
    '体育与健康': ['运动能力', '健康行为', '体育品德'],
}
# 各科开设年级，用来判「学段是否可能错」
OPEN_AT = {'语文': (1, 9), '数学': (1, 9), '英语': (3, 9), '道德与法治': (1, 9),
           '体育与健康': (1, 9), '艺术': (1, 9), '劳动': (1, 9), '科学': (1, 9),
           '信息科技': (3, 8), '历史': (7, 9), '地理': (7, 9), '生物学': (7, 9),
           '物理': (8, 9), '化学': (9, 9)}

SYS = """你是一位有二十年经验的{disc}教研员，正在审一份由 AI 从课标抽取的能力图谱。

给你一条能力断言，做三件事：

**一、打核心素养标签**
从这个清单里选 1–2 个最贴切的（**只能从清单里选，不许自造**）：
{lits}

**二、给出主题与能力维度**
- topic：这条属于哪个内容主题（如「秦汉时期」「物质的性质」「数与运算」），4–10 字
- dimension：这条主要练的是哪种能力（通常就是上面选中的核心素养之一）

**三、挑错（这是最重要的一件）**
你是来找问题的，不是来盖章的。逐项检查，有问题才报，没问题就返回空数组：
- `stage`：这个学段放错了吗？（该学科{open_at}才开设；内容难度与年级是否匹配）
- `undecidable`：这条能对一个具体孩子答「会 / 不会」吗？还是一句口号或章节名？
- `not-a-capability`：这根本不是学生能力，而是教学建议、编写说明、课程目标？
- `truncated`：句子被截断了、缺主干、或明显是从长句里切坏的？
- `evidence-weak`：给的掌握证据证明不了这条能力？

每条问题写清**具体哪里不对**，不要写「建议进一步完善」这种废话。
拿不准就不报 —— 误报会浪费老师的时间，而老师的时间是这个项目最稀缺的东西。

只输出一行 JSON，不要代码块、不要解释：
{{"literacy":["…"],"topic":"…","dimension":"…","issues":[{{"type":"stage","detail":"实验室制取气体是九年级内容，标成一年级"}}]}}"""

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
    ap.add_argument('--concurrency', type=int, default=12)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    base, key, model = os.environ['MIMO_BASE'], os.environ['MIMO_KEY'], os.environ.get('MIMO_MODEL', 'mimo-v2.5')
    CACHE.mkdir(exist_ok=True)

    files = {}
    for f in sorted((ROOT / 'anchors').rglob('*.jsonl')):
        files[f] = [json.loads(l) for l in f.open(encoding='utf-8')]
    targets = [(f, i, r) for f, rows in files.items() for i, r in enumerate(rows)
               if not a.only or r['discipline'] == a.only]
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
        lo, hi = OPEN_AT.get(d, (1, 9))
        sysp = SYS.format(disc=d, lits='、'.join(LITERACY.get(d, [])),
                          open_at=f'{lo}–{hi} 年级')
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
        obj = {}
        if m:
            try:
                obj = json.loads(m.group(0))
            except Exception:
                obj = {'error': '解析失败'}
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
                lits = [x for x in (o.get('literacy') or []) if x in LITERACY.get(r['discipline'], [])]
                if lits:
                    r['literacy'] = lits[:2]; stat['补素养'] += 1
                if r['track'] == 'MATRIX':
                    if o.get('topic'):
                        r['topic'] = str(o['topic'])[:40]
                    if o.get('dimension'):
                        r['dimension'] = str(o['dimension'])[:30]
                    if r.get('topic') and r.get('dimension'):
                        stat['补维度'] += 1
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
