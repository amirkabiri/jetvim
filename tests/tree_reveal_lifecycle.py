#!/usr/bin/env python3
"""Reveal never loops on unnamed/tool buffers or a non-progressing ancestor."""
import json
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parent.parent
support = {'__file__': str(ROOT / 'tests/autosave.py')}
exec((ROOT / 'tests/autosave.py').read_text().split('\nwith tempfile.TemporaryDirectory', 1)[0], support)
Editor, equal, STATE = support['Editor'], support['equal'], support['STATE']

def literal(value):
    return json.dumps(str(value), ensure_ascii=False)

with tempfile.TemporaryDirectory(prefix='reveal-life-', dir=STATE) as directory, \
     tempfile.TemporaryDirectory(prefix='reveal-out-', dir=STATE) as external:
    project = Path(directory)
    (project / 'home').mkdir()
    main = project / 'main.lua'; main.write_text('-- unchanged\n')
    nested = project / 'nested'; nested.mkdir()
    target = nested / 'file.lua'; target.write_text('-- nested\n')
    outside = Path(external) / 'outside.lua'; outside.write_text('-- outside\n')
    editor = Editor(project, project / 'home/settings.lua', disabled=True, disable_lsp=True)
    lua = editor.lua
    registry = json.loads((ROOT / 'config/keymap.json').read_text())
    index = next(i for i, item in enumerate(registry, 1) if item['id'] == 'reveal')
    native = b'\x1b[1;11P'
    relay = f'\x1b[{0xF0000+index}u'.encode()

    def close_menu():
        lua('require("jetvim.tree_context").close(true);return true')
    def open_file(path):
        close_menu()
        lua('require("jetvim.project").open(' + literal(path) + ');return true')
        editor.wait('return vim.api.nvim_buf_get_name(0)==' + literal(path))
    def select(path):
        close_menu()
        equal(lua('local t=require("jetvim.tree");t.focus();t.expanded[' + literal(nested) + ']=true;t.render();'
                  'for row,e in pairs(t.rows)do if e.path==' + literal(path) + ' then vim.api.nvim_win_set_cursor(t.win,{row,0});return true end end;return false'),
              True, 'fixture tree entry selected')
    def selected():
        return lua('local t=require("jetvim.tree");return t.rows[vim.api.nvim_win_get_cursor(t.win)[1]].path')
    try:
        lua('_G.reveal_messages={};vim.notify=function(text)table.insert(reveal_messages,text)end;return true')
        for chord in (native, relay):
            open_file(main)
            lua('vim.cmd.enew();return true')
            editor.raw(chord)
            equal(lua('return require("jetvim.tree_context").state'), None, 'unnamed reveal returns without a context menu')
            equal(lua('return vim.api.nvim_buf_get_name(0)'), '', 'unnamed reveal keeps current buffer')
            lua('vim.cmd.edit(vim.fn.fnameescape(' + literal(outside) + '));return true')
            editor.raw(chord)
            equal(lua('return require("jetvim.tree_context").state'), None, 'outside reveal returns without a context menu')
            equal(lua('return vim.api.nvim_buf_get_name(0)'), str(outside), 'outside reveal keeps editor focus')
            for path in (project, target):
                select(path)
                editor.raw(chord)
                editor.wait('return vim.bo.filetype=="jetvim-tree-context"')
                equal(selected(), str(path), 'reveal from sidebar preserves root or selected file')
                editor.raw(b'\x1b[27u')
                editor.wait('return vim.bo.filetype=="jetvim-tree"')
                equal(selected(), str(path), 'Escape retains tree selection')
        # The synthetic dirname defect is capped before invocation: a regression
        # throws after 12 calls rather than leaving a runaway test backend.
        for chord in (native, relay):
            open_file(target)
            lua('''
              _G.reveal_original_dir=vim.fs.dirname;_G.reveal_dir_calls=0
              _G.reveal_bounded=false
              vim.fs.dirname=function(path)
                reveal_dir_calls=reveal_dir_calls+1
                if reveal_dir_calls>12 then reveal_bounded=true;error('bounded ancestor regression')end
                if path==''' + literal(nested) + ''' then return path end
                return reveal_original_dir(path)
              end
              return true
            ''')
            try:
                editor.raw(chord)
                editor.wait('return vim.bo.filetype=="jetvim-tree-context"')
                equal(lua('return reveal_bounded'), False, 'no-progress guard terminates before safety cap')
                equal(lua('return reveal_dir_calls<=6'), True, 'no-progress ancestor needs bounded dirname calls')
                equal(selected(), str(target), 'no-progress handling still reveals selected file')
            finally:
                lua('vim.fs.dirname=reveal_original_dir;return true')
                close_menu()
        equal(lua('return vim.v.errmsg'), '', 'reveal lifecycle leaves no editor errors')
        equal(main.read_text(), '-- unchanged\n', 'main file stays unchanged')
        equal(target.read_text(), '-- nested\n', 'nested file stays unchanged')
        equal(outside.read_text(), '-- outside\n', 'outside file stays unchanged')
        print(f'PASS: {support["checks"]} bounded reveal lifecycle checks through native/relay PTY input')
    finally:
        try:
            lua('if reveal_original_dir then vim.fs.dirname=reveal_original_dir end;require("jetvim.tree_context").close(true);return true')
        except Exception:
            pass
        editor.close()
