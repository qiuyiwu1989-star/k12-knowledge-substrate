#!/usr/bin/env python3
"""
gaozhong_rewrite.py — 高中的能力转写层。决策见 DECISIONS.md 2026-09-28（邱懿武选「全部 20 科」）。

## 为什么

高中锚点按「不改写，只筛」落库（gaozhong_commit.py）：拆句，只收原样就能过可判定闸的。
「了解盖斯定律及其简单应用」「掌握平面向量数乘运算」这类知识型要求过不了闸，整句没进库。
映射基准里高中的缺口（椭圆、中心法则、联合国的作用、财政）全在这里。
义教早有能力转写层（capability_rewrite.py），高中没有 —— 这个工具补上。

## 每一句产出两条锚点

  · **源锚点**（原句层）：断言就是那句分句，一字不改；type=KNOWLEDGE；reviewStatus=disputed、
    挂 undecidable（「原句层」）—— **不可引用**，它的作用是让转写有据可查
  · **转写锚点**：能力断言，evidenceSource/method = capability-rewrite，provenance.derivedFrom 指向源锚点。
    过了全部闸和复审才是 ai-reviewed

转写没过就两条都不落 —— 不留孤零零的原句层。

## 闸（顺序即执行顺序）

  1. 候选：高中抽取产物里，被可判定闸以「无可观察行为动词」「了解后面不是具体事实」拒掉的分句；
     10–60 字；滤掉乱码（PDF 数学字体的私用区字符、「犪犿狀」这类错位编码）和表头残片
  2. 转写（DeepSeek）：capability_rewrite.SYS 同一份规则，另要一句家长问句
  3. 机械闸：不许仍是 KNOWLEDGE；不许含「知道 / 了解 / 理解…」；
     **话题闸按分句比**：转写断言与分句至少共享 2 个实义二字词 ——
     试跑里「研究三角函数的周期性」被写成「举出对数函数图象」、「知道质能关系」被写成「时空观的差异」，
     原工具按整条原文比对，全放过了
  4. 归一 → 可判定闸 → 去重签名（全部问 scripts/lib/ 的 node 脚本，不在 Python 里再写一遍）
  5. 复审（豆包 Seed 2.0 Pro —— 与转写不是同一家模型）：
     a. ai_review 同一份提示词挑问题；stage 异议按课标学段裁决（高中一律 G10–G12，doc_stage）
     b. 忠实度：这条能力是不是仍在要求原句那件事、有没有加原文没有的事实
     两问都过才落库

    LLM_BASE=… LLM_KEY=… LLM_ENDPOINT=/chat/completions python3 tools/gaozhong_rewrite.py --limit 60
    … python3 tools/gaozhong_rewrite.py --write
"""
import sys
sys.dont_write_bytecode = True

import argparse, collections, hashlib, json, os, re, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import gaozhong_commit as G                        # noqa: E402  拆句、清洗、node 调用、认知层级
import capability_rewrite as C                     # noqa: E402  转写规则
from ai_review import SYS as REVIEW, OPEN_AT       # noqa: E402
from repair import call                            # noqa: E402
from mint_py import load_used_ids, mint_id         # noqa: E402
from doc_stage import split_stage_issues           # noqa: E402

CACHE = TOOLS / 'out' / '.cache-gzrw'
LOG = TOOLS / 'out' / 'gaozhong-rewrite-log.jsonl'
REWRITER = 'deepseek-v4-1-flash-260910'
REVIEWER = 'doubao-seed-2-0-pro-260215'

# PDF 数学字体抽出来的错位编码（犪=a、犿=m、狀=n…）和私用区字符：出现即整句不可信
GARBLE = re.compile('[-犪犫犮犱犲犳犵犺犻犼犽犾犿狀狅狆狇狉狊狋狌狏狑狓狔狕]')
# 表头 / 标签残片：「能表 2 学业质量水平…」「能续表课程级别…」「能（一）学业质量内涵…」「能所涉及的…包括：」
FRAGMENT = re.compile(r'^能(续?表\s*\d|续表|（[一二三四五六]）|\d+\s*[\.．、]|[\d\s]+级|所涉及|本系列|本模块|通过本模块'
                      r'|如[：:，,]|例如|比如)'
                      r'|[:：]$|学业质量水平|课程级别|课程类型')
