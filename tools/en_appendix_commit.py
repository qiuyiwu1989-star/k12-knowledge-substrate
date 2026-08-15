#!/usr/bin/env python3
"""
en_appendix_commit.py — 把重切后的英语附录落进 lists/ 与 anchors/。

做三件事：
  1. 建 3 条新锚点：地理名称、节日与文化专有名词、不规则动词表
  2. 修 4 条已有锚点的 itemCount（重切后条数变了）
  3. 落盘 8 张表（7 张附录表 + 不规则动词表）

itemCount 不是装饰字段 —— 插件用它算「3/299（1%）」这样的完成度，
错了会直接显示给家长看。重切改了条数就必须同步。

    python3 tools/en_appendix_commit.py
"""
import json, re, secrets, string, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from reslice_en_appendix import (  # noqa: E402
    read_runs, sectionize, norm, TABLES, SRC, VOTE, RUNS, PDF,
)
import fitz  # noqa: E402

ALNUM = string.ascii_letters + string.digits


def new_id(taken):
    """无语义 ID。ID 一旦被档案引用就不能变，所以不能带含义 —— 含义会过时。"""
    while True:
        i = 'ca_' + ''.join(secrets.choice(ALNUM) for _ in range(8))
        if i not in taken:
            taken.add(i)
            return i


def load_anchors():
    out = {}
    for f in sorted((ROOT / 'anchors').glob('*.jsonl')):
        for line in f.open(encoding='utf-8'):
            if line.strip():
                a = json.loads(line)
                out.setdefault(f.name, []).append(a)
    return out


# ── 段名 → 锚点。已有的写死 ID，新的留 None 由脚本生成 ───────────────
ANCHOR_FOR = {
    '二级词汇表': 'ca_vNZfgewe',
    '三级词汇表': 'ca_GF4KvJd2',
    '数词表': 'ca_CPrxFxbn',
    '月份、星期词汇表': 'ca_2EAmQTtU',
    '部分国家、重要组织机构名称缩写': 'ca_c2uXsvWR',
    '部分地理名称及相关信息': None,
    '部分重要节日名称、中国文化专有名词': None,
}

NEW_ANCHOR_SPEC = {
    '部分地理名称及相关信息': dict(
        statement='能说出常见国家、地区名称及其对应的国民与语言的英文表达',
        verb='说出', object='国家地区名称及国民语言的英文表达',
        stage=('G3', 'G9'), list_id='lst_en-geo',
        evidence=['看到 China 能说出 Chinese', '能区分国家名与国民/语言名的写法'],
        assessment='给{{name}}一个国家名，他能说出对应的国民和语言怎么说吗？',
    ),
    '部分重要节日名称、中国文化专有名词': dict(
        statement='能用英文说出常见节日名称与中国文化专有名词',
        verb='说出', object='节日名称与中国文化专有名词的英文表达',
        stage=('G3', 'G9'), list_id='lst_en-culture',
        evidence=['能说出春节、端午等节日的英文名', '能说出京剧、丝绸之路等文化词的英文表达'],
        assessment='{{name}}能用英文说出这些节日和文化词吗？',
    ),
}

VERB_ANCHOR = dict(
    statement='能说出并写出英语不规则动词的过去式和过去分词',
    verb='写出', object='不规则动词的过去式和过去分词',
    stage=('G7', 'G9'), list_id='lst_en-irregular-verbs',
    evidence=['给出动词原形能写出过去式与过去分词', '能识别 cost/cut 这类三态同形的动词'],
    assessment='给{{name}}报动词原形，他能写出过去式和过去分词吗？',
)


def mk_anchor(aid, spec, page_range, item_count):
    lo, hi = spec['stage']
    return {
        'id': aid, 'discipline': '英语', 'track': 'LIST', 'strand': '语言知识',
        'topic': None, 'dimension': None,
        'statement': spec['statement'], 'verb': spec['verb'], 'object': spec['object'],
        'type': 'LANGUAGE', 'literacy': ['语言能力'], 'cognitive': '掌握',
        'stageHint': {'min': lo, 'max': hi},
        'evidence': spec['evidence'], 'assessment': spec['assessment'],
        'evidenceSource': 'curriculum-appendix',
        'reviewStatus': 'auto-confirmed', 'reviewedBy': [],
        'deprecated': False, 'supersededBy': None,
        'autoConfirmBasis': [
            '来源：教育部《义务教育英语课程标准（2022年版）》附录，非模型生成',
            f'抽取经 {RUNS} 次集合投票（阈值 ≥{VOTE}）并按表头切段，不按页码切',
            '判定标准客观（说对/写对），不依赖教学判断',
        ],
        'provenance': {
            'srcSubject': '英语', 'srcPage': page_range[0],
            'srcPageRange': f'{page_range[0]}–{page_range[1]}',
            'method': 'curriculum-appendix', 'itemCount': item_count,
            'declaredCount': None,
        },
        'schemaVersion': '0.1.0',
    }


