#!/usr/bin/env python3
"""Render asynchronous lint diagnostics and Git markers without leaving typing mode."""
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
SOCKET = STATE / f'diagnostics-live-{os.getpid()}.sock'
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


def wait(code,label):
    deadline=time.monotonic()+5
    while not lua(code):
        assert time.monotonic()<deadline,label
        time.sleep(.03)


def rendered_gutter():
    lua('pcall(vim.api.nvim__inspect_cell,1,0,0); vim.cmd("redraw!"); return true')
    time.sleep(.05)
    return lua('local win=vim.g.live_owner; local p=vim.fn.screenpos(win,2,1); local origin=vim.api.nvim_win_get_position(win); local cells={}; '
               'for c=origin[2]+1,p.col-1 do cells[#cells+1]=vim.api.nvim__inspect_cell(1,p.row-1,c-1) end; return cells')


with tempfile.TemporaryDirectory(prefix='diagnostics-live-',dir=STATE) as directory:
    project=Path(directory)
    (project/'main.txt').write_text('first\nchanged\n')
    process=subprocess.Popen([str(ROOT/'jetvim'),directory,'main.txt','--listen',str(SOCKET)],cwd=ROOT,stdin=slave,stdout=slave,stderr=slave,
                             env=dict(os.environ,TERM='xterm-256color',JETVIM_DISABLE_VCS='1',JETVIM_DISABLE_AUTOSAVE='1'))
    os.close(slave);reader=threading.Thread(target=drain,daemon=True);reader.start()
    try:
        deadline=time.monotonic()+10
        while not SOCKET.exists():
            assert process.poll() is None and time.monotonic()<deadline,'editor startup'
            time.sleep(.03)
        time.sleep(.4)
        equal(lua('return vim.fn.mode()'),'i','Jetvim defaults to typing mode')
        equal(lua('return vim.diagnostic.config().update_in_insert'),True,'diagnostic updates enabled during typing')
        lua('vim.g.live_owner=vim.api.nvim_get_current_win(); vim.g.live_buf=vim.api.nvim_get_current_buf(); vim.api.nvim_win_set_cursor(0,{2,3}); '
            '_G.live_system=vim.system; vim.g.live_git_calls=0; vim.system=function(argv,...) if argv[1]=="git" then vim.g.live_git_calls=vim.g.live_git_calls+1; error("Git execution forbidden in live diagnostics fixture") end; return _G.live_system(argv,...) end; '
            'local g=require("jetvim.gutter"); g.states[vim.g.live_buf]={path=vim.api.nvim_buf_get_name(0),project=require("jetvim.project").root,baseline="first\\noriginal\\nremoved\\n",generation=0}; '
            'vim.env.JETVIM_DISABLE_VCS=nil; g.render(vim.g.live_buf); vim.env.JETVIM_DISABLE_VCS="1"; return true')
        caret=lua('return vim.api.nvim_win_get_cursor(0)')
        equal(lua('local g=require("jetvim.gutter"); local m=vim.api.nvim_buf_get_extmarks(vim.g.live_buf,g.namespace,0,-1,{details=true}); return #m==2 and m[1][2]==1 and m[2][2]==1'),True,'real gutter diff emits modification and deletion on final row')
        initial=rendered_gutter()
        text=''.join(cell[0] for cell in initial)
        equal('▎' in text and '▸' in text,True,'both Git markers actually rendered before lint arrives')
        lua('vim.defer_fn(function() local api=require("jetvim.api"); api.diagnostics("live-eslint",vim.g.live_buf,{{line=2,column=1,severity="error",message="Live ESLint error"}}); '
            'api.diagnostics("live-oxlint",vim.g.live_buf,{{line=2,column=2,severity="error",message="Live Oxlint error"}}); end,100); return true')
        wait('return #vim.diagnostic.get(vim.g.live_buf)==2','async lint publishes two diagnostic sources')
        wait('local o=require("jetvim.overview"); return o.panes[vim.g.live_owner]~=nil','overview appears without InsertLeave')
        equal(lua('return vim.fn.mode()'),'i','async lint keeps typing mode')
        equal(lua('return vim.api.nvim_get_current_win()'),lua('return vim.g.live_owner'),'async lint preserves editor focus')
        equal(lua('return vim.api.nvim_win_get_cursor(0)'),caret,'async lint preserves caret')
        cells=rendered_gutter();text=''.join(cell[0] for cell in cells)
        equal(text.count('▎'),1,'modified Git bar survives multiple diagnostic providers')
        equal(text.count('▸'),1,'deleted Git marker survives multiple diagnostic providers')
        equal(text.count('E'),1,'one highest-severity diagnostic remains visible beside Git')
        equal(text.index('▎')<text.index('E') and text.index('▸')<text.index('E'),True,'Git markers remain left of diagnostic sign')
        groups={'▎':'JetvimGutterModified','▸':'JetvimGutterDeleted','E':'DiagnosticSignError'}
        for symbol,group in groups.items():
            cell=next(c for c in cells if c[0]==symbol)
            expected=lua('return vim.api.nvim_get_hl(0,{name='+json.dumps(group)+',link=false}).fg')
            equal(cell[1].get('foreground'),expected,group+' actual sign color')
        virtual=lua('local win=vim.g.live_owner; local p=vim.fn.screenpos(win,2,1); local origin=vim.api.nvim_win_get_position(win); local result=""; '
                    'for c=p.col,origin[2]+vim.api.nvim_win_get_width(win) do result=result..vim.fn.screenstring(p.row,c) end; return result')
        equal('Live ESLint error' in virtual or 'Live Oxlint error' in virtual,True,'actual virtual diagnostic text appears without leaving insert')
        equal(lua('local p=require("jetvim.overview").panes[vim.g.live_owner]; return p.cells[vim.api.nvim_win_get_height(vim.g.live_owner)-1].severity'),1,'overview immediately reports highest severity')
        stripe=lua('local p=require("jetvim.overview").panes[vim.g.live_owner]; local pos=vim.api.nvim_win_get_position(p.win); return vim.fn.screenstring(pos[1]+vim.api.nvim_win_get_height(p.win),pos[2]+1)')
        equal(stripe,'█','actual right-edge overview marker appears immediately')
        equal(lua('return vim.g.live_git_calls'),0,'cached gutter render never invokes Git')
        equal(lua('return vim.fn.mode()'),'i','render checks preserve typing mode throughout')
        raw(b'Z')
        equal(lua('return vim.api.nvim_get_current_line()'),'chaZnged','typing continues at original caret after lint')
        equal(lua('return vim.v.errmsg'),'','no editor errors')
        print(f'PASS: {checks} live diagnostic and Git coexistence TUI checks')
    finally:
        if process.poll() is None:
            try:lua('vim.cmd("qa!"); return true')
            except Exception:pass
            try:process.wait(timeout=4)
            except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=4)
        stop.set();reader.join(timeout=2);os.close(master);SOCKET.unlink(missing_ok=True)
