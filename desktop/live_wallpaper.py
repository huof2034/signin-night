"""Independent WE player -> scoped WGC frames -> Qt background, no desktop capture.

The native capture runs in a separate process. A fixed-size, latest-frame mmap
keeps exceptions, driver faults and slow consumers away from account/schedule UI.
"""
from __future__ import annotations
import ctypes
from ctypes import wintypes as wt
import hashlib
import importlib.util
import json
import mmap
import os
from pathlib import Path
import struct
import subprocess
import sys
import time
import threading
import uuid

from PySide6.QtCore import QObject,QProcess,QTimer,Signal,Slot,Qt,QSize
from PySide6.QtGui import QImage,QPainter,QColor
from PySide6.QtWidgets import QWidget,QApplication
from .appearance import engine_roots,engine_running,palette

HERE=Path(__file__).resolve().parent
VENDOR=HERE/'vendor'
CAPACITY=64+1280*720*4
MAGIC=0x41485554


def bridge(job,timeout=30):
    result=subprocess.run([str(VENDOR/'wallpaper-api/node.exe'),str(HERE/'wallpaper_bridge.cjs'),json.dumps(job)],
        capture_output=True,timeout=timeout,creationflags=0x08000000)
    if result.returncode:
        try:
            detail=json.loads(result.stdout)
            raise RuntimeError(f'wallpaper bridge failed: {detail.get("operation","unknown")} / {detail.get("code","unknown")} / timeout={bool(detail.get("timeout"))}')
        except ValueError:raise RuntimeError('wallpaper bridge failed')
    return json.loads(result.stdout)


def native_api():
    u=ctypes.WinDLL('user32',use_last_error=True);k=ctypes.WinDLL('kernel32',use_last_error=True)
    u.SetThreadDpiAwarenessContext.argtypes=[ctypes.c_void_p];u.SetThreadDpiAwarenessContext.restype=ctypes.c_void_p
    u.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    u.FindWindowW.argtypes=[wt.LPCWSTR,wt.LPCWSTR];u.FindWindowW.restype=wt.HWND
    u.GetClassNameW.argtypes=[wt.HWND,wt.LPWSTR,ctypes.c_int]
    u.SetWindowPos.argtypes=[wt.HWND,wt.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wt.UINT]
    u.GetWindowLongW.argtypes=[wt.HWND,ctypes.c_int];u.GetWindowLongW.restype=wt.LONG
    u.SetWindowLongW.argtypes=[wt.HWND,ctypes.c_int,wt.LONG]
    u.PostMessageW.argtypes=[wt.HWND,wt.UINT,wt.WPARAM,wt.LPARAM]
    u.GetClientRect.argtypes=[wt.HWND,ctypes.POINTER(wt.RECT)]
    u.GetWindowRect.argtypes=[wt.HWND,ctypes.POINTER(wt.RECT)]
    u.ClientToScreen.argtypes=[wt.HWND,ctypes.POINTER(wt.POINT)]
    u.IsWindow.argtypes=[wt.HWND];u.IsWindowVisible.argtypes=[wt.HWND];u.IsIconic.argtypes=[wt.HWND]
    u.ShowWindow.argtypes=[wt.HWND,ctypes.c_int]
    u.GetWindowThreadProcessId.argtypes=[wt.HWND,ctypes.POINTER(wt.DWORD)]
    u.GetWindow.argtypes=[wt.HWND,wt.UINT];u.GetWindow.restype=wt.HWND
    u.GetWindowTextW.argtypes=[wt.HWND,wt.LPWSTR,ctypes.c_int]
    u.GetForegroundWindow.restype=wt.HWND;u.SetForegroundWindow.argtypes=[wt.HWND]
    k.CreateEventW.argtypes=[ctypes.c_void_p,wt.BOOL,wt.BOOL,wt.LPCWSTR];k.CreateEventW.restype=wt.HANDLE
    k.SetEvent.argtypes=[wt.HANDLE];k.WaitForSingleObject.argtypes=[wt.HANDLE,wt.DWORD]
    k.OpenProcess.argtypes=[wt.DWORD,wt.BOOL,wt.DWORD];k.OpenProcess.restype=wt.HANDLE
    k.CloseHandle.argtypes=[wt.HANDLE]
    return u,k


