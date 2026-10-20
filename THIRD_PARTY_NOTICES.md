# 第三方来源与许可声明

安装目录 `_internal/third-party-licenses` 与 `_internal/desktop/vendor` 中保留实际分发组件的许可证。构建用 NSIS 不随程序运行，不需要用户另行安装。

| 组件 | 来源 / 许可 |
| --- | --- |
| 学校接口适配 | [UnthinkingBrain/-_ahut_wqqd](https://github.com/UnthinkingBrain/-_ahut_wqqd)，署名保留在 upstream/main.py，固定提交见 UPSTREAM.json。上游没有单独 LICENSE 文件，README 要求不得用于商业活动；不依据 README 的 MIT 徽章推定重新授权 |
| CPython | [python.org](https://www.python.org/)，PSF 及随附第三方许可 |
| PySide6 / Shiboken6 / Qt 6 | [Qt for Python](https://doc.qt.io/qtforpython-6/licenses.html)，LGPLv3/GPLv3/商业许可及所含第三方许可；此处使用开放源码发行组件并动态加载库 |
| aiohttp 及 Python 依赖 | MIT/Apache/BSD 等，以随附许可证为准 |
| PyInstaller bootloader | GPLv2 或更高版本及分发应用的 bootloader 例外，许可证随附 |
| Node.js | [nodejs/node](https://github.com/nodejs/node)，MIT 与随附依赖许可，NODE-LICENSE.txt 随附 |
| wallpaper-engine-api | [cabraviva/wallpaper-engine-api](https://github.com/cabraviva/wallpaper-engine-api)，MIT，包内 LICENSE 随附 |
| uuid | [uuidjs/uuid](https://github.com/uuidjs/uuid)，MIT |
| RePKG | [notscuffed/repkg](https://github.com/notscuffed/repkg)，MIT 及 THIRD-PARTY-NOTICES.txt |
| windows-capture | [NiiightmareXD/windows-capture](https://github.com/NiiightmareXD/windows-capture)，MIT |
| NSIS | [NSIS License](https://nsis.sourceforge.io/License)，zlib/libpng 及组件许可 |

Qt 库保持独立 DLL，不阻止用户替换兼容库；应用的 Python 源代码与构建说明在本仓库公开。Qt/PySide 源码可从 [Qt 官方源码归档](https://download.qt.io/official_releases/QtForPython/pyside6/) 和 [Qt 6 源码归档](https://download.qt.io/official_releases/qt/) 获取，版本以安装包健康检查及 requirements-desktop.txt 为准。允许为调试对 LGPL 库的修改而进行必要的逆向工程。

Wallpaper Engine 本体和用户壁纸不包含在安装包中，属于各自权利人。默认密码是上游公开的系统初始密码提示，并非开发者个人密码。本项目不声明对第三方代码拥有额外权利，也不将上游整体重新授权。
