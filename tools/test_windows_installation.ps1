param(
    [string]$InstallerPath = "dist\installer\BOTW_Companion_0.40.0-alpha.29_Setup.exe",
    [string]$PreviousInstallerPath = ""
)

$ErrorActionPreference = "Stop"

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw "Ce test d'installation doit être exécuté sous Windows."
}

$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$temporaryRoot = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { [IO.Path]::GetTempPath() }
$testRoot = Join-Path $temporaryRoot "BOTW Companion installation test"
$expectedVersion = "0.40.0a29"

function Resolve-TestPath([string]$Path) {
    if ([IO.Path]::IsPathRooted($Path)) { return $Path }
    return Join-Path $projectRoot $Path
}

function Invoke-Installer([string]$Path, [string[]]$ExtraArguments = @()) {
    $arguments = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-") + $ExtraArguments
    $process = Start-Process -FilePath $Path -ArgumentList $arguments -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw "Installation silencieuse échouée avec le code $($process.ExitCode) : $Path"
    }
}

function Invoke-Uninstaller([string]$Path) {
    $process = Start-Process -FilePath $Path -ArgumentList @(
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"
    ) -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw "Désinstallation silencieuse échouée avec le code $($process.ExitCode)."
    }
}

function Assert-InstalledLayout([string]$InstallRoot) {
    $required = @(
        (Join-Path $InstallRoot "BOTW Companion.exe"),
        (Join-Path $InstallRoot "unins000.exe"),
        (Join-Path $InstallRoot "_internal\botw_companion\dsu\windows\JoyConDSU.exe"),
        (Join-Path $InstallRoot "_internal\botw_companion\dsu\windows\SDL3.dll"),
        (Join-Path $InstallRoot "_internal\botw_companion\dsu\windows\manifest.json"),
        (Join-Path $InstallRoot "_internal\botw_companion\dsu\windows\SDL3-LICENSE.txt"),
        (Join-Path $InstallRoot "_internal\botw_companion\data\localization_fr.json"),
        (Join-Path $InstallRoot "_internal\botw_companion\data\nomenclature_fr_reference.json"),
        (Join-Path $InstallRoot "LICENSE"),
        (Join-Path $InstallRoot "THIRD_PARTY_NOTICES.md")
    )
    foreach ($path in $required) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Installation incomplète : $path"
        }
    }
}

