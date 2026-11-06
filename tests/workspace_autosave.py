#!/usr/bin/env python3
"""Actual idle/focus autosaves run format + ESLint hooks and publish diagnostics."""
import json
from pathlib import Path
import tempfile
import time
ROOT=Path(__file__).resolve().parent.parent
support={'__file__':str(ROOT/'tests/autosave.py')}
exec((ROOT/'tests/autosave.py').read_text().split('\nwith tempfile.TemporaryDirectory',1)[0],support)
Editor,equal,STATE=support['Editor'],support['equal'],support['STATE']
with tempfile.TemporaryDirectory(prefix='workspace-autosave-',dir=STATE) as directory:
    project=Path(directory)
    home=project/'home';home.mkdir()
    preferences=home/'settings.lua'
    (project/'main.lua').write_text('-- initial\n')
    source=project/'main.js';source.write_text('initial\n')
    (project/'package.json').write_text('{}')
    (project/'eslint.config.cjs').write_text('module.exports=[]')
    binaries=project/'node_modules/.bin';binaries.mkdir(parents=True)
    tool='''#!/usr/bin/env python3
import json,pathlib,sys,time
root=pathlib.Path(__file__).resolve().parents[2]
file=next(arg for arg in sys.argv[1:] if arg.endswith('.js'))
name=pathlib.Path(sys.argv[0]).name
with (root/'jobs.log').open('a') as stream: stream.write(name+'\\n')
if name=='prettier':
    path=pathlib.Path(file);path.write_text(path.read_text().upper())
else:
    print(json.dumps([{'filePath':file,'messages':[{'line':1,'column':1,'severity':2,'message':'saved file lint'}]}]))
    sys.exit(1)
'''
    for name in ('prettier','eslint'):
        binary=binaries/name;binary.write_text(tool);binary.chmod(0o755)
    def config(debounce=True):
        preferences.write_text('''return {
  autosave={enabled=true,debounce='''+('true' if debounce else 'false')+''',delay_ms=1000,on_focus_lost=true},
  hooks={after_save={
    {name='format',pattern=[[\\.js$]],workspace=true,command={'prettier','--write','{file}'}},
    {name='lint',pattern=[[\\.js$]],workspace=true,command={'eslint','--format','json','{file}'},diagnostics='eslint'},
  }},
}
''')
    config()
    editor=Editor(project,preferences)
    try:
        editor.open(source)
        editor.raw('x')
        time.sleep(.35)
        equal((project/'jobs.log').exists(),False,'idle hooks wait for debounce')
        editor.wait('local b=vim.api.nvim_get_current_buf(); local ns=require("jetvim.api").namespaces["hook:lint"]; return ns and #vim.diagnostic.get(b,{namespace=ns})==1',seconds=6)
        equal(source.read_text(),'XINITIAL\n','idle autosave formats disk')
        equal(editor.lua('return vim.api.nvim_buf_get_lines(0,0,1,false)[1]'),'XINITIAL','idle formatter reloads editor')
        equal((project/'jobs.log').read_text().splitlines(),['prettier','eslint'],'idle save runs both hooks exactly once')
        equal(editor.lua('return vim.fn.mode()'),'i','idle hook pipeline preserves insert mode')
        # A second actual edit must also invoke hooks, not only the first save.
        editor.raw('y')
        editor.wait('return vim.fn.readfile(vim.uv.cwd().."/jobs.log")[4] == "eslint"',seconds=6)
        editor.wait('return not vim.b.jetvim_hook_running')
        equal(source.read_text(),'XYINITIAL\n','second idle save formats newer contents')
        equal(editor.lua('local ns=require("jetvim.api").namespaces["hook:lint"];return #vim.diagnostic.get(0,{namespace=ns})'),1,'second idle save publishes lint')
        # A formatter may rewrite identical bytes. Later disk polling must not
        # erase diagnostics that were just produced for that same saved text.
        editor.raw(' '); editor.raw(b'\x7f')
        editor.wait('return vim.fn.readfile(vim.uv.cwd().."/jobs.log")[6] == "eslint"',seconds=6)
        editor.wait('return not vim.b.jetvim_hook_running')
        time.sleep(.8)
        equal(source.read_text(),'XYINITIAL\n','no-op formatting leaves contents unchanged')
        equal(editor.lua('local ns=require("jetvim.api").namespaces["hook:lint"];return #vim.diagnostic.get(0,{namespace=ns})'),1,'no-op formatting diagnostics survive disk polling')
        editor.raw('q')
        editor.wait('return vim.fn.readfile(vim.uv.cwd().."/jobs.log")[8] == "eslint"',seconds=6)
        editor.wait('return not vim.b.jetvim_hook_running')
        equal(source.read_text(),'XYQINITIAL\n','next idle save works after no-op formatter metadata change')
        # Focus-leave autosaves work with debounce entirely disabled.
        config(debounce=False)
        editor.lua('vim.cmd("JetvimReloadSettings"); return true')
        editor.raw('z');time.sleep(.25)
        equal(len((project/'jobs.log').read_text().splitlines()),8,'disabled debounce runs no idle hook')
        source_buf=editor.lua('return vim.api.nvim_get_current_buf()')
        editor.raw(b'\x1b[49;9u')
        editor.wait('return vim.bo.filetype=="jetvim-tree"')
        editor.wait('return vim.fn.readfile(vim.uv.cwd().."/jobs.log")[10] == "eslint"',seconds=6)
        editor.wait(f'return not vim.b[{source_buf}].jetvim_hook_running')
        equal(source.read_text(),'XYQZINITIAL\n','focus-leave autosave formats disk')
        equal(editor.lua(f'local ns=require("jetvim.api").namespaces["hook:lint"];return #vim.diagnostic.get({source_buf},{{namespace=ns}})'),1,'focus-leave save publishes lint into hidden editor')
        equal(editor.lua('return vim.bo.filetype'),'jetvim-tree','background format/lint preserves sidebar focus')
    finally:
        editor.close()
    # Reproduce the former 100ms configuration: a new edit during a running
    # formatter must survive, and autosave pauses rather than overwrite either
    # side. A deliberate Cmd-S resolves that conflict and restarts lint safely.
    source.write_text('initial\n');(project/'jobs.log').unlink()
    config()
    preferences.write_text(preferences.read_text().replace('delay_ms=1000','delay_ms=100'))
    formatter=binaries/'prettier'
    formatter.write_text(tool.replace("path=pathlib.Path(file);", "time.sleep(.4); path=pathlib.Path(file);"))
    editor=Editor(project,preferences)
    try:
        editor.open(source);editor.raw('x')
        editor.wait('return vim.fn.filereadable(vim.uv.cwd().."/jobs.log")==1',seconds=3)
        editor.raw('y')
        editor.wait('return not vim.b.jetvim_hook_running',seconds=4)
        time.sleep(.65)
        equal(editor.lua('return vim.api.nvim_buf_get_lines(0,0,1,false)[1]'),'xyinitial','typing during formatter preserves newer editor text')
        equal(source.read_text(),'XINITIAL\n','formatter output retained on disk for review')
        equal(editor.lua('return vim.bo.modified'),True,'formatter conflict keeps edits dirty')
        equal((project/'jobs.log').read_text().splitlines(),['prettier'],'stale formatter output skips ESLint')
        equal(editor.lua('local s=require("jetvim.autosave").states[vim.api.nvim_get_current_buf()]; return s.error~=nil'),True,'autosave pauses on formatter/disk conflict')
        start=len(editor.output)
        editor.raw(b'\x1b[115;9u')
        deadline=time.monotonic()+3
        while b'Do you really want to write' not in editor.output[start:]:
            assert time.monotonic()<deadline, 'explicit save conflict confirmation missing'
            time.sleep(.02)
        editor.raw('y')
        deadline=time.monotonic()+3
        while b'Press ENTER' not in editor.output[start:]:
            assert time.monotonic()<deadline, 'post-save acknowledgement prompt missing'
            time.sleep(.02)
        editor.raw('\r')
        editor.wait('return vim.fn.readfile(vim.uv.cwd().."/jobs.log")[3]=="eslint"',seconds=5)
        editor.wait('return not vim.b.jetvim_hook_running')
        equal(source.read_text(),'XYINITIAL\n','explicit CmdS restarts formatter using latest edits')
        equal(editor.lua('local ns=require("jetvim.api").namespaces["hook:lint"];return #vim.diagnostic.get(0,{namespace=ns})'),1,'ESLint resumes after explicit save resolves conflict')
    finally:
        editor.close()
print(f'PASS: {support["checks"]} workspace autosave hook PTY checks')
