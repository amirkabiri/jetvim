#!/usr/bin/env python3
"""Validate the allowlisted release payload and emit a local review manifest."""
import hashlib
from pathlib import Path, PurePosixPath
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parent.parent
subprocess.run(['bash', str(ROOT / 'scripts/package.sh')], cwd=ROOT, check=True)
dist = ROOT / '.jetvim/dist'
archive = dist / 'jetvim.tar.gz'
checksum = (dist / 'SHA256SUMS').read_text().split()
assert checksum == [hashlib.sha256(archive.read_bytes()).hexdigest(), 'jetvim.tar.gz']
allowed = {'jetvim', 'install.sh', 'init.lua', 'README.md', 'config', 'lua', 'syntax', 'indent', 'scripts', 'docs', 'assets', 'terminal', 'macos', 'VERSION', 'LICENSE'}
required = {'jetvim/jetvim', 'jetvim/install.sh', 'jetvim/init.lua', 'jetvim/README.md',
            'jetvim/syntax/elixir.vim', 'jetvim/indent/elixir.vim', 'jetvim/assets/jetvim.svg', 'jetvim/macos/KeyBridge.swift', 'jetvim/terminal/warp.md'}
manifest = []
with tarfile.open(archive, 'r:gz') as tar:
    for member in tar.getmembers():
        path = PurePosixPath(member.name)
        assert not path.is_absolute() and '..' not in path.parts, member.name
        assert path.parts[0] == 'jetvim' and len(path.parts) >= 2, member.name
        assert path.parts[1] in allowed, member.name
        assert not any(part in {'.git', '.jetvim', '.idea', '__pycache__', 'node_modules'} for part in path.parts), member.name
        assert not member.issym() and not member.islnk(), member.name
        assert member.isfile() or member.isdir(), member.name
        assert member.uid == member.gid == 0 and not member.uname and not member.gname, member.name
        manifest.append(member.name)
assert required <= set(manifest), 'Missing public application files: ' + ', '.join(sorted(required - set(manifest)))
(dist / 'MANIFEST.txt').write_text('\n'.join(sorted(manifest)) + '\n')
print(f'PASS: checksum and {len(manifest)} public archive entries; manifest in .jetvim/dist/MANIFEST.txt')
