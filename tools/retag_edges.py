#!/usr/bin/env python3
"""
retag_edges.py — 给 3,069 条先修边补上语义类型与失败表征（specs/001）。

## 判据只有一条

> **能否描述出，不具备前置的孩子在后继上失败时的具体、可观察的表现。**

描述不出来的，一律降为 `convention` 并移出推理图。
这和锚点的判据「能不能对一个具体孩子答会/不会」同构 —— 两者都要求落到可观测。

现状：3,069 条边只有一种语义（「A 排在 B 之前」），`strength` 是 3,066 soft / 3 hard
（等于没用过），`evidence` 里两项都是样板（「课标学段序：G10 → G10」去重后只有 26 个值，
其中 1,441 条两端学段相同 ＝ 零信息；「候选池 40 选 5」是取样记录不是证据）。
所以这一轮同时把 evidence 里的假证据处理掉。

## 两段式，顺序不可颠倒

**第一段不告诉模型存在分类任务**，只问失败表现：

    一个完全不会「A」的孩子去做「B」，他会失败在哪一步？
    如果你认为他不会失败，就直接回答「不会失败」。

**第二段只给 signature，不给两端断言**，按四类词表分类。

理由：一次性问「这是什么类型」，模型会先选标签再倒推理由，产出的是无法证伪的标签。
这和 `adversarial_verify.py` 是同一个道理 —— **换的是信息流，不是措辞**。
第一段答「不会失败」的直接置为 convention，**不进第二段**（省一半调用，也堵死
「先分类再补理由」的路）。

## 增量

按 `retagHash = sha256(前置断言 → 后继断言)` 跳过未变更的边。
锚点涨到 10,000 时全量重跑的模型成本是线性的 —— **增量是架构要求，不是优化项**。
全量重跑要显式 `--force-all`。

## 闸（机械，全部在 validate.mjs 里也有一份，编号一致）

  F002  type 必须在 component/instrument/semantic/convention 内
  F003  convention 不得进推理图
  F004  failureSignature 非空且 ≥12 字（convention 边固定为「无可观测影响」）
  F005  failureSignature 不得命中空泛词黑名单
  W104  instrument 不得标 hard（按定义它就是「能到但绕远路」）

模型给的 type 若与它自己写的 signature 矛盾（例如说「不会失败」却分类成 component），
以第一段为准 —— **第一段是证据，第二段只是给证据贴标签**。

    python3 tools/retag_edges.py --dry-run --limit 30
    python3 tools/retag_edges.py --only 数学
    python3 tools/retag_edges.py
"""
import argparse, collections, hashlib, json, os, re, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repair import call            # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(__file__).parent / '.cache-retag'

TYPES = ('component', 'instrument', 'semantic', 'convention')
BLACKLIST = ['基础不牢', '基本功不扎实', '能力不足', '理解不深', '知识欠缺',
             '思维能力差', '学习习惯不好', '掌握不牢', '理解不到位']
MIN_SIG = 12
CONVENTION_SIG = '无可观测影响'
NO_FAIL = '不会失败'

# ── 第一段：只问失败表现，**不提分类** ────────────────────────────────
SYS1 = """你是{disc}老师。回答一个只关于课堂现象的问题。

一个学生**完全不会**下面这条 A，现在让他去做 B。

A（他不会的）：{pre}
B（要他做的）：{post}

他会失败在哪一步？请描述**具体的、可观察的**表现 —— 一个旁观者站在旁边能看见什么。

要求：
1. 说具体动作和具体错法，不说抽象评价。
   ❌ 基础不牢／理解不深／能力不足        这些等于没说
   ✅ 列竖式时个位不够减，直接拿小的减大的，得出 5-8=3
2. 20–60 字，一句话。
3. **如果不会 A 其实并不妨碍做 B**（比如两者只是教材前后排在一起，
   或者不会 A 也能用别的办法完成 B 且不吃亏），就只回答四个字：不会失败

只输出一行 JSON，不要代码块：
{{"signature":"…"}}
{{"signature":"不会失败"}}"""

