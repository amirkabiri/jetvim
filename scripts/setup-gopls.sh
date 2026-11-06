#!/bin/sh
# Install optional Go language tooling and its caches inside this checkout.
set -eu
JETVIM_SETUP_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
JETVIM_HOME=${JETVIM_HOME:-"$JETVIM_SETUP_ROOT/.jetvim"}
export JETVIM_HOME
if ! command -v go >/dev/null 2>&1; then
  echo 'Go language support requires Go 1.27+ already on PATH.' >&2
  exit 1
fi
export GOBIN="$JETVIM_HOME/tools/go/bin"
export GOPATH="$JETVIM_HOME/tools/go/path"
export GOMODCACHE="$JETVIM_HOME/cache/go-mod"
export GOCACHE="$JETVIM_HOME/cache/go-build"
export GOPLSCACHE="$JETVIM_HOME/cache/gopls"
export GOTMPDIR="$JETVIM_HOME/tmp"
export TMPDIR="$GOTMPDIR"
export GOENV=off GOTELEMETRY=off GOTOOLCHAIN=local
export GOPROXY=https://proxy.golang.org GOSUMDB=sum.golang.org
export TEST_TELEMETRY_DIR="$JETVIM_HOME/cache/go-telemetry"
mkdir -p "$GOBIN" "$GOPATH" "$GOMODCACHE" "$GOCACHE" "$GOPLSCACHE" "$GOTMPDIR" "$TEST_TELEMETRY_DIR"
printf 'off\n' > "$TEST_TELEMETRY_DIR/mode"
cd "$JETVIM_SETUP_ROOT"
# Resolved from the official module proxy on 2026-11-06; requires Go 1.27+.
JETVIM_GOPLS_BUILD="$JETVIM_HOME/tools/go/build"
mkdir -p "$JETVIM_GOPLS_BUILD"
go mod download -json golang.org/x/tools/gopls@v0.24.0 > "$JETVIM_GOPLS_BUILD/module.json"
# Upstream gopls does not expose a telemetry-directory environment override.
# A local source copy passes its upstream telemetry API our local directory;
# the local mode file above disables both counters and uploads. No module-cache
# source, global telemetry preference or HOME value is changed.
if command -v python3 >/dev/null 2>&1; then
python3 - "$JETVIM_GOPLS_BUILD" <<'PY'
import json
from pathlib import Path
import shutil
import sys
build = Path(sys.argv[1])
module = json.loads((build / 'module.json').read_text())
source_dir = build / 'source'
if source_dir.exists():
    shutil.rmtree(source_dir)
shutil.copytree(module['Dir'], source_dir, copy_function=shutil.copyfile)
for directory in [source_dir, *(path for path in source_dir.rglob('*') if path.is_dir())]:
    directory.chmod(0o755)
source = source_dir / 'main.go'
text = source.read_text()
needle = 'telemetry.Start(telemetry.Config{'
if text.count(needle) != 1:
    raise SystemExit('Unexpected gopls entry point; refusing an unconfined build.')
text = text.replace('import (', 'import (\n\t"os"', 1)
text = text.replace(needle, needle + '\n\t\tTelemetryDir: os.Getenv("TEST_TELEMETRY_DIR"),', 1)
source.write_text(text)
(build / 'module-dir').write_text(str(source.parent))
PY
elif command -v node >/dev/null 2>&1; then
node - "$JETVIM_GOPLS_BUILD" <<'JS'
const fs = require('node:fs');
const path = require('node:path');
const build = process.argv[2];
const moduleInfo = JSON.parse(fs.readFileSync(path.join(build, 'module.json'), 'utf8'));
const sourceDir = path.join(build, 'source');
fs.rmSync(sourceDir, {recursive: true, force: true});
fs.cpSync(moduleInfo.Dir, sourceDir, {recursive: true});
function writableDirs(dir) {
  fs.chmodSync(dir, 0o755);
  for (const item of fs.readdirSync(dir, {withFileTypes: true})) {
    if (item.isDirectory()) writableDirs(path.join(dir, item.name));
  }
}
writableDirs(sourceDir);
const source = path.join(sourceDir, 'main.go');
let text = fs.readFileSync(source, 'utf8');
const needle = 'telemetry.Start(telemetry.Config{';
if (text.split(needle).length !== 2) throw new Error('Unexpected gopls entry point; refusing an unconfined build.');
text = text.replace('import (', 'import (\n\t"os"').replace(needle, needle + '\n\t\tTelemetryDir: os.Getenv("TEST_TELEMETRY_DIR"),');
fs.chmodSync(source, 0o644);
fs.writeFileSync(source, text);
fs.writeFileSync(path.join(build, 'module-dir'), sourceDir);
JS
else
  echo 'Go setup needs Python 3 or Node.js to prepare the local server.' >&2
  exit 1
fi
JETVIM_GOPLS_SOURCE=$(cat "$JETVIM_GOPLS_BUILD/module-dir")
cd "$JETVIM_GOPLS_SOURCE"
go build -mod=readonly -ldflags '-X main.version=v0.24.0-jetvim' -o "$GOBIN/gopls" .
printf '%s\n' 'Installed gopls locally. Restart Jetvim to use it.' "Server: $GOBIN/gopls"
