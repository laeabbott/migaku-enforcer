; Migaku Enforcer — Inno Setup installer script
;
; Build the exe first:  pyinstaller migaku_enforcer.spec
; Then compile this with Inno Setup (https://jrsoftware.org/isinfo.php):
;   iscc installer.iss
; Output: Output\MigakuEnforcerSetup.exe
;
; Deliberately does NOT register the Task Scheduler "start at login" entry itself
; — that stays an in-app step (the setup wizard's "Start at Login" page, or the
; Settings dialog's Startup tab), so it's a user-visible, user-reversible choice
; backed by MigakuEnforcer.install_startup()/uninstall_startup() rather than
; something the installer does silently that the app would then have to reconcile.

#define MyAppName "Migaku Enforcer"
#define MyAppVersion "1.0"
#define MyAppExeName "MigakuEnforcer.exe"

[Setup]
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\Migaku Enforcer
DefaultGroupName=Migaku Enforcer
OutputBaseFilename=MigakuEnforcerSetup
OutputDir=Output
Compression=lzma
SolidCompression=yes
; The installer itself doesn't need admin — it only copies one exe + a shortcut,
; both to per-user locations (see the "auto" constants below). Requiring admin
; here just to write to Program Files would trigger a UAC prompt (and the
; UAC secure-desktop switch's well-known side effect of briefly interrupting
; audio playback) on every single "let me just try this out" launch of the
; installer. PrivilegesRequiredOverridesAllowed lets an advanced user still
; opt into an all-users/Program Files install via the command line or a
; dialog; the default is the no-elevation-needed per-user path.
; The app itself still requires admin every time IT runs (it edits the hosts
; file and kills OS processes) — that prompt is unavoidable and expected, and
; happens later/separately at first launch, not during install.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline dialog
UninstallDisplayIcon={app}\{#MyAppExeName}
DisableProgramGroupPage=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Migaku Enforcer"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall Migaku Enforcer"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Migaku Enforcer"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; MigakuEnforcer.exe carries a requireAdministrator manifest, so launching it via
; plain CreateProcess (what "Flags: postinstall" normally does) fails with
; "CreateProcess failed; code 740: The requested operation requires elevation" —
; Setup itself runs elevated already, but that elevation isn't inherited by a
; plainly-launched child. Rather than fight that, just open the install folder
; and tell the user to right-click -> Run as administrator themselves; see the
; PostInstallPrompt in [Code] below.
Filename: "{win}\explorer.exe"; Parameters: """{app}"""; Flags: postinstall skipifsilent shellexec nowait; Description: "Open the installation folder"

[UninstallDelete]
; Intentionally does NOT remove %APPDATA%\MigakuEnforcer (config, credentials,
; logs) — that's user data, not an installed program file, and should survive
; a reinstall. The scheduled task IS removed (see CurUninstallStepChanged in
; [Code] below), since leaving it pointed at a now-deleted exe would just
; error at next login.

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    MsgBox(
      'Setup is complete!' + #13#10 + #13#10 +
      'Migaku Enforcer needs administrator privileges to run (it blocks websites ' +
      'and closes apps), so it can''t be launched automatically from here.' + #13#10 + #13#10 +
      'The installation folder will open next — right-click MigakuEnforcer.exe ' +
      'and choose "Run as administrator" to launch it and complete setup.',
      mbInformation, MB_OK);
  end;
end;

function NeedsElevatedUninstallCleanup(): Boolean;
var
  ResultCode: Integer;
begin
  // Both checks below are plain read-only queries — no elevation needed just
  // to ask "is X there". Only escalate (and show a UAC prompt) if there's
  // actually something to clean up, so a normal "never used start-at-login,
  // app isn't running" uninstall stays completely prompt-free.
  Result := False;

  if Exec('cmd.exe', '/C schtasks /query /tn "MigakuStudyEnforcer" >nul 2>&1',
     '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    if ResultCode = 0 then
      Result := True;

  if Exec('cmd.exe',
     '/C tasklist /FI "IMAGENAME eq {#MyAppExeName}" | find /I "{#MyAppExeName}" >nul 2>&1',
     '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    if ResultCode = 0 then
      Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    // MigakuEnforcer.exe usually runs elevated (manual "Run as administrator",
    // or the "start at login" scheduled task), so a plain, non-elevated
    // taskkill/schtasks call fails against it with Access Denied — it can't
    // stop a higher-privilege process. Now that the uninstaller itself runs
    // non-elevated by default (see PrivilegesRequired=lowest above), this one
    // cleanup step self-elevates via its own UAC prompt instead of requiring
    // the whole installer to be elevated just for this — and only fires that
    // prompt when NeedsElevatedUninstallCleanup() found something to clean up.
    if NeedsElevatedUninstallCleanup() then
      ShellExec('runas', 'cmd.exe',
        '/C taskkill /IM "{#MyAppExeName}" /F & schtasks /delete /tn "MigakuStudyEnforcer" /f & exit /b 0',
        '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;
