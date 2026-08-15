#!/usr/bin/env python3
"""
extract_xueye.py — Pass B：把【学业要求】小节逐字转写出来。

**只转写，不切分。** 从转写切出可判定能力断言是下一道独立工序（to_candidates.py）。
两者混在一起做，转写错误和判断错误就分不开了。

和 Pass A 抽的字表/篇目不同，学业要求是散文，**没有连号可校验**，所以：
  · 跑 3 次，逐句比对
  · 句子级一致的直接入库，不一致的整句进复核队列
  · 每条都带 srcPage / stage / domain，将来能翻回原页

页面来自 Pass A 建的索引（tools/out/page-index.jsonl），不需要手工指定页码。

  python3 tools/extract_xueye.py --pdf-dir <目录> [--only 数学] [--runs 3]
"""
import argparse, base64, collections, difflib, hashlib, itertools, json, os, random, re, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib import request, error

import fitz

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(__file__).parent / '.cache-xueye'
INDEX = ROOT / 'tools/out/page-index.jsonl'

# Pass A 的实测结论：14 个学科里只有 11 个用【学业要求】这个标题。
# 语文用【学习内容】+ 四个学习任务群块，英语用【内容要求】，劳动用【素养表现】。
# 只抓【学业要求】会系统性漏掉语文/英语/劳动三个大学科。
TARGET_BLOCKS = ['学业要求', '素养表现', '学业质量描述', '学习内容',
                 '识字与写字', '阅读与鉴赏', '表达与交流', '梳理与探究']

PROMPT = """逐字转写这一页中「描述学生应当达到的能力表现」的小节正文。这是《义务教育课程标准（2022年版）》的一页扫描件。

**要转写**的小节（页面上出现哪个就转哪个）：
【学业要求】【素养表现】【学业质量描述】【学习内容】
以及语文的学习任务群小节：【识字与写字】【阅读与鉴赏】【表达与交流】【梳理与探究】
另外：若本页是英语课标，且【内容要求】里有「能……」形式描述学生能做什么的句子，也要转写。

**不要转写**：【教学提示】【活动建议】【教学目标】【教学思路】，以及案例、样题、参考答案。

输出规则：
- 每进入一个要转写的小节，先输出一行 @小节名（如 @学业要求 或 @素养表现）
- 小节内的编号标题（如「1. 数与运算」）输出为 #1. 数与运算
- 正文按原文的分号和句号断句，每个完整句子占一行，逐字照抄，不改写、不合并、不概括
- 保留括号中的「例N」标注和顿号
- 若小节从上一页续下来，先输出 @续，再从本页第一句开始转写
- 本页若没有任何要转写的内容，只输出一行 #NONE
不解释、不总结、不写任何前言后语。第一个字符必须是 @ 或 #。"""

ENDPOINTS = [("/v1/chat/completions", "openai"), ("/anthropic/v1/messages", "anthropic")]
_rr = itertools.count()


