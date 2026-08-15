#!/usr/bin/env python3
"""
reslice_en_appendix.py — 英语课标附录按**内容边界**重新切表。

为什么重做：原先 consolidate_cihui.py 用 `table_of(page)` 按页码分表，
而 p135 是一张混合页 —— 上半是三级词汇表的 Y/Z 尾巴（yard…zoo），
下半是数词表的开头（one/first…）。整页被划给数词表，于是 15 个 y/z 词
躺进了「数词表」，而词汇表少了它们。

边界其实一直在数据里：抽取 prompt 会把小标题输出成 `#X` / `##X` 行。
判据：标题文本是单个字母 → 音序标记（表内的 A/B/C…）；否则 → 换表。

    python3 tools/reslice_en_appendix.py [--write]

不加 --write 只报告，不落盘。
"""
import argparse, collections, hashlib, json, re, sys
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from extract_pages import PROMPTS  # noqa: E402

PDF = '/private/tmp/claude-501/-Users-qiu-Documents/b12cd2ef-e387-4206-a1b0-5a4144871447/scratchpad/kebiao/英语.pdf'
CACHE = ROOT / 'tools/.cache'
PAGES = range(94, 140)
RUNS = 5
VOTE = 3          # 5 次里出现 ≥3 次才采纳

SRC = '义务教育英语课程标准（2022年版）附录3 词汇表及相关附表'


def norm(w):
    """投票用的归一键。不归一时 `colour (AmE color)` 和 `colour(AmE color)`
    会各得 2 票，双双入选 —— 二级表曾因此从 505 涨到 1012。"""
    w = re.sub(r'\s+', ' ', w.strip().lower())
    w = re.sub(r'\s*([(（/])\s*', r'\1', w)
    w = re.sub(r'\s*([)）])', r'\1', w)
    return w.rstrip('*＊ ').strip()


# 附录里到底有哪几张表是**已知的**，用白名单认，不靠「是不是单个字母」猜。
# 教训：靠猜时，模型某一次把词条 `X-ray`、`a / an *` 输成了 `#` 开头的标题行，
# 于是凭空多出两张「表」，1521 个词被划进一张叫「a / an *」的表里。
SECTIONS = [
    (re.compile(r'二级词汇表'),                 '二级词汇表'),
    (re.compile(r'三级词汇表'),                 '三级词汇表'),
    (re.compile(r'数词表'),                     '数词表'),
    (re.compile(r'月份|星期'),                  '月份、星期词汇表'),
    (re.compile(r'地理名称'),                   '部分地理名称及相关信息'),
    (re.compile(r'组织机构名称缩写|名称缩写'),  '部分国家、重要组织机构名称缩写'),
    (re.compile(r'节日名称|中国文化专有名词'),  '部分重要节日名称、中国文化专有名词'),
]


def match_section(t):
    """标题文本 → 规范段名；不是已知表名就返回 None（当音序标记忽略）"""
    for pat, name in SECTIONS:
        if pat.search(t):
            return name
    return None


# 表内的栏目标签，不是词条。原表里「月份」「星期」是分组小标题，
# 「n.」「n., adj.」是词性栏的表头，都被转写成了普通行。
JUNK = re.compile(r'^(月份|星期|基数词|序数词|[a-z]{1,4}\.(,\s*[a-z]{1,4}\.)*)$', re.I)


def is_junk(w):
    return bool(JUNK.fullmatch(w.strip()))


def read_runs(doc):
    """→ {page: [run0_lines, run1_lines, ...]}"""
    out = {}
    for pg in PAGES:
        png = doc[pg - 1].get_pixmap(dpi=150).tobytes('png')
        runs = []
        for r in range(RUNS):
            h = hashlib.sha256(png + PROMPTS['cihui'].encode() + str(r).encode()).hexdigest()[:24]
            f = CACHE / f"{h}.json"
            if not f.exists():
                continue
            runs.append([l.rstrip() for l in json.loads(f.read_text())['content'].split('\n') if l.strip()])
        out[pg] = runs
    return out


def sectionize(runs_by_page):
    """按标题切段。返回 [(section, page, order, word)]，section 跨页延续。

    同时做集合投票：同一页同一段里，一个词在 ≥VOTE 次转写中出现才采纳。
    顺序取首次出现该词的那一次转写里的位置（各次在 temperature=0 下高度一致）。
    """
    section = '二级词汇表'          # p94 起是词汇表正文，二级在前
    rows, seen_global = [], set()
    for pg in sorted(runs_by_page):
        runs = runs_by_page[pg]
        if not runs:
            continue
        votes = collections.Counter()
        first_pos, surface = {}, collections.defaultdict(collections.Counter)
        end_section = collections.Counter()          # 各次转写走到页尾时停在哪段 → 投票
        for lines in runs:
            cur = section
            for pos, line in enumerate(lines):
                s = line.strip()
                if s.startswith('#'):
                    m = match_section(s.lstrip('#').strip())
                    if m:
                        cur = m
                    continue                          # 音序标记/噪声，跳过
                w = s.split('\t')[-1].strip()
                if not w or is_junk(w):
                    continue
                k = (cur, norm(w))
                votes[k] += 1
                surface[k][w] += 1
                first_pos.setdefault(k, pos)
            end_section[cur] += 1
        # 页尾所在段也要投票 —— 单看一次转写会被它的转写噪声带偏
        section = end_section.most_common(1)[0][0]

        for k, n in votes.items():
            if n < VOTE:
                continue
            sect, nk = k
            if (sect, nk) in seen_global:            # 跨页重复识别
                continue
            seen_global.add((sect, nk))
            rows.append({
                'section': sect, 'page': pg, 'pos': first_pos[k],
                'word': surface[k].most_common(1)[0][0], 'votes': n,
            })
    rows.sort(key=lambda r: (r['page'], r['pos']))
    return rows


