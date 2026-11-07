#!/usr/bin/env python3
"""Search closure must yield to InsertLeave rather than poll the event loop."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / '.jetvim'
STATE.mkdir(exist_ok=True)
NVIM = shutil.which('nvim')
assert NVIM, 'Neovim is required'
checks = 0
def equal(actual, expected, label):
    global checks
    assert actual == expected, f'{label}: expected {expected!r}, got {actual!r}'
    checks += 1

class Backend:
    def __init__(self, directory, name):
        self.socket = directory / (name + '.sock')
        self.log = (directory / (name + '.log')).open('w')
        self.process = None
        try:
            self.process = subprocess.Popen([NVIM, '--headless', '-u', 'NONE', '-i', 'NONE', '-n', '--listen', str(self.socket)],
                                            cwd=directory, stdin=subprocess.DEVNULL, stdout=self.log, stderr=self.log,
                                            env=dict(os.environ, XDG_CACHE_HOME=str(directory / 'cache'), XDG_STATE_HOME=str(directory / 'state')))
            deadline = time.monotonic() + 5
            while not self.socket.exists():
                assert self.process.poll() is None and time.monotonic() < deadline, 'backend startup'
                time.sleep(.02)
        except BaseException:
            self.close()
            raise
    def lua(self, code):
        expression = 'json_encode(luaeval(' + json.dumps('(function() ' + code + ' end)()') + '))'
        result = subprocess.run([NVIM, '--server', str(self.socket), '--remote-expr', expression], capture_output=True, text=True, timeout=4)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    def wait(self, code):
        deadline = time.monotonic() + 5
        while not self.lua(code):
            assert time.monotonic() < deadline, 'timeout: ' + code
            time.sleep(.02)
    def close(self):
        if self.process:
            if self.process.poll() is None and self.socket.exists():
                try: self.lua('vim.cmd("qa!");return true')
                except Exception: pass
            try: self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.terminate(); self.process.wait(timeout=3)
        self.log.close()
        self.socket.unlink(missing_ok=True)

with tempfile.TemporaryDirectory(prefix='search-close-lifecycle-', dir=STATE) as directory:
    project = Path(directory)
    main = project / 'main.lua'; main.write_text('-- unchanged\n')
    backend = ui = None
    try:
        backend = Backend(project, 'editor')
        ui = Backend(project, 'ui-client')
        lua = backend.lua
        lua('vim.opt.runtimepath:append('+json.dumps(str(ROOT))+');require("jetvim.project").setup('+json.dumps(str(project))+');'
            'vim.cmd.edit('+json.dumps(str(main))+');return true')
        # A hard budget makes the old busy loop fail promptly without leaving a
        # spinning fixture. The mode itself and event loop are entirely real.
        lua('_G.ScheduleCount=0;_G.OriginalSchedule=vim.schedule;vim.schedule=function(callback) '
            '_G.ScheduleCount=_G.ScheduleCount+1;if _G.ScheduleCount<=100 then _G.OriginalSchedule(callback) end end;return true')
        for surface in ('headless', 'attached', 'detached'):
            if surface == 'attached':
                ui.lua('_G.EditorChannel=vim.fn.sockconnect("pipe",'+json.dumps(str(backend.socket))+',{rpc=true});'
                       'vim.rpcrequest(_G.EditorChannel,"nvim_ui_attach",100,30,{rgb=true});return true')
                equal(lua('return #vim.api.nvim_list_uis()'), 1, 'real RPC UI attached')
            for module in ('project_search', 'search'):
                name = 'jetvim.' + module
                lua('vim.cmd.edit('+json.dumps(str(main))+');vim.api.nvim_win_set_cursor(0,{1,5});require('+json.dumps(name)+').open();return true')
                backend.wait('return vim.fn.mode()=="i"')
                if surface == 'detached':
                    # Reattach for each module, then detach with its input active.
                    if lua('return #vim.api.nvim_list_uis()') == 0:
                        ui.lua('vim.rpcrequest(_G.EditorChannel,"nvim_ui_attach",100,30,{rgb=true});return true')
                    ui.lua('vim.rpcrequest(_G.EditorChannel,"nvim_ui_detach");return true')
                    equal(lua('return #vim.api.nvim_list_uis()'), 0, 'real RPC UI detached with search active')
                if module == 'project_search':
                    lua('local s=require("jetvim.project_search").state;_G.JobKills=0;_G.CloseRuns=0;'
                        's.job={kill=function()_G.JobKills=_G.JobKills+1 end};_G.CloseTimer=vim.uv.new_timer();'
                        's.timer=_G.CloseTimer;s.timer:start(10000,0,function()error("cancelled timer fired")end);return true')
                    lua('require("jetvim.project_search").close(function()_G.CloseRuns=_G.CloseRuns+1;vim.cmd.startinsert()end);'
                        'require("jetvim.project_search").close();return true')
                    equal(lua('return require("jetvim.project_search").state==nil'), True, surface+' FindFiles state closes immediately')
                    backend.wait('return _G.CloseRuns==1 and vim.fn.mode()=="i"')
                    equal(lua('return {_G.JobKills,_G.CloseTimer:is_closing(),_G.CloseRuns}'), [1, True, 1], 'double close cancels once and accepts once')
                else:
                    lua('require("jetvim.search").close();require("jetvim.search").close();return true')
                    equal(lua('local s=require("jetvim.search");return s.input==nil and s.win==nil'), True, surface+' Find state closes immediately')
                    backend.wait('return vim.fn.mode()=="i"')
                equal(lua('return #vim.api.nvim_list_wins()'), 1, surface+' closes both floating search windows')
                equal(lua('return vim.api.nvim_buf_get_name(0)'), str(main), surface+' restores source window')
                equal(lua('return vim.api.nvim_win_get_cursor(0)'), [1, 5], surface+' restores exact source insertion caret')
                count = lua('return _G.ScheduleCount')
                time.sleep(.08)
                equal(lua('return _G.ScheduleCount'), count, surface+' idle closure schedules no recurring callbacks')
                equal(count < 100, True, 'closure stays below scheduler safety budget')
                lua('_G.ScheduleCount=0;return true')
        # Reopening a modal before InsertLeave must invalidate its continuation.
        for module in ('project_search', 'search'):
            name = json.dumps('jetvim.' + module)
            lua('require('+name+').open();return true'); backend.wait('return vim.fn.mode()=="i"')
            lua('_G.StaleAccept=0;local s=require('+name+');s.close(function()_G.StaleAccept=_G.StaleAccept+1 end);s.open();return true')
            backend.wait('return vim.fn.mode()=="i"')
            equal(lua('return _G.StaleAccept'), 0, 'new modal invalidates old acceptance')
            equal(lua('local s=require('+name+');return '+('s.state~=nil' if module == 'project_search' else 's.input~=nil')), True, 'new modal remains open')
            lua('require('+name+').close();return true'); backend.wait('return vim.fn.mode()=="i"')
            lua('require('+name+').open();return true'); backend.wait('return vim.fn.mode()=="i"')
            lua('_G.StaleAccept=0;require('+name+').close(function()_G.StaleAccept=_G.StaleAccept+1 end);vim.cmd.vnew();return true')
            backend.wait('return vim.fn.mode()=="n"')
            equal(lua('return _G.StaleAccept'), 0, 'switching windows invalidates deferred acceptance')
            equal(lua('return vim.api.nvim_buf_get_name(0)'), '', 'stale continuation never moves focus back')
            lua('vim.cmd("close!");return true')
            lua('require('+name+').open();return true'); backend.wait('return vim.fn.mode()=="i"')
            lua('_G.StaleAccept=0;require('+name+').close(function()_G.StaleAccept=_G.StaleAccept+1 end);'
                'vim.api.nvim_buf_set_lines(0,0,-1,false,{""});return true')
            backend.wait('return vim.fn.mode()=="n"')
            equal(lua('return _G.StaleAccept'), 0, 'source edits invalidate old caret and deferred acceptance')
            lua('vim.cmd("edit!");return true')
        equal(lua('return vim.v.errmsg'), '', 'lifecycle changes leave no Neovim errors')
        equal(main.read_text(), '-- unchanged\n', 'search lifecycle never changes source file')
    finally:
        if ui: ui.close()
        if backend: backend.close()

# Exercise actual Escape input, not only API closure, in a live terminal too.
support = {'__file__': str(ROOT / 'tests/autosave.py')}
exec((ROOT / 'tests/autosave.py').read_text().split('\nwith tempfile.TemporaryDirectory', 1)[0], support)
with tempfile.TemporaryDirectory(prefix='search-close-pty-', dir=STATE) as directory:
    project = Path(directory); (project / 'home').mkdir(); (project / 'main.lua').write_text('-- unchanged\n')
    editor = support['Editor'](project, project / 'home/settings.lua', disabled=True, disable_lsp=True)
    try:
        for chord, module in ((b'\x1b[102;9u', 'search'), (b'\x1b[102;10u', 'project_search')):
            editor.raw(chord); editor.wait('return vim.fn.mode()=="i" and vim.bo.filetype=='+json.dumps('jetvim-search' if module == 'search' else 'jetvim-project-search'))
            editor.raw(b'\x1b[27u')
            editor.wait('return vim.fn.mode()=="i" and vim.fs.basename(vim.api.nvim_buf_get_name(0))=="main.lua"')
            equal(editor.lua('local s=require("jetvim.'+module+'");return '+('s.state==nil' if module == 'project_search' else 's.input==nil')), True, 'native Escape closes search and restores typing')
    finally:
        editor.close()
print(f'PASS: {checks} search close lifecycle checks (headless, UI detach and native terminal)')
