"""Local appearance preferences and read-only wallpaper colour discovery.

No wallpaper is executed, uploaded, copied, or modified. Wallpaper Engine's
current selection is read from config.json; its preview is sufficient for UI tint.
"""
from __future__ import annotations

import colorsys
import json
import os
from pathlib import Path
import re
import uuid

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QImageReader, QPalette

THEMES = {'light': '浅色', 'dark': '夜间', 'system': '跟随系统', 'wallpaper': '动态壁纸'}
DEFAULTS = dict(theme='wallpaper', startup_animation=True, notifications=True,
                notify_success=True, notify_failed=True, notify_mode=True,
                close_to_tray=True, engine_path='', accent='#3478ed', wallpaper_dark=True,
                surface_transparency=14)


def surface_transparency(value):
    return value if type(value) is int and 0 <= value <= 100 else DEFAULTS['surface_transparency']


class Preferences:
    def __init__(self, data):
        self.path = Path(data) / 'ui-preferences.json'
        try:
            value = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            value = {}
        self.value = dict(DEFAULTS)
        if isinstance(value, dict):
            for key, default in DEFAULTS.items():
                if type(value.get(key)) is type(default): self.value[key] = value[key]
        if self.value['theme'] not in THEMES: self.value['theme'] = DEFAULTS['theme']
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', self.value['accent']): self.value['accent'] = DEFAULTS['accent']
        self.value['surface_transparency'] = surface_transparency(self.value['surface_transparency'])

    def set(self, **changes):
        if 'surface_transparency' in changes:
            changes['surface_transparency'] = surface_transparency(changes['surface_transparency'])
        value = {**self.value, **changes}
        if value == self.value: return
        temporary = self.path.with_name('.ui-preferences-' + uuid.uuid4().hex + '.tmp')
        try:
            temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)
        self.value = value


def system_dark():
    if os.name == 'nt':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
                return winreg.QueryValueEx(key, 'AppsUseLightTheme')[0] == 0
        except OSError: pass
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    return bool(app and app.styleHints().colorScheme() == Qt.ColorScheme.Dark)


def blend(first, second, amount):
    a, b = QColor(first), QColor(second)
    return QColor.fromRgbF(*(a.getRgbF()[i] * (1-amount) + b.getRgbF()[i] * amount for i in range(3))).name()


def luminance(color):
    channels = QColor(color).getRgbF()[:3]
    linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
    return sum(c * w for c, w in zip(linear, (.2126, .7152, .0722)))


def palette(mode, accent='#3478ed', wallpaper_dark=True):
    dark = mode == 'dark' or (mode == 'system' and system_dark()) or (mode == 'wallpaper' and wallpaper_dark)
    color = QColor(accent if mode == 'wallpaper' else '#3478ed')
    hue, lightness, saturation = colorsys.rgb_to_hls(*color.getRgbF()[:3])
    if saturation < .08: hue = .60
    # Readable filled buttons and accent text have separate contrast targets.
    filled = QColor.fromRgbF(*colorsys.hls_to_rgb(hue, .43, max(.48, saturation))).name()
    while luminance(filled) > .17:
        filled = QColor(filled).darker(108).name()
    accent_text = blend(filled, '#ffffff', .45) if dark else filled
    base = '#101724' if dark else '#f5f8fd'
    surface = '#1c2636' if dark else '#ffffff'
    if mode == 'wallpaper':
        base = blend(base, color.name(), .10 if dark else .06)
        surface = blend(surface, color.name(), .06 if dark else .025)
    return dict(dark=dark, accent=filled, accent_text=accent_text, bg=base, surface=surface,
                text='#e5edf8' if dark else '#24364f', heading='#f2f6ff' if dark else '#243b5e',
                muted='#a7b6cc' if dark else '#647994', small='#9aadc7' if dark else '#71839c',
                border='#354357' if dark else '#dfe7f2', input='#151e2c' if dark else '#fbfcff',
                soft=blend(surface, filled, .14 if dark else .08),
                glow=blend(base, filled, .25 if mode == 'wallpaper' else .10),
                success='#88d5ae' if dark else '#287958', success_bg='#1c3a32' if dark else '#e9f6ef',
                error='#f6a8b0' if dark else '#a7404b', error_bg='#402933' if dark else '#fff0f0',
                warning='#e7c77e' if dark else '#8c6625', warning_bg='#3b3325' if dark else '#fff4df')


