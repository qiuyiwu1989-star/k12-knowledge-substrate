#!/usr/bin/env python3
"""
gaozhong_commit.py — 把 tools/out/gaozhong/ 的抽取结果落成 anchors/。

## 一条核心决定：**不改写，只筛**

义务教育那批栽在改写上：可判定闸要一个可判定动词，流水线就找了最省力的
「能说出 <名词> 是 <名词>」，把 93 条动手能力削成了常识问答（见 docs/rewrite.md）。
根因不是模型笨，是**只要允许改写，就存在一条比忠实更省力的过闸路径**。

所以这里的规则是：**拆句，然后只留原样就能过闸的**。不调模型，不改一个字。
过不了闸的不硬凑，进 candidates/ 等人看。代价是产出少，收益是**没有一条是编的**。

## 拆句

一个条目常含两三条要求：

    1.1.1 了解近代实验科学产生的背景，认识实验对物理学发展的推动作用。
          → 「了解近代实验科学产生的背景」 + 「认识实验对物理学发展的推动作用」

按句末标点和「，+ 要求动词」切。**不跨句拼、不补主语、不换动词。**

## 学段与课程类型

高中课标**按模块给内容，不按年级**。所以 stageHint 一律 G10–G12，
真实区分放在 `courseType`（必修 / 选择性必修 / 选修）上。

**不要发明年级精度。** 「必修 1 就是高一」是教学惯例，不是课标条文 ——
那正是 Marble「4–15 岁逐岁」的毛病：发明出来的精度看着专业，实际是假的。

    python3 tools/gaozhong_commit.py --dry-run
    python3 tools/gaozhong_commit.py --only 物理
    python3 tools/gaozhong_commit.py
"""
import argparse, collections, json, re, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mint_py import load_used_ids, mint_id          # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'tools/out/gaozhong'

# 高中课标里 DAG 档只给这三科 —— 和义务教育一致。其余走 MATRIX。
# LIST 档是清单覆盖模型（字表词表篇目），高中课标没有这种东西。
DAG_SUBJECTS = {'数学', '物理', '化学'}

# 认知层级：从课标自己的动词读，不猜。
COGNITIVE_MAP = [
    (['运用', '应用', '设计', '论证', '解决', '制作', '创作', '评价'], '应用'),
    (['掌握', '会', '能'], '掌握'),
    (['理解', '认识', '说明', '解释', '分析', '比较'], '理解'),
    (['了解', '知道', '感受', '体会', '初步'], '了解'),
]

# 标签粘连：英语等科把课程类型和分类标签粘在句首
# （「选择性必修理解性技能1. 区分、分析和概括语篇中的主要观点」）。
LABEL_LEAD = re.compile(
    r'^(选择性必修|选修|必修)?\s*'
    r'(理解性技能|表达性技能|元认知策略|认知策略|交际策略|情感管理策略|资源策略|'
    r'语言知识|文化知识|学习策略|语言技能|主题|语篇|听|说|读|写|译|看)*\s*'
    r'(\d+\s*[.．、]\s*)?')

# 要求动词。用来判断「，」之后是不是新的一条要求。
REQ_VERB = ('了解', '知道', '理解', '认识', '掌握', '会', '能', '运用', '应用',
            '说明', '解释', '描述', '分析', '比较', '判断', '设计', '制作',
            '操作', '探究', '计算', '测量', '表达', '交流', '评价', '举例',
            '列举', '识别', '归纳', '论证', '感受', '体会', '说出', '指出')


def clean(text):
    """去掉粘在句首的课程类型和分类标签。只削句首，不动内容。"""
    prev = None
    while prev != text:
        prev = text
        text = LABEL_LEAD.sub('', text, count=1).lstrip('：:，、 ')
    return text.strip()


def split_reqs(text):
    """把一个条目拆成若干条要求。**只切，不补、不改。**

    两级：先按句末标点切，再看「，」后面是不是接着一个要求动词。
    「，」后接要求动词说明是并列的另一条要求（「了解 A，认识 B」）；
    不接就是同一条要求的成分（「通过实验，了解 A」）—— 那种不能切开，
    切开就丢了「通过实验」这个条件。
    """
    out = []
    for sent in re.split(r'(?<=[。？！；])', text):
        sent = sent.strip()
        if not sent:
            continue
        # 「，」后紧跟要求动词 → 并列要求，切；否则保留整句
        parts, buf = [], ''
        for seg in re.split(r'(?<=，)', sent):
            if buf and any(seg.lstrip().startswith(v) for v in REQ_VERB):
                parts.append(buf); buf = seg
            else:
                buf += seg
        if buf:
            parts.append(buf)
        for p in parts:
            p = p.strip().strip('，；')
            if len(p) >= 8:
                out.append(p)
    return out


