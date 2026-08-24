"""grain.py — grain.mjs 的 Python 孪生。**阈值读同一份 mappings/grain.json，不许各写一套。**"""
import json, re
from pathlib import Path

_CFG = json.loads((Path(__file__).resolve().parent.parent / 'mappings' / 'grain.json').read_text(encoding='utf-8'))


def _g(x):
    return int(x[1:]) if isinstance(x, str) and re.fullmatch(r'G\d+', x) else None


def grain_span(anchor):
    sh = anchor.get('stageHint') or {}
    lo, hi = _g(sh.get('min')), _g(sh.get('max'))
    return None if lo is None or hi is None or hi < lo else hi - lo + 1


def grain_of(anchor):
    n = grain_span(anchor)
    if n is None:
        return dict(_CFG['unknown'], span=None)
    b = next((b for b in _CFG['bands'] if n <= b['max']), _CFG['bands'][-1])
    return {'span': n, 'key': b['key'], 'label': b['label'],
            'warn': b['warn'].replace('{n}', str(n)) if b.get('warn') else None}
