param(
    [switch]$SkipExeBuild
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BuildRoot = Join-Path $Root "build\installer"
$SourceRoot = Join-Path $BuildRoot "source"
$PayloadRoot = Join-Path $BuildRoot "payload"
$BinRoot = Join-Path $BuildRoot "bin"
$BuildPython = Join-Path $Root ".build-venv\Scripts\python.exe"
$Icon = Join-Path $Root "assets\cancheria.ico"
$SanitizedConfig = Join-Path $Root "src\cancheria\config\config_backups\config_20261006_213845.py"

if (-not $BuildRoot.StartsWith($Root, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Directorio de build fuera del proyecto: $BuildRoot"
}
if (-not (Test-Path -LiteralPath $BuildPython -PathType Leaf)) {
    throw "No existe el entorno de build: $BuildPython. Ejecutá build_windows.bat primero."
}
if (-not (Test-Path -LiteralPath $SanitizedConfig -PathType Leaf)) {
    throw "No existe la plantilla de configuración limpia: $SanitizedConfig"
}

if (Test-Path -LiteralPath $BuildRoot) {
    Remove-Item -LiteralPath $BuildRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $SourceRoot, $PayloadRoot, $BinRoot -Force | Out-Null

$RootFiles = @(
    "WPSetter.py",
    "calendario.py",
    "cancheria_desktop.py",
    "cancheria_updater.py",
    "config.py",
    "configurador_cancheria.py",
    "event_registration_engine.py",
    ".env.example",
    "README.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md"
)
$SourceDirs = @("src", "legacy", "assets", "docs", "examples")

foreach ($name in $RootFiles) {
    $source = Join-Path $Root $name
    if (Test-Path -LiteralPath $source -PathType Leaf) {
        Copy-Item -LiteralPath $source -Destination (Join-Path $SourceRoot $name) -Force
    }
}
foreach ($name in $SourceDirs) {
    Copy-Item -LiteralPath (Join-Path $Root $name) -Destination (Join-Path $SourceRoot $name) -Recurse -Force
}

# The installed package must be genuinely fresh.  Use the repository's clean
# configuration template and remove every local backup that could contain data
# entered on the build machine.
$StagedConfigDir = Join-Path $SourceRoot "src\cancheria\config"
Copy-Item -LiteralPath $SanitizedConfig -Destination (Join-Path $StagedConfigDir "legacy_config.py") -Force
$StagedBackups = Join-Path $StagedConfigDir "config_backups"
if (Test-Path -LiteralPath $StagedBackups) {
    $resolvedBackups = (Resolve-Path -LiteralPath $StagedBackups).Path
    if (-not $resolvedBackups.StartsWith($SourceRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Ruta de backups fuera del staging: $resolvedBackups"
    }
    Remove-Item -LiteralPath $resolvedBackups -Recurse -Force
}
Get-ChildItem -LiteralPath $SourceRoot -Directory -Filter "__pycache__" -Recurse -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $SourceRoot -File -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -in @(".pyc", ".pyo") } |
    Remove-Item -Force

$env:PYTHONPATH = (Join-Path $SourceRoot "src")
$SpecDir = Join-Path $BuildRoot "spec"
New-Item -ItemType Directory -Path $SpecDir -Force | Out-Null

if (-not $SkipExeBuild) {
    $CommonHiddenImports = @(
        "--hidden-import", "json",
        "--hidden-import", "sqlite3",
        "--hidden-import", "_sqlite3",
        "--hidden-import", "decimal",
        "--hidden-import", "zoneinfo",
        "--hidden-import", "email.mime.image",
        "--hidden-import", "email.mime.multipart",
        "--hidden-import", "email.mime.text",
        "--hidden-import", "openai",
        "--hidden-import", "playwright.async_api",
        "--hidden-import", "pytz",
        "--hidden-import", "dotenv",
        "--hidden-import", "cancheria.legacy_bridge",
        "--hidden-import", "cancheria.paths",
        "--hidden-import", "cancheria.config.legacy_config",
        "--hidden-import", "cancheria.domain.events.registration",
        "--hidden-import", "cancheria.domain.reservations.calendar",
        "--hidden-import", "cancheria.admin.desktop_service",
        "--hidden-import", "cancheria.desktop.admin_panel",
        "--hidden-import", "cancheria.desktop.update_service",
        "--hidden-import", "cancheria.desktop.update_helper",
        "--hidden-import", "cancheria.desktop.ai_control"
    )
    $MainArgs = @(
        "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", "cancheria",
        "--distpath", $BinRoot,
        "--workpath", (Join-Path $BuildRoot "pyinstaller-cancheria"),
        "--specpath", $SpecDir,
        "--icon", $Icon,
        "--paths", (Join-Path $SourceRoot "src")
    ) + $CommonHiddenImports + @((Join-Path $SourceRoot "cancheria_desktop.py"))
    & $BuildPython -m PyInstaller @MainArgs
    if ($LASTEXITCODE -ne 0) { throw "Falló la compilación de cancheria.exe" }

    $ConfigArgs = @(
        "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", "configurador_cancheria",
        "--distpath", $BinRoot,
        "--workpath", (Join-Path $BuildRoot "pyinstaller-configurador"),
        "--specpath", $SpecDir,
        "--icon", $Icon,
        "--paths", (Join-Path $SourceRoot "src"),
        "--hidden-import", "json",
        "--hidden-import", "sqlite3",
        "--hidden-import", "_sqlite3",
        "--hidden-import", "decimal",
        "--hidden-import", "zoneinfo",
        "--hidden-import", "cancheria.paths",
        "--hidden-import", "cancheria.config.legacy_config",
        (Join-Path $SourceRoot "configurador_cancheria.py")
    )
    & $BuildPython -m PyInstaller @ConfigArgs
    if ($LASTEXITCODE -ne 0) { throw "Falló la compilación de configurador_cancheria.exe" }

    $UpdaterArgs = @(
        "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", "CancheriaUpdater",
        "--distpath", $BinRoot,
        "--workpath", (Join-Path $BuildRoot "pyinstaller-updater"),
        "--specpath", $SpecDir,
        "--icon", $Icon,
        "--paths", (Join-Path $SourceRoot "src"),
        "--hidden-import", "cancheria.desktop.update_service",
        "--hidden-import", "cancheria.desktop.update_helper",
        (Join-Path $SourceRoot "cancheria_updater.py")
    )
    & $BuildPython -m PyInstaller @UpdaterArgs
    if ($LASTEXITCODE -ne 0) { throw "Falló la compilación de CancheriaUpdater.exe" }
}

foreach ($name in $RootFiles) {
    $source = Join-Path $SourceRoot $name
    if (Test-Path -LiteralPath $source -PathType Leaf) {
        Copy-Item -LiteralPath $source -Destination (Join-Path $PayloadRoot $name) -Force
    }
}
foreach ($name in $SourceDirs) {
    Copy-Item -LiteralPath (Join-Path $SourceRoot $name) -Destination (Join-Path $PayloadRoot $name) -Recurse -Force
}
Copy-Item -LiteralPath (Join-Path $BinRoot "cancheria.exe") -Destination $PayloadRoot -Force
Copy-Item -LiteralPath (Join-Path $BinRoot "configurador_cancheria.exe") -Destination $PayloadRoot -Force
Copy-Item -LiteralPath (Join-Path $BinRoot "CancheriaUpdater.exe") -Destination $PayloadRoot -Force
New-Item -ItemType Directory -Path (Join-Path $PayloadRoot "runtime"), (Join-Path $PayloadRoot "wa_profile"), (Join-Path $PayloadRoot "sessions") -Force | Out-Null

# Verify the fresh source payload contains no OpenAI-style key or operational
# files from the machine that built it.
$SecretMatches = Get-ChildItem -LiteralPath $PayloadRoot -File -Filter "*.py" -Recurse |
    Select-String -Pattern "sk-[A-Za-z0-9_-]{16,}" -AllMatches
if ($SecretMatches) {
    throw "El payload contiene una credencial y no se generará el instalador."
}
$UnexpectedRuntimeFiles = Get-ChildItem -LiteralPath (Join-Path $PayloadRoot "runtime") -File -Recurse -ErrorAction SilentlyContinue
if ($UnexpectedRuntimeFiles) {
    throw "El runtime limpio contiene datos inesperados."
}

$env:CANCHERIA_INSTALL_ROOT = $PayloadRoot
& (Join-Path $PayloadRoot "cancheria.exe") --self-test
if ($LASTEXITCODE -ne 0) { throw "Falló el self-test del cancheria.exe limpio" }
& (Join-Path $PayloadRoot "configurador_cancheria.exe") --self-test
if ($LASTEXITCODE -ne 0) { throw "Falló el self-test del configurador limpio" }
& (Join-Path $PayloadRoot "CancheriaUpdater.exe") --self-test
if ($LASTEXITCODE -ne 0) { throw "Falló el self-test de CancheriaUpdater.exe" }
$PayloadSelfTestBuild = Join-Path $PayloadRoot "build"
if (Test-Path -LiteralPath $PayloadSelfTestBuild) {
    Remove-Item -LiteralPath $PayloadSelfTestBuild -Recurse -Force
}
# Import-based self-tests may create bytecode caches in the external source
# tree.  They are build artifacts, not installation inputs.
Get-ChildItem -LiteralPath $PayloadRoot -Directory -Filter "__pycache__" -Recurse -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $PayloadRoot -File -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -in @(".pyc", ".pyo") } |
    Remove-Item -Force
Get-ChildItem -LiteralPath (Join-Path $PayloadRoot "src") -Directory -Filter "*.egg-info" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force

$IsccCandidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)
$Iscc = $IsccCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $Iscc) {
    throw "No se encontró ISCC.exe. Instalá Inno Setup 6 para compilar el instalador."
}

& $Iscc (Join-Path $Root "installer\cancheria.iss")
if ($LASTEXITCODE -ne 0) { throw "Falló Inno Setup" }

$Installer = Join-Path $Root "release\InstaladorCancheria.exe"
if (-not (Test-Path -LiteralPath $Installer -PathType Leaf)) {
    throw "Inno Setup terminó sin crear $Installer"
}
$Hash = (Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash
& $BuildPython (Join-Path $Root "scripts\build_update_packages.py") `
    --payload $PayloadRoot --platform windows --version "0.2.23"
if ($LASTEXITCODE -ne 0) { throw "Falló la creación del paquete de actualización Windows" }
Write-Output "INSTALLER=$Installer"
Write-Output "SHA256=$Hash"

