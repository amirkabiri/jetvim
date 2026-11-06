#!/usr/bin/env python3
"""Right Arrow focuses a selected Git diff through actual PTY input; Git is mocked."""
import json
import os
from pathlib import Path
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
support = {'__file__': str(ROOT / 'tests/git_changes.py')}
exec((ROOT / 'tests/git_changes.py').read_text().split('\nwith tempfile.TemporaryDirectory', 1)[0], support)
Editor, equal, STATE = support['Editor'], support['equal'], support['STATE']
support['ENV']['JETVIM_DISABLE_VCS'] = '1'
support['ENV']['JETVIM_DISABLE_AUTOSAVE'] = '1'


def raw(editor, data):
    os.write(editor.master, data)
    time.sleep(.10)


def geometry(editor):
    return editor.lua('local g=require("jetvim.git"); return {vim.api.nvim_win_get_height(g.list_win),'
                      'vim.api.nvim_win_get_width(g.list_win),vim.api.nvim_win_get_width(g.diff_win)}')


def focus_list(editor, row=None):
    editor.lua('local g=require("jetvim.git"); vim.api.nvim_set_current_win(g.list_win); '
               + ('vim.api.nvim_win_set_cursor(g.list_win,{' + str(row) + ',0}); ' if row else '')
               + 'return true')
    time.sleep(.06)


def current(editor, side):
    return editor.lua('return vim.api.nvim_get_current_win()==require("jetvim.git").' + side + '_win')


def latest_job(editor, path):
    return editor.lua('for i=#_G.git_focus_jobs,1,-1 do if _G.git_focus_jobs[i].path=='
                      + json.dumps(path) + ' then return i end end; return 0')


def complete(editor, job, text):
    editor.lua('_G.git_focus_jobs[' + str(job) + '].callback({code=0,stdout=' + json.dumps(text)
               + ',stderr=""}); return true')
    time.sleep(.08)


def preview_text(editor):
    return editor.lua('return table.concat(vim.api.nvim_buf_get_lines(require("jetvim.git").diff_buf,0,-1,false),"\\n")')


