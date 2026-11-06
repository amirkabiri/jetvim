#!/usr/bin/env python3
"""Verify Fn-arrow/PageUp/PageDown using real terminal bytes and editor modes."""
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import struct
import subprocess
import termios
import threading
import time

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / '.jetvim'
STATE.mkdir(exist_ok=True)
SOCKET = STATE / f'paging-{os.getpid()}.sock'
master, slave = pty.openpty()
fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 35, 120, 0, 0))
env = dict(os.environ, TERM='xterm-256color', JETVIM_DISABLE_VCS='1')
process = subprocess.Popen([str(ROOT / 'jetvim'), '--listen', str(SOCKET)], cwd=ROOT,
                           stdin=slave, stdout=slave, stderr=slave, env=env)
os.close(slave)
stop = threading.Event()
output = bytearray()
checks = 0


def drain():
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


reader = threading.Thread(target=drain, daemon=True)
reader.start()


def lua(code):
    expr = "json_encode(luaeval('(function() " + code.replace("'", "''") + " end)()'))"
    result = subprocess.run([str(ROOT / 'jetvim'), '--server', str(SOCKET), '--remote-expr', expr],
                            cwd=ROOT, capture_output=True, text=True, timeout=10, env=env)
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return json.loads(result.stdout)


def equal(actual, expected, label):
    global checks
    assert actual == expected, f'{label}: expected {expected!r}, got {actual!r}'
    checks += 1


def send(data):
    os.write(master, data)
    time.sleep(0.07)


def fixture(lines, row=1, col=0):
    normal_mode()
    lua('vim.cmd.enew({bang=true}); vim.api.nvim_buf_set_name(0, vim.env.JETVIM_ROOT .. "/.jetvim/paging-fixture-" .. vim.fn.getpid() .. "-" .. vim.api.nvim_get_current_buf()); '
        'vim.api.nvim_buf_set_lines(0,0,-1,false,vim.json.decode(' + json.dumps(json.dumps(lines)) + ')); '
        f'vim.api.nvim_win_set_cursor(0, {{{row},{col}}}); return true')


def cursor():
    return lua('return vim.api.nvim_win_get_cursor(0)')


def normal_mode():
    # CSI-u Escape is unambiguous; a bare ESC may still be waiting for the
    # terminal timeout and would later move the caret after the fixture sets it.
    send(b'\x1b[27u')
    deadline = time.monotonic() + 2
    while lua('return vim.fn.mode()') != 'n':
        if time.monotonic() > deadline:
            raise AssertionError('Escape did not leave insert/selection mode')
        time.sleep(0.02)


def page(direction):
    # macOS terminals normally translate Fn-Up/Fn-Down into these legacy keys.
    send(b'\x1b[5~' if direction == -1 else b'\x1b[6~')


