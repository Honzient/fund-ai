; Inno Setup 安装脚本：把 PyInstaller 产物封装为可安装 EXE
; 编译: ISCC.exe fund_ai.iss（需先安装 Inno Setup 6，见 scripts/build_exe.ps1）

#define MyAppName "基金智能分析预测平台"
#define MyAppNameEn "FundAI"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "FundAI"
#define MyAppExeName "FundAI.exe"

[Setup]
AppId={{F8A2E3C1-6B4D-4E2A-9C7B-1D5E8F3A2B41}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\FundAI
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
OutputDir=..\dist_exe
OutputBaseFilename=FundAI-Setup-{#MyAppVersion}
SetupIconFile=..\assets\fundai.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; 无需管理员权限：程序数据写入 %LOCALAPPDATA%\FundAI
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"

[Files]
Source: "..\dist_exe\FundAI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即运行 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
