#!/usr/bin/env python3
"""
apply_review.py — 把老师从图上导出的标记，回流到数据里。

复核这件事只有闭环才成立：
  老师在图上标记 → 导出 JSONL → 本工具 → reviewStatus 变 disputed → 排除出生产数据

**不做自动修改，只做降级。** 老师说「学段不对」，我们不去猜正确学段是什么；
标成 disputed，让它退出可用集合，等人来定。自动改会把一个「有人怀疑」
悄悄变成「有人确认」，那比不改更糟。

  python3 tools/apply_review.py review-*.jsonl [--dry-run]
"""
import argparse, collections, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ISSUE_CN = {'stage': '学段不对', 'wording': '表述要改', 'reject': '不该收',
            'missing-pre': '缺前置', 'other': '其他', 'edge-wrong': '依赖不成立'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('files', nargs='+')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    marks = []
    for f in a.files:
        for l in Path(f).read_text(encoding='utf-8').split('\n'):
            if l.strip():
                marks.append(json.loads(l))
    if not marks:
        sys.exit('没有读到任何标记')

    by_rev = collections.Counter(m.get('reviewer', 'anonymous') for m in marks)
    by_issue = collections.Counter(m['issue'] for m in marks)
    print(f"读入 {len(marks)} 条标记")
    print("  复核者:", dict(by_rev))
    print("  问题类型:", {ISSUE_CN.get(k, k): v for k, v in by_issue.most_common()})

    anchor_marks = {m['anchorId']: m for m in marks if m['kind'] == 'anchor'}
    edge_marks = {(m['anchorId'], m['prerequisiteId']) for m in marks if m['kind'] == 'edge'}

    # 锚点：降级为 disputed，把老师的意见和署名记进 reviewedBy / disputes
    touched_a = 0
    for f in sorted((ROOT / 'anchors').rglob('*.jsonl')):
        rows = [json.loads(l) for l in f.open(encoding='utf-8')]
        dirty = False
        for r in rows:
            m = anchor_marks.get(r['id'])
            if not m:
                continue
            r['reviewStatus'] = 'disputed'
            r.setdefault('disputes', []).append({
                'issue': m['issue'], 'note': m.get('note') or '',
                'by': m.get('reviewer') or 'anonymous', 'at': m.get('at'),
            })
            who = f"teacher:{(m.get('reviewer') or 'anonymous')}"
            if who not in (r.get('reviewedBy') or []):
                r.setdefault('reviewedBy', []).append(who)
            dirty = True; touched_a += 1
        if dirty and not a.dry_run:
            with f.open('w', encoding='utf-8') as fh:
                for r in rows:
                    fh.write(json.dumps(r, ensure_ascii=False) + '\n')

    # 边：标 disputed。不删 —— 删了就查不到「谁在什么时候说它不对」
    touched_e = 0
    for f in sorted((ROOT / 'edges').rglob('*.jsonl')):
        rows = [json.loads(l) for l in f.open(encoding='utf-8')]
        dirty = False
        for r in rows:
            if (r['anchorId'], r['prerequisiteId']) not in edge_marks:
                continue
            r['reviewStatus'] = 'disputed'
            dirty = True; touched_e += 1
        if dirty and not a.dry_run:
            with f.open('w', encoding='utf-8') as fh:
                for r in rows:
                    fh.write(json.dumps(r, ensure_ascii=False) + '\n')

    print(f"\n{'[dry-run] 将' if a.dry_run else '已'}标记 disputed：锚点 {touched_a} 条 · 边 {touched_e} 条")
    miss = set(anchor_marks) - {r['id'] for f in (ROOT / 'anchors').rglob('*.jsonl')
                                for r in map(json.loads, f.open(encoding='utf-8'))}
    if miss:
        print(f"  ⚠ {len(miss)} 条标记找不到对应锚点（数据可能已重建，ID 变了）")
    print("\n下一步：这些 disputed 条目已退出可用集合。逐条看老师的 disputes 说明，")
    print("      改对了把 reviewStatus 升为 expert-confirmed，改不动的保持 disputed。")
    print("      每条都带 provenance.srcPage，能直接翻回课标原页核对。")


if __name__ == '__main__':
    main()
