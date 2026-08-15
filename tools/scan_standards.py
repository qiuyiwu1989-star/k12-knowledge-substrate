#!/usr/bin/env python3
"""
scan_standards.py — Pass A：给课标扫描件的每一页打结构标签，建页面索引。

为什么要单独一遍：1,594 页里真正含【学业要求】的可能只有 15–25%。
先花一遍便宜的分类，把 Pass B（昂贵的逐条抽取）圈定到相关页上，
比对全部页做深度抽取省一个数量级，而且索引本身就是可复用的资产。

分类用低 DPI（默认 110）——判断版面结构不需要看清每个字，image token 减半。
Pass B 才用 150 DPI。

  python3 tools/scan_standards.py --pdf-dir <目录> [--dpi 110] [--concurrency 48]
  python3 tools/scan_standards.py --pdf-dir <目录> --only 数学        # 先试跑一科
"""
import argparse, base64, collections, hashlib, itertools, json, os, random, re, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib import request, error

import fitz

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(__file__).parent / '.cache-scan'

PROMPT = """你在阅读《义务教育课程标准（2022年版）》某一学科的一页扫描件。判断这一页的版面结构。

只输出一行 JSON，不要代码块、不要解释、不要任何前言后语：
{"section":"…","heading":"…","stage":"…","domain":"…","blocks":["…"]}

字段说明：
- section：本页主体属于哪一部分，只能取其一
  目录 / 前言 / 课程性质 / 课程理念 / 课程目标 / 课程内容 / 学业质量 / 课程实施 / 附录 / 案例 / 其他
- heading：本页出现的最靠上的小标题原文（如「第一学段（1～2年级）」「（一）数与代数」）；没有就填 ""
- stage：本页涉及的学段，取 第一学段 / 第二学段 / 第三学段 / 第四学段 / 全学段 / ""（判断不了就空）
- domain：本页涉及的内容领域原文（如「数与代数」「图形与几何」「阅读与鉴赏」）；没有就填 ""
- blocks：本页出现了哪些方括号小节标题，从 ["内容要求","学业要求","教学提示","学业质量描述","素养表现"] 里选，可多选，没有就 []

注意：blocks 只填这一页上**实际出现**的方括号标题（形如【内容要求】【学业要求】【教学提示】），
正文里顺带提到的词不算。"""


# 双端点：/v1 与 /anthropic 是两个独立限流池，轮询能把有效吞吐拉高约 50%。
# 实测视觉请求的并发天花板远低于文本：/v1 约 24、/anthropic 约 16（超了就 429）。
ENDPOINTS = [("/v1/chat/completions", "openai"), ("/anthropic/v1/messages", "anthropic")]
_rr = itertools.count()


