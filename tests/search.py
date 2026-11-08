#!/usr/bin/env python3
"""Exercise literal/regex inline search and project search through PTY keys."""
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
SOCKET = STATE / f'search-{os.getpid()}.sock'
master, slave = pty.openpty()
fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 120, 0, 0))
stop = threading.Event()
checks = 0


def drain():
    while not stop.is_set():
        ready, _, _ = select.select([master], [], [], 0.1)
        if ready:
            try:
                if not os.read(master, 65536):
                    break
            except OSError:
                break


def lua(code):
    expr = "json_encode(luaeval('(function() " + code.replace("'", "''") + " end)()'))"
    result = subprocess.run([str(ROOT / 'jetvim'), '--server', str(SOCKET), '--remote-expr', expr],
                            cwd=ROOT, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def equal(actual, expected, label):
    global checks
    assert actual == expected, f'{label}: expected {expected!r}, got {actual!r}'
    checks += 1


def keys(value):
    lua('return vim.api.nvim_input(' + json.dumps(value, ensure_ascii=False) + ')')
    time.sleep(0.06)


def raw(value):
    os.write(master, value)
    time.sleep(0.15)


def clear_highlights(label):
    equal(lua('return vim.v.hlsearch'),0,label+' clears native highlight state')
    equal(lua('return vim.o.hlsearch'),True,label+' keeps hlsearch preference enabled')
    equal(lua('local s=require("jetvim.search"); return #vim.api.nvim_buf_get_extmarks(s.source,vim.api.nvim_get_namespaces().JetvimSearch,0,-1,{})'),0,label+' clears custom search marks')
    lua('pcall(vim.api.nvim__inspect_cell,1,0,0); vim.cmd("redraw!"); return true')
    time.sleep(.06)
    equal(lua('local s=require("jetvim.search"); local search=vim.api.nvim_get_hl(0,{name="Search",link=false}); local active=vim.api.nvim_get_hl(0,{name="IncSearch",link=false}); '
              'for _,column in ipairs({1,7,13}) do local p=vim.fn.screenpos(s.owner,1,column); local cell=vim.api.nvim__inspect_cell(1,p.row-1,p.col-1); '
              'local bg=cell[2].background; if bg and (bg==search.bg or bg==active.bg) then return false end end; return true'),True,label+' actual TUI text cells have no search background')



with tempfile.TemporaryDirectory(prefix='search-project-', dir=STATE) as directory:
    project = Path(directory)
    content = ['hello HELLO hello', 'world', 'héllo hello', 'last hello']
    (project / 'main.txt').write_text('\n'.join(content) + '\n')
    process = subprocess.Popen([str(ROOT / 'jetvim'), directory, 'main.txt', '--listen', str(SOCKET)],
                               cwd=ROOT, stdin=slave, stdout=slave, stderr=slave,
                               env=dict(os.environ, TERM='xterm-256color', JETVIM_DISABLE_VCS='1', JETVIM_DISABLE_AUTOSAVE='1'))
    os.close(slave)
    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    try:
        deadline = time.monotonic() + 10
        while not SOCKET.exists():
            assert process.poll() is None and time.monotonic() < deadline, 'editor did not start'
            time.sleep(0.03)
        time.sleep(0.5)
        lua('vim.g.search_owner=vim.api.nvim_get_current_win(); vim.g.search_source=vim.api.nvim_get_current_buf(); return true')
        windows = lua('return #vim.api.nvim_list_wins()')
        widths = lua('return {vim.api.nvim_win_get_width(0), vim.api.nvim_win_get_width(require("jetvim.tree").win)}')
        raw(b'\x1b[102;9u')
        equal(lua('return vim.bo.filetype'), 'jetvim-search', 'native CommandF focuses inline input')
        equal(lua('local s=require("jetvim.search"); local c=vim.api.nvim_win_get_config(s.win); return {c.relative,c.win,c.row,c.height}'),
              ['win', lua('return vim.g.search_owner'), 0, 1], 'one row at top of active editor')
        raw(b'hello')
        equal(lua('return #require("jetvim.search").matches'), 5, 'plain text matches case-insensitively')
        equal(lua('return vim.api.nvim_buf_get_lines(vim.g.search_source,0,-1,false)'), content, 'query never edits source')
        equal(lua('return vim.api.nvim_win_get_cursor(vim.g.search_owner)'), [1,0], 'initial match at caret')
        raw(b'\r')
        equal(lua('return vim.api.nvim_win_get_cursor(vim.g.search_owner)'), [1,6], 'Enter advances while field remains open')
        keys('<S-CR>')
        equal(lua('return vim.api.nvim_win_get_cursor(vim.g.search_owner)'), [1,0], 'Shift Enter goes backwards')
        raw(b'\x1b[103;9u')
        equal(lua('return vim.api.nvim_win_get_cursor(vim.g.search_owner)'), [1,6], 'CommandG advances while input focused')
        equal(lua('return vim.fn.mode()'), 'i', 'CommandG preserves search input typing')
        raw(b'\x1b[103;10u')
        equal(lua('return vim.api.nvim_win_get_cursor(vim.g.search_owner)'), [1,0], 'CommandShiftG moves backwards in input')
        keys('<C-u>')
        raw(b'/hello/i')
        equal(lua('return #require("jetvim.search").matches'), 5, 'slash regex i flag ignores case')
        keys('<C-u>')
        raw(b'h(ello|i)')
        equal(lua('return #require("jetvim.search").matches'), 0, 'bare grouping characters are literal')
        keys('<C-u>')
        raw(b'/h(ello|i)/')
        equal(lua('return #require("jetvim.search").matches'), 4, 'regex grouping and alternatives')
        keys('<C-u>')
        raw(b'[')
        equal(lua('return require("jetvim.search").error'), None, 'bare bracket is valid literal text')
        equal(lua('return #require("jetvim.search").matches'), 0, 'bare bracket never starts a regex')
        keys('<C-u>')
        raw(b'/[/')
        equal(lua('return require("jetvim.search").error ~= nil'), True, 'invalid regex handled inline')
        equal(lua('return vim.api.nvim_buf_get_lines(require("jetvim.search").status_buf,0,1,false)[1]:find("Invalid regex",1,true) ~= nil'), True, 'invalid regex visible status')
        equal(lua('return vim.v.errmsg'), '', 'invalid regex never opens error prompt')
        keys('<C-u>')
        raw(b'/hello/g')
        equal(lua('return require("jetvim.search").error:find("Invalid regex flag",1,true) ~= nil'), True, 'unsupported flags visible')
        keys('<C-u>')
        raw(b'/^/')
        equal(lua('return #require("jetvim.search").matches'), 4, 'zero width regex terminates and matches line starts')
        keys('<C-u>')
        raw('héllo'.encode())
        equal(lua('return #require("jetvim.search").matches'), 1, 'UTF8 literal matches without byte corruption')
        lua('local s=require("jetvim.search"); vim.api.nvim_win_set_width(s.owner,vim.api.nvim_win_get_width(s.owner)-5); return true')
        time.sleep(0.15)
        equal(lua('local s=require("jetvim.search"); return vim.api.nvim_win_get_width(s.win)+vim.api.nvim_win_get_width(s.status_win)==vim.api.nvim_win_get_width(s.owner)'), True, 'search bar follows editor resize')
        lua('vim.api.nvim_win_set_width(require("jetvim.search").owner,' + str(widths[0]) + '); return true')
        keys('<C-u>')
        raw(b'hello')
        keys('<CR>')
        equal(lua('return vim.v.hlsearch'),1,'plain query exercises native highlighting before close')
        keys('<Esc>')
        time.sleep(0.1)
        clear_highlights('plain Escape')
        equal(lua('return vim.fn.getreg("/")'),r'\c\Vhello','closing preserves literal ignore-case search pattern')
        equal(lua('return vim.api.nvim_get_current_win()'), lua('return vim.g.search_owner'), 'Escape returns editor focus')
        equal(lua('return vim.api.nvim_win_get_cursor(vim.g.search_owner)'), [1,6], 'Escape keeps selected match caret')
        equal(lua('return #vim.api.nvim_list_wins()'), windows, 'no leaked search windows')
        equal(lua('return {vim.api.nvim_win_get_width(0),vim.api.nvim_win_get_width(require("jetvim.tree").win)}'), widths, 'search preserves split dimensions')
        equal(lua('local n=0; for _,b in ipairs(vim.api.nvim_list_bufs()) do if vim.bo[b].filetype=="jetvim-search" then n=n+1 end end; return n'), 0, 'no leaked search buffers')
        lua('vim.api.nvim_win_set_cursor(0,{1,6}); return true')
        raw(b'\x1b[103;9u')
        equal(lua('return vim.api.nvim_win_get_cursor(vim.g.search_owner)'), [1,12], 'CommandG continues after close')
        bindings=json.loads((ROOT/'config/keymap.json').read_text())
        index=next(i for i,item in enumerate(bindings,1) if item['id']=='find')
        raw(f'\x1b[{0xF0000+index}u'.encode())
        equal(lua('return vim.bo.filetype'), 'jetvim-search', 'relay CommandF opens inline input')
        keys('<C-u>');raw(b'/hello/i')
        equal(lua('return #require("jetvim.search").matches'),5,'reopened regex still finds case-insensitive matches')
        keys('<Esc>')
        clear_highlights('regex Escape')
        equal(lua('return vim.fn.getreg("/")'),r'\c\vhello','closing preserves regex and ignore-case flag')
        equal(lua('return vim.fn.mode()'),'i','closing regex preserves editor typing')
        raw(b'\x1b[103;10u')
        equal(lua('return vim.api.nvim_win_get_cursor(vim.g.search_owner)'),[1,6],'CommandShiftG navigates retained case-insensitive pattern')
        # Both entry routes use literal text unless balanced slashes opt into
        # regex. Backslashes must not smuggle Vim's magic/case switches through.
        literal_content = ['hello world | HELLO WORLD', 'a.b aXb A.B', '[ ] ^ $ (x|y) x+y? {2} *',
                           r'path/foo C:\Temp\file \C \c \v \V', 'ÄPFEL äpfel', 'slash /open']
        lua('vim.api.nvim_buf_set_lines(vim.g.search_source,0,-1,false,vim.json.decode('+json.dumps(json.dumps(literal_content))+'));'
            '_G.SearchOriginalCase={vim.o.ignorecase,vim.o.smartcase};vim.o.ignorecase=false;vim.o.smartcase=true;return true')
        raw(f'\x1b[{0xF0000+index}u'.encode())
        cases = [('hello world',2), ('HELLO WORLD',2), ('a.b',2), ('[ ]',1), ('^ $',1),
                 ('(x|y)',1), ('x+y?',1), ('{2}',1), ('*',1), (r'C:\Temp\file',1),
                 (r'\C',2), (r'\c',2), (r'\v',2), (r'\V',2), ('äpfel',2), ('/open',1),
                 ('path/foo',1), ('/path\\/foo/',1), ('/a.b/',2), ('/a.b/i',3),
                 ('/hello world/',1), ('/HELLO WORLD/',1), ('/hello world/i',2)]
        for text, count in cases:
            keys('<C-u>'); raw(text.encode())
            equal(lua('return #require("jetvim.search").matches'),count,'text/regex semantics: '+text)
            equal(lua('return require("jetvim.search").error'),None,'valid literal or regex query: '+text)
            equal(lua('return vim.fn.mode()'),'i','search typing remains active')
        equal(lua('return vim.api.nvim_buf_get_lines(vim.g.search_source,0,-1,false)'),literal_content,'all literal/regex query input leaves source unchanged')
        keys('<C-u>')
        equal(lua('local s=require("jetvim.search");return vim.api.nvim_buf_get_lines(s.status_buf,0,1,false)[1]:find("Text",1,true)~=nil'),True,'empty search advertises text and slash-regex modes')
        keys('<Esc>'); clear_highlights('literal/regex table Escape')
        lua('vim.o.ignorecase=_G.SearchOriginalCase[1];vim.o.smartcase=_G.SearchOriginalCase[2];return true')
        equal((project/'main.txt').read_text(),'\n'.join(content)+'\n','query tests never write source file')
        # Find in Files must route from tree, rather than becoming speed-search text.
        lua('require("jetvim.tree").focus(); return true')
        lua('_G.search_original_executable=vim.fn.executable; vim.fn.executable=function(name) if name=="rg" then return 0 end; return _G.search_original_executable(name) end; return true')
        raw(b'\x1b[102;10u')
        equal(lua('return vim.bo.filetype'), 'jetvim-project-search', 'native CommandShiftF opens focused project modal from tree')
        keys('<Esc>')
        lua('require("jetvim.tree").focus(); return true')
        raw(b'mai')
        raw(b'\x1b[70;9u')
        equal(lua('return vim.bo.filetype'), 'jetvim-project-search', 'capital-letter native CommandShiftF routes during tree speed search')
        keys('<Esc>')
        lua('require("jetvim.tree").focus(); return true')
        index=next(i for i,item in enumerate(bindings,1) if item['id']=='find_project')
        raw(f'\x1b[{0xF0000+index}u'.encode())
        equal(lua('return vim.bo.filetype'), 'jetvim-project-search', 'relay CommandShiftF opens focused project modal from tree')
        keys('<Esc>')
        equal(lua('return require("jetvim.tree").query'), '', 'project shortcut never adds tree search text')
        lua('vim.fn.executable=_G.search_original_executable; return true')
        equal(lua('return vim.v.errmsg'), '', 'clean error state')
        print(f'PASS: {checks} search and project shortcut checks')
    finally:
        subprocess.run([str(ROOT/'jetvim'),'--server',str(SOCKET),'--remote-send','<Esc>:qa!<CR>'], cwd=ROOT,capture_output=True)
        try: process.wait(timeout=4)
        except subprocess.TimeoutExpired: process.kill(); process.wait()
        stop.set(); reader.join(timeout=1); os.close(master)
        if SOCKET.exists(): SOCKET.unlink()
