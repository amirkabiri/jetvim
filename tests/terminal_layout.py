#!/usr/bin/env python3
"""Remember tool-pane sizes across real terminal toggles and project restarts."""
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
support = {'__file__': str(ROOT / 'tests/autosave.py')}
exec((ROOT / 'tests/autosave.py').read_text().split('\nwith tempfile.TemporaryDirectory', 1)[0], support)
Editor, equal, STATE = support['Editor'], support['equal'], support['STATE']
bindings = json.loads((ROOT / 'config/keymap.json').read_text())


def relay(editor, action):
    index = next(i for i, entry in enumerate(bindings, 1) if entry['id'] == action)
    editor.raw(f'\x1b[{0xF0000 + index}u')


def toggle(editor, bridged=False):
    if bridged:
        relay(editor, 'terminal')
    else:
        editor.raw(b'\x1b[57375;3u')


def height(editor):
    return editor.lua('return vim.api.nvim_win_get_height(require("jetvim.actions").term_win)')


def resize_host(editor, columns, rows):
    fcntl.ioctl(editor.master, termios.TIOCSWINSZ, struct.pack('HHHH', rows, columns, 0, 0))
    os.kill(editor.process.pid, signal.SIGWINCH)
    editor.wait(f'return vim.o.columns == {columns} and vim.o.lines == {rows}')
    time.sleep(.15)


def prepare(editor):
    # No shell startup files and no Git commands: geometry tests stub Git data.
    editor.lua('vim.o.shell="/bin/sh"; local g=require("jetvim.git"); g.refresh=function() '
               'for _,b in ipairs({g.list_buf,g.diff_buf}) do vim.bo[b].modifiable=true; '
               'vim.api.nvim_buf_set_lines(b,0,-1,false,{"Geometry fixture"}); vim.bo[b].modified=false; vim.bo[b].modifiable=false end end; return true')


