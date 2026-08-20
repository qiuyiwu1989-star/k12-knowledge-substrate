#!/usr/bin/env python3
"""
fix_fallback_evidence.py — 把兜底模板证据换成真的可观察证据（F206）。

## 病灶

860 条锚点的 evidence 是同一个模板：

    断言：能了解《共产党宣言》的主要内容
    证据：能在历史课堂或作业情境中完成：能了解《共产党宣言》的主要内容

**它回答不了「凭什么说他会」** —— 只是把断言又说了一遍。其中 315 条现在
标着「可被 L3 档案引用」，也就是说档案会拿一条没有判据的锚点去记录一个孩子。

## 想做的闸做不出来 —— 这一节记的是失败

原本想设两道方向相反的闸：既要比断言更具体，又不许编原文没有的事实。
第二条试了两种实现，**都不成立**：

  · **「证据的实词必须几乎全部来自断言+原文」** → 24 条全拒。
    看被拒的内容才发现闸判错了：「能正确写出 tall 的比较级 taller」
    正是要的那种具体，越界字是「人句它身造高」这类虚词和**举例**。
    **举例恰恰是证据必须做的事** —— 把「举例说明」和「替课标发明要求」
    混为一谈，是这个闸的根本毛病。

  · **「证据必须还在讲断言宾语那件事」** → 17/46 误拒。
    因为 `object` 字段本身是「动词之后的文字」粗切出来的碎片
    （「自己的意图」「规则」「软件」），拿它当话题锚不可靠。
    「能用升调表达疑问，用降调表达肯定」明明就在讲调型，字面重叠却是 0。

所以：**这里没有可判定的机器闸**，而这个项目的规矩是
「没有可判定答案的东西不该机器打标」。既然拦不住，就别假装拦得住 ——
改成 `capability-rewrite` 那一层的办法：

  · 证据来源标成 `evidence-drafted`，**单独可查、单独统计、能一条命令撤掉**
  · validate 加一条：起草证据的锚点**永远够不到 auto-confirmed**
  · 机器只保留三道拿得准的：不是兜底模板、不是断言的复读、长度合规
  · 「不许编」由提示词承担，**这是真实的削弱**，所以来源标记才是承重件

## 这不是 capability-rewrite

那一层改的是**断言**（我们自己的教育主张）。这里断言一个字不动，
只写「怎么看出他会」。但两者共享同一条纪律：**我们自己加的东西必须能被认出来。**

    python3 tools/fix_fallback_evidence.py --dry-run --limit 20
    python3 tools/fix_fallback_evidence.py
"""
import argparse, collections, json, os, re, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repair import call        # noqa: E402
from citable import CITABLE    # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(__file__).parent / '.cache-fbev'
FALLBACK = re.compile(r'^能在.{1,8}(课堂|作业).{0,6}情境中完成：|^能完成：')

SYS = """你在给一条能力断言写「掌握证据」—— 一个旁观者怎么看出这孩子会了。

能力断言：{stmt}
课标原文：{src}

现在这条锚点的证据是废的，它只是把断言又说了一遍。要换成真能用的。

**两条相反的要求，都得满足：**

1. **比断言更具体。** 说清在什么情境下、做出什么动作、做到什么程度算数。
   ❌ 能了解《共产党宣言》的主要内容              （复读断言）
   ✅ 给一段《共产党宣言》节选，能指出其中两条主要主张并各举一句原文
2. **不许添加课标原文里没有的事实。** 你可以描述任务场景（给一段材料、
   完成一道题、当场演示），但**不许替课标发明具体内容**。
   ❌ 能说出《共产党宣言》发表于 1848 年       （原文没提年份，这是你加的）

写 2 条证据，每条 12–40 字，都以「能」开头，都是旁观者能看见的具体行为。
再写一句给家长照着念的问句，用 {{{{name}}}} 指代孩子，不超过 40 字，口语化。

原文里如果实在没有可展开的东西（比如原文本身就只有一句空泛要求），
就老实说写不出来 —— 硬凑出来的证据比没有更糟。

只输出一行 JSON，不要代码块：
{{"ok":true,"evidence":["…","…"],"assessment":"…"}}
{{"ok":false,"why":"原文只有一句『增强意识』，没有可观察的行为可写"}}"""


