#!/usr/bin/env python3
"""Native terminal range selection opens unique scoped search files safely."""
import json
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parent.parent
support = {'__file__': str(ROOT / 'tests/autosave.py')}
exec((ROOT / 'tests/autosave.py').read_text().split('\nwith tempfile.TemporaryDirectory', 1)[0], support)
Editor, equal, STATE = support['Editor'], support['equal'], support['STATE']

with tempfile.TemporaryDirectory(prefix='project-search-open-all-', dir=STATE) as directory:
    fixture = Path(directory); project = fixture / 'project'; project.mkdir()
    scope = project / 'scope'; scope.mkdir(); (project / 'home').mkdir()
    (project / 'main.lua').write_text('-- unchanged origin\n')
    (project / 'existing.lua').write_text('-- existing disk\n')
    sources = []
    for number in range(8):
        path = scope / f'file{number}.txt'
        path.write_text(f'header {number}\nneedle alpha {number}\nspacer\nneedle beta {number}\nneedle gamma {number}\n')
        sources.append(path)
    outside = fixture / 'outside.txt'; outside.write_text('private fixture outside project\n')
    sibling = project / 'sibling.txt'; sibling.write_text('fixture outside selected scope\n')
    editor = Editor(project, project / 'home/settings.lua', disabled=True, disable_lsp=True)
    lua = editor.lua
    bindings = json.loads((ROOT / 'config/keymap.json').read_text())
    relay = {item['id']: f'\x1b[{0xF0000 + index}u'.encode() for index, item in enumerate(bindings, 1)}
    def items():
        return lua('return require("jetvim.project_search").state.items')
    def selected_items():
        return lua('local s=require("jetvim.project_search").state;return vim.list_slice(s.items,math.min(s.anchor or s.selected,s.selected),math.max(s.anchor or s.selected,s.selected))')
    def unique(entries):
        result, seen = [], set()
        for item in entries:
            path = Path(item['path']).resolve()
            if path in seen: continue
            seen.add(path); result.append([str(path), item['line'], item['col']])
        return result
    def geometry():
        return lua('local out={};for _,w in ipairs(vim.api.nvim_list_wins())do if vim.api.nvim_win_get_config(w).relative=="" then '
                   'out[#out+1]={w,vim.api.nvim_win_get_width(w),vim.api.nvim_win_get_height(w)}end end;return out')
    def open_search(text='needle', chord=b'\x1b[102;10u'):
        editor.raw(b'\x1b[27u')
        lua('local p=require("jetvim.project");_G.OriginalSearchOpen("main.lua");_G.SearchOpenCalls={};return true')
        editor.raw(chord)
        editor.wait('return require("jetvim.project_search").state~=nil and vim.fn.mode()=="i"')
        editor.raw(text.encode())
        editor.wait('local s=require("jetvim.project_search").state;return s and #s.items>0 and not s.busy and not s.timer')
    def accept(expected, label):
        before = geometry()
        editor.raw(b'\r')
        editor.wait('return require("jetvim.project_search").state==nil')
        editor.wait('return vim.fn.mode()=="i"')
        equal(lua('return _G.SearchOpenCalls'), expected, label)
        if expected:
            equal(lua('return vim.api.nvim_buf_get_name(0)'), expected[-1][0], 'last unique selected file keeps editor focus')
            equal(lua('return vim.api.nvim_win_get_cursor(0)'), expected[-1][1:], 'final file opens at its first selected match')
        equal(geometry(), before, 'bulk opening preserves pane geometry without splits')
        equal(lua('return #vim.api.nvim_list_tabpages()'), 1, 'bulk opens editor buffers without Vim tab pages')
        equal(lua('return vim.bo.buftype'), '', 'bulk opening focuses a normal editor')
        equal(lua('return vim.api.nvim_buf_get_lines(vim.fn.bufnr("existing.lua"),0,-1,false)'), ['-- existing unsaved'], 'existing unsaved tab is preserved')
    try:
        lua('_G.OriginalSearchOpen=require("jetvim.project").open;_G.SearchOpenCalls={};'
            'require("jetvim.project").open=function(path,row,col) '
            'if path==_G.SearchFailPath then error("fixture open error")end;'
            'table.insert(_G.SearchOpenCalls,{path,row,col});return _G.OriginalSearchOpen(path,row,col)end;'
            '_G.OriginalSearchOpen("existing.lua");vim.api.nvim_buf_set_lines(0,0,-1,false,{"-- existing unsaved"});return true')
        lua('for _,path in ipairs(vim.json.decode('+json.dumps(json.dumps([str(path) for path in sources]))+'))do vim.fn.bufadd(path)end;return true')
        equal(lua('return vim.fn.buflisted('+json.dumps(str(sources[0]))+')'), 0, 'pre-existing search file buffer starts unlisted')
        open_search()
        editor.raw(b'\x1b[1;2B' * 5)
        expected = unique(selected_items())
        equal(len(expected) >= 2, True, 'native ShiftDown range spans multiple files')
        accept(expected, 'Enter opens each selected file only once at first match')
        for path, row, col in expected:
            equal(lua('return vim.fn.buflisted('+json.dumps(path)+')'), 1, 'each opened match remains in editor tabs')
        open_search(chord=relay['find_project'])
        editor.raw(b'\x1b[B' * 8 + b'\x1b[1;2A' * 5)
        equal(lua('local s=require("jetvim.project_search").state;return {s.anchor,s.selected}'), [9,4], 'reverse selection retains fixed anchor')
        accept(unique(selected_items()), 'reverse range opens in visible result order')
        open_search(); editor.raw(b'\x1b[6;2~')
        equal(len(unique(selected_items())) >= 4, True, 'ShiftFnDown selects files across a visible page')
        accept(unique(selected_items()), 'page range opens all unique selected files')
        open_search(); accept(unique(selected_items()), 'default selection still opens one match')
        open_search(); editor.raw(b'\x1b[1;2B' * 5 + b'\x1b[B')
        equal(lua('return require("jetvim.project_search").state.anchor==nil'), True, 'plain arrow collapses bulk range')
        accept(unique(selected_items()), 'collapsed selection opens only active match')
        open_search(); editor.raw(b'\x1b[6;2~ alpha')
        editor.wait('local s=require("jetvim.project_search").state;return s.query=="needle alpha" and #s.items==8 and not s.busy and not s.timer')
        equal(lua('return require("jetvim.project_search").state.anchor==nil'), True, 'new query clears prior bulk range')
        editor.raw(b'\x1b[1;2B')
        accept(unique(selected_items()), 'filtered results open only the newly selected files')
        open_search()
        missing = Path(selected_items()[0]['path']); saved = missing.read_text(); missing.unlink()
        accept([], 'all vanished results leave source focused and typing')
        equal(lua('return vim.fs.basename(vim.api.nvim_buf_get_name(0))'), 'main.lua', 'invalid selection returns to original editor')
        missing.write_text(saved)
        # A busy query cannot accept a partial range, and a stale generation
        # cannot revive it after typing a different query.
        open_search(); editor.raw(b'\x1b[6;2~')
        lua('_G.SearchJobs={};_G.SearchOriginalSystem=vim.system;vim.system=function(argv,opts,done) '
            'if argv[1]~="rg" then return _G.SearchOriginalSystem(argv,opts,done)end;'
            'local job={opts=opts,done=done,killed=false};job.kill=function(self)self.killed=true end;'
            'table.insert(_G.SearchJobs,job);return job end;return true')
        editor.raw(b' stale'); editor.wait('return #_G.SearchJobs==1')
        def stream(job, row):
            entries = ''.join(json.dumps({'type': 'match', 'data': {
                'path': {'text': f'scope/file{number}.txt'}, 'lines': {'text': 'needle alpha\n'},
                'line_number': row, 'submatches': [{'start': 0}]}})+'\n' for number in (0,1))
            lua(f'_G.SearchJobs[{job}].opts.stdout(nil,'+json.dumps(entries)+');return true')
        stream(1, 2); editor.wait('return #require("jetvim.project_search").state.items==2')
        editor.raw(b'\x1b[1;2B\r')
        equal(lua('local s=require("jetvim.project_search").state;return s~=nil and s.busy'), True, 'Enter does not accept a partial busy result range')
        equal(lua('return _G.SearchOpenCalls'), [], 'busy selection opens no files')
        editor.raw(b' new'); editor.wait('return #_G.SearchJobs==2')
        equal(lua('return _G.SearchJobs[1].killed'), True, 'new query cancels old selected search')
        stream(1, 2); lua('_G.SearchJobs[1].done({code=0});return true')
        equal(lua('local s=require("jetvim.project_search").state;return {#s.items,s.anchor or 0,s.selected}'), [0,0,1], 'stale completion cannot revive prior bulk range')
        editor.raw(b'\r')
        equal(lua('return _G.SearchOpenCalls'), [], 'new busy query cannot accept stale results')
        stream(2, 4); lua('_G.SearchJobs[2].done({code=0});vim.system=_G.SearchOriginalSystem;return true')
        editor.wait('local s=require("jetvim.project_search").state;return #s.items==2 and not s.busy')
        editor.raw(b'\x1b[1;2B'); accept(unique(selected_items()), 'only current query range opens after async completion')
        open_search(); editor.raw(b'\x1b[1;2B')
        lua('require("jetvim.project_search").choose();vim.cmd.enew();return true')
        editor.wait('return require("jetvim.project_search").state==nil and vim.fn.mode()=="n"')
        equal(lua('return _G.SearchOpenCalls'), [], 'changed origin prevents queued bulk opening')
        open_search(); editor.raw(b'\x1b[1;2B')
        lua('require("jetvim.project_search").choose();require("jetvim.project").root='+json.dumps(str(fixture))+';return true')
        editor.wait('return require("jetvim.project_search").state==nil')
        equal(lua('return _G.SearchOpenCalls'), [], 'changed project root prevents queued bulk opening')
        lua('require("jetvim.project").root='+json.dumps(str(project))+';return true')
        # Revalidate scope and paths after results have already arrived.
        editor.raw(b'\x1b[27u')
        equal(lua('_G.OriginalSearchOpen("main.lua");require("jetvim.tree").focus();local t=require("jetvim.tree");'
            'for row,e in pairs(t.rows)do if e.path=='+json.dumps(str(scope))+' then vim.api.nvim_win_set_cursor(t.win,{row,0});return true end end;return false'), True, 'scope directory selected in file tree')
        editor.raw(b'\x1b[102;10u'); editor.wait('return require("jetvim.project_search").state~=nil and vim.fn.mode()=="i"')
        editor.raw(b'needle'); editor.wait('local s=require("jetvim.project_search").state;return #s.items==24 and not s.busy and not s.timer')
        equal(lua('return require("jetvim.project_search").state.scope'), str(scope), 'file validation uses selected folder scope')
        originals = unique(items())
        Path(originals[0][0]).unlink()
        Path(originals[1][0]).unlink(); Path(originals[1][0]).symlink_to(outside)
        Path(originals[2][0]).unlink(); Path(originals[2][0]).symlink_to(sibling)
        Path(originals[3][0]).unlink(); Path(originals[3][0]).symlink_to(originals[4][0])
        lua('_G.SearchOpenCalls={};_G.SearchFailPath='+json.dumps(originals[5][0])+';return true')
        editor.raw(b'\x1b[1;2F')
        expected = []
        seen = set()
        for item in selected_items():
            path = Path(item['path']).resolve()
            if not path.is_file() or scope not in path.parents or str(path) == originals[5][0] or path in seen: continue
            seen.add(path); expected.append([str(path),item['line'],item['col']])
        accept(expected, 'deleted/outside/scope-escaping paths skip; aliases deduplicate and open errors do not stop later files')
        equal(lua('return vim.fn.bufnr('+json.dumps(str(outside))+')'), -1, 'outside fixture is never loaded')
        equal(lua('return vim.fn.bufnr('+json.dumps(str(sibling))+')'), -1, 'outside-scope file is never loaded')
        equal(Path(originals[0][0]).exists(), False, 'bulk open never recreates deleted result')
        lua('_G.SearchFailPath=nil;return true')
        equal((project / 'existing.lua').read_text(), '-- existing disk\n', 'unsaved tab stays unsaved on disk')
        equal((project / 'main.lua').read_text(), '-- unchanged origin\n', 'origin remains unchanged')
        equal(lua('return vim.v.errmsg'), '', 'bulk opening leaves no Neovim errors')
        print(f'PASS: {support["checks"]} project search open-all terminal checks')
    finally:
        editor.close()
