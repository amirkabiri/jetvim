#!/usr/bin/env python3
"""Native tree Select ranges open unique safe files without changing user buffers."""
import json
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parent.parent
support = {'__file__': str(ROOT / 'tests/autosave.py')}
exec((ROOT / 'tests/autosave.py').read_text().split('\nwith tempfile.TemporaryDirectory', 1)[0], support)
Editor, equal, STATE = support['Editor'], support['equal'], support['STATE']

def literal(value):
    return json.dumps(str(value), ensure_ascii=False)

with tempfile.TemporaryDirectory(prefix='tree-open-all-', dir=STATE) as directory:
    fixture = Path(directory); project = fixture / 'project'; project.mkdir()
    (project / 'home').mkdir()
    main = project / 'main.lua'; main.write_text('-- unchanged\n')
    scope = project / 'scope'; scope.mkdir()
    folder = scope / 'folder'; folder.mkdir(); (folder / 'child.txt').write_text('do not open recursively\n')
    files = []
    for name in ('a.txt', 'b.txt', 'c.txt', 'd fail.txt', 'e δ.txt', 'f.txt'):
        path = scope / name; path.write_text(name+' disk\n'); files.append(path)
    alias = scope / 'z alias.txt'; alias.symlink_to(files[-1])
    outside = fixture / 'outside.txt'; outside.write_text('private outside\n')
    escape = scope / 'y outside.txt'; escape.symlink_to(outside)
    fifo = scope / 'x pipe'; os.mkfifo(fifo)
    editor = Editor(project, project / 'home/settings.lua', disabled=True, disable_lsp=True)
    lua = editor.lua
    bindings = json.loads((ROOT / 'config/keymap.json').read_text())
    relays = {item['id']: f'\x1b[{0xF0000+i}u'.encode() for i,item in enumerate(bindings,1)}

    def geometry():
        return lua('local out={};for _,w in ipairs(vim.api.nvim_list_wins())do if vim.api.nvim_win_get_config(w).relative=="" then '
                   'out[#out+1]={w,vim.api.nvim_win_get_width(w),vim.api.nvim_win_get_height(w)}end end;return out')
    def select(path, chord=b'\x1b[49;9u'):
        editor.raw(b'\x1b[27u')
        lua('_G.TreeOriginalOpen("main.lua");return true')
        editor.raw(chord)
        editor.wait('return vim.bo.filetype=="jetvim-tree" and vim.fn.mode()=="n"')
        equal(lua('local t=require("jetvim.tree");t.expanded['+literal(scope)+']=true;t.render();'
                  'for row,e in pairs(t.rows)do if e.path=='+literal(path)+' then vim.api.nvim_win_set_cursor(t.win,{row,0});return true end end;return false'),
              True, 'fixture file or folder selected')
        lua('_G.TreeLoads={};_G.TreeAdds={};_G.TreeSwitches={};_G.TreeOpenCalls={};return true')
    def row(path):
        return lua('for r,e in pairs(require("jetvim.tree").rows)do if e.path=='+literal(path)+'then return r end end')
    def accept(expected, packet=b'\r'):
        before = geometry()
        editor.raw(packet)
        editor.wait('return vim.bo.filetype~="jetvim-tree" and vim.fn.mode()=="i"')
        equal(lua('return vim.api.nvim_buf_get_name(0)'), str(expected[-1]), 'last selected file receives editor focus')
        for path in expected:
            equal(lua('return vim.fn.buflisted('+literal(path)+')'), 1, 'selected file appears in editor tabs')
        equal(geometry(), before, 'bulk open preserves pane geometry')
        equal(lua('return #TreeSwitches'), 1, 'bulk open switches visible editor buffer once')
        equal(lua('return vim.env.JETVIM_DISABLE_AUTOSAVE'), '1', 'bulk opening leaves fixture autosave configuration unchanged')
    try:
        lua('''
          _G.TreeOriginalOpen=require('jetvim.project').open
          _G.TreeOriginalLoad=vim.fn.bufload;_G.TreeOriginalAdd=vim.fn.bufadd
          _G.TreeOriginalSwitch=vim.api.nvim_set_current_buf
          _G.TreeLoads={};_G.TreeAdds={};_G.TreeSwitches={};_G.TreeOpenCalls={};_G.TreeMessages={}
          vim.notify=function(text)TreeMessages[#TreeMessages+1]=text end
          vim.fn.bufload=function(buf)
            local path=vim.api.nvim_buf_get_name(buf);TreeLoads[#TreeLoads+1]=path
            if path==TreeFailPath then error('fixture read error')end
            return TreeOriginalLoad(buf)
          end
          vim.fn.bufadd=function(path)TreeAdds[#TreeAdds+1]=path;return TreeOriginalAdd(path)end
          vim.api.nvim_set_current_buf=function(buf)TreeSwitches[#TreeSwitches+1]=buf;return TreeOriginalSwitch(buf)end
          require('jetvim.project').open=function(path,...)TreeOpenCalls[#TreeOpenCalls+1]=path;return TreeOriginalOpen(path,...)end
          return true
        ''')
        # Preserve already-loaded dirty buffers, including one initially unlisted.
        lua('TreeOriginalOpen('+literal(files[0])+');vim.api.nvim_buf_set_lines(0,0,-1,false,{"dirty listed"});'
            'TreeOriginalOpen('+literal(files[1])+');vim.api.nvim_buf_set_lines(0,0,-1,false,{"dirty unlisted"});vim.bo.buflisted=false;return true')
        dirty = lua('return {vim.fn.bufnr('+literal(files[0])+'),vim.fn.bufnr('+literal(files[1])+')}')
        select(files[0])
        editor.raw(b'\x1b[1;2B'*2)
        equal(lua('return {vim.fn.mode(),vim.fn.getpos("v")[2],vim.api.nvim_win_get_cursor(0)[1]}'), ['s',row(files[0]),row(files[2])], 'native ShiftDown keeps inclusive anchor and endpoint rows')
        accept(files[:3])
        equal(lua('return TreeLoads'), [str(files[2])], 'dirty listed and unlisted buffers are reused without reload')
        equal(lua('return {vim.api.nvim_buf_get_lines('+str(dirty[0])+',0,-1,false),vim.api.nvim_buf_get_lines('+str(dirty[1])+',0,-1,false)}'), [['dirty listed'],['dirty unlisted']], 'dirty text survives opening every selected file')
        equal(lua('return {vim.bo['+str(dirty[0])+'].modified,vim.bo['+str(dirty[1])+'].modified}'), [True,True], 'dirty buffers remain modified')
        select(files[2],relays['tree'])
        accept(files[:3], b'\x1b[1;2A'*2+b'\r')
        equal(lua('return TreeLoads'), [], 'reverse selected loaded buffers are not read again')
        # Canonical aliases deduplicate, directories do not recursively open,
        # vanished and nonregular paths skip, and a read error does not stop later files.
        select(folder)
        files[2].unlink()
        lua('_G.TreeFailPath='+literal(files[3])+';return true')
        steps = row(alias)-row(folder)
        accept([files[0],files[1],files[4],files[5]], b'\x1b[1;2B'*steps+b'\r')
        equal(lua('return TreeLoads'), [str(files[3]),str(files[4]),str(files[5])], 'read errors continue and canonical aliases load only once')
        equal(lua('return vim.fn.bufnr('+literal(outside)+')'), -1, 'outside symlink target is never loaded')
        equal(lua('return vim.fn.bufnr('+literal(folder/'child.txt')+')'), -1, 'selected folder children are not opened recursively')
        equal(lua('return vim.fn.bufnr('+literal(fifo)+')'), -1, 'nonregular selected entry is not loaded')
        equal(files[2].exists(), False, 'deleted selection is not recreated')
        lua('_G.TreeFailPath=nil;return true')
        # A query restricts range acceptance even across visible nonmatching rows.
        files[2].write_text('c restored\n')
        gap=scope/'bb gap.lua';gap.write_text('valid but not matching query\n')
        select(files[0]);editor.raw('.txt')
        editor.wait('return require("jetvim.tree").query==".txt"')
        steps=row(alias)-row(files[0])
        accept([files[0],files[1],files[2],files[3],files[4],files[5]], b'\x1b[1;2B'*steps+b'\r')
        equal(lua('return require("jetvim.tree").query'), '', 'acceptance clears the old query')
        equal(lua('return vim.fn.bufnr('+literal(gap)+')'), -1, 'valid nonmatching row inside selected range is not opened')
        # Esc cancels a native selection; singleton Enter retains folder semantics.
        select(folder);editor.raw(b'\x1b[1;2B\x1b[27u')
        editor.wait('return vim.fn.mode()=="n"')
        equal(lua('return TreeLoads'), [], 'cancelled native selection loads no files')
        select(folder);editor.raw(b'\r')
        equal(lua('return require("jetvim.tree").expanded['+literal(folder)+']'), True, 'singleton folder Enter expands it')
        editor.raw(b'\r')
        equal(lua('return require("jetvim.tree").expanded['+literal(folder)+']'), False, 'singleton folder Enter collapses it')
        equal(lua('return vim.bo.filetype'), 'jetvim-tree', 'folder Enter keeps sidebar focus')
        # The relay selection action already used by the bridge has identical acceptance.
        select(files[0],relays['tree'])
        accept([files[0],files[1],gap,files[2],files[3],files[4],files[5],main], relays['select_file_end']+b'\r')
        lua('TreeOriginalOpen("main.lua");require("jetvim.tree").open_entry();return true')
        equal(lua('return vim.api.nvim_buf_get_name(0)'), str(main), 'stale open-entry callback cannot act on an editor row')
        equal(files[0].read_text(), 'a.txt disk\n', 'dirty listed file remains unsaved on disk')
        equal(files[1].read_text(), 'b.txt disk\n', 'dirty unlisted file remains unsaved on disk')
        equal(main.read_text(), '-- unchanged\n', 'origin file is unchanged')
        equal(lua('return vim.v.errmsg'), '', 'bulk opening leaves no editor errors')
        print(f'PASS: {support["checks"]} tree open-all native/relay terminal checks')
    finally:
        try:
            lua('vim.fn.bufload=TreeOriginalLoad;vim.fn.bufadd=TreeOriginalAdd;vim.api.nvim_set_current_buf=TreeOriginalSwitch;require("jetvim.project").open=TreeOriginalOpen;return true')
        except Exception:
            pass
        editor.close()
