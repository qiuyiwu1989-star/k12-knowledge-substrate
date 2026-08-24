#!/usr/bin/env bash
# release.sh — 发一个版本。**pin 的正解是 git tag，不是下载 tarball。**
#
# 2026-08-24 实测：站点出网 6 KB/s（48 kbps），4.4MB 的快照要 12 分钟，
# 四次尝试全部失败（TLS 握手 35 / HTTP2 帧错 16 / 超时 28 / 连接失败 000）。
# 服务器本身没问题 —— 负载 0.95，本机回环取同一个文件 213 MB/s。
# 瓶颈只在出网那一段，而那不是这个项目能修的。
#
# 所以把 pin 的主路径换成 git：数据本来就在仓库里，`git checkout v1.0`
# 是瞬时的、可靠的、可校验的。tarball 降级成便利品。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
V=$(cat VERSION)

[ -z "$(git status --porcelain)" ] || { echo "✗ 工作区不干净，先提交"; exit 1; }
git rev-parse "v$V" >/dev/null 2>&1 && { echo "✗ tag v$V 已存在。发布版本不可变，先动 VERSION"; exit 1; }

echo "── 全量闸 ──"; npm run check >/dev/null
# 闸的道数从 package.json 数出来，不手打 —— 上一版写死「十三道」，
# 加了第十四道之后它就在说谎了。这个仓库专门有一道 sync-docs 拦这种事。
N=$(node -e "console.log(require('./package.json').scripts.check.split('&&').length)")
echo "✓ $N 道全绿"

[ -f "releases/$V.json" ] || { echo "✗ 缺 releases/$V.json，先跑 npm run release-manifest -- $V"; exit 1; }

C=$(node -e "const m=require('./manifest.json').counts;console.log(\`锚点 \${m.anchors}（存活 \${m.liveAnchors}）· 边 \${m.edges}\`)")
git tag -a "v$V" -m "v$V — $C

pin 用法：git checkout v$V
数据契约见 CONTRACT.md，粒度口径见 GRAIN.md。
教师签字数为 0：「可引用」= AI 看过没挑出毛病。"
echo "✓ tag v$V  $C"
echo "  推送：git push origin v$V"
