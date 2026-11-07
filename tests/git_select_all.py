#!/usr/bin/env python3
"""Select change entries through native/relay PTY input; every Git call is mocked."""
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


def quote(value): return json.dumps(value, ensure_ascii=False)
def json_lua(value): return 'vim.json.decode(' + quote(json.dumps(value, ensure_ascii=False)) + ')'
def raw(editor, data):
    os.write(editor.master, data)
    time.sleep(.08)


with tempfile.TemporaryDirectory(prefix='git-select-', dir=STATE) as directory:
    project = Path(directory)
    odd = 'odd\t世界\r\nfile.lua'
    for name in ('one.lua', 'conflict.lua', 'new.lua', odd):
        (project / name).write_text('-- unchanged\n')
    (project / 'alternate').mkdir()
    status = 'UU conflict.lua\0MM one.lua\0 D deleted.lua\0?? ' + odd + '\0'
    editor = Editor(project, 'one.lua')
    def lua(code): return editor.lua(code)
    def count(): return lua('return require("jetvim.git").selected_count')
    def selected():
        return lua('local result={};for _,e in ipairs(require("jetvim.git").selected_entries()) do '
                   'result[#result+1]={section=e.section,path=e.path} end;return result')
    def list_focus(): lua('vim.api.nvim_set_current_win(require("jetvim.git").list_win);return true')
    def snapshot():
        return lua('local g=require("jetvim.git");return {lines=vim.api.nvim_buf_get_lines(g.diff_buf,0,-1,false),'
                   'view=vim.api.nvim_win_call(g.diff_win,vim.fn.winsaveview),'
                   'geometry={vim.api.nvim_win_get_height(g.list_win),vim.api.nvim_win_get_width(g.list_win),'
                   'vim.api.nvim_win_get_width(g.diff_win)},diff=g.diff_buf,win=vim.api.nvim_get_current_win(),'
                   'cursor=vim.api.nvim_win_get_cursor(g.list_win),calls=#_G.git_select_calls}')
    def marks():
        return lua('local g=require("jetvim.git");return vim.api.nvim_buf_get_extmarks(g.list_buf,'
                   'vim.api.nvim_get_namespaces().JetvimGitSelection,0,-1,{details=true})')
    def refresh(value, expected):
        lua('_G.git_select_status=' + json_lua(value) + ';local g=require("jetvim.git");'
            '_G.git_select_previous_rows=g.rows;g.refresh();return true')
        editor.wait('local g=require("jetvim.git");return g.rows~=_G.git_select_previous_rows and vim.tbl_count(g.rows)==' + str(expected))
        editor.wait('return not table.concat(vim.api.nvim_buf_get_lines(require("jetvim.git").diff_buf,0,-1,false),"\\n"):find("Loading",1,true)')
    try:
        lua('_G.git_select_status=' + json_lua(status) + ''';
_G.git_select_calls={};_G.git_select_root=vim.uv.cwd();_G.git_select_root_code=0;_G.git_select_status_code=0
_G.git_select_system=vim.system
vim.system=function(argv,opts,callback)
  if argv[1]~='git' then return _G.git_select_system(argv,opts,callback) end
  _G.git_select_calls[#_G.git_select_calls+1]=argv
  local response
  if vim.tbl_contains(argv,'rev-parse') then response={code=_G.git_select_root_code,stdout=_G.git_select_root..'\\n',stderr='not a repository'}
  elseif vim.tbl_contains(argv,'status') then response={code=_G.git_select_status_code,stdout=_G.git_select_status,stderr='status error'}
  else
    assert(vim.tbl_contains(argv,'diff'),'Unexpected mocked Git query')
    local lines={'diff fixture','--- before','+++ after'}
    for i=1,30 do lines[#lines+1]='+ change '..i end
    response={code=0,stdout=table.concat(lines,'\\n'),stderr=''}
  end
  vim.schedule(function() callback(response) end)
  return {kill=function()end}
end
return true
''')
        raw(editor, b'\x1b[57;9u')
        editor.wait('return vim.bo.filetype=="jetvim-git" and vim.tbl_count(require("jetvim.git").rows)==5')
        editor.wait('return table.concat(vim.api.nvim_buf_get_lines(require("jetvim.git").diff_buf,0,-1,false),"\\n"):find("change 30",1,true)~=nil')
        lua('vim.api.nvim_win_set_cursor(require("jetvim.git").diff_win,{12,2});return true')
        bindings = json.loads((ROOT / 'config/keymap.json').read_text())
        index = next(i for i, binding in enumerate(bindings, 1) if binding['id'] == 'select_all')
        variants = [('native CmdA', b'\x1b[97;9u'), ('private relay CmdA', f'\x1b[{0xF0000+index}u'.encode())]
        for label, chord in variants:
            before = snapshot()
            raw(editor, chord)
            equal(count(), 5, label + ' selects all change entries')
            equal(lua('return vim.fn.mode()'), 'n', label + ' does not select scratch-buffer text')
            equal(snapshot(), before, label + ' leaves diff, scroll, geometry, cursor and Git calls untouched')
            equal(selected(), [
                {'section':'Conflicts','path':'conflict.lua'},
                {'section':'Staged Changes','path':'one.lua'},
                {'section':'Unstaged Changes','path':'one.lua'},
                {'section':'Unstaged Changes','path':'deleted.lua'},
                {'section':'Untracked Files','path':odd},
            ], label + ' preserves exact section/raw-path identities')
            highlights = marks()
            rows = lua('local rows={};for row in pairs(require("jetvim.git").rows) do rows[#rows+1]=row-1 end;table.sort(rows);return rows')
            equal(sorted(mark[1] for mark in highlights if mark[3].get('line_hl_group')), rows,
                  label + ' visibly highlights only actual entries, never headers')
            equal(all(mark[3]['virt_text'][0][0] == ' ✓ ' for mark in highlights if mark[3].get('line_hl_group')),
                  True, label + ' marks each selected entry')
            equal(any('5 changes selected' in mark[3]['virt_text'][0][0] for mark in highlights), True,
                  label + ' shows accurate change-entry count')
            equal(lua('return vim.api.nvim_get_hl(0,{name="JetvimGitSelected",link=false}).fg==nil'), True,
                  label + ' selection background does not replace filename status colors')
            raw(editor, chord)
            equal(count(), 5, label + ' is idempotent')
            equal(snapshot(), before, label + ' repeat causes no preview refresh')
            raw(editor, b'\x1b[B')
            equal(count(), 0, label + ' ordinary Down clears multiselection')
            equal(marks(), [], label + ' ordinary Down clears all selection decorations')
        for mode, chord in [('Visual', variants[0][1]), ('Select', variants[1][1])]:
            editor.keys('v')
            if mode == 'Select': editor.keys('<C-g>')
            raw(editor, chord)
            equal(lua('return vim.fn.mode()'), 'n', mode + ' list CmdA exits text-selection mode')
            equal(count(), 5, mode + ' list CmdA still selects change entries')
            raw(editor, b'\x1b[B')
        lua('_G.git_select_clear_count=0;_G.git_select_clear_namespace=vim.api.nvim_buf_clear_namespace;'
            'vim.api.nvim_buf_clear_namespace=function(buf,ns,...) '
            'if ns==vim.api.nvim_get_namespaces().JetvimGitSelection then git_select_clear_count=git_select_clear_count+1 end;'
            'return git_select_clear_namespace(buf,ns,...) end;return true')
        for arrow in (b'\x1b[A',b'\x1b[B',b'\x1b[D',b'\x1b[C'):
            raw(editor, arrow)
        equal(lua('vim.api.nvim_buf_clear_namespace=git_select_clear_namespace;return git_select_clear_count'), 0,
              'ordinary arrows with empty selection do no selection redraw work')
        list_focus()
        for arrow, side in [(b'\x1b[A','list'),(b'\x1b[D','list'),(b'\x1b[C','diff')]:
            list_focus();raw(editor, variants[0][1]);raw(editor, arrow)
            equal(count(), 0, 'ordinary arrow clears selection')
            equal(lua('return vim.api.nvim_get_current_win()==require("jetvim.git").' + side + '_win'), True,
                  'arrow preserves expected list/diff focus')
        list_focus();raw(editor, variants[0][1])
        lua('local g=require("jetvim.git");vim.api.nvim_win_set_cursor(g.list_win,{4,0});return true')
        editor.wait('return require("jetvim.git").selected_count==0')
        raw(editor, variants[1][1])
        equal(count(), 5, 'CmdA from a section header still selects all entries')
        refresh(status, 5)
        equal(count(), 5, 'same-repository refresh preserves selected identities')
        refresh('MM one.lua\0?? new.lua\0', 3)
        equal(count(), 2, 'refresh prunes removed entries and does not auto-select new files')
        equal([entry['path'] for entry in selected()], ['one.lua','one.lua'], 'staged/unstaged identities both survive refresh')
        lua('_G.git_select_root=vim.uv.cwd().."/alternate";return true')
        refresh('MM one.lua\0?? new.lua\0', 3)
        equal(count(), 0, 'different repository cannot inherit prior selection')
        raw(editor, variants[0][1])
        lua('_G.git_select_root_code=128;require("jetvim.git").refresh();return true')
        editor.wait('return next(require("jetvim.git").rows)==nil')
        raw(editor, variants[0][1])
        equal(count(), 0, 'non-repository CmdA is a safe no-op')
        equal(marks(), [], 'non-repository clears stale decorations')
        lua('_G.git_select_root_code=0;_G.git_select_root=vim.uv.cwd();return true')
        refresh('', 0);raw(editor, variants[1][1])
        equal(count(), 0, 'clean repository CmdA selects no headers or status messages')
        refresh(status, 5);raw(editor, variants[0][1])
        lua('_G.git_select_status_code=128;require("jetvim.git").refresh();return true')
        editor.wait('return next(require("jetvim.git").rows)==nil')
        equal(count(), 0, 'failed status refresh clears selection')
        equal(marks(), [], 'failed status refresh clears selection decorations')
        lua('_G.git_select_status_code=0;return true')
        refresh(status, 5);raw(editor, variants[0][1])
        lua('local executable=vim.fn.executable;vim.fn.executable=function(name,...) '
            'if name=="git" then return 0 end;return executable(name,...) end;'
            'require("jetvim.git").refresh();vim.fn.executable=executable;return true')
        equal(count(), 0, 'missing Git clears selection safely')
        equal(marks(), [], 'missing Git clears selection decorations')
        refresh(status, 5)
        lua('local g=require("jetvim.git");for row,e in pairs(g.rows) do if e.path=="one.lua" and e.section=="Staged Changes" then '
            'vim.api.nvim_win_set_cursor(g.list_win,{row,0});break end end;return true')
        raw(editor, variants[0][1])
        editor.keys('<Tab>')
        raw(editor, variants[0][1])
        equal(lua('return vim.fn.mode()'), 's', 'CmdA in diff keeps normal read-only text selection')
        equal(count(), 5, 'diff text selection does not change list multiselection')
        raw(editor, b'\x1b[27u');editor.keys('<S-Tab>')
        raw(editor, b'\r')
        editor.wait('return vim.bo.buftype==""')
        equal(lua('return vim.api.nvim_buf_get_name(0)'), str(project/'one.lua'), 'Enter opens only focused change')
        equal(lua('return vim.fn.bufnr(' + quote(str(project/odd)) + ')'), -1, 'Enter does not bulk-open other selected files')
        equal(lua('return vim.fn.bufnr(' + quote(str(project/'deleted.lua')) + ')'), -1, 'Enter does not create a buffer for selected deletion')
        raw(editor, b'\x1b[57;9u')
        editor.wait('return vim.bo.filetype=="jetvim-git"')
        raw(editor, variants[0][1]);raw(editor, b'\x1b[57;9u')
        equal(count(), 0, 'hiding panel clears selection')
        raw(editor, b'\x1b[57;9u')
        editor.wait('return vim.bo.filetype=="jetvim-git" and vim.tbl_count(require("jetvim.git").rows)==5')
        equal(count(), 0, 'recreated panel starts without stale selection')
        equal(all((project/name).read_text()=='-- unchanged\n' for name in ('one.lua','conflict.lua','new.lua',odd)),
              True, 'select-all and navigation never write source files')
        equal(lua('return vim.v.errmsg'), '', 'no editor errors')
        print(f'PASS: {support["checks"]} Git select-all PTY checks (all Git commands mocked)')
    finally:
        editor.close()
