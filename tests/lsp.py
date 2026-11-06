#!/usr/bin/env python3
"""Verify local TypeScript dependencies, actual attachment, and Command-B."""
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / '.jetvim'
PROJECT = STATE / f'lsp-project-{os.getpid()}'
PROJECT.mkdir(parents=True, exist_ok=True)
SERVER = STATE / 'tools/typescript/node_modules/.bin/typescript-language-server'
assert SERVER.exists(), 'Run ./scripts/setup-typescript.sh before the optional language-server test.'
(PROJECT / 'tsconfig.json').write_text(json.dumps({'compilerOptions': {'strict': True, 'target': 'ES2022', 'module': 'ESNext'}, 'include': ['*.ts']}))
(PROJECT / 'definitions.ts').write_text('export function greet(name: string): string {\n  return `Hello ${name}`;\n}\n')
main_lines = ['import { greet } from "./definitions";', '', 'const message = greet("Jetvim");', 'console.log(message);']
(PROJECT / 'main.ts').write_text('\n'.join(main_lines) + '\n')
SOCKET = STATE / f'lsp-{os.getpid()}.sock'
checks = 0


def lua(code):
    expr = "json_encode(luaeval('(function() " + code.replace("'", "''") + " end)()'))"
    result = subprocess.run([str(ROOT / 'jetvim'), '--server', str(SOCKET), '--remote-expr', expr],
                            cwd=ROOT, capture_output=True, text=True, timeout=10,
                            env=dict(os.environ, JETVIM_DISABLE_VCS='1'))
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def check(value, label):
    global checks
    assert value, label
    checks += 1


def wait(code, label, seconds=20):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if lua(code):
            return
        time.sleep(0.08)
    raise AssertionError(label + '; see .jetvim/lsp-test.log and .jetvim/state/jetvim/lsp.log')


log = (STATE / 'lsp-test.log').open('w')
process = subprocess.Popen([str(ROOT / 'jetvim'), str(PROJECT), '--headless', '--listen', str(SOCKET), 'main.ts'],
                           cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                           env=dict(os.environ, JETVIM_DISABLE_VCS='1'))
try:
    deadline = time.monotonic() + 10
    while not SOCKET.exists():
        assert process.poll() is None and time.monotonic() < deadline, 'editor did not start'
        time.sleep(0.03)
    check(lua('return vim.bo.filetype') == 'typescript', 'TypeScript file type detected')
    check(lua('return vim.lsp.is_enabled("ts_ls")') is True, 'user-enabled ts_ls preserved')
    check(lua('return vim.fn.exepath("typescript-language-server")').startswith(str(STATE / 'tools/typescript/')), 'launcher exposes local server executable')
    wait('return #vim.lsp.get_clients({bufnr=0,method="textDocument/definition"}) > 0', 'TypeScript server did not attach')
    check(True, 'actual language server attached')
    client = lua('local c=vim.lsp.get_clients({bufnr=0,method="textDocument/definition"})[1]; '
                 'return {name=c.name,root=c.config.root_dir,options=c.config.init_options,cmd=c.config.cmd}')
    check(client['name'] == 'ts_ls', 'expected server client')
    check(client['root'] == str(PROJECT), 'server workspace is the selected project')
    check(client['options']['disableAutomaticTypingAcquisition'] is True, 'global automatic typing downloads disabled')
    check(client['options']['tsserver']['logDirectory'].startswith(str(STATE)), 'TypeScript log path stays local')
    check(client['options']['tsserver']['fallbackPath'].startswith(str(STATE / 'tools/typescript/')), 'local TypeScript fallback is configured')
    check(client['cmd'] == ['typescript-language-server', '--stdio'], 'user command remains unchanged')
    lua(f'vim.api.nvim_win_set_cursor(0,{{3,{main_lines[2].index("greet") + 2}}}); return true')
    wait('local c=vim.lsp.get_clients({bufnr=0,method="textDocument/definition"})[1]; '
         'if not c then return false end; '
         'local result=vim.lsp.buf_request_sync(0,"textDocument/definition",vim.lsp.util.make_position_params(0,c.offset_encoding),1000); '
         'for _,response in pairs(result or {}) do if response.result and #response.result>0 then return true end end; return false',
         'TypeScript project did not become semantically ready')
    check(True, 'actual TypeScript semantic definition is ready')
    lua(f'vim.api.nvim_win_set_cursor(0,{{3,{main_lines[2].index("greet") + 2}}}); return vim.api.nvim_input("i<D-b>")')
    wait('return vim.fs.basename(vim.api.nvim_buf_get_name(0)) == "definitions.ts"', 'Command-B did not jump to definition')
    check(lua('return vim.api.nvim_win_get_cursor(0)[1]') == 1, 'Command-B lands on function declaration')
    # At the declaration Command-B becomes a usage list, including the call in main.ts.
    lua('return vim.api.nvim_input("<D-b>")')
    wait('return vim.bo.buftype == "prompt"', 'Command-B on declaration did not open usages picker')
    check(True, 'Command-B on declaration opens usages list')
    wait('for _,b in ipairs(vim.api.nvim_list_bufs()) do if vim.api.nvim_buf_is_loaded(b) then '
         'for _,line in ipairs(vim.api.nvim_buf_get_lines(b,0,-1,false)) do '
         'if line:find("main.ts:3:",1,true) then return true end end end end;return false',
         'usages picker did not contain actual TypeScript call')
    check(True, 'actual server reference appears in usages list')
    lua('return vim.api.nvim_input("main.ts:3:<CR>")')
    wait('return vim.fs.basename(vim.api.nvim_buf_get_name(0)) == "main.ts" and vim.api.nvim_win_get_cursor(0)[1] == 3',
         'selecting usage did not navigate back to call')
    check(True, 'selecting real usage returns to its call site')
    info = lua('local old=vim.notify; local message; vim.notify=function(text) message=text end; '
               'vim.cmd("JetvimLspInfo"); vim.notify=old; return message')
    check('ts_ls' in info and str(SERVER) in info, 'language diagnostics show attached server and local executable')
    check(lua('return vim.v.errmsg') == '', 'no editor/LSP startup errors')
    print(f'PASS: {checks} real TypeScript checks, including server attachment and Command-B definition navigation')
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
    log.close()
    SOCKET.unlink(missing_ok=True)
