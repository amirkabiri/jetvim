#!/usr/bin/env python3
"""LEAD-ONLY: real Git cache plus rendered filename colors. Never run as an agent.

Uses the reviewed Git fixture helpers without executing their top-level test suite.
All fixture writes remain inside this checkout's ignored .jetvim directory.
"""
import hashlib
import json
from pathlib import Path
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
support = {'__file__': str(ROOT / 'tests/git_changes.py')}
exec((ROOT / 'tests/git_changes.py').read_text().split('\nwith tempfile.TemporaryDirectory', 1)[0], support)
Editor, git, equal = support['Editor'], support['git'], support['equal']
STATE = support['STATE']
# This is explicitly a real-Git test; normal agent-run UI tests use the opt-out.
support['ENV'].pop('JETVIM_DISABLE_VCS', None)
# This fixture exercises filename-cache rendering, not independent blame/gutter
# providers. Disable only their setup before init creates any timers/autocmds;
# otherwise a queued blame refresh can be counted as render-triggered Git.
# Keep real VCS setup and delayed process observation enabled below.
FILENAME_CACHE_INIT = (
    "lua for _, name in ipairs({'jetvim.blame', 'jetvim.gutter'}) do "
    "package.preload[name] = function() return { setup = function() end } end end"
)


def lookup(editor, path):
    return editor.lua('return require("jetvim.vcs").status(' + json.dumps(str(path), ensure_ascii=False) + ')')


def tree_marks(editor, path):
    return editor.lua('local t=require("jetvim.tree"); '
                      'for row,e in pairs(t.rows) do if e.path==' + json.dumps(str(path), ensure_ascii=False) + ' then '
                      'local result={name=e.name,column=e.column}; '
                      'for _,m in ipairs(vim.api.nvim_buf_get_extmarks(t.buf,vim.api.nvim_get_namespaces().JetvimTreeDecorations,{row-1,0},{row-1,-1},{details=true})) do '
                      'local d=m[4]; if m[3]==e.column and d.end_col==e.column+#e.name then result.name_group=d.hl_group '
                      'elseif m[3]<e.column and d.end_col<=e.column and d.hl_group:match("^JetvimIcon") then result.icon_group=d.hl_group end end; '
                      'return result end end; return nil')


def tab_group(editor, filename):
    evaluated = editor.lua('return vim.api.nvim_eval_statusline(vim.o.tabline,{use_tabline=true,maxwidth=vim.o.columns,highlights=true})')
    offset = evaluated['str'].encode().find(filename.encode())
    assert offset >= 0, 'Tab filename missing: ' + filename
    segments = [mark for mark in evaluated['highlights'] if mark['start'] <= offset]
    return segments[-1]['group'], evaluated


