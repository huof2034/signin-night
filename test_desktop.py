"""Offline behavioral checks. No real scheduler, SSH or school requests."""
import asyncio
from datetime import datetime, timezone, timedelta
import hashlib
import json
import logging
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

import app
from desktop import core


class Scheduler:
    def __init__(self): self.time = '22:00'; self.enabled = False; self.old_disabled = False; self.failure = None; self.calls = []
    def apply(self, value, enabled):
        self.calls.append((value, enabled))
        if self.failure and self.failure(value, enabled): raise core.UserError('simulated scheduler failure')
        self.time, self.enabled = value, enabled
    def disable(self): self.enabled = False
    def info(self): return {'state': 'Ready' if self.enabled else 'Disabled', 'next_run': self.time}
    def disable_old(self, root): self.old_disabled = True
    def restore_old(self): self.old_disabled = False


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ahut-desktop-tests-'); self.root = Path(self.temp.name)
        self.original = (app.DATA, app.ACCOUNT, app.ROOT)
        self.execute = patch.object(core, 'execute', return_value=Mock(returncode=0, stdout='', stderr='')); self.execute.start()
        self.sid = patch.object(core.Service, '_sid', return_value='S-1-5-21-1'); self.sid.start()
        self.task = Scheduler()
        self.service = core.Service(data=self.root/'data', old_root=self.root/'old', scheduler=self.task, migrate=False)
        self.account = {'student_id':'259099999', 'password_hash': hashlib.md5(b'offline-test-only').hexdigest()}
        app.save_account(self.account)
        self.rpc = patch.object(self.service, 'rpc', side_effect=core.UserError('offline')); self.rpc_mock = self.rpc.start()

    def tearDown(self):
        self.rpc.stop(); self.execute.stop(); self.sid.stop()
        app.DATA, app.ACCOUNT, app.ROOT = self.original
        self.temp.cleanup()

    def manage(self):
        self.service.settings.update(managed=True, enabled=True, mode='local'); self.service.save(); self.service.flag(True); self.task.enabled=True

    def test_time_validation_rejects_bad_and_unsupported_values(self):
        for value in ['22:99','1:30','24:00','21:19','22:00;echo x','']:
            with self.assertRaises(core.UserError): core.validate_time(value)
        self.assertEqual(core.validate_time('21:40'),'21:40')

    def test_window_follows_time_and_beijing_timezone(self):
        self.assertTrue(core.within_window(datetime(2026,10,19,13,45,tzinfo=timezone.utc),'21:40'))
        self.assertFalse(core.within_window(datetime(2026,10,19,22,0,tzinfo=core.CHINA),'21:40'))
        self.assertFalse(core.within_window(datetime(2026,10,20,0,1,tzinfo=core.CHINA),'23:55'))

    def test_login_failure_does_not_overwrite_saved_account(self):
        before = app.ACCOUNT.read_bytes()
        with patch.object(self.service,'_verify',new=AsyncMock(side_effect=core.UserError('invalid'))):
            with self.assertRaises(core.UserError): self.service.login('259088888','bad')
        self.assertEqual(before,app.ACCOUNT.read_bytes())

    def test_login_verifies_without_signing_in(self):
        with patch.object(self.service,'_verify',new=AsyncMock(return_value='测试同学')) as verify, patch.object(app,'perform') as signin:
            result = self.service.login(auto_login=False)
            self.assertTrue(result['configured']); self.assertTrue(result['identity']['verified_at']); verify.assert_awaited_once(); signin.assert_not_called()

    def test_invalid_account_change_requires_password(self):
        with self.assertRaises(core.UserError): self.service.login('259088888','')

    def test_save_time_updates_real_scheduler_and_marks_offline_backup_pending(self):
        self.manage()
        result = self.service.save_schedule('21:50')
        self.assertEqual(self.task.time,'21:50'); self.assertTrue(self.task.enabled); self.assertTrue(result['pending_sync']); self.assertEqual(result['time'],'21:50')

    def test_unmanaged_schedule_does_not_modify_legacy_task(self):
        self.service.save_schedule('22:10')
        self.assertEqual(self.task.calls,[]); self.assertFalse(self.service.status()['managed'])

    def test_failed_local_schedule_restores_last_working_configuration(self):
        self.manage(); self.task.failure=lambda time,enabled:time=='22:10'
        with self.assertRaises(core.UserError): self.service.save_schedule('22:10')
        self.assertEqual(self.service.settings['time'],'22:00'); self.assertEqual(self.task.time,'22:00'); self.assertTrue(self.task.enabled)

    def test_cloud_connectivity_failure_preserves_current_local_task(self):
        self.manage()
        with patch.object(self.service,'check_connection',side_effect=core.UserError('network')):
            with self.assertRaises(core.UserError): self.service.switch_cloud()
        self.assertTrue(app.enabled()); self.assertTrue(self.task.enabled)

    def test_uncertain_cloud_activation_leaves_local_off_and_unknown(self):
        self.manage(); self.rpc_mock.side_effect=lambda action,payload=None: {} if action in ('import','deactivate') else (_ for _ in ()).throw(core.UserError('timeout'))
        with patch.object(self.service,'check_connection',return_value={'ready':True}):
            with self.assertRaises(core.UserError): self.service.switch_cloud()
        self.assertFalse(app.enabled()); self.assertFalse(self.task.enabled); self.assertEqual(self.service.settings['mode'],'unknown')

    def test_local_recovery_requires_confirmed_cloud_shutdown(self):
        self.manage(); self.service.flag(False); self.service.settings['mode']='unknown'; self.service.save(); self.task.enabled=False
        with self.assertRaises(core.UserError): self.service.activate_local()
        self.assertFalse(app.enabled()); self.assertFalse(self.task.enabled)

    def test_successful_cloud_switch_disables_local(self):
        self.manage(); self.rpc_mock.side_effect=lambda action,payload=None:{'local_enabled':True,'task':{'ActiveState':'active'}} if action=='activate' else {}
        with patch.object(self.service,'check_connection',return_value={'ready':True}): result=self.service.switch_cloud()
        self.assertEqual(result['mode'],'cloud'); self.assertTrue(result['enabled']); self.assertFalse(app.enabled()); self.assertFalse(self.task.enabled)

    def test_successful_local_switch_confirms_remote_and_syncs_success(self):
        self.manage(); self.service.settings['mode']='cloud'; self.service.save(); self.service.flag(False)
        state=self.service.status(); self.rpc_mock.side_effect=None; self.rpc_mock.return_value={'local_enabled':False,'account_tag':state['account_tag'],'last_success':'2026-10-19'}
        result=self.service.activate_local()
        self.assertEqual(result['mode'],'local'); self.assertEqual(result['last_success'],'2026-10-19'); self.assertTrue(app.enabled()); self.assertTrue(self.task.enabled)

    def test_pause_cloud_failure_does_not_claim_paused(self):
        self.manage(); self.service.settings['mode']='cloud'; self.service.flag(False)
        with self.assertRaises(core.UserError): self.service.pause()
        self.assertEqual(self.service.settings['mode'],'unknown'); self.assertFalse(app.enabled())

    def test_day_success_guard_skips_network_in_new_worker(self):
        self.manage(); app.remember_success('2026-10-19')
        with patch.object(core,'now',return_value=datetime(2026,10,19,22,5,tzinfo=core.CHINA)), patch.object(app,'perform') as signin:
            self.assertEqual(self.service.scheduled_run(),0); signin.assert_not_called()

    def test_disabled_worker_does_not_load_credentials(self):
        with patch.object(app,'load_account') as account:
            self.assertEqual(self.service.scheduled_run(),0); account.assert_not_called()

    def test_events_never_contain_password_hash_or_student_id(self):
        self.service.event('schedule','时间设置完成。',mode='local')
        stored=(self.service.data/'events.jsonl').read_text(encoding='utf-8')
        self.assertNotIn(self.account['password_hash'],stored); self.assertNotIn(self.account['student_id'],stored)

    def test_failure_during_takeover_restores_enabled_legacy_task(self):
        self.service.old_data.mkdir(parents=True); core.write_plain(self.service.old_data/'enabled.json',{'enabled':True})
        self.task.failure=lambda time,enabled:enabled
        with self.assertRaises(core.UserError): self.service.activate_local()
        self.assertTrue(json.loads((self.service.old_data/'enabled.json').read_text())['enabled']); self.assertFalse(self.task.old_disabled); self.assertFalse(app.enabled())

    def test_config_switch_refuses_when_signin_lock_is_held(self):
        self.manage()
        with app.exclusive():
            with self.assertRaises(app.BusyError): self.service.save_schedule('22:10')
        self.assertEqual(self.service.settings['time'],'22:00')

    def test_unknown_endpoint_prevents_changing_account(self):
        self.manage(); self.service.settings['mode']='unknown'; self.service.save()
        with patch.object(self.service,'_verify',new=AsyncMock()) as verify:
            with self.assertRaises(core.UserError): self.service.login('259088888','test')
            verify.assert_not_awaited()

    def test_cloud_connection_cannot_be_replaced_until_local_recovery(self):
        self.manage(); self.service.settings['mode']='cloud'; self.service.save()
        with self.assertRaises(core.UserError):
            self.service.save_connection({'host':'new.example.com','port':22,'user':'root','key':'any'})
        self.assertFalse((self.service.data/'vps.json').exists())

    def test_worker_fails_closed_for_unknown_or_wrong_endpoint(self):
        self.manage(); self.service.settings['mode']='unknown'; self.service.save()
        with patch.object(app,'perform') as signin:
            self.assertEqual(self.service.scheduled_run(),0); signin.assert_not_called()

    def test_success_on_vps_is_merged_before_reimport(self):
        self.manage(); tag=self.service.status()['account_tag']; payloads=[]
        def rpc(action,payload=None):
            if action=='deactivate': return {'local_enabled':False,'account_tag':tag,'last_success':'2026-10-19'}
            if action=='import': payloads.append(payload); return {}
            return {'local_enabled':True,'task':{'ActiveState':'active'}}
        self.rpc_mock.side_effect=rpc
        with patch.object(self.service,'check_connection',return_value={'ready':True}): self.service.switch_cloud()
        self.assertEqual(payloads[0]['last_success'],'2026-10-19')

    def test_legacy_launcher_is_guarded_after_takeover(self):
        self.service.old_data.mkdir(parents=True)
        self.service.activate_local()
        self.assertTrue((self.service.old_data/'desktop-managed.json').exists())
        core.write_plain(self.service.data/'desktop-managed.json',{'worker':'test'})
        with patch.object(app,'perform') as signin:
            self.assertEqual(app.run(),0); signin.assert_not_called()

    def test_private_log_filter_masks_school_identity_and_credentials(self):
        log=logging.LogRecord('test',logging.INFO,'',1,'为 张三('+self.account['student_id']+') 登录 '+self.account['password_hash']+' https://example.invalid?password=secret',(),None)
        core.PrivateLogFilter(self.account).filter(log)
        for private in ['张三',self.account['student_id'],self.account['password_hash'],'password=secret']:
            self.assertNotIn(private,log.getMessage())

    def test_cloud_monitor_refreshes_success_without_enabling_local(self):
        self.manage(); tag=self.service.status()['account_tag']; self.service.settings['mode']='cloud'; self.service.save(); self.service.flag(False)
        self.rpc_mock.side_effect=None; self.rpc_mock.return_value={'account_tag':tag,'last_success':'2026-10-19','task':{'ActiveState':'active'}}
        self.service.monitor()
        self.assertEqual(self.service.status()['last_success'],'2026-10-19'); self.assertFalse(app.enabled())

    def test_managed_app_relocation_does_not_touch_unrelated_legacy_folder(self):
        self.manage(); self.service.old_data.mkdir(parents=True)
        core.write_plain(self.service.old_data/'enabled.json',{'enabled':True})
        self.service.activate_local()
        self.assertFalse(self.task.old_disabled)
        self.assertTrue(json.loads((self.service.old_data/'enabled.json').read_text())['enabled'])


if __name__=='__main__': unittest.main()
