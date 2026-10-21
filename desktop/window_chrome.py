"""Theme-aware native Windows frame; unsupported DWM effects degrade safely."""
import ctypes
import os
from ctypes import wintypes as wt
from functools import lru_cache


def windows_frame_available():
    from PySide6.QtWidgets import QApplication
    return os.name=='nt' and QApplication.platformName()!='offscreen'


@lru_cache(maxsize=1)
def native_api():
    user=ctypes.WinDLL('user32',use_last_error=True)
    get_style=user.GetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p)==8 else user.GetWindowLongW
    set_style=user.SetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p)==8 else user.SetWindowLongW
    get_style.argtypes=[wt.HWND,ctypes.c_int];get_style.restype=ctypes.c_ssize_t
    set_style.argtypes=[wt.HWND,ctypes.c_int,ctypes.c_ssize_t];set_style.restype=ctypes.c_ssize_t
    user.SetWindowPos.argtypes=[wt.HWND,wt.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wt.UINT]
    user.SetWindowPos.restype=wt.BOOL
    user.GetWindowRect.argtypes=[wt.HWND,ctypes.POINTER(wt.RECT)];user.GetWindowRect.restype=wt.BOOL
    user.ScreenToClient.argtypes=[wt.HWND,ctypes.POINTER(wt.POINT)];user.ScreenToClient.restype=wt.BOOL
    user.IsZoomed.argtypes=[wt.HWND];user.IsZoomed.restype=wt.BOOL
    user.MonitorFromWindow.argtypes=[wt.HWND,wt.DWORD];user.MonitorFromWindow.restype=wt.HANDLE
    user.GetMonitorInfoW.argtypes=[wt.HANDLE,ctypes.c_void_p];user.GetMonitorInfoW.restype=wt.BOOL
    return user,get_style,set_style


def enable_custom_frame(window):
    """Keep Windows resizing, shadow, taskbar and keyboard window operations."""
    if not windows_frame_available():return
    try:
        user,get_style,set_style=native_api();handle=int(window.winId())
        style=get_style(handle,-16);wanted=(style & ~0x80000000)|0x00cf0000
        if wanted!=style:
            set_style(handle,-16,wanted)
            user.SetWindowPos(handle,None,0,0,0,0,0x0027)  # FRAMECHANGED, NOMOVE/NOSIZE/NOZORDER
        class Margins(ctypes.Structure):_fields_=[(name,ctypes.c_int) for name in ('left','right','top','bottom')]
        margins=Margins(1,1,1,1);extend=ctypes.WinDLL('dwmapi').DwmExtendFrameIntoClientArea
        extend.argtypes=[wt.HWND,ctypes.POINTER(Margins)];extend.restype=ctypes.c_long
        extend(handle,ctypes.byref(margins))
    except (OSError,AttributeError):pass


def resize_hit(width,height,x,y,border,maximized=False):
    """WM_NCHITTEST edge codes, in physical pixels (DPI and monitor safe)."""
    if maximized or not (0<=x<width and 0<=y<height):return None
    left=x<border;right=x>=width-border;top=y<border;bottom=y>=height-border
    if top:return 13 if left else 14 if right else 12
    if bottom:return 16 if left else 17 if right else 15
    return 10 if left else 11 if right else None


def frame_event(window,message):
    if not windows_frame_available():return None
    try:
        msg=wt.MSG.from_address(int(message));user,_,_=native_api()
        if msg.message==0x0083 and msg.wParam:  # WM_NCCALCSIZE: own the complete title area.
            if user.IsZoomed(msg.hWnd):
                class MonitorInfo(ctypes.Structure):
                    _fields_=[('size',wt.DWORD),('monitor',wt.RECT),('work',wt.RECT),('flags',wt.DWORD)]
                monitor=MonitorInfo();monitor.size=ctypes.sizeof(monitor)
                if user.GetMonitorInfoW(user.MonitorFromWindow(msg.hWnd,2),ctypes.byref(monitor)):
                    rect=wt.RECT.from_address(msg.lParam)
                    rect.left=monitor.work.left;rect.top=monitor.work.top;rect.right=monitor.work.right;rect.bottom=monitor.work.bottom
            return True,0
        if msg.message==0x0084 and hasattr(window,'title_bar'):
            x=ctypes.c_short(msg.lParam & 0xffff).value;y=ctypes.c_short((msg.lParam>>16)&0xffff).value
            rect=wt.RECT()
            if not user.GetWindowRect(msg.hWnd,ctypes.byref(rect)):return None
            hit=resize_hit(rect.right-rect.left,rect.bottom-rect.top,x-rect.left,y-rect.top,
                           max(5,round(6*window.devicePixelRatioF())),bool(user.IsZoomed(msg.hWnd)))
            if hit is not None:return True,hit
            point=wt.POINT(x,y)
            if user.ScreenToClient(msg.hWnd,ctypes.byref(point)):
                from PySide6.QtCore import QPoint
                ratio=window.devicePixelRatioF();local=QPoint(round(point.x/ratio),round(point.y/ratio))
                return True,2 if window.title_bar.drag_at(local) else 1
    except (OSError,AttributeError,ValueError,TypeError):return None
    return None


def apply_chrome(window, colors, mode):
    import os,ctypes
    from ctypes import wintypes as wt
    from PySide6.QtWidgets import QApplication
    if os.name!='nt' or QApplication.platformName()=='offscreen':return False
    try:
        from PySide6.QtGui import QColor
        dwm=ctypes.WinDLL('dwmapi')
        set_attr=dwm.DwmSetWindowAttribute
        set_attr.argtypes=[wt.HWND,wt.DWORD,ctypes.c_void_p,wt.DWORD];set_attr.restype=ctypes.c_long
        handle=int(window.winId())
        def put(key,value):
            data=wt.DWORD(value);return set_attr(handle,key,ctypes.byref(data),ctypes.sizeof(data))==0
        def color(value):
            c=QColor(value);return c.red()|(c.green()<<8)|(c.blue()<<16)
        put(20,int(colors['dark']));put(33,2)
        put(34,0xfffffffe)  # No black outline; keep the compositor's soft shadow.
        glass=put(38,3 if mode=='wallpaper' else 2)
        put(35,0xffffffff if glass else color(colors['bg']))
        put(36,color(colors['heading']))
        return True
    except (OSError,AttributeError,ValueError):return False
