#!/usr/bin/env python3
"""
repair.py — 按课标原句修复存疑锚点。**有据重写，不是重新生成。**

905 条存疑锚点里，100% 都能拿回它在课标里的原句（provenance.srcText）。
所以正确的做法是修，不是删：AI 已经诊断出「哪里不对」，原句还在，
把两样一起交给模型，让它照着原句改对。

**科学性靠一条机械约束保证：改完的断言必须能从原句里推出来。**
落实为字面覆盖率检查 —— 改写后的实义字有多少出现在原句里。
低于阈值就判为「凭空发挥」，打回不采纳。没有这道检查，
「修复」和「换一个更好听的说法」就分不开了。

分流：
  · not-a-capability  → 不修，直接弃用（本来就不是学生能力，是教学建议/课程目标）
  · stage             → 只改学段，断言不动
  · 其余              → 照原句重写断言 + 证据

  python3 tools/repair.py [--only 数学] [--dry-run]
"""
import argparse, collections, hashlib, itertools, json, os, random, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib import request, error

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(__file__).parent / '.cache-repair'
STOP = set('的了和与或在是有能会对为以及等这那其中一个可以进行并且或者通过根据'
           '能够可能应该我们他们你们它们什么怎样如何')

SYS = """你是{disc}教研员，正在修一条从课标里抽坏了的能力断言。

给你三样东西：抽坏的断言、它的问题诊断、**课标原句**。

任务：**照着课标原句**把断言改对。

铁规矩：
1. **只能用原句里有的意思。** 原句没提的内容一个字都不许加 —— 这是修复不是创作。
   原句信息不够改成可判定的，就老实说改不了（fixable: false）。
2. 改完必须能对一个具体孩子答「会 / 不会」。
   ❌ 形成初步的数感    ❌ 体会解决问题的道理    ❌ 描述这些图形的特征（「这些」指代不明）
   ✅ 能说出不同数位上的数表示的数值        ✅ 能计算两位数和三位数的加减法
3. 句式统一为「能 + 可观察动词 + 明确对象」，8–40 字，不要顿号堆叠（最多 2 个）。
4. 指代词（这些/该/上述）必须换成具体所指，换不出来就是改不了。
5. 证据写 2 条，每条是旁观者能看见的具体行为，比断言更具体。

只输出一行 JSON，不要代码块：
{{"fixable":true,"statement":"…","verb":"…","object":"…","evidence":["…","…"],"stage":"G3","why":"改了什么"}}
stage 只在诊断里有学段问题时给，否则留空字符串。改不了就 {{"fixable":false,"why":"原句只是教学建议，不含学生能力"}}"""

ENDPOINTS = [("/v1/chat/completions", "openai"), ("/anthropic/v1/messages", "anthropic")]
_rr = itertools.count()


