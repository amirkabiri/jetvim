#!/usr/bin/env python3
"""Elixir PTY/LSP integration; --real requires the optional installed ElixirLS."""
import argparse
import json
import os
from pathlib import Path
import shlex
import tempfile

ROOT = Path(__file__).resolve().parent.parent
support = {'__file__': str(ROOT / 'tests/autosave.py')}
exec((ROOT / 'tests/autosave.py').read_text().split('\nwith tempfile.TemporaryDirectory', 1)[0], support)
Editor, equal, STATE = support['Editor'], support['equal'], support['STATE']
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--real', action='store_true')
args = parser.parse_args()

# This is a protocol fixture, not an implementation or a substitute for ElixirLS.
FAKE_SERVER = r'''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
root=Path(os.environ['JETVIM_PROJECT'])
def send(message):
    data=json.dumps(dict(jsonrpc='2.0',**message)).encode()
    sys.stdout.buffer.write(('Content-Length: %d\r\n\r\n'%len(data)).encode()+data);sys.stdout.buffer.flush()
def location(name,line,start,end):
    return {'uri':(root/name).as_uri(),'range':{'start':{'line':line,'character':start},'end':{'line':line,'character':end}}}
while True:
    headers={}
    while True:
        line=sys.stdin.buffer.readline()
        if not line:sys.exit(0)
        if line in (b'\r\n',b'\n'):break
        key,value=line.decode().split(':',1);headers[key.lower()]=value.strip()
    message=json.loads(sys.stdin.buffer.read(int(headers['content-length'])))
    method=message.get('method');params=message.get('params',{})
    result=None
    if method=='initialize':result={'capabilities':{'definitionProvider':True,'referencesProvider':True,'textDocumentSync':{'openClose':True,'change':1,'save':{'includeText':True}}},'serverInfo':{'name':'Jetvim Elixir protocol fixture'}}
    elif method=='textDocument/definition':
        position=params['position'];name=Path(params['textDocument']['uri']).name
        result=None if name=='greeter.ex' and position['character']<6 else location('lib/greeter.ex',1,2,43)
    elif method=='textDocument/references':result=[location('lib/caller.ex',1,23,28)]
    elif method in ('textDocument/didOpen','textDocument/didSave'):
        doc=params['textDocument']
        send({'method':'textDocument/publishDiagnostics','params':{'uri':doc['uri'],'diagnostics':[{'range':{'start':{'line':1,'character':2},'end':{'line':1,'character':5}},'message':'fixture diagnostic','severity':2,'source':'elixir-fixture'}]}})
    elif method=='exit':sys.exit(0)
    if 'id' in message:send({'id':message['id'],'result':result})
'''

def literal(value): return json.dumps(str(value), ensure_ascii=False)

