"""Own only fixture processes; identify them again before sending a signal."""
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / '.jetvim'
OWNER = re.compile(r'^JetvimTestOwner-[0-9a-f]{32}$')


def identity(pid, token=None):
    if not isinstance(pid, int) or pid <= 1 or pid == os.getpid():
        return None
    result = subprocess.run(['ps', '-ww', '-p', str(pid), '-o', 'stat=', '-o', 'lstart=', '-o', 'command='],
                            capture_output=True, text=True, timeout=3, env=dict(os.environ, LC_ALL='C'))
    parts = result.stdout.strip().split(None, 6)
    if result.returncode or len(parts) != 7 or parts[0].startswith(('Z', 'X')):
        return None
    command = parts[6]
    if token is not None and (not OWNER.fullmatch(token) or token not in command):
        return None
    return {'pid': pid, 'started': ' '.join(parts[1:6]), 'command': command, 'token': token}


def matches(record):
    if not isinstance(record, dict):
        return False
    try:
        current = identity(record.get('pid'), record.get('token'))
    except (OSError, subprocess.SubprocessError, TypeError):
        return False
    return current is not None and current == record


def stop_owned(records, grace=1):
    """Never select processes by name, cwd, broad PGID, or a reused PID."""
    records = list({(r['pid'], r['started'], r['command']): r for r in records if matches(r)}.values())
    for record in records:
        if matches(record):
            try:
                os.kill(record['pid'], signal.SIGTERM)
            except ProcessLookupError:
                pass
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline and any(matches(r) for r in records):
        time.sleep(.03)
    for record in records:
        if matches(record):
            try:
                os.kill(record['pid'], signal.SIGKILL)
            except ProcessLookupError:
                pass
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline and any(matches(r) for r in records):
        time.sleep(.03)
    return [r for r in records if matches(r)]


def manifest_path(value):
    path = Path(value).resolve()
    if not path.is_relative_to(STATE.resolve()):
        raise ValueError('Fixture process manifests must remain inside .jetvim')
    return path


def register(record):
    value = os.environ.get('JETVIM_TEST_PROCESS_MANIFEST')
    if not value or not record:
        return
    path = manifest_path(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, (json.dumps(record) + '\n').encode())
    finally:
        os.close(fd)


def cleanup_manifest(value):
    path = manifest_path(value)
    if not path.exists():
        return []
    records = []
    for line in path.read_text(errors='replace').splitlines():
        try:
            record = json.loads(line)
            # Only fixture registrations containing their unique argv token are
            # accepted from disk. A corrupt record cannot select arbitrary PIDs.
            if (isinstance(record, dict) and isinstance(record.get('token'), str)
                    and OWNER.fullmatch(record['token']) and isinstance(record.get('command'), str)
                    and record['token'] in record['command'] and isinstance(record.get('started'), str)
                    and isinstance(record.get('pid'), int)):
                records.append(record)
        except (ValueError, TypeError):
            continue
    return stop_owned(records)


def process_table():
    result = subprocess.run(['ps', '-ww', '-e', '-o', 'pid=', '-o', 'ppid=', '-o', 'stat=', '-o', 'lstart=', '-o', 'command='],
                            capture_output=True, text=True, timeout=3, env=dict(os.environ, LC_ALL='C'))
    result.check_returncode()
    rows = {}
    for line in result.stdout.splitlines():
        parts = line.split(None, 8)
        if len(parts) == 9 and not parts[2].startswith(('Z', 'X')):
            try:
                pid, ppid = int(parts[0]), int(parts[1])
                rows[pid] = (ppid, {'pid': pid, 'started': ' '.join(parts[3:8]), 'command': parts[8], 'token': None})
            except ValueError:
                continue
    return rows


def descendants(parent, rows=None):
    """Snapshot descendants while their parent still identifies ownership."""
    rows = process_table() if rows is None else rows
    owned, records = {parent}, []
    while True:
        found = [record for pid, (ppid, record) in rows.items()
                 if ppid in owned and pid not in owned and pid != os.getpid()]
        if not found:
            return records
        for record in found:
            owned.add(record['pid'])
            records.append(record)


def run_test(argv, *, cwd, env, timeout=300, observed=None):
    """Clean registered backends even if a test aborts before its finally block."""
    directory = STATE / 'ci-processes'
    directory.mkdir(parents=True, exist_ok=True)
    manifest = directory / (uuid.uuid4().hex + '.jsonl')
    child_env = dict(env, JETVIM_TEST_PROCESS_MANIFEST=str(manifest))
    process = subprocess.Popen(argv, cwd=cwd, env=child_env, start_new_session=True)
    stop_watch, known = threading.Event(), {}
    def observe():
        # Manual harnesses may lack a registration, and their parent can exit
        # before finally executes. Remember ancestry while it is still intact.
        rows = process_table()
        for pid, record in list(known.items()):
            current = rows.get(pid)
            if (not current or current[1]['started'] != record['started']
                    or current[1]['command'] != record['command']):
                del known[pid]
        for record in descendants(process.pid, rows):
            known[record['pid']] = record
        if observed:
            observed(list(known.values()))
    def watch():
        while not stop_watch.is_set():
            try:
                observe()
            except (OSError, subprocess.SubprocessError):
                pass  # Manifest cleanup remains available if ps briefly fails.
            stop_watch.wait(.15)
    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    try:
        returncode = process.wait(timeout=timeout)
        return subprocess.CompletedProcess(argv, returncode)
    finally:
        stop_watch.set()
        watcher.join(timeout=4)
        # Capture descendants while their parent still identifies ownership;
        # detached Nvim backends are not necessarily in the frontend's group.
        if process.poll() is None:
            try:
                observe()
            except (OSError, subprocess.SubprocessError):
                pass
        # Apply the recorded identity even after nonzero/abrupt parent exit.
        # Rechecking immediately before signals rejects PID reuse.
        ancestry_survivors = stop_owned(reversed(list(known.values())))
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        survivors = cleanup_manifest(manifest)
        remaining = [r for r in survivors + ancestry_survivors if matches(r)]
        if remaining:
            raise RuntimeError('Fixture process cleanup failed: ' + repr([r['pid'] for r in remaining]))
