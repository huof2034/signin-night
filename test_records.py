"""Success-response durability, interrupted cleanup and evidence-based recovery."""
import asyncio
from datetime import datetime
import json
import subprocess
import sys
from types import SimpleNamespace
from unittest import TestCase,main
from unittest.mock import AsyncMock,Mock,patch

from desktop import accounts,core,records
import app as legacy
import test_accounts as fixtures


class RecordTests(TestCase):
    setUp=fixtures.AccountTests.setUp
    tearDown=fixtures.AccountTests.tearDown
    add=fixtures.AccountTests.add
    both=fixtures.AccountTests.both
    instant=datetime(2026,10,21,22,1,tzinfo=core.CHINA)

    def prepare(self):self.add();self.service.resume();return self.service.account('primary')

    def run_step(self,*,cleanup_error=False):
        module=SimpleNamespace(sign_in_by_step=AsyncMock(return_value=dict(success=True,step=6)))
        async def perform(mod,account):
            await mod.sign_in_by_step(object(),5,False)
            self.assertEqual(self.service.success('primary',account),'2026-10-21')
            if cleanup_error:raise RuntimeError('simulated tail/session cleanup error')
            return dict(success=True)
        with patch.object(accounts,'now',return_value=self.instant),patch.object(legacy,'load_upstream',return_value=module),patch.object(legacy,'perform',new=AsyncMock(side_effect=perform)) as call:
            result=self.service.scheduled_run('primary')
        return result,call

    def test_response_is_saved_before_async_cleanup_and_survives_cleanup_failure(self):
        account=self.prepare();code,call=self.run_step(cleanup_error=True)
        self.assertEqual(code,0);self.assertEqual(self.service.success('primary',account),'2026-10-21')
        with patch.object(accounts,'now',return_value=self.instant),patch.object(legacy,'perform') as repeat:
            self.assertEqual(self.service.scheduled_run('primary'),0);repeat.assert_not_called()

    def test_real_upstream_loop_tail_delay_failure_cannot_erase_confirmation(self):
        self.prepare();module=legacy.load_upstream();calls=[]
        async def step(user,index,debug=False):calls.append(index);return dict(success=True,step=index+1,msg='')
        async def delay(seconds):
            if len(calls)==6:raise RuntimeError('interrupted final delay')
        with patch.object(accounts,'now',return_value=self.instant),patch.object(legacy,'load_upstream',return_value=module),patch.object(module,'sign_in_by_step',new=step),patch.object(module.asyncio,'sleep',new=delay),patch('aiohttp.ClientSession._request',side_effect=AssertionError('No network allowed')):
            self.assertEqual(self.service.scheduled_run('primary'),0)
        self.assertEqual(calls,list(range(6)));self.assertEqual(self.service.status()['last_success'],'2026-10-21')

    def test_receipt_still_works_when_compatibility_file_write_fails(self):
        account=self.prepare();original=legacy.write_json
        def write(path,value):
            if path==self.service.success_path('primary'):raise PermissionError('simulated compatibility file lock')
            return original(path,value)
        with patch.object(legacy,'write_json',side_effect=write):code,_=self.run_step()
        self.assertEqual(code,0);self.assertEqual(self.service.success('primary',account),'2026-10-21')
        records.receipt_path(self.service.data,'primary').write_text('{invalid',encoding='utf-8')
        self.assertIsNone(self.service.success('primary',account))

    def test_receipt_write_failure_is_explicit_and_does_not_repeat_submission(self):
        self.prepare();original=legacy.write_json
        def write(path,value):
            if path==records.receipt_path(self.service.data,'primary'):raise PermissionError('simulated disk error')
            return original(path,value)
        with patch.object(legacy,'write_json',side_effect=write):code,_=self.run_step()
        self.assertEqual(code,1);event=self.service.history()[0]
        self.assertEqual(event['kind'],'record_failed');self.assertTrue(event['school_confirmed'])
        with patch.object(accounts,'now',return_value=self.instant),patch.object(legacy,'perform') as repeat:
            self.assertEqual(self.service.scheduled_run('primary'),1);repeat.assert_not_called()

    def test_other_steps_or_unconfirmed_result_never_create_a_receipt(self):
        self.prepare();module=SimpleNamespace(sign_in_by_step=AsyncMock(return_value=dict(success=True,step=5)))
        async def perform(mod,account):await mod.sign_in_by_step(object(),4,False);return dict(success=False)
        with patch.object(accounts,'now',return_value=self.instant),patch.object(legacy,'load_upstream',return_value=module),patch.object(legacy,'perform',new=perform):
            self.assertEqual(self.service.scheduled_run(),1)
        self.assertFalse(records.receipt_path(self.service.data,'primary').exists())

    def test_receipt_is_account_bound_and_removed_with_account(self):
        a=self.prepare();records.commit_success(self.service.data,'primary',a,self.instant)
        other=dict(a,student_id='259066666');self.assertIsNone(self.service.success('primary',other))
        self.service.remove_account('primary');self.assertFalse(records.receipt_path(self.service.data,'primary').exists())

    def test_receipt_survives_missing_or_corrupt_legacy_success_file(self):
        a=self.prepare();records.commit_success(self.service.data,'primary',a,self.instant)
        self.service.success_path('primary').write_text('{bad-json',encoding='utf-8')
        self.assertEqual(self.service.status()['last_success'],'2026-10-21')

    def test_concurrent_process_events_are_complete(self):
        script="from desktop.core import Service;import sys;s=Service(data=sys.argv[1],migrate=False);[s.event('probe','offline',sequence=sys.argv[2]+str(i)) for i in range(30)]"
        processes=[subprocess.Popen([sys.executable,'-B','-c',script,str(self.service.data),prefix],creationflags=0x08000000 if core.WINDOWS else 0) for prefix in ('A','B')]
        try:
            for process in processes:self.assertEqual(process.wait(timeout=20),0)
        finally:
            for process in processes:
                if process.poll() is None:process.kill();process.wait(timeout=10)
        entries=[e for e in self.service.history(1000) if e.get('kind')=='probe']
        self.assertEqual(len(entries),60);self.assertEqual(len({e['sequence'] for e in entries}),60)

    def test_outside_window_and_disabled_skips_have_a_reason_without_decrypting(self):
        self.add()
        with patch.object(self.service,'account') as decrypt:self.assertEqual(self.service.scheduled_run(),0);decrypt.assert_not_called()
        self.assertEqual(self.service.history()[0]['skip_reason'],'disabled')
        self.service.resume()
        with patch.object(accounts,'now',return_value=self.instant.replace(hour=21,minute=53)),patch.object(self.service,'account') as decrypt:
            self.assertEqual(self.service.scheduled_run(),0);decrypt.assert_not_called()
        self.assertEqual(self.service.history()[0]['skip_reason'],'outside_window')

    def test_record_failure_notification_does_not_claim_school_rejected(self):
        from desktop.notifications import EventNotifications
        started=core.now();self.prepare();self.service.account_event('primary','record_failed','保存失败',school_confirmed=True)
        prefs=dict(notifications=True,notify_success=True,notify_failed=True,notify_mode=True)
        result=EventNotifications(started).consume(self.service.history(),prefs)
        self.assertEqual(result[-1][0],'本地回执保存失败');self.assertIn('学校已返回成功',result[-1][1])

    def legacy_evidence(self):
        account=self.prepare();tag=records.account_tag(account)[:16]
        events=[dict(at='2026-10-20T12:00:00+08:00',kind='login',profile_id='primary',account_tag=tag)]
        task=dict(state='Ready',last_result=0,last_run='2026-10-21T22:00:00')
        path=self.service.data/'signin-primary.log'
        path.write_text('2026-10-21 22:00:01,001 INFO 为 (****9999) 尝试执行签到\n2026-10-21 22:00:16,001 INFO 为 当前账号 晚寝签到成功\n',encoding='utf-8')
        return account,events,task,path

    def test_log_recovery_requires_identity_and_task_corroboration(self):
        a,events,task,path=self.legacy_evidence()
        candidate=records.recovery_candidate(self.service.data,'primary',a,events,task,self.instant,[a])
        self.assertEqual(candidate['instant'].isoformat(),'2026-10-21T22:00:16+08:00')
        for changed in ({**task,'last_result':1},{**task,'state':'Running'},{**task,'last_run':'2026-10-20T22:00:00'}):
            self.assertIsNone(records.recovery_candidate(self.service.data,'primary',a,events,changed,self.instant,[a]))
        self.assertIsNone(records.recovery_candidate(self.service.data,'primary',a,[],task,self.instant,[a]))
        self.assertIsNone(records.recovery_candidate(self.service.data,'primary',a,events,task,self.instant,[a,dict(a,student_id='259099999')]))
        path.write_text(path.read_text('utf-8').replace('****9999','****8888'),encoding='utf-8')
        self.assertIsNone(records.recovery_candidate(self.service.data,'primary',a,events,task,self.instant,[a]))

    def test_recovery_preserves_original_and_marks_provenance_without_network(self):
        a,events,task,path=self.legacy_evidence()
        legacy.write_json(self.service.success_path('primary'),dict(student_id=a['student_id'],date='2026-10-19'))
        previous=self.service.success_path('primary').read_bytes()
        with patch.object(accounts,'now',return_value=self.instant),patch.object(self.service,'history',return_value=events),patch.object(self.tasks['primary'],'info',return_value=task),patch.object(legacy,'perform') as submit:
            status=self.service.recover_record();submit.assert_not_called()
        self.assertEqual(status['last_success'],'2026-10-21');self.assertEqual(status['success_source'],'log_recovery')
        self.assertEqual((self.service.data/'last-success-primary.before-recovery.json').read_bytes(),previous)
        self.assertEqual(self.service.history()[0]['kind'],'record_recovered')


if __name__=='__main__':main()
