#!/usr/bin/env python3
"""
undegrade.py — 把被自己的抽取降级成「能说出 X」的锚点，按课标原文的动词改回去。

## 为什么要有这个工具

512 条 KNOWLEDGE 型锚点里 **505 条动词是「说出」**。那不是课标的语言，是我们
抽取流水线的模板。同口径实测：义务教育课标原文能力动词占 64%、高中 20 科平均
也是 64% —— **课标原文没有知识本位，是我们加上去的**。

最刺眼的样本：

    原文：能运用生活中的物品自制简易乐器，为歌曲伴奏或表现音乐情境。
    我们：能说出自制简易乐器所使用的材料是生活中的物品
          ↑ 一条动手能力，被削成了一道常识问答

根因是可判定性闸自己：闸要一个可判定动词，而「能说出 <名词> 是 <名词>」是最省力的
过闸方式，任何句子都能这么改且必定过闸。**闸把流水线逼向了问答题。**
完整分析见 docs/rewrite.md。

## 这个工具做什么、不做什么

**做**：原文里带着更强动词（运用/设计/制作/探究/计算/观察/分析…）**且第一个要求动词
不是「知道/了解」**的那 117 条，把断言改回原文的动词。这仍然是**课标转述** ——
用的是课标自己的词，所以「每条都能翻回教育部文件某一页」这条护城河不动。
实测 117 条里 75 条过了全部闸。

**顺带弃用**：18 条原文是面向教师的表述（教学重点/引导学生…），主语根本不是孩子。
「能说出『概览中外美术史』的教学重点是…」怎么改都不是儿童能力，只能弃用。

**不做**：原文第一个要求动词就是「知道 / 了解」的那些不在此列。把它们改成能力形态是
**我们自己的教育主张**，得走能力转写层（`evidenceSource: capability-rewrite`，
六条硬闸见 validate.mjs）。两件事不能混。

## 筛选规则是被样本打出来的，别简化它

初版用子串匹配数出「167 条被降级」，试跑立刻打脸 —— 三类假阳性：

  · **名词误判**：「环境设计的定义」里的「设计」、「传统工艺创作」里的「创作」
  · **被动定语**：「日常生活用品都是经过设计的」→ 被改成「能设计日常生活用品」
  · **主语是教师**：「教学重点是…设计单元教学活动」→ 孩子不设计单元教学

我为前两类写了三轮正则，每轮都被新样本打脸。最后靠一条更硬的判据解决：
**原文的第一个要求动词是什么，原文的要求就是什么**（`first_requirement`）。
一条挡住全部坏例，好例一个没伤。167 → 117。

## 三条设计决定

1. **原地改，不弃用重建。** ID 被档案当主键引用，换 ID 代价极大；
   仓库已有 128 条 `statementBefore` + `repair` 的先例，沿用。
2. **改完一律降级到 llm-proposed。** 断言实质变了，之前那次裁定
   （其中 34 条原是 ai-adjudicated）对新句子不成立。**不降级就是把「改过了」
   悄悄变成「审过了」** —— 那比不改更糟。可用锚点会因此下降，这是诚实的代价。
3. **端点触及被改锚点的边也降级。** 115 条边的一端含义变了，
   原先的先修判断得重新看。边不删，只降级留档。

## 闸

改写必须同时过三道，任何一道不过就跳过、留在原状：
  · 可判定性 —— scripts/lib/decidability.mjs（和 CI 同一个闸）
  · 接地校验 —— 字面覆盖率 ≥ 0.62，防止「修复」变成「创作」
  · 去重签名 —— 同学科下 (verb, object) 不得与已有锚点冲突

    python3 tools/undegrade.py --dry-run          # 只看会改成什么，不写盘
    python3 tools/undegrade.py --only 科学        # 单学科
    python3 tools/undegrade.py                    # 全量写盘
"""
import argparse, collections, glob, json, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repair import call, grounded, STOP   # noqa: E402  复用双端点调用与接地校验

ROOT = Path(__file__).resolve().parent.parent

# 原文里出现这些动词，说明课标本来要求的是「做」，不是「说出」。
# 分两档只为报告好读，处理逻辑一样 —— 都是「用原文的动词」。
STRONG = ['运用', '应用', '设计', '论证', '探究', '制作', '操作', '解决', '创作',
          '演奏', '演唱', '绘制', '测量', '计算', '书写', '朗读', '背诵']
