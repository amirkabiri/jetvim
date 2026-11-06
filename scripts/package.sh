#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd -P)
python3 - "$root" <<'PY'
import hashlib, pathlib, tarfile, sys
root = pathlib.Path(sys.argv[1])
out = root / '.jetvim/dist'
out.mkdir(parents=True, exist_ok=True)
archive = out / 'jetvim.tar.gz'
# Explicit public payload: never include runtime, editor metadata or local files.
names = ['jetvim', 'install.sh', 'init.lua', 'README.md', 'config', 'lua', 'scripts', 'docs', 'assets', 'terminal', 'macos']
with tarfile.open(archive, 'w:gz') as tar:
    for name in names:
        path = root / name
        if path.exists():
            def public(info):
                if any(part in ('.jetvim', '.idea', '__pycache__') for part in pathlib.PurePosixPath(info.name).parts):
                    return None
                if info.issym() or info.islnk():
                    raise SystemExit('Refusing package symlink: ' + info.name)
                info.uid = info.gid = 0
                info.uname = info.gname = ''
                return info
            tar.add(path, arcname='jetvim/' + name, filter=public)
(out / 'SHA256SUMS').write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + '  jetvim.tar.gz\n')
print(archive)
PY
