#!/usr/bin/env bash
# fetch-standards.sh — 下载 2022 版义务教育课程方案与 14 个学科课标（官方 PDF）
#
# 来源：中国政府网 教材〔2022〕2 号 通知附件
#   https://www.gov.cn/zhengce/zhengceku/2022-04/21/content_5686535.htm
# 链接已于 2026-08 实测可用（HTTP 200）。moe.gov.cn 的同名页面有 https→http 跳转，
# 抓取会失败，一律走 gov.cn。
#
# ⚠️ 这 15 份 PDF 全部是 150 DPI 扫描图，**没有文字层**（实测 1594 页，0 页可抽文本）。
#    传统 OCR 会产生截断错误（open-curriculum-cn 的 content_req 有 18% 疑似 OCR 损伤）。
#    正确做法是逐页交给多模态模型识读，见 docs/EXTRACTION.md。
#
#   bash scripts/fetch-standards.sh [输出目录，默认 ./sources/standards-2022]

set -euo pipefail
OUT="${1:-sources/standards-2022}"
BASE="https://www.gov.cn/zhengce/zhengceku/2022-04/21"
mkdir -p "$OUT"

declare -a DOCS=(
  "00-课程方案:P020231110625849851424"
  "01-道德与法治:P020231110625850485111"
  "02-语文:P020231110625852228892"
  "03-历史:P020231110625855197412"
  "04-数学:P020231110625858986255"
  "05-英语:P020231110625865933831"
  "06-日语:P020231110625870869115"
  "07-俄语:P020231110625875204999"
  "08-地理:P020231110625877186721"
  "09-科学:P020231110625878910829"
  "10-物理:P020231110625884914045"
  "11-化学:P020231110625887065052"
  "12-生物学:P020231110625889861385"
  "13-信息科技:P020231110625892033795"
  "14-体育与健康:P020231110625894022221"
  "15-艺术:P020231110625899365479"
  "16-劳动:P020231110625904756878"
)

for d in "${DOCS[@]}"; do
  name="${d%%:*}"; id="${d##*:}"
  target="$OUT/$name.pdf"
  if [ -s "$target" ]; then printf "  = %-18s 已存在\n" "$name"; continue; fi
  code=$(curl -sS -L -A "Mozilla/5.0" -o "$target" -w "%{http_code}" "$BASE/$id.pdf")
  printf "  %s %-18s HTTP %s  %s\n" "$([ "$code" = 200 ] && echo ✓ || echo ✗)" "$name" "$code" "$(du -h "$target" | cut -f1)"
done

cat <<'EOF'

下一步：抽取【学业要求】而不是【内容要求】。
课标的「学业要求」章节原文就已经是「能 + 动词 + 对象」的可判定句式，
和 L0 锚点的形状天然吻合；「内容要求」是章节级内容，抽出来只会得到章节名。
EOF
