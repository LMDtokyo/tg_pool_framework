; TgPoolLauncher.iss — Inno Setup script for the Telegram Andromeda desktop launcher.
;
; What this installer does:
;   1. Installs the self-contained WPF launcher (TgPoolLauncher.exe) -- bundles
;      the .NET runtime, so the target PC needs no separate .NET install.
;   2. Installs the Python local-agent source (tg_pool\, main.py, requirements.txt,
;      .env.example) alongside it -- the launcher runs it via
;      `python -m uvicorn tg_pool.api.app:app`.
;   3. Creates the Data\ folder tree (Accounts, AccountsSpare, Tdata, Sessions,
;      TdataExports, Proxies, Exports, Logs, Crashes) that the app reads/writes
;      at runtime -- see apps/desktop/Services/AppPaths.cs.
;   4. Checks whether Python is present on PATH; if so, runs
;      `pip install -r requirements.txt` during install so first launch works
;      immediately. If not, tells the user to install Python 3.10+ and points
;      them at pip install afterwards -- this installer does NOT bundle its
;      own Python interpreter (see the build notes at the bottom of this file
;      for what that would take).
;
; Build steps (run from the repo root):
;   1. dotnet publish apps\desktop -c Release -p:PublishProfile=win-x64
;   2. iscc packaging\windows-installer\TgPoolLauncher.iss
;   Output: packaging\windows-installer\Output\TelegramAndromedaSetup-<version>.exe
;
; Requires Inno Setup 6 (https://jrsoftware.org/isinfo.php) to compile.

#define MyAppName "Telegram Andromeda"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "TG Pool Framework"
#define MyAppExeName "TgPoolLauncher.exe"
#define UserRoot "..\..\"
#define LocalAgentDir "..\..\services\local-agent"
#define PublishDir "..\..\apps\desktop\bin\Release\net10.0-windows\win-x64\publish"
; Production license/payment server -- installer writes these as per-user env
; vars so every customer install points here without manual configuration.
; See ARCHITECTURE.md / admin/README.md for the server-side deployment this
; talks to; update both values together if the server ever moves.
#define LicenseServerUrl "https://142-111-194-9.sslip.io/license-api"
#define PaymentServerUrl "https://142-111-194-9.sslip.io/pay-api"

[Setup]
; Fixed AppId (GUID) so upgrades/reinstalls are recognized as the same product
; across versions -- generate once, never change.
AppId={{6F1C9F3E-6E2E-4C8B-9E9A-6E9B7C6E9A11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\TelegramAndromeda
DefaultGroupName={#MyAppName}
; lowest + dialog: installer offers "install for me only" (no admin, goes under
; the user's own LocalAppData\Programs -- always writable, no ACL issues) or
; "install for all users" (Program Files, needs admin). Either way {app}\Data
; ends up somewhere the app can read/write without special permissions.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=Output
OutputBaseFilename=TelegramAndromedaSetup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
russian.PythonMissing=Python не найден в PATH.%nУстанови Python 3.10+ с python.org (отметь "Add python.exe to PATH" при установке), затем перезапусти установку -- или после установки открой консоль в папке программы и выполни:%npip install -r requirements.txt
english.PythonMissing=Python was not found on PATH.%nInstall Python 3.10+ from python.org (check "Add python.exe to PATH" during its setup), then re-run this installer -- or after installing, open a console in the app folder and run:%npip install -r requirements.txt
russian.InstallingDeps=Установка Python-зависимостей (requirements.txt) -- это может занять пару минут...
english.InstallingDeps=Installing Python dependencies (requirements.txt) -- this can take a couple of minutes...

[Files]
; The self-contained single-file WPF launcher (built via the win-x64 publish
; profile -- see apps/desktop/Properties/PublishProfiles/win-x64.pubxml).
Source: "{#PublishDir}\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; Python local-agent source -- the launcher spawns `python -m uvicorn tg_pool.api.app:app`
; with {app} as the working directory (see BackendProcessManager.cs).
; __pycache__ excluded: dev-machine bytecode cache, not source -- Python
; regenerates it fresh on first run against whatever interpreter is installed.
Source: "{#LocalAgentDir}\tg_pool\*"; DestDir: "{app}\tg_pool"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "__pycache__,*.pyc"
Source: "{#LocalAgentDir}\main.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#LocalAgentDir}\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#LocalAgentDir}\.env.example"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
; Pre-create the managed Data folders with broad permissions -- the app also
; creates these itself on startup (AppPaths.Initialize()), but doing it here
; too means a per-machine (admin) install still leaves them writable by the
; user who actually runs the app.
Name: "{app}\Data\Accounts"; Permissions: users-modify
Name: "{app}\Data\AccountsSpare"; Permissions: users-modify
Name: "{app}\Data\Tdata"; Permissions: users-modify
Name: "{app}\Data\Sessions"; Permissions: users-modify
Name: "{app}\Data\TdataExports"; Permissions: users-modify
Name: "{app}\Data\Proxies"; Permissions: users-modify
Name: "{app}\Data\Exports"; Permissions: users-modify
Name: "{app}\Data\Logs"; Permissions: users-modify
Name: "{app}\Data\Crashes"; Permissions: users-modify

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Registry]
; Per-user (no admin needed, matches PrivilegesRequired=lowest) so the app's
; Environment.GetEnvironmentVariable("LICENSE_SERVER_URL"/"PAYMENT_SERVER_URL")
; lookups resolve to the production server without any manual setup step.
Root: HKCU; Subkey: "Environment"; ValueType: string; ValueName: "LICENSE_SERVER_URL"; ValueData: "{#LicenseServerUrl}"; Flags: preservestringtype
Root: HKCU; Subkey: "Environment"; ValueType: string; ValueName: "PAYMENT_SERVER_URL"; ValueData: "{#PaymentServerUrl}"; Flags: preservestringtype

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[Code]
function IsPythonAvailable(): Boolean;
var
  ResultCode: Integer;
begin
  // `python --version` -- succeeds (exit 0) only if a real interpreter is on PATH.
  Result := Exec('cmd.exe', '/C python --version', '', SW_HIDE,
    ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  ReqsPath: String;
begin
  if CurStep = ssPostInstall then
  begin
    if IsPythonAvailable() then
    begin
      WizardForm.StatusLabel.Caption := ExpandConstant('{cm:InstallingDeps}');
      ReqsPath := ExpandConstant('{app}\requirements.txt');
      Exec('cmd.exe', '/C pip install -r "' + ReqsPath + '"', ExpandConstant('{app}'),
        SW_SHOWNORMAL, ewWaitUntilTerminated, ResultCode);
      // Non-fatal if pip fails (offline machine, broken pip, etc.) -- the user
      // can always re-run `pip install -r requirements.txt` manually; the
      // installer must not abort just because deps didn't install right now.
    end
    else
      MsgBox(ExpandConstant('{cm:PythonMissing}'), mbInformation, MB_OK);
  end;
end;

// ---------------------------------------------------------------------------
// Build notes: why this doesn't bundle its own Python interpreter
// ---------------------------------------------------------------------------
// A fully self-contained installer (zero dependencies on the target PC) would
// need to embed a Python distribution with every package in requirements.txt
// pre-installed, including C-extension-heavy ones (lupa needs a Lua runtime,
// cryptg compiles native code, pandas/openpyxl are large). Doing that properly
// means building a matching embeddable Python + wheels on a CI machine for the
// target architecture and testing it on a clean VM -- a separate, larger task
// from wiring up this installer. This script instead assumes a normal Python
// install already exists (or the user installs one when prompted) and runs
// `pip install -r requirements.txt` against it during setup.
