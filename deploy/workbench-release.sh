#!/usr/bin/env bash
# Package the exact committed runtime; never copy a dirty checkout to production.
set -euo pipefail
cd "$(dirname "$0")/.."
git diff --quiet HEAD -- workbench mcp tools/mapper.py tools/citable.py tools/grain.py scripts/lib scripts/usage.mjs anchors edges mappings VERSION deploy/workbench-install.sh
revision=$(git rev-parse HEAD)
archive="${TMPDIR:-/tmp}/k12-workbench-${revision}.tgz"
git archive --format=tar "$revision" workbench mcp tools/mapper.py tools/citable.py tools/grain.py scripts/lib scripts/usage.mjs anchors edges mappings VERSION package.json deploy/workbench-install.sh | gzip > "$archive"
test -s "$archive"
printf '%s\n' "$archive"
shasum -a 256 "$archive"