with tempfile.TemporaryDirectory(prefix='git-focus-', dir=STATE) as directory:
    project = Path(directory)
    (project / 'one.lua').write_text('-- first\n')
    (project / 'two.lua').write_text('-- second\n')
    editor = Editor(project, 'one.lua')
    try:
        editor.lua('''
_G.git_focus_jobs={}
_G.git_focus_entries={
  {section='Unstaged Changes',status='M',path='one.lua'},
  {section='Unstaged Changes',status='M',path='two.lua'},
}
_G.git_focus_original_system=vim.system
vim.system=function(argv,opts,callback)
  if argv[1]~='git' then return _G.git_focus_original_system(argv,opts,callback) end
  assert(vim.tbl_contains(argv,'diff'),'Unexpected mocked Git query')
  _G.git_focus_jobs[#_G.git_focus_jobs+1]={path=argv[#argv],callback=callback}
  return {kill=function()end}
end
local g=require('jetvim.git')
g.refresh=function() g.repo=vim.uv.cwd(); g.render(_G.git_focus_entries) end
return true
''')
        raw(editor, b'\x1b[57;9u')
        editor.wait('return vim.bo.filetype=="jetvim-git"')
        equal(current(editor, 'list'), True, 'Command9 focuses the changes list')
        initial = geometry(editor)
        selected = editor.lua('local g=require("jetvim.git"); return vim.api.nvim_win_get_cursor(g.list_win)[1]')
        equal(editor.lua('local g=require("jetvim.git"); return g.rows[vim.api.nvim_win_get_cursor(g.list_win)[1]].path'),
              'one.lua', 'first changed file selected')
        pending = editor.lua('return #_G.git_focus_jobs')
        raw(editor, b'\x1b[C')
        equal(current(editor, 'diff'), True, 'native CSI Right focuses the diff immediately')
        equal(editor.lua('return vim.fn.mode()'), 'n', 'diff remains in navigation mode')
        equal(geometry(editor), initial, 'Right does not resize either pane')
        equal(editor.lua('local g=require("jetvim.git"); return vim.api.nvim_win_get_cursor(g.list_win)[1]'),
              selected, 'Right preserves the selected list row')
        equal('one.lua' in preview_text(editor), True, 'preview identifies the selected file while loading')
        equal(editor.lua('return #_G.git_focus_jobs'), pending, 'focus reuses the current selected preview query')
        complete(editor, latest_job(editor, 'one.lua'), 'diff one\n+first change\n')
        equal('+first change' in preview_text(editor), True, 'selected diff renders after focus moves')
        equal(current(editor, 'diff'), True, 'asynchronous preview preserves diff focus')
        editor.lua('vim.api.nvim_win_set_cursor(0,{4,2}); return true')
        editor.keys('<S-Tab>')
        pending = editor.lua('return #_G.git_focus_jobs')
        raw(editor, b'\x1b[C')
        equal(editor.lua('return vim.api.nvim_win_get_cursor(0)'), [4, 2], 'refocusing an existing diff preserves its reading position')
        equal(editor.lua('return #_G.git_focus_jobs'), pending, 'refocusing a loaded diff does not rerun Git')
        equal(editor.lua('return #vim.fn.win_findbuf(vim.fn.bufnr(vim.uv.cwd().."/one.lua"))'), 1,
              'focusing diff does not create another source editor')
        before = editor.lua('return vim.api.nvim_win_get_cursor(0)[2]')
        raw(editor, b'\x1b[C')
        equal(current(editor, 'diff'), True, 'Right inside diff stays in diff')
        equal(editor.lua('return vim.api.nvim_win_get_cursor(0)[2]'), before + 1, 'Right inside diff navigates text')
        editor.keys('<S-Tab>')
        equal(current(editor, 'list'), True, 'ShiftTab still returns to the list')
        raw(editor, b'\x1bOC')
        equal(current(editor, 'diff'), True, 'application-mode SS3 Right also focuses the diff')
        editor.keys('<S-Tab>')
        focus_list(editor, 4)
        raw(editor, b'\x1b[C')
        equal(current(editor, 'list'), True, 'Right on section heading does not focus a file diff')
        equal(editor.lua('return vim.api.nvim_win_get_cursor(0)[1]'), 4, 'header selection stays unchanged')
        focus_list(editor, 5)
        old = latest_job(editor, 'one.lua')
        # Select another row and press Right before depending on CursorMoved.
        editor.lua('local g=require("jetvim.git"); vim.api.nvim_win_set_cursor(g.list_win,{6,0}); return true')
        raw(editor, b'\x1b[C')
        equal(current(editor, 'diff'), True, 'Right focuses the newly selected file diff')
        equal('two.lua' in preview_text(editor), True, 'new selection appears in preview heading immediately')
        complete(editor, latest_job(editor, 'two.lua'), 'diff two\n+second change\n')
        complete(editor, old, 'diff one\n+stale first change\n')
        equal('+second change' in preview_text(editor), True, 'late old-file callback cannot replace current diff')
        equal('stale' in preview_text(editor), False, 'stale preview output is ignored')
        equal(current(editor, 'diff'), True, 'stale result does not steal focus')
        equal(editor.lua('return vim.fn.bufnr(vim.uv.cwd().."/two.lua")'), -1, 'Right does not open selected source file')
        equal(geometry(editor), initial, 'selection and preview callbacks preserve pane sizes')
        editor.keys('<S-Tab>')
        editor.lua('require("jetvim.git").render({}); return true')
        raw(editor, b'\x1b[C')
        equal(current(editor, 'list'), True, 'Right on a clean list is a safe no-op')
        editor.keys('<Tab>')
        equal(current(editor, 'diff'), True, 'existing Tab focus still works on empty list')
        editor.keys('<S-Tab>')
        editor.lua('local g=require("jetvim.git"); g.repo=nil; g.rows={}; '
                   'vim.bo[g.list_buf].modifiable=true; vim.api.nvim_buf_set_lines(g.list_buf,0,-1,false,{"Not a Git repository"}); '
                   'vim.bo[g.list_buf].modifiable=false; vim.bo[g.list_buf].modified=false; return true')
        raw(editor, b'\x1b[C')
        equal(current(editor, 'list'), True, 'Right in non-repository view is a safe no-op')
        editor.lua('local g=require("jetvim.git"); g.refresh(); vim.api.nvim_win_close(g.diff_win,true); return true')
        raw(editor, b'\x1b[C')
        equal(current(editor, 'list'), True, 'missing preview window does not throw or create extra panes')
        raw(editor, b'\x1b[57;9u')
        editor.wait('local g=require("jetvim.git"); return vim.api.nvim_win_is_valid(g.diff_win)')
        raw(editor, b'\x1b[C')
        equal(current(editor, 'diff'), True, 'Right works after preview-pane recovery')
        equal(geometry(editor), initial, 'preview recovery retains original dimensions')
        equal((project / 'one.lua').read_text(), '-- first\n', 'preview focus does not write first file')
        equal((project / 'two.lua').read_text(), '-- second\n', 'preview focus does not write second file')
        equal(editor.lua('return vim.v.errmsg'), '', 'no native editor errors')
        print(f'PASS: {support["checks"]} Git diff-focus PTY checks (all Git queries mocked)')
    finally:
        editor.close()
