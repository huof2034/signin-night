"""Receipt-backed status and recovery provenance, without school requests."""
from unittest import TestCase,main
from desktop import core,records
import test_accounts_ui as fixtures


class RecordUiTests(TestCase):
    setUpClass=classmethod(fixtures.StandardUiTests.setUpClass.__func__)
    setUp=fixtures.StandardUiTests.setUp
    tearDown=fixtures.StandardUiTests.tearDown

    def prepare(self):
        self.service.select_account('primary');self.window.task_state=dict(state='Ready',last_run=core.now().isoformat(),last_result=0)
        self.window.refresh();self.window.go(0);self.app.processEvents()

    def test_missing_record_offers_repair_and_receipt_hides_false_warning(self):
        self.prepare();self.assertTrue(self.window.repair_record_button.isVisible())
        account=self.service.account('primary');records.commit_success(self.service.data,'primary',account,core.now())
        self.service.success_path('primary').write_text('{broken',encoding='utf-8');self.window.refresh();self.app.processEvents()
        self.assertEqual(self.window.today_status.text(),'今日已完成')
        self.assertIn('成功回执已保存',self.window.recent_label.text())
        self.assertFalse(self.window.execution_feedback.isVisible());self.assertFalse(self.window.repair_record_button.isVisible())

    def test_recovered_receipt_is_labelled_and_never_claims_fresh_online_verification(self):
        self.prepare();account=self.service.account('primary')
        records.commit_success(self.service.data,'primary',account,core.now(),source='log_recovery')
        self.window.refresh()
        self.assertIn('从当次成功执行日志恢复',self.window.today_detail.text())
        self.assertIn('未重新提交',self.window.today_detail.text())

    def test_skip_reason_is_shown_instead_of_missing_success_warning(self):
        self.prepare();self.service.skip_event('primary','本次未执行：时间不在执行窗口内。','outside_window')
        self.window.refresh();self.app.processEvents()
        self.assertIn('时间不在执行窗口',self.window.execution_feedback.text())
        self.assertFalse(self.window.repair_record_button.isVisible());self.assertEqual(self.window.today_status.text(),'本次未执行')


if __name__=='__main__':main()
