#!/usr/bin/env python3
"""Safe compiled terminal focus guards; never creates a keyboard event tap."""
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(os.environ.get('JETVIM_KEYBRIDGE_CHECKER'), 'compiled Swift helper supplied by lead/CI')
class TerminalBridge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = Path(os.environ['JETVIM_KEYBRIDGE_CHECKER']).resolve()
        if not cls.binary.is_relative_to(ROOT / '.jetvim'):
            raise AssertionError('Check helper must remain in local runtime')

    def run_helper(self, *arguments):
        return subprocess.run([str(self.binary), str(ROOT / 'config/keymap.json'), *arguments],
                              capture_output=True, text=True, timeout=15)

    def test_focus_guards_without_permissions_or_event_tap(self):
        # The helper checks both allowed apps, lookalikes, the other selected app,
        # missing/mismatched titles and empty tokens using only pure functions.
        for target in ((), ('warp',), ('terminal',)):
            with self.subTest(target=target):
                result = self.run_helper('--check-focus', *target)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('FOCUS GUARD OK: 20 cases', result.stdout)
                self.assertEqual(result.stderr, '')

    def test_existing_routing_checks_work_for_both_targets(self):
        bindings = json.loads((ROOT / 'config/keymap.json').read_text())
        count = sum(1 + len(item.get('aliases', [])) for item in bindings)
        for target in ('warp', 'terminal'):
            for flag, marker in (('--check-keymap', f'KEYMAP OK: {count} physical shortcuts'),
                                 ('--check-fn-keys', 'FN ROUTING OK: 57 cases')):
                with self.subTest(target=target, flag=flag):
                    result = self.run_helper(flag, target)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn(marker, result.stdout)
                    self.assertEqual(result.stderr, '')

    def test_invalid_target_rejected_before_accessibility(self):
        for target in ('auto', '*', 'com.apple.Terminal', 'warp,terminal', 'Terminal'):
            with self.subTest(target=target):
                result = self.run_helper('--check-focus', target)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stderr.strip(), 'Unknown bridge target: ' + target)
                self.assertEqual(result.stdout, '')

    def test_empty_session_rejected_before_accessibility(self):
        for target in ('warp', 'terminal'):
            with self.subTest(target=target):
                result = self.run_helper('', target)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stderr.strip(), 'Session title must not be empty')
                self.assertEqual(result.stdout, '')

    def test_extra_target_arguments_rejected_before_accessibility(self):
        result = self.run_helper('--check-focus', 'terminal', 'warp')
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stderr.startswith('Usage: keybridge '), result.stderr)
        self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main(verbosity=2)
