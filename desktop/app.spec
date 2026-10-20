# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from importlib.metadata import distribution
import sys

root = Path(SPECPATH).parent
datas = [(str(root / 'upstream' / name), 'upstream') for name in ['main.py','README.md']]
datas.append((str(root / 'THIRD_PARTY_NOTICES.md'), '.'))

datas.append((str(root / 'desktop' / 'wallpaper_bridge.cjs'), 'desktop'))
datas.append((str(root / 'desktop' / 'vendor'), 'desktop/vendor'))
for package in ['PySide6-Essentials','shiboken6','aiohttp','aiohappyeyeballs','aiosignal','attrs','frozenlist','idna','multidict','propcache','yarl','pyinstaller']:
    metadata = distribution(package)
    for item in metadata.files or []:
        if 'licenses' in item.parts and metadata.locate_file(item).is_file():
            relative = Path(*item.parts[item.parts.index('licenses')+1:])
            datas.append((str(metadata.locate_file(item)), str(Path('third-party-licenses') / package / relative.parent)))
python_license = Path(sys.base_prefix) / 'LICENSE.txt'
if python_license.exists(): datas.append((str(python_license), 'third-party-licenses/Python'))

smoke = globals().get('SMOKE_LOGIN', False)
entry = root / 'desktop' / 'login_smoke_main.py' if smoke else root / 'desktop_main.py'
target_name = 'AHUTLoginSmoke' if smoke else '晚安助手'
a = Analysis([str(entry)], pathex=[str(root)], binaries=[], datas=datas,
             hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=['tkinter','_tkinter','PySide6.QtQml','PySide6.QtQuick','PySide6.QtWebEngineCore'],
             noarchive=False, optimize=0 if smoke else 1)
# Qt uses the unversioned Windows ICU API. A foreign ICU on PATH can be
# collected under the same DLL name while exporting only versioned symbols.
# Keep the OS ICU dependency, matching the working PySide6 installation.
a.binaries = [entry for entry in a.binaries if Path(entry[0]).name.lower() not in {'icuuc.dll','icudt78.dll'}]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=target_name, debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          icon=str(root / 'desktop' / 'assets' / 'moon.ico'), version=str(root / 'desktop' / 'version.txt'))
collection = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=target_name)
