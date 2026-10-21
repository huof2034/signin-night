"""Two-account migration, isolation, task routing and edition boundaries. Offline."""
import hashlib
import json
import tempfile
from pathlib import Path
from datetime import datetime
from unittest import TestCase, main
from unittest.mock import patch, Mock, AsyncMock
from desktop import accounts, core
from test_desktop import Scheduler
import app as legacy


class AccountTests(TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='ahut-two-accounts-');self.root=Path(self.tmp.name)
        self.original=(legacy.DATA,legacy.ACCOUNT,legacy.ROOT)
        self.execution=patch.object(core,'execute',return_value=Mock(returncode=0,stdout='',stderr=''));self.execution.start()
        self.sid=patch.object(core.Service,'_sid',return_value='S-1-5-21-1');self.sid.start()
        self.tasks={slot:Scheduler() for slot in accounts.SLOTS}
        self.service=accounts.StandardService(data=self.root/'data',old_root=self.root/'old',migrate=False,scheduler_factory=self.tasks.get)
        self.verify=patch.object(self.service,'_verify',new=AsyncMock(return_value='离线测试'));self.verify_mock=self.verify.start()

    def tearDown(self):
        self.verify.stop();self.execution.stop();self.sid.stop();legacy.DATA,legacy.ACCOUNT,legacy.ROOT=self.original;self.tmp.cleanup()

    def add(self, student='259099999'):
        return self.service.login(student,'test-only-password',False,profile_id=None)

    def both(self):
        self.add();self.service.resume();self.service.save_schedule('22:00')
        self.add('259088888');self.service.resume();self.service.save_schedule('22:10')

    def test_original_ciphertext_schedule_identity_and_success_are_preserved(self):
        folder=self.root/'old-version';base=core.Service(data=folder,old_root=self.root/'old',scheduler=Scheduler(),migrate=False)
        legacy.save_account({'student_id':'259077777','password_hash':'a'*32});legacy.remember_success('2026-10-20')
        base.settings.update(enabled=True,managed=True,time='22:00',mode='local');base.save()
        before=(folder/'account.dpapi').read_bytes();plan=(folder/'desktop.json').read_bytes()
        service=accounts.StandardService(data=folder,migrate=False,scheduler_factory=self.tasks.get)
        state=service.status();self.assertEqual(state['selected_profile'],'primary');self.assertEqual(state['time'],'22:00');self.assertTrue(state['enabled'])
        self.assertEqual(state['last_success'],'2026-10-20');self.assertEqual((folder/'account.dpapi').read_bytes(),before);self.assertEqual((folder/'desktop.json').read_bytes(),plan)
        self.assertFalse(self.tasks['primary'].calls)

    def test_add_verify_does_not_sign_in_and_second_defaults_paused(self):
        with patch.object(legacy,'perform') as perform:
            self.add();state=self.add('259088888');perform.assert_not_called()
        self.assertEqual(len(state['accounts']),2);self.assertFalse(state['enabled']);self.assertEqual(state['time'],'22:00')
        raw=(self.service.data/'account-secondary.dpapi').read_bytes();self.assertNotIn(b'259088888',raw);self.assertNotIn(b'password_hash',raw)
        text=(self.service.data/'profiles.json').read_text(encoding='utf-8');self.assertNotIn('259088888',text);self.assertNotIn(hashlib.md5(b'test-only-password').hexdigest(),text)

    def test_limit_and_duplicate_are_rejected_before_network(self):
        self.add()
        with self.assertRaises(core.UserError):self.add()
        self.add('259088888');self.verify_mock.reset_mock()
        with self.assertRaises(core.UserError):self.add('259066666')
        self.verify_mock.assert_not_awaited();self.assertEqual(len(self.service.status()['accounts']),2)

    def test_failed_add_or_reverification_preserves_both_accounts_and_plans(self):
        self.both();before={p.name:p.read_bytes() for p in self.service.data.glob('*.dpapi')};plan=(self.service.data/'profiles.json').read_bytes()
        self.verify_mock.side_effect=core.UserError('wrong password')
        with self.assertRaises(core.UserError):self.service.login('259088888','wrong')
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.service.data.glob('*.dpapi')});self.assertEqual(plan,(self.service.data/'profiles.json').read_bytes())

    def test_switching_pause_and_time_apply_only_to_selected_profile(self):
        self.both();self.service.pause();self.service.save_schedule('22:20');self.service.select_account('primary')
        state=self.service.status();self.assertTrue(state['enabled']);self.assertEqual(state['time'],'22:00');self.assertTrue(self.tasks['primary'].enabled)
        self.assertFalse(self.tasks['secondary'].enabled);self.assertEqual(self.tasks['secondary'].time,'22:20')
        self.assertTrue(accounts.StandardService(data=self.service.data,migrate=False,scheduler_factory=self.tasks.get).status()['enabled'])

    def test_scheduler_failure_preserves_working_plan(self):
        self.add();self.service.resume();self.tasks['primary'].failure=lambda time,enabled:time=='22:10'
        with self.assertRaises(core.UserError):self.service.save_schedule('22:10')
        self.assertEqual(self.service.status()['time'],'22:00');self.assertTrue(self.tasks['primary'].enabled)

    def test_task_identity_ignores_ui_selection_and_successes_do_not_cross(self):
        self.both()
        with patch.object(accounts,'now',return_value=datetime(2026,10,20,22,5,tzinfo=core.CHINA)),patch.object(legacy,'load_upstream',return_value=Mock()),patch.object(legacy,'perform',new=AsyncMock(return_value={'success':True})) as perform:
            self.assertEqual(self.service.scheduled_run('primary'),0);self.assertEqual(perform.await_args.args[1]['student_id'],'259099999')
            self.assertEqual(self.service.scheduled_run('primary'),0);self.assertEqual(perform.await_count,1)
            self.assertEqual(self.service.scheduled_run('secondary'),0);self.assertEqual(perform.await_count,1)
        with patch.object(accounts,'now',return_value=datetime(2026,10,20,22,12,tzinfo=core.CHINA)),patch.object(legacy,'load_upstream',return_value=Mock()),patch.object(legacy,'perform',new=AsyncMock(return_value={'success':True})) as perform:
            self.assertEqual(self.service.scheduled_run('secondary'),0);self.assertEqual(perform.await_count,1)
        self.assertEqual(self.service.success('primary',self.service.account('primary')),'2026-10-20');self.assertEqual(self.service.success('secondary',self.service.account('secondary')),'2026-10-20')

    def test_same_time_and_primary_failure_do_not_block_secondary(self):
        self.both();self.service.save_schedule('22:00')
        with patch.object(accounts,'now',return_value=datetime(2026,10,20,22,2,tzinfo=core.CHINA)),patch.object(legacy,'load_upstream',return_value=Mock()),patch.object(legacy,'perform',new=AsyncMock(side_effect=[RuntimeError('network'),{'success':True}])) as perform:
            self.assertEqual(self.service.scheduled_run('primary'),1);self.assertEqual(self.service.scheduled_run('secondary'),0);self.assertEqual(perform.await_count,2)
        self.assertIsNone(self.service.success('primary',self.service.account('primary')));self.assertEqual(self.service.success('secondary',self.service.account('secondary')),'2026-10-20')

    def test_account_execution_locks_are_independent(self):
        self.both();self.service.save_schedule('22:00')
        with core.external_lock(self.service.data/'locks'/'primary'),patch.object(accounts,'now',return_value=datetime(2026,10,20,22,2,tzinfo=core.CHINA)),patch.object(legacy,'load_upstream',return_value=Mock()),patch.object(legacy,'perform',new=AsyncMock(return_value={'success':True})):
            with self.assertRaises(core.UserError):self.service.scheduled_run('primary')
            self.assertEqual(self.service.scheduled_run('secondary'),0)

    def test_disabled_or_outside_window_does_not_load_credentials(self):
        self.add()
        with patch.object(self.service,'account') as account:
            self.assertEqual(self.service.scheduled_run(),0);account.assert_not_called()
        self.service.resume()
        with patch.object(accounts,'now',return_value=datetime(2026,10,20,23,1,tzinfo=core.CHINA)),patch.object(self.service,'account') as account:
            self.assertEqual(self.service.scheduled_run(),0);account.assert_not_called()

    def test_remove_disables_only_one_task_and_reuse_never_inherits_success(self):
        self.both();legacy.write_json(self.service.success_path('secondary'),{'student_id':'259088888','date':'2026-10-20'})
        self.service.remove_account('secondary');self.assertFalse(self.tasks['secondary'].enabled);self.assertTrue(self.tasks['primary'].enabled)
        state=self.add('259066666');self.assertFalse(state['enabled']);self.assertIsNone(state['last_success']);self.assertEqual(state['selected_profile'],'secondary')

    def test_standard_vps_is_blocked_without_ssh_or_schedule_change(self):
        self.both();before=(self.service.data/'profiles.json').read_bytes()
        with patch.object(self.service,'ssh') as ssh:
            for operation in (self.service.switch_cloud,self.service.deploy_remote,self.service.check_connection):
                with self.assertRaises(core.UserError):operation()
            ssh.assert_not_called()
        self.assertEqual(before,(self.service.data/'profiles.json').read_bytes())

    def test_logs_and_notifications_identify_accounts_without_full_ids(self):
        self.both();events=self.service.history();text=json.dumps(events)
        self.assertNotIn('259099999',text);self.assertNotIn('259088888',text);self.assertTrue(all(e.get('account_label') for e in events))
        from desktop.notifications import EventNotifications
        started=core.now();self.service.account_event('secondary','success','成功')
        prefs={'notifications':True,'notify_success':True,'notify_failed':True,'notify_mode':True}
        messages=EventNotifications(started).consume(self.service.history(),prefs);self.assertIn('账号 2',messages[0][1]);self.assertIn('8888',messages[0][1])

    def test_windows_tasks_have_distinct_names_and_explicit_profile_arguments(self):
        with patch.object(core,'ps',return_value=Mock(stdout=json.dumps({'ok':True,'task':{'state':'Ready'},'previous_xml':None}))) as ps:
            core.WindowsTask(worker='C:/app/app.exe',name=core.TASK+'-Secondary',profile_id='secondary').apply('22:10',True)
        text=ps.call_args.args[0];self.assertIn('--scheduled --profile secondary',text);self.assertIn(core.TASK+'-Secondary',text);self.assertIn('22:10:00+08:00',text)

    def test_verification_cannot_overwrite_a_slot_claimed_during_network_wait(self):
        self.add();before=(self.service.data/'account.dpapi').read_bytes()
        async def claimed(account):
            value=self.service.store();value['profiles']['secondary']={'time':'22:00','enabled':False,'managed':True,'auto_login':False};self.service.write_store(value);return '测试'
        self.verify_mock.side_effect=claimed
        with self.assertRaises(core.UserError):self.add('259088888')
        self.assertEqual(before,(self.service.data/'account.dpapi').read_bytes());self.assertFalse((self.service.data/'account-secondary.dpapi').exists())

    def test_legacy_takeover_failure_restores_old_timer_and_flags(self):
        self.add();value=self.service.store();value['profiles']['primary']['managed']=False;self.service.write_store(value)
        old=self.service.old_data;old.mkdir(parents=True);core.write_plain(old/'enabled.json',{'enabled':True})
        self.tasks['primary'].failure=lambda time,enabled:enabled
        with self.assertRaises(core.UserError):self.service.resume()
        self.assertTrue(json.loads((old/'enabled.json').read_text())['enabled']);self.assertFalse((old/'desktop-managed.json').exists());self.assertFalse(self.tasks['primary'].old_disabled)
        self.assertFalse(self.service.status()['managed'])


if __name__=='__main__':main()
