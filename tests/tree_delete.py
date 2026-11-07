#!/usr/bin/env python3
"""Contextual tree deletion via actual native/relay terminal input; no Git."""
import json
import os
from pathlib import Path
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
support = {'__file__': str(ROOT / 'tests/autosave.py')}
exec((ROOT / 'tests/autosave.py').read_text().split('\nwith tempfile.TemporaryDirectory', 1)[0], support)
Editor, equal, STATE = support['Editor'], support['equal'], support['STATE']

with tempfile.TemporaryDirectory(prefix='delete-', dir=STATE) as directory:
    project = Path(directory)
    (project / 'home').mkdir()
    preferences = project / 'home/settings.lua'
    preferences.write_text('return {autosave={enabled=true,debounce=false,on_focus_lost=false}}\n')
    (project / 'main.lua').write_text('first\nsecond\n')
    editor = Editor(project, preferences, disable_lsp=True)
    bindings = json.loads((ROOT / 'config/keymap.json').read_text())
    index = next(i for i, item in enumerate(bindings, 1) if item['id'] == 'delete_line')
    relay = f'\x1b[{0xF0000 + index}u'.encode()
    native = b'\x1b[127;9u'
    forward = b'\x1b[3;9~'
    def lua(code): return editor.lua(code)
    def choose(path):
        editor.raw(b'\x1b[27u')
        found = lua('local t=require("jetvim.tree"); t.focus(); '
                    'local parent=vim.fs.dirname(' + json.dumps(str(path)) + '); '
                    'while parent and require("jetvim.project").resolve(parent) do t.expanded[parent]=true; '
                    'if parent==require("jetvim.project").root then break end;parent=vim.fs.dirname(parent) end; '
                    't.clear_search();t.render();for row,e in pairs(t.rows) do if e.path==' + json.dumps(str(path)) + ' then '
                    'vim.api.nvim_win_set_cursor(t.win,{row,0});return true end end;return false')
        equal(found, True, 'selected deletion entry is visible')
    def stub(choice=1, body=''):
        lua('vim.fn.confirm=function(prompt,buttons,default) '
            'vim.g.delete_prompt=prompt;vim.g.delete_buttons=buttons;vim.g.delete_default=default;' + body +
            ' return ' + str(choice) + ' end;return true')
    def remove(path, chord=relay):
        choose(path); stub(); editor.raw(chord)
    def open_buffer(path):
        lua('require("jetvim.project").open(' + json.dumps(str(path)) + ');return true')
        return lua('return vim.api.nvim_get_current_buf()')
    def wait_prompt(chord):
        start = len(editor.output)
        os.write(editor.master, chord)
        deadline = time.monotonic() + 5
        while b'Permanently delete' not in editor.output[start:]:
            assert time.monotonic() < deadline, 'native deletion confirmation missing'
            time.sleep(.02)
    try:
        lua('_G.delete_original_confirm=vim.fn.confirm;vim.g.delete_messages={};'
            'vim.notify=function(text) table.insert(vim.g.delete_messages,text) end;return true')
        # A genuine terminal confirmation defaults to Cancel; both choices work.
        file = project / 'cancel me.txt'; file.write_text('keep\n')
        choose(file); wait_prompt(native); editor.raw('c')
        equal(file.read_text(), 'keep\n', 'native cancel preserves file')
        equal(lua('return vim.bo.filetype'), 'jetvim-tree', 'cancel retains sidebar focus')
        wait_prompt(native); editor.raw('d')
        equal(file.exists(), False, 'native Command Backspace confirms file deletion')
        equal(lua('return vim.bo.filetype'), 'jetvim-tree', 'successful deletion retains sidebar focus')
        equal(lua('local t=require("jetvim.tree");return t.rows[vim.api.nvim_win_get_cursor(t.win)[1]]~=nil'), True, 'selection remains on an existing tree entry')
        file = project / 'relay-confirm.txt'; file.write_text('relay\n')
        choose(file); wait_prompt(relay); editor.raw('d')
        equal(file.exists(), False, 'bridge relay opens real deletion confirmation')
        # The equivalent bridge relay keeps the original action index.
        file = project / 'literal ; $(data).txt'; file.write_text('literal\n')
        remove(file)
        equal(file.exists(), False, 'relay deletes literal filename without shell evaluation')
        equal(lua('return vim.g.delete_default'), 2, 'deletion prompt defaults to cancel')
        equal(lua('return vim.g.delete_prompt:find("cannot be undone",1,true)~=nil'), True, 'permanent deletion is explicit')
        folder = project / 'folder'; (folder / 'child').mkdir(parents=True)
        (folder / 'child/file.txt').write_text('child\n')
        remove(folder, forward)
        equal(folder.exists(), False, 'native Command Forward Delete removes folder recursively')
        equal(lua('return vim.g.delete_prompt:find("all its contents",1,true)~=nil'), True, 'folder confirmation explains recursive deletion')
        # Project root and forged escape entries never even open a confirmation.
        choose(project); lua('vim.g.delete_prompt="unchanged";return true'); editor.raw(native)
        equal(project.exists(), True, 'project root is protected')
        equal(lua('return vim.g.delete_prompt'), 'unchanged', 'root has no destructive confirmation')
        outside = project.parent / ('delete-outside-' + str(os.getpid())); outside.mkdir()
        (outside / 'target.txt').write_text('outside\n')
        try:
            for destination in (outside / 'target.txt', project / 'escape/target.txt'):
                if destination == project / 'escape/target.txt': (project / 'escape').symlink_to(outside, target_is_directory=True)
                choose(project)
                lua('local t=require("jetvim.tree");t.rows[2]={path=' + json.dumps(str(destination)) + '};return true')
                editor.raw(native)
                equal((outside / 'target.txt').read_text(), 'outside\n', 'forged outside/symlink-parent deletion is blocked')
            link = project / 'outside-link'; link.symlink_to(outside, target_is_directory=True)
            remove(link)
            equal(link.is_symlink(), False, 'directory symlink itself is unlinked')
            equal((outside / 'target.txt').read_text(), 'outside\n', 'symlink target remains unchanged')
            folder = project / 'links'; folder.mkdir(); (folder / 'external').symlink_to(outside, target_is_directory=True)
            (folder / 'owned.txt').write_text('owned\n'); remove(folder)
            equal(folder.exists(), False, 'folder with symlink children is deleted')
            equal((outside / 'target.txt').read_text(), 'outside\n', 'recursive deletion never follows child symlinks')
        finally:
            import shutil
            shutil.rmtree(outside)
        target = project / 'target.txt'; target.write_text('target\n')
        target_buf = open_buffer(target)
        link = project / 'inside-link'; link.symlink_to(target)
        remove(link)
        equal(lua('return vim.api.nvim_buf_is_valid(' + str(target_buf) + ')'), True, 'unlinking alias preserves actual target buffer')
        equal(target.read_text(), 'target\n', 'unlinking alias preserves actual target file')
        # Dirty descendants and any active save hook block deletion before prompt.
        folder = project / 'dirty'; folder.mkdir(); child = folder / 'child.lua'; child.write_text('disk\n')
        dirty = open_buffer(child)
        lua('vim.api.nvim_buf_set_lines(0,0,-1,false,{"unsaved"});return true')
        choose(folder); stub(); lua('vim.g.delete_prompt="unchanged";return true'); editor.raw(relay)
        equal(child.read_text(), 'disk\n', 'dirty descendant keeps disk content')
        equal(lua('return vim.api.nvim_buf_get_lines(' + str(dirty) + ',0,-1,false)'), ['unsaved'], 'dirty descendant retains editor text')
        equal(lua('return vim.g.delete_prompt'), 'unchanged', 'dirty buffer blocks deletion before confirmation')
        lua('vim.bo[' + str(dirty) + '].modified=false;vim.b[' + str(dirty) + '].jetvim_hook_running=true;return true')
        editor.raw(native)
        equal(folder.exists(), True, 'active hook flag blocks deletion')
        lua('vim.b[' + str(dirty) + '].jetvim_hook_running=nil;require("jetvim.hooks").states[' + str(dirty) + ']={};return true')
        editor.raw(native)
        equal(folder.exists(), True, 'active hook state also blocks deletion')
        lua('require("jetvim.hooks").states[' + str(dirty) + ']=nil;return true')
        # Revalidate buffer state and filesystem identity after the prompt returns.
        stub(body='vim.api.nvim_buf_set_lines(' + str(dirty) + ',0,-1,false,{"late edit"})')
        editor.raw(native)
        equal(folder.exists(), True, 'late edits during confirmation cancel deletion')
        equal(lua('return vim.b[' + str(dirty) + '].jetvim_closing'), None, 'failed deletion releases autosave protection')
        lua('vim.bo[' + str(dirty) + '].modified=false;return true')
        replaced = project / 'replace.txt'; replaced.write_text('old\n'); choose(replaced)
        stub(body='vim.uv.fs_rename(' + json.dumps(str(replaced)) + ',' + json.dumps(str(project/'replacement-backup')) + ');vim.fn.writefile({"new"},' + json.dumps(str(replaced)) + ')')
        editor.raw(relay)
        equal(replaced.read_text(), 'new\n', 'replacement file created during prompt is not deleted')
        replace_dir = project / 'replace-dir'; replace_dir.mkdir(); (replace_dir / 'file').write_text('owned\n')
        choose(replace_dir)
        stub(body='vim.uv.fs_rename(' + json.dumps(str(replace_dir)) + ',' + json.dumps(str(project/'renamed-dir')) + ');vim.uv.fs_symlink(' + json.dumps(str(project/'dirty')) + ',' + json.dumps(str(replace_dir)) + ')')
        editor.raw(native)
        equal(replace_dir.is_symlink(), True, 'directory replaced by symlink during prompt is not traversed')
        equal(child.exists(), True, 'replacement symlink target survives')
        failed = project / 'failed.txt'; failed.write_text('retain\n'); failed_buf = open_buffer(failed)
        choose(failed); stub(); lua('_G.delete_unlink=vim.uv.fs_unlink;vim.uv.fs_unlink=function()return nil,"fixture denied" end;return true')
        editor.raw(native); lua('vim.uv.fs_unlink=_G.delete_unlink;return true')
        equal(failed.read_text(), 'retain\n', 'filesystem failure preserves file')
        equal(lua('return vim.api.nvim_buf_is_valid(' + str(failed_buf) + ')'), True, 'filesystem failure preserves open buffer')
        # Closing an open clean file preserves editor splits and cannot recreate
        # a deleted path from an already-armed autosave timer.
        clean = project / 'open.lua'; clean.write_text('clean\n'); clean_buf = open_buffer(clean)
        lua('vim.cmd.vsplit();return true')
        choose(clean)
        geometry = lua('return #vim.api.nvim_list_wins()')
        preferences.write_text('return {autosave={enabled=true,delay_ms=100,on_focus_lost=false}}\n')
        lua('vim.cmd("JetvimReloadSettings");return true')
        stub(body='vim.bo[' + str(clean_buf) + '].modified=true;require("jetvim.autosave").schedule(' + str(clean_buf) + ');vim.bo[' + str(clean_buf) + '].modified=false;vim.g.delete_timer_armed=require("jetvim.autosave").states[' + str(clean_buf) + '].timer:is_active()')
        editor.raw(native)
        equal(lua('return vim.g.delete_timer_armed'), True, 'actual autosave timer armed before deletion')
        equal(clean.exists(), False, 'open file deleted')
        equal(lua('return vim.api.nvim_buf_is_valid(' + str(clean_buf) + ')'), False, 'deleted clean buffer is wiped')
        equal(lua('return #vim.api.nvim_list_wins()'), geometry, 'deletion preserves editor and sidebar windows')
        time.sleep(.25)
        equal(clean.exists(), False, 'deleted file is never recreated by autosave')
        # Contextual dispatch retains editor Command Backspace behavior.
        open_buffer(project / 'main.lua'); editor.raw(native)
        equal(lua('return vim.api.nvim_buf_get_lines(0,0,-1,false)'), ['second'], 'editor Command Backspace still deletes a line')
        equal((project / 'main.lua').is_file(), True, 'editor line action does not delete file')
        equal(lua('return vim.v.errmsg'), '', 'deletion leaves no editor errors')
        print(f'PASS: {support["checks"]} tree deletion and safety checks through actual PTY input')
    finally:
        editor.close()
