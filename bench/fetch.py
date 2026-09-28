#!/usr/bin/env python3
"""
fetch.py — 把映射基准要用的题目拉到本地 bench/.cache/（不进 git）。

**为什么题目原文不进仓库。** 三个来源的许可不一样：
  · CMATH（小学数学应用题）      CC BY 4.0     —— 可再分发，需署名
  · C-Eval（初中各科选择题）      CC BY-NC-SA 4.0 —— 非商用 + 相同方式共享，和本仓库的 ODbL 不兼容
  · GAOKAO-Bench（高考题）        Apache 2.0    —— 可再分发
统一只在仓库里存「来源 + 编号 + 标注」，原文按需现拉。最严的那个许可决定做法，
比按来源分三套规矩好记，也不会哪天有人把 NC 的题顺手提交进来。

    python3 bench/fetch.py            # 拉全部来源，写 bench/.cache/pool.jsonl
"""
import json, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / '.cache'
HF = 'https://hf-mirror.com'
ROWS = 'https://datasets-server.huggingface.co/rows'
GK = 'https://raw.githubusercontent.com/OpenLMLab/GAOKAO-Bench/main/Data/'

# 初中：C-Eval 的 middle_school_* → 我们的学科名
CEVAL = {'mathematics': '数学', 'physics': '物理', 'chemistry': '化学', 'biology': '生物学',
         'history': '历史', 'geography': '地理', 'politics': '道德与法治'}
# 高中：GAOKAO-Bench 的文件 → 我们的学科名。只取选择/填空/默写这类「一题一考点」的，
# 长篇阅读理解一题考一串能力，拿来量映射命中率会把问题搅浑，先不收
GAOKAO = {
    'Objective_Questions/2010-2022_Math_I_MCQs.json': '数学',
    'Objective_Questions/2010-2022_Math_II_MCQs.json': '数学',
    'Objective_Questions/2010-2022_Physics_MCQs.json': '物理',
    'Objective_Questions/2010-2022_Chemistry_MCQs.json': '化学',
    'Objective_Questions/2010-2022_Biology_MCQs.json': '生物学',
    'Objective_Questions/2010-2022_History_MCQs.json': '历史',
    'Objective_Questions/2010-2022_Geography_MCQs.json': '地理',
    'Objective_Questions/2010-2022_Political_Science_MCQs.json': '思想政治',
    'Objective_Questions/2010-2022_Chinese_Lang_and_Usage_MCQs.json': '语文',
    'Subjective_Questions/2010-2022_Chinese_Language_Famous_Passages_and_Sentences_Dictation.json': '语文',
    'Subjective_Questions/2010-2022_Math_I_Fill-in-the-Blank.json': '数学',
}


def get(url, tries=4):
    # 用 curl 而不是 urllib：hf-mirror 回 308，而 Python 3.9 的 urllib 不跟 308
    for i in range(tries):
        p = subprocess.run(['curl', '-sfL', '-m', '90', url], capture_output=True)
        if p.returncode == 0 and p.stdout:
            return p.stdout
        time.sleep(2 + 3 * i)
    raise RuntimeError(f'拉不下来：{url}')


def cmath():
    raw = get(f'{HF}/datasets/weitianwen/cmath/resolve/main/cmath_dev.jsonl').decode()
    for i, l in enumerate(raw.splitlines()):
        x = json.loads(l)
        yield {'src': 'cmath', 'ref': f'cmath_dev#{i}', 'stage': f"G{x['grade']}",
               'discipline': '数学', 'text': x['question']}


def ceval():
    for cfg, disc in CEVAL.items():
        off = 0
        while True:
            u = f'{ROWS}?dataset=ceval/ceval-exam&config=middle_school_{cfg}&split=val&offset={off}&length=100'
            d = json.loads(get(u))
            rows = d.get('rows') or []
            for r in rows:
                x = r['row']
                opts = '  '.join(f"{k}. {x[k]}" for k in 'ABCD' if x.get(k))
                yield {'src': 'ceval', 'ref': f"ceval/middle_school_{cfg}/val#{x['id']}", 'stage': 'G7-G9',
                       'discipline': disc, 'text': f"{x['question']}\n{opts}"}
            if len(rows) < 100:
                break
            off += 100


def gaokao():
    for path, disc in GAOKAO.items():
        d = json.loads(get(GK + path))
        for x in d['example']:
            yield {'src': 'gaokao', 'ref': f"gaokao/{path.split('/')[-1]}#{x['index']}", 'stage': 'G10-G12',
                   'discipline': disc, 'text': x['question'].strip(), 'year': x.get('year')}


def main():
    CACHE.mkdir(exist_ok=True)
    pool = []
    for name, fn in (('CMATH', cmath), ('C-Eval', ceval), ('GAOKAO-Bench', gaokao)):
        n0 = len(pool)
        pool.extend(fn())
        print(f'  {name:<13} {len(pool) - n0:>5} 题', flush=True)
    (CACHE / 'pool.jsonl').write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in pool),
                                      encoding='utf-8')
    print(f'✓ bench/.cache/pool.jsonl  {len(pool)} 题')


if __name__ == '__main__':
    sys.exit(main())