with tempfile.TemporaryDirectory(prefix='terminal-layout-', dir=STATE) as directory:
    base = Path(directory)
    project, home = base / 'project', base / 'home'
    project.mkdir(); home.mkdir()
    (project / 'main.lua').write_text('-- main\n')
    preferences = home / 'settings.lua'
    editor = Editor(project, preferences, disabled=True)
    layout = project / '.idea/jetvim/layout.json'
    try:
        prepare(editor)
        editor_window = editor.lua('return vim.api.nvim_get_current_win()')
        equal(layout.exists(), False, 'startup creates no layout metadata')
        # Opening and immediately resizing in one input batch must be retained.
        editor.raw(b'\x1b[57375;3u\x1b[1;7A')
        editor.wait('return vim.bo.buftype == "terminal"')
        initial = height(editor)
        equal(initial, 14, 'same-batch native toggle then resize is applied')
        editor.raw(b'\x1b[1;7A')
        editor.raw(b'\x1b[1;7A')
        chosen = height(editor)
        equal(chosen, initial + 4, 'native ControlOptionUp resizes terminal pane')
        term_buf = editor.lua('return vim.api.nvim_get_current_buf()')
        for bridged in (False, True, False):
            toggle(editor, bridged)
            equal(editor.lua('return vim.api.nvim_win_is_valid(require("jetvim.actions").term_win or -1)'), False, 'terminal hides')
            toggle(editor, bridged)
            equal(height(editor), chosen, 'terminal toggle restores chosen height')
            equal(editor.lua('return vim.api.nvim_get_current_buf()'), term_buf, 'terminal process buffer survives toggle')
        # SGR mouse drag of horizontal separator, as a user dragging its edge.
        geometry = editor.lua('local w=require("jetvim.actions").term_win; return {row=vim.api.nvim_win_get_position(w)[1],col=40}')
        row = geometry['row']
        editor.raw(f'\x1b[<0;40;{row}M')
        editor.raw(f'\x1b[<32;40;{row-2}M')
        editor.raw(f'\x1b[<0;40;{row-2}m')
        dragged = height(editor)
        equal(dragged, chosen + 2, 'mouse separator drag resizes terminal')
        toggle(editor, True); toggle(editor, True)
        equal(height(editor), dragged, 'mouse chosen height survives toggle')
        editor.raw('exit\r')
        editor.wait('return vim.fn.jobwait({vim.b.terminal_job_id},0)[1] ~= -1')
        if editor.lua('local w=require("jetvim.actions").term_win; return w ~= nil and vim.api.nvim_win_is_valid(w)'):
            toggle(editor)
        toggle(editor)
        equal(height(editor), dragged, 'exited terminal recreation restores height')
        equal(editor.lua('return vim.api.nvim_get_current_buf() ~= ' + str(term_buf)), True, 'exited process gets a fresh terminal buffer')
        # External window closure must not lose the last stable dimensions.
        editor.lua('vim.api.nvim_win_close(require("jetvim.actions").term_win,true); return true')
        toggle(editor, True)
        equal(height(editor), dragged, 'manual terminal-window close retains dimensions')
        toggle(editor)
        equal(editor.lua('return vim.api.nvim_win_is_valid(' + str(editor_window) + ')'), True, 'original editor identity remains intact')
        editor.lua('local t=require("jetvim.tree"); vim.api.nvim_win_set_width(t.win,43); t.remember_width(); return true')
        relay(editor, 'git_changes')
        editor.lua('local g=require("jetvim.git"); vim.api.nvim_win_set_height(g.list_win,16); vim.api.nvim_win_set_width(g.list_win,57); g.remember_size(); return true')
        relay(editor, 'git_changes')
        editor.wait('return vim.bo.filetype ~= "jetvim-git"')
        editor.lua('require("jetvim.layout").flush(); return true')
        expected = {'terminal_height': dragged, 'tree_width':43, 'git_height':16, 'git_list_width':57}
        equal(json.loads(layout.read_text())['sizes'], expected, 'all tool dimensions persisted as project JSON data')
        toggle(editor)
        relay(editor, 'git_changes')
        equal(editor.lua('local a=require("jetvim.actions"); local g=require("jetvim.git"); return vim.api.nvim_win_is_valid(a.term_win) and vim.api.nvim_win_is_valid(g.list_win)'), True, 'terminal and Git can coexist beside resized sidebar')
        relay(editor, 'git_changes')
        editor.lua('require("jetvim.layout").flush(); return true')
        equal(json.loads(layout.read_text())['sizes'], expected, 'hiding Git does not capture expanded terminal survivor')
        toggle(editor)
        relay(editor, 'git_changes')
        toggle(editor)
        toggle(editor)
        editor.lua('require("jetvim.layout").flush(); return true')
        equal(json.loads(layout.read_text())['sizes'], expected, 'hiding terminal does not capture expanded Git survivor')
        relay(editor, 'git_changes')
        editor.lua('local g=require("jetvim.git"); if vim.api.nvim_win_is_valid(g.list_win) then g.hide() end; return true')
    finally:
        editor.close()
    editor = Editor(project, preferences, disabled=True)
    try:
        prepare(editor)
        equal(editor.lua('return vim.api.nvim_win_get_width(require("jetvim.tree").win)'), 43, 'tree width survives restart')
        toggle(editor)
        equal(height(editor), expected['terminal_height'], 'terminal height survives restart')
        toggle(editor)
        relay(editor, 'git_changes')
        equal(editor.lua('local g=require("jetvim.git"); return {height=vim.api.nvim_win_get_height(g.list_win),width=vim.api.nvim_win_get_width(g.list_win)}'), {'height':16,'width':57}, 'Git height and list width survive restart')
        relay(editor, 'git_changes')
        editor.lua('require("jetvim.tree").hide(); return true')
        resize_host(editor, 40, 19)
        editor.lua('require("jetvim.tree").focus(); return true')
        equal(editor.lua('return vim.api.nvim_win_get_width(require("jetvim.tree").win) <= 28'), True, 'restored tree clamps to narrow host')
        editor.lua('require("jetvim.tree").editor(); return true')
        toggle(editor)
        equal(height(editor) <= 12, True, 'restored terminal clamps to smaller host')
        toggle(editor)
        relay(editor, 'git_changes')
        equal(editor.lua('local g=require("jetvim.git"); return vim.api.nvim_win_get_width(g.list_win) <= 29 and vim.api.nvim_win_get_height(g.list_win) <= 12'), True, 'restored Git panes clamp to narrow and short host')
        relay(editor, 'git_changes')
        editor.lua('require("jetvim.layout").flush(); return true')
        equal(json.loads(layout.read_text())['sizes'], expected, 'temporary host clamp does not overwrite preferred sizes')
        resize_host(editor, 140, 35)
        editor.lua('local t=require("jetvim.tree"); t.hide(); t.focus(); t.editor(); return true')
        equal(editor.lua('return vim.api.nvim_win_get_width(require("jetvim.tree").win)'), 43, 'larger host restores original preferred tree width')
        toggle(editor)
        equal(height(editor), expected['terminal_height'], 'larger host restores original preferred terminal height')
        toggle(editor)
        relay(editor, 'git_changes')
        equal(editor.lua('local g=require("jetvim.git"); return {vim.api.nvim_win_get_height(g.list_win),vim.api.nvim_win_get_width(g.list_win)}'), [16,57], 'larger host restores original preferred Git dimensions')
    finally:
        editor.close()
    # Malformed and out-of-bound JSON never executes code or crashes startup.
    layout.write_text('{invalid json')
    editor = Editor(project, preferences, disabled=True)
    try:
        prepare(editor)
        equal(editor.lua('return require("jetvim.layout").get("terminal_height",12)'), 12, 'malformed layout falls back safely')
    finally:
        editor.close()
    layout.write_text(json.dumps({'version':1,'sizes':{'tree_width':-5,'terminal_height':10001,'git_height':'execute()','git_list_width':51}}))
    editor = Editor(project, preferences, disabled=True)
    try:
        equal(editor.lua('local l=require("jetvim.layout"); return {l.get("tree_width",30),l.get("terminal_height",12),l.get("git_height",14),l.get("git_list_width",42)}'), [30,12,14,51], 'invalid dimensions ignored individually')
    finally:
        editor.close()
    # A project metadata symlink escaping the selected project is never written.
    escaped, target = base / 'symlink-project', base / 'outside-project'
    escaped.mkdir(); target.mkdir()
    (escaped/'main.lua').write_text('-- safe\n')
    (escaped/'.idea').symlink_to(target, target_is_directory=True)
    editor = Editor(escaped, preferences, disabled=True)
    try:
        editor.lua('local t=require("jetvim.tree"); vim.api.nvim_win_set_width(t.win,40); t.remember_width(); require("jetvim.layout").flush(); return true')
        equal(list(target.iterdir()), [], 'metadata symlink escape creates no external files')
    finally:
        editor.close()
print('PASS:', support['checks'], 'terminal and persistent tool-pane layout checks through real PTY input')
