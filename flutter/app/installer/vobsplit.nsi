; ---------------------------------------------------------------------------
;  VOB Splitter —— Windows 安装包（Flutter 桌面版）
;
;  界面不是 NSIS 自带那套 MUI2，而是自己写的一套 Duilib 皮肤：
;    plugin/VobSkin.dll  —— NSIS 插件，把 Duilib 窗口拉起来
;    skin/setup.xml       —— 安装界面布局（Duilib XML）
;    skin/uninstall.xml   —— 卸载界面布局
;    skin/assets/*.png    —— 自绘的少量位图（复选框、最小化/关闭、进度条）
;
;  流程：
;    Page custom SkinPage  —— 自定义页的创建函数被调用后，
;      插件进入自己的消息循环，直到脚本调用 Finish / Quit。
;      安装动作全部在回调里做，每做一步就更新一次进度；
;      回调之间消息循环会继续转，所以进度条是实时刷新的。
;
;    UninstPage custom un.SkinUninstallPage —— 卸载界面同样自绘。
;      卸载器是独立的 exe，插件 DLL 不会自动打进去，脚本自己解一份到
;      $PLUGINSDIR；而且卸载流程整个放在**一次**插件调用里
;      （VobSkin::RunUninstallSkin），不依赖插件在多次调用之间常驻。
;
;  编译前置：
;    cd flutter\app && flutter build windows --release
;    python plugin\build_plugin.py
;
;  编译：
;    makensis /DMyOutFile=... vobsplit.nsi
; ---------------------------------------------------------------------------

Unicode true

; NSIS 默认每次插件调用结束后就卸载插件，于是每次调用都是一个全新的模块实例 ——
; 窗口建在一个实例里，后面的 SetSkinCaption / BindSkinCallback 全落在另一个实例上，
; 全是空操作（表现就是标题改不了、按钮点了没反应）。
; 这里让插件常驻，直到安装程序结束。
SetPluginUnload alwaysoff

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"

; 我们自己的 Duilib 皮肤插件（编译期 makensis 要能找到它）
!addplugindir "plugin\build"

!define APPNAME      "VOB Splitter"
!define APPVERSION   "1.0.0"
!define APPPUBLISHER "VOB Splitter contributors"
!define APPEXE       "vobsplit_gui.exe"
!define APPREGKEY    "Software\VOB Splitter"
!define APPUNINSTKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}"

!ifndef MyOutFile
  !define MyOutFile "..\..\..\..\release\vobsplit-win-x64-setup.exe"
!endif

; 应用文件（flutter build windows --release 的产物）
!define APP_SRC "..\build\windows\x64\runner\Release"

Name "${APPNAME} ${APPVERSION}"
OutFile "${MyOutFile}"
InstallDir "$PROGRAMFILES64\${APPNAME}"
InstallDirRegKey HKLM "${APPREGKEY}" InstallDir
RequestExecutionLevel admin
ShowInstDetails show
ShowUninstDetails show

VIProductVersion "1.0.0.0"
VIAddVersionKey "ProductName"     "${APPNAME}"
VIAddVersionKey "CompanyName"     "${APPPUBLISHER}"
VIAddVersionKey "FileDescription" "VOB Splitter - DVD VOB lossless splitter"
VIAddVersionKey "FileVersion"     "${APPVERSION}"
VIAddVersionKey "ProductVersion"  "${APPVERSION}"
VIAddVersionKey "LegalCopyright"  "MIT License"
VIAddVersionKey "InternalName"    "vobsplit"

!define MUI_ICON   "..\windows\runner\resources\app_icon.ico"
!define MUI_UNICON "..\windows\runner\resources\app_icon.ico"
!define MUI_ABORTWARNING

; NSIS 自带那套页面一个都不用，只留自绘皮肤
Page custom SkinPage
UninstPage custom un.SkinUninstallPage

; 语言放最后（NSIS 要求 MUI_LANGUAGE 在页面宏之后）
!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "English"

Var InstAborted
Var UninstAborted
Var UninstDone
; 静默安装（/S）时 NSIS **不会调用自定义页面的函数**（实测过），
; 所以安装动作必须能脱离界面独立执行，这三个变量就是干这个的。
Var SilentMode      ; 1 = 静默模式（不碰界面）
Var Installed       ; 1 = 已经装过了（Section 里就别再装一遍）
Var UiValue         ; 界面进度更新的参数（用 Var 不用 $0/$1，Call 时寄存器行为没保证）
Var UiDelay

; ---------------------------------------------------------------------------
;  安装界面
; ---------------------------------------------------------------------------
Function SkinPage
  InitPluginsDir
  ; 注意：File /r 是扁平化的 —— skin 里的文件会直接落到 OutPath，
  ; 所以 OutPath 要指到 skin 目录本身
  SetOutPath "$PLUGINSDIR\skin"
  File /r "skin\*"
  File /oname=appicon.ico "..\windows\runner\resources\app_icon.ico"

  VobSkin::InitSkin "$PLUGINSDIR\skin" "setup.xml" "$PLUGINSDIR\appicon.ico"
  VobSkin::SetSkinCaption "${APPNAME} 安装程序"
  VobSkin::SetSkinControl "lblVersion" "text" "${APPVERSION}"
  VobSkin::SetSkinControl "editDir" "text" "$INSTDIR"

  GetFunctionAddress $0 OnSkinCancel
  VobSkin::BindSkinCallback "btnClose" $0
  VobSkin::BindSkinCallback "btnCancel" $0
  GetFunctionAddress $0 OnSkinBrowse
  VobSkin::BindSkinCallback "btnBrowse" $0
  GetFunctionAddress $0 OnSkinInstall
  VobSkin::BindSkinCallback "btnInstall" $0
  GetFunctionAddress $0 OnSkinFinish
  VobSkin::BindSkinCallback "btnFinish" $0

  VobSkin::ShowSkinPage 0

  ; 进消息循环，直到脚本调用 Finish / Quit
  VobSkin::RunSkin
FunctionEnd

Function OnSkinBrowse
  VobSkin::GetSkinControl "editDir" "text"
  Pop $0
  ; 插件里用 IFileDialog 弹现代的文件夹选择器
  VobSkin::BrowseFolder "$0"
  Pop $1
  ${If} $1 != ""
    StrCpy $INSTDIR "$1"
    VobSkin::SetSkinControl "editDir" "text" "$INSTDIR"
  ${EndIf}
FunctionEnd

Function OnSkinCancel
  MessageBox MB_YESNO|MB_ICONQUESTION "确定要退出 ${APPNAME} 安装程序吗？" IDYES +2
    Return
  StrCpy $InstAborted "1"
  VobSkin::QuitSkin
  Abort
FunctionEnd

; ---------------------------------------------------------------------------
;  安装动作
;
;  交互路径和静默路径共用这一段：
;    交互 —— 页面回调里调 DoInstall，边装边刷进度条
;    静默 —— Section 里调 DoInstall，全程不出现任何界面
;
;  联想应用商店的《PC应用审核规范》要求：静默安装时必须在桌面创建快捷方式，
;  所以静默路径无条件建桌面快捷方式；交互路径听用户的勾选。
; ---------------------------------------------------------------------------

; 刷进度条。静默模式下没有界面，直接跳过。
Function UiProgress
  ${If} $SilentMode != "1"
    VobSkin::SetSkinControl "progressBar" "value" $UiValue
    VobSkin::DelaySkin $UiDelay
  ${EndIf}
FunctionEnd

Function DoInstall
  ; 写文件（目录版产物整体铺开）
  SetOutPath "$INSTDIR"
  File "${APP_SRC}\vobsplit_gui.exe"
  StrCpy $UiValue 45
  StrCpy $UiDelay 250
  Call UiProgress
  File "${APP_SRC}\flutter_windows.dll"
  StrCpy $UiValue 68
  StrCpy $UiDelay 250
  Call UiProgress
  File "${APP_SRC}\file_selector_windows_plugin.dll"
  StrCpy $UiValue 80
  StrCpy $UiDelay 250
  Call UiProgress

  SetOutPath "$INSTDIR\data"
  File /r "${APP_SRC}\data\*"
  StrCpy $UiValue 88
  StrCpy $UiDelay 250
  Call UiProgress

  ; 快捷方式
  ${If} $SilentMode == "1"
    ; 静默安装：必须在桌面创建快捷方式（商店审核硬性要求）
    CreateShortCut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\${APPEXE}"
  ${Else}
    VobSkin::GetSkinControl "chkShortcut" "selected"
    Pop $0
    ${If} $0 == "1"
      CreateShortCut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\${APPEXE}"
    ${EndIf}
  ${EndIf}
  CreateShortCut "$SMPROGRAMS\${APPNAME}.lnk" "$INSTDIR\${APPEXE}"
  CreateShortCut "$SMPROGRAMS\卸载 ${APPNAME}.lnk" "$INSTDIR\uninstall.exe"

  ; 卸载器与注册表（这样「程序和卸载」里才有这一项）
  WriteUninstaller "$INSTDIR\uninstall.exe"
  WriteRegStr   HKLM "${APPUNINSTKEY}" "DisplayName"     "${APPNAME}"
  WriteRegStr   HKLM "${APPUNINSTKEY}" "DisplayVersion"  "${APPVERSION}"
  WriteRegStr   HKLM "${APPUNINSTKEY}" "Publisher"       "${APPPUBLISHER}"
  WriteRegStr   HKLM "${APPUNINSTKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr   HKLM "${APPUNINSTKEY}" "DisplayIcon"     "$INSTDIR\${APPEXE}"
  WriteRegStr   HKLM "${APPUNINSTKEY}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegDWORD HKLM "${APPUNINSTKEY}" "NoModify" 1
  WriteRegDWORD HKLM "${APPUNINSTKEY}" "NoRepair" 1
  WriteRegStr   HKLM "${APPREGKEY}" "InstallDir" "$INSTDIR"
FunctionEnd

; 安装：分几步做，每步之间让插件回到消息循环，进度条才能实时刷新
Function OnSkinInstall
  ; 读用户选的安装路径
  VobSkin::GetSkinControl "editDir" "text"
  Pop $0
  ${If} $0 != ""
    StrCpy $INSTDIR "$0"
  ${EndIf}

  ; 切到进度页
  VobSkin::ShowSkinPage 1
  VobSkin::SetSkinControl "lblInstallPath" "text" "$INSTDIR"
  VobSkin::SetSkinControl "lblStatus" "text" "正在写入程序文件…"
  StrCpy $UiValue 8
  StrCpy $UiDelay 450
  Call UiProgress

  Call DoInstall

  VobSkin::SetSkinControl "progressBar" "value" 100
  VobSkin::SetSkinControl "lblStatus" "text" "安装完成"
  VobSkin::DelaySkin 250
  VobSkin::ShowSkinPage 2
  VobSkin::SetSkinControl "lblDonePath" "text" "已安装到 $INSTDIR"
  StrCpy $Installed "1"
FunctionEnd

Function OnSkinFinish
  VobSkin::GetSkinControl "chkRun" "selected"
  Pop $0
  ${If} $0 == "1"
    Exec "$INSTDIR\${APPEXE}"
  ${EndIf}
  VobSkin::FinishSkin
FunctionEnd

; ---------------------------------------------------------------------------
;  卸载界面
; ---------------------------------------------------------------------------
Function un.SkinUninstallPage
  ; 卸载器是独立的 exe，插件 DLL 不会自动打进去 —— 自己解一份出来
  InitPluginsDir
  SetOutPath "$PLUGINSDIR"
  File "plugin\build\VobSkin.dll"

  SetOutPath "$PLUGINSDIR\skin"
  File /r "skin\*"
  File /oname=appicon.ico "..\windows\runner\resources\app_icon.ico"

  ; 安装路径以注册表里的为准（卸载器自己那份不一定准）
  ReadRegStr $0 HKLM "${APPREGKEY}" "InstallDir"
  ${If} $0 != ""
    StrCpy $INSTDIR "$0"
  ${EndIf}

  GetFunctionAddress $0 un.OnUninstCancel
  GetFunctionAddress $1 un.OnUninstRun
  GetFunctionAddress $2 un.OnUninstFinish

  ; 整个卸载流程放在一次插件调用里：
  ; 插件只有在这一调用期间是确定存在的，多步调用在卸载器里会掉进新的模块实例。
  VobSkin::RunUninstallSkin "$PLUGINSDIR\skin" "uninstall.xml" "$PLUGINSDIR\appicon.ico" \
    "${APPNAME} 卸载程序" "${APPVERSION}" "$INSTDIR" $0 $1 $2
FunctionEnd

Function un.OnUninstCancel
  MessageBox MB_YESNO|MB_ICONQUESTION "确定要退出 ${APPNAME} 卸载程序吗？" IDYES +2
    Return
  StrCpy $UninstAborted "1"
  VobSkin::QuitSkin
  Abort
FunctionEnd

Function un.OnUninstRun
  VobSkin::ShowSkinPage 1
  VobSkin::SetSkinControl "lblStatus" "text" "正在删除程序文件…"
  VobSkin::SetSkinControl "progressBar" "value" 15
  VobSkin::DelaySkin 350

  Call un.RemoveFiles

  VobSkin::SetSkinControl "progressBar" "value" 80
  VobSkin::SetSkinControl "lblStatus" "text" "正在清理快捷方式与注册表…"
  VobSkin::DelaySkin 250

  Delete "$SMPROGRAMS\${APPNAME}.lnk"
  Delete "$SMPROGRAMS\卸载 ${APPNAME}.lnk"
  Delete "$DESKTOP\${APPNAME}.lnk"
  DeleteRegKey HKLM "${APPREGKEY}"
  DeleteRegKey HKLM "${APPUNINSTKEY}"

  VobSkin::SetSkinControl "progressBar" "value" 100
  VobSkin::SetSkinControl "lblStatus" "text" "卸载完成"
  VobSkin::DelaySkin 450
  VobSkin::ShowSkinPage 2

  ; 标记一下：删除动作已经在自绘界面里做完了，
  ; 下面的卸载段就不用再删一遍（静默模式 /S 没走过界面，那边才需要补）
  StrCpy $UninstDone "1"
FunctionEnd

Function un.OnUninstFinish
  VobSkin::FinishSkin
FunctionEnd

; 删除程序文件与注册表（自绘界面和静默模式共用）
Function un.RemoveFiles
  Delete /REBOOTOK "$INSTDIR\vobsplit_gui.exe"
  Delete /REBOOTOK "$INSTDIR\flutter_windows.dll"
  Delete /REBOOTOK "$INSTDIR\file_selector_windows_plugin.dll"
  Delete "$INSTDIR\uninstall.exe"
  RMDir /r /REBOOTOK "$INSTDIR\data"
  RMDir /REBOOTOK "$INSTDIR"
FunctionEnd

; ---------------------------------------------------------------------------
;  安装收尾
;
;  交互安装：安装动作在 OnSkinInstall 回调里已经做完了，这里直接跳过。
;  静默安装（/S）：NSIS 不会调用自定义页面的函数（实测过），
;  界面那条路整个走不到 —— 安装动作改由这里的 Section 执行。
;  联想应用商店的《PC应用审核规范》要求安装包支持静默安装，
;  且静默安装过程中不能出现任何界面。
; ---------------------------------------------------------------------------
Section "Install ${APPNAME}"
  ${If} $InstAborted == "1"
    Abort
  ${EndIf}

  ${If} $Installed != "1"
    StrCpy $SilentMode "1"
    Call DoInstall
    StrCpy $Installed "1"
  ${EndIf}
SectionEnd

; ---------------------------------------------------------------------------
;  卸载收尾
;
;  卸载器的 Section 必须以 "un." 开头，否则会被当成安装段 ——
;  卸载器里一段都没有，就会「什么都不显示直接退出」。
;  自绘界面已经删过一遍时这里跳过；静默模式（/S）没走过界面，
;  删除动作在这里补上。
; ---------------------------------------------------------------------------
Section "un.Uninstall"
  ${If} $UninstAborted == "1"
    Abort
  ${EndIf}

  ${If} $UninstDone != "1"
    Call un.RemoveFiles
    Delete "$SMPROGRAMS\${APPNAME}.lnk"
    Delete "$SMPROGRAMS\卸载 ${APPNAME}.lnk"
    Delete "$DESKTOP\${APPNAME}.lnk"
    DeleteRegKey HKLM "${APPREGKEY}"
    DeleteRegKey HKLM "${APPUNINSTKEY}"
  ${EndIf}
SectionEnd
