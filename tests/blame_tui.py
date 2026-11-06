#!/usr/bin/env python3
"""Real insert-mode terminal arrow moves the cached gray blame annotation."""
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
ROOT=Path(__file__).resolve().parent.parent
socket=ROOT/'.jetvim'/f'blame-tui-{os.getpid()}.sock'
master,slave=pty.openpty()
fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',30,110,0,0))
env=dict(os.environ,TERM='xterm-256color',JETVIM_DISABLE_VCS='1',JETVIM_DISABLE_AUTOSAVE='1')
process=subprocess.Popen([str(ROOT/'jetvim'),'--listen',str(socket)],cwd=ROOT,stdin=slave,stdout=slave,stderr=slave,env=env)
os.close(slave)
stop=threading.Event()
def drain():
    while not stop.is_set():
        if select.select([master],[],[],.1)[0]:
            try: os.read(master,65536)
            except OSError: break
thread=threading.Thread(target=drain,daemon=True);thread.start()
def lua(code):
    expression="json_encode(luaeval('(function() "+code.replace("'","''")+" end)()'))"
    result=subprocess.run([str(ROOT/'jetvim'),'--server',str(socket),'--remote-expr',expression],cwd=ROOT,env=env,capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
    return json.loads(result.stdout)
try:
    deadline=time.monotonic()+10
    while not socket.exists():
        assert process.poll() is None and time.monotonic()<deadline,'TUI startup'
        time.sleep(.03)
    time.sleep(.5)
    lua('vim.cmd("stopinsert"); require("jetvim.tree").editor(); vim.cmd.enew({bang=true}); vim.api.nvim_buf_set_name(0,vim.env.JETVIM_ROOT.."/.jetvim/blame-tui.txt"); vim.api.nvim_buf_set_lines(0,0,-1,false,{"one","two"}); local b=vim.api.nvim_get_current_buf(); local s=require("jetvim.settings").get(); s.git={blame={enabled=true,mode="current_line"}}; require("jetvim.settings").get=function() return s end; vim.env.JETVIM_DISABLE_VCS=nil; require("jetvim.blame").states[b]={tick=vim.api.nvim_buf_get_changedtick(b),lines={"Ada · First","Ben · Second"}}; require("jetvim.blame").render(b); vim.api.nvim_win_set_cursor(0,{1,0}); vim.cmd.startinsert(); return true')
    time.sleep(.15)
    lua('local b=vim.api.nvim_get_current_buf(); require("jetvim.blame").states[b]={tick=vim.api.nvim_buf_get_changedtick(b),lines={"Ada · First","Ben · Second"}}; require("jetvim.blame").render(b); return true')
    assert lua('return vim.fn.mode()')=='i','insert mode'
    os.write(master,b'\x1b[B');time.sleep(.2)
    assert lua('return vim.api.nvim_win_get_cursor(0)[1]')==2,'terminal Down moved cursor'
    marks=lua('local ns=require("jetvim.api").namespaces["annotations:git-blame"]; return vim.api.nvim_buf_get_extmarks(0,ns,0,-1,{details=true})')
    assert len(marks)==1 and marks[0][1]==1 and marks[0][3]['virt_text'][0][0]=='  Ben · Second',marks
    assert lua('return vim.fn.mode()')=='i','arrow preserves insert mode'
    print('blame TUI: 4 checks passed')
finally:
    if process.poll() is None:
        try: lua('vim.cmd("qa!"); return true')
        except Exception: pass
        try: process.wait(timeout=4)
        except subprocess.TimeoutExpired: process.terminate();process.wait(timeout=4)
    stop.set();thread.join(timeout=2);os.close(master)