try:
    deadline = time.monotonic() + 10
    while not SOCKET.exists():
        if process.poll() is not None or time.monotonic() > deadline:
            raise RuntimeError('TUI startup failed')
        time.sleep(0.03)
    time.sleep(0.6)
    equal(lua('return vim.v.errmsg'), '', 'clean startup')
    fixture(['0123456789abcdefghij'] * 200, row=2, col=8)
    equal(lua('return vim.fn.maparg("<PageUp>","n") ~= ""'), True, 'PageUp mapping exists')
    equal(lua('return vim.fn.maparg("<PageDown>","i") ~= ""'), True, 'insert PageDown mapping exists')
    page(-1)
    equal(cursor(), [1, 8], 'second line PageUp reaches first line')
    page(-1)
    equal(cursor(), [1, 8], 'PageUp stays at top')
    equal(lua('return vim.fn.mode()'), 'n', 'normal paging stays normal')
    lua('vim.api.nvim_win_set_cursor(0,{199,8}); return true')
    page(1)
    equal(cursor(), [200, 8], 'penultimate line PageDown reaches last line')
    page(1)
    equal(cursor(), [200, 8], 'PageDown stays at bottom')
    lua('vim.api.nvim_win_set_cursor(0,{50,8}); return true')
    step = lua('return math.max(1,vim.api.nvim_win_get_height(0)-2)')
    page(1)
    equal(cursor(), [50 + step, 8], 'page moves editor text height with overlap')
    page(-1)
    equal(cursor(), [50, 8], 'opposite page returns same row/column')
    for _ in range(10):
        page(1)
    equal(cursor(), [200, 8], 'repeated pages clamp bottom')
    for _ in range(10):
        page(-1)
    equal(cursor(), [1, 8], 'repeated pages clamp top')
    fixture(['one', 'two', 'three'], row=2, col=1)
    page(-1)
    equal(cursor(), [1, 1], 'short file PageUp reaches first')
    page(1)
    equal(cursor(), [3, 1], 'short file PageDown reaches last')
    fixture([''])
    page(-1)
    page(1)
    equal(cursor(), [1, 0], 'empty buffer remains valid')
    # Preferred visual column survives clipping by short lines in either direction.
    lines = ['0123456789abcdefghij'] * 150
    lines[2 + step] = 'x'
    fixture(lines, row=3, col=12)
    page(1)
    equal(cursor(), [3 + step, 1], 'short target clamps column to line end')
    page(1)
    equal(cursor(), [3 + 2 * step, 12], 'preferred column returns on long line')
    page(-1)
    equal(cursor(), [3 + step, 1], 'reverse page clips same short line')
    page(-1)
    equal(cursor(), [3, 12], 'reverse page restores preferred column')
    page(1)
    send(b'h')
    page(1)
    equal(cursor(), [3 + 2 * step, 0], 'manual horizontal movement resets preferred column')
    # Display columns differ from UTF-8 byte offsets and from tab byte positions.
    lines = ['0123456789abcdefghij'] * 150
    lines[2 + step] = 'ab界caféZ'
    fixture(lines, row=3, col=7)
    page(1)
    equal(cursor(), [3 + step, len('ab界caf'.encode())], 'wide/Unicode destination uses visual column')
    page(1)
    equal(cursor(), [3 + 2 * step, 7], 'Unicode line does not corrupt preferred column')
    lines[2 + step] = '\tABCD'
    fixture(lines, row=3, col=5)
    lua('vim.bo.tabstop=4; return true')
    page(1)
    equal(cursor(), [3 + step, 2], 'tab destination uses visual column')
    page(1)
    equal(cursor(), [3 + 2 * step, 5], 'tab line does not corrupt preferred column')
    # Native terminal page keys must preserve typing mode and subsequent edits.
    fixture(['0123456789abcdefghij'] * 150, row=2, col=7)
    send(b'i')
    page(-1)
    equal(cursor(), [1, 7], 'typing PageUp reaches first line')
    equal(lua('return vim.fn.mode()'), 'i', 'PageUp preserves typing mode')
    page(1)
    equal(cursor(), [1 + step, 7], 'typing PageDown moves page')
    equal(lua('return vim.fn.mode()'), 'i', 'PageDown preserves typing mode')
    send(b'X')
    equal(lua('return vim.api.nvim_get_current_line()'), '0123456X789abcdefghij', 'typing after page inserts at expected caret')
    # Also exercise Neovim's direct key path independently of PTY decoding.
    normal_mode()
    lua('vim.api.nvim_win_set_cursor(0,{2,2}); vim.api.nvim_input("<PageUp>"); return true')
    time.sleep(0.07)
    equal(cursor(), [1, 2], 'direct PageUp path clamps first line')
    equal(lua('return vim.v.errmsg'), '', 'no editor errors')
    print(f'PASS: {checks} paging checks using native CSI PageUp/PageDown bytes and direct keys')
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
    (STATE / 'paging-output.log').write_bytes(output)
    os.close(master)
    SOCKET.unlink(missing_ok=True)
