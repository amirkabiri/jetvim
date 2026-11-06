#!/usr/bin/env python3
"""Validate the actual TUI theme and capture its rendered grid, without Git."""
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import shutil
import struct
import sys
import subprocess
import termios
import threading
import time

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / '.jetvim'
STATE.mkdir(exist_ok=True)
PROJECT = STATE / f'appearance-project-{os.getpid()}'
PROJECT.mkdir(exist_ok=True)
for name in ('apps', 'docs', 'packages', 'scripts', 'test'):
    (PROJECT / name).mkdir(exist_ok=True)
example = [
    '{', '  "$schema": "./node_modules/oxlint/configuration_schema.json",',
    '  "extends": [', '    "./node_modules/@example/styleguide/oxlint/rules/base.json",',
    '    "./node_modules/@example/styleguide/oxlint/rules/react.json"', '  ],',
    '  "options": {', '    "typeAware": true,', '    "respectEslintDisableDirectives": false,',
    '    "tabWidth": 2', '  },', '  "settings": {', '    "react": {', '      "version": "19"',
    '    }', '  },', '  "env": {', '    "browser": true,', '    "node": true,',
    '    "builtin": true', '  },', '  "categories": {', '    "correctness": "warn",',
    '    "suspicious": "warn",', '    "pedantic": "off"', '  },',
    '  "ignorePatterns": ["node_modules/", "dist/", "coverage/"]', '}',
]
(PROJECT / '.oxlintrc.json').write_text('\n'.join(example) + '\n')
for name, text in {'hello.jsonl': '{"type":"mode","mode":"normal"}\n',
                   'catalog-info.yaml': 'apiVersion: backstage.io/v1alpha1\n',
                   'README.md': '# Project\n', '100%done.json': '{}\n',
                   '.editorconfig': 'root = true\n', '.env.template': 'PORT=3000\n'}.items():
    (PROJECT / name).write_text(text)
SOCKET = STATE / f'appearance-{os.getpid()}.sock'
master, slave = pty.openpty()
fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 38, 132, 0, 0))
process = subprocess.Popen([str(ROOT / 'jetvim'), str(PROJECT), '--listen', str(SOCKET), '.oxlintrc.json'],
                           cwd=ROOT, stdin=slave, stdout=slave, stderr=slave,
                           env=dict(os.environ, TERM='xterm-256color', JETVIM_DISABLE_VCS='1'))
os.close(slave)
stop = threading.Event()


def drain():
    while not stop.is_set():
        readable, _, _ = select.select([master], [], [], 0.1)
        if readable:
            try:
                if not os.read(master, 65536):
                    return
            except OSError:
                return


reader = threading.Thread(target=drain, daemon=True)
reader.start()


