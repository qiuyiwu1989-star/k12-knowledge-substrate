#!/usr/bin/env bash
# fetch-standards-gaozhong.sh — 下载《普通高中课程方案和课程标准（2017年版2020年修订）》
#
# 来源：人民教育出版社「普通高中课程方案及20科课程标准」专题页
#   https://www.pep.com.cn/xw/zt/rjwy/gzkb2020/
# 教育部印发通知（教材〔2020〕3 号）：
#   http://www.moe.gov.cn/srcsite/A26/s8001/202006/t20200603_462199.html
# 教育部课程教材研究所也有同一批文件（https://www.ictr.edu.cn/download_center/put.html），
# 但该站对无 Cookie 的请求返回 412，脚本走人教社。
# 链接已于 2026-08-17 实测：21 份全部 HTTP 200。
#
# ✅ 与义务教育版最大的不同：**这 21 份全部带文字层**（实测 2,276 页，逐份抽样均可提取）。
#    义务教育那 15 份是 150 DPI 扫描图、零文字层，必须逐页喂多模态模型。
#    高中这批可以直接 pypdf 提取 —— 不过 VLM、不引入识读幻觉，
#    抽取路径和义务教育完全不同，别套用 tools/extract_pages.py。
#
# ⚠️ 人教社会掐高频连接（LibreSSL SSL_ERROR_SYSCALL）。必须限速：
#    每份之间 sleep，且分多轮只补缺的。无脑并发会拿到一堆 0 字节文件。
#
#   bash scripts/fetch-standards-gaozhong.sh [输出目录，默认 ./sources/standards-gaozhong]

set -euo pipefail
OUT="${1:-sources/standards-gaozhong}"
BASE="https://www.pep.com.cn/xw/zt/rjwy/gzkb2020/202205"
REFERER="https://www.pep.com.cn/xw/zt/rjwy/gzkb2020/"
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"
MINSIZE=100000        # 小于 100KB 一律视为失败重来
mkdir -p "$OUT"

declare -a DOCS=(
  "00-课程方案:P020220517517917054840"
  "01-语文:P020220517522412911080"
  "02-数学:P020220517519489596282"
  "03-英语:P020220517522153664167"
  "04-思想政治:P020220517519869509154"
  "05-历史:P020220517518171679768"
  "06-地理:P020220517516728907929"
  "07-物理:P020220517520664858048"
  "08-化学:P020220517517668288401"
  "09-生物学:P020220517519140545267"
  "10-信息技术:P020220517521187437000"
  "11-通用技术:P020220517520410285510"
  "12-艺术:P020220517521458591016"
  "13-音乐:P020220517521792634168"
  "14-美术:P020220517518487651706"
  "15-体育与健康:P020220517520130143580"
  "16-日语:P020220517518796185803"
  "17-俄语:P020220517517065940620"
  "18-德语:P020220517516321579367"
  "19-法语:P020220517517384841139"
  "20-西班牙语:P020220517520908798310"
)

# 分 4 轮只补缺的。实测第 1 轮会因限流丢 15 份，第 2 轮补回 3 份，
# 越往后越少 —— 单轮串行 + sleep 也压不住，只能靠多轮。
for round in 1 2 3 4; do
  missing=0
  for doc in "${DOCS[@]}"; do
    name="${doc%%:*}"; id="${doc##*:}"
    target="$OUT/$name.pdf"
    if [[ -s "$target" ]] && (( $(wc -c < "$target") > MINSIZE )); then continue; fi
    missing=$((missing + 1))
    printf '  第%d轮 取 %-14s ' "$round" "$name"
    if curl -sS --retry 2 --retry-delay 3 -A "$UA" -e "$REFERER" \
         -o "$target" "$BASE/$id.pdf" 2>/dev/null \
       && (( $(wc -c < "$target") > MINSIZE )); then
      printf '%.1f MB\n' "$(echo "scale=2; $(wc -c < "$target") / 1048576" | bc)"
    else
      rm -f "$target"; echo "失败（下一轮重试）"
    fi
    sleep 3
  done
  (( missing == 0 )) && break
done

have=$(find "$OUT" -name '*.pdf' -size +100k | wc -l | tr -d ' ')
echo "✓ $have / ${#DOCS[@]} 份 — $(du -sh "$OUT" | cut -f1)"
if (( have < ${#DOCS[@]} )); then
  echo "⚠️ 仍有缺失，直接再跑一次本脚本即可（只补缺的）"; exit 1
fi

# 文字层自检。这批的价值就在这一点上，抽不出文本就说明拿错了文件。
python3 - "$OUT" <<'PY'
import sys
from pathlib import Path
try:
    from pypdf import PdfReader
except ImportError:
    print("（未装 pypdf，跳过文字层自检：pip3 install --user pypdf）"); sys.exit(0)
tot = bad = 0
for p in sorted(Path(sys.argv[1]).glob('*.pdf')):
    r = PdfReader(str(p)); n = len(r.pages); tot += n
    mid = (r.pages[n // 2].extract_text() or '').strip()
    if len(mid) < 200:
        print(f"  ⚠️ {p.stem} 中间页只抽到 {len(mid)} 字 — 可能是扫描页"); bad += 1
print(f"✓ 合计 {tot} 页，{bad} 份文字层可疑")
PY
