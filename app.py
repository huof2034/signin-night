"""Single-account AHUT launcher. No school request is made by check/configure/status."""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import ctypes
import getpass
import hashlib
import importlib.util
import json
import logging
from logging.handlers import TimedRotatingFileHandler
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parent
DATA = ROOT / '.local'
CHINA = timezone(timedelta(hours=8))
IS_WINDOWS = os.name == 'nt'
ACCOUNT = DATA / ('account.dpapi' if IS_WINDOWS else 'account.json')
if not IS_WINDOWS:
    os.environ['TZ'] = 'Asia/Shanghai'
    time.tzset()


class BusyError(RuntimeError):
    pass


def ensure_data():
    DATA.mkdir(mode=0o700, exist_ok=True)
    if not IS_WINDOWS:
        DATA.chmod(0o700)
        linux_owner(DATA)


def linux_owner(path):
    if not IS_WINDOWS and os.geteuid() == 0:
        import pwd
        try:
            owner = pwd.getpwnam('ahut-wqqd')
        except KeyError:
            return
        os.chown(path, owner.pw_uid, owner.pw_gid)


def atomic_write(path: Path, data: bytes):
    ensure_data()
    temporary = path.with_name(path.name + '.tmp')
    try:
        with temporary.open('wb') as stream:
            if not IS_WINDOWS:
                os.fchmod(stream.fileno(), 0o600)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        linux_owner(path)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write_json(path, value):
    atomic_write(path, json.dumps(value, ensure_ascii=False).encode('utf-8'))


def dpapi(data: bytes, decrypt=False) -> bytes:
    """Windows DPAPI CurrentUser; never writes plaintext credentials to disk."""
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source = Blob(len(data), buffer)
    target = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                         ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(ctypes.cast(target.data, ctypes.c_void_p))


def validate_account(value):
    student_id = str(value.get('student_id', '')).strip()
    password_hash = str(value.get('password_hash', ''))
    if not re.fullmatch(r'[0-9]{6,20}', student_id):
        raise ValueError('学号应为 6 至 20 位数字。')
    if not re.fullmatch(r'[0-9a-f]{32}', password_hash):
        raise ValueError('账号配置中的密码摘要无效，请重新配置。')
    return {'student_id': student_id, 'password_hash': password_hash}


def load_account():
    if not ACCOUNT.exists():
        raise ValueError('尚未填写签到账号，请先运行“配置账号”。')
    contents = ACCOUNT.read_bytes()
    if IS_WINDOWS:
        contents = dpapi(contents, decrypt=True)
    return validate_account(json.loads(contents))


def save_account(value):
    account = validate_account(value)
    contents = json.dumps(account).encode('utf-8')
    atomic_write(ACCOUNT, dpapi(contents) if IS_WINDOWS else contents)


def last_success(account=None):
    record = read_json(DATA / 'last-success.json', {})
    if account is not None and record.get('student_id') != account['student_id']:
        return None
    return record.get('date')


def remember_success(date_text):
    if not date_text:
        return
    datetime.strptime(date_text, '%Y-%m-%d')
    account = load_account()
    previous = last_success(account)
    if previous is None or date_text > previous:
        write_json(DATA / 'last-success.json', dict(student_id=account['student_id'], date=date_text))


@contextlib.contextmanager
def exclusive():
    ensure_data()
    with (DATA / 'run.lock').open('a+b') as stream:
        if not IS_WINDOWS:
            os.fchmod(stream.fileno(), 0o600)
            linux_owner(DATA / 'run.lock')
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if IS_WINDOWS:
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise BusyError('签到进程正在运行，请稍后再切换。') from exc
        try:
            yield
        finally:
            stream.seek(0)
            if IS_WINDOWS:
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def enabled():
    return read_json(DATA / 'enabled.json', {}).get('enabled') is True


def set_enabled(value):
    with exclusive():
        write_json(DATA / 'enabled.json', {'enabled': value})


def configure(gui=False):
    def save(student_id, password):
        if not password:
            raise ValueError('请输入考勤系统密码。')
        value = {'student_id': student_id.strip(),
                 'password_hash': hashlib.md5(password.encode('utf-8')).hexdigest()}
        with exclusive():
            save_account(value)

    if not gui:
        student_id = input('签到学号: ')
        password = getpass.getpass('考勤系统密码（输入不显示）: ')
        save(student_id, password)
        print('账号已保存。配置过程没有发起登录或签到请求。')
        return
    import tkinter as tk
    from tkinter import messagebox
    window = tk.Tk()
    window.title('安徽工业大学晚寝签到 — 本机账号配置')
    window.geometry('490x260')
    window.resizable(False, False)
    tk.Label(window, text='每天北京时间 22:00；当前默认使用本机方案',
             font=('Microsoft YaHei UI', 11)).pack(pady=(18, 10))
    grid = tk.Frame(window)
    grid.pack()
    tk.Label(grid, text='学号').grid(row=0, column=0, padx=10, pady=8)
    student = tk.Entry(grid, width=32)
    student.grid(row=0, column=1)
    tk.Label(grid, text='考勤密码').grid(row=1, column=0, padx=10, pady=8)
    password = tk.Entry(grid, width=32, show='●')
    password.grid(row=1, column=1)
    tk.Label(window, text='仅保存在本机加密文件中；保存后不会立即签到。',
             fg='#555555').pack(pady=10)

    def submit():
        try:
            save(student.get(), password.get())
        except Exception as exc:
            messagebox.showerror('无法保存', str(exc), parent=window)
            return
        password.delete(0, 'end')
        messagebox.showinfo('已保存', '账号配置已保存。每天 22:00 由启用的一端执行。', parent=window)
        window.destroy()

    tk.Button(window, text='保存账号', command=submit, width=20).pack()
    student.focus_set()
    window.mainloop()


