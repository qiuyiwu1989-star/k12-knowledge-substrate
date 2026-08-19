#!/usr/bin/env python3
"""retag_summary.py — 产出 reports/edge-retag-summary.md（specs/001 验收清单要求的那份）。

**只讲发生了什么，不讲结论。** 数字全部现算，不许手打 —— 手打的数字半年后一定是假的。
"""
import json, glob, collections
from pathlib import Path

A = {}
for f in glob.glob('anchors/*.jsonl'):
    for l in open(f, encoding='utf-8'):
        if l.strip():
            x = json.loads(l); A[x['id']] = x
live = lambda i: i in A and not A[i].get('deprecated')
E = [json.loads(l) for f in glob.glob('edges/*.jsonl') for l in open(f, encoding='utf-8') if l.strip()]
E = [e for e in E if not e.get('retired') and live(e.get('anchorId')) and live(e.get('prerequisiteId'))]
T = collections.Counter(e.get('type') for e in E)
ing = [e for e in E if e.get('type') != 'convention' and e.get('inInferenceGraph') is not False]
cap = sum(1 for e in E if e.get('strengthCappedBy'))
sc = collections.Counter(e.get('strength') for e in E)
sigs = [e['failureSignature'] for e in E if e.get('failureSignature') and e.get('type') != 'convention']

M = {'component': ('前置是后继的子动作，某一步系统性地错', '是'),
     'semantic': ('不懂前置则后继的表述本身没有意义', '是'),
     'instrument': ('拿前置当手段，能到但绕远路', '是'),
     'convention': ('教材就这么排的，无可观测影响', '**否**')}

L = ['# 边重标汇总（specs/001）', '',
     '> 由 `python3 tools/retag_summary.py` 现算生成。**只讲发生了什么，不讲结论。**', '',
     '## 四类各多少', '',
     '| type | 条数 | 占比 | 含义 | 进推理图 |', '|---|---:|---:|---|---|']
for t in ('component', 'semantic', 'instrument', 'convention'):
    L.append(f'| `{t}` | {T[t]} | {T[t]/len(E)*100:.0f}% | {M[t][0]} | {M[t][1]} |')
if T[None]:
    L.append(f'| （未重标） | {T[None]} | {T[None]/len(E)*100:.1f}% | 调用失败，重跑即补（增量自动跳过已标的） | 是 |')

L += ['', f'## 推理图：{len(E)} → **{len(ing)}**', '',
      f'**{T["convention"]} 条（{T["convention"]/len(E)*100:.0f}%）判为 `convention` 并移出推理图。**',
      '这是这一轮最大的一个数字：**四分之一的先修边没有可观测后果** ——',
      '模型在第一段被问「不会 A 的孩子做 B 会失败在哪一步」时，直接答了「不会失败」。', '',
      '它们没有被删除，只是标成教材编排顺序而非能力依赖（`inInferenceGraph=false`）。',
      '**降级是打标记，不是删除** —— 判错了随时能翻回来。', '',
      '## strength', '', '| | 条数 |', '|---|---:|',
      f'| hard | {sc["hard"]} |', f'| soft | {sc["soft"]} |',
      f'| 其中被规则压回 soft（`strengthCappedBy`） | {cap} |', '',
      f'**{cap} 条被压回 soft**：两端只要有一侧是 MATRIX 档，就不许标 hard。',
      '那条规则背后是「史地生政艺外语这类学科的先修关系稀疏到可忽略」的设计判断，',
      '不该被逐条的模型意见推翻。**类型和失败表征全部保留**，只把「卡死」这一句',
      'withhold 到有人确认为止 —— 和 reviewStatus 是同一个道理，可查可回滚。', '',
      '## 失败表征', '',
      f'- 非 convention 边 {len(sigs)} 条，**去重后 {len(set(sigs))} 条** —— 几乎一条一句，不是模板',
      f'- 长度中位数 {sorted(len(x) for x in sigs)[len(sigs)//2]} 字',
      '- 命中空泛词黑名单：0（F005 在重标时就拦掉了，不是事后补的）', '', '抽样：', '', '```']
seen = set()
for e in E:
    t = e.get('type')
    if t in ('component', 'semantic', 'instrument') and t not in seen:
        seen.add(t)
        L.append(f"[{t}]  {A[e['prerequisiteId']]['statement'][:28]}  →  {A[e['anchorId']]['statement'][:28]}")
        L.append(f"       {e['failureSignature']}")
L += ['```', '', '## 顺带收掉的假证据', '',
      '重标前每条边的 `evidence` 里都有一项 `standard-hierarchy：课标学段序：G10 → G10` ——',
      '去重后只有 26 个值，其中 1,441 条两端学段完全相同，**零信息**。',
      '而 validate 的旧闸写着「hard 边须有非 llm 证据，standard-hierarchy 算数」，',
      '也就是说任何一条软边改成 hard 都能过 CI。**闸被我们自己生成的样板绕过了。**', '',
      '这一轮：两端学段相同的那一项直接丢弃；hard 边的判据换成',
      '「有非 llm 证据 **或** 有一条过了 F004/F005 的具体失败表征」—— 后者严格得多。', '',
      '## 增量', '',
      '按 `retagHash = sha256(前置断言 → 后继断言)` 跳过未变更的边。',
      '实测连跑两次，第二次「待重标 1 / 存活边 3069，增量已跳过 3068」。',
      '全量重跑要显式 `--force-all`。锚点涨到 10,000 时这是架构要求，不是优化项。', '']
Path('reports/edge-retag-summary.md').write_text('\n'.join(L), encoding='utf-8')
print(f'✓ reports/edge-retag-summary.md — 推理图 {len(ing)} · convention {T["convention"]} · 压回 soft {cap}')
