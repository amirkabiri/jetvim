#!/usr/bin/env python3
"""Real local gopls attachment and native Command-B test; never invokes Git."""
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
SERVER = STATE / 'tools/go/bin/gopls'
assert SERVER.exists(), 'Run ./scripts/setup-gopls.sh before this optional language-server test.'
SOCKET = STATE / f'go-lsp-{os.getpid()}.sock'
ENV = dict(os.environ, TERM='xterm-256color', JETVIM_DISABLE_VCS='1', JETVIM_DISABLE_AUTOSAVE='1')
checks = 0


def check(condition, label):
    global checks
    assert condition, label
    checks += 1


def lua(code):
    expression = "json_encode(luaeval('(function() " + code.replace("'", "''") + " end)()'))"
    result = subprocess.run([str(ROOT / 'jetvim'), '--server', str(SOCKET), '--remote-expr', expression],
                            cwd=ROOT, env=ENV, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def wait(code, label, seconds=60):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if lua(code):
            return
        time.sleep(0.08)
    raise AssertionError(label + '; see .jetvim/go-lsp-test.log and local LSP log')


with tempfile.TemporaryDirectory(prefix='go-lsp-project-', dir=STATE) as folder:
    project = Path(folder)
    (project / 'go.mod').write_text('module example.invalid/jetvim-go-test\n\ngo 1.27.0\n')
    (project / 'definitions.go').write_text('package demo\n\nfunc Greet(name string) string { return "Hello " + name }\n')
    main = ['package demo', '', 'func Message() string {', '    return Greet("Jetvim")', '}']
    (project / 'main.go').write_text('\n'.join(main) + '\n')
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 35, 140, 0, 0))
    log = (STATE / 'go-lsp-test.log').open('wb')
    process = subprocess.Popen([str(ROOT / 'jetvim'), folder, 'main.go', '--listen', str(SOCKET)],
                               cwd=ROOT, env=ENV, stdin=slave, stdout=slave, stderr=slave)
    os.close(slave)
    stop = threading.Event()

    def drain():
        pending = b''
        replies = {
            b'\x1b]10;?\x07': b'\x1b]10;rgb:bcbc/bebe/c4c4\x07',
            b'\x1b]11;?\x07': b'\x1b]11;rgb:1e1e/1f1f/2222\x07',
            b'\x1b]10;?\x1b\\': b'\x1b]10;rgb:bcbc/bebe/c4c4\x1b\\',
            b'\x1b]11;?\x1b\\': b'\x1b]11;rgb:1e1e/1f1f/2222\x1b\\',
            b'\x1b[5n': b'\x1b[0n', b'\x1b[6n': b'\x1b[1;1R',
            b'\x1b[c': b'\x1b[?1;2c', b'\x1b[?u': b'\x1b[?0u',
        }
        while not stop.is_set():
            ready, _, _ = select.select([master], [], [], 0.1)
            if not ready:
                continue
            try:
                data = os.read(master, 65536)
            except OSError:
                break
            if not data:
                break
            log.write(data)
            pending += data
            for query, answer in replies.items():
                while query in pending:
                    os.write(master, answer)
                    pending = pending.replace(query, b'', 1)
            pending = pending[-64:]

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    try:
        deadline = time.monotonic() + 10
        while not SOCKET.exists():
            assert process.poll() is None and time.monotonic() < deadline, 'editor did not start'
            time.sleep(0.03)
        wait('return vim.bo.filetype == "go"', 'Go file type was not detected')
        check(lua('return vim.lsp.is_enabled("gopls")'), 'user-enabled gopls preserved')
        check(lua('return vim.fn.exepath("gopls")') == str(SERVER), 'launcher finds local gopls')
        wait('return #vim.lsp.get_clients({bufnr=0,method="textDocument/definition"})>0', 'gopls did not attach')
        client = lua('local c=vim.lsp.get_clients({bufnr=0,method="textDocument/definition"})[1]; '
                     'return {name=c.name,root=c.config.root_dir,cmd=c.config.cmd,env=c.config.cmd_env}')
        check(client['name'] == 'gopls', 'actual gopls client attached')
        check(client['root'] == folder, 'Go workspace is the selected module')
        check(client['cmd'] == ['gopls'], 'user gopls command is unchanged')
        for key in ('GOPLSCACHE', 'GOCACHE', 'GOMODCACHE', 'GOPATH', 'GOTMPDIR', 'TMPDIR', 'TEST_TELEMETRY_DIR'):
            check(client['env'][key].startswith(str(STATE) + '/'), key + ' remains in local runtime')
        for key in ('GOENV', 'GOTELEMETRY', 'GOTOOLCHAIN'):
            check(client['env'][key] == ('local' if key == 'GOTOOLCHAIN' else 'off'), key + ' safe process setting')
        check(lua('return vim.env.GOPLSCACHE') == str(STATE / 'cache/gopls'), 'gopls process cache path local')
        col = main[3].index('Greet') + 2
        lua(f'vim.api.nvim_win_set_cursor(0,{{4,{col}}}); return true')
        wait('local c=vim.lsp.get_clients({bufnr=0,method="textDocument/definition"})[1]; '
             'if not c then return false end; '
             'local results=vim.lsp.buf_request_sync(0,"textDocument/definition",vim.lsp.util.make_position_params(0,c.offset_encoding),1000); '
             'for _,r in pairs(results or {}) do if r.result and #r.result>0 then return true end end; return false',
             'Go module was not semantically ready')
        check(True, 'real Go definition response received')
        lua('vim.cmd.startinsert(); return true')
        time.sleep(0.08)
        os.write(master, b'\x1b[98;9u')
        wait('return vim.fs.basename(vim.api.nvim_buf_get_name(0)) == "definitions.go"', 'native Command-B did not jump to Go definition')
        check(lua('return vim.api.nvim_win_get_cursor(0)[1]') == 3, 'Command-B lands on Go declaration')
        info = lua('local old=vim.notify; local message; vim.notify=function(text) message=text end; '
                   'vim.cmd("JetvimLspInfo"); vim.notify=old; return message')
        check('gopls enabled: yes' in info and str(SERVER) in info and folder in info, 'LSP info shows enabled Go server, executable and root')
        missing = lua('local old=vim.fn.exepath; vim.fn.exepath=function(name) if name=="gopls" then return "" end; return old(name) end; '
                      'local notify=vim.notify; local message; vim.notify=function(text) message=text end; vim.cmd("JetvimLspInfo"); '
                      'vim.notify=notify; vim.fn.exepath=old; return message')
        check('gopls not found' in missing and 'scripts/setup-gopls.sh' in missing, 'missing Go server diagnostic explains local setup')
        check(lua('return vim.v.errmsg') == '', 'no editor/LSP errors')
        print(f'PASS: {checks} real Go LSP checks including native PTY Command-B')
    finally:
        if process.poll() is None:
            try:
                lua('for _,c in ipairs(vim.lsp.get_clients()) do c:stop(true) end; vim.cmd("qa!"); return true')
            except Exception:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=5)
        stop.set()
        reader.join(timeout=2)
        log.close()
        os.close(master)
        SOCKET.unlink(missing_ok=True)
