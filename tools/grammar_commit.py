#!/usr/bin/env python3
"""
grammar_commit.py — 语法项目表落库。

**关于可信度分档，这里做了一个克制的决定：**

语法项目锚点标 `ai-reviewed`，不标 `auto-confirmed`。

抽取本身是机械的（来自课标附录，结构不变量可验），但「判定是否客观」这一条
过不去：「这个字写对没有」「这个词拼对没有」是二值的，旁人一眼可判；
「系动词用对了没有」要看具体句子，是程度判断。auto-confirmed 的三条依据里
第三条明确写着「判定标准客观，不依赖教学判断」—— 语法项目不满足。

放宽这条线很容易（可用锚点数会好看一点），但那正是这个项目要防的失败模式：
一旦 usable 里混进需要教学判断的东西，「可用」这个词就不再有意义。

这 2 条锚点会进教师复核队列，且排序靠前 —— 一次判定解锁 49 个语法项目，
性价比在全库里数一数二。

    python3 tools/grammar_commit.py
"""
import json, secrets, string, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALNUM = string.ascii_letters + string.digits
SRC = '义务教育英语课程标准（2022年版）附录4 语法项目表'


def build(rows):
    """→ [(L1序, L1名, L2序, L2名, 条目序, 条目名, plus)]，按结构不变量去重。

    不变量：同一个二级标题下，条目编号不会重复。实测模型会把一小节整块重复
    输出一遍（1.宾语从句 2.状语从句 1.宾语从句 2.状语从句），相邻去重抓不到，
    按 (L1, L2, 编号) 去重才行。
    """
    out, seen = [], set()
    l1 = l1n = l2 = l2n = None
    for r in rows:
        t, num, txt, plus = r['value']
        if t == 'L1':
            l1, l1n = num, txt; l2 = l2n = None
            k = ('L1', num)
            if k not in seen:
                seen.add(k); out.append((num, txt, None, None, None, None, plus))
        elif t == 'L2':
            l2, l2n = num, txt
            k = ('L2', l1, num)
            if k not in seen:
                seen.add(k); out.append((l1, l1n, num, txt, None, None, plus))
        else:
            k = ('I', l1, l2, num)
            if k in seen:
                continue
            seen.add(k); out.append((l1, l1n, l2, l2n, num, txt, plus))
    return out


def normalize_keys(keys):
    """规范化一律走 scripts/decide.mjs —— 规范形的定义只有那一份实现。
    在 Python 侧照着写第二份，两份必然漂移，然后「入库时通过、校验时被拒」
    会成批出现且没人说得清哪份对。"""
    import subprocess
    payload = '\n'.join(json.dumps({'statement': k, 'discipline': '英语'},
                                    ensure_ascii=False) for k in keys)
    r = subprocess.run(['node', str(ROOT / 'scripts/decide.mjs')], input=payload,
                       capture_output=True, text=True, check=True)
    return [json.loads(l)['normalized'] for l in r.stdout.split('\n') if l.strip()]


