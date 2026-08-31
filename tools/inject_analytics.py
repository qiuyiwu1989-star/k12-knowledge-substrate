#!/usr/bin/env python3
"""inject_analytics.py — 把统计脚本注入 dist/ 里的所有页面。

## 为什么是一个独立步骤，不是五个生成器各贴一遍

页面模板现在有 5 种（首页 3D / 2D / 关于 / 全部能力点 / 数据索引），
外加 3,671 个锚点详情页，而且还会增加。片段贴 N 份 = 同一个东西有 N 份定义，
那正是这个仓库立了 `no-dup-defs` 专门拦的病。片段只存 `deploy/analytics.html`。

## 为什么注入 dist/ 而不是源码

仓库里的 html 保持干净，本地预览也不打点 —— 只有真正发出去的那份带统计。

## 为什么要核对数量

漏一个页面就是漏一块数据，**而漏了不会有任何报错**。所以注入完必须数：
注入数 ≠ 页面数就退出码 1，让 build 停在这里。
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SNIP = (ROOT / 'deploy' / 'analytics.html').read_text(encoding='utf-8').strip()
DIST = ROOT / 'dist'


def main():
    if not SNIP:
        sys.exit('✗ deploy/analytics.html 是空的')
    pages = list(DIST.rglob('*.html'))
    if not pages:
        sys.exit('✗ dist/ 里一个 html 都没有 —— 先跑构建')
    done = 0
    for f in pages:
        t = f.read_text(encoding='utf-8')
        if SNIP in t:                      # 已注入（重复跑不会贴两遍）
            done += 1
            continue
        if '</body>' not in t:
            sys.exit(f'✗ {f.relative_to(ROOT)} 没有 </body>，注入不了')
        f.write_text(t.replace('</body>', SNIP + '\n</body>', 1), encoding='utf-8')
        done += 1
    print(f'✓ 统计脚本注入 {done}/{len(pages)} 个页面')
    if done != len(pages):
        sys.exit(f'✗ 有 {len(pages) - done} 个页面没注入')


if __name__ == '__main__':
    main()
