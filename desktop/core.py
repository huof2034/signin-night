"""Desktop/remote service layer. This module does not depend on Qt."""
from __future__ import annotations

import argparse
import asyncio
import base64
import contextlib
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import uuid
from datetime import datetime, timedelta, timezone

import app as legacy

CHINA = timezone(timedelta(hours=8))
WINDOWS = os.name == 'nt'
TASK = 'AHUT-WQQD-Desktop-Daily'
TASK_DESCRIPTION = 'Managed by AHUT SignIn Desktop'
ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1] if Path(__file__).parent.name == 'desktop' else Path(__file__).parent))
OLD_ROOT = Path(__file__).resolve().parents[1] if not getattr(sys, 'frozen', False) and Path(__file__).parent.name == 'desktop' else Path(sys.executable).resolve().parents[2]


class UserError(RuntimeError):
    """An error safe to display without credential-bearing exception details."""


def now():
    return datetime.now(CHINA)


def validate_time(value):
    if not isinstance(value, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value):
        raise UserError('请选择有效的小时和分钟。')
    if value < '21:20':
        raise UserError('当前适配脚本要求 21:20 后执行；实际开放时段仍以学校系统为准。')
    return value


def within_window(instant, scheduled, minutes=15):
    hour, minute = map(int, validate_time(scheduled).split(':'))
    instant = instant.astimezone(CHINA)
    start = instant.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return start <= instant < min(start + timedelta(minutes=minutes), start.replace(hour=23, minute=59, second=59, microsecond=999999))


def execute(arguments, *, stdin=None, timeout=45, check=True):
    try:
        result = subprocess.run(arguments, input=stdin, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=timeout,
                                creationflags=subprocess.CREATE_NO_WINDOW if WINDOWS else 0)
    except subprocess.TimeoutExpired:
        raise UserError('操作超时。远端状态可能尚未确认，请恢复连接后重试。') from None
    except OSError:
        raise UserError('无法启动所需的系统工具，请检查安装和文件权限。') from None
    if check and result.returncode:
        raise UserError('系统操作未完成，请检查任务权限或 SSH 连接。')
    return result


def ps(script, check=True):
    encoded = base64.b64encode(('[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false);$ErrorActionPreference="Stop";' + script).encode('utf-16le')).decode()
    return execute(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded], check=check)


def quote_ps(value):
    return "'" + str(value).replace("'", "''") + "'"


