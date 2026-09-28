"""doc_stage.py — 课标文件本身定下的学段。**课标写了学段，模型的意见不能盖过课标。**

规则出自 resolve_disputed.py ①②。evfix_commit / evfix_round2 / revive 都要用它来裁决
复审提的 stage 异议 —— 原先在两个脚本里各写一份，第三个要用时收成这一处。
"""
import re
from fix_src_stages import read_bands, STD

_BANDS = None


def doc_stage(r, fname):
    """返回 ((lo, hi), 理由)；课标没定学段时返回 (None, None)。fname 是锚点所在文件名。"""
    global _BANDS
    if _BANDS is None:
        _BANDS, _ = read_bands()
    if fname.startswith('gaozhong-'):
        return (10, 12), '出自普通高中课标，学段由文档决定'
    m = re.fullmatch(r'第([一二三四])学段', ((r.get('provenance') or {}).get('srcStage') or '').strip())
    if m:
        return _BANDS.get(r['discipline'], STD)[m.group(1)], f'课标正文标了{m.group(0)}'
    return None, None


def split_stage_issues(r, fname, issues):
    """把复审提的 stage 异议按课标学段裁决：课标定了且与标注一致的 stage 异议撤掉。
    返回 (剩下的异议, 被撤的异议, 理由)。"""
    ds, why = doc_stage(r, fname)
    h = r.get('stageHint') or {}
    if ds and (h.get('min'), h.get('max')) == (f'G{ds[0]}', f'G{ds[1]}'):
        return [x for x in issues if x['type'] != 'stage'], [x for x in issues if x['type'] == 'stage'], why
    return issues, [], why
