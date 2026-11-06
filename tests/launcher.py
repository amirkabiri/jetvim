#!/usr/bin/env python3
"""Test project selection and PATH invocation using only in-checkout fixtures."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / '.jetvim'
STATE.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='project with spaces ', dir=STATE) as folder:
    project = Path(folder)
    (project / 'example.lua').write_text('-- example\n')
    check = ['--headless', 'example.lua', '-c', 'lua dofile(vim.env.JETVIM_ROOT .. "/tests/project.lua")', '+qa!']
    invocations = [
        ([str(ROOT / 'jetvim'), folder, *check], ROOT, os.environ.copy()),
        ([str(ROOT / 'jetvim'), *check], project, os.environ.copy()),
        (['jetvim', '.', *check], project, dict(os.environ, PATH=str(ROOT) + os.pathsep + os.environ['PATH'])),
    ]
    for command, cwd, env in invocations:
        result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stdout + result.stderr
        assert (project / 'example.lua').read_text() == '-- project write works\n'
    print('PASS: explicit project directory, current directory, PATH invocation, project writes, tree/search and installation settings')
