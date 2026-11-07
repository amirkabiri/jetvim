#!/usr/bin/env python3
"""Reveal/path context menu through native and private-relay terminal input."""
import json
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parent.parent
support = {'__file__': str(ROOT / 'tests/autosave.py')}
exec((ROOT / 'tests/autosave.py').read_text().split('\nwith tempfile.TemporaryDirectory', 1)[0], support)
Editor, equal, STATE = support['Editor'], support['equal'], support['STATE']

with tempfile.TemporaryDirectory(prefix='tree-menu-', dir=STATE) as directory, \
     tempfile.TemporaryDirectory(prefix='tree-menu-out-', dir=STATE) as outside_directory:
    project, outside = Path(directory), Path(outside_directory)
    (project / 'home').mkdir()
    (project / 'main.lua').write_text('-- editor stays unchanged\n')
    nested = project / 'nested space'; nested.mkdir()
    file = nested / 'δ file.txt'; file.write_text('target stays unchanged\n')
    external = outside / 'outside.txt'; external.write_text('outside unchanged\n')
    link = project / 'outside-link'; link.symlink_to(external)
    editor = Editor(project, project / 'home/settings.lua', disabled=True, disable_lsp=True)
    lua = editor.lua
    bindings = json.loads((ROOT / 'config/keymap.json').read_text())
    index = next(i for i, item in enumerate(bindings, 1) if item['id'] == 'reveal')
    relay = f'\x1b[{0xF0000 + index}u'.encode()
    native = b'\x1b[1;11P'
    kitty = b'\x1b[57364;11u'
    original = b'\x1b[57364;3u'
    original_legacy = b'\x1b[1;3P'
    def open_file(path):
        lua('require("jetvim.tree_context").close(true);require("jetvim.project").open(' + json.dumps(str(path), ensure_ascii=False) + ');return true')
        editor.wait('return vim.api.nvim_buf_get_name(0)==' + json.dumps(str(path), ensure_ascii=False))
    def menu(chord=native):
        editor.raw(chord)
        editor.wait('return vim.bo.filetype=="jetvim-tree-context"')
    def selected_path():
        return lua('local t=require("jetvim.tree");return t.rows[vim.api.nvim_win_get_cursor(t.win)[1]].path')
    def tree_focus():
        editor.wait('return vim.bo.filetype=="jetvim-tree"')
    def choose(path):
        lua('require("jetvim.tree_context").close(true);local t=require("jetvim.tree");t.focus();t.render();'
            'for row,e in pairs(t.rows) do if e.path==' + json.dumps(str(path), ensure_ascii=False) + ' then vim.api.nvim_win_set_cursor(t.win,{row,0});return true end end;return false')
    try:
        lua('''
          _G.context_has=vim.fn.has;_G.context_executable=vim.fn.executable;_G.context_setreg=vim.fn.setreg
          _G.context_messages={};vim.notify=function(text)table.insert(context_messages,text)end
          vim.fn.has=function(name)if name=='clipboard' then return 1 end;return context_has(name)end
          vim.fn.setreg=function(name,text,kind)
            if name=='+' then _G.context_clipboard={text=vim.deepcopy(text),kind=kind};return 0 end
            return context_setreg(name,text,kind)
          end
          return true
        ''')
        open_file(file)
        geometry = lua('local t=require("jetvim.tree");return {#vim.api.nvim_list_wins(),vim.api.nvim_win_get_width(t.win)}')
        for chord in (native, kitty, relay, original, original_legacy):
            open_file(file); menu(chord)
            equal(selected_path(), str(file), 'shortcut reveals the correct nested file')
            equal(lua('return vim.api.nvim_buf_get_lines(0,0,-1,false)'), ['  Copy Relative Path', '  Copy Absolute Path'], 'context has exactly two path actions')
            equal(lua('return vim.api.nvim_win_get_height(0)'), 2, 'context is a compact two-row popup')
            editor.raw(b'\x1b[27u'); tree_focus()
            equal(selected_path(), str(file), 'Escape keeps revealed file selected')
            equal(lua('local t=require("jetvim.tree");return {#vim.api.nvim_list_wins(),vim.api.nvim_win_get_width(t.win)}'), geometry, 'Escape restores tree focus without resizing panes')
        # The generated profile aliases the existing relay ID, never a new action.
        expected = f'keybind = super+alt+f1=esc:[{0xF0000+index}u'
        equal(expected in (ROOT / 'terminal/ghostty.conf').read_text(), True, 'Command Option F1 adapter preserves reveal relay')
        menu(); editor.raw(b'\x1b[B\x1b[A\r'); tree_focus()
        relative = 'nested space/δ file.txt'
        equal(lua('return vim.fn.getreg(\'"\')'), relative, 'relative path copied to local register')
        equal(lua('return context_clipboard'), {'text': [relative], 'kind': 'v'}, 'available clipboard receives literal relative path')
        equal(lua('local h=require("jetvim.edit").history[1];return {h.text,h.kind}'), [[relative], 'v'], 'path copy uses normal text clipboard history')
        menu(relay); editor.raw(b'\x1b[B\r'); tree_focus()
        equal(lua('return vim.fn.getreg(\'"\')'), str(file), 'Down Enter copies absolute path')
        equal(lua('return context_clipboard.text'), [str(file)], 'absolute path reaches clipboard provider')
        # An unavailable clipboard falls back to the local register without
        # attempting external system clipboard commands from this fixture.
        lua('vim.fn.has=function(name)if name=="clipboard"then return 0 end;return context_has(name)end;'
            'vim.fn.executable=function(name)if name=="pbcopy"then return 0 end;return context_executable(name)end;'
            'context_clipboard=nil;return true')
        menu(); editor.raw(b'\x1b[B\r'); tree_focus()
        equal(lua('return vim.fn.getreg(\'"\')'), str(file), 'clipboard-free terminal retains copied path locally')
        equal(lua('return context_clipboard'), None, 'fallback never invokes unavailable system clipboard')
        choose(nested); menu(); editor.raw(b'\r'); tree_focus()
        equal(lua('return vim.fn.getreg(\'"\')'), 'nested space', 'selected folder path is relative to project root')
        choose(link); menu(); editor.raw(b'\x1b[B\r'); tree_focus()
        equal(lua('return vim.fn.getreg(\'"\')'), str(link), 'symlink path copied without resolving its outside target')
        equal(external.read_text(), 'outside unchanged\n', 'path actions never touch symlink target')
        choose(project); menu(); editor.raw(b'\r'); tree_focus()
        equal(lua('return vim.fn.getreg(\'"\')'), '.', 'project root has dot relative path')
        # Changing the selection behind an open menu invalidates its context.
        choose(file); menu(); previous = lua('return vim.fn.getreg(\'"\')')
        lua('local t=require("jetvim.tree");vim.api.nvim_win_set_cursor(t.win,{2,0});return true')
        editor.raw(b'\r'); tree_focus()
        equal(lua('return vim.fn.getreg(\'"\')'), previous, 'stale menu selection cannot copy the wrong path')
        equal(lua('return context_messages[#context_messages]:find("context changed",1,true)~=nil'), True, 'stale context explains why copy was skipped')
        # A removed path is rejected even when its old tree row still exists.
        removed = nested / 'removed.txt'; removed.write_text('temporary menu target\n')
        choose(removed); menu(); previous = lua('return vim.fn.getreg(\'"\')')
        removed.unlink()
        editor.raw(b'\r'); tree_focus()
        equal(lua('return vim.fn.getreg(\'"\')'), previous, 'removed menu target cannot be copied')
        equal(lua('return context_messages[#context_messages]:find("context changed",1,true)~=nil'), True, 'removed target explains skipped copy')
        # Reopening while open replaces one popup, not a stack of windows.
        choose(file); menu()
        for _ in range(3):
            menu(relay)
            equal(lua('return #vim.api.nvim_list_wins()'), geometry[0]+1, 'repeated reveal keeps one context popup')
        editor.raw(b'\x1b[27u'); tree_focus()
        equal(lua('local n=0;for _,b in ipairs(vim.api.nvim_list_bufs())do if vim.bo[b].filetype=="jetvim-tree-context" then n=n+1 end end;return n'), 0, 'closed menus leave no scratch buffers')
        menu();lua('require("jetvim.tree").editor();return true')
        editor.wait('return require("jetvim.tree_context").state==nil')
        equal(lua('return #vim.api.nvim_list_wins()'), geometry[0], 'leaving context closes popup without window leaks')
        # Unnamed and outside-project buffers do not reveal or copy a bogus root.
        lua('vim.cmd.enew();return true');editor.raw(native)
        equal(lua('return require("jetvim.tree_context").state'), None, 'unnamed buffer has no file menu')
        lua('vim.cmd.edit(vim.fn.fnameescape(' + json.dumps(str(external), ensure_ascii=False) + '));return true');editor.raw(native)
        equal(lua('return require("jetvim.tree_context").state'), None, 'outside project file has no misleading tree menu')
        equal(lua('return vim.api.nvim_buf_get_name(0)'), str(external), 'outside reveal leaves original editor focus')
        equal((project / 'main.lua').read_text(), '-- editor stays unchanged\n', 'main editor file never changed')
        equal(file.read_text(), 'target stays unchanged\n', 'revealed file never changed')
        equal(lua('return vim.v.errmsg'), '', 'context operations leave no editor errors')
        print(f'PASS: {support["checks"]} tree reveal/context/clipboard terminal checks')
    finally:
        try:
            lua('require("jetvim.tree_context").close(true);vim.fn.has=context_has;vim.fn.executable=context_executable;vim.fn.setreg=context_setreg;return true')
        except Exception:pass
        editor.close()
