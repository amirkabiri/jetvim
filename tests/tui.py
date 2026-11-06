#!/usr/bin/env python3
"""Check startup layout and real PTY bytes, rather than only nvim_input keys."""
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
SOCKET = ROOT / '.jetvim' / f'tui-{os.getpid()}.sock'
master, slave = pty.openpty()
fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 35, 120, 0, 0))
env = dict(os.environ, TERM='xterm-256color')
process = subprocess.Popen([str(ROOT / 'jetvim'), '--listen', str(SOCKET)],
                           cwd=ROOT, stdin=slave, stdout=slave, stderr=slave, env=env)
os.close(slave)
stop = threading.Event()
output = bytearray()


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
                            cwd=ROOT, capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


try:
    deadline = time.monotonic() + 10
    while not SOCKET.exists():
        if time.monotonic() > deadline or process.poll() is not None:
            raise RuntimeError('TUI startup failed')
        time.sleep(0.05)
    time.sleep(0.8)
    assert lua('return vim.v.errmsg') == ''
    assert lua('return #vim.api.nvim_list_wins()') == 2
    screen = lua('local rows = {}; for r = 1, vim.o.lines do local s = {}; for c = 1, vim.o.columns do s[#s + 1] = vim.fn.screenstring(r, c) end; rows[#rows + 1] = table.concat(s) end; return rows')
    (ROOT / '.jetvim/tui-screen.txt').write_text('\n'.join(screen) + '\n')
    assert any('Project' in row for row in screen), screen
    assert any('J E T V I M' in row for row in screen), screen
    lua('vim.cmd.enew(); vim.api.nvim_buf_set_name(0, vim.env.JETVIM_ROOT .. "/.jetvim/tui-fixture.lua"); vim.api.nvim_buf_set_lines(0, 0, -1, false, {"relay"}); return true')
    bindings = json.loads((ROOT / 'config/keymap.json').read_text())
    duplicate = next(i for i, item in enumerate(bindings, 1) if item['id'] == 'duplicate')
    os.write(master, f'\x1b[{0xF0000 + duplicate}u'.encode())
    time.sleep(0.3)
    assert lua('return vim.api.nvim_buf_get_lines(0, 0, -1, false)') == ['relay', 'relay'], 'terminal transport did not invoke duplicate'
    os.write(master, b'iX')
    time.sleep(0.1)
    os.write(master, f'\x1b[{0xF0000 + duplicate}u'.encode())
    time.sleep(0.3)
    assert lua('return vim.api.nvim_buf_get_lines(0, 0, -1, false)') == ['relay', 'Xrelay', 'Xrelay']
    assert lua('return vim.fn.mode()') == 'i'
    # CSI u with the Super modifier is the native Command key path.
    os.write(master, b'\x1b[100;9u')
    time.sleep(0.3)
    assert lua('return vim.api.nvim_buf_line_count(0)') == 4, 'native Command-D was not decoded'
    os.write(master, b'\x1b[983041u')
    time.sleep(0.3)
    assert lua('return vim.bo.filetype') == 'jetvim-tree', 'Command-1 relay did not focus project'
    assert lua('return vim.v.errmsg') == ''
    print('PASS: live TUI startup, layout, PTY editing and sidebar relay')
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
    (ROOT / '.jetvim/tui-output.log').write_bytes(output)
    os.close(master)
    SOCKET.unlink(missing_ok=True)
