#!/usr/bin/env python3
"""Selected editor text seeds literal inline Find via real terminal shortcuts."""
import json
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parent.parent
support = {'__file__': str(ROOT / 'tests/autosave.py')}
exec((ROOT / 'tests/autosave.py').read_text().split('\nwith tempfile.TemporaryDirectory', 1)[0], support)
Editor, equal, STATE = support['Editor'], support['equal'], support['STATE']

with tempfile.TemporaryDirectory(prefix='search-selection-', dir=STATE) as directory:
    project = Path(directory); (project/'home').mkdir()
    original = ['prefix hello world suffix', 'HELLO WORLD', '/hello/i', '/HELLO/I', 'héllo héllo',
                'start alpha', 'beta end', 'START ALPHA', 'BETA END']
    (project/'main.lua').write_text('\n'.join(original)+'\n')
    editor = Editor(project,project/'home/settings.lua',disabled=True,disable_lsp=True)
    lua = editor.lua
    bindings = json.loads((ROOT/'config/keymap.json').read_text())
    find_index = next(i for i,item in enumerate(bindings,1) if item['id']=='find')
    native, relay = b'\x1b[102;9u', f'\x1b[{0xF0000+find_index}u'.encode()
    owner = lua('return vim.api.nvim_get_current_win()')
    source = lua('return vim.api.nvim_get_current_buf()')
    windows = lua('return #vim.api.nvim_list_wins()')
    def position(row,col,typing=False,selection='exclusive'):
        editor.raw(b'\x1b[27u')
        lua('vim.api.nvim_set_current_win('+str(owner)+');vim.o.selection='+json.dumps(selection)+';'
            'vim.api.nvim_win_set_cursor(0,{'+str(row)+','+str(col)+'});return true')
        if typing: editor.raw(b'i')
    def opened(text,count,label):
        editor.wait('return vim.bo.filetype=="jetvim-search" and vim.fn.mode()=="i"')
        equal(lua('return require("jetvim.search").query'),text,label+' prefills exact visible query')
        equal(lua('return vim.api.nvim_get_current_line()'),text,label+' displays query in input')
        equal(lua('return #require("jetvim.search").matches'),count,label+' matches selection literally')
        equal(lua('return require("jetvim.search").error'),None,label+' has no pattern error')
        equal(lua('return require("jetvim.search").owner'),owner,label+' preserves source editor')
        equal(lua('return vim.api.nvim_buf_get_lines('+str(source)+',0,-1,false)'),original,label+' never edits selected source')
    def close(label):
        editor.raw(b'\x1b[27u')
        editor.wait('return require("jetvim.search").input==nil and vim.fn.mode()=="i"')
        equal(lua('return vim.api.nvim_get_current_win()'),owner,label+' restores editor focus')
        equal(lua('return #vim.api.nvim_list_wins()'),windows,label+' removes both search windows')
        equal(lua('return #vim.api.nvim_buf_get_extmarks('+str(source)+',vim.api.nvim_get_namespaces().JetvimSearch,0,-1,{})'),0,label+' clears all match highlights')
        equal(lua('return vim.v.hlsearch'),0,label+' clears native highlights')
    try:
        lua('vim.fn.setreg("a","register stays");vim.fn.setreg(string.char(34),"unnamed stays");return true')
        position(1,7,typing=True)
        editor.raw(b'\x1b[1;2C'*11+native)
        opened('hello world',2,'same-packet ShiftRight and native Find')
        equal(lua('return vim.api.nvim_win_get_cursor('+str(owner)+')'),[1,7],'initial match starts at selected range')
        editor.raw(b'\r');equal(lua('return vim.api.nvim_win_get_cursor('+str(owner)+')'),[2,0],'Enter advances selected-text matches')
        close('forward Select')
        position(1,18,typing=True);editor.raw(b'\x1b[1;2D'*11+relay)
        opened('hello world',2,'reverse Select relay');close('reverse Select')
        position(1,7);editor.raw(b'v'+b'\x1b[C'*11+native)
        opened('hello world',2,'forward Visual');close('forward Visual')
        position(1,18);editor.raw(b'v'+b'\x1b[D'*11+relay)
        opened('hello world',2,'reverse Visual relay');close('reverse Visual')
        position(5,0,selection='inclusive');editor.raw(b'v'+b'\x1b[C'*4+native)
        opened('héllo',2,'inclusive UTF8 Visual');close('inclusive UTF8 Visual')
        position(3,0,typing=True);editor.raw(b'\x1b[1;2F'+native)
        opened('/hello/i',2,'slash-wrapped selection')
        equal(lua('return vim.fn.getreg("/")'),r'\c\V/hello/i','selection cannot accidentally activate regex')
        # Even replacing the seed with identical slash text in one packet is a
        # deliberate edit: its changedtick clears the initial literal override.
        editor.raw(b'\x15/hello/i')
        equal(lua('return require("jetvim.search").literal_seed==nil'),True,'query edit clears literal seed metadata')
        equal(lua('return #require("jetvim.search").matches'),4,'edited slash query follows ordinary regex grammar')
        close('edited slash seed')
        # A new editor selection replaces an existing search without leaking it.
        editor.raw(native);editor.wait('return vim.bo.filetype=="jetvim-search"')
        lua('vim.api.nvim_set_current_win('+str(owner)+');vim.cmd.stopinsert();return true')
        editor.raw(b'\x1b[27u')
        lua('vim.api.nvim_win_set_cursor(0,{5,0});return true')
        editor.raw(b'v'+b'\x1b[C'*5+relay)
        opened('héllo',2,'new selection replaces existing modal')
        equal(lua('return #vim.api.nvim_list_wins()'),windows+2,'reseed reuses one search field pair');close('reseed existing modal')
        # Multiline selection retains the whole literal behind an escaped input.
        position(6,6,typing=True);editor.raw(b'\x1b[1;2B'+b'\x1b[1;2D'*2+native)
        opened('alpha\\nbeta',2,'multiline Select')
        equal(lua('local m=require("jetvim.search").matches[1];return {m.row,m.col,m.end_row,m.finish}'),[6,6,7,4],'multiline match tracks both byte endpoints')
        equal(lua('local s=require("jetvim.search");local ms=vim.api.nvim_buf_get_extmarks(s.source,vim.api.nvim_get_namespaces().JetvimSearch,0,-1,{details=true});return {ms[1][2],ms[1][3],ms[1][4].end_row,ms[1][4].end_col}'),[5,6,6,4],'multiline highlight spans rows')
        editor.raw(b'\r');equal(lua('return vim.api.nvim_win_get_cursor('+str(owner)+')'),[8,6],'Enter navigates multiline literal matches')
        close('multiline Select')
        position(7,4);editor.raw(b'v'+b'\x1b[A'+b'\x1b[C'*2+relay)
        opened('alpha\\nbeta',2,'reverse multiline Visual');close('reverse multiline Visual')
        position(2,0);editor.raw(b'V'+native)
        opened('HELLO WORLD',2,'linewise Visual');close('linewise Visual')
        # No active selection keeps the previous query, including its mode.
        position(1,0,typing=True);editor.raw(relay)
        opened('HELLO WORLD',2,'no-selection reopen');close('no-selection reopen')
        other = lua('vim.cmd("rightbelow vnew");vim.api.nvim_buf_set_name(0,'+json.dumps(str(project/'other.txt'))+');'
                    'vim.api.nvim_buf_set_lines(0,0,-1,false,{"other hello token"});'
                    'require("jetvim.tree").editor_win='+str(owner)+';return vim.api.nvim_get_current_win()')
        editor.raw(b'\x1b[27u');lua('vim.api.nvim_win_set_cursor(0,{1,6});return true')
        editor.raw(b'v'+b'\x1b[C'*5+native)
        editor.wait('return vim.bo.filetype=="jetvim-search" and vim.fn.mode()=="i"')
        equal(lua('local s=require("jetvim.search");return {s.owner,s.query,#s.matches}'),[other,'hello',1],'selection belongs to actual editor split rather than remembered split')
        editor.raw(b'\x1b[27u');editor.wait('return require("jetvim.search").input==nil and vim.fn.mode()=="i"')
        equal(lua('return vim.api.nvim_get_current_win()'),other,'selection Find returns to actual source split')
        lua('vim.cmd("close!");return true')
        position(1,0,typing=True);editor.raw(native);editor.wait('return vim.bo.filetype=="jetvim-search"')
        editor.raw(b'\x1b[1;2H'+relay)
        equal(lua('return require("jetvim.search").query'),'hello','Find-input selection does not reseed editor search')
        equal(lua('return require("jetvim.search").source'),source,'Find-input selection never becomes source')
        close('query selection')
        lua('require("jetvim.tree").focus();return true');editor.raw(b'v'+relay)
        editor.wait('return vim.bo.filetype=="jetvim-search" and vim.fn.mode()=="i"')
        equal(lua('local s=require("jetvim.search");return {s.query,s.source}'),['hello',source],'tool-window selection never seeds or becomes editor source')
        close('tool selection')
        lua('vim.api.nvim_buf_set_lines('+str(source)+',0,-1,false,vim.split(string.rep("a\\nb\\n",6001),"\\n",{trimempty=true}));return true')
        position(1,0,typing=True);editor.raw(b'\x1b[1;2B\x1b[1;2C'+native)
        editor.wait('return vim.bo.filetype=="jetvim-search" and vim.fn.mode()=="i"')
        equal(lua('local s=require("jetvim.search");return {s.query,#s.matches,s.limited}'),['a\\nb',5000,True],'multiline literal honors 5000-match cap')
        close('multiline match cap')
        lua('vim.api.nvim_buf_set_lines('+str(source)+',0,-1,false,{"a","b",string.rep("x",2*1024*1024),"a","b"});return true')
        position(1,0,typing=True);editor.raw(b'\x1b[1;2B\x1b[1;2C'+relay)
        editor.wait('return vim.bo.filetype=="jetvim-search" and vim.fn.mode()=="i"')
        equal(lua('local s=require("jetvim.search");return {#s.matches,s.limited}'),[1,True],'multiline literal never scans beyond 2MiB source cap')
        close('multiline source cap')
        equal(lua('return {vim.fn.getreg("a"),vim.fn.getreg(string.char(34))}'),['register stays','unnamed stays'],'selection extraction never yanks or changes registers')
        equal((project/'main.lua').read_text(),'\n'.join(original)+'\n','search never writes selected source')
        equal(lua('return vim.v.errmsg'),'','selection-prefilled search leaves no errors')
        print(f'PASS: {support["checks"]} selection-prefilled search terminal checks')
    finally:
        editor.close()
