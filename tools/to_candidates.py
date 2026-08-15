#!/usr/bin/env python3
"""
to_candidates.py — 把【学业要求】转写切分成候选锚点，过可判定性闸。

这是「切分」工序，和「转写」严格分开。它做三件事，都不做判断：
  1. 机械切分：课标的学业要求是分号分隔的复句，一个分句通常就是一条能力
  2. 过闸：调 scripts/decide.mjs（**过滤器只有这一份实现**，Python 侧不重写）
  3. 分流：过闸的进候选池（reviewStatus=llm-proposed），没过的进复核队列附拒绝理由

产出的一律是 `llm-proposed` —— 按底座规则，这类锚点**禁止被 L3 档案引用**，
必须由学科主编复核升级为 expert-confirmed 才能上生产。

  python3 tools/to_candidates.py [--only 数学]
"""
import argparse, collections, json, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / 'tools/out/xueye-raw.jsonl'

# 课标学业要求的典型形态：
#   「能用数表示物体的个数或事物的顺序，能认、读、写万以内的数；能说出不同数位上的数表示的数值；…」
# 分号是能力边界，逗号后若再起「能/会/可以」也是新能力边界。
# 分号是能力边界；逗号后若再起一个「能/会」或一个实义动词，也是能力边界。
# 只切「，能」太保守：实测「能…列出方程，理解方程的意义」这类复句切不开，
# 结果整句因「并列项过多」被闸门拒掉，白白丢一条真锚点。
_V = '能|会|可以|理解|掌握|知道|了解|说出|描述|解释|计算|比较|判断|运用|应用|设计|制作|识别|区分|归纳|分析'
# 无标点直接相接的两条也要切：「会计算能根据参照点的方向…」是两条断言被 OCR 粘在一起。
# 只在「实义动词短语 + 能/会 + 2字以上」这个格式下切，避免误伤「能会意」这类。
GLUE = re.compile(r'(?<=[一-龥]{2})(?=(?:能|会)(?:根据|用|在|通过|结合|借助|选择|利用|运用)[^，。；]{2,})')
SPLIT = re.compile(rf'[；;]|(?<=[，,])(?=(?:{_V})[^，。；]{{2,}})')
# 前导符号：课标正文里的项目符号、条目编号（如「·」「1-9」「(3)」）不属于断言本身
# 前导噪声。实测这几类都出现过：
#   「·能描述…」项目符号 / 「(6)能在…」括号编号 / 「1-9 能正确书写…」条目号
#   「）2.3 认识…」← 从「（家国情怀）2.3 认识…」切出来的碎片，孤立右括号 + 章节号
LEAD_NOISE = re.compile(
    r'^(?:[\s·•●○◇\-—]'          # 项目符号
    r'|[）)]'                     # 孤立右括号（切分残留）
    r'|[（(]\s*[^）)]{0,40}[）)]'  # 完整括号注（如「（家国情怀）」「（唯物史观、史料实证）」）
    r'|\d+(?:\.\d+)*\s*[-–.、)]'   # 章节号 2.3 / 1-9 / 1.
    r'|\d{1,2}(?=(?:列举|概述|举例|说明|描述|分析|比较|关注|注重|根据|理解|掌握|运用|设计|制作|能|会))'
    # ↑ 裸数字直接贴动词：「7列举人体的主要内分泌腺」。不能无脑剥前导数字，
    #   否则「2位数加法」「3个角」会被砍头；只在后面跟动词时才认。
    r')+\s*')
# 块标记漏进正文：转写时 @学业要求 偶尔被写成【学业要求】混在句首
BLOCK_MARK = re.compile(r'^【[^】]{2,8}】\s*')
# OCR 把公式吐成 LaTeX：$y=5x$ → y=5x
LATEX = re.compile(r'\$([^$]{1,30})\$')
TAIL_NOISE = re.compile(r'[，,]?(?:形成|发展|增强|提高|培养|感悟|体会|养成|逐步形成)[^，。；]*(?:意识|观念|能力|素养|精神|态度|习惯)。?$')

SUBJECT_MAP = {
    '00-课程方案': None, '01-道德与法治': '道德与法治', '02-语文': '语文', '03-历史': '历史',
    '04-数学': '数学', '05-英语': '英语', '06-日语': None, '07-俄语': None, '08-地理': '地理',
    '09-科学': '科学', '10-物理': '物理', '11-化学': '化学', '12-生物学': '生物学',
    '13-信息科技': '信息科技', '14-体育与健康': '体育与健康', '15-艺术': '艺术', '16-劳动': '劳动',
    # 直接用中文名命名的文件
    '数学': '数学', '语文': '语文', '英语': '英语', '历史': '历史', '地理': '地理', '科学': '科学',
    '物理': '物理', '化学': '化学', '生物学': '生物学', '信息科技': '信息科技', '劳动': '劳动',
    '艺术': '艺术', '体育与健康': '体育与健康', '道德与法治': '道德与法治', '方案': None,
}
STAGE_GRADE = {'第一学段': ('G1', 'G2'), '第二学段': ('G3', 'G4'),
               '第三学段': ('G5', 'G6'), '第四学段': ('G7', 'G9'), '全学段': ('G1', 'G9')}


