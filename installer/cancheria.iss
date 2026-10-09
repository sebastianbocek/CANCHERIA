#define MyAppName "CANCHERIA"
#define MyAppVersion "0.2.15"
#define MyAppPublisher "CANCHERIA"
#define PayloadDir "..\build\installer\payload"
#ifndef MyAppId
  #define MyAppId "{{9970E2DD-6EF1-49D3-AF8A-475BE7D988D5}"
#endif
#ifndef MyAppDefaultDir
  #define MyAppDefaultDir "{localappdata}\Programs\CANCHERIA"
#endif

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={#MyAppDefaultDir}
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
Source: "{#PayloadDir}\src\cancheria\config\legacy_config.py"; DestDir: "{app}\src\cancheria\config"; Flags: ignoreversion onlyifdoesntexist uninsneveruninstall
; config.py contiene la API key del cliente desde v0.1.8 y tampoco se pisa.
Source: "{#PayloadDir}\config.py"; DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist uninsneveruninstall
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
  PreservedLegacyConfig: String;
  PreservedRootConfig: String;
  HasPreservedLegacyConfig: Boolean;
  HasPreservedRootConfig: Boolean;

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
  PreserveDir: String;
  InstalledLegacyConfig: String;
  InstalledRootConfig: String;
begin
  Result := '';
  UpdateBackupPath := '';
  HasPreservedLegacyConfig := False;
  HasPreservedRootConfig := False;
  if not ExistingCancheriaInstallation() then
    exit;

  { Copia explícita fuera de la carpeta instalada. No dependemos sólo de }
  { reemplazo de [Files]: al finalizar restauramos exactamente los archivos }
  { que configuró el cliente. }
  PreserveDir := ExpandConstant('{tmp}\cancheria-preserved-config');
  if DirExists(PreserveDir) then
    DelTree(PreserveDir, True, True, True);
  if not ForceDirectories(PreserveDir) then
  begin
    Result := 'No se pudo preparar el área temporal para conservar la configuración. La actualización fue cancelada.';
    exit;
  end;

  InstalledLegacyConfig := ExpandConstant('{app}\src\cancheria\config\legacy_config.py');
  InstalledRootConfig := ExpandConstant('{app}\config.py');
  PreservedLegacyConfig := PreserveDir + '\legacy_config.py';
  PreservedRootConfig := PreserveDir + '\config.py';

  if FileExists(InstalledLegacyConfig) then
  begin
    if not CopyFile(InstalledLegacyConfig, PreservedLegacyConfig, False) then
    begin
      Result := 'No se pudo conservar la configuración existente del negocio. La actualización fue cancelada.';
      exit;
    end;
    HasPreservedLegacyConfig := True;
  end;
  if FileExists(InstalledRootConfig) then
  begin
    if not CopyFile(InstalledRootConfig, PreservedRootConfig, False) then
    begin
      Result := 'No se pudo conservar el config.py existente. La actualización fue cancelada.';
      exit;
    end;
    HasPreservedRootConfig := True;
  end;

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

procedure CurStepChanged(CurStep: TSetupStep);
var
  DestinationLegacyConfig: String;
  DestinationRootConfig: String;
begin
  if CurStep <> ssPostInstall then
    exit;

  DestinationLegacyConfig := ExpandConstant('{app}\src\cancheria\config\legacy_config.py');
  DestinationRootConfig := ExpandConstant('{app}\config.py');

  if HasPreservedLegacyConfig then
  begin
    if not ForceDirectories(ExtractFileDir(DestinationLegacyConfig)) then
      RaiseException('No se pudo recrear la carpeta de configuración de CANCHERIA.');
    if not CopyFile(PreservedLegacyConfig, DestinationLegacyConfig, False) then
      RaiseException('No se pudo restaurar la configuración anterior del negocio.');
  end;

  if HasPreservedRootConfig then
  begin
    if not CopyFile(PreservedRootConfig, DestinationRootConfig, False) then
      RaiseException('No se pudo restaurar el config.py anterior.');
  end;
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

