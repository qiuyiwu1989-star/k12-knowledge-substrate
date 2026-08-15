#!/usr/bin/env python3
"""
neirong_commit.py — 把【内容要求】抽出的候选落成 ai-adjudicated 锚点。

用户明示授权：「AI 先评估修改，人只要异议再改」。这一档就是为它设的。

**为什么不直接标 auto-confirmed。** 那个档的含义是「判定客观、根本不需要
教师」——「这个字写对没有」属于它。这批不是：「细胞是生物体结构和功能的
基本单位」孩子答得出算会，但要不要按这个颗粒度算掌握、算到什么程度，
仍是教学判断。混进 auto-confirmed 之后，任何消费方都无法再区分
「机器能判的」和「AI 替人判的」——而**「有异议再改」恰恰需要这个区分才成立**：
没有标记，就没有东西可供异议。

    python3 tools/neirong_commit.py 历史 生物学 地理
"""
import json, secrets, string, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALNUM = string.ascii_letters + string.digits

FILE = {'语文': 'chinese', '数学': 'math', '英语': 'english', '物理': 'physics',
        '化学': 'chemistry', '生物学': 'biology', '历史': 'history', '地理': 'geography',
        '道德与法治': 'morality', '科学': 'science', '艺术': 'art',
        '体育与健康': 'pe', '劳动': 'labor', '信息科技': 'infotech'}

STRAND = {'历史': '史料实证', '地理': '区域认知', '生物学': '生命观念',
          '道德与法治': '道德修养', '劳动': '劳动观念', '信息科技': '信息意识'}

SRC = '义务教育课程标准（2022年版）课程内容·内容要求'


def normalize(items, disc):
    """规范形只有 scripts/decide.mjs 一份实现。中文引号““””要归一成 " —— 不归一
    同一条断言就有两种写法，去重签名跟着分裂。"""
    import subprocess
    payload = '\n'.join(json.dumps({'statement': s, 'discipline': disc},
                                    ensure_ascii=False) for s in items)
    r = subprocess.run(['node', str(ROOT / 'scripts/decide.mjs')], input=payload,
                       capture_output=True, text=True, check=True)
    return [json.loads(l)['normalized'] for l in r.stdout.split('\n') if l.strip()]


def parse_stage(s):
    """'G7-9' → ('G7','G9')；后半段没有 G 前缀，直接 split 会得到非法年级。"""
    s = (s or '').strip()
    m = __import__('re').fullmatch(r'G(\d+)\s*[-–~]\s*G?(\d+)', s)
    if m:
        return f'G{m.group(1)}', f'G{m.group(2)}'
    m = __import__('re').fullmatch(r'G(\d+)', s)
    if m:
        return f'G{m.group(1)}', f'G{m.group(1)}'
    return 'G1', 'G9'


def main():
    subjects = sys.argv[1:] or ['历史', '生物学', '地理']

    taken, files = set(), {}
    for f in sorted((ROOT / 'anchors').glob('*.jsonl')):
        files[f.name] = [json.loads(l) for l in f.open(encoding='utf-8') if l.strip()]
        taken |= {a['id'] for a in files[f.name]}

    def nid():
        while True:
            i = 'ca_' + ''.join(secrets.choice(ALNUM) for _ in range(8))
            if i not in taken:
                taken.add(i); return i

    # 已有断言的去重签名，防止新抽的和存量撞车
    # 去重签名用的是 (学科, 动词, 对象)，跟 statement 不是一回事 ——
    # 两条不同措辞的断言可能对象相同。校验器按签名卡，这里就得按签名去重。
    def sig_of(disc, verb, obj):
        import re as _re
        return (disc, verb, _re.sub(r'[（）《》「」，。、；：？！\s·—]', '', obj))

    # **本脚本上一轮写进去的不算存量。** 第一版在移除旧记录之前就建了签名集，
    # 于是新写的每一条都和自己的上一版撞签名，重跑一次只剩 3 条。
    def is_prev_run(a):
        return a.get('evidenceSource') == 'curriculum-content'
    existing_sig = {(a['discipline'], a['statement'])
                    for v in files.values() for a in v if not is_prev_run(a)}
    existing_sigs = {sig_of(a['discipline'], a.get('verb') or '', a.get('object') or '')
                     for v in files.values() for a in v
                     if not a.get('deprecated') and not is_prev_run(a)}

    total = 0
    for subj in subjects:
        p = ROOT / f'tools/out/{subj}-candidates.json'
        if not p.exists():
            print(f"  ! {subj} 无候选文件，跳过"); continue
        cand = json.loads(p.read_text(encoding='utf-8'))
        for c, nk in zip(cand, normalize([c['statement'] for c in cand], subj)):
            c['statement'] = nk

        fname = f'{FILE[subj]}.jsonl'
        arr = files.setdefault(fname, [])
        # 可重跑：先清掉上一轮本脚本写进去的
        before = len(arr)
        arr[:] = [a for a in arr if a.get('evidenceSource') != 'curriculum-content']
        if before != len(arr):
            print(f"  ~ {subj} 剔除上一轮写入的 {before - len(arr)} 条")

        added = 0
        for c in cand:
            if (subj, c['statement']) in existing_sig:
                continue
            obj = c['statement'].replace('能说出', '', 1).strip()
            sg = sig_of(subj, c.get('verb') or '说出', obj)
            if sg in existing_sigs:
                continue
            existing_sig.add((subj, c['statement']))
            existing_sigs.add(sg)
            lo, hi = parse_stage(c.get('stage'))
            arr.append({
                'id': nid(), 'discipline': subj, 'track': 'MATRIX',
                'strand': STRAND.get(subj, '学科内容'),
                'topic': None, 'dimension': None,
                'statement': c['statement'], 'verb': c.get('verb') or '说出',
                'object': obj,
                'type': 'KNOWLEDGE', 'literacy': [], 'cognitive': '了解',
                'stageHint': {'min': lo, 'max': hi},
                'evidence': [f'问：{obj}是什么？能答出即为会',
                             '答案与课标原文一致，不要求逐字复述'],
                'assessment': f'{{{{name}}}}能说出{obj}吗？',
                'evidenceSource': 'curriculum-content',
                'reviewStatus': 'ai-adjudicated', 'reviewedBy': ['ai:extraction-pipeline'],
                'deprecated': False, 'supersededBy': None,
                'adjudication': {
                    'by': 'ai', 'basis': [
                        '来源：课标【内容要求】原文，非模型自由生成',
                        '过可判定性闸 + 命题闸（须是有标准答案的命题，不能是主题）',
                        f'接地校验：改写与原句字面覆盖 ≥62%',
                    ],
                    'pendingObjection': True,
                    'note': '用户授权「AI 先判、人有异议再改」。教师复核后应改判为 expert-confirmed 或 disputed。',
                },
                'provenance': {'srcSubject': subj, 'srcText': c['srcText'],
                               'method': 'curriculum-content-rewrite'},
                'schemaVersion': '0.1.0',
            })
            added += 1
        total += added
        print(f"  + {subj:<8} {added} 条 → anchors/{fname}")

    for fname, arr in files.items():
        with (ROOT / 'anchors' / fname).open('w', encoding='utf-8') as f:
            for a in arr:
                f.write(json.dumps(a, ensure_ascii=False) + '\n')
    print(f"  合计新增 {total} 条 ai-adjudicated 锚点")


if __name__ == '__main__':
    main()
