#!/usr/bin/env python3
"""
fix_restates_plan.py — 两类抽取残渣，2026-09-28 用课标原件核对学段时撞见。

1. **复述课程安排的伪断言**（17 条，多数可引用）
   「能说出 3~4 年级学生应调查不同环境中动物的类型和数量」「能说出第四学段的学习任务 1 是演出舞台剧目」。
   孩子会不会「说出课标给哪个年级排了什么」不是能力 —— 那是把教学建议套上「能说出」。
   → 拆掉「能说出 X 年级学生应」这层框子，还原成原句说的那件事（见下方 REWRITE 前的注释）。
     可判定闸新加了 RESTATES_PLAN，以后抽出来当场拦下。

2. **断言开头粘着表格的行标签**（4 条）
   「~6年级能说出太阳系的基本结构」「水平三·掌握…」—— 科学、体育的表格左列是学段 / 水平，
   抽取时把那一格连着切了进来。→ 去掉前缀，断言其余一字不动；学段由 apply_stage 按原件定。

    python3 tools/fix_restates_plan.py            # 只看不写
    python3 tools/fix_restates_plan.py --write
"""
import argparse, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ★ 第一版是全部弃用 —— validate 当场拦下：其中 11 条是真正能力版本的 derivedFrom / splitFrom 源，
#   弃用源等于让转写成了孤证。所以改成：**把「能说出 X 年级学生应」这层框子拆掉，还原成原句说的那件事**，
#   锚点留在用（源链不断）；只有 2 条弃用（一条与同族重复，一条只是学习任务的名字）。
REWRITE = {
    'ca_ZZqB8uTv': '能观察动物取食、争斗等行为',
    'ca_TbQvMfZa': '能观察蚯蚓对刺激（如光、热）的反应',
    'ca_0nSa2sri': '能观察蚂蚁（或蜜蜂）的社群行为',
    'ca_1fVemFIw': '能观察鸟类的筑巢与育雏、迁徙行为',
    'ca_Y3DBGveb': '能观察鸟类的筑巢与育雏',
    'ca_ja89YmaW': '能利用三球仪模拟地球、月球和太阳的相对运动',
    'ca_U7GgVizO': '能调查不同环境中的植物、动物的类型和数量',
    'ca_dv32R2fF': '能调查不同环境中动物的类型和数量',
    'ca_6e6Ghayy': '能利用图片或实物，观察对比沙漠、盐碱地及海底植物的外部形态的异同',
    'ca_5wRMnz47': '能观察对比沙漠植物的外部形态的异同',
    'ca_FLKPbexT': '能观察对比海底植物的外部形态的异同',
    'ca_Hudo9H2v': '能制作生命系统构成层次的概念图',
    'ca_aubUqili': '能围绕学习活动展开调查，从多方面获取活动各阶段的材料',
    'ca_Go3P6uox': '能进行小型歌舞剧表演和即兴表演',
    'ca_GcHZA1D2': '能完成舞台剧目的演出',          # 「能演出舞台剧目」只有 7 字，schema 要 ≥8
}
DEPRECATE = {
    'ca_z3MvQNLP': ('ca_Go3P6uox', None),
    'ca_HitSfjqU': (None, '「领略蒙太奇」「接触多媒体」是课标给 3~7 年级影视排的学习任务名，'
                          '拆掉「能说出…学习任务包括」之后不剩可判定的能力'),
}
# 断言去前缀：旧 → 新（只去掉粘进来的行标签，其余一字不动）
PREFIX = {
    'ca_USTDPpGr': ('~6年级能说出太阳系的基本结构', '能说出太阳系的基本结构'),
    'ca_MCgnFGHd': ('水平三·', ''),
    'ca_l78Frdub': ('1~2年级学生能运用', '能运用'),
    'ca_6tM3vU6e': ('~9年级，可确定项目目标为"', ''),   # 剩下「能够根据需求…」是原文的
}
WHY = ('复述的是课程安排（「能说出 X 年级学生应……」「学习任务包括……」），不是孩子身上可判定的能力。'
       '2026-09-28 用课标原件核对学段时撞见；可判定闸新增 RESTATES_PLAN 规则拦这一类')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--write', action='store_true')
    a = ap.parse_args()
    files = {f: [json.loads(l) for l in f.read_text(encoding='utf-8').splitlines() if l.strip()]
             for f in sorted((ROOT / 'anchors').glob('*.jsonl'))}
    byid = {r['id']: r for rows in files.values() for r in rows}
    import re, subprocess, sys
    sys.path.insert(0, str(ROOT / 'tools'))
    from repair import grounded
    p = subprocess.run(['node', str(ROOT / 'scripts/lib/check-stdin.mjs')],
                       input='\n'.join(REWRITE.values()), capture_output=True, text=True)
    for (i, new), v in zip(REWRITE.items(), map(json.loads, p.stdout.splitlines())):
        r = byid[i]
        g = grounded(new, (r.get('provenance') or {}).get('srcText') or '')
        if not g[0]:
            raise SystemExit(f'{i} 还原后不忠于原句：{new}  覆盖 {g[1]:.0%}')
        # 还原成原句之后，多数过不了可判定闸（「观察…」是过程，直接判不了会不会）——
        # 这恰恰说明当初为什么要套「能说出…应…」：是为了让原句层混过闸。
        # 可判定的是由它转写出来的子条（derivedFrom），那些照旧可引用；原句层留在用、进 disputed。
        ok = bool(v.get('ok'))
        print(f"还原 {i}  {r['statement'][:28]}  →  {new}  " + ('（过闸，保持可引用）' if ok else '（原句层，进 disputed）'))
        if a.write:
            r.setdefault('provenance', {})['verbFixedFrom'] = r['statement']
            r['statement'] = new
            if v.get('verb'):
                r['verb'] = v['verb']
            r['deprecated'] = False
            r['supersededBy'] = None
            r.pop('dropReason', None)
            if not ok:
                r['reviewStatus'] = 'disputed'
                r['aiIssues'] = [{'type': 'undecidable', 'by': 'rule:restates-plan',
                                  'detail': '原句层：' + '；'.join(v.get('reasons') or [])[:60]
                                            + '。可判定的能力版本是由它转写 / 拆出的子条'}] + \
                    [x for x in (r.get('aiIssues') or []) if x['type'] == 'resolved']
    for i, (sup, why) in DEPRECATE.items():
        r = byid[i]
        print(f"弃用 {i}  {r['statement'][:36]}" + (f"  → {sup}" if sup else ''))
        if a.write:
            r['deprecated'] = True
            r['supersededBy'] = sup
            r['dropReason'] = why or '与同族条目重复：拆掉「能说出…的名称」之后就是 ' + sup
    for i, (old, new) in PREFIX.items():
        r = byid[i]
        st = r['statement']
        if (r.get('provenance') or {}).get('leadStripped') == old:
            continue                                   # 已经剥过（脚本可重跑）
        if not st.startswith(old):
            raise SystemExit(f'{i} 断言开头不是「{old}」：{st[:30]}')
        fixed = new + st[len(old):]
        fixed = fixed.rstrip('"”')
        print(f"去前缀 {i}  {st[:30]}  →  {fixed[:30]}")
        if a.write:
            r['statement'] = fixed
            r.setdefault('provenance', {})['leadStripped'] = old
    if a.write:
        for f, rows in files.items():
            f.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')
        print('已写回')


if __name__ == '__main__':
    main()
