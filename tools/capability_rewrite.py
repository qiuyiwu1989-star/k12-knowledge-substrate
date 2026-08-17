#!/usr/bin/env python3
"""
capability_rewrite.py — 把「知道 X」型知识锚点，转写成一条可判定的能力断言。

## 这一层和别处的根本区别

其余所有锚点都是**课标转述** —— 用的是课标自己的词，每条都能翻回教育部文件某一页。
这一层不是。课标写「知道中国传统工艺来自民间」，转写成「能举例说出中国传统工艺
的民间来源」——**「该不该把这条知识变成这条能力」是我们自己的教育判断**。

底座的全部价值在那条溯源链上。所以这一层必须能被一眼认出来、能被单独统计、
能被单独撤掉。六条闸由 validate.mjs 机器强制（selftest 逐条注入验证过）：

  1. 必须有 provenance.derivedFrom，指回源知识锚点
  2. method 不得标成 curriculum-content-rewrite（不许冒充课标转述）
  3. **永远够不到 auto-confirmed** —— 那档的含义是「判定客观、根本不需要人」，
     而这里恰恰全是需要人的教学判断
  4. 产物不得仍是 KNOWLEDGE 型（那就没转写）
  5. derivedFrom 必须指向活跃的 KNOWLEDGE 锚点，且同学科
  6. 有 derivedFrom 却不标 capability-rewrite 一律拦

## 为什么是新增，不是原地改

`undegrade.py` 是原地改 —— 那些是**修错**，源锚点本来就该长成那样。
这里是**新增** —— 源锚点没错，「知道 X」本身是课标的忠实转述，得留着。
新增的那条是我们在它之上的主张，两条并存，各自可查。

所以源锚点保持原样，新锚点 `derivedFrom` 指向它。

## 闸

  · 可判定性 —— scripts/lib/check-stdin.mjs（和 CI 同一个闸）
  · 归一 —— scripts/lib/normalize-stdin.mjs（跑到不动点）
  · 去重签名 —— 同学科下 (verb, object) 不得撞已有锚点
  · **接地不做** —— 转写本来就会偏离原文字面，那是这一层的定义。
    改用另一条：转写后的对象必须仍出现在原文里，防止换了话题。

    python3 tools/capability_rewrite.py --dry-run
    python3 tools/capability_rewrite.py --limit 20
    python3 tools/capability_rewrite.py
"""
import argparse, collections, json, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repair import call            # noqa: E402
from mint_py import load_used_ids, mint_id   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

SYS = """你是{disc}教研员。课标只要求学生「知道 / 了解」某个事实，
现在要在此之上写一条**可判定的能力断言** —— 一个具体孩子能被判定「会 / 不会」。

课标原文：{src}
现有的知识型锚点：{stmt}

这不是改写，是**在知识之上提出一条能力要求**。规则：

1. 能力必须**以这条知识为对象**，不许换话题。
   知识「中国传统工艺来自民间」→ ✅ 能举例说出中国传统工艺的民间来源
                              ❌ 能设计一件传统工艺作品（那是另一条能力，原文没要求）
2. 必须可判定：一个旁观者能看出他会不会。
   ❌ 能体会传统工艺的价值      ❌ 能形成文化认同
   ✅ 能举例说出两种中国民间传统工艺及其产地
3. 断言里**不许出现**「知道 / 了解 / 理解 / 认识 / 领会 / 体会 / 感受」——
   那些正是要摆脱的词。
4. 句式「能 + 可观察动词 + 明确对象」，10–40 字，顿号最多 2 个。
5. 不许添加原文没有的具体事实。可以要求学生「举例」，但不许你替他举例。
6. 证据 2 条，都是旁观者能看见的具体行为。
7. type 选 CONCEPTUAL / PROCEDURAL / REPRESENTATIONAL / LANGUAGE，不许 KNOWLEDGE。

写不出来就老实说写不出来 —— 有些知识确实没有对应的可判定能力，
硬凑出来的是假锚点，比没有更糟。

只输出一行 JSON，不要代码块：
{{"ok":true,"statement":"…","verb":"…","object":"…","type":"CONCEPTUAL","evidence":["…","…"],"why":"这条能力要求学生做什么"}}
{{"ok":false,"why":"「体会劳动的意义」这类没有可判定的能力形态"}}"""


