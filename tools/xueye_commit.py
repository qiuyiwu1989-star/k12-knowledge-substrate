#!/usr/bin/env python3
"""
xueye_commit.py — 把学业要求候选（tools/out/xueye-candidates.jsonl）落成锚点。

## 这批和别的批次不同的一点

候选里带着 `literacy` —— 那是**课标自己在括号里标的**学科核心素养
（「…观察、识别、描述与地貌、大气、水…有关的自然现象（**地理实践力**）」）。
别的批次的素养标签是我们打的，这一批是白拿的官方对应，**必须原样保留**。

## 其余字段按现有规矩补

  track       数理化走 DAG，其余 MATRIX（和 gaozhong_commit 一致）
  object      动词之后的文字（和现有锚点同一套切法）
  cognitive   从课标自己的动词读，不猜
  evidence    兜底模板，**evidenceSource 标 fallback 不冒充课标**
              （860 条那次的教训：evidenceSource 说的是证据来源，不是断言来源）
  stageHint   候选里已有 G10–G12。高中按模块给内容，不发明年级精度

## 闸

  · 归一到不动点 → 可判定闸 → 去重签名，全部调 scripts/lib/ 下的同一份实现
  · **不许自己算签名**（signature-stdin.mjs 是唯一真相）

    python3 tools/xueye_commit.py --dry-run
    python3 tools/xueye_commit.py
"""
import argparse, collections, json, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mint_py import load_used_ids, mint_id      # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'tools/out/xueye-candidates.jsonl'
DAG_SUBJECTS = {'数学', '物理', '化学'}
FILE = {'数学': 'math', '语文': 'chinese', '英语': 'english', '物理': 'physics', '化学': 'chemistry',
        '生物学': 'biology', '历史': 'history', '地理': 'geography', '道德与法治': 'morality',
        '科学': 'science', '信息科技': 'infotech', '劳动': 'labor', '艺术': 'art', '体育与健康': 'pe'}
COGNITIVE_MAP = [
    (['运用', '应用', '设计', '论证', '解决', '制作', '创作', '评价'], '应用'),
    (['掌握', '会', '能'], '掌握'),
    (['理解', '认识', '说明', '解释', '分析', '比较'], '理解'),
    (['了解', '知道', '感受', '体会', '初步'], '了解'),
]


def cognitive_of(s):
    for verbs, level in COGNITIVE_MAP:
        if any(v in s for v in verbs):
            return level
    return '了解'