def main():
    doc = fitz.open(PDF)
    rows = sectionize(read_runs(doc))
    by = {}
    for r in rows:
        by.setdefault(r['section'], []).append(r)

    files = load_anchors()
    taken = {a['id'] for v in files.values() for a in v}

    # ── 1. 建新锚点 ───────────────────────────────────────────
    new_anchors = []
    for sect, spec in NEW_ANCHOR_SPEC.items():
        items = by.get(sect, [])
        if not items:
            print(f"  ! 段「{sect}」没抽到条目，跳过"); continue
        pages = sorted({i['page'] for i in items})
        aid = new_id(taken)
        ANCHOR_FOR[sect] = aid
        new_anchors.append(mk_anchor(aid, spec, (pages[0], pages[-1]), len(items)))
        print(f"  + {aid}  {spec['statement']}  {len(items)} 条")

    # 不规则动词表
    verbs = [json.loads(l) for l in (ROOT / 'tools/out/en-irregular-verbs.jsonl')
             .open(encoding='utf-8') if l.strip()]
    vaid = new_id(taken)
    new_anchors.append(mk_anchor(vaid, VERB_ANCHOR, (140, 144), len(verbs)))
    print(f"  + {vaid}  {VERB_ANCHOR['statement']}  {len(verbs)} 条")

    # ── 2. 修已有锚点的 itemCount ─────────────────────────────
    count_by_anchor = {ANCHOR_FOR[s]: len(v) for s, v in by.items() if ANCHOR_FOR.get(s)}
    changed = []
    for fname, arr in files.items():
        for a in arr:
            n = count_by_anchor.get(a['id'])
            if n is None:
                continue
            old = (a.get('provenance') or {}).get('itemCount')
            if old != n:
                a['provenance']['itemCount'] = n
                changed.append((a['id'], a['statement'], old, n))
    for aid, st, o, n in changed:
        print(f"  ~ {aid}  itemCount {o} → {n}   {st}")

    # ── 3. 落盘 ───────────────────────────────────────────────
    LISTS = ROOT / 'lists/vocab'
    for old in ['en-abbr.jsonl', 'en-calendar.jsonl', 'en-numerals.jsonl',
                'en-vocab-l2.jsonl', 'en-vocab-l3.jsonl']:
        (LISTS / old).unlink(missing_ok=True)

    def write_list(list_id, stage, sect, items, alpha, page_of, extra_tag=None):
        if alpha:
            items = sorted(items, key=lambda r: norm(r['key']))
        f = LISTS / f"{list_id.replace('lst_', '')}.jsonl"
        with f.open('w', encoding='utf-8') as fh:
            for i, r in enumerate(items, 1):
                fh.write(json.dumps({
                    'listId': list_id, 'key': r['key'], 'kind': 'WORD',
                    'stage': stage, 'level': None, 'seq': i,
                    'tags': [sect] + ([extra_tag] if extra_tag else []),
                    'anchorIds': [ANCHOR_FOR.get(sect) or r.get('anchor')],
                    'meta': {'table': sect},
                    'source': SRC,
                    'extraction': {'srcPage': page_of(r), 'agree': f'≥{VOTE}/{RUNS}',
                                   'method': 'vlm-5vote-setconsensus+headingslice'},
                    'schemaVersion': '0.1.0',
                }, ensure_ascii=False) + '\n')
        print(f"  → {f.name}  {len(items)} 条")

    for sect, items in by.items():
        if sect not in TABLES:
            print(f"  ! 段「{sect}」未登记，跳过"); continue
        list_id, stage, alpha = TABLES[sect]
        write_list(list_id, stage, sect,
                   [{'key': i['word'], 'page': i['page']} for i in items],
                   alpha, lambda r: r['page'])

    # 不规则动词：三列，key 取原形，过去式/过去分词进 meta
    f = LISTS / 'en-irregular-verbs.jsonl'
    with f.open('w', encoding='utf-8') as fh:
        for i, r in enumerate(verbs, 1):
            base, past, part = (list(r['value']) + ['', ''])[:3]
            fh.write(json.dumps({
                'listId': 'lst_en-irregular-verbs', 'key': base, 'kind': 'WORD',
                'stage': 'G7-9', 'level': None, 'seq': i, 'tags': ['不规则动词表'],
                'anchorIds': [vaid],
                'meta': {'table': '不规则动词表', 'past': past, 'pastParticiple': part},
                'source': '义务教育英语课程标准（2022年版）附录 不规则动词表',
                'extraction': {'srcPage': r['page'], 'agree': r['agree'],
                               'method': 'vlm-5vote-positional'},
                'schemaVersion': '0.1.0',
            }, ensure_ascii=False) + '\n')
    print(f"  → {f.name}  {len(verbs)} 条")

    # 锚点回写
    tgt = ROOT / 'anchors/english-lists.jsonl'
    arr = files.get('english-lists.jsonl', []) + new_anchors
    with tgt.open('w', encoding='utf-8') as fh:
        for a in arr:
            fh.write(json.dumps(a, ensure_ascii=False) + '\n')
    print(f"  → anchors/english-lists.jsonl  {len(arr)} 条（新增 {len(new_anchors)}）")

    for fname, arr2 in files.items():
        if fname == 'english-lists.jsonl':
            continue
        if any(a['id'] in count_by_anchor for a in arr2):
            with (ROOT / 'anchors' / fname).open('w', encoding='utf-8') as fh:
                for a in arr2:
                    fh.write(json.dumps(a, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    main()