with tempfile.TemporaryDirectory(prefix='elixir-lsp-', dir=STATE) as directory:
    project = Path(directory) / 'project'; project.mkdir()
    home = Path(directory) / 'home'; home.mkdir()
    server = home / 'tools/elixir-ls/language_server.sh'; server.parent.mkdir(parents=True)
    if args.real:
        real_home = Path(os.environ.get('JETVIM_ELIXIR_REAL_HOME', str(STATE))).resolve()
        actual = real_home / 'tools/elixir-ls/language_server.sh'
        assert actual.is_file(), 'Run scripts/setup-elixir.sh first; set JETVIM_ELIXIR_REAL_HOME for a custom tools home.'
        server.write_text('#!/bin/sh\nexport JETVIM_HOME='+shlex.quote(str(real_home))+'\nexec '+shlex.quote(str(actual))+' "$@"\n')
    else:
        server.write_text(FAKE_SERVER)
    server.chmod(0o755)
    (project / 'lib').mkdir(); (project / 'test').mkdir()
    (project / 'main.lua').write_text('-- fixture bootstrap\n')
    (project / 'mix.exs').write_text('defmodule JetvimFixture.MixProject do\n  use Mix.Project\n  def project, do: [app: :jetvim_fixture, version: "0.1.0", elixir: ">= 1.16.0", deps: []]\n  def application, do: []\nend\n')
    greeter = project / 'lib/greeter.ex'
    greeter.write_text('defmodule Greeter do\n  def greet(name), do: "Hello " <> name\nend\n')
    caller = project / 'lib/caller.ex'
    caller_lines = ['defmodule Caller do', '  def call, do: Greeter.greet("Jetvim")', 'end']
    caller.write_text('\n'.join(caller_lines)+'\n')
    script = project / 'test/sample_test.exs'; script.write_text('Greeter.greet("script")\n')
    editor = Editor(project, home / 'settings.lua', disabled=True)
    lua = editor.lua
    try:
        lua('require("jetvim.project").open('+literal(caller)+');return true')
        editor.wait('return #vim.lsp.get_clients({bufnr=0,method="textDocument/definition"})>0',seconds=120 if args.real else 10)
        equal(lua('return vim.bo.filetype'),'elixir','.ex uses Elixir filetype')
        equal(lua('return vim.lsp.is_enabled("elixirls")'),True,'installed optional Elixir server is enabled')
        equal(lua('return vim.lsp.is_enabled("ts_ls") and vim.lsp.is_enabled("gopls")'),True,'existing TypeScript and Go configurations remain enabled')
        config = lua('local c=vim.lsp.get_clients({bufnr=0})[1];return {name=c.name,root=c.config.root_dir,cmd=c.config.cmd,env=c.config.cmd_env,settings=c.config.settings}')
        equal(config['name'],'elixirls','expected Elixir language client attaches')
        equal(config['root'],str(project),'Mix root is selected instead of the lib directory')
        equal(config['cmd'],[str(server)],'local language-server executable is used without global PATH edits')
        for variable, suffix in [('MIX_HOME','tools/elixir/mix'),('HEX_HOME','tools/elixir/hex'),('MIX_INSTALL_DIR','tools/elixir/install'),('TMPDIR','tmp'),('REBAR_CACHE_DIR','cache/rebar3')]:
            equal(config['env'][variable],str(home/suffix),variable+' stays in the configured Jetvim home')
        equal(config['settings']['elixirLS']['dialyzerEnabled'],False,'expensive Dialyzer analysis is opt-in')
        equal(config['settings']['elixirLS']['fetchDeps'],False,'project dependency downloads are explicit')
        equal(config['settings']['elixirLS']['mcpEnabled'],False,'unrelated MCP server remains disabled')
        lua('vim.api.nvim_win_set_cursor(0,{2,'+str(caller_lines[1].index('greet')+1)+'});return true')
        if args.real:
            editor.wait('local c=vim.lsp.get_clients({bufnr=0,method="textDocument/definition"})[1];if not c then return false end;local r=vim.lsp.buf_request_sync(0,"textDocument/definition",vim.lsp.util.make_position_params(0,c.offset_encoding),1500);for _,v in pairs(r or {})do local result=v.result;if type(result)=="table" then if result.uri or result.targetUri then result={result}end;for _,target in ipairs(result)do if (target.uri or target.targetUri)==vim.uri_from_fname('+literal(greeter)+')then return true end end end end;return false',seconds=120)
        editor.raw(b'\x1b[98;9u')
        editor.wait('return vim.api.nvim_buf_get_name(0)=='+literal(greeter),seconds=30)
        equal(lua('return vim.api.nvim_win_get_cursor(0)'),[2,6],'native Command-B lands on function name rather than ElixirLS declaration keyword')
        equal(lua('return vim.api.nvim_buf_get_lines(0,0,-1,false)'),greeter.read_text().splitlines(),'navigation does not insert shortcut text')
        lua('_G.ElixirPicker=nil;local pick=require("jetvim.ui").pick;require("jetvim.ui").pick=function(title,items,accept,options) ElixirPicker={title=title,items=items};return pick(title,items,accept,options)end;return true')
        editor.raw(b'\x1b[98;9u')
        editor.wait('return ElixirPicker~=nil and ElixirPicker.title=="Usages" and vim.bo.buftype=="prompt"',seconds=60)
        labels = lua('local r={};for _,i in ipairs(ElixirPicker.items)do r[#r+1]=i.label end;return r')
        equal(any('caller.ex' in label for label in labels),True,'Command-B on definition lists usages')
        editor.raw(b'\r');editor.wait('return vim.api.nvim_buf_get_name(0)=='+literal(caller))
        equal(lua('return vim.api.nvim_buf_get_name(0)'),str(caller),'Enter in usages returns to calling file')
        lua('require("jetvim.project").open('+literal(script)+');return true')
        editor.wait('return #vim.lsp.get_clients({bufnr=0,method="textDocument/definition"})>0',seconds=30)
        equal(lua('return vim.bo.filetype'),'elixir','.exs scripts use the same Elixir client')
        lua('vim.api.nvim_win_set_cursor(0,{1,9});return true')
        bindings=json.loads((ROOT/'config/keymap.json').read_text())
        index=next(i for i,item in enumerate(bindings,1) if item['id']=='definition')
        editor.raw(f'\x1b[{0xF0000+index}u'.encode())
        editor.wait('return vim.api.nvim_buf_get_name(0)=='+literal(greeter),seconds=30)
        equal(lua('return vim.api.nvim_buf_get_name(0)'),str(greeter),'private terminal relay navigates an Elixir script reference')
        lua('require("jetvim.project").open('+literal(caller)+');return true')
        if args.real:
            lua('vim.api.nvim_buf_set_lines(0,1,2,false,{"  def call, do: missing_function()"});return true')
            editor.raw(b'\x1b[115;9u')
        if args.real:
            expected_diagnostic = 'for _,d in ipairs(vim.diagnostic.get(0))do if d.severity==vim.diagnostic.severity.ERROR and d.lnum==1 and d.message:find("missing_function",1,true)then _G.ElixirObservedDiagnostic=vim.deepcopy(d);return true end end;return false'
            try:
                editor.wait(expected_diagnostic,seconds=120)
            except AssertionError as error:
                details=lua('return vim.diagnostic.get(0)')
                raise AssertionError(str(error)+'; current diagnostics='+json.dumps(details,ensure_ascii=False)) from error
            diagnostic=lua('return ElixirObservedDiagnostic')
        else:
            editor.wait('return #vim.diagnostic.get(0)>0',seconds=10)
            diagnostic=lua('return vim.diagnostic.get(0)[1]')
        equal(bool(diagnostic),True,'language-server diagnostics reach the editor')
        equal(diagnostic['lnum'],1,'diagnostic retains its source line')
        info=lua('_G.ElixirMessages={};local original=vim.notify;vim.notify=function(text)table.insert(ElixirMessages,text)end;vim.cmd("JetvimLspInfo");vim.notify=original;return table.concat(ElixirMessages,"\\n")')
        equal('elixirls enabled: yes' in info and str(server) in info and str(project) in info,True,'LSP info identifies Elixir server, enabled state and Mix root')
        equal(lua('return vim.v.errmsg'),'','Elixir integration leaves no editor errors')
        label='real ElixirLS' if args.real else 'protocol fixture; not a real Elixir server'
        print(f'PASS: {support["checks"]} Elixir LSP terminal checks ({label})')
    finally:
        editor.close()
