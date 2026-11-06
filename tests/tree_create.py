#!/usr/bin/env python3
"""Create sidebar files and folders through native and bridge-relay CommandN."""
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
SOCKET = STATE / f'tree-create-{os.getpid()}.sock'
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
    deadline=time.monotonic()+4
    while not path.exists():
        assert time.monotonic()<deadline, 'file was not created: '+path.name
        time.sleep(.03)


with tempfile.TemporaryDirectory(prefix='tree-create-',dir=STATE) as directory:
    project=Path(directory)
    (project/'nested').mkdir()
    (project/'nested/anchor.txt').write_text('existing data\n')
    (project/'editor.txt').write_text('source stays unchanged\n')
    outside=project.parent/('tree-create-outside-'+str(os.getpid()))
    outside.mkdir()
    (project/'outside-link').symlink_to(outside,target_is_directory=True)
    process=subprocess.Popen([str(ROOT/'jetvim'),directory,'editor.txt','--listen',str(SOCKET)],
                             cwd=ROOT,stdin=slave,stdout=slave,stderr=slave,
                             env=dict(os.environ,TERM='xterm-256color',JETVIM_DISABLE_VCS='1',JETVIM_DISABLE_AUTOSAVE='1'))
    os.close(slave)
    reader=threading.Thread(target=drain,daemon=True);reader.start()
    try:
        deadline=time.monotonic()+10
        while not SOCKET.exists():
            assert process.poll() is None and time.monotonic()<deadline,'editor startup'
            time.sleep(.03)
        time.sleep(.4)
        bindings=json.loads((ROOT/'config/keymap.json').read_text())
        index=next(i for i,item in enumerate(bindings,1) if item['id']=='tree_new')
        native=b'\x1b[110;9u'
        relay=f'\x1b[{0xF0000+index}u'.encode()
        lua('vim.g.tree_create_source=vim.api.nvim_get_current_buf(); vim.g.tree_create_notices={}; vim.notify=function(text) table.insert(vim.g.tree_create_notices,text) end; return true')
        def choose(path):
            lua('vim.cmd.stopinsert(); return true');time.sleep(.04)
            result=lua('local t=require("jetvim.tree"); t.focus(); t.expanded['+json.dumps(str(project/'nested'))+']=true; t.render(); '
                       'for row,e in pairs(t.rows) do if e.path=='+json.dumps(str(path))+' then vim.api.nvim_win_set_cursor(t.win,{row,0}); return true end end; return false')
            equal(result,True,'selected parent entry visible')
        def prompt(chord):
            raw(chord)
            equal(lua('return vim.fn.mode()'),'c','CommandN opens creation prompt')
            equal(lua('return vim.fn.getcmdprompt():find("New file",1,true) ~= nil'),True,'creation prompt context')
        choose(project)
        prompt(native); raw(b'created.txt\r');wait_file(project/'created.txt')
        equal((project/'created.txt').read_bytes(),b'','native creates empty file immediately')
        equal(lua('return vim.api.nvim_buf_get_name(0)'),str(project/'created.txt'),'new file opens in editor')
        choose(project/'nested')
        prompt(relay);raw(b'child/grand/\r');wait_file(project/'nested/child/grand')
        equal((project/'nested/child/grand').is_dir(),True,'relay trailing slash creates nested folders under selection')
        equal(lua('return vim.bo.filetype'),'jetvim-tree','folder creation retains sidebar focus')
        equal(lua('local t=require("jetvim.tree"); return t.rows[vim.api.nvim_win_get_cursor(t.win)[1]].path'),str(project/'nested/child/grand'),'created folder is revealed and selected')
        choose(project/'nested/anchor.txt')
        prompt(relay);raw(b'sibling.txt\r');wait_file(project/'nested/sibling.txt')
        equal((project/'nested/sibling.txt').is_file(),True,'selected file creates sibling in its parent')
        choose(project)
        prompt(native);raw(b'cancelled.txt');keys('<Esc>')
        equal((project/'cancelled.txt').exists(),False,'cancelled name never creates a file')
        equal(lua('return vim.fn.mode()'),'n','cancel returns to sidebar')
        choose(project)
        prompt(relay);raw(b'../escaped-tree-create.txt\r')
        equal((project.parent/'escaped-tree-create.txt').exists(),False,'parent traversal cannot escape selected project')
        equal(lua('return vim.bo.filetype'),'jetvim-tree','invalid path leaves tree focused')
        choose(project)
        prompt(native);raw(b'outside-link/blocked.txt\r')
        equal((outside/'blocked.txt').exists(),False,'symlink escape blocked')
        choose(project/'nested')
        prompt(relay);raw(b'anchor.txt\r')
        equal((project/'nested/anchor.txt').read_text(),'existing data\n','existing file never truncated')
        # Outside tree, the contextual action must not insert private characters.
        lua('require("jetvim.tree").editor(); vim.api.nvim_set_current_buf(vim.g.tree_create_source); vim.cmd.startinsert(); return true')
        time.sleep(.08)
        raw(native);raw(relay)
        equal(lua('return vim.api.nvim_buf_get_lines(0,0,-1,false)'),['source stays unchanged'],'editor CommandN remains contextual no-op')
        lua('vim.cmd.stopinsert(); return true');time.sleep(.04)
        lua('vim.g.tree_create_terminal_input=""; local b=vim.api.nvim_create_buf(false,true); vim.api.nvim_open_term(b,{on_input=function(_,_,_,data) vim.g.tree_create_terminal_input=vim.g.tree_create_terminal_input..data end}); vim.api.nvim_set_current_buf(b); vim.cmd.startinsert(); return true')
        time.sleep(.08)
        raw(native);raw(relay)
        equal(lua('return vim.fn.mode()'),'t','terminal CommandN keeps terminal input')
        equal(lua('return vim.g.tree_create_terminal_input'),'','native and private creation shortcut never leak into terminal')
        equal(lua('return vim.v.errmsg'),'','clean editor error state')
        print(f'PASS: {checks} native/relay sidebar creation checks')
    finally:
        if process.poll() is None:
            try:lua('vim.cmd("qa!"); return true')
            except Exception:pass
            try:process.wait(timeout=4)
            except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=4)
        stop.set();reader.join(timeout=2);os.close(master);SOCKET.unlink(missing_ok=True)
        import shutil
        shutil.rmtree(outside)
