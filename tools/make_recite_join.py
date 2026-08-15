#!/usr/bin/env python3
"""
make_recite_join.py — 出一份给外部产品对接用的背诵篇目映射。

面向的场景：诗歌库（shige.yongle.school）这类已有自己诗词数据的产品，
要把自己的记录对上底座的锚点 ID，从此两边共用一套 ID。

对接方只需要做一件事：拿自己的 (标题, 作者) 去 matchKey 上查。
其余的坑这份文件替它填了：

  · **标点混用。** 诗歌库正文里全角半角混着用（这是那个项目实测的坑），
    所以匹配键全部去标点、去空白后再比。
  · **同名不同篇。** 135 篇里有 6 组同标题的（如两首《望岳》），
    光靠标题会撞。matchKey 带首句前 5 字消歧，titleOnly 里标出了哪些会撞。
  · **书名号。** 《江南》和 江南 都能匹配上。

    python3 tools/make_recite_join.py
"""
import collections, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUNCT = re.compile(r'[《》〈〉「」『』（）()，,。.；;：:？?！!、\s·—…"\'"　]+')


def norm(s):
    """去标点、去空白、转小写。跨库匹配的规范形。"""
    return PUNCT.sub('', str(s or '')).lower()


def main():
    items = [json.loads(l) for l in (ROOT / 'lists/recite/yiwu-135.jsonl')
             .open(encoding='utf-8') if l.strip()]
    anchors = {}
    for f in sorted((ROOT / 'anchors').glob('*.jsonl')):
        for l in f.open(encoding='utf-8'):
            if l.strip():
                a = json.loads(l); anchors[a['id']] = a

    dup = collections.Counter(norm(x['key']) for x in items)
    collide = {k for k, n in dup.items() if n > 1}

    rows = []
    for x in items:
        meta = x.get('meta') or {}
        title, author = x['key'], meta.get('author') or ''
        first = meta.get('firstLine') or ''
        aid = (x.get('anchorIds') or [None])[0]
        a = anchors.get(aid) or {}
        tn = norm(title)
        rows.append({
            'anchorId': aid,
            'seq': x['seq'],
            'title': title,
            'author': author,
            'firstLine': first,
            'stage': x['stage'],
            'statement': a.get('statement'),
            'assessment': a.get('assessment'),
            # ── 匹配键 ───────────────────────────────────────
            'titleNorm': tn,
            'authorNorm': norm(author),
            'firstLineNorm': norm(first),
            # 同名篇目靠首句前 5 字消歧；不同名的 matchKey 退化成 titleNorm
            'matchKey': f'{tn}|{norm(first)[:5]}' if tn in collide else tn,
            'titleAmbiguous': tn in collide,
        })

    out = ROOT / 'mappings/recite-135-join.json'
    out.write_text(json.dumps({
        'schemaVersion': '0.1.0',
        'about': '教育部《义务教育语文课程标准（2022年版）》附录1 背诵推荐篇目 → 底座锚点 ID',
        'howToMatch': (
            '把你的 (标题, 作者) 用同样的规则归一（去《》()，。空白等标点、转小写），'
            '再查 matchKey；标题唯一时 matchKey 就是归一标题，标题重复时是 归一标题|首句前5字。'
            'titleAmbiguous=true 的条目必须带首句才能唯一确定。'
        ),
        'normalizeRule': 'strip 《》〈〉「」『』（）(),，。.;；:：?？!！、·—…"\\\'" 与空白，再 lower()',
        'count': len(rows),
        'ambiguousTitles': sorted(collide),
        'items': rows,
    }, ensure_ascii=False, indent=1), encoding='utf-8')

    print(f"  → {out}  {len(rows)} 篇")
    print(f"  同名需靠首句消歧的标题 {len(collide)} 组: {sorted(collide)}")
    stages = collections.Counter(r['stage'] for r in rows)
    print(f"  学段分布: {dict(stages)}")
    miss = [r for r in rows if not r['anchorId'] or not r['author']]
    print(f"  缺锚点或缺作者的: {len(miss)}")
    if miss:
        for r in miss[:5]:
            print(f"    {r['seq']} {r['title']} author={r['author']!r} anchor={r['anchorId']}")


if __name__ == '__main__':
    main()