MEDIUM = ['表达', '交流', '评述', '欣赏', '观察', '比较', '分析', '解释',
          '判断', '描述', '说明', '列举', '举例']
KNOW = ['知道', '了解', '理解', '认识', '感受', '体会']

SYS = """你是{disc}教研员。有一条能力断言被抽取流水线**削平**了：课标原文要求学生「做」某事，
而抽出来的断言只要求学生「说出」某个名词。你的任务是按原文的动词把它改回去。

课标原文：{src}
被削平的断言：{bad}
原文里的动词：{verbs}

规则（违反任何一条就算改失败）：
1. **必须用原文自己的动词**，不许换成同义词，也不许再退回「说出」。
2. 只能用原文里已有的信息。**不许添加原文没有的对象、条件、程度**。
   这是「修复」和「创作」的分界线 —— 加了原文没有的东西，就不再是课标转述了。
3. 改完必须能对一个具体孩子答「会 / 不会」：
   ❌ 感受音乐的美      ❌ 运用所学知识解决问题（「所学知识」指代不明）
   ✅ 能运用生活中的物品自制简易乐器      ✅ 能测量并记录一天中气温的变化
4. 句式「能 + 原文动词 + 明确对象」，8–40 字，顿号最多 2 个。
5. 指代词（这些/该/上述）换成具体所指，换不出来就是改不了。
6. 证据写 2 条，每条是旁观者**能看见的具体行为**。
7. type 从下面选一个：PROCEDURAL（动手做）/ CONCEPTUAL（说明解释）/
   REPRESENTATIONAL（画图列表等表征）/ LANGUAGE（语言运用）。**不许再是 KNOWLEDGE。**

只输出一行 JSON，不要代码块：
{{"ok":true,"statement":"…","verb":"…","object":"…","type":"PROCEDURAL","evidence":["…","…"],"why":"改了什么"}}
改不了就 {{"ok":false,"why":"原文虽有动词但主语是教师，不含学生能力"}}"""


TRIAGE = """你是{disc}教研员，正在审一条从课标里抽出来的能力断言。

课标原文：{src}
抽出来的断言：{bad}

先判断**课标原文对学生的要求到底是什么**，再决定怎么处理。三选一：

A. **要求学生做某事**（原文里有真正作谓语的行为动词）
   → 用原文自己的动词重写断言。
   ⚠️ 注意区分动词和名词：「我国目前使用的乐谱形式」里的「使用」是定语，
   「语言使用中」里的「使用」是名词，「环境设计的定义」里的「设计」是名词 ——
   这些都**不是**对学生的要求。
   ⚠️ 「探索」「合作」「参与」「尝试」这类过程词不是可判定产出。
   原文「探索并掌握等腰三角形判定定理」的产出是掌握定理，不是「能探索」。

B. **要求学生知道某事**（知道 / 了解 / 理解 / 认识，或原文是纯陈述句）
   → 不重写。这类要变成能力形态属于额外的教育主张，走另一条流程。

C. **原文的主语根本不是学生**（教学重点 / 教学建议 / 引导学生 / 与学生一起…）
   → 这条锚点该弃用，孩子的能力里没有这一项。

选 A 才重写，规则：
1. 必须用原文自己的动词，不许换同义词，不许退回「说出」。
2. 只能用原文已有的信息，**不许添加原文没有的对象、条件、程度**。
3. 断言里不许出现「知道/了解/理解/认识/领会/体会」。
4. 句式「能 + 动词 + 明确对象」，8–40 字，顿号最多 2 个，指代词换成具体所指。
5. 证据 2 条，都是旁观者能看见的具体行为。
6. type 选 PROCEDURAL / CONCEPTUAL / REPRESENTATIONAL / LANGUAGE，不许 KNOWLEDGE。

只输出一行 JSON，不要代码块：
A → {{"kind":"A","statement":"…","verb":"…","object":"…","type":"PROCEDURAL","evidence":["…","…"],"why":"…"}}
B → {{"kind":"B","why":"原文要求是『了解中国画的三远法』，属知识"}}
C → {{"kind":"C","why":"原文是教学建议，主语是教师"}}"""


def load_anchors():
    files = {}
    for f in sorted((ROOT / 'anchors').glob('*.jsonl')):
        files[f] = [json.loads(l) for l in f.open(encoding='utf-8') if l.strip()]
    return files