with tempfile.TemporaryDirectory(prefix='vcs colors ', dir=STATE) as folder:
    repo = Path(folder)
    git(repo, 'init', '--initial-branch=main')
    for filename in ('modified.lua', 'clean.lua', 'deleted.lua', ':(literal).lua'):
        (repo / filename).write_text('-- original\n')
    (repo / 'nested').mkdir()
    (repo / 'nested/inside.lua').write_text('-- nested original\n')
    git(repo, 'add', '--all')
    git(repo, 'commit', '-m', 'VCS color fixture')
    (repo / 'modified.lua').write_text('-- changed\n')
    (repo / ':(literal).lua').write_text('-- magic changed\n')
    (repo / 'nested/inside.lua').write_text('-- nested changed\n')
    (repo / 'deleted.lua').unlink()
    (repo / 'untracked.lua').write_text('-- untracked\n')
    (repo / 'added.lua').write_text('-- staged\n')
    git(repo, 'add', '--', 'added.lua')
    index_before = hashlib.sha256((repo / '.git/index').read_bytes()).hexdigest()
    editor = Editor(repo, 'modified.lua', pre_init=FILENAME_CACHE_INIT)
    try:
        equal(editor.lua('return {vim.fn.exists("#JetvimBlame"),vim.fn.exists("#JetvimGitGutter")}'),
              [0, 0], 'unrelated Git providers never install background refreshes in filename fixture')
        editor.wait('return require("jetvim.vcs").status(vim.uv.cwd().."/modified.lua")=="modified"')
        equal(lookup(editor, repo / 'modified.lua'), 'modified', 'tracked modification cached')
        equal(lookup(editor, repo / 'untracked.lua'), 'untracked', 'untracked filename cached')
        equal(lookup(editor, repo / 'added.lua'), 'added', 'staged addition cached')
        equal(lookup(editor, repo / 'deleted.lua'), 'deleted', 'deleted filename cached')
        equal(lookup(editor, repo / 'clean.lua'), None, 'clean tracked file has normal status')
        equal(lookup(editor, repo / ':(literal).lua'), 'modified', 'literal pathspec-like filename cached')
        editor.lua('vim.cmd.badd("untracked.lua"); require("jetvim.tree").render(); return true')
        for filename, status, color in (('modified.lua', 'Modified', 0x6C95EB), ('untracked.lua', 'Untracked', 0xE06C75)):
            marks = tree_marks(editor, repo / filename)
            equal(marks['name_group'], 'JetvimFile' + status, filename + ' tree filename uses VCS group')
            equal(marks['icon_group'], 'JetvimIconLua', filename + ' tree icon retains filetype group')
            equal(editor.lua('return vim.api.nvim_get_hl(0,{name=' + json.dumps(marks['name_group']) + ',link=false}).fg'), color, filename + ' actual tree foreground')
            group, evaluated = tab_group(editor, filename)
            equal(group.startswith('JetvimFile' + status), True, filename + ' tab filename has VCS segment')
            equal(editor.lua('return vim.api.nvim_get_hl(0,{name=' + json.dumps(group) + ',link=false}).fg'), color, filename + ' actual tab foreground')
            equal(any(mark['group'].startswith('JetvimIconLua') for mark in evaluated['highlights']), True, 'tab icons retain filetype segments')
        # Rendering reads the cache. It must not schedule more Git subprocesses.
        editor.lua('vim.g.vcs_render_jobs=0; _G.JetvimVcsOriginalSystem=vim.system; '
                   'vim.system=function(cmd,...) if cmd[1]=="git" then vim.g.vcs_render_jobs=vim.g.vcs_render_jobs+1 end; return _G.JetvimVcsOriginalSystem(cmd,...) end; '
                   'for i=1,100 do require("jetvim.vcs").status(vim.uv.cwd().."/modified.lua"); require("jetvim.theme").tabs(); require("jetvim.tree").render() end; return true')
        time.sleep(0.35)
        equal(editor.lua('local count=vim.g.vcs_render_jobs; vim.system=_G.JetvimVcsOriginalSystem; return count'), 0, 'cache reads and redraws never spawn Git')
        # Saving causes a real status refresh and re-colors an edited clean file.
        editor.lua('require("jetvim.project").open("clean.lua"); vim.api.nvim_buf_set_lines(0,0,-1,false,{"-- saved change"}); vim.cmd.write(); return true')
        editor.wait('return require("jetvim.vcs").status(vim.uv.cwd().."/clean.lua")=="modified"')
        equal(tree_marks(editor, repo / 'clean.lua')['name_group'], 'JetvimFileModified', 'save refresh re-colors tree filename')
        equal(tab_group(editor, 'clean.lua')[0].startswith('JetvimFileModified'), True, 'save refresh re-colors editor tab')
        equal(editor.lua('return vim.v.errmsg'), '', 'no provider or renderer errors')
    finally:
        editor.close()
    equal(hashlib.sha256((repo / '.git/index').read_bytes()).hexdigest(), index_before, 'automatic status does not change index')
    editor = Editor(repo / 'nested', 'inside.lua', pre_init=FILENAME_CACHE_INIT)
    try:
        editor.wait('return require("jetvim.vcs").status(vim.uv.cwd().."/inside.lua")=="modified"')
        equal(lookup(editor, repo / 'modified.lua'), None, 'status cache excludes files outside selected project')
        equal(lookup(editor, repo / 'nested/inside.lua'), 'modified', 'nested project finds repository-relative paths')
        equal(tree_marks(editor, repo / 'nested/inside.lua')['name_group'], 'JetvimFileModified', 'nested project tree gets blue filename')
    finally:
        editor.close()
print(f'PASS: {support["checks"]} real Git filename-color checks (lead-executed only)')
