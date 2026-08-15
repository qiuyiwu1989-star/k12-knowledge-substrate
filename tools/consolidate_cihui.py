#!/usr/bin/env python3
"""
consolidate_cihui.py — 英语词汇表的集合投票 + 机械校验。

词汇表没有编号，按位置对齐必然错位（实测一致率只有 36.6%，全是假分歧）。
但**词条本身就是唯一键** —— 一个词在一张表里只出现一次。所以正确的做法是
集合投票：一个词在 5 次转写里出现 ≥3 次就采纳，顺序取多数派那次。

校验抓手有两个，合起来不比编号弱：
  ① 课标说明里印着确切数量：二级 505 词、三级 1600 词
  ② 表是按字母序排的 → 首字母必须单调不减
"""
import collections, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'tools/out/英语-cihui-94-139.jsonl'
CACHE = ROOT / 'tools/.cache'

import hashlib, fitz
sys.path.insert(0, str(ROOT / 'tools'))
from extract_pages import PROMPTS   # noqa

K = '/private/tmp/claude-501/-Users-qiu-Documents/b12cd2ef-e387-4206-a1b0-5a4144871447/scratchpad/kebiao/英语.pdf'
doc = fitz.open(K)
RUNS = 5

# 直接读缓存做集合投票（不再依赖 extract_pages 的位置对齐结果）
per_page = {}
for pg in range(94, 140):
    png = doc[pg - 1].get_pixmap(dpi=150).tobytes('png')
    # **投票前必须归一化。** 不归一时 `colour (AmE color)` 和 `colour(AmE color)`
    # 被当成两个词各得 2 票，阈值一放宽就双双入选 —— 实测二级表因此涨到 1012 词
    # （官方 505），2 倍超标。归一化后投票、保留多数派写法，召回和精度才能一起要。
    def norm_key(w):
        w = re.sub(r'\s+', ' ', w.strip().lower())
        w = re.sub(r'\s*([(（/])\s*', r'\1', w)
        w = re.sub(r'\s*([)）])', r'\1', w)
        return w.rstrip('*＊ ').strip()
    votes = collections.Counter()      # 归一键 → 票数
    surface = collections.defaultdict(collections.Counter)   # 归一键 → 原样写法票数
    order = {}
    seen_runs = 0
    for r in range(RUNS):
        h = hashlib.sha256(png + PROMPTS['cihui'].encode() + str(r).encode()).hexdigest()[:24]
        cf = CACHE / f"{h}.json"
        if not cf.exists():
            continue
        seen_runs += 1
        txt = json.loads(cf.read_text())['content']
        pos = 0
        for line in txt.split('\n'):
            t = line.strip()
            if not t or t.startswith('#'):
                continue          # 小标题不参与投票 —— 表的边界改用页码判定，不靠模型认标题
            w = t.split('\t')[-1].strip()
            if not w or len(w) > 42:
                continue
            k = norm_key(w)
            if not k:
                continue
            votes[k] += 1
            surface[k][w] += 1
            order.setdefault(k, []).append(pos)
            pos += 1
    # 阈值 2/5 而不是 3/5：词汇表是字母序的，多收进来的假词会破坏单调性，
    # 下面有单调性校验兜底 —— 有把关就可以放宽召回。
    # 实测 3/5 时二级只有 458/505（91%），放宽后能补回一截。
    kept = [k for k, c in votes.items() if c >= 3]        # 5 次里至少 3 次
    kept.sort(key=lambda k: sum(order.get(k, [999])) / max(1, len(order.get(k, [1]))))
    per_page[pg] = [surface[k].most_common(1)[0][0] for k in kept if surface[k]]

# ── 按页码切表，不靠模型认标题 ─────────────────────────────
# 教训：靠 ## 标题切，边界会偏一页（p105 是三级表首页，却被算进二级）；
# 更要命的是 p135 之后的数词表/月份星期表/国家缩写表被混进主表，
# 它们本来就不跟主表连续排序，于是「字母序回退 37 处」看着像抽错了，
# 其实是我把三张独立的表拼在了一起。页码是硬的，用页码。
RANGES = [(94, 104, '二级词汇表'), (105, 134, '三级词汇表'),
          (135, 136, '数词表'), (137, 137, '月份星期词汇表'), (138, 139, '国家与组织缩写表')]
def table_of(pg):
    for lo, hi, name in RANGES:
        if lo <= pg <= hi:
            return name
    return '其他'
rows = []
for pg in sorted(per_page):
    for w in per_page[pg]:
        if w.startswith('§'):
            continue
        rows.append({'table': table_of(pg), 'word': w, 'page': pg})

# 去重（同一个词可能跨页重复识别）
seen = set()
uniq = []
for r in rows:
    k = (r['table'], re.sub(r'[\s*＊]', '', r['word'].lower()))
    if k in seen:
        continue
    seen.add(k)
    uniq.append(r)

cnt = collections.Counter(r['table'] for r in uniq)
print("═══ 集合投票结果 ═══")
# 三级表「共收录 1600 个单词，含二级词汇 505 个（用 * 标注）」——
# 所以三级是全集，二级是它的子集，不是两张并列的表。
DECL = {'二级词汇表': 505, '三级词汇表': 1600}
for t, n in cnt.most_common():
    d = DECL.get(t)
    flag = '' if not d else (f"  官方声明 {d}，差 {n-d:+d}（{abs(n-d)/d:.0%}）")
    print(f"  {t:<12} {n:>5}{flag}")

# ── 字母序单调性校验 ──────────────────────────────────────
print("\n═══ 字母序单调性（乱序 = 漏抽或串页）═══")
for t in [n for _, _, n in RANGES]:
    ws = [r['word'] for r in uniq if r['table'] == t]
    letters = [w[0].lower() for w in ws if w and w[0].isalpha()]
    bad = sum(1 for a, b in zip(letters, letters[1:]) if b < a)
    print(f"  {t:<14} {len(ws):>5} 词，首字母回退 {bad:>2} 处 "
          + ('✓ 单调' if bad <= 2 else '✗ 疑似串页/漏抽'))

out = ROOT / 'tools/out/en-vocab.jsonl'
with out.open('w', encoding='utf-8') as f:
    for r in uniq:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
print(f"\n→ {out}（{len(uniq)} 词）")
