"""Standard-edition UI behavior with fake school and scheduler."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import tempfile
from pathlib import Path
from unittest import TestCase,main
from unittest.mock import patch,Mock,AsyncMock
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import QTime
from PySide6.QtTest import QTest
from desktop import accounts,core,gui
from test_desktop import Scheduler
import app as legacy


class StandardUiTests(TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='ahut-standard-ui-');self.root=Path(self.tmp.name);self.original=(legacy.DATA,legacy.ACCOUNT,legacy.ROOT)
        self.execution=patch.object(core,'execute',return_value=Mock(returncode=0,stdout='',stderr=''));self.execution.start()
        self.sid=patch.object(core.Service,'_sid',return_value='S-1-5-21-1');self.sid.start()
        self.tasks={slot:Scheduler() for slot in accounts.SLOTS}
        self.service=accounts.StandardService(data=self.root/'data',migrate=False,scheduler_factory=self.tasks.get)
        self.verify=patch.object(self.service,'_verify',new=AsyncMock(return_value='测试账号'));self.verify.start()
        self.service.login('259099999','offline',False);self.service.resume();self.service.login('259088888','offline',False,profile_id=None)
        from desktop.appearance import Preferences
        Preferences(self.service.data).set(theme='light',startup_animation=False,auto_check_updates=False)
        self.window=gui.Window(self.service);self.window.show();self.window.enter_offline();self.app.processEvents()
    def tearDown(self):
        w=self.window;w.refresh_timer.stop();w.task_timer.stop();w.countdown_timer.stop();w.event_timer.stop();w.wallpaper_timer.stop();w.update_timer.stop();w.update_start_timer.stop();w.update_pool.waitForDone(2000);w.pool.waitForDone(2000);self.app.processEvents();w.tray.hide();w._quitting=True;w.close();w.deleteLater();self.app.processEvents()
        self.verify.stop();self.execution.stop();self.sid.stop();legacy.DATA,legacy.ACCOUNT,legacy.ROOT=self.original;self.tmp.cleanup()
    def wait_job(self):
        for _ in range(120):
            self.app.processEvents()
            if not self.window.busy:return
            QTest.qWait(30)
        self.fail('UI operation did not finish')
    def test_picker_resets_unsaved_time_and_does_not_pause_other_account(self):
        self.window.go(1);self.window.time_edit.setTime(QTime(22,30));self.window.account_combo.setCurrentIndex(self.window.account_combo.findData('primary'));self.wait_job()
        self.assertEqual(self.window.state['selected_profile'],'primary');self.assertEqual(self.window.time_edit.text(),'22:00');self.assertTrue(self.tasks['primary'].enabled);self.assertFalse(self.tasks['secondary'].enabled)
        self.assertIn('账号 1',self.window.account_summary.text());self.assertIn('账号 2',self.window.account_summary.text())
    def test_full_account_slots_disable_add_and_vps_remains_disabled_after_jobs(self):
        self.assertFalse(self.window.add_account_button.isEnabled());self.assertFalse(self.window.quick_cloud.isEnabled());self.window.toggle_enabled(True);self.wait_job()
        self.assertFalse(self.window.quick_cloud.isEnabled());self.assertFalse(self.window.detail_cloud.isEnabled());self.assertFalse(self.window.add_account_button.isEnabled())
    def test_removal_confirmation_preserves_other_account_and_opens_free_slot(self):
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.No):self.window.remove_current_account()
        self.assertEqual(len(self.service.status()['accounts']),2)
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):self.window.remove_current_account();self.wait_job()
        self.assertEqual(len(self.window.state['accounts']),1);self.assertTrue(self.window.add_account_button.isEnabled());self.assertTrue(self.tasks['primary'].enabled)
        self.window.show_login(add=True);self.assertTrue(self.window.login_adding);self.assertEqual(self.window.student_edit.text(),'');self.assertEqual(self.window.password_edit.text(),'')
    def test_current_profile_plan_and_history_have_clear_identity(self):
        self.window.go(1);self.window.time_edit.setTime(QTime(22,20));self.window.apply_time();self.wait_job()
        self.assertEqual(self.tasks['secondary'].time,'22:20');self.assertTrue(self.tasks['primary'].enabled)
        self.assertIn('当前账号',self.window.schedule_saved.text());self.window.go(3);self.window.render_history()
        messages=[self.window.history_table.item(row,3).text() for row in range(self.window.history_table.rowCount())]
        self.assertTrue(any('账号 2' in t for t in messages));self.assertTrue(any('账号 1' in t for t in messages))

    def test_reusing_account_slot_does_not_inherit_old_failure_status(self):
        self.service.account_event('secondary','failed','旧账号执行未成功。')
        self.service.remove_account('secondary');self.service.login('259066666','offline',False,profile_id=None);self.service.resume()
        self.window.refresh();self.assertEqual(self.window.today_status.text(),'等待执行')
        self.assertNotIn('旧账号',self.window.recent_label.text())


if __name__=='__main__':main()
