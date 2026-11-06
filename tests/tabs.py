#!/usr/bin/env python3
"""Exercise editor-tab shortcuts, native CSI-u forms and relay bytes in a PTY."""
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import struct
import subprocess
import tempfile
import termios
import threading
import time

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / '.jetvim'
STATE.mkdir(exist_ok=True)
SOCKET = STATE / f'tabs-{os.getpid()}.sock'
master, slave = pty.openpty()
fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 120, 0, 0))
stop = threading.Event()
checks = 0


def drain():
    while not stop.is_set():
        ready, _, _ = select.select([master], [], [], 0.1)
        if ready:
            try:
                if not os.read(master, 65536):
                    break
            except OSError:
                break


def lua(code):
    expr = "json_encode(luaeval('(function() " + code.replace("'", "''") + " end)()'))"
    result = subprocess.run([str(ROOT / 'jetvim'), '--server', str(SOCKET), '--remote-expr', expr],
                            cwd=ROOT, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def equal(actual, expected, label):
    global checks
    assert actual == expected, f'{label}: expected {expected!r}, got {actual!r}'
    checks += 1


def keys(value):
    lua('return vim.api.nvim_input(' + json.dumps(value, ensure_ascii=False) + ')')
    time.sleep(0.06)


def raw(value):
    os.write(master, value)
    time.sleep(0.15)


def name():
    return lua('return vim.fs.basename(vim.api.nvim_buf_get_name(0))')


with tempfile.TemporaryDirectory(prefix='tabs-', dir=STATE) as directory:
    project = Path(directory)
    for file in ('one.lua', 'two.lua', 'three.lua'):
        (project / file).write_text('-- ' + file + '\n')
    process = subprocess.Popen([str(ROOT / 'jetvim'), directory, 'one.lua', 'two.lua', 'three.lua', '--listen', str(SOCKET)],
                               cwd=ROOT, stdin=slave, stdout=slave, stderr=slave,
                               env=dict(os.environ, TERM='xterm-256color'))
    os.close(slave)
    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    try:
        deadline = time.monotonic() + 10
        while not SOCKET.exists():
            if process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('Editor did not start')
            time.sleep(0.03)
        time.sleep(0.6)
        equal(lua('return vim.v.errmsg'), '', 'clean startup')
        equal(name(), 'one.lua', 'first editor')
        keys('<D-S-]>')
        equal(name(), 'two.lua', 'Command Shift ] advances')
        equal(lua('return vim.fn.mode()'), 'i', 'typing survives tab switch')
        keys('<D-S-[>')
        equal(name(), 'one.lua', 'Command Shift [ goes back')
        keys('<Esc>')
        keys('<D-S-[>')
        equal(name(), 'three.lua', 'previous wraps')
        equal(lua('return vim.fn.mode()'), 'n', 'normal mode survives tab switch')
        raw(b'\x1b[91;10u')
        equal(name(), 'two.lua', 'CSI-u unshifted bracket plus Super+Shift')
        raw(b'\x1b[93;10u')
        equal(name(), 'three.lua', 'CSI-u next unshifted bracket plus Super+Shift')
        raw(b'\x1b[123;9u')
        equal(name(), 'two.lua', 'CSI-u shifted left brace plus Super')
        raw(b'\x1b[125;9u')
        equal(name(), 'three.lua', 'CSI-u shifted right brace plus Super')
        bindings = json.loads((ROOT / 'config/keymap.json').read_text())
        for action, expected in [('previous_tab', 'two.lua'), ('next_tab', 'three.lua')]:
            index = next(i for i, item in enumerate(bindings, 1) if item['id'] == action)
            raw(f'\x1b[{0xF0000 + index}u'.encode())
            equal(name(), expected, 'relay ' + action)
        lua('local buf = vim.api.nvim_create_buf(true, false); vim.api.nvim_buf_call(buf, function() vim.fn.jobstart({"/usr/bin/true"}, {term=true}) end); return true')
        keys('<D-S-]>')
        equal(name(), 'one.lua', 'next skips listed terminal')
        keys('<D-S-[>')
        equal(name(), 'three.lua', 'previous skips listed terminal')
        lua('vim.api.nvim_buf_set_lines(0, 0, -1, false, {"unsaved"}); return true')
        keys('<D-S-]>')
        keys('<D-S-[>')
        equal(lua('return vim.api.nvim_buf_get_lines(0, 0, -1, false)'), ['unsaved'], 'switch preserves unsaved editor')
        keys('i')
        keys('<D-S-]>')
        keys('X')
        equal(name(), 'one.lua', 'typing targets switched editor')
        equal(lua('return vim.api.nvim_get_current_line()'), 'X-- one.lua', 'text inserted into active tab')
        keys('<Esc>')
        lua('vim.g.tabs_editor_win = vim.api.nvim_get_current_win(); vim.g.tabs_term_input = ""; '
            'vim.g.tabs_terminal = vim.api.nvim_create_buf(true, false); '
            'vim.api.nvim_open_term(vim.g.tabs_terminal, {on_input=function(_, _, _, data) vim.g.tabs_term_input = vim.g.tabs_term_input .. data end}); '
            'package.loaded["jetvim.git"] = {toggle=function() vim.g.tabs_git_routed = (vim.g.tabs_git_routed or 0) + 1 end}; return true')
        def terminal():
            lua('vim.api.nvim_set_current_win(vim.g.tabs_editor_win); vim.api.nvim_set_current_buf(vim.g.tabs_terminal); vim.cmd.startinsert(); return true')
            time.sleep(0.08)
            equal(lua('return vim.fn.mode()'), 't', 'internal terminal focused')
        terminal()
        raw(b'\x1b[49;9u')
        equal(lua('return vim.bo.filetype'), 'jetvim-tree', 'native Command1 leaves terminal for sidebar')
        terminal()
        raw(b'\x1b[983041u')
        equal(lua('return vim.bo.filetype'), 'jetvim-tree', 'relay Command1 leaves terminal for sidebar')
        terminal()
        raw(b'\x1b[57;9u')
        equal(lua('return vim.g.tabs_git_routed'), 1, 'native Command9 routes from terminal without running Git')
        equal(lua('return vim.fn.mode()'), 'n', 'Command9 exits terminal mode before action')
        terminal()
        git_index = next(i for i, item in enumerate(bindings, 1) if item['id'] == 'git_changes')
        raw(f'\x1b[{0xF0000 + git_index}u'.encode())
        equal(lua('return vim.g.tabs_git_routed'), 2, 'relay Command9 routes from terminal without running Git')
        equal(lua('return vim.g.tabs_term_input'), '', 'tool window shortcuts never leak to terminal input')
        equal(lua('return vim.v.errmsg'), '', 'no editor errors')
        print(f'PASS: {checks} tab shortcut checks, including native PTY bytes and terminal skipping')
    finally:
        if process.poll() is None:
            try:
                lua('vim.cmd("qa!"); return true')
            except Exception:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=5)
        stop.set()
        reader.join(timeout=2)
        os.close(master)
        SOCKET.unlink(missing_ok=True)
