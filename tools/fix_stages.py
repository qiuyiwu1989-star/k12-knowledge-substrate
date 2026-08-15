#!/usr/bin/env python3
"""
fix_stages.py — 用课程方案的开设年级硬约束修正学段。

这个错误是可视化顶出来的：图上「能完成氧气和二氧化碳的实验室制取」标在 1–2 年级，
一眼就知道不对。查下来物理 39%、化学 60%、生物学 38% 的条目都被标到了小学。

根因：物理/化学/生物学是初中才开设的学科，课标正文不用小学那套「第一学段」表述，
Pass A 抽不到学段就落回了默认值 → STAGE_GRADE 把它映射成 G1。

修法不是猜，是查《义务教育课程方案（2022年版）》的开设年级 —— 这是硬事实：
把每个学科的学段区间裁剪到它实际开设的年级范围内。
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
G = lambda s: int(s[1:]) if s and s.startswith('G') else None

# 《义务教育课程方案（2022年版）》各科开设年级
OPEN_AT = {
    '语文': (1, 9), '数学': (1, 9), '英语': (3, 9),          # 外语 3 年级起
    '道德与法治': (1, 9), '体育与健康': (1, 9), '艺术': (1, 9), '劳动': (1, 9),
    '科学': (1, 9),                                          # 科学 1–9（初中分科后仍保留综合）
    '信息科技': (3, 8),                                       # 信息科技 3–8 年级
    '历史': (7, 9), '地理': (7, 9),                           # 初中才独立开设
    '生物学': (7, 9), '物理': (8, 9), '化学': (9, 9),
}

changed = 0
for f in sorted((ROOT / 'anchors').rglob('*.jsonl')):
    rows = [json.loads(l) for l in f.open(encoding='utf-8')]
    for r in rows:
        lo, hi = OPEN_AT.get(r['discipline'], (1, 9))
        sh = r.get('stageHint') or {}
        a, b = G(sh.get('min')) or lo, G(sh.get('max')) or hi
        na, nb = max(lo, min(hi, a)), max(lo, min(hi, b))
        if nb < na:
            na = nb = lo
        if (na, nb) != (a, b) or not r.get('stageHint'):
            r['stageHint'] = {'min': f'G{na}', 'max': f'G{nb}'}
            r.setdefault('stageFix', '按课程方案开设年级裁剪')
            changed += 1
    with f.open('w', encoding='utf-8') as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + '\n')

print(f"✓ 修正 {changed} 条学段（含补齐 stageHint 为空的）")