def call(sysp, user, base, key, model, timeout=120):
    last = None
    for attempt in range(7):
        suffix, style = ENDPOINTS[next(_rr) % len(ENDPOINTS)]
        if style == "anthropic":
            body = {"model": model, "max_tokens": 600, "thinking": {"type": "disabled"},
                    "system": sysp, "messages": [{"role": "user", "content": user}]}
            hdr = {"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
        else:
            body = {"model": model, "temperature": 0, "max_completion_tokens": 600,
                    "thinking": {"type": "disabled"},
                    "messages": [{"role": "system", "content": sysp}, {"role": "user", "content": user}]}
            hdr = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
        req = request.Request(base + suffix, data=json.dumps(body).encode(), headers=hdr)
        try:
            d = json.load(request.urlopen(req, timeout=timeout))
            if style == "anthropic":
                return "".join(b.get("text", "") for b in d.get("content", []))
            return d['choices'][0]['message'].get('content') or ''
        except error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code not in (429, 500, 502, 503, 504):
                raise RuntimeError(f"HTTP {e.code}")
        except Exception as e:
            last = type(e).__name__
        time.sleep(min(25.0, 1.4 * (1.9 ** attempt)) * (.6 + random.random() * .8))
    raise RuntimeError(f"重试耗尽（{last}）")


def grounded(new_stmt, src, thresh=0.62):
    """字面覆盖率：改写后的实义字有多少出现在课标原句里。

    这是「修复」和「创作」的分界线。没有这道检查，模型可以把
    「体会解决问题的道理」改成任何一句好听的可判定断言，
    而那句话跟课标已经没关系了 —— 那不是修数据，是造数据。
    """
    a = {c for c in new_stmt if '一' <= c <= '鿿'} - STOP
    b = {c for c in src if '一' <= c <= '鿿'}
    if not a:
        return False, 0.0
    r = len(a & b) / len(a)
    return r >= thresh, r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default=None)
    ap.add_argument('--concurrency', type=int, default=10)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    base, key, model = os.environ['MIMO_BASE'], os.environ['MIMO_KEY'], os.environ.get('MIMO_MODEL', 'mimo-v2.5')
    CACHE.mkdir(exist_ok=True)

    files = {f: [json.loads(l) for l in f.open(encoding='utf-8')]
             for f in sorted((ROOT / 'anchors').rglob('*.jsonl'))}
    todo = [(f, i, r) for f, rows in files.items() for i, r in enumerate(rows)
            if r['reviewStatus'] == 'disputed' and (r.get('provenance') or {}).get('srcText')
            and (not a.only or r['discipline'] == a.only)]
    print(f"待修 {len(todo)} 条 · 并发 {a.concurrency}")

    def work(job):
        f, i, r = job
        iss = r.get('aiIssues') or []
        types = {x.get('type') for x in iss}
        # not-a-capability 不修：它根本不是学生能力，改写只会把教学建议包装成能力
        if 'not-a-capability' in types:
            return f, i, {'verdict': 'drop', 'why': 'AI 判定不是学生能力（教学建议/课程目标）'}
        p = r['provenance']
        user = (f"抽坏的断言：{r['statement']}\n"
                f"当前学段：{(r.get('stageHint') or {}).get('min','?')}\n"
                f"当前证据：{' / '.join((r.get('evidence') or [])[:2])}\n"
                f"问题诊断：" + '；'.join(f"{x['type']}：{x.get('detail','')[:90]}" for x in iss[:3]) + "\n"
                f"**课标原句**：{p['srcText'][:220]}\n"
                f"出处：{r['discipline']}课标 第 {p.get('srcPage','?')} 页")
        sysp = SYS.format(disc=r['discipline'])
        h = hashlib.sha256((sysp + user).encode()).hexdigest()[:24]
        cf = CACHE / f"{h}.json"
        if cf.exists():
            return f, i, json.loads(cf.read_text())
        try:
            txt = call(sysp, user, base, key, model)
        except Exception as e:
            return f, i, {'verdict': 'error', 'why': str(e)[:40]}
        m = re.search(r'\{.*\}', txt, re.S)
        o = {}
        if m:
            try:
                o = json.loads(m.group(0))
            except Exception:
                o = {'verdict': 'error', 'why': '解析失败'}
        cf.write_text(json.dumps(o, ensure_ascii=False))
        return f, i, o

    t0 = time.time()
    stat = collections.Counter()
    pending = []           # 待过闸的修复结果
    with ThreadPoolExecutor(a.concurrency) as ex:
        for n, (f, i, o) in enumerate(ex.map(work, todo), 1):
            r = files[f][i]
            v = o.get('verdict')
            if v == 'drop':
                r['deprecated'] = True
                r['supersededBy'] = None
                r['dropReason'] = o.get('why', '')
                stat['弃用'] += 1
            elif v == 'error' or o.get('error'):
                stat['调用失败'] += 1
            elif o.get('fixable') is False:
                r['repairAttempt'] = {'fixable': False, 'why': (o.get('why') or '')[:120]}
                stat['原句信息不足，改不了'] += 1
            elif o.get('statement'):
                ok, ratio = grounded(o['statement'], r['provenance']['srcText'])
                if not ok:
                    r['repairAttempt'] = {'fixable': False,
                                          'why': f"改写脱离课标原句（字面覆盖 {ratio:.0%} < 62%），不采纳"}
                    stat['脱离原句，打回'] += 1
                else:
                    pending.append((f, i, o, ratio))
            else:
                stat['无产出'] += 1
            if n % 100 == 0 or n == len(todo):
                print(f"  {n}/{len(todo)}（{time.time()-t0:.0f}s）", flush=True)

    # ── 过可判定性闸：改完还是不可判定的，一律不采纳 ──
    if pending:
        payload = '\n'.join(json.dumps({'statement': o['statement'], 'discipline': files[f][i]['discipline'],
                                        'k': k}, ensure_ascii=False)
                            for k, (f, i, o, _) in enumerate(pending))
        res = subprocess.run(['node', str(ROOT / 'scripts/decide.mjs')], input=payload,
                             capture_output=True, text=True)
        verdicts = {json.loads(l)['k']: json.loads(l) for l in res.stdout.split('\n') if l.strip()}
        for k, (f, i, o, ratio) in enumerate(pending):
            r = files[f][i]
            d = verdicts.get(k, {})
            if not d.get('ok'):
                r['repairAttempt'] = {'fixable': False,
                                      'why': '改写后仍不过可判定性闸：' + '；'.join(d.get('reasons', []))[:110]}
                stat['改完仍不可判定'] += 1
                continue
            # 改前=改后 → 这不是修复，是**复审推翻了初判**。
            # 混在「修复成功」里会虚报工作量，也会掩盖「AI 初判误报率有多高」这个信号。
            if d['normalized'].strip() == r['statement'].strip():
                r['repairAttempt'] = {'fixable': True, 'noop': True,
                                      'why': '复审认为原断言本身没问题：' + (o.get('why') or '')[:100]}
                r['reviewStatus'] = 'llm-proposed'
                r.pop('aiIssues', None)
                stat['复审推翻初判'] += 1
                continue
            r['statementBefore'] = r['statement']
            r['statement'] = d['normalized']
            r['verb'] = o.get('verb') or d.get('verb') or r['verb']
            r['object'] = (o.get('object') or r['object'])[:40]
            if o.get('evidence'):
                r['evidence'] = [str(x)[:60] for x in o['evidence'] if isinstance(x, str)][:4]
                r['evidenceSource'] = 'repaired-from-source'
            st = (o.get('stage') or '').strip()
            if re.fullmatch(r'G[1-9]', st):
                r['stageHint'] = {'min': st, 'max': st}
            r['repair'] = {'why': (o.get('why') or '')[:120], 'grounding': round(ratio, 2)}
            r['reviewStatus'] = 'llm-proposed'      # 修完退回未审，等重跑 AI 审查
            r.pop('aiIssues', None)
            stat['修复成功'] += 1

    if not a.dry_run:
        for f, rows in files.items():
            with f.open('w', encoding='utf-8') as fh:
                for r in rows:
                    fh.write(json.dumps(r, ensure_ascii=False) + '\n')

    print(f"\n用时 {time.time()-t0:.0f}s")
    for k, v in stat.most_common():
        print(f"  {k:<22} {v:>4}")
    print("\n  修复成功的已退回 llm-proposed，需重跑 enrich_review 复审。")
    print("  弃用的标了 deprecated —— 不删除，因为档案里可能已有引用。")


if __name__ == '__main__':
    main()
