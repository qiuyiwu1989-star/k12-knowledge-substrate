"""Run from an extracted committed archive with sudo; update only /mcp/ and homepage CTA."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

source = Path(__file__).resolve().parents[1] / 'site' / 'mcp'
root = Path('/var/www/k12.yongle.school')
revision = sys.argv[1]
assert len(revision) == 40 and all(c in '0123456789abcdef' for c in revision)
assert {p.name for p in source.iterdir()} == {'index.html', 'style.css', 'app.js'}
homepage = root / 'index.html'
original = homepage.read_bytes()
text = original.decode('utf-8')
entry = '<a id="mcp-entry" href="/mcp/">MCP 接入</a>'
anchor = '<a href="/about/">方法论</a>'
if 'id="mcp-entry"' not in text:
    assert text.count(anchor) == 1, 'Homepage layout changed; inspect before patching'
    text = text.replace(anchor, anchor + '\n  ' + entry)
else:
    assert entry in text, 'Existing MCP entry differs; inspect before patching'
backup = Path('/var/backups/k12-mcp-page') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
backup.mkdir(parents=True)
shutil.copy2(homepage, backup / 'index.html')
had_page = (root / 'mcp').exists()
if had_page:
    shutil.copytree(root / 'mcp', backup / 'mcp')
staging = root / ('.mcp-' + revision)
assert not staging.exists()
shutil.copytree(source, staging)
for f in staging.iterdir():
    f.chmod(0o644)
staging.chmod(0o755)
try:
    assert homepage.read_bytes() == original, 'Concurrent homepage edit'
    if had_page:
        shutil.rmtree(root / 'mcp')
    os.replace(staging, root / 'mcp')
    temp = root / '.index-mcp-next.html'
    temp.write_text(text, encoding='utf-8')
    temp.chmod(homepage.stat().st_mode & 0o777)
    os.chown(temp, homepage.stat().st_uid, homepage.stat().st_gid)
    os.replace(temp, homepage)
    for path in ['/mcp/', '/mcp/style.css', '/mcp/app.js', '/', '/zhishi/', '/workbench/']:
        subprocess.run(['curl', '--fail', '--silent', '--show-error', '--max-time', '20', '--resolve', 'k12.yongle.school:443:127.0.0.1', 'https://k12.yongle.school' + path, '-o', '/dev/null'], check=True)
except Exception:
    shutil.copy2(backup / 'index.html', homepage)
    if (root / 'mcp').exists():
        shutil.rmtree(root / 'mcp')
    if had_page:
        shutil.copytree(backup / 'mcp', root / 'mcp')
    raise
manifest = {'revision': revision, 'backup': str(backup), 'homepage_before_sha256': hashlib.sha256(original).hexdigest(), 'homepage_after_sha256': hashlib.sha256(homepage.read_bytes()).hexdigest(), 'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}, 'previous_mcp_page': had_page}
(backup / 'release.json').write_text(json.dumps(manifest, indent=2))
print(json.dumps(manifest))
