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
    with tempfile.TemporaryDirectory(prefix='launcher-home-', dir=STATE) as runtime_home:
        for command, cwd, env in invocations:
            env.update(JETVIM_HOME=runtime_home, JETVIM_DISABLE_AUTOSAVE='1', JETVIM_DISABLE_VCS='1')
            env.pop('JETVIM_SETTINGS_FILE', None)
            result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, timeout=15)
            assert result.returncode == 0, result.stdout + result.stderr
            assert (project / 'example.lua').read_text() == '-- project write works\n'
    print('PASS: explicit project directory, current directory, PATH invocation, project writes, tree/search and scoped Lua settings')