# ★ 子串匹配会把名词误判成动词。第一次统计说「93 条被降级」，试跑就打脸：
#   「了解环境设计的定义」里的「设计」是名词「环境设计」的一部分，
#   「继承与创新是传统工艺创作的重要原则」里的「创作」也是名词。
#   拿这些当「原文要求学生做」，模型就会凭空造出动手能力（实测接地掉到 0.67）。
#
# 两条判据：动词后面不能紧跟名词化后缀，前面得像个谓语位置。
NOUNIFY = re.compile(r'^(原则|方法|方式|能力|意识|观念|素养|过程|活动|作品|成果|者|类别|'
                     r'要素|定义|规律|思路|理念|技法|技能|水平|领域|环节|阶段|工具|手段)')
PREDICATE_LEAD = re.compile(r'[能会要需应][^，。；]{0,4}$|尝试$|学会$|初步$|^$|[，。；：、（(]$')


# 被动 / 定语用法：「经过设计的」「所使用的」「被观察的」——
# 动词在这里描述的是**对象的属性**，不是**要求学生做的事**。
# 试跑打脸样本：原文「日常生活用品都是经过设计的」被改成「能设计日常生活用品」。
# 课标只要求孩子知道东西是被设计出来的，从没要求他去设计。
PASSIVE_LEAD = re.compile(r'(经过|所|被|受|加以|得到|进行了)$')

# 面向教师的原文。这类**改也改不对** —— 主语是老师，不是孩子。
# 「『概览中外美术史』的教学重点是…设计单元教学活动」改成任何形式都不是儿童能力。
# 这些不进修复队列，进弃用队列。
TEACHER_SRC = re.compile(r'教学重点|教学建议|教学提示|教学策略|本学习任务|本任务|'
                         r'引导学生|组织学生|指导学生|鼓励学生|帮助学生|'
                         r'教师应|教师可|教师要|建议教师|可安排|应安排')


def verb_is_predicate(src, v):
    """v 在 src 里是不是真的作谓语（而不是名词的一部分、也不是被动定语）。"""
    for m in re.finditer(re.escape(v), src):
        tail = src[m.end():m.end() + 4]
        if NOUNIFY.match(tail):
            continue                      # 设计+原则 / 创作+原则 → 名词
        head = src[:m.start()]
        if PASSIVE_LEAD.search(head[-3:]):
            continue                      # 经过+设计+的 → 被动定语
        if tail[:1] == '的' and not tail[1:2]:
            continue                      # 结尾就是「…设计的」→ 定语
        # 谓语位置：句首、标点后、或前面是能/会/尝试/学会这类助动词
        if PREDICATE_LEAD.search(head[-6:]) or not head:
            return True
        # 「，运用形状、色彩…欣赏、评述」这类并列谓语
        if head.endswith(('，', '、', '；', '。')) or tail[:1] not in ('', '的'):
            return True
    return False


def first_requirement(src):
    """原文里第一个出现的「要求动词」。它决定这句话到底要求学生做什么。

    只看第一个，是因为课标句子里后半段常常出现别的动词，但那些是在描述对象
    （「日常生活用品都是经过设计的」）或者在列举内容，不是在提要求。
    """
    best, pos = None, len(src) + 1
    for v in KNOW + STRONG + MEDIUM:
        p = src.find(v)
        if 0 <= p < pos:
            best, pos = v, p
    return best


def pick_all_knowledge(files):
    """triage 模式：所有带原文的 KNOWLEDGE 锚点，**不做正则预筛**。

    为什么放弃正则预筛 —— 我为它打了四轮补丁，每轮都有新的假阳性：
      名词误判（环境设计的定义）→ 被动定语（都是经过设计的）→
      教师主语（与学生一起探索）→ 定语（我国目前使用的乐谱形式）
    每次收紧都漏掉真阳性，每次放宽都放进假阳性。**这是语法判断，正则做不了。**
    交给模型判断，三道机械闸（归一 / 可判定 / 接地 + 去重）当安全网 ——
    模型判错，闸拦得住；正则判错，没有东西拦得住。
    """
    out = []
    for f, arr in files.items():
        for i, a in enumerate(arr):
            if a.get('deprecated') or a.get('type') != 'KNOWLEDGE':
                continue
            if (a.get('provenance') or {}).get('srcText'):
                out.append((f, i, a, []))
    return out


