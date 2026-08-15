#!/usr/bin/env python3
"""
promote.py — 候选 → anchors/。

方向调整后的做法：**先把整张图建出来，再让老师在图里挑毛病。**
让老师逐条判断孤立断言（「圆锥的特征该不该放五年级」）是不可能完成的任务，
他需要看到前后左右有什么。所以候选整体转正为 llm-proposed 锚点，
带上机器起草的 evidence，进图、连边、可视化，然后开放批评。

诚实性靠 reviewStatus 承载，不靠「不进库」：
  · 全部 llm-proposed —— manifest 的 usableAnchors 依然不算它们
  · evidence 来自机器起草，evidenceSource 字段标明
  · JUNK 桶不转正（那是机器都能判定的垃圾）
"""
import collections, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'tools/out/review-sheet.jsonl'
FILE = {'数学': 'math', '语文': 'chinese', '英语': 'english', '物理': 'physics', '化学': 'chemistry',
        '生物学': 'biology', '历史': 'history', '地理': 'geography', '道德与法治': 'morality',
        '科学': 'science', '信息科技': 'infotech', '劳动': 'labor', '艺术': 'art', '体育与健康': 'pe'}

rows = [json.loads(l) for l in SRC.open(encoding='utf-8')]
keep = [r for r in rows if r['bucket'] != 'JUNK']
out = collections.defaultdict(list)
no_ev = 0
for r in keep:
    ev = [e for e in (r.get('evidenceDraft') or []) if isinstance(e, str) and len(e) >= 4]
    if not ev:
        no_ev += 1
        ev = [f"能完成：{r['statement']}"]          # 兜底，标注来源为 fallback
        src = 'fallback'
    else:
        src = 'llm-draft'
    out[r['discipline']].append({
        'id': r['id'], 'discipline': r['discipline'], 'track': r['track'],
        'strand': r.get('strand'), 'topic': None, 'dimension': None,
        'statement': r['statement'], 'verb': r['verb'], 'object': r['object'],
        'type': r['type'], 'literacy': r.get('literacy') or [], 'cognitive': r['cognitive'],
        'stageHint': r.get('stageHint'),
        'evidence': ev[:4],
        'assessment': r.get('assessmentDraft') or None,
        'evidenceSource': src,
        'reviewStatus': 'llm-proposed', 'reviewedBy': [],
        'deprecated': False, 'supersededBy': None,
        'triageBucket': r['bucket'], 'provenance': r['provenance'],
        'schemaVersion': '0.1.0',
    })

tot = 0
for disc, rs in sorted(out.items()):
    p = ROOT / 'anchors' / f"{FILE.get(disc, disc)}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('w', encoding='utf-8') as f:
        for r in rs:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    tot += len(rs)
    print(f"  anchors/{p.name:<15} {len(rs):>4}")
print(f"\n转正 {tot} 条（丢弃 JUNK {len(rows)-len(keep)} 条）· evidence 兜底 {no_ev} 条")
print("  全部 llm-proposed —— usableAnchors 不算它们，图建出来是为了让人挑毛病，不是为了假装完成")
