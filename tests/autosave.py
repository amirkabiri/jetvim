#!/usr/bin/env python3
"""Default-on autosave and persisted settings through real terminal input."""
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
checks = 0


def equal(actual, expected, label):
    global checks
    assert actual == expected, f'{label}: expected {expected!r}, got {actual!r}'
    checks += 1


class Editor:
    def __init__(self, project, settings, disabled=False, disable_lsp=False):
        self.settings_path = settings
        self.socket = STATE / f'auto-{os.getpid()}-{time.monotonic_ns() % 10000}.sock'
        self.env = dict(os.environ, TERM='xterm-256color', JETVIM_DISABLE_VCS='1',
                        JETVIM_HOME=str(settings.parent), JETVIM_SETTINGS_FILE=str(settings))
        self.env.pop('JETVIM_DISABLE_AUTOSAVE', None)
        if disabled:
            self.env['JETVIM_DISABLE_AUTOSAVE'] = '1'
        self.master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 35, 140, 0, 0))
        self.stop, self.output = threading.Event(), bytearray()
        command = [str(ROOT / 'jetvim'), str(project), 'main.lua', '--listen', str(self.socket)]
        if disable_lsp:
            # Hook-only fixtures must not launch unrelated installed JS/TS servers.
            command.extend(['--cmd', 'lua vim.lsp.enable=function() end'])
        self.process = subprocess.Popen(command, cwd=ROOT, env=self.env, stdin=slave, stdout=slave, stderr=slave)
        os.close(slave)
        self.reader = threading.Thread(target=self.drain, daemon=True)
        self.reader.start()
        deadline = time.monotonic() + 10
        while not self.socket.exists():
            assert self.process.poll() is None and time.monotonic() < deadline, 'editor did not start'
            time.sleep(0.03)
        self.wait('return vim.fs.basename(vim.api.nvim_buf_get_name(0)) == "main.lua"')

    def drain(self):
        while not self.stop.is_set():
            ready, _, _ = select.select([self.master], [], [], 0.1)
            if ready:
                try:
                    data = os.read(self.master, 65536)
                except OSError:
                    return
                if not data:
                    return
                self.output.extend(data)
                if b'\x1b]11;?' in data:
                    os.write(self.master, b'\x1b]11;rgb:1e1e/1f1f/2222\x07')
                if b'\x1b[5n' in data:
                    os.write(self.master, b'\x1b[0n')
                if b'\x1b[6n' in data:
                    os.write(self.master, b'\x1b[1;1R')

    def lua(self, code):
        expr = "json_encode(luaeval('(function() " + code.replace("'", "''") + " end)()'))"
        result = subprocess.run([str(ROOT / 'jetvim'), '--server', str(self.socket), '--remote-expr', expr],
                                cwd=ROOT, env=self.env, capture_output=True, text=True, timeout=8)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    def raw(self, value):
        os.write(self.master, value.encode() if isinstance(value, str) else value)
        time.sleep(0.08)

    def wait(self, code, seconds=5):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self.lua(code):
                return
            time.sleep(0.04)
        raise AssertionError('timed out: ' + code)

    def disk(self, path, expected, seconds=3):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if path.exists() and path.read_text() == expected:
                equal(path.read_text(), expected, 'autosave disk contents')
                return
            time.sleep(0.04)
        raise AssertionError(f'file did not autosave: {path.name}: {path.read_text() if path.exists() else "missing"!r}')

    def edit(self, text):
        self.lua('vim.api.nvim_buf_set_lines(0,0,-1,false,{' + json.dumps(text) + '}); return true')

    def open(self, path):
        self.raw(b'\x1b[27u')
        self.lua('require("jetvim.project").open(' + json.dumps(str(path)) + '); return true')

    def settings(self, relay=False, scope='User settings'):
        if relay:
            bindings = json.loads((ROOT / 'config/keymap.json').read_text())
            index = next(i for i, entry in enumerate(bindings, 1) if entry['id'] == 'settings')
            self.raw(f'\x1b[{0xF0000 + index}u')
        else:
            self.raw(b'\x1b[44;9u')
        self.wait('return vim.bo.buftype == "prompt"')
        self.raw(scope + '\r')
        if scope == 'User settings':
            self.wait('return vim.api.nvim_buf_get_name(0) == ' + json.dumps(str(self.settings_path)))
        else:
            self.wait('return vim.api.nvim_buf_get_name(0) == vim.uv.cwd() .. "/.idea/jetvim/settings.lua"')

    def close(self):
        if self.process.poll() is None:
            try:
                self.raw(b'\x1b[27u')
                self.lua('vim.cmd("qa!"); return true')
            except Exception:
                pass
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=5)
        self.stop.set()
        self.reader.join(timeout=2)
        os.close(self.master)
        self.socket.unlink(missing_ok=True)
        (STATE / 'autosave-output.log').write_bytes(self.output)


