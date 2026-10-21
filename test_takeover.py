"""Owned legacy task compatibility and safe takeover rollback. Offline."""
import copy
from pathlib import Path
from unittest import TestCase,main
from unittest.mock import patch
from desktop import core
import test_accounts as fixtures


class LegacyValidationTests(TestCase):
    def task(self):
        return {'description':r'Managed by AHUT-WQQD Desktop v1 at C:\legacy\AHUT-SignIn',
                'enabled':True,'state':'Ready','actions':[{'execute':'powershell.exe',
                'arguments':r'-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "C:\legacy\AHUT-SignIn\run-task.ps1"'}]}

    def test_dsh_task_is_recognized_with_matching_script(self):
        self.assertEqual(core.WindowsTask.validate_legacy(self.task(),Path(r'C:\original'))['root'],r'C:\legacy\AHUT-SignIn')

    def test_unrelated_marker_and_changed_command_are_rejected(self):
        for field in ('description','arguments','execute'):
            value=self.task()
            if field=='description':value[field]='Unrelated task'
            else:value['actions'][0][field]='other-command'
            with self.assertRaises(core.UserError):core.WindowsTask.validate_legacy(value,Path(r'C:\original'))

    def test_running_legacy_is_never_disabled(self):
        value=self.task();value['state']='Running';task=core.WindowsTask()
        with patch.object(task,'legacy_info',return_value=value),patch.object(task,'_set_legacy') as change:
            with self.assertRaises(core.UserError):task.disable_old(Path(r'C:\original'))
            change.assert_not_called()


class TakeoverTests(TestCase):
    setUp=fixtures.AccountTests.setUp
    tearDown=fixtures.AccountTests.tearDown
    add=fixtures.AccountTests.add

    def test_existing_managed_plan_cannot_enable_before_legacy_validation(self):
        self.add();self.service.resume();task=self.tasks['primary'];task.enabled=False
        before=(self.service.data/'profiles.json').read_bytes();calls=list(task.calls)
        with patch.object(task,'disable_old',side_effect=core.UserError('Unrelated legacy')):
            with self.assertRaises(core.UserError):self.service.resume()
        self.assertFalse(task.enabled);self.assertEqual(task.calls,calls)
        self.assertEqual((self.service.data/'profiles.json').read_bytes(),before)

    def test_failure_restores_actual_disabled_state_and_old_owner(self):
        self.add();self.service.resume();task=self.tasks['primary'];task.enabled=False;task.old_disabled=False
        task.failure=lambda scheduled,enabled:enabled
        with self.assertRaises(core.UserError):self.service.resume()
        self.assertFalse(task.enabled);self.assertFalse(task.old_disabled)
        self.assertEqual(task.calls[-1],('22:00',False))


if __name__=='__main__':main()
