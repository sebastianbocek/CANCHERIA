#define MyAppName "CANCHERIA"
#define MyAppVersion "0.1.8"
#define MyAppPublisher "CANCHERIA"
#define PayloadDir "..\build\installer\payload"

[Setup]
AppId={{9970E2DD-6EF1-49D3-AF8A-475BE7D988D5}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\CANCHERIA
DefaultGroupName=CANCHERIA
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\release
OutputBaseFilename=InstaladorCancheria
SetupIconFile=..\assets\cancheria.ico
UninstallDisplayIcon={app}\cancheria.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UsePreviousAppDir=yes
VersionInfoVersion={#MyAppVersion}.0
VersionInfoDescription=Instalador de CANCHERIA
VersionInfoProductName=CANCHERIA
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Flags: checkedonce

[Files]
; Se extrae temporalmente antes de actualizar para respaldar los datos del
; cliente. No queda instalado junto al programa.
Source: "..\scripts\backup_before_update.ps1"; DestDir: "{tmp}"; Flags: dontcopy
; La configuración editable se instala solo la primera vez. Una actualización
; futura del instalador no pisa los datos que cargó el dueño del complejo.
Source: "{#PayloadDir}\src\cancheria\config\legacy_config.py"; DestDir: "{app}\src\cancheria\config"; Flags: ignoreversion onlyifdoesntexist
; config.py contiene la API key del cliente desde v0.1.8 y tampoco se pisa.
Source: "{#PayloadDir}\config.py"; DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Excludes: "config.py,src\cancheria\config\legacy_config.py,build\*"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{app}\runtime"
Name: "{app}\wa_profile"
Name: "{app}\sessions"
; Los respaldos pertenecen al cliente y no deben borrarse al desinstalar.
Name: "{app}\Backups"; Flags: uninsneveruninstall

[Icons]
Name: "{group}\CANCHERIA"; Filename: "{app}\cancheria.exe"; WorkingDir: "{app}"
Name: "{group}\Configurar CANCHERIA"; Filename: "{app}\configurador_cancheria.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\CANCHERIA"; Filename: "{app}\cancheria.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; La configuración es el primer paso recomendado. No abrimos ambos EXE a la
; vez porque el cliente todavía no cargó su API key, canchas ni horarios.
Filename: "{app}\configurador_cancheria.exe"; Description: "Configurar mi negocio ahora (recomendado)"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\cancheria.exe"; Description: "Abrir CANCHERIA sin configurar"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent unchecked

[Code]
var
  UpdateBackupPath: String;

function ChromeInstalled(): Boolean;
begin
  Result :=
    FileExists(ExpandConstant('{pf}\Google\Chrome\Application\chrome.exe')) or
    FileExists(ExpandConstant('{pf32}\Google\Chrome\Application\chrome.exe')) or
    FileExists(ExpandConstant('{localappdata}\Google\Chrome\Application\chrome.exe'));
end;

function ExistingCancheriaInstallation(): Boolean;
begin
  Result :=
    FileExists(ExpandConstant('{app}\cancheria.exe')) or
    FileExists(ExpandConstant('{app}\src\cancheria\config\legacy_config.py')) or
    DirExists(ExpandConstant('{app}\runtime')) or
    DirExists(ExpandConstant('{app}\wa_profile'));
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  PowerShellExe: String;
  BackupScript: String;
  BackupDir: String;
  ResultFile: String;
  Params: String;
  ResultCode: Integer;
  ResultLines: TArrayOfString;
begin
  Result := '';
  UpdateBackupPath := '';
  if not ExistingCancheriaInstallation() then
    exit;

  ExtractTemporaryFile('backup_before_update.ps1');
  PowerShellExe := ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe');
  BackupScript := ExpandConstant('{tmp}\backup_before_update.ps1');
  BackupDir := ExpandConstant('{app}\Backups');
  ResultFile := ExpandConstant('{tmp}\cancheria_backup_result.txt');
  DeleteFile(ResultFile);
  Params :=
    '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + BackupScript + '"' +
    ' -InstallDir "' + ExpandConstant('{app}') + '"' +
    ' -BackupDir "' + BackupDir + '"' +
    ' -ResultFile "' + ResultFile + '"';

  if (not Exec(PowerShellExe, Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode)) or
     (ResultCode <> 0) then
  begin
    Result :=
      'No se pudo crear el respaldo automático previo a la actualización.' + #13#10 +
      'Cerrá CANCHERIA y Google Chrome, verificá que haya espacio en disco y volvé a intentar.' + #13#10 +
      'La actualización no modificó los archivos instalados.';
    exit;
  end;

  if FileExists(ResultFile) and LoadStringsFromFile(ResultFile, ResultLines) and
     (GetArrayLength(ResultLines) > 0) then
    UpdateBackupPath := ResultLines[0];
  UpdateBackupPath := Trim(UpdateBackupPath);
  if UpdateBackupPath = '' then
    UpdateBackupPath := BackupDir;
  if not WizardSilent then
    SuppressibleMsgBox(
      'Respaldo automático creado correctamente:' + #13#10 + #13#10 +
      UpdateBackupPath + #13#10 + #13#10 +
      'Ahora CANCHERIA se actualizará conservando los datos del cliente.',
      mbInformation,
      MB_OK,
      IDOK
    );
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  if not ChromeInstalled() then
    MsgBox(
      'CANCHERIA utiliza Google Chrome para WhatsApp Web.' + #13#10 + #13#10 +
      'Podés completar la instalación, pero instalá Chrome antes de encender el agente.',
      mbInformation,
      MB_OK
    );
end;

