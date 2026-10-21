"""Theme-aware native Windows frame; unsupported DWM effects degrade safely."""
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
