#!/usr/bin/env python3
"""Run cache/orchestration checks with a mocked process API; no Git commands."""
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent
result = subprocess.run([str(ROOT / 'jetvim'), '--headless', '-c',
                         'lua dofile(vim.env.JETVIM_ROOT .. "/tests/vcs_cache.lua")', '+qa!'],
                        cwd=ROOT, env=dict(os.environ, JETVIM_DISABLE_VCS='1'),
                        capture_output=True, text=True, timeout=15)
print(result.stdout + result.stderr, end='')
raise SystemExit(result.returncode)
