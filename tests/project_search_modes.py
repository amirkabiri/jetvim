#!/usr/bin/env python3
"""Scoped Find in Files text/regex modes through native and relay input."""
import json
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parent.parent
support = {'__file__': str(ROOT / 'tests/autosave.py')}
exec((ROOT / 'tests/autosave.py').read_text().split('\nwith tempfile.TemporaryDirectory', 1)[0], support)
Editor, equal, STATE = support['Editor'], support['equal'], support['STATE']

with tempfile.TemporaryDirectory(prefix='project-search-modes-', dir=STATE) as directory:
    project = Path(directory); (project / 'home').mkdir(); scope = project / 'scope'; scope.mkdir()
    (project / 'main.lua').write_text('-- unchanged editor\n')
    lines = ['Hello World', 'hello world', 'HELLO WORLD', 'a.b', 'aXb', 'A.B', '(x|y)',
             'x+y? ^ $ [ bracket]', r'C:\Temp\file \C \c \v \V', 'path/foo', '/open', 'ÄPFEL äpfel', '--smart-case']
    (scope / 'a.txt').write_text('\n'.join(lines)+'\n')
    (scope / 'b.txt').write_text('HELLO WORLD\npath/foo\n')
    (project / 'outside.txt').write_text('hello world\na.b\n')
    rgconfig = project / 'rg.conf'; rgconfig.write_text('--case-sensitive\n--fixed-strings\n--glob=!a.txt\n')
    previous_config = os.environ.get('RIPGREP_CONFIG_PATH')
    os.environ['RIPGREP_CONFIG_PATH'] = str(rgconfig)
    try:
        editor = Editor(project, project / 'home/settings.lua', disabled=True, disable_lsp=True)
    finally:
        if previous_config is None: os.environ.pop('RIPGREP_CONFIG_PATH', None)
        else: os.environ['RIPGREP_CONFIG_PATH'] = previous_config
    lua = editor.lua
    bindings = json.loads((ROOT / 'config/keymap.json').read_text())
    index = next(i for i,item in enumerate(bindings,1) if item['id']=='find_project')
    relay = f'\x1b[{0xF0000+index}u'.encode()
    def open_search(chord):
        editor.raw(b'\x1b[27u')
        equal(lua('local t=require("jetvim.tree");t.focus();for row,e in pairs(t.rows)do if e.path=='+json.dumps(str(scope))+' then '
                  'vim.api.nvim_win_set_cursor(t.win,{row,0});return true end end;return false'),True,'scope folder selected')
        editor.raw(chord)
        editor.wait('local s=require("jetvim.project_search").state;return s~=nil and vim.fn.mode()=="i"')
        equal(lua('return require("jetvim.project_search").state.scope'),str(scope),'shortcut retains selected folder scope')
    def search(text, expected, regex=False, ignore_case=True, expression=None):
        editor.raw(b'\x15'+text.encode())
        editor.wait('local s=require("jetvim.project_search").state;return s.query=='+json.dumps(text,ensure_ascii=False)+' and not s.timer and not s.busy')
        equal(lua('local s=require("jetvim.project_search").state;local out={};for _,i in ipairs(s.items)do out[#out+1]={vim.fs.basename(i.path),i.line}end;'
                  'table.sort(out,function(a,b)return a[1]==b[1] and a[2]<b[2] or a[1]<b[1]end);return out'),expected,'matching mode: '+text)
        equal(lua('return vim.fn.mode()'),'i','mode query remains editable')
        equal(lua('local s=require("jetvim.project_search").state;return vim.api.nvim_buf_get_lines(s.input,0,1,false)[1]'),text,'mode parsing preserves original query text')
        equal(lua('local s=require("jetvim.project_search").state;for _,i in ipairs(s.items)do if not require("jetvim.project_search").contains(s.scope,i.path)then return false end end;return true'),True,'all matches stay scoped')
        args = lua('return _G.SearchModeCalls[#_G.SearchModeCalls].argv')
        equal('--fixed-strings' in args,not regex,'only literal mode uses fixed strings')
        equal('--ignore-case' in args,ignore_case,'ignore case flag is explicit')
        equal('--case-sensitive' in args,not ignore_case,'sensitive regex overrides smart case')
        equal('--no-config' in args,True,'workspace rg config cannot override search mode')
        equal(args[-3:],['--',text if expression is None else expression,'.'],'pattern remains an argv value behind option terminator')
        equal(lua('return _G.SearchModeCalls[#_G.SearchModeCalls].cwd'),str(scope),'rg cwd remains guarded scope')
    try:
        lua('_G.SearchModeSystem=vim.system;_G.SearchModeCalls={};vim.system=function(argv,opts,done) '
            'if argv[1]=="rg" then table.insert(_G.SearchModeCalls,{argv=argv,cwd=opts.cwd})end;return _G.SearchModeSystem(argv,opts,done)end;return true')
        open_search(b'\x1b[102;10u')
        equal(lua('return vim.api.nvim_eval_statusline(vim.wo.statusline,{}).str:find("Text",1,true)~=nil'),True,'modal advertises plain text and slash regex')
        hello = [['a.txt',1],['a.txt',2],['a.txt',3],['b.txt',1]]
        search('hello world',hello)
        search('HELLO WORLD',hello)
        search('a.b',[['a.txt',4],['a.txt',6]])
        for literal,row in [('(x|y)',7),('x+y?',8),('^ $',8),('[',8),(r'C:\Temp\file',9),(r'\C',9),(r'\v',9),('/open',11),('--smart-case',13),('äpfel',12)]:
            search(literal,[['a.txt',row]])
        search('/a.b/',[['a.txt',4],['a.txt',5]],regex=True,ignore_case=False,expression='a.b')
        search('/a.b/i',[['a.txt',4],['a.txt',5],['a.txt',6]],regex=True,expression='a.b')
        search('/hello world/',[['a.txt',2]],regex=True,ignore_case=False,expression='hello world')
        search('/HELLO WORLD/',[['a.txt',3],['b.txt',1]],regex=True,ignore_case=False,expression='HELLO WORLD')
        search('/hello world/i',hello,regex=True,expression='hello world')
        search('/path\\/foo/',[['a.txt',10],['b.txt',2]],regex=True,ignore_case=False,expression='path/foo')
        editor.raw(b'\x15/hello/g')
        editor.wait('local s=require("jetvim.project_search").state;return not s.timer and s.message:find("Invalid regex flag",1,true)~=nil')
        equal(lua('return #require("jetvim.project_search").state.items'),0,'unsupported flags clear results and show inline error')
        editor.raw(b'\x15/[/')
        editor.wait('local s=require("jetvim.project_search").state;return not s.timer and not s.busy and s.message:find("Search failed:",1,true)~=nil')
        equal(lua('return vim.bo.filetype'),'jetvim-project-search','invalid rg regex leaves modal focused')
        equal(lua('return #require("jetvim.project_search").state.items'),0,'invalid regex never reuses stale matches')
        equal(lua('return vim.v.errmsg'),'','invalid regex never opens a Neovim error prompt')
        editor.raw(b'\x1b[27u');editor.wait('return require("jetvim.project_search").state==nil')
        open_search(relay);search('HELLO WORLD',hello)
        # Explicitly deliver cancelled callbacks across literal/regex transitions.
        lua('_G.SearchModeJobs={};vim.system=function(argv,opts,done)local job={argv=argv,opts=opts,done=done,killed=false};'
            'job.kill=function(self)self.killed=true end;table.insert(_G.SearchModeJobs,job);return job end;return true')
        editor.raw(b'\x15old');editor.wait('return #_G.SearchModeJobs==1')
        def stream(job):
            entries = ''.join(json.dumps({'type':'match','data':{'path':{'text':'a.txt'},'lines':{'text':'old'},'line_number':row,'submatches':[{'start':0}]}})+'\n' for row in (1,2))
            lua(f'_G.SearchModeJobs[{job}].opts.stdout(nil,'+json.dumps(entries)+');return true')
        stream(1);editor.wait('return #require("jetvim.project_search").state.items==2')
        editor.raw(b'\x1b[1;2B\x15/new/i');editor.wait('return #_G.SearchModeJobs==2')
        equal(lua('return _G.SearchModeJobs[1].killed'),True,'literal to regex cancels active job')
        equal(lua('local s=require("jetvim.project_search").state;return {#s.items,s.anchor or 0,s.selected}'),[0,0,1],'mode change clears selected range')
        stream(1);lua('_G.SearchModeJobs[1].opts.stderr(nil,"stale failure");_G.SearchModeJobs[1].done({code=2});return true')
        equal(lua('local s=require("jetvim.project_search").state;return s.busy and #s.items==0 and s.message~="stale failure"'),True,'cancelled literal callbacks cannot alter regex query')
        editor.raw(b'\x15PLAIN');editor.wait('return #_G.SearchModeJobs==3')
        equal(lua('return _G.SearchModeJobs[2].killed'),True,'regex to literal cancels active job')
        stream(2);lua('_G.SearchModeJobs[2].done({code=0});return true')
        equal(lua('local s=require("jetvim.project_search").state;return s.query=="PLAIN" and s.busy and #s.items==0'),True,'stale regex completion cannot revive results')
        equal(lua('return vim.tbl_contains(_G.SearchModeJobs[3].argv,"--fixed-strings") and vim.tbl_contains(_G.SearchModeJobs[3].argv,"--ignore-case")'),True,'returning to text restores fixed ignore-case args')
        stream(3);lua('_G.SearchModeJobs[3].done({code=0});return true')
        editor.wait('return not require("jetvim.project_search").state.busy')
        editor.raw(b'\x15/hello/g');editor.wait('return require("jetvim.project_search").state.message:find("Invalid regex flag",1,true)~=nil')
        equal(lua('return #_G.SearchModeJobs'),3,'invalid flags never launch rg')
        lua('vim.system=_G.SearchModeSystem;return true')
        editor.raw(b'\x1b[27u');editor.wait('return require("jetvim.project_search").state==nil')
        equal((scope/'a.txt').read_text(),'\n'.join(lines)+'\n','search modes never change matching files')
        equal((project/'main.lua').read_text(),'-- unchanged editor\n','query input never writes editor file')
        equal(lua('return vim.api.nvim_buf_get_lines(vim.fn.bufnr("main.lua"),0,-1,false)'),['-- unchanged editor'],'query input never changes editor memory')
        equal(lua('return vim.v.errmsg'),'','mode transitions leave no Neovim error')
        print(f'PASS: {support["checks"]} scoped project search mode terminal checks')
    finally:
        editor.close()