def player_bounds(u,host):
    client=wt.RECT();point=wt.POINT();u.GetClientRect(host,ctypes.byref(client));u.ClientToScreen(host,ctypes.byref(point))
    width=min(1280,client.right);height=min(720,client.bottom,int(width*9/16));width=min(width,int(height*16/9))
    return point.x,point.y,width,height


def position_player(u,h,host):
    # Desktop windows occupy their own z-order band. HWND_BOTTOM alone can still
    # cover desktop icons, so confine the player to its opaque host's client area.
    if not u.IsWindow(host) or u.IsIconic(host) or not u.IsWindowVisible(host):
        u.ShowWindow(h,0);return
    x,y,width,height=player_bounds(u,host)
    if width<16 or height<16:return
    for index,clear,add in [(-16,0x00cf0000,0x80000000),(-20,0x8,0x08000080)]:
        old=u.GetWindowLongW(h,index)&0xffffffff;new=(old&~clear)|add
        if old!=new:u.SetWindowLongW(h,index,wt.LONG(new))
    rect=wt.RECT();u.GetWindowRect(h,ctypes.byref(rect))
    target=(x,y,x+width,y+height)
    if tuple((rect.left,rect.top,rect.right,rect.bottom))!=target:
        u.SetWindowPos(h,host,x,y,width,height,0x0030)
    elif u.GetWindow(h,3)!=host:
        u.SetWindowPos(h,host,0,0,0,0,0x0013)


def guard_player_window(name,host,stop):
    """Confine only our named pop-out behind its host and preserve focus."""
    u,k=native_api();previous=u.GetForegroundWindow()
    callback_type=ctypes.WINFUNCTYPE(None,wt.HANDLE,wt.DWORD,wt.HWND,wt.LONG,wt.LONG,wt.DWORD,wt.DWORD)
    @callback_type
    def on_event(hook,event,hwnd,obj,child,thread,stamp):
        if hwnd==host and event==0x8003:
            h=player_window(u,name)
            if h:u.ShowWindow(h,0)
            return
        if not hwnd or event not in (0x8002,0x800c):return
        cls=ctypes.create_unicode_buffer(256);u.GetClassNameW(hwnd,cls,256)
        if cls.value!='WPEOverlappedWallpaper':return
        title=ctypes.create_unicode_buffer(256);u.GetWindowTextW(hwnd,title,256)
        if title.value!=name:return
        position_player(u,hwnd,host)
        if u.GetForegroundWindow()==hwnd and previous:u.SetForegroundWindow(previous)
    u.SetWinEventHook.argtypes=[wt.DWORD,wt.DWORD,wt.HMODULE,callback_type,wt.DWORD,wt.DWORD,wt.DWORD];u.SetWinEventHook.restype=wt.HANDLE
    u.UnhookWinEvent.argtypes=[wt.HANDLE]
    u.PeekMessageW.argtypes=[ctypes.POINTER(wt.MSG),wt.HWND,wt.UINT,wt.UINT,wt.UINT]
    hook=u.SetWinEventHook(0x8002,0x800c,None,on_event,0,0,0x0002)
    message=wt.MSG()
    try:
        while not stop.wait(.01):
            while u.PeekMessageW(ctypes.byref(message),None,0,0,1):u.TranslateMessage(ctypes.byref(message));u.DispatchMessageW(ctypes.byref(message))
    finally:
        if hook:u.UnhookWinEvent(hook)


def player_window(u,name):
    if not name.startswith('AHUTLive-'):return None
    h=u.FindWindowW(None,name)
    if not h:return None
    cls=ctypes.create_unicode_buffer(256);u.GetClassNameW(h,cls,256)
    return h if cls.value=='WPEOverlappedWallpaper' else None