def lua(code):
    expr = "json_encode(luaeval('(function() " + code.replace("'", "''") + " end)()'))"
    result = subprocess.run([str(ROOT / 'jetvim'), '--server', str(SOCKET), '--remote-expr', expr],
                            cwd=ROOT, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def capture(name):
    # The first private inspect call enables hlstate and invalidates cached
    # attribute IDs. Prime it before the redraw, never halfway through a frame.
    lua('pcall(vim.api.nvim__inspect_cell,1,0,0); return true')
    lua('vim.cmd("redraw!"); return true')
    time.sleep(0.05)
    grid = lua('local rows = {}; for row = 0, vim.o.lines - 1 do local cells = {}; '
               'for col = 0, vim.o.columns - 1 do local ok,cell=pcall(vim.api.nvim__inspect_cell,1,row,col); '
               'cells[#cells+1] = ok and cell or {vim.fn.screenstring(row+1,col+1), {}} end; '
               'rows[#rows+1] = cells end; return rows')
    (STATE / f'{name}-grid.json').write_text(json.dumps(grid, ensure_ascii=False))
    (STATE / f'{name}-screen.txt').write_text('\n'.join(''.join(cell[0] for cell in row) for row in grid) + '\n')
    return grid


RENDERER = r'''
import AppKit
import Foundation
let data = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
let grid = try JSONSerialization.jsonObject(with: data) as! [[[Any]]]
let cw = 8.0, ch = 19.0
let width = Int(Double(grid[0].count) * cw), height = Int(Double(grid.count) * ch)
let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: width, pixelsHigh: height,
  bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
  colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
let context = NSGraphicsContext(bitmapImageRep: bitmap)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = context
func color(_ value: Int) -> NSColor {
  return NSColor(red: CGFloat((value >> 16) & 255) / 255,
    green: CGFloat((value >> 8) & 255) / 255, blue: CGFloat(value & 255) / 255, alpha: 1)
}
for (row, cells) in grid.enumerated() {
  for (col, cell) in cells.enumerated() {
    let text = cell[0] as? String ?? " "
    let attr = cell.count > 1 ? cell[1] as? [String: Any] ?? [:] : [:]
    let bg = attr["background"] as? Int ?? 0x1e1f22
    let fg = attr["foreground"] as? Int ?? 0xbcbec4
    let x = Double(col) * cw, y = Double(height) - Double(row + 1) * ch
    color(bg).setFill()
    NSRect(x: x, y: y, width: cw, height: ch).fill()
    let font = NSFont.monospacedSystemFont(ofSize: 13, weight: attr["bold"] as? Bool == true ? .semibold : .regular)
    (text as NSString).draw(at: NSPoint(x: x, y: y + 2), withAttributes: [.font: font, .foregroundColor: color(fg)])
    if attr["underline"] as? Bool == true {
      color(attr["special"] as? Int ?? fg).setFill()
      NSRect(x: x, y: y + 1, width: cw, height: 1).fill()
    }
  }
}
NSGraphicsContext.restoreGraphicsState()
try bitmap.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: CommandLine.arguments[2]))
'''


checks = 0


def check(value, label):
    global checks
    assert value, label
    checks += 1


try:
    deadline = time.monotonic() + 10
    while not SOCKET.exists():
        assert process.poll() is None and time.monotonic() < deadline, 'editor did not start'
        time.sleep(0.03)
    time.sleep(0.7)
    os.write(master, b'\x1b')
    time.sleep(0.15)
    check(lua('return vim.v.errmsg') == '', 'clean startup')
    for group, field, expected in (
        ('Normal', 'bg', 0x1e1f22), ('JetvimTreeNormal', 'bg', 0x1b1c1e),
        ('TabLineSel', 'bg', 0x25324d), ('TabLineSel', 'sp', 0x6c95eb),
        ('JetvimPickerSelected', 'bg', 0x2d4268), ('JetvimToolNormal', 'bg', 0x1b1c1e),
        ('DiffAdd', 'bg', 0x283d30), ('jsonKeyword', 'fg', 0xc191d6),
        ('jsonString', 'fg', 0x6aab73), ('jsonNumber', 'fg', 0xcf8e6d),
        ('JetvimFileModified', 'fg', 0x6c95eb), ('JetvimFileUntracked', 'fg', 0xe06c75),
        ('JetvimFileModifiedActive', 'bg', 0x25324d), ('JetvimFileUntrackedTab', 'bg', 0x1e1f22),
    ):
        check(lua(f'return vim.api.nvim_get_hl(0,{{name="{group}"}}).{field}') == expected, f'{group} {field}')
    check(lua('return vim.fn.synIDattr(vim.fn.synIDtrans(vim.fn.synID(2,4,1)),"fg#")') == '#c191d6', 'actual JSON keys are purple')
    check(lua('return vim.fn.synIDattr(vim.fn.synIDtrans(vim.fn.synID(2,16,1)),"fg#")') == '#6aab73', 'actual JSON strings are green')
    check(lua('return vim.fn.synIDattr(vim.fn.synIDtrans(vim.fn.synID(10,17,1)),"fg#")') == '#cf8e6d', 'actual JSON numeric literal is orange')
    for filename in ('example.json', 'example.ts', 'example.py', 'example.go', 'example.md', 'generic.file'):
        check(lua(f'return vim.fn.strdisplaywidth(require("jetvim.icons").for_path("{filename}").text)') == 2, filename + ' icon width')
    check(lua('local i=require("jetvim.icons"); i.setup({icons="nerd"}); local result=i.for_path("file.json").text; '
              'i.setup({icons="portable"}); return result ~= "{}"') is True, 'Nerd Font icons are opt-in')
    lua('vim.cmd.badd("hello.jsonl"); vim.cmd.badd("catalog-info.yaml"); '
        'local buf=vim.fn.bufadd(vim.uv.cwd() .. "/100%done.json"); vim.bo[buf].buflisted=true; '
        'vim.api.nvim_set_current_buf(buf); return true')
    check('100%done.json' in lua('return vim.api.nvim_eval_statusline(vim.o.tabline,{use_tabline=true,maxwidth=vim.o.columns}).str'), 'percent filename escaped in tabline')
    text = lua('local previous=vim.api.nvim_get_current_buf(); local b=vim.api.nvim_create_buf(true,false); '
               'vim.api.nvim_buf_set_name(b,vim.uv.cwd() .. "/line\\r\\nbreak.lua"); vim.api.nvim_set_current_buf(b); '
               'local text=vim.api.nvim_eval_statusline(vim.o.tabline,{use_tabline=true,maxwidth=vim.o.columns}).str; '
               'vim.api.nvim_set_current_buf(previous); vim.api.nvim_buf_delete(b,{force=true}); return text')
    check('line␍↵break.lua' in text and '\r' not in text and '\n' not in text, 'control characters sanitized in tab labels')
    lua('vim.cmd.buffer(vim.fn.bufnr(".oxlintrc.json")); vim.bo.modified=true; return true')
    check('●' in lua('return vim.api.nvim_eval_statusline(vim.o.tabline,{use_tabline=true,maxwidth=vim.o.columns}).str'), 'modified tab indicator')
    lua('vim.bo.modified=false; local t=require("jetvim.tree"); t.focus(); vim.api.nvim_win_set_width(t.win,34); return true')
    width = lua('return vim.api.nvim_win_get_width(require("jetvim.tree").win)')
    lua('require("jetvim.theme").setup({icons="portable"}); return true')
    check(lua('return vim.api.nvim_win_get_width(require("jetvim.tree").win)') == width, 'theme never resets pane widths')
    check(lua('return vim.fs.basename(vim.api.nvim_buf_get_name(require("jetvim.theme").active_editor))') == '.oxlintrc.json', 'active editor remembered while sidebar focused')
    # Mock the shared cache getter, never execute Git from this appearance test.
    lua('require("jetvim.vcs").status = function(path) '
        'if path:match("oxlintrc%.json$") then return "modified" '
        'elseif path:match("hello%.jsonl$") then return "untracked" end end; '
        'vim.api.nvim_exec_autocmds("User",{pattern="JetvimVcsChanged"}); '
        'require("jetvim.tree").render(); return true')
    lua('require("jetvim.tree").editor(); vim.api.nvim_win_set_cursor(0,{17,9}); return true')
    grid = capture('appearance')
    check(any('Project' in ''.join(cell[0] for cell in row) for row in grid), 'project title rendered')
    check(any('{}' in ''.join(cell[0] for cell in row) for row in grid), 'portable JSON icon rendered')
    for name, expected in (('.oxlintrc.json', 0x6c95eb), ('hello.jsonl', 0xe06c75)):
        tab_text = ''.join(cell[0] for cell in grid[0])
        column = tab_text.index(name)
        check(grid[0][column][1].get('foreground') == expected, name + ' tab VCS filename color')
        tree_rows = [row for row in grid[1:] if name in ''.join(cell[0] for cell in row[:width])]
        check(bool(tree_rows), name + ' tree row present')
        tree_text = ''.join(cell[0] for cell in tree_rows[0])
        check(tree_rows[0][tree_text.index(name)][1].get('foreground') == expected, name + ' tree VCS filename color')
    lua('require("jetvim.ui").pick("Find Action",{"Go to File", "Git Changes", "Reformat Code"},function() end); return true')
    time.sleep(0.1)
    check(lua('local ns=vim.api.nvim_get_namespaces().JetvimPickerAppearance; '
              'for _,b in ipairs(vim.api.nvim_list_bufs()) do '
              'if #vim.api.nvim_buf_get_extmarks(b,ns,0,-1,{})>0 then return true end end; return false'), 'picker selected row highlighted')
    os.write(master, b'\x1b')
    time.sleep(0.1)
    check(lua('return vim.v.errmsg') == '', 'no renderer or picker errors')
    print(f'PASS: {checks} appearance checks; real TUI grid capture in .jetvim/appearance-grid.json')
    if sys.platform == 'darwin' and shutil.which('swiftc'):
        source, binary = STATE / 'render-appearance.swift', STATE / 'render-appearance'
        source.write_text(RENDERER)
        cache = STATE / 'cache/swift'
        cache.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, TMPDIR=str(STATE / 'tmp'), CLANG_MODULE_CACHE_PATH=str(cache), SWIFT_MODULECACHE_PATH=str(cache))
        subprocess.run(['swiftc', '-module-cache-path', str(cache), str(source), '-o', str(binary)], check=True, env=env)
        for name in ('appearance',):
            subprocess.run([str(binary), str(STATE / f'{name}-grid.json'), str(STATE / f'{name}.png')], check=True, env=env)
        print('Rendered .jetvim/appearance.png from actual TUI cells.')
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
    os.close(master)
    SOCKET.unlink(missing_ok=True)
