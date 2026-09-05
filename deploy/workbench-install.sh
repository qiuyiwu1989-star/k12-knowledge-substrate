#!/usr/bin/env bash
# Run on the already-authorized host as root: bash script ARCHIVE COMMIT
# Only adds /workbench/ to the existing k12 site. No full-site replacement.
set -euo pipefail
test "$(id -u)" = 0
exec 9>/var/lock/k12-workbench.lock
flock -n 9
archive=${1:?archive required}
revision=${2:?commit required}
[[ "$revision" =~ ^[0-9a-f]{40}$ ]]
test -s "$archive"
base=/opt/k12-workbench
release="$base/releases/$revision"
config=/etc/nginx/sites-available/k12.yongle.school
site=/var/www/k12.yongle.school/index.html
stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup="/var/backups/k12-workbench/$stamp"
nginx -t
test -f "$config" && test -s "$site"
mkdir -p "$backup" "$base/releases"
cp -a "$config" "$backup/nginx.conf"
cp -a "$site" "$backup/index.html"
if test -L "$base/current"; then readlink -f "$base/current" > "$backup/previous-release"; fi
if test -f /etc/systemd/system/k12-workbench.service; then cp -a /etc/systemd/system/k12-workbench.service "$backup/service"; fi
if runuser -u postgres -- psql -Atc "SELECT 1 FROM pg_database WHERE datname='k12_workbench'" | grep -q 1; then
  runuser -u postgres -- pg_dump k12_workbench > "$backup/database.sql"
fi
activated=0
rollback() {
  cp -a "$backup/nginx.conf" "$config"
  cp -a "$backup/index.html" "$site"
  if test "$activated" = 1; then
    if test -f "$backup/previous-release"; then
      ln -sfn "$(cat "$backup/previous-release")" "$base/current"
      if test -f "$backup/service"; then cp -a "$backup/service" /etc/systemd/system/k12-workbench.service; systemctl daemon-reload; fi
      systemctl restart k12-workbench || true
    else systemctl stop k12-workbench || true; fi
  fi
  nginx -t && systemctl reload nginx
  echo "Install failed; restored site. Backup: $backup" >&2
}
trap rollback ERR
if test -e "$release"; then echo 'Release already exists; use a new commit or explicit rollback.' >&2; exit 1; fi
mkdir -p "$release"
tar -xzf "$archive" -C "$release"
test -s "$release/workbench/public/index.html"
test -s "$release/anchors/science.jsonl"
npm ci --prefix "$release/workbench" --omit=dev --ignore-scripts
if ! id k12-workbench >/dev/null 2>&1; then useradd --system --home-dir /var/lib/k12-workbench --create-home --shell /usr/sbin/nologin k12-workbench; fi
if ! runuser -u postgres -- psql -Atc "SELECT 1 FROM pg_roles WHERE rolname='k12-workbench'" | grep -q 1; then
  runuser -u postgres -- createuser k12-workbench
fi
if ! runuser -u postgres -- psql -Atc "SELECT 1 FROM pg_database WHERE datname='k12_workbench'" | grep -q 1; then
  runuser -u postgres -- createdb --owner=k12-workbench k12_workbench
fi
chmod -R a+rX "$release"
# This dedicated service has read-only filesystem access to the source; only its own DB is writable.
cat > /etc/systemd/system/k12-workbench.service <<'UNIT'
[Unit]
Description=K12 application mapping workbench
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=k12-workbench
Group=k12-workbench
WorkingDirectory=/opt/k12-workbench/current
ExecStart=/usr/bin/node workbench/server.mjs
Environment=NODE_ENV=production
Environment=PORT=3412
Environment=WORKBENCH_ORIGIN=https://k12.yongle.school
Environment=WORKBENCH_DB=postgres
Environment=PGHOST=/var/run/postgresql
Environment=PGUSER=k12-workbench
Environment=PGDATABASE=k12_workbench
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=K12_USAGE=0
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
MemoryMax=384M
TasksMax=32
UMask=0077

[Install]
WantedBy=multi-user.target
UNIT
activated=1
ln -sfn "$release" "$base/current"
systemctl daemon-reload
systemctl enable k12-workbench.service
systemctl restart k12-workbench.service
healthy=0
for attempt in $(seq 1 15); do
  if curl --fail --silent http://127.0.0.1:3412/workbench/api/health > "$backup/health.json"; then healthy=1; break; fi
  sleep 1
done
if test "$healthy" != 1; then
  if test -f "$backup/previous-release"; then ln -sfn "$(cat "$backup/previous-release")" "$base/current"; systemctl restart k12-workbench; else systemctl stop k12-workbench; fi
  echo "Health failed. Existing nginx unchanged. Backup: $backup" >&2; exit 1
fi
python3 - "$config" "$site" <<'PY'
from pathlib import Path
import sys
config, site = map(Path, sys.argv[1:])
s = config.read_text()
if '# K12-WORKBENCH-BEGIN' not in s:
    marker = '    location / {'
    if s.count(marker) != 1: raise SystemExit('Unexpected nginx layout; no config edits applied')
    block = '''    # K12-WORKBENCH-BEGIN
    location = /workbench { return 302 /workbench/; }
    location ^~ /workbench/ {
        proxy_pass http://127.0.0.1:3412;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 25s;
        client_max_body_size 128k;
    }
    # K12-WORKBENCH-END

'''
    config.write_text(s.replace(marker, block + marker, 1))
s = site.read_text()
if 'id="mapping-entry"' not in s:
    if '</style></head><body>' not in s or '<input id="q"' not in s: raise SystemExit('Unexpected homepage layout')
    css = '#mapping-entry{position:fixed;right:26px;top:74px;z-index:7;font-size:12px;color:var(--fg);background:var(--chip);border:1px solid var(--line);border-radius:7px;padding:6px 12px;text-decoration:none}\n@media(max-width:1180px){#mapping-entry{top:auto;bottom:56px;right:18px}}\n'
    s = s.replace('</style></head><body>', css + '</style></head><body>', 1)
    s = s.replace('<input id="q"', '<a id="mapping-entry" href="/workbench/">应用映射工作台 ↗</a>\n<input id="q"', 1)
    site.write_text(s)
PY
if ! nginx -t; then
  cp -a "$backup/nginx.conf" "$config"
  cp -a "$backup/index.html" "$site"
  echo "Nginx test failed; restored backup: $backup" >&2; exit 1
fi
systemctl reload nginx
# Reload returns before the new workers necessarily accept connections.
curl --fail --silent --show-error --retry 10 --retry-all-errors --retry-delay 1 --max-time 5 \
  --resolve k12.yongle.school:443:127.0.0.1 https://k12.yongle.school/workbench/api/health
trap - ERR
printf '\nRelease: %s\nBackup: %s\n' "$revision" "$backup"
