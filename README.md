# 晚安助手 · AHUT

安徽工业大学晚寝考勤桌面助手。Windows 普通版支持两个账号独立定时、在线账号验证、系统托盘、结果通知，以及浅色、夜间、跟随系统和 Wallpaper Engine 动态壁纸主题。

**[下载最新版 Windows 安装包](https://github.com/huof2034/signin-night/releases/latest/download/AHUTSignIn-Setup-1.5.0-x64.exe)** · [全部版本](https://github.com/huof2034/signin-night/releases) · [中文使用说明](docs/使用说明.md)

## 免责声明与使用限制

本项目为非学校官方的学习研究及个人非商业使用工具。使用前请阅读并遵守以下约定：

- **禁止用于任何非法用途或者商业活动**，包括收费分发、软件销售、商业代签到服务等。
- 仅可使用本人持有或已获得明确授权的账号，不得盗用账号、侵犯他人隐私或干扰学校系统。
- 使用者应遵守法律法规、学校规章及考勤要求，并对自己的使用行为承担相应责任。
- 软件按现状提供，无法保证学校接口、网络及设备环境始终可用；请自行核实考勤结果。不同意上述约定，请停止使用。

## 安装与开始使用

1. 下载 `AHUTSignIn-Setup-1.5.0-x64.exe`，在 Windows 10/11 x64 上运行。安装到当前用户目录，无需另外安装 Python 或 Node.js。
2. 打开“晚安助手”，输入自己的学号和学校考勤密码，点击“验证并进入”。首次添加账号必须联网验证；验证操作不会提交签到。
3. 考勤系统默认密码为：`Ahgydx@920`。这只是提示，不会自动填入；若已修改密码，请输入自己的密码。
4. 在定时设置中选择北京时间，启用自动签到。默认时间为每天 **22:00**，新添加账号的计划需要自行启用。
5. 可添加第二个账号，分别设置每日时间及启用状态。切换当前账号不会暂停另一个账号。

定时任务要求电脑开机、当前用户已登录、网络能访问学校系统。锁屏后可运行；关机、退出 Windows 登录和离线时不能保证执行。程序请求系统唤醒，但能否从睡眠唤醒取决于设备电源设置。当前脚本支持设置 21:30–23:30，实际开放时段以学校为准，单次执行内按原有逻辑有限重试（总超时 180 秒），跨日后不会补交昨日签到。

## 外观与通知

- 浅色、夜间、跟随系统和壁纸适配四种主题；支持开启动画开关。
- Wallpaper Engine 为可选依赖。支持的动态壁纸会独立、静音播放同一项目，动画进度可能与桌面不同；不支持的项目自动回退到静态预览或基础主题。
- 壁纸模式提供卡片及侧栏透明度调节。壁纸与配色在本机处理，不上传桌面画面。
- 关闭窗口默认收起到系统托盘；托盘运行时显示签到和运行状态通知。完全退出托盘后，Windows 定时任务仍可执行，但界面不会弹出结果通知。
- 普通版只提供本机执行。VPS 入口暂不开放，本版本没有付费或会员系统。

## 隐私与更新

发布包不包含开发者账号、密码、SSH 密钥、VPS 配置、签到记录或个人壁纸。你的账号凭据保存在 `%LOCALAPPDATA%\AHUTSignIn`，使用当前 Windows 用户的 DPAPI 加密；验证时直接联系学校考勤系统，不通过作者服务器。请妥善保护自己的 Windows 账户。

升级时先在托盘中退出程序，再安装新版。已有账号和计划保留，安装程序会更新已托管任务的执行路径。卸载会清理属于该安装目录的计划任务与快捷方式，保留个人数据以便重装；如需完全清除，请在卸载后自行删除上述数据目录。

“外观与通知 → 软件更新”及托盘菜单提供**手动检查更新**。默认启动 8 秒后自动检查，窗口或托盘运行期间每 4 小时检查一次 GitHub 正式发布版；可关闭自动检查，完全退出程序后不再检查。发现新版会显示下载入口并按通知设置提示，由你下载安装，不会自动覆盖程序或打断签到。检查仅访问公开版本信息，不发送学号、密码或壁纸；网络失败不影响签到计划。

1.5.0 同时改进分钟跨小时调整（22:00 减一分钟为 21:59）、主题标题栏和外框、主页计划状态与倒计时、配置失败原因提示，以及系统计划的保存速度与回读校验。

安装包暂未购买代码签名证书。可使用发布页 `SHA256SUMS.txt` 校验文件。Windows 10/11 x64 为目标平台，当前发布检查在 Windows 11 x64 完成；学校接口、网络、驱动和 Wallpaper Engine 项目兼容性可能影响实际使用。请查看日志并以学校系统确认的结果为准。

## 从源码构建

需要 Windows x64、Python 3.14 x64、Node.js x64。依赖及构建脚本在仓库中，运行时无需开发环境。

```powershell
python -m venv .desktop-venv
.\.desktop-venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
.\.desktop-venv\Scripts\python.exe -B desktop\setup_wallpaper_deps.py --node "C:\path\to\node.exe"
powershell -NoProfile -ExecutionPolicy Bypass -File desktop\build.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File desktop\build-installer.ps1
```

安装包输出到 `dist`。安装器构建脚本自动下载并校验 NSIS 3.13；壁纸组件的版本和来源保存在 `desktop/vendor/SOURCES.json`。请阅读 [第三方声明](THIRD_PARTY_NOTICES.md)。

离线回归测试（不会提交学校签到）：

```powershell
.\.desktop-venv\Scripts\python.exe -B -m unittest test_offline test_desktop test_desktop_ui test_appearance test_live_wallpaper test_login_runtime test_accounts test_accounts_ui test_release test_takeover test_updates test_software_updates
.\.desktop-venv\Scripts\python.exe -B test_accounts_runtime.py
```

## 来源

学校接口逻辑基于 [UnthinkingBrain/-_ahut_wqqd](https://github.com/UnthinkingBrain/-_ahut_wqqd)，固定版本及文件校验见 `UPSTREAM.json`。保留原作者署名及使用要求；上游 README 标注不得用于商业活动，本仓库不将上游重新授权为 MIT。非学校官方客户端，仅供本人获授权的账号使用，请遵守学校要求。