def load_upstream():
    spec = importlib.util.spec_from_file_location('ahut_upstream', ROOT / 'upstream' / 'main.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    # Upstream calls a millisecond function with seconds. Normalize its input only.
    original_sign_code = module.generate_signCode
    module.generate_signCode = lambda stamp: original_sign_code(stamp * 1000 if stamp < 10**11 else stamp)
    # Never execute upstream.main(), which uses random demo accounts and debug=True.
    module.USER_LIST = []
    logging.getLogger().setLevel(logging.INFO)
    return module


def setup_logging():
    logger = logging.getLogger()
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    ensure_data()
    handler = TimedRotatingFileHandler(DATA / 'signin.log', when='midnight', backupCount=30,
                                     encoding='utf-8', utc=True)
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


async def perform(module, account):
    import aiohttp
    user = module.User(int(account['student_id']), password=account['password_hash'], is_encrypted=1)
    # Use upstream's required request headers while adding bounded network timeouts.
    headers = dict(user.session.headers)
    await user.close()
    user._session = aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=30, connect=10))
    try:
        return await asyncio.wait_for(module.sign_in(user, debug=False), timeout=180)
    finally:
        await user.close()


def run():
    with exclusive():
        if IS_WINDOWS and (DATA / 'desktop-managed.json').exists():
            print('此安装已由桌面版接管，请使用晚安助手管理计划。')
            return 0
        if not enabled():
            print('本端未启用，跳过。')
            return 0
        now = datetime.now(CHINA)
        if now.hour != 22 or now.minute >= 15:
            print('当前不在北京时间 22:00–22:14 的执行窗口，跳过。')
            return 0
        account = load_account()
        today = now.date().isoformat()
        if last_success(account) == today:
            print('今天已有成功记录，跳过重复执行。')
            return 0
        module = load_upstream()
        setup_logging()
        logging.info('开始定时任务，北京时间 %s', now.isoformat())
        try:
            result = asyncio.run(perform(module, account))
        except Exception as exc:
            # Exception text may contain an authentication URL; never log it.
            logging.error('任务异常：%s。请检查网络或学校系统。', type(exc).__name__)
            return 1
        if result.get('success'):
            remember_success(today)
            logging.info('任务成功。')
            return 0
        logging.error('任务未成功，请查看前面的步骤日志。')
        return 1


def status():
    account = None
    if ACCOUNT.exists():
        account = load_account()
    return {'configured': account is not None, 'enabled': enabled(),
            'student_id_suffix': account['student_id'][-4:] if account else None,
            'account_tag': hashlib.sha256(account['student_id'].encode()).hexdigest()[:16] if account else None,
            'last_success': last_success(account) if account else None,
            'beijing_now': datetime.now(CHINA).isoformat()}


def cloud_state(on):
    if IS_WINDOWS:
        raise ValueError('cloud-state 仅用于 Linux VPS。')
    timer = 'ahut-wqqd.timer'
    if on:
        load_account()
        set_enabled(True)
        try:
            subprocess.run(['systemctl', 'enable', '--now', timer], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except Exception:
            set_enabled(False)
            raise
    else:
        subprocess.run(['systemctl', 'disable', '--now', timer], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        set_enabled(False)  # Refuses switching if a sign-in is in flight.
    print(json.dumps(status()))


def main():
    parser = argparse.ArgumentParser(description='本机 / VPS 晚寝签到启动器')
    parser.add_argument('command', choices=['configure', 'check', 'status', 'run', 'enable',
                                         'disable', 'export-account', 'import-account',
                                         'cloud-state', 'remember-success'])
    parser.add_argument('value', nargs='?')
    parser.add_argument('--gui', action='store_true')
    parser.add_argument('--require-account', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'configure':
            configure(args.gui)
        elif args.command == 'check':
            module = load_upstream()
            assert module.generate_signCode(1792418400) == module.generate_signCode(1792418400000)
            if args.require_account:
                load_account()
            print(json.dumps({'offline_check': 'ok', **status()}, ensure_ascii=False))
        elif args.command == 'status':
            print(json.dumps(status(), ensure_ascii=False))
        elif args.command == 'run':
            return run()
        elif args.command in ('enable', 'disable'):
            set_enabled(args.command == 'enable')
        elif args.command == 'export-account':
            account = load_account()
            print(json.dumps({**account, 'last_success': last_success(account)}))
        elif args.command == 'import-account':
            if IS_WINDOWS:
                raise ValueError('导入仅用于 VPS；Windows 请使用配置账号界面。')
            value = json.load(sys.stdin)
            with exclusive():
                save_account(value)
                remember_success(value.get('last_success'))
            print('账号已通过 SSH 导入。')
        elif args.command == 'cloud-state':
            if args.value not in ('on', 'off'):
                raise ValueError('需要 on 或 off。')
            cloud_state(args.value == 'on')
        elif args.command == 'remember-success':
            with exclusive():
                remember_success(args.value)
        return 0
    except (ValueError, BusyError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        print('操作失败：' + type(exc).__name__ + '；请检查权限、网络或配置。', file=sys.stderr)
        return 1


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
