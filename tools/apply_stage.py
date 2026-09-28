#!/usr/bin/env python3
"""
apply_stage.py — 把「翻课标原件定学段」的判读结果落到锚点上。

## 为什么要翻原件

两类锚点的学段是不可信的：
  · 标成 G1–G9 的占位 —— 抽取时没认出学段，填了整个义务教育
  · disputed 里挂着 stage 异议的 —— 复审说学段标错了，但没有课标依据可以裁
原先的 stage_by_page 按「页 → 学段标题」前向填充，对两种版式无能为力：
  · 科学、体育的内容要求是一张表，1～2 / 3～4 / 5～6 / 7～9 年级是**列**，同一页四个学段都有
  · 「第二学段（3～4年级）」这种横幅式标题，页索引没认出来（信息科技那 4 条就是这么错的）
所以逐条看原件的扫描页：这句话落在哪个学段的标题下、哪一列里。
判读结果在 tools/out/stage-judge-*.jsonl（落库后归档一份到 reports/stage-judgments-2026-09-28.jsonl），每条带页码和依据。

## 落库规则

  · 只收 confidence=high 的判读；low 和 null 一律不动
  · 学段按原件改，旧值记进 provenance.stageFixedFrom；恰好是一个学段的，srcStage 记「第X学段」
  · 挂着 stage 异议的：异议记成 resolved（附原件页码和依据）。
    剩下没有别的异议、且过可判定闸的 → ai-reviewed（与 resolve_disputed ② 同一处置：
    课标写了学段，模型的意见不能盖过课标）；还有别的异议的留在 disputed
  · **不改 srcPage**，哪怕判读时发现原句在相邻页 —— srcPage 是 ID 的出处判据，改它就是换锚点

    python3 tools/apply_stage.py            # 只看不写
    python3 tools/apply_stage.py --write
"""
import sys
sys.dont_write_bytecode = True

import argparse, collections, glob, json, re, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from fix_src_stages import read_bands, STD       # noqa: E402  学段划分按学科取（艺术是 1-2／3-5／6-7／8-9）
CN = {'一': '第一学段', '二': '第二学段', '三': '第三学段', '四': '第四学段'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--write', action='store_true')
    a = ap.parse_args()

    judge = {}
    for f in sorted(glob.glob(str(ROOT / 'tools/out/stage-judge-*.jsonl'))):
        for l in open(f, encoding='utf-8'):
            if l.strip():
                x = json.loads(l)
                judge[x['id']] = x
    bands, _ = read_bands()
    files = {f: [json.loads(l) for l in f.read_text(encoding='utf-8').splitlines() if l.strip()]
             for f in sorted((ROOT / 'anchors').glob('*.jsonl'))}
    byid = {r['id']: r for rows in files.values() for r in rows}

    stat, samples = collections.Counter(), collections.defaultdict(list)
    todo = []
    for i, j in judge.items():
        r = byid.get(i)
        if not r or r.get('deprecated'):
            stat['锚点不在 / 已弃用 → 跳过'] += 1
            continue
        m = re.fullmatch(r'G(\d{1,2})-G(\d{1,2})', str(j.get('stage') or ''))
        if j.get('confidence') != 'high' or not m:
            stat['判读不确定（low / null）→ 不动'] += 1
            continue
        lo, hi = int(m.group(1)), int(m.group(2))
        if not (1 <= lo <= hi <= 9):
            stat['区间不合法 → 不动'] += 1
            continue
        todo.append((r, j, lo, hi))

    # 撤异议升档前要过可判定闸（resolve_disputed 的教训：模型没挑出的问题，不等于没问题）
    need_gate = [r for r, _, _, _ in todo if r['reviewStatus'] == 'disputed']
    p = subprocess.run(['node', str(ROOT / 'scripts/lib/check-stdin.mjs')],
                       input='\n'.join(r['statement'] for r in need_gate), capture_output=True, text=True, timeout=600)
    vs = [json.loads(l) for l in p.stdout.splitlines() if l.strip()]
    if len(vs) != len(need_gate):
        sys.exit('可判定闸对不齐，不敢往下走')
    gate_ok = {r['id']: v.get('ok') for r, v in zip(need_gate, vs)}

    for r, j, lo, hi in todo:
        h = r.get('stageHint') or {}
        old = f"{h.get('min')}-{h.get('max')}"
        new = f'G{lo}-G{hi}'
        changed = old != new
        basis = f"课标原件 PDF 第 {j.get('page')} 页：{str(j.get('basis') or '')[:60]}"
        stat['学段改了' if changed else '学段原件确认无误'] += 1
        if changed:
            samples['改'].append((r, old, new, basis))
            if a.write:
                r['stageHint'] = {'min': f'G{lo}', 'max': f'G{hi}'}
                r.setdefault('provenance', {})['stageFixedFrom'] = old
        name = next((CN[k] for k, v in bands.get(r['discipline'], STD).items() if tuple(v) == (lo, hi)), None)
        if a.write and name:
            r.setdefault('provenance', {})['srcStage'] = name
        live = [x for x in r.get('aiIssues') or [] if x['type'] != 'resolved']
        if r['reviewStatus'] == 'disputed' and any(x['type'] == 'stage' for x in live):
            rest = [x for x in live if x['type'] != 'stage']
            if not rest and gate_ok.get(r['id']):
                stat['stage 异议撤销 → ai-reviewed'] += 1
                samples['升'].append((r, old, new, basis))
                up = True
            else:
                stat['stage 异议撤销，但还有别的异议 / 过不了闸 → 留 disputed'] += 1
                up = False
            if a.write:
                resolved = [x for x in r.get('aiIssues') or [] if x['type'] == 'resolved']
                was = next(x for x in live if x['type'] == 'stage')
                r['aiIssues'] = rest + resolved + [{
                    'type': 'resolved',
                    'detail': f"复审提了 stage（{was.get('detail', '')[:40]}）→ 按原件裁决："
                              f"{basis}，学段 {old} → {new}" if changed else
                              f"复审提了 stage（{was.get('detail', '')[:40]}）→ 撤销：{basis}，原件与标注一致"}]
                if up:
                    r['reviewStatus'] = 'ai-reviewed'

    for k, n in sorted(stat.items()):
        print(f'  {n:>4}  {k}')
    for r, old, new, b in samples['改'][:8]:
        print(f"    {r['id']} [{r['discipline']}] {old} → {new}  {r['statement'][:26]}  ({b[:40]})")
    if not a.write:
        print('（没写盘；加 --write 写回）')
        return
    for f, rows in files.items():
        f.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')
    print('已写回')


if __name__ == '__main__':
    main()
