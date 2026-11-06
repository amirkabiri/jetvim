#!/usr/bin/env python3
"""Exercise sidebar Speed Search through real terminal input and window focus."""
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import struct
import subprocess
import tempfile
import termios
import threading
import time

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / '.jetvim'
STATE.mkdir(exist_ok=True)
SOCKET = STATE / f'sidebar-{os.getpid()}.sock'
checks = 0


def lua(code):
    expression = "json_encode(luaeval('(function() " + code.replace("'", "''") + " end)()'))"
    result = subprocess.run([str(ROOT / 'jetvim'), '--server', str(SOCKET), '--remote-expr', expression],
                            cwd=ROOT, capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return json.loads(result.stdout)


def equal(actual, expected, label):
    global checks
    assert actual == expected, f'{label}: expected {expected!r}, got {actual!r}'
    checks += 1


def wait_for(code, expected, label):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        actual = lua(code)
        if actual == expected:
            equal(actual, expected, label)
            return
        time.sleep(0.025)
    equal(actual, expected, label)


with tempfile.TemporaryDirectory(prefix='sidebar-project-', dir=STATE) as folder:
    project = Path(folder) / 'ProjectRoot'
    project.mkdir()
    control_name = 'odd\r\ncontrol\tname.txt'
    for filename in ['alpha.txt', 'alpine.txt', 'README.md', 'ruler.lua', 'résumé.txt', 'سلام.txt', 'space name.txt', control_name]:
        (project / filename).write_text('fixture\n')
    (project / 'nested').mkdir()
    (project / 'nested' / 'hidden-child.txt').write_text('nested fixture\n')
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 35, 120, 0, 0))
    process = subprocess.Popen([str(ROOT / 'jetvim'), str(project), '--listen', str(SOCKET)],
                               cwd=ROOT, stdin=slave, stdout=slave, stderr=slave,
                               env=dict(os.environ, TERM='xterm-256color', JETVIM_DISABLE_VCS='1'))
    os.close(slave)
    stop, output = threading.Event(), bytearray()

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

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()

    def send(value):
        os.write(master, value.encode() if isinstance(value, str) else value)

    def escape():
        send(b'\x1b')
        time.sleep(0.14)

    def selected():
        return lua('local t = require("jetvim.tree"); local e = t.rows[vim.api.nvim_win_get_cursor(t.win)[1]]; return e and e.name or ""')

    def name_group(filename):
        return lua('local t=require("jetvim.tree"); for row,e in pairs(t.rows) do if e.name==' + json.dumps(filename) + ' then for _,mark in ipairs(vim.api.nvim_buf_get_extmarks(t.buf,vim.api.nvim_create_namespace("JetvimTreeDecorations"),{row-1,0},{row-1,-1},{details=true})) do if mark[3]==e.column then return mark[4].hl_group end end end end; return ""')

    try:
        deadline = time.monotonic() + 10
        while not SOCKET.exists():
            if process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('Sidebar test editor did not start')
            time.sleep(0.03)
        wait_for('return #vim.api.nvim_list_wins()', 2, 'sidebar displayed at startup')
        equal(lua('return vim.wo[require("jetvim.tree").win].winhighlight:find("CursorLine:JetvimTreeCursorLineInactive",1,true) ~= nil'), True, 'initial editor focus leaves sidebar selection muted')
        lua('require("jetvim.project").open("alpha.txt"); return true')
        # The relay is the same private CSI-u key emitted by the Warp bridge.
        send(b'\x1b[983041u')
        wait_for('return vim.bo.filetype', 'jetvim-tree', 'Command-1 relay focuses sidebar')
        equal(lua('return vim.wo[require("jetvim.tree").win].winhighlight:find("CursorLine:JetvimTreeCursorLine,",1,true) ~= nil'), True, 'focused sidebar uses blue selection')
        equal(lua('local t=require("jetvim.tree"); local root=t.rows[2]; for _, entry in pairs(t.rows) do if entry.name=="nested" then return entry.column-root.column end end'), 2, 'first-level folder indents one step beneath project root')
        initial_width = lua('return vim.api.nvim_win_get_width(require("jetvim.tree").win)')
        position = lua('return vim.api.nvim_win_get_position(require("jetvim.tree").win)')
        divider, mouse_row = position[1] + initial_width + 1, position[0] + 6
        send(f'\x1b[<0;{divider};{mouse_row}M')
        time.sleep(0.08)
        send(f'\x1b[<32;{divider + 12};{mouse_row}M')
        time.sleep(0.08)
        send(f'\x1b[<0;{divider + 12};{mouse_row}m')
        wait_for('return vim.api.nvim_win_get_width(require("jetvim.tree").win)', initial_width + 12, 'mouse drag resizes sidebar divider')
        send('ral')
        wait_for('return require("jetvim.tree").query', 'ral', 'r/a/l search rather than run former tree commands')
        equal(lua('return vim.bo.buftype'), 'nofile', 'letters do not create a prompt')
        escape()
        wait_for('return require("jetvim.tree").query', '', 'Escape clears search')
        equal(lua('return vim.bo.filetype'), 'jetvim-tree', 'first Escape retains sidebar focus')
        send('AL')
        wait_for('return require("jetvim.tree").query', 'AL', 'case-insensitive query accepted')
        equal(lua('return #require("jetvim.tree").matches'), 2, 'case-insensitive visible matches')
        equal(selected(), 'alpha.txt', 'first matching file selected')
        equal(lua('local t=require("jetvim.tree"); local row=vim.api.nvim_win_get_cursor(t.win)[1]; local e=t.rows[row]; local line=vim.api.nvim_buf_get_lines(t.buf,row-1,row,false)[1]; local icon=require("jetvim.icons").for_path(e.path,e.directory,t.expanded[e.path]); return line:sub(1,e.column):find(icon.text,1,true) ~= nil'), True, 'file icon occupies prefix before searchable filename')
        equal(lua('local t=require("jetvim.tree"); local row=vim.api.nvim_win_get_cursor(t.win)[1]; local e=t.rows[row]; local line=vim.api.nvim_buf_get_lines(t.buf,row-1,row,false)[1]; return line:sub(e.column,e.column)'), ' ', 'explicit gap separates icon and filename label')
        equal(lua('local t=require("jetvim.tree"); local row=vim.api.nvim_win_get_cursor(t.win)[1]; local line=vim.api.nvim_buf_get_lines(t.buf,row-1,row,false)[1]; local found={}; for _, mark in ipairs(vim.api.nvim_buf_get_extmarks(t.buf,vim.api.nvim_create_namespace("JetvimTreeSearch"),0,-1,{details=true})) do if mark[2]==row-1 then found[#found+1]=line:sub(mark[3]+1,mark[4].end_col) end end; return table.concat(found)'), 'al', 'search highlights filename bytes after icon prefix')
        equal(lua('return #vim.api.nvim_buf_get_extmarks(require("jetvim.tree").buf, vim.api.nvim_create_namespace("JetvimTreeSearch"), 0, -1, {}) > 0'), True, 'matches highlighted')
        lua('local v=require("jetvim.vcs"); v._sidebar_original_status=v.status; v.status=function(path) local name=vim.fs.basename(path); if name=="alpha.txt" then return "modified" elseif name=="alpine.txt" then return "untracked" end end; vim.api.nvim_exec_autocmds("User",{pattern="JetvimVcsChanged"}); return true')
        equal(name_group('alpha.txt'), 'JetvimFileModified', 'cached modified status colors filename blue')
        equal(name_group('alpine.txt'), 'JetvimFileUntracked', 'cached untracked status colors filename red')
        equal(name_group('README.md'), 'JetvimFileNormal', 'clean filename retains neutral color')
        equal(name_group('nested'), 'JetvimTreeName', 'folder label retains its own styling')
        equal(selected(), 'alpha.txt', 'asynchronous VCS update preserves selected path')
        equal(lua('return require("jetvim.tree").query'), 'AL', 'asynchronous VCS update preserves search query')
        equal(lua('local t=require("jetvim.tree"); local row=vim.api.nvim_win_get_cursor(t.win)[1]; local e=t.rows[row]; local icon=require("jetvim.icons").for_path(e.path,e.directory,t.expanded[e.path]); for _,mark in ipairs(vim.api.nvim_buf_get_extmarks(t.buf,vim.api.nvim_create_namespace("JetvimTreeDecorations"),{row-1,0},{row-1,-1},{details=true})) do if mark[4].hl_group==icon.hl then return true end end; return false'), True, 'Git filename color does not overwrite filetype icon color')
        equal(lua('local t=require("jetvim.tree"); local row=vim.api.nvim_win_get_cursor(t.win)[1]; for _,mark in ipairs(vim.api.nvim_buf_get_extmarks(t.buf,vim.api.nvim_create_namespace("JetvimTreeSearch"),{row-1,0},{row-1,-1},{details=true})) do if mark[4].priority>100 then return true end end; return false'), True, 'search highlights take precedence over Git filename color')
        lua('local v=require("jetvim.vcs"); v.status=v._sidebar_original_status; v._sidebar_original_status=nil; vim.api.nvim_exec_autocmds("User",{pattern="JetvimVcsChanged"}); return true')
        send(b'\x1b[B')
        wait_for('local t = require("jetvim.tree"); return t.rows[vim.api.nvim_win_get_cursor(t.win)[1]].name', 'alpine.txt', 'Down chooses next match')
        send(b'\x1b[B')
        wait_for('local t = require("jetvim.tree"); return t.rows[vim.api.nvim_win_get_cursor(t.win)[1]].name', 'alpha.txt', 'Down wraps matching files')
        send(b'\x1b[A')
        wait_for('local t = require("jetvim.tree"); return t.rows[vim.api.nvim_win_get_cursor(t.win)[1]].name', 'alpine.txt', 'Up chooses previous match')
        (project / '000-first.txt').write_text('new sibling shifts tree rows\n')
        lua('require("jetvim.tree").render(); return true')
        equal(selected(), 'alpine.txt', 'rerender preserves selected path when preceding rows change')
        equal(lua('return require("jetvim.tree").query'), 'AL', 'rerender retains search query')
        equal(lua('return vim.api.nvim_win_get_width(require("jetvim.tree").win)'), initial_width + 12, 'search and rerender preserve manually resized width')
        # A mouse can put the cursor on an unmatched row while a search is active.
        lua('local t = require("jetvim.tree"); for row, entry in pairs(t.rows) do if entry.name == "README.md" then vim.api.nvim_win_set_cursor(t.win, {row, 0}); break end end; return true')
        send(b'\r')
        time.sleep(0.08)
        equal(lua('return vim.bo.filetype'), 'jetvim-tree', 'Enter on a nonmatching mouse selection does not open it')
        send(b'\x1b[B')
        wait_for('local t = require("jetvim.tree"); return t.rows[vim.api.nvim_win_get_cursor(t.win)[1]].name', 'alpha.txt', 'arrow recovers from nonmatching mouse selection')
        send(b'\x7f')
        wait_for('return require("jetvim.tree").query', 'A', 'Backspace shortens query')
        escape()
        send('zzmissing')
        wait_for('return #require("jetvim.tree").matches', 0, 'no-match query has no results')
        equal(lua('return vim.api.nvim_buf_get_lines(0, 2, 3, false)[1]'), '  Search [0]: zzmissing', 'no-match feedback visible')
        send(b'\r')
        time.sleep(0.08)
        equal(lua('return vim.bo.filetype'), 'jetvim-tree', 'Enter on no matches does not open stale selection')
        escape()
        send('سلام')
        wait_for('return require("jetvim.tree").query', 'سلام', 'non-ASCII text starts search')
        equal(selected(), 'سلام.txt', 'non-ASCII filename selected')
        send(b'\x7f')
        wait_for('return require("jetvim.tree").query', 'سلا', 'Backspace removes a Unicode character')
        escape()
        send('RÉSUMÉ')
        wait_for('return require("jetvim.tree").query', 'RÉSUMÉ', 'mixed ASCII/Unicode text order preserved')
        equal(selected(), 'résumé.txt', 'Unicode case folding matches filename')
        escape()
        send('hidden-child')
        wait_for('return require("jetvim.tree").query', 'hidden-child', 'query in collapsed tree')
        equal(lua('return #require("jetvim.tree").matches'), 0, 'collapsed descendants not searched as visible nodes')
        escape()
        send('nested')
        wait_for('local t = require("jetvim.tree"); return t.rows[vim.api.nvim_win_get_cursor(t.win)[1]].name', 'nested', 'directory found')
        send(b'\r')
        wait_for('return require("jetvim.tree").query', '', 'Enter clears query when expanding directory')
        send(b'\x1b[C')
        wait_for('local t = require("jetvim.tree"); return t.rows[vim.api.nvim_win_get_cursor(t.win)[1]].name', 'hidden-child.txt', 'Right enters expanded folder first child')
        send(b'\x1b[D')
        wait_for('local t = require("jetvim.tree"); return t.rows[vim.api.nvim_win_get_cursor(t.win)[1]].name', 'nested', 'Left on file selects parent folder')
        send(b'\x1b[D')
        wait_for('return not require("jetvim.tree").expanded[require("jetvim.project").root .. "/nested"]', True, 'Left collapses expanded folder')
        send(b'\x1b[C')
        wait_for('return require("jetvim.tree").expanded[require("jetvim.project").root .. "/nested"]', True, 'Right expands collapsed folder')
        equal(selected(), 'nested', 'first Right retains selection on expanded folder')
        send(b'\x1b[D')
        wait_for('return not require("jetvim.tree").expanded[require("jetvim.project").root .. "/nested"]', True, 'expanded folder closes on first Left')
        send(b'\x1b[D')
        wait_for('local t=require("jetvim.tree"); return t.rows[vim.api.nvim_win_get_cursor(t.win)[1]].root == true', True, 'second Left on closed direct child selects project root')
        send(b'\x1b[D')
        wait_for('return not require("jetvim.tree").expanded[require("jetvim.project").root]', True, 'Left collapses project root')
        equal(lua('return vim.tbl_count(require("jetvim.tree").rows)'), 1, 'collapsed root hides children')
        send(b'\x1b[D')
        equal(lua('local t=require("jetvim.tree"); return t.rows[vim.api.nvim_win_get_cursor(t.win)[1]].root'), True, 'closed root has no parent and remains selected')
        send('ProjectRoot')
        wait_for('return require("jetvim.tree").query', 'ProjectRoot', 'project root participates in visible-node search')
        equal(lua('return #require("jetvim.tree").matches'), 1, 'collapsed root remains searchable')
        escape()
        send(b'\x1b[C')
        wait_for('return require("jetvim.tree").expanded[require("jetvim.project").root]', True, 'Right expands closed root')
        send(b'\x1b[C')
        wait_for('local t=require("jetvim.tree"); return t.rows[vim.api.nvim_win_get_cursor(t.win)[1]].name', 'nested', 'second Right on root enters first child, skipping search header')
        send(b'\x1b[A')
        wait_for('local t=require("jetvim.tree"); return t.rows[vim.api.nvim_win_get_cursor(t.win)[1]].root', True, 'Up from first child selects root, skipping search header')
        send(b'\x1b[B')
        wait_for('local t=require("jetvim.tree"); return t.rows[vim.api.nvim_win_get_cursor(t.win)[1]].name', 'nested', 'Down from root skips search header')
        send(b'\x1b[C')
        wait_for('return require("jetvim.tree").expanded[require("jetvim.project").root .. "/nested"]', True, 'nested folder can reopen after root navigation')
        send('hidden-child')
        wait_for('local t = require("jetvim.tree"); return t.rows[vim.api.nvim_win_get_cursor(t.win)[1]].name', 'hidden-child.txt', 'expanded descendant found')
        send(b'\x1b[D')
        wait_for('local t = require("jetvim.tree"); return t.rows[vim.api.nvim_win_get_cursor(t.win)[1]].name', 'nested', 'Left navigates to nonmatching parent while searching')
        equal(lua('return require("jetvim.tree").query'), '', 'moving to nonmatching parent dismisses search')
        send('hidden-child')
        wait_for('local t = require("jetvim.tree"); return t.rows[vim.api.nvim_win_get_cursor(t.win)[1]].name', 'hidden-child.txt', 'search can resume after structural navigation')
        send(b'\r')
        wait_for('return vim.fs.basename(vim.api.nvim_buf_get_name(0))', 'hidden-child.txt', 'Enter opens matching file')
        equal(lua('return require("jetvim.tree").query'), '', 'file open clears search')
        send(b'\x1b[983041u')
        wait_for('return vim.bo.filetype', 'jetvim-tree', 'bridge relay still works after Unicode search')
        send('space name')
        wait_for('return require("jetvim.tree").query', 'space name', 'space is accepted in filename search')
        equal(selected(), 'space name.txt', 'filename with spaces found')
        escape()
        escape()
        wait_for('return vim.fs.basename(vim.api.nvim_buf_get_name(0))', 'hidden-child.txt', 'second Escape returns to editor')
        equal(lua('return vim.wo[require("jetvim.tree").win].winhighlight:find("CursorLine:JetvimTreeCursorLineInactive",1,true) ~= nil'), True, 'returning editor focus mutes sidebar selection')
        send(b'\x1b[983041u')
        wait_for('return vim.bo.filetype', 'jetvim-tree', 'sidebar refocused for creation fallback')
        send('alpha')
        wait_for('local t = require("jetvim.tree"); return t.rows[vim.api.nvim_win_get_cursor(t.win)[1]].name', 'alpha.txt', 'file selected before creation')
        escape()
        send(b'\x1b[2~')
        wait_for('return vim.fn.mode()', 'c', 'Insert retains new-file creation without plain-letter shortcuts')
        send('created.txt\r')
        wait_for('return vim.fs.basename(vim.api.nvim_buf_get_name(0))', 'created.txt', 'creation prompt opens new file')
        (project / 'nested' / 'inner').mkdir()
        (project / 'nested' / 'inner' / 'leaf.txt').write_text('nested directory fixture\n')
        lua('require("jetvim.tree").render(); return true')
        send(b'\x1b[983041u')
        wait_for('return vim.bo.filetype', 'jetvim-tree', 'sidebar refocused for nested-folder regression')
        send('inner')
        wait_for('local t=require("jetvim.tree"); return t.rows[vim.api.nvim_win_get_cursor(t.win)[1]].name', 'inner', 'nested folder found')
        send(b'\r')
        wait_for('return require("jetvim.tree").expanded[require("jetvim.project").root .. "/nested/inner"]', True, 'nested folder expanded')
        send(b'\x1b[D')
        wait_for('return not require("jetvim.tree").expanded[require("jetvim.project").root .. "/nested/inner"]', True, 'first Left closes nested folder')
        send(b'\x1b[D')
        wait_for('local t=require("jetvim.tree"); return t.rows[vim.api.nvim_win_get_cursor(t.win)[1]].name', 'nested', 'second Left on nested closed folder selects its parent')
        equal(lua('return vim.api.nvim_win_get_width(require("jetvim.tree").win)'), initial_width + 12, 'refocus and structural navigation preserve chosen width')
        send('odd')
        wait_for('local t=require("jetvim.tree"); return t.rows[vim.api.nvim_win_get_cursor(t.win)[1]].name', control_name, 'control-character filename searchable after safe startup rendering')
        equal(lua('local t=require("jetvim.tree"); return t.rows[vim.api.nvim_win_get_cursor(t.win)[1]].label'), 'odd␍↵control⇥name.txt', 'CR/newline/tab represented by visible safe glyphs')
        escape()
        send('odd␍↵')
        wait_for('return require("jetvim.tree").query', 'odd␍↵', 'search can include rendered control-character labels')
        equal(lua('local t=require("jetvim.tree"); local row=vim.api.nvim_win_get_cursor(t.win)[1]; local line=vim.api.nvim_buf_get_lines(t.buf,row-1,row,false)[1]; local found={}; for _,mark in ipairs(vim.api.nvim_buf_get_extmarks(t.buf,vim.api.nvim_create_namespace("JetvimTreeSearch"),{row-1,0},{row-1,-1},{details=true})) do found[#found+1]=line:sub(mark[3]+1,mark[4].end_col) end; return table.concat(found)'), 'odd␍↵', 'control-label search highlights valid rendered byte ranges')
        send(b'\r')
        wait_for('return vim.api.nvim_buf_get_name(0)', str(project / control_name), 'Enter opens original raw path rather than escaped display label')
        equal(lua('return vim.v.errmsg'), '', 'no editor errors')
        print(f'PASS: {checks} sidebar Speed Search checks through live PTY input')
    finally:
        if process.poll() is None:
            try:
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
        (STATE / 'sidebar-output.log').write_bytes(output)
        os.close(master)
        SOCKET.unlink(missing_ok=True)
