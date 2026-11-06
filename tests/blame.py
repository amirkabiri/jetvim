#!/usr/bin/env python3
"""Blame parser/cache checks use mocked processes; --real requires lead-run Git."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / '.jetvim/tests/blame'
FIXTURE.mkdir(parents=True, exist_ok=True)
real = '--real' in sys.argv
if real:
    for args in [['init'], ['config','user.name','Example Author'], ['config','user.email','author@example.invalid']]:
        subprocess.run(['git','-C',str(FIXTURE),*args],check=True,capture_output=True)
(FIXTURE/'sample.txt').write_text('first\nsecond\n')
if real:
    subprocess.run(['git','-C',str(FIXTURE),'add','sample.txt'],check=True)
    subprocess.run(['git','-C',str(FIXTURE),'commit','--allow-empty','-m','Example commit'],check=True,capture_output=True)
script = r'''
local project=vim.env.JETVIM_ROOT..'/.jetvim/tests/blame'
require('jetvim.project').setup(project)
vim.cmd.edit(project..'/sample.txt')
local buf=vim.api.nvim_get_current_buf()
local blame=require('jetvim.blame')
local api=require('jetvim.api')
local mode='current_line'
require('jetvim.settings').get=function() return {git={blame={enabled=true,mode=mode}}} end
local count=0
local function check(value,message) assert(value,message);count=count+1 end
local parsed=blame.parse('abc123 1 1 1\nauthor Ada\nsummary First\n\tx\n000000 2 2 1\nauthor Nobody\n\tx\n')
check(parsed[1]=='Ada · First','author summary')
check(parsed[2]=='Uncommitted changes','dirty blame')
local calls=0
if not vim.env.JETVIM_REAL_BLAME then
  vim.env.JETVIM_DISABLE_VCS=nil
  vim.system=function(argv,opts,callback)
    calls=calls+1
    check(opts.stdin=='first\nsecond\n','contents stdin')
    check(argv[#argv]==project..'/sample.txt','literal filename argv')
    vim.defer_fn(function() callback({code=0,stdout='abc123 1 1 1\nauthor Ada\nsummary First\n\tfirst\nabc123 2 2 1\nauthor Ada\nsummary First\n\tsecond\n'}) end,10)
    return {kill=function() end}
  end
end
blame.refresh(buf)
check(vim.wait(5000,function()return blame.states[buf] and blame.states[buf].lines end,10),'blame received')
local ns=api.namespaces['annotations:git-blame']
check(#vim.api.nvim_buf_get_extmarks(buf,ns,0,-1,{})==1,'current-line annotation')
vim.api.nvim_win_set_cursor(0,{2,0});blame.render(buf)
local marks=vim.api.nvim_buf_get_extmarks(buf,ns,0,-1,{details=true})
check(#marks==1 and marks[1][2]==1,'cursor moves cached annotation')
if not vim.env.JETVIM_REAL_BLAME then check(calls==1,'cursor does not launch git') end
mode='all';blame.render(buf)
check(#vim.api.nvim_buf_get_extmarks(buf,ns,0,-1,{})==2,'all-line annotations')
vim.api.nvim_buf_set_lines(buf,0,1,false,{'unsaved'})
blame.render(buf)
check(#vim.api.nvim_buf_get_extmarks(buf,ns,0,-1,{})==0,'stale cache hidden')
if vim.env.JETVIM_REAL_BLAME then
  blame.refresh(buf)
  check(vim.wait(5000,function()return blame.states[buf] and blame.states[buf].lines end,10),'unsaved blame received')
  check(blame.states[buf].lines[1]=='Uncommitted changes','real Git uses unsaved contents')
  check(vim.fn.readfile(project..'/sample.txt')[1]=='first','blame does not write disk')
end
print('blame: '..count..' checks passed')
'''
(FIXTURE/'test.lua').write_text(script)
env=dict(os.environ,JETVIM_DISABLE_VCS='1',JETVIM_DISABLE_AUTOSAVE='1')
if real:
    env.pop('JETVIM_DISABLE_VCS',None)
    env['JETVIM_REAL_BLAME']='1'
result=subprocess.run([str(ROOT/'jetvim'),'--headless','-c','lua dofile(vim.env.JETVIM_ROOT .. "/.jetvim/tests/blame/test.lua")','+qa!'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=20)
print(result.stdout+result.stderr,end='')
raise SystemExit(result.returncode if 'checks passed' in result.stdout+result.stderr else 1)