def pick(files):
    """分两队：能修的（fix）和该弃用的（drop）。

    fix  —— type 是 KNOWLEDGE，原文里有真作谓语的更强动词
    drop —— 原文是面向教师的表述，主语根本不是孩子，改也改不对
    """
    fix, drop = [], []
    for f, arr in files.items():
        for i, a in enumerate(arr):
            if a.get('deprecated'):
                continue
            src = (a.get('provenance') or {}).get('srcText') or ''
            if not src:
                continue
            if TEACHER_SRC.search(src):
                drop.append((f, i, a))
                continue
            if a.get('type') != 'KNOWLEDGE':
                continue
            # ★ 最硬的一条判据，比上面那些正则可靠得多：
            #   **原文的第一个要求动词是什么，原文的要求就是什么。**
            #   「知道我们的生活离不开设计，日常生活用品都是经过设计的」——
            #   后面确实有「设计」，但要求是「知道」。改成「能设计日常生活用品」
            #   是凭空造能力（试跑真出过这条）。这类属于 135 条转写队列。
            #   写这条之前我拿正则猜了三轮语法，每轮都被新样本打脸；
            #   「看第一个动词」一条就把三个坏例全挡住了，而好例一个没伤。
            if first_requirement(src) in KNOW:
                continue
            vs = [v for v in STRONG if verb_is_predicate(src, v)] \
                or [v for v in MEDIUM if verb_is_predicate(src, v)]
            if vs:
                fix.append((f, i, a, vs))
    return fix, drop


