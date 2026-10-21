"""Standard edition: two independent local profiles, with no Qt or VPS access."""
from __future__ import annotations

import asyncio
import contextlib
from copy import deepcopy
import hashlib
import json
import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime, timedelta

from . import core
from .core import legacy, UserError, now, CHINA, external_lock, validate_time, within_window

SLOTS = ('primary', 'secondary')
LIMIT = 2


class StandardService(core.Service):
    edition = 'standard'

    def __init__(self, *args, scheduler_factory=None, **kwargs):
        super().__init__(*args, **kwargs)
        first = self.scheduler
        self.schedulers = {slot: (scheduler_factory(slot) if scheduler_factory else
            core.WindowsTask(name=core.TASK if slot == 'primary' else core.TASK+'-Secondary', profile_id=slot)) for slot in SLOTS}
        if kwargs.get('scheduler') is not None: self.schedulers['primary'] = first
        if not (self.data/'profiles.json').exists():
            with external_lock(self.data), external_lock(self.data/'profiles-store'):
                if not (self.data/'profiles.json').exists():
                    old_mode=legacy.read_json(self.old_data/'mode.json',{}).get('mode','local')
                    if self.settings['mode'] != 'local' or (not self.settings['managed'] and old_mode!='local'):
                        raise UserError('旧版运行端尚未确认为本机。请先在旧版切回本机并确认 VPS 停用，再使用普通版。')
                    profiles = {}
                    if self.credential_path('primary').exists():
                        self.account('primary')  # Validate the original ciphertext before migration.
                        profiles['primary'] = {k:self.settings[k] for k in ('time','enabled','managed','auto_login')}
                        profiles['primary']['identity'] = self.read('identity.json', {})
                        profiles['primary']['legacy_history'] = True
                    self.write_store({'version':1, 'selected':'primary' if profiles else None, 'profiles':profiles})

    def store(self):
        value = self.read('profiles.json', None)
        if not isinstance(value, dict) or value.get('version') != 1 or not isinstance(value.get('profiles'),dict):
            raise UserError('双账号配置损坏，请保留原文件后修复。')
        profiles=value['profiles']
        if len(profiles)>LIMIT or any(slot not in SLOTS for slot in profiles): raise UserError('账号数量或标识无效。')
        for key,profile in profiles.items():
            profile.setdefault('legacy_history',key=='primary')
            validate_time(profile['time'],existing=True)
            if any(type(profile.get(k)) is not bool for k in ('enabled','managed','auto_login')): raise UserError('账号计划配置无效。')
        if (profiles and value.get('selected') not in profiles) or (not profiles and value.get('selected') is not None): raise UserError('当前账号配置无效。')
        return value

    def write_store(self, value): legacy.write_json(self.data/'profiles.json', value)

    def credential_path(self, slot):
        if slot not in SLOTS: raise UserError('账号标识无效。')
        return self.data/('account.dpapi' if slot=='primary' else 'account-secondary.dpapi')

    def account(self, slot):
        try:
            raw=self.credential_path(slot).read_bytes()
            return legacy.validate_account(json.loads(legacy.dpapi(raw,decrypt=True)))
        except Exception:
            raise UserError('无法读取该账号的加密凭据，请重新验证账号。') from None

    def saved_student(self):
        slot=self.store()['selected']
        try:return self.account(slot)['student_id'] if slot else ''
        except UserError:return ''

    def label(self, slot, account=None):
        try:account=account or self.account(slot)
        except UserError:return ('账号 1' if slot=='primary' else '账号 2')+' · 凭据待修复'
        return ('账号 1' if slot=='primary' else '账号 2')+' · ****'+account['student_id'][-4:]

    def success_path(self, slot): return self.data/('last-success.json' if slot=='primary' else 'last-success-secondary.json')

    def success(self, slot, account):
        record=legacy.read_json(self.success_path(slot), {})
        return record.get('date') if record.get('student_id')==account['student_id'] else None

    def account_event(self, slot, kind, message, **details):
        account=self.account(slot)
        self.event(kind, message, profile_id=slot, account_label=self.label(slot,account), account_tag=hashlib.sha256(account['student_id'].encode()).hexdigest()[:16], mode='local', **details)

    def status(self, task=False):
        store=self.store();slot=store['selected'];current=now();accounts=[];credentials={}
        for key,profile in store['profiles'].items():
            try:account=self.account(key)
            except UserError:account=None
            credentials[key]=account
            accounts.append({'profile_id':key,'label':self.label(key,account),'time':profile['time'],'enabled':profile['enabled'],
                             'last_success':self.success(key,account) if account else None,'managed':profile['managed'],'credential_ok':bool(account)})
        profile=store['profiles'].get(slot,{'time':'22:00','enabled':False,'managed':True,'auto_login':True,'identity':{}})
        account=credentials.get(slot)
        hour,minute=map(int,profile['time'].split(':'));following=current.replace(hour=hour,minute=minute,second=0,microsecond=0)
        if following<=current:following+=timedelta(days=1)
        result={**profile,'mode':'local','pending_sync':False,'edition':'standard','account_limit':LIMIT,'accounts':accounts,
                'selected_profile':slot,'configured':bool(slot),'credential_ok':bool(account),'masked_id':'****'+account['student_id'][-4:] if account else '凭据待修复' if slot else '',
                'account_tag':hashlib.sha256(account['student_id'].encode()).hexdigest()[:16] if account else None,
                'last_success':self.success(slot,account) if account else None,'local_enabled':profile['enabled'],'time_valid':'21:30'<=profile['time']<='23:30',
                'next_run':following.isoformat(),'now':current.isoformat(),'identity':profile.get('identity',{}),'data_dir':str(self.data)}
        self.settings=result
        if task:result['task']=self.schedulers[slot].info() if slot else None
        return result

    def select_account(self, slot):
        with external_lock(self.data/'profiles-store'):
            value=self.store()
            if slot not in value['profiles']:raise UserError('该账号不存在。')
            value['selected']=slot;self.write_store(value)
        return self.status()

    def duplicate_student(self, slot, student_id, profiles):
        for key in profiles:
            if key==slot:continue
            try:other=self.account(key)
            except UserError:continue
            if other['student_id']==student_id:return True
        return False

    def login(self, student_id='', password='', auto_login=True, *, profile_id='selected'):
        value=self.store();slot=value['selected'] if profile_id=='selected' else profile_id
        if slot is None:
            if len(value['profiles'])>=LIMIT:raise UserError('普通版最多同时保存两个账号。请先移除不再使用的账号。')
            slot=next(key for key in SLOTS if key not in value['profiles'])
        if slot not in SLOTS:raise UserError('账号标识无效。')
        existing=slot in value['profiles']
        original_ciphertext=self.credential_path(slot).read_bytes() if existing else None
        if password:
            account=legacy.validate_account({'student_id':student_id.strip(),'password_hash':hashlib.md5(password.encode('utf-8')).hexdigest()})
        elif existing:
            account=self.account(slot)
            if student_id and student_id.strip()!=account['student_id']:raise UserError('请通过“添加账号”保存其他学号，当前账号不会被覆盖。')
        else:raise UserError('添加账号时请输入学号和考勤密码。')
        if existing and self.account(slot)['student_id']!=account['student_id']:raise UserError('请通过“添加账号”保存其他学号，当前账号不会被覆盖。')
        if self.duplicate_student(slot,account['student_id'],value['profiles']):raise UserError('该学号已经保存，请直接切换到对应账号。')
        username=asyncio.run(self._verify(account))
        encrypted=original_ciphertext if existing and self.account(slot)==account else legacy.dpapi(json.dumps(account).encode('utf-8'))
        with external_lock(self.data/'locks'/slot), external_lock(self.data/'profiles-store'):
            value=self.store()
            if (slot in value['profiles'])!=existing or (existing and self.credential_path(slot).read_bytes()!=original_ciphertext):
                raise UserError('账号列表或凭据在验证期间已更改，请重新选择账号后重试。')
            if slot not in value['profiles'] and len(value['profiles'])>=LIMIT:raise UserError('普通版最多同时保存两个账号。')
            if self.duplicate_student(slot,account['student_id'],value['profiles']):raise UserError('该学号已经保存。')
            profile=value['profiles'].get(slot,{'time':'22:00','enabled':False,'managed':True,'auto_login':True,'legacy_history':False})
            profile.update(auto_login=bool(auto_login),identity={'name':username,'verified_at':now().isoformat()})
            value['profiles'][slot]=profile;value['selected']=slot
            path=self.credential_path(slot);before=path.read_bytes() if path.exists() else None
            try:
                legacy.atomic_write(path,encrypted);self.write_store(value)
            except Exception:
                if before is not None:legacy.atomic_write(path,before)
                else:path.unlink(missing_ok=True)
                raise
            self.account_event(slot,'login','学校账号验证通过，未提交签到。')
        return self.status()

    def update_plan(self, *, scheduled=None, enabled=None):
        value=self.store();slot=value['selected']
        if not slot:raise UserError('请先添加并验证学校账号。')
        if scheduled is not None:validate_time(scheduled)
        with external_lock(self.data/'locks'/slot), external_lock(self.data/'profiles-store'):
            value=self.store();previous=deepcopy(value);profile=value['profiles'][slot]
            if scheduled is not None:profile['time']=scheduled
            if enabled is not None:profile.update(enabled=bool(enabled),managed=True)
            task=self.schedulers[slot];old=previous['profiles'][slot]
            takeover=slot=='primary' and not old['managed'] and profile['managed']
            legacy_folder=self.old_data if takeover and self.old_data!=self.data and self.old_data.exists() else None
            with external_lock(legacy_folder) if legacy_folder else contextlib.nullcontext():
                backups={name:(legacy_folder/name).read_bytes() if (legacy_folder/name).exists() else None for name in ('enabled.json','desktop-managed.json')} if legacy_folder else {}
                old_enabled=legacy.read_json(legacy_folder/'enabled.json',{}).get('enabled',False) if legacy_folder else False
                stopped_old=False;task_changed=False;verified=None;fast=hasattr(task,'apply_verified')
                actual=None if fast else task.info()
                previous_enabled=actual.get('enabled',actual.get('state')!='Disabled') if actual else False
                try:
                    if slot=='primary' and (takeover or enabled is True):
                        task.disable_old(self.old_root);stopped_old=True
                        if legacy_folder:
                            core.write_plain(legacy_folder/'enabled.json',{'enabled':False})
                            core.write_plain(legacy_folder/'desktop-managed.json',{'data_dir':str(self.data)})
                    if profile['managed']:
                        task_changed=True
                        if fast:verified=task.apply_verified(profile['time'],profile['enabled'])
                        else:task.apply(profile['time'],profile['enabled'])
                    self.write_store(value)
                    persisted=self.store()['profiles'][slot]
                    if any(persisted[k]!=profile[k] for k in ('time','enabled','managed')):raise UserError('计划配置写入后校验失败，已回滚系统任务。')
                except Exception:
                    try:self.write_store(previous)
                    except Exception:self.event('error','账号计划配置回滚未确认，请检查保存的时间与启用状态。',profile_id=slot)
                    if task_changed:
                        try:
                            if fast:task.restore_previous()
                            else:task.apply(old['time'],previous_enabled)
                        except Exception:
                            self.event('error','系统计划回滚未确认，请检查该账号的任务状态。',profile_id=slot)
                    if legacy_folder:
                        for name,content in backups.items():
                            path=legacy_folder/name
                            if content is None:path.unlink(missing_ok=True)
                            else:path.write_bytes(content)
                    if stopped_old:task.restore_old()
                    raise
            self.account_event(slot,'schedule' if scheduled is not None else 'mode' if enabled else 'pause',
                               f'每日计划已保存：北京时间 {profile["time"]}，'+('已启用。' if profile['enabled'] else '已暂停。'))
        result=self.status()
        result['task']=verified if verified is not None else task.info()
        return result

    def save_schedule(self, scheduled): return self.update_plan(scheduled=scheduled)
    def activate_local(self): return self.update_plan(enabled=True)
    def resume(self): return self.update_plan(enabled=True)
    def pause(self): return self.update_plan(enabled=False)

    def remove_account(self, slot):
        if slot not in SLOTS:raise UserError('账号标识无效。')
        with external_lock(self.data/'locks'/slot), external_lock(self.data/'profiles-store'):
            value=self.store()
            if slot not in value['profiles']:raise UserError('该账号不存在。')
            previous=deepcopy(value);label=self.label(slot);task=self.schedulers[slot]
            task.disable()
            del value['profiles'][slot]
            if value['selected']==slot:value['selected']=next(iter(value['profiles']),None)
            try:self.write_store(value)
            except Exception:
                old=previous['profiles'][slot];task.apply(old['time'],old['enabled'] and old['managed']);raise
            # Metadata removal is the commit point: a remaining encrypted orphan
            # cannot run and is never re-imported from an existing profiles file.
            self.credential_path(slot).unlink(missing_ok=True)
            self.success_path(slot).unlink(missing_ok=True)
            self.event('account_removed','已移除账号及其本机计划。',profile_id=slot,account_label=label,mode='local')
        return self.status()

    def monitor(self):
        value=self.store();slot=value['selected']
        return {'task':self.schedulers[slot].info() if slot else None,'profile_id':slot}

    def switch_cloud(self): raise UserError('普通版仅支持本机运行；VPS 将在后续付费版开放。')
    def rpc(self,*args,**kwargs): return self.switch_cloud()
    def deploy_remote(self): return self.switch_cloud()
    def check_connection(self): return self.switch_cloud()
    def save_connection(self,*args,**kwargs): return self.switch_cloud()

    def scheduled_run(self, profile_id=None):
        # Explicit task identity, independent of the profile selected in the UI.
        slot=profile_id or 'primary'
        if slot not in SLOTS:raise UserError('账号标识无效。')
        with external_lock(self.data/'locks'/slot):
            profile=self.store()['profiles'].get(slot)
            if not profile or not profile['managed'] or not profile['enabled']:return 0
            current=now()
            if not '21:30'<=profile['time']<='23:30':
                self.account_event(slot,'failed','计划时间不在新版允许的 21:30–23:30 范围，请重新设置。');return 1
            if not within_window(current,profile['time']):return 0
            account=self.account(slot)
            if self.success(slot,account)==current.date().isoformat():
                self.account_event(slot,'skipped','今天已有成功记录，跳过重复执行。');return 0
            module=legacy.load_upstream()
            class BeijingDateTime(datetime):
                @classmethod
                def now(cls,tz=None):return super().now(tz or CHINA)
            module.datetime=BeijingDateTime
            def beijing_time():
                value=now()
                return {'date':value.strftime('%Y-%m-%d'),'time':value.strftime('%H:%M:%S'),'weekday':'星期'+'一二三四五六日'[value.weekday()],'full':value.strftime('%Y年%m月%d日 %H:%M:%S')}
            module.get_time=beijing_time
            logger=logging.getLogger()
            for handler in list(logger.handlers):logger.removeHandler(handler);handler.close()
            handler=TimedRotatingFileHandler(self.data/f'signin-{slot}.log',when='midnight',backupCount=30,encoding='utf-8',utc=True)
            handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'));handler.addFilter(core.PrivateLogFilter(account));logger.addHandler(handler);logger.setLevel(logging.INFO)
            self.account_event(slot,'running','定时签到开始。')
            try:
                result=asyncio.run(legacy.perform(module,account))
                if result.get('success'):
                    legacy.write_json(self.success_path(slot),{'student_id':account['student_id'],'date':current.date().isoformat()})
                    if self.success(slot,account)!=current.date().isoformat():raise UserError('学校已返回成功，但本地成功记录未能保存，请在学校系统核实结果。')
                    self.account_event(slot,'success','学校系统已确认今日签到成功。');return 0
                self.account_event(slot,'failed','学校系统未确认签到成功，请查看该账号的日志。');return 1
            except Exception as exc:
                logging.error('签到异常类型：%s',type(exc).__name__)
                self.account_event(slot,'failed','签到发生网络或系统异常，请查看该账号的日志。');return 1
            finally:
                logger.removeHandler(handler);handler.close()
