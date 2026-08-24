#!/usr/bin/env bash
# publish.sh — 把 dist/ 发到生产。**每一步都有闸，任一闸不过就不切换。**
#
# 这个脚本存在的理由：我手敲过十几次同样的 ssh 命令，每次都要记得带上那几个
# test。忘一次就可能把缺分片、缺详情页的版本切上去 —— 实际发生过一次，
# 是 `test -f .../slice/index.json` 当场拦住的（分片被 `rm -rf dist` 删了）。
#
# **只留一份回滚副本。** 原先 `cp -a` 出 .bak 再 `mv` 出 .old，
# 两份是同一份内容，白占 75MB × 2，而服务器磁盘已经 90%。
# 现在：旧版直接 mv 成 .bak（瞬间、不占额外空间），上一次的 .bak 才删。
set -euo pipefail
H=ubuntu@146.56.239.22
K="${DEPLOY_KEY:-$HOME/.ssh/id_deepbrain_deploy}"
D=/var/www/k12.yongle.school
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT"
[ -s dist/index.html ] || { echo "✗ dist/index.html 空 —— 先跑 deploy/build.sh"; exit 1; }
N=$(find dist/a -name index.html 2>/dev/null | wc -l | tr -d ' ')
[ "$N" -gt 2800 ] || { echo "✗ 详情页只有 $N 个，少于 2800 —— 构建没跑全"; exit 1; }
[ -f dist/data/slice/index.json ] || { echo "✗ 分片缺失 —— make_slices 没跑或被 rm -rf dist 删了"; exit 1; }
echo "本地闸通过：详情页 $N · 分片在 · 首页非空"

tar czf /tmp/k12-dist.tgz -C dist .
scp -q -o IdentitiesOnly=yes -i "$K" /tmp/k12-dist.tgz "$H":/tmp/

ssh -o IdentitiesOnly=yes -i "$K" "$H" "
set -e
df -h /var | tail -1
rm -rf /tmp/k12new && mkdir -p /tmp/k12new && tar xzf /tmp/k12-dist.tgz -C /tmp/k12new 2>/dev/null
# 服务器侧再验一遍 —— 传输可能截断，本地过闸不等于远端完整
test -s /tmp/k12new/index.html || { echo '✗ 远端首页空'; exit 1; }
test \"\$(find /tmp/k12new/a -name index.html | wc -l)\" -gt 2800 || { echo '✗ 远端详情页不足'; exit 1; }
test -f /tmp/k12new/data/slice/index.json || { echo '✗ 远端分片缺失'; exit 1; }
sudo rm -rf $D.bak
sudo mv $D $D.bak            # 瞬间，不额外占空间；上一份 .bak 刚删掉
sudo mv /tmp/k12new $D && sudo chown -R www-data:www-data $D
echo '已切换（回滚：sudo rm -rf $D && sudo mv $D.bak $D）'
df -h /var | tail -1
"
sleep 2
echo "── 外网核验 ──"
for u in / /list/ /about/ /data/manifest.json /data/slice/index.json; do
  printf '  %-28s ' "$u"
  curl -s -o /dev/null -w 'HTTP %{http_code}\n' --max-time 40 "https://k12.yongle.school$u"
done
curl -s --max-time 40 https://k12.yongle.school/data/manifest.json | python3 -c "
import json,sys;m=json.load(sys.stdin);c=m['counts']
print(f\"  线上：存活{c['liveAnchors']} 可用{m['usableAnchors']} 边{c['edges']} 签字{m['humanConfirmedAnchors']}\")"
