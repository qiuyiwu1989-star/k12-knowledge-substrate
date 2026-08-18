#!/usr/bin/env python3
"""
make_assessment.py — 给锚点补 assessment：家长/老师照着念的那一句问句。

## 它是**渲染**，不是改写

statement 是给机器看的（「能背诵《杂说》全文且不错漏」），
assessment 是给一个具体的人照着念的（「{{name}}能把《杂说》完整背下来吗？」）。

**同一件事的两种说法，不许是两件事。** 所以这里的闸全部围绕「不许引入新信息」：
转写层允许在知识之上提主张，这里一点都不允许 —— 它只换说法。

## 为什么值得单独做一遍

高中 891 条 + 转写层 217 条一条 assessment 都没有，而**复核单和孩子视角都靠它**。
锚点进了库却进不了这两个页面，等于老师和家长看不见 —— 骨架有了，脸没有。

## 四道闸

  1. 必须含 {{name}} 占位符 —— 它是给某个具体孩子念的，不是通告
  2. 必须以问号结尾 —— 它是一个能被回答「会/不会」的问题
  3. **不许出现 statement 里没有的实义词**（除白名单虚词）—— 这是「渲染 vs 改写」的分界线
  4. 不许含悬空指代（这张表/这些字…而句内无所指）—— validate.mjs 同款检查，
     那道闸是从「一个孩子的视角」成批看数据时才发现的：家长手里没有那张表

    python3 tools/make_assessment.py --dry-run
    python3 tools/make_assessment.py --limit 20
    python3 tools/make_assessment.py
"""
import argparse, collections, json, os, re, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repair import call        # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

SYS = """把一条能力断言改写成**家长或老师照着念**的一句问句。

断言：{stmt}
学科：{disc}{extra}
这条锚点自带的判定证据：{ev}

这是换说法，不是提新要求。规则：

0. **优先用上面那条证据把问句问得具体**。证据写的就是「旁观者能看见的行为」，
   把它变成家长真会问的话。反例：「{{{{name}}}}能掌握在有害环境中自我保护的方法吗？」——
   家长没法拿这句去问孩子。有证据就用证据，没有再退回断言本身。

1. 必须包含 {{{{name}}}} 占位符（会被换成孩子的名字）。
2. 必须是一句问句，以「？」结尾。
3. **只能用断言和证据里已有的内容** —— 不许自己另举例子、加条件、改范围。
   断言「能说出细菌是单细胞生物」→ ✅ {{{{name}}}}能说出细菌是单细胞生物吗？
                              ❌ {{{{name}}}}能说出细菌和病毒的区别吗？（凭空加了病毒）
4. 口语一点，像家长真会问的话，20–45 字。
5. **不许出现「这张表」「这些字」「上面的」这类指代** —— 家长手里没有那张表。
   要提具体对象就把名字写出来。
6. 断言里的书名号、专有名词原样保留。

只输出一行 JSON：{{"q":"…"}}"""

STOP = set('的了和与或在是有能会对为以及等这那其中一个可以进行并且或者通过根据你我他'
           '吗呢啊吧呀把被让给从向到于就都也还又要想能够什么怎么样时候地方东西说话'
           '出来上去下来起来一些一样这样那样问一问看一看试试请你和他她它们')
DANGLING = re.compile(r'这张表|这些字|这些词|这批|该表|上面的')


def content_words(s):
    """实义字集合。虚词和常见口语词不算 —— 问句本来就要比断言口语。"""
    return {c for c in s if '一' <= c <= '鿿'} - STOP


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default=None)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--concurrency', type=int, default=12)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    base, key = os.environ['MIMO_BASE'], os.environ['MIMO_KEY']
    model = os.environ.get('MIMO_MODEL', 'mimo-v2.5')

    files = {f: [json.loads(l) for l in f.open(encoding='utf-8') if l.strip()]
             for f in sorted((ROOT / 'anchors').glob('*.jsonl'))}
    targets = [(f, i, x) for f, arr in files.items() for i, x in enumerate(arr)
               if not x.get('deprecated') and not x.get('assessment')
               and (not a.only or x['discipline'] == a.only)]
    if a.limit:
        targets = targets[:a.limit]
    print(f"待补 {len(targets)} 条")
    print(f"  分布: {dict(collections.Counter(x['discipline'] for _, _, x in targets).most_common(6))}")

    def work(t):
        f, i, x = t
        extra = ''
        if x.get('courseType'):
            extra = f"（高中{x['courseType']}课程）"
        ev = ' ／ '.join((x.get('evidence') or [])[:2]) or '（无）'
        try:
            raw = call(SYS.format(stmt=x['statement'], disc=x['discipline'],
                                  extra=extra, ev=ev),
                       '写。', base, key, model)
        except Exception as e:
            return t, None, f'调用失败：{type(e).__name__}'
        m = re.search(r'\{.*\}', raw, re.S)
        if not m:
            return t, None, '没吐 JSON'
        try:
            q = (json.loads(m.group(0)).get('q') or '').strip()
        except Exception:
            return t, None, 'JSON 解析失败'
        if '{{name}}' not in q:
            return t, None, '缺 {{name}} 占位符'
        if not q.endswith(('？', '?')):
            return t, None, '不是问句'
        if not (12 <= len(q) <= 60):
            return t, None, f'长度 {len(q)} 越界'
        mm = DANGLING.search(q)
        if mm:
            before = q[:q.index(mm.group(0))]
            if not re.search(r"['‘’\"“”《》]|[^，。]、[^，。]", before):
                return t, None, f'悬空指代「{mm.group(0)}」'
        # ★ 核心闸：问句里不许出现**断言和证据之外**的实义字。
        #   这一条把「渲染」和「改写」分开 —— 少了它，模型会顺手补例子、补条件。
        #   证据算合法来源，因为证据本身就是这条锚点的一部分（课标例题或复核时写的
        #   可观察行为）。允许它，问句才能具体到家长真拿得起来；
        #   不允许，产出就退化成「断言 + 吗？」，等于没做。
        allowed = content_words(x['statement']) | content_words(' '.join(x.get('evidence') or []))
        new = content_words(q) - allowed
        if len(new) > 3:
            return t, None, f'引入了断言和证据之外的内容（{"".join(sorted(new))[:8]}）'
        return t, q, None

    results = []
    with ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        for n, r in enumerate(ex.map(work, targets), 1):
            results.append(r)
            if n % 100 == 0:
                print(f"  …{n}/{len(targets)}")

    ok = [(t, q) for t, q, e in results if q]
    bad = [(t, e) for t, q, e in results if not q]
    print(f"\n成功 {len(ok)} · 跳过 {len(bad)}")
    for why, c in collections.Counter(e.split('（')[0] for _, e in bad).most_common(6):
        print(f"  {c:>4}  {why}")

    print("\n─── 样本 ───")
    for (f, i, x), q in ok[:6]:
        print(f"  断言：{x['statement'][:50]}")
        print(f"  问句：{q}")
        print()

    if a.dry_run:
        print("（--dry-run：没有写盘）")
        return
    for (f, i, x), q in ok:
        files[f][i]['assessment'] = q
    for f, arr in files.items():
        with f.open('w', encoding='utf-8') as fh:
            for x in arr:
                fh.write(json.dumps(x, ensure_ascii=False) + '\n')
    print(f"已写 {len(ok)} 条 assessment")
    print("下一步：npm run check")


if __name__ == '__main__':
    main()
