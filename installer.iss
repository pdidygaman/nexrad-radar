; ── Inno Setup script for NEXRAD Radar ───────────────────────────────
; Builds a per-user installer .exe → Start Menu + optional Desktop shortcut.
; Compile:  "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer.iss

#define MyAppName "NEXRAD Radar"
#define MyAppVersion "1.0"
#define MyAppPublisher "NEXRAD Radar"
#define MyAppExeName "NEXRAD Radar.exe"

[Setup]
AppId={{8F2A1C64-9D3E-4B7A-A1F2-6E5C7B9D4A10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=installer
OutputBaseFilename=NEXRAD-Radar-Setup
SetupIconFile=icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
; Auto-update safety net: if a running instance still holds the app files
; (e.g. a lingering child process), close it via the Restart Manager rather
; than failing. We relaunch the app ourselves (updater.ps1), so don't restart.
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\NEXRAD Radar\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Also place the icon at the app root for the shortcuts
Source: "icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Icon comes from the exe (embedded) — always present and correct
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; AppUserModelID: "NEXRADRadar.Viewer.1"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
; Desktop shortcut always created so it's obvious how to open the app
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; AppUserModelID: "NEXRADRadar.Viewer.1"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName} now"; Flags: nowait postinstall skipifsilent