# 分句必须**是一条要求**：含至少一个要求动词；不含「学生 / 教师」（那是教学活动的描写，不是对孩子的要求）。
# 全量试跑抽 40 条人工看，7 条可疑几乎全是这类源句：「学生通过观察东市和西市示意图」
# 「汴河穿城而过，三重城垣都与水道相连」「田径类运动系列包括…」—— 转写本身没错，错在源句不是要求
REQ_VERB = re.compile('了解|理解|认识|知道|掌握|懂得|学会|领会|体会|感受|感悟|体验|探讨|探究|阐明|阐述|简述|评述|评价|'
                      '关注|树立|形成|运用|应用|辨析|辨别|分析|说明|比较|概述|描述|识别|区分|熟悉|明确|'
                      '计算|求|判断|撰写|阅读|介绍|列举|举例|解释|归纳|概括|表达|理清|梳理|收集|绘制|设计')
TEACHING = re.compile('学生|教师|老师|引导|组织学生')
COG = ('了解', '理解', '掌握', '认识', '知道', '领会', '体会', '感受', '懂得', '学会', '能够', '能', '初步',
       '进一步', '基本', '主要', '相关', '有关', '一定', '简单', '常见', '的', '和', '与', '及', '等')

EXTRA = """
8. 另写一句**给家长照着念的问句**，用 {{{{name}}}} 指代孩子，不超过 40 字，口语化，放在 "assessment" 字段。
   例：{{{{name}}}}，你能用盖斯定律把这两个反应的焓变加出来吗？"""

FIDELITY = """你在核对一条「能力转写」是否忠实。

课标原句：{clause}
（所在段落：{src}）
转写后的能力：{stmt}

只问两件事：
1. 这条能力要求的，是不是**仍然是原句说的那件事**？（换了话题 = 不是，比如原句讲三角函数、转写讲对数函数）
2. 转写有没有**加进原文没有的具体事实**？（要求学生「举例」可以；替学生给出原文没有的具体内容不行）

只输出一行 JSON：{{"same": true/false, "addsFacts": true/false, "why": "一句话"}}"""


def verb_object(s):
    """源句层的 verb / object。取第一个**当谓语用**的要求动词：后面不紧跟「的」、且剩下的对象 ≥2 字。
    （「集合的…」「辨别的…」里那个词是定语；validate 会拦，签名也会跟着错）"""
    for m in REQ_VERB.finditer(s, 1):
        rest = s[m.end():].strip(' ，,。；')
        if not s[m.end():m.end() + 1] == '的' and len(rest) >= 2:
            return m.group(0), rest
    return s[1:3], s[3:].strip(' ，,。；') or s[1:]


def bigrams(s):
    t = ''.join(c for c in s if '一' <= c <= '鿿')
    for w in COG:
        t = t.replace(w, '|')
    return {t[i:i + 2] for i in range(len(t) - 1) if '|' not in t[i:i + 2]}


