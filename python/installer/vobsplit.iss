; ---------------------------------------------------------------------------
;  VOB Splitter —— Inno Setup 安装脚本（Python 版）
;
;  打包对象：python\build_exe.py 产出的目录版 exe（dist\vobsplit\）
;  刻意不用单文件版：onefile 运行时会把整个包解压到 %TEMP% 再执行，
;  既不可审计，也给注入留了面。目录版是一个正常文件夹，可逐文件检查。
;
;  编译：
;    iscc installer\vobsplit.iss
;  指定输出名：
;    iscc /DMyOutputBase=vobsplit-setup-1.0.0 installer\vobsplit.iss
;  带中文安装界面（需系统装有 Inno 的 SimplifiedChinese 语言包）：
;    iscc /DUseChinese installer\vobsplit.iss
;
;  注意：Inno 的相对路径一律相对**脚本所在目录**（python\installer\）解析。
; ---------------------------------------------------------------------------

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
; Inno 的 VersionInfoVersion 必须是四段式
#ifndef MyAppVersionInfo
  #define MyAppVersionInfo "1.0.0.0"
#endif
#ifndef MyOutputBase
  #define MyOutputBase "vobsplit-setup"
#endif
#ifndef MyAppName
  #define MyAppName "VOB Splitter"
#endif
#ifndef MyAppPublisher
  #define MyAppPublisher "VOB Splitter contributors"
#endif
#ifndef MyAppExeName
  #define MyAppExeName "vobsplit.exe"
#endif
; PyInstaller 目录版产物（本脚本位于 python\installer\，故为 ..\dist\vobsplit）
#ifndef MyDistDir
  #define MyDistDir "..\dist\vobsplit"
#endif
; 命令行版产物（可选：没打 --with-cli 时自动跳过）
#ifndef MyCliDistDir
  #define MyCliDistDir "..\dist\vobsplit-cli"
#endif
#ifndef MyCliExeName
  #define MyCliExeName "vobsplit-cli.exe"
#endif

#define MyAppId "{{7C2A1F8E-5B4D-4C39-9E77-2D1B6A0F5C31}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersionInfo}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} 安装程序
VersionInfoProductName={#MyAppName}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
; 安装程序自己的图标：带深色圆角底板的双帧字形
; （与应用图标分开——应用图标是透明底，贴在应用自己的深色标题栏上才不违和）
SetupIconFile=..\assets\vobsplit-setup.ico
OutputDir=..\..\release
OutputBaseFilename={#MyOutputBase}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
DisableProgramGroupPage=yes
CloseApplications=yes
LicenseFile=..\..\LICENSE
InfoBeforeFile=NOTICE.txt

[Languages]
; 默认英文：任何机器都能编译
Name: "english"; MessagesFile: "compiler:Default.isl"
#ifdef UseChinese
  ; 需要系统装有 Inno 的 SimplifiedChinese 语言包，缺失时用 /DUseChinese 打开
  Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
#endif

[CustomMessages]
english.CreateDesktopIcon=Create a desktop shortcut
english.LaunchApp=Launch {#MyAppName}
english.CliShortcut=VOB Splitter (Command Line)
#ifdef UseChinese
chinesesimplified.CreateDesktopIcon=创建桌面快捷方式
chinesesimplified.LaunchApp=启动 {#MyAppName}
chinesesimplified.CliShortcut=VOB Splitter 命令行
#endif

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; PyInstaller 目录版：主程序 + _internal 依赖目录，整包带走
Source: "{#MyDistDir}\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#MyDistDir}\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
; 命令行版（只在 build_exe.py --with-cli 打过时才存在）
Source: "{#MyCliDistDir}\{#MyCliExeName}"; DestDir: "{app}\cli"; Flags: ignoreversion skipifsourcedoesntexist
Source: "{#MyCliDistDir}\_internal\*"; DestDir: "{app}\cli\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Comment: "{#MyAppName}"
Name: "{group}\{#MyAppName} ({cm:CliShortcut})"; Filename: "{app}\cli\{#MyCliExeName}"; WorkingDir: "{app}"; Check: HasCli
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchApp}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\cli"

[Code]
{ 命令行版只有在 build_exe.py --with-cli 打过时才存在。
  没有它就不装、也不建快捷方式。 }
function HasCli: Boolean;
begin
  Result := FileExists(ExpandConstant('{src}\..\dist\vobsplit-cli\vobsplit-cli.exe'));
end;
