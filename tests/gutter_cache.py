#!/usr/bin/env python3
"""Mocked/pure gutter checks. This never executes Git."""
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent
result = subprocess.run([str(ROOT / 'jetvim'), '--headless', '-c',
                         'lua dofile(vim.env.JETVIM_ROOT .. "/tests/gutter_cache.lua")', '+qa!'],
                        cwd=ROOT, env=dict(os.environ, JETVIM_DISABLE_VCS='1', JETVIM_DISABLE_AUTOSAVE='1'),
                        capture_output=True, text=True, timeout=20)
print(result.stdout + result.stderr, end='')
raise SystemExit(result.returncode)
