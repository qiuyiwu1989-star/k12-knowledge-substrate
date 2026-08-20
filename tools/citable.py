"""citable.py — 「可被 L3 档案引用」的唯一定义，从 mappings/citable.json 现读。

和 scripts/lib/citable.mjs 读的是同一个文件。**不许在任何工具里再写一遍这个集合。**
"""
import json, os
from pathlib import Path

_ROOT = Path(os.environ.get('K12_ROOT', Path(__file__).resolve().parent.parent))
_J = json.loads((_ROOT / 'mappings/citable.json').read_text(encoding='utf-8'))
CITABLE = set(_J['citable'])
HUMAN_CONFIRMED = set(_J['humanConfirmed'])
# 图上的成色分档。和 CITABLE 是两件事：成色决定填充强度，可引用决定要不要加白边。
TIERS = _J['tiers']
