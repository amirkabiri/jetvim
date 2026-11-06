#!/usr/bin/env python3
"""Optional Mac-host sbx argv and private-PTY transport; no container or AX tap."""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import pty
import select
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / '.jetvim'
STATE.mkdir(exist_ok=True)
spec = importlib.util.spec_from_file_location('jetvim_warp_sbx', ROOT / 'scripts/warp.py')
warp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(warp)


def executable(path, source):
    path.write_text('#!' + sys.executable + '\n' + source)
    path.chmod(0o755)


class SbxBridge(unittest.TestCase):
    def test_command_preserves_remote_arguments_and_session(self):
        arguments = ['/remote/folder with spaces', 'file;echo nope', '$(literal).lua', '--headless']
        self.assertEqual(warp.session_command(ROOT, ['--sbx', 'hacker', *arguments], 'Jetvim-test'),
                         ['sbx', 'exec', '-it', 'hacker', 'env', 'JETVIM_SESSION_TITLE=Jetvim-test', 'jetvim', *arguments])
        self.assertEqual(warp.session_command(ROOT, ['--sbx', 'name_2.test-3'], 'Jetvim-a')[-1], 'jetvim')
        self.assertEqual(warp.session_command(ROOT, ['main.lua'], 'Jetvim-test'),
                         ['nvim', '--noplugin', '-u', str(ROOT / 'init.lua'), '-i', 'NONE', 'main.lua'])

    def test_invalid_container_arguments(self):
        for arguments in (['--sbx'], ['--sbx', ''], ['--sbx', '-hacker'], ['--sbx', 'semi;colon'],
                          ['--sbx', 'has space'], ['--sbx', '../path'], ['--sbx', 'a\nb']):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                warp.session_command(ROOT, arguments, 'Jetvim-test')

    def test_invalid_bridge_app_fails_before_helper_or_runtime(self):
        with tempfile.TemporaryDirectory(prefix='sbxa-', dir=STATE) as folder:
            home = Path(folder) / 'must-not-be-created'
            with mock.patch.dict(os.environ, {'JETVIM_ROOT':str(ROOT), 'JETVIM_HOME':str(home), 'JETVIM_BRIDGE_APP':'other-app'}):
                with self.assertRaisesRegex(SystemExit, 'JETVIM_BRIDGE_APP must be warp or terminal'):
                    warp.main()
            self.assertFalse(home.exists())

    def test_launcher_remote_mode_without_local_neovim(self):
        with tempfile.TemporaryDirectory(prefix='sbxl-', dir=STATE) as folder:
            fixture = Path(folder)
            binaries = fixture / 'bin'; binaries.mkdir()
            log = fixture / 'launch.json'
            executable(binaries / 'python3', 'import json,os,sys\nfrom pathlib import Path\n'
                       'Path(os.environ["SBX_TEST_LOG"]).write_text(json.dumps({"args":sys.argv[1:],"cwd":os.getcwd(),"app":os.environ.get("JETVIM_BRIDGE_APP")}))\n')
            executable(binaries / 'sbx', 'raise SystemExit("A real sbx must never run in this launcher test")\n')
            for name in ('dirname', 'mkdir'):
                (binaries / name).symlink_to(shutil.which(name))
            home = fixture / 'home'
            env = dict(os.environ, PATH=str(binaries), JETVIM_HOME=str(home), SBX_TEST_LOG=str(log))
            remote = str(fixture)  # Even a path that exists on the Mac stays remote.
            result = subprocess.run([str(ROOT / 'jetvim'), '--warp-keys', '--sbx', 'hacker', remote, 'a b.lua'],
                                    cwd=ROOT, env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(log.read_text()),
                             {'args':[str(ROOT / 'scripts/warp.py'),'--sbx','hacker',remote,'a b.lua'], 'cwd':str(ROOT),'app':'warp'})
            self.assertFalse((binaries / 'nvim').exists())
            result = subprocess.run([str(ROOT / 'jetvim'), '--terminal-keys', '--sbx', 'hacker', remote],
                                    cwd=ROOT, env=dict(env, JETVIM_BRIDGE_APP='warp'), capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(log.read_text())['app'], 'terminal')
            self.assertEqual(json.loads(log.read_text())['args'][1:], ['--sbx', 'hacker', remote])
            result = subprocess.run([str(ROOT / 'jetvim'), '--warp-keys', '--sbx', 'hacker'],
                                    cwd=ROOT, env=dict(env, JETVIM_BRIDGE_APP='terminal'), capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(log.read_text())['app'], 'warp')
            for args, message in [(['--sbx','hacker'],'requires --warp-keys'),
                                  (['--warp-keys','--sbx'],'requires a container name'),
                                  (['--warp-keys','--sbx','bad;name'],'invalid sbx container name')]:
                missing_home = fixture / 'must-not-be-created'
                result = subprocess.run([str(ROOT / 'jetvim'), *args], cwd=ROOT,
                                        env=dict(env, JETVIM_HOME=str(missing_home)), capture_output=True, text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
                self.assertFalse(missing_home.exists())
            (binaries / 'sbx').unlink()
            result = subprocess.run([str(ROOT / 'jetvim'), '--warp-keys', '--sbx', 'hacker'], cwd=ROOT,
                                    env=dict(env, JETVIM_HOME=str(missing_home)), capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('sbx must be installed', result.stderr)
            self.assertFalse(missing_home.exists())

    def test_private_pty_transport_resize_exit_and_restore(self):
        for app in ('warp', 'terminal'):
            with self.subTest(app=app):
                self.check_transport(app)

    def check_transport(self, app):
        with tempfile.TemporaryDirectory(prefix='sbxp-', dir=STATE) as folder:
            fixture = Path(folder)
            home = fixture / 'home'; (home / 'bin').mkdir(parents=True)
            binaries = fixture / 'bin'; binaries.mkdir()
            gate, log = fixture / 'keys', fixture / 'child.json'
            helper_log = fixture / 'helper.json'
            gate.write_text('')
            executable(home / 'bin/keybridge', '''import json,os,sys,time
from pathlib import Path
Path(os.environ['SBX_TEST_HELPER_LOG']).write_text(json.dumps(sys.argv[1:]))
print('READY',flush=True)
gate=Path(os.environ['SBX_TEST_GATE']); previous=''
while True:
    text=gate.read_text()
    if text != previous:
        print(text[len(previous):],end='',flush=True);previous=text
    time.sleep(.01)
''')
            future = (ROOT / 'macos/KeyBridge.swift').stat().st_mtime + 86400
            os.utime(home / 'bin/keybridge', (future, future))
            executable(binaries / 'sbx', '''import fcntl,json,os,signal,struct,sys,termios,tty
from pathlib import Path
log=Path(os.environ['SBX_TEST_LOG']); payload=bytearray()
tty.setraw(0)
record={'argv':sys.argv[1:]}
def publish(*args):
    record['size']=list(struct.unpack('HHHH',fcntl.ioctl(0,termios.TIOCGWINSZ,bytes(8)))[:2])
    record['data']=list(payload);log.write_text(json.dumps(record))
signal.signal(signal.SIGWINCH,publish)
publish()
while True:
    data=os.read(0,4096)
    if not data:break
    payload.extend(data);publish()
    if b'\\x04' in data:raise SystemExit(7)
''')
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 100, 0, 0))
            original = termios.tcgetattr(slave)
            env = dict(os.environ, JETVIM_ROOT=str(ROOT), JETVIM_HOME=str(home), JETVIM_PROJECT=str(ROOT),
                       PATH=str(binaries) + os.pathsep + os.environ['PATH'], SBX_TEST_GATE=str(gate), SBX_TEST_LOG=str(log),
                       JETVIM_BRIDGE_APP=app, SBX_TEST_HELPER_LOG=str(helper_log))
            # This overrides only platform detection. The helper and sbx are
            # fixture scripts; neither accesses macOS APIs or a real container.
            code = ('import importlib.util,sys; s=importlib.util.spec_from_file_location("bridge",sys.argv[1]); '
                    'm=importlib.util.module_from_spec(s);s.loader.exec_module(m);sys.argv=sys.argv[1:]; '
                    'm.sys.platform="darwin";raise SystemExit(m.main())')
            process = subprocess.Popen([sys.executable, '-c', code, str(ROOT / 'scripts/warp.py'),
                                        '--sbx', 'hacker', '/remote folder', 'literal;name'],
                                       cwd=ROOT, env=env, stdin=slave, stdout=slave, stderr=slave)
            output = bytearray()
            def wait_for(predicate):
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    if select.select([master], [], [], .02)[0]:
                        output.extend(os.read(master, 65536))
                    try:
                        if log.exists() and predicate(json.loads(log.read_text())):return
                    except json.JSONDecodeError:pass
                    if process.poll() is not None:break
                self.fail('PTY state timed out: ' + output.decode(errors='replace'))
            try:
                wait_for(lambda state: state['size']==[30,100])
                args = json.loads(log.read_text())['argv']
                self.assertEqual(args[:4], ['exec','-it','hacker','env'])
                self.assertRegex(args[4], r'^JETVIM_SESSION_TITLE=Jetvim-[0-9a-f]{8}$')
                self.assertEqual(args[5:], ['jetvim','/remote folder','literal;name'])
                helper_args = json.loads(helper_log.read_text())
                self.assertEqual(helper_args[:2], [str(ROOT / 'config/keymap.json'), args[4].split('=',1)[1]])
                self.assertEqual(helper_args[2:], ['terminal'] if app == 'terminal' else [])
                os.write(master,b'hello')
                gate.write_text('save\nnative:shift-page-up\n')
                relay = warp.shortcut_sequence('save',warp.key_sequences(json.loads((ROOT / 'config/keymap.json').read_text())))
                expected = b'hello' + relay + b'\x1b[5;2~'
                wait_for(lambda state: bytes(state['data']) == expected)
                fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',42,123,0,0))
                os.kill(process.pid,signal.SIGWINCH)
                wait_for(lambda state: state['size']==[42,123])
                os.write(master,b'\x04')
                self.assertEqual(process.wait(timeout=8),7)
                restored = termios.tcgetattr(slave)
                # macOS may set the transient PENDIN bit when queued input is
                # reprocessed; the actual input/output/local modes must restore.
                restored[3] &= ~getattr(termios, 'PENDIN', 0)
                original[3] &= ~getattr(termios, 'PENDIN', 0)
                self.assertEqual(restored,original)
            finally:
                if process.poll() is None:
                    process.terminate();process.wait(timeout=8)
                os.close(master);os.close(slave)


if __name__ == '__main__':
    unittest.main(verbosity=2)
