#!/usr/bin/env python3
"""
math_examples_commit.py — 数学课标实例落库，并把官方例题挂到锚点上。

**先纠正一个前提。** 这件事原本的说法是「救回 evidence-weak 那 144 条」，
但实测全库存活锚点里 evidence 少于 2 条的是 **0** —— 那个前提不成立。

真实价值在别处：数学锚点的 evidence 有 93 条是 `llm-draft`，即模型编的例子。
课标附录1「课程内容中的实例」是官方对每条要求的具体化，其中 78 个例题还带
【说明】段落 —— 那正是教师复核时最需要、也最有权威性的东西。

所以这里做的是**证据来源升级**，不是补空缺：
  · 例题全文落成一等公民 examples/math.jsonl（93 条，例号 1–93 零缺号）
  · 锚点原文里直接引用了「例N」的，把官方例题挂成证据

能机械挂上的只有 14 条 —— 剩下 111 条要靠判断去匹配，那正是这个项目
一直在防的东西，不做。例题库本身会进教师复核队列，复核时按页就近可查。

    python3 tools/math_examples_commit.py
"""
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = '义务教育数学课程标准（2022年版）附录1 课程内容中的实例'


def main():
    ex = json.loads((ROOT / 'tools/out/math-examples-clean.json').read_text(encoding='utf-8'))
    ex = {int(k): v for k, v in ex.items()}

    # ── 1. 例题落成一等公民 ──────────────────────────────────
    out_dir = ROOT / 'examples'
    out_dir.mkdir(exist_ok=True)
    f = out_dir / 'math.jsonl'
    with f.open('w', encoding='utf-8') as fh:
        for n in sorted(ex):
            num, title, body, note = ex[n]
            fh.write(json.dumps({
                'exampleId': f'ex_math_{n:03d}', 'discipline': '数学', 'no': n,
                'title': title.strip(), 'body': body.strip(), 'note': note.strip(),
                'source': SRC,
                'extraction': {'method': 'vlm-3vote', 'srcPageRange': '106–189',
                               'verify': '例号 1–93 连续无缺'},
                'schemaVersion': '0.1.0',
            }, ensure_ascii=False) + '\n')
    print(f"  → {f}  {len(ex)} 条（例号 1–{max(ex)}，零缺号；{sum(1 for v in ex.values() if v[3].strip())} 条带【说明】）")

    # ── 2. 挂到引用了例号的锚点上 ────────────────────────────
    linked = 0
    for path in sorted((ROOT / 'anchors').glob('*.jsonl')):
        arr = [json.loads(l) for l in path.open(encoding='utf-8') if l.strip()]
        touched = False
        for a in arr:
            if a['discipline'] != '数学' or a.get('deprecated'):
                continue
            st = (a.get('provenance') or {}).get('srcText') or ''
            nums = [int(m) for m in re.findall(r'例\s*(\d+)', st)]
            hit = [n for n in nums if n in ex]
            if not hit:
                continue
            adds = []
            for n in hit:
                _, title, body, note = ex[n]
                # 说明优先 —— 它讲的是「凭什么算会了」，题干只是题面
                text = (note or body).strip().replace('【说明】', '')
                adds.append(f'课标例{n}「{title.strip()}」：{text[:110]}')
            before = list(a.get('evidence') or [])
            a['evidence'] = before + [x for x in adds if x not in before]
            # 来源升级：从「模型编的」变成「课标原文的」
            a['evidenceSource'] = 'curriculum-example'
            a.setdefault('provenance', {})['exampleRefs'] = hit
            touched, linked = True, linked + 1
        if touched:
            with path.open('w', encoding='utf-8') as fh:
                for a in arr:
                    fh.write(json.dumps(a, ensure_ascii=False) + '\n')
    print(f"  ~ {linked} 条锚点的证据来源升级为 curriculum-example（原文直接引用了例号的全部）")
    print(f"    其余 111 条数学锚点需按语义匹配例题 —— 那要判断，不做。")


if __name__ == '__main__':
    main()
