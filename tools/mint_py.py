"""ID 铸造（Python 侧）。规则与 scripts/lib/mint.mjs 一致：无语义、永不复用。

铸造前必须加载**全部**已用 ID（含 candidates/ 和 retired/）。
复用一个「看起来没人用」的 ID 是这套系统里最贵的错误——
它会把两个孩子的不同能力记录悄悄合并，而且没有任何报错。
"""
import json
import random
import re
from pathlib import Path

ALPHABET = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # 去掉 0/O/1/l/I
ID_RE = re.compile(r'"(?:id|anchorId|prerequisiteId|supersededBy)"\s*:\s*"(ca_[A-Za-z0-9]{8})"')


def load_used_ids(root: Path):
    used = set()
    for d in ('anchors', 'candidates', 'edges', 'lists', 'mappings', 'retired'):
        p = root / d
        if not p.exists():
            continue
        for f in p.rglob('*.jsonl'):
            for line in f.read_text(encoding='utf-8').split('\n'):
                used.update(ID_RE.findall(line))
    return used


def mint_id(used: set, rng=random):
    for _ in range(10000):
        s = 'ca_' + ''.join(rng.choice(ALPHABET) for _ in range(8))
        if s not in used:
            used.add(s)
            return s
    raise RuntimeError('ID 空间冲突过于频繁——检查 used 是否被正确加载')
