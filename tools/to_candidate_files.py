#!/usr/bin/env python3
"""
to_candidate_files.py — 把过闸的候选落成 candidates/<学科>.jsonl，并铸 ID。

**候选不是锚点。** 它们没有 evidence、没有 assessment、没经任何人复核。
硬塞进 anchors/ 等于假装完成了，所以单独一层：
  candidates/  —— 有 ID、过了可判定性闸、可被引用讨论，但**禁止被 L3 档案引用**
  anchors/     —— 学科主编复核并补齐 evidence 后才搬进来

ID 在候选阶段就铸定：复核只是升级状态、补齐字段，不换 ID，
这样复核过程中的讨论、issue、PR 都能稳定指向同一条。
"""
import collections, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from mint_py import load_used_ids, mint_id   # noqa: E402

SRC = ROOT / 'tools/out/anchor-candidates.jsonl'

# 档位：统一的是 ID 空间，不是数据结构。硬把所有学科塞进一张先修图必产垃圾边。
TRACK = {
    '数学': 'DAG', '物理': 'DAG', '化学': 'DAG',
    '语文': 'LIST', '英语': 'LIST',
    '科学': 'MATRIX', '生物学': 'MATRIX', '历史': 'MATRIX', '地理': 'MATRIX',
    '道德与法治': 'MATRIX', '信息科技': 'MATRIX', '劳动': 'MATRIX',
    '艺术': 'MATRIX', '体育与健康': 'MATRIX',
}
FILE = {'数学': 'math', '语文': 'chinese', '英语': 'english', '物理': 'physics', '化学': 'chemistry',
        '生物学': 'biology', '历史': 'history', '地理': 'geography', '道德与法治': 'morality',
        '科学': 'science', '信息科技': 'infotech', '劳动': 'labor', '艺术': 'art',
        '体育与健康': 'pe'}

# 动词 → 锚点类型。是启发式，复核时会改；先给一个不离谱的默认值。
PROCEDURAL = {'计算', '口算', '笔算', '心算', '演算', '估算', '换算', '测量', '称量', '求解', '化简',
              '制作', '搭建', '组装', '拆装', '连接', '操作', '演示', '绘制', '画出', '书写', '默写',
              '演奏', '演唱', '表演', '仿写', '临摹', '投掷', '传接', '运球', '起跳', '游泳', '滚翻'}
REPRESENTATIONAL = {'标出', '标注', '圈出', '连线', '补全', '填出', '列出', '呈现', '表示'}
LANGUAGE = {'朗读', '诵读', '默读', '跟读', '认读', '拼读', '组词', '造句', '摘抄', '翻译', '听写'}
META = {'反思', '评价', '规划', '监控', '调节'}


def infer_type(verb, statement):
    if verb in PROCEDURAL:
        return 'PROCEDURAL'
    if verb in REPRESENTATIONAL:
        return 'REPRESENTATIONAL'
    if verb in LANGUAGE:
        return 'LANGUAGE'
    if verb in META:
        return 'META'
    return 'CONCEPTUAL'


def infer_cognitive(statement):
    for w, c in [('熟练', '应用'), ('运用', '应用'), ('应用', '应用'), ('解决', '应用'),
                 ('说明', '理解'), ('解释', '理解'), ('描述', '理解'), ('比较', '理解'),
                 ('说出', '了解'), ('列举', '了解')]:
        if w in statement:
            return c
    return '掌握'


PUNCT = re.compile(r'[（）《》「」【】，。、；：？！·—\s]')


def obj_of(statement, verb):
    """动词之后的部分作为 object（去重签名用）。取不到就退回整句。"""
    i = statement.find(verb)
    tail = statement[i + len(verb):] if i >= 0 else statement
    tail = re.sub(r'^[的地得，,、]+', '', tail).strip()
    return (tail or statement)[:40]


def main():
    if not SRC.exists():
        sys.exit(f"缺少 {SRC}，先跑 tools/to_candidates.py")
    cands = [json.loads(l) for l in SRC.open(encoding='utf-8')]

    used = load_used_ids(ROOT)
    sigs = {}
    # 已有锚点的签名也要占位，避免候选和正式锚点撞车
    for f in (ROOT / 'anchors').rglob('*.jsonl'):
        for l in f.open(encoding='utf-8'):
            a = json.loads(l)
            sigs[f"{a['discipline']}|{a['verb']}|{a['object']}"] = a['id']

    out = collections.defaultdict(list)
    dup = 0
    for c in cands:
        disc, verb = c['discipline'], c['verb']
        obj = obj_of(c['statement'], verb)
        sig = disc + '|' + verb + '|' + PUNCT.sub('', obj)
        if sig in sigs:
            dup += 1
            continue
        cid = mint_id(used)
        sigs[sig] = cid
        out[disc].append({
            'id': cid, 'discipline': disc, 'track': TRACK.get(disc, 'MATRIX'),
            'strand': c.get('strand') or None, 'topic': None, 'dimension': None,
            'statement': c['statement'], 'verb': verb, 'object': obj,
            'type': infer_type(verb, c['statement']),
            'literacy': c.get('literacy') or [], 'cognitive': infer_cognitive(c['statement']),
            'stageHint': c.get('stageHint'),
            'reviewStatus': 'llm-proposed', 'reviewedBy': [],
            'deprecated': False, 'supersededBy': None,
            'provenance': c['provenance'],
            'schemaVersion': '0.1.0',
        })

    total = 0
    for disc, rows in sorted(out.items()):
        p = ROOT / 'candidates' / f"{FILE.get(disc, disc)}.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open('w', encoding='utf-8') as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
        total += len(rows)
        print(f"  candidates/{p.name:<14} {len(rows):>4} 条  [{TRACK.get(disc)}]")
    print(f"\n共 {total} 条候选入库（去重丢弃 {dup} 条重复签名）")
    print("  全部 reviewStatus=llm-proposed —— 禁止被 L3 档案引用，须学科主编复核补齐 evidence 后搬入 anchors/")


if __name__ == '__main__':
    main()
