#!/usr/bin/env python3
"""Usages select-all and multi-file opening through actual terminal input."""
import json
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parent.parent
support = {'__file__': str(ROOT / 'tests/autosave.py')}
exec((ROOT / 'tests/autosave.py').read_text().split('\nwith tempfile.TemporaryDirectory', 1)[0], support)
Editor, equal, STATE = support['Editor'], support['equal'], support['STATE']

with tempfile.TemporaryDirectory(prefix='usage-all-', dir=STATE) as directory:
    project = Path(directory)
    (project / 'home').mkdir()
    source = ['local target = function() end', 'target()']
    (project / 'main.lua').write_text('\n'.join(source) + '\n')
    (project / 'alpha.lua').write_text('-- alpha\n😀 target()\ntarget()\n')
    (project / 'beta.lua').write_text('target()\n')
    (project / 'keep.lua').write_text('-- already open\n')
    editor = Editor(project, project / 'home/settings.lua', disabled=True, disable_lsp=True)
    lua = editor.lua
    bindings = json.loads((ROOT / 'config/keymap.json').read_text())
    index = next(i for i, item in enumerate(bindings, 1) if item['id'] == 'select_all')
    relay = f'\x1b[{0xF0000 + index}u'.encode()
    native = b'\x1b[97;9u'
    def location(file, line, start=0, end=6):
        return {'uri': (project / file).as_uri(), 'range': {'start': {'line': line, 'character': start}, 'end': {'line': line, 'character': end}}}
    usages = [location('alpha.lua', 1, 3, 9), location('alpha.lua', 2), location('beta.lua', 0)]
    def listed():
        return lua('local out={};for _,b in ipairs(vim.api.nvim_list_bufs()) do if vim.bo[b].buflisted then '
                   'out[#out+1]=vim.fs.basename(vim.api.nvim_buf_get_name(b)) end end;table.sort(out);return out')
    def results():
        return lua('for _,w in ipairs(vim.api.nvim_list_wins()) do local c=vim.api.nvim_win_get_config(w);'
                   'local b=vim.api.nvim_win_get_buf(w);if c.relative~="" and vim.bo[b].buftype~="prompt" then '
                   'return {lines=vim.api.nvim_buf_get_lines(b,0,-1,false),footer=c.footer} end end;return nil')
    def reset():
        editor.raw(b'\x1b[27u')
        lua('vim.cmd.stopinsert();require("jetvim.tree").editor();'
            'local main=vim.fn.bufnr('+json.dumps(str(project/'main.lua'))+');if main>=0 then vim.bo[main].modified=false end;'
            'for _,b in ipairs(vim.api.nvim_list_bufs()) do local n=vim.fs.basename(vim.api.nvim_buf_get_name(b));'
            'if n=="alpha.lua" or n=="beta.lua" then vim.bo[b].buflisted=false end end;'
            'vim.cmd.edit(vim.fn.fnameescape('+json.dumps(str(project/'main.lua'))+'));'
            'vim.api.nvim_win_set_cursor(0,{1,8});_G.usage_opens={};'
            '_G.usage_client={id=999,offset_encoding="utf-16"};return true')
        # Lua JSON parsing keeps paths, Unicode and protocol field names literal.
        lua('_G.usage_refs=vim.json.decode('+json.dumps(json.dumps(usages))+');'
            '_G.usage_def=vim.json.decode('+json.dumps(json.dumps(location('main.lua',0,6,12)))+');'
            'function usage_client:request(method,params,callback,buf) '
            'local response=method=="textDocument/definition" and {usage_def} or usage_refs;'
            'vim.schedule(function() callback(nil,response) end);return true,1 end;'
            'function usage_client:cancel_request() end;'
            'vim.lsp.get_clients=function()return {usage_client} end;'
            'vim.lsp.util.show_document=function(location,encoding,options) '
            'usage_opens[#usage_opens+1]={uri=location.uri,encoding=encoding};'
            'return usage_original_show(location,encoding,options) end;return true')
        editor.raw(b'i')
    def open_usages():
        editor.raw(b'\x1b[98;9u')
        editor.wait('return vim.bo.buftype=="prompt"')
    try:
        lua('_G.usage_original_show=vim.lsp.util.show_document;'
            'vim.cmd.badd("keep.lua");return true')
        baseline_windows = lua('return #vim.api.nvim_list_wins()')
        for chord in (native, relay):
            reset(); open_usages()
            query = lua('return vim.api.nvim_get_current_line()')
            editor.raw(chord)
            equal(lua('return vim.api.nvim_get_current_line()'),query,'select-all leaves query unchanged')
            equal(lua('return vim.fn.mode()'),'i','select-all stays in query typing mode')
            display=results()
            equal(sum('✓' in line for line in display['lines']),3,'all usage rows visibly selected')
            equal('3 selected' in json.dumps(display['footer']),True,'footer reports selection count')
            editor.raw(b'\r')
            editor.wait('return #usage_opens==2')
            equal([Path(item['uri']).name for item in lua('return usage_opens')],['alpha.lua','beta.lua'],'bulk open deduplicates files in result order')
            equal(lua('return usage_opens[1].encoding'),'utf-16','usage keeps client encoding')
            alpha=lua('return vim.fn.bufnr('+json.dumps(str(project/'alpha.lua'))+')')
            equal(lua('local p=vim.fn.getbufinfo('+str(alpha)+')[1];return p.listed'),1,'first usage file is listed as editor tab')
            equal(listed(),['alpha.lua','beta.lua','keep.lua','main.lua'],'all selected files and existing tabs stay listed')
            equal(lua('return vim.api.nvim_get_current_buf()~=require("jetvim.tree").buf and vim.bo.buftype==""'),True,'bulk open returns editor focus')
            equal(lua('return #vim.api.nvim_list_wins()'),baseline_windows,'bulk opening adds no editor splits or leaked popups')
            equal(lua('local t=vim.api.nvim_eval_statusline(vim.o.tabline,{use_tabline=true,maxwidth=vim.o.columns});return t.str:find("alpha.lua",1,true)~=nil and t.str:find("beta.lua",1,true)~=nil'),True,'opened files appear in actual tab strip')
            equal(lua('return vim.api.nvim_buf_get_lines(vim.fn.bufnr('+json.dumps(str(project/'main.lua'))+'),0,-1,false)'),source,'bulk navigation does not edit source')
        reset();open_usages();editor.raw(native+b'\r')
        editor.wait('return #usage_opens==2')
        equal(len(lua('return usage_opens')),2,'CommandA and Enter in one packet opens every distinct file')
        # One packet must resolve typed filtering before Command-A and Enter.
        reset();open_usages();editor.raw(b'alpha.lua:2'+native+b'\r')
        editor.wait('return #usage_opens==1')
        equal(lua('return vim.fs.basename(vim.api.nvim_buf_get_name(0))'),'alpha.lua','filter plus select-all opens only matching file')
        equal(lua('return vim.api.nvim_win_get_cursor(0)'),[2,5],'first usage keeps UTF16-to-UTF8 cursor location')
        equal('beta.lua' in listed(),False,'filtered-out file remains unopened')
        # Editing the query clears the old selection, then Enter is single-open.
        reset();open_usages();editor.raw(native)
        editor.raw(b'beta')
        equal(any('✓' in line for line in results()['lines']),False,'query edits clear previous marks')
        editor.raw(b'\r');editor.wait('return #usage_opens==1')
        equal(lua('return vim.fs.basename(vim.api.nvim_buf_get_name(0))'),'beta.lua','edited query chooses its single result')
        reset();open_usages();editor.raw(native+b'\x1b[27u')
        editor.wait('return vim.bo.buftype~="prompt"')
        equal(lua('return #usage_opens'),0,'Escape cancels selected usages without opening')
        equal(lua('return #vim.api.nvim_list_wins()'),baseline_windows,'cancel closes both popup windows')
        reset();open_usages();editor.raw(b'\x1b[B\x1b[B\r')
        editor.wait('return #usage_opens==1')
        equal(lua('return vim.fs.basename(vim.api.nvim_buf_get_name(0))'),'beta.lua','ordinary arrow and Enter remains a single-open choice')
        # Empty filtering must not re-use a previous selection.
        reset();open_usages();editor.raw(b'no-match'+native+b'\r')
        editor.wait('return vim.bo.buftype~="prompt"')
        equal(lua('return #usage_opens'),0,'empty filter never opens stale selected usages')
        # A source edit while the picker is open invalidates its pending choice.
        reset();open_usages()
        lua('local b=vim.fn.bufnr('+json.dumps(str(project/'main.lua'))+');'
            'vim.api.nvim_buf_set_lines(b,1,2,false,{"changed source"});return true')
        editor.raw(native+b'\r')
        editor.wait('return vim.bo.buftype~="prompt"')
        equal(lua('return #usage_opens'),0,'stale source prevents all bulk jumps')
        equal(lua('return vim.api.nvim_get_current_line()'),source[0],'stale choice keeps original editor active')
        equal(lua('return vim.api.nvim_buf_get_lines(0,1,2,false)'),['changed source'],'stale bulk choice preserves new edits')
        # An unavailable result cannot prevent later valid selected files opening.
        reset();open_usages()
        lua('_G.usage_show=vim.lsp.util.show_document;_G.usage_notify=vim.notify;'
            '_G.usage_failures=0;_G.usage_notices={};'
            'vim.notify=function(text)table.insert(usage_notices,text)end;'
            'vim.lsp.util.show_document=function(location,encoding,options) '
            'if location.uri:find("alpha.lua",1,true) then usage_failures=usage_failures+1;error("fixture open failure") end;'
            'return usage_show(location,encoding,options) end;return true')
        editor.raw(native+b'\r')
        editor.wait('return vim.fs.basename(vim.api.nvim_buf_get_name(0))=="beta.lua"')
        equal(lua('return usage_failures'),1,'failed file is attempted once despite duplicate usages')
        equal(lua('return #usage_opens'),1,'valid later file still opens after one failure')
        equal(lua('return #usage_notices'),1,'failed opening is reported once')
        lua('vim.notify=usage_notify;vim.lsp.util.show_document=usage_show;return true')
        # Other pickers retain their single-item API and do not map CmdA to rows.
        reset()
        lua('require("jetvim.ui").pick("Single picker",{{label="alpha"},{label="beta"}},function(item)_G.single_choice=item.label end);return true')
        editor.wait('return vim.bo.buftype=="prompt"')
        equal(lua('return vim.fn.maparg("<D-a>","i",false,true).buffer==1'),False,'ordinary picker does not intercept CommandA as result selection')
        editor.raw(b'\r')
        editor.wait('return _G.single_choice~=nil')
        equal(lua('return single_choice'),'alpha','ordinary picker Enter still returns one item')
        # Select-all includes results below the visible first page.
        extra=[]
        for number in range(20):
            file='bulk-'+str(number).zfill(2)+'.lua'
            (project/file).write_text('target()\n')
            extra.append(location(file,0))
        reset()
        lua('_G.usage_refs=vim.json.decode('+json.dumps(json.dumps(extra))+');return true')
        open_usages()
        equal(len(results()['lines']),16,'long usages list displays only its first page')
        editor.raw(native+b'\r')
        editor.wait('return #usage_opens==20')
        equal(lua('return #usage_opens'),20,'select-all opens offscreen usages too')
        equal(lua('return #vim.api.nvim_list_wins()'),baseline_windows,'many opened usages still reuse editor panes')
        equal(lua('return vim.v.errmsg'),'','no picker or navigation errors')
        print(f'PASS: {support["checks"]} usages select-all/open-all terminal checks')
    finally:
        editor.close()
