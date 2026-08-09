; KOTOBA·AI 安装器脚本（Inno Setup 6，免费开源）
;
; 升级机制：AppId 跨版本固定，新版 Setup.exe 运行时会自动检测已装版本
; 并复用上次的安装路径（含用户自定义路径），直接覆盖升级，无需卸载重装。
;
; 数据策略：所有用户数据存于 %APPDATA%\KOTOBA-AI（或设置页自定义目录，指针
; 位于默认目录内 data_dir.txt），与安装目录完全分离。卸载时可选删除数据。

#define MyAppName "KOTOBA·AI"
#define MyAppVersion "4.0.1"
#define MyAppPublisher "KOTOBA·AI"
#define MyAppExeName "KOTOBA-AI.exe"

[Setup]
; 固定 GUID：升级链条的锚点，发布版本间永不更改
AppId={{8F4B2C6A-7E5D-4B3A-9C1E-2A6D8F0B4E31}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
; 按用户安装：写入 %LOCALAPPDATA%，无 UAC、无管理员权限，安装目录始终可写
DefaultDirName={localappdata}\Programs\KOTOBA-AI
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=KOTOBA-AI-Setup-{#MyAppVersion}
SetupIconFile=..\logo.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; 升级时若应用正在运行，自动关闭后再覆盖（避免 exe 被锁）
CloseApplications=force
CloseApplicationsFilter={#MyAppExeName}
UninstallDisplayName={#MyAppName}

[Languages]
Name: "chinesesimplified"; MessagesFile: "languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："; Flags: unchecked

; 升级时先清理旧的 onedir 载荷，避免上一版残留文件与新结构混杂
[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\{#MyAppExeName}"

[Files]
Source: "..\dist\KOTOBA-AI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\logo.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即运行 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
var
  DeleteDataPage: TInputOptionWizardPage;

// 读取真实数据目录：默认 %APPDATA%\KOTOBA-AI；存在自定义指针则用指针指向的目录
function GetAppDataDir(): String;
var
  DefaultDir, PtrFile: String;
  DataDir: AnsiString; // LoadStringFromFile 第二参需 AnsiString（Inno 6.7.3 实测）
begin
  DefaultDir := ExpandConstant('{userappdata}\KOTOBA-AI');
  PtrFile := DefaultDir + '\data_dir.txt';
  Result := DefaultDir;
  if FileExists(PtrFile) then begin
    if LoadStringFromFile(PtrFile, DataDir) then begin
      DataDir := Trim(DataDir);
      if DataDir <> '' then
        Result := DataDir;
    end;
  end;
end;

// 仅在卸载时创建「是否删除用户数据」复选框（默认不勾，保护数据）
procedure InitializeWizard();
begin
  if IsUninstaller then begin
    DeleteDataPage := CreateInputOptionPage(
      wpWelcome, '卸载 {#MyAppName}', '是否删除用户数据？',
      '学习数据（进度、错题本、知识库、配置等）保存在数据目录中，与程序目录分离。'
      + #13#10 + #13#10
      + '勾选后将一并删除数据目录，此操作不可恢复。',
      True, False);
    DeleteDataPage.Add('删除全部用户数据（含配置、进度、错题本）');
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if (CurUninstallStep = usPostUninstall)
     and Assigned(DeleteDataPage)
     and DeleteDataPage.Values[0] then
  begin
    DataDir := GetAppDataDir();
    if DataDir <> '' then
      if not DelTree(DataDir, True, True, True) then
        MsgBox('无法删除数据目录：' + DataDir, mbError, MB_OK);
  end;
end;
