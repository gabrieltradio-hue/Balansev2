; Inno Setup script: turns the PyInstaller folder dist\Balanse into one setup file.
; Compile with build_installer.bat, or open this file in Inno Setup and press Compile.

[Setup]
AppId={{6B1F2C1E-3D4A-4E7B-9A55-BA1A5E0B0001}
AppName=BALANSE
AppVersion=1.0.0
AppPublisher=BALANSE
DefaultDirName={autopf}\BALANSE
DefaultGroupName=BALANSE
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=BalanseSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Installs per user by default, so no administrator password is needed
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\Balanse.exe

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "dist\Balanse\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\BALANSE"; Filename: "{app}\Balanse.exe"
Name: "{group}\Uninstall BALANSE"; Filename: "{uninstallexe}"
Name: "{autodesktop}\BALANSE"; Filename: "{app}\Balanse.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Balanse.exe"; Description: "Open BALANSE"; Flags: nowait postinstall skipifsilent
