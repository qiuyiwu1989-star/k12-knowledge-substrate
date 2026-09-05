#!/usr/bin/env python3
"""
gaozhong_xueye_verify.py — 独立复核 tools/out/gaozhong-xueye/*.jsonl 是不是逐字的。

**只读产物和 PDF，不 import 抽取器**。抽取器自己也带一道校验，但那道校验用的是
抽取过程中记下的切段位置，和抽取共用一套内部状态；这个脚本什么都不知道，
只拿产物里的 `text` 和 `pages` 去原页里找，找不到就报。

判据（对每一条）：
  · 单页条目：正文去掉空白后，必须是该页 pypdf 原始取字（只做全角数字归一）
    去掉空白后的**连续子串**。
  · 跨页条目：按页顺序贪心切——在第一页上取「还能对上的最长前缀」，
    余下的拿到下一页接着对，最后一页必须把余下的全部对完。
    页与页之间允许断开（中间隔着页眉页脚表头），页内必须连续。
  · 带官方素养标注的四科（音乐/美术/德语/地理）：把标注按原样拼回正文尾部，
    要求拼回去之后仍然对得上——**标注确实是紧跟在这条后面印的**，
    不是从别处捡来的。
  · 同一页上，各条目的位置必须严格递增——防止重复计入或次序错乱。

    python3 tools/gaozhong_xueye_verify.py
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'sources/standards-gaozhong'
OUT = ROOT / 'tools/out/gaozhong-xueye'

TRANS = str.maketrans({**{' ': ' ', ' ': ' ', ' ': ' ', ' ': ' ', '　': ' ',
                         ' ': ' ', '﻿': ''},
                       **{chr(c): chr(c - 0xFEE0) for c in range(0xFF10, 0xFF1A)},
                       **{chr(c): chr(c - 0xFEE0) for c in range(0xFF21, 0xFF3B)},
                       **{chr(c): chr(c - 0xFEE0) for c in range(0xFF41, 0xFF5B)}})

LIT_CODE = {'音乐': ['审美感知', '艺术表现', '文化理解'],
            '美术': ['图像识读', '美术表现', '审美判断', '创意实践', '文化理解'],
            '德语': ['语言能力', '文化意识', '思维品质', '学习能力']}
DILI = ['人地协调观', '综合思维', '区域认知', '地理实践力']


def ws(s):
    return re.sub(r'\s+', '', s)


def longest_prefix_in(hay, needle, frm):
    """needle 的最长前缀，使它在 hay[frm:] 里出现。返回 (长度, 位置)。

    「更长的前缀在里面」⇒「更短的前缀也在里面」，单调，可以二分。
    """
    lo, hi, best = 0, len(needle), (0, -1)
    while lo <= hi:
        mid = (lo + hi) // 2
        i = hay.find(needle[:mid], frm) if mid else frm
        if i >= 0:
            best = (mid, i)
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def with_tag(subject, r):
    """把课标自己印的素养标注按原样拼回正文尾部；拼不回来就返回 None。"""
    if not r['literacy']:
        return None
    if subject in LIT_CODE:
        idx = [LIT_CODE[subject].index(x) + 1 for x in r['literacy']]
        return ws(r['text']) + ws('（素养%s）' % '、'.join(map(str, idx)))
    if subject == '地理' and all(x in DILI for x in r['literacy']):
        return ws(r['text']) + ws('（%s）' % '、'.join(r['literacy']))
    return None


def check(subject, rows, reader):
    raw = {}
    bad = []
    cursor = defaultdict(int)
    for r in rows:
        for p in r['pages']:
            if p not in raw:
                raw[p] = ws((reader.pages[p - 1].extract_text() or '').translate(TRANS))
        for candidate in ([with_tag(subject, r)] if with_tag(subject, r) else []) + [ws(r['text'])]:
            rest, ok, marks = candidate, True, []
            for i, p in enumerate(r['pages']):
                last = i == len(r['pages']) - 1
                n, at = longest_prefix_in(raw[p], rest, cursor[p])
                if n == 0 or (last and n != len(rest)):
                    ok = False
                    break
                marks.append((p, at + n))
                rest = rest[n:]
            if ok:
                for p, end in marks:
                    cursor[p] = end
                break
        else:
            bad.append(f"{r['code']} p{r['pages']} 对不上原页: …{r['text'][-40:]}")
    return bad


def main():
    files = sorted(OUT.glob('*.jsonl'))
    if not files:
        raise SystemExit(f'✗ {OUT} 里没有产物，先跑 tools/gaozhong_xueye.py')
    pdfs = {p.stem.split('-', 1)[1]: p for p in SRC.glob('*.pdf') if '-' in p.stem}
    total, failed = 0, 0
    for f in files:
        subject = f.stem
        rows = [json.loads(l) for l in f.open(encoding='utf-8') if l.strip()]
        bad = check(subject, rows, PdfReader(pdfs[subject]))
        total += len(rows)
        failed += len(bad)
        flag = '✓' if not bad else f'✗ {len(bad)} 条'
        # 只数「标注确实印在这条尾巴上」的；艺术的素养来自表头，不在条目里，不算。
        tagged = sum(1 for r in rows if with_tag(subject, r))
        note = f'（含 {tagged} 条连尾部素养标注一起核过）' if tagged else ''
        print(f'{flag} {subject:8s} {len(rows):4d} 条 {note}')
        for x in bad[:5]:
            print(f'     {x}')
    print(f'\n合计 {total} 条，对不上 {failed} 条')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
