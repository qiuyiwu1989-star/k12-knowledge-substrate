#!/usr/bin/env python3
"""
evfix_round2.py — 证据第二轮：带着复核意见重写，**起草 → 过闸 → 复审**一条龙。

对象两批（都不含证据抄自课标的 curriculum-* —— 课标自己写得弱，不归我们改写）：

  A. 已可引用、但挂着 fieldIssues:evidence-weak 的。断言没毛病，证据跟断言对不上或太空。
     例：断言「能运用最常用的调型表达自己的意图」，证据却在讲连读和弱化。
  B. disputed 且唯一未撤的异议是 evidence-weak 的（多数是 v1.5 复审刚挑出来的）。

和第一轮（_evfix.py + evfix_commit.py）的差别只有一处：起草时把**旧证据和复核意见**
一起交给模型 —— 第一轮是「占位模板换真证据」，这一轮是「真证据被指出了具体毛病，照着改」。

落库规则（与 evfix_commit 同源）：
  · 新证据过不了闸 → 什么都不动
  · 复审没挑出问题 → 换证据、摘 evidence-weak；B 批升 ai-reviewed，异议记 resolved
  · 复审只说证据还弱 → 什么都不动（新证据没比旧的强，不换）
  · 复审挑出断言本身的问题：stage 异议先用课标学段裁决；剩下的
      - A 批**不动** —— 上一轮复核放行了这条断言，这一轮（同一个起草模型）说不行，是两个判官冲突，
        按 resolve_disputed 的规矩留给人。试跑时 4 条里有一条挑的是**前置**的毛病、一条把
        日语术语「こそあ」判成截断 —— 拿这种意见把可引用的降下去，是让弱证据替断言背锅的反面
      - B 批进 disputed（本来就是 disputed，只是异议换成了新挑的）
    python3 tools/evfix_round2.py            # 只看不写
    python3 tools/evfix_round2.py --write
"""
import sys
sys.dont_write_bytecode = True

import argparse, collections, hashlib, json, os, re, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import fix_fallback_evidence as F              # noqa: E402  起草提示词与闸
from ai_review import SYS as REVIEW, OPEN_AT   # noqa: E402  复审提示词
from evfix_commit import call, PARENT_ASK      # noqa: E402
from doc_stage import split_stage_issues       # noqa: E402

CACHE = TOOLS / 'out' / '.cache-evfix2'
LOG = TOOLS / 'out' / 'evidence-fix-round2.jsonl'


