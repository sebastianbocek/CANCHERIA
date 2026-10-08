param(
    [Parameter(Mandatory = $true)]
    [string]$InstallDir,

    [Parameter(Mandatory = $true)]
    [string]$BackupDir,

    [string]$ResultFile = ""
)

$ErrorActionPreference = "Stop"

function Copy-BackupItem {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RelativePath
    )

    $source = Join-Path $script:InstallRoot $RelativePath
    if (-not (Test-Path -LiteralPath $source)) {
        return
    }
    $destination = Join-Path $script:StageRoot $RelativePath
    $destinationParent = Split-Path -Parent $destination
    if ($destinationParent) {
        New-Item -ItemType Directory -Path $destinationParent -Force | Out-Null
    }
    Copy-Item -LiteralPath $source -Destination $destination -Recurse -Force
}

try {
    $InstallRoot = (Resolve-Path -LiteralPath $InstallDir).Path
    $BackupRoot = [System.IO.Path]::GetFullPath($BackupDir)
    New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null

    $tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
    $StageRoot = Join-Path $tempRoot ("CANCHERIA_UPDATE_BACKUP_" + [guid]::NewGuid().ToString("N"))
    if (-not $StageRoot.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "El staging del respaldo quedó fuera de la carpeta temporal."
    }
    New-Item -ItemType Directory -Path $StageRoot -Force | Out-Null

    $backupItems = @(
        "config.py",
        "config_backups",
        "src\cancheria\config\legacy_config.py",
        "src\cancheria\config\config_backups",
        "runtime",
        "wa_profile",
        "sessions",
        "audios",
        "comprobantes",
        "torneos",
        "agent_learning",
        ".env",
        "blacklist_numbers.json",
        "bot_state.pkl",
        "business_events.json",
        "calendar_events.db",
        "calendario_turnos.csv",
        "calendario_turnos.csv.reservation_id.seq",
        "client_memory.json",
        "conversation_log.jsonl",
        "conversation_states.json",
        "human_cases.json",
        "operations_metrics.jsonl",
        "proactive_state.json",
        "reservas_contactos.csv",
        "selector_adaptation_cache.json",
        "selector_health_history.json",
        "turnos_terminados.csv"
    )
    foreach ($item in $backupItems) {
        Copy-BackupItem -RelativePath $item
    }

    # Los caches del navegador no son necesarios para recuperar la sesión y
    # pueden multiplicar innecesariamente el tamaño de cada respaldo.
    $profileStage = Join-Path $StageRoot "wa_profile"
    if (Test-Path -LiteralPath $profileStage -PathType Container) {
        $cacheNames = @(
            "Cache", "Code Cache", "GPUCache", "DawnCache",
            "GrShaderCache", "ShaderCache", "Crashpad"
        )
        Get-ChildItem -LiteralPath $profileStage -Directory -Recurse -Force -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -in $cacheNames } |
            Sort-Object { $_.FullName.Length } -Descending |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    }

    $createdAt = Get-Date
    $info = @(
        "CANCHERIA - Respaldo automático antes de actualizar",
        "Fecha: $($createdAt.ToString('yyyy-MM-dd HH:mm:ss'))",
        "Instalación original: $InstallRoot",
        "",
        "Este ZIP contiene configuración y datos privados del cliente.",
        "No debe compartirse públicamente."
    )
    Set-Content -LiteralPath (Join-Path $StageRoot "LEEME_RESPALDO.txt") -Value $info -Encoding UTF8

    # ZIP no admite timestamps anteriores a 1980 ni posteriores a 2107.
    # Normalizamos sólo la copia temporal; los datos originales del cliente no
    # se modifican.
    $zipMinimumDate = [DateTime]::SpecifyKind([DateTime]::Parse("1980-01-01T00:00:00"), [DateTimeKind]::Utc)
    $zipMaximumDate = [DateTime]::SpecifyKind([DateTime]::Parse("2107-12-31T23:59:58"), [DateTimeKind]::Utc)
    Get-ChildItem -LiteralPath $StageRoot -File -Recurse -Force | ForEach-Object {
        if ($_.LastWriteTimeUtc -lt $zipMinimumDate) {
            $_.LastWriteTimeUtc = $zipMinimumDate
        }
        elseif ($_.LastWriteTimeUtc -gt $zipMaximumDate) {
            $_.LastWriteTimeUtc = $zipMaximumDate
        }
    }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $timestamp = $createdAt.ToString("yyyyMMdd_HHmmss_fff")
    $zipPath = Join-Path $BackupRoot "CANCHERIA_BACKUP_ANTES_ACTUALIZAR_$timestamp.zip"
    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $StageRoot,
        $zipPath,
        [System.IO.Compression.CompressionLevel]::Optimal,
        $false
    )
    if (-not (Test-Path -LiteralPath $zipPath -PathType Leaf)) {
        throw "No se creó el archivo ZIP esperado."
    }
    if ($ResultFile) {
        Set-Content -LiteralPath $ResultFile -Value $zipPath -Encoding UTF8
    }
    Write-Output $zipPath
    exit 0
}
catch {
    Write-Error "No se pudo crear el respaldo automático: $($_.Exception.Message)"
    exit 1
}
finally {
    if ($StageRoot -and
        (Test-Path -LiteralPath $StageRoot) -and
        $StageRoot.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase) -and
        ([System.IO.Path]::GetFileName($StageRoot) -like "CANCHERIA_UPDATE_BACKUP_*")) {
        Remove-Item -LiteralPath $StageRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