def main():
    rows = json.loads((ROOT / 'tools/out/en-grammar-clean.json').read_text(encoding='utf-8'))
    tree = build(rows)
    items = [t for t in tree if t[4] is not None]
    heads = [t for t in tree if t[4] is None]
    plus_items = [t for t in tree if t[6] == '+']
    print(f"结构：{len([t for t in tree if t[2] is None])} 个大类 · "
          f"{len(heads) - len([t for t in tree if t[2] is None])} 个中类 · {len(items)} 个条目")
    print(f"标「+」（仅作理解要求）：{len(plus_items)} 条 — {[t[5] or t[3] for t in plus_items]}")

    # ── 锚点 ────────────────────────────────────────────────
    existing = {}
    for f in sorted((ROOT / 'anchors').glob('*.jsonl')):
        existing[f.name] = [json.loads(l) for l in f.open(encoding='utf-8') if l.strip()]
    taken = {a['id'] for v in existing.values() for a in v}

    def nid():
        while True:
            i = 'ca_' + ''.join(secrets.choice(ALNUM) for _ in range(8))
            if i not in taken:
                taken.add(i); return i

    use_id, understand_id = nid(), nid()
    n_use = len([t for t in tree if t[6] != '+'])
    n_und = len(plus_items)

    def mk(aid, statement, verb, obj, stage, evidence, assessment, count, note):
        return {
            'id': aid, 'discipline': '英语', 'track': 'LIST', 'strand': '语言知识',
            'topic': None, 'dimension': None,
            'statement': statement, 'verb': verb, 'object': obj,
            'type': 'LANGUAGE', 'literacy': ['语言能力'], 'cognitive': '应用',   # 枚举只有 了解/理解/掌握/应用
            'stageHint': stage, 'evidence': evidence, 'assessment': assessment,
            'evidenceSource': 'curriculum-appendix',
            # ↓ 见文件顶部注释：抽取是机械的，判定不是客观的，所以停在 ai-reviewed
            'reviewStatus': 'ai-reviewed', 'reviewedBy': [],
            'deprecated': False, 'supersededBy': None,
            'autoConfirmBasis': [],
            'reviewNote': note,
            'provenance': {
                'srcSubject': '英语', 'srcPage': 145, 'srcPageRange': '145–149',
                'method': 'curriculum-appendix', 'itemCount': count, 'declaredCount': None,
            },
            'schemaVersion': '0.1.0',
        }

    anchors = [
        mk(use_id, '能在句子中正确使用课标语法项目表所列的语法项目', '使用',
           '课标语法项目表所列的语法项目', {'min': 'G3', 'max': 'G9'},
           ['在自己写的句子中该项目使用无误', '被指出错误后能说出正确形式'],
           '给{{name}}一个含该语法点的句子，他能判断对错并改正吗？', n_use,
           '需教师确认：语法项目的掌握判定依赖具体语境，非二值。确认后可解锁 '
           f'{n_use} 个语法项目条目。'),
        mk(understand_id, '能理解课标语法项目表中标注「+」的三级语法项目', '理解',
           '标注「+」的三级语法项目', {'min': 'G7', 'max': 'G9'},
           ['读到含该项目的句子能说出句意', '不要求自己主动使用'],
           '{{name}}读到含这个语法点的句子，能说出意思吗？', n_und,
           '课标原文规定这些项目「仅作理解要求」，判定标准与上一条不同，需分开确认。'),
    ]
    for a in anchors:
        print(f"  + {a['id']}  {a['statement']}  {a['provenance']['itemCount']} 条  [{a['reviewStatus']}]")

    # ── 清单 ────────────────────────────────────────────────
    f = ROOT / 'lists/grammar'
    f.mkdir(parents=True, exist_ok=True)
    out = f / 'en-grammar.jsonl'
    raw_keys = [(txt or l2n or l1n) for (l1, l1n, l2, l2n, num, txt, plus) in tree]
    norm_keys = normalize_keys(raw_keys)
    with out.open('w', encoding='utf-8') as fh:
        for i, ((l1, l1n, l2, l2n, num, txt, plus), key) in enumerate(zip(tree, norm_keys), 1):
            depth = 1 if l2 is None else (2 if num is None else 3)
            path = '/'.join(x for x in [l1n, l2n if depth >= 2 else None,
                                        txt if depth == 3 else None] if x)
            fh.write(json.dumps({
                'listId': 'lst_en-grammar', 'key': key, 'kind': 'GRAMMAR',
                'stage': 'G7-9' if plus else 'G3-9',
                # level 是「年级」字段（校验器按 GRADE_RE 卡），不是树深度。
                # 深度放 meta.depth。
                'level': None, 'seq': i,
                'tags': ['语法项目表'] + (['仅作理解'] if plus else []),
                'anchorIds': [understand_id if plus else use_id],
                'meta': {'table': '语法项目表', 'path': path, 'depth': depth,
                         'understandOnly': bool(plus)},
                'source': SRC,
                'extraction': {'srcPage': 145, 'agree': '≥3/5',
                               'method': 'vlm-5vote-hierarchical'},
                'schemaVersion': '0.1.0',
            }, ensure_ascii=False) + '\n')
    print(f"  → {out}  {len(tree)} 条")

    tgt = ROOT / 'anchors/english-lists.jsonl'
    # 脚本可重跑：先剔掉上一轮写进去的同名锚点，否则每跑一次多两条孤儿
    keep = [a for a in existing['english-lists.jsonl']
            if a['statement'] not in {x['statement'] for x in anchors}]
    dropped = len(existing['english-lists.jsonl']) - len(keep)
    if dropped:
        print(f"  ~ 剔除上一轮重复写入的 {dropped} 条")
    arr = keep + anchors
    with tgt.open('w', encoding='utf-8') as fh:
        for a in arr:
            fh.write(json.dumps(a, ensure_ascii=False) + '\n')
    print(f"  → anchors/english-lists.jsonl  {len(arr)} 条")


if __name__ == '__main__':
    main()