def gate(d, stmt):
    ev = [e for e in (d.get('evidence') or []) if isinstance(e, str) and 10 <= len(e) <= 60]
    if len(ev) < 2:
        return None, '证据不足 2 条或长度不合'
    if any(F.FALLBACK.match(e) for e in ev):
        return None, '又写成兜底模板'
    if any(len(F.zh(e) - F.zh(stmt)) < 3 for e in ev):
        return None, '还是在复读断言'
    return ev, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--concurrency', type=int, default=10)
    a = ap.parse_args()
    base, key, model = os.environ['LLM_BASE'], os.environ['LLM_KEY'], os.environ['LLM_MODEL']
    # 复审模型可以和起草模型分开（REVIEW_MODEL）。不分开就是同一个模型审自己写的 —— 偏宽，
    # 2026-09-28 这样升上去的 60 条事后又让豆包补审了一遍
    rmodel = os.environ.get('REVIEW_MODEL') or model
    suffix = os.environ.get('LLM_ENDPOINT', '/chat/completions')
    by = 'ai:' + re.sub(r'-\d{6}$', '', rmodel) + '-' + time.strftime('%Y-%m-%d')
    CACHE.mkdir(exist_ok=True)

    files = {f: [json.loads(l) for l in f.read_text(encoding='utf-8').splitlines() if l.strip()]
             for f in sorted((ROOT / 'anchors').rglob('*.jsonl'))}
    byid = {r['id']: r for rows in files.values() for r in rows}
    fileof = {r['id']: f.name for f, rows in files.items() for r in rows}
    edges_in = collections.defaultdict(list)
    for f in sorted((ROOT / 'edges').rglob('*.jsonl')):
        for l in f.open(encoding='utf-8'):
            e = json.loads(l)
            edges_in[e['anchorId']].append(e['prerequisiteId'])
    jobs = []
    for r in byid.values():
        if r.get('deprecated') or str(r.get('evidenceSource', '')).startswith('curriculum-'):
            continue
        if not (r.get('provenance') or {}).get('srcText'):
            continue
        if r['reviewStatus'] == 'ai-reviewed' and 'evidence-weak' in (r.get('fieldIssues') or []):
            jobs.append(('A', r))
        elif r['reviewStatus'] == 'disputed':
            live = [i for i in r.get('aiIssues') or [] if i['type'] != 'resolved']
            if live and {i['type'] for i in live} == {'evidence-weak'}:
                jobs.append(('B', r))
    print(f"A 已可引用但证据弱 {sum(g == 'A' for g, _ in jobs)} · B 仅因证据弱存疑 {sum(g == 'B' for g, _ in jobs)}")

    def ask(sysp, user, tag):
        mdl = rmodel if tag == 'review' else model
        h = hashlib.sha256((mdl + tag + sysp + user).encode()).hexdigest()[:24]
        cf = CACHE / f'{h}.json'
        if cf.exists():
            return json.loads(cf.read_text(encoding='utf-8'))
        for _ in range(3):
            try:
                txt = call(sysp, user, base, key, mdl, suffix)
            except Exception as e:
                return {'error': str(e)[:60]}
            m = re.search(r'\{.*\}', txt, re.S)
            try:
                o = json.loads(m.group(0)) if m else None
            except Exception:
                o = None
            if isinstance(o, dict):
                cf.write_text(json.dumps(o, ensure_ascii=False), encoding='utf-8')
                return o
        return {'error': '解析失败'}

    def work(job):
        g, r = job
        complaint = next((i.get('detail', '') for i in r.get('aiIssues') or [] if i['type'] == 'evidence-weak'), '')
        src = (r.get('provenance') or {}).get('srcText', '')[:260]
        user = (f"上一版证据：{' / '.join((r.get('evidence') or [])[:3])}\n"
                f"复核意见：{complaint or '证据没能证明这条能力（证据和断言对不上，或太空）'}\n"
                f"照上面的要求重写，针对复核意见改。")
        d = ask(F.SYS.format(stmt=r['statement'], src=src), user, 'draft')
        if d.get('error'):
            return job, {'stage': 'draft', 'why': d['error']}
        if not d.get('ok'):
            return job, {'stage': 'draft', 'why': '模型说写不出：' + str(d.get('why', ''))[:60]}
        ev, why = gate(d, r['statement'])
        if not ev:
            return job, {'stage': 'gate', 'why': why, 'candidate': d.get('evidence')}
        disc = r['discipline']
        lo, hi = OPEN_AT[disc]
        pres = [byid[p]['statement'] for p in edges_in.get(r['id'], [])[:5] if p in byid]
        ruser = (f"能力断言：{r['statement']}\n"
                 f"领域：{r.get('strand') or '未标注'}\n"
                 f"标注学段：{(r.get('stageHint') or {}).get('min','?')}–{(r.get('stageHint') or {}).get('max','?')}\n"
                 f"掌握证据：{' / '.join(ev)}\n"
                 f"已标的直接前置：{' / '.join(pres) if pres else '（无）'}\n"
                 f"来源：{disc}课标 第 {(r.get('provenance') or {}).get('srcPage','?')} 页")
        o = ask(REVIEW.format(disc=disc, open_at=f'{lo}–{hi} 年级'), ruser, 'review')
        if o.get('error') or not isinstance(o.get('issues'), list):
            return job, {'stage': 'review', 'why': o.get('error') or '回答里没有 issues 字段'}
        return job, {'stage': 'ok', 'ev': ev, 'assessment': d.get('assessment'),
                     'issues': [x for x in o['issues'] if isinstance(x, dict) and x.get('type')]}

    stat, log = collections.Counter(), []
    with ThreadPoolExecutor(a.concurrency) as ex:
        for (g, r), res in ex.map(work, jobs):
            row = {'id': r['id'], 'group': g, 'discipline': r['discipline'], 'model': model, **res}
            log.append(row)
            if res['stage'] != 'ok':
                stat[f"{g} 没动（{res['stage']}：{res['why'][:14]}）"] += 1
                continue
            iss, wd, why = split_stage_issues(r, fileof[r['id']], res['issues'])
            types = {x['type'] for x in iss}
            if 'evidence-weak' in types:
                stat[f'{g} 没动（复审说新证据仍弱）'] += 1
                row['outcome'] = 'still-weak'
                continue
            if iss and g == 'A':
                row['outcome'] = 'conflict'
                stat['A 没动（复审对断言本身有异议，与上一轮冲突，留给人）'] += 1
                continue
            # 新证据过了闸、复审没说它弱 → 换
            r['evidence'] = res['ev']
            if r.get('evidenceSource') == 'capability-rewrite':
                r['evidenceDrafted'] = True
            else:
                r['evidenceSource'] = 'evidence-drafted'
            if res.get('assessment') and not r.get('assessment'):
                r['assessment'] = PARENT_ASK.sub('', res['assessment'])
            fi = [x for x in (r.get('fieldIssues') or []) if x != 'evidence-weak']
            if fi:
                r['fieldIssues'] = fi
            else:
                r.pop('fieldIssues', None)
            r['reviewedBy'] = sorted(set((r.get('reviewedBy') or []) + [by]))
            wdr = [{'type': 'resolved', 'by': by,
                    'detail': f"复审提了 stage（{x.get('detail','')[:40]}）→ 撤销：{why}，模型的意见不能盖过课标"}
                   for x in wd[:1]]
            prior = [i for i in r.get('aiIssues') or [] if i['type'] == 'resolved']
            if iss:
                r['aiIssues'] = iss[:5] + prior + wdr
                r['reviewStatus'] = 'disputed'
                row['outcome'] = 'disputed'
                stat[f'{g} 换了证据，但复审挑出断言问题 → disputed'] += 1
            else:
                if g == 'B':
                    old = next((i for i in r.get('aiIssues') or [] if i['type'] == 'evidence-weak'), {})
                    r['aiIssues'] = prior + [{'type': 'resolved', 'by': by,
                                              'detail': f"原异议 evidence-weak（{old.get('detail','')[:60]}）："
                                                        f"带着这条意见重写证据，复审未挑出问题"}] + wdr
                    r['reviewStatus'] = 'ai-reviewed'
                elif wdr:
                    r['aiIssues'] = (r.get('aiIssues') or []) + wdr
                row['outcome'] = 'fixed'
                stat[f'{g} 换了证据' + (' → ai-reviewed' if g == 'B' else '，摘掉 evidence-weak')] += 1

    for k, n in sorted(stat.items()):
        print(f'  {n:>4}  {k}')
    LOG.write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in log), encoding='utf-8')
    if not a.write:
        print(f'（没写盘；明细见 {LOG.relative_to(ROOT)}；加 --write 写回）')
        return
    for f, rows in files.items():
        f.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')
    print(f'已写回，reviewedBy 记为 {by}')


if __name__ == '__main__':
    main()
