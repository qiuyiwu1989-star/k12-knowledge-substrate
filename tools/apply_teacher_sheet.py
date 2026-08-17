#!/usr/bin/env python3
"""
apply_teacher_sheet.py — 吃 review-queue/teacher-sheet.html 复制出来的结果。

## 为什么和 apply_review.py 分开

`apply_review.py` **只会降级**。那是对的设计（老师说「学段不对」，我们不猜正确学段），
但它漏了一半：老师说「成立」的那些，得能真的升上去。

**`expert-confirmed` 一直是 0，整个可信度分级就一直没有底。**
把「有人签字」这条路修通，比再多抽一千条锚点值钱。

## 两个方向，规则不同

| 老师的判定 | 落到数据上 | 为什么 |
|---|---|---|
| 成立 | `expert-confirmed` + `reviewedBy: teacher:<名字>` | 这是签字，必须记名 |
| 学段不对 / 表述要改 / 不该收 | `disputed` + 记进 `disputes` | 只降级，不猜正确答案 |

**签字必须有名字，`--by` 是必填的。** 匿名的「成立」不是签字，是又一条没人负责的断言 ——
那正是这个项目一直在防的东西。

## 用

    pbpaste > /tmp/r.json                          # 老师发回来的那段
    python3 tools/apply_teacher_sheet.py /tmp/r.json --by 张老师 --dry-run
    python3 tools/apply_teacher_sheet.py /tmp/r.json --by 张老师
    npm run check                                  # 一定要跑
"""
import argparse, collections, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CN = {'ok': '成立', 'stage': '学段不对', 'wording': '表述要改', 'reject': '不该收'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('files', nargs='+', help='老师复制回来的 JSON（可多份）')
    ap.add_argument('--by', required=True,
                    help='复核者姓名或标识。**必填** —— 匿名的「成立」不是签字')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    rows = []
    for f in a.files:
        d = json.loads(Path(f).read_text(encoding='utf-8'))
        if d.get('schema') != 'k12-teacher-review/1':
            sys.exit(f'{f}: schema 不对（{d.get("schema")}），这不是复核单导出的格式')
        rows += d.get('rows') or []
    if not rows:
        sys.exit('没有读到任何判定')

    who = a.by if a.by.startswith('teacher:') else f'teacher:{a.by}'
    seen = {}
    for r in rows:                       # 同一条重复判定，后一次为准
        seen[r['anchorId']] = r
    cnt = collections.Counter(r['verdict'] for r in seen.values())
    print(f"读入 {len(seen)} 条判定，复核者 {who}")
    for k, v in cnt.most_common():
        print(f"  {CN.get(k, k)}：{v}")

    up = down = 0
    missing = set(seen)
    for f in sorted((ROOT / 'anchors').rglob('*.jsonl')):
        arr = [json.loads(l) for l in f.open(encoding='utf-8') if l.strip()]
        dirty = False
        for r in arr:
            m = seen.get(r['id'])
            if not m:
                continue
            missing.discard(r['id'])
            if r.get('deprecated'):
                print(f"  ⚠ {r['id']} 已弃用，跳过")
                continue
            if m['verdict'] == 'ok':
                r['reviewStatus'] = 'expert-confirmed'
                up += 1
            else:
                r['reviewStatus'] = 'disputed'
                r.setdefault('disputes', []).append({
                    'issue': m['verdict'], 'note': m.get('note') or '', 'by': who})
                down += 1
            # 签名一律记上，不管升还是降 —— 「谁看过这条」本身就是资产
            if who not in (r.get('reviewedBy') or []):
                r.setdefault('reviewedBy', []).append(who)
            if m.get('note'):
                r['reviewNote'] = m['note']
            dirty = True
        if dirty and not a.dry_run:
            with f.open('w', encoding='utf-8') as fh:
                for r in arr:
                    fh.write(json.dumps(r, ensure_ascii=False) + '\n')

    verb = '[dry-run] 将' if a.dry_run else '已'
    print(f"\n{verb}升为 expert-confirmed：{up} 条　{verb}降为 disputed：{down} 条")
    if missing:
        print(f"  ⚠ {len(missing)} 条找不到对应锚点（数据重建过？）：{list(missing)[:4]}")
    if up and not a.dry_run:
        print(f"\n★ expert-confirmed 第一次不是 0 了。跑 npm run check 确认，"
              f"然后 manifest 里的 humanConfirmedAnchors 会变成 {up}。")
    print("\n注意：降级的那些**没有自动改**。逐条看 disputes 里老师的说明，")
    print("     改对了再升 expert-confirmed，改不动的保持 disputed。")


if __name__ == '__main__':
    main()
