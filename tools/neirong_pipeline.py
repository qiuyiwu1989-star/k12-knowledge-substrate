#!/usr/bin/env python3
"""
neirong_pipeline.py — 【内容要求】抽取物的统一过闸流水线。

三道闸，顺序不能换：
  1. 去重      —— 生成任务，各次措辞不同，同一事实会重复
  2. 元描述闸  —— 关于课标文件本身的话不是学生能力（硬闸，prompt 只是软约束）
  3. 可判定闸  —— 走 scripts/decide.mjs，全线唯一实现
  4. 接地闸    —— 改写里的汉字 ≥62% 能在所引原文里找到

第 4 道是「改写」和「创作」的分界线。实测它拦下过「能说出司马迁撰写了
《史记》」—— 原文只写「司马迁与《史记》」，改写擅自添了「撰写」这个事实。
宁可严，漏掉的还能重抽；编进去的会一直留在库里当真话用。

    python3 tools/neirong_pipeline.py 历史 地理 …
"""
import json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from neirong_filter import is_meta, is_proposition  # noqa: E402

STOP = set('的了和与及或在中对能会把被为是有个之其等这那所以并且但')


def grounded(new, src, th=0.62):
    a = {c for c in new if '一' <= c <= '鿿'} - STOP
    b = {c for c in src if '一' <= c <= '鿿'}
    return (len(a & b) / len(a) if a else 0) >= th


def run(subject):
    f = ROOT / f'tools/out/{subject}-neirong.jsonl'
    if not f.exists():
        return None
    rows = [json.loads(l) for l in f.open(encoding='utf-8') if l.strip()]

    seen = {}
    for r in rows:
        stmt, src, stage = (list(r['value']) + ['', ''])[:3]
        if stmt and stmt not in seen:
            # 页码要带着走 —— 学段靠它兜底（课程内容按学段分块排，
            # 学段标题之后的页都属于那个学段）
            seen[stmt] = {'statement': stmt, 'srcText': src, 'stage': stage,
                          'page': r.get('page')}
    cand = list(seen.values())

    nometa = [c for c in cand if not is_meta(c['statement'])]

    payload = '\n'.join(json.dumps({'statement': c['statement'], 'discipline': subject},
                                   ensure_ascii=False) for c in nometa)
    r = subprocess.run(['node', str(ROOT / 'scripts/decide.mjs')], input=payload,
                       capture_output=True, text=True, check=True)
    res = [json.loads(l) for l in r.stdout.split('\n') if l.strip()]
    passed = [(c, x) for c, x in zip(nometa, res) if x['ok']]

    # 命题闸：见 neirong_filter.is_proposition 上方注释 —— 改写给了动词，
    # 可判定闸就拦不住主题式要求了，必须补这一道。
    prop = [(c, x) for c, x in passed if is_proposition(c['statement'])]

    final = []
    for c, x in prop:
        if grounded(c['statement'], c['srcText']):
            final.append({**c, 'verb': x['verb'], 'discipline': subject})

    out = ROOT / f'tools/out/{subject}-candidates.json'
    out.write_text(json.dumps(final, ensure_ascii=False), encoding='utf-8')
    return {
        'subject': subject, 'raw': len(rows), 'dedup': len(cand),
        'meta_dropped': len(cand) - len(nometa),
        'gate_passed': len(passed), 'proposition': len(prop), 'grounded': len(final),
    }


def main():
    subjects = sys.argv[1:] or ['历史', '道德与法治', '地理', '劳动', '生物学', '信息科技']
    print(f"{'学科':<12}{'原始':>6}{'去重':>6}{'滤元':>6}{'过闸':>6}{'命题':>6}{'接地':>6}  保留率")
    tot = 0
    for s in subjects:
        r = run(s)
        if not r:
            print(f"{s:<12}  （无抽取产物，跳过）"); continue
        tot += r['grounded']
        print(f"{s:<12}{r['raw']:>6}{r['dedup']:>6}{r['meta_dropped']:>6}"
              f"{r['gate_passed']:>6}{r['proposition']:>6}{r['grounded']:>6}"
              f"  {r['grounded']/r['dedup']:.0%}")
    print(f"{'合计可用候选':<12}{tot:>29}")


if __name__ == '__main__':
    main()
