#!/usr/bin/env python3
"""
eval.py — 量映射器：给一道题，它能不能把题目真正考的那几条锚点排到前面。

这是「可以被映射」这句话第一次有数。之前 mapper 只有 3 条自测用例，准不准没人知道。

    python3 bench/fetch.py                      # 先把题拉到本地（原文不进仓库）
    python3 bench/eval.py                       # 只量粗召回 —— MCP 的 search_anchors 走的就是这一段
    python3 bench/eval.py --rerank              # 再量精排（要 LLM_* 或 MIMO_* 环境变量）

**评的是 search_anchors 实际交给调用方的东西**：给学科、给年级、只召回可引用的。
学段是区间的（初中 G7–G9、高中 G10–G12）按区间中点传年级 —— 调用方手上通常只有一个年级。

**金标是 AI 标的，不是老师标的。** 标注时禁止使用 mapper 和 MCP 检索，
只能自己 grep 锚点 —— 否则就是拿被测对象去出考卷。金标的 labeledBy 如实记着。
老师复核金标之前，这里的数字的意思是「和一个认真的 AI 标注者比」，不是「和真相比」。
"""
import sys
sys.dont_write_bytecode = True

import argparse, collections, json, os, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / 'tools'))
import mapper as M                               # noqa: E402

KS = (1, 3, 5, 10)
BAND = lambda st: '小学' if st in {f'G{i}' for i in range(1, 7)} else ('初中' if st == 'G7-G9' else '高中')
MID = {'G7-G9': 8, 'G10-G12': 11}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rerank', action='store_true')
    ap.add_argument('--expand', action='store_true', help='再量「查询改写 + 粗召回」（精排也跟着吃改写后的候选池）')
    ap.add_argument('--pool', type=int, default=25)
    ap.add_argument('--out', default=str(ROOT / 'reports' / 'mapping-bench.md'))
    a = ap.parse_args()

    items = [json.loads(l) for l in (HERE / 'mapping-100.jsonl').open(encoding='utf-8')]
    pool = {x['ref']: x for x in map(json.loads, (HERE / '.cache' / 'pool.jsonl').open(encoding='utf-8'))}
    anchors = M.load()
    byid = {x['id']: x for x in anchors}
    df, n = M.build_df(anchors)

    # 同族：一条锚点和从它拆出来 / 转写出来的条目（splitFrom、derivedFrom，上下一层）。
    # 原句和拆出来的原子都可引用，映射器给了意思相同的另一条，严格口径算没中 ——
    # 所以两个口径都报：严格（只认金标本身）和同族（金标的父或子也算）。
    link = collections.defaultdict(set)
    for x in anchors:
        pv = x.get('provenance') or {}
        for k in ('splitFrom', 'derivedFrom'):
            p = x.get(k) or pv.get(k)
            if p:
                link[x['id']].add(p)
                link[p].add(x['id'])
    fam = lambda g: {g} | link[g]

    import hashlib
    stale = [it['qid'] for it in items
             if hashlib.sha256(pool[it['ref']]['text'].encode()).hexdigest()[:16] != it['textSha']]
    if stale:
        sys.exit(f'上游改了题面，旧金标不能评新题：{stale}')
    unlabeled = [it['qid'] for it in items if it['gold'] is None]
    if unlabeled:
        sys.exit(f'还有 {len(unlabeled)} 题没标金标：{unlabeled[:8]}…')
    dead = [(it['qid'], g) for it in items for g in it['gold']
            if g not in byid or byid[g]['reviewStatus'] not in M.CITABLE]
    if dead:
        sys.exit(f'金标指向了不存在 / 已弃用 / 不可引用的锚点：{dead}')

    env = M.llm_env()
    if (a.rerank or a.expand) and not env:
        sys.exit('--rerank / --expand 要 LLM_BASE/LLM_KEY（或 MIMO_*）')

    def recall(qq, it, stage):
        cands = []
        for x in anchors:
            if x['reviewStatus'] not in M.CITABLE:
                continue
            r = M.score(qq, x, it['discipline'], stage, df, n)
            if r:
                cands.append((r[0], r[1], x))
        cands.sort(key=lambda t: -t[0])
        return cands

    from concurrent.futures import ThreadPoolExecutor

    def one(it):
        q = pool[it['ref']]['text']
        stage = MID.get(it['stage']) or M.G(it['stage'])
        cands = recall(q, it, stage)
        row = {'it': it, 'ranked': [c[2]['id'] for c in cands], 'rr': None, 'xr': None, 'xrr': None}
        if not it['gold']:
            return row
        if a.rerank:
            picks, _ = M.rerank(q, cands[:a.pool], *env)
            row['rr'] = [c[2]['id'] for c, _ in picks] if picks is not None else None
        if a.expand:
            ex = M.expand(q, it['discipline'], stage, *env)
            xc = recall(q + ('\n' + ex if ex else ''), it, stage)
            row['xr'] = [c[2]['id'] for c in xc]
            if a.rerank:
                picks, _ = M.rerank(q, xc[:a.pool], *env)      # 精排看原文
                row['xrr'] = [c[2]['id'] for c, _ in picks] if picks is not None else None
        return row

    t0 = time.time()
    with ThreadPoolExecutor(8 if (a.rerank or a.expand) else 1) as ex:
        rows = list(ex.map(one, items))

    def metrics(get, loose=False):
        """get(row) → 排好的 ID 列表。只在有金标的题上算。loose=同族也算中。"""
        lab = [r for r in rows if r['it']['gold']]
        if loose:
            lab = [dict(r, it=dict(r['it'], gold=sorted(set().union(*(fam(g) for g in r['it']['gold'])))))
                   for r in lab]
        out = {}
        for k in KS:
            out[f'hit@{k}'] = sum(bool(set(get(r)[:k]) & set(r['it']['gold'])) for r in lab) / max(1, len(lab))
        rec = []
        for r in lab:
            g = r['it']['gold']
            pos = [get(r).index(x) + 1 for x in g if x in get(r)]
            rec.append(1 / min(pos) if pos else 0)
        out['mrr'] = sum(rec) / max(1, len(rec))
        out['n'] = len(lab)
        return out

    # 每题的排名留一份在 .cache/，诊断「第一名换成了谁」用（不进仓库）
    (HERE / '.cache' / 'last-run.json').write_text(json.dumps(
        [{'qid': r['it']['qid'], 'gold': r['it']['gold'], 'coarse': r['ranked'][:10],
          'deep': (r['xrr'] if r.get('xrr') is not None else r.get('xr') or [])[:10]} for r in rows],
        ensure_ascii=False), encoding='utf-8')
    coarse = metrics(lambda r: r['ranked'])
    reach = sum(bool(set(r['ranked'][:a.pool]) & set(r['it']['gold'])) for r in rows if r['it']['gold'])
    by = collections.defaultdict(list)
    for r in rows:
        by[BAND(r['it']['stage'])].append(r)
        by[r['it']['discipline']].append(r)
    fit = collections.Counter(r['it'].get('fit') or ('none' if not r['it']['gold'] else '?') for r in rows)

    L = ['# 映射基准：100 道真题对到锚点', '',
         f'> 由 `bench/eval.py` 生成（{time.strftime("%Y-%m-%d")}）。题目来源与许可见 `bench/fetch.py`；'
         '原文不进仓库。', '',
         '**金标是 AI 标的，不是老师标的**（标注时禁用 mapper 与 MCP 检索）。'
         '下面的命中率意思是「和一个认真的 AI 标注者比」，老师复核金标之前不要当成准确率对外说。', '',
         '## 一、底座覆盖得到吗', '',
         f'100 题里 **{sum(1 for r in rows if r["it"]["gold"])}** 题能在可引用锚点里找到对应'
         f'（完全对上 {fit.get("exact", 0)} · 部分对上 {fit.get("partial", 0)}），'
         f'**{sum(1 for r in rows if not r["it"]["gold"])}** 题找不到 —— 那是底座的覆盖缺口，不是映射器的错。', '']
    gaps = [r['it'] for r in rows if not r['it']['gold']]
    if gaps:
        L += ['| 题 | 学段 | 学科 | 缺什么 |', '|---|---|---|---|']
        for g in gaps:
            L.append(f"| {g['qid']} | {g['stage']} | {g['discipline']} | {(g.get('note') or '').replace('|', '／')[:80]} |")
        L.append('')
    L += ['## 二、映射器把它排到前面了吗', '',
          '只在有金标的题上算。hit@k = 前 k 条里至少有一条金标锚点。', '',
          '| | 题数 | hit@1 | hit@3 | hit@5 | hit@10 | MRR |', '|---|---:|---:|---:|---:|---:|---:|']

    def line(name, m):
        return (f"| {name} | {m['n']} | " + ' | '.join(f"{m[f'hit@{k}']:.0%}" for k in KS)
                + f" | {m['mrr']:.2f} |")
    L.append(line('**粗召回（search_anchors 实际给的）**', coarse))
    L.append(line('粗召回 · 同族也算中', metrics(lambda r: r['ranked'], loose=True)))
    if a.rerank:
        L.append(line('粗召回 + 精排', metrics(lambda r: r['rr'] if r['rr'] is not None else r['ranked'])))
    if a.expand:
        L.append(line('改写 + 粗召回', metrics(lambda r: r['xr'])))
        xreach = sum(bool(set(r['xr'][:a.pool]) & set(r['it']['gold'])) for r in rows if r['it']['gold'])
    if a.expand and a.rerank:
        L.append(line('**改写 + 粗召回 + 精排**', metrics(lambda r: r['xrr'] if r['xrr'] is not None else r['xr'])))
        L.append(line('改写 + 粗召回 + 精排 · 同族也算中',
                      metrics(lambda r: r['xrr'] if r['xrr'] is not None else r['xr'], loose=True)))
    L += ['', f"前 {a.pool} 条候选里含金标的：只用原文 {reach} / {coarse['n']}"
          + (f"，加上改写 {xreach} / {coarse['n']}" if a.expand else '')
          + ' —— 这是精排的天花板，池外的它看不到。', '',
          '改写和精排各是一次模型调用（本次用的模型：' + (env[2] if env else '—') + '）。'
          'search_anchors 默认只走粗召回；传 `deep: true` 才走「改写 + 精排」。', '',
          '### 分学段 / 分学科（粗召回）', '',
          '| | 题数 | hit@1 | hit@3 | hit@5 | hit@10 | MRR |', '|---|---:|---:|---:|---:|---:|---:|']
    for k in ['小学', '初中', '高中'] + sorted(x for x in by if x not in ('小学', '初中', '高中')):
        sub = by[k]
        lab = [r for r in sub if r['it']['gold']]
        if not lab:
            continue
        m = {}
        for kk in KS:
            m[f'hit@{kk}'] = sum(bool(set(r['ranked'][:kk]) & set(r['it']['gold'])) for r in lab) / len(lab)
        m['mrr'] = sum((1 / min(r['ranked'].index(x) + 1 for x in r['it']['gold'] if x in r['ranked']))
                       if set(r['ranked']) & set(r['it']['gold']) else 0 for r in lab) / len(lab)
        m['n'] = len(lab)
        L.append(line(k, m))
    L += ['', '## 三、没排进前 10 的（粗召回）', '',
          '只列锚点，不列题面（许可见 fetch.py）。拿 qid 去 `bench/.cache/pool.jsonl` 查原题。', '']
    miss = [r for r in rows if r['it']['gold'] and not set(r['ranked'][:10]) & set(r['it']['gold'])]
    for r in miss:
        it = r['it']
        L.append(f"- **{it['qid']}** {it['stage']} {it['discipline']} — 金标：" +
                 '；'.join(byid[g]['statement'][:36] for g in it['gold']))
        if r['ranked']:
            L.append(f"  排第一的是：{byid[r['ranked'][0]]['statement'][:40]}")
        else:
            L.append('  粗召回一条都没捞到')
    Path(a.out).write_text('\n'.join(L) + '\n', encoding='utf-8')
    print(f"✓ {a.out}  用时 {time.time() - t0:.0f}s")
    print('  粗召回 ' + '  '.join(f"hit@{k} {coarse[f'hit@{k}']:.0%}" for k in KS) + f"  MRR {coarse['mrr']:.2f}"
          f"  （{coarse['n']} 题有金标）")


if __name__ == '__main__':
    main()
