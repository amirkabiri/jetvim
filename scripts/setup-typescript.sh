#!/bin/sh
# Install the optional TypeScript tooling only inside this Jetvim checkout.
set -eu
JETVIM_SETUP_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
JETVIM_TYPESCRIPT_TOOLS="$JETVIM_SETUP_ROOT/.jetvim/tools/typescript"
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo 'TypeScript setup requires Node.js and npm already available on PATH.' >&2
  exit 1
fi
node -e 'const [major, minor, patch] = process.versions.node.split(".").map(Number); if (major < 22 || (major === 22 && (minor < 22 || (minor === 22 && patch < 2)))) { console.error("typescript-language-server 6 requires Node.js >=22.22.2; current: " + process.version); process.exit(1); }'
mkdir -p "$JETVIM_TYPESCRIPT_TOOLS" "$JETVIM_SETUP_ROOT/.jetvim/npm-cache" "$JETVIM_SETUP_ROOT/.jetvim/tmp"
for JETVIM_NPM_CONFIG in "$JETVIM_SETUP_ROOT/.jetvim/npm-user.npmrc" "$JETVIM_SETUP_ROOT/.jetvim/npm-global.npmrc"; do
  if [ ! -f "$JETVIM_NPM_CONFIG" ]; then : > "$JETVIM_NPM_CONFIG"; fi
done
export npm_config_cache="$JETVIM_SETUP_ROOT/.jetvim/npm-cache"
export npm_config_userconfig="$JETVIM_SETUP_ROOT/.jetvim/npm-user.npmrc"
export npm_config_globalconfig="$JETVIM_SETUP_ROOT/.jetvim/npm-global.npmrc"
export npm_config_update_notifier=false
export TMPDIR="$JETVIM_SETUP_ROOT/.jetvim/tmp"
cd "$JETVIM_SETUP_ROOT"
# The upstream server currently documents TypeScript 6, rather than TypeScript 7.
npm install --global=false --prefix "$JETVIM_TYPESCRIPT_TOOLS" --ignore-scripts \
  --no-audit --no-fund --save-exact typescript-language-server@6.0.3 typescript@6.0.3
printf '%s\n' 'Installed TypeScript tooling locally. Restart Jetvim to use it.' \
  "Server: $JETVIM_TYPESCRIPT_TOOLS/node_modules/.bin/typescript-language-server"