def call(png, base, key, model, timeout=240):
    b64 = base64.b64encode(png).decode()
    last = None
    for attempt in range(8):
        suffix, style = ENDPOINTS[next(_rr) % len(ENDPOINTS)]
        if style == "anthropic":
            body = {"model": model, "max_tokens": 4000, "thinking": {"type": "disabled"},
                    "messages": [{"role": "user", "content": [
                        {"type": "text", "text": PROMPT},
                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}}]}]}
            hdr = {"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
        else:
            body = {"model": model, "temperature": 0, "max_completion_tokens": 4000,
                    "thinking": {"type": "disabled"},
                    "messages": [{"role": "user", "content": [
                        {"type": "text", "text": PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}]}
            hdr = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
        req = request.Request(base + suffix, data=json.dumps(body).encode(), headers=hdr)
        try:
            d = json.load(request.urlopen(req, timeout=timeout))
            if style == "anthropic":
                return "".join(b.get("text", "") for b in d.get("content", [])), {}
            return d['choices'][0]['message'].get('content') or '', d.get('usage', {})
        except error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code not in (429, 500, 502, 503, 504):
                raise RuntimeError(f"HTTP {e.code}: {e.read().decode()[:160]}")
        except Exception as e:
            last = type(e).__name__
        time.sleep(min(30.0, 1.5 * (1.9 ** attempt)) * (0.6 + random.random() * 0.8))
    raise RuntimeError(f"重试耗尽（{last}）")


def norm(s):
    """比对用的归一化：去空白、统一标点。不改动入库文本。"""
    s = re.sub(r'\s+', '', s)
    for a, b in [(',', '，'), (';', '；'), (':', '：'), ('(', '（'), (')', '）'), ('.', '。')]:
        s = s.replace(a, b)
    return s.rstrip('。；')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pdf-dir', required=True)
    ap.add_argument('--only', default=None)
    ap.add_argument('--runs', type=int, default=3)
    ap.add_argument('--concurrency', type=int, default=24)
    ap.add_argument('--dpi', type=int, default=150)
    ap.add_argument('--out', default=str(ROOT / 'tools/out/xueye-raw.jsonl'))
    a = ap.parse_args()

    base, key, model = os.environ['MIMO_BASE'], os.environ['MIMO_KEY'], os.environ.get('MIMO_MODEL', 'mimo-v2.5')
    CACHE.mkdir(exist_ok=True)

    idx = [json.loads(l) for l in INDEX.open(encoding='utf-8')]
    targets = [r for r in idx
               if (set(r.get('blocks') or []) & set(TARGET_BLOCKS) or r.get('section') == '学业质量')
               and (not a.only or a.only in r['subject'])]
    # 学业要求常跨页续写：把命中页的下一页也带上，避免截断（下一页无内容会返回 #NONE）
    have = {(r['subject'], r['page']) for r in targets}
    extra = [{'subject': r['subject'], 'page': r['page'] + 1, 'stage': r['stage'],
              'domain': r['domain'], 'heading': '(续页)'} for r in targets
             if (r['subject'], r['page'] + 1) not in have]
    targets = sorted(targets + extra, key=lambda r: (r['subject'], r['page']))
    print(f"目标页 {len(targets)}（其中续页 {len(extra)}）· {a.runs} 次投票 · 并发 {a.concurrency}")

    docs = {p.stem: fitz.open(p) for p in Path(a.pdf_dir).glob('*.pdf')}
    jobs = [(t, r) for t in targets for r in range(a.runs)]

    def work(job):
        t, r = job
        doc = docs[t['subject']]
        if t['page'] > doc.page_count:
            return t, r, '#NONE'
        png = doc[t['page'] - 1].get_pixmap(dpi=a.dpi).tobytes('png')
        h = hashlib.sha256(png + PROMPT.encode() + str(r).encode()).hexdigest()[:24]
        cf = CACHE / f"{h}.json"
        if cf.exists():
            return t, r, json.loads(cf.read_text())['content']
        try:
            txt, _ = call(png, base, key, model)
        except Exception as e:
            return t, r, f"#FAILED {e}"
        cf.write_text(json.dumps({'content': txt}, ensure_ascii=False))
        return t, r, txt

    t0 = time.time()
    got = collections.defaultdict(dict)
    with ThreadPoolExecutor(a.concurrency) as ex:
        for n, (t, r, txt) in enumerate(ex.map(work, jobs), 1):
            got[(t['subject'], t['page'])][r] = (t, txt)
            if n % 50 == 0 or n == len(jobs):
                print(f"  {n}/{len(jobs)}（{time.time()-t0:.0f}s）", flush=True)

    # ---- 页级字符流投票 ----
    # 教训：按「整行精确匹配」投票是错的。三次转写的文字可以完全一致，只是断行不同
    #（有的把分号复句整句放一行，有的在每个分号处断开），行级比对会把它们全判成分歧。
    # 正确单位是**页级字符流**：先拼成一整段比对，断句由我们确定性地做，
    # 这样直接消掉一整类方差，剩下的分歧才是真的转写差异。
    SENT_SPLIT = re.compile(r'(?<=[。；;])')

    rows, conflicts = [], []
    for (subj, page), runs in sorted(got.items()):
        t = runs[0][0]
        streams = []          # [(块名列表, 拼接文本, 原始行)]
        for r in range(a.runs):
            lines = [l.strip() for l in runs[r][1].strip().split('\n') if l.strip()]
            lines = [l for l in lines if l != '#NONE' and not l.startswith('#FAILED')]
            body, block, secs = [], '', []
            for l in lines:
                if l.startswith('@'):
                    block = l.lstrip('@').strip(); continue
                if l.startswith('#'):
                    secs.append(l.lstrip('#').strip()); continue
                body.append((block, l))
            streams.append((secs, ''.join(x[1] for x in body), body))
        if not any(st[1] for st in streams):
            continue

        # 最长的一次作基准（截断是主要失败模式，长的那次信息更全）
        ref_i = max(range(len(streams)), key=lambda i: len(streams[i][1]))
        secs, ref_text, ref_body = streams[ref_i]
        # 只和「没摆烂」的跑次比：实测 75% 的分歧是某一次直接返回几个字符甚至空，
        # 那是模型 bail 掉了，不是看错字。拿它当分歧算，会把真正的转写差异淹没掉。
        BAIL = 0.8            # 长度不足最长次 80% 视为该次未完成，不参与一致性判定
        peers = [st[1] for i, st in enumerate(streams)
                 if i != ref_i and st[1] and len(st[1]) >= BAIL * len(ref_text)]
        bailed = a.runs - 1 - len(peers)
        sims = [difflib.SequenceMatcher(None, norm(ref_text), norm(x)).ratio() for x in peers]
        page_agree = min(sims) if sims else (0.0 if bailed == a.runs - 1 else 1.0)

        # 断句：由我们做，不依赖模型的断行
        block_of = {}
        for blk, line in ref_body:
            for piece in SENT_SPLIT.split(line):
                if piece.strip():
                    block_of[piece.strip()] = blk
        sentences = [x.strip() for x in SENT_SPLIT.split(ref_text) if len(x.strip()) >= 6]

        for sec in secs:
            rows.append({'subject': subj, 'page': page, 'stage': t.get('stage') or '',
                         'domain': t.get('domain') or '', 'heading': t.get('heading') or '',
                         'block': '', 'kind': 'section', 'text': sec, 'agree': f"{page_agree:.2f}"})
        for sent in sentences:
            rows.append({'subject': subj, 'page': page, 'stage': t.get('stage') or '',
                         'domain': t.get('domain') or '', 'heading': t.get('heading') or '',
                         'block': block_of.get(sent, ''), 'kind': 'sentence',
                         'text': sent, 'agree': f"{page_agree:.2f}"})
        if page_agree < 0.98:
            conflicts.append({'subject': subj, 'page': page, 'agree': round(page_agree, 3),
                              'bailedRuns': bailed, 'lengths': [len(st[1]) for st in streams],
                              'reason': '仅一次跑出内容，无可比对' if not peers else '内容差异',
                              'texts': [st[1][:600] for st in streams]})

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    if conflicts:
        out.with_suffix('.conflicts.json').write_text(
            json.dumps(conflicts, ensure_ascii=False, indent=1), encoding='utf-8')

    sents = [r for r in rows if r['kind'] == 'sentence']
    pages_all = len({(r['subject'], r['page']) for r in rows})
    clean = pages_all - len(conflicts)
    print(f"\n用时 {time.time()-t0:.0f}s")
    print(f"转写句子 {len(sents)} 条（另有 {len(rows)-len(sents)} 个小节标题）→ {out}")
    print(f"  页级字符流一致（≥0.98）{clean}/{pages_all} = {clean/max(1,pages_all):.1%}"
          f"，{len(conflicts)} 页进复核队列")
    if conflicts:
        import statistics as st_
        print(f"  分歧页相似度中位数 {st_.median(c['agree'] for c in conflicts):.3f}")
    print("  按学科:", dict(collections.Counter(r['subject'] for r in sents).most_common()))


if __name__ == '__main__':
    main()
