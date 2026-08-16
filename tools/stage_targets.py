#!/usr/bin/env python3
"""
stage_targets.py — 落「学段目标量」：每个学段该认识多少字、会写多少字。

**这解决什么，不解决什么。**

不解决：3500 字表切不出年级。那张表是按**音序**排的（阿啊哎哀唉埃挨癌矮…），
课标只给每个学段的**数量**，从不说是哪 1600 个字。切它就是编。

解决：产品终于能说出「识字 386 / 第一学段目标 1600（24%）」，而不是
「识字 386 / 3500（11%）」—— 后者对一个二年级孩子毫无意义，会把家长吓着。

数据全部来自课标正文原句，四个学段一条不缺，见下方 srcText。

    python3 tools/stage_targets.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 课标《义务教育语文课程标准（2022年版）》各学段「识字与写字」学段要求原句。
# 四条都在抽取语料里核对过，不是转述。
TARGETS = [
    dict(stage='G1-2', band='第一学段', recognize=1600, write=800,
         srcText='在学习与生活中，累计认识 1600 个左右常用汉字，能正确书写 800 个左右常用汉字。'),
    dict(stage='G3-4', band='第二学段', recognize=2500, write=1600,
         srcText='在学习与生活中，累计认识 2500 个左右常用汉字'),
    dict(stage='G5-6', band='第三学段', recognize=3000, write=2500,
         srcText='在学习与生活中，累计认识3000个左右常用汉字'),
    dict(stage='G7-9', band='第四学段', recognize=3500, write=3000,
         srcText='在学习与生活中，累计认识 3500 个左右常用汉字，能规范、端正、整洁地书写常用汉字；'),
]

# 挂到哪些锚点上。字表一是「会写」目标，字表二是「认识」目标。
ANCHOR_KIND = {
    'ca_5DS8mPj4': 'write',      # 常用字表一 2500，要求会写
    'ca_d7cDMEV4': 'recognize',  # 常用字表二 1000，只要求认识
    'ca_GyQEdbby': 'write',      # 基本字表 299，第一学段
}


def main():
    out = {
        'schemaVersion': '0.1.0',
        'about': '语文识字写字的分学段累计目标量，来自课标正文学段要求原句',
        'caveat': (
            '这是**数量**目标，不是字表切分。常用字表按音序排列，课标从不说哪些字属于哪个学段，'
            '因此本文件不能用来把 3500 字表切成四段 —— 那需要教材层的生字表，而教材层因版权不在本库。'
        ),
        'usage': (
            '产品算完成度时应按孩子所在学段取目标：二年级孩子识字 386，'
            '该显示 386/1600（第一学段目标 24%），不是 386/3500（11%）。'
        ),
        'targets': TARGETS,
        'anchorKind': ANCHOR_KIND,
    }
    p = ROOT / 'mappings/stage-targets.json'
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f"  → {p}")
    for t in TARGETS:
        print(f"    {t['band']}（{t['stage']}）  认识 {t['recognize']}　会写 {t['write']}")

    # 把目标量挂进锚点，产品不用再去 join 一次
    n = 0
    for f in sorted((ROOT / 'anchors').glob('*.jsonl')):
        arr = [json.loads(l) for l in f.open(encoding='utf-8') if l.strip()]
        touched = False
        for a in arr:
            kind = ANCHOR_KIND.get(a['id'])
            if not kind:
                continue
            a['stageTargets'] = [
                {'stage': t['stage'], 'band': t['band'], 'target': t[kind]} for t in TARGETS
            ]
            touched, n = True, n + 1
        if touched:
            with f.open('w', encoding='utf-8') as fh:
                for a in arr:
                    fh.write(json.dumps(a, ensure_ascii=False) + '\n')
    print(f"  ~ {n} 条字表锚点挂上了分学段目标量")


if __name__ == '__main__':
    main()
