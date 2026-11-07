#!/usr/bin/env python3
"""Own/reap fixture TUIs and backends without touching other editor sessions."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
support = {'__file__': str(ROOT / 'tests/autosave.py')}
exec((ROOT / 'tests/autosave.py').read_text().split('\nwith tempfile.TemporaryDirectory', 1)[0], support)
Editor, equal, STATE, processes = support['Editor'], support['equal'], support['STATE'], support['process_support']


with tempfile.TemporaryDirectory(prefix='life-', dir=STATE) as directory:
    folder = Path(directory)
    sequence = 0
    def fixture():
        global sequence
        sequence += 1
        project = folder / str(sequence)
        (project / 'home').mkdir(parents=True)
        (project / 'main.lua').write_text('-- process fixture\n')
        return project
    def start():
        project = fixture()
        return Editor(project, project / 'home/settings.lua', disabled=True, disable_lsp=True)
    def stopped(records, label):
        equal(any(processes.matches(record) for record in records), False, label)

    control = start()
    control.lua('vim.g.JetvimLifecycleControl="live";return true')
    def control_alive():
        equal(control.process.poll(), None, 'independent live frontend remains running')
        equal(control.lua('return vim.g.JetvimLifecycleControl'), 'live', 'independent live backend remains usable')
    try:
        editor = start()
        owned = list(editor._owned.values())
        equal(len(owned), 2, 'both TUI frontend and detached backend recorded')
        equal(all(editor.owner_token in record['command'] for record in owned), True, 'ownership token identifies both processes')
        editor.close(); editor.close()
        stopped(owned, 'ordinary close reaps frontend and backend')
        equal(editor.process.poll() is not None, True, 'frontend handle reaped')
        equal(editor.reader.is_alive(), False, 'PTY reader exits')
        equal(editor.pidfile.exists(), False, 'backend PID file removed')
        control_alive()

        project = fixture()
        failed = Editor.__new__(Editor)
        def fail_wait(*_args, **_kwargs): raise AssertionError('injected constructor failure')
        failed.wait = fail_wait
        try:
            failed.__init__(project, project / 'home/settings.lua', disabled=True, disable_lsp=True)
        except AssertionError as exc:
            equal(str(exc), 'injected constructor failure', 'startup failure remains visible')
        else: raise AssertionError('constructor failure was not exercised')
        equal(len(failed._owned), 2, 'startup failure retains exact frontend/backend ownership')
        stopped(failed._owned.values(), 'constructor failure cleans both processes')
        equal(failed.process.poll() is not None, True, 'constructor failure reaps frontend')
        equal(failed.reader.is_alive(), False, 'constructor failure stops PTY reader')
        control_alive()

        editor = start()
        owned = list(editor._owned.values())
        editor.process.terminate(); editor.process.wait(timeout=5)
        editor.close()
        stopped(owned, 'close remains safe after frontend already exited')
        control_alive()

        editor = start()
        owned = list(editor._owned.values())
        backend = editor.lua('return vim.fn.getpid()')
        # Only this newly created fixture is stopped; RPC cannot service qa!, so
        # teardown must use its captured identity rather than assume TUI exit.
        os.kill(backend, signal.SIGSTOP)
        try: editor.close()
        finally: processes.stop_owned(owned)
        stopped(owned, 'blocked backend cleanup uses bounded forced fallback')
        control_alive()

        project = fixture()
        ready = project / 'aborted.json'
        worker = project / 'abort.py'
        worker.write_text('''import json,os,signal
from pathlib import Path
root=Path(''' + repr(str(ROOT)) + ''')
scope={'__file__':str(root/'tests/autosave.py')}
exec((root/'tests/autosave.py').read_text().split('\\nwith tempfile.TemporaryDirectory',1)[0],scope)
project=Path(''' + repr(str(project)) + ''')
editor=scope['Editor'](project,project/'home/settings.lua',disabled=True,disable_lsp=True)
Path(''' + repr(str(ready)) + ''').write_text(json.dumps(list(editor._owned.values())))
os.kill(editor.lua('return vim.fn.getpid()'),signal.SIGSTOP)
os._exit(23)
''')
        result = processes.run_test([sys.executable, str(worker)], cwd=ROOT, env=os.environ, timeout=15)
        equal(result.returncode, 23, 'CI supervisor preserves failed test exit status')
        stopped(json.loads(ready.read_text()), 'CI manifest cleans backend after test bypasses finally')
        control_alive()

        # A manual PTY harness does not use Editor or write a process manifest.
        # Release its crash only once ancestry observation has seen the backend;
        # this tests reparenting deterministically rather than relying on sleeps.
        project = fixture()
        ready, release, backend_pid = project / 'manual.json', project / 'release', project / 'backend.pid'
        worker = project / 'manual.py'
        worker.write_text('''import json,os,pty,select,signal,subprocess,threading,time
from pathlib import Path
root=Path(''' + repr(str(ROOT)) + ''')
project=Path(''' + repr(str(project)) + ''')
master,slave=pty.openpty()
pidfile=Path(''' + repr(str(backend_pid)) + ''')
socket=project/'manual.sock'
record='lua vim.fn.writefile({tostring(vim.fn.getpid())},'+json.dumps(str(pidfile))+')'
frontend=subprocess.Popen([str(root/'jetvim'),str(project),'main.lua','--listen',str(socket),'--cmd',record],
 stdin=slave,stdout=slave,stderr=slave,cwd=root,env=dict(os.environ,TERM='xterm-256color',
 JETVIM_HOME=str(project/'home'),JETVIM_DISABLE_VCS='1',JETVIM_DISABLE_AUTOSAVE='1'))
os.close(slave)
def drain():
 while True:
  try:
   if select.select([master],[],[],.1)[0]: os.read(master,65536)
  except OSError:return
threading.Thread(target=drain,daemon=True).start()
deadline=time.monotonic()+10
while True:
 try:
  backend=int(pidfile.read_text())
  break
 except (OSError,ValueError):
  assert time.monotonic()<deadline
  time.sleep(.02)
Path(''' + repr(str(ready)) + ''').write_text(json.dumps({'frontend':frontend.pid,'backend':backend}))
while not Path(''' + repr(str(release)) + ''').exists():
 assert time.monotonic()<deadline
 time.sleep(.02)
os.kill(backend,signal.SIGSTOP)
os._exit(29)
''')
        def release_observed(records):
            if ready.exists() and not release.exists():
                try:
                    ids = json.loads(ready.read_text())
                except (OSError, ValueError):
                    return
                if any(record['pid'] == ids['backend'] for record in records):
                    release.write_text('backend observed')
        result = processes.run_test([sys.executable, str(worker)], cwd=ROOT, env=os.environ,
                                    timeout=15, observed=release_observed)
        equal(result.returncode, 29, 'CI preserves failed manual PTY test status')
        ids = json.loads(ready.read_text())
        equal(processes.identity(ids['frontend']), None, 'manual frontend cleaned after failed test')
        equal(processes.identity(ids['backend']), None, 'unregistered reparented backend cleaned after failed test')
        control_alive()

        ready = folder / 'timeout.json'
        worker = folder / 'timeout.py'
        worker.write_text('''import json,subprocess,sys,time
from pathlib import Path
child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])
Path(''' + repr(str(ready)) + ''').write_text(json.dumps({'parent':__import__('os').getpid(),'child':child.pid}))
time.sleep(60)
''')
        try:
            processes.run_test([sys.executable, str(worker)], cwd=ROOT, env=os.environ, timeout=5)
        except subprocess.TimeoutExpired:
            equal(True, True, 'CI timeout remains visible')
        else: raise AssertionError('CI timeout was not exercised')
        ids = json.loads(ready.read_text())
        equal(processes.identity(ids['parent']), None, 'timed-out Python owner is reaped')
        equal(processes.identity(ids['child']), None, 'timed-out test descendant is stopped')
        control_alive()

        manifest = folder / 'corrupt.jsonl'
        record = dict(next(iter(control._owned.values())))
        record['started'] = 'a different process start time'
        manifest.write_text('not-json\n{"pid":\n' + json.dumps(record) + '\n')
        equal(processes.cleanup_manifest(manifest), [], 'corrupt/stale records cannot select live process')
        control_alive()
        invalid = ROOT / 'forbidden-process-manifest.jsonl'
        try: processes.manifest_path(invalid)
        except ValueError: equal(invalid.exists(), False, 'manifest cannot write outside runtime directory')
        else: raise AssertionError('out-of-runtime manifest accepted')
        print(f'PASS: {support["checks"]} fixture process ownership/cleanup checks')
    finally:
        control.close()
