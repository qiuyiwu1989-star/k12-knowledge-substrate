#!/usr/bin/env python3
"""
tag_literacy.py — 给锚点填核心素养（literacy）与 MATRIX 的 dimension。

## 这两个字段是同一件事

实测库里 `dimension` 的取值就是核心素养（科学观念 / 运动能力 / 审美感知…）。
MATRIX 档的结构是「能力维度 × 主题」，那个「维度」指的正是核心素养。
分成两个字段是历史遗留 —— **本工具一次填两个，取值必须一致**，
否则同一条锚点在两处说法不同，join 就废了。

## 为什么敢让 AI 直接落盘

和横切打标同级：**封闭词表分类**，取值只能来自 `mappings/literacy.json`
（义务教育沿用库中已按 2022 版课标填的，高中逐科摘自课标「学科核心素养」正文）。
模型自造的一律丢弃。

错误代价也在同一量级：先修边打错会把孩子往错方向推；
核心素养打错最坏只是分类不准，不影响任何判定。

## topic 不在这里填

`topic`（主题）是内容归属，不是能力维度。高中的 topic 抽取时就从课标
主题名带过来了；义务教育缺的那些要靠复核补 —— 机器猜主题会造出
课标里根本不存在的主题名，那比空着更糟。

    python3 tools/tag_literacy.py --dry-run
    python3 tools/tag_literacy.py --only 物理
    python3 tools/tag_literacy.py
"""
import argparse, collections, json, os, re, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repair import call        # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
VOCAB = json.loads((ROOT / 'mappings/literacy.json').read_text(encoding='utf-8'))['disciplines']

SYS = """你是{disc}教研员。给下面这条能力断言标注它主要发展哪一项**学科核心素养**。

断言：{stmt}

只能从这份清单里选（这是{disc}课标列出的全部核心素养）：
{opts}

规则：
1. 选 1 项；确实同等重要才选 2 项。**宁少勿多。**
2. **不许自造**清单以外的名称，一个字都不能改。
3. 判据是「这条能力主要在练哪一项素养」，不是「它涉及哪些素养」——
   涉及往往是全部，那样标等于没标。
4. 实在判断不出就返回空数组，不要硬凑。

只输出一行 JSON：{{"lit":["…"],"why":"一句话"}}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default=None)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--concurrency', type=int, default=12)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    base, key = os.environ['MIMO_BASE'], os.environ['MIMO_KEY']
    model = os.environ.get('MIMO_MODEL', 'mimo-v2.5')

    files = {f: [json.loads(l) for l in f.open(encoding='utf-8') if l.strip()]
             for f in sorted((ROOT / 'anchors').glob('*.jsonl'))}
    targets = [(f, i, x) for f, arr in files.items() for i, x in enumerate(arr)
               if not x.get('deprecated')
               and (not x.get('literacy') or (x['track'] == 'MATRIX' and not x.get('dimension')))
               and x['discipline'] in VOCAB
               and (not a.only or x['discipline'] == a.only)]
    if a.limit:
        targets = targets[:a.limit]
    print(f"待标 {len(targets)} 条")
    print(f"  {dict(collections.Counter(x['discipline'] for _, _, x in targets).most_common(6))}")

    def work(t):
        f, i, x = t
        vals = VOCAB[x['discipline']]['values']
        opts = '\n'.join(f'  · {v}' for v in vals)
        try:
            raw = call(SYS.format(disc=x['discipline'], stmt=x['statement'], opts=opts),
                       '标。', base, key, model)
        except Exception as e:
            return t, None, f'调用失败：{type(e).__name__}'
        m = re.search(r'\{.*\}', raw, re.S)
        if not m:
            return t, None, '没吐 JSON'
        try:
            lit = json.loads(m.group(0)).get('lit') or []
        except Exception:
            return t, None, 'JSON 解析失败'
        # ★ 封闭词表的意义全在这一句：模型自造的一律丢弃，不做模糊匹配。
        #   做了模糊匹配就等于允许自造 —— 「科学思维能力」会被匹到「科学思维」，
        #   下次又冒出「科学性思维」，词表就烂了。
        keep = [v for v in lit if v in vals][:2]
        if not keep:
            return t, None, ('自造了词表外的值' if lit else '模型判断不出')
        return t, keep, None

    results = []
    with ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        for n, r in enumerate(ex.map(work, targets), 1):
            results.append(r)
            if n % 200 == 0:
                print(f"  …{n}/{len(targets)}")

    ok = [(t, v) for t, v, e in results if v]
    bad = [(t, e) for t, v, e in results if not v]
    print(f"\n成功 {len(ok)} · 跳过 {len(bad)}")
    for why, c in collections.Counter(e.split('：')[0] for _, e in bad).most_common(5):
        print(f"  {c:>4}  {why}")
    dist = collections.Counter(v for _, vs in ok for v in vs)
    print(f"\n素养分布（前 10）：")
    for k, c in dist.most_common(10):
        print(f"  {k:<22} {c}")
    print("\n─── 样本 ───")
    for (f, i, x), v in ok[:5]:
        print(f"  [{x['discipline']}] {x['statement'][:46]}")
        print(f"     → {v}")

    if a.dry_run:
        print("\n（--dry-run：没有写盘）")
        return
    for (f, i, x), v in ok:
        rec = files[f][i]
        rec['literacy'] = v
        # dimension 与 literacy 同源：MATRIX 的「能力维度」就是核心素养。
        # 只填主项 —— dimension 是单值，取第一个。
        if rec['track'] == 'MATRIX' and not rec.get('dimension'):
            rec['dimension'] = v[0]
    for f, arr in files.items():
        with f.open('w', encoding='utf-8') as fh:
            for x in arr:
                fh.write(json.dumps(x, ensure_ascii=False) + '\n')
    print(f"\n已写 {len(ok)} 条（literacy + MATRIX 的 dimension）")
    print("下一步：npm run check")


if __name__ == '__main__':
    main()
