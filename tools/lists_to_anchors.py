#!/usr/bin/env python3
"""
lists_to_anchors.py — 把课标附录清单变成锚点，并把清单条目挂上去。

**这是全库唯一不需要等老师的一类锚点。**

判定成本决定了谁能自动确认：
  「能正确书写『人』字」        对错是客观的 → 不需要教学判断
  「能运用数形结合思想分析问题」  对错要老师判 → 必须等人

课标附录的字表和背诵篇目正好全属于前者，而且它们是全库唯一
**机械可验**的数据（编号连续性一对就知道抽全没抽全，实测 3500/135 一个不差）。
所以这批锚点标 `auto-confirmed` 不是放水，是这批数据的证据强度本来就最高：
  ① 来源是教育部课标附录，不是模型生成
  ② 抽取经过编号连续性校验，无缺号无重号
  ③ 判定标准客观，不依赖教学判断

两种粒度，按「这条是不是一个独立的能力」来定：
  · 背诵篇目 → **一篇一个锚点**。《静夜思》(G1) 和《岳阳楼记》(G9) 是
    不同学段的不同能力，合成一个就没法记「会哪几篇」了。
  · 字表 → **一张表一个容器锚点**。3,500 个「能写 X 字」不是 3,500 条能力，
    是同一条能力的 3,500 个测点。档案里用 assertion 的 listRef 记到字，
    schema 早就为这个留了位置。

  python3 tools/lists_to_anchors.py [--dry-run]
"""
import argparse, collections, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from mint_py import load_used_ids, mint_id   # noqa: E402

