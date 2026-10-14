; Inno Setup script - creates a normal Windows Setup.exe
[Setup]
AppName=4nextech Time
AppVersion=1.0
AppPublisher=4nextech
DefaultDirName={autopf}\4nextech Time
DefaultGroupName=4nextech Time
OutputDir=installer_output
OutputBaseFilename=4nextech-Time-Setup
SetupIconFile=static\icons\app.ico
UninstallDisplayIcon={app}\4nextech Time.exe
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: checkedonce
Name: "startup"; Description: "Start automatically when Windows starts"; Flags: checkedonce

[Files]
Source: "dist\4nextech Time\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\4nextech Time"; Filename: "{app}\4nextech Time.exe"
Name: "{autodesktop}\4nextech Time"; Filename: "{app}\4nextech Time.exe"; Tasks: desktopicon
Name: "{userstartup}\4nextech Time"; Filename: "{app}\4nextech Time.exe"; Tasks: startup

[Run]
; let phones on the same Wi-Fi reach the app
Filename: "netsh"; Parameters: "advfirewall firewall add rule name=""4nextech Time"" dir=in action=allow protocol=TCP localport=80,5000"; Flags: runhidden
Filename: "{app}\4nextech Time.exe"; Description: "Launch 4nextech Time"; Flags: postinstall nowait skipifsilent

[UninstallRun]
Filename: "netsh"; Parameters: "advfirewall firewall delete rule name=""4nextech Time"""; Flags: runhidden
; data (employees, punches) stays in %LOCALAPPDATA%\4nextech Time and is NOT deleted on uninstall
