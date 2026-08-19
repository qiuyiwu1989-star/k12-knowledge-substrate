#!/usr/bin/env python3
"""
split_teacher_sheet.py — 把合订复核单按学科裁成 24 份单科版。

## 为什么要拆

合订本 24 科 410 条 729KB。老师打开，**先要在 24 个学科里找自己那科** ——
那一下就是流失点。发的时候要能说「数学老师看这个」，
不是「这里有 24 科你自己找」。

## 为什么是「裁」不是「重新生成」

从合订本的 HTML 里按学科面板裁，而不是再写一遍生成逻辑：
**两套生成逻辑必然漂移** —— 改了合订本忘了改单科版，两边说的话就不一样了，
而它们是给同一个老师看的同一件事。裁的话，合订本改什么单科版就跟着改什么。

    python3 tools/make_teacher_sheet.py      # 先出合订本
    python3 tools/split_teacher_sheet.py     # 再裁
"""
import re, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'review-queue/teacher-sheet.html'
OUT = ROOT / 'review-queue/by-subject'


def main():
    if not SRC.exists():
        raise SystemExit('先跑 python3 tools/make_teacher_sheet.py')
    h = SRC.read_text(encoding='utf-8')

    # 每科一个 <section class=pane data-d="学科" hidden>…</section>
    panes = re.findall(r'<section class=pane data-d="([^"]+)" hidden>(.*?)</section>', h, re.S)
    if not panes:
        raise SystemExit('没找到学科面板 —— 合订本的结构变了，这个裁法要跟着改')
    print(f"合订本里 {len(panes)} 个学科面板")

    head = h[:h.index('<div class=tabs')]
    tail = h[h.index('<div id=dock>'):]
    # 学科切换的 JS 在单科版里没用，但留着无害（tabs 为空时 show() 不会被调用）
    tail = tail.replace('show(tabs[0].dataset.d);',
                        'if(tabs.length) show(tabs[0].dataset.d); else tally();')

    OUT.mkdir(exist_ok=True)
    for old in OUT.glob('*.html'):
        old.unlink()

    idx = []
    for disc, body in panes:
        n = body.count('data-id=')
        # 单科版：去掉学科 tab 条，面板直接显示
        page = (head
                .replace('<title>课标能力复核单</title>', f'<title>{disc}·课标能力复核单</title>')
                .replace('这些条目，AI 已经审过一遍了。<br>请你来挑刺。',
                         f'{disc}：这 {n} 条，AI 已经审过一遍了。<br>请你来挑刺。')
                + f'<section class=pane data-d="{disc}">{body}</section>'
                + tail)
        # localStorage 的 key 按学科分开 —— 不同老师在同一台机器上做不同科，
        # 共用一个 key 会互相覆盖
        page = page.replace("const KEY='k12-teacher-verdicts-v1';",
                            f"const KEY='k12-teacher-verdicts-v1:{disc}';")
        f = OUT / f'{disc}.html'
        f.write_text(page, encoding='utf-8')
        idx.append((disc, n, f.stat().st_size))

    idx.sort(key=lambda x: -x[1])
    print(f"\n→ {OUT}/  （{len(idx)} 份）")
    for d, n, sz in idx[:8]:
        print(f"    {d:<10} {n:>3} 条  {sz // 1024:>3} KB")
    avg = sum(x[2] for x in idx) // len(idx) // 1024
    print(f"    …平均 {avg} KB（合订本 {SRC.stat().st_size // 1024} KB）")


if __name__ == '__main__':
    main()
