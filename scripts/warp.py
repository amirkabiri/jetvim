#!/usr/bin/env python3
"""Run Jetvim in a private PTY; relay scoped macOS shortcut events into it."""
import fcntl
import json
import os
from pathlib import Path
import pty
import re
import select
import shutil
import signal
import struct
import subprocess
import sys
import termios
import tty
import uuid


NATIVE_SEQUENCES = {
    'native:shift-page-up': b'\x1b[5;2~',
    'native:shift-page-down': b'\x1b[6;2~',
    'native:shift-home': b'\x1b[1;2H',
    'native:shift-end': b'\x1b[1;2F',
}


def key_sequences(bindings):
    """Keep existing private relay IDs independent of supplemental native keys."""
    return {item['id']: f'\x1b[{0xF0001 + index}u'.encode() for index, item in enumerate(bindings)}


def shortcut_sequence(action, sequences):
    """Only fixed native navigation IDs or registered editor actions are sent."""
    return NATIVE_SEQUENCES.get(action) or sequences.get(action)


def session_command(root, args, token):
    """Build an argv, never a shell command; remote paths belong to Linux."""
    if args[:1] == ['--sbx']:
        if len(args) < 2 or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', args[1]):
            raise ValueError('--sbx requires a valid container name.')
        return ['sbx', 'exec', '-it', args[1], 'env',
                'JETVIM_SESSION_TITLE=' + token, 'jetvim', *args[2:]]
    return ['nvim', '--noplugin', '-u', str(root / 'init.lua'), '-i', 'NONE', *args]


def main():
    root = Path(os.environ['JETVIM_ROOT'])
    home = Path(os.environ.get('JETVIM_HOME', str(root / '.jetvim')))
    app = os.environ.get('JETVIM_BRIDGE_APP', 'warp')
    if app not in ('warp', 'terminal'):
        raise SystemExit('JETVIM_BRIDGE_APP must be warp or terminal.')
    app_name = 'Terminal' if app == 'terminal' else 'Warp'
    if sys.platform != 'darwin' or not sys.stdin.isatty():
        raise SystemExit('--warp-keys and --terminal-keys require macOS and an interactive terminal.')
    token = 'Jetvim-' + uuid.uuid4().hex[:8]
    try:
        command = session_command(root, sys.argv[1:], token)
    except ValueError as error:
        raise SystemExit(str(error))
    if command[0] == 'sbx' and not shutil.which('sbx'):
        raise SystemExit('sbx must be installed on the macOS host; install Jetvim inside the container too.')
    source = root / 'macos/KeyBridge.swift'
    binary = home / 'bin/keybridge'
    binary.parent.mkdir(parents=True, exist_ok=True)
    if not binary.exists() or binary.stat().st_mtime < source.stat().st_mtime:
        compiler = shutil.which('swiftc')
        if not compiler:
            raise SystemExit('The macOS key bridge needs the Swift compiler. Plain ./jetvim works without it.')
        cache = home / 'cache/swift'
        cache.mkdir(parents=True, exist_ok=True)
        print(f'Building the optional {app_name} key bridge in {home} …', flush=True)
        subprocess.run([compiler, '-module-cache-path', str(cache), str(source), '-o', str(binary)], check=True)
    env = os.environ.copy()
    env['JETVIM_SESSION_TITLE'] = token
    bindings = json.loads((root / 'config/keymap.json').read_text())
    sequences = key_sequences(bindings)
    helper_args = [str(binary), str(root / 'config/keymap.json'), token]
    if app == 'terminal':
        helper_args.append('terminal')
    bridge = subprocess.Popen(helper_args, stdout=subprocess.PIPE)
    master = slave = None
    editor = None
    original = termios.tcgetattr(sys.stdin.fileno())
    previous_handler = None
    try:
        def terminate(signum, _frame):
            raise SystemExit(128 + signum)

        signal.signal(signal.SIGTERM, terminate)
        signal.signal(signal.SIGHUP, terminate)
        # The helper reports readiness only after macOS has authorized the tap.
        ready, _, _ = select.select([bridge.stdout], [], [], 10)
        if not ready or bridge.stdout.readline() != b'READY\n':
            raise SystemExit(f'{app_name} key bridge could not start. Use ./jetvim for the standard terminal mode.')
        master, slave = pty.openpty()

        def resize(*_):
            size = fcntl.ioctl(sys.stdin.fileno(), termios.TIOCGWINSZ, struct.pack('HHHH', 0, 0, 0, 0))
            fcntl.ioctl(master, termios.TIOCSWINSZ, size)

        resize()

        def controlling_terminal():
            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)

        editor = subprocess.Popen(command,
                                  stdin=slave, stdout=slave, stderr=slave, env=env,
                                  cwd=os.environ.get('JETVIM_PROJECT', str(root)), preexec_fn=controlling_terminal)
        os.close(slave)
        slave = None
        previous_handler = signal.signal(signal.SIGWINCH, resize)
        tty.setraw(sys.stdin.fileno())
        pending = b''
        while editor.poll() is None:
            readable, _, _ = select.select([sys.stdin.fileno(), master, bridge.stdout], [], [], 0.2)
            for channel in readable:
                if channel == sys.stdin.fileno():
                    data = os.read(channel, 65536)
                    if not data:
                        return 0
                    os.write(master, data)
                elif channel == master:
                    try:
                        data = os.read(master, 65536)
                    except OSError:
                        return editor.wait()
                    if not data:
                        return editor.wait()
                    os.write(sys.stdout.fileno(), data)
                else:
                    data = os.read(bridge.stdout.fileno(), 4096)
                    if not data:
                        raise RuntimeError('The macOS key bridge exited unexpectedly.')
                    pending += data
                    while b'\n' in pending:
                        line, pending = pending.split(b'\n', 1)
                        sequence = shortcut_sequence(line.decode(), sequences)
                        if sequence:
                            os.write(master, sequence)
        return editor.returncode
    finally:
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, original)
        if previous_handler is not None:
            signal.signal(signal.SIGWINCH, previous_handler)
        bridge.terminate()
        bridge.wait(timeout=5)
        if editor and editor.poll() is None:
            os.killpg(editor.pid, signal.SIGTERM)
            editor.wait(timeout=5)
        for descriptor in (master, slave):
            if descriptor is not None:
                os.close(descriptor)
        # Reset a session title set by this wrapper; no preference files change.
        sys.stdout.write(f'\x1b]0;{app_name}\x07')
        sys.stdout.flush()


if __name__ == '__main__':
    sys.exit(main())
