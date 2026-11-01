"""Coordinate scheduled workers with in-place updates without changing tasks."""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes as wt
import hashlib
import os
from pathlib import Path


@contextmanager
def installation_lock(executable, timeout=0):
    if os.name != 'nt':
        yield
        return
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [wt.LPVOID, wt.BOOL, wt.LPCWSTR]
    kernel.CreateMutexW.restype = wt.HANDLE
    kernel.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
    kernel.ReleaseMutex.argtypes = [wt.HANDLE]
    kernel.CloseHandle.argtypes = [wt.HANDLE]
    name = 'Local\\AHUTUpdate-' + hashlib.sha256(str(Path(executable).resolve()).casefold().encode()).hexdigest()
    handle = kernel.CreateMutexW(None, False, name)
    if not handle:
        raise RuntimeError('无法校验程序更新状态。')
    acquired = False
    try:
        acquired = kernel.WaitForSingleObject(handle, int(timeout * 1000)) in (0, 0x80)
        if not acquired:
            raise RuntimeError('程序文件正在使用中，本次未安装，请稍后重试。')
        yield
    finally:
        if acquired:
            kernel.ReleaseMutex(handle)
        kernel.CloseHandle(handle)