function Test-InstalledRuntime([string]$InstallRoot, [string]$DataRoot, [int]$Port,
                               [switch]$ValidateUpgradeData) {
    $application = Join-Path $InstallRoot "BOTW Companion.exe"
    $dsuExecutable = Join-Path $InstallRoot "_internal\botw_companion\dsu\windows\JoyConDSU.exe"
    $originalPath = $env:PATH
    $originalDataRoot = $env:BOTW_COMPANION_DATA_DIR
    $server = $null
    try {
        $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
        $env:BOTW_COMPANION_DATA_DIR = $DataRoot
        $selfTest = Start-Process -FilePath $application -ArgumentList "--package-self-test" -Wait -PassThru -NoNewWindow
        if ($selfTest.ExitCode -ne 0) {
            throw "L'application installée dépend encore d'un outil de développement externe."
        }
        & $dsuExecutable --list-controllers | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Le moteur JoyConDSU installé ne charge pas SDL3 de manière autonome."
        }

        $serverOutput = Join-Path $testRoot "server-$Port.stdout.log"
        $serverError = Join-Path $testRoot "server-$Port.stderr.log"
        $server = Start-Process -FilePath $application -ArgumentList @(
            "--server", "--port", "$Port"
        ) -WorkingDirectory $InstallRoot -RedirectStandardOutput $serverOutput `
            -RedirectStandardError $serverError -PassThru
        $identity = $null
        for ($attempt = 0; $attempt -lt 120; $attempt++) {
            if ($server.HasExited) {
                $diagnostics = @(
                    "Le serveur installé s'est arrêté avant de répondre (code $($server.ExitCode))."
                    "Sortie standard : $serverOutput"
                    "Sortie d'erreur : $serverError"
                ) -join [Environment]::NewLine
                throw $diagnostics
            }
            try {
                $identity = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/version" -TimeoutSec 1
                break
            } catch {
                Start-Sleep -Milliseconds 250
            }
        }
        if (-not $identity -or $identity.application -ne "BOTW Companion" -or
            $identity.version -ne $expectedVersion -or -not $identity.session_token) {
            throw "Le serveur installé n'expose pas l'identité attendue."
        }

        if ($ValidateUpgradeData) {
            $manual = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/manual" -TimeoutSec 2
            $routes = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/routes" -TimeoutSec 2
            $preferences = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/preferences" -TimeoutSec 2
            $entry = $manual.entries.PSObject.Properties["korogus:alpha24"].Value
            $session = $routes.sessions.PSObject.Properties["session-alpha24"].Value
            if (-not $entry.completed -or $entry.note -ne "Conservé depuis alpha.24" -or
                $routes.active_session_id -ne "session-alpha24" -or
                $session.entries[0].tracking_id -ne "sanctuaires:alpha24" -or
                -not $session.entries[0].locked -or
                $preferences.values.map_content_mode -ne "dlc" -or
                $preferences.values.dsu_mode -ne "integrated") {
                throw "La mise à niveau a altéré le suivi, les itinéraires ou les préférences."
            }
        }

        Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$Port/api/shutdown" `
            -Headers @{ "X-BOTW-Session-Token" = $identity.session_token } -TimeoutSec 2 | Out-Null
        if (-not $server.WaitForExit(10000)) {
            $server.Kill()
            throw "Le serveur installé ne s'arrête pas proprement."
        }
    } finally {
        if ($server -and -not $server.HasExited) { $server.Kill(); $server.WaitForExit() }
        $env:PATH = $originalPath
        $env:BOTW_COMPANION_DATA_DIR = $originalDataRoot
    }
}

$resolvedInstaller = Resolve-TestPath $InstallerPath
if (-not (Test-Path -LiteralPath $resolvedInstaller -PathType Leaf)) {
    throw "Installateur introuvable : $resolvedInstaller"
}
if (Test-Path -LiteralPath $testRoot) { Remove-Item -LiteralPath $testRoot -Recurse -Force }

