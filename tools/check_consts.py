#!/usr/bin/env python3
"""check_consts.py — 拦「加了学科，常量表没跟上」。

2026-09-28 立。起因是同一个病撞了两次，都是**加高中 20 科时没人回头对常量表**：

  · make_graph.COLORS 只有义务教育那 14 科 → 943 个点（全图 26%）没有颜色，画成灰
  · ai_review.OPEN_AT 把艺术写成 (1,9)，而《普通高中艺术课程标准》真实存在、
    库里 61 条 G10–G12 → 复核时 34 条里 32 条被误判学段错

两个常量都**只能手写**（颜色是设计选择；开设年级必须是独立于锚点的事实，
否则用锚点自己的学段去核锚点的学段就成了循环论证）。所以不能「改成现读」，
只能立闸盯着。三条：

  1. 每个存活学科都在 COLORS 里
  2. 每个存活学科都在 OPEN_AT 里
  3. 锚点的学段必须和开设年级**有交集** —— 没交集的超过 3 条就红。
     这一条抓的是「键在、值错」，也就是当初艺术 (1,9) 那种（G10–G12 和 1–9 完全不相交）。

     ★ 第一版写成「必须完全落在范围内」，当场报了四科。看数据才发现三科是闸写严了：
       英语 43 条 G1–G9 是「义务教育全段」的占位（课标按级别不按年级），
       物理 / 化学各十几条 G7–G9 是课标自己的第四学段 —— 学段级标注天然会超出开课那一年。
       **正确的判据是「开课的年份里至少有一年能教这条」，也就是有交集。**
       改完之后只剩信息科技 4 条 G1–G2 是真错（课标原件印在第二学段，已改成 G3–G4）。
"""
import json, re, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from make_graph import COLORS          # noqa: E402
from ai_review import OPEN_AT          # noqa: E402

G = lambda s: int(s[1:]) if isinstance(s, str) and re.fullmatch(r'G\d+', s) else None
live = []
for f in sorted((ROOT / 'anchors').glob('*.jsonl')):
    for l in f.open(encoding='utf-8'):
        if l.strip():
            a = json.loads(l)
            if not a.get('deprecated'):
                live.append(a)
discs = Counter(a['discipline'] for a in live)
bad = []
no_color = sorted(d for d in discs if d not in COLORS)
no_open = sorted(d for d in discs if d not in OPEN_AT)
if no_color:
    bad.append(f'✗ {len(no_color)} 个学科没有颜色（会画成灰）：' + '、'.join(f'{d}({discs[d]})' for d in no_color))
if no_open:
    bad.append(f'✗ {len(no_open)} 个学科没有开设年级（复核判不了学段）：' + '、'.join(no_open))
outside = defaultdict(list)
for a in live:
    rng = OPEN_AT.get(a['discipline'])
    sh = a.get('stageHint') or {}
    lo, hi = G(sh.get('min')), G(sh.get('max'))
    if rng and lo and hi and (hi < rng[0] or lo > rng[1]):      # 不相交
        # 已经标了 fieldIssues: stage 的是**已知问题**，放行 —— 闸拦的是没人发现的。
        # 和对待已弃用锚点同一个逻辑。2026-09-28 首跑抓出信息科技 4 条标成一二年级的
        # 「数据与编码」，而信息科技三年级才开课；但义务教育课标原件不在仓库里，
        # 翻不了原文，**推断不能当事实写进学段字段**，所以只标记、不改学段。
        # 同日补记：翻到原件（2022 版信息科技课标 PDF 第 31、34 页），两处都在
        # 「第二学段（3～4 年级）」之下 —— 已按原文改成 G3–G4，标记摘掉。现在这里没有例外。
        if 'stage' in (a.get('fieldIssues') or []):
            continue
        outside[a['discipline']].append(a['id'])
for d, ids in sorted(outside.items(), key=lambda t: -len(t[1])):
    if ids:
        bad.append(f'✗ {d}：OPEN_AT 写的是 {OPEN_AT[d]}，但有 {len(ids)} 条锚点'
                   f'和开设年级完全不相交 —— 要么常量写错了（当初艺术 (1,9) 就是这样），要么这些锚点学段标错了：' + ' '.join(ids[:6]))
if bad:
    print('\n'.join(bad))
    print('\n  加学科时 COLORS（tools/make_graph.py）和 OPEN_AT（tools/ai_review.py）要一起改。')
    sys.exit(1)
print(f'✓ {len(discs)} 个学科都有颜色和开设年级，且各科锚点都和开设年级有交集（已标记的已知问题除外）')
