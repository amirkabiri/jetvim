#!/usr/bin/env python3
"""Option-Backspace edits query text without leaving either focused search input."""
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
SOCKET = STATE / f'word-delete-{os.getpid()}.sock'
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


with tempfile.TemporaryDirectory(prefix='word-delete-',dir=STATE) as directory:
    project=Path(directory)
    (project/'scope').mkdir()
    (project/'main.txt').write_text('editor unchanged\n')
    process=subprocess.Popen([str(ROOT/'jetvim'),directory,'main.txt','--listen',str(SOCKET)],cwd=ROOT,stdin=slave,stdout=slave,stderr=slave,
                             env=dict(os.environ,TERM='xterm-256color',JETVIM_DISABLE_VCS='1',JETVIM_DISABLE_AUTOSAVE='1'))
    os.close(slave);reader=threading.Thread(target=drain,daemon=True);reader.start()
    try:
        deadline=time.monotonic()+10
        while not SOCKET.exists():
            assert process.poll() is None and time.monotonic()<deadline,'editor startup'
            time.sleep(.03)
        time.sleep(.4)
        bindings=json.loads((ROOT/'config/keymap.json').read_text())
        index=next(i for i,item in enumerate(bindings,1) if item['id']=='delete_word_left')
        variants=[('native Alt Backspace127',b'\x1b[127;3u'),('native Alt CtrlH8',b'\x1b[8;3u'),
                  ('legacy EscDEL',b'\x1b\x7f'),('terminal relay',f'\x1b[{0xF0000+index}u'.encode())]
        lua('vim.g.word_source=vim.api.nvim_get_current_buf(); _G.word_executable=vim.fn.executable; vim.fn.executable=function(name) if name=="rg" then return 0 end; return _G.word_executable(name) end; require("jetvim.tree").focus(); return true')
        raw(b'\x1b[102;10u')
        equal(lua('return vim.bo.filetype'),'jetvim-project-search','actual CommandShiftF opens modal input')
        def exercise(module,label):
            input_buffer=lua('local s=require('+json.dumps(module)+'); return s.state and s.state.input or s.input')
            window=lua('return vim.api.nvim_get_current_win()')
            def reset(text):
                lua('vim.api.nvim_buf_set_lines('+str(input_buffer)+',0,-1,false,{'+json.dumps(text,ensure_ascii=False)+'}); '
                    'vim.api.nvim_win_set_cursor('+str(window)+',{1,'+str(len(text.encode()))+'}); vim.cmd.startinsert(); return true')
                time.sleep(.04)
            def check(expected,description):
                equal(lua('return vim.fn.mode()'),'i',label+' '+description+' preserves insert mode')
                equal(lua('return vim.api.nvim_get_current_win()'),window,label+' '+description+' preserves focus')
                equal(lua('return vim.api.nvim_buf_get_lines(0,0,1,false)[1]'),expected,label+' '+description+' exact query text')
                equal(lua('return vim.api.nvim_win_get_cursor(0)'),[1,len(expected.encode())],label+' '+description+' caret at query end')
            for name,chord in variants:
                reset('alpha beta gamma');raw(chord);check('alpha beta ',name)
                reset('alpha beta gamma');raw(chord+chord+b'X');check('alpha X',name+' repeated batch then typing')
            for text,expected in [('alpha.beta gamma','alpha.beta '),('héllo 世界','héllo '),('alpha   ','')]:
                reset(text);raw(variants[0][1]+b'Z');check(expected+'Z','Unicode/punctuation/whitespace')
            reset('alpha beta');raw(b'\x7f');check('alpha bet','ordinary Backspace remains one character')
            reset('alpha beta');raw(b'\x08');check('alpha bet','ordinary CtrlH remains one character')
            reset('query');raw(b'\x20');check('query ','ordinary space remains a space')
            equal(lua('local s=require('+json.dumps(module)+'); return s.state and s.state.query or s.query'),'query ',label+' query callback observes final typed text')
            keys('<Esc>')
        exercise('jetvim.project_search','Find in Files')
        lua('require("jetvim.tree").editor(); vim.api.nvim_set_current_buf(vim.g.word_source); vim.cmd.startinsert(); return true')
        time.sleep(.08);raw(b'\x1b[102;9u')
        equal(lua('return vim.bo.filetype'),'jetvim-search','actual CommandF opens inline input')
        exercise('jetvim.search','Find in File')
        equal(lua('return vim.api.nvim_buf_get_lines(vim.g.word_source,0,-1,false)'),['editor unchanged'],'query deletion never edits source file')
        equal(lua('return vim.v.errmsg'),'','no editor errors')
        lua('vim.fn.executable=_G.word_executable; return true')
        print(f'PASS: {checks} modal/inline word deletion PTY checks')
    finally:
        if process.poll() is None:
            try:lua('vim.cmd("qa!"); return true')
            except Exception:pass
            try:process.wait(timeout=4)
            except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=4)
        stop.set();reader.join(timeout=2);os.close(master);SOCKET.unlink(missing_ok=True)
