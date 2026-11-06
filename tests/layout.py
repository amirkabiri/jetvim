#!/usr/bin/env python3
"""Regression: closing editor tabs must never close or resize project/tool panes."""
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import struct
import subprocess
import sys
import tempfile
import termios
import threading
import time

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / '.jetvim'
STATE.mkdir(exist_ok=True)
SOCKET = STATE / f'layout-{os.getpid()}.sock'
ENV = dict(os.environ, TERM='xterm-256color', JETVIM_DISABLE_VCS='1', JETVIM_DISABLE_AUTOSAVE='1')
checks = 0
welcome = '--welcome' in sys.argv


def equal(actual, expected, label):
    global checks
    assert actual == expected, f'{label}: expected {expected!r}, got {actual!r}'
    checks += 1


def lua(code):
    expression = "json_encode(luaeval('(function() " + code.replace("'", "''") + " end)()'))"
    result = subprocess.run([str(ROOT / 'jetvim'), '--server', str(SOCKET), '--remote-expr', expression],
                            cwd=ROOT, env=ENV, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def wait(code, expected=True):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        actual = lua(code)
        if actual == expected:
            return actual
        time.sleep(0.03)
    raise AssertionError(f'timed out: {code}; actual={actual!r}')


def raw(data):
    os.write(master, data.encode() if isinstance(data, str) else data)
    time.sleep(0.10)


def name():
    return lua('return vim.fs.basename(vim.api.nvim_buf_get_name(0))')


def geometry():
    return lua('local t=require("jetvim.tree"); local wins={}; for _,w in ipairs(vim.api.nvim_tabpage_list_wins(0)) do '
               'wins[#wins+1]={w,vim.api.nvim_win_get_width(w),vim.api.nvim_win_get_height(w),vim.api.nvim_win_get_position(w)} end; return wins')


def tree_open(filename):
    if lua('return vim.bo.filetype') != 'jetvim-tree':
        raw(b'\x1b[49;9u')
    wait('return vim.bo.filetype', 'jetvim-tree')
    lua('local t=require("jetvim.tree"); t.clear_search(); for row,e in pairs(t.rows) do if e.name==' + json.dumps(filename) + ' then vim.api.nvim_win_set_cursor(t.win,{row,0}); return true end end; error("missing tree file")')
    raw(b'\r')
    wait('return vim.fs.basename(vim.api.nvim_buf_get_name(0))', filename)


with tempfile.TemporaryDirectory(prefix='layout-', dir=STATE) as directory:
    project = Path(directory)
    for filename in ('one.lua', 'two.lua', 'three.lua'):
        (project / filename).write_text('-- ' + filename + '\n')
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 35, 140, 0, 0))
    initial_files = [] if welcome else ['one.lua', 'two.lua']
    process = subprocess.Popen([str(ROOT / 'jetvim'), directory, *initial_files, '--listen', str(SOCKET)],
                               cwd=ROOT, env=ENV, stdin=slave, stdout=slave, stderr=slave)
    os.close(slave)
    stop = threading.Event()
    output = bytearray()

    def drain():
        while not stop.is_set():
            ready, _, _ = select.select([master], [], [], 0.1)
            if ready:
                try:
                    data = os.read(master, 65536)
                except OSError:
                    return
                if not data:
                    return
                output.extend(data)
                if b'\x1b]11;?' in data:
                    os.write(master, b'\x1b]11;rgb:1e1e/1f1f/2222\x07')
                if b'\x1b[5n' in data:
                    os.write(master, b'\x1b[0n')
                if b'\x1b[6n' in data:
                    os.write(master, b'\x1b[1;1R')

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    try:
        deadline = time.monotonic() + 10
        while not SOCKET.exists():
            assert process.poll() is None and time.monotonic() < deadline, 'editor startup failed'
            time.sleep(0.03)
        wait('return package.loaded["jetvim.tree"] ~= nil')
        wait('return #vim.api.nvim_tabpage_list_wins(0)', 2)
        if welcome:
            before = geometry()
            equal(lua('return vim.bo.buftype'), 'nofile', 'welcome screen begins in editor slot')
            tree_open('one.lua')
            equal(geometry(), before, 'first file from welcome reuses original editor and tree widths')
            equal(lua('return vim.bo.buflisted'), True, 'first file from welcome is an editor tab')
            raw(b'\x1b[119;9u')
            equal(geometry(), before, 'close from initial welcome layout preserves geometry')
            equal(lua('return vim.b.jetvim_editor_placeholder == true and vim.bo.buftype=="nofile"'), True, 'first welcome file closes to an empty editor slot')
            raw(b'\x1b[111;10u')
            wait('return vim.bo.buftype', 'prompt')
            raw('two.lua\r')
            wait('return vim.fs.basename(vim.api.nvim_buf_get_name(0))', 'two.lua')
            equal(geometry(), before, 'picker from empty welcome editor reuses original panes')
            equal(lua('local t=require("jetvim.tree"); return vim.api.nvim_win_get_buf(t.win)==t.buf'), True, 'welcome tree retains actual tree buffer')
            welcome_width = lua('return vim.api.nvim_win_get_width(require("jetvim.tree").win)')
            raw(b'\x1b[119;9u')
            raw(b'\x1b[49;9u')
            wait('return vim.bo.filetype', 'jetvim-tree')
            raw(b'\x1b[49;9u')
            equal(lua('return #vim.api.nvim_tabpage_list_wins(0)'), 1, 'welcome empty-editor sidebar toggles hidden')
            raw(b'\x1b[983041u')
            wait('return vim.bo.filetype', 'jetvim-tree')
            equal(lua('return vim.api.nvim_win_get_width(require("jetvim.tree").win)'), welcome_width, 'welcome sidebar relay reopens at original width')
            print(f'PASS: {checks} no-file startup layout checks through actual PTY input')
            sys.exit(0)
        wait('return vim.fs.basename(vim.api.nvim_buf_get_name(0))', 'one.lua')
        lua('require("jetvim.project").open("two.lua"); require("jetvim.project").open("one.lua"); return true')
        tree = lua('return require("jetvim.tree").win')
        editor = lua('return vim.api.nvim_get_current_win()')
        # Exercise actual mouse resizing, rather than only setting a width via RPC.
        width = lua('return vim.api.nvim_win_get_width(require("jetvim.tree").win)')
        position = lua('return vim.api.nvim_win_get_position(require("jetvim.tree").win)')
        x, y = position[1] + width + 1, position[0] + 6
        raw(f'\x1b[<0;{x};{y}M')
        raw(f'\x1b[<32;{x + 13};{y}M')
        raw(f'\x1b[<0;{x + 13};{y}m')
        wait('return vim.api.nvim_win_get_width(require("jetvim.tree").win)', width + 13)
        lua('vim.api.nvim_set_current_win(' + str(editor) + '); return true')
        baseline = geometry()
        raw(b'\x1b[119;9u')  # Command-W
        wait('return vim.api.nvim_buf_is_valid(vim.fn.bufnr("one.lua")) == false or vim.fn.buflisted("one.lua") == 0')
        equal(geometry(), baseline, 'closing a tab preserves pane geometry')
        equal(name(), 'two.lua', 'closing first tab selects another editor')
        raw(b'\x1b[119;9u')
        equal(geometry(), baseline, 'closing last tab preserves editor slot and sidebar width')
        equal(lua('return require("jetvim.tree").win'), tree, 'sidebar window identity survives last close')
        equal(lua('local t=require("jetvim.tree"); return vim.api.nvim_win_get_buf(t.win)==t.buf and vim.bo[t.buf].filetype=="jetvim-tree"'), True, 'sidebar retains its actual tree buffer')
        equal(lua('return vim.api.nvim_get_current_win()'), editor, 'editor window identity survives last close')
        equal(lua('return #vim.api.nvim_tabpage_list_wins(0)'), 2, 'empty editor has exactly two panes')
        for _ in range(3):
            raw(b'\x1b[119;9u')
        equal(geometry(), baseline, 'repeated Command-W with no open files is harmless')
        raw(b'\x1b[49;9u')
        wait('return vim.bo.filetype', 'jetvim-tree')
        for _ in range(3):
            raw(b'\x1b[119;9u')
        equal(lua('return vim.api.nvim_win_is_valid(require("jetvim.tree").win)'), True, 'Command-W from sidebar never deletes it')
        equal(lua('local t=require("jetvim.tree"); return vim.api.nvim_win_get_buf(t.win)==t.buf and vim.bo[t.buf].filetype=="jetvim-tree"'), True, 'repeated sidebar close preserves tree role')
        equal(geometry(), baseline, 'Command-W from empty sidebar preserves panes')
        raw(b'\x1b[49;9u')
        equal(lua('return vim.api.nvim_win_is_valid(require("jetvim.tree").win)'), False, 'Command-1 hides a focused sidebar after all files close')
        equal(lua('return vim.b.jetvim_editor_placeholder == true'), True, 'hiding tree preserves empty editor slot')
        raw(b'\x1b[49;9u')
        wait('return vim.bo.filetype', 'jetvim-tree')
        tree = lua('return require("jetvim.tree").win')
        baseline = geometry()
        equal(lua('return vim.api.nvim_win_get_width(require("jetvim.tree").win)'), width + 13, 'Command-1 reopens sidebar at user-selected width')
        raw(b'\x1b[983041u')
        equal(lua('return #vim.api.nvim_tabpage_list_wins(0)'), 1, 'relay Command-1 hides focused sidebar')
        raw(b'\x1b[983041u')
        wait('return vim.bo.filetype', 'jetvim-tree')
        baseline = geometry()
        equal(lua('return vim.api.nvim_win_get_width(require("jetvim.tree").win)'), width + 13, 'relay Command-1 preserves resized sidebar width')
        lua('local t=require("jetvim.tree"); t.win=t.editor_win; return true')
        # Use unconditional focus here: repairing a stale cache must find the
        # already displayed tree, not split beside it or restyle the editor.
        lua('require("jetvim.tree").focus(); return true')
        equal(geometry(), baseline, 'wrong-role tree cache recovers existing sidebar without another split')
        equal(lua('local t=require("jetvim.tree"); return vim.api.nvim_win_get_buf(t.win)==t.buf'), True, 'recovered sidebar cache matches actual tree buffer')
        lua('local t=require("jetvim.tree"); t.editor_win=t.win; return true')
        tree_open('three.lua')
        equal(geometry(), baseline, 'opening from tree reuses full-size editor slot')
        equal(lua('local t=require("jetvim.tree"); return t.editor_win ~= t.win and vim.api.nvim_win_get_buf(t.win)==t.buf'), True, 'valid cached sidebar window cannot be mistaken for editor')
        raw(b'\x1b[49;9u')
        wait('return vim.bo.filetype', 'jetvim-tree')
        equal(geometry(), baseline, 'Command-1 from editor focuses visible tree without hiding')
        raw(b'\x1b[49;9u')
        equal(name(), 'three.lua', 'Command-1 hide focuses current editor')
        equal(lua('return vim.fn.mode()'), 'i', 'Command-1 hide resumes editable file typing')
        raw(b'\x1b[983041u')
        wait('return vim.bo.filetype', 'jetvim-tree')
        baseline = geometry()
        equal(lua('return vim.api.nvim_win_get_width(require("jetvim.tree").win)'), width + 13, 'editor/sidebar toggle roundtrip preserves width')
        raw(b'\x1b')
        time.sleep(0.15)
        wait('return vim.fs.basename(vim.api.nvim_buf_get_name(0))', 'three.lua')
        for _ in range(3):
            raw(b'\x1b[119;9u')
            tree_open('three.lua')
            equal(geometry(), baseline, 'repeated close/open from tree preserves geometry')
        raw(b'\x1b[119;9u')
        raw(b'\x1b[111;10u')  # Command-Shift-O
        wait('return vim.bo.buftype', 'prompt')
        raw('two.lua\r')
        wait('return vim.fs.basename(vim.api.nvim_buf_get_name(0))', 'two.lua')
        equal(geometry(), baseline, 'Go to File after closing all tabs preserves geometry')
        # Closing while the tree is focused closes an editor, never the tree.
        raw(b'\x1b[49;9u')
        wait('return vim.bo.filetype', 'jetvim-tree')
        bindings = json.loads((ROOT / 'config/keymap.json').read_text())
        relay = next(i for i, item in enumerate(bindings, 1) if item['id'] == 'close')
        raw(f'\x1b[{0xF0000 + relay}u')
        equal(geometry(), baseline, 'bridge close from sidebar preserves geometry')
        equal(lua('return vim.api.nvim_win_is_valid(require("jetvim.tree").win)'), True, 'bridge close keeps sidebar')
        tree_open('one.lua')
        # A terminal pane is a real special buffer; no shell or Git runs.
        lua('vim.g.layout_tool=vim.api.nvim_create_buf(false,true); vim.g.layout_tool_input=""; vim.cmd("botright 7split"); '
            'vim.g.layout_tool_win=vim.api.nvim_get_current_win(); vim.api.nvim_win_set_buf(0,vim.g.layout_tool); '
            'vim.api.nvim_open_term(vim.g.layout_tool,{on_input=function(_,_,_,data) vim.g.layout_tool_input=vim.g.layout_tool_input..data end}); require("jetvim.tree").editor(); return true')
        tools_geometry = geometry()
        raw(b'\x1b[119;9u')
        equal(geometry(), tools_geometry, 'closing final editor with tool pane preserves geometry')
        tree_open('two.lua')
        equal(geometry(), tools_geometry, 'reopening with tool pane preserves geometry')
        equal(lua('return vim.api.nvim_win_get_buf(vim.g.layout_tool_win)'), lua('return vim.g.layout_tool'), 'tool buffer preserved')
        lua('vim.api.nvim_set_current_win(vim.g.layout_tool_win); vim.cmd.startinsert(); return true')
        wait('return vim.fn.mode()', 't')
        raw(b'\x1b[119;9u')
        raw(f'\x1b[{0xF0000 + relay}u')
        equal(lua('return vim.fn.mode()'), 't', 'Command-W in terminal keeps terminal input mode')
        equal(lua('return vim.g.layout_tool_input'), '', 'native and bridge Command-W do not leak into terminal')
        equal(geometry(), tools_geometry, 'terminal Command-W preserves every pane')
        raw(b'\x1c\x0e')
        wait('return vim.fn.mode()', 'n')
        lua('require("jetvim.tree").editor(); return true')
        # Exercise real terminal confirmation dialogs, including their hotkeys.
        def confirm(choice):
            start = len(output)
            os.write(master, b'\x1b[119;9u')
            deadline = time.monotonic() + 5
            while b'Save changes to' not in output[start:]:
                assert time.monotonic() < deadline, 'save confirmation was not displayed'
                time.sleep(0.025)
            raw(choice)

        lua('vim.api.nvim_buf_set_lines(0,0,-1,false,{"unsaved cancel"}); return true')
        modified = lua('return vim.api.nvim_get_current_buf()')
        confirm('c')
        equal(lua('return vim.api.nvim_get_current_buf()'), modified, 'Cancel keeps modified editor active')
        equal(lua('return vim.bo.modified'), True, 'Cancel retains modified flag')
        equal(lua('return vim.api.nvim_get_current_line()'), 'unsaved cancel', 'Cancel retains unsaved contents')
        equal(lua('return vim.b.jetvim_closing == nil'), True, 'Cancel clears autosave close guard')
        equal(geometry(), tools_geometry, 'Cancel leaves geometry unchanged')
        confirm('s')
        equal((project / 'two.lua').read_text(), 'unsaved cancel\n', 'Save writes before closing')
        equal(lua('return vim.fn.buflisted(' + str(modified) + ')'), 0, 'Save closes editor tab')
        equal(geometry(), tools_geometry, 'Save and close preserves geometry')
        tree_open('two.lua')
        lua('vim.api.nvim_buf_set_lines(0,0,-1,false,{"discard me"}); return true')
        confirm('d')
        equal((project / 'two.lua').read_text(), 'unsaved cancel\n', 'Discard does not overwrite disk')
        equal(geometry(), tools_geometry, 'Discard and close preserves geometry')
        tree_open('two.lua')
        lua('vim.g.layout_original_confirm=vim.o.confirm; vim.bo.readonly=true; vim.api.nvim_buf_set_lines(0,0,-1,false,{"keep failed save"}); '
            '_G.layout_notify=vim.notify; vim.notify=function(message) vim.g.layout_save_error=message end; return true')
        failed = lua('return vim.api.nvim_get_current_buf()')
        confirm('s')
        equal(lua('return vim.api.nvim_get_current_buf()'), failed, 'failed Save keeps editor active')
        equal(lua('return vim.bo.modified'), True, 'failed Save preserves modified flag')
        equal(lua('return vim.api.nvim_get_current_line()'), 'keep failed save', 'failed Save preserves unsaved contents')
        equal(geometry(), tools_geometry, 'failed Save leaves geometry unchanged')
        equal(lua('return vim.g.layout_save_error:find("Could not save file",1,true) ~= nil'), True, 'failed Save explains error')
        equal((project / 'two.lua').read_text(), 'unsaved cancel\n', 'failed Save does not alter disk')
        equal(lua('return vim.o.confirm == vim.g.layout_original_confirm'), True, 'failed Save restores confirmation setting')
        equal(lua('return vim.b.jetvim_closing == nil'), True, 'failed Save clears autosave close guard')
        lua('vim.notify=_G.layout_notify; vim.bo.readonly=false; vim.v.errmsg=""; return true')
        equal(lua('return vim.v.errmsg'), '', 'no editor errors')
        print(f'PASS: {checks} close/reopen layout checks through actual PTY input')
    finally:
        if process.poll() is None:
            try:
                os.write(master, b'\x1b')
                lua('vim.cmd("qa!"); return true')
            except Exception:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=5)
        stop.set()
        reader.join(timeout=2)
        (STATE / 'layout-output.log').write_bytes(output)
        os.close(master)
        SOCKET.unlink(missing_ok=True)
if not welcome:
    subprocess.run([sys.executable, str(Path(__file__).resolve()), '--welcome'], cwd=ROOT, env=ENV, check=True)
