#!/usr/bin/env python3
"""
make_slices.py — 把底座切成别人拿得走的静态数据包。

## 两种片，性质不同，绝不能混

  **学段片 `stage/`** —— 归属。课标自己就是按学段编排的（G1-2/G3-4/G5-6/G7-9），
    高中按模块给内容、不分年级，所以是 G10-12 一整段。一条锚点只属于一个学段片。

  **年级投影片 `grade-projection/`** —— **不是归属，是切面**。
    「G8 这一年，哪些锚点覆盖到你」。同一条会同时出现在三个年级片里，**那是对的**。

文件名故意叫 `grade-projection` 而不是 `grade`：防着被人当成
「三年级的知识图谱」引出去。数据支持这个区别 ——
真精确到一年的只有 149 条，1,745 条跨 3 年，188 条跨满九年。
**替课标发明它没说的年级精度，正是这个项目一直拒绝的做法**（见 CLAUDE.md 红线）。

## 每片都带 _meta

消费方不看正文也该能判断这批数据够不够格用在自己的场景里。所以 `_meta` 里
**必须原样带上教师签字数** —— 现在是 0，而「可引用 1,747」的含义是
「AI 看过、没挑出毛病」，不是有人签过字。

## 精度标注

每条带 `span`：真实精度是 `year`（1 年）/ `stage`（学段）/ `module`（高中模块）/
`unspecified`（跨满九年，等于没给）。年级片里 `unspecified` 的单独归到
`lowPrecision` 数组，不混在正文里。

    python3 tools/make_slices.py
    python3 tools/make_slices.py --out dist/data
"""
import argparse, collections, json, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from citable import CITABLE, HUMAN_CONFIRMED     # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STAGES = [('G1-2', 1, 2), ('G3-4', 3, 4), ('G5-6', 5, 6), ('G7-9', 7, 9), ('G10-12', 10, 12)]


def g(s):
    return int(s[1:]) if isinstance(s, str) and s.startswith('G') else None


def span_of(a):
    sh = a.get('stageHint') or {}
    lo, hi = g(sh.get('min')), g(sh.get('max'))
    if lo is None:
        return None, 'unspecified'
    hi = hi or lo
    n = hi - lo + 1
    if n >= 9:
        kind = 'unspecified'          # 跨满九年 = 等于没给年级信息
    elif lo >= 10:
        kind = 'module'               # 高中按模块给内容，不分年级
    elif n == 1:
        kind = 'year'
    else:
        kind = 'stage'
    return (lo, hi), kind


def slim(a, span, kind):
    """片里的一条。**不重复整个锚点** —— 消费方要全量去 /data/anchors。
    这里只放定位、引用、判定用得着的。"""
    p = a.get('provenance') or {}
    return {
        'id': a['id'], 'discipline': a['discipline'], 'track': a['track'],
        'statement': a['statement'], 'verb': a.get('verb'), 'object': a.get('object'),
        'stage': {'min': (a.get('stageHint') or {}).get('min'),
                  'max': (a.get('stageHint') or {}).get('max')},
        # ★ 真实精度。年级片里这一条最要紧 —— 没有它，读者会以为每条都精确到年
        'span': kind,
        'courseType': a.get('courseType'),
        'cognitive': a.get('cognitive'), 'literacy': a.get('literacy') or [],
        'topic': a.get('topic'), 'strand': a.get('strand'),
        'evidence': a.get('evidence') or [], 'assessment': a.get('assessment'),
        # 成色一路透传，不许在片里丢掉
        'reviewStatus': a['reviewStatus'],
        'citable': a['reviewStatus'] in CITABLE,
        'humanConfirmed': a['reviewStatus'] in HUMAN_CONFIRMED,
        'fieldIssues': a.get('fieldIssues') or [],
        'isOurAssertion': a.get('evidenceSource') == 'capability-rewrite',
        'srcPage': p.get('srcPage'), 'srcText': p.get('srcText'),
    }


