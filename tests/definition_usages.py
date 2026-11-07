#!/usr/bin/env python3
"""Command-B definition/usages routing through real terminal input and mocked LSP."""
import json
from pathlib import Path
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
support = {'__file__': str(ROOT / 'tests/autosave.py')}
exec((ROOT / 'tests/autosave.py').read_text().split('\nwith tempfile.TemporaryDirectory', 1)[0], support)
Editor, equal, STATE = support['Editor'], support['equal'], support['STATE']

with tempfile.TemporaryDirectory(prefix='nav-', dir=STATE) as directory:
    project = Path(directory)
    (project / 'home').mkdir()
    (project / 'main.lua').write_text('😀 target()\nlocal target = 1\n')
    (project / 'other.lua').write_text('target()\n')
    editor = Editor(project, project / 'home/settings.lua', disabled=True, disable_lsp=True)
    def lua(code): return editor.lua(code)
    def reset(encoding='utf-16', col=7, typing=True):
        editor.raw(b'\x1b[27u')
        lua('vim.bo.modified=false;vim.cmd.edit(vim.fn.fnameescape(' + json.dumps(str(project / 'main.lua')) + ')); '
            'vim.api.nvim_win_set_cursor(0,{1,' + str(col) + '}); '
            '_G.nav_requests={};_G.nav_messages={};_G.nav_jumps={};_G.nav_picks={}; '
            '_G.nav_client={id=999,offset_encoding=' + json.dumps(encoding) + '}; '
            'function nav_client:request(method,params,callback,buf) '
            'nav_requests[#nav_requests+1]={method=method,params=params,callback=callback,buf=buf};return true,#nav_requests end; '
            'function nav_client:cancel_request() end; '
            'vim.lsp.get_clients=function() return {nav_client} end; '
            'vim.notify=function(message) nav_messages[#nav_messages+1]=message end; '
            'vim.lsp.util.show_document=function(location,encoding) nav_jumps[#nav_jumps+1]={location=location,encoding=encoding};return true end; '
            'require("jetvim.ui").pick=function(title,items,accept) nav_picks[#nav_picks+1]={title=title,items=items,accept=accept} end; return true')
        if typing: editor.raw(b'i')
    def press():
        editor.raw(b'\x1b[98;9u')
    def reply(index, locations=None, error=None):
        lua('nav_requests[' + str(index) + '].callback(' + ('{message=' + json.dumps(error) + '}' if error else 'nil')
            + ',' + ('nil' if locations is None else 'vim.json.decode(' + json.dumps(json.dumps(locations)) + ')') + ');return true')
        time.sleep(.06)
    def location(file='main.lua', start=3, end=9, line=0):
        return {'uri': (project / file).as_uri(), 'range': {'start': {'line':line,'character':start}, 'end': {'line':line,'character':end}}}
    def pick_count(): return lua('return #nav_picks')
    try:
        reset()
        press()
        equal(lua('return nav_requests[1].method'), 'textDocument/definition', 'native CmdB requests definition first')
        equal(lua('return nav_requests[1].params.position'), {'line':0,'character':5}, 'UTF16 origin uses client units after emoji')
        reply(1, [location()])
        equal(lua('return nav_requests[2].method'), 'textDocument/references', 'definition under caret requests usages')
        equal(lua('return nav_requests[2].params.context.includeDeclaration'), False, 'usage query excludes declaration')
        reply(2, [location('other.lua',0,6), location('other.lua',0,6)])
        equal(lua('return nav_picks[1].title'), 'Usages', 'usages open list even with one unique usage')
        equal(lua('return #nav_picks[1].items'),1,'duplicate usages are collapsed')
        equal(lua('return nav_picks[1].items[1].label:match("other.lua:1:1")~=nil'),True,'usage displays file and position')
        lua('nav_picks[1].accept(nav_picks[1].items[1]);return true')
        equal(lua('return nav_jumps[1].location.uri'),(project/'other.lua').as_uri(),'usage selection navigates to chosen file')
        for typing in (False, True):
            reset(typing=typing)
            before = lua('return vim.api.nvim_buf_get_lines(0,0,-1,false)')
            press()
            equal(lua('return nav_requests[1].params.position'), {'line':0,'character':5},
                  'native CmdB uses the caret in ' + ('Insert' if typing else 'Normal') + ' mode')
            reply(1, location('other.lua',0,6))
            equal(lua('return #nav_jumps'),1,'native CmdB navigates from either starting mode')
            equal(lua('return vim.api.nvim_buf_get_lines(0,0,-1,false)'),before,'CmdB never types a mode-switch character')
        for encoding, start, end, expected in [('utf-8',5,11,7),('utf-16',3,9,5),('utf-32',2,8,4)]:
            reset(encoding)
            press()
            equal(lua('return nav_requests[1].params.position.character'),expected,encoding+' origin position')
            reply(1, [location(start=start,end=end)])
            equal(lua('return #nav_requests'),2,encoding+' self definition detects exact range')
            reply(2, [])
            equal(lua('return nav_messages[#nav_messages]'),'No usages found','empty usages reported without blank popup')
        reset()
        press(); reply(1, location('other.lua',0,6))
        equal(lua('return #nav_requests'),1,'ordinary definition navigation does not request references')
        equal(lua('return #nav_jumps'),1,'single ordinary definition jumps immediately')
        equal(pick_count(),0,'single definition needs no chooser')
        reset()
        press(); reply(1,[location('other.lua',0,6),location(line=1,start=6,end=12)])
        equal(lua('return nav_picks[1].title'),'Definitions','multiple definitions remain selectable')
        reset()
        press()
        reply(1,[{'targetUri':(project/'main.lua').as_uri(),
                  'targetRange':{'start':{'line':0,'character':0},'end':{'line':1,'character':16}},
                  'targetSelectionRange':{'start':{'line':1,'character':6},'end':{'line':1,'character':12}}}])
        equal(lua('return #nav_requests'),1,'LocationLink uses symbol range instead of broad body range')
        equal(lua('return #nav_jumps'),1,'reference inside a definition body still jumps to actual symbol')
        reset()
        press()
        reply(1,[{'targetUri':(project/'main.lua').as_uri(),
                  'targetRange':{'start':{'line':0,'character':0},'end':{'line':1,'character':16}},
                  'targetSelectionRange':location()['range']}])
        equal(lua('return #nav_requests'),2,'LocationLink symbol self requests references')
        reply(2,None,'References failed')
        equal(lua('return nav_messages[#nav_messages]'),'References failed','reference server failure is visible')
        for change in ['vim.api.nvim_win_set_cursor(0,{2,0})',
                       'vim.api.nvim_buf_set_lines(0,0,1,false,{"changed"})',
                       'vim.cmd.enew()']:
            reset(); press(); lua(change+';return true'); reply(1,[location()])
            equal(lua('return #nav_requests'),1,'stale response after origin changed does not request references')
            equal(lua('return #nav_jumps+#nav_picks'),0,'stale response does not move editor or show popup')
        reset()
        lua('vim.api.nvim_buf_set_lines(0,0,1,false,{"😀 target()"});return true')
        press()
        before_tick = lua('return vim.api.nvim_buf_get_changedtick(0)')
        lua('vim.cmd.write();return true')
        equal(lua('return vim.api.nvim_buf_get_changedtick(0)') > before_tick,True,'native save changes tick without changing source text')
        reply(1,[location()])
        equal(lua('return #nav_requests'),2,'save-only tick change keeps pending definition request valid')
        reply(2,[location('other.lua',0,6)])
        equal(pick_count(),1,'save-only tick change preserves usages popup')
        reset(); press(); reply(1,[location(),location('other.lua',0,6)])
        equal(lua('return #nav_requests'),2,'definition with alternate overload targets still shows usages')
        reset(); press(); press(); reply(1,[location('other.lua',0,6)])
        equal(lua('return #nav_jumps'),0,'superseded invocation cannot navigate')
        reply(2,[location('other.lua',0,6)])
        equal(lua('return #nav_jumps'),1,'latest invocation still navigates')
        reset(); press(); reply(1,None,'Definition failed')
        equal(lua('return nav_messages[#nav_messages]'),'Definition failed','definition server failure reported')
        reset(); press(); reply(1,[])
        equal(lua('return nav_messages[#nav_messages]'),'No definition found','empty definitions are reported')
        reset(); lua('vim.lsp.get_clients=function() return {} end;return true'); press()
        equal(lua('return nav_messages[1]:match("needs a language server")~=nil'),True,'missing server keeps existing useful warning')
        equal(lua('return #nav_requests'),0,'missing server makes no request')
        reset(); lua('nav_client.request=function() return false end;return true'); press()
        equal(lua('return nav_messages[1]'),'Language server request failed','request refusal does not hang')
        equal(lua('return vim.v.errmsg'),'','no editor error')
        print(f'PASS: {support["checks"]} definition/usages terminal-input checks')
    finally:
        editor.close()
