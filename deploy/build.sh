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
python3 tools/make_slices.py --out dist/data/slice   # 学段片=归属 · 年级片=投影 · 学科片
python3 tools/make_teacher_sheet.py
python3 tools/split_teacher_sheet.py

rm -rf dist && mkdir -p dist/2d dist/data
cp graph-3d.html dist/index.html    # 首页是 3D
cp graph.html    dist/2d/index.html # /2d 是俯视版
mkdir -p dist/about && cp about.html dist/about/index.html  # /about 是项目与方法论介绍
mkdir -p dist/list  && cp list.html  dist/list/index.html   # /list 是全部能力点的目录
cp data-index.html dist/data/index.html                     # /data/ 原先是 404
cp -r anchor-pages/a dist/a                                 # 2,158 个锚点详情页 + 共享资产
cp manifest.json dist/data/
for d in anchors edges lists mappings; do mkdir -p "dist/data/$d"; cp -r "$d"/* "dist/data/$d/"; done
echo "✓ dist/ 就绪 — $(du -sh dist | cut -f1)，$(find dist -type f | wc -l | tr -d ' ') 个文件"
