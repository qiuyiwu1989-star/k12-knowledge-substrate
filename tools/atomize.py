#!/usr/bin/env python3
"""
atomize.py — 判定锚点是不是**原子**，能机械拆的拆开。

## 原子的判据

> 如果对同一个孩子，可能出现「A 会、B 不会」，那 A 和 B 就是两个原子。

这不是新判据，是可判定性往下推一层：一个锚点只承载一个二值结论。
承载两个，档案里就会出现「半会」，而「半会」不是一个能记录的状态。

    能认、读、写万以内的数            读得出 3000 却写不出来是常态 → 三个原子
    会计算平行四边形、三角形、梯形的面积  三角形会梯形不会是常态       → 三个原子
    能说出直角、锐角、钝角的特征        一个概念族，一次判定         → 一个原子

## 为什么必须用模型，不能用正则

正则分不出「并列的是能力」和「并列的是同一个宾语内部的成分」：

    能知道南海诸岛、台湾及其附属岛屿是中国版图一部分   ← 顿号在宾语内部，一条
    能认、读、写万以内的数                        ← 顿号分开三个动词，三条

`undegrade.py` 在这上面栽过四轮正则（名动混淆、被动定语、教师主语、定语从句），
教训写在那个文件里：**模型判错，闸拦得住；正则判错，没有东西拦得住。**

## 拆分不是改写 —— 闸就设在这条界线上

这个项目立过「零模型调用、不改一个字」的规矩（见 docs/rewrite.md）。
拆分之所以不违反，是因为**拆出来的每一条都必须是原句的子串重组**：

    ✅ 能认、读、写万以内的数 → 能认万以内的数 ／ 能读万以内的数 ／ 能写万以内的数
    ❌ 能说出略读的目的是粗知文章大意          原文没有「目的是」，这是编的

五道闸，全是机械的：
  1. **不许新增实词** —— 拆出的汉字必须全部出现在原句里（和 make_assessment 同一道闸）
  2. **可判定** —— 每一条单独过 check-stdin.mjs
  3. **归一到不动点** —— 落盘的字符串必须就是过闸的那个字符串
  4. **去重签名** —— 同学科下 (verb, object) 不得撞已有锚点
  5. **不许留悬空指代** —— 「其／该／这／上述」在母条里有指代对象，拆出来就没有了：
     「…体裁、类别和表现形式，并运用所学知识分析**其**特点」拆开后，
     「运用所学知识分析其特点和表现作用」的「其」指向空气。
     validate.mjs 早有一条同类检查（管 assessment 的），这里是同一个道理。

## 拆出来的和母条是「组成」，不是「先修」

「会写 3000」不是「会读 3000」的后继 —— 它们没有先后。所以新增一种边
`composes`，母条由子条组成。硬塞进 prerequisite 会污染整张先修图。

## 召回边界（说在前面）

只把带复合信号的条目送去判（顿号／「并」／「和」／逗号后另起要求），
**没有任何标点信号的复合句判不出来**。这是有意的取舍：全量送判要多花一倍调用，
而无信号的复合句在实测样本里没见到。

    python3 tools/atomize.py --dry-run
    python3 tools/atomize.py --only 数学
    python3 tools/atomize.py
"""
import argparse, collections, json, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repair import call                        # noqa: E402
from mint_py import load_used_ids, mint_id     # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(__file__).parent / '.cache-atomize'

REQ = ('了解', '知道', '理解', '认识', '掌握', '会', '能', '运用', '应用', '说明', '解释',
       '描述', '分析', '比较', '判断', '设计', '制作', '操作', '探究', '计算', '测量',
       '表达', '交流', '评价', '举例', '列举', '识别', '归纳', '论证', '说出', '指出')

