#!/usr/bin/env python3
"""LEAD-ONLY test: creates local Git fixtures and validates the read-only panel.

Implementation agents must not execute this file: it invokes Git. All repositories,
files, sockets and logs are created under this checkout's ignored .jetvim directory.
"""
import hashlib
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import shutil
import struct
import subprocess
import tempfile
import termios
import threading
import time

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / '.jetvim'
STATE.mkdir(exist_ok=True)
(STATE / 'tmp').mkdir(exist_ok=True)
ENV = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null',
           TMPDIR=str(STATE / 'tmp'), GIT_OPTIONAL_LOCKS='0', GIT_CEILING_DIRECTORIES=str(STATE))
checks = 0


def equal(actual, expected, label):
    global checks
    assert actual == expected, f'{label}: expected {expected!r}, got {actual!r}'
    checks += 1


def git(repo, *args, expected_codes=(0,)):
    result = subprocess.run(['git', '-c', 'user.name=Jetvim Test', '-c', 'user.email=jetvim-test@example.invalid',
                             '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false',
                             '-c', 'commit.gpgsign=false', '-C', str(repo), *args],
                            env=ENV, capture_output=True, timeout=15)
    assert result.returncode in expected_codes, result.stderr.decode(errors='replace')
    return result.stdout


class Editor:
    def __init__(self, project, file, pre_init=None):
        self.home = Path(tempfile.mkdtemp(prefix='git-home-', dir=STATE))
        self.env = dict(ENV, TERM='xterm-256color', JETVIM_HOME=str(self.home),
                        JETVIM_SETTINGS_FILE=str(self.home / 'settings.lua'))
        self.socket = STATE / f'git-test-{os.getpid()}-{time.monotonic_ns() % 100000}.sock'
        self.log_path = self.socket.with_suffix('.log')
        self.log = self.log_path.open('w')
        self.master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 35, 140, 0, 0))
        self.stop = threading.Event()
        argv = [str(ROOT / 'jetvim'), str(project), file, '--listen', str(self.socket),
                '-c', 'lua vim.g.JetvimTestReady = true']
        if pre_init is not None:
            argv.extend(['--cmd', pre_init])
        self.process = subprocess.Popen(argv,
                                        cwd=ROOT, env=self.env, stdout=slave, stderr=slave, stdin=slave)
        os.close(slave)
        self.reader = threading.Thread(target=self.drain, daemon=True)
        self.reader.start()
        try:
            deadline = time.monotonic() + 10
            while not self.socket.exists():
                if self.process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError('Editor failed to start; see ' + str(self.log_path))
                time.sleep(0.03)
            self.wait('return vim.g.JetvimTestReady == true')
            initial = str((Path(project) / file).resolve())
            self.wait('return vim.api.nvim_buf_get_name(0) == ' + json.dumps(initial, ensure_ascii=False))
            equal(self.lua('return vim.api.nvim_buf_get_name(0)'), initial, 'initial argument file loaded before first key')
            self.base_windows = self.lua('return #vim.api.nvim_list_wins()')
        except Exception:
            self.close()
            raise

    def drain(self):
        pending = b''
        replies = {
            b'\x1b]10;?\x07': b'\x1b]10;rgb:bcbc/bebe/c4c4\x07',
            b'\x1b]11;?\x07': b'\x1b]11;rgb:1e1e/1f1f/2222\x07',
            b'\x1b]10;?\x1b\\': b'\x1b]10;rgb:bcbc/bebe/c4c4\x1b\\',
            b'\x1b]11;?\x1b\\': b'\x1b]11;rgb:1e1e/1f1f/2222\x1b\\',
            b'\x1b[5n': b'\x1b[0n',
            b'\x1b[6n': b'\x1b[1;1R',
            b'\x1b[c': b'\x1b[?1;2c',
            b'\x1b[?u': b'\x1b[?0u',
        }
        while not self.stop.is_set():
            ready, _, _ = select.select([self.master], [], [], 0.1)
            if ready:
                try:
                    data = os.read(self.master, 65536)
                except OSError:
                    break
                if not data:
                    break
                self.log.write(data.decode(errors='replace'))
                self.log.flush()
                # Emulate the startup queries of an actual terminal, rather than
                # leaving Nvim waiting for its foreground/background/DSR replies.
                pending += data
                while True:
                    matches = [(pending.find(query), query) for query in replies if query in pending]
                    if not matches:
                        pending = pending[-64:]
                        break
                    index, query = min(matches, key=lambda item: item[0])
                    try:
                        os.write(self.master, replies[query])
                    except OSError:
                        return
                    pending = pending[index + len(query):]

    def lua(self, code):
        expr = "json_encode(luaeval('(function() " + code.replace("'", "''") + " end)()'))"
        result = subprocess.run([str(ROOT / 'jetvim'), '--server', str(self.socket), '--remote-expr', expr],
                                cwd=ROOT, env=self.env, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    def keys(self, value):
        self.lua('return vim.api.nvim_input(' + json.dumps(value, ensure_ascii=False) + ')')
        time.sleep(0.06)

    def wait(self, code):
        deadline = time.monotonic() + 8
        while not self.lua(code):
            if time.monotonic() > deadline:
                raise AssertionError('Timed out waiting for: ' + code)
            time.sleep(0.04)

    def rows(self):
        return self.lua('local entries = {}; for _, entry in pairs(require("jetvim.git").rows) do entries[#entries + 1] = {entry.section, entry.path, entry.status} end; return entries')

    def preview(self, section, path, needle):
        code = ('local g = require("jetvim.git"); for row, entry in pairs(g.rows) do '
                'if entry.section == ' + json.dumps(section) + ' and entry.path == ' + json.dumps(path, ensure_ascii=False) + ' then '
                'vim.api.nvim_win_set_cursor(g.list_win, {row, 0}); g.preview(); return true end end; return false')
        equal(self.lua(code), True, 'select ' + section + ': ' + path)
        self.wait('local g = require("jetvim.git"); return table.concat(vim.api.nvim_buf_get_lines(g.diff_buf, 0, -1, false), string.char(10)):find(' + json.dumps(needle) + ', 1, true) ~= nil')

    def close(self):
        if self.process.poll() is None:
            try:
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
        self.log.close()
        self.socket.unlink(missing_ok=True)
        shutil.rmtree(self.home, ignore_errors=True)


with tempfile.TemporaryDirectory(prefix='git changes ', dir=STATE) as folder:
    repo = Path(folder)
    git(repo, 'init', '--initial-branch=main')
    initial = {'base.lua': 'old base\n', 'staged.lua': 'old stage\n', 'both.lua': 'original both\n',
               'deleted.lua': 'gone\n', 'rename original.lua': 'rename content\n',
               ':(literal).lua': 'magic old\n', 'subfolder/inside.lua': 'inside old\n'}
    for name, text in initial.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    git(repo, 'add', '--all')
    git(repo, 'commit', '-m', 'Create isolated test fixture')
    (repo / 'staged.lua').write_text('staged update\n')
    (repo / 'both.lua').write_text('staged both\n')
    (repo / 'rename original.lua').rename(repo / 'renamed target.lua')
    git(repo, 'add', '--', 'staged.lua', 'both.lua', 'rename original.lua', 'renamed target.lua')
    (repo / 'base.lua').write_text('working base\n')
    (repo / 'both.lua').write_text('working both\n')
    (repo / ':(literal).lua').write_text('magic change\n')
    (repo / 'subfolder/inside.lua').write_text('inside change\n')
    (repo / 'deleted.lua').unlink()
    (repo / 'untracked file.lua').write_text('new untracked content\n')
    (repo / 'line\r\nbreak.lua').write_text('newline filename content\n')
    index_before = hashlib.sha256((repo / '.git/index').read_bytes()).hexdigest()
    baseline = {str(path.relative_to(repo)): path.read_bytes() for path in repo.rglob('*') if path.is_file() and '.git' not in path.parts}
    editor = Editor(repo, 'base.lua')
    try:
        equal(editor.lua('return vim.v.errmsg'), '', 'clean startup')
        editor.keys('<D-9>')
        editor.wait('local g = require("jetvim.git"); return g.repo ~= nil and next(g.rows) ~= nil')
        equal(editor.lua('return vim.bo.filetype'), 'jetvim-git', 'Command9 focuses Git change list')
        equal(editor.lua('local g = require("jetvim.git"); return {vim.bo[g.list_buf].modifiable, vim.bo[g.diff_buf].modifiable}'), [False, False], 'panes are read only')
        entries = editor.rows()
        expected = {('Staged Changes', 'staged.lua'), ('Staged Changes', 'both.lua'), ('Staged Changes', 'renamed target.lua'),
                    ('Unstaged Changes', 'base.lua'), ('Unstaged Changes', 'both.lua'), ('Unstaged Changes', 'deleted.lua'),
                    ('Unstaged Changes', ':(literal).lua'), ('Unstaged Changes', 'subfolder/inside.lua'),
                    ('Untracked Files', 'untracked file.lua'), ('Untracked Files', 'line\r\nbreak.lua')}
        equal({(entry[0], entry[1]) for entry in entries}, expected, 'staged, unstaged, rename, delete and byte-preserved untracked names')
        editor.preview('Staged Changes', 'staged.lua', '+staged update')
        editor.preview('Staged Changes', 'both.lua', '+staged both')
        editor.preview('Unstaged Changes', 'both.lua', '+working both')
        editor.preview('Staged Changes', 'renamed target.lua', 'rename to renamed target.lua')
        editor.preview('Unstaged Changes', 'deleted.lua', '-gone')
        editor.keys('<CR>')
        equal(editor.lua('return vim.bo.filetype'), 'jetvim-git', 'Enter on deleted file stays in change list')
        equal((repo / 'deleted.lua').exists(), False, 'opening deleted entry never recreates the file')
        editor.preview('Unstaged Changes', ':(literal).lua', '+magic change')
        editor.preview('Untracked Files', 'untracked file.lua', '+new untracked content')
        editor.preview('Untracked Files', 'line\r\nbreak.lua', '+newline filename content')
        editor.keys('<Tab>')
        equal(editor.lua('return vim.bo.filetype'), 'diff', 'Tab focuses diff preview')
        editor.keys('<S-Tab>')
        equal(editor.lua('return vim.bo.filetype'), 'jetvim-git', 'ShiftTab returns to changes')
        editor.preview('Unstaged Changes', 'base.lua', '+working base')
        editor.keys('<CR>')
        equal(editor.lua('return vim.fs.basename(vim.api.nvim_buf_get_name(0))'), 'base.lua', 'Enter opens selected source file')
        editor.keys('<D-9>')
        equal(editor.lua('return vim.bo.filetype'), 'jetvim-git', 'Command9 refocuses visible panel')
        editor.keys('<Esc>')
        equal(editor.lua('return vim.fs.basename(vim.api.nvim_buf_get_name(0))'), 'base.lua', 'Escape focuses editor')
        editor.keys('<D-9>')
        editor.keys('<S-Esc>')
        equal(editor.lua('local g = require("jetvim.git"); return vim.api.nvim_win_is_valid(g.list_win)'), False, 'ShiftEscape hides panel')
        editor.keys('<D-9>')
        editor.wait('local g = require("jetvim.git"); return next(g.rows) ~= nil')
        old_list = editor.lua('local g = require("jetvim.git"); vim.api.nvim_win_close(g.diff_win, true); return g.list_win')
        editor.keys('<D-9>')
        editor.wait('local g = require("jetvim.git"); return vim.api.nvim_win_is_valid(g.list_win) and vim.api.nvim_win_is_valid(g.diff_win)')
        equal(editor.lua('return vim.api.nvim_win_is_valid(' + str(old_list) + ')'), False, 'recovery closes orphaned change list')
        equal(editor.lua('return #vim.api.nvim_list_wins()'), editor.base_windows + 2, 'partial-pane recovery leaves initial windows plus two Git panes')
        editor.keys('<D-9>')
        equal(editor.lua('local g = require("jetvim.git"); return vim.api.nvim_win_is_valid(g.list_win)'), False, 'Command9 toggles focused panel hidden')
        editor.keys('<Esc>')
        editor.lua('vim.g.git_terminal = vim.api.nvim_create_buf(true, false); vim.g.git_terminal_input = ""; '
                   'vim.api.nvim_open_term(vim.g.git_terminal, {on_input=function(_, _, _, data) vim.g.git_terminal_input = vim.g.git_terminal_input .. data end}); '
                   'vim.api.nvim_set_current_buf(vim.g.git_terminal); vim.cmd.startinsert(); return true')
        time.sleep(0.06)
        equal(editor.lua('return vim.fn.mode()'), 't', 'internal terminal focused')
        editor.keys('<D-9>')
        editor.wait('return vim.bo.filetype == "jetvim-git"')
        equal(editor.lua('return vim.g.git_terminal_input'), '', 'Command9 does not leak into terminal input')
        equal(editor.lua('return vim.v.errmsg'), '', 'no editor errors')
    finally:
        editor.close()
    equal(hashlib.sha256((repo / '.git/index').read_bytes()).hexdigest(), index_before, 'panel never changes index')
    equal({str(path.relative_to(repo)): path.read_bytes() for path in repo.rglob('*') if path.is_file() and '.git' not in path.parts}, baseline, 'panel never changes worktree')
    editor = Editor(repo / 'subfolder', 'inside.lua')
    try:
        editor.keys('<D-9>')
        editor.wait('return next(require("jetvim.git").rows) ~= nil')
        equal({entry[1] for entry in editor.rows()}, {'subfolder/inside.lua'}, 'subdirectory project scopes changes')
        editor.preview('Unstaged Changes', 'subfolder/inside.lua', '+inside change')
    finally:
        editor.close()
with tempfile.TemporaryDirectory(prefix='git clean ', dir=STATE) as folder:
    repo = Path(folder)
    git(repo, 'init', '--initial-branch=main')
    (repo / 'clean.lua').write_text('-- clean\n')
    git(repo, 'add', '--all')
    git(repo, 'commit', '-m', 'Clean test fixture')
    editor = Editor(repo, 'clean.lua')
    try:
        editor.keys('<D-9>')
        editor.wait('local g = require("jetvim.git"); return table.concat(vim.api.nvim_buf_get_lines(g.list_buf, 0, -1, false), string.char(10)):find("Working tree clean.", 1, true) ~= nil')
        equal(editor.rows(), [], 'clean repository has no changed-file rows')
        equal(editor.lua('return vim.bo.filetype'), 'jetvim-git', 'clean repository still opens Git panel')
        equal(editor.lua('return vim.v.errmsg'), '', 'clean repository has no errors')
    finally:
        editor.close()
with tempfile.TemporaryDirectory(prefix='not a repository ', dir=STATE) as folder:
    project = Path(folder)
    (project / 'plain.lua').write_text('-- plain\n')
    editor = Editor(project, 'plain.lua')
    try:
        editor.keys('<D-9>')
        editor.wait('local g = require("jetvim.git"); return table.concat(vim.api.nvim_buf_get_lines(g.list_buf, 0, -1, false), string.char(10)):find("not in a Git repository", 1, true) ~= nil')
        equal(editor.rows(), [], 'non-repository has no stale changed-file rows')
        equal(editor.lua('return vim.bo.filetype'), 'jetvim-git', 'non-repository displays explanatory tool window')
        editor.keys('<Esc>')
        equal(editor.lua('return vim.fs.basename(vim.api.nvim_buf_get_name(0))'), 'plain.lua', 'Escape leaves non-repository panel')
        equal(editor.lua('return vim.v.errmsg'), '', 'non-repository handled without editor error')
    finally:
        editor.close()
with tempfile.TemporaryDirectory(prefix='git conflict ', dir=STATE) as folder:
    repo = Path(folder)
    git(repo, 'init', '--initial-branch=main')
    (repo / 'conflict.lua').write_text('base\n')
    git(repo, 'add', '--all')
    git(repo, 'commit', '-m', 'Conflict base')
    git(repo, 'checkout', '-b', 'topic')
    (repo / 'conflict.lua').write_text('topic\n')
    git(repo, 'add', '--all')
    git(repo, 'commit', '-m', 'Topic change')
    git(repo, 'checkout', 'main')
    (repo / 'conflict.lua').write_text('main\n')
    git(repo, 'add', '--all')
    git(repo, 'commit', '-m', 'Main change')
    git(repo, 'merge', 'topic', expected_codes=(1,))
    index_before = (repo / '.git/index').read_bytes()
    worktree_before = (repo / 'conflict.lua').read_bytes()
    editor = Editor(repo, 'conflict.lua')
    try:
        editor.keys('<D-9>')
        editor.wait('return next(require("jetvim.git").rows) ~= nil')
        equal(editor.rows(), [['Conflicts', 'conflict.lua', 'UU']], 'real merge conflict appears once in Conflicts')
        editor.preview('Conflicts', 'conflict.lua', '<<<<<<< HEAD')
        equal(editor.lua('return vim.v.errmsg'), '', 'conflict diff has no editor errors')
    finally:
        editor.close()
    equal((repo / '.git/index').read_bytes(), index_before, 'conflict preview preserves merge index')
    equal((repo / 'conflict.lua').read_bytes(), worktree_before, 'conflict preview preserves merge markers')
print(f'PASS: {checks} Git Changes checks (lead-executed only)')
