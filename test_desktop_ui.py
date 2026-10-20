"""Offscreen Qt component tests; no external UI automation or school calls."""
import os
import asyncio
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch, AsyncMock

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import QTime, QThread

import app as legacy
from desktop import core, gui
from test_desktop import Scheduler


class QtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([]); cls.app.setStyle('Fusion'); cls.app.setStyleSheet(gui.STYLES)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='ahut-qt-test-'); self.folder=Path(self.temp.name)
        self.previous=(legacy.DATA,legacy.ACCOUNT,legacy.ROOT)
        self.exec_patch=patch.object(core,'execute',return_value=Mock(returncode=0,stdout='',stderr='')); self.exec_patch.start()
        self.sid_patch=patch.object(core.Service,'_sid',return_value='S-1-5-21-1'); self.sid_patch.start()
        self.service=core.Service(data=self.folder/'data',old_root=self.folder/'old',scheduler=Scheduler(),migrate=False)
        self.service.settings.update(auto_login=False,managed=True); self.service.save()
        self.window=gui.Window(self.service); self.window.show(); self.app.processEvents()

    def tearDown(self):
        self.window.refresh_timer.stop(); self.window.task_timer.stop(); self.window.countdown_timer.stop(); self.window.pool.waitForDone(2000); self.app.processEvents()
        self.window.tray.hide(); self.window._quitting=True; self.window.close(); self.window.deleteLater(); self.app.processEvents()
        self.exec_patch.stop(); self.sid_patch.stop(); legacy.DATA,legacy.ACCOUNT,legacy.ROOT=self.previous; self.temp.cleanup()

    def wait_job(self):
        for _ in range(100):
            self.app.processEvents()
            if not self.window.busy: return
            QTest.qWait(40)
        self.fail('Qt background job did not complete')

    def test_pages_and_daily_time_editor(self):
        self.window.enter_offline(); self.window.go(1); self.app.processEvents()
        self.assertEqual(self.window.page_heading.text(),'定时设置')
        self.assertEqual(self.window.time_edit.minimumTime(),QTime(21,20))
        self.window.time_edit.setTime(QTime(22,10)); self.assertIn('未保存',self.window.schedule_saved.text())
        self.window.go(4); self.assertEqual(self.window.page_heading.text(),'账号与连接')

    def test_daily_time_text_has_visible_editing_width(self):
        self.window.enter_offline(); self.window.go(1); self.app.processEvents()
        inner=self.window.time_edit.lineEdit()
        self.assertGreater(inner.width(),inner.fontMetrics().horizontalAdvance('22:00')+20)
        self.assertEqual(self.window.time_edit.text(),'22:00')

    def test_successful_school_login_leaves_signin_uninvoked(self):
        with patch.object(self.service,'_verify',new=AsyncMock(return_value='测试同学')),patch.object(legacy,'perform') as signin:
            self.window.student_edit.setText('259099999'); self.window.password_edit.setText('only-for-offline-test'); self.window.login_button.click(); self.wait_job()
            self.assertEqual(self.window.root_stack.currentIndex(),1); self.assertTrue(self.window.authenticated); self.assertEqual(self.window.password_edit.text(),''); signin.assert_not_called()

    def test_invalid_login_displays_error_without_leaving_login_screen(self):
        self.window.student_edit.setText('abc'); self.window.password_edit.setText('test'); self.window.login_button.click(); self.wait_job()
        self.assertEqual(self.window.root_stack.currentIndex(),0); self.assertTrue(self.window.login_error.isVisible()); self.assertFalse(self.window.authenticated)

    def test_rejected_password_after_network_wait_can_be_retried(self):
        legacy.save_account({'student_id':'259099999','password_hash':'a'*32})
        before=legacy.ACCOUNT.read_bytes()
        threads=[]
        original_notify=self.window.notify
        def notify(*args,**kwargs):
            threads.append(QThread.currentThread()==self.app.thread())
            return original_notify(*args,**kwargs)
        self.window.notify=notify
        async def reject(account):
            await asyncio.sleep(.15)
            raise core.UserError('学号或考勤密码未通过验证，请检查后重试。')
        with patch.object(self.service,'_verify',side_effect=reject),patch.object(legacy,'perform') as signin:
            self.window.student_edit.setText('259099999'); self.window.password_edit.setText('wrong-test-password')
            self.window.login_button.click(); self.wait_job()
            self.assertTrue(self.window.isVisible()); self.assertEqual(self.window.root_stack.currentIndex(),0)
            self.assertTrue(self.window.login_error.isVisible()); self.assertTrue(self.window.login_button.isEnabled())
            self.assertEqual(legacy.ACCOUNT.read_bytes(),before); signin.assert_not_called()
        self.assertTrue(all(threads),'Login result touched widgets outside the UI thread')
        with patch.object(self.service,'_verify',new=AsyncMock(return_value='测试同学')):
            self.window.password_edit.setText('retry-test-password'); self.window.login_button.click(); self.wait_job()
        self.assertEqual(self.window.root_stack.currentIndex(),1); self.assertTrue(self.window.authenticated)

    def test_async_time_save_updates_widget_and_scheduler(self):
        self.service.settings.update(enabled=True,managed=True); self.service.save(); self.service.flag(True)
        with patch.object(self.service,'rpc',side_effect=core.UserError('offline')):
            self.window.enter_offline(); self.window.go(1); self.window.time_edit.setTime(QTime(22,10)); self.window.save_time.click(); self.wait_job()
        self.assertEqual(self.service.scheduler.time,'22:10'); self.assertIn('22:10',self.window.big_time.text()); self.assertIn('备用端待同步',self.window.schedule_saved.text())

    def test_busy_job_prevents_duplicate_submission(self):
        calls=[]
        def operation(): calls.append(1); return {}
        self.window.job('test',operation); self.window.job('duplicate',operation); self.wait_job()
        self.assertEqual(len(calls),1)

    def test_refresh_keeps_unsaved_time(self):
        self.window.time_edit.setTime(QTime(22,10)); self.window.refresh()
        self.assertEqual(self.window.time_edit.time(),QTime(22,10)); self.assertIn('未保存',self.window.schedule_saved.text())

    def test_disabled_system_task_is_reported_as_needing_repair(self):
        self.service.settings.update(enabled=True,managed=True); self.service.save(); self.service.flag(True)
        self.window.task_state={'state':'Disabled'}; self.window.refresh()
        self.assertEqual(self.window.plan_pill.text(),'需要修复')

    def test_status_refresh_does_not_submit_a_pause_or_resume(self):
        with patch.object(self.service,'resume') as resume,patch.object(self.service,'pause') as pause:
            for enabled in (True,False,True):
                self.service.settings['enabled']=enabled; self.service.save(); self.window.refresh(); self.app.processEvents()
            resume.assert_not_called(); pause.assert_not_called()


if __name__=='__main__': unittest.main()