SYS = """你在审一份{disc}能力图谱。判断一条断言是**一个**能力还是**几个**能力粘在一起。

判据只有一条：

> 对同一个孩子，可不可能出现「前半个会、后半个不会」？
> 可能 → 是几条；不可能 → 是一条。

对照着看：

    能认、读、写万以内的数          读得出 3000 却写不出来很常见 → 三条
    会计算平行四边形、三角形、梯形的面积  三角形会、梯形不会很常见     → 三条
    能说出直角、锐角、钝角的特征       会认一个就会认另两个，一次判定 → 一条
    能知道南海诸岛、台湾及其附属岛屿是中国版图一部分
                                顿号在同一个宾语内部          → 一条
    能尝试利用录音、录像等手段记录社会的不同方面
                                「录音、录像」是手段的举例      → 一条

**并列成分在宾语内部的，一律算一条。** 只有并列的本身是不同的能力才算多条。

如果是多条，把它拆开。拆分有一条铁律：

> **只许用原句里已经有的字，一个新字都不许加。**

    ✅ 能认、读、写万以内的数 → ["能认万以内的数","能读万以内的数","能写万以内的数"]
    ❌ 加了原句没有的词（哪怕更通顺）—— 一律算失败，宁可返回拆不动

拆出来的每一条必须**自己站得住**：不许留「其／该／上述」这种指向母条的指代词。

    ❌ 「…体裁、类别和表现形式，并运用所学知识分析**其**特点」
       拆成「运用所学知识分析其特点」—— 「其」指向空气
    ✅ 拆成「能分析所听音乐的特点」—— 但前提是这些字原句里都有；没有就标 cant

拆开会丢掉条件的，不许拆：
    「能在具体情境中，理解比例尺的意义」—— 拆掉「在具体情境中」就变了要求 → 标 cant

只输出一行 JSON，不要代码块：
{{"verdict":"atom"}}
{{"verdict":"split","parts":["…","…"]}}
{{"verdict":"cant","why":"拆开会丢掉『通过实验』这个条件"}}"""


# 拆开之后会指向空气的指代词。母条里它们有着落，子条里没有。
DANGLING = re.compile(r'其[^他它中]|该[一-鿿]|上述|前者|后者|这一|这些|它们|此类')


def dangling(part, whole):
    """子条含指代词，且指代对象不在子条自己里 → 悬空。

    判据：指代词之前必须还有一个具名成分（引号、书名号、顿号并列，或至少 6 个汉字）。
    这和 validate.mjs 管 assessment 悬空指代用的是同一套判断。
    """
    m = DANGLING.search(part)
    if not m:
        return None
    before = part[:m.start()]
    if re.search(r"['‘’\"“”《》]|[^，。]、[^，。]", before):
        return None
    return m.group(0)[:2] if len(content_chars(before)) < 6 else None


def content_chars(s):
    return {c for c in s if '一' <= c <= '鿿'}