def node_call(script, lines):
    p = subprocess.run(['node', str(ROOT / 'scripts/lib' / script)],
                       input='\n'.join(lines), capture_output=True, text=True, timeout=300)
    if p.returncode != 0:
        raise RuntimeError(f'{script}: {(p.stderr or "")[:200]}')
    out = [json.loads(l) for l in p.stdout.splitlines() if l.strip()]
    if len(out) != len(lines):
        raise RuntimeError(f'{script} 返回 {len(out)} 条，期望 {len(lines)}')
    return out


def content_chars(s):
    return {c for c in s if '一' <= c <= '鿿'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default=None)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--concurrency', type=int, default=10)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    base, key = os.environ['MIMO_BASE'], os.environ['MIMO_KEY']
    model = os.environ.get('MIMO_MODEL', 'mimo-v2.5')

    files = {f: [json.loads(l) for l in f.open(encoding='utf-8') if l.strip()]
             for f in sorted((ROOT / 'anchors').glob('*.jsonl'))}
    live = [x for arr in files.values() for x in arr if not x.get('deprecated')]

    # 已经转写过的不再转 —— 幂等，可以反复跑
    done_src = {(x.get('provenance') or {}).get('derivedFrom')
                for x in live if x.get('evidenceSource') == 'capability-rewrite'}
    targets = [x for x in live
               if x['type'] == 'KNOWLEDGE' and (x.get('provenance') or {}).get('srcText')
               and x['id'] not in done_src
               and (not a.only or x['discipline'] == a.only)]
    if a.limit:
        targets = targets[:a.limit]
    print(f"待转写 {len(targets)} 条（已转写过 {len(done_src)} 条，跳过）")

    sig = {(x['discipline'], x.get('verb'), x.get('object')) for x in live}

    def work(anc):
        src = anc['provenance']['srcText']
        try:
            raw = call(SYS.format(disc=anc['discipline'], src=src, stmt=anc['statement']),
                       '写。', base, key, model)
        except Exception as e:
            return anc, None, f'调用失败：{type(e).__name__}'
        m = re.search(r'\{.*\}', raw, re.S)
        if not m:
            return anc, None, '模型没吐 JSON'
        try:
            d = json.loads(m.group(0))
        except Exception:
            return anc, None, 'JSON 解析失败'
        if not d.get('ok'):
            return anc, None, '模型说写不出：' + str(d.get('why', ''))[:50]
        stmt = d.get('statement', '')
        if d.get('type') == 'KNOWLEDGE':
            return anc, None, '产物仍是 KNOWLEDGE'
        bad = [w for w in ('知道', '了解', '理解', '认识', '领会', '体会', '感受') if w in stmt]
        if bad:
            return anc, None, f'含不可判定认知词（{"/".join(bad)}）'
        # 换话题检测：转写后的对象必须和原文有实质重叠。
        # 接地校验在这一层不适用（转写本来就偏离字面），但「不许换话题」仍是硬约束。
        obj = d.get('object', '')
        ov = content_chars(obj) & content_chars(src)
        if obj and len(ov) / max(1, len(content_chars(obj))) < 0.45:
            return anc, None, f'对象与原文重叠仅 {len(ov)}/{len(content_chars(obj))} —— 疑似换了话题'
        return anc, d, None

    results = []
    with ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        for n, r in enumerate(ex.map(work, targets), 1):
            results.append(r)
            if n % 40 == 0:
                print(f"  …{n}/{len(targets)}")

    cand = [(anc, d) for anc, d, e in results if d]
    skipped = [(anc, e) for anc, d, e in results if not d]

    # 归一（到不动点），再过可判定闸 —— 闸检查的必须就是要落盘的字符串
    if cand:
        for field in ('statement', 'object'):
            norm = node_call('normalize-stdin.mjs',
                             [json.dumps({'text': d.get(field, ''), 'discipline': anc['discipline']},
                                         ensure_ascii=False) for anc, d in cand])
            for (anc, d), v in zip(cand, norm):
                d[field] = v
        verdicts = node_call('check-stdin.mjs', [d['statement'] for _, d in cand])
        kept = []
        for (anc, d), v in zip(cand, verdicts):
            if not v.get('ok'):
                skipped.append((anc, '不过可判定闸：' + '；'.join(v.get('reasons', []))[:60]))
                continue
            k = (anc['discipline'], d['verb'], d['object'])
            if k in sig:
                skipped.append((anc, f'去重签名冲突（{d["verb"]}/{d["object"][:20]}）'))
                continue
            sig.add(k)
            kept.append((anc, d))
    else:
        kept = []

    print(f"\n转写成功 {len(kept)} · 跳过 {len(skipped)}")
    for why, c in collections.Counter(e.split('（')[0].split('：')[0] for _, e in skipped).most_common(6):
        print(f"  {c:>4}  {why}")

    print("\n─── 样本 ───")
    for anc, d in kept[:6]:
        print(f"  原文：{anc['provenance']['srcText'].strip()[:56]}")
        print(f"  知识：{anc['statement'][:56]}")
        print(f"  能力：{d['statement'][:56]}  [{d['type']}]")
        print()

    if a.dry_run:
        print("（--dry-run：没有写盘）")
        return

    used = load_used_ids(ROOT)
    new_rows = collections.defaultdict(list)
    for anc, d in kept:
        new_rows[anc['discipline']].append({
            'id': mint_id(used), 'discipline': anc['discipline'], 'track': anc['track'],
            'strand': anc.get('strand'), 'topic': anc.get('topic'),
            'dimension': anc.get('dimension'),
            'statement': d['statement'], 'verb': d['verb'], 'object': d['object'],
            'type': d['type'], 'literacy': anc.get('literacy') or [],
            'cognitive': '应用' if d['type'] == 'PROCEDURAL' else '理解',
            'stageHint': anc.get('stageHint'),
            'courseType': anc.get('courseType'),
            'evidence': (d.get('evidence') or [])[:2] or [f"能就「{anc['object']}」举出具体例子"],
            'assessment': None,
            # ★ 这三个字段是这一层的全部身份。改动它们就等于抹掉分层。
            'evidenceSource': 'capability-rewrite',
            'reviewStatus': 'llm-proposed',
            'reviewedBy': [],
            'deprecated': False, 'supersededBy': None,
            'crosscutting': [], 'practice': [],
            'provenance': {
                'derivedFrom': anc['id'],
                'method': 'capability-rewrite',
                'why': d.get('why', ''),
                'srcSubject': (anc.get('provenance') or {}).get('srcSubject'),
                'srcPage': (anc.get('provenance') or {}).get('srcPage'),
                'srcText': (anc.get('provenance') or {}).get('srcText'),
            },
            'schemaVersion': '0.1.0',
        })

    n = 0
    for disc, rows in new_rows.items():
        f = ROOT / f'anchors/rewrite-{disc}.jsonl'
        old = [json.loads(l) for l in f.open(encoding='utf-8') if l.strip()] if f.exists() else []
        with f.open('w', encoding='utf-8') as fh:
            for r in old + rows:
                fh.write(json.dumps(r, ensure_ascii=False) + '\n')
        n += len(rows)
    print(f"已写 {n} 条 → anchors/rewrite-*.jsonl（{len(new_rows)} 个文件）")
    print("全部 evidenceSource=capability-rewrite · reviewStatus=llm-proposed")
    print("manifest 里会单列 rewrittenAnchors —— 说「N 条来自课标」时能一眼看出多少不是。")
    print("下一步：npm run check")


if __name__ == '__main__':
    main()
