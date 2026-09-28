#!/usr/bin/env python3
"""
revive.py — 复查「只由一个模型判下」的弃用，误判的撤销。决策见 DECISIONS.md 2026-09-28。

## 为什么要做

映射基准（bench/）标金标时撞见：「能根据具体问题中的数量关系列出方程」被 repair.py 判
「AI 判定不是学生能力」弃用 —— 而它在可判定性自测（selftest）里是「通过」的正例。
1,014 条弃用锚点没有替代条目，其中 821 条的弃用只凭一个模型的一次判断。
一条真能力被误弃用，底座里那块就是空的：题目对不上、档案引用不了。

## 复查谁

弃用、没有 supersededBy、也没有在用的拆分子条，且弃用理由属于这三类：
  · 「课标原句本身是口号或教学建议…修不出来」（repair.py）
  · 「AI 判定不是学生能力」（repair.py 见 not-a-capability 直接弃用，没有第二意见）
  · 「AI 裁决」
机械规则判下的（指标类、主语是教师）和「模型与可判定闸一致」的**不动** —— 那些有第二个判官。

## 撤销的门槛（全过才撤）

  1. **可判定闸放行**（scripts/lib/check-stdin.mjs，和 CI 同一个）
  2. **断言忠于课标原句**：实义字覆盖 ≥ 62%（repair.grounded）—— 撤销的是误判，不是给改写开后门
  3. **没有同句在用**：已有一条在用的锚点断言一字不差，就不撤（撤了是重复）
  4. **证据是真的**：占位模板先起草真证据（fix_fallback_evidence 的提示词和闸），起不出来不撤
  5. **另一个模型复审没挑出问题**：ai_review 同一份提示词、同一种输入格式；
     stage 异议按课标学段裁决（doc_stage）。当初判弃用的是 mimo，复审用的是另一个模型

复审的结论分三种处置：
  · 没挑出问题 → 撤销弃用，ai-reviewed（可引用）
  · 只挑了**字段**上的问题（stage / evidence-weak）→ 撤销弃用，但进 disputed 挂着具体异议。
    弃用说的是「这不是一条能力」；复审只说学段标宽了、证据不够好，那是字段的毛病，
    不该让断言替它们背锅（schema 里 fieldIssues 那段话）。挂着异议排队，不进可引用
  · 也判了 not-a-capability / undecidable / truncated → 两个模型一致，维持弃用

原弃用理由记进 aiIssues 的 resolved 条目，不删历史。

    LLM_BASE=… LLM_KEY=… LLM_MODEL=… LLM_ENDPOINT=/chat/completions python3 tools/revive.py [--only 数学]
    … python3 tools/revive.py --write
"""
import sys
sys.dont_write_bytecode = True

import argparse, collections, hashlib, json, os, re, subprocess, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import fix_fallback_evidence as F                 # noqa: E402  起草提示词、兜底模板
from ai_review import SYS as REVIEW, OPEN_AT      # noqa: E402  复审提示词
from repair import call, grounded                 # noqa: E402
from evfix_round2 import gate                     # noqa: E402  证据闸
from doc_stage import split_stage_issues          # noqa: E402
from evfix_commit import PARENT_ASK               # noqa: E402

CACHE = TOOLS / 'out' / '.cache-revive'
LOG = TOOLS / 'out' / 'revive-log.jsonl'
REASONS = ('课标原句本身是口号或教学建议', 'AI 判定不是学生能力', 'AI 裁决')
FB = re.compile(r'^能在.{1,10}课堂或作业情境中完成')
FIELD = {'stage', 'evidence-weak'}          # 字段级异议：不否定「这是一条能力」


