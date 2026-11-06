#!/usr/bin/env python3
"""Validate structural selection through a real Neovim input/event loop."""
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / '.jetvim'
STATE.mkdir(exist_ok=True)
SOCKET = STATE / f'selection-{os.getpid()}.sock'
checks = 0


def lua(code):
    expression = "json_encode(luaeval('(function() " + code.replace("'", "''") + " end)()'))"
    result = subprocess.run([str(ROOT / 'jetvim'), '--server', str(SOCKET), '--remote-expr', expression],
                            cwd=ROOT, capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return json.loads(result.stdout)


def check(condition, label):
    global checks
    assert condition, label
    checks += 1


def equal(actual, expected, label):
    check(actual == expected, f'{label}: expected {expected!r}, got {actual!r}')


def keys(value):
    lua('return vim.api.nvim_input(' + json.dumps(value, ensure_ascii=False) + ')')
    time.sleep(0.025)


def fixture(lines, filetype, row=1, col=0):
    keys('<Esc>')
    lua('vim.cmd.enew({ bang = true }); vim.api.nvim_buf_set_name(0, vim.env.JETVIM_ROOT .. "/.jetvim/selection-fixture-" .. vim.fn.getpid() .. "-" .. vim.api.nvim_get_current_buf()); '
        'vim.cmd("noautocmd setlocal filetype=' + filetype + '"); '
        'vim.api.nvim_buf_set_lines(0, 0, -1, false, vim.json.decode(' + json.dumps(json.dumps(lines)) + ')); '
        f'vim.api.nvim_win_set_cursor(0, {{{row}, {col}}}); return true')
    return lua('return vim.api.nvim_get_current_buf()')


def selection():
    return lua('local s = require("jetvim.edit").selection(); if not s then return vim.NIL end; return {range=s,text=table.concat(vim.api.nvim_buf_get_text(0,s[1],s[2],s[3],s[4],{}), "\\n")}')


def expansions(limit=24):
    steps = []
    for _ in range(limit):
        keys('<M-Up>')
        current = selection()
        check(current is not None, 'extend must create a selection')
        if steps and steps[-1] == current:
            return steps
        if steps:
            a, b = steps[-1]['range'], current['range']
            check(tuple(b[:2]) <= tuple(a[:2]) and tuple(b[2:]) >= tuple(a[2:]), 'each step must contain previous selection')
            check(b != a, 'each step must strictly grow')
        steps.append(current)
    raise AssertionError('selection did not saturate')


log = (STATE / 'selection.log').open('w')
process = subprocess.Popen([str(ROOT / 'jetvim'), '--headless', '--listen', str(SOCKET)], cwd=ROOT,
                           stdin=subprocess.DEVNULL, stdout=log, stderr=log)
try:
    deadline = time.monotonic() + 10
    while not SOCKET.exists():
        if process.poll() is not None or time.monotonic() > deadline:
            raise RuntimeError('Editor did not start; see .jetvim/selection.log')
        time.sleep(0.03)
    equal(lua('return vim.v.errmsg'), '', 'clean startup')
    lua('_G.JetvimTestParser = vim.treesitter.get_parser; vim.treesitter.get_parser = function() return nil end; return true')
    source = ['package main', '', 'func main() {', '  if ready {', '    print(target, "}") // ignored }', '    next()', '  }', '}', '', 'var after = 1']
    fixture(source, 'go', row=5, col=12)
    keys('i')
    steps = expansions()
    equal(steps[0]['text'], 'target', 'word first')
    texts = [step['text'] for step in steps]
    check('target, "}"' in texts, 'argument expression expansion')
    check('if ready {\n    print(target, "}") // ignored }\n    next()\n  }' in texts, 'enclosing if block ignores braces in strings/comments')
    check('func main() {\n  if ready {\n    print(target, "}") // ignored }\n    next()\n  }\n}' in texts, 'enclosing function block')
    equal(steps[-1]['text'], '\n'.join(source), 'eventually whole buffer')
    equal(lua('return #require("jetvim.selection").states[vim.api.nvim_get_current_buf()].history'), len(steps), 'saturation does not duplicate history')
    for expected in reversed(steps[:-1]):
        keys('<M-Down>')
        equal(selection(), expected, 'shrink reverses exact expansion')
    keys('<M-Down>')
    equal(selection(), None, 'shrink restores caret')
    equal(lua('return vim.api.nvim_win_get_cursor(0)'), [5, 12], 'exact original caret restored')
    equal(lua('return vim.fn.mode()'), 'i', 'shrink returns typing mode')
    keys('<M-Down>')
    equal(lua('return vim.api.nvim_win_get_cursor(0)'), [5, 12], 'extra shrink is harmless')
    raw_go = ['func main() {', '  path := `C:\\`', '  if ready {', '    consume(target)', '  }', '}', 'var after = 1']
    fixture(raw_go, 'go', row=4, col=14)
    texts = [step['text'] for step in expansions()]
    check('if ready {\n    consume(target)\n  }' in texts, 'Go raw string trailing backslash does not escape backtick')
    # Python fallback follows indentation and includes elif/else as one outer block.
    python = ['def outer():', '    if ready:', '        target(value)', '        next_step()', '    else:', '        fallback()', '    after()', '', 'def sibling():', '    pass']
    fixture(python, 'python', row=3, col=10)
    steps = expansions()
    texts = [step['text'] for step in steps]
    check('if ready:\n        target(value)\n        next_step()\n    else:\n        fallback()' in texts, 'Python conditional with else is one block')
    check('\n'.join(python[:7]) in texts, 'Python enclosing function')
    check(not any('def sibling' in text and text != '\n'.join(python) for text in texts), 'Python blocks do not grow into sibling lines')
    # Compact JSONL must traverse objects rather than select arbitrary prefixes.
    jsonl = ['{"outer":{"inner":{"value":42},"peer":true},"other":0}', '{"unrelated":true}']
    fixture(jsonl, 'json', col=jsonl[0].index('value') + 2)
    steps = expansions()
    texts = [step['text'] for step in steps]
    check('{"value":42}' in texts, 'compact JSON inner object')
    check('{"inner":{"value":42},"peer":true}' in texts, 'compact JSON middle object')
    check(jsonl[0] in texts, 'compact JSON outer object')
    check(not any(text.startswith('{"outer":') and text != jsonl[0] and text != '\n'.join(jsonl) for text in texts), 'no malformed JSON prefix selection')
    fixture(['function outer() {', '  const pattern = /[{}]/;', '  if (ready) {', '    consume(target); // }', '  }', '}', 'const after = 1;'], 'javascript', row=4, col=14)
    texts = [step['text'] for step in expansions()]
    check('if (ready) {\n    consume(target); // }\n  }' in texts, 'regex/comment braces do not corrupt JS blocks')
    check('function outer() {\n  const pattern = /[{}]/;\n  if (ready) {\n    consume(target); // }\n  }\n}' in texts, 'JS regex literal is skipped structurally')
    # Lua fallback understands end-delimited blocks and long strings/comments.
    lua_lines = ['local function outer()', '  if ready then', '    print(target)', '    local s = [=[ end } ]=]', '    --[[ end if while ]]', '    next_step()', '  end', 'end', '', 'local unrelated = 1']
    fixture(lua_lines, 'lua', row=3, col=11)
    steps = expansions()
    texts = [step['text'] for step in steps]
    check('\n'.join(lua_lines[1:7]).lstrip() in texts, 'Lua fallback if/end block')
    check('\n'.join(lua_lines[:8]) in texts, 'Lua fallback function/end block')
    check(not any(text.startswith('outer()') for text in texts), 'Lua function body excludes its name and parameters')
    ordinary_comment = ['local function outer()', '  -- ordinary comment with later --[[', '  if ready then', '    print(target)', '  end', 'end', 'local after = 1']
    fixture(ordinary_comment, 'lua', row=4, col=11)
    texts = [step['text'] for step in expansions()]
    check('if ready then\n    print(target)\n  end' in texts, 'Lua long comment opener must be contiguous at start')
    # Unicode names use byte-exact ranges, not ASCII byte scanning.
    fixture(['const café = "hello";', 'const later = 1;'], 'javascript', col=len('const ca'.encode()))
    keys('i<M-Up>')
    equal(selection()['text'], 'café', 'Unicode identifier')
    keys('<M-Down>')
    equal(lua('return vim.api.nvim_win_get_cursor(0)'), [1, len('const ca'.encode())], 'Unicode caret restore')
    # History must never migrate to another buffer or survive edits/manual changes.
    old = fixture(['first_word', 'tail'], 'text', col=3)
    keys('<M-Up><M-Up>')
    new = fixture(['second_word', 'end'], 'text', col=2)
    keys('<M-Down>')
    equal(selection(), None, 'different buffer has no stale selection history')
    keys('<M-Up>')
    lua('vim.api.nvim_buf_set_lines(0, 1, 2, false, {"changed"}); return true')
    before = selection()
    keys('<M-Down>')
    equal(selection(), before, 'edits invalidate shrink history')
    fixture(['alpha beta', 'tail'], 'text', col=1)
    keys('<M-Up>')
    keys('<S-Right>')
    before = selection()
    keys('<M-Down>')
    equal(selection(), before, 'manual selection invalidates shrink history')
    fixture(['alpha beta', 'tail'], 'text', col=1)
    keys('<M-Up>')
    lua('vim.cmd("noautocmd setlocal filetype=python"); return true')
    before = selection()
    keys('<M-Down>')
    equal(selection(), before, 'filetype change invalidates shrink history')
    # Restore installed parser path and verify syntax-aware expression parents.
    lua('vim.treesitter.get_parser = _G.JetvimTestParser; return true')
    fixture(['local result = first + second', 'return result'], 'lua', col=17)
    available = lua('local ok,p = pcall(vim.treesitter.get_parser,0,nil,{error=false}); return ok and p ~= nil')
    check(available, 'bundled Lua parser is available for syntax path')
    steps = expansions()
    check('first + second' in [step['text'] for step in steps], 'Tree-sitter binary expression expansion')
    equal(lua('return vim.v.errmsg'), '', 'no editor errors')
    print(f'PASS: {checks} structural selection checks (fallback and installed Tree-sitter parser)')
finally:
    if process.poll() is None:
        try:
            lua('vim.cmd("qa!"); return true')
        except (AssertionError, subprocess.SubprocessError, json.JSONDecodeError):
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)
    log.close()
    SOCKET.unlink(missing_ok=True)
