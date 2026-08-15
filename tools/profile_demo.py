#!/usr/bin/env python3
"""
profile_demo.py — 参考实现：一个产品怎么把档案写在底座上，又怎么从底座取回价值。

**这是整个项目的验收测试。** 前面所有工作（抽取、审查、建边、可视化）
都只是在造一把尺子；尺子有没有用，要看能不能量出东西。

这个脚本模拟诗歌库/识字应用往档案里写断言，然后回答三个问题：
  1. 这孩子现在识字量多少、背了几篇？（家长最认的指标）
  2. 他**下一步该学什么**？—— 前置已满足但自己还没掌握的锚点
  3. 他卡在哪？—— 想学的东西缺哪几条前置

第 2 问是底座存在的全部理由。没有依赖图，你只能按课本顺序推；
有了依赖图，你能按**这个孩子实际的掌握状态**推。

数据是造的（stu_DEMO0001），但断言格式、校验规则、推荐算法都是真的，
换成真实产品的输出可以直接跑。

  python3 tools/profile_demo.py
"""
import collections, json, random, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
random.seed(20260815)

anchors = {}
for f in sorted((ROOT / 'anchors').rglob('*.jsonl')):
    for l in f.open(encoding='utf-8'):
        a = json.loads(l)
        anchors[a['id']] = a
edges = [json.loads(l) for f in sorted((ROOT / 'edges').rglob('*.jsonl'))
         for l in f.open(encoding='utf-8')]
lists = [json.loads(l) for f in sorted((ROOT / 'lists').rglob('*.jsonl'))
         for l in f.open(encoding='utf-8')]

pre = collections.defaultdict(list)
post = collections.defaultdict(list)
for e in edges:
    pre[e['anchorId']].append(e['prerequisiteId'])
    post[e['prerequisiteId']].append(e['anchorId'])

# ── 只有 usable 的锚点能被档案引用。这条规则是整个底座的分界线，
#    demo 里也必须守 —— 一旦这里放水，生产里就没人守得住。
USABLE = {'auto-confirmed', 'expert-confirmed'}
usable = {k: v for k, v in anchors.items() if v['reviewStatus'] in USABLE}
print(f"可被档案引用的锚点：{len(usable)} / {len(anchors)}")
if not usable:
    sys.exit('没有 usable 锚点，先跑 tools/lists_to_anchors.py')

STU = 'stu_DEMO0001'
asserts = []
seq = [0]


def mk(anchor_id, listRef=None, level=1.0, holder='ai:shige-app', src='shige'):
    seq[0] += 1
    return {
        'assertionId': f'as_DEMO{seq[0]:08d}',
        'subject': STU, 'predicate': 'MASTERED', 'anchorId': anchor_id,
        'listRef': listRef, 'freeText': None, 'level': level,
        'validFrom': '2026-08-15', 'validUntil': None,
        'holder': holder,
        # AI 写入一律 proposed。只有老师/家长显式确认过的才是 confirmed，
        # 沉默不算确认 —— 这条在 schema 注释里写着，demo 也不能破。
        'confidence': 'proposed' if holder.startswith('ai:') else 'confirmed',
        'evidence': [f'{src}:2026-08-15'],
        'supersedes': None, 'sourceApp': src, 'schemaVersion': '0.1.0',
    }


# ── 模拟：一个二年级孩子 ──────────────────────────────────────
jiben = next((a for a in usable.values() if '基本字表' in a['statement']), None)
biao1 = next((a for a in usable.values() if '字表一' in a['statement']), None)
recite = [a for a in usable.values() if a['verb'] == '背诵'
          and (a.get('stageHint') or {}).get('min') == 'G1']

# 识字：基本字表 300 会 214 个，常用字表一 2500 会 386 个
jb_items = [x for x in lists if x['listId'] == 'lst_hanzi-jiben-300']
b1_items = [x for x in lists if x['listId'] == 'lst_hanzi-changyong-3500'
            and (x.get('meta') or {}).get('table') == '字表一']
for x in random.sample(jb_items, 214):
    asserts.append(mk(jiben['id'], {'listId': x['listId'], 'key': x['key']}, src='shizi'))
for x in random.sample(sorted(b1_items, key=lambda r: r['seq'])[:900], 386):
    asserts.append(mk(biao1['id'], {'listId': x['listId'], 'key': x['key']}, src='shizi'))