with tempfile.TemporaryDirectory(prefix='autosave-', dir=STATE) as directory:
    project = Path(directory)
    home = project / 'user-home'; home.mkdir()
    preferences = home / 'settings.lua'
    main = project / 'main.lua'; main.write_text('-- original\n')
    second = project / 'second.lua'; second.write_text('-- second\n')
    editor = Editor(project, preferences)
    def options(**values):
        fields = ','.join(k + '=' + ('true' if v is True else 'false' if v is False else str(v)) for k,v in values.items())
        preferences.write_text('return {autosave={' + fields + '}}\n')
        editor.lua('vim.cmd("JetvimReloadSettings"); return true')
    try:
        equal(editor.lua('return require("jetvim.settings").get().autosave'),
              {'enabled':True,'debounce':True,'delay_ms':1000,'on_focus_lost':True}, 'installed defaults')
        # Observe debounce timing inside the editor's monotonic event loop.
        # Python/CI can be descheduled past a correct timer's deadline; elapsed
        # host sleeps cannot prove that an automatic write happened too early.
        editor.wait('return vim.fn.mode() == "i"')
        editor.lua('''
          _G.JetvimAutosaveTiming = { edits = {}, writes = {}, previous = vim.api.nvim_get_current_line() }
          local timing = _G.JetvimAutosaveTiming
          local group = vim.api.nvim_create_augroup('JetvimAutosaveTimingTest', { clear = true })
          local buf = vim.api.nvim_get_current_buf()
          vim.api.nvim_create_autocmd('TextChangedI', { group = group, buffer = buf, callback = function()
            local text = vim.api.nvim_buf_get_lines(buf, 0, 1, false)[1]
            if not vim.bo[buf].modified or text == timing.previous then return end
            timing.previous, timing.last_edit = text, vim.uv.now()
            local state = require('jetvim.autosave').states[buf]
            timing.edits[#timing.edits + 1] = {
              text = text, delay = require('jetvim.settings').get().autosave.delay_ms,
              due = state and state.timer and state.timer:get_due_in(),
            }
          end })
          vim.api.nvim_create_autocmd('BufWritePre', { group = group, buffer = buf, callback = function()
            timing.writes[#timing.writes + 1] = {
              text = vim.api.nvim_buf_get_lines(buf, 0, 1, false)[1],
              elapsed = timing.last_edit and vim.uv.now() - timing.last_edit,
              delay = require('jetvim.settings').get().autosave.delay_ms,
            }
          end })
          return true
        ''')
        # Real insert-mode keystrokes each arm the complete one-second delay,
        # including a second keystroke while the first timer is normally pending.
        editor.raw('X'); time.sleep(.50)
        editor.raw('Y')
        editor.disk(main, 'XY-- original\n')
        timing = editor.lua('return _G.JetvimAutosaveTiming')
        equal([edit['text'] for edit in timing['edits']], ['X-- original', 'XY-- original'], 'real typing produces both debounce edits')
        equal([edit['due'] for edit in timing['edits']], [1000, 1000], 'each keystroke restarts the full default delay')
        for write in timing['writes']:
            equal(write['elapsed'] >= write['delay'], True, 'default autosave waits a complete delay after latest edit')
        equal(editor.lua('return vim.bo.modified'), False, 'debounced save clears dirty flag')
        equal(editor.lua('return vim.fn.mode()'), 'i', 'debounced save preserves insert mode')
        options(enabled=True, debounce=True, delay_ms=250, on_focus_lost=False)
        editor.raw('Z')
        editor.disk(main, 'XYZ-- original\n')
        timing = editor.lua('vim.api.nvim_del_augroup_by_name("JetvimAutosaveTimingTest"); return _G.JetvimAutosaveTiming')
        equal(timing['edits'][-1]['text'], 'XYZ-- original', 'custom delay observes real inserted text')
        equal(timing['edits'][-1]['due'], 250, 'custom delay arms a full 250ms timer')
        equal(timing['writes'][-1]['text'], 'XYZ-- original', 'custom timer writes final edit')
        equal(timing['writes'][-1]['elapsed'] >= 250, True, 'custom delay never writes before its editor-side deadline')
        # Focus writes work independently when idle/debounce writes are disabled.
        options(enabled=True, debounce=False, on_focus_lost=True)
        editor.edit('-- sidebar leave')
        time.sleep(.35)
        equal(main.read_text(), 'XYZ-- original\n', 'debounce false suppresses idle writes')
        editor.raw(b'\x1b[49;9u')
        editor.wait('return vim.bo.filetype == "jetvim-tree"')
        editor.disk(main, '-- sidebar leave\n')
        editor.open(main); editor.edit('-- other file leave'); editor.open(second)
        editor.disk(main, '-- other file leave\n')
        # Disabled focus writes stay dirty, but Cmd-S is always immediate.
        options(enabled=True, debounce=False, on_focus_lost=False)
        editor.open(main); editor.edit('-- manual only'); editor.open(second)
        time.sleep(.35)
        equal(main.read_text(), '-- other file leave\n', 'focus false disables leave writes')
        editor.open(main); editor.raw(b'\x1b[115;9u')
        editor.disk(main, '-- manual only\n', seconds=1)
        equal(editor.lua('return vim.bo.modified'), False, 'native CmdS saves with both triggers disabled')
        options(enabled=False)
        editor.edit('-- master disabled'); editor.open(second); time.sleep(1.15)
        equal(main.read_text(), '-- manual only\n', 'master gate disables both automatic triggers')
        editor.open(main); editor.raw(b'\x1b[115;9u')
        editor.disk(main, '-- master disabled\n', seconds=1)
        # Same-buffer split focus must not trigger a focus-leave write.
        options(enabled=True, debounce=False, on_focus_lost=True)
        editor.edit('-- same split')
        editor.lua('vim.cmd.vsplit(); return true');time.sleep(.2)
        equal(main.read_text(), '-- master disabled\n', 'same-file split focus does not save')
        editor.lua('vim.cmd.close(); return true');time.sleep(.1)
        # Queue focus writes while a formatter is still running.
        editor.lua('vim.b.jetvim_hook_running=true; return true')
        editor.open(second);time.sleep(.25)
        equal(main.read_text(), '-- master disabled\n', 'focus write waits for formatter')
        editor.lua('for _,b in ipairs(vim.api.nvim_list_bufs()) do if vim.api.nvim_buf_get_name(b):match("main.lua$") then vim.b[b].jetvim_hook_running=nil end end; return true')
        editor.disk(main, '-- same split\n')
        # Disk conflicts, read-only files and unnamed/tool buffers stay protected.
        editor.open(main); editor.edit('-- local conflict');main.write_text('-- external\n')
        editor.open(second);time.sleep(.3)
        equal(main.read_text(), '-- external\n', 'focus write protects external disk changes')
        equal(editor.lua('for _,b in ipairs(vim.api.nvim_list_bufs()) do if vim.api.nvim_buf_get_name(b):match("main.lua$") then return vim.bo[b].modified end end'), True, 'disk conflict preserves edits')
        readonly=project/'readonly.lua';readonly.write_text('-- readonly original\n')
        editor.open(readonly);editor.lua('vim.bo.readonly=true; return true')
        editor.edit('-- readonly');editor.open(second);time.sleep(.2)
        equal(readonly.read_text(), '-- readonly original\n', 'read-only file skipped on leave')
        editor.open(readonly);editor.lua('vim.bo.readonly=false; vim.cmd("edit!"); return true')
        options(enabled=True, debounce=True, delay_ms=250, on_focus_lost=True)
        editor.lua('vim.cmd.enew(); return true');editor.edit('unnamed');time.sleep(.4)
        equal(editor.lua('return vim.api.nvim_buf_get_name(0)'), '', 'unnamed buffer stays unnamed')
        equal(editor.lua('return vim.bo.modified'), True, 'unnamed buffer stays dirty')
        editor.lua('vim.bo.modified=false; vim.cmd.enew(); vim.api.nvim_buf_set_name(0,vim.uv.cwd().."/tool.lua"); vim.bo.buftype="nofile"; return true')
        editor.edit('tool text');time.sleep(.4)
        equal((project/'tool.lua').exists(), False, 'tool buffer never written')
        editor.open(project/'missing/deep.lua');editor.edit('-- no directory');time.sleep(.4)
        equal((project/'missing').exists(), False, 'autosave never creates missing parent directories')
        equal(editor.lua('return vim.bo.modified'), True, 'write error preserves buffer')
        equal(editor.lua('return vim.o.confirm'), True, 'write error restores confirmation')
        # Closing dialogs can outlive the timer; explicit Discard must win.
        discard=project/'discard.lua';discard.write_text('-- original\n')
        editor.open(discard);editor.edit('-- discard this')
        start=len(editor.output);os.write(editor.master,b'\x1b[119;9u')
        deadline=time.monotonic()+5
        while b'Save changes to' not in editor.output[start:]:
            assert time.monotonic()<deadline, 'close confirmation missing'
            time.sleep(.02)
        time.sleep(.6)
        equal(discard.read_text(), '-- original\n', 'timer cannot save during close confirmation')
        editor.raw('d');time.sleep(.4)
        equal(discard.read_text(), '-- original\n', 'Discard prevents focus-leave and idle writes')
        # Invalid new flags retain the last working settings.
        preferences.write_text('return {autosave={debounce="yes"}}\n')
        editor.lua('vim.cmd("JetvimReloadSettings"); return true')
        equal(editor.lua('return require("jetvim.settings").get().autosave.debounce'), True, 'invalid flag retains valid config')
    finally:
        editor.close()
    preferences.write_text('return {autosave={enabled=false}}\n')
    editor = Editor(project, preferences)
    try:
        equal(editor.lua('return require("jetvim.settings").get().autosave.enabled'), False, 'master flag survives restart')
        editor.edit('-- persistent disabled');time.sleep(1.1)
        equal(main.read_text(), '-- external\n', 'disabled setting respected after restart')
    finally:
        editor.close()
print(f'PASS: {checks} debounce/focus autosave checks through real PTY input')
