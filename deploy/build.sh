#!/usr/bin/env bash
# build.sh — 生成可发布的静态站点到 dist/
#
# 站点是纯静态：两个单文件图谱 + 数据集直取。没有后端、没有数据库 ——
# 整站 4.6MB，加数据库只会多一个会坏的东西。
set -euo pipefail
cd "$(dirname "$0")/.."

npm run check                       # 数据不过校验就不发布
python3 tools/make_graph.py --out graph.html
python3 tools/make_graph3d.py
python3 tools/make_about.py
python3 tools/make_list.py
python3 tools/make_data_index.py
python3 tools/make_anchor_pages.py            # /a/<id>/ 每条锚点一个详情页（specs/003）
python3 tools/make_teacher_sheet.py
python3 tools/split_teacher_sheet.py

rm -rf dist && mkdir -p dist/2d dist/data
cp graph-3d.html dist/index.html    # 首页是 3D
cp graph.html    dist/2d/index.html # /2d 是俯视版
# ⚠️ 分片必须在 `rm -rf dist` **之后**跑。第一版放在了前面，刚生成就被删掉 ——
#    而部署脚本里的 `test -f .../slice/index.json` 闸当场拦住了切换，
#    线上没被换成缺分片的版本。**闸比我可靠。**
python3 tools/make_slices.py --out dist/data/slice   # 学段片=归属 · 年级片=投影 · 学科片

mkdir -p dist/about && cp about.html dist/about/index.html  # /about 是项目与方法论介绍
mkdir -p dist/list  && cp list.html  dist/list/index.html   # /list 是全部能力点的目录
cp data-index.html dist/data/index.html                     # /data/ 原先是 404
cp -r anchor-pages/a dist/a                                 # 2,158 个锚点详情页 + 共享资产
cp manifest.json dist/data/
for d in anchors edges lists mappings; do mkdir -p "dist/data/$d"; cp -r "$d"/* "dist/data/$d/"; done
# ── 版本化快照：调用方 pin 的就是这个 ──────────────────────────────
# 打成单个 tgz，不摊开成目录 —— 一份快照 4MB 上下，摊开是几千个小文件，
# 服务器上要长期留十几份，inode 和 rsync 都吃不消。
# **已发布的版本不许覆盖**：build 时如果本地已有同名快照就直接报错，
# 逼你先动 VERSION（version-diff 那道闸会告诉你该动 major 还是 minor）。
VER=$(cat VERSION)
mkdir -p dist/data/v
tar czf "dist/data/v/$VER.tgz" -C dist/data anchors edges lists mappings manifest.json slice
echo "{\"latest\":\"$VER\"}" > dist/data/v/latest.json
echo "✓ 快照 dist/data/v/$VER.tgz — $(du -h "dist/data/v/$VER.tgz" | cut -f1)"

# 统计脚本注入所有页面。片段只存 deploy/analytics.html —— 5 种模板 + 3,671 个
# 详情页，贴 N 份就是同一个东西有 N 份定义，正是 no-dup-defs 拦的那个病。
# 注入 dist/ 而非源码：仓库里的 html 保持干净，本地预览也不打点。
# 工具自己核对数量 —— 漏一个页面就是漏一块数据，**而漏了不会有任何报错**。
python3 tools/inject_analytics.py

echo "✓ dist/ 就绪 — $(du -sh dist | cut -f1)，$(find dist -type f | wc -l | tr -d ' ') 个文件"