def stylesheet(base, p, mode, transparency=14):
    # Map the original light UI's shades to semantic roles, so every page shares
    # inputs, errors, tables and menus rather than partially recolouring widgets.
    roles = {
        'text':['#24364f','#59718f','#3f5b7e'], 'heading':['#243b5e','#2d496d'],
        'muted':['#7789a2','#8091a9','#8e9db1','#7d8da3','#7186a2','#8596af'],
        'accent_text':['#2c579b','#4c73ab'], 'accent':['#3478ed','#286be0','#6e9fec','#7ea9f0'],
        'surface':['#ffffff'], 'bg':['#f5f8fd'], 'input':['#fbfcff','#fafcff'],
        'border':['#e3ebf5','#e6edf6','#dfe7f2','#cbdaf0','#e6ebf2','#dce6f4','#cad9ed','#edf1f7','#d6e1f0','#e2eaf5','#dce8fb'],
        'soft':['#edf4ff','#f0f5fd','#e8f0fd','#f0f3f8','#f3f7fd','#eaf2ff','#f3f7ff','#bad2fb','#e9eff9'],
        'muted_disabled':['#a7b3c4','#abc6f6','#8fb4f3'],
        'success':['#328a65'], 'success_bg':['#e9f6ef'],
        'error':['#b35459'], 'error_bg':['#fff0f0','#f2d8da'],
        'warning':['#967027'], 'warning_bg':['#fff4df','#f5dfb1']}
    mapping = {hexcode:p.get(role, p['muted']) for role, codes in roles.items() for hexcode in codes}
    result = re.sub(r'#[0-9a-fA-F]{6}', lambda m:mapping.get(m[0],m[0]), base)
    result += f'''
QMainWindow,QWidget#Main {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {p['bg']},stop:1 {p['glow']}); }}
QWidget#LoginRight {{ background:{p['surface']}; }}
QLabel#LoginHeadline {{ font-size:34px; color:{p['accent_text']}; font-weight:600; }}
QPushButton#Primary,QPushButton#Primary:disabled {{ color:white; }}
QPushButton#Primary:hover {{ background:{QColor(p['accent']).lighter(112).name()}; }}
QPushButton#Primary:disabled {{ background:{blend(p['accent'],p['surface'],.50)}; border-color:{p['border']}; }}
QPushButton#Nav:checked,QPushButton#Mode:checked {{ color:{p['accent_text']}; }}
QCheckBox::indicator:checked {{ image:none; background:{p['accent']}; border:3px solid {p['accent']}; }}
QLabel#Unverified {{ background:{p['soft']}; color:{p['muted']}; border-radius:7px; padding:5px 10px; font-size:11px; }}
QComboBox {{ background:{p['input']}; color:{p['text']}; border:1px solid {p['border']}; border-radius:8px; padding:8px 26px 8px 12px; min-height:20px; }}
QComboBox::drop-down {{ width:24px; border:0; }}
QComboBox::down-arrow,QTimeEdit::up-arrow,QTimeEdit::down-arrow {{ image:none; }}
QComboBox QAbstractItemView {{ background:{p['surface']}; color:{p['text']}; selection-background-color:{p['soft']}; }}
QToolTip {{ background:{p['surface']}; color:{p['text']}; border:1px solid {p['border']}; padding:6px; }}
QDialog,QMessageBox {{ background:{p['bg']}; }}
QSlider::groove:horizontal {{ height:6px; background:{p['border']}; border-radius:3px; }}
QSlider::sub-page:horizontal {{ background:{p['accent']}; border-radius:3px; }}
QSlider::handle:horizontal {{ width:16px; margin:-6px 0; background:{p['surface']}; border:2px solid {p['accent']}; border-radius:9px; }}
QSlider::groove:horizontal:disabled,QSlider::sub-page:horizontal:disabled {{ background:{p['border']}; }}
QSlider::handle:horizontal:disabled {{ border-color:{p['muted']}; }}
'''
    if mode == 'wallpaper':
        rgb = QColor(p['surface']).getRgb()[:3]
        alpha=round(255*(100-surface_transparency(transparency))/100)
        surface=f'rgba({rgb[0]},{rgb[1]},{rgb[2]},{alpha})'
        result += f'QFrame#Card {{ background:{surface}; border:1px solid {p["border"]}; border-radius:16px; }}'
        result += f'QWidget#Sidebar {{ background:{surface}; }}'
    return result


