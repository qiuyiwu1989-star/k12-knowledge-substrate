#!/usr/bin/env python3
"""
tag_crosscutting.py — 给锚点打横切维度标签。

为什么这件事比「多造几条跨学科前置边」安全得多：

  · 前置边打错 → 推荐路径把孩子往错方向推
  · 横切标签打错 → 最坏只是关联推荐不准

**错误代价不在一个量级**，所以这里允许 AI 直接落盘，而前置边一直只敢标
llm-proposed。

另外，这是**封闭词表分类**（7 选 0–2 / 8 选 0–2），不是开放生成。模型只能从
给定 id 里挑，挑不出就返回空数组。开放式打标会退化成同义词泛滥，那就又变回
一堆没法 join 的自由文本。

    python3 tools/tag_crosscutting.py [--limit N] [--only 语文]
"""
import argparse, base64, hashlib, json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib import request, error

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(__file__).parent / '.cache-cc'

VOCAB = json.loads((ROOT / 'mappings/crosscutting.json').read_text(encoding='utf-8'))
CC_IDS = [c['id'] for c in VOCAB['crosscutting']]
PR_IDS = [p['id'] for p in VOCAB['practice']]

CC_MENU = '\n'.join(f"  {c['id']}｜{c['zh']}｜{c['desc']}" for c in VOCAB['crosscutting'])
PR_MENU = '\n'.join(f"  {p['id']}｜{p['zh']}" for p in VOCAB['practice'])

PROMPT = f"""给一条 K12 能力锚点打「横切维度」标签。

【跨学科通用概念】只能从下面选，最多 2 个，宁缺毋滥：
{CC_MENU}

【实践】只能从下面选，最多 2 个，宁缺毋滥：
{PR_MENU}

判据：
- 通用概念问的是「这条锚点让学生练的，本质上是哪一类思维」。
  「能说出形声字的构字规律」→ patterns（练的是找规律），不是 structure-function。
- 实践问的是「学生要做哪类动作」。「能背诵《静夜思》」→ 不做任何一类科学实践，
  practice 返回空数组。**大量语文识字/背诵类锚点的两个字段都该是空的，这很正常。**
- 拿不准就不打。空数组是完全可接受的答案，打错比不打更坏。

只输出一行 JSON，不要解释：
{{"crosscutting":["..."],"practice":["..."],"why":"不超过20字"}}"""


def call(text, base, key, model, timeout=120):
    body = {"model": model, "temperature": 0, "max_completion_tokens": 300,
            "thinking": {"type": "disabled"},
            "messages": [{"role": "user", "content": PROMPT + "\n\n锚点：" + text}]}
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


def parse(txt):
    """只认词表内的 id。模型自造的一律丢弃 —— 这是封闭词表的意义所在。"""
    i, j = txt.find('{'), txt.rfind('}')
    if i < 0 or j < 0:
        return [], [], ''
    try:
        d = json.loads(txt[i:j + 1])
    except Exception:
        return [], [], ''
    cc = [x for x in (d.get('crosscutting') or []) if x in CC_IDS][:2]
    pr = [x for x in (d.get('practice') or []) if x in PR_IDS][:2]
    return cc, pr, str(d.get('why', ''))[:40]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default=None)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--concurrency', type=int, default=24)
    a = ap.parse_args()

    base, key = os.environ['MIMO_BASE'], os.environ['MIMO_KEY']
    model = os.environ.get('MIMO_MODEL', 'mimo-v2.5')
    CACHE.mkdir(exist_ok=True)

    files = {}
    targets = []
    for f in sorted((ROOT / 'anchors').glob('*.jsonl')):
        arr = [json.loads(l) for l in f.open(encoding='utf-8') if l.strip()]
        files[f.name] = arr
        for x in arr:
            if x.get('deprecated'):
                continue
            if a.only and x['discipline'] != a.only:
                continue
            targets.append(x)
    if a.limit:
        targets = targets[:a.limit]
    print(f"待打标 {len(targets)} 条")

    def work(x):
        txt = f"{x['discipline']}｜{x['statement']}"
        h = hashlib.sha256((txt + PROMPT).encode()).hexdigest()[:24]
        cf = CACHE / f"{h}.json"
        if cf.exists():
            d = json.loads(cf.read_text()); return x, d['cc'], d['pr'], d['why'], True, False
        try:
            cc, pr, why = parse(call(txt, base, key, model))
        except Exception:
            # 单条失败不许拖垮全局。429 是限流不是任务失败 —— 上一版让一条
            # 重试耗尽把 689 条的活整个带崩了，缓存也白写。失败的下次重跑补上。
            return x, None, None, '', False, True
        cf.write_text(json.dumps({'cc': cc, 'pr': pr, 'why': why}, ensure_ascii=False))
        return x, cc, pr, why, False, False

    t0, done, hit, failed = time.time(), 0, 0, 0
    with ThreadPoolExecutor(a.concurrency) as ex:
        for x, cc, pr, why, cached, bad in ex.map(work, targets):
            if bad:
                failed += 1                      # 保持原样，不覆盖已有标签
            else:
                x['crosscutting'] = cc
                x['practice'] = pr
                if why:
                    x.setdefault('provenance', {})['crosscuttingWhy'] = why
            done += 1; hit += cached
            if done % 100 == 0:
                print(f"  {done}/{len(targets)}（缓存 {hit}，失败 {failed}，{time.time()-t0:.0f}s）", flush=True)

    for fname, arr in files.items():
        with (ROOT / 'anchors' / fname).open('w', encoding='utf-8') as f:
            for x in arr:
                f.write(json.dumps(x, ensure_ascii=False) + '\n')

    import collections
    cc_n = collections.Counter(c for x in targets for c in (x.get('crosscutting') or []))
    pr_n = collections.Counter(p for x in targets for p in (x.get('practice') or []))
    both_empty = sum(1 for x in targets if not x.get('crosscutting') and not x.get('practice'))
    print(f"\n用时 {time.time()-t0:.0f}s　失败 {failed} 条（重跑即补，已成功的走缓存不重烧）")
    print(f"两个字段都为空的: {both_empty}/{len(targets)}（识字背诵类本来就该空）")
    zh = {c['id']: c['zh'] for c in VOCAB['crosscutting']}
    print("\n通用概念分布：")
    for k, v in cc_n.most_common():
        print(f"  {zh[k]:<16} {v}")
    zhp = {p['id']: p['zh'] for p in VOCAB['practice']}
    print("实践分布：")
    for k, v in pr_n.most_common():
        print(f"  {zhp[k]:<16} {v}")


if __name__ == '__main__':
    main()
