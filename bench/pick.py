#!/usr/bin/env python3
"""
pick.py — 从 bench/.cache/pool.jsonl 里**按固定种子分层抽** 100 题，写 bench/mapping-100.jsonl。

只跑一次。之后这 100 题就定了，标注往上加，不再重抽 —— 重抽等于换考卷，
前后两次命中率就没法比了。

分层（按学段和学科铺开，不按「映射器擅长什么」挑）：
  小学  CMATH        每个年级 5 题        30
  初中  C-Eval       7 科 × 5 题          35
  高中  GAOKAO-Bench 数学 6 · 语文 5 · 其余 6 科各 4   35

排除：题面引用了图（「如图」「下图」…）—— 看不到图，人也标不准；
     题面超过 500 字 —— 一题考一串能力，拿来量「对到哪几条」会把问题搅浑。

仓库里只存来源、编号和题面哈希（fetch.py 头注释说了为什么不存原文）。
哈希用来发现上游改了题：改了就得重标，不能拿旧标注去评新题。
"""
import collections, hashlib, json, random
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEED = 20260928
FIG = ('如图', '下图', '图中', '图示', '右图', '左图', '上图', '图所示', '示意图')
QUOTA_GK = {'数学': 6, '语文': 5}


def ok(x):
    t = x['text']
    return len(t) <= 500 and not any(k in t for k in FIG)


def main():
    pool = [json.loads(l) for l in (HERE / '.cache' / 'pool.jsonl').open(encoding='utf-8')]
    rnd = random.Random(SEED)
    strata = collections.defaultdict(list)
    for x in pool:
        if not ok(x):
            continue
        key = (x['src'], x['stage'] if x['src'] == 'cmath' else x['discipline'])
        strata[key].append(x)
    picked = []
    for key in sorted(strata):
        src, k = key
        n = 5 if src in ('cmath', 'ceval') else QUOTA_GK.get(k, 4)
        xs = sorted(strata[key], key=lambda x: x['ref'])
        picked += rnd.sample(xs, min(n, len(xs)))
    out = []
    for i, x in enumerate(picked, 1):
        out.append({'qid': f'q{i:03d}', 'src': x['src'], 'ref': x['ref'], 'stage': x['stage'],
                    'discipline': x['discipline'],
                    'textSha': hashlib.sha256(x['text'].encode()).hexdigest()[:16],
                    'gold': None, 'labeledBy': None, 'note': None})
    (HERE / 'mapping-100.jsonl').write_text(
        ''.join(json.dumps(o, ensure_ascii=False) + '\n' for o in out), encoding='utf-8')
    c = collections.Counter((o['src'], o['discipline']) for o in out)
    print(f'✓ bench/mapping-100.jsonl  {len(out)} 题')
    for k, n in sorted(c.items()):
        print(f'   {k[0]:<7}{k[1]:<6}{n}')


if __name__ == '__main__':
    main()
