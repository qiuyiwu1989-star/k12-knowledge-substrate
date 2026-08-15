#!/usr/bin/env python3
"""
to_lists.py — 把 extract_pages.py 的转写产物转成 L1 清单条目（lists/*.jsonl）。

只做格式转换和溯源标注，不做任何判断：
  · stage 来自课标原文的分组标题（权威）
  · level（具体年级）一律留空 —— 课标里没有年级，只能由 L2 教材编排层提供
  · 每条带 extraction.agree 投票一致度和 srcPage，转写是机器做的必须留痕
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'tools' / 'out'


def load(name):
    return [json.loads(l) for l in (OUT / name).open(encoding='utf-8')]


def norm(s):
    return re.sub(r'\s+', '', str(s)).strip()


def write(rel, rows):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f"  → {rel}  {len(rows)} 条")
    return len(rows)


# ---------- 附录5 常用字表 3500 字 ----------
rows, seq_seen = [], {}
for r in load('语文-zibiao-77-109.jsonl'):
    k = str(r['key'])
    if not k.isdigit():
        continue                      # 音序字母、标题行不入库
    table = '字表一' if r.get('seq', 0) == 0 else '字表二'
    ch = norm(r['value'])
    if len(ch) != 1:
        print(f"  ⚠ 跳过异常条目 p{r['page']} {k} {ch!r}", file=sys.stderr); continue
    rows.append({
        "listId": "lst_hanzi-changyong-3500", "key": ch, "kind": "HANZI",
        "stage": "G1-9", "level": None, "seq": int(k),
        "tags": [table, "写" if table == '字表一' else "认"],
        "anchorIds": [],
        "meta": {"table": table},
        "source": "义务教育语文课程标准（2022年版）附录5 义务教育语文课程常用字表",
        "extraction": {"srcPage": r['page'], "agree": r['agree'], "method": "vlm-5vote"},
        "schemaVersion": "0.1.0",
    })
n1 = sum(1 for r in rows if r['meta']['table'] == '字表一')
n2 = len(rows) - n1
print(f"常用字表：字表一 {n1} + 字表二 {n2} = {len(rows)}（官方 2500+1000=3500）")
write('lists/hanzi/changyong-3500.jsonl', rows)

# ---------- 附录4 识字写字教学基本字表 300 字 ----------
rows, stroke = [], None
for r in load('语文-jibenzi-73-76.jsonl'):
    v = norm(r['value'])
    if r['key'] == '#':
        m = re.match(r'^(\d+)画', v)
        if m:
            stroke = int(m.group(1))
        continue
    if v == '画' or re.fullmatch(r'\d+', v) or not v:
        continue                      # 「N画」被拆成两格的残片
    rows.append({
        "listId": "lst_hanzi-jiben-300", "key": v, "kind": "HANZI",
        "stage": "G1-2", "level": None, "seq": None,
        # 笔画分组不可靠：模型对无编号表格是「按行」读的（实测 p76 证实），
        # 跨栏时笔画标题的归属会错乱，所以这里不落 strokes，等人工复核补。
        "tags": ["基本字", "写"],
        "anchorIds": [],
        "meta": {"strokes": None, "needsReview": "笔画分组待人工核；本表无连号，无法机械校验"},
        "source": "义务教育语文课程标准（2022年版）附录4 识字、写字教学基本字表",
        "extraction": {"srcPage": r['page'], "agree": r['agree'], "method": "vlm-5vote"},
        "schemaVersion": "0.1.0",
    })
print(f"基本字表：{len(rows)}（官方 300）{'✓' if len(rows) == 300 else '✗'}")
write('lists/hanzi/jiben-300.jsonl', rows)

# ---------- 附录1 优秀诗文背诵推荐篇目 135 篇 ----------
STAGE = {0: "G1-6", 1: "G7-9"}
rows = []
for r in load('语文-pianmu-65-70.jsonl'):
    if not str(r['key']).isdigit():
        continue
    v = r['value'] if isinstance(r['value'], list) else [r['value'], '', '']
    title, first, author = (list(v) + ['', '', ''])[:3]
    title = norm(title)
    # 少数票把「篇名（首句）」写在了一格里，兜底拆开
    m = re.match(r'^(.+?)（(.+)）$', title)
    if m and not first:
        title, first = m.group(1), m.group(2)
    rows.append({
        "listId": "lst_recite-yiwu-135", "key": title, "kind": "RECITE",
        "stage": STAGE.get(r.get('seq', 0), None), "level": None, "seq": int(r['key']),
        "tags": ["必背"], "anchorIds": [],
        "meta": {"firstLine": norm(first), "author": norm(author)},
        "source": "义务教育语文课程标准（2022年版）附录1 优秀诗文背诵推荐篇目",
        "extraction": {"srcPage": r['page'], "agree": r['agree'], "method": "vlm-5vote"},
        "schemaVersion": "0.1.0",
    })
g1 = sum(1 for r in rows if r['stage'] == 'G1-6')
print(f"背诵篇目：G1-6 {g1} + G7-9 {len(rows)-g1} = {len(rows)}（官方 75+60=135）")

# 回挂已有锚点
anchors = {}
for f in (ROOT / 'anchors').rglob('*.jsonl'):
    for l in f.open(encoding='utf-8'):
        a = json.loads(l)
        anchors.setdefault(a['object'].replace('全诗', ''), a['id'])
hit = 0
for r in rows:
    if r['key'] in anchors:
        r['anchorIds'] = [anchors[r['key']]]; hit += 1
print(f"  回挂已有锚点 {hit} 条")
write('lists/recite/yiwu-135.jsonl', rows)