def apply_native_palette(app, p):
    value = QPalette()
    for role, color in [('Window','bg'),('WindowText','text'),('Base','input'),('AlternateBase','soft'),
                        ('Text','text'),('Button','surface'),('ButtonText','text'),('Highlight','accent'),
                        ('HighlightedText',None),('ToolTipBase','surface'),('ToolTipText','text'),('PlaceholderText','muted')]:
        value.setColor(getattr(QPalette.ColorRole, role), QColor(p[color] if color else '#ffffff'))
    value.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(p['muted']))
    app.setPalette(value)


def read_json(path, max_bytes=8_000_000):
    try:
        if path.stat().st_size > max_bytes: return {}
        value = json.loads(path.read_text(encoding='utf-8-sig'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, UnicodeError): return {}


def mapping(value):
    return value if isinstance(value,dict) else {}


def local_path(value):
    """Reject network paths and URLs; theme detection must stay entirely local."""
    if not isinstance(value, str) or not value or value.startswith(('\\\\','//')) or '://' in value: return None
    path = Path(value)
    return path if path.is_absolute() else None


def engine_roots(custom=''):
    roots = []
    if custom:
        candidate = local_path(custom)
        if candidate: roots.append(candidate.parent if candidate.suffix.lower()=='.exe' else candidate)
    if os.name != 'nt': return roots
    import winreg
    steam = None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as key:
            steam = Path(winreg.QueryValueEx(key, 'SteamPath')[0])
    except OSError: pass
    if steam:
        libraries = [steam]
        try:
            content = (steam/'steamapps/libraryfolders.vdf').read_text(encoding='utf-8')
            libraries += [Path(item.replace('\\\\','\\')) for item in re.findall(r'"path"\s+"([^"]+)"', content)]
        except OSError: pass
        roots.extend(item/'steamapps/common/wallpaper_engine' for item in libraries)
    return [root for root in dict.fromkeys(roots) if local_path(str(root))]


def windows_wallpaper():
    if os.name != 'nt': return None
    import ctypes
    buffer = ctypes.create_unicode_buffer(32768)
    if ctypes.windll.user32.SystemParametersInfoW(0x0073, len(buffer), buffer, 0):
        return local_path(buffer.value)
    return None


def engine_running():
    """Read the process names directly; do not start WE just to query a wallpaper."""
    if os.name != 'nt': return False
    import ctypes
    from ctypes import wintypes
    class ProcessEntry(ctypes.Structure):
        _fields_=[('dwSize',wintypes.DWORD),('cntUsage',wintypes.DWORD),('th32ProcessID',wintypes.DWORD),
                  ('th32DefaultHeapID',ctypes.c_size_t),('th32ModuleID',wintypes.DWORD),('cntThreads',wintypes.DWORD),
                  ('th32ParentProcessID',wintypes.DWORD),('pcPriClassBase',wintypes.LONG),('dwFlags',wintypes.DWORD),
                  ('szExeFile',wintypes.WCHAR*260)]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes=[wintypes.DWORD,wintypes.DWORD]; kernel.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
    kernel.Process32FirstW.argtypes=[wintypes.HANDLE,ctypes.POINTER(ProcessEntry)]; kernel.Process32FirstW.restype=wintypes.BOOL
    kernel.Process32NextW.argtypes=[wintypes.HANDLE,ctypes.POINTER(ProcessEntry)]; kernel.Process32NextW.restype=wintypes.BOOL
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]; kernel.CloseHandle.restype=wintypes.BOOL
    handle=kernel.CreateToolhelp32Snapshot(2,0)
    if handle in (None,ctypes.c_void_p(-1).value): return False
    try:
        entry=ProcessEntry(); entry.dwSize=ctypes.sizeof(entry)
        valid=kernel.Process32FirstW(handle,ctypes.byref(entry))
        while valid:
            if entry.szExeFile.lower() in ('wallpaper32.exe','wallpaper64.exe'): return True
            valid=kernel.Process32NextW(handle,ctypes.byref(entry))
        return False
    finally: kernel.CloseHandle(handle)


def scheme_color(value):
    try:
        channels = [float(c) for c in value.split()]
        if len(channels)!=3 or not all(0 <= c <= 1 for c in channels) or max(channels)<.02: return None
        return QColor.fromRgbF(*channels).name()
    except (ValueError, TypeError, AttributeError): return None


