#define MyAppName "BOTW Companion"
#define MyAppExeName "BOTW Companion.exe"
#define MyAppVersion GetEnv("BOTW_APP_VERSION")
#define MyAppNumericVersion GetEnv("BOTW_APP_NUMERIC_VERSION")

#if MyAppVersion == ""
  #error MyAppVersion must be provided by the build script
#endif
#if MyAppNumericVersion == ""
  #error MyAppNumericVersion must be provided by the build script
#endif

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
OutputBaseFilename=BOTW_Companion_{#MyAppVersion}_Setup
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
UsePreviousAppDir=yes
UsePreviousTasks=yes
VersionInfoVersion={#MyAppNumericVersion}
VersionInfoProductVersion={#MyAppNumericVersion}
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
