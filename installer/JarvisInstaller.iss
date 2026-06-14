#define AppName "Jarvis"
#define AppVersion "0.1.0"
#define AppExeName "Jarvis.exe"

[Setup]
AppId=Jarvis
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=installer\output
OutputBaseFilename={#AppName}-{#AppVersion}-windows-installer
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern
SetupLogging=yes

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "dist\Jarvis\Jarvis.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\Jarvis\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "run_jarvis.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "run_jarvis_console.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "test_packaged_app.bat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[Dirs]
Name: "{app}"
Name: "{app}\_internal"
