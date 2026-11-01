"""Standalone Windows updater. No school requests or task registration."""
from __future__ import annotations
import ctypes
from ctypes import wintypes as wt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from desktop.update_lock import installation_lock

APP = '晚安助手.exe'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def wait_process(pid, timeout=30):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    kernel.OpenProcess.restype = wt.HANDLE
    kernel.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
    kernel.CloseHandle.argtypes = [wt.HANDLE]
    handle = kernel.OpenProcess(0x100000, False, pid)
    if not handle:
        return
    try:
        if kernel.WaitForSingleObject(handle, timeout * 1000) != 0:
            raise RuntimeError('助手未退出，更新已取消。')
    finally:
        kernel.CloseHandle(handle)


def run(job):
    work = Path(job['work']).resolve()
    target = Path(job['target']).resolve()
    installer = Path(job['installer']).resolve()
    result = Path(job['result']).resolve()
    if (not work.name.startswith('ahut-update-') or installer.parent != work
            or target == work or target.is_relative_to(work)
            or not (target / APP).is_file() or not (target / '_internal').is_dir()
            or digest(installer) != job['sha256']):
        raise RuntimeError('更新文件或目录校验失败。')
    if job.get('parent'):
        wait_process(job['parent'])
    if job.get('wallpaper_pid'):
        wait_process(job['wallpaper_pid'], 15)
    # Refuse an in-use installation immediately, without waiting for attendance.
    check = subprocess.run([str(target / APP), '--prepare-update'], timeout=30)
    if check.returncode:
        raise RuntimeError('程序文件正在使用中，本次未安装，请稍后重试更新。')
    backup = work / 'backup'
    backup.mkdir()
    names = [APP, '_internal', '使用说明.md', 'THIRD_PARTY_NOTICES.md']
    for name in names:
        source = target / name
        if source.is_dir():
            shutil.copytree(source, backup / name, symlinks=True)
        elif source.is_file():
            shutil.copy2(source, backup / name)
    changed = False
    try:
        changed = True
        command = subprocess.list2cmdline([str(installer), '/S', '/UPDATE'])
        # NSIS /D must be last and consumes the remaining text, including spaces.
        installed = subprocess.run(command + ' /D=' + str(target))
        if installed.returncode == 2:
            changed = False  # Installer refused the in-use directory before copying.
        if installed.returncode:
            raise RuntimeError('安装未完成（代码 %s）。' % installed.returncode)
        report = work / 'selfcheck.json'
        checked = subprocess.run([str(target / APP), '--self-check', str(report)], timeout=60)
        if checked.returncode or not json.loads(report.read_text('utf-8')).get('ok'):
            raise RuntimeError('新版自检失败。')
        if job['version'] != json.loads(report.read_text('utf-8')).get('version'):
            raise RuntimeError('新版版本校验失败。')
    except Exception:
        if changed:
            for name in names:
                source = backup / name
                if source.is_dir():
                    shutil.copytree(source, target / name, dirs_exist_ok=True, symlinks=True)
                elif source.is_file():
                    shutil.copy2(source, target / name)
        raise
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\AHUTSignIn', 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
            if Path(winreg.QueryValueEx(key, 'InstallLocation')[0]).resolve() == target:
                winreg.SetValueEx(key, 'DisplayVersion', 0, winreg.REG_SZ, job['version'])
    except OSError:
        pass
    result.write_text(json.dumps({'ok': True, 'version': job['version'], 'work': str(work)}, ensure_ascii=False), 'utf-8')


def main():
    if sys.argv[1:] == ['--self-check']:
        return 0
    job_path = Path(sys.argv[1]).resolve()
    job = json.loads(job_path.read_text('utf-8'))
    success = False
    try:
        with installation_lock(Path(job['target']) / APP):
            run(job)
        success = True
    except Exception as exc:
        Path(job['result']).write_text(json.dumps({'ok': False, 'message': str(exc),
            'backup': str(job_path.parent / 'backup')}, ensure_ascii=False), 'utf-8')
    finally:
        command = [str(Path(job['target']) / APP)] + job.get('restart_args', [])
        try:
            subprocess.Popen(command, close_fds=True)
        except OSError:
            ctypes.windll.user32.MessageBoxW(None, '更新未完成，请重新打开助手。备份位置：' + str(job_path.parent / 'backup'), '晚安助手', 0x10)
    if success:
        # Remove only this updater's uniquely created workspace after restart.
        # The runner executable lives outside it and is removed on the next launch.
        work = Path(job['work']).resolve()
        if work == job_path.parent and work.name.startswith('ahut-update-'):
            try:
                shutil.rmtree(work)
            except OSError:
                pass  # The restarted application cleans the running updater later.
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
