"""1.5 desktop UX and verified schedule-save regressions, no school traffic."""
import json
from unittest import TestCase,main
from unittest.mock import patch,Mock
from PySide6.QtCore import QTime,Qt
from PySide6.QtTest import QTest
from desktop import core
import test_accounts_ui as fixtures


class UpdateUiTests(TestCase):
    setUpClass=classmethod(fixtures.StandardUiTests.setUpClass.__func__)
    setUp=fixtures.StandardUiTests.setUp
    tearDown=fixtures.StandardUiTests.tearDown
    wait_job=fixtures.StandardUiTests.wait_job

    def primary(self):
        self.service.select_account('primary');self.window.task_state={'state':'Ready'};self.window.refresh()

    def test_minute_step_carries_across_hour_and_stops_at_boundaries(self):
        self.window.go(1);edit=self.window.time_edit;edit.setTime(QTime(22,0));edit.setCurrentSection(edit.Section.MinuteSection)
        edit.stepDown();self.assertEqual(edit.time(),QTime(21,59))
        edit.stepUp();self.assertEqual(edit.time(),QTime(22,0))
        edit.setTime(QTime(21,30));edit.stepDown();self.assertEqual(edit.time(),QTime(21,30))
        edit.setTime(QTime(23,30));edit.stepUp();self.assertEqual(edit.time(),QTime(23,30))

    def test_keyboard_down_carries_minute(self):
        self.window.go(1);edit=self.window.time_edit;edit.setTime(QTime(22,0));edit.setFocus();edit.setCurrentSection(edit.Section.MinuteSection)
        QTest.keyClick(edit,Qt.Key.Key_Down);self.assertEqual(edit.time(),QTime(21,59))

    def test_home_displays_real_disabled_task_and_hides_countdown(self):
        self.primary();self.window.task_state={'state':'Disabled'};self.window.refresh();self.window.go(0);self.app.processEvents()
        self.assertTrue(self.window.configuration_notice.isVisible())
        self.assertIn('未启用',self.window.configuration_notice.text())
        self.assertIn('需要修复',self.window.plan_pill.text())
        self.assertNotIn('距离下次执行',self.window.count_label.text())

    def test_home_reports_time_drift_and_success_has_checkmark(self):
        self.primary();self.window.task_state={'state':'Ready','schedule_time':'22:10'};self.window.refresh()
        self.assertIn('不一致',self.window.configuration_notice.text())
        self.window.task_state={'state':'Ready','schedule_time':'22:00'};self.window.refresh()
        self.assertEqual(self.window.plan_pill.text(),'已启用');self.assertEqual(self.window.plan_pill.property('health'),'ok')

    def test_failed_save_reason_survives_return_to_home(self):
        self.primary();self.tasks['primary'].failure=lambda time,enabled:time=='22:20'
        self.window.go(1);self.window.time_edit.setTime(QTime(22,20));self.window.apply_time();self.wait_job();self.window.go(0);self.app.processEvents()
        self.assertIn('simulated scheduler failure',self.window.configuration_notice.text())
        self.assertTrue(self.window.configuration_notice.isVisible())
        self.assertEqual(self.service.status()['time'],'22:00')

    def test_legacy_out_of_range_plan_can_open_and_requests_new_time(self):
        self.primary();store=self.service.store();store['profiles']['primary']['time']='21:20';self.service.write_store(store)
        self.window.refresh();self.assertIn('21:30–23:30',self.window.configuration_notice.text())

    def test_fast_save_uses_one_powershell_call_and_preserves_other_account(self):
        self.primary();task=core.WindowsTask(worker='C:/app/desktop.exe',profile_id='primary');self.service.schedulers['primary']=task
        result={'ok':True,'previous_xml':None,'task':{'state':'Ready','schedule_time':'22:15','enabled':True}}
        with patch.object(core,'ps',return_value=Mock(stdout=json.dumps(result))) as call:
            state=self.service.save_schedule('22:15')
        self.assertEqual(call.call_count,1);self.assertEqual(state['task']['schedule_time'],'22:15')
        self.assertEqual(self.service.store()['profiles']['secondary']['time'],'22:00')


class RangeTests(TestCase):
    def test_new_range_is_inclusive_and_old_values_are_readable_only(self):
        for value in ('21:30','23:30'):self.assertEqual(core.validate_time(value),value)
        for value in ('21:29','23:31'):
            with self.assertRaises(core.UserError):core.validate_time(value)
        self.assertEqual(core.validate_time('21:20',existing=True),'21:20')


if __name__=='__main__':main()
