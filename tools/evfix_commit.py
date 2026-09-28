#!/usr/bin/env python3
"""
evfix_commit.py — 把 tools/out/evidence-fix.jsonl 里过了闸的证据写回锚点，**再让 AI 复审一遍**才升档。

背景（CHANGELOG v1.4）：252 条断言过了 AI 复核，但证据是占位模板
（「能在X课堂或作业情境中完成：<断言原文>」），被卡在 llm-proposed + fieldIssues:evidence-weak；
另有 32 条 disputed 的唯一异议就是 evidence-weak。_evfix.py 给这 284 条起草了真证据。

**为什么不直接升档。** 原来的复核看的是占位证据。换了证据等于换了被审的东西 ——
新证据可能编出了课标里没有的要求，也可能跟断言对不上。所以写回之后用 ai_review 的
同一份提示词、同一种输入格式再审一次，审过了才升 ai-reviewed，挑出问题的进 disputed。

**这一轮的一个弱点，照实记下来。** 证据起草和复审用的是同一个模型
（火山方舟 DeepSeek V4.1 Flash：当时 mimo 额度用完）。同一个模型审自己写的东西，
比换一个模型审要宽。reviewedBy 里单独记了模型名，哪天要换模型重审，按它筛出来就行。

    LLM_BASE=… LLM_KEY=… LLM_MODEL=… LLM_ENDPOINT=/chat/completions python3 tools/evfix_commit.py            # 只看不写
    … python3 tools/evfix_commit.py --write
"""
import sys
sys.dont_write_bytecode = True

import argparse, collections, hashlib, json, os, random, re, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib import request, error

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
from ai_review import SYS, OPEN_AT            # noqa: E402  同一份提示词，不另写
from fix_src_stages import read_bands, STD    # noqa: E402  学段划分只有一份定义

SRC = TOOLS / 'out' / 'evidence-fix.jsonl'
CACHE = TOOLS / 'out' / '.cache-evfix-review'
PARENT_ASK = re.compile(r'^(家长|您|可以)[^，,。]{0,6}问[:：]\s*')


