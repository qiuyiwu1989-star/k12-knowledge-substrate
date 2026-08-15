#!/usr/bin/env python3
"""
extract_pages.py — 用多模态模型逐页忠实转写课标扫描件。

设计原则（非常重要）：
  1. **只转写，不判断。** 本工具的产出是「忠实逐字转写」，不是锚点。
     从转写切分出可判定能力断言是下一道独立工序——两者混在一起做，
     转写错误和判断错误就分不开了，出问题无法定位。
  2. **N 次投票 + 机械校验。** 带连号的表格（字表、篇目）抽完检查编号
     连续性，这是 100% 机械可验的；不一致的条目进复核队列。
  3. **可续跑。** 每页每次调用的原始响应落盘缓存，重跑不重复烧 token。

用法：
  export MIMO_BASE=... MIMO_KEY=... MIMO_MODEL=mimo-v2.5
  python3 tools/extract_pages.py --pdf 语文.pdf --pages 77-109 --kind zibiao --runs 5

实测要点（2026-08-15，mimo-v2.5）：
  · mimo-v2.5-pro 不支持图像，视觉只能用 mimo-v2.5
  · 必须 thinking:{"type":"disabled"}；reasoning_effort:"none" 已失效（400）
  · 关掉 thinking 后模型会把思考写进 content，靠 prompt 末句硬约束输出形态
  · 用 max_completion_tokens，不要用 max_tokens（会被 reasoning 吃光返回空串）
"""
import argparse, base64, collections, hashlib, json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib import request, error

import fitz  # PyMuPDF

CACHE = Path(__file__).parent / '.cache'

# 静态前缀在前、图片在最后 —— prompt 缓存要求变量内容置于末尾
PROMPTS = {
    'zibiao': """逐字转写这一页的全部表格内容。这是《义务教育语文课程标准（2022年版）》常用字表的一页，条目形如「编号 汉字」，分多栏排列。

输出规则：
- 每行一个条目，格式为 编号<TAB>汉字
- 按从左到右、从上到下的阅读顺序（先读完第一栏，再读第二栏）
- 表中作为音序标记的单个大写英文字母（A/B/C…）也要输出，格式为 <TAB>字母（编号位置留空）
- 若本页含「字表一」「字表二」等小标题，输出一行 #字表一 或 #字表二
- 不要输出页眉、页脚、页码、书名
不解释、不总结、不写任何前言后语。第一个字符必须是第一个条目的第一个字符。""",

    'jibenzi': """逐字转写这一页的全部内容。这是《义务教育语文课程标准（2022年版）》附录4「识字、写字教学基本字表」的一页，共300字，按笔画数分组排列，分多栏。

输出规则：
- 遇到「N画」这样的笔画分组标题，输出一行 #N画
- 其余每行一个汉字，格式为 <TAB>汉字（每行只有一个汉字）
- 按从左到右、从上到下的阅读顺序（先读完第一栏，再读第二栏）
- 括号中的偏旁变体（如「刀（刂）」）原样保留在同一行
- 不要输出页眉、页脚、页码、书名、说明性段落
不解释、不总结、不写任何前言后语。第一个字符必须是第一个条目的第一个字符。""",

    'cihui': """逐词转写这一页英语词汇表的全部内容。这是《义务教育英语课程标准（2022年版）》附录3 词汇表的一页，按字母序分多栏排列。

输出规则：
- 每行一个词条，格式为 <TAB>词条
- 按从左到右、从上到下的阅读顺序（先读完第一栏，再读第二栏）
- 词条**原样保留**括号和斜杠：`a / an`、`be (am, is, are)`、`colour (AmE color)`、`AI (= artificial intelligence)`
- 词条后的星号 `*` 原样保留（它标记三级新增词）
- 遇到单个大写字母的音序标题（A/B/C…），输出一行 #A
- 遇到「二级词汇表」「三级词汇表」这类小标题，输出一行 ##标题
- 不要输出页眉、页脚、页码、说明段落
不解释、不总结、不写任何前言后语。第一个字符必须是 # 或制表符。""",

    'buguize': """逐行转写这一页「不规则动词表」的内容。三列：动词原形 / 过去式 / 过去分词。

输出规则：
- 每行一个动词，格式为 原形<TAB>过去式<TAB>过去分词
- 一格里有多个形式的用斜杠原样保留，如 `dreamt / dreamed`、`got / gotten`、`burnt / burned`
- 破折号「—」原样保留（表示该形式不存在）
- 括号注释原样保留，如 `hang (悬挂)`、`be (am, is, are)`
- 不要输出表头「动词/过去式/过去分词」，不要输出页眉页脚页码
不解释、不总结。第一个字符必须是第一个动词的第一个字母。""",

    'yufa': """逐行转写这一页「语法项目表」的内容。这是《义务教育英语课程标准（2022年版）》附录4，是一份三层的层级清单。

层级形如：
    一、词类            ← 第一层，中文数字加顿号
    （一）名词          ← 第二层，圆括号里的中文数字
    1. 可数名词及其单、复数   ← 条目，阿拉伯数字加点

输出规则（每行三或四段，用制表符分隔）：
- 第一层输出：L1<TAB>序号<TAB>标题文字（如 `L1	一	词类`）
- 第二层输出：L2<TAB>序号<TAB>标题文字（如 `L2	一	名词`）
- 条目输出：I<TAB>序号<TAB>条目文字（如 `I	1	可数名词及其单、复数`）
- 「+」号可能出现在行首（如 `+（八）主谓一致`）也可能在行末。**无论在哪**，都在第四段输出一个 +
  （如 `L2	八	主谓一致	+`）。第三段的文字里不要保留这个 +
- 序号只写序号本身，不带顿号、圆括号、点号
- 条目文字去掉行首的「1.」，只保留内容
- 不要输出页眉、页脚、页码、书名、「说明」段落及其解释文字
不解释、不总结。第一个字符必须是 L 或 I。""",

    'pianmu': """逐字转写这一页的全部篇目列表。这是《义务教育语文课程标准（2022年版）》附录1「优秀诗文背诵推荐篇目」的一页，条目形如「编号 篇名（首句）  作者」。

输出规则：
- 每行一个条目，格式为 编号<TAB>篇名<TAB>首句<TAB>作者
- 首句是篇名后圆括号里的内容；没有圆括号时首句留空
- 作者是行末右对齐的部分；作者位置若是《诗经》这类书名，原样输出
- 若本页含「1～6年级（75篇）」「7～9年级（60篇）」这样的分组标题，输出一行 #标题原文
- 不要输出页眉、页脚、页码、书名、说明性段落
不解释、不总结、不写任何前言后语。第一个字符必须是第一个条目的第一个字符。""",
}


