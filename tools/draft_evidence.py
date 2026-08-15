#!/usr/bin/env python3
"""
draft_evidence.py — 给候选起草 evidence 和 assessment，供老师确认/修改。

为什么值得做：24 人 × 20 小时那个测算，成立与否取决于老师**要不要自己写字**。
让老师从零写 evidence，一条要 3–5 分钟；让老师看两条草稿点「对/改」，一条 20 秒。
这一步是把复核从「创作」降级成「判断」——**老师的稀缺资源是判断力，不是打字**。

起草的一律是草稿：`evidenceDraft` / `assessmentDraft`，**不是** `evidence`。
校验器只认 `evidence`，所以草稿进不了 anchors/，必须老师确认后才转正。

  python3 tools/draft_evidence.py --discipline 数学 --buckets READY,NO_STAGE
"""
import argparse, collections, itertools, json, os, random, re, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib import request, error

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(__file__).parent / '.cache-draft'

PROMPT = """你在为一个 K12 能力图谱起草「掌握证据」。给定一条能力断言，写出判断一个孩子是否掌握它的**可观察证据**。

规则：
- 恰好 2 条证据，每条是一个旁观者能看到孩子做出来的具体行为，不是感受、不是态度
- 每条 8–24 字，用「能……」开头
- 证据必须比断言更具体：断言说「能计算两位数进位加法」，证据要说「正确计算 37+45 并说明进位发生在哪一位」
- 再写 1 句给家长看的检核问句，用 {{name}} 指代孩子，口语化，不超过 40 字

只输出一行 JSON，不要代码块、不要解释：
{"evidence":["…","…"],"assessment":"…"}"""

ENDPOINTS = [("/v1/chat/completions", "openai"), ("/anthropic/v1/messages", "anthropic")]
_rr = itertools.count()


def call(user_text, base, key, model, timeout=120):
    last = None
    for attempt in range(6):
        suffix, style = ENDPOINTS[next(_rr) % len(ENDPOINTS)]
        if style == "anthropic":
            body = {"model": model, "max_tokens": 500, "thinking": {"type": "disabled"},
                    "system": PROMPT,
                    "messages": [{"role": "user", "content": user_text}]}
            hdr = {"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
        else:
            body = {"model": model, "temperature": 0, "max_completion_tokens": 500,
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
        time.sleep(min(20.0, 1.5 * (1.9 ** attempt)) * (0.6 + random.random() * 0.8))
    raise RuntimeError(f"重试耗尽（{last}）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--discipline', default=None)
    ap.add_argument('--buckets', default='READY,NO_STAGE,JUDGE')
    ap.add_argument('--concurrency', type=int, default=20)
    ap.add_argument('--src', default=str(ROOT / 'tools/out/triage.jsonl'))
    ap.add_argument('--out', default=str(ROOT / 'tools/out/review-sheet.jsonl'))
    a = ap.parse_args()

    base, key, model = os.environ['MIMO_BASE'], os.environ['MIMO_KEY'], os.environ.get('MIMO_MODEL', 'mimo-v2.5')
    CACHE.mkdir(exist_ok=True)
    buckets = set(a.buckets.split(','))

    rows = [json.loads(l) for l in open(a.src, encoding='utf-8')]
    if a.discipline:
        rows = [r for r in rows if r['discipline'] == a.discipline]
    todo = [r for r in rows if r['bucket'] in buckets]
    print(f"起草 {len(todo)} 条（桶：{','.join(sorted(buckets))}）· 并发 {a.concurrency}")

    def work(r):
        ctx = (f"学科：{r['discipline']}\n领域：{r.get('strand') or '未标注'}\n"
               f"学段提示：{(r.get('stageHint') or {}).get('min','?')}-{(r.get('stageHint') or {}).get('max','?')}\n"
               f"能力断言：{r['statement']}")
        h = __import__('hashlib').sha256((PROMPT + ctx).encode()).hexdigest()[:24]
        cf = CACHE / f"{h}.json"
        if cf.exists():
            return r, json.loads(cf.read_text())
        try:
            txt = call(ctx, base, key, model)
        except Exception as e:
            return r, {'error': str(e)[:80]}
        m = re.search(r'\{.*\}', txt, re.S)
        obj = {}
        if m:
            try:
                obj = json.loads(m.group(0))
            except Exception:
                obj = {'error': '解析失败', 'raw': txt[:200]}
        cf.write_text(json.dumps(obj, ensure_ascii=False))
        return r, obj

    t0 = time.time()
    out, bad = [], 0
    with ThreadPoolExecutor(a.concurrency) as ex:
        for n, (r, obj) in enumerate(ex.map(work, todo), 1):
            ev = obj.get('evidence') if isinstance(obj.get('evidence'), list) else None
            if not ev or len(ev) < 2:
                bad += 1
            out.append({**r, 'evidenceDraft': ev or [], 'assessmentDraft': obj.get('assessment') or '',
                        'draftError': obj.get('error')})
            if n % 50 == 0 or n == len(todo):
                print(f"  {n}/{len(todo)}（{time.time()-t0:.0f}s）", flush=True)

    # JUNK 也写进复核单，但标成待丢弃 —— 老师有权推翻机器的分诊
    for r in rows:
        if r['bucket'] not in buckets:
            out.append({**r, 'evidenceDraft': [], 'assessmentDraft': '', 'draftError': None})

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, 'w', encoding='utf-8') as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f"\n用时 {time.time()-t0:.0f}s · 起草失败 {bad} 条 → {a.out}")
    print("  产出的是 evidenceDraft（草稿），**不是** evidence —— 校验器只认后者，老师确认后才转正")


if __name__ == '__main__':
    main()