def call(sysp, user, base, key, model, suffix, timeout=120):
    last = None
    for attempt in range(8):
        body = {"model": model, "temperature": 0, "max_completion_tokens": 700,
                "thinking": {"type": "disabled"},
                "messages": [{"role": "system", "content": sysp}, {"role": "user", "content": user}]}
        req = request.Request(base + suffix, data=json.dumps(body).encode(),
                              headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        try:
            d = json.load(request.urlopen(req, timeout=timeout))
            return d['choices'][0]['message'].get('content') or ''
        except error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code == 429 and b'quota exhausted' in (e.read() or b''):
                raise RuntimeError('quota exhausted')
            if e.code not in (429, 500, 502, 503, 504):
                raise RuntimeError(last)
        except Exception as e:
            last = type(e).__name__
        time.sleep(min(25.0, 1.4 * (1.9 ** attempt)) * (.6 + random.random() * .8))
    raise RuntimeError(f"重试耗尽（{last}）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--concurrency', type=int, default=10)
    a = ap.parse_args()
    base, key = os.environ['LLM_BASE'], os.environ['LLM_KEY']
    model = os.environ['LLM_MODEL']
    suffix = os.environ.get('LLM_ENDPOINT', '/chat/completions')
    by = 'ai:' + re.sub(r'-\d{6}$', '', model) + '-' + time.strftime('%Y-%m-%d')
    CACHE.mkdir(exist_ok=True)

    drafts = {}
    for l in SRC.read_text(encoding='utf-8').splitlines():
        r = json.loads(l)
        if r['ok']:
            drafts[r['id']] = r

    files = {f: [json.loads(l) for l in f.read_text(encoding='utf-8').splitlines() if l.strip()]
             for f in sorted((ROOT / 'anchors').rglob('*.jsonl'))}
    byid = {r['id']: r for rows in files.values() for r in rows}
    fileof = {r['id']: f.name for f, rows in files.items() for r in rows}
    BANDS, _ = read_bands()

    def doc_stage(r):
        """课标文件本身定下的学段。**课标写了学段，模型的意见不能盖过课标**（resolve_disputed ①②）。"""
        if fileof[r['id']].startswith('gaozhong-'):
            return (10, 12), '出自普通高中课标，学段由文档决定'
        m = re.fullmatch(r'第([一二三四])学段', ((r.get('provenance') or {}).get('srcStage') or '').strip())
        if m:
            return BANDS.get(r['discipline'], STD)[m.group(1)], f'课标正文标了{m.group(0)}'
        return None, None
    edges_in = collections.defaultdict(list)
    for f in sorted((ROOT / 'edges').rglob('*.jsonl')):
        for l in f.open(encoding='utf-8'):
            e = json.loads(l)
            edges_in[e['anchorId']].append(e['prerequisiteId'])

    # 只动还处在原状态的：起草之后若有人改过（升档 / 弃用），不覆盖
    jobs = []
    for i, d in drafts.items():
        r = byid.get(i)
        if not r or r.get('deprecated'):
            continue
        if d['group'] == 'held' and r['reviewStatus'] != 'llm-proposed':
            continue
        if d['group'] == 'disputed-ev-only' and r['reviewStatus'] != 'disputed':
            continue
        jobs.append((r, d))
    print(f'过闸草稿 {len(drafts)} · 可写回 {len(jobs)}')

    def work(job):
        r, d = job
        disc = r['discipline']
        lo, hi = OPEN_AT[disc]
        sysp = SYS.format(disc=disc, open_at=f'{lo}–{hi} 年级')
        pres = [byid[p]['statement'] for p in edges_in.get(r['id'], [])[:5] if p in byid]
        # 与 ai_review.work() 同一种输入格式，只是证据换成新起草的
        user = (f"能力断言：{r['statement']}\n"
                f"领域：{r.get('strand') or '未标注'}\n"
                f"标注学段：{(r.get('stageHint') or {}).get('min','?')}–{(r.get('stageHint') or {}).get('max','?')}\n"
                f"掌握证据：{' / '.join(d['evidence'][:3])}\n"
                f"已标的直接前置：{' / '.join(pres) if pres else '（无）'}\n"
                f"来源：{disc}课标 第 {(r.get('provenance') or {}).get('srcPage','?')} 页")
        h = hashlib.sha256((model + '\n' + sysp + user).encode()).hexdigest()[:24]
        cf = CACHE / f'{h}.json'
        if cf.exists():
            return job, json.loads(cf.read_text(encoding='utf-8'))
        try:
            txt = call(sysp, user, base, key, model, suffix)
        except Exception as e:
            return job, {'error': str(e)[:60]}
        m = re.search(r'\{.*\}', txt, re.S)
        try:
            o = json.loads(m.group(0)) if m else {'error': '没吐 JSON'}
        except Exception:
            o = {'error': '解析失败'}
        # 与 ai_review 同一条：「没挑出问题」必须来自一个有 issues 键的回答
        if 'error' not in o and not isinstance(o.get('issues'), list):
            o = {'error': '回答里没有 issues 字段'}
        if 'error' not in o:
            cf.write_text(json.dumps(o, ensure_ascii=False), encoding='utf-8')
        return job, o

    stat, kinds, samples = collections.Counter(), collections.Counter(), collections.defaultdict(list)
    with ThreadPoolExecutor(a.concurrency) as ex:
        for (r, d), o in ex.map(work, jobs):
            g = d['group']
            if o.get('error'):
                stat[f'{g} 复审调用失败 → 不动'] += 1
                continue
            r['evidence'] = d['evidence']
            if r.get('evidenceSource') == 'capability-rewrite':
                r['evidenceDrafted'] = True
            else:
                r['evidenceSource'] = 'evidence-drafted'
            if d.get('assessment') and not r.get('assessment'):
                r['assessment'] = PARENT_ASK.sub('', d['assessment'])
            iss = [x for x in (o.get('issues') or []) if isinstance(x, dict) and x.get('type')]
            withdrawn = []
            ds, why = doc_stage(r)
            h = r.get('stageHint') or {}
            if ds and (h.get('min'), h.get('max')) == (f'G{ds[0]}', f'G{ds[1]}'):
                withdrawn = [x for x in iss if x['type'] == 'stage']
                iss = [x for x in iss if x['type'] != 'stage']
                if withdrawn:
                    stat['  其中 stage 异议被课标学段撤销'] += 1
            fi = [x for x in (r.get('fieldIssues') or []) if x != 'evidence-weak']
            if any(x['type'] == 'evidence-weak' for x in iss):
                fi.append('evidence-weak')
            if fi:
                r['fieldIssues'] = sorted(set(fi))
            else:
                r.pop('fieldIssues', None)
            r['reviewedBy'] = sorted(set((r.get('reviewedBy') or []) + [by]))
            wd = [{'type': 'resolved', 'by': by,
                   'detail': f"复审提了 stage（{x.get('detail','')[:40]}）→ 撤销：{why}，模型的意见不能盖过课标"}
                  for x in withdrawn[:1]]
            if iss:
                r['aiIssues'] = iss[:5] + wd
                r['reviewStatus'] = 'disputed'
                key_ = f'{g} → disputed（复审挑出问题）'
                for x in iss:
                    kinds[x['type']] += 1
            else:
                if g == 'disputed-ev-only':
                    old = next((x for x in r.get('aiIssues') or [] if x['type'] == 'evidence-weak'), {})
                    r['aiIssues'] = [{'type': 'resolved', 'by': by,
                                      'detail': f"原异议 evidence-weak（{old.get('detail','')[:60]}）："
                                                f"证据已重写，复审未挑出问题"}] + wd
                elif wd:
                    r['aiIssues'] = wd
                r['reviewStatus'] = 'ai-reviewed'
                key_ = f'{g} → ai-reviewed'
            stat[key_] += 1
            samples[key_].append(r)

    for k, n in sorted(stat.items()):
        print(f'  {n:>4}  {k}')
    print('  复审挑出的问题类型：', dict(kinds.most_common()))
    for k, rs in samples.items():
        if 'disputed' in k:
            for r in rs[:4]:
                print(f"    {r['id']} {r['statement'][:30]} ← {r['aiIssues'][0]['type']}：{r['aiIssues'][0].get('detail','')[:60]}")
    if not a.write:
        print('（没写盘；加 --write 写回）')
        return
    for f, rows in files.items():
        f.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')
    print(f'已写回，reviewedBy 记为 {by}')


if __name__ == '__main__':
    main()
