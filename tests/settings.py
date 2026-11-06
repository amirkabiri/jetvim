#!/usr/bin/env python3
"""Layered Lua settings, explicit project trust and CmdComma scope selection."""
import json
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parent.parent
support = {'__file__': str(ROOT / 'tests/autosave.py')}
exec((ROOT / 'tests/autosave.py').read_text().split('\nwith tempfile.TemporaryDirectory', 1)[0], support)
Editor, equal, STATE = support['Editor'], support['equal'], support['STATE']


def effective(editor):
    return editor.lua('return require("jetvim.settings").get().autosave')


def write_code(editor, lines):
    payload = json.dumps(json.dumps(lines))
    editor.lua('vim.api.nvim_buf_set_lines(0,0,-1,false,vim.json.decode(' + payload + ')); vim.cmd.write(); return true')


with tempfile.TemporaryDirectory(prefix='layered-settings-', dir=STATE) as directory:
    base = Path(directory)
    home = base / 'home'
    home.mkdir()
    user = home / 'settings.lua'
    project_a, project_b = base / 'project-a', base / 'project-b'
    for project in (project_a, project_b):
        project.mkdir()
        (project / 'main.lua').write_text('-- main\n')
    editor = Editor(project_a, user, disabled=True)
    try:
        defaults = editor.lua('return dofile(vim.env.JETVIM_ROOT.."/config/settings.lua").autosave')
        equal(effective(editor), defaults, 'missing global file inherits installed defaults')
        equal(editor.lua('return require("jetvim.settings").get().git.blame'), {'enabled': True, 'mode': 'current_line'}, 'inline Git blame enabled by default')
        equal(user.exists(), False, 'startup does not create global settings')
        editor.settings()
        equal(user.read_text(), (ROOT / 'config/settings.lua').read_text(), 'user scope creates missing global from defaults once')
        equal(editor.lua('return vim.api.nvim_buf_get_name(0)'), str(user), 'native scope chooser opens user code')
        write_code(editor, ['-- User preferences retained', 'return {autosave={enabled=true,delay_ms=1000}}'])
        equal(effective(editor), {'enabled': True, 'debounce': True, 'delay_ms': 1000, 'on_focus_lost': True}, 'global settings applied')
        original = user.read_text()
        editor.settings(relay=True)
        equal(user.read_text(), original, 'reopening user settings never overwrites existing code')
        editor.settings(scope='Project settings')
        project_settings = project_a / '.idea/jetvim/settings.lua'
        equal(editor.lua('return vim.api.nvim_buf_get_name(0)'), str(project_settings), 'project scope opens project Lua file')
        equal('enabled' in project_settings.read_text() or 'delay_ms' in project_settings.read_text(), False, 'new project config contains no copied defaults')
        equal(editor.lua('return vim.tbl_count(dofile(require("jetvim.project").root.."/.idea/jetvim/settings.lua"))'), 0, 'new project config is empty overrides')
        equal(editor.lua('return require("jetvim.settings").is_trusted()'), True, 'intentionally created empty project config is trusted')
        write_code(editor, ['return {autosave={enabled=false}}'])
        equal(effective(editor), {'enabled': False, 'debounce': True, 'delay_ms': 1000, 'on_focus_lost': True}, 'sparse project enabled override inherits global delay')
        write_code(editor, ['return {autosave={debounce=false,on_focus_lost=false}}'])
        equal(effective(editor), {'enabled': True, 'debounce': False, 'delay_ms': 1000, 'on_focus_lost': False}, 'project overrides each autosave trigger independently')
        write_code(editor, ['return {autosave={enabled=false}}'])
        editor.settings()
        write_code(editor, ['-- User comments stay', 'return {autosave={enabled=true,delay_ms=1600}}'])
        equal(effective(editor), {'enabled': False, 'debounce': True, 'delay_ms': 1600, 'on_focus_lost': True}, 'global delay changes without re-enabling project autosave')
        editor.settings(scope='Project settings')
        write_code(editor, ['return {autosave={delay_ms=20}}'])
        equal(effective(editor), {'enabled': False, 'debounce': True, 'delay_ms': 1600, 'on_focus_lost': True}, 'invalid sparse project settings retain last good values')
        write_code(editor, ['return {autosave='])
        equal(effective(editor), {'enabled': False, 'debounce': True, 'delay_ms': 1600, 'on_focus_lost': True}, 'project syntax errors retain last good values')
        write_code(editor, ['return {autosave={enabled=false}}'])
        # Lua functions remain functions, and a project hook list replaces the
        # complete global list rather than merging numeric array positions.
        editor.settings()
        write_code(editor, [
            'return {autosave={enabled=true,delay_ms=1600},',
            ' hooks={after_save={',
            '  {pattern="^NEVER_MATCH$",callback=function() return "global-one" end},',
            '  {pattern="^NEVER_MATCH$",callback=function() return "global-two" end},',
            ' }}, git={blame={enabled=false,mode="all"}}}',
        ])
        equal(editor.lua('return require("jetvim.settings").get().hooks.after_save[2].callback()'), 'global-two', 'Lua callback values are preserved')
        editor.settings(scope='Project settings')
        write_code(editor, ['return {autosave={enabled=false},hooks={after_save={{pattern="^NEVER_MATCH$",callback=function() return "project" end}}},git={blame={enabled=true}}}'])
        equal(editor.lua('return #require("jetvim.settings").get().hooks.after_save'), 1, 'project hook list replaces full global list')
        equal(editor.lua('return require("jetvim.settings").get().hooks.after_save[1].callback()'), 'project', 'project callback replaces global callback')
        equal(editor.lua('return require("jetvim.settings").get().git.blame'), {'enabled': True, 'mode': 'all'}, 'sparse blame settings inherit global mode')
        write_code(editor, ['return {autosave={enabled=false},hooks={after_save={}}}'])
        equal(editor.lua('return #require("jetvim.settings").get().hooks.after_save'), 0, 'explicit empty hook list clears inherited hooks')
        equal(json.loads((home / 'trusted-projects.json').read_text())['projects'][str(project_a.resolve())], True, 'trust persisted by real project path')
    finally:
        editor.close()
    editor = Editor(project_a, user, disabled=True)
    try:
        equal(effective(editor), {'enabled': False, 'debounce': True, 'delay_ms': 1600, 'on_focus_lost': True}, 'project trust and sparse overrides survive relaunch')
        equal(editor.lua('return #require("jetvim.settings").get().hooks.after_save'), 0, 'empty project hook override survives relaunch')
    finally:
        editor.close()
    marker = project_b / 'executed.txt'
    b_settings = project_b / '.idea/jetvim/settings.lua'
    b_settings.parent.mkdir(parents=True)
    b_settings.write_text('vim.fn.writefile({"executed"}, ' + json.dumps(str(marker)) + ')\nreturn {autosave={enabled=false}}\n')
    editor = Editor(project_b, user, disabled=True)
    try:
        equal(marker.exists(), False, 'untrusted project Lua is not executed at startup')
        equal(effective(editor), {'enabled': True, 'debounce': True, 'delay_ms': 1600, 'on_focus_lost': True}, 'another project inherits user preferences')
        original = b_settings.read_text()
        editor.settings(relay=True, scope='Project settings')
        equal(b_settings.read_text(), original, 'opening existing project settings preserves its code')
        equal(marker.exists(), False, 'opening existing project settings does not grant trust or execute code')
        equal(editor.lua('return require("jetvim.settings").is_trusted()'), False, 'existing unfamiliar project remains untrusted')
        write_code(editor, original.rstrip('\n').split('\n'))
        equal(marker.exists(), False, 'saving untrusted project code does not execute it')
        editor.lua('vim.cmd("JetvimTrustProject"); return true')
        equal(marker.read_text(), 'executed\n', 'explicit trust command allows project Lua execution')
        equal(effective(editor), {'enabled': False, 'debounce': True, 'delay_ms': 1600, 'on_focus_lost': True}, 'trusted project overrides only its chosen field')
        marker.unlink()
        editor.lua('vim.cmd("JetvimUntrustProject"); return true')
        equal(marker.exists(), False, 'revocation never executes project Lua')
        equal(effective(editor), {'enabled': True, 'debounce': True, 'delay_ms': 1600, 'on_focus_lost': True}, 'revocation restores user settings')
        editor.lua('vim.cmd("JetvimReloadSettings"); return true')
        equal(marker.exists(), False, 'reload after revocation never executes project Lua')
        equal(str(project_b.resolve()) in json.loads((home / 'trusted-projects.json').read_text())['projects'], False, 'revocation persisted')
        equal(editor.lua('return vim.v.errmsg'), '', 'layering and trust have no editor errors')
    finally:
        editor.close()
    editor = Editor(project_b, user, disabled=True)
    try:
        equal(marker.exists(), False, 'revoked project remains untrusted after relaunch')
        equal(effective(editor), {'enabled': True, 'debounce': True, 'delay_ms': 1600, 'on_focus_lost': True}, 'revoked project inherits global after relaunch')
    finally:
        editor.close()
print(f'PASS: {support["checks"]} layered Lua settings and project-trust checks through real PTY input')
