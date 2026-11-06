#!/usr/bin/env python3
"""Real async argv jobs and editor diagnostics; no Git execution."""
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / '.jetvim/tests/hooks'
FIXTURE.mkdir(parents=True, exist_ok=True)
(FIXTURE / "quoted ' file.js").write_text('hello\n')
script = r'''
local root = vim.env.JETVIM_ROOT
local project = root .. '/.jetvim/tests/hooks'
require('jetvim.project').setup(project)
vim.cmd.edit(vim.fn.fnameescape(project .. "/quoted ' file.js"))
local buf = vim.api.nvim_get_current_buf()
local settings = require('jetvim.settings')
local hooks = require('jetvim.hooks')
local api = require('jetvim.api')
local count = 0
local function check(value, message) assert(value, message); count = count + 1 end
local configured = {}
local auto = {enabled=false,debounce=true,delay_ms=100,on_focus_lost=false}
settings.get = function() return { autosave=auto, hooks={after_save=configured} } end
hooks.setup()
local function wait() check(vim.wait(6000, function() return hooks.states[buf] == nil end, 10), 'hook finished') end
configured = {{pattern=[[\.js$]], command={'python3','-c',[[import sys; print('[{"messages":[{"line":1,"column":2,"severity":2,"message":"Oops","ruleId":"demo"}]}]'); sys.exit(1)]],'{file}'}, diagnostics='eslint', name='lint'}}
hooks.run(buf); wait()
local ns = api.namespaces['hook:lint']
local diagnostics = vim.diagnostic.get(buf,{namespace=ns})
check(#diagnostics == 1 and diagnostics[1].lnum==0 and diagnostics[1].col==1, 'one-based conversion')
check(diagnostics[1].severity==vim.diagnostic.severity.ERROR and diagnostics[1].code=='demo', 'severity and rule')
configured[1].command={'python3','-c',[[print('[{"messages":[]}]')]]}
hooks.run(buf); wait()
check(#vim.diagnostic.get(buf,{namespace=ns})==0, 'clean lint clears findings')
configured={{pattern=[[\.js$]],command={'python3','-c',[[import sys; open(sys.argv[1],'w').write('formatted\n')]],'{file}'}}}
hooks.run(buf); wait()
check(vim.api.nvim_buf_get_lines(buf,0,1,false)[1]=='formatted', 'formatter reloads clean buffer')
check(not vim.bo[buf].modified, 'formatter reload stays clean')
configured={{pattern=[[\.js$]],command={'python3','-c',[[import time,sys; time.sleep(.2); open(sys.argv[1],'w').write('external\n')]],'{file}'}}}
hooks.run(buf)
vim.api.nvim_buf_set_lines(buf,0,-1,false,{'user edit'})
wait()
check(vim.api.nvim_buf_get_lines(buf,0,1,false)[1]=='user edit' and vim.bo[buf].modified, 'formatter preserves newer edits')
vim.cmd('edit!')
configured={{pattern=[[\.js$]],command={'python3','-c',[[import time;time.sleep(.2); print('[{"messages":[{"message":"stale"}]}]')]]},diagnostics='eslint',name='stale'}}
hooks.run(buf); vim.api.nvim_buf_set_lines(buf,0,-1,false,{'new text'}); wait()
check(#vim.diagnostic.get(buf,{namespace=api.namespaces['hook:stale']})==0,'stale diagnostics ignored')
vim.cmd('edit!')
local notices={}; vim.notify=function(text) notices[#notices+1]=text end
configured={{pattern='[',command={'python3','-c','pass'}}}
hooks.run(buf)
check(#notices>0,'invalid regex nonmodal warning')
configured={{pattern=[[\.js$]],command={'python3','-c','import time; time.sleep(2)'},timeout_ms=25}}
hooks.run(buf); wait()
check(#notices>1,'timeout reported')
configured={{pattern=[[\.js$]],command={'python3','-c',[[import time; time.sleep(.2)]]}}}
hooks.run(buf); hooks.run(buf); hooks.run(buf); wait()
check(not vim.b[buf].jetvim_hook_running,'coalesced queue clears busy flag')
api.annotations('demo',buf,{{line=1,text='gray annotation'}})
check(#vim.api.nvim_buf_get_extmarks(buf,api.namespaces['annotations:demo'],0,-1,{})==1,'annotation bridge')
api.annotations('demo',buf,{})
check(#vim.api.nvim_buf_get_extmarks(buf,api.namespaces['annotations:demo'],0,-1,{})==0,'annotations clear')
vim.cmd('edit!')
configured={{pattern=[[\.js$]],command={'python3','-c','import time; time.sleep(.2)'}}}
hooks.run(buf)
vim.api.nvim_buf_set_name(buf,project..'/renamed.js')
check(hooks.states[buf]==nil and not vim.b[buf].jetvim_hook_running,'rename cancels and clears busy state')
vim.api.nvim_buf_set_name(buf,project.."/quoted ' file.js")
local out=vim.json.encode({{filePath=project..'/other.js',messages={{message='other file'}}},{filePath=vim.api.nvim_buf_get_name(buf),messages={{line=1,column=4,severity=1,message='unicode'}}}})
vim.api.nvim_buf_set_lines(buf,0,-1,false,{'😀x'})
local parsed=hooks.eslint(out,nil,{file=vim.api.nvim_buf_get_name(buf),buffer=buf})
check(#parsed==1 and parsed[1].column==6 and parsed[1].severity=='warn','ESLint file filter and UTF16 column conversion')
vim.fn.writefile({'placeholder'},project..'/{project}.js')
vim.cmd.edit({args={project..'/{project}.js'},bang=true})
buf=vim.api.nvim_get_current_buf()
configured={{pattern=[[\.js$]],command={'python3','-c',[=[import sys; assert sys.argv[1].endswith('/'+chr(123)+'project'+chr(125)+'.js'),sys.argv[1]]=],'{file}'}}}
local before=#notices
hooks.run(buf); wait()
check(#notices==before,'filename placeholder tokens remain literal')
for _, invalid in ipairs({{false},{{line=1,severity=99,message='bad severity'}},{{line=1.5,message='fractional row'}}}) do
  configured={
    {name='malformed',pattern=[[\.js$]],command={'python3','-c','pass'},diagnostics=function() return invalid end},
    {name='following',pattern=[[\.js$]],command={'python3','-c','pass'},diagnostics=function() return {{line=1,message='queue continued'}} end},
  }
  local warnings=#notices
  hooks.run(buf); wait()
  check(not vim.b[buf].jetvim_hook_running and #notices>warnings,'malformed custom diagnostics warn and release busy flag')
  check(#vim.diagnostic.get(buf,{namespace=api.namespaces['hook:following']})==1,'queue continues after malformed diagnostic')
end
configured={}
vim.env.JETVIM_DISABLE_AUTOSAVE=nil
vim.cmd('edit!')
auto.enabled=true
vim.api.nvim_buf_set_lines(buf,0,-1,false,{'autosave recovered'})
require('jetvim.autosave').schedule(buf)
check(vim.wait(2000,function() return not vim.bo[buf].modified end,10),'autosave runs after malformed hook diagnostics')
check(vim.fn.readfile(vim.api.nvim_buf_get_name(buf))[1]=='autosave recovered','recovered autosave writes disk')
print('hooks: '..count..' checks passed')
'''
(FIXTURE / 'test.lua').write_text(script)
result = subprocess.run([str(ROOT/'jetvim'), '--headless', '-c', 'lua dofile(vim.env.JETVIM_ROOT .. "/.jetvim/tests/hooks/test.lua")', '+qa!'], cwd=ROOT, env=dict(os.environ,JETVIM_DISABLE_VCS='1',JETVIM_DISABLE_AUTOSAVE='1'), capture_output=True,text=True,timeout=30)
print(result.stdout+result.stderr,end='')
if 'checks passed' not in result.stdout+result.stderr:
    raise SystemExit(1)
raise SystemExit(result.returncode)