def meta(rows, kind, key, commit):
    by = collections.Counter(r['reviewStatus'] for r in rows)
    return {
        'sliceKind': kind, 'sliceKey': key,
        'anchors': len(rows),
        'citable': sum(1 for r in rows if r['citable']),
        # **原样带上，不许省** —— 「可引用」的含义是 AI 看过没挑出毛病，不是有人签过字
        'humanConfirmed': sum(1 for r in rows if r['humanConfirmed']),
        'byReviewStatus': dict(by.most_common()),
        'bySpan': dict(collections.Counter(r['span'] for r in rows).most_common()),
        'disciplines': dict(collections.Counter(r['discipline'] for r in rows).most_common()),
        'schemaVersion': '0.1.0', 'sourceCommit': commit,
        'note': ('学段片是归属：一条锚点只属于一个学段片。' if kind == 'stage' else
                 '年级投影片**不是归属，是切面**：同一条锚点会出现在多个年级片里，那是对的。'
                 '课标不是按年级组织的，替它发明年级精度是这个项目明确拒绝的做法。'
                 if kind == 'grade-projection' else '按学科归属。'),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='dist/data/slice')
    a = ap.parse_args()
    out = ROOT / a.out
    try:
        commit = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT,
                                capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        commit = None

    live = []
    for f in sorted((ROOT / 'anchors').glob('*.jsonl')):
        for l in f.open(encoding='utf-8'):
            if l.strip():
                x = json.loads(l)
                if not x.get('deprecated'):
                    live.append(x)
    print(f'存活锚点 {len(live)}')

    prepared = []
    for x in live:
        sp, kind = span_of(x)
        prepared.append((sp, kind, slim(x, sp, kind)))

    n_files = 0
    # ── 学段片：归属 ──────────────────────────────────────────────
    for key, lo, hi in STAGES:
        # 归属判据：**按起点归**，一条只进一个片。
        # （上一版这里先写了「区间有重叠就算」再被这一行覆盖 —— 死代码，已删。
        #   重叠判据会让一条 G1–G9 的锚点同时进五个学段片，那就不是归属了。）
        rows = [r for sp, k, r in prepared if sp and lo <= sp[0] <= hi]
        payload = {'_meta': meta(rows, 'stage', key, commit), 'anchors': rows}
        (out / 'stage').mkdir(parents=True, exist_ok=True)
        (out / 'stage' / f'{key}.json').write_text(
            json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        n_files += 1
        print(f'  stage/{key:<7} {len(rows):>5} 条 · 可引用 {payload["_meta"]["citable"]}')

    # ── 年级投影片：切面 ─────────────────────────────────────────
    (out / 'grade-projection').mkdir(parents=True, exist_ok=True)
    for gr in range(1, 13):
        hit = [(k, r) for sp, k, r in prepared if sp and sp[0] <= gr <= sp[1]]
        rows = [r for k, r in hit if k != 'unspecified']
        low = [r for k, r in hit if k == 'unspecified']
        m = meta(rows, 'grade-projection', f'G{gr}', commit)
        m['lowPrecisionCount'] = len(low)
        payload = {'_meta': m, 'anchors': rows,
                   # 跨满九年的单独放 —— 它们「覆盖到」每一个年级，等于没给年级信息，
                   # 混在正文里会让这一片看着比实际厚
                   'lowPrecision': low}
        (out / 'grade-projection' / f'G{gr}.json').write_text(
            json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        n_files += 1
        print(f'  grade-projection/G{gr:<3} {len(rows):>5} 条（另 {len(low)} 条精度不足）')

    # ── 学科片：归属 ─────────────────────────────────────────────
    (out / 'subject').mkdir(parents=True, exist_ok=True)
    by_disc = collections.defaultdict(list)
    for sp, k, r in prepared:
        by_disc[r['discipline']].append(r)
    for d, rows in sorted(by_disc.items()):
        payload = {'_meta': meta(rows, 'subject', d, commit), 'anchors': rows}
        (out / 'subject' / f'{d}.json').write_text(
            json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        n_files += 1

    # ── 目录 ─────────────────────────────────────────────────────
    index = {
        'schemaVersion': '0.1.0', 'sourceCommit': commit,
        'totals': {'anchors': len(live),
                   'citable': sum(1 for _, _, r in prepared if r['citable']),
                   'humanConfirmed': sum(1 for _, _, r in prepared if r['humanConfirmed'])},
        'howToCite': '引用锚点用 id（ca_ 开头，永不复用）。'
                     '**引用前先看 _meta.humanConfirmed** —— 现在是 0，'
                     '「可引用」的含义是「AI 看过、没挑出毛病」，不是有人签过字。',
        'slices': {
            'stage': [k for k, _, _ in STAGES],
            'grade-projection': [f'G{i}' for i in range(1, 13)],
            'subject': sorted(by_disc),
        },
        'spanMeaning': {
            'year': '真精确到某一年', 'stage': '学段制的一档（如 G3–4）',
            'module': '高中按模块给内容，不分年级',
            'unspecified': '跨满九年，等于没给年级信息 —— 年级片里单独归到 lowPrecision',
        },
    }
    (out / 'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding='utf-8')
    size = sum(f.stat().st_size for f in out.rglob('*.json'))
    print(f'\n→ {out}　{n_files + 1} 个文件 · {size/1024/1024:.1f}MB')
    print(f'  总计 {index["totals"]["anchors"]} 条 · 可引用 {index["totals"]["citable"]}'
          f' · 教师签字 {index["totals"]["humanConfirmed"]}')


if __name__ == '__main__':
    main()
