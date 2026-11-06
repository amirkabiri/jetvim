#!/usr/bin/env python3
"""Native external-file reloads and conflict safety. --git-restore is lead-only."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
support = {'__file__': str(ROOT / 'tests/autosave.py')}
exec((ROOT / 'tests/autosave.py').read_text().split('\nwith tempfile.TemporaryDirectory', 1)[0], support)
Editor, equal, STATE = support['Editor'], support['equal'], support['STATE']


def contents(editor, buf=0):
    return editor.lua(f'return vim.api.nvim_buf_get_lines({buf},0,-1,false)')


def changed(editor, expected, buf=0):
    text = json.dumps(expected, ensure_ascii=False)
    editor.wait(f'return vim.deep_equal(vim.api.nvim_buf_get_lines({buf},0,-1,false),vim.json.decode(' + json.dumps(text, ensure_ascii=False) + '))')
    equal(contents(editor, buf), expected, 'external change reaches buffer')


def git(project, *args):
    # This helper is called only with explicit --git-restore by the lead or CI.
    result = subprocess.run(['git', '-C', str(project), *args], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    return result.stdout


with tempfile.TemporaryDirectory(prefix='disk-', dir=STATE) as directory:
    project = Path(directory)
    home = project / 'home'; home.mkdir()
    prefs = home / 'settings.lua'
    prefs.write_text('return {autosave={debounce=false,on_focus_lost=false}}\n')
    main = project / 'main.lua'
    main.write_text('\n'.join('local value_' + str(i) + ' = ' + str(i) for i in range(1, 101)) + '\n')
    second = project / 'other.lua'; second.write_text('-- other\n')
    editor = Editor(project, prefs, disabled=True)
    try:
        editor.lua('vim.g.disk_events=0; vim.g.disk_reads=0; vim.g.disk_writes=0; vim.g.disk_vcs=0; '
                   'vim.api.nvim_create_autocmd("User",{pattern="JetvimDiskChanged",callback=function() vim.g.disk_events=vim.g.disk_events+1 end}); '
                   'vim.api.nvim_create_autocmd("BufReadPost",{callback=function() vim.g.disk_reads=vim.g.disk_reads+1 end}); '
                   'vim.api.nvim_create_autocmd("BufWritePost",{callback=function() vim.g.disk_writes=vim.g.disk_writes+1 end}); '
                   'require("jetvim.vcs").refresh=function() vim.g.disk_vcs=vim.g.disk_vcs+1 end; '
                   '_G.disk_notices={}; vim.notify=function(text) table.insert(_G.disk_notices,text) end; return true')
        buf = editor.lua('return vim.api.nvim_get_current_buf()')
        owner = editor.lua('return vim.api.nvim_get_current_win()')
        editor.lua('vim.api.nvim_win_set_cursor(0,{60,6}); vim.cmd("normal! zt"); vim.cmd.startinsert(); return true')
        caret = editor.lua('return vim.api.nvim_win_get_cursor(0)')
        view = editor.lua('return vim.fn.winsaveview().topline')
        initial = main.read_text()
        main.write_text(initial.replace('value_1 = 1', 'value_1 = 9'))
        changed(editor, main.read_text().splitlines())
        equal(editor.lua('return vim.api.nvim_win_get_cursor(0)'), caret, 'reload keeps caret')
        equal(editor.lua('return vim.fn.winsaveview().topline'), view, 'reload keeps scroll position')
        equal(editor.lua('return vim.api.nvim_get_current_win()'), owner, 'reload never steals window focus')
        equal(editor.lua('return vim.fn.mode()'), 'i', 'reload keeps typing mode')
        equal(editor.lua('return vim.g.disk_writes'), 0, 'reload does not save or run save hooks')
        equal(editor.lua('return vim.g.disk_reads>0 and vim.g.disk_vcs>0'), True, 'read observers and VCS refreshed')
        equal(editor.lua('return vim.bo.modified'), False, 'reloaded buffer stays clean')
        # Explicit clean reload scopes restore their guards on failure and can
        # handle native FileChangedShell even when autoread is disabled.
        equal(editor.lua('local disk=require("jetvim.disk"); local auto=require("jetvim.autosave"); local writing=auto.writing; local ok=pcall(disk.with_native_reload,0,function() error("fixture") end); return not ok and disk.native_reload==nil and auto.writing==writing'),True,'native read scope restores guards after callback failure')
        editor.lua('require("jetvim.disk").timer:stop(); vim.bo.autoread=false; return true')
        main.write_text('-- explicit native reload\n')
        editor.lua('require("jetvim.disk").with_native_reload(0,function() vim.cmd("checktime") end); return true')
        changed(editor,['-- explicit native reload'])
        editor.lua('vim.bo.autoread=true; local disk=require("jetvim.disk"); disk.timer:start(500,500,vim.schedule_wrap(disk.schedule)); return true')
        # Same-size writes and atomic replacement are both observed.
        main.write_text('-- same size A\n')
        changed(editor, ['-- same size A'])
        main.write_text('-- same size B\n')
        changed(editor, ['-- same size B'])
        replacement = project / 'atomic.tmp'; replacement.write_text('-- atomic replace\n')
        os.replace(replacement, main)
        changed(editor, ['-- atomic replace'])
        equal(editor.lua('return vim.api.nvim_win_get_cursor(0)[1]'), 1, 'shorter file clamps caret safely')
        # Native reads detect BOM/CRLF and preserve Unicode as editor text.
        main.write_bytes(b'\xef\xbb\xbf' + 'local greeting = "héllo 😀"\r\nsecond line\r\n'.encode())
        changed(editor, ['local greeting = "héllo 😀"', 'second line'])
        equal(editor.lua('return vim.bo.fileformat'), 'dos', 'external CRLF recognized')
        equal(editor.lua('return vim.bo.bomb'), True, 'external UTF8 BOM recognized')
        main.write_bytes(b'no-final-newline')
        changed(editor, ['no-final-newline'])
        equal(editor.lua('return vim.bo.endofline'), False, 'external missing final newline preserved')
        # Readonly clean files still reflect disk while keeping readonly state.
        editor.lua('vim.bo.readonly=true; return true')
        main.write_text('-- readonly new\n')
        changed(editor, ['-- readonly new'])
        equal(editor.lua('return vim.bo.readonly'), True, 'reload retains readonly preference')
        editor.lua('vim.bo.readonly=false; return true')
        # Old saved-version diagnostics disappear, awaiting fresh tool output.
        editor.lua('require("jetvim.api").diagnostics("hook:stale",0,{{line=1,message="old error"}}); vim.diagnostic.set(vim.api.nvim_create_namespace("DiskLspLive"),0,{{lnum=0,col=0,message="language server retained"}}); return true')
        main.write_text('-- diagnostics refreshed\n')
        changed(editor, ['-- diagnostics refreshed'])
        equal(editor.lua('return #vim.diagnostic.get(0,{namespace=require("jetvim.api").namespaces["hook:stale"]})'), 0, 'stale hook diagnostics cleared')
        equal(editor.lua('return #vim.diagnostic.get(0,{namespace=vim.api.nvim_create_namespace("DiskLspLive")})'), 1, 'language-server namespace retained')
        # Hidden loaded files reload without switching away from the current file.
        editor.open(second)
        other_buf = editor.lua('return vim.api.nvim_get_current_buf()')
        main.write_text('-- hidden reload\n')
        changed(editor, ['-- hidden reload'], buf)
        equal(editor.lua('return vim.api.nvim_get_current_buf()'), other_buf, 'hidden reload preserves active buffer')
        equal(editor.lua('return vim.api.nvim_get_current_win()'), owner, 'hidden reload preserves editor pane')
        # Dirty buffers keep edits and never accept a new disk baseline.
        editor.open(main)
        editor.edit('-- unsaved local')
        main.write_text('-- external conflict\n')
        editor.wait('return #_G.disk_notices>0')
        count = editor.lua('return #_G.disk_notices')
        equal(editor.lua('return require("jetvim.disk").acknowledge(0,require("jetvim.autosave").states[vim.api.nvim_get_current_buf()].expected)'),False,'dirty buffer cannot acknowledge external version')
        equal(editor.lua('return pcall(require("jetvim.disk").with_native_reload,0,function() error("must not run") end)'),False,'dirty buffer cannot enter native reload scope')
        editor.lua('vim.cmd("checktime"); return true')
        equal(editor.lua('return vim.api.nvim_get_mode().blocking'), False, 'native timestamp check does not block on conflict')
        time.sleep(1.1)
        equal(contents(editor), ['-- unsaved local'], 'disk conflict preserves unsaved text')
        equal(editor.lua('return vim.bo.modified'), True, 'disk conflict keeps dirty flag')
        equal(editor.lua('return #_G.disk_notices'), count, 'same disk version warns once')
        equal(main.read_text(), '-- external conflict\n', 'disk observer never overwrites external change')
        equal(editor.lua('return vim.deep_equal(require("jetvim.autosave").states[vim.api.nvim_get_current_buf()].expected,require("jetvim.disk").states[vim.api.nvim_get_current_buf()].expected)'), True, 'conflict retains autosave original baseline')
        editor.lua('vim.cmd("edit!"); return true')
        changed(editor, ['-- external conflict'])
        # Deleted files are retained, then recreated files reload naturally.
        main.unlink()
        editor.wait('return _G.disk_notices[#_G.disk_notices]:find("deleted on disk",1,true) ~= nil')
        equal(contents(editor), ['-- external conflict'], 'deleted file keeps editor contents')
        equal(main.exists(), False, 'observer never recreates deleted file')
        main.write_text('-- recreated\n')
        changed(editor, ['-- recreated'])
        # FocusGained catches changes immediately even if the poll timer is stopped.
        editor.lua('require("jetvim.disk").timer:stop(); return true')
        main.write_text('-- focus refresh\n')
        editor.lua('vim.api.nvim_exec_autocmds("FocusGained",{}); return true')
        changed(editor, ['-- focus refresh'])
        # BufEnter catches a hidden-buffer edit missed while polling is stopped.
        editor.open(second)
        main.write_text('-- enter refresh\n')
        editor.open(main)
        changed(editor, ['-- enter refresh'])
        equal(editor.lua('return vim.v.errmsg'), '', 'reloads avoid native error prompts')
        if '--git-restore' in sys.argv:
            git(project, 'init')
            git(project, 'config', 'user.name', 'Example Author')
            git(project, 'config', 'user.email', 'author@example.invalid')
            git(project, 'add', 'main.lua')
            git(project, 'commit', '-m', 'Disk reload fixture')
            editor.lua('require("jetvim.disk").timer:start(500,500,vim.schedule_wrap(require("jetvim.disk").schedule)); return true')
            main.write_text('-- changed tracked file\n')
            changed(editor, ['-- changed tracked file'])
            git(project, 'restore', '--', 'main.lua')
            changed(editor, ['-- enter refresh'])
    finally:
        editor.close()

# A hidden reload must not trigger a synthetic focus-leave save of dirty current text.
with tempfile.TemporaryDirectory(prefix='disk-autosave-', dir=STATE) as directory:
    project = Path(directory); home = project/'home'; home.mkdir()
    prefs=home/'settings.lua'; prefs.write_text('return {autosave={debounce=false,on_focus_lost=true}}\n')
    main=project/'main.lua'; main.write_text('-- first\n')
    other=project/'other.lua'; other.write_text('-- other original\n')
    editor=Editor(project,prefs)
    try:
        first=editor.lua('return vim.api.nvim_get_current_buf()')
        editor.open(other); editor.edit('-- other unsaved')
        main.write_text('-- background external\n')
        changed(editor,['-- background external'],first)
        equal(other.read_text(),'-- other original\n','background reload does not focus-save another dirty file')
        equal(editor.lua('return vim.bo.modified'),True,'background reload keeps current unsaved state')
        editor.lua('vim.api.nvim_buf_set_lines(0,0,-1,false,{"-- user saved"}); vim.cmd.write(); return true')
        # A clean reload updates autosave's baseline so later genuine edits can save.
        other.write_text('-- other external\n');changed(editor,['-- other external'])
        editor.edit('-- after reload edit');editor.open(main)
        editor.disk(other,'-- after reload edit\n')
        equal(editor.lua('return vim.v.errmsg'),'','focus autosave stays healthy after disk reload')
    finally: editor.close()


# The watcher must not interrupt a formatter's own reload and following lint job.
with tempfile.TemporaryDirectory(prefix='disk-hooks-', dir=STATE) as directory:
    project = Path(directory); home = project/'home'; home.mkdir()
    prefs = home/'settings.lua'; prefs.write_text('return {autosave={debounce=false,on_focus_lost=false}}\n')
    main = project/'main.lua'; main.write_text('-- original\n')
    marker = project/'lint-ran'
    commands = [
        {'name':'slow-format','pattern':r'\.lua$', 'command':[sys.executable,'-c',
         'from pathlib import Path; import sys,time; Path(sys.argv[1]).write_text("-- formatted\\n"); time.sleep(1.2)','{file}']},
        {'name':'after-format-lint','pattern':r'\.lua$', 'command':[sys.executable,'-c',
         'from pathlib import Path; import json,sys; Path(sys.argv[1]).write_text("ran"); print(json.dumps([dict(line=1,message="fresh lint")]))',str(marker)],
         'diagnostics':None},
    ]
    editor=Editor(project,prefs,disabled=True)
    try:
        encoded=json.dumps(json.dumps(commands))
        editor.lua('local get=require("jetvim.settings").get; require("jetvim.settings").get=function() local value=get(); value.hooks={after_save=vim.json.decode('+encoded+')}; value.hooks.after_save[2].diagnostics=function(stdout) return vim.json.decode(stdout) end; return value end; return true')
        editor.edit('-- saved'); editor.lua('vim.cmd.write(); return true')
        editor.wait('return vim.fn.readfile(vim.api.nvim_buf_get_name(0))[1]=="-- formatted"')
        time.sleep(.65)
        equal(contents(editor),['-- saved'],'disk watcher waits while formatter owns reload')
        equal(editor.lua('return vim.b.jetvim_hook_running'),True,'pipeline remains active during delayed formatter')
        editor.wait('return vim.b.jetvim_hook_running == nil')
        changed(editor,['-- formatted'])
        equal(marker.read_text(),'ran','formatter followed by lint despite watcher polls')
        equal(editor.lua('local ns=require("jetvim.api").namespaces["hook:after-format-lint"]; return ns and vim.diagnostic.get(0,{namespace=ns})[1].message'),'fresh lint','new pipeline diagnostics remain visible')
    finally: editor.close()

# Identical formatter output still changes mtime; it must not erase fresh lint.
with tempfile.TemporaryDirectory(prefix='disk-noop-hooks-', dir=STATE) as directory:
    project=Path(directory); home=project/'home'; home.mkdir()
    prefs=home/'settings.lua';prefs.write_text('return {autosave={debounce=false,on_focus_lost=false}}\n')
    main=project/'main.lua';main.write_text('-- original\n')
    command=[sys.executable,'-c','from pathlib import Path; import sys,time; p=Path(sys.argv[1]); p.write_bytes(p.read_bytes()); time.sleep(.7)','{file}']
    editor=Editor(project,prefs,disabled=True)
    try:
        encoded=json.dumps(json.dumps(command))
        editor.lua('local get=require("jetvim.settings").get; require("jetvim.settings").get=function() local value=get(); value.hooks={after_save={{name="noop-format",pattern=[[\\.lua$]],command=vim.json.decode('+encoded+')},{name="noop-lint",pattern=[[\\.lua$]],command={"python3","-c","pass"},diagnostics=function() return {{line=1,message="fresh noop lint"}} end}}}; return value end; return true')
        editor.edit('-- saved');editor.lua('vim.cmd.write(); return true')
        editor.wait('return vim.b.jetvim_hook_running==nil')
        time.sleep(.85)
        equal(editor.lua('local ns=require("jetvim.api").namespaces["hook:noop-lint"]; return ns and #vim.diagnostic.get(0,{namespace=ns})'),1,'identical formatter output preserves fresh lint after watcher poll')
        editor.lua('vim.env.JETVIM_DISABLE_AUTOSAVE=nil; local get=require("jetvim.settings").get; require("jetvim.settings").get=function() local value=get(); value.autosave.debounce=true; value.autosave.delay_ms=250; return value end; return true')
        editor.edit('-- autosaved after noop')
        editor.disk(main,'-- autosaved after noop\n')
    finally:editor.close()

print(f'PASS: {support["checks"]} external disk-change and conflict checks through real PTY input')
