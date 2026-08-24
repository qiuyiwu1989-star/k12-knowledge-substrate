#!/usr/bin/env python3
"""
adjudicate.py — 裁决 disputed：那条异议到底成不成立。

## 怎么避免「同一个模型自己确认自己」

`ai_review` 当初挑错时，**看不到课标原文** —— 它拿到的是断言、领域、学段、
证据、前置、页码。所以裁决这一步改的是**信息流**，不是措辞（和
`adversarial_verify.py` 同一个道理）：

    挑错时：断言 + 证据 ──→ 「有什么问题」
    裁决时：断言 + **课标原文** + 那条具体异议 ──→ 「这条异议对着原文还成立吗」

裁决者能看到挑错者没看到的东西，所以它有资格推翻。

## 三个判决

  uphold    异议成立 → **弃用**。这条锚点本来就不该存在
  overrule  异议不成立 → 退回 ai-reviewed
  unclear   判不了 → 保留 disputed，等人

## overrule 有两道硬闸

**一、必须从原文里引一句**

推翻异议 = 主张「课标确实要求这件事」。那就得**指出课标哪句话要求的**。
引文逐字核对是不是 srcText 的子串，**对不上就不算推翻** ——
降级为 unclear。没有这道闸，模型可以凭空推翻任何异议。

（这条闸抓的是同一类毛病：`make_assessment` 用「实词不得超出断言与证据」，
`atomize` 用「拆出的字必须全部来自原句」。**凡是模型要主张什么，
就要它从原文里指出来。**）

**二、不许推翻我们自己的闸**

裁决者可以推翻**模型的意见**，不能推翻**这个项目自己的机器闸**。
断言完全可能是课标原话、同时仍然不可判定 —— 「能体会…的意义」就是这样，
它逐字来自课标，但对一个具体孩子答不出「会/不会」。
所以 overrule 之前再过一遍 `check-stdin.mjs`，闸拒的一律降为 unclear。

## uphold 直接弃用，不留 disputed

`disputed` 已经证明是终态垃圾桶：进去就没人管，越积越多（144 → 977）。
裁决的意义就是给出下落，所以 uphold 就弃用、写清 dropReason。
**弃用是标记不是删除** —— 那一行留在文件里，档案引用解析得到。

    python3 tools/adjudicate.py --dry-run --limit 30
    python3 tools/adjudicate.py --only 数学
    python3 tools/adjudicate.py
"""
import argparse, collections, hashlib, json, os, re, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repair import call        # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(__file__).parent / '.cache-adjud'

SYS = """你在裁决一条异议。有人对下面这条能力锚点提了意见，你要判断**这条意见成不成立**。

课标原文（教育部文件的原话）：
{src}

从原文改写出来的能力断言：
{stmt}

有人提的意见：
{issues}

**关键：提意见的人没有看到课标原文，你看到了。** 所以你有资格推翻他。

判三种：

  uphold    意见成立 —— 这条断言确实不该留。典型：
              · 主语不是学生（是教师该做什么、教材该怎么编）
              · 是残句，缺主干
              · 原文根本没要求这件事，是改写时加的
  overrule  意见不成立 —— 课标确实要求学生做这件事，断言是忠实的。
              **必须从上面的原文里逐字引一句支持它的话。**
              引文对不上原文，你这条推翻就作废。
  unclear   判不了 —— 原文不够、或者这是真需要教学经验的判断。老实说不知道。

注意几种常见的误判，遇到就 overrule：
  · 「能了解 X」被说成「不可判定」—— 但课标原文写的就是「了解 X」，
    我们的判据允许把它当作「能说出 X」。**忠实转述不该因为课标用词而被否**。
  · 「能说出…」被说成「是知识不是能力」—— 说得出来本身就是可观察的行为。
  · 断言比原文短、丢了一些修饰 —— 那是拆句，不是不忠实。

拿不准就 unclear。**硬判比不判更糟** —— 这批数据后面还要给人看。

只输出一行 JSON，不要代码块：
{{"verdict":"overrule","quote":"从原文里逐字抄的一句","why":"…"}}
{{"verdict":"uphold","why":"原文说的是教师应当引导学生…，主语是教师"}}
{{"verdict":"unclear","why":"…"}}"""


