#!/usr/bin/env python3
"""Run test groups. Git fixtures are explicitly opt-in and reserved for CI/lead."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
GROUPS = {
    'core': ('integration', 'tui', 'launcher', 'sidebar', 'selection', 'tabs', 'appearance',
             'disk', 'workspace', 'workspace_autosave', 'tree_create', 'project_search', 'word_delete', 'paging', 'page_selection', 'fn_bridge', 'search', 'settings', 'hooks', 'oxlint', 'diagnostics_live', 'blame', 'blame_tui', 'terminal_layout', 'terminal_keys', 'resize', 'layout', 'overview', 'vcs_cache', 'gutter_cache', 'autosave', 'git_layout', 'git_focus'),
    'git': ('git_changes', 'vcs', 'git_gutter', ('blame', '--real'), ('disk', '--git-restore')),
    'languages': ('lsp', 'go_lsp'),
    'installer': ('install',),
}
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('group', choices=GROUPS)
args = parser.parse_args()
env = dict(os.environ, JETVIM_DISABLE_VCS='1', JETVIM_DISABLE_AUTOSAVE='1', PYTHONDONTWRITEBYTECODE='1')
for entry in GROUPS[args.group]:
    name, *flags = (entry,) if isinstance(entry, str) else entry
    print(f'Running {name}', flush=True)
    subprocess.run([sys.executable, str(ROOT / 'tests' / (name + '.py')), *flags], cwd=ROOT, env=env, check=True, timeout=300)
