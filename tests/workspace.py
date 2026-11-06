#!/usr/bin/env python3
"""Workspace hook resolution and actual argv jobs; no Git or network."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / '.jetvim'
STATE.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix="workspace ' ", dir=STATE) as directory:
    fixture = Path(directory)
    package = fixture / 'packages/app'
    nested = package / 'src/deep'
    nested.mkdir(parents=True)
    (fixture/'package.json').write_text('{}')
    (package/'package.json').write_text('{}')
    source = nested/'{project} file.js'
    source.write_text('before\n')
    tool = '''#!/usr/bin/env python3
import json,os,pathlib,sys
pathlib.Path(os.environ['JETVIM_WORKSPACE_TESTLOG']).write_text(json.dumps({'argv':sys.argv,'cwd':os.getcwd(),'flat':os.getenv('ESLINT_USE_FLAT_CONFIG')}))
if pathlib.Path(sys.argv[0]).name=='prettier':
    pathlib.Path(sys.argv[-1]).write_text('formatted\\n')
else:
    print(json.dumps([{'filePath':next(arg for arg in sys.argv[1:] if arg.endswith(' file.js')),'messages':[{'line':1,'column':1,'severity':2,'message':'workspace lint'}]}]))
    sys.exit(1)
'''
    for directory in (fixture/'node_modules/.bin', package/'node_modules/.bin', fixture/'packages/tooling/.bin'):
        directory.mkdir(parents=True)
        for command in ('eslint','prettier'):
            binary=directory/command
            binary.write_text(tool)
            binary.chmod(0o755)
    script=r'''
local root=vim.env.JETVIM_WORKSPACE_FIXTURE
local file=root..'/packages/app/src/deep/{project} file.js'
local pkg=root..'/packages/app'
local resolve=require('jetvim.workspace').resolve
local count=0
local function check(value,message) assert(value,message);count=count+1 end
check(require('jetvim.workspace').contains('/virtual/path','/'),'filesystem root boundary accepts descendants')
check(not require('jetvim.workspace').contains('/virtual/sibling','/virtual/root'),'non-root boundary rejects siblings')
local function write(path,text) vim.fn.writefile({text},path) end
local function run(command,args,paths)
  local argv={command};vim.list_extend(argv,args or {'--format','json',file})
  return resolve(root,file,argv,paths)
end
local plan=run('prettier',{'--write',file})
check(plan.cwd==pkg,'nearest package cwd')
check(plan.argv[1]==pkg..'/node_modules/.bin/prettier','nearest local binary')
check(plan.argv[#plan.argv]==file,'literal placeholder filename')
vim.uv.fs_unlink(pkg..'/node_modules/.bin/prettier')
plan=run('prettier',{'--write',file},{'packages/tooling/.bin'})
check(plan.argv[1]==root..'/node_modules/.bin/prettier','ancestor binary before explicit fallback')
vim.uv.fs_unlink(root..'/node_modules/.bin/prettier')
plan=run('prettier',{'--write',file},{'packages/tooling/.bin'})
check(plan.argv[1]==root..'/packages/tooling/.bin/prettier','explicit project fallback')
local missing,err=run('prettier',{'--write',file},{})
check(not missing and err:find('not installed',1,true),'no global or download fallback')
missing,err=run('prettier',{'--write',file},{'../elsewhere'})
check(not missing and err:find('leaves',1,true),'escaping tool path rejected')
plan=run('eslint')
check(plan.skip==true,'unconfigured eslint skips')
write(root..'/eslint.config.mjs','export default []')
plan=run('eslint')
check(plan.config==root..'/eslint.config.mjs' and plan.env.ESLINT_USE_FLAT_CONFIG=='true','flat root config')
write(pkg..'/.eslintrc.json','{}')
plan=run('eslint')
check(plan.config==pkg..'/.eslintrc.json' and plan.env.ESLINT_USE_FLAT_CONFIG=='false','closer legacy config wins over root flat')
check(plan.argv[#plan.argv-1]=='--config' and plan.argv[#plan.argv]==pkg..'/.eslintrc.json','legacy config passed explicitly')
vim.uv.fs_unlink(pkg..'/.eslintrc.json')
write(pkg..'/package.json','{"eslintConfig":{}}')
plan=run('eslint')
check(plan.config==pkg..'/package.json' and plan.env.ESLINT_USE_FLAT_CONFIG=='false','package eslintConfig mode')
check(#plan.argv==4,'package JSON is not passed as --config')
write(pkg..'/package.json','{}')
write(pkg..'/eslint.config.cjs','module.exports=[]')
plan=run('eslint')
check(plan.config==pkg..'/eslint.config.cjs','nearest flat config')
plan=run('eslint',{'--config','custom.config.mjs','--format','json',file})
check(plan.config=='custom.config.mjs' and #plan.argv==6 and plan.env.ESLINT_USE_FLAT_CONFIG=='true','explicit flat config preserved')
plan=run('eslint',{'--config=custom.eslintrc.json',file})
check(plan.env.ESLINT_USE_FLAT_CONFIG=='false' and #plan.argv==3,'explicit JSON config preserved')
plan=run('eslint',{'--format','json','--',file})
check(plan.argv[4]=='--config' and plan.argv[6]=='--' and plan.argv[7]==file,'config inserted before argument separator')
local original={'prettier','--write',file}
resolve(root,file,original,{'packages/tooling/.bin'})
check(original[1]=='prettier' and #original==3,'caller argv unchanged')
-- Real hook processes prove cwd/env/argv survive the adapter and ESLint code1.
require('jetvim.project').setup(root)
vim.cmd.edit(vim.fn.fnameescape(file))
local buf=vim.api.nvim_get_current_buf()
local configured={tool_paths={'packages/tooling/.bin'},after_save={
  {name='format',workspace=true,pattern=[[\.js$]],command={'prettier','--write','{file}'}},
  {name='lint',workspace=true,pattern=[[\.js$]],command={'eslint','--format','json','{file}'},diagnostics='eslint'},
}}
require('jetvim.settings').get=function()return {autosave={enabled=false},hooks=configured}end
local hooks=require('jetvim.hooks')
hooks.run(buf)
check(vim.wait(5000,function()return hooks.states[buf]==nil end,10),'workspace hooks finished')
check(vim.api.nvim_buf_get_lines(buf,0,1,false)[1]=='formatted','workspace formatter reload')
local metadata=vim.json.decode(table.concat(vim.fn.readfile(vim.env.JETVIM_WORKSPACE_TESTLOG),'\n'))
check(metadata.cwd==pkg and metadata.flat=='true','actual process cwd and ESLint mode')
check(metadata.argv[#metadata.argv-2]==file,'actual argv preserves placeholder filename')
local ns=require('jetvim.api').namespaces['hook:lint']
check(#vim.diagnostic.get(buf,{namespace=ns})==1,'workspace ESLint JSON published')
vim.uv.fs_unlink(root..'/eslint.config.mjs');vim.uv.fs_unlink(pkg..'/eslint.config.cjs')
configured.after_save={configured.after_save[2]}
local prior=table.concat(vim.fn.readfile(vim.env.JETVIM_WORKSPACE_TESTLOG),'\n')
hooks.run(buf)
check(hooks.states[buf]==nil and not vim.b[buf].jetvim_hook_running,'configless skip releases busy flag')
check(#vim.diagnostic.get(buf,{namespace=ns})==0,'configless skip clears previous diagnostics')
check(table.concat(vim.fn.readfile(vim.env.JETVIM_WORKSPACE_TESTLOG),'\n')==prior,'configless skip does not execute ESLint')
local auto=require('jetvim.autosave')
local expected=vim.deepcopy(auto.states[buf].expected)
write(file,'external different content')
check(not auto.acknowledge(buf),'acknowledge refuses mismatching external bytes')
check(vim.deep_equal(auto.states[buf].expected,expected),'failed acknowledge leaves baseline unchanged')
write(file,'formatted')
check(auto.acknowledge(buf),'acknowledge accepts matching clean bytes')
check(auto.states[buf].safe==true,'accepted acknowledgement keeps autosave safe')
print('workspace: '..count..' checks passed')
'''
    (fixture/'test.lua').write_text(script)
    env=dict(os.environ,JETVIM_DISABLE_VCS='1',JETVIM_DISABLE_AUTOSAVE='1',JETVIM_WORKSPACE_FIXTURE=str(fixture),JETVIM_WORKSPACE_TESTLOG=str(fixture/'job.json'))
    result=subprocess.run([str(ROOT/'jetvim'),'--headless','-c','lua dofile(vim.env.JETVIM_WORKSPACE_FIXTURE.."/test.lua")','+qa!'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=30)
    output=result.stdout+result.stderr
    print(output,end='')
    raise SystemExit(result.returncode if 'checks passed' in output else 1)
