#!/usr/bin/env bash
# User-local installer. Never changes shell profiles or system packages.
set -euo pipefail
fail() { printf 'jetvim: %s\n' "$*" >&2; exit 1; }
JETVIM_HOME=${JETVIM_HOME:-"$HOME/.jetvim"}
case "$JETVIM_HOME" in /*) ;; *) fail 'JETVIM_HOME must be an absolute path';; esac
export GOENV=off GOTELEMETRY=off GOTOOLCHAIN=local
export GOCACHE="$JETVIM_HOME/cache/go-build" GOPATH="$JETVIM_HOME/tools/go/path"
export GOMODCACHE="$JETVIM_HOME/cache/go-mod"
mkdir -p "$JETVIM_HOME" "$JETVIM_HOME/tools" "$JETVIM_HOME/cache" "$JETVIM_HOME/bin"
work=$(mktemp -d "$JETVIM_HOME/cache/install.XXXXXXXX")
trap 'rm -rf "$work"' EXIT
if [ -n "${JETVIM_SOURCE_DIR:-}" ]; then
  code=$(cd "$JETVIM_SOURCE_DIR" && pwd -P)
else
  command -v git >/dev/null || fail 'Git is required. Install Git, then run this command again.'
  code="$JETVIM_HOME/code"
  if [ -e "$code" ]; then
    [ "$(git -C "$code" remote get-url origin)" = 'https://github.com/amirkabiri/jetvim.git' ] || fail 'Existing code directory has a different origin; nothing was overwritten.'
    git -C "$code" diff --quiet && git -C "$code" diff --cached --quiet || fail 'Code has local changes; save them before updating.'
    git -C "$code" fetch origin main
    git -C "$code" merge --ff-only FETCH_HEAD
  else
    git clone --depth=1 --branch main https://github.com/amirkabiri/jetvim.git "$work/code"
    mv "$work/code" "$code"
  fi
fi
[ -f "$code/init.lua" ] && [ -f "$code/config/install-assets.tsv" ] || fail 'Incomplete Jetvim source directory.'
case "$(uname -s)" in Darwin) platform=macos;; Linux) platform=linux;; *) fail 'Supported systems: macOS and Linux.';; esac
case "$(uname -m)" in arm64|aarch64) arch=arm64;; x86_64|amd64) arch=x86_64;; *) fail 'Supported architectures: arm64 and x86_64.';; esac
hash() { if command -v shasum >/dev/null; then shasum -a 256 "$1"; else sha256sum "$1"; fi | awk '{print $1}'; }
fetch_tool() {
  local name=$1 row url expected kind dest
  row=$(awk -F '\t' -v n="$name" -v p="$platform" -v a="$arch" '$1==n && $2==p && $3==a {print $4 " " $5 " " $6}' "$code/config/install-assets.tsv")
  [ -n "$row" ] || fail "No pinned $name download for $platform/$arch."
  read -r url expected kind <<< "$row"
  command -v curl >/dev/null || fail 'curl is required.'
  printf 'Installing %s locally…\n' "$name"
  curl --fail --location --retry 2 --proto '=https' --tlsv1.2 "$url" -o "$work/$name.tar.gz"
  [ "$(hash "$work/$name.tar.gz")" = "$expected" ] || fail "$name download checksum mismatch."
  dest="$work/$name"
  mkdir -p "$dest"
  tar -xzf "$work/$name.tar.gz" --strip-components=1 -C "$dest"
  if [ "$kind" = single ]; then mkdir -p "$dest/bin"; mv "$dest/rg" "$dest/bin/rg"; fi
  case "$name" in
    neovim) "$dest/bin/nvim" --version >/dev/null || fail 'Bundled Neovim cannot run here; Linux needs compatible glibc.';;
    ripgrep) "$dest/bin/rg" --version >/dev/null || fail 'Bundled ripgrep cannot run here.';;
    node) "$dest/bin/node" --version >/dev/null || fail 'Bundled Node cannot run here.';;
    go-toolchain) "$dest/bin/go" version >/dev/null || fail 'Bundled Go cannot run here.';;
  esac
  [ ! -e "$JETVIM_HOME/tools/$name" ] || mv "$JETVIM_HOME/tools/$name" "$work/$name.old"
  mv "$dest" "$JETVIM_HOME/tools/$name"
}
export PATH="$JETVIM_HOME/tools/neovim/bin:$JETVIM_HOME/tools/ripgrep/bin:$JETVIM_HOME/tools/node/bin:$JETVIM_HOME/tools/go/toolchain/bin:$PATH"
nvim_ok() { command -v nvim >/dev/null && nvim --version | awk 'NR==1 {sub(/^NVIM v/, ""); split($0,v,"."); ok=(v[1]>0 || v[2]>=11)} END {exit !ok}'; }
if ! nvim_ok; then fetch_tool neovim; nvim_ok || fail 'Bundled Neovim cannot run here (Linux requires glibc; try a compatible system Neovim 0.11+).'; fi
if [ "${JETVIM_SKIP_RIPGREP:-0}" != 1 ] && ! command -v rg >/dev/null; then fetch_tool ripgrep; fi
if [ "${JETVIM_SKIP_LANGUAGES:-0}" != 1 ]; then
  if ! command -v node >/dev/null || ! command -v npm >/dev/null || ! node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 24 ? 0 : 1)'; then fetch_tool node; fi
  if ! command -v go >/dev/null || ! go version | awk '{sub(/^go/,"",$3); split($3,v,"."); exit !(v[1]>1 || (v[1]==1 && v[2]>=27))}'; then
    fetch_tool go-toolchain
    mkdir -p "$JETVIM_HOME/tools/go"
    [ ! -e "$JETVIM_HOME/tools/go/toolchain" ] || mv "$JETVIM_HOME/tools/go/toolchain" "$work/go-toolchain.old"
    mv "$JETVIM_HOME/tools/go-toolchain" "$JETVIM_HOME/tools/go/toolchain"
  fi
  export JETVIM_HOME
  bash "$code/scripts/setup-typescript.sh"
  bash "$code/scripts/setup-gopls.sh"
fi
if [ ! -e "$JETVIM_HOME/settings.lua" ] && [ ! -L "$JETVIM_HOME/settings.lua" ]; then cp "$code/config/settings.lua" "$JETVIM_HOME/settings.lua"; fi
# The wrapper keeps settings and tools outside the updatable code clone.
# Quote both paths for POSIX shells, including spaces and apostrophes.
quote() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"; }
{
  printf '#!/bin/sh\nexport JETVIM_HOME='; quote "$JETVIM_HOME"
  printf '\nexec '; quote "$code/jetvim"; printf ' "$@"\n'
} > "$work/jetvim"
chmod +x "$work/jetvim"
mv "$work/jetvim" "$JETVIM_HOME/bin/jetvim"
bin=${JETVIM_BIN_DIR:-}
if [ -z "$bin" ]; then
  bin="$HOME/.local/bin"
  # Source bootstrap must remain local even when no explicit bin override is set.
  if [ -n "${JETVIM_SOURCE_DIR:-}" ]; then
    bin="$JETVIM_HOME/bin"
  else
    for candidate in "$HOME/.local/bin" "$HOME/bin" /opt/homebrew/bin /usr/local/bin; do
      case ":$PATH:" in *":$candidate:"*)
        if [ -d "$candidate" ] && [ -w "$candidate" ]; then bin=$candidate; break; fi;;
      esac
    done
  fi
fi
mkdir -p "$bin"
if [ "$bin" != "$JETVIM_HOME/bin" ]; then
  if [ -e "$bin/jetvim" ] || [ -L "$bin/jetvim" ]; then
    [ -L "$bin/jetvim" ] && [ "$(readlink "$bin/jetvim")" = "$JETVIM_HOME/bin/jetvim" ] || fail "Refusing to replace existing $bin/jetvim."
  fi
  ln -sf "$JETVIM_HOME/bin/jetvim" "$bin/jetvim"
fi
printf 'Installed Jetvim. Run: %s [folder]\n' "$bin/jetvim"
case ":$PATH:" in *":$bin:"*) ;; *) printf 'Add to your shell PATH: export PATH="%s:$PATH"\n' "$bin";; esac