# ── 表定义：段名 → (listId, stage, 是否字母序) ──────────────────────
TABLES = {
    '二级词汇表':                     ('lst_en-vocab-l2', 'G3-6', True),
    '三级词汇表':                     ('lst_en-vocab-l3', 'G7-9', True),
    '数词表':                         ('lst_en-numerals', 'G3-9', False),
    '月份、星期词汇表':               ('lst_en-calendar', 'G3-9', False),
    '部分地理名称及相关信息':         ('lst_en-geo', 'G3-9', True),
    '部分国家、重要组织机构名称缩写': ('lst_en-orgabbr', 'G7-9', False),
    '部分重要节日名称、中国文化专有名词': ('lst_en-culture', 'G3-9', False),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--write', action='store_true')
    a = ap.parse_args()

    doc = fitz.open(PDF)
    rows = sectionize(read_runs(doc))

    by = collections.defaultdict(list)
    for r in rows:
        by[r['section']].append(r)

    print("═══ 按标题切出来的段 ═══")
    for sect, items in sorted(by.items(), key=lambda kv: -len(kv[1])):
        known = '✓' if sect in TABLES else '✗ 未登记'
        pages = sorted({i['page'] for i in items})
        print(f"  {sect:<34}{len(items):>5} 条  p{pages[0]}–p{pages[-1]}  {known}")
        print(f"      首: {[i['word'] for i in items[:4]]}")
        print(f"      末: {[i['word'] for i in items[-4:]]}")

    # ── 机械校验 ──────────────────────────────────────────────
    print("\n═══ 机械校验 ═══")
    # 课标原文：「三级词汇表共收录 1600 个单词，含二级词汇 505 个（用 * 标注）」。
    # 所以 505 是 L3 里**带星词**的数量，不是二级表本身的大小 —— 早先拿 505 去
    # 卡二级表，永远差 -47，看起来像漏抽，其实是拿错了尺子。
    ok = True
    l3 = by.get('三级词汇表', [])
    starred = sum(1 for i in l3 if '*' in i['word'] or '＊' in i['word'])
    print(f"  三级表总量 {len(l3)}（声明 1600，差 {len(l3) - 1600:+d}）")
    print(f"  三级表带星词 {starred}（声明 505，差 {starred - 505:+d}）")
    if abs(len(l3) - 1600) / 1600 > 0.06:
        print("    ✗ 总量偏差过大"); ok = False
    if abs(starred - 505) / 505 > 0.08:
        print("    ✗ 带星数偏差过大"); ok = False

    for sect, items in by.items():
        if sect not in TABLES:
            continue
        _, _, alpha = TABLES[sect]
        line = f"  {sect:<34}{len(items):>5} 条"
        if alpha:
            # 落盘时会按字母序重排（源表本来就是字母序，排序=还原而非猜测），
            # 所以这里报的是**抽取阶段**的乱序程度，是质量信号，不是最终产物的缺陷。
            ws = [norm(i['word']) for i in items]
            bad = sum(1 for x, y in zip(ws, ws[1:]) if y < x)
            line += f"  抽取期乱序 {bad} 处（落盘时按字母序还原）"
        print(line)

    if not a.write:
        print("\n（未落盘。确认无误后加 --write）")
        return 0 if ok else 1

    # ── 落盘 ──────────────────────────────────────────────────
    LISTS = ROOT / 'lists/vocab'
    for old in ['en-abbr.jsonl', 'en-calendar.jsonl', 'en-numerals.jsonl',
                'en-vocab-l2.jsonl', 'en-vocab-l3.jsonl']:
        (LISTS / old).unlink(missing_ok=True)

    anchors = json.loads((ROOT / 'tools/out/en-list-anchors.json').read_text(encoding='utf-8')) \
        if (ROOT / 'tools/out/en-list-anchors.json').exists() else {}

    written = {}
    for sect, items in by.items():
        if sect not in TABLES:
            print(f"  ! 段「{sect}」未登记，跳过（{len(items)} 条）")
            continue
        list_id, stage, alpha = TABLES[sect]
        if alpha:
            items = sorted(items, key=lambda r: norm(r['word']))   # 源表即字母序，排序=还原
        f = LISTS / f"{list_id.replace('lst_', '')}.jsonl"
        with f.open('w', encoding='utf-8') as fh:
            for i, r in enumerate(items, 1):
                fh.write(json.dumps({
                    'listId': list_id, 'key': r['word'], 'kind': 'WORD',
                    'stage': stage, 'level': None, 'seq': i, 'tags': [sect],
                    'anchorIds': anchors.get(list_id, []),
                    'meta': {'table': sect},
                    'source': SRC,
                    'extraction': {'srcPage': r['page'], 'agree': f"≥{VOTE}/{RUNS}",
                                   'method': 'vlm-5vote-setconsensus+headingslice'},
                    'schemaVersion': '0.1.0',
                }, ensure_ascii=False) + '\n')
        written[list_id] = len(items)
        print(f"  → {f.name}  {len(items)} 条")
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
