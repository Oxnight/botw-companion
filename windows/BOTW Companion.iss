#define MyAppName "BOTW Companion"
#define MyAppVersion "0.40.0-alpha.24"
#define MyAppExeName "BOTW Companion.exe"

[Setup]
AppId={{CE150634-F42B-4815-BE57-F0729FC71365}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=BOTW Companion contributors
DefaultDirName={localappdata}\Programs\BOTW Companion
DefaultGroupName=BOTW Companion
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist\installer
OutputBaseFilename=BOTW_Companion_0.40.0-alpha.24_Setup
SetupIconFile=BOTW Companion.ico
LicenseFile=..\LICENSE
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
CloseApplications=force
RestartApplications=no
VersionInfoVersion=0.40.0.24
VersionInfoProductVersion=0.40.0.24
VersionInfoDescription=Installateur BOTW Companion

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; GroupDescription: "Raccourcis supplémentaires :"; Flags: checkedonce

[Files]
Source: "..\dist\BOTW Companion\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\BOTW Companion"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\BOTW Companion"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer BOTW Companion"; Flags: nowait postinstall skipifsilent
