#!/usr/bin/env python3
"""Check the public source surface; never read runtime state or print secret values."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
DIRECTORIES = ('assets', 'config', 'docs', 'lua', 'syntax', 'indent', 'macos', 'scripts', 'terminal', 'tests', '.github')
TOP_FILES = ('AGENTS.md', 'TASKS.md', 'README.md', 'LICENSE', 'install.sh', 'init.lua', 'jetvim', '.gitignore', 'VERSION')
PATTERNS = {
    'private home path': re.compile(r'/(?:Users|home)/[A-Za-z0-9_.-]+/'),
    'email address requiring review': re.compile(r'\b[A-Za-z0-9_.+-]+@(?!example\.(?:invalid|com|org|net)\b)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'),
    'credential in URL': re.compile(r'https?://[^/\s:@]+:[^/@\s]+@'),
    'private key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    'GitHub token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})\b'),
    'cloud access key': re.compile(r'\bAKIA[A-Z0-9]{16}\b'),
    'Slack token': re.compile(r'\bxox[baprs]-[A-Za-z0-9-]{20,}\b'),
    'internal fixture reference': re.compile(r'@' + 'divar' + r'/'),
}


def public_files():
    for name in TOP_FILES:
        path = ROOT / name
        if path.is_file():
            yield path
    for name in DIRECTORIES:
        directory = ROOT / name
        if directory.exists():
            for path in sorted(directory.rglob('*')):
                if path.is_file() and not path.is_symlink() and '__pycache__' not in path.parts:
                    yield path


def main():
    findings = 0
    count = 0
    for path in public_files():
        count += 1
        try:
            content = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            print(f'{path.relative_to(ROOT)}: binary file requires manual review')
            findings += 1
            continue
        for number, line in enumerate(content.splitlines(), 1):
            for label, pattern in PATTERNS.items():
                if pattern.search(line):
                    print(f'{path.relative_to(ROOT)}:{number}: {label} [value redacted]')
                    findings += 1
    print(f'Public source audit: {count} files, {findings} findings. Pattern scan only; review history separately.')
    return bool(findings)


if __name__ == '__main__':
    sys.exit(main())