def placeholder(a):
    ev = a.get('evidence') or []
    return (not ev) or bool(FB.match(str(ev[0]))) or a.get('evidenceSource') == 'fallback'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--only', default=None)
    ap.add_argument('--concurrency', type=int, default=10)
    a = ap.parse_args()
    base, key, model = os.environ['LLM_BASE'], os.environ['LLM_KEY'], os.environ['LLM_MODEL']
    by = 'ai:' + re.sub(r'-\d{6}$', '', model) + '-' + time.strftime('%Y-%m-%d')
    CACHE.mkdir(exist_ok=True)

    files = {f: [json.loads(l) for l in f.read_text(encoding='utf-8').splitlines() if l.strip()]
             for f in sorted((ROOT / 'anchors').glob('*.jsonl'))}
    byid = {r['id']: r for rows in files.values() for r in rows}
    fileof = {r['id']: f.name for f, rows in files.items() for r in rows}
    live_kids = collections.defaultdict(int)
    for r in byid.values():
        p = r.get('splitFrom') or (r.get('provenance') or {}).get('splitFrom')
        if p and not r.get('deprecated'):
            live_kids[p] += 1
    # 同句判据去掉句首「能 / 能够 / 会」和标点：「能计算…方差」与「会计算…方差」是同一句。
    # 第一版只比原文，漏了这一对，是 validate 的去重签名闸抓出来的
    norm = lambda t: re.sub(r'[\s，,。、；;：:]', '', re.sub(r'^(能够|能|会)', '', t))
    live_st = {norm(r['statement']) for r in byid.values() if not r.get('deprecated')}
    edges_in = collections.defaultdict(list)
    for f in sorted((ROOT / 'edges').rglob('*.jsonl')):
        for l in f.open(encoding='utf-8'):
            e = json.loads(l)
            edges_in[e['anchorId']].append(e['prerequisiteId'])

    stat = collections.Counter()
    cand = []
    for r in byid.values():
        if not r.get('deprecated') or r.get('supersededBy') or live_kids[r['id']]:
            continue
        if not str(r.get('dropReason') or '').startswith(REASONS):
            continue
        if a.only and r['discipline'] != a.only:
            continue
        cand.append(r)
    print(f'复查 {len(cand)} 条')

    # ── 1. 可判定闸（一次批量，和 CI 同一个）──
    p = subprocess.run(['node', str(ROOT / 'scripts/lib/check-stdin.mjs')],
                       input='\n'.join(r['statement'] for r in cand), capture_output=True, text=True, timeout=600)
    verdicts = [json.loads(l) for l in p.stdout.splitlines() if l.strip()]
    if p.returncode != 0 or len(verdicts) != len(cand):
        sys.exit(f'可判定闸对不齐（{len(verdicts)} vs {len(cand)}），不敢往下走')
    pre = []
    for r, v in zip(cand, verdicts):
        src = (r.get('provenance') or {}).get('srcText') or ''
        if not v.get('ok'):
            stat['① 可判定闸拦下 → 维持弃用'] += 1
        elif not src or not grounded(r['statement'], src)[0]:
            stat['② 断言不忠于课标原句 → 维持弃用'] += 1
        elif norm(r['statement']) in live_st:
            stat['③ 已有同句在用 → 维持弃用'] += 1
        elif r['discipline'] not in OPEN_AT:
            stat['OPEN_AT 缺学科 → 跳过'] += 1
        else:
            pre.append(r)

    def ask(sysp, user, tag):
        h = hashlib.sha256((model + tag + sysp + user).encode()).hexdigest()[:24]
        cf = CACHE / f'{h}.json'
        if cf.exists():
            return json.loads(cf.read_text(encoding='utf-8'))
        for _ in range(3):
            try:
                txt = call(sysp, user, base, key, model)
            except Exception as e:
                return {'error': str(e)[:60]}
            m = re.search(r'\{.*\}', txt or '', re.S)
            try:
                o = json.loads(m.group(0)) if m else None
            except Exception:
                o = None
            if isinstance(o, dict):
                cf.write_text(json.dumps(o, ensure_ascii=False), encoding='utf-8')
                return o
        return {'error': '解析失败'}

    def work(r):
        src = (r.get('provenance') or {}).get('srcText', '')
        ev, ass = r.get('evidence'), None
        if placeholder(r):
            d = ask(F.SYS.format(stmt=r['statement'], src=src[:260]), '写。', 'draft')
            if d.get('error') or not d.get('ok'):
                return r, {'stage': 'draft', 'why': d.get('error') or ('写不出：' + str(d.get('why', ''))[:40])}
            ev, why = gate(d, r['statement'])
            if not ev:
                return r, {'stage': 'draft', 'why': '证据闸：' + why}
            ass = d.get('assessment')
        disc = r['discipline']
        lo, hi = OPEN_AT[disc]
        pres = [byid[x]['statement'] for x in edges_in.get(r['id'], [])[:5] if x in byid]
        user = (f"能力断言：{r['statement']}\n"
                f"领域：{r.get('strand') or '未标注'}\n"
                f"标注学段：{(r.get('stageHint') or {}).get('min','?')}–{(r.get('stageHint') or {}).get('max','?')}\n"
                f"掌握证据：{' / '.join(ev[:3])}\n"
                f"已标的直接前置：{' / '.join(pres) if pres else '（无）'}\n"
                f"来源：{disc}课标 第 {(r.get('provenance') or {}).get('srcPage','?')} 页")
        o = ask(REVIEW.format(disc=disc, open_at=f'{lo}–{hi} 年级'), user, 'review')
        if o.get('error') or not isinstance(o.get('issues'), list):
            return r, {'stage': 'review', 'why': o.get('error') or '回答里没有 issues 字段'}
        iss = [x for x in o['issues'] if isinstance(x, dict) and x.get('type')]
        iss, wd, why = split_stage_issues(r, fileof[r['id']], iss)
        return r, {'stage': 'ok', 'ev': ev, 'drafted': ass is not None or placeholder(r),
                   'assessment': ass, 'issues': iss, 'withdrawn': wd, 'why': why}

    log, revived = [], collections.defaultdict(list)
    with ThreadPoolExecutor(a.concurrency) as ex:
        for r, res in ex.map(work, pre):
            row = {'id': r['id'], 'discipline': r['discipline'], 'statement': r['statement'],
                   'dropReason': r.get('dropReason'), 'model': model,
                   **{k: v for k, v in res.items() if k != 'ev'}}
            log.append(row)
            if res['stage'] != 'ok':
                stat[f"④ {'起草证据' if res['stage'] == 'draft' else '复审调用'}失败 → 维持弃用"] += 1
                continue
            types = {x['type'] for x in res['issues']}
            if types - FIELD:
                stat[f"⑤ 复审也判了{'、'.join(sorted(types - FIELD))} → 维持弃用"] += 1
                row['outcome'] = 'kept'
                continue
            row['outcome'] = 'revived-disputed' if types else 'revived'
            stat['✓ 撤销弃用 → ai-reviewed' if not types else
                 f"✓ 撤销弃用 → disputed（只挂 {'、'.join(sorted(types))}）"] += 1
            revived[r['discipline']].append(r)
            if not a.write:
                continue
            old = r.pop('dropReason', '') or ''
            r['deprecated'] = False
            r['supersededBy'] = None
            if res['drafted']:
                r['evidence'] = res['ev']
                if r.get('evidenceSource') == 'capability-rewrite':
                    r['evidenceDrafted'] = True
                else:
                    r['evidenceSource'] = 'evidence-drafted'
            if res.get('assessment') and not r.get('assessment'):
                r['assessment'] = PARENT_ASK.sub('', res['assessment'])
            r['fieldIssues'] = [x for x in (r.get('fieldIssues') or []) if x != 'evidence-weak']
            if not r['fieldIssues']:
                r.pop('fieldIssues')
            r['reviewStatus'] = 'disputed' if res['issues'] else 'ai-reviewed'
            r['reviewedBy'] = sorted(set((r.get('reviewedBy') or []) + [by]))
            prior = [x for x in (r.get('aiIssues') or []) if x['type'] == 'resolved']
            r['aiIssues'] = res['issues'][:5] + prior + [{'type': 'resolved', 'by': by,
                                      'detail': f'撤销弃用（2026-09-28）。原弃用理由：{old[:90]}。'
                                                f'复查：可判定闸放行、断言忠于课标原句、另一个模型复审'
                                                + ('只挑了字段问题，进 disputed 排队' if res['issues'] else '未挑出问题')}] + \
                [{'type': 'resolved', 'by': by,
                  'detail': f"复审提了 stage（{x.get('detail','')[:40]}）→ 撤销：{res['why']}"} for x in res['withdrawn'][:1]]

    for k, n in sorted(stat.items()):
        print(f'  {n:>4}  {k}')
    print('  撤销弃用按学科：', {d: len(v) for d, v in sorted(revived.items(), key=lambda t: -len(t[1]))})
    for d, rs in list(revived.items())[:4]:
        for r in rs[:3]:
            print(f"    {r['id']} [{d}] {r['statement'][:40]}")
    LOG.write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in log), encoding='utf-8')
    if not a.write:
        print(f'（没写盘；明细见 {LOG.relative_to(ROOT)}；加 --write 写回）')
        return
    for f, rows in files.items():
        f.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')
    print(f'已写回，reviewedBy 记为 {by}')


if __name__ == '__main__':
    main()
