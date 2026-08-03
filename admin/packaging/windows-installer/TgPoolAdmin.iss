; Standalone TgPoolAdmin installer.
; Build: dotnet publish apps\admin-desktop -c Release -p:PublishProfile=win-x64
; Compile: iscc packaging\windows-installer\TgPoolAdmin.iss

#define MyAppName "TG Pool Administrator"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "TG Pool Framework"
#define MyAppExeName "TgPoolAdmin.exe"
#define PublishDir "..\..\apps\admin-desktop\bin\Release\net10.0-windows\win-x64\publish"

[Setup]
AppId={{0F94EAF9-1C42-4F15-9B21-EE88993E23AB}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\TgPoolAdmin
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=Output
OutputBaseFilename=TgPoolAdminSetup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Files]
; The only installed payload is the self-contained, single-file administrator app.
Source: "{#PublishDir}\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