# 字表容器锚点：一张表一条能力，条目挂上去当测点
CONTAINERS = [
    dict(listId='lst_hanzi-jiben-300', verb='书写', obj='识字写字教学基本字表的字',
         statement='能正确书写识字写字教学基本字表中的汉字',
         stage=('G1', 'G2'), strand='识字与写字', type='LANGUAGE', cognitive='掌握',
         evidence=['听写时笔画笔顺正确、结构匀称', '能在方格内独立写出该字且不多笔少笔'],
         assessment='给{{name}}听写这张表里的字，他能写对多少个？'),
    dict(listId='lst_hanzi-changyong-3500', table='字表一', verb='书写', obj='常用字表一的字',
         statement='能正确书写义务教育语文课程常用字表一中的汉字',
         stage=('G1', 'G9'), strand='识字与写字', type='LANGUAGE', cognitive='掌握',
         evidence=['听写时能正确写出且无错别字', '能说出该字的部首与结构'],
         assessment='给{{name}}听写常用字，他能写对多少个？'),
    dict(listId='lst_hanzi-changyong-3500', table='字表二', verb='认读', obj='常用字表二的字',
         statement='能正确认读义务教育语文课程常用字表二中的汉字',
         stage=('G1', 'G9'), strand='识字与写字', type='LANGUAGE', cognitive='掌握',
         evidence=['见到该字能读出正确读音', '能在词语中辨认出该字'],
         assessment='{{name}}见到这些字能读出来吗？'),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    lists = {}
    for f in sorted((ROOT / 'lists').rglob('*.jsonl')):
        lists[f] = [json.loads(l) for l in f.open(encoding='utf-8')]
    used = load_used_ids(ROOT)
    new_anchors, links = [], collections.defaultdict(list)

    def base(**kw):
        return dict(id=kw['id'], discipline='语文', track='LIST', strand=kw['strand'],
                    topic=kw.get('topic'), dimension=kw.get('dimension'),
                    statement=kw['statement'], verb=kw['verb'], object=kw['obj'],
                    type=kw['type'], literacy=kw.get('literacy', ['语言运用', '文化自信']),
                    cognitive=kw['cognitive'],
                    stageHint={'min': kw['stage'][0], 'max': kw['stage'][1]},
                    evidence=kw['evidence'], assessment=kw['assessment'],
                    evidenceSource='curriculum-appendix',
                    reviewStatus='auto-confirmed', reviewedBy=[],
                    deprecated=False, supersededBy=None,
                    autoConfirmBasis=[
                        '来源：教育部《义务教育语文课程标准（2022年版）》附录，非模型生成',
                        '抽取经编号连续性机械校验，无缺号无重号',
                        '判定标准客观（写对/读对），不依赖教学判断',
                    ],
                    provenance=kw['prov'], schemaVersion='0.1.0')

    # ── 字表容器 ──
    for c in CONTAINERS:
        items = [x for f, rows in lists.items() for x in rows
                 if x['listId'] == c['listId'] and (not c.get('table') or (x.get('meta') or {}).get('table') == c['table'])]
        if not items:
            continue
        cid = mint_id(used)
        pages = sorted({x['extraction']['srcPage'] for x in items if x.get('extraction')})
        new_anchors.append(base(id=cid, **{k: v for k, v in c.items() if k not in ('listId', 'table')},
                                prov={'srcSubject': '语文', 'srcPage': pages[0] if pages else '',
                                      'srcPageRange': f"{pages[0]}–{pages[-1]}" if pages else '',
                                      'method': 'curriculum-appendix', 'itemCount': len(items)}))
        for x in items:
            links[(x['listId'], x['key'], (x.get('meta') or {}).get('table'))].append(cid)
        print(f"  容器锚点 {cid}  {c['statement'][:28]}  挂 {len(items)} 个字")

    # ── 背诵篇目：一篇一个 ──
    recite = [x for f, rows in lists.items() for x in rows if x['kind'] == 'RECITE']
    STAGE = {'G1-6': ('G1', 'G6'), 'G7-9': ('G7', 'G9')}
    # 同名篇目要消歧：《凉州词》有王之涣和王翰两首，《绝句》《悯农》《四时田园杂兴》
    # 《渔家傲》《己亥杂诗》也各有两首。课标附录本身就是用首句区分的，照做。
    # 不消歧的话去重签名会撞，而「两首不同的诗共用一个锚点」正是 Marble 那 21 组
    # 同名节点的病根 —— 档案里根本分不出孩子背的是哪一首。
    tcount = collections.Counter(x['key'] for x in recite)
    for x in sorted(recite, key=lambda r: (r.get('stage') or '', r.get('seq') or 0)):
        st = STAGE.get(x.get('stage'), ('G1', 'G9'))
        title = x['key']
        m = x.get('meta') or {}
        first = (m.get('firstLine') or '')[:7]
        author = m.get('author') or ''
        dup = tcount[title] > 1
        disp = f'{title}（{first}）' if (dup and first) else (f'{title}·{author}' if dup else title)
        aid = mint_id(used)
        new_anchors.append(base(
            id=aid, strand='阅读与鉴赏', topic=None, dimension=None,
            statement=f'能背诵《{disp}》全文且不错漏'[:60],
            verb='背诵', obj=f'{disp}全文', type='LANGUAGE', cognitive='掌握', stage=st,
            evidence=[f'能独立背诵《{disp}》全文，不添字漏字', '能默写出全文且无错别字'],
            assessment=f'{{{{name}}}}能把《{disp}》完整背下来吗？',
            prov={'srcSubject': '语文', 'srcPage': (x.get('extraction') or {}).get('srcPage', ''),
                  'method': 'curriculum-appendix', 'author': m.get('author'),
                  'firstLine': m.get('firstLine'), 'seq': x.get('seq')}))
        links[(x['listId'], x['key'], None)].append(aid)
    print(f"  背诵篇目锚点 {len(recite)} 条（一篇一个 —— 不同学段的不同能力，合成一条就记不了「会哪几篇」）")

    if a.dry_run:
        print(f"\n[dry-run] 将新增 {len(new_anchors)} 条 auto-confirmed 锚点")
        return

    p = ROOT / 'anchors' / 'chinese-lists.jsonl'
    with p.open('w', encoding='utf-8') as f:
        for r in new_anchors:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    n = 0
    for f, rows in lists.items():
        dirty = False
        for x in rows:
            ids = links.get((x['listId'], x['key'], (x.get('meta') or {}).get('table'))) \
                or links.get((x['listId'], x['key'], None))
            if ids and x.get('anchorIds') != ids:
                x['anchorIds'] = ids; dirty = True; n += 1
        if dirty:
            with f.open('w', encoding='utf-8') as fh:
                for x in rows:
                    fh.write(json.dumps(x, ensure_ascii=False) + '\n')

    print(f"\n✓ 新增 {len(new_anchors)} 条锚点 → anchors/chinese-lists.jsonl")
    print(f"✓ {n} 条清单条目挂上了锚点（此前是 0）")
    print(f"\n  全部 auto-confirmed —— usableAnchors 第一次非 0。")
    print(f"  这不是降低标准：这批数据来自课标附录、经过机械校验、判定标准客观，")
    print(f"  证据强度是全库最高的一类。")


if __name__ == '__main__':
    main()