def node_call(script, lines):
    if not lines:
        return []
    p = subprocess.run(['node', str(ROOT / 'scripts/lib' / script)],
                       input='\n'.join(lines), capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        raise RuntimeError(f'{script}: {(p.stderr or "")[:200]}')
    out = [json.loads(l) for l in p.stdout.splitlines() if l.strip()]
    if len(out) != len(lines):
        raise RuntimeError(f'{script} 返回 {len(out)} 条，期望 {len(lines)}')
    return out


def compound_signal(s):
    """粗筛：有没有复合的标点信号。**只管召回，判断交给模型。**"""
    if '、' in s:
        return True
    if re.search(r'并(能|会|进行|说明|解释|运用|判断|表达|描述|用)', s):
        return True
    if any(seg.lstrip().startswith(v) for seg in re.split(r'(?<=，)', s)[1:] for v in REQ):
        return True
    return bool(re.search(r'[一-鿿]{2,}和[一-鿿]{2,}', s)) and len(s) >= 20


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default=None)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--concurrency', type=int, default=10)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    base, key = os.environ['MIMO_BASE'], os.environ['MIMO_KEY']
    model = os.environ.get('MIMO_MODEL', 'mimo-v2.5')
    CACHE.mkdir(exist_ok=True)

    files = {f: [json.loads(l) for l in f.open(encoding='utf-8') if l.strip()]
             for f in sorted((ROOT / 'anchors').glob('*.jsonl'))}
    live = [x for arr in files.values() for x in arr if not x.get('deprecated')]
    byid = {x['id']: x for x in live}

    # 已经拆过的不再拆 —— 幂等，可以反复跑
    done = {e['composedOf'] for e in load_edges() if e.get('kind') == 'composes'}
    targets = [x for x in live if compound_signal(x['statement'])
               and x['id'] not in done and (not a.only or x['discipline'] == a.only)]
    if a.limit:
        targets = targets[:a.limit]
    print(f"带复合信号 {len(targets)} / 存活 {len(live)}（已拆过 {len(done)} 条，跳过）")

    def work(anc):
        import hashlib
        sysp = SYS.format(disc=anc['discipline'])
        user = f"断言：{anc['statement']}\n课标原文：{(anc.get('provenance') or {}).get('srcText', '（无）')[:180]}"
        h = hashlib.sha256((sysp + user).encode()).hexdigest()[:24]
        cf = CACHE / f'{h}.json'
        if cf.exists():
            return anc, json.loads(cf.read_text(encoding='utf-8'))
        try:
            raw = call(sysp, user, base, key, model)
        except Exception as e:
            return anc, {'verdict': 'error', 'why': f'{type(e).__name__}'}
        m = re.search(r'\{.*\}', raw, re.S)
        try:
            d = json.loads(m.group(0)) if m else {'verdict': 'error', 'why': '没吐 JSON'}
        except Exception:
            d = {'verdict': 'error', 'why': 'JSON 解析失败'}
        cf.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
        return anc, d

    results = []
    with ThreadPoolExecutor(a.concurrency) as ex:
        for n, r in enumerate(ex.map(work, targets), 1):
            results.append(r)
            if n % 100 == 0:
                print(f'  …{n}/{len(targets)}', flush=True)

    verdicts = collections.Counter(d.get('verdict') for _, d in results)
    print('\n模型三分类：', dict(verdicts))

    # ── 闸 ──────────────────────────────────────────────────────────
    cand, rejected = [], collections.Counter()
    for anc, d in results:
        if d.get('verdict') != 'split':
            continue
        parts = [p for p in (d.get('parts') or []) if isinstance(p, str) and len(p) >= 6]
        if len(parts) < 2:
            rejected['拆出不足 2 条'] += 1
            continue
        src = content_chars(anc['statement'])
        extra = [p for p in parts if content_chars(p) - src]
        if extra:
            new = ''.join(sorted(content_chars(extra[0]) - src))
            rejected[f'新增了原句没有的字'] += 1
            continue
        dang = [(p, dangling(p, anc['statement'])) for p in parts]
        dang = [(p, d) for p, d in dang if d]
        if dang:
            rejected['拆出的条留下悬空指代'] += 1
            continue
        cand.append((anc, parts))

    # 归一到不动点 —— 落盘的字符串必须就是过闸的那个字符串
    flat = [(i, p) for i, (_, parts) in enumerate(cand) for p in parts]
    norm = node_call('normalize-stdin.mjs',
                     [json.dumps({'text': p, 'discipline': cand[i][0]['discipline']},
                                 ensure_ascii=False) for i, p in flat])
    again = node_call('normalize-stdin.mjs',
                      [json.dumps({'text': p, 'discipline': cand[i][0]['discipline']},
                                  ensure_ascii=False) for (i, _), p in zip(flat, norm)])
    if [x for x, y in zip(norm, again) if x != y]:
        sys.exit('归一不幂等，不敢往下走')
    grouped = collections.defaultdict(list)
    for (i, _), p in zip(flat, norm):
        grouped[i].append(p)

    # 可判定闸 + 去重签名
    checks = node_call('check-stdin.mjs', [p for i in sorted(grouped) for p in grouped[i]])
    it = iter(checks)
    sig = {(x['discipline'], x.get('verb'), x.get('object')) for x in live}
    kept = []
    for i in sorted(grouped):
        anc, parts = cand[i][0], grouped[i]
        vs = [next(it) for _ in parts]
        bad = [(p, v) for p, v in zip(parts, vs) if not v.get('ok')]
        if bad:
            rejected['拆出的条过不了可判定闸'] += 1
            continue
        rows, clash = [], False
        for p, v in zip(parts, vs):
            verb = v.get('verb') or ''
            j = p.find(verb)
            obj = (p[j + len(verb):].strip('，。；、 ') if j >= 0 else p)[:60] or p[:60]
            k = (anc['discipline'], verb, obj)
            if k in sig:
                clash = True
                break
            sig.add(k)
            rows.append((p, verb, obj, v))
        if clash:
            rejected['与已有锚点去重签名冲突'] += 1
            continue
        kept.append((anc, rows))

    print(f"\n过闸 {len(kept)} 条母锚点 → 拆出 {sum(len(r) for _, r in kept)} 条原子")
    for k, n in rejected.most_common():
        print(f'  拒 {n:>4}  {k}')

    print('\n─── 样本 ───')
    for anc, rows in kept[:6]:
        print(f"  母：{anc['discipline']} {anc['statement']}")
        for p, verb, obj, _ in rows:
            print(f"      → {p}")
        print()

    if a.dry_run:
        print('（--dry-run：没有写盘）')
        return
    write(files, kept)


