"""Release-specific privacy and lifecycle regressions; no live sign-in."""
from pathlib import Path
from unittest import TestCase,main
from unittest.mock import patch
from desktop import maintenance,core
import test_accounts as account_tests
import test_accounts_ui as ui_tests


class ReleaseAccounts(TestCase):
    setUp=account_tests.AccountTests.setUp
    tearDown=account_tests.AccountTests.tearDown
    add=account_tests.AccountTests.add
    both=account_tests.AccountTests.both
    def test_one_damaged_credential_does_not_block_other_profile(self):
        self.both();self.service.credential_path('primary').write_bytes(b'invalid-test-data')
        state=self.service.status()
        self.assertTrue(state['credential_ok'])
        self.assertFalse(state['accounts'][0]['credential_ok'])
        self.service.login('259088888','test-only-password',False)
        self.service.select_account('primary')
        self.assertEqual(self.service.saved_student(),'')
        self.assertFalse(self.service.status()['credential_ok'])
        self.service.remove_account('primary')
        self.assertEqual(self.service.status()['selected_profile'],'secondary')


class ReleaseUI(TestCase):
    setUpClass=classmethod(ui_tests.StandardUiTests.setUpClass.__func__)
    setUp=ui_tests.StandardUiTests.setUp
    tearDown=ui_tests.StandardUiTests.tearDown
    def test_password_hint_is_visible_without_prefilling_password(self):
        self.window.show_login()
        self.app.processEvents()
        self.assertTrue(self.window.default_password_hint.isVisible())
        self.assertIn('Ahgydx@920',self.window.default_password_hint.text())
        self.assertEqual(self.window.password_edit.text(),'')


class MaintenanceTests(TestCase):
    def test_uninstall_filters_both_description_and_executable(self):
        with patch.object(core,'ps') as call:
            maintenance.uninstall_tasks(Path('example-install')/'app.exe')
        script=call.call_args.args[0]
        self.assertIn(core.TASK_DESCRIPTION,script)
        self.assertIn('$_.Execute -ne',script)
        self.assertIn(str((Path('example-install')/'app.exe').resolve()),script)
        self.assertNotIn('Remove-Item',script)

    def test_lifecycle_failure_has_nonzero_exit(self):
        with patch.object(maintenance,'install_tasks',side_effect=core.UserError('test')):
            self.assertEqual(maintenance.main(['--install-tasks']),1)


if __name__=='__main__':main()