# ── 第二段：只给 signature，**不给两端断言** ──────────────────────────
SYS2 = """把一句「失败表现」归到四类关系里的一类。**你看不到原始的两条能力，这是有意的** ——
只凭这句失败表现判断。

  component  前置是后继的一个子动作。失败表现是：会做，但某一步系统性地错，错点能定位。
  instrument 做后继时拿前置当手段。失败表现是：能做到，但绕远路、很慢、用笨办法。
  semantic   不懂前置则后继的表述本身没有意义。失败表现是：读不懂题、答非所问、整片空白。
  convention 没有可观测的影响。

再判 strength：
  hard  不具备就卡死，做不出来
  soft  能做出来，只是更慢或更差
**instrument 按定义就是「能到但绕远路」，所以永远是 soft。**

失败表现：{sig}

只输出一行 JSON：{{"type":"component","strength":"hard"}}"""


def sha(pre, post):
    return hashlib.sha256(f'{pre}→{post}'.encode()).hexdigest()[:16]


def one_json(raw):
    m = re.search(r'\{.*\}', raw or '', re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default=None)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--concurrency', type=int, default=12)
    ap.add_argument('--force-all', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    base, key = os.environ['MIMO_BASE'], os.environ['MIMO_KEY']
    model = os.environ.get('MIMO_MODEL', 'mimo-v2.5')
    CACHE.mkdir(exist_ok=True)

    A = {}
    for f in sorted((ROOT / 'anchors').glob('*.jsonl')):
        for l in f.open(encoding='utf-8'):
            if l.strip():
                x = json.loads(l); A[x['id']] = x
    live = lambda i: i in A and not A[i].get('deprecated')

    files = {f: [json.loads(l) for l in f.open(encoding='utf-8') if l.strip()]
             for f in sorted((ROOT / 'edges').glob('*.jsonl'))}

    jobs = []
    for f, rows in files.items():
        for i, e in enumerate(rows):
            if e.get('retired') or not live(e.get('anchorId')) or not live(e.get('prerequisiteId')):
                continue
            pre, post = A[e['prerequisiteId']], A[e['anchorId']]
            h = sha(pre['statement'], post['statement'])
            if not a.force_all and e.get('retagHash') == h and e.get('type'):
                continue
            if a.only and post['discipline'] != a.only:
                continue
            jobs.append((f, i, e, pre, post, h))
    if a.limit:
        jobs = jobs[:a.limit]
    total_live = sum(1 for rows in files.values() for e in rows
                     if not e.get('retired') and live(e.get('anchorId')) and live(e.get('prerequisiteId')))
    print(f"待重标 {len(jobs)} / 存活边 {total_live}"
          f"（增量已跳过 {total_live - len(jobs) if not a.only else 0} 条）")

    def work(job):
        f, i, e, pre, post, h = job
        cf = CACHE / f'{h}.json'
        if cf.exists():
            return job, json.loads(cf.read_text(encoding='utf-8'))
        # 第一段
        try:
            r1 = call(SYS1.format(disc=post['discipline'], pre=pre['statement'], post=post['statement']),
                      '答。', base, key, model)
        except Exception as ex:
            return job, {'err': f'第一段调用失败：{type(ex).__name__}'}
        d1 = one_json(r1)
        if not d1 or not isinstance(d1.get('signature'), str):
            return job, {'err': '第一段没吐 JSON'}
        sig = d1['signature'].strip()
        if NO_FAIL in sig or sig == NO_FAIL:
            out = {'type': 'convention', 'strength': 'soft', 'signature': CONVENTION_SIG}
            cf.write_text(json.dumps(out, ensure_ascii=False), encoding='utf-8')
            return job, out
        # 第二段：只给 signature
        try:
            r2 = call(SYS2.format(sig=sig), '判。', base, key, model)
        except Exception as ex:
            return job, {'err': f'第二段调用失败：{type(ex).__name__}'}
        d2 = one_json(r2) or {}
        out = {'type': d2.get('type'), 'strength': d2.get('strength'), 'signature': sig}
        cf.write_text(json.dumps(out, ensure_ascii=False), encoding='utf-8')
        return job, out

    results = []
    with ThreadPoolExecutor(a.concurrency) as ex:
        for n, r in enumerate(ex.map(work, jobs), 1):
            results.append(r)
            if n % 200 == 0:
                print(f'  …{n}/{len(jobs)}', flush=True)

    stat, rej = collections.Counter(), collections.Counter()
    applied = []
    for job, out in results:
        f, i, e, pre, post, h = job
        if out.get('err'):
            rej[out['err'].split('：')[0]] += 1
            continue
        t, s, sig = out.get('type'), out.get('strength'), (out.get('signature') or '').strip()
        if t not in TYPES:
            rej[f'F002 type 词表外'] += 1; continue
        if t == 'convention':
            sig, s = CONVENTION_SIG, 'soft'
        else:
            if len(sig) < MIN_SIG:
                rej['F004 失败表征过短'] += 1; continue
            hit = next((w for w in BLACKLIST if w in sig), None)
            if hit:
                rej[f'F005 空泛词「{hit}」'] += 1; continue
        if s not in ('hard', 'soft'):
            s = 'soft'
        if t == 'instrument':
            s = 'soft'          # W104：可绕过的关系不应卡死
        applied.append((f, i, t, s, sig, h))
        stat[t] += 1
        stat[f'  └ {t}/{s}'] += 1

    print(f"\n重标成功 {len(applied)} · 未采纳 {sum(rej.values())}")
    for k in TYPES:
        if stat[k]:
            print(f"  {stat[k]:>5}  {k}")
    for k, n in rej.most_common(8):
        print(f"  拒 {n:>4}  {k}")

    print("\n─── 样本 ───")
    shown = 0
    seen_t = set()
    for job, out in results:
        f, i, e, pre, post, h = job
        t = out.get('type')
        if t in TYPES and t not in seen_t and not out.get('err'):
            seen_t.add(t); shown += 1
            print(f"  [{t}] {pre['statement'][:30]}  →  {post['statement'][:30]}")
            print(f"        失败表现：{out.get('signature')}")
    print()

    if a.dry_run:
        print('（--dry-run：没有写盘）')
        return

    for f, i, t, s, sig, h in applied:
        e = files[f][i]
        e['type'] = t
        e['strength'] = s
        e['failureSignature'] = sig
        e['inInferenceGraph'] = (t != 'convention')
        e['retagHash'] = h
        # 假证据一并收掉：「课标学段序：G10 → G10」两端学段相同时是零信息，
        # 而 validate 的「hard 边须有非 llm 证据」把它当成证据 —— 闸被样板绕过。
        ev = []
        for v in (e.get('evidence') or []):
            d = str(v.get('detail') or '')
            m = re.match(r'^课标学段序：(G\d+) → (G\d+)$', d)
            if m and m.group(1) == m.group(2):
                continue                     # 零信息，丢掉
            if v.get('kind') == 'llm' and d.startswith('候选池'):
                v = {'kind': 'llm', 'detail': d + '；本轮已两段式重标'}
            ev.append(v)
        ev.append({'kind': 'expert' if False else 'llm',
                   'detail': f'两段式重标：先写失败表现（不告知有分类任务），再独立调用分类为 {t}'})
        e['evidence'] = ev
    for f, rows in files.items():
        with f.open('w', encoding='utf-8') as fh:
            for e in rows:
                fh.write(json.dumps(e, ensure_ascii=False) + '\n')
    print(f'已写盘 {len(applied)} 条。记得 npm run check + npm run fw-report')


if __name__ == '__main__':
    main()
