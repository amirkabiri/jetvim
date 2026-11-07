#!/usr/bin/env python3
"""Shared undo-directory creation races must not abort editor startup."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / '.jetvim'
STATE.mkdir(exist_ok=True)
NVIM = shutil.which('nvim')
assert NVIM, 'Neovim is required'
checks = 0
with tempfile.TemporaryDirectory(prefix='startup-directories-', dir=STATE) as directory:
    fixture = Path(directory)
    for scenario in ('fresh', 'existing', 'concurrent', 'occupied', 'denied'):
        project = fixture / scenario; project.mkdir()
        home = project / 'home'; home.mkdir()
        temporary = project / 'tmp'; temporary.mkdir()
        undo = home / 'undo'
        if scenario == 'existing': undo.mkdir()
        if scenario == 'occupied': undo.write_text('keep this file\n')
        script = project / 'check.lua'
        script.write_text('''
local root, scenario = vim.env.JETVIM_ROOT, vim.env.STARTUP_SCENARIO
vim.opt.runtimepath:prepend(root)
local undo = vim.env.JETVIM_HOME .. '/undo'
local original = vim.fn.mkdir
local calls = 0
vim.fn.mkdir = function(path, flags)
  if path == undo then
    calls = calls + 1
    if scenario == 'concurrent' then
      original(path, flags) -- A concurrent session wins the creation race.
      vim.v.errmsg = 'E739: Cannot create directory: ' .. path .. ': file already exists'
      error(vim.v.errmsg)
    elseif scenario == 'denied' then
      vim.v.errmsg = 'E739: Cannot create directory: permission denied'
      error(vim.v.errmsg)
    end
  end
  return original(path, flags)
end
local previous = scenario == 'concurrent' and 'prior diagnostic remains intact' or ''
vim.v.errmsg = previous
local ok, err = pcall(require('jetvim').setup, root)
vim.fn.mkdir = original
assert(calls == 1, 'undo creation runs exactly once without retries')
if scenario == 'occupied' or scenario == 'denied' then
  assert(not ok, 'real directory creation failure must abort startup')
  assert(tostring(err):find('E739', 1, true), 'original mkdir failure remains visible: ' .. tostring(err))
  assert(vim.fn.isdirectory(undo) == 0, 'failure does not fabricate a directory')
else
  assert(ok, tostring(err))
  assert(vim.fn.isdirectory(undo) == 1, 'startup creates/retains undo directory')
  assert(vim.v.errmsg == previous, 'benign race must preserve prior diagnostic')
  assert(vim.fn.exists(':JetvimFiles') == 2, 'full editor setup reaches command registration')
end
print('PASS: ' .. scenario)
vim.cmd('qa!')
''')
        env = dict(os.environ, JETVIM_ROOT=str(ROOT), JETVIM_PROJECT=str(project), JETVIM_HOME=str(home),
                   JETVIM_SETTINGS_FILE=str(home / 'settings.lua'), TMPDIR=str(temporary), NVIM_LOG_FILE=str(project / 'nvim.log'),
                   JETVIM_DISABLE_VCS='1', JETVIM_DISABLE_AUTOSAVE='1', STARTUP_SCENARIO=scenario,
                   XDG_CACHE_HOME=str(project / 'cache'), XDG_STATE_HOME=str(project / 'state'),
                   XDG_DATA_HOME=str(project / 'data'), XDG_CONFIG_HOME=str(project / 'config'))
        # run() owns and reaps this direct Neovim child, including on timeout.
        result = subprocess.run([NVIM, '--headless', '-u', 'NONE', '-i', 'NONE', '-n', '-l', str(script)],
                                cwd=project, env=env, capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, scenario + ': ' + result.stdout + result.stderr
        assert 'PASS: ' + scenario in result.stdout + result.stderr
        checks += 1
        if scenario == 'occupied':
            assert undo.read_text() == 'keep this file\n', 'occupied undo path must remain untouched'
            checks += 1
print(f'PASS: {checks} startup directory creation checks')
