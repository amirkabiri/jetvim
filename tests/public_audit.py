#!/usr/bin/env python3
"""Regression checks for the redacted public-source scanner, without Git."""
from contextlib import redirect_stdout
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('public_audit', ROOT / 'scripts/public-audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
STATE = ROOT / '.jetvim'
STATE.mkdir(exist_ok=True)


class AuditTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='public-audit-', dir=STATE)
        self.root = Path(self.folder.name)
        self.previous = audit.ROOT
        audit.ROOT = self.root

    def tearDown(self):
        audit.ROOT = self.previous
        self.folder.cleanup()

    def scan(self):
        output = io.StringIO()
        with redirect_stdout(output):
            failed = audit.main()
        return failed, output.getvalue()

    def test_redacts_credentials_and_paths(self):
        secret = 'gh' + 'p_' + 'Z' * 36
        private_path = '/' + 'Users/' + 'example/private-project'
        (self.root / 'README.md').write_text(secret + '\n' + private_path)
        failed, output = self.scan()
        self.assertTrue(failed)
        self.assertIn('README.md:1: GitHub token [value redacted]', output)
        self.assertIn('README.md:2: private home path [value redacted]', output)
        self.assertNotIn(secret, output)
        self.assertNotIn(private_path, output)

    def test_excludes_runtime_and_generated_state(self):
        for directory in ('.git', '.jetvim', '.idea'):
            target = self.root / directory
            target.mkdir()
            (target / 'private.txt').write_text('gh' + 'p_' + 'Z' * 36)
        (self.root / 'README.md').write_text('# Public example\n')
        failed, output = self.scan()
        self.assertFalse(failed, output)
        self.assertIn('1 files, 0 findings', output)

    def test_reserved_email_is_safe_and_personal_email_is_redacted(self):
        (self.root / 'README.md').write_text('test' + '@' + 'example.invalid')
        self.assertFalse(self.scan()[0])
        email = 'someone' + '@' + 'private-domain.test'
        (self.root / 'README.md').write_text(email)
        failed, output = self.scan()
        self.assertTrue(failed)
        self.assertIn('email address requiring review', output)
        self.assertNotIn(email, output)

    def test_unknown_binary_requires_review(self):
        (self.root / 'assets').mkdir()
        (self.root / 'assets/unreviewed.bin').write_bytes(b'\xff\x00')
        failed, output = self.scan()
        self.assertTrue(failed)
        self.assertIn('binary file requires manual review', output)


if __name__ == '__main__':
    unittest.main()
