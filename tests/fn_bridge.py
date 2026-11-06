#!/usr/bin/env python3
"""Portable Fn navigation transport tests; optional safe compiled Swift checks."""
import importlib.util
import json
import os
from pathlib import Path
import pty
import select
import subprocess
import tty
import unittest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('jetvim_warp', ROOT / 'scripts/warp.py')
warp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(warp)


class FnBridge(unittest.TestCase):
    def test_existing_relay_indices_are_unchanged(self):
        bindings = json.loads((ROOT / 'config/keymap.json').read_text())
        sequences = warp.key_sequences(bindings)
        self.assertEqual(len(sequences), len(bindings))
        for index, item in enumerate(bindings, 1):
            with self.subTest(action=item['id']):
                expected = f'\x1b[{0xF0000 + index}u'.encode()
                self.assertEqual(sequences[item['id']], expected)
                self.assertEqual(warp.shortcut_sequence(item['id'], sequences), expected)

    def test_fn_selection_uses_standard_native_sequences(self):
        expected = {
            'native:shift-page-up': b'\x1b[5;2~',
            'native:shift-page-down': b'\x1b[6;2~',
            'native:shift-home': b'\x1b[1;2H',
            'native:shift-end': b'\x1b[1;2F',
        }
        self.assertEqual(warp.NATIVE_SEQUENCES, expected)
        for action, sequence in expected.items():
            with self.subTest(action=action):
                self.assertEqual(warp.shortcut_sequence(action, {}), sequence)

    def test_unrecognized_ids_are_not_forwarded(self):
        for action in ('READY', 'native:shift-up', 'native:anything', '\x1b[5;2~', 'not-an-action'):
            with self.subTest(action=action):
                self.assertIsNone(warp.shortcut_sequence(action, {}))

    def test_sequences_reach_only_the_private_pty(self):
        master, slave = pty.openpty()
        try:
            tty.setraw(slave)
            for action, expected in warp.NATIVE_SEQUENCES.items():
                with self.subTest(action=action):
                    os.write(master, warp.shortcut_sequence(action, {}))
                    ready, _, _ = select.select([slave], [], [], 2)
                    self.assertTrue(ready)
                    self.assertEqual(os.read(slave, 4096), expected)
        finally:
            os.close(master)
            os.close(slave)

    @unittest.skipUnless(os.environ.get('JETVIM_KEYBRIDGE_CHECKER'), 'compiled Swift helper supplied by lead/CI')
    def test_compiled_routing_without_permissions_or_event_tap(self):
        binary = Path(os.environ['JETVIM_KEYBRIDGE_CHECKER']).resolve()
        self.assertTrue(binary.is_relative_to(ROOT / '.jetvim'), 'Check helper must remain in local runtime')
        for flag, marker in (('--check-keymap', 'KEYMAP OK:'), ('--check-fn-keys', 'FN ROUTING OK:')):
            result = subprocess.run([str(binary), str(ROOT / 'config/keymap.json'), flag],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(marker, result.stdout)
            self.assertNotIn('permission', result.stderr.lower())
            if flag == '--check-fn-keys':
                line = next(line for line in result.stdout.splitlines() if line.startswith('NATIVE IDS: '))
                self.assertEqual(set(line.removeprefix('NATIVE IDS: ').split(',')), set(warp.NATIVE_SEQUENCES))


if __name__ == '__main__':
    unittest.main(verbosity=2)
