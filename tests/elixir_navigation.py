#!/usr/bin/env python3
"""ElixirLS declaration ranges: mocked clients, actual terminal navigation keys."""
import json
from pathlib import Path
import tempfile

ROOT=Path(__file__).resolve().parent.parent
support={'__file__':str(ROOT/'tests/autosave.py')}
exec((ROOT/'tests/autosave.py').read_text().split('\nwith tempfile.TemporaryDirectory',1)[0],support)
Editor,equal,STATE=support['Editor'],support['equal'],support['STATE']
with tempfile.TemporaryDirectory(prefix='elixir-nav-',dir=STATE) as directory:
    project=Path(directory);(project/'home').mkdir()
    main=project/'main.lua';main.write_text('caller()\n')
    target=project/'target.ex';target.write_text('  def héllo(name) do\n    héllo(name)\n  end\n')
    editor=Editor(project,project/'home/settings.lua',disabled=True,disable_lsp=True)
    lua=editor.lua
    def setup(encoding='utf-16',client='elixirls',keyword='def',identifier='héllo',operator=False):
        lua('vim.cmd.stopinsert();vim.bo.modified=false;require("jetvim.project").open('+json.dumps(str(main))+');vim.cmd.stopinsert();'
            'local b=vim.fn.bufadd('+json.dumps(str(target))+');vim.fn.bufload(b);'
            'vim.api.nvim_buf_set_lines(b,0,-1,false,vim.json.decode('+json.dumps(json.dumps([
                '  '+keyword+' '+identifier+(' + right do' if operator else '(name) do'),'    '+identifier+'(name)','  end']))+'));'
            '_G.ElixirNavRequests={};_G.ElixirNavShown=nil;_G.ElixirNavClient={name='+json.dumps(client)+',offset_encoding='+json.dumps(encoding)+'};'
            'function ElixirNavClient:request(method,params,complete) '
            'ElixirNavRequests[#ElixirNavRequests+1]=method;'
            'complete(nil,method=="textDocument/definition" and {uri=vim.uri_from_fname('+json.dumps(str(target))+'),'
            'range={start={line=0,character=2},["end"]={line=2,character=5}}} or {});return true,1 end;'
            'function ElixirNavClient:cancel_request()end;return true')
    try:
        lua('_G.ElixirNavClients=vim.lsp.get_clients;_G.ElixirNavShow=vim.lsp.util.show_document;'
            'vim.lsp.get_clients=function(opts)if opts and (opts.method=="textDocument/definition" or opts.method=="textDocument/references")then return {ElixirNavClient}end;return ElixirNavClients(opts)end;'
            'vim.lsp.util.show_document=function(location,encoding,opts)ElixirNavShown=vim.deepcopy(location);return ElixirNavShow(location,encoding,opts)end;return true')
        for encoding,end_character in [('utf-8',12),('utf-16',11),('utf-32',11)]:
            setup(encoding)
            editor.raw(b'\x1b[98;9u')
            editor.wait('return ElixirNavShown~=nil')
            selection=lua('return ElixirNavShown.targetSelectionRange')
            equal(selection,{'start':{'line':0,'character':6},'end':{'line':0,'character':end_character}},encoding+' converts Unicode identifier byte endpoints')
            equal(lua('return vim.api.nvim_win_get_cursor(0)'),[1,6],encoding+' jumps to identifier rather than keyword')
            equal(lua('return ElixirNavShown.targetRange'),{'start':{'line':0,'character':2},'end':{'line':2,'character':5}},encoding+' preserves full declaration target range')
            lua('vim.api.nvim_win_set_cursor(0,{2,5});ElixirNavRequests={};ElixirNavShown=nil;return true')
            editor.raw(b'\x1b[98;9u');editor.wait('return ElixirNavShown~=nil')
            equal(lua('return ElixirNavRequests'),['textDocument/definition'],encoding+' recursive body reference jumps to definition instead of listing usages')
            equal(lua('return vim.api.nvim_win_get_cursor(0)'),[1,6],encoding+' recursive reference returns to name')
        for keyword in ('defp','defmacro','defmacrop','defguard','defguardp'):
            setup(keyword=keyword,identifier='greet')
            editor.raw(b'\x1b[98;9u');editor.wait('return ElixirNavShown~=nil')
            equal(lua('return vim.api.nvim_win_get_cursor(0)'),[1,len(keyword)+3],keyword+' declaration jumps past keyword')
        for client,identifier,operator in [('generic','héllo',False),('elixirls','left',True),('elixirls','unquote',False)]:
            setup(client=client,identifier=identifier,operator=operator)
            editor.raw(b'\x1b[98;9u');editor.wait('return ElixirNavShown~=nil')
            equal(lua('return ElixirNavShown.targetSelectionRange'),None,'generic, operator and dynamic-name locations remain unchanged')
            equal(lua('return vim.api.nvim_win_get_cursor(0)'),[1,2],'unrecognized declaration retains server-provided destination')
        equal(main.read_text(),'caller()\n','navigation never writes caller')
        equal(target.read_text(),'  def héllo(name) do\n    héllo(name)\n  end\n','navigation never writes target')
        equal(lua('return vim.v.errmsg'),'','Elixir normalization leaves no editor errors')
        print(f'PASS: {support["checks"]} Elixir navigation PTY checks (mocked clients)')
    finally:
        try:
            lua('vim.lsp.get_clients=ElixirNavClients;vim.lsp.util.show_document=ElixirNavShow;return true')
        except Exception:
            pass
        editor.close()
