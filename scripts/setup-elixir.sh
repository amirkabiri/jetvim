#!/bin/sh
# Optional ElixirLS: the Erlang/Elixir runtime must already be on PATH.
set -eu
JETVIM_SETUP_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
JETVIM_HOME=${JETVIM_HOME:-"$JETVIM_SETUP_ROOT/.jetvim"}
export JETVIM_HOME
for JETVIM_ELIXIR_REQUIREMENT in elixir erl mix python3; do
  if ! command -v "$JETVIM_ELIXIR_REQUIREMENT" >/dev/null 2>&1; then
    echo 'Elixir setup requires existing compatible Elixir, Erlang/OTP and Python 3 on PATH. No runtime was installed.' >&2
    exit 1
  fi
done
mkdir -p "$JETVIM_HOME/tools/elixir-ls" "$JETVIM_HOME/tools/elixir/mix" \
  "$JETVIM_HOME/tools/elixir/hex" "$JETVIM_HOME/tools/elixir/install" \
  "$JETVIM_HOME/cache/rebar3" "$JETVIM_HOME/tmp" "$JETVIM_HOME/config" \
  "$JETVIM_HOME/cache" "$JETVIM_HOME/data" "$JETVIM_HOME/state"
export MIX_HOME="$JETVIM_HOME/tools/elixir/mix"
export HEX_HOME="$JETVIM_HOME/tools/elixir/hex"
export MIX_INSTALL_DIR="$JETVIM_HOME/tools/elixir/install"
export REBAR_CACHE_DIR="$JETVIM_HOME/cache/rebar3"
export XDG_CONFIG_HOME="$JETVIM_HOME/config" XDG_CACHE_HOME="$JETVIM_HOME/cache"
export XDG_DATA_HOME="$JETVIM_HOME/data" XDG_STATE_HOME="$JETVIM_HOME/state"
export TMPDIR="$JETVIM_HOME/tmp" ERL_CRASH_DUMP="$JETVIM_HOME/elixir-erl-crash.dump"
export MIX_ENV=prod ELS_LOCAL=0
JETVIM_ELIXIR_TOOLS="$JETVIM_HOME/tools/elixir-ls"
export JETVIM_ELIXIR_TOOLS
python3 - <<'PY'
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
import urllib.request
import zipfile

version = 'v0.31.1'
checksum = 'bac08322ea3698157eb2373bb5b65e38c15df9dd41e1c06f142f874367fa472f'
tools = Path(os.environ['JETVIM_ELIXIR_TOOLS']).resolve()
release = tools / ('release-' + version)
if not (release / 'launch.exs').exists():
    with tempfile.TemporaryDirectory(prefix='elixir-ls-', dir=os.environ['TMPDIR']) as folder:
        archive = Path(folder) / 'release.zip'
        url = f'https://github.com/elixir-lsp/elixir-ls/releases/download/{version}/elixir-ls-{version}.zip'
        with urllib.request.urlopen(url, timeout=60) as response, archive.open('wb') as destination:
            shutil.copyfileobj(response, destination)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != checksum:
            raise SystemExit('ElixirLS archive checksum mismatch; refusing installation.')
        extracted = Path(folder) / 'release'
        with zipfile.ZipFile(archive) as package:
            for entry in package.infolist():
                path = (extracted / entry.filename).resolve()
                if extracted.resolve() not in path.parents or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                    raise SystemExit('Unsafe ElixirLS archive entry; refusing installation.')
            package.extractall(extracted)
        for filename in ('launch.exs', 'quiet_install.exs', 'installer.exs', 'VERSION'):
            if not (extracted / filename).is_file():
                raise SystemExit('Incomplete ElixirLS archive.')
        if release.exists():
            shutil.rmtree(release)
        extracted.rename(release)
PY
# Prebuild explicitly here, rather than downloading a server on editor startup.
# Upstream Mix installs the pinned server and its dependencies for this runtime.
cd "$JETVIM_ELIXIR_TOOLS"
mix local.hex --force
mix local.rebar --force
elixir "$JETVIM_ELIXIR_TOOLS/release-v0.31.1/quiet_install.exs" </dev/null
cat > "$JETVIM_ELIXIR_TOOLS/language_server.sh" <<'WRAPPER'
#!/bin/sh
set -eu
JETVIM_ELIXIR_SERVER=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
JETVIM_HOME=${JETVIM_HOME:-$(CDPATH= cd -- "$JETVIM_ELIXIR_SERVER/../.." && pwd -P)}
export JETVIM_HOME
export MIX_HOME="$JETVIM_HOME/tools/elixir/mix" HEX_HOME="$JETVIM_HOME/tools/elixir/hex"
export MIX_INSTALL_DIR="$JETVIM_HOME/tools/elixir/install" REBAR_CACHE_DIR="$JETVIM_HOME/cache/rebar3"
export XDG_CONFIG_HOME="$JETVIM_HOME/config" XDG_CACHE_HOME="$JETVIM_HOME/cache"
export XDG_DATA_HOME="$JETVIM_HOME/data" XDG_STATE_HOME="$JETVIM_HOME/state"
export TMPDIR="$JETVIM_HOME/tmp" ERL_CRASH_DUMP="$JETVIM_HOME/elixir-erl-crash.dump"
export ELS_MODE=language_server ELS_LOCAL=0 MIX_ENV=prod
unset MIX_OS_DEPS_COMPILE_PARTITION_COUNT
# An ephemeral cookie prevents Erlang from creating a cookie in the user's home.
JETVIM_ELIXIR_COOKIE=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
exec elixir --erl "-kernel standard_io_encoding latin1 +sbwt none +sbwtdcpu none +sbwtdio none -setcookie $JETVIM_ELIXIR_COOKIE" "$JETVIM_ELIXIR_SERVER/release-v0.31.1/launch.exs"
WRAPPER
chmod 755 "$JETVIM_ELIXIR_TOOLS/language_server.sh"
printf '%s\n' 'Installed ElixirLS v0.31.1 locally. Restart Jetvim to use it.' \
  "Server: $JETVIM_ELIXIR_TOOLS/language_server.sh"
