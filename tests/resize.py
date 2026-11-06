#!/usr/bin/env python3
"""Resize real Neovim panes through native terminal keys and relay sequences."""
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
SOCKET = STATE / f'resize-{os.getpid()}.sock'
ENV = dict(os.environ, TERM='xterm-256color', JETVIM_DISABLE_VCS='1')
checks = 0


def lua(code):
    expression = "json_encode(luaeval('(function() " + code.replace("'", "''") + " end)()'))"
    result = subprocess.run([str(ROOT / 'jetvim'), '--server', str(SOCKET), '--remote-expr', expression],
                            cwd=ROOT, env=ENV, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def equal(actual, expected, label):
    global checks
    assert actual == expected, f'{label}: expected {expected!r}, got {actual!r}'
    checks += 1


def wait(code, expected, label):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        actual = lua(code)
        if actual == expected:
            equal(actual, expected, label)
            return
        time.sleep(0.025)
    equal(actual, expected, label)


with tempfile.TemporaryDirectory(prefix='resize-', dir=STATE) as folder:
    project = Path(folder)
    for filename in ('one.lua', 'two.lua'):
        (project / filename).write_text('-- ' + filename + '\n')
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 40, 140, 0, 0))
    process = subprocess.Popen([str(ROOT / 'jetvim'), folder, 'one.lua', 'two.lua', '--listen', str(SOCKET),
                                '-c', 'lua vim.g.resize_ready=true'],
                               cwd=ROOT, env=ENV, stdin=slave, stdout=slave, stderr=slave)
    os.close(slave)
    stop, output = threading.Event(), bytearray()

    def drain():
        pending = b''
        replies = {
            b'\x1b]10;?\x07': b'\x1b]10;rgb:bcbc/bebe/c4c4\x07',
            b'\x1b]11;?\x07': b'\x1b]11;rgb:1e1e/1f1f/2222\x07',
            b'\x1b[5n': b'\x1b[0n', b'\x1b[6n': b'\x1b[1;1R',
            b'\x1b[c': b'\x1b[?1;2c', b'\x1b[?u': b'\x1b[?0u',
        }
        while not stop.is_set():
            readable, _, _ = select.select([master], [], [], 0.1)
            if readable:
                try:
                    data = os.read(master, 65536)
                except OSError:
                    break
                if not data:
                    break
                output.extend(data)
                pending += data
                while True:
                    matches = [(pending.find(query), query) for query in replies if query in pending]
                    if not matches:
                        pending = pending[-64:]
                        break
                    index, query = min(matches, key=lambda pair: pair[0])
                    try:
                        os.write(master, replies[query])
                    except OSError:
                        return
                    pending = pending[index + len(query):]

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()

    def raw(data):
        os.write(master, data)
        time.sleep(0.09)

    def key(direction):
        raw(b'\x1b[1;7' + {'left': b'D', 'right': b'C', 'up': b'A', 'down': b'B'}[direction])

    def width(win):
        return lua(f'return vim.api.nvim_win_get_width({win})')

    def height(win):
        return lua(f'return vim.api.nvim_win_get_height({win})')

    def focus(win, typing=False):
        raw(b'\x1c\x0e')
        wait('return vim.fn.mode()', 'n', 'setup enters normal mode')
        lua(f'vim.api.nvim_set_current_win({win}); return true')
        if typing:
            raw(b'i')

    try:
        deadline = time.monotonic() + 10
        while not SOCKET.exists():
            assert process.poll() is None and time.monotonic() < deadline, 'editor failed to start'
            time.sleep(0.03)
        wait('return vim.g.resize_ready == true', True, 'editor initialization complete')
        wait('return vim.fs.basename(vim.api.nvim_buf_get_name(0))', 'one.lua', 'file loaded')
        tree = lua('return require("jetvim.tree").win')
        editor = lua('return vim.api.nvim_get_current_win()')
        focus(tree)
        before = width(tree)
        key('right')
        equal(width(tree), before + 4, 'native CtrlOptionRight grows left sidebar')
        equal(lua('return vim.api.nvim_get_current_win()'), tree, 'sidebar resize keeps focus')
        key('left')
        equal(width(tree), before, 'native CtrlOptionLeft shrinks sidebar')
        sidebar_height = height(tree)
        key('up')
        key('down')
        equal(height(tree), sidebar_height, 'unavailable vertical divider is a no-op')
        equal(lua('return require("jetvim.tree").query'), '', 'resize keys do not enter sidebar search')
        focus(editor, True)
        editor_width = width(editor)
        key('left')
        equal(width(editor), editor_width + 4, 'editor stretches toward left divider')
        equal(width(tree), before - 4, 'editor left growth takes sidebar space')
        equal(lua('return vim.fn.mode()'), 'i', 'resize preserves typing mode')
        key('right')
        equal(width(editor), editor_width, 'editor right shrinks back toward outside edge')
        raw(b'X')
        equal(lua('return vim.api.nvim_get_current_line()'), 'X-- one.lua', 'typing remains at same caret after resize')
        raw(b'\x1b[27u')
        raw(b'\x1b[1;5C')
        equal(lua('return vim.fs.basename(vim.api.nvim_buf_get_name(0))'), 'two.lua', 'CtrlRight retains next-tab action')
        raw(b'\x1b[1;5D')
        equal(lua('return vim.fs.basename(vim.api.nvim_buf_get_name(0))'), 'one.lua', 'CtrlLeft retains previous-tab action')
        lua('vim.api.nvim_win_set_cursor(0,{1,2}); return true')
        raw(b'\x1b[1;3A')
        equal(lua('return vim.fn.mode()'), 's', 'OptionUp retains structural selection')
        selection = lua('return require("jetvim.edit").selection()')
        key('left')
        equal(lua('return vim.fn.mode()'), 's', 'resizing preserves select mode')
        equal(lua('return require("jetvim.edit").selection()'), selection, 'resizing preserves selected text range')
        key('right')
        raw(b'\x1b[1;3B')
        equal(lua('return require("jetvim.edit").selection() == nil'), True, 'OptionDown retains selection shrinking')

        focus(editor)
        tool = lua('vim.cmd("botright 10split"); local w=vim.api.nvim_get_current_win(); local b=vim.api.nvim_create_buf(false,true); vim.api.nvim_win_set_buf(w,b); return w')
        before_height = height(tool)
        key('up')
        equal(height(tool), before_height + 2, 'bottom tool grows upward')
        equal(lua('return vim.api.nvim_get_current_win()'), tool, 'vertical resize keeps tool focus')
        key('down')
        equal(height(tool), before_height, 'bottom tool shrinks downward')
        full_width = width(tool)
        key('left')
        key('right')
        equal(width(tool), full_width, 'full-width bottom tool has no horizontal divider')
        focus(editor)
        top_height = height(editor)
        key('down')
        equal(height(editor), top_height + 2, 'top editor grows down into bottom tool')
        key('up')
        equal(height(editor), top_height, 'top editor shrinks upward')

        focus(tool)
        preview = lua('vim.cmd("rightbelow vsplit"); local w=vim.api.nvim_get_current_win(); vim.api.nvim_win_set_buf(w,vim.api.nvim_create_buf(false,true)); return w')
        preview_width = width(preview)
        list_width = width(tool)
        key('left')
        equal(width(preview), preview_width + 4, 'right tool column grows toward its left neighbor')
        equal(width(tool), list_width - 4, 'right tool growth takes left tool width')
        key('right')
        equal(width(preview), preview_width, 'right tool column restores size')
        equal(width(tree), before, 'bottom column resizing does not change sidebar width')

        lua('vim.g.resize_term_input=""; local b=vim.api.nvim_create_buf(false,true); '
            'vim.api.nvim_open_term(b,{on_input=function(_,_,_,data) vim.g.resize_term_input=vim.g.resize_term_input..data end}); '
            'vim.api.nvim_set_current_buf(b); vim.cmd.startinsert(); return true')
        wait('return vim.fn.mode()', 't', 'internal terminal receives focus')
        key('left')
        equal(width(preview), preview_width + 4, 'native resize works in terminal input')
        equal(lua('return vim.fn.mode()'), 't', 'terminal input mode restored after native resize')
        bindings = json.loads((ROOT / 'config/keymap.json').read_text())
        index = next(i for i, binding in enumerate(bindings, 1) if binding['id'] == 'resize_right')
        raw(f'\x1b[{0xF0000 + index}u'.encode())
        equal(width(preview), preview_width, 'relay resize works in terminal input')
        equal(lua('return vim.fn.mode()'), 't', 'terminal input mode restored after relay resize')
        equal(lua('return vim.g.resize_term_input'), '', 'resize shortcuts never leak into terminal process')
        focus(preview)
        for _ in range(40):
            key('left')
        equal(width(tool), 10, 'repeated growth respects neighboring minimum width')
        limit_width = width(preview)
        key('left')
        equal(width(preview), limit_width, 'resize is harmless at minimum limit')
        for _ in range(20):
            key('down')
        equal(height(preview), 3, 'repeated shrink respects minimum height')
        equal(height(tool), 3, 'shared bottom group retains consistent height')
        equal(lua('return vim.api.nvim_get_current_win()'), preview, 'limits never change focus')

        lua('vim.cmd.tabnew(); return true')
        solo = lua('return vim.api.nvim_get_current_win()')
        geometry = [width(solo), height(solo)]
        for direction in ('left', 'right', 'up', 'down'):
            key(direction)
        equal([width(solo), height(solo)], geometry, 'single pane resizing is a no-op')
        equal(lua('return #vim.api.nvim_tabpage_list_wins(0)'), 1, 'resize never creates panes')
        panes = lua('vim.cmd("vsplit"); vim.cmd("vsplit"); local wins=vim.api.nvim_tabpage_list_wins(0); '
                    'table.sort(wins,function(a,b) return vim.api.nvim_win_get_position(a)[2]<vim.api.nvim_win_get_position(b)[2] end); return wins')
        left, middle, right = panes
        focus(middle)
        left_width, middle_width, right_width = width(left), width(middle), width(right)
        key('left')
        equal(width(middle), middle_width + 4, 'middle pane grows left toward specified divider')
        equal(width(left), left_width - 4, 'middle left growth takes left neighbor')
        equal(width(right), right_width, 'middle left growth does not take right neighbor')
        key('right')
        equal(width(middle), middle_width + 8, 'middle pane can also grow right')
        equal(width(right), right_width - 4, 'middle right growth takes right neighbor')
        equal(width(left), left_width - 4, 'middle right growth leaves left neighbor unchanged')
        floating = lua('return vim.api.nvim_open_win(vim.api.nvim_create_buf(false,true),true,{relative="editor",row=3,col=3,width=20,height=3,style="minimal"})')
        for direction in ('left', 'right', 'up', 'down'):
            key(direction)
        equal([width(floating), height(floating)], [20, 3], 'floating dialog resize is intentionally a no-op')
        equal(lua('return vim.api.nvim_get_current_win()'), floating, 'floating dialog keeps focus')
        equal(lua('return vim.v.errmsg'), '', 'no editor errors')
        print(f'PASS: {checks} keyboard resize checks through native and relay PTY input')
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
        (STATE / 'resize-output.log').write_bytes(output)
        os.close(master)
        SOCKET.unlink(missing_ok=True)