def zh(t):
    return {c for c in t if '一' <= c <= '鿿'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default=None)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--concurrency', type=int, default=10)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    base, key = os.environ['MIMO_BASE'], os.environ['MIMO_KEY']
    model = os.environ.get('MIMO_MODEL', 'mimo-v2.5')
    CACHE.mkdir(exist_ok=True)

    files = {f: [json.loads(l) for l in f.read_text(encoding='utf-8').splitlines() if l.strip()]
             for f in sorted((ROOT / 'anchors').glob('*.jsonl'))}
    targets = [(f, i, x) for f, rows in files.items() for i, x in enumerate(rows)
               if not x.get('deprecated') and x['reviewStatus'] in CITABLE
               and any(FALLBACK.match(e or '') for e in (x.get('evidence') or []))
               and (x.get('provenance') or {}).get('srcText')
               and (not a.only or x['discipline'] == a.only)]
    if a.limit:
        targets = targets[:a.limit]
    print(f'待补真证据 {len(targets)} 条（可引用 + 证据是兜底模板 + 有课标原文）')

    def work(job):
        import hashlib
        f, i, x = job
        src = (x.get('provenance') or {}).get('srcText', '')[:260]
        sysp = SYS.format(stmt=x['statement'], src=src)
        h = hashlib.sha256(sysp.encode()).hexdigest()[:24]
        cf = CACHE / f'{h}.json'
        if cf.exists():
            return job, json.loads(cf.read_text(encoding='utf-8'))
        try:
            raw = call(sysp, '写。', base, key, model)
        except Exception as e:
            return job, {'err': type(e).__name__}
        m = re.search(r'\{.*\}', raw, re.S)
        try:
            d = json.loads(m.group(0)) if m else {'err': '没吐 JSON'}
        except Exception:
            d = {'err': 'JSON 解析失败'}
        cf.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
        return job, d

    res = []
    with ThreadPoolExecutor(a.concurrency) as ex:
        for n, r in enumerate(ex.map(work, targets), 1):
            res.append(r)
            if n % 50 == 0:
                print(f'  …{n}/{len(targets)}', flush=True)

    kept, rej = [], collections.Counter()
    for (f, i, x), d in res:
        if d.get('err'):
            rej[d['err']] += 1; continue
        if not d.get('ok'):
            rej['模型说写不出'] += 1; continue
        ev = [e for e in (d.get('evidence') or []) if isinstance(e, str) and 10 <= len(e) <= 60]
        if len(ev) < 2:
            rej['证据不足 2 条或长度不合'] += 1; continue
        if any(FALLBACK.match(e) for e in ev):
            rej['又写成兜底模板'] += 1; continue
        # 拿得准的闸只剩这一道：必须比断言更具体，不许还是复读。
        # 「不许编原文没有的事实」拦不住（见文件头），靠 evidenceSource 标记兜底。
        if any(len(zh(e) - zh(x['statement'])) < 3 for e in ev):
            rej['还是在复读断言'] += 1; continue
        kept.append((f, i, x, ev, d.get('assessment')))

    print(f'\n通过两道闸 {len(kept)} / {len(res)}')
    for k, n in rej.most_common(6):
        print(f'  拒 {n:>4}  {k}')
    print('\n─── 样本 ───')
    for f, i, x, ev, _ in kept[:4]:
        print(f'  断言：{x["statement"][:46]}')
        print(f'  旧证据：{(x.get("evidence") or ["—"])[0][:46]}')
        for e in ev:
            print(f'  新证据：{e}')
        print()
    if a.dry_run:
        print('（--dry-run：没有写盘）')
        return
    touched = set()
    for f, i, x, ev, ass in kept:
        r = files[f][i]
        r['evidence'] = ev
        r['evidenceSource'] = 'evidence-drafted'   # 不再是 fallback，也不冒充课标来源
        if ass and not r.get('assessment'):
            r['assessment'] = ass
        touched.add(f)
    for f in touched:
        f.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in files[f]), encoding='utf-8')
    print(f'已写盘 {len(kept)} 条')


if __name__ == '__main__':
    main()