def worker_main(arguments):
    job=json.loads(arguments[0]);name=job['name']
    if not name.startswith('AHUTLive-'):return 2
    u,k=native_api();host=job.get('host',0);host_pid=wt.DWORD()
    if not host or not u.GetWindowThreadProcessId(host,ctypes.byref(host_pid)) or host_pid.value!=job['parent']:return 2
    stop=k.CreateEventW(None,True,False,job['event']);parent=k.OpenProcess(0x00100000,False,job['parent'])
    shared=mmap.mmap(-1,CAPACITY,tagname=job['map']);control=None;sequence=0;opened=False;stage='initialize'
    guard_stop=threading.Event();guard_thread=None
    def status(value):struct.pack_into('<I',shared,28,value)
    def stopping():return k.WaitForSingleObject(stop,0)==0 or not parent or k.WaitForSingleObject(parent,0)==0 or not u.IsWindow(host) or u.IsIconic(host) or not u.IsWindowVisible(host)
    def frame(native,length,width,height,stop_list,timestamp):
        nonlocal sequence
        if stopping():stop_list[0]=True;return
        stride=int(native.bytes_per_row)
        if not (0<width<=16384 and 0<height<=16384 and stride>=width*4 and length==stride*height):return
        image=QImage(native.buffer_view(),width,height,stride,QImage.Format.Format_ARGB32)
        image=image.scaled(QSize(1280,720),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation).convertToFormat(QImage.Format.Format_RGB32)
        raw=bytes(image.constBits())
        if len(raw)>CAPACITY-64:stop_list[0]=True;status(3);return
        sequence+=2
        struct.pack_into('<Q',shared,8,sequence-1)
        shared[64:64+len(raw)]=raw
        struct.pack_into('<IIIIQ',shared,16,image.width(),image.height(),image.bytesPerLine(),1,int(time.monotonic()*1000))
        struct.pack_into('<Q',shared,8,sequence)
    try:
        struct.pack_into('<I',shared,0,MAGIC);status(0)
        if stopping():return 0
        # Inspect the scene container using the user-selected RePKG project.
        if job.get('type')=='scene':
            stage='scene-check'
            package=Path(job['file'])
            if package.suffix.lower()!='.pkg' or not package.is_file():raise RuntimeError('missing scene package')
            result=subprocess.run([str(VENDOR/'repkg/RePKG.exe'),'info',str(package)],capture_output=True,timeout=30,creationflags=0x08000000)
            if result.returncode:raise RuntimeError('scene resource check failed')
        if stopping():return 0
        guard_thread=threading.Thread(target=guard_player_window,args=(name,host,guard_stop),daemon=True);guard_thread.start()
        stage='open-player'
        x,y,width,height=player_bounds(u,host)
        # The engine briefly creates a decorated window before borderless takes
        # effect. Leave an initial inset; the show hook restores exact bounds.
        inset=min(32,(width-16)//2,(height-16)//2)
        opened=True;bridge({**job,'action':'open','placement':{'x':x+inset,'y':y+inset,'width':width-2*inset,'height':height-2*inset}})
        h=None
        for _ in range(40):
            if stopping():return 0
            h=player_window(u,name)
            if h:break
            time.sleep(.1)
        if not h:raise RuntimeError('player not created')
        position_player(u,h,host)
        stage='load-capture'
        spec=importlib.util.spec_from_file_location('windows_capture',VENDOR/'capture/windows_capture.pyd')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        capture=module.NativeWindowsCapture(frame,lambda:status(4),False,False,False,33,None,None,None,h)
        stage='start-capture'
        control=capture.start_free_threaded()
        stage='capture'
        while not stopping() and not control.is_finished():
            position_player(u,h,host);time.sleep(.1)
        return 0
    except Exception as exc:
        try:
            log=Path(os.environ['LOCALAPPDATA'])/'AHUTSignIn'/'ui-diagnostics.log'
            with log.open('a',encoding='utf-8') as output:output.write(f'{time.strftime("%Y-%m-%d %H:%M:%S")} wallpaper-worker {stage} {type(exc).__name__}: {str(exc)[:400]}\n')
        except OSError:pass
        status(3);return 1
    finally:
        guard_stop.set()
        if guard_thread:guard_thread.join(1)
        if control and not control.is_finished():
            try:control.stop()
            except Exception:pass
        if opened:
            h=player_window(u,name)
            if h:u.ShowWindow(h,0);u.PostMessageW(h,0x0010,0,0)
            try:bridge({**job,'action':'close'})
            except Exception:pass
        if parent:k.CloseHandle(parent)
        k.CloseHandle(stop);shared.close()


class WallpaperCanvas(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.frame=QImage();self.enabled=False
    def set_frame(self,frame):self.frame=frame;self.update()
    def paintEvent(self,event):
        painter=QPainter(self);p=getattr(self.window(),'theme_colors',palette('dark'))
        painter.fillRect(self.rect(),QColor(p['bg']))
        if self.enabled and not self.frame.isNull():
            image=self.frame
            scale=max(self.width()/image.width(),self.height()/image.height())
            width,height=image.width()*scale,image.height()*scale
            from PySide6.QtCore import QRectF
            painter.drawImage(QRectF((self.width()-width)/2,(self.height()-height)/2,width,height),image)
            veil=QColor('#08121f' if p['dark'] else '#ffffff');veil.setAlpha(70 if p['dark'] else 90)
            painter.fillRect(self.rect(),veil)
        painter.end()


class LiveWallpaper(QObject):
    status_changed=Signal(str)
    frame_ready=Signal(QImage)
    def __init__(self,parent,custom_path=lambda:''):
        super().__init__(parent);self.owner=parent;self.custom_path=custom_path;self.active=False
        self.query=None;self.process=None;self.shared=None;self.stop_event=None;self.job=None;self.signature=None;self.sequence=0
        self.message='动态背景待启动';self.started=0;self.failed_until=0
        self.poll=QTimer(self);self.poll.setInterval(33);self.poll.timeout.connect(self.read_frame)
        self.discovery=QTimer(self);self.discovery.setInterval(5000);self.discovery.timeout.connect(self.discover)
        self.query_timeout=QTimer(self);self.query_timeout.setSingleShot(True);self.query_timeout.timeout.connect(self.cancel_query)

    def say(self,message):
        if self.message!=message:self.message=message;self.status_changed.emit(message)

    def enable(self,enabled):
        enabled=bool(enabled and os.name=='nt' and QApplication.platformName()=='windows')
        if self.active==enabled:return
        self.active=enabled
        if enabled:self.discovery.start();self.discover()
        else:self.discovery.stop();self.cancel_query();self.stop_player();self.say('动态背景已暂停')

    @Slot()
    def shutdown(self):self.enable(False)

    def cancel_query(self):
        self.query_timeout.stop()
        if self.query and self.query.state()!=QProcess.ProcessState.NotRunning:self.query.kill()

    def discover(self):
        if not self.active or self.query or time.monotonic()<self.failed_until:return
        if not engine_running():self.stop_player();self.say('请启动 Wallpaper Engine 以显示动态壁纸');return
        roots=[p for p in engine_roots(self.custom_path()) if (p/'config.json').is_file()]
        node=VENDOR/'wallpaper-api/node.exe'
        if not roots or not node.is_file():self.say('动态组件不可用，请检查 Wallpaper Engine 目录');return
        query=QProcess(self);self.query=query
        query.setProgram(str(node));query.setArguments([str(HERE/'wallpaper_bridge.cjs'),json.dumps({'action':'current','engine':str(roots[0])})])
        query.finished.connect(self.discovered);query.errorOccurred.connect(self.query_error)
        if not self.process:self.say('正在读取当前壁纸项目…')
        self.query_timeout.start(30_000);query.start()

    @Slot(QProcess.ProcessError)
    def query_error(self,error):
        if self.query and error==QProcess.ProcessError.FailedToStart:self.finish_query(None)

    @Slot(int,QProcess.ExitStatus)
    def discovered(self,code,exit_status):
        if not self.query:return
        try:value=json.loads(bytes(self.query.readAllStandardOutput())) if code==0 else None
        except ValueError:value=None
        self.finish_query(value)

    def finish_query(self,value):
        query=self.query;self.query=None;self.query_timeout.stop()
        if query:query.deleteLater()
        if not self.active:return
        if not value or value.get('error'):
            self.say('无法定位当前壁纸，请检查 Wallpaper Engine 配置');return
        signature=hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
        if signature==self.signature and self.process and self.process.poll() is None:return
        self.stop_player();self.signature=signature;self.start_player(value)

    def start_player(self,value):
        u,k=native_api();name='AHUTLive-'+uuid.uuid4().hex
        job={**value,'name':name,'parent':os.getpid(),'host':int(self.owner.winId()),'event':'Local\\'+name+'-stop','map':'Local\\'+name+'-frame'}
        self.job=job;self.sequence=0;self.started=time.monotonic()
        self.stop_event=k.CreateEventW(None,True,False,job['event']);self.shared=mmap.mmap(-1,CAPACITY,tagname=job['map'])
        args=[sys.executable] if getattr(sys,'frozen',False) else [sys.executable,'-B',str(HERE.parent/'desktop_main.py')]
        try:self.process=subprocess.Popen(args+['--wallpaper-worker',json.dumps(job)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=0x08000000)
        except OSError:
            self.stop_player();self.failed_until=time.monotonic()+30;self.say('动态组件无法启动，请重新安装完整程序包');return
        self.say('正在加载当前壁纸的独立动态播放器…');self.poll.start()

    def stop_player(self):
        self.poll.stop()
        if self.stop_event:
            u,k=native_api();k.SetEvent(self.stop_event);k.CloseHandle(self.stop_event);self.stop_event=None
            if self.job:
                h=player_window(u,self.job['name'])
                if h:u.ShowWindow(h,0);u.PostMessageW(h,0x0010,0,0)
        process=self.process;self.process=None
        if process:
            # Native capture teardown cannot block account UI. A stale helper is
            # scoped to this process and its uniquely named player only.
            def reap():
                if process.poll() is None:process.terminate()
            QTimer.singleShot(6000,self,reap)
        if self.shared:self.shared.close();self.shared=None
        self.signature=None;self.job=None;self.frame_ready.emit(QImage())

    def reposition(self):
        if self.job:
            u,k=native_api();h=player_window(u,self.job['name'])
            if h:position_player(u,h,self.job['host'])

    def read_frame(self):
        if not self.shared or not self.process:return
        if self.process.poll() is not None:
            self.stop_player();self.failed_until=time.monotonic()+30;self.say('动态播放未能启动，可检查组件后重新读取');return
        magic=struct.unpack_from('<I',self.shared,0)[0]
        if magic!=MAGIC:return
        sequence=struct.unpack_from('<Q',self.shared,8)[0]
        status=struct.unpack_from('<I',self.shared,28)[0]
        if status==3 or (not sequence and time.monotonic()-self.started>45):
            self.stop_player();self.failed_until=time.monotonic()+30;self.say('当前壁纸动态播放不可用，未使用预览图替代');return
        if not sequence or sequence%2:return
        if sequence==self.sequence:
            heartbeat=struct.unpack_from('<Q',self.shared,32)[0]
            if time.monotonic()*1000-heartbeat>5000:self.say('播放器暂停或画面暂未更新；保留最后一帧')
            return
        width,height,stride=struct.unpack_from('<III',self.shared,16)
        if not (0<width<=1280 and 0<height<=720 and stride==width*4):return
        raw=bytes(self.shared[64:64+stride*height])
        if sequence!=struct.unpack_from('<Q',self.shared,8)[0]:return
        self.sequence=sequence
        self.frame_ready.emit(QImage(raw,width,height,stride,QImage.Format.Format_RGB32).copy())
        self.say('当前桌面同项目 · 独立动态播放 · 非逐帧镜像')
