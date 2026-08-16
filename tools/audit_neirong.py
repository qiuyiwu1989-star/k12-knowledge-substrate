#!/usr/bin/env python3
"""
audit_neirong.py — 对【内容要求】抽出的锚点做质量审计并修正。

619 条一口气入库，抽查发现 27% 有问题。三类分开处理，**不搞一刀切**：

**① 凭空造出的关系（弃用）**
改写声称「X 的作用/目的/意义是 Y」，而原文根本没有这几个词。
  ✗ 能说出略读的目的是粗知文章大意  ← 学习略读，粗知文章大意
原文是「学略读 → 达到粗知大意」的动作与结果，改写把它编成了定义。
接地校验查不出来（字面覆盖率很高），因为编的是**关系**不是词。

**② 指标类（弃用）**
「能说出课外阅读总量不少于100万字」—— 阅读量是给学生定的**目标**，
不是可说的知识。这类已由 mappings/stage-targets.json 那套机制承载。

**③ 学段错配（修，不弃用）**
句子里点名了年级（「1~2年级开设…」），stageHint 却是别的。
其中本身就是课程编排说明的一并弃用，其余按句中年级修正。

**明确不做的：不按「原文有动作动词」批量删。**
第一版检测器这么判，命中 116 条 —— 但里面混着大量好数据：
「探索并掌握周长公式」→「能说出长方形周长公式是（长+宽）×2」
是正当的能力分解，事实正确、可判定。按那个判据删会毁掉好数据。

    python3 tools/audit_neirong.py [--write]
"""
import argparse, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

INVENT = re.compile(r'的(作用|目的|意义|功能|价值|特点|本质|定义)是')
INVENT_SRC = re.compile(r'作用|目的|意义|功能|价值|特点|本质|定义')
METRIC = re.compile(r'\d+\s*(万?词|字|篇|次|分钟|米|秒|个左右)以?上?|不少于|累计达到|每分钟|总量')
GRADE = re.compile(r'(\d)\s*[~～-]\s*(\d)\s*年级|第([一二三四])学段')
ARRANGE = re.compile(r'开设|选项|学习任务为|主要满足|依托|每位学生至少|课时|学段设置')
CN = {'一': (1, 2), '二': (3, 4), '三': (5, 6), '四': (7, 9)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--write', action='store_true')
    a = ap.parse_args()

    files = {}
    for f in sorted((ROOT / 'anchors').glob('*.jsonl')):
        files[f.name] = [json.loads(l) for l in f.open(encoding='utf-8') if l.strip()]

    drop_invent, drop_metric, drop_arrange, fix_stage = [], [], [], []
    for arr in files.values():
        for x in arr:
            if x.get('evidenceSource') != 'curriculum-content' or x.get('deprecated'):
                continue
            st = x['statement']
            src = (x.get('provenance') or {}).get('srcText') or ''

            if INVENT.search(st) and not INVENT_SRC.search(src):
                drop_invent.append(x); continue
            if METRIC.search(st):
                drop_metric.append(x); continue

            m = GRADE.search(st)
            if not m:
                continue
            if ARRANGE.search(st):
                drop_arrange.append(x); continue
            lo, hi = CN[m.group(3)] if m.group(3) else (int(m.group(1)), int(m.group(2)))
            h = x.get('stageHint') or {}
            try:
                cur = (int(h['min'][1:]), int(h['max'][1:]))
            except Exception:
                continue
            if cur != (lo, hi):
                fix_stage.append((x, lo, hi, cur))

    print(f"① 凭空造出「X的作用/目的是Y」   弃用 {len(drop_invent)} 条")
    print(f"② 指标类（阅读量/速度/字数）    弃用 {len(drop_metric)} 条")
    print(f"③ 课程编排说明（漏网）         弃用 {len(drop_arrange)} 条")
    print(f"④ 学段错配                    修正 {len(fix_stage)} 条")
    for x, lo, hi, cur in fix_stage[:5]:
        print(f"    G{cur[0]}-{cur[1]} → G{lo}-{hi}　{x['statement'][:40]}")

    if not a.write:
        print("\n（未落盘。确认无误后加 --write）")
        return

    for x in drop_invent:
        x['deprecated'] = True
        x['dropReason'] = ('改写凭空造出「X的作用/目的是Y」这类关系，原文没有这个判断。'
                           '接地校验查不出来 —— 编的是关系不是词，字面覆盖率照样很高。')
    for x in drop_metric:
        x['deprecated'] = True
        x['dropReason'] = ('指标类（阅读量/速度/字数），是给学生定的目标不是可说的知识。'
                           '这类由 mappings/stage-targets.json 那套机制承载。')
    for x in drop_arrange:
        x['deprecated'] = True
        x['dropReason'] = '课程编排说明（开设什么课/怎么排课），不是学生能力。抽取阶段的过滤漏网。'
    for x, lo, hi, cur in fix_stage:
        x['stageHint'] = {'min': f'G{lo}', 'max': f'G{hi}'}
        x.setdefault('provenance', {})['stageFixedFrom'] = f'G{cur[0]}-G{cur[1]}'

    for fname, arr in files.items():
        with (ROOT / 'anchors' / fname).open('w', encoding='utf-8') as f:
            for x in arr:
                f.write(json.dumps(x, ensure_ascii=False) + '\n')
    n = len(drop_invent) + len(drop_metric) + len(drop_arrange)
    print(f"\n✓ 弃用 {n} 条（留档不删），修正学段 {len(fix_stage)} 条")


if __name__ == '__main__':
    main()