class PrivateLogFilter(logging.Filter):
    def __init__(self, account):
        super().__init__(); self.account = account

    def filter(self, record):
        message = record.getMessage()
        student = self.account['student_id']
        message = re.sub(r'[^\s,，：:()（）]{1,30}[（(]' + re.escape(student) + r'[)）]', '当前账号', message)
        message = message.replace(student, '****' + student[-4:]).replace(self.account['password_hash'], '[已隐藏]')
        message = re.sub(r'(?:https?://)[^\s]+', '[接口地址已隐藏]', message)
        message = re.sub(r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', '[凭据已隐藏]', message)
        message = re.sub(r'(请检查|返回信息)\s*[{\[].*', r'\1（原始响应已隐藏）', message)
        record.msg, record.args = message, ()
        return True


def write_plain(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        if not WINDOWS:
            temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@contextlib.contextmanager
def external_lock(folder):
    """Acquire the previous launcher's lock without changing shared module globals."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / 'run.lock').open('a+b') as handle:
        handle.seek(0, 2)
        if not handle.tell():
            handle.write(b'0'); handle.flush()
        handle.seek(0)
        try:
            if WINDOWS:
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise UserError('签到正在执行，请等待完成后再操作。') from None
        try:
            yield
        finally:
            handle.seek(0)
            if WINDOWS:
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class WindowsTask:
    def __init__(self, worker=None, name=TASK, profile_id=None):
        self.worker = str(Path(worker).resolve()) if worker else None
        self.name = name
        self.profile_id = profile_id

    def apply(self, scheduled, enabled):
        validate_time(scheduled)
        if self.worker or getattr(sys, 'frozen', False):
            executable, arguments = self.worker or sys.executable, '--scheduled'
        else:
            executable = str(Path(sys.executable).with_name('pythonw.exe'))
            arguments = '"' + str(ROOT / 'desktop_main.py') + '" --scheduled'
        if self.profile_id:
            if self.profile_id not in ('primary', 'secondary'): raise UserError('账号标识无效。')
            arguments += ' --profile ' + self.profile_id
        script = f"""
$name={quote_ps(self.name)};$description={quote_ps(TASK_DESCRIPTION)}
$existing=Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
if($existing -and $existing.Description -ne $description){{throw 'Conflicting scheduled task'}}
$action=New-ScheduledTaskAction -Execute {quote_ps(executable)} -Argument {quote_ps(arguments)}
$trigger=New-ScheduledTaskTrigger -Daily -At {quote_ps(scheduled)}
$trigger.StartBoundary=[DateTime]::Today.ToString('yyyy-MM-dd')+'T{scheduled}:00+08:00'
$principal=New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings=New-ScheduledTaskSettingsSet -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
$settings.Enabled=${str(bool(enabled)).lower()}
Register-ScheduledTask -TaskName $name -Description $description -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
if(${str(bool(enabled)).lower()}){{Enable-ScheduledTask -TaskName $name | Out-Null}}else{{Disable-ScheduledTask -TaskName $name | Out-Null}}
$actual=Get-ScheduledTask -TaskName $name
if($actual.Settings.Enabled -ne ${str(bool(enabled)).lower()}){{throw 'Scheduled task enable state was not confirmed'}}
"""
        ps(script)

    def disable(self):
        ps(f"$t=Get-ScheduledTask -TaskName {quote_ps(self.name)} -ErrorAction SilentlyContinue;if($t){{if($t.Description -ne {quote_ps(TASK_DESCRIPTION)}){{throw 'Conflicting task'}};Disable-ScheduledTask -TaskName {quote_ps(self.name)} | Out-Null}}")

    def info(self):
        output = ps(f"$t=Get-ScheduledTask -TaskName {quote_ps(self.name)} -ErrorAction SilentlyContinue;if($t){{$i=Get-ScheduledTaskInfo -TaskName {quote_ps(self.name)};@{{state=$t.State.ToString();next_run=$i.NextRunTime.ToString('o');last_result=$i.LastTaskResult}}|ConvertTo-Json -Compress}}else{{'null'}}").stdout
        return json.loads(output or 'null')

    def disable_old(self, old_root):
        expected = 'Managed by AHUT-WQQD at ' + str(old_root)
        script = f"$t=Get-ScheduledTask -TaskName 'AHUT-WQQD-2200' -ErrorAction SilentlyContinue;if($t){{if($t.Description -ne {quote_ps(expected)}){{throw 'Unrelated legacy task'}};Disable-ScheduledTask -TaskName 'AHUT-WQQD-2200' | Out-Null}}"
        ps(script)

    def restore_old(self):
        ps("Enable-ScheduledTask -TaskName 'AHUT-WQQD-2200' | Out-Null")


class SystemdTask:
    timer = Path('/etc/systemd/system/ahut-wqqd.timer')

    def apply(self, scheduled, enabled):
        validate_time(scheduled)
        content = f'''# Managed by AHUT-WQQD dual-mode installation v1
[Unit]
Description=AHUT daily sign-in (Beijing {scheduled})
[Timer]
OnCalendar=*-*-* {scheduled}:00 Asia/Shanghai
AccuracySec=1s
RandomizedDelaySec=0
Persistent=false
Unit=ahut-wqqd.service
[Install]
WantedBy=timers.target
'''
        previous = self.timer.read_bytes() if self.timer.exists() else None
        previous_active = self.info().get('ActiveState') == 'active'
        if previous is not None and b'Managed by AHUT-WQQD' not in previous:
            raise UserError('远端同名定时器不属于本项目，已停止修改。')
        try:
            execute(['systemctl', 'disable', '--now', 'ahut-wqqd.timer'])
            self.timer.write_text(content, encoding='utf-8'); self.timer.chmod(0o644)
            execute(['systemd-analyze', 'verify', str(self.timer)])
            execute(['systemctl', 'daemon-reload'])
            if enabled:
                execute(['systemctl', 'enable', '--now', 'ahut-wqqd.timer'])
        except Exception:
            if previous is not None:
                self.timer.write_bytes(previous)
                execute(['systemctl', 'daemon-reload'], check=False)
                if previous_active:
                    execute(['systemctl', 'enable', '--now', 'ahut-wqqd.timer'], check=False)
            raise

    def disable(self):
        execute(['systemctl', 'disable', '--now', 'ahut-wqqd.timer'])

    def info(self):
        output = execute(['systemctl', 'show', 'ahut-wqqd.timer', '-p', 'ActiveState', '-p', 'UnitFileState', '-p', 'NextElapseUSecRealtime']).stdout
        return dict(line.split('=', 1) for line in output.splitlines() if '=' in line)


class Service:
    def __init__(self, data=None, old_root=None, scheduler=None, migrate=True):
        self.data = Path(data) if data else (Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'AHUTSignIn' if WINDOWS else ROOT / '.local')
        self.old_root = Path(old_root or OLD_ROOT)
        self.old_data = self.old_root / '.local'
        self.scheduler = scheduler or (WindowsTask() if WINDOWS else SystemdTask())
        self.mutex = threading.RLock()
        existed = self.data.exists()
        legacy.ROOT, legacy.DATA = ROOT, self.data
        legacy.ACCOUNT = self.data / ('account.dpapi' if WINDOWS else 'account.json')
        legacy.ensure_data()
        if WINDOWS and not existed:
            execute(['icacls.exe', str(self.data), '/inheritance:r', '/grant:r', '*' + self._sid() + ':(OI)(CI)F', '*S-1-5-18:(OI)(CI)F'])
        if migrate and WINDOWS and not (self.data / 'desktop.json').exists() and self.old_data.exists():
            self._migrate()
        defaults = {'time': '22:00', 'enabled': False, 'mode': 'local', 'managed': not WINDOWS, 'pending_sync': True, 'revision': uuid.uuid4().hex, 'auto_login': True}
        self.settings = self.read('desktop.json', defaults)
        if not isinstance(self.settings, dict):
            raise UserError('计划配置损坏，请保留原文件后修复。')
        self.settings = {**defaults, **self.settings}
        validate_time(self.settings['time'])
        if self.settings['mode'] not in ('local', 'cloud', 'unknown') or any(type(self.settings[k]) is not bool for k in ('enabled','managed','pending_sync','auto_login')):
            raise UserError('计划配置无效，已停止启动。')
        if not (self.data / 'desktop.json').exists():
            self.save()

    def _sid(self):
        if not hasattr(self, '_cached_sid'):
            self._cached_sid = ps('[Security.Principal.WindowsIdentity]::GetCurrent().User.Value').stdout.strip()
        return self._cached_sid

    def read(self, name, default):
        return legacy.read_json(self.data / name, default)

    def save(self):
        legacy.write_json(self.data / 'desktop.json', self.settings)

    def flag(self, enabled):
        legacy.write_json(self.data / 'enabled.json', {'enabled': bool(enabled)})

    def _migrate(self):
        for name in ['account.dpapi', 'vps.json', 'last-success.json']:
            source = self.old_data / name
            if source.exists() and not (self.data / name).exists():
                shutil.copy2(source, self.data / name)
        source_key = self.old_data / 'ssh' / 'id_ed25519'
        if source_key.exists():
            target = self.data / 'ssh' / 'id_ed25519'
            target.parent.mkdir(exist_ok=True)
            if not target.exists():
                shutil.copyfile(source_key, target)
            if source_key.with_suffix('.pub').exists():
                shutil.copyfile(source_key.with_suffix('.pub'), target.with_suffix('.pub'))
            execute(['icacls.exe', str(target), '/inheritance:r', '/grant:r', '*' + self._sid() + ':F', '*S-1-5-18:F'])
            execute(['icacls.exe', str(target), '/remove:g', '*S-1-5-32-544'])
        self.flag(False)
        self.event('migration', '已导入旧版加密账号与连接配置，尚未接管定时任务。')

    def event(self, kind, message, **details):
        entry = {'at': now().isoformat(), 'kind': kind, 'message': message, **details}
        path = self.data / 'events.jsonl'
        with self.mutex:
            if path.exists() and path.stat().st_size > 2_000_000:
                backup = path.with_suffix('.previous.jsonl'); backup.unlink(missing_ok=True); path.replace(backup)
            with path.open('a', encoding='utf-8') as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + '\n')
        if not WINDOWS:
            path.chmod(0o600); legacy.linux_owner(path)

    def history(self, limit=200):
        path = self.data / 'events.jsonl'
        if not path.exists():
            return []
        result = []
        for line in path.read_text(encoding='utf-8').splitlines()[-limit:]:
            try:
                result.append(json.loads(line))
            except ValueError:
                continue
        return list(reversed(result))

    def status(self, task=False):
        self.settings = self.read('desktop.json', self.settings)
        account = legacy.load_account() if legacy.ACCOUNT.exists() else None
        tag = hashlib.sha256(account['student_id'].encode()).hexdigest()[:16] if account else None
        current = now()
        hour, minute = map(int, self.settings['time'].split(':'))
        following = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if following <= current:
            following += timedelta(days=1)
        result = {**self.settings, 'configured': bool(account), 'masked_id': '****' + account['student_id'][-4:] if account else '',
                  'account_tag': tag, 'last_success': legacy.last_success(account) if account else None,
                  'local_enabled': legacy.enabled(), 'next_run': following.isoformat(), 'now': current.isoformat(),
                  'identity': self.read('identity.json', {}), 'data_dir': str(self.data)}
        if task:
            result['task'] = self.scheduler.info()
        return result

    async def _verify(self, account):
        import aiohttp
        module = legacy.load_upstream()
        user = module.User(int(account['student_id']), password=account['password_hash'], is_encrypted=1)
        try:
            headers = dict(user.session.headers)
            await user.close()
            user._session = aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=18, connect=8))
            async with user.session.post(module.WEB_DICT['token_api'], params=module.generate_params(user)) as response:
                if response.status >= 400:
                    if response.status in (400, 401):
                        raise UserError('学号或考勤密码未通过验证，请检查后重试。')
                    raise UserError(f'学校系统暂时不可用（HTTP {response.status}）。')
                value = await response.json(content_type=None)
            if not value.get('refresh_token'):
                description = str(value.get('error_description', ''))
                if 'credentials' in description.lower() or '密码' in description:
                    raise UserError('学号或考勤密码未通过验证，请检查后重试。')
                raise UserError('学校系统未返回有效登录凭据，请稍后重试。')
            return str(value.get('userName', '学校考勤账号'))
        except UserError:
            raise
        except Exception:
            raise UserError('无法完成学校账号验证，请检查网络或稍后重试。') from None
        finally:
            await user.close()

    def login(self, student_id='', password='', auto_login=True):
        if self.settings.get('managed') and self.settings.get('mode') == 'unknown':
            raise UserError('请先恢复连接并确认运行端，再验证或更换账号。')
        if password:
            account = legacy.validate_account({'student_id': student_id.strip(), 'password_hash': hashlib.md5(password.encode('utf-8')).hexdigest()})
        else:
            account = legacy.load_account()
            if student_id and student_id.strip() != account['student_id']:
                raise UserError('更换学号时需要重新输入密码。')
        username = asyncio.run(self._verify(account))
        with self.mutex, legacy.exclusive():
            if self.settings.get('managed') and self.settings.get('mode') == 'cloud':
                self.rpc('import', self.profile(account=account))
            legacy.save_account(account)
            self.settings['auto_login'] = bool(auto_login); self.save()
            legacy.write_json(self.data / 'identity.json', {'verified_at': now().isoformat(), 'name': username})
            self.event('login', '学校账号验证通过。')
        return self.status()

    def connection(self):
        value = self.read('vps.json', {'host': '', 'port': 22, 'user': 'root'})
        value.setdefault('key', str(self.data / 'ssh' / 'id_ed25519'))
        self._validate_connection(value)
        return value

    def _validate_connection(self, value):
        if not re.fullmatch(r'[A-Za-z0-9.:-]+', str(value.get('host', ''))) or not 1 <= int(value.get('port', 0)) <= 65535:
            raise UserError('SSH 地址或端口无效。')
        if value.get('user') != 'root':
            raise UserError('当前 VPS 安装与管理功能需要 root 账号。')

    def save_connection(self, value):
        self._validate_connection(value)
        if self.settings['mode'] != 'local' or self.settings['enabled'] and not legacy.enabled():
            raise UserError('请先确认已切回本机，再修改 VPS 连接。')
        if not Path(value['key']).is_file():
            raise UserError('找不到选定的 SSH 私钥文件。')
        legacy.write_json(self.data / 'vps.json', value)
        self.event('connection', '已更新备用服务器连接。')
        return value

    def ssh(self, command, payload=None, timeout=45, rpc_response=False):
        value = self.connection()
        key = Path(value['key'])
        if not key.is_file():
            raise UserError('尚未配置 SSH 私钥，请在账号与连接中设置。')
        args = ['ssh.exe' if WINDOWS else 'ssh', '-i', str(key), '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=8', '-p', str(value['port']), value['user'] + '@' + value['host'], command]
        result = execute(args, stdin=payload, timeout=timeout, check=False)
        if result.returncode:
            if rpc_response:
                try:
                    response = json.loads(result.stdout)
                    if response.get('ok') is False and isinstance(response.get('error'), str):
                        return result.stdout.strip()
                except (ValueError, AttributeError):
                    pass
            if 'Host key verification failed' in result.stderr:
                raise UserError('服务器指纹未通过验证，请先在 SSH 客户端确认服务器身份。')
            if 'Permission denied' in result.stderr:
                raise UserError('SSH 密钥登录被拒绝，请检查服务器授权和私钥配置。')
            raise UserError('无法确认 VPS 状态。请检查 SSH 转发或网络后重试。')
        return result.stdout.strip()

    def rpc(self, action, payload=None):
        if action not in {'status', 'import', 'activate', 'deactivate', 'schedule', 'history', 'prepare'}:
            raise UserError('未知远端操作。')
        command = '/opt/ahut-wqqd/.venv/bin/python -B /opt/ahut-wqqd/desktop_core.py --rpc ' + action
        output = self.ssh(command, json.dumps(payload or {}), timeout=65, rpc_response=True)
        try:
            result = json.loads(output)
        except ValueError:
            raise UserError('远端返回了无法识别的状态，请先安装或更新备用端。') from None
        if not result.get('ok'):
            raise UserError(result.get('error', '远端操作未完成。'))
        return result.get('data')

    def check_connection(self):
        output = self.ssh("test -f /opt/ahut-wqqd/desktop_core.py && echo DESKTOP || echo LEGACY")
        if output != 'DESKTOP':
            return {'ready': False, 'message': 'SSH 已连接，备用端需要安装桌面版服务。'}
        state = self.rpc('status')
        return {'ready': True, 'message': 'SSH 已连接，备用服务可用。', 'status': state}

    def monitor(self):
        if self.settings['mode'] == 'cloud':
            state = self.rpc('status')
            with self.mutex, legacy.exclusive():
                self._merge_success(state)
            return state
        return {'task': self.scheduler.info()}

    def profile(self, account=None):
        account = account or legacy.load_account()
        return {'account': account, 'last_success': legacy.last_success(account), 'time': self.settings['time'], 'revision': self.settings['revision']}

    def _merge_success(self, status):
        if status.get('account_tag') == self.status()['account_tag'] and status.get('last_success'):
            legacy.remember_success(status['last_success'])

    def _latest_legacy_success(self):
        if self.old_data == self.data or not (self.old_data / 'last-success.json').exists():
            return
        record = legacy.read_json(self.old_data / 'last-success.json', {})
        if legacy.ACCOUNT.exists() and record.get('student_id') == legacy.load_account()['student_id']:
            legacy.remember_success(record.get('date'))

    def activate_local(self):
        legacy.load_account()
        remote = None
        old_mode = legacy.read_json(self.old_data / 'mode.json', {}).get('mode', 'local')
        if self.settings['mode'] != 'local' or (not self.settings['managed'] and old_mode != 'local'):
            remote = self.rpc('deactivate')
            if remote['local_enabled']:
                raise UserError('尚未确认 VPS 停用，本机保持停用。')
        with self.mutex, legacy.exclusive():
            if remote:
                self._merge_success(remote)
            previous = dict(self.settings)
            taking_over = not previous['managed']
            old_flag = legacy.read_json(self.old_data / 'enabled.json', {}).get('enabled', False) if taking_over else False
            with external_lock(self.old_data) if taking_over and self.old_data != self.data and self.old_data.exists() else contextlib.nullcontext():
                if taking_over: self._latest_legacy_success()
                try:
                    self.scheduler.apply(self.settings['time'], False)
                    self.scheduler.disable_old(self.old_root) if WINDOWS and taking_over else None
                    if WINDOWS and taking_over and self.old_data.exists() and self.old_data != self.data:
                        write_plain(self.old_data / 'enabled.json', {'enabled': False})
                    self.settings.update(mode='local', enabled=True, managed=True)
                    self.save(); self.flag(True)
                    self.scheduler.apply(self.settings['time'], True)
                    if WINDOWS and taking_over and self.old_data != self.data and self.old_data.exists():
                        worker = getattr(self.scheduler, 'worker', None) or (sys.executable if getattr(sys, 'frozen', False) else '')
                        write_plain(self.old_data / 'desktop-managed.json', {'data_dir': str(self.data), 'worker': worker})
                except Exception:
                    self.settings = previous; self.save(); self.flag(previous['enabled'] and previous['mode'] == 'local' and previous['managed'])
                    if old_flag and not previous['managed'] and WINDOWS:
                        write_plain(self.old_data / 'enabled.json', {'enabled': True}); self.scheduler.restore_old()
                    raise
            self.event('mode', '已切换到本机，VPS 保持停用。', mode='local')
        return self.status(task=True)

    def switch_cloud(self):
        if not self.settings['managed']:
            raise UserError('请先点击“接管本机计划”，再切换到 VPS。')
        state = self.check_connection()
        if not state['ready']:
            raise UserError(state['message'])
        with self.mutex, legacy.exclusive():
            stopped = self.rpc('deactivate')
            if stopped.get('local_enabled'):
                raise UserError('备用端未确认停用，暂不开始切换。')
            self._merge_success(stopped)
            self.rpc('import', self.profile())
            self.scheduler.disable(); self.flag(False)
            self.settings.update(mode='unknown', enabled=False); self.save()
            try:
                remote = self.rpc('activate')
                if not remote['local_enabled'] or remote.get('task', {}).get('ActiveState') != 'active':
                    raise UserError('未确认 VPS 启用。')
            except Exception:
                self.event('error', '切换未确认，本机保持停用。请恢复连接后重试或切回本机。')
                raise
            self.settings.update(mode='cloud', enabled=True, pending_sync=False); self.save()
            self.event('mode', '已切换到 VPS，本机定时任务已停用。', mode='cloud')
        return self.status(task=True)

    def pause(self):
        if not self.settings['managed']:
            raise UserError('新版尚未接管计划，请先完成接管。')
        if self.settings['mode'] != 'local':
            try:
                remote = self.rpc('deactivate')
            except UserError:
                self.settings.update(mode='unknown', enabled=False); self.save(); self.flag(False)
                self.event('error', '暂停结果未确认，请恢复 SSH 连接后重试。')
                raise
            if remote['local_enabled']:
                raise UserError('未确认 VPS 停用。')
        with self.mutex, legacy.exclusive():
            self.scheduler.disable(); self.flag(False)
            self.settings['enabled'] = False; self.save()
            self.event('pause', '自动签到计划已暂停。')
        return self.status(task=True)

    def resume(self):
        return self.switch_cloud() if self.settings['mode'] == 'cloud' else self.activate_local()

    def save_schedule(self, scheduled):
        validate_time(scheduled)
        with self.mutex, legacy.exclusive():
            previous = dict(self.settings)
            revision = uuid.uuid4().hex
            if self.settings['managed'] and self.settings['mode'] == 'unknown':
                raise UserError('请先确认运行端状态，再修改计划。')
            if self.settings['mode'] == 'cloud' and self.settings['managed']:
                try:
                    self.rpc('schedule', {'time': scheduled, 'revision': revision})
                except UserError:
                    self.settings.update(mode='unknown', enabled=False); self.save(); self.flag(False)
                    self.event('error', '云端时间修改结果未确认，请检查连接后恢复运行端。')
                    raise
            self.settings.update(time=scheduled, revision=revision, pending_sync=True)
            try:
                if self.settings['managed']:
                    self.scheduler.apply(scheduled, self.settings['enabled'] and self.settings['mode'] == 'local')
                self.save()
            except Exception:
                self.settings = previous; self.save()
                self.scheduler.apply(previous['time'], previous['enabled'] and previous['mode'] == 'local')
                if previous['mode'] == 'cloud':
                    try:
                        self.rpc('schedule', {'time': previous['time'], 'revision': previous['revision']})
                    except UserError:
                        self.settings.update(mode='unknown', enabled=False); self.save(); self.flag(False)
                raise
            if self.settings['mode'] == 'cloud':
                self.settings['pending_sync'] = False
            else:
                try:
                    self.rpc('schedule', {'time': scheduled, 'revision': revision})
                    self.settings['pending_sync'] = False
                except UserError:
                    pass
            self.save()
            self.event('schedule', f'每日计划已更新为北京时间 {scheduled}。', pending_sync=self.settings['pending_sync'])
        return self.status(task=True)

    def deploy_remote(self):
        if self.settings['mode'] != 'local':
            raise UserError('请先切回本机，再安装或更新备用服务。')
        stage = self.ssh('mktemp -d /tmp/ahut-desktop.XXXXXXXX')
        if not re.fullmatch(r'/tmp/ahut-desktop\.[A-Za-z0-9]+', stage):
            raise UserError('远端临时目录校验失败。')
        server = ROOT / 'server' if (ROOT / 'server').exists() else ROOT
        source_core = server / 'desktop_core.py' if (server / 'desktop_core.py').exists() else server / 'core.py' if (server / 'core.py').exists() else ROOT / 'desktop' / 'core.py'
        try:
            with tempfile.TemporaryDirectory(prefix='ahut-desktop-deploy-') as temporary:
                archive = Path(temporary) / 'server.tar.gz'
                with tarfile.open(archive, 'w:gz') as bundle:
                    for source, name in [(server / 'app.py', 'app.py'), (source_core, 'desktop_core.py'), (server / 'requirements.txt', 'requirements.txt'), (server / 'install-vps.sh', 'install-vps.sh'), (server / 'README-使用说明.md', 'README-使用说明.md'), (server / 'UPSTREAM.json', 'UPSTREAM.json')]:
                        bundle.add(source, arcname=name, recursive=False)
                    bundle.add(ROOT / 'upstream', arcname='upstream')
                value = self.connection()
                execute(['scp.exe', '-i', value['key'], '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=8', '-P', str(value['port']), str(archive), value['user'] + '@' + value['host'] + ':' + stage + '/server.tar.gz'], timeout=60)
                self.ssh(f"set -e; tar -xzf '{stage}/server.tar.gz' -C '{stage}'; if ! test -x /opt/ahut-wqqd/.venv/bin/python; then bash '{stage}/install-vps.sh' >&2; fi; grep -qxF 'AHUT-WQQD dual-mode installation v1' /opt/ahut-wqqd/INSTALLATION; install -m 644 '{stage}/desktop_core.py' /opt/ahut-wqqd/desktop_core.py", timeout=180)
                self.rpc('prepare')
                self.rpc('import', self.profile())
                self.settings['pending_sync'] = False; self.save()
                self.event('deploy', 'VPS 桌面版服务已就绪，保持停用备用。')
                return self.check_connection()
        finally:
            try:
                self.ssh("rm -r -- '" + stage + "'", timeout=12)
            except UserError:
                self.event('warning', '远端部署临时目录未能自动清理。')

    def remote_action(self, action, payload):
        if WINDOWS:
            raise UserError('远端操作仅支持 Linux。')
        if action == 'status':
            return self.status(task=True)
        if action == 'history':
            return self.history()
        if action == 'prepare':
            if execute(['systemctl', 'is-active', '--quiet', 'ahut-wqqd.service'], check=False).returncode == 0:
                raise UserError('远端任务正在运行，暂不能更新。')
            timer = self.scheduler.info()
            if timer.get('ActiveState') == 'active':
                raise UserError('远端定时器仍在运行，请先停用再更新。')
            unit = Path('/etc/systemd/system/ahut-wqqd.service')
            original = unit.read_text(encoding='utf-8')
            if '# Managed by AHUT-WQQD' not in original:
                raise UserError('同名远端服务不属于本项目。')
            backup = self.data / 'legacy-service.backup'
            if not backup.exists():
                backup.write_text(original, encoding='utf-8'); backup.chmod(0o600); legacy.linux_owner(backup)
            unit.write_text(re.sub(r'^ExecStart=.*$', 'ExecStart=/opt/ahut-wqqd/.venv/bin/python -B /opt/ahut-wqqd/desktop_core.py --scheduled', original, flags=re.M), encoding='utf-8'); unit.chmod(0o644)
            execute(['systemctl', 'daemon-reload'])
            self.scheduler.apply(self.settings['time'], False)
            self.settings.update(managed=True, mode='cloud', enabled=False); self.save(); self.flag(False)
            return self.status(task=True)
        with self.mutex, legacy.exclusive():
            if action == 'import':
                account = legacy.validate_account(payload['account'])
                legacy.save_account(account)
                legacy.remember_success(payload.get('last_success'))
                scheduled = validate_time(payload['time'])
                self.scheduler.apply(scheduled, self.settings['enabled'])
                self.settings.update(time=scheduled, revision=payload['revision'], mode='cloud', managed=True); self.save()
            elif action == 'schedule':
                scheduled = validate_time(payload['time'])
                self.scheduler.apply(scheduled, self.settings['enabled'])
                self.settings.update(time=scheduled, revision=payload['revision']); self.save()
            elif action == 'activate':
                legacy.load_account()
                self.flag(True)
                try:
                    self.scheduler.apply(self.settings['time'], True)
                except Exception:
                    self.flag(False)
                    raise
                self.settings.update(mode='cloud', enabled=True, managed=True); self.save()
            elif action == 'deactivate':
                self.scheduler.disable(); self.flag(False)
                self.settings['enabled'] = False; self.save()
            else:
                raise UserError('未知远端操作。')
            self.event(action, '远端配置已更新。', mode='cloud')
        return self.status(task=True)

    def scheduled_run(self):
        with legacy.exclusive():
            self.settings = self.read('desktop.json', self.settings)
            expected_mode = 'local' if WINDOWS else 'cloud'
            if not legacy.enabled() or not self.settings['enabled'] or not self.settings['managed'] or self.settings['mode'] != expected_mode:
                return 0
            current = now()
            if not within_window(current, self.settings['time']):
                self.event('skipped', '当前不在已配置的执行时间窗口，已跳过。')
                return 0
            account = legacy.load_account()
            if legacy.last_success(account) == current.date().isoformat():
                self.event('skipped', '今天已有成功记录，跳过重复执行。')
                return 0
            module = legacy.load_upstream()
            # Make upstream's date/time checks use Beijing even if Windows changes zones.
            class BeijingDateTime(datetime):
                @classmethod
                def now(cls, tz=None):
                    return super().now(tz or CHINA)
            module.datetime = BeijingDateTime
            def beijing_time():
                value = now()
                return {'date': value.strftime('%Y-%m-%d'), 'time': value.strftime('%H:%M:%S'), 'weekday': '星期' + '一二三四五六日'[value.weekday()], 'full': value.strftime('%Y年%m月%d日 %H:%M:%S')}
            module.get_time = beijing_time
            legacy.setup_logging()
            for handler in logging.getLogger().handlers:
                handler.addFilter(PrivateLogFilter(account))
            self.event('running', '定时签到开始。', mode='local' if WINDOWS else 'cloud')
            try:
                result = asyncio.run(legacy.perform(module, account))
            except Exception as exc:
                logging.error('签到异常类型：%s', type(exc).__name__)
                self.event('failed', '签到发生网络或系统异常，请查看日志。', mode='local' if WINDOWS else 'cloud')
                return 1
            if result.get('success'):
                legacy.remember_success(current.date().isoformat())
                self.event('success', '学校系统已确认今日签到成功。', mode='local' if WINDOWS else 'cloud')
                return 0
            self.event('failed', '学校系统未确认签到成功，请查看详细日志。', mode='local' if WINDOWS else 'cloud')
            return 1


def command_main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--scheduled', action='store_true')
    parser.add_argument('--profile', choices=['primary','secondary'], help='Local standard-edition account slot')
    parser.add_argument('--verify-login', action='store_true', help='Verify the saved school account without checking in')
    parser.add_argument('--rpc', choices=['status', 'import', 'activate', 'deactivate', 'schedule', 'history', 'prepare'])
    parser.add_argument('--data-dir')
    args = parser.parse_args(argv)
    try:
        if WINDOWS:
            if args.rpc:raise UserError('普通版仅支持本机账号计划，VPS 功能尚未开放。')
            from desktop.accounts import StandardService
            service = StandardService(data=args.data_dir, migrate=not args.data_dir)
        else:service = Service(data=args.data_dir, migrate=not args.data_dir)
        if args.scheduled:
            return service.scheduled_run(args.profile) if WINDOWS else service.scheduled_run()
        if args.verify_login:
            service.login(auto_login=service.settings['auto_login'])
            return 0
        content = sys.stdin.read() if args.rpc and sys.stdin else ''
        payload = json.loads(content) if content.strip() else {}
        result = service.remote_action(args.rpc, payload) if args.rpc else service.status()
        if sys.stdout:
            print(json.dumps({'ok': True, 'data': result}, ensure_ascii=False))
        return 0
    except Exception as exc:
        message = str(exc) if isinstance(exc, (UserError, ValueError, legacy.BusyError)) else '操作未完成，请检查日志和连接。'
        if sys.stdout:
            print(json.dumps({'ok': False, 'error': message}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(command_main())