def normalize_batch(items):
    """批量归一（scripts/lib/normalize-stdin.mjs）。items 是 [(text, discipline)]。

    第一次跑忘了这道，CI 当场报 60 处「未规范化」—— 模型爱吐全角引号和句末句号。
    归一规则只能有一份（scripts/lib/normalize.mjs），Python 侧不许自己再写。
    """
    if not items:
        return []
    inp = '\n'.join(json.dumps({'text': t, 'discipline': d}, ensure_ascii=False)
                     for t, d in items)
    p = subprocess.run(['node', str(ROOT / 'scripts/lib/normalize-stdin.mjs')],
                       input=inp, capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        raise RuntimeError('归一调用失败：' + (p.stderr or '')[:200])
    out = [json.loads(l) for l in p.stdout.splitlines() if l.strip()]
    if len(out) != len(items):
        raise RuntimeError(f'归一返回 {len(out)} 条，期望 {len(items)} 条')
    return out


def decidable_batch(stmts):
    """批量走 CI 用的同一个闸（scripts/lib/check-stdin.mjs）。

    刻意不在 Python 里重实现判定逻辑 —— 那必然和 CI 漂移，
    而漂移方向永远是「本地觉得能过、CI 说不行」，每次都白跑一整批。
    也刻意批量：167 条各起一个 node 进程要多花半分钟。
    """
    if not stmts:
        return []
    p = subprocess.run(['node', str(ROOT / 'scripts/lib/check-stdin.mjs')],
                       input='\n'.join(s.replace('\n', ' ') for s in stmts),
                       capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        raise RuntimeError('可判定闸调用失败：' + (p.stderr or '')[:200])
    out = [json.loads(l) for l in p.stdout.splitlines() if l.strip()]
    if len(out) != len(stmts):
        raise RuntimeError(f'闸返回 {len(out)} 条，期望 {len(stmts)} 条')
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default=None, help='只处理某个学科')
    ap.add_argument('--limit', type=int, default=0, help='只处理前 N 条（试跑用）')
    ap.add_argument('--concurrency', type=int, default=8)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--triage', action='store_true',
                    help='模型三分类（做/知道/教师主语）代替正则预筛，覆盖全部 KNOWLEDGE 锚点')
    a = ap.parse_args()

    base, key = os.environ['MIMO_BASE'], os.environ['MIMO_KEY']
    model = os.environ.get('MIMO_MODEL', 'mimo-v2.5')

    files = load_anchors()
    if a.triage:
        targets, droppable = pick_all_knowledge(files), []
    else:
        targets, droppable = pick(files)
    if a.only:
        droppable = [d for d in droppable if d[2]['discipline'] == a.only]
        targets = [t for t in targets if t[2]['discipline'] == a.only]
    if a.limit:
        targets = targets[:a.limit]

    kinds = collections.Counter('实做' if any(v in STRONG for v in vs) else '表现'
                                for _, _, _, vs in targets)
    print(f"待修 {len(targets)} 条（实做 {kinds['实做']} · 表现 {kinds['表现']}）")
    print(f"待弃用 {len(droppable)} 条（原文主语是教师，不是孩子 —— 改也改不对）")

    # 去重签名：同学科下 (verb, object) 不得撞车。**必须含未改的那些**，
    # 否则改出来的新句子可能和另一条已有锚点重复，CI 才报错，白跑一趟。
    sig = collections.defaultdict(set)
    for f, arr in files.items():
        for x in arr:
            if not x.get('deprecated'):
                sig[x['discipline']].add((x.get('verb'), x.get('object')))

    def work(t):
        f, i, anc, vs = t
        src = anc['provenance']['srcText']
        if a.triage:
            prompt = TRIAGE.format(disc=anc['discipline'], src=src, bad=anc['statement'])
        else:
            prompt = SYS.format(disc=anc['discipline'], src=src,
                                bad=anc['statement'], verbs=' / '.join(vs))
        try:
            raw = call(prompt, '改。', base, key, model)
        except Exception as e:
            return t, None, f'调用失败：{type(e).__name__}'
        m = re.search(r'\{.*\}', raw, re.S)
        if not m:
            return t, None, '模型没吐 JSON'
        try:
            d = json.loads(m.group(0))
        except Exception:
            return t, None, 'JSON 解析失败'
        if a.triage:
            k = d.get('kind')
            if k == 'B':
                return t, None, 'B·原文要求是知道 → 转写层'
            if k == 'C':
                return t, {'_deprecate': True, 'why': d.get('why', '')}, None
            if k != 'A':
                return t, None, f'模型返回未知 kind「{k}」'
            d['ok'] = True
        if not d.get('ok'):
            return t, None, '模型判定改不了：' + str(d.get('why', ''))[:60]

        stmt, verb, obj = d.get('statement', ''), d.get('verb', ''), d.get('object', '')
        if d.get('type') == 'KNOWLEDGE':
            return t, None, '改完仍是 KNOWLEDGE'
        if verb == '说出':
            return t, None, '又退回了「说出」'
        if vs and not any(v in stmt for v in vs):
            return t, None, f'没用原文动词（{"/".join(vs)}）'
        if not vs and verb and verb not in src:
            # triage 模式没有预筛出的动词表，就直接查模型给的动词在不在原文里 ——
            # 不在原文里，就说明它换了词或者自己编了一个
            return t, None, f'动词「{verb}」不在原文里'
        # 试跑实测：模型会把原文的「了解 / 领会」整句抄进断言 ——
        # 「能观察学习与生活用品，了解『实用与美观相结合』的设计原则」。
        # 它靠前半句的「观察」过了闸，后半句仍然不可判定。半句可判定不算可判定。
        bad = [w for w in ('知道', '了解', '理解', '认识', '领会', '体会', '感受', '懂得') if w in stmt]
        if bad:
            return t, None, f'改写里仍含不可判定认知词（{"/".join(bad)}）'
        g_ok, g = grounded(stmt, src)
        if not g_ok:
            return t, None, f'接地不足 {g:.2f}'
        if (verb, obj) in sig[anc['discipline']]:
            return t, None, f'去重签名冲突（{verb}/{obj}）'
        d['_grounding'] = round(g, 2)
        return t, d, None

    results = []
    with ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        for n, r in enumerate(ex.map(work, targets), 1):
            results.append(r)
            if n % 20 == 0:
                print(f"  …{n}/{len(targets)}")

    # triage 判 C 的直接进弃用队列，不进改写流程
    for t, d, e in results:
        if d and d.get('_deprecate'):
            droppable.append((t[0], t[1], t[2]))
    cand = [(t, d) for t, d, e in results if d and not d.get('_deprecate')]

    # ★ 归一必须在可判定闸**之前** —— 闸看的是最终要写盘的那个字符串。
    #   先过闸再归一，等于闸检查的和落盘的不是一个东西。
    flat, slots = [], []
    for t, d in cand:
        disc = t[2]['discipline']
        for k in ('statement', 'object', 'verb'):
            if isinstance(d.get(k), str) and d[k]:
                flat.append((d[k], disc)); slots.append((d, k))
        for i2, ev in enumerate(d.get('evidence') or []):
            flat.append((ev, disc)); slots.append((d, ('evidence', i2)))
    for (d, k), new in zip(slots, normalize_batch(flat)):
        if isinstance(k, tuple):
            d['evidence'][k[1]] = new
        else:
            d[k] = new

    # 可判定闸放在最后批量过 —— 一次 node 进程，不是 167 次
    verdicts = decidable_batch([d['statement'] for _, d in cand])
    fixed, gate_fail = [], []
    for (t, d), v in zip(cand, verdicts):
        if v.get('ok'):
            fixed.append((t, d))
        else:
            gate_fail.append((t, '不过可判定闸：' + '；'.join(v.get('reasons', []))[:70]))

    skipped = [(t, e) for t, d, e in results if not d] + gate_fail

    # 新句子之间也可能互撞（同一批里两条改出同样的 verb/object）
    seen, dedup = set(), []
    for t, d in fixed:
        k = (t[2]['discipline'], d['verb'], d['object'])
        if k in seen:
            skipped.append((t, f'与同批另一条撞签名（{d["verb"]}/{d["object"]}）'))
            continue
        seen.add(k); dedup.append((t, d))
    fixed = dedup
    print(f"\n改成功 {len(fixed)} · 跳过 {len(skipped)}")
    print("跳过原因：")
    for why, c in collections.Counter(e.split('（')[0].split('：')[0] for _, e in skipped).most_common():
        print(f"  {c:>4}  {why}")

    print("\n─── 样本（前 8 条）───")
    for (f, i, anc, vs), d in fixed[:8]:
        print(f"  原文：{anc['provenance']['srcText'].strip()[:58]}")
        print(f"  旧  ：{anc['statement'][:58]}")
        print(f"  新  ：{d['statement'][:58]}   [{d.get('type')}·接地{d['_grounding']}]")
        print()

    if a.dry_run:
        print("（--dry-run：没有写盘）")
        return

    # 写盘：原地改，留审计。同时降级 —— 断言变了，旧裁定不再成立。
    changed_ids = set()
    for (f, i, anc, vs), d in fixed:
        arr = files[f]
        old = arr[i]
        old_stmt = old['statement']
        old['statementBefore'] = old_stmt
        old['statement'] = d['statement']
        old['verb'] = d['verb']
        old['object'] = d['object']
        old['type'] = d['type']
        if d.get('evidence'):
            old['evidence'] = d['evidence'][:2]
        old['repair'] = {'kind': 'undegrade', 'why': d.get('why', ''),
                         'grounding': d['_grounding'], 'srcVerbs': vs}
        # ★ 必须降级。不降级就是把「改过了」悄悄变成「审过了」。
        old['reviewStatus'] = 'llm-proposed'
        old['reviewedBy'] = []
        changed_ids.add(old['id'])

    # 主语错位的一律弃用留档。留档而非删除 —— 当初为什么收进来，得查得到。
    for f, i, anc in droppable:
        x = files[f][i]
        x['deprecated'] = True
        x['dropReason'] = ('原文是面向教师的表述（教学重点/教学建议/引导学生…），'
                           '主语不是学生，抽成儿童能力锚点属主语错位')
        changed_ids.add(x['id'])

    for f, arr in files.items():
        with f.open('w', encoding='utf-8') as fh:
            for x in arr:
                fh.write(json.dumps(x, ensure_ascii=False) + '\n')

    # 端点含义变了的边也降级留档
    ed = 0
    for ef in sorted(glob.glob(str(ROOT / 'edges/*.jsonl'))):
        arr = [json.loads(l) for l in open(ef, encoding='utf-8') if l.strip()]
        hit = False
        for e in arr:
            if e['anchorId'] in changed_ids or e['prerequisiteId'] in changed_ids:
                if e.get('reviewStatus') != 'llm-proposed':
                    e['reviewStatus'] = 'llm-proposed'
                    e['reviewedBy'] = []
                e['note'] = '端点断言已按课标原文动词修正，先修判断需重看'
                ed += 1
                hit = True
        if hit:
            with open(ef, 'w', encoding='utf-8') as fh:
                for e in arr:
                    fh.write(json.dumps(e, ensure_ascii=False) + '\n')

    print(f"\n已写盘：改 {len(fixed)} 条（降级为 llm-proposed）· 弃用 {len(droppable)} 条主语错位"
          f" · 标记 {ed} 条边需重看")
    print("下一步：npm run check")


if __name__ == '__main__':
    main()
