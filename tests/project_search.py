#!/usr/bin/env python3
"""Actual PTY scoped modal search, rg results and stale asynchronous job protection."""
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
SOCKET = STATE / f'project-search-{os.getpid()}.sock'
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


def wait(code,label,seconds=6):
    deadline=time.monotonic()+seconds
    while not lua(code):
        assert time.monotonic()<deadline,label
        time.sleep(.04)


with tempfile.TemporaryDirectory(prefix='project-search-',dir=STATE) as directory:
    project=Path(directory)
    scope=project/'scope';scope.mkdir()
    (project/'editor.txt').write_text('editor unchanged\n')
    (project/'outside.txt').write_text('needle root\n')
    (scope/'a.txt').write_text('alpha\nneedle first\n')
    (scope/'b.txt').write_text('prefix needle second\n')
    (scope/'control\nname.txt').write_text('needle control\n')
    for name in ('.jetvim','.idea','node_modules'):
        (scope/name).mkdir();(scope/name/'cached.txt').write_text('needle excluded\n')
    (scope/'.ignore').write_text('ignored.txt\n')
    (scope/'ignored.txt').write_text('needle ignored\n')
    outside=project.parent/('project-search-outside-'+str(os.getpid()));outside.mkdir()
    (outside/'private.txt').write_text('needle outside project\n')
    (project/'outside-link').symlink_to(outside,target_is_directory=True)
    process=subprocess.Popen([str(ROOT/'jetvim'),directory,'editor.txt','--listen',str(SOCKET)],cwd=ROOT,stdin=slave,stdout=slave,stderr=slave,
                             env=dict(os.environ,TERM='xterm-256color',JETVIM_DISABLE_VCS='1',JETVIM_DISABLE_AUTOSAVE='1'))
    os.close(slave);reader=threading.Thread(target=drain,daemon=True);reader.start()
    try:
        deadline=time.monotonic()+10
        while not SOCKET.exists():
            assert process.poll() is None and time.monotonic()<deadline,'editor startup'
            time.sleep(.03)
        time.sleep(.4)
        lua('vim.g.project_search_source=vim.api.nvim_get_current_buf(); return true')
        bindings=json.loads((ROOT/'config/keymap.json').read_text())
        index=next(i for i,item in enumerate(bindings,1) if item['id']=='find_project')
        relay=f'\x1b[{0xF0000+index}u'.encode()
        native=b'\x1b[102;10u'
        def choose(path):
            lua('vim.cmd.stopinsert(); return true');time.sleep(.03)
            equal(lua('local t=require("jetvim.tree"); t.focus(); t.expanded['+json.dumps(str(scope))+']=true; t.render(); '
                      'for row,e in pairs(t.rows) do if e.path=='+json.dumps(str(path))+' then vim.api.nvim_win_set_cursor(t.win,{row,0}); return true end end; return false'),True,'scope entry selected')
        equal(lua('return require("jetvim.project_search").contains("/","/tmp/example.txt")'),True,'filesystem-root scope accepts absolute child')
        equal(lua('return require("jetvim.project_search").contains("/src/app","/src/application/file.txt")'),False,'scope prefix respects directory boundary')
        choose(scope)
        origin=lua('return vim.api.nvim_get_current_win()')
        windows=lua('return #vim.api.nvim_list_wins()')
        raw(native)
        equal(lua('return vim.bo.filetype'),'jetvim-project-search','native CommandShiftF immediately focuses modal')
        equal(lua('return vim.fn.mode()'),'i','modal query accepts typing immediately')
        equal(lua('local text=vim.api.nvim_eval_statusline(vim.wo.statusline,{}).str; return text:find("Find in Files",1,true)~=nil and not text:find("Scratch",1,true) and not text:find("JETVIM-PROJECT-SEARCH",1,true)'),True,'friendly popup status without internal buffer labels')
        equal(lua('return require("jetvim.project_search").state.scope'),str(scope),'selected folder scope')
        equal(lua('local s=require("jetvim.project_search").state; local c=vim.api.nvim_win_get_config(s.promptwin); return c.relative=="editor" and tostring(c.title[1][1]):find("scope/",1,true)~=nil'),True,'centered float visibly labels scope')
        raw(b'needle')
        wait('local s=require("jetvim.project_search").state; return s and not s.busy and not s.timer and #s.items==3','real scoped rg results')
        equal(lua('return #require("jetvim.project_search").state.items'),3,'scope excludes root/ignored/cache matches')
        equal(lua('local s=require("jetvim.project_search").state; for _,i in ipairs(s.items) do if i.path:find("control",1,true) then return i.label:find("↵",1,true)~=nil and not i.label:find("\\n",1,true) end end; return false'),True,'control filenames display safely on one row')
        keys('<C-u>');raw(b'needle.')
        wait('local s=require("jetvim.project_search").state; return s and not s.busy and not s.timer and s.message=="No matches"','literal project query')
        equal(lua('return #require("jetvim.project_search").state.items'),0,'project search treats punctuation literally')
        keys('<C-u>');raw(b'needle')
        wait('local s=require("jetvim.project_search").state; return s and not s.busy and not s.timer and #s.items==3','restored literal results')
        equal(lua('for _,i in ipairs(require("jetvim.project_search").state.items) do if i.path:match("/b%.txt$") then return i.col end end'),7,'rg match byte column is preserved')
        raw(b'\x1b[B')
        expected=lua('local s=require("jetvim.project_search").state; return s.items[s.selected]')
        equal(lua('return require("jetvim.project_search").state.selected'),2,'Down selects next search result')
        raw(b'\r')
        wait('return require("jetvim.project_search").state==nil','Enter closes modal')
        equal(lua('return vim.api.nvim_buf_get_name(0)'),expected['path'],'Enter opens chosen file')
        equal(lua('return vim.api.nvim_win_get_cursor(0)'),[expected['line'],expected['col']],'Enter opens matching line and byte column')
        equal(lua('return #vim.api.nvim_list_wins()'),windows,'accept leaves no modal windows')
        choose(scope/'a.txt');raw(relay)
        equal(lua('return require("jetvim.project_search").state.scope'),str(scope),'relay uses selected file parent')
        keys('<Esc>');equal(lua('return vim.api.nvim_get_current_win()'),origin,'Escape restores sidebar focus')
        choose(project);raw(b'\x1b[70;9u')
        equal(lua('return require("jetvim.project_search").state.scope'),str(project),'capital native shortcut scopes root to whole project')
        raw(b'needle')
        wait('local s=require("jetvim.project_search").state; return s and not s.busy and not s.timer and #s.items==4','whole project results')
        choose(scope);raw(relay)
        equal(lua('return require("jetvim.project_search").state.scope'),str(scope),'reopening from tree updates existing modal scope')
        equal(lua('return #vim.api.nvim_list_wins()'),windows+2,'rescoping replaces existing modal windows')
        keys('<Esc>')
        # Missing rg must never suppress or unfocus the modal.
        lua('_G.project_search_executable=vim.fn.executable; _G.project_search_executable_calls=0; vim.fn.executable=function(name) if name=="rg" then _G.project_search_executable_calls=_G.project_search_executable_calls+1; return 0 end; return _G.project_search_executable(name) end; return true')
        choose(scope);raw(native)
        equal(lua('return _G.project_search_executable_calls'),0,'modal opens before probing dependencies')
        equal(lua('return vim.fn.mode()'),'i','missing rg still focused typing')
        raw(b'needle')
        wait('local s=require("jetvim.project_search").state; return s and s.message:find("requires ripgrep",1,true)~=nil','visible missing rg message')
        keys('<Esc>');lua('vim.fn.executable=_G.project_search_executable; return true')
        # A selected symlink outside the project must never be used as cwd.
        choose(project/'outside-link');raw(relay)
        equal(lua('return require("jetvim.project_search").state.scope'),None,'outside symlink scope blocked')
        raw(b'needle');time.sleep(.3)
        equal(lua('return require("jetvim.project_search").state.message:find("outside",1,true)~=nil'),True,'outside scope explained inline')
        keys('<Esc>')
        # Capture argv/cwd and deliver stale callbacks even after kill().
        lua("""_G.project_search_system=vim.system; _G.project_search_jobs={}; vim.system=function(argv,opts,done)
          local job={argv=argv,cwd=opts.cwd,killed=false}; table.insert(_G.project_search_jobs,job)
          local text=argv[#argv-1]
          function job.deliver()
            if text=='timeout' then done({code=124})
            else
              local line=vim.json.encode({type='match',data={path={text='./a.txt'},lines={text=text},line_number=1,submatches={{start=0}}}})..'\\n'
              opts.stdout(nil,text=='cap' and line:rep(501) or line); done({code=0})
            end
            -- Resolve after all stdout/completion callbacks have been scheduled.
            vim.schedule(function() job.delivered=true end)
          end
          -- Old jobs remain active until the test deliberately delivers their
          -- callbacks after cancellation, regardless of host/RPC latency.
          if text~='old' then vim.defer_fn(job.deliver,30) end
          return {kill=function()job.killed=true end}
        end; return true""")
        choose(scope);raw(native);raw(b'old')
        wait('return #_G.project_search_jobs==1','old query started')
        equal(lua('local s=require("jetvim.project_search").state; return s.busy and s.job~=nil'),True,'old query remains active until cancelled')
        keys('<C-u>');raw(b'new')
        wait('local s=require("jetvim.project_search").state; return #_G.project_search_jobs==2 and s and not s.busy and not s.timer','new query finished')
        new_items=lua('return require("jetvim.project_search").state.items')
        equal([item['label'] for item in new_items],['a.txt:1  new'],'new query contains only its current result')
        lua('_G.project_search_jobs[1].deliver(); return true')
        wait('return _G.project_search_jobs[1].delivered','stale callbacks delivered after newer results')
        equal(lua('return require("jetvim.project_search").state.items'),new_items,'stale job cannot append or replace any new result')
        equal(lua('return _G.project_search_jobs[1].killed'),True,'changing query kills active job')
        equal(lua('return _G.project_search_jobs[2].cwd'),str(scope),'async search uses guarded selected cwd')
        equal(lua('local a=_G.project_search_jobs[2].argv; return {a[#a-2],a[#a-1],a[#a]}'),['--','new','.'],'query is an argv value after option terminator')
        equal(lua('return vim.tbl_contains(_G.project_search_jobs[2].argv,"!.git")'),True,'Git metadata excluded without a Git fixture')
        keys('<C-u>');raw(b'old')
        wait('return #_G.project_search_jobs==3','cancelled query started')
        keys('<Esc>')
        wait('return require("jetvim.project_search").state==nil','Escape closes active query')
        equal(lua('return _G.project_search_jobs[3].killed'),True,'Escape kills pending job')
        lua('_G.project_search_jobs[3].deliver(); return true')
        wait('return _G.project_search_jobs[3].delivered','cancelled callbacks delivered after close')
        equal(lua('return require("jetvim.project_search").state==nil'),True,'cancelled callback never resurrects modal')
        equal(lua('local n=0; for _,b in ipairs(vim.api.nvim_list_bufs()) do if vim.bo[b].filetype=="jetvim-project-search" then n=n+1 end end; return n'),0,'no leaked modal buffers')
        equal(lua('return #vim.api.nvim_list_wins()'),windows,'no leaked modal windows after cancellation')
        choose(scope);raw(native);raw(b'cap')
        wait('local s=require("jetvim.project_search").state; return s and not s.busy and not s.timer and s.capped','bounded result stream')
        equal(lua('return #require("jetvim.project_search").state.items'),500,'stream stops at result limit')
        equal(lua('return _G.project_search_jobs[#_G.project_search_jobs].killed'),True,'result limit stops subprocess')
        keys('<C-u>');raw(b'timeout')
        wait('local s=require("jetvim.project_search").state; return s and s.message=="Search timed out"','timeout shown inline')
        equal(lua('return vim.bo.filetype'),'jetvim-project-search','timeout keeps query focused')
        keys('<Esc>')
        lua('vim.system=_G.project_search_system; return true')
        equal(lua('return vim.api.nvim_buf_get_lines(vim.g.project_search_source,0,-1,false)'),['editor unchanged'],'modal query never edits editor text')
        equal(lua('return vim.v.errmsg'),'','no editor errors')
        print(f'PASS: {checks} scoped project-search modal and async checks')
    finally:
        if process.poll() is None:
            try:lua('vim.cmd("qa!"); return true')
            except Exception:pass
            try:process.wait(timeout=4)
            except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=4)
        stop.set();reader.join(timeout=2);os.close(master);SOCKET.unlink(missing_ok=True)
        import shutil
        shutil.rmtree(outside)
