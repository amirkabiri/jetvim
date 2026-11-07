#!/usr/bin/env python3
"""Run test groups. Git fixtures are explicitly opt-in and reserved for CI/lead."""
import argparse
import importlib.util
import os
from pathlib import Path
import signal
import sys

ROOT = Path(__file__).resolve().parent.parent
_process_spec = importlib.util.spec_from_file_location('jetvim_fixture_processes', ROOT / 'tests/process_support.py')
process_support = importlib.util.module_from_spec(_process_spec)
_process_spec.loader.exec_module(process_support)
GROUPS = {
    'core': ('integration', 'tui', 'launcher', 'process_lifecycle', 'sidebar', 'selection', 'tabs', 'appearance',
             'disk', 'workspace', 'workspace_autosave', 'tree_create', 'tree_delete', 'tree_rename', 'tree_context', 'tree_reveal_lifecycle', 'project_search', 'project_search_selection', 'word_delete', 'paging', 'page_selection', 'definition_usages', 'usages_open_all', 'fn_bridge', 'mac_bridge', 'terminal_bridge', 'search', 'search_close_lifecycle', 'file_location', 'settings', 'settings_menu', 'hooks', 'oxlint', 'diagnostics_live', 'blame', 'blame_tui', 'terminal_layout', 'terminal_keys', 'terminal_paste', 'resize', 'layout', 'overview', 'vcs_cache', 'gutter_cache', 'autosave', 'git_layout', 'git_focus'),
    'git': ('git_changes', 'vcs', 'git_gutter', ('blame', '--real'), ('disk', '--git-restore')),
    'languages': ('lsp', 'go_lsp'),
    'installer': ('install',),
}
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('group', choices=GROUPS)
args = parser.parse_args()
env = dict(os.environ, JETVIM_DISABLE_VCS='1', JETVIM_DISABLE_AUTOSAVE='1', PYTHONDONTWRITEBYTECODE='1')
def interrupted(signum, _frame):
    raise SystemExit(128 + signum)
for signum in (signal.SIGTERM, signal.SIGHUP):
    signal.signal(signum, interrupted)
for entry in GROUPS[args.group]:
    name, *flags = (entry,) if isinstance(entry, str) else entry
    print(f'Running {name}', flush=True)
    process_support.run_test([sys.executable, str(ROOT / 'tests' / (name + '.py')), *flags],
                             cwd=ROOT, env=env, timeout=300).check_returncode()
