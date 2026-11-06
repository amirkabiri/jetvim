#!/usr/bin/env python3
"""LEAD-ONLY: actual Git HEAD baselines and left-side buffer change markers.

Implementation agents must not execute this test. It invokes Git while creating
isolated fixture repositories under the checkout's ignored .jetvim directory.
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
support['ENV'].pop('JETVIM_DISABLE_VCS', None)
support['ENV']['JETVIM_DISABLE_AUTOSAVE'] = '1'
# Measure the gutter provider independently. Blame legitimately starts Git after
# text changes, while filename-cache updates can refresh every gutter baseline.
# Disable those unrelated providers before init installs their jobs/autocmds;
# keep the real gutter and the all-Git process observer below enabled.
GUTTER_INIT = (
    "lua package.preload['jetvim.blame'] = function() return { setup = function() end } end; "
    "package.preload['jetvim.vcs'] = function() return { setup = function() end, "
    "refresh = function() end, status = function() end } end"
)


def marks(editor):
    return editor.lua('local g=require("jetvim.gutter"); local out={}; '
                      'for _,m in ipairs(vim.api.nvim_buf_get_extmarks(0,g.namespace,0,-1,{details=true})) do '
                      'out[#out+1]={row=m[2]+1,group=m[4].sign_hl_group,text=m[4].sign_text} end; '
                      'table.sort(out,function(a,b) if a.row==b.row then return a.group<b.group end; return a.row<b.row end); return out')


def wait_marks(editor, expected):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        actual = {(item['row'], item['group']) for item in marks(editor)}
        if actual == expected:
            equal(actual, expected, 'expected gutter row/color marks')
            return
        time.sleep(0.04)
    equal(actual, expected, 'gutter marks after timeout')


def open_file(editor, path):
    editor.lua('require("jetvim.project").open(' + json.dumps(path, ensure_ascii=False) + '); return true')
    editor.wait('return require("jetvim.gutter").states[vim.api.nvim_get_current_buf()] ~= nil')
    editor.wait('local s=require("jetvim.gutter").states[vim.api.nvim_get_current_buf()]; return s and not s.pending and not s.job')


with tempfile.TemporaryDirectory(prefix='git gutter ', dir=STATE) as folder:
    repo = Path(folder)
    git(repo, 'init', '--initial-branch=main')
    initial = {
        'changed.lua': 'first\nsecond\nthird\nfourth\n',
        'added-lines.lua': 'first\nlast\n',
        'deleted-lines.lua': 'first\nremoved\nlast\n',
        'deleted-eof.lua': 'first\nremoved\n',
        'whole-file.lua': 'removed\n',
        'both.lua': 'original\n',
        ':(literal).lua': 'original\n',
        'overlap.lua': 'one\ntwo\nthree\n',
        'blank.lua': '\n',
        'empty.lua': '',
        '.gitignore': 'ignored.lua\n',
    }
    for name, text in initial.items():
        (repo / name).write_text(text)
    (repo / 'binary.dat').write_bytes(b'a\0b\n')
    git(repo, 'add', '--all')
    git(repo, 'commit', '-m', 'Git gutter HEAD fixture')
    (repo / 'changed.lua').write_text('first\nchanged\nthird\nfourth\n')
    (repo / 'added-lines.lua').write_text('first\nadded\nlast\n')
    (repo / 'deleted-lines.lua').write_text('first\nlast\n')
    (repo / 'deleted-eof.lua').write_text('first\n')
    (repo / 'whole-file.lua').write_text('')
    (repo / 'both.lua').write_text('staged\n')
    git(repo, 'add', '--', 'both.lua')
    (repo / 'both.lua').write_text('working\n')
    (repo / 'new file.lua').write_text('new one\nnew two\n')
    (repo / 'ignored.lua').write_text('ignored\n')
    (repo / ':(literal).lua').write_text('literal changed\n')
    (repo / 'overlap.lua').write_text('changed\n')
    (repo / 'binary.dat').write_bytes(b'a\0changed\n')
    index = (repo / '.git/index').read_bytes()
    baseline = {str(path.relative_to(repo)): path.read_bytes() for path in repo.rglob('*') if path.is_file() and '.git' not in path.parts}
    editor = Editor(repo, 'changed.lua', pre_init=GUTTER_INIT)
    try:
        equal(editor.lua('return {vim.fn.exists("#JetvimBlame"),vim.fn.exists("#JetvimVcs"),vim.fn.exists("#JetvimGitGutter")}'),
              [0, 0, 1], 'only the gutter provider installs Git refreshes in this fixture')
        editor.wait('local s=require("jetvim.gutter").states[vim.api.nvim_get_current_buf()]; return s and not s.pending and not s.job')
        wait_marks(editor, {(2, 'JetvimGutterModified')})
        equal(editor.lua('return vim.wo.signcolumn'), 'yes:3', 'left gutter has three stable sign slots')
        equal(editor.lua('return vim.api.nvim_get_hl(0,{name="JetvimGutterModified",link=false}).fg'), 0x6C95EB, 'modified line is blue')
        # The actual status-column string is rendered left of the line number.
        gutter = editor.lua('return vim.api.nvim_eval_statusline("%s%l", {winid=vim.api.nvim_get_current_win(),use_statuscol_lnum=2,highlights=true})')
        equal(gutter['str'].find('▎') < gutter['str'].find('2'), True, 'change bar appears before line number')
        current = marks(editor)[0]
        equal(current['text'].strip(), '▎', 'left marker glyph is a bar')
        open_file(editor, 'blank.lua')
        wait_marks(editor, set())
        open_file(editor, 'empty.lua')
        wait_marks(editor, set())
        open_file(editor, 'added-lines.lua')
        wait_marks(editor, {(2, 'JetvimGutterAdded')})
        equal(editor.lua('return vim.api.nvim_get_hl(0,{name="JetvimGutterAdded",link=false}).fg'), 0x6AAB73, 'added line is green')
        open_file(editor, 'deleted-lines.lua')
        wait_marks(editor, {(1, 'JetvimGutterDeleted')})
        equal(editor.lua('return vim.api.nvim_get_hl(0,{name="JetvimGutterDeleted",link=false}).fg'), 0xE06C75, 'removed line anchor is red')
        open_file(editor, 'deleted-eof.lua')
        wait_marks(editor, {(1, 'JetvimGutterDeleted')})
        open_file(editor, 'whole-file.lua')
        wait_marks(editor, {(1, 'JetvimGutterDeleted')})
        open_file(editor, 'both.lua')
        wait_marks(editor, {(1, 'JetvimGutterModified')})
        equal(editor.lua('return require("jetvim.gutter").states[vim.api.nvim_get_current_buf()].baseline'), 'original\n', 'staged and unstaged compare net content against HEAD')
        open_file(editor, 'new file.lua')
        wait_marks(editor, {(1, 'JetvimGutterAdded'), (2, 'JetvimGutterAdded')})
        open_file(editor, 'ignored.lua')
        editor.wait('local s=require("jetvim.gutter").states[vim.api.nvim_get_current_buf()]; return s and not s.job')
        time.sleep(0.25)
        equal(marks(editor), [], 'ignored file has no markers')
        open_file(editor, 'binary.dat')
        editor.wait('local s=require("jetvim.gutter").states[vim.api.nvim_get_current_buf()]; return s and not s.job')
        time.sleep(0.25)
        equal(marks(editor), [], 'binary file has no misleading text markers')
        open_file(editor, ':(literal).lua')
        wait_marks(editor, {(1, 'JetvimGutterModified')})
        open_file(editor, 'overlap.lua')
        wait_marks(editor, {(1, 'JetvimGutterModified'), (1, 'JetvimGutterDeleted')})
        editor.lua('local ns=vim.api.nvim_create_namespace("JetvimGutterFixtureDiagnostic"); '
                   'vim.api.nvim_buf_set_extmark(0,ns,0,0,{sign_text="E",sign_hl_group="DiagnosticError",priority=10}); return true')
        signs = editor.lua('return vim.api.nvim_eval_statusline("%s",{winid=vim.api.nvim_get_current_win(),use_statuscol_lnum=1,highlights=true}).str')
        for glyph in ('▎', '▸', 'E'):
            equal(glyph in signs, True, 'overlapping Git/diagnostic gutter glyph remains visible: ' + glyph)
        open_file(editor, 'changed.lua')
        wait_marks(editor, {(2, 'JetvimGutterModified')})
        # No disk write: editing only uses the already cached HEAD blob.
        editor.lua('vim.g.gutter_fixture_calls=0; _G.gutter_fixture_system=vim.system; '
                   'vim.system=function(argv,...) if argv[1]=="git" then vim.g.gutter_fixture_calls=vim.g.gutter_fixture_calls+1 end; return _G.gutter_fixture_system(argv,...) end; '
                   'vim.api.nvim_buf_set_lines(0,0,-1,false,{"first","second","third","fourth"}); require("jetvim.gutter").changed(); return true')
        wait_marks(editor, set())
        editor.lua('vim.api.nvim_buf_set_lines(0,2,2,false,{"unsaved added"}); require("jetvim.gutter").changed(); '
                   'vim.g.gutter_fixture_observed=false; '
                   'vim.defer_fn(function() vim.g.gutter_fixture_observed=true end,350); return true')
        wait_marks(editor, {(3, 'JetvimGutterAdded')})
        # Let the editor process both cached redraw and any accidentally queued
        # baseline-fetch timers before reading the spy. Host scheduling cannot
        # shorten this observation window.
        editor.wait('return vim.g.gutter_fixture_observed == true')
        equal(editor.lua('return vim.bo.modified'), True, 'unsaved edits included')
        equal(editor.lua('return vim.g.gutter_fixture_calls'), 0, 'typing does not start Git subprocesses')
        editor.lua('vim.system=_G.gutter_fixture_system; return true')
        equal(editor.lua('return vim.v.errmsg'), '', 'no Git gutter editor errors')
    finally:
        editor.close()
    equal((repo / '.git/index').read_bytes(), index, 'gutter reads never change Git index')
    equal({str(path.relative_to(repo)): path.read_bytes() for path in repo.rglob('*') if path.is_file() and '.git' not in path.parts}, baseline, 'gutter never writes working files')

with tempfile.TemporaryDirectory(prefix='gutter nonrepo ', dir=STATE) as folder:
    project = Path(folder)
    (project / 'plain.lua').write_text('plain\n')
    editor = Editor(project, 'plain.lua', pre_init=GUTTER_INIT)
    try:
        time.sleep(0.5)
        equal(marks(editor), [], 'non-repository file has no markers')
        equal(editor.lua('return vim.v.errmsg'), '', 'non-repository gutter has no errors')
    finally:
        editor.close()
print(f'PASS: {support["checks"]} real Git gutter checks (lead-executed only)')
