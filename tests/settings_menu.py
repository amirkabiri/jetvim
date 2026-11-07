#!/usr/bin/env python3
"""Sectioned settings chooser through native/relay keys and actual popup rows."""
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import struct
import tempfile
import termios

ROOT = Path(__file__).resolve().parent.parent
support = {'__file__': str(ROOT / 'tests/autosave.py')}
exec((ROOT / 'tests/autosave.py').read_text().split('\nwith tempfile.TemporaryDirectory', 1)[0], support)
Editor, equal, STATE = support['Editor'], support['equal'], support['STATE']

with tempfile.TemporaryDirectory(prefix='settings-menu-', dir=STATE) as directory:
    base = Path(directory)
    code = base / 'code with spaces'; code.mkdir()
    for name in ('jetvim', 'init.lua'):
        shutil.copy2(ROOT / name, code / name)
    for name in ('config', 'lua'):
        shutil.copytree(ROOT / name, code / name)
    support['ROOT'] = code
    project = base / 'project with spaces'; project.mkdir()
    (project / 'main.lua').write_text('-- main\n')
    home = base / 'home'; home.mkdir()
    user = home / 'settings.lua'
    appearance = code / 'config/appearance.lua'
    appearance_original = appearance.read_text()
    editor = Editor(project, user, disabled=True, disable_lsp=True)
    lua = editor.lua
    bindings = json.loads((code / 'config/keymap.json').read_text())
    index = next(i for i, item in enumerate(bindings, 1) if item['id'] == 'settings')
    native = b'\x1b[44;9u'
    relay = f'\x1b[{0xF0000 + index}u'.encode()
    def open_menu(chord=native):
        editor.raw(chord)
        editor.wait('return vim.bo.buftype=="prompt"')
    def display():
        return lua('for _,w in ipairs(vim.api.nvim_list_wins()) do local c=vim.api.nvim_win_get_config(w);'
                   'local b=vim.api.nvim_win_get_buf(w);if c.relative~="" and vim.bo[b].buftype~="prompt" then '
                   'local selected={};for _,m in ipairs(vim.api.nvim_buf_get_extmarks(b,vim.api.nvim_get_namespaces().JetvimPickerAppearance,0,-1,{details=true})) do '
                   'if m[4].line_hl_group=="JetvimPickerSelected" then selected[#selected+1]=m[2]+1 end end;'
                   'return {lines=vim.api.nvim_buf_get_lines(b,0,-1,false),selected=selected,height=vim.api.nvim_win_get_height(w)} end end;return nil')
    def selected_label():
        state = display()
        equal(len(state['selected']), 1, 'exactly one actionable item is highlighted')
        return state['lines'][state['selected'][0] - 1].strip()
    def wait_path(path, typing=True):
        editor.wait('return vim.api.nvim_buf_get_name(0)=='+json.dumps(str(path)))
        if typing:
            editor.wait('return vim.fn.mode()=="i"')
            equal(lua('return vim.fn.mode()'), 'i', 'configuration opens in typing mode')
    def resize(rows):
        fcntl.ioctl(editor.master, termios.TIOCSWINSZ, struct.pack('HHHH', rows, 140, 0, 0))
        os.kill(editor.process.pid, signal.SIGWINCH)
        editor.wait('return vim.o.lines=='+str(rows))
    try:
        baseline = lua('return #vim.api.nvim_list_wins()')
        open_menu()
        lines = display()['lines']
        equal([line.strip() for line in lines], [
            '──── Project ────', '› Project settings', '──── User ────',
            'User settings', 'Appearance', 'LSP'], 'project-first settings order and divider rows')
        equal(display()['selected'], [2], 'default selection is Project settings, never its heading')
        editor.raw(b'\x1b[B')
        equal(selected_label(), '› User settings', 'Down skips User divider')
        editor.raw(b'\x1b[A\x1b[A')
        equal(selected_label(), '› Project settings', 'Up skips headings and clamps at first item')
        editor.raw(b'\r')
        project_settings = project / '.idea/jetvim/settings.lua'
        wait_path(project_settings)
        equal(lua('return vim.tbl_count(dofile('+json.dumps(str(project_settings))+'))'), 0, 'default project choice creates empty overrides')
        equal(user.exists(), False, 'choosing project does not create global preferences')
        equal(lua('return #vim.api.nvim_list_wins()'), baseline, 'choosing closes both popup windows')
        open_menu(relay)
        editor.raw(b'User settings\r')
        wait_path(user)
        equal(user.read_text(), (code / 'config/settings.lua').read_text(), 'User settings opens user file from installed defaults')
        original_user = user.read_text()
        open_menu()
        editor.raw(b'Appearance')
        equal([line.strip() for line in display()['lines']], ['──── User ────', '› Appearance'], 'filter hides empty Project section and matches only item labels')
        editor.raw(b'\r')
        wait_path(appearance)
        expected = appearance_original + '-- fixture config save\n'
        lua('vim.api.nvim_buf_set_lines(0,-1,-1,false,{"-- fixture config save"});return true')
        editor.raw(b'\x1b[115;9u')
        editor.disk(appearance, expected)
        equal((ROOT / 'config/appearance.lua').read_text(), appearance_original, 'tool editing is confined to copied source root')
        open_menu(relay)
        editor.raw(b'\x1b[B' * 3)
        equal(selected_label(), '› LSP', 'arrow navigation reaches last user item')
        editor.raw(b'\x1b[B\r')
        wait_path(code / 'config/lsp.lua')
        equal(user.read_text(), original_user, 'Appearance and LSP opening do not replace global settings')
        # Filtering both scopes keeps the configured section order.
        open_menu()
        editor.raw(b'settings')
        equal([line.strip() for line in display()['lines']], ['──── Project ────', '› Project settings', '──── User ────', 'User settings'], 'filter preserves scope order')
        editor.raw(b'\x1b[27u')
        wait_path(code / 'config/lsp.lua', typing=False)
        equal(lua('return #vim.api.nvim_list_wins()'), baseline, 'Escape restores origin without leaked windows')
        open_menu()
        editor.raw(b'no-match-here')
        equal(display()['lines'], ['   No matches'], 'unmatched query has no orphan headings')
        equal(display()['selected'], [], 'empty query results have no selectable divider')
        editor.raw(b'\r')
        wait_path(code / 'config/lsp.lua', typing=False)
        # Four visible result rows are fewer than the six display rows. Selection
        # must remain visible while crossing dividers and reaching the last item.
        resize(14)
        open_menu(relay)
        equal(display()['height'], 4, 'small terminal gives four-row list viewport')
        editor.raw(b'\x1b[B' * 3)
        equal(selected_label(), '› LSP', 'small viewport scrolls selected item into view')
        equal(any('User' in line and '────' in line for line in display()['lines']), True, 'visible user group retains divider')
        editor.raw(b'\x1b[A' * 3)
        equal(selected_label(), '› Project settings', 'small viewport returns to first selectable item')
        editor.raw(b'\x1b[27u')
        resize(35)
        equal(lua('return vim.v.errmsg'), '', 'settings chooser leaves no editor errors')
        print(f'PASS: {support["checks"]} grouped settings-menu terminal checks')
    finally:
        editor.close()