# 断言必须以这些词起头。**这是碎片过滤器**：抽取阶段的跨页截断会留下
# 「赛的基本规则，并能够在比赛中遵守规则」这种从半个词开始的句子（实测真出过），
# 而它照样能过可判定闸 —— 闸看的是有没有动词，不看开头是否完整。
GOOD_OPENER = REQ_VERB + (
    '能', '会', '通过', '根据', '在', '用', '利用', '结合', '尝试', '初步',
    '正确', '独立', '主动', '积极', '进一步', '学会', '熟悉', '关注', '养成',
    '选择', '收集', '整理', '观察', '发现', '完成', '参与', '合作', '遵守',
    '针对', '围绕', '以', '从', '对', '把', '将', '借助')


def opener_ok(s):
    return any(s.startswith(w) for w in GOOD_OPENER)


def ensure_neng(s):
    """补「能」前缀。仓库里现有锚点一律是「能 + 动词 + 对象」，句式统一了，
    家长向问句才能机械生成。**这是加前缀，不是改写** —— 一个字不动原文语义。"""
    if s.startswith(('能', '会')):
        return s
    return '能' + s


def cognitive_of(s):
    for verbs, level in COGNITIVE_MAP:
        if any(v in s for v in verbs):
            return level
    return '了解'


def node_call(script, payload_lines):
    p = subprocess.run(['node', str(ROOT / 'scripts/lib' / script)],
                       input='\n'.join(payload_lines), capture_output=True,
                       text=True, timeout=300)
    if p.returncode != 0:
        raise RuntimeError(f'{script} 失败：{(p.stderr or "")[:200]}')
    return [json.loads(l) for l in p.stdout.splitlines() if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default=None)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    files = sorted(SRC.glob('*.jsonl'))
    if not files:
        sys.exit('没有抽取结果。先跑 python3 tools/gaozhong_extract.py')

    raw = []
    for f in files:
        if f.stem == 'warnings':
            continue
        for l in f.open(encoding='utf-8'):
            if l.strip():
                r = json.loads(l)
                if r['section'] == '内容要求' and (not a.only or r['subject'] == a.only):
                    raw.append(r)
    print(f"读入 {len(raw)} 条内容要求（{len({r['subject'] for r in raw})} 科）")

    # 拆句
    cand, frag_drop = [], []
    for r in raw:
        base = clean(r['text'])
        for s in split_reqs(base):
            if not opener_ok(s):
                frag_drop.append(s)
                continue
            cand.append({'src': r, 'statement': ensure_neng(s)})
    print(f"拆成 {len(cand)} 条候选（另丢弃 {len(frag_drop)} 条开头不完整的碎片）")
    if frag_drop:
        print("    碎片样本：" + ' ／ '.join(x[:22] for x in frag_drop[:3]))

    # 归一（必须在过闸之前 —— 闸检查的必须就是要落盘的字符串）
    norm = node_call('normalize-stdin.mjs',
                     [json.dumps({'text': c['statement'], 'discipline': c['src']['subject']},
                                 ensure_ascii=False) for c in cand])
    if len(norm) != len(cand):
        sys.exit(f'归一返回 {len(norm)} 条，期望 {len(cand)} 条 —— 对齐坏了，不敢往下走')
    changed = 0
    for c, n in zip(cand, norm):
        if n != c['statement']:
            changed += 1
        c['statement'] = n
    print(f"  归一改动 {changed} 条")
    # 二次核对：归一必须是幂等的。不核对，就会像第一次那样把带尾空格的句子写进库，
    # 等 CI 报「未规范化」才发现 —— 而那时已经铸了 494 个 ID。
    again = node_call('normalize-stdin.mjs',
                      [json.dumps({'text': c['statement'], 'discipline': c['src']['subject']},
                                  ensure_ascii=False) for c in cand])
    bad = [(c['statement'], g) for c, g in zip(cand, again) if g != c['statement']]
    if bad:
        sys.exit(f'归一不幂等，{len(bad)} 条：{bad[:2]}')

    # 可判定闸
    verdicts = node_call('check-stdin.mjs', [c['statement'] for c in cand])
    passed, rejected = [], collections.Counter()
    for c, v in zip(cand, verdicts):
        if v.get('ok'):
            c['verb'] = v.get('verb')
            passed.append(c)
        else:
            rejected[(v.get('reasons') or ['?'])[0].split('：')[0]] += 1
    print(f"过可判定闸 {len(passed)} / {len(cand)} = {len(passed)/max(1,len(cand))*100:.0f}%")
    for k, n in rejected.most_common(6):
        print(f"    拒 {n:>4}  {k}")

    # 去重：同学科下 (verb, object) 不得重复。object 取动词之后的部分。
    used_sig = set()
    for f in sorted((ROOT / 'anchors').glob('*.jsonl')):
        for l in f.open(encoding='utf-8'):
            if l.strip():
                x = json.loads(l)
                if not x.get('deprecated'):
                    used_sig.add((x['discipline'], x.get('verb'), x.get('object')))
    kept, dup = [], 0
    for c in passed:
        verb = c['verb']
        i = c['statement'].find(verb)
        obj = c['statement'][i + len(verb):].strip('，。；、 ') if i >= 0 else c['statement']
        obj = obj[:60] or c['statement'][:60]
        sig = (c['src']['subject'], verb, obj)
        if sig in used_sig:
            dup += 1
            continue
        used_sig.add(sig)
        c['object'] = obj
        kept.append(c)
    print(f"去重后 {len(kept)}（撞签名丢弃 {dup}）")

    by_subj = collections.Counter(c['src']['subject'] for c in kept)
    by_course = collections.Counter(c['src'].get('course') or '未标' for c in kept)
    print(f"\n学科分布：{dict(by_subj.most_common())}")
    print(f"课程类型：{dict(by_course)}")

    print("\n─── 样本 ───")
    for c in kept[:6]:
        s = c['src']
        print(f"  [{s['subject']}·{s.get('course') or '?'}] {s.get('code') or '-'} p{s['page']}")
        print(f"    {c['statement']}")

    if a.dry_run:
        print("\n（--dry-run：没有写盘）")
        return

    used = load_used_ids(ROOT)
    rows = []
    for c in kept:
        s = c['src']
        subj = s['subject']
        rows.append({
            'id': mint_id(used), 'discipline': subj,
            'track': 'DAG' if subj in DAG_SUBJECTS else 'MATRIX',
            'strand': s.get('topicName'), 'topic': s.get('topicName'),
            'dimension': None,
            'statement': c['statement'], 'verb': c['verb'], 'object': c['object'],
            'type': 'KNOWLEDGE' if cognitive_of(c['statement']) == '了解' else 'CONCEPTUAL',
            'literacy': [], 'cognitive': cognitive_of(c['statement']),
            # 高中课标按模块给内容，不按年级。**不发明年级精度。**
            'stageHint': {'min': 'G10', 'max': 'G12'},
            'courseType': s.get('course'),
            'evidence': ([s['examples'][0]] if s.get('examples') else
                         [f"能在{subj}课堂或作业情境中完成：{c['statement'][:40]}"]),
            'assessment': None,
            'evidenceSource': 'curriculum-content-gaozhong',
            'reviewStatus': 'llm-proposed',      # 无人看过。不是 llm 生成，但也没人复核
            'reviewedBy': [], 'deprecated': False, 'supersededBy': None,
            'crosscutting': [], 'practice': [],
            'provenance': {
                'srcSubject': subj, 'srcPage': s['page'],
                'srcCode': s.get('code'), 'srcTopic': s.get('topicName'),
                'srcCourse': s.get('course'), 'srcCourseNo': s.get('courseNo'),
                'srcText': s['text'],
                'method': 'gaozhong-textlayer-split',
            },
            'schemaVersion': '0.1.0',
        })

    # 按学科分文件写。**追加到 anchors/gaozhong-<学科>.jsonl**，
    # 不混进义务教育的文件 —— 两份课标是两个来源，分开才查得清。
    n = 0
    for subj in sorted({r['discipline'] for r in rows}):
        f = ROOT / f'anchors/gaozhong-{subj}.jsonl'
        with f.open('w', encoding='utf-8') as fh:
            for r in rows:
                if r['discipline'] == subj:
                    fh.write(json.dumps(r, ensure_ascii=False) + '\n'); n += 1
    print(f"\n已写 {n} 条 → anchors/gaozhong-*.jsonl（{len({r['discipline'] for r in rows})} 个文件）")
    print("全部 reviewStatus=llm-proposed —— 无人看过，不计入 usableAnchors。")
    print("下一步：npm run check")


if __name__ == '__main__':
    main()
