#!/usr/bin/env python3
"""
apply_review.py — 把老师从图上导出的标记，回流到数据里。

复核这件事只有闭环才成立。而闭环有**两个方向**：

  老师标「学段不对/表述要改/不该收」 → disputed        → 退出可用集合
  老师标「成立」                    → expert-confirmed → 进入可用集合

**第一版只做了降级方向**，「成立」被和否定意见一样打成 disputed。
后果很荒唐：**哪怕老师认真做完 411 条全标「成立」，expert-confirmed 仍然是 0** ——
系统压根没有记录「人认可了」的通路，而那正是整个项目唯一重要的进度指标。
这不是少写了一个分支，是把复核理解成了「挑错」而不是「签字」。

## 两个方向的严格程度不对称，这是有意的

**降级只需要一个人说不对。** 一条被怀疑的锚点继续留在可用集合里，
代价是它可能被写进某个孩子的档案 —— 宁可错杀。

**升级要求署名。** `expert-confirmed` 的含义是「有具体的人对这条负责」，
匿名的「成立」不构成签字，只记成 ai-adjudicated 之上的一次背书但不升级。
署名是可核对的：reviewedBy 里留 `teacher:<名字>`，将来出问题查得到人。

**不做自动修改。** 老师说「学段不对」，我们不去猜正确学段是什么；
标成 disputed 让它退出可用集合，等人来定。自动改会把「有人怀疑」
悄悄变成「有人确认」，那比不改更糟。

  python3 tools/apply_review.py review-*.jsonl [--dry-run]
"""
import argparse, collections, json, os, sys
from pathlib import Path

# K12_ROOT 可指向任意数据根 —— validate.mjs 早就认它（selftest 和分片 CI 用），
# 工具侧一直没跟上，于是复核闭环没法在临时目录里被测试。
# 想测一条会改数据的流程，就必须能让它改别处的数据。
ROOT = Path(os.environ.get('K12_ROOT') or Path(__file__).resolve().parent.parent)
ISSUE_CN = {'ok': '成立（签字）', 'stage': '学段不对', 'wording': '表述要改',
            'reject': '不该收', 'missing-pre': '缺前置', 'other': '其他',
            'edge-wrong': '依赖不成立'}


def verdict_of(m):
    """取一条标记的结论。**两端字段名不一样，只在这一处收敛。**

    复核单导出叫 `verdict`，图谱页导出叫 `issue`。散在各处各写各的，
    就会像第一版那样：一个分支认 issue、另一个分支 KeyError。
    """
    return m.get('issue') or m.get('verdict') or 'other'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('files', nargs='+')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    # ★ 两种输入格式都要认。
    #   复核单（make_teacher_sheet.py）导出的是 {schema, reviewedAt, rows:[...]}
    #   一整个 JSON；图谱页导出的是 JSONL 一行一条。
    #   **第一版只认 JSONL，喂真实导出直接崩** —— 这条闭环从来没端到端跑过，
    #   而它是整个项目唯一能把 humanConfirmedAnchors 从 0 抬起来的通路。
    #   接口两端各自演进却从不对接，是最容易积累的一类债。
    marks = []
    for f in a.files:
        raw = Path(f).read_text(encoding='utf-8').strip()
        if raw.startswith('{') and '"rows"' in raw[:400]:
            d = json.loads(raw)
            who = (d.get('reviewer') or '').strip()
            when = d.get('reviewedAt')
            for r in d.get('rows') or []:
                marks.append({**r, 'kind': r.get('kind', 'anchor'),
                              'reviewer': r.get('reviewer') or who,
                              'at': r.get('at') or when})
        else:
            for l in raw.split('\n'):
                if l.strip():
                    m = json.loads(l)
                    m.setdefault('kind', 'anchor')
                    marks.append(m)
    if not marks:
        sys.exit('没读到任何标记')
    if not marks:
        sys.exit('没有读到任何标记')

    by_rev = collections.Counter(m.get('reviewer', 'anonymous') for m in marks)
    by_issue = collections.Counter(verdict_of(m) for m in marks)
    print(f"读入 {len(marks)} 条标记")
    print("  复核者:", dict(by_rev))
    print("  问题类型:", {ISSUE_CN.get(k, k): v for k, v in by_issue.most_common()})

    anchor_marks = {m['anchorId']: m for m in marks if m['kind'] == 'anchor'}
    edge_marks = {(m['anchorId'], m['prerequisiteId']) for m in marks if m['kind'] == 'edge'}

    # 锚点：降级为 disputed，把老师的意见和署名记进 reviewedBy / disputes
    touched_a = confirmed_a = skipped_anon = skipped_disputed = 0
    for f in sorted((ROOT / 'anchors').rglob('*.jsonl')):
        rows = [json.loads(l) for l in f.open(encoding='utf-8')]
        dirty = False
        for r in rows:
            m = anchor_marks.get(r['id'])
            if not m:
                continue
            reviewer = (m.get('reviewer') or '').strip()
            who = f"teacher:{reviewer or 'anonymous'}"
            issue = verdict_of(m)

            if issue in ('ok', '成立'):
                # ★ 升级方向。要求署名 —— expert-confirmed 的含义是
                #   「有具体的人对这条负责」，匿名的「成立」不构成签字。
                if not reviewer:
                    skipped_anon += 1
                    continue
                # 已经 disputed 的不因为一句「成立」就翻案：
                # 有人说过不对，就得先把那条意见处理掉。
                if r['reviewStatus'] == 'disputed':
                    skipped_disputed += 1
                    continue
                r['reviewStatus'] = 'expert-confirmed'
                r.setdefault('endorsements', []).append({
                    'by': reviewer, 'at': m.get('at'), 'note': m.get('note') or '',
                })
                confirmed_a += 1
            else:
                r['reviewStatus'] = 'disputed'
                r.setdefault('disputes', []).append({
                    'issue': issue, 'note': m.get('note') or '',
                    'by': reviewer or 'anonymous', 'at': m.get('at'),
                })
                touched_a += 1

            if who not in (r.get('reviewedBy') or []):
                r.setdefault('reviewedBy', []).append(who)
            dirty = True
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

    v = '[dry-run] 将' if a.dry_run else '已'
    print(f"\n{v}降级 disputed：锚点 {touched_a} 条 · 边 {touched_e} 条")
    print(f"{v}升级 expert-confirmed：锚点 {confirmed_a} 条")
    if skipped_anon:
        print(f"  ⚠ {skipped_anon} 条标了「成立」但没署名 —— 未升级。"
              f"expert-confirmed 的含义是有人负责，匿名不算签字")
    if skipped_disputed:
        print(f"  ⚠ {skipped_disputed} 条标了「成立」但已被人标为 disputed —— 未升级。"
              f"先处理掉那条异议再说")
    miss = set(anchor_marks) - {r['id'] for f in (ROOT / 'anchors').rglob('*.jsonl')
                                for r in map(json.loads, f.open(encoding='utf-8'))}
    if miss:
        print(f"  ⚠ {len(miss)} 条标记找不到对应锚点（数据可能已重建，ID 变了）")
    print("\n下一步：")
    print("  · disputed 的已退出可用集合。逐条看 disputes 说明，改对了升 expert-confirmed，")
    print("    改不动的保持 disputed。")
    print("  · expert-confirmed 的是**第一批有人签字的锚点**。跑 npm run manifest 看")
    print("    humanConfirmedAnchors 从 0 变成了多少 —— 那是这个项目唯一重要的进度指标。")
    print("      每条都带 provenance.srcPage，能直接翻回课标原页核对。")


if __name__ == '__main__':
    main()