def call(png, base, key, model, timeout=180):
    b64 = base64.b64encode(png).decode()
    last = None
    for attempt in range(8):
        suffix, style = ENDPOINTS[next(_rr) % len(ENDPOINTS)]
        if style == "anthropic":
            body = {"model": model, "max_tokens": 600, "thinking": {"type": "disabled"},
                    "messages": [{"role": "user", "content": [
                        {"type": "text", "text": PROMPT},
                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}}]}]}
            hdr = {"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
        else:
            body = {"model": model, "temperature": 0, "max_completion_tokens": 600,
                    "thinking": {"type": "disabled"},
                    "messages": [{"role": "user", "content": [
                        {"type": "text", "text": PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}]}
            hdr = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
        req = request.Request(base + suffix, data=json.dumps(body).encode(), headers=hdr)
        try:
            d = json.load(request.urlopen(req, timeout=timeout))
            if style == "anthropic":
                txt = "".join(b.get("text", "") for b in d.get("content", []))
                u = d.get("usage", {})
                usage = {"completion_tokens": u.get("output_tokens", 0),
                         "prompt_tokens_details": {"image_tokens": u.get("input_tokens", 0)}}
            else:
                txt = d['choices'][0]['message'].get('content') or ''
                usage = d.get('usage', {})
            return txt, usage
        except error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code not in (429, 500, 502, 503, 504):
                raise RuntimeError(f"HTTP {e.code}: {e.read().decode()[:160]}")
        except Exception as e:
            last = type(e).__name__
        # 429 是限流不是失败：退避 + 抖动，绝不让限流风暴烧光重试配额
        time.sleep(min(30.0, 1.5 * (1.9 ** attempt)) * (0.6 + random.random() * 0.8))
    raise RuntimeError(f"重试耗尽（最后一次 {last}）")


def parse_json(txt):
    m = re.search(r'\{.*\}', txt, re.S)
    if not m:
        return None
    raw = m.group(0)
    try:
        return json.loads(raw)
    except Exception:
        pass
    # 模型偶尔吐残缺 JSON（掉键名，如 "stage":"全学段","","blocks":[]）。
    # 与其整页判失败重跑，不如按字段名逐个捞——版面标签是弱结构，捞到什么算什么。
    out = {}
    for k in ('section', 'heading', 'stage', 'domain'):
        mm = re.search(rf'"{k}"\s*:\s*"([^"]*)"', raw)
        out[k] = mm.group(1) if mm else ''
    mm = re.search(r'"blocks"\s*:\s*\[([^\]]*)\]', raw)
    out['blocks'] = re.findall(r'"([^"]+)"', mm.group(1)) if mm else []
    return out if out.get('section') else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pdf-dir', required=True)
    ap.add_argument('--only', default=None, help='只跑文件名含该串的学科')
    ap.add_argument('--dpi', type=int, default=110)
    ap.add_argument('--concurrency', type=int, default=32)  # 双端点合计；单端点视觉天花板 /v1≈24 /anthropic≈16
    ap.add_argument('--out', default=str(ROOT / 'tools/out/page-index.jsonl'))
    a = ap.parse_args()

    base, key, model = os.environ['MIMO_BASE'], os.environ['MIMO_KEY'], os.environ.get('MIMO_MODEL', 'mimo-v2.5')
    CACHE.mkdir(exist_ok=True)

    pdfs = sorted(p for p in Path(a.pdf_dir).glob('*.pdf') if not a.only or a.only in p.name)
    jobs = []
    docs = {}
    for p in pdfs:
        d = fitz.open(p); docs[p] = d
        jobs += [(p, i) for i in range(d.page_count)]
    print(f"{len(pdfs)} 份 PDF，共 {len(jobs)} 页 · dpi={a.dpi} · 并发 {a.concurrency}")

    tokens = {'img': 0, 'out': 0}
    lock_hits = [0]

    def work(job):
        p, i = job
        png = docs[p][i].get_pixmap(dpi=a.dpi).tobytes('png')
        h = hashlib.sha256(png + PROMPT.encode()).hexdigest()[:24]
        cf = CACHE / f"{h}.json"
        if cf.exists():
            lock_hits[0] += 1
            rec = json.loads(cf.read_text())
        else:
            try:
                txt, usage = call(png, base, key, model)
            except Exception as e:            # 单页失败不炸全局，标记后继续
                return p, i, None, f"__FAILED__ {e}"
            rec = {'content': txt, 'usage': usage}
            cf.write_text(json.dumps(rec, ensure_ascii=False))
        u = rec.get('usage', {})
        tokens['img'] += u.get('prompt_tokens_details', {}).get('image_tokens', 0)
        tokens['out'] += u.get('completion_tokens', 0)
        return p, i, parse_json(rec['content']), rec['content']

    t0 = time.time()
    rows, bad = [], 0
    with ThreadPoolExecutor(a.concurrency) as ex:
        for n, (p, i, obj, raw) in enumerate(ex.map(work, jobs), 1):
            if obj is None:
                bad += 1
                obj = {'section': '解析失败', 'heading': '', 'stage': '', 'domain': '', 'blocks': []}
            rows.append({'subject': p.stem, 'page': i + 1, **{k: obj.get(k) for k in
                        ('section', 'heading', 'stage', 'domain', 'blocks')}})
            if n % 100 == 0 or n == len(jobs):
                print(f"  {n}/{len(jobs)}（缓存 {lock_hits[0]}，{time.time()-t0:.0f}s）", flush=True)

    rows.sort(key=lambda r: (r['subject'], r['page']))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    print(f"\n用时 {time.time()-t0:.0f}s · 解析失败 {bad} 页 · image_token {tokens['img']:,} / output {tokens['out']:,}")
    print(f"→ {out}\n")
    sec = collections.Counter(r['section'] for r in rows)
    print("section 分布:", dict(sec.most_common()))
    xy = [r for r in rows if '学业要求' in (r['blocks'] or [])]
    print(f"含【学业要求】的页: {len(xy)} / {len(rows)} = {len(xy)/len(rows):.0%}")
    per = collections.Counter(r['subject'] for r in xy)
    for s, n in per.most_common():
        pgs = [r['page'] for r in xy if r['subject'] == s]
        print(f"  {s:<12} {n:>3} 页  {pgs[:6]}{'…' if len(pgs) > 6 else ''}")


if __name__ == '__main__':
    main()