def candidates(only=None, source='gaozhong', covered=None):
    raw = []
    if source == 'history':
        # 义教历史：扫描件 OCR 出的【内容要求】段落（tools/out/yijiao-历史-ocr.jsonl）。
        # 每段是一串「通过…，了解…；…」—— 几乎全是知识型，过闸的也走转写（统一出证据和问句）
        # 用校对过的版本（子 agent 对照扫描页逐字校：繁菜→繁荣、张睿→张謇、力强盛→国力强盛 等 8 处）
        for l in open(ROOT / 'tools/out/yijiao-历史-ocr.proofed.jsonl', encoding='utf-8'):
            raw.append(json.loads(l))
    for d in (('gaozhong', 'gaozhong2') if source == 'gaozhong' else ()):
        for f in sorted((ROOT / 'tools/out' / d).glob('*.jsonl')):
            if f.stem == 'warnings':
                continue
            for l in open(f, encoding='utf-8'):
                if l.strip():
                    r = json.loads(l)
                    if r['section'] in G.SECTIONS and (not only or r['subject'] == only):
                        raw.append(r)
    cand = []
    for r in raw:
        base = G.clean(r['text'])
        if G.head_truncated(r):
            base, _ = G.strip_truncated_head(base, r.get('topicName') or '')
        for s in G.split_reqs(base):
            cand.append((r, G.ensure_neng(s)))
    norm = G.node_call('normalize-stdin.mjs', [json.dumps({'text': s, 'discipline': r['subject']}, ensure_ascii=False)
                                               for r, s in cand])
    cand = [(r, n) for (r, _), n in zip(cand, norm)]
    v = G.node_call('check-stdin.mjs', [s for _, s in cand])
    seen, out, stat = set(), [], collections.Counter()
    for (r, s), vv in zip(cand, v):
        if source == 'gaozhong':
            if vv.get('ok') or not vv.get('reasons'):
                continue
            if vv['reasons'][0].split('：')[0] not in ('无可观察行为动词', '「了解」后面不是具体事实'):
                continue
        elif covered and covered(s):
            stat['已有锚点覆盖'] += 1
            continue
        key = (r['subject'], s)
        if key in seen:
            continue
        seen.add(key)
        if not (10 <= len(s) <= 60):
            stat['长度不在 10–60'] += 1
        elif GARBLE.search(s) or GARBLE.search(r['text']):
            stat['乱码（数学字体错位编码）'] += 1
        elif FRAGMENT.search(s):
            stat['表头 / 标签残片'] += 1
        elif TEACHING.search(s):
            stat['教学活动描写（含学生 / 教师）'] += 1
        elif not REQ_VERB.search(s[1:]):
            stat['没有要求动词（描述 / 目录 / 残片）'] += 1
        else:
            out.append((r, s))
    return out, stat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--only', default=None)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--concurrency', type=int, default=10)
    ap.add_argument('--source', default='gaozhong', choices=['gaozhong', 'history'],
                    help='history = 义教历史（OCR 的内容要求段落），学段 G7–G9')
    a = ap.parse_args()
    HS = a.source == 'gaozhong'
    STAGE = ('G10', 'G12') if HS else ('G7', 'G9')
    base, key = os.environ['LLM_BASE'], os.environ['LLM_KEY']
    CACHE.mkdir(exist_ok=True)

    files = {f: [json.loads(l) for l in f.read_text(encoding='utf-8').splitlines() if l.strip()]
             for f in sorted((ROOT / 'anchors').glob('*.jsonl'))}
    live = [x for rows in files.values() for x in rows if not x.get('deprecated')]
    have = {(x['discipline'], x['statement']) for rows in files.values() for x in rows}   # 已有源句 → 跳过（可重跑）

    covered = None
    if not HS:
        # 已被现有锚点覆盖的分句跳过：分句的实义二字词有一半以上出现在某条在用历史锚点的原句 / 断言里
        pool = [bigrams((x.get('provenance') or {}).get('srcText', '') + x['statement'])
                for x in live if x['discipline'] == '历史' and x['stageHint']['min'] in ('G7', 'G8', 'G9')]
        def covered(s):
            b = bigrams(s)
            return bool(b) and any(len(b & p) / len(b) >= 0.5 for p in pool)
    cand, pre = candidates(a.only, a.source, covered)
    cand = [(r, s) for r, s in cand if (r['subject'], s) not in have]
    if a.limit:
        import random
        random.Random(20260928).shuffle(cand)
        cand = cand[:a.limit]
    print(f'候选 {len(cand)} 句  （预滤：{dict(pre)}）', flush=True)

    def ask(model, sysp, user, tag):
        h = hashlib.sha256((model + tag + sysp + user).encode()).hexdigest()[:24]
        cf = CACHE / f'{h}.json'
        if cf.exists():
            return json.loads(cf.read_text(encoding='utf-8'))
        for _ in range(3):
            try:
                txt = call(sysp, user, base, key, model)
            except Exception as e:
                return {'error': str(e)[:60]}
            m = re.search(r'\{.*\}', txt or '', re.S)
            try:
                o = json.loads(m.group(0)) if m else None
            except Exception:
                o = None
            if isinstance(o, dict):
                cf.write_text(json.dumps(o, ensure_ascii=False), encoding='utf-8')
                return o
        return {'error': '解析失败'}

    def rewrite(item):
        r, s = item
        d = ask(REWRITER, C.SYS.format(disc=r['subject'], src=r['text'][:260], stmt=s + '（原句层，没过可判定闸）') + EXTRA,
                '写。', 'rw')
        if d.get('error'):
            return item, None, '转写调用失败'
        if not d.get('ok'):
            return item, None, '模型说写不出'
        st = d.get('statement', '')
        if d.get('type') == 'KNOWLEDGE':
            return item, None, '仍是 KNOWLEDGE'
        if any(w in st for w in ('知道', '了解', '理解', '认识', '领会', '体会', '感受')):
            return item, None, '含不可判定认知词'
        if len(bigrams(st) & bigrams(s)) < 2:
            return item, None, '话题闸：与分句共享实义词不足 2 个'
        if '{{name}}' not in (d.get('assessment') or ''):
            return item, None, '家长问句缺 {{name}}'
        return item, d, None

    stat = collections.Counter()
    with ThreadPoolExecutor(a.concurrency) as ex:
        res = list(ex.map(rewrite, cand))
    ok = []
    for item, d, e in res:
        if e:
            stat[f'✗ {e}'] += 1
        else:
            ok.append((item, d))
    # 归一 → 可判定闸 → 去重签名（与在册锚点、与本批彼此）
    if ok:
        for field in ('statement', 'object'):
            norm = G.node_call('normalize-stdin.mjs', [json.dumps({'text': d.get(field, ''), 'discipline': it[0]['subject']},
                                                                  ensure_ascii=False) for it, d in ok])
            for (it, d), n in zip(ok, norm):
                d[field] = n
        vs = G.node_call('check-stdin.mjs', [d['statement'] for _, d in ok])
        used_sig = set(G.node_call('signature-stdin.mjs', [json.dumps(x, ensure_ascii=False) for x in live], raw=True))
        sigs = G.node_call('signature-stdin.mjs', [json.dumps({'discipline': it[0]['subject'], 'verb': v.get('verb') or d.get('verb'),
                                                               'statement': d['statement']}, ensure_ascii=False)
                                                   for (it, d), v in zip(ok, vs)], raw=True)
        ok2 = []
        for (it, d), v, sg in zip(ok, vs, sigs):
            if not v.get('ok'):
                stat['✗ 转写后过不了可判定闸'] += 1
            elif sg in used_sig:
                stat['✗ 去重签名撞了已有锚点'] += 1
            else:
                used_sig.add(sg)
                d['verb'] = v.get('verb') or d.get('verb')
                ok2.append((it, d))
        ok = ok2

    def review(pair):
        (r, s), d = pair
        disc = r['subject']
        lo, hi = OPEN_AT[disc]
        user = (f"能力断言：{d['statement']}\n领域：未标注\n标注学段：{STAGE[0]}–{STAGE[1]}\n"
                f"掌握证据：{' / '.join((d.get('evidence') or [])[:3]) or '（无）'}\n已标的直接前置：（无）\n"
                f"来源：{disc}课标 第 {r.get('page', '?')} 页")
        o = ask(REVIEWER, REVIEW.format(disc=disc, open_at=f'{lo}–{hi} 年级'), user, 'rv')
        if o.get('error') or not isinstance(o.get('issues'), list):
            return pair, '复审调用失败', None
        iss = [x for x in o['issues'] if isinstance(x, dict) and x.get('type')]
        iss, _, _ = split_stage_issues({'provenance': {'srcStage': '' if HS else '第四学段'}, 'discipline': disc,
                                        'stageHint': {'min': STAGE[0], 'max': STAGE[1]}},
                                       'gaozhong-x.jsonl' if HS else 'history.jsonl', iss)
        if iss:
            return pair, '复审挑出问题（' + '、'.join(sorted({x['type'] for x in iss})) + '）', iss
        f = ask(REVIEWER, FIDELITY.format(clause=s, src=r['text'][:200], stmt=d['statement']), '判。', 'fd')
        if f.get('error'):
            return pair, '忠实度调用失败', None
        if not f.get('same') or f.get('addsFacts'):
            return pair, '忠实度：' + ('换了话题' if not f.get('same') else '加了原文没有的事实'), f
        return pair, None, None

    with ThreadPoolExecutor(a.concurrency) as ex:
        rev = list(ex.map(review, ok))
    kept, log = [], []
    for pair, why, det in rev:
        (r, s), d = pair
        log.append({'subject': r['subject'], 'page': r.get('page'), 'clause': s, 'statement': d['statement'],
                    'verdict': why or 'ok', 'detail': det})
        if why:
            stat[f'✗ {why}'] += 1
        else:
            kept.append(pair)
    stat['✓ 落库'] = len(kept)
    for k, n in sorted(stat.items(), key=lambda t: -t[1]):
        print(f'  {n:>5}  {k}')
    by = collections.Counter(r['subject'] for (r, _), _ in kept)
    print('  按学科：', dict(by.most_common()))
    for (r, s), d in kept[:8]:
        print(f"    [{r['subject']}] {s[:30]}\n        → {d['statement']}")
    LOG.write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in log), encoding='utf-8')
    if not a.write:
        print(f'（没写盘；明细 {LOG.relative_to(ROOT)}；加 --write 写回）')
        return

    used = load_used_ids(ROOT)
    today = time.strftime('%Y-%m-%d')
    rw_by = f'ai:{REWRITER.rsplit("-", 1)[0]}-{today}'
    rv_by = f'ai:{REVIEWER.rsplit("-", 1)[0]}-{today}'
    add = collections.defaultdict(list)
    for (r, s), d in kept:
        disc = r['subject']
        track = 'DAG' if disc in G.DAG_SUBJECTS else 'MATRIX'
        prov = {'srcSubject': disc, 'srcPage': int(r['page']) if str(r.get('page', '')).isdigit() else None,
                'srcText': r['text'], 'srcCourse': r.get('course'), 'srcCourseNo': r.get('courseNo') or '',
                'srcSection': r['section']}
        if not HS:
            prov['srcStage'] = '第四学段'
            prov['srcTopic'] = r.get('topicName')
        prov = {k: v for k, v in prov.items() if v is not None}
        v0, obj0 = verb_object(s)
        src_id, rw_id = mint_id(used), mint_id(used)
        add[f'gaozhong-{disc}.jsonl' if HS else 'history.jsonl'].append({
            'id': src_id, 'discipline': disc, 'track': track, 'strand': None, 'topic': None, 'dimension': None,
            'statement': s, 'verb': v0, 'object': obj0,
            'type': 'KNOWLEDGE', 'literacy': [], 'cognitive': G.cognitive_of(s),
            'stageHint': {'min': STAGE[0], 'max': STAGE[1]}, 'courseType': r.get('course'),
            # schema 要求证据至少 1 条。源句本身给不出「怎么看出他会了」，借用转写的证据
            # （那正是「这条知识怎么看得见」），标 evidence-drafted，不冒充课标来源
            'evidence': (d.get('evidence') or [])[:3], 'evidenceSource': 'evidence-drafted',
            'reviewStatus': 'disputed',
            'reviewedBy': [], 'deprecated': False, 'supersededBy': None,
            'aiIssues': [{'type': 'undecidable', 'by': 'rule:gaozhong-rewrite',
                          'detail': '原句层：课标原句，过不了可判定闸（知识型要求）。可判定的能力版本见由它转写的子条'}],
            'provenance': {**prov, 'method': 'gaozhong-textlayer-split' if HS else 'ocr-vision-split'},
            'schemaVersion': '0.1.0'})
        add[f'gaozhong-rewrite-{disc}.jsonl' if HS else f'rewrite-{disc}.jsonl'].append({
            'id': rw_id, 'discipline': disc, 'track': track, 'strand': None, 'topic': None, 'dimension': None,
            'statement': d['statement'], 'verb': d['verb'], 'object': d.get('object') or '',
            'type': d.get('type') or 'CONCEPTUAL', 'literacy': [], 'cognitive': G.cognitive_of(d['statement']),
            'stageHint': {'min': STAGE[0], 'max': STAGE[1]}, 'courseType': r.get('course'),
            'evidence': (d.get('evidence') or [])[:3], 'assessment': d['assessment'],
            'evidenceSource': 'capability-rewrite', 'reviewStatus': 'ai-reviewed',
            'reviewedBy': [rw_by, rv_by], 'deprecated': False, 'supersededBy': None,
            'provenance': {**prov, 'derivedFrom': src_id, 'method': 'capability-rewrite',
                           'why': str(d.get('why') or '')[:120]},
            'schemaVersion': '0.1.0'})
    for name, rows in add.items():
        p = ROOT / 'anchors' / name
        old = p.read_text(encoding='utf-8') if p.exists() else ''
        p.write_text(old + ''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in rows), encoding='utf-8')
    print(f'已写回：源锚点 {len(kept)} 条 + 转写 {len(kept)} 条，分到 {len(add)} 个文件')


if __name__ == '__main__':
    main()
