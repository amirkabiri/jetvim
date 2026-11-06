#!/usr/bin/env python3
"""Git-pane geometry through real terminal input, with every Git query stubbed."""
import fcntl
import json
import os
from pathlib import Path
import signal
import struct
import tempfile
import termios
import time

ROOT = Path(__file__).resolve().parent.parent
support = {'__file__': str(ROOT / 'tests/git_changes.py')}
exec((ROOT / 'tests/git_changes.py').read_text().split('\nwith tempfile.TemporaryDirectory', 1)[0], support)
Editor, equal = support['Editor'], support['equal']
STATE = support['STATE']
support['ENV']['JETVIM_DISABLE_VCS'] = '1'
support['ENV']['JETVIM_DISABLE_AUTOSAVE'] = '1'


def raw(editor, data):
    os.write(editor.master, data)
    time.sleep(0.09)


def toggle(editor):
    raw(editor, b'\x1b[57;9u')


def key(editor, direction):
    raw(editor, b'\x1b[1;7' + {'up': b'A', 'down': b'B', 'right': b'C', 'left': b'D'}[direction])


def size(editor):
    return editor.lua('local g=require("jetvim.git"); return {height=vim.api.nvim_win_get_height(g.list_win), '
                      'width=vim.api.nvim_win_get_width(g.list_win),preview=vim.api.nvim_win_get_width(g.diff_win)}')


def resize_terminal(editor, columns, rows):
    fcntl.ioctl(editor.master, termios.TIOCSWINSZ, struct.pack('HHHH', rows, columns, 0, 0))
    os.kill(editor.process.pid, signal.SIGWINCH)
    editor.wait(f'return vim.o.columns == {columns} and vim.o.lines == {rows}')


with tempfile.TemporaryDirectory(prefix='git-pane-layout-', dir=STATE) as folder:
    project = Path(folder)
    (project / 'one.lua').write_text('-- fixture\n')
    editor = Editor(project, 'one.lua')
    try:
        editor.lua('_G.git_layout_system=vim.system; vim.system=function(argv,...) '
                   'if argv[1]=="git" then error("Git command forbidden in geometry test") end; '
                   'return _G.git_layout_system(argv,...) end; '
                   'local g=require("jetvim.git"); g.refresh=function() '
                   'g.rows={}; for _,b in ipairs({g.list_buf,g.diff_buf}) do vim.bo[b].modifiable=true; '
                   'vim.api.nvim_buf_set_lines(b,0,-1,false,{"Mocked Git pane","No Git queries run"}); '
                   'vim.bo[b].modifiable=false; vim.bo[b].modified=false end end; return true')
        toggle(editor)
        editor.wait('return vim.bo.filetype == "jetvim-git"')
        baseline = size(editor)
        key(editor, 'up'); key(editor, 'up')
        key(editor, 'right'); key(editor, 'right'); key(editor, 'right')
        chosen = size(editor)
        equal(chosen['height'], baseline['height'] + 4, 'native resize grows bottom panel height')
        equal(chosen['width'], baseline['width'] + 12, 'native resize grows internal change list width')
        equal(editor.lua('return vim.bo.filetype'), 'jetvim-git', 'resize retains Git list focus')
        for _ in range(3):
            toggle(editor)
            equal(editor.lua('local g=require("jetvim.git"); return vim.api.nvim_win_is_valid(g.list_win)'), False, 'Command9 hides panel')
            toggle(editor)
            editor.wait('return vim.bo.filetype == "jetvim-git"')
            equal(size(editor), chosen, 'Command9 show restores chosen height and list width')
        editor.keys('<Esc>')
        equal(editor.lua('return vim.fs.basename(vim.api.nvim_buf_get_name(0))'), 'one.lua', 'Escape focuses source without hiding')
        toggle(editor)
        equal(size(editor), chosen, 'Command9 refocus from editor does not reset dimensions')
        editor.keys('<S-Esc>')
        toggle(editor)
        equal(size(editor), chosen, 'ShiftEscape hide also remembers dimensions')
        # A manually closed preview expands the list to full width. It must not
        # overwrite the width of the previous complete pane pair.
        editor.lua('local g=require("jetvim.git"); vim.api.nvim_win_close(g.diff_win,true); return true')
        time.sleep(0.1)
        equal(editor.lua('return require("jetvim.git").size.list_width'), chosen['width'], 'partial preview closure does not capture expanded list width')
        toggle(editor)
        equal(size(editor), chosen, 'preview recovery restores complete pair dimensions')
        equal(editor.lua('return #vim.api.nvim_tabpage_list_wins(0)'), editor.base_windows + 2, 'preview recovery leaves no orphaned pane')
        editor.lua('local g=require("jetvim.git"); vim.api.nvim_set_current_win(g.diff_win); vim.api.nvim_win_close(g.list_win,true); return true')
        time.sleep(0.1)
        toggle(editor)
        equal(size(editor), chosen, 'list recovery restores complete pair dimensions')
        equal(editor.lua('return #vim.api.nvim_tabpage_list_wins(0)'), editor.base_windows + 2, 'list recovery leaves no orphaned pane')
        # Save a larger preference, then genuinely shrink the backing PTY before
        # showing it again. The restored panel must fit the new terminal bounds.
        editor.lua('local g=require("jetvim.git"); vim.api.nvim_win_set_height(g.list_win,23); '
                   'vim.api.nvim_win_set_width(g.list_win,100); g.remember_size(); return true')
        toggle(editor)
        resize_terminal(editor, 64, 20)
        toggle(editor)
        narrowed = size(editor)
        equal(narrowed['width'] <= 53, True, 'list width clamps to narrow terminal')
        equal(narrowed['preview'] >= 10, True, 'narrow terminal retains readable preview')
        equal(narrowed['height'] <= 13, True, 'height clamps to short terminal')
        equal(narrowed['height'] >= 1, True, 'short terminal panel remains usable')
        toggle(editor)
        resize_terminal(editor, 140, 35)
        toggle(editor)
        equal(size(editor)['width'], 100, 'larger host restores desired width before temporary clamp')
        equal(size(editor)['height'], 23, 'larger host restores desired height before temporary clamp')
        equal(editor.lua('return vim.v.errmsg'), '', 'no pane lifecycle or resize errors')
        print(f'PASS: {support["checks"]} Git pane layout checks with mocked queries (no Git execution)')
    finally:
        editor.close()
