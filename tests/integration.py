#!/usr/bin/env python3
"""Exercise a real Neovim event loop and key mappings; all artifacts stay local."""
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / '.jetvim'
STATE.mkdir(exist_ok=True)
SOCKET = STATE / f'test-{os.getpid()}.sock'
checks = 0


def lua(code):
    expression = "json_encode(luaeval('(function() " + code.replace("'", "''") + " end)()'))"
    result = subprocess.run([str(ROOT / 'jetvim'), '--server', str(SOCKET), '--remote-expr', expression],
                            cwd=ROOT, capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return json.loads(result.stdout)


def equal(actual, expected, label):
    global checks
    assert actual == expected, f'{label}: expected {expected!r}, got {actual!r}'
    checks += 1


def keys(value):
    lua('return vim.api.nvim_input(' + json.dumps(value, ensure_ascii=False) + ')')
    time.sleep(0.035)


def fixture(lines, row=1, col=0):
    keys('<Esc>')
    lua('vim.cmd.enew({ bang = true }); vim.api.nvim_buf_set_name(0, vim.env.JETVIM_ROOT .. "/.jetvim/fixture-" .. vim.fn.getpid() .. "-" .. vim.api.nvim_get_current_buf() .. ".lua"); '
        'vim.bo.filetype = "lua"; vim.bo.commentstring = "-- %s"; '
        'vim.api.nvim_buf_set_lines(0, 0, -1, false, vim.json.decode(' + json.dumps(json.dumps(lines)) + ')); '
        f'vim.api.nvim_win_set_cursor(0, {{{row}, {col}}}); return true')


def lines():
    return lua('return vim.api.nvim_buf_get_lines(0, 0, -1, false)')


log = (STATE / 'integration.log').open('w')
process = subprocess.Popen([str(ROOT / 'jetvim'), '--headless', '--listen', str(SOCKET)], cwd=ROOT,
                           stdin=subprocess.DEVNULL, stdout=log, stderr=log)
try:
    deadline = time.monotonic() + 10
    while not SOCKET.exists():
        if process.poll() is not None or time.monotonic() > deadline:
            raise RuntimeError('Editor did not start; see .jetvim/integration.log')
        time.sleep(0.03)
    equal(lua('return vim.v.errmsg'), '', 'clean startup')
    equal(lua('return #require("jetvim.keymap").bindings'), len(json.loads((ROOT / 'config/keymap.json').read_text())), 'registered actions')
    equal(lua('return vim.fn.stdpath("cache"):sub(1, #vim.env.JETVIM_ROOT) == vim.env.JETVIM_ROOT'), True, 'local cache')
    equal(lua('return require("jetvim.project").resolve("/etc/passwd") == nil'), True, 'outside path rejected')
    equal(lua('return require("jetvim.project").resolve(vim.env.JETVIM_ROOT .. "/../jetvim-other/file") == nil'), True, 'sibling path rejected')
    lua('vim.uv.fs_symlink("/etc", vim.env.JETVIM_ROOT .. "/.jetvim/outside-link"); return true')
    equal(lua('return require("jetvim.project").resolve(".jetvim/outside-link/new-file") == nil'), True, 'symlink escape rejected')
    fixture(['alpha', 'beta'])
    keys('<D-d>')
    equal(lines(), ['alpha', 'alpha', 'beta'], 'duplicate in normal mode')
    keys('<D-BS>')
    equal(lines(), ['alpha', 'beta'], 'delete line')
    fixture(['alpha', 'beta'], col=2)
    keys('i')
    keys('<D-d>')
    equal(lines(), ['alpha', 'alpha', 'beta'], 'duplicate in typing mode')
    equal(lua('return vim.fn.mode()'), 'i', 'duplicate preserves typing')
    keys('X')
    equal(lines(), ['alpha', 'alXpha', 'beta'], 'typing after duplicate')
    keys('<D-Left>')
    equal(lua('return vim.fn.mode()'), 'i', 'navigation preserves typing')
    keys('Y')
    equal(lines(), ['alpha', 'YalXpha', 'beta'], 'Command-left reaches line start')
    keys('<D-Right>')
    keys('Z')
    equal(lines(), ['alpha', 'YalXphaZ', 'beta'], 'Command-right reaches after final character')
    fixture(['alpha'])
    keys('i<D-d>')
    keys('<D-z>')
    equal(lines(), ['alpha'], 'undo editing shortcut')
    keys('<D-S-z>')
    equal(lines(), ['alpha', 'alpha'], 'redo editing shortcut')
    fixture(['alpha beta'])
    keys('i<D-S-Right>')
    equal(lua('return vim.fn.mode()'), 's', 'Command-shift-right selects')
    keys('X')
    equal(lines(), ['X'], 'typing replaces selected line')
    fixture(['alpha beta'])
    keys('i<S-Right><S-Right>')
    keys('X')
    equal(lines(), ['Xpha beta'], 'Shift-arrow replacement')
    fixture(['alpha beta'])
    keys('i<M-S-Right>')
    keys('X')
    equal(lines(), ['X beta'], 'Option-shift-right selects word')
    fixture(['alpha', 'beta'])
    keys('<M-S-Down>')
    equal(lines(), ['beta', 'alpha'], 'move line down')
    keys('<M-S-Up>')
    equal(lines(), ['alpha', 'beta'], 'move line up')
    fixture(['local a = 1', 'local b = 2'])
    keys('<D-/>')
    equal(lines(), ['-- local a = 1', 'local b = 2'], 'comment')
    keys('<D-/>')
    equal(lines(), ['local a = 1', 'local b = 2'], 'uncomment')
    fixture(['one two'])
    keys('i<M-Up>')
    equal(lua('return vim.fn.mode()'), 's', 'extend selection')
    keys('<M-Down>')
    equal(lua('return vim.fn.mode()'), 'i', 'shrink selection returns to typing')
    fixture(['abc'])
    lua('require("jetvim.edit").paste({"XYZ"}, "v"); return true')
    equal(lines(), ['XYZabc'], 'paste at caret')
    fixture(['hello world'], col=5)
    keys('i<D-CR>')
    equal(lines(), ['hello', ' world'], 'split at caret')
    fixture(['alpha', 'beta'])
    keys('<D-a>')
    keys('X')
    equal(lines(), ['X'], 'select all includes final character')
    fixture(['save test'])
    keys('<D-s>')
    equal(lua('return vim.bo.modified'), False, 'save all')
    fixture(['tree test'])
    keys('<D-1>')
    equal(lua('return vim.bo.filetype'), 'jetvim-tree', 'project shortcut focuses sidebar')
    keys('<Esc>')
    equal(lua('return vim.bo.filetype'), 'lua', 'Escape returns to editor')
    keys('<D-S-o>')
    equal(lua('return vim.bo.buftype'), 'prompt', 'Go to File opens picker')
    keys('README')
    time.sleep(0.05)
    keys('<CR>')
    equal(lua('return vim.fs.basename(vim.api.nvim_buf_get_name(0))'), 'README.md', 'file picker filters and opens')
    keys('<Esc>')
    keys('<D-S-a>')
    equal(lua('return vim.bo.buftype'), 'prompt', 'action picker opens')
    keys('<Esc>')
    equal(lua('return vim.bo.buftype'), '', 'picker cancel restores editor')
    fixture(['relay'])
    bindings = json.loads((ROOT / 'config/keymap.json').read_text())
    index = next(i for i, item in enumerate(bindings, 1) if item['id'] == 'duplicate')
    keys(chr(0xF0000 + index))
    equal(lines(), ['relay', 'relay'], 'decoded terminal relay key')
    equal(lua('return vim.v.errmsg'), '', 'no editor errors')
    print(f'PASS: {checks} integration checks')
finally:
    if process.poll() is None:
        try:
            lua('vim.cmd("qa!"); return true')
        except (AssertionError, subprocess.SubprocessError, json.JSONDecodeError):
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)
    log.close()
    SOCKET.unlink(missing_ok=True)
