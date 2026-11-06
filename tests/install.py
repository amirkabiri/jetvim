#!/usr/bin/env python3
"""Offline installer checks. All fixtures live under this checkout; Git is mocked."""
import hashlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / '.jetvim' / 'installer-tests'
BASE.mkdir(parents=True, exist_ok=True)

class Install(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(dir=BASE, prefix='case '))
        self.addCleanup(shutil.rmtree, self.tmp)
        self.home = self.tmp / "user's home"
        self.source = self.tmp / 'source'
        self.mock = self.tmp / 'mock'
        self.mock.mkdir()
        self.source.mkdir()
        (self.source / 'config').mkdir()
        (self.source / 'init.lua').write_text('-- fixture\n')
        (self.source / 'config/settings.lua').write_text('return { autosave = true }\n')
        shutil.copy2(ROOT / 'jetvim', self.source / 'jetvim')
        self.asset = self.tmp / 'nvim.tar.gz'
        with tarfile.open(self.asset, 'w:gz') as tar:
            content = b'#!/bin/sh\nif [ "$1" = --version ]; then echo "NVIM v0.12.6"; else printf "%s\\n" "$JETVIM_HOME" "$JETVIM_ROOT" "$@"; fi\n'
            info = tarfile.TarInfo('nvim/bin/nvim'); info.mode = 0o755; info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
        self.digest = hashlib.sha256(self.asset.read_bytes()).hexdigest()
        self.manifest()
        self.script('uname', '#!/bin/sh\ncase "$1" in -s) echo "${MOCK_OS:-Darwin}";; -m) echo "${MOCK_ARCH:-arm64}";; esac\n')
        self.script('nvim', '#!/bin/sh\necho "NVIM v0.10.0"\n')
        self.script('curl', f'#!{sys.executable}\nimport os,shutil,sys\na=sys.argv\nopen(os.environ["MOCK_LOG"],"a").write(" ".join(a)+"\\n")\nshutil.copyfile(os.environ["MOCK_ASSET"], a[a.index("-o")+1])\n')
        self.script('git', f'#!{sys.executable}\nimport os,shutil,sys\na=sys.argv[1:]\nopen(os.environ["MOCK_GIT_LOG"],"a").write(repr(a)+"\\n")\nif a[0]=="clone": shutil.copytree(os.environ["MOCK_SOURCE"],a[-1])\nelif "get-url" in a: print("https://github.com/amirkabiri/jetvim.git")\n')
        self.env = dict(os.environ, PATH=str(self.mock)+':'+os.environ['PATH'],
                        JETVIM_HOME=str(self.home), JETVIM_BIN_DIR=str(self.tmp/'bin'),
                        JETVIM_SOURCE_DIR=str(self.source), JETVIM_SKIP_LANGUAGES='1',
                        JETVIM_SKIP_RIPGREP='1', MOCK_ASSET=str(self.asset),
                        MOCK_LOG=str(self.tmp/'downloads'), MOCK_GIT_LOG=str(self.tmp/'git-log'),
                        MOCK_SOURCE=str(self.source))
    def script(self, name, text):
        p=self.mock/name; p.write_text(text); p.chmod(0o755)
    def manifest(self, digest=None):
        (self.source/'config/install-assets.tsv').write_text(''.join(
            f'neovim\t{p}\t{a}\thttps://example.invalid/{p}-{a}.tar.gz\t{digest or self.digest}\ttree\n'
            for p in ['macos','linux'] for a in ['arm64','x86_64']))
    def run_install(self, ok=True):
        result=subprocess.run(['bash', str(ROOT/'install.sh')],env=self.env,text=True,capture_output=True)
        self.assertEqual(result.returncode==0,ok,result.stdout+result.stderr)
        return result
    def test_four_platforms_pinned_downloads(self):
        for system,arch,expected in [('Darwin','arm64','macos-arm64'),('Darwin','x86_64','macos-x86_64'),('Linux','aarch64','linux-arm64'),('Linux','x86_64','linux-x86_64')]:
            with self.subTest(system=system,arch=arch):
                self.env.update(MOCK_OS=system,MOCK_ARCH=arch)
                self.run_install()
                self.assertIn(expected,(self.tmp/'downloads').read_text())
                shutil.rmtree(self.home/'tools/neovim')
    def test_update_preserves_settings_runtime_and_wrapper_quotes(self):
        self.run_install()
        settings=self.home/'settings.lua'; settings.write_text('return { custom = true }')
        (self.home/'cache/preserved').write_text('yes')
        self.run_install()
        self.assertEqual(settings.read_text(),'return { custom = true }')
        self.assertTrue((self.home/'cache/preserved').exists())
        result=subprocess.run([str(self.tmp/'bin/jetvim'),'--headless'],env=self.env,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn(str(self.home),result.stdout)
        self.assertIn(str(self.source),result.stdout)
        self.assertEqual(len((self.tmp/'downloads').read_text().splitlines()),1)
    def test_checksum_failure_no_settings_or_entrypoint(self):
        self.manifest('0'*64)
        result=self.run_install(False)
        self.assertIn('checksum mismatch',result.stderr)
        self.assertFalse((self.home/'settings.lua').exists())
        self.assertFalse((self.home/'tools/neovim').exists())
    def test_existing_binary_collision(self):
        (self.tmp/'bin').mkdir(); target=self.tmp/'bin/jetvim'; target.write_text('mine')
        result=self.run_install(False)
        self.assertIn('Refusing to replace',result.stderr)
        self.assertEqual(target.read_text(),'mine')
    def test_existing_compatible_neovim_reused(self):
        self.script('nvim','#!/bin/sh\necho "NVIM v0.11.2"\n')
        self.run_install()
        self.assertFalse((self.tmp/'downloads').exists())
    def test_unknown_platform_rejected(self):
        self.env['MOCK_ARCH']='mips'
        self.assertIn('Supported architectures',self.run_install(False).stderr)
    def test_clone_and_fast_forward_update_use_mock_only(self):
        self.env.pop('JETVIM_SOURCE_DIR')
        self.run_install(); self.run_install()
        log=(self.tmp/'git-log').read_text()
        self.assertEqual(log.count("'clone'"),1)
        self.assertIn("'fetch', 'origin', 'main'",log)
        self.assertIn("'merge', '--ff-only', 'FETCH_HEAD'",log)
        self.assertTrue((self.home/'code/init.lua').exists())
    def test_gopls_patchers_keep_source_untouched(self):
        import json
        script = (ROOT/'scripts/setup-gopls.sh').read_text()
        upstream = self.tmp/'module-cache'
        upstream.mkdir()
        original = 'package main\nimport (\n)\nfunc main() { telemetry.Start(telemetry.Config{}) }\n'
        (upstream/'main.go').write_text(original)
        (upstream/'main.go').chmod(0o444)
        commands = [('python3', script.split("<<'PY'\n",1)[1].split('\nPY\n',1)[0])]
        if shutil.which('node'):
            commands.append(('node', script.split("<<'JS'\n",1)[1].split('\nJS\n',1)[0]))
        for executable, program in commands:
            with self.subTest(patcher=executable):
                build=self.tmp/('build-'+executable); build.mkdir()
                (build/'module.json').write_text(json.dumps({'Dir':str(upstream)}))
                result=subprocess.run([executable,'-',str(build)],input=program,text=True,capture_output=True)
                self.assertEqual(result.returncode,0,result.stderr)
                patched=(build/'source/main.go').read_text()
                self.assertIn('TelemetryDir: os.Getenv("TEST_TELEMETRY_DIR")',patched)
                self.assertEqual((upstream/'main.go').read_text(),original)
                self.assertEqual((build/'module-dir').read_text(),str(build/'source'))
    def test_source_symlink_chain_resolves(self):
        self.run_install()
        link=self.tmp/'linked'; link.symlink_to('source/jetvim')
        env=dict(self.env, JETVIM_HOME=str(self.home))
        result=subprocess.run([str(link),'--headless'],env=env,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn(str(self.source),result.stdout)

if __name__=='__main__': unittest.main(verbosity=2)