# 2022 课标各科的核心素养词。它们出现在句首括号里是标签，不是能力本身。
LITERACY_WORDS = [
    '唯物史观', '时空观念', '史料实证', '历史解释', '家国情怀',
    '数感', '量感', '符号意识', '运算能力', '几何直观', '空间观念', '推理意识', '推理能力',
    '数据意识', '数据观念', '模型意识', '模型观念', '应用意识', '创新意识',
    '语言运用', '思维能力', '审美创造', '文化自信',
    '科学观念', '科学思维', '探究实践', '态度责任',
    '信息意识', '计算思维', '数字化学习与创新', '信息社会责任',
    '政治认同', '道德修养', '法治观念', '健全人格', '责任意识',
    '人地协调观', '综合思维', '区域认知', '地理实践力',
    '生命观念', '科学探究', '社会责任',
    '审美感知', '艺术表现', '创意实践', '文化理解',
    '运动能力', '健康行为', '体育品德',
    '劳动观念', '劳动能力', '劳动习惯和品质', '劳动精神',
]
LIT_RE = re.compile(r'^[（(]([^）)]{2,40})[）)]')


def strip_literacy(s):
    """剥离句首的核心素养标签括号，返回 (剩余文本, 素养列表)。"""
    m = LIT_RE.match(s.strip())
    if not m:
        return s, []
    inner = m.group(1)
    hits = [w for w in LITERACY_WORDS if w in inner]
    # 只有确实是素养标签才剥（否则「（例6）」这类括号会被误当标签）
    if not hits:
        return s, []
    return s[m.end():].strip(), hits


def split_sentence(s):
    s = s.strip().rstrip('。')
    parts = [q for p in SPLIT.split(s) if p for q in GLUE.split(p) if q and q.strip(' ，,。')]
    parts = [p.strip(' ，,。') for p in parts]
    out = []
    for p in parts:
        p = BLOCK_MARK.sub('', p)                      # 砍掉漏进来的【学业要求】块标记
        p = LATEX.sub(r'\1', p)                        # $y=5x$ → y=5x
        p = LEAD_NOISE.sub('', p)                      # 砍掉「·」「1-9」这类前导符号
        p = TAIL_NOISE.sub('', p).strip(' ，,。')       # 砍掉「…形成初步的数感和符号意识」这类口号尾巴
        if len(p) >= 6:
            out.append(p)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default=None)
    a = ap.parse_args()

    if not RAW.exists():
        sys.exit(f"缺少 {RAW}，先跑 tools/extract_xueye.py")
    rows = [json.loads(l) for l in RAW.open(encoding='utf-8')]
    rows = [r for r in rows if r['kind'] == 'sentence' and (not a.only or a.only in r['subject'])]

    cands = []
    for r in rows:
        disc = SUBJECT_MAP.get(r['subject'], r['subject'])
        if disc is None:
            continue
        text, lits = strip_literacy(r['text'])
        for frag in split_sentence(text):
            cands.append({
                'statement': frag, 'discipline': disc, 'literacy': lits,
                'srcSubject': r['subject'], 'srcPage': r['page'],
                'stage': r.get('stage') or '', 'domain': r.get('domain') or '',
                'srcAgree': r.get('agree'), 'srcText': r['text'],
            })
    print(f"转写句子 {len(rows)} → 机械切分候选 {len(cands)} 条（平均 {len(cands)/max(1,len(rows)):.1f} 条/句）")

    # ---- 过闸：唯一实现在 scripts/decide.mjs ----
    payload = '\n'.join(json.dumps(c, ensure_ascii=False) for c in cands)
    proc = subprocess.run(['node', str(ROOT / 'scripts/decide.mjs')], input=payload,
                          capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"decide.mjs 失败：{proc.stderr[:400]}")
    judged = [json.loads(l) for l in proc.stdout.split('\n') if l.strip()]

    passed = [j for j in judged if j['ok']]
    failed = [j for j in judged if not j['ok']]
    print(f"过可判定性闸: {len(passed)}/{len(judged)} = {len(passed)/max(1,len(judged)):.1%}")
    print("  被拒理由 Top:", dict(collections.Counter(
        r.split('：')[0] for j in failed for r in j['reasons']).most_common(6)))

    outdir = ROOT / 'tools/out'
    with (outdir / 'anchor-candidates.jsonl').open('w', encoding='utf-8') as f:
        for j in passed:
            lo, hi = STAGE_GRADE.get(j['stage'], (None, None))
            f.write(json.dumps({
                'statement': j['normalized'], 'discipline': j['discipline'],
                'literacy': j.get('literacy') or [],
                'verb': j['verb'], 'strand': j['domain'] or None,
                'stageHint': {'min': lo, 'max': hi} if lo else None,
                'reviewStatus': 'llm-proposed',
                'provenance': {'srcSubject': j['srcSubject'], 'srcPage': j['srcPage'],
                               'srcStage': j['stage'], 'srcAgree': j['srcAgree'],
                               'srcText': j['srcText'], 'method': 'vlm-transcribe+split'},
            }, ensure_ascii=False) + '\n')
    with (outdir / 'candidates-rejected.jsonl').open('w', encoding='utf-8') as f:
        for j in failed:
            f.write(json.dumps(j, ensure_ascii=False) + '\n')

    print(f"→ tools/out/anchor-candidates.jsonl（{len(passed)} 条，全部 llm-proposed，禁止被档案引用）")
    print(f"→ tools/out/candidates-rejected.jsonl（{len(failed)} 条，附拒绝理由，供改写或确认丢弃）")
    per = collections.Counter(j['discipline'] for j in passed)
    print("  按学科:", dict(per.most_common()))


if __name__ == '__main__':
    main()