def call_vlm(png_bytes, prompt, run_idx, base, key, model, timeout=300):
    b64 = base64.b64encode(png_bytes).decode()
    body = {
        "model": model,
        "temperature": 0,
        "max_completion_tokens": 8000,
        "thinking": {"type": "disabled"},
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ]}],
    }
    req = request.Request(base + "/v1/chat/completions", data=json.dumps(body).encode(),
                          headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    delay = 2.0
    for attempt in range(6):
        try:
            d = json.load(request.urlopen(req, timeout=timeout))
            return d['choices'][0]['message'].get('content') or '', d.get('usage', {})
        except error.HTTPError as e:
            # 429 是限流不是失败 —— 退避重试，不计入任务级失败
            if e.code in (429, 500, 502, 503, 504) and attempt < 5:
                time.sleep(delay); delay *= 1.8; continue
            raise RuntimeError(f"HTTP {e.code}: {e.read().decode()[:200]}")
        except Exception:
            if attempt < 5:
                time.sleep(delay); delay *= 1.8; continue
            raise
    raise RuntimeError("重试耗尽")


def page_png(doc, idx, dpi=150):
    return doc[idx].get_pixmap(dpi=dpi).tobytes('png')


def parse(kind, text):
    """把一次转写解析成 [(序, 载荷)]，序用于投票对齐。"""
    rows = []
    for raw in text.strip().split('\n'):
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.lstrip().startswith('#'):
            rows.append(('#', line.strip().lstrip('#').strip()))
            continue
        parts = [p.strip() for p in line.split('\t')]
        if kind == 'cihui':
            if line.lstrip().startswith('##'):
                rows.append(('##', line.strip().lstrip('#').strip()))
            else:
                w = parts[-1].strip() if parts else ''
                if w:
                    rows.append(('@' + str(len(rows)), w))
            continue
        if kind == 'buguize':
            if len(parts) >= 3 and parts[0]:
                rows.append(('@' + str(len(rows)), tuple(parts[:3])))
            continue
        if kind == 'yufa':
            # L1/L2/I<TAB>序号<TAB>文字[<TAB>+]
            if len(parts) >= 3 and parts[0] in ('L1', 'L2', 'I'):
                plus = '+' if (len(parts) >= 4 and '+' in parts[3]) or parts[2].startswith('+') else ''
                txt = parts[2].lstrip('+＋').strip()
                item = (parts[0], parts[1], txt, plus)
                # 同一段连续重复原地丢弃。实测同一页各次转写行数在 19–23 之间摆动，
                # 差额全是模型把某一小节重复输出了一遍 —— 不在这里压平，
                # 位置对齐就会整段错位，投票结果虚低且并出重复条目。
                if rows and rows[-1][1] == item:
                    continue
                rows.append(('@' + str(len(rows)), item))
            continue
        if kind in ('zibiao', 'jibenzi'):
            if len(parts) >= 2 and parts[0]:
                rows.append((parts[0], parts[1]))
            elif len(parts) >= 2:
                rows.append(('@' + str(len(rows)), parts[1]))   # 无编号条目按位置对齐
            elif parts and parts[0]:
                m = re.match(r'^(\d+)\s*(\S+)$', parts[0])
                rows.append((m.group(1), m.group(2)) if m else ('@' + str(len(rows)), parts[0]))
        else:  # pianmu
            if parts and re.match(r'^\d+$', parts[0]):
                rows.append((parts[0], tuple(parts[1:] + [''] * (3 - len(parts[1:])))[:3]))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pdf', required=True)
    ap.add_argument('--pages', required=True, help='1-indexed，如 77-109 或 65-70')
    ap.add_argument('--kind', required=True, choices=list(PROMPTS))
    ap.add_argument('--runs', type=int, default=5)
    ap.add_argument('--concurrency', type=int, default=24)
    ap.add_argument('--out', default=None)
    a = ap.parse_args()

    base, key, model = os.environ['MIMO_BASE'], os.environ['MIMO_KEY'], os.environ.get('MIMO_MODEL', 'mimo-v2.5')
    lo, hi = (int(x) for x in a.pages.split('-')) if '-' in a.pages else (int(a.pages), int(a.pages))
    CACHE.mkdir(exist_ok=True)

    doc = fitz.open(a.pdf)
    pages = list(range(lo - 1, hi))
    print(f"页 {lo}–{hi}（{len(pages)} 页）· kind={a.kind} · {a.runs} 次投票 · 并发 {a.concurrency}")

    pngs = {i: page_png(doc, i) for i in pages}
    jobs = [(i, r) for i in pages for r in range(a.runs)]

    def work(job):
        i, r = job
        h = hashlib.sha256(pngs[i] + PROMPTS[a.kind].encode() + str(r).encode()).hexdigest()[:24]
        cf = CACHE / f"{h}.json"
        if cf.exists():
            return i, r, json.loads(cf.read_text())['content'], True
        txt, usage = call_vlm(pngs[i], PROMPTS[a.kind], r, base, key, model)
        cf.write_text(json.dumps({'page': i + 1, 'run': r, 'content': txt, 'usage': usage}, ensure_ascii=False))
        return i, r, txt, False

    t0 = time.time()
    results = collections.defaultdict(dict)
    cached = 0
    with ThreadPoolExecutor(a.concurrency) as ex:
        for n, (i, r, txt, hit) in enumerate(ex.map(work, jobs), 1):
            results[i][r] = txt
            cached += hit
            if n % 20 == 0 or n == len(jobs):
                print(f"  {n}/{len(jobs)} 调用完成（缓存命中 {cached}）", flush=True)
    print(f"  用时 {time.time() - t0:.1f}s")

    # ---- 投票 ----
    # 按「编号」而不是「位置」对齐：某一次跑多输出/少输出一行（比如把分组标题
    # 当成条目），位置对齐会让整页后续全部错位，投票结果虚低。编号是天然的锚点。
    def keyed(rows, page):
        """→ {(组序, 编号或位置键): 载荷}，组序在编号回退时 +1（一页里可能横跨两个分组）"""
        out, grp, prev = {}, 0, 0
        for pos, (k, v) in enumerate(rows):
            if k == '#':
                out[(grp, f'#{pos}')] = ('#', v)
                continue
            if str(k).isdigit():
                n = int(k)
                if n < prev:
                    grp += 1
                prev = n
                out[(grp, n)] = (k, v)
            else:
                out[(grp, f'{k}@{pos}')] = (k, v)
        return out

    # ── 防跑飞：给错页码时，模型会在非目标页上打转，一页吐上百行。
    #    实测把语法表页码写成 145-153（实际到 149），p153 一次吐了 894 行。
    #    行数中位数的 3 倍是硬上限，超了直接报错而不是产出垃圾。
    runaway = []
    for i in pages:
        counts = sorted(len(parse(a.kind, results[i][r])) for r in range(a.runs))
        med = counts[len(counts) // 2]
        if med > 200:
            runaway.append((i + 1, med))
    if runaway:
        print("  ✗ 疑似跑飞（页, 中位行数）:", runaway)
        print("    多半是页码给错了，模型在非目标页上打转。核对页码后重跑。")
        return 1

    out_rows, conflicts = [], []
    for i in pages:
        maps = [keyed(parse(a.kind, results[i][r]), i) for r in range(a.runs)]
        # 位置键形如 '@7@7' / '#12'，尾部那个数字才是页内顺序。
        # 教训：原先直接 str() 比较，'@10@10' < '@2@2'，整页条目被打乱成
        # 0,10,11,…,19,1,20,… —— 数据全对但顺序全错，而顺序正是字母序校验的依据。
        def _pos(k):
            m = re.search(r'(\d+)$', str(k))
            return int(m.group(1)) if m else 0
        allkeys = sorted(set().union(*[set(m) for m in maps]),
                         key=lambda x: (x[0], (0, x[1], 0) if isinstance(x[1], int)
                                              else (1, 0, _pos(x[1]))))
        for gk in allkeys:
            votes = [m.get(gk) for m in maps]
            c = collections.Counter(v for v in votes if v is not None)
            top, n = c.most_common(1)[0]
            if n < a.runs:
                conflicts.append({'page': i + 1, 'group': gk[0], 'key': str(gk[1]),
                                  'votes': [list(v) if v else None for v in votes]})
            out_rows.append({'page': i + 1, 'group': gk[0], 'key': top[0], 'value': top[1],
                             'agree': f"{n}/{a.runs}"})

    out = Path(a.out or f"tools/out/{Path(a.pdf).stem}-{a.kind}-{lo}-{hi}.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)

    # ---- 机械校验：分组内编号连续性（这是自验证类抽取的全部依据）----
    print(f"\n条目 {len(out_rows)} 行 → {out}")
    # 序列号必须全局判定：分组内的 group 只在页内有效，跨页要重新走一遍。
    # 页 68 同时含序列0 的尾（70–75）和序列1 的头（1–14），所以只能按顺序走、遇回退才切。
    merged, seq, prev = collections.defaultdict(list), 0, 0
    for r in out_rows:
        if not str(r['key']).isdigit():
            continue
        n = int(r['key'])
        if n < prev:
            seq += 1
        prev = n
        merged[seq].append(n)
        r['seq'] = seq
    ok = True
    for g, ns in sorted(merged.items()):
        ns = sorted(ns)
        miss = sorted(set(range(min(ns), max(ns) + 1)) - set(ns))
        dup = [k for k, v in collections.Counter(ns).items() if v > 1]
        flag = '✓' if not miss and not dup else '✗'
        ok &= not miss and not dup
        print(f"  {flag} 序列{g}: {len(ns)} 条，{min(ns)}–{max(ns)}"
              + (f"，缺号 {miss[:15]}" if miss else "，无缺号")
              + (f"，重号 {dup[:15]}" if dup else ""))

    with out.open('w', encoding='utf-8') as f:      # seq 计算完再落盘
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f"  {a.runs} 次全票一致率: {(len(out_rows) - len(conflicts)) / max(1, len(out_rows)):.1%}"
          f"（分歧 {len(conflicts)} 处）")
    if conflicts:
        cp = out.with_suffix('.conflicts.json')
        cp.write_text(json.dumps(conflicts, ensure_ascii=False, indent=1))
        print(f"  分歧已写入 {cp} —— 这些进人工复核队列")


if __name__ == '__main__':
    main()
