#!/usr/bin/env python3
"""Native/relay clipboard paste into child PTYs, with no OS clipboard access."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
support = {'__file__': str(ROOT / 'tests/autosave.py')}
exec((ROOT / 'tests/autosave.py').read_text().split('\nwith tempfile.TemporaryDirectory', 1)[0], support)
Editor, equal, STATE = support['Editor'], support['equal'], support['STATE']


with tempfile.TemporaryDirectory(prefix='terminal-paste-', dir=STATE) as directory:
    project = Path(directory)
    (project / 'home').mkdir()
    (project / 'main.lua').write_text('-- editor stays unchanged\n')
    capture = project / 'capture.py'
    capture.write_text('''import os,sys,tty
from pathlib import Path
tty.setraw(0)
if sys.argv[2] == 'bracketed': os.write(1,b'\\x1b[?2004h')
os.write(1,b'paste-ready\\r\\n')
data=b''
while b'\\x1e' not in data: data += os.read(0,65536)
Path(sys.argv[1]).write_bytes(data.split(b'\\x1e',1)[0])
''')
    shell = project / 'readline.sh'
    shell.write_text('''#!/usr/bin/env bash
IFS= read -e -r -p 'paste-fixture> ' line
printf '%s' "$line" > "$1"
''')
    editor = Editor(project, project / 'home/settings.lua', disabled=True, disable_lsp=True)
    def lua(code): return editor.lua(code)
    def clipboard(lines, kind='v'):
        lua('_G.JetvimPasteClipboard={' +
            'vim.json.decode(' + json.dumps(json.dumps(lines, ensure_ascii=False), ensure_ascii=False) + '),' + json.dumps(kind) + '};return true')
    def start(argv, prompt='paste-ready'):
        lua('vim.cmd.stopinsert(); return true')
        time.sleep(.04)
        lua('require("jetvim.tree").editor();vim.api.nvim_set_current_buf(vim.g.JetvimPasteSource);'
            'vim.cmd.enew();vim.fn.jobstart(vim.json.decode(' + json.dumps(json.dumps(argv)) + '),{term=true});'
            'vim.cmd.startinsert();return true')
        # Seeing output after the bracketed-paste escape proves Nvim parsed it.
        editor.wait('return table.concat(vim.api.nvim_buf_get_lines(0,0,-1,false),"\\n"):find(' + json.dumps(prompt) + ',1,true) ~= nil')
        equal(lua('return vim.fn.mode()'), 't', 'child terminal input active')
        return lua('return {win=vim.api.nvim_get_current_win(),buf=vim.api.nvim_get_current_buf()}')
    def result(path):
        deadline = time.monotonic() + 5
        while not path.exists():
            if time.monotonic() > deadline: raise AssertionError('child did not create ' + path.name)
            time.sleep(.03)
        return path.read_bytes()
    try:
        lua('vim.g.JetvimPasteSource=vim.api.nvim_get_current_buf();'
            'vim.g.clipboard={name="Jetvim paste fixture",copy={'
            '["+"]=function() end,["*"]=function() end},paste={'
            '["+"]=function() return _G.JetvimPasteClipboard end,'
            '["*"]=function() return _G.JetvimPasteClipboard end},cache_enabled=0};'
            'vim.g.loaded_clipboard_provider=nil;vim.cmd("runtime autoload/provider/clipboard.vim");return true')
        equal(lua('return vim.fn.has("clipboard")'), 1, 'mock clipboard provider available without touching OS clipboard')
        lua('vim.fn.setreg(string.char(34),{"unnamed must not leak"},"v");return true')
        bindings = json.loads((ROOT / 'config/keymap.json').read_text())
        index = next(i for i, item in enumerate(bindings, 1) if item['id'] == 'paste')
        variants = [('native CmdV', b'\x1b[118;9u'), ('bridge CmdV', f'\x1b[{0xF0000+index}u'.encode())]
        cases = [
            ('Unicode', ['hello 世界 👋'], 'v', 'hello 世界 👋'),
            ('multiline', ['first', 'second'], 'v', 'first\nsecond'),
            ('trailing newline', ['first', ''], 'v', 'first\n'),
            ('linewise', ['first', 'second'], 'V', 'first\nsecond\n'),
            ('literal space', [' '], 'v', ' '),
            ('empty clipboard', [''], 'v', ''),
        ]
        for number, (label, chord) in enumerate(variants):
            for case_number, (case, lines, kind, expected) in enumerate(cases):
                clipboard(lines, kind)
                path = project / f'capture-{number}-{case_number}.bytes'
                origin = start([sys.executable, str(capture), str(path), 'bracketed'])
                editor.raw(chord)
                equal(lua('return vim.fn.mode()'), 't', label + ' keeps terminal input for ' + case)
                equal(lua('return {win=vim.api.nvim_get_current_win(),buf=vim.api.nvim_get_current_buf()}'), origin,
                      label + ' preserves terminal focus for ' + case)
                editor.raw(b'X\x1e')
                framed = ('\x1b[200~' + expected + '\x1b[201~') if expected else ''
                equal(result(path), (framed + 'X').encode(), label + ' pastes exact bracketed ' + case + ' without added spaces')
            clipboard(['clipboard payload'])
            path = project / f'plain-{number}.bytes'
            start([sys.executable, str(capture), str(path), 'plain'])
            editor.raw(chord + b'X\x1e')
            equal(result(path), b'clipboard payloadX', label + ' plus printable input in one packet remains ordered')
        bash = shutil.which('bash')
        assert bash, 'bash is required for readline regression'
        for number, (label, chord) in enumerate(variants):
            clipboard(['literal "quotes" $HOME; value'])
            path = project / f'shell-{number}.bytes'
            start([bash, '--noprofile', '--norc', str(shell), str(path)], 'paste-fixture>')
            editor.raw(chord)
            equal(lua('return vim.fn.mode()'), 't', label + ' keeps Bash input active')
            editor.raw(b'\r')
            equal(result(path), b'literal "quotes" $HOME; value', label + ' pastes clipboard into real Bash readline')
        lua('_G.JetvimPasteHas=vim.fn.has;_G.JetvimPasteExecutable=vim.fn.executable;'
            'vim.fn.has=function(name,...) if name=="clipboard" then return 0 end;return JetvimPasteHas(name,...) end;'
            'vim.fn.executable=function(name,...) if name=="pbpaste" then return 0 end;return JetvimPasteExecutable(name,...) end;'
            'vim.fn.setreg(string.char(34),{"local register fallback"},"v");return true')
        for number, (label, chord) in enumerate(variants):
            path = project / f'fallback-{number}.bytes'
            start([sys.executable, str(capture), str(path), 'plain'])
            editor.raw(chord + b'\x1e')
            equal(result(path), b'local register fallback', label + ' uses local register without a clipboard provider')
        lua('vim.fn.has=JetvimPasteHas;vim.fn.executable=JetvimPasteExecutable;return true')
        equal(lua('return vim.api.nvim_buf_get_lines(vim.g.JetvimPasteSource,0,-1,false)'),
              ['-- editor stays unchanged'], 'terminal pastes never alter source buffer')
        for label, chord in variants:
            lua('vim.cmd.stopinsert();return true')
            time.sleep(.04)
            lua('require("jetvim.tree").editor();vim.api.nvim_set_current_buf(vim.g.JetvimPasteSource);'
                'vim.api.nvim_buf_set_lines(0,0,-1,false,{"base"});vim.api.nvim_win_set_cursor(0,{1,0});vim.cmd.startinsert();return true')
            clipboard(['EDITOR', 'PASTE'])
            editor.raw(chord)
            editor.wait('return vim.api.nvim_get_current_line()=="PASTEbase"')
            equal(lua('return vim.api.nvim_buf_get_lines(0,0,-1,false)'), ['EDITOR', 'PASTEbase'],
                  label + ' still pastes into the code editor')
            equal(lua('return vim.fn.mode()'), 'i', label + ' preserves editor typing mode')
        equal(lua('return vim.v.errmsg'), '', 'no terminal paste errors')
        print(f'PASS: {support["checks"]} terminal clipboard paste PTY/readline checks')
    finally:
        editor.close()
