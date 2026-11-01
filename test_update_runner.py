"""Installer failure recovery and task-independent updater regression tests."""
import hashlib
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import patch
from desktop import update_runner as runner
from desktop.update_lock import installation_lock


class RunnerTests(TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name);self.work=root/'ahut-update-test';self.work.mkdir()
        self.target=root/'app with spaces';self.target.mkdir()
        (self.target/runner.APP).write_bytes(b'old');(self.target/'_internal').mkdir()
        (self.target/'_internal'/'lib').write_bytes(b'old-library')
        (self.target/'install-options.ini').write_bytes(b'keep-options')
        self.installer=self.work/'setup.exe';self.installer.write_bytes(b'installer')
        self.result=root/'result.json'
        self.job=dict(work=str(self.work),target=str(self.target),installer=str(self.installer),result=str(self.result),
            sha256=hashlib.sha256(b'installer').hexdigest(),version='1.5.4')

    def test_update_succeeds_and_only_passes_update_mode(self):
        calls=[]
        def execute(command,**kwargs):
            calls.append(command)
            if isinstance(command,str):
                (self.target/runner.APP).write_bytes(b'new')
                self.assertTrue(command.endswith('/D='+str(self.target)))
                self.assertIn('/UPDATE',command)
            elif '--self-check' in command:
                Path(command[-1]).write_text(json.dumps(dict(ok=True,version='1.5.4')))
            return SimpleNamespace(returncode=0)
        with patch.object(runner.subprocess,'run',side_effect=execute):runner.run(self.job)
        self.assertTrue(json.loads(self.result.read_text())['ok'])
        self.assertEqual((self.target/'install-options.ini').read_bytes(),b'keep-options')
        self.assertEqual(len(calls),3)

    def test_failed_install_restores_original_files(self):
        def execute(command,**kwargs):
            if isinstance(command,str):
                (self.target/runner.APP).write_bytes(b'broken')
                (self.target/'_internal'/'lib').write_bytes(b'broken')
                return SimpleNamespace(returncode=4)
            return SimpleNamespace(returncode=0)
        with patch.object(runner.subprocess,'run',side_effect=execute),self.assertRaises(RuntimeError):runner.run(self.job)
        self.assertEqual((self.target/runner.APP).read_bytes(),b'old')
        self.assertEqual((self.target/'_internal'/'lib').read_bytes(),b'old-library')

    def test_in_use_executable_refused_without_backup_or_install(self):
        with patch.object(runner.subprocess,'run',return_value=SimpleNamespace(returncode=1)) as execute,self.assertRaisesRegex(RuntimeError,'正在使用'):
            runner.run(self.job)
        execute.assert_called_once();self.assertFalse((self.work/'backup').exists())

    def test_failed_post_install_validation_restores_original(self):
        def execute(command,**kwargs):
            if isinstance(command,str):(self.target/runner.APP).write_bytes(b'new')
            elif '--self-check' in command:Path(command[-1]).write_text(json.dumps(dict(ok=True,version='wrong')))
            return SimpleNamespace(returncode=0)
        with patch.object(runner.subprocess,'run',side_effect=execute),self.assertRaisesRegex(RuntimeError,'版本'):
            runner.run(self.job)
        self.assertEqual((self.target/runner.APP).read_bytes(),b'old')

    def test_tampered_installer_never_executes(self):
        self.installer.write_bytes(b'tampered')
        with patch.object(runner.subprocess,'run') as execute,self.assertRaises(RuntimeError):runner.run(self.job)
        execute.assert_not_called()

    def test_update_and_scheduled_worker_cannot_replace_files_concurrently(self):
        executable=self.target/runner.APP
        code="from desktop.update_lock import installation_lock;import time,sys\nwith installation_lock(sys.argv[1]):\n print('locked',flush=True)\n time.sleep(2)\n"
        process=subprocess.Popen([sys.executable,'-B','-c',code,str(executable)],stdout=subprocess.PIPE,text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(),'locked')
            with self.assertRaises(RuntimeError):
                with installation_lock(executable):pass
            with installation_lock(executable,timeout=5):pass
        finally:
            process.wait(timeout=10);process.stdout.close()


if __name__=='__main__':main()