def node_call(script, lines, raw=False):
    """raw=True 时按纯文本行读 —— signature-stdin.mjs 吐的是签名字符串不是 JSON。"""
    if not lines:
        return []
    p = subprocess.run(['node', str(ROOT / 'scripts/lib' / script)],
                       input='\n'.join(lines), capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        raise RuntimeError(f'{script}: {(p.stderr or "")[:200]}')
    lines_out = [l for l in p.stdout.splitlines() if l.strip()]
    out = lines_out if raw else [json.loads(l) for l in lines_out]
    if len(out) != len(lines):
        raise RuntimeError(f'{script} 返回 {len(out)} 条，期望 {len(lines)}')
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    cand = [json.loads(l) for l in SRC.open(encoding='utf-8') if l.strip()]
    print(f'读入候选 {len(cand)} 条 · {len({c["discipline"] for c in cand})} 科')

    # 归一到不动点 —— 落盘的字符串必须就是过闸的那个
    norm = node_call('normalize-stdin.mjs',
                     [json.dumps({'text': c['statement'], 'discipline': c['discipline']},
                                 ensure_ascii=False) for c in cand])
    again = node_call('normalize-stdin.mjs',
                      [json.dumps({'text': n, 'discipline': c['discipline']}, ensure_ascii=False)
                       for c, n in zip(cand, norm)])
    if [x for x, y in zip(norm, again) if x != y]:
        sys.exit('归一不幂等，不敢往下走')
    changed = sum(1 for c, n in zip(cand, norm) if c['statement'] != n)
    for c, n in zip(cand, norm):
        c['statement'] = n
    print(f'  归一改动 {changed} 条')

    verdicts = node_call('check-stdin.mjs', [c['statement'] for c in cand])
    passed, rej = [], collections.Counter()
    for c, v in zip(cand, verdicts):
        if v.get('ok'):
            c['verb'] = v.get('verb')
            passed.append(c)
        else:
            rej[(v.get('reasons') or ['?'])[0].split('：')[0]] += 1
    print(f'过可判定闸 {len(passed)} / {len(cand)} = {len(passed)*100//max(1,len(cand))}%')
    for k, n in rej.most_common(6):
        print(f'    拒 {n:>4}  {k}')

    # 组装 + 去重签名（调唯一那份实现）
    used = load_used_ids(ROOT)
    draft = []
    for c in passed:
        verb = c['verb'] or ''
        i = c['statement'].find(verb)
        obj = (c['statement'][i + len(verb):].strip('，。；、 ') if i >= 0 else c['statement'])[:60]
        subj = c['discipline']
        ev = [f"能在{subj}课堂或作业情境中完成：{c['statement'][:40]}"]
        draft.append({
            'id': None, 'discipline': subj,
            'track': 'DAG' if subj in DAG_SUBJECTS else 'MATRIX',
            'strand': None, 'topic': None, 'dimension': None,
            'statement': c['statement'], 'verb': verb, 'object': obj or c['statement'][:60],
            'type': 'KNOWLEDGE' if cognitive_of(c['statement']) == '了解' else 'CONCEPTUAL',
            # ★ 课标括号里自己标的素养，白拿的官方对应，原样保留
            'literacy': c.get('literacy') or [],
            'cognitive': cognitive_of(c['statement']),
            'stageHint': c.get('stageHint') or {'min': 'G10', 'max': 'G12'},
            'courseType': c.get('courseType'),
            'evidence': ev,
            'assessment': None,
            'evidenceSource': 'fallback',     # 兜底证据不冒充课标来源
            'reviewStatus': 'llm-proposed',
            'reviewedBy': [], 'deprecated': False, 'supersededBy': None,
            'crosscutting': [], 'practice': [],
            'provenance': {**(c.get('provenance') or {}), 'srcSubject': subj,
                           'method': 'gaozhong-xueye-split'},
            'schemaVersion': '0.1.0',
        })

    existing = []
    for f in sorted((ROOT / 'anchors').glob('*.jsonl')):
        for l in f.open(encoding='utf-8'):
            if l.strip():
                x = json.loads(l)
                if not x.get('deprecated'):
                    existing.append(x)
    sigs = set(node_call('signature-stdin.mjs',
                         [json.dumps(x, ensure_ascii=False) for x in existing], raw=True))
    mine = node_call('signature-stdin.mjs',
                     [json.dumps(x, ensure_ascii=False) for x in draft], raw=True)
    kept, dup = [], 0
    for x, sg in zip(draft, mine):
        if sg in sigs:
            dup += 1
            continue
        sigs.add(sg)
        kept.append(x)
    print(f'去重后 {len(kept)}（撞签名丢弃 {dup}）')
    print(f'  带课标官方素养标注的：{sum(1 for x in kept if x["literacy"])}')

    print('\n─── 样本 ───')
    for x in kept[:4]:
        print(f'  {x["discipline"]}｜{x["statement"][:52]}')
        print(f'     素养 {x["literacy"]} · p{x["provenance"].get("srcPage")}')
    if a.dry_run:
        print('\n（--dry-run：没有写盘）')
        return
    out = collections.defaultdict(list)
    for x in kept:
        x['id'] = mint_id(used)
        out[FILE.get(x['discipline'], f'gaozhong-{x["discipline"]}')].append(x)
    for stem, rows in out.items():
        with (ROOT / 'anchors' / f'{stem}.jsonl').open('a', encoding='utf-8') as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f'\n已写 {len(kept)} 条 → {len(out)} 个文件')


if __name__ == '__main__':
    main()
