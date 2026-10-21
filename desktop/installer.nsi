Unicode true
!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"
!ifndef VERSION
!define VERSION "1.5.0"
!endif
Name "晚安助手"
OutFile "..\dist\AHUTSignIn-Setup-${VERSION}-x64.exe"
InstallDir "$LOCALAPPDATA\Programs\AHUTSignIn"
InstallDirRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AHUTSignIn" "InstallLocation"
RequestExecutionLevel user
SetCompressor /SOLID lzma
BrandingText "晚安助手 · AHUT"
VIProductVersion "1.5.0.0"
VIAddVersionKey /LANG=2052 "ProductName" "晚安助手安装程序"
VIAddVersionKey /LANG=2052 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=2052 "FileDescription" "晚安助手 Windows x64 安装程序"
VIAddVersionKey /LANG=2052 "LegalCopyright" "AHUT SignIn Desktop contributors"
!define MUI_ICON "assets\moon.ico"
!define MUI_UNICON "assets\moon.ico"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"
Var NoRegister
Var NoShortcuts

Function .onInit
 ${IfNot} ${RunningX64}
  MessageBox MB_ICONSTOP "此安装包需要 Windows x64。"
  Abort
 ${EndIf}
 StrCpy $NoRegister 0
 StrCpy $NoShortcuts 0
 ClearErrors
 ${GetOptions} $CMDLINE "/NOREGISTER" $0
 ${IfNot} ${Errors}
  StrCpy $NoRegister 1
 ${EndIf}
 ClearErrors
 ${GetOptions} $CMDLINE "/NOSHORTCUTS" $0
 ${IfNot} ${Errors}
  StrCpy $NoShortcuts 1
 ${EndIf}
FunctionEnd

Section "安装"
 SetShellVarContext current
 IfFileExists "$INSTDIR\晚安助手.exe" 0 copy_files
 ExecWait '"$INSTDIR\晚安助手.exe" --prepare-update' $0
 ${If} $0 != 0
  MessageBox MB_ICONSTOP "请先从托盘退出该安装目录的晚安助手，并等待签到完成，再重新安装。" /SD IDOK
  SetErrorLevel 2
  Quit
 ${EndIf}
copy_files:
 SetOutPath "$INSTDIR"
 File /r "..\dist\晚安助手\*"
 WriteINIStr "$INSTDIR\install-options.ini" "Install" "NoRegister" $NoRegister
 WriteINIStr "$INSTDIR\install-options.ini" "Install" "NoShortcuts" $NoShortcuts
 WriteUninstaller "$INSTDIR\Uninstall.exe"
 ${If} $NoShortcuts == 0
  CreateDirectory "$SMPROGRAMS\晚安助手"
  CreateShortcut "$SMPROGRAMS\晚安助手\晚安助手.lnk" "$INSTDIR\晚安助手.exe"
  CreateShortcut "$SMPROGRAMS\晚安助手\使用说明.lnk" "$INSTDIR\使用说明.md"
  CreateShortcut "$SMPROGRAMS\晚安助手\卸载.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortcut "$DESKTOP\晚安助手.lnk" "$INSTDIR\晚安助手.exe"
 ${EndIf}
 ${If} $NoRegister == 0
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AHUTSignIn" "DisplayName" "晚安助手"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AHUTSignIn" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AHUTSignIn" "Publisher" "AHUT SignIn Desktop"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AHUTSignIn" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AHUTSignIn" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AHUTSignIn" "QuietUninstallString" '$\"$INSTDIR\Uninstall.exe$\" /S'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AHUTSignIn" "DisplayIcon" "$INSTDIR\晚安助手.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AHUTSignIn" "URLInfoAbout" "https://github.com/huof2034/signin-night"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AHUTSignIn" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AHUTSignIn" "NoRepair" 1
  ExecWait '"$INSTDIR\晚安助手.exe" --install-tasks' $0
  ${If} $0 != 0
   MessageBox MB_ICONEXCLAMATION "程序已安装，但账号或定时任务迁移未完成。请打开程序逐个账号检查时间并重新启用计划。" /SD IDOK
   SetErrorLevel 3
  ${EndIf}
 ${EndIf}
SectionEnd

Section "Uninstall"
 SetShellVarContext current
 StrCpy $1 0
 ReadRegStr $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AHUTSignIn" "InstallLocation"
 ${If} $0 == $INSTDIR
  StrCpy $1 1
 ${EndIf}
 ReadINIStr $NoRegister "$INSTDIR\install-options.ini" "Install" "NoRegister"
 ReadINIStr $NoShortcuts "$INSTDIR\install-options.ini" "Install" "NoShortcuts"
 ExecWait '"$INSTDIR\晚安助手.exe" --prepare-update' $0
 ${If} $0 != 0
  MessageBox MB_ICONSTOP "请先从托盘退出晚安助手，并等待签到完成，再重新卸载。" /SD IDOK
  SetErrorLevel 2
  Quit
 ${EndIf}
 ${If} $NoRegister != 1
  ExecWait '"$INSTDIR\晚安助手.exe" --uninstall-tasks' $0
  ${If} $0 != 0
   MessageBox MB_ICONSTOP "无法确认定时任务已清理，卸载已停止。请检查任务权限后重试。" /SD IDOK
   SetErrorLevel 3
   Quit
  ${EndIf}
  ReadRegStr $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AHUTSignIn" "InstallLocation"
  ${If} $0 == $INSTDIR
   DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AHUTSignIn"
  ${EndIf}
 ${EndIf}
 ${If} $NoShortcuts != 1
 ${AndIf} $1 == 1
  Delete "$DESKTOP\晚安助手.lnk"
  Delete "$SMPROGRAMS\晚安助手\晚安助手.lnk"
  Delete "$SMPROGRAMS\晚安助手\使用说明.lnk"
  Delete "$SMPROGRAMS\晚安助手\卸载.lnk"
  RMDir "$SMPROGRAMS\晚安助手"
 ${EndIf}
 Delete "$INSTDIR\晚安助手.exe"
 Delete "$INSTDIR\使用说明.md"
 Delete "$INSTDIR\THIRD_PARTY_NOTICES.md"
 Delete "$INSTDIR\install-options.ini"
 RMDir /r "$INSTDIR\_internal"
 Delete "$INSTDIR\Uninstall.exe"
 RMDir "$INSTDIR"
SectionEnd
