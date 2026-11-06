#!/usr/bin/env python3
"""Verify Option-Backspace PTY bytes and real shell readline word deletion."""
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import shutil
import struct
import subprocess
import tempfile
import termios
import threading
import time

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / '.jetvim'
STATE.mkdir(exist_ok=True)
SOCKET = STATE / f'terminal-keys-{os.getpid()}.sock'
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


def wait_file(path):
    deadline = time.monotonic() + 5
    while not path.exists():
        assert time.monotonic() < deadline, 'child did not create ' + path.name
        time.sleep(0.03)


with tempfile.TemporaryDirectory(prefix='terminal-keys-', dir=STATE) as directory:
    project = Path(directory)
    (project / 'editor.txt').write_text('keep editor unchanged\n')
    capture = project / 'capture.py'
    capture.write_text("""import os,sys,tty
from pathlib import Path
tty.setraw(0)
Path(sys.argv[1]).write_text('ready')
data=b''
while not data.endswith((b'\\r',b'\\n')):
 data += os.read(0,4096)
Path(sys.argv[2]).write_bytes(data)
""")
    inputrc = project / 'inputrc'
    inputrc.write_text('set editing-mode emacs\n')
    shell_script = project / 'readline.sh'
    shell_script.write_text("""#!/usr/bin/env bash
bind '"\\C-w": backward-kill-word'
printf ready > "$1"
IFS= read -e -r -p 'fixture> ' line
printf '%s' "$line" > "$2"
""")
    process = subprocess.Popen([str(ROOT/'jetvim'),directory,'editor.txt','--listen',str(SOCKET)],
                               cwd=ROOT,stdin=slave,stdout=slave,stderr=slave,
                               env=dict(os.environ,TERM='xterm-256color',JETVIM_DISABLE_VCS='1',JETVIM_DISABLE_AUTOSAVE='1',INPUTRC=str(inputrc),HISTFILE=str(project/'history')))
    os.close(slave)
    reader = threading.Thread(target=drain,daemon=True); reader.start()
    try:
        deadline=time.monotonic()+10
        while not SOCKET.exists():
            assert process.poll() is None and time.monotonic()<deadline, 'editor startup'
            time.sleep(.03)
        time.sleep(.4)
        lua('vim.g.terminal_keys_source=vim.api.nvim_get_current_buf(); return true')
        bindings=json.loads((ROOT/'config/keymap.json').read_text())
        index=next(i for i,item in enumerate(bindings,1) if item['id']=='delete_word_left')
        variants=[('CSI-u mac Delete/Backspace',b'\x1b[127;3u'),('CSI-u Alt CtrlH Backspace',b'\x1b[8;3u'),
                  ('legacy Alt Backspace',b'\x1b\x7f'),('bridge relay',f'\x1b[{0xF0000+index}u'.encode()),
                  ('existing CtrlW',b'\x17')]
        def start(argv,ready):
            lua('vim.cmd.stopinsert(); return true')
            time.sleep(.04)
            lua('require("jetvim.tree").editor(); '
                'vim.api.nvim_set_current_buf(vim.g.terminal_keys_source); vim.cmd.enew(); '
                'vim.fn.jobstart(vim.json.decode('+json.dumps(json.dumps(argv))+'),{term=true}); vim.cmd.startinsert(); return true')
            wait_file(ready)
            time.sleep(.08)
            equal(lua('return vim.fn.mode()'),'t','child terminal input active')
        import sys
        for number,(label,chord) in enumerate(variants):
            ready,result=project/f'capture-{number}.ready',project/f'capture-{number}.bytes'
            start([sys.executable,str(capture),str(ready),str(result)],ready)
            raw(b'alpha beta gamma')
            raw(chord)
            equal(lua('return vim.fn.mode()'),'t',label+' keeps terminal input')
            raw(b'X\r'); wait_file(result)
            equal(list(result.read_bytes()),list(b'alpha beta gamma\x17X\r'),label+' sends exactly one CtrlW without extra space or escape bytes')
        bash=shutil.which('bash')
        assert bash,'bash is required for readline regression'
        for number,(label,chord) in enumerate(variants):
            ready,result=project/f'shell-{number}.ready',project/f'shell-{number}.result'
            start([bash,'--noprofile','--norc',str(shell_script),str(ready),str(result)],ready)
            raw(b'alpha beta gamma')
            raw(chord)
            raw(b'X\r'); wait_file(result)
            equal(result.read_text(),'alpha beta X',label+' deletes preceding shell word without extra whitespace')
        equal(lua('return vim.api.nvim_buf_get_lines(vim.g.terminal_keys_source,0,-1,false)'),['keep editor unchanged'],'terminal shortcuts never edit source buffer')
        equal(lua('return vim.v.errmsg'),'','no editor errors')
        print(f'PASS: {checks} terminal key transport and real Bash readline checks')
    finally:
        if process.poll() is None:
            try: lua('vim.cmd("qa!"); return true')
            except Exception: pass
            try: process.wait(timeout=4)
            except subprocess.TimeoutExpired: process.terminate();process.wait(timeout=4)
        stop.set();reader.join(timeout=2);os.close(master);SOCKET.unlink(missing_ok=True)
