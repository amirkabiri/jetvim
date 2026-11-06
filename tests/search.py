#!/usr/bin/env python3
"""Exercise inline regex search and project search through native/relay PTY keys."""
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
SOCKET = STATE / f'search-{os.getpid()}.sock'
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


with tempfile.TemporaryDirectory(prefix='search-project-', dir=STATE) as directory:
    project = Path(directory)
    content = ['hello HELLO hello', 'world', 'héllo hello', 'last hello']
    (project / 'main.txt').write_text('\n'.join(content) + '\n')
    process = subprocess.Popen([str(ROOT / 'jetvim'), directory, 'main.txt', '--listen', str(SOCKET)],
                               cwd=ROOT, stdin=slave, stdout=slave, stderr=slave,
                               env=dict(os.environ, TERM='xterm-256color', JETVIM_DISABLE_VCS='1', JETVIM_DISABLE_AUTOSAVE='1'))
    os.close(slave)
    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    try:
        deadline = time.monotonic() + 10
        while not SOCKET.exists():
            assert process.poll() is None and time.monotonic() < deadline, 'editor did not start'
            time.sleep(0.03)
        time.sleep(0.5)
        lua('vim.g.search_owner=vim.api.nvim_get_current_win(); vim.g.search_source=vim.api.nvim_get_current_buf(); return true')
        windows = lua('return #vim.api.nvim_list_wins()')
        widths = lua('return {vim.api.nvim_win_get_width(0), vim.api.nvim_win_get_width(require("jetvim.tree").win)}')
        raw(b'\x1b[102;9u')
        equal(lua('return vim.bo.filetype'), 'jetvim-search', 'native CommandF focuses inline input')
        equal(lua('local s=require("jetvim.search"); local c=vim.api.nvim_win_get_config(s.win); return {c.relative,c.win,c.row,c.height}'),
              ['win', lua('return vim.g.search_owner'), 0, 1], 'one row at top of active editor')
        raw(b'hello')
        equal(lua('return #require("jetvim.search").matches'), 4, 'incremental plain regex matches')
        equal(lua('return vim.api.nvim_buf_get_lines(vim.g.search_source,0,-1,false)'), content, 'query never edits source')
        equal(lua('return vim.api.nvim_win_get_cursor(vim.g.search_owner)'), [1,0], 'initial match at caret')
        raw(b'\r')
        equal(lua('return vim.api.nvim_win_get_cursor(vim.g.search_owner)'), [1,12], 'Enter advances while field remains open')
        keys('<S-CR>')
        equal(lua('return vim.api.nvim_win_get_cursor(vim.g.search_owner)'), [1,0], 'Shift Enter goes backwards')
        raw(b'\x1b[103;9u')
        equal(lua('return vim.api.nvim_win_get_cursor(vim.g.search_owner)'), [1,12], 'CommandG advances while input focused')
        equal(lua('return vim.fn.mode()'), 'i', 'CommandG preserves search input typing')
        raw(b'\x1b[103;10u')
        equal(lua('return vim.api.nvim_win_get_cursor(vim.g.search_owner)'), [1,0], 'CommandShiftG moves backwards in input')
        keys('<C-u>')
        raw(b'/hello/i')
        equal(lua('return #require("jetvim.search").matches'), 5, 'slash regex i flag ignores case')
        keys('<C-u>')
        raw(b'h(ello|i)')
        equal(lua('return #require("jetvim.search").matches'), 4, 'regex grouping and alternatives')
        keys('<C-u>')
        raw(b'[')
        equal(lua('return require("jetvim.search").error ~= nil'), True, 'invalid regex handled inline')
        equal(lua('return vim.api.nvim_buf_get_lines(require("jetvim.search").status_buf,0,1,false)[1]:find("Invalid regex",1,true) ~= nil'), True, 'invalid regex visible status')
        equal(lua('return vim.v.errmsg'), '', 'invalid regex never opens error prompt')
        keys('<C-u>')
        raw(b'/hello/g')
        equal(lua('return require("jetvim.search").error:find("Invalid regex flag",1,true) ~= nil'), True, 'unsupported flags visible')
        keys('<C-u>')
        raw(b'^')
        equal(lua('return #require("jetvim.search").matches'), 4, 'zero width regex terminates and matches line starts')
        keys('<C-u>')
        raw('héllo'.encode())
        equal(lua('return #require("jetvim.search").matches'), 1, 'UTF8 regex matches without byte corruption')
        lua('local s=require("jetvim.search"); vim.api.nvim_win_set_width(s.owner,vim.api.nvim_win_get_width(s.owner)-5); return true')
        time.sleep(0.15)
        equal(lua('local s=require("jetvim.search"); return vim.api.nvim_win_get_width(s.win)+vim.api.nvim_win_get_width(s.status_win)==vim.api.nvim_win_get_width(s.owner)'), True, 'search bar follows editor resize')
        lua('vim.api.nvim_win_set_width(require("jetvim.search").owner,' + str(widths[0]) + '); return true')
        keys('<C-u>')
        raw(b'hello')
        keys('<CR>')
        keys('<Esc>')
        time.sleep(0.1)
        equal(lua('return vim.api.nvim_get_current_win()'), lua('return vim.g.search_owner'), 'Escape returns editor focus')
        equal(lua('return vim.api.nvim_win_get_cursor(vim.g.search_owner)'), [1,12], 'Escape keeps selected match caret')
        equal(lua('return #vim.api.nvim_list_wins()'), windows, 'no leaked search windows')
        equal(lua('return {vim.api.nvim_win_get_width(0),vim.api.nvim_win_get_width(require("jetvim.tree").win)}'), widths, 'search preserves split dimensions')
        equal(lua('local n=0; for _,b in ipairs(vim.api.nvim_list_bufs()) do if vim.bo[b].filetype=="jetvim-search" then n=n+1 end end; return n'), 0, 'no leaked search buffers')
        lua('vim.api.nvim_win_set_cursor(0,{1,6}); return true')
        raw(b'\x1b[103;9u')
        equal(lua('return vim.api.nvim_win_get_cursor(vim.g.search_owner)'), [1,12], 'CommandG continues after close')
        bindings=json.loads((ROOT/'config/keymap.json').read_text())
        index=next(i for i,item in enumerate(bindings,1) if item['id']=='find')
        raw(f'\x1b[{0xF0000+index}u'.encode())
        equal(lua('return vim.bo.filetype'), 'jetvim-search', 'relay CommandF opens inline input')
        keys('<Esc>')
        # Find in Files must route from tree, rather than becoming speed-search text.
        lua('require("jetvim.tree").focus(); return true')
        lua('_G.search_original_executable=vim.fn.executable; vim.fn.executable=function(name) if name=="rg" then return 0 end; return _G.search_original_executable(name) end; return true')
        raw(b'\x1b[102;10u')
        equal(lua('return vim.fn.mode()'), 'c', 'native CommandShiftF opens project prompt from tree')
        keys('<Esc>')
        lua('require("jetvim.tree").focus(); return true')
        raw(b'mai')
        raw(b'\x1b[70;9u')
        equal(lua('return vim.fn.mode()'), 'c', 'capital-letter native CommandShiftF routes during tree speed search')
        keys('<Esc>')
        lua('require("jetvim.tree").focus(); return true')
        index=next(i for i,item in enumerate(bindings,1) if item['id']=='find_project')
        raw(f'\x1b[{0xF0000+index}u'.encode())
        equal(lua('return vim.fn.mode()'), 'c', 'relay CommandShiftF opens project prompt from tree')
        keys('<Esc>')
        equal(lua('return require("jetvim.tree").query'), 'mai', 'project shortcut never adds tree search text')
        lua('vim.fn.executable=_G.search_original_executable; return true')
        equal(lua('return vim.v.errmsg'), '', 'clean error state')
        print(f'PASS: {checks} search and project shortcut checks')
    finally:
        subprocess.run([str(ROOT/'jetvim'),'--server',str(SOCKET),'--remote-send','<Esc>:qa!<CR>'], cwd=ROOT,capture_output=True)
        try: process.wait(timeout=4)
        except subprocess.TimeoutExpired: process.kill(); process.wait()
        stop.set(); reader.join(timeout=1); os.close(master)
        if SOCKET.exists(): SOCKET.unlink()