# 背诵：小学 75 篇里背了 23 篇，其中 6 篇老师当面确认过
learned = random.sample(recite, 23)
for i, a in enumerate(learned):
    asserts.append(mk(a['id'], holder='teacher:gao' if i < 6 else 'ai:shige-app', src='shige'))

print(f"写入断言 {len(asserts)} 条（{STU}）")

# ── 校验：断言必须指向 usable 锚点 ───────────────────────────
bad = [a for a in asserts if a['anchorId'] not in usable]
assert not bad, f'{len(bad)} 条断言指向了不可用锚点'
print("✓ 全部断言都指向 usable 锚点")

# ── 一问：家长最认的指标 ─────────────────────────────────────
by_anchor = collections.Counter(a['anchorId'] for a in asserts)
print("\n═══ 这孩子现在到哪了 ═══")
for aid, n in by_anchor.most_common():
    a = usable[aid]
    tot = (a.get('provenance') or {}).get('itemCount')
    if tot:
        print(f"  {a['statement'][:30]}  {n} / {tot}  {n/tot:.0%}")
recited = [usable[a['anchorId']] for a in asserts if usable[a['anchorId']]['verb'] == '背诵']
conf = sum(1 for a in asserts if a['confidence'] == 'confirmed')
print(f"  背诵篇目  {len(recited)} / {len([a for a in usable.values() if a['verb']=='背诵'])} 篇")
print(f"  识字量合计 {sum(1 for a in asserts if a.get('listRef'))} 字"
      f"（其中老师当面确认 {conf} 条，其余为 AI 判定待确认）")

# ── 二问：下一步该学什么（底座存在的全部理由）─────────────────
mastered = {a['anchorId'] for a in asserts}
mastered_items = {(a['listRef']['listId'], a['listRef']['key']) for a in asserts if a.get('listRef')}


def ready(a):
    """前置全在已掌握集合里，且自己还没掌握 → 现在就能学"""
    if a['id'] in mastered:
        return False
    ps = pre.get(a['id'], [])
    return all(p in mastered for p in ps)


nxt = [a for a in usable.values() if ready(a)]
# 排序：学段早的优先，同学段里「解锁得多」的优先
nxt.sort(key=lambda a: ((a.get('stageHint') or {}).get('min', 'G9'), -len(post.get(a['id'], []))))
print(f"\n═══ 下一步能学什么（前置已满足，共 {len(nxt)} 条）═══")
for a in nxt[:8]:
    unlocks = len(post.get(a['id'], []))
    print(f"  [{(a.get('stageHint') or {}).get('min')}] {a['statement'][:34]}"
          + (f"  → 解锁 {unlocks} 条" if unlocks else ''))

# 字表类：推荐下一批该学的字（按课标编号顺序）
undone = [x for x in sorted(b1_items, key=lambda r: r['seq'])
          if (x['listId'], x['key']) not in mastered_items][:20]
print(f"\n  识字下一批（按课标常用字表顺序）：{''.join(x['key'] for x in undone)}")

# ── 三问：想学某条，还缺什么 ─────────────────────────────────
target = next((a for a in usable.values()
               if a['verb'] == '背诵' and (a.get('stageHint') or {}).get('min') == 'G7'), None)
if target:
    seen, miss, q = set(), [], [target['id']]
    while q:
        v = q.pop()
        for p in pre.get(v, []):
            if p in seen:
                continue
            seen.add(p)
            if p not in mastered:
                miss.append(p)
            q.append(p)
    print(f"\n═══ 想学「{target['statement'][:26]}」还缺 {len(miss)} 条前置 ═══")
    for p in miss[:5]:
        print(f"  · {anchors[p]['statement'][:40]}")
    if not miss:
        print("  （这条没有前置依赖 —— 背诵类锚点之间本来就不互为先修，")
        print("    这正是 LIST 档不建图的原因：它是覆盖模型，不是链）")

out = ROOT / 'tools/out/profile-demo.jsonl'
out.parent.mkdir(parents=True, exist_ok=True)
with out.open('w', encoding='utf-8') as f:
    for a in asserts:
        f.write(json.dumps(a, ensure_ascii=False) + '\n')
print(f"\n→ {out}（{len(asserts)} 条断言，数据是造的，格式和规则是真的）")
print("  注意：这个文件**不进仓库**，.gitignore 挡着 —— L3 档案永不入库。")
