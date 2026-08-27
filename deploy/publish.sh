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
# ── 全量闸必须绿 ────────────────────────────────────────────────
# 我在两天里两次把 check 红着的版本发了出去。第一次是文档日期不一致、
# 第二次也是 —— 都无害，但**同一个缺口踩两次就不是偶然**：
# publish 从来不跑 check，而人在部署那一刻是最不想再等的。
# 这一道会让每次发布慢几十秒，那是它该有的成本。
# 明确要跳过时：SKIP_CHECK=1 npm run publish（会打印出来，不会静默）
if [ "${SKIP_CHECK:-0}" = "1" ]; then
  echo "⚠ 已跳过全量闸（SKIP_CHECK=1）—— 你自己知道在做什么"
else
  echo "── 全量闸 ──"
  npm run check >/tmp/k12-publish-check.log 2>&1 || {
    echo "✗ check 没过，不发。日志：/tmp/k12-publish-check.log"
    grep -E "^✗" /tmp/k12-publish-check.log | head -5
    exit 1
  }
  N=$(node -e "console.log(require('./package.json').scripts.check.split('&&').length)")
  echo "✓ $N 道全绿"
fi

[ -s dist/index.html ] || { echo "✗ dist/index.html 空 —— 先跑 deploy/build.sh"; exit 1; }
# ── dist 必须是当前版本构建出来的 ────────────────────────────────
# 这个脚本**不构建**。2026-08-25 我改完数据、打好 v1.1 的 tag，直接跑 publish，
# 结果发上去的是 v1.0 时的 dist —— 全部闸都绿，因为它们检查的是
# 「dist 完不完整」，没有一条检查「dist 是不是当前这份数据构建的」。
# 快照文件名带着版本号，所以这一条查得很便宜。
V=$(cat VERSION)
[ -f "dist/data/v/$V.tgz" ] || {
  echo "✗ dist 里没有 v$V 的快照 —— dist 是旧版本构建的，先跑 bash deploy/build.sh"
  echo "  现有：$(ls dist/data/v/*.tgz 2>/dev/null | xargs -n1 basename 2>/dev/null | tr '\n' ' ')"
  exit 1
}
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
# ── 历史版本必须活过整树切换 ────────────────────────────────────
# 这个脚本是「整棵目录换掉」的，而已发布的快照就在这棵树里面 ——
# 不搬走的话，第二次发布就把第一次的快照抹了，
# 而 CONTRACT.md 里白纸黑字写着「每个发布版本永久可取」。
# 这是那句承诺唯一的执行点。
mkdir -p /tmp/k12new/data/v
if [ -d $D/data/v ]; then sudo cp -n $D/data/v/*.tgz /tmp/k12new/data/v/ 2>/dev/null || true; fi
for f in $D/data/v/*.tgz; do
  [ -e \"\$f\" ] || continue
  b=\$(basename \"\$f\")
  test -f /tmp/k12new/data/v/\$b || { echo \"✗ 已发布版本 \$b 会在这次切换中丢失\"; exit 1; }
done
ls /tmp/k12new/data/v/*.tgz 2>/dev/null | xargs -n1 basename | sed 's/\.tgz\$//' | sort -V | \
  python3 -c \"import sys,json;print(json.dumps({'versions':[l.strip() for l in sys.stdin if l.strip()]}))\" \
  > /tmp/k12new/data/v/index.json
echo \"  可取版本：\$(python3 -c \"import json;print(' '.join(json.load(open('/tmp/k12new/data/v/index.json'))['versions']))\")\"

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