def load_edges():
    out = []
    for f in sorted((ROOT / 'edges').glob('*.jsonl')):
        for l in f.open(encoding='utf-8'):
            if l.strip():
                out.append(json.loads(l))
    return out


FILE = {'数学': 'math', '语文': 'chinese', '英语': 'english', '物理': 'physics', '化学': 'chemistry',
        '生物学': 'biology', '历史': 'history', '地理': 'geography', '道德与法治': 'morality',
        '科学': 'science', '信息科技': 'infotech', '劳动': 'labor', '艺术': 'art', '体育与健康': 'pe'}


def write(files, kept):
    used = load_used_ids(ROOT)
    new_rows = collections.defaultdict(list)
    new_edges = collections.defaultdict(list)
    for anc, rows in kept:
        stem = FILE.get(anc['discipline'], f"gaozhong-{anc['discipline']}")
        for p, verb, obj, v in rows:
            nid = mint_id(used)
            child = {**{k: anc[k] for k in anc if k not in
                        ('id', 'statement', 'verb', 'object', 'reviewedBy', 'aiIssues',
                         'adjudication', 'independentCheck', 'autoConfirmBasis', 'triageBucket')},
                     'id': nid, 'statement': p, 'verb': verb, 'object': obj,
                     'reviewedBy': [],
                     # 拆出来的条**不继承母条的复核档** —— 母条被谁看过，
                     # 不等于拆出来的这条被看过。一律退回从没审过。
                     'reviewStatus': 'llm-proposed'}
            child['provenance'] = {**(anc.get('provenance') or {}), 'splitFrom': anc['id'],
                                   'method': 'atomize/substring-recombination'}
            new_rows[stem].append(child)
            new_edges[stem].append({'anchorId': anc['id'], 'composedOf': nid, 'kind': 'composes',
                                    'reason': f"母条「{anc['statement'][:24]}」由若干可分别判定的原子组成",
                                    'evidence': [{'kind': 'set-containment',
                                                  'detail': '子条文字全部来自母条原句，机器校验'}],
                                    'reviewStatus': 'llm-proposed', 'reviewedBy': [],
                                    'schemaVersion': '0.1.0'})
    for stem, rows in new_rows.items():
        with (ROOT / 'anchors' / f'{stem}.jsonl').open('a', encoding='utf-8') as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + '\n')
    for stem, rows in new_edges.items():
        with (ROOT / 'edges' / f'{stem}-composes.jsonl').open('a', encoding='utf-8') as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f'写入 {sum(len(v) for v in new_rows.values())} 条原子 + '
          f'{sum(len(v) for v in new_edges.values())} 条 composes 边')


if __name__ == '__main__':
    main()