def norm(t):
    return re.sub(r'\s+', '', t or '')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default=None)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--concurrency', type=int, default=12)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    base, key = os.environ['MIMO_BASE'], os.environ['MIMO_KEY']
    model = os.environ.get('MIMO_MODEL', 'mimo-v2.5')
    CACHE.mkdir(exist_ok=True)

    files = {f: [json.loads(l) for l in f.read_text(encoding='utf-8').splitlines() if l.strip()]
             for f in sorted((ROOT / 'anchors').glob('*.jsonl'))}
    targets = [(f, i, x) for f, rows in files.items() for i, x in enumerate(rows)
               if not x.get('deprecated') and x['reviewStatus'] == 'disputed'
               and (x.get('provenance') or {}).get('srcText')
               and [q for q in (x.get('aiIssues') or []) if q.get('type') != 'resolved']
               and (not a.only or x['discipline'] == a.only)]
    if a.limit:
        targets = targets[:a.limit]
    print(f'待裁决 {len(targets)} 条')

    def work(job):
        f, i, x = job
        src = (x.get('provenance') or {}).get('srcText', '')[:400]
        live = [q for q in (x.get('aiIssues') or []) if q.get('type') != 'resolved']
        issues = '\n'.join(f"· [{q['type']}] {q.get('detail','')[:160]}" for q in live)
        sysp = SYS.format(src=src, stmt=x['statement'], issues=issues)
        h = hashlib.sha256(sysp.encode()).hexdigest()[:24]
        cf = CACHE / f'{h}.json'
        if cf.exists():
            return job, json.loads(cf.read_text(encoding='utf-8'))
        try:
            raw = call(sysp, '裁。', base, key, model)
        except Exception as e:
            return job, {'verdict': 'error', 'why': type(e).__name__}
        m = re.search(r'\{.*\}', raw or '', re.S)
        try:
            d = json.loads(m.group(0)) if m else {'verdict': 'error', 'why': '没吐 JSON'}
        except Exception:
            d = {'verdict': 'error', 'why': 'JSON 解析失败'}
        cf.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
        return job, d

    res = []
    with ThreadPoolExecutor(a.concurrency) as ex:
        for n, r in enumerate(ex.map(work, targets), 1):
            res.append(r)
            if n % 100 == 0:
                print(f'  …{n}/{len(targets)}', flush=True)

    # 先批量过一遍我们自己的可判定闸 —— 裁决者可以推翻**模型的意见**，
    # 但不能推翻**这个项目自己的机器闸**。
    # 断言完全可能是课标原话、同时仍然不可判定（「能体会…的意义」就是这样），
    # 那种情况下 overrule 会把一条不可判定的锚点放回可引用集合。
    import subprocess
    stmts = [x['statement'] for (_, _, x), _ in res]
    pr = subprocess.run(['node', str(ROOT / 'scripts/lib/check-stdin.mjs')],
                        input='\n'.join(stmts), capture_output=True, text=True, timeout=600)
    gate_ok = [json.loads(l).get('ok') for l in pr.stdout.splitlines() if l.strip()]
    if len(gate_ok) != len(res):
        sys.exit(f'可判定闸返回 {len(gate_ok)} 条，期望 {len(res)} —— 对齐坏了，不敢往下走')

    stat = collections.Counter()
    apply_ = []
    for k, ((f, i, x), d) in enumerate(res):
        v = d.get('verdict')
        if v == 'overrule' and not gate_ok[k]:
            stat['我们自己的闸也拒 → 降为 unclear'] += 1
            v = 'unclear'
        if v == 'overrule':
            # ★ 硬闸：引文必须逐字出现在课标原文里。对不上 = 推翻作废
            src = norm((x.get('provenance') or {}).get('srcText', ''))
            q = norm(d.get('quote', ''))
            if len(q) < 6 or q not in src:
                stat['引文对不上原文 → 降为 unclear'] += 1
                v = 'unclear'
        stat[v] += 1
        if v in ('uphold', 'overrule'):
            apply_.append((f, i, v, d))

    print('\n裁决结果：')
    for k in ('overrule', 'uphold', 'unclear', 'error',
              '引文对不上原文 → 降为 unclear', '我们自己的闸也拒 → 降为 unclear'):
        if stat[k]:
            print(f'  {stat[k]:>4}  {k}')

    print('\n─── 样本 ───')
    shown = collections.Counter()
    for k, ((f, i, x), d) in enumerate(res):
        v = d.get('verdict')
        if v == 'overrule' and not gate_ok[k]:
            continue
        if v in ('overrule', 'uphold') and shown[v] < 2:
            shown[v] += 1
            live = [q['type'] for q in (x.get('aiIssues') or []) if q.get('type') != 'resolved']
            print(f'  [{v}] {x["discipline"]}｜{x["statement"][:46]}')
            print(f'        原异议 {live} → {str(d.get("why",""))[:76]}')
            if d.get('quote'):
                print(f'        引文：{d["quote"][:60]}')
            print()

    if a.dry_run:
        print('（--dry-run：没有写盘）')
        return

    touched = set()
    for f, i, v, d in apply_:
        x = files[f][i]
        if v == 'uphold':
            x['deprecated'] = True
            x['dropReason'] = ('AI 裁决：异议成立。' + str(d.get('why', ''))[:180]
                               + '（裁决者看得到课标原文，挑错者看不到 —— 见 tools/adjudicate.py）')
        else:
            x['reviewStatus'] = 'ai-reviewed'
            x['adjudication'] = {'verdict': 'overrule', 'why': str(d.get('why', ''))[:200],
                                 'quote': str(d.get('quote', ''))[:200],
                                 'method': '裁决者看课标原文，挑错者看不到；引文逐字核对过'}
            for q in (x.get('aiIssues') or []):
                if q.get('type') != 'resolved':
                    q['detail'] = '【裁决为不成立】原异议：' + str(q.get('detail', ''))[:120]
                    q['type'] = 'resolved'
        touched.add(f)
    for f in touched:
        f.write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in files[f]), encoding='utf-8')
    print(f'\n弃用 {sum(1 for *_, v, _ in [(0, 0, v, 0) for _, _, v, _ in apply_] if v == "uphold")} 条 · '
          f'恢复 {sum(1 for _, _, v, _ in apply_ if v == "overrule")} 条')


if __name__ == '__main__':
    main()