def sample_image(path):
    if not path or not path.is_file() or path.stat().st_size > 32_000_000: return None
    reader = QImageReader(str(path)); size = reader.size()
    if not size.isValid() or size.width()*size.height()>100_000_000: return None
    reader.setScaledSize(size.scaled(QSize(80,80), Qt.AspectRatioMode.KeepAspectRatio))
    image = reader.read()
    if image.isNull(): return None
    buckets = {}; totals = [0.,0.,0.]; count=0
    for y in range(image.height()):
        for x in range(image.width()):
            c=image.pixelColor(x,y)
            if c.alphaF()<.5: continue
            rgb=c.getRgbF()[:3]; hue,sat,val=colorsys.rgb_to_hsv(*rgb)
            count+=1
            for i in range(3): totals[i]+=rgb[i]
            if .08<val<.98 and sat>.12:
                key=int(hue*24)%24
                weight=.2+sat
                bucket=buckets.setdefault(key,[0.,0.,0.,0.]); bucket[3]+=weight
                for i in range(3): bucket[i]+=rgb[i]*weight
    if not count: return None
    average=QColor.fromRgbF(*(v/count for v in totals))
    if buckets:
        best=max(buckets.values(),key=lambda b:b[3]); color=QColor.fromRgbF(*(v/best[3] for v in best[:3]))
    else: color=average
    return {'accent':color.name(),'dark':luminance(average.name())<.48}


class WallpaperReader:
    def __init__(self):
        self.cached_signature = None
        self.cached_result = None

    def resolve(self, custom=''):
        for root in (engine_roots(custom) if engine_running() else []):
            config=read_json(root/'config.json')
            profiles=[(key,value) for key,value in config.items() if isinstance(value,dict) and isinstance(value.get('general'),dict)]
            username=os.environ.get('USERNAME','').lower()
            profiles.sort(key=lambda pair:pair[0].lower()!=username)
            for _,profile in profiles:
                selected=mapping(profile['general'].get('wallpaperconfig')).get('selectedwallpapers',{})
                if not isinstance(selected,dict): continue
                chosen=selected.get('Monitor0') or next(iter(selected.values()),{})
                if not isinstance(chosen,dict): continue
                wallpaper=local_path(chosen.get('file'))
                if not wallpaper: continue
                folder=wallpaper if wallpaper.is_dir() else wallpaper.parent
                project=read_json(folder/'project.json',1_000_000)
                preview=None
                name=project.get('preview')
                if isinstance(name,str) and name and '://' not in name:
                    candidate=(folder/name).resolve()
                    if candidate.is_relative_to(folder.resolve()): preview=candidate
                properties=mapping(profile.get('wproperties')).get(chosen['file'],{})
                override=(properties.get('Monitor0') or next(iter(properties.values()),{})) if isinstance(properties,dict) else {}
                color=scheme_color(override.get('schemecolor')) if isinstance(override,dict) else None
                default=mapping(mapping(project.get('general')).get('properties')).get('schemecolor',{})
                color=color or scheme_color(default.get('value') if isinstance(default,dict) else default)
                signature=(str(wallpaper),color,self.stamp(preview))
                if signature==self.cached_signature: return self.cached_result
                sampled=sample_image(preview)
                if not color and not sampled: continue
                return self.cache(signature,{'accent':color or sampled['accent'],
                    'dark':sampled['dark'] if sampled else luminance(color)<.48,
                    'source':'Wallpaper Engine · 主显示器 · '+('壁纸配色' if color else '预览图取色'),
                    'detail':'配色由本地壁纸预览与配置生成；不读取动态画面。'})
        wallpaper=windows_wallpaper()
        signature=('windows',self.stamp(wallpaper))
        if signature==self.cached_signature: return self.cached_result
        sampled=sample_image(wallpaper)
        if sampled:
            return self.cache(signature,{**sampled,'source':'Windows 桌面壁纸 · 本地取色','detail':'Wallpaper Engine 配色不可用，使用系统静态壁纸。'})
        return {'source':'暂未读取到壁纸 · 使用上次配色','detail':'可在下方指定 Wallpaper Engine 安装目录，再点击重新读取。'}

    @staticmethod
    def stamp(path):
        try: return (str(path),path.stat().st_mtime_ns,path.stat().st_size) if path else None
        except OSError: return None

    def cache(self, signature, value):
        self.cached_signature=signature; self.cached_result=value; return value