# Installation propre et autonomie complète.
$cleanInstallRoot = Join-Path $testRoot "Installation propre"
$cleanDataRoot = Join-Path $testRoot "Données propres"
New-Item -ItemType Directory -Force -Path $cleanDataRoot | Out-Null
$cleanSentinel = Join-Path $cleanDataRoot "donnees-a-conserver.json"
Set-Content -LiteralPath $cleanSentinel -Value '{"preserver":true}' -Encoding ASCII -NoNewline
Invoke-Installer $resolvedInstaller @("/DIR=`"$cleanInstallRoot`"", "/TASKS=`"desktopicon`"")
Assert-InstalledLayout $cleanInstallRoot
Test-InstalledRuntime $cleanInstallRoot $cleanDataRoot 18766
Invoke-Uninstaller (Join-Path $cleanInstallRoot "unins000.exe")
if (Test-Path -LiteralPath (Join-Path $cleanInstallRoot "BOTW Companion.exe")) {
    throw "L'exécutable est encore présent après désinstallation."
}
if (-not (Test-Path -LiteralPath $cleanSentinel -PathType Leaf)) {
    throw "La désinstallation a supprimé les données personnelles."
}

# Mise à niveau réelle depuis le premier installateur macOS/Windows publié ensemble.
if ($PreviousInstallerPath) {
    $resolvedPreviousInstaller = Resolve-TestPath $PreviousInstallerPath
    if (-not (Test-Path -LiteralPath $resolvedPreviousInstaller -PathType Leaf)) {
        throw "Installateur alpha.24 introuvable : $resolvedPreviousInstaller"
    }
    $upgradeInstallRoot = Join-Path $testRoot "Installation mise à niveau"
    $upgradeDataRoot = Join-Path $testRoot "Données alpha.24"
    New-Item -ItemType Directory -Force -Path $upgradeDataRoot | Out-Null
    Invoke-Installer $resolvedPreviousInstaller @(
        "/DIR=`"$upgradeInstallRoot`"", "/TASKS=`"desktopicon`""
    )

    $timestamp = "2026-09-06T12:00:00+00:00"
    [ordered]@{
        schema_version = 2; revision = 7; updated_at = $timestamp
        entries = [ordered]@{
            "korogus:alpha24" = [ordered]@{
                completed = $true; note = "Conservé depuis alpha.24"; updated_at = $timestamp
            }
        }
    } | ConvertTo-Json -Depth 10 | Set-Content (Join-Path $upgradeDataRoot "manual_tracking.json") -Encoding UTF8
    [ordered]@{
        schema_version = 3; revision = 4; updated_at = $timestamp
        active_session_id = "session-alpha24"
        sessions = [ordered]@{
            "session-alpha24" = [ordered]@{
                id = "session-alpha24"; name = "Route conservée"; start = $null
                strategy = "region"; created_at = $timestamp; updated_at = $timestamp
                entries = @([ordered]@{
                    tracking_id = "sanctuaires:alpha24"; locked = $true
                    snapshot = [ordered]@{ name = "Sanctuaire conservé"; x = 12.5; z = -8.25 }
                })
            }
        }
    } | ConvertTo-Json -Depth 10 | Set-Content (Join-Path $upgradeDataRoot "route_sessions.json") -Encoding UTF8
    [ordered]@{
        schema_version = 1; revision = 3; updated_at = $timestamp
        values = [ordered]@{ map_content_mode = "dlc"; sync_interval = 15; dsu_mode = "integrated" }
    } | ConvertTo-Json -Depth 10 | Set-Content (Join-Path $upgradeDataRoot "preferences.json") -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $upgradeDataRoot "export-alpha24.json") `
        -Value '{"application":"BOTW Companion","schema_version":2,"origine":"alpha.24"}' `
        -Encoding UTF8 -NoNewline

    # Aucun /DIR ni /TASKS : Inno doit retrouver l'installation et les choix alpha.24.
    Invoke-Installer $resolvedInstaller
    Assert-InstalledLayout $upgradeInstallRoot
    $desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "BOTW Companion.lnk"
    $startMenuShortcut = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\BOTW Companion\BOTW Companion.lnk"
    foreach ($shortcut in @($desktopShortcut, $startMenuShortcut)) {
        if (-not (Test-Path -LiteralPath $shortcut -PathType Leaf)) {
            throw "Raccourci absent après mise à niveau : $shortcut"
        }
        $target = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcut).TargetPath
        if ([IO.Path]::GetFullPath($target) -ne [IO.Path]::GetFullPath((Join-Path $upgradeInstallRoot "BOTW Companion.exe"))) {
            throw "Le raccourci ne cible pas l'application mise à niveau : $shortcut"
        }
    }
    Test-InstalledRuntime $upgradeInstallRoot $upgradeDataRoot 18768 -ValidateUpgradeData
    Invoke-Uninstaller (Join-Path $upgradeInstallRoot "unins000.exe")
    foreach ($name in @("manual_tracking.json", "route_sessions.json", "preferences.json", "export-alpha24.json")) {
        if (-not (Test-Path -LiteralPath (Join-Path $upgradeDataRoot $name) -PathType Leaf)) {
            throw "La désinstallation a supprimé une donnée alpha.24 : $name"
        }
    }
}

Write-Host "Installation propre, mise à niveau alpha.24, raccourcis, données, runtime et DSU validés." -ForegroundColor Green
