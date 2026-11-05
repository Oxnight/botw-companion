param(
    [string]$InstallerPath = "",
    [string]$PreviousInstallerPath = "",
    [switch]$InteractiveAssistedUpdate
)

$ErrorActionPreference = "Stop"

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw "Ce test d'installation doit être exécuté sous Windows."
}

$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$temporaryRoot = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { [IO.Path]::GetTempPath() }
$testRoot = Join-Path $temporaryRoot "BOTW Companion installation test $([guid]::NewGuid())"
$uninstallSubkey = "Software\Microsoft\Windows\CurrentVersion\Uninstall\{CE150634-F42B-4815-BE57-F0729FC71365}_is1"
$desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "BOTW Companion.lnk"
$startMenuShortcut = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\BOTW Companion\BOTW Companion.lnk"
$metadata = (& python (Join-Path $projectRoot "tools\release_metadata.py") | ConvertFrom-Json)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if (-not $InstallerPath) {
    $InstallerPath = Join-Path "dist\installer" $metadata.installer_name
}
$expectedVersion = $metadata.pep440_version

function Resolve-TestPath([string]$Path) {
    if ([IO.Path]::IsPathRooted($Path)) { return $Path }
    return Join-Path $projectRoot $Path
}

function Assert-CleanTestAccount {
    # /DIR does not isolate Inno's AppId registration or per-user shortcuts.
    foreach ($hive in @([Microsoft.Win32.RegistryHive]::CurrentUser, [Microsoft.Win32.RegistryHive]::LocalMachine)) {
        foreach ($view in @([Microsoft.Win32.RegistryView]::Registry32, [Microsoft.Win32.RegistryView]::Registry64)) {
            $registry = [Microsoft.Win32.RegistryKey]::OpenBaseKey($hive, $view)
            try {
                $key = $registry.OpenSubKey($uninstallSubkey)
                if ($key) {
                    $key.Dispose()
                    throw "Use a disposable Windows account without an existing BOTW Companion installation."
                }
            } finally { $registry.Dispose() }
        }
    }
    foreach ($shortcut in @($desktopShortcut, $startMenuShortcut)) {
        if (Test-Path -LiteralPath $shortcut) { throw "Existing shortcut must remain untouched: $shortcut" }
    }
    if (Get-Process -Name "BOTW Companion", "BOTW Companion Updater" -ErrorAction SilentlyContinue) {
        throw "Use a disposable Windows account with no running BOTW Companion processes."
    }
}

function Assert-InstallerLanguage([string]$InstallRoot, [string]$Language) {
    $registration = Get-ItemProperty -LiteralPath "HKCU:\$uninstallSubkey"
    if ($registration.'Inno Setup: Language' -ne $Language -or
        $registration.DisplayVersion -ne $metadata.display_version -or
        [IO.Path]::GetFullPath($registration.'Inno Setup: App Path') -ne [IO.Path]::GetFullPath($InstallRoot)) {
        throw "Installed language/path/version mismatch: expected $Language in $InstallRoot; recorded language $($registration.'Inno Setup: Language')."
    }
    Write-Host "Inno Setup recorded language: $Language"
}

function Assert-InstalledShortcuts([string]$InstallRoot) {
    foreach ($shortcut in @($desktopShortcut, $startMenuShortcut)) {
        if (-not (Test-Path -LiteralPath $shortcut -PathType Leaf)) {
            throw "Raccourci absent après mise à niveau : $shortcut"
        }
        $target = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcut).TargetPath
        if ([IO.Path]::GetFullPath($target) -ne [IO.Path]::GetFullPath((Join-Path $InstallRoot "BOTW Companion.exe"))) {
            throw "Le raccourci ne cible pas l'application mise à niveau : $shortcut"
        }
    }
}

function Assert-PreservedData([string]$DataRoot, [hashtable]$Hashes) {
    foreach ($name in $Hashes.Keys) {
        $path = Join-Path $DataRoot $name
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or
            (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $Hashes[$name]) {
            throw "Synthetic data changed or disappeared: $name"
        }
    }
}

function Start-ApplicationObservation {
    $source = "BOTW-installation-$([guid]::NewGuid())"
    Register-CimIndicationEvent -Namespace root/cimv2 -SourceIdentifier $source -OperationTimeoutSec 10 `
        -Query "SELECT * FROM Win32_ProcessStartTrace WHERE ProcessName = 'BOTW Companion.exe' OR ProcessName = 'BOTW Companion Updater.exe'" | Out-Null
    return $source
}

function Test-ApplicationLineage([object[]]$Processes, [int]$ExpectedCount, [int]$ParentProcessId = 0) {
    $applications = @($Processes | Where-Object { $_.name -eq "BOTW Companion.exe" })
    if ($ExpectedCount -notin @(0, 1) -or $applications.Count -ne $ExpectedCount) { return $false }
    $byId = @{}
    foreach ($process in $Processes) {
        $processId = [long]$process.id
        if ($processId -le 0 -or $byId.ContainsKey($processId) -or
            $process.name -notin @("BOTW Companion.exe", "BOTW Companion Updater.exe")) { return $false }
        $byId[$processId] = $process
    }
    # Index the complete observation before walking any ancestry.
    foreach ($process in $Processes) {
        $seen = @{}
        $ancestor = [long]$process.id
        while ($byId.ContainsKey($ancestor)) {
            if ($seen.ContainsKey($ancestor)) { return $false }
            $seen[$ancestor] = $true
            $ancestor = [long]$byId[$ancestor].parent_id
        }
    }
    if ($ExpectedCount -eq 0) { return $true }
    if (-not $byId.ContainsKey([long]$ParentProcessId) -or
        $byId[[long]$ParentProcessId].name -ne "BOTW Companion Updater.exe") { return $false }
    foreach ($process in $Processes) {
        $ancestor = if ($process.name -eq "BOTW Companion.exe") { [long]$process.parent_id } else { [long]$process.id }
        while ($ancestor -ne $ParentProcessId) {
            if (-not $byId.ContainsKey($ancestor) -or
                $byId[$ancestor].name -ne "BOTW Companion Updater.exe") { return $false }
            $ancestor = [long]$byId[$ancestor].parent_id
        }
    }
    return $true
}

function Assert-ApplicationLaunches([string]$Source, [int]$ExpectedCount, [int]$ParentProcessId = 0) {
    $launches = @()
    $drain = [Diagnostics.Stopwatch]::StartNew()
    # Drain asynchronous process notifications after the installer/relay exits.
    while ($drain.ElapsedMilliseconds -lt 1000) {
        Wait-Event -SourceIdentifier $Source -Timeout 1 | Out-Null
        foreach ($event in @(Get-Event -SourceIdentifier $Source -ErrorAction SilentlyContinue)) {
            $started = $event.SourceEventArgs.NewEvent
            if (-not $started) { throw "Process-start observation failed: $($event.SourceEventArgs)" }
            $launches += [ordered]@{ name = $started.ProcessName; id = $started.ProcessID; parent_id = $started.ParentProcessID }
            Remove-Event -EventIdentifier $event.EventIdentifier
        }
    }
    ConvertTo-Json -InputObject @($launches) | Set-Content (Join-Path $testRoot "$Source.json") -Encoding UTF8
    if (-not (Test-ApplicationLineage $launches $ExpectedCount $ParentProcessId)) {
        throw "Unexpected application launches: expected $ExpectedCount from parent $ParentProcessId; observed $($launches | ConvertTo-Json -Compress -AsArray)."
    }
}

function Stop-ApplicationObservation([string]$Source) {
    Unregister-Event -SourceIdentifier $Source
    Get-Event -SourceIdentifier $Source -ErrorAction SilentlyContinue | Remove-Event
}

function Invoke-Installer([string]$Path, [string[]]$ExtraArguments, [string]$DataRoot,
                          [switch]$Interactive) {
    if (-not $DataRoot -or -not [IO.Path]::GetFullPath($DataRoot).StartsWith(
        "$testRoot$([IO.Path]::DirectorySeparatorChar)", [StringComparison]::OrdinalIgnoreCase)) {
        throw "Installer validation requires data inside its owned temporary directory."
    }
    $arguments = @("/NORESTART", "/SP-") + $ExtraArguments
    if (-not $Interactive) { $arguments += @("/VERYSILENT", "/SUPPRESSMSGBOXES") }
    $originalDataRoot = $env:BOTW_COMPANION_DATA_DIR
    $observation = Start-ApplicationObservation
    $process = $null
    try {
        # An unexpected launch must inherit synthetic data, never the user's data.
        $env:BOTW_COMPANION_DATA_DIR = $DataRoot
        $process = Start-Process -FilePath $Path -ArgumentList $arguments -PassThru
        if (-not $process.WaitForExit(120000)) {
            $process.Kill($true)
            $process.WaitForExit()
            throw "Installer validation exceeded its deadline."
        }
        if ($process.ExitCode -ne 0) {
            throw "Installation silencieuse échouée avec le code $($process.ExitCode) : $Path"
        }
        Assert-ApplicationLaunches $observation 0
    } finally {
        if ($process) { $process.Dispose() }
        $env:BOTW_COMPANION_DATA_DIR = $originalDataRoot
        Stop-ApplicationObservation $observation
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

function Invoke-ExactProcess([string]$Path, [string[]]$Arguments,
                             [string]$WorkingDirectory, [int]$TimeoutMilliseconds) {
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $Path
    $startInfo.WorkingDirectory = $WorkingDirectory
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    foreach ($argument in $Arguments) {
        $startInfo.ArgumentList.Add($argument)
    }
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    try {
        if (-not $process.Start()) {
            throw "Le processus de validation n'a pas pu démarrer : $Path"
        }
        if (-not $process.WaitForExit($TimeoutMilliseconds)) {
            $process.Kill($true)
            $process.WaitForExit()
            throw "Le processus de validation a dépassé le délai autorisé : $Path"
        }
        return [pscustomobject]@{ ExitCode = $process.ExitCode; Id = $process.Id }
    } finally {
        $process.Dispose()
    }
}

function Assert-InstalledLayout([string]$InstallRoot) {
    $required = @(
        (Join-Path $InstallRoot "BOTW Companion.exe"),
        (Join-Path $InstallRoot "BOTW Companion Updater.exe"),
        (Join-Path $InstallRoot "unins000.exe"),
        (Join-Path $InstallRoot "_internal\botw_companion\dsu\windows\JoyConDSU.exe"),
        (Join-Path $InstallRoot "_internal\botw_companion\dsu\windows\SDL3.dll"),
        (Join-Path $InstallRoot "_internal\botw_companion\dsu\windows\manifest.json"),
        (Join-Path $InstallRoot "_internal\botw_companion\dsu\windows\SDL3-LICENSE.txt"),
        (Join-Path $InstallRoot "_internal\botw_companion\data\localization_fr.json"),
        (Join-Path $InstallRoot "_internal\botw_companion\data\nomenclature_fr_reference.json"),
        (Join-Path $InstallRoot "LICENSE"),
        (Join-Path $InstallRoot "THIRD_PARTY_NOTICES.md"),
        (Join-Path $InstallRoot "DATA_SOURCES.md"),
        (Join-Path $InstallRoot "PRIVACY.md"),
        (Join-Path $InstallRoot "SECURITY.md"),
        (Join-Path $InstallRoot "licenses\PYTHON-3.12.txt"),
        (Join-Path $InstallRoot "licenses\SDL3-3.4.14.txt"),
        (Join-Path $InstallRoot "licenses\CERTIFI-MPL-2.0.txt")
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
            "--server", "--port", "$Port", "--sans-navigateur", "--arreter-avec-ryujinx"
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
            $entry = $manual.entries.PSObject.Properties["korogus:reference"].Value
            $session = $routes.sessions.PSObject.Properties["session-reference"].Value
            if (-not $entry.completed -or $entry.note -ne "Conservé depuis la version précédente" -or
                $routes.active_session_id -ne "session-reference" -or
                $session.entries[0].tracking_id -ne "sanctuaires:reference" -or
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

function Test-AssistedUpdate([string]$InstallRoot, [string]$DataRoot,
                              [string]$SourceInstaller, [int]$Port) {
    $application = Join-Path $InstallRoot "BOTW Companion.exe"
    $installedUpdater = Join-Path $InstallRoot "BOTW Companion Updater.exe"
    $updateRoot = Join-Path $DataRoot "updates"
    $installer = Join-Path $updateRoot $metadata.installer_name
    $installerMetadata = "$installer.metadata.json"
    $log = Join-Path $updateRoot "logs\assisted-update.log"
    New-Item -ItemType Directory -Force -Path $updateRoot | Out-Null
    $relayDirectory = Join-Path $updateRoot "relay\ci-validation"
    New-Item -ItemType Directory -Force -Path $relayDirectory | Out-Null
    $updater = Join-Path $relayDirectory "BOTW Companion Updater.exe"
    Copy-Item -LiteralPath $installedUpdater -Destination $updater -Force
    Copy-Item -LiteralPath $SourceInstaller -Destination $installer -Force
    [ordered]@{ port = $Port } | ConvertTo-Json | Set-Content `
        (Join-Path $DataRoot "launcher.json") -Encoding UTF8
    $digest = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
    $size = (Get-Item -LiteralPath $installer).Length
    $releaseUrl = "https://github.com/Oxnight/botw-companion/releases/tag/$($metadata.tag)"
    $downloadUrl = (
        "https://github.com/Oxnight/botw-companion/releases/download/" +
        "$($metadata.tag)/$($metadata.installer_name)"
    )
    [ordered]@{
        schema_version = 1
        version = $metadata.display_version
        filename = $metadata.installer_name
        url = $downloadUrl
        size = $size
        digest = "sha256:$digest"
        etag = $null
        last_modified = $null
        ready = $true
    } | ConvertTo-Json -Compress | Set-Content `
        -LiteralPath $installerMetadata -Encoding UTF8 -NoNewline
    $originalDataRoot = $env:BOTW_COMPANION_DATA_DIR
    $observation = $null
    try {
        $env:BOTW_COMPANION_DATA_DIR = $DataRoot
        $updaterArguments = @(
            "--root", $updateRoot,
            "--installer", $installer,
            "--metadata", $installerMetadata,
            "--version", $metadata.display_version,
            "--digest", $digest,
            "--size", "$size",
            "--parent-pid", "4294967294",
            "--application", $application,
            "--port", "$Port",
            "--log", $log,
            "--release-url", $releaseUrl,
            "--silent"
        )
        $observation = Start-ApplicationObservation
        $updaterProcess = Invoke-ExactProcess $updater $updaterArguments `
            $relayDirectory 120000
        $updaterExitCode = $updaterProcess.ExitCode
        if ($updaterExitCode -ne 0) {
            $failureStatePath = Join-Path $updateRoot "installation.json"
            $failureDetails = ""
            if (Test-Path -LiteralPath $failureStatePath -PathType Leaf) {
                $failureState = Get-Content -LiteralPath $failureStatePath -Raw | ConvertFrom-Json
                $failureDetails = " État : $($failureState.status). $($failureState.message)"
                if ($failureState.log_path -and
                    (Test-Path -LiteralPath $failureState.log_path -PathType Leaf)) {
                    Write-Host "----- Journal du relais de mise à jour -----"
                    Get-Content -LiteralPath $failureState.log_path -Raw | Write-Host
                    Write-Host "----- Fin du journal du relais -----"
                }
            }
            throw "Le relais de mise à jour a échoué avec le code $updaterExitCode.$failureDetails"
        }
        $state = Get-Content -LiteralPath (Join-Path $updateRoot "installation.json") `
            -Raw | ConvertFrom-Json
        if ($state.status -ne "succeeded" -or (Test-Path -LiteralPath $installer) -or
            (Test-Path -LiteralPath $installerMetadata)) {
            throw "Le relais n'a pas validé le redémarrage ou nettoyé le paquet."
        }
        $identity = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/version" -TimeoutSec 2
        if ($identity.version -ne $expectedVersion) {
            throw "La version relancée après mise à jour n'est pas celle attendue."
        }
        Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$Port/api/shutdown" `
            -Headers @{ "X-BOTW-Session-Token" = $identity.session_token } -TimeoutSec 2 | Out-Null
        $stopped = $false
        for ($attempt = 0; $attempt -lt 100; $attempt++) {
            try {
                Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/version" -TimeoutSec 1 | Out-Null
            } catch {
                $stopped = $true
                break
            }
            Start-Sleep -Milliseconds 100
        }
        if (-not $stopped) {
            throw "La version relancée ne s'est pas arrêtée proprement après le test."
        }
        # The onefile updater relaunches the app from a bootloader child.
        Assert-ApplicationLaunches $observation 1 $updaterProcess.Id
    } finally {
        $env:BOTW_COMPANION_DATA_DIR = $originalDataRoot
        if ($observation) { Stop-ApplicationObservation $observation }
    }
}

$resolvedInstaller = Resolve-TestPath $InstallerPath
if (-not (Test-Path -LiteralPath $resolvedInstaller -PathType Leaf)) {
    throw "Installateur introuvable : $resolvedInstaller"
}
& (Join-Path $projectRoot "tests\windows_process_lineage.ps1")
Assert-CleanTestAccount
New-Item -ItemType Directory -Path $testRoot | Out-Null
Write-Host "Native installation diagnostics: $testRoot"

# Clean installation and complete self-containment.
foreach ($language in @("english", "french")) {
    $cleanInstallRoot = Join-Path $testRoot "Installation propre $language"
    $cleanDataRoot = Join-Path $testRoot "Données propres $language"
    New-Item -ItemType Directory -Force -Path $cleanDataRoot | Out-Null
    $cleanSentinel = Join-Path $cleanDataRoot "donnees-a-conserver.json"
    Set-Content -LiteralPath $cleanSentinel -Value '{"preserver":true}' -Encoding ASCII -NoNewline
    Invoke-Installer $resolvedInstaller @(
        "/LANG=$language", "/DIR=`"$cleanInstallRoot`"", "/TASKS=`"desktopicon`""
    ) $cleanDataRoot
    Assert-InstalledLayout $cleanInstallRoot
    Assert-InstallerLanguage $cleanInstallRoot $language
    Assert-InstalledShortcuts $cleanInstallRoot
    & python (Join-Path $projectRoot "tools\seed_installation_data.py") $cleanDataRoot
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $dataHashes = @{}
    foreach ($file in Get-ChildItem -LiteralPath $cleanDataRoot -File) {
        $dataHashes[$file.Name] = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
    }

    # Omit /LANG, /DIR and /TASKS to exercise Inno's previous choices.
    Invoke-Installer $resolvedInstaller @() $cleanDataRoot
    Assert-InstallerLanguage $cleanInstallRoot $language
    Assert-InstalledShortcuts $cleanInstallRoot
    Assert-PreservedData $cleanDataRoot $dataHashes
    if ($InteractiveAssistedUpdate) {
        # Complete the visible wizard to test the guard independently of skipifsilent.
        Write-Host "Complete the $language assisted-update wizard within 120 seconds."
        Invoke-Installer $resolvedInstaller @("/ASSISTEDUPDATE=1") $cleanDataRoot -Interactive
        Assert-InstallerLanguage $cleanInstallRoot $language
        Assert-InstalledShortcuts $cleanInstallRoot
        Assert-PreservedData $cleanDataRoot $dataHashes
    }
    Test-InstalledRuntime $cleanInstallRoot $cleanDataRoot 18766 -ValidateUpgradeData
    Test-AssistedUpdate $cleanInstallRoot $cleanDataRoot $resolvedInstaller 18767
    Assert-InstallerLanguage $cleanInstallRoot $language
    Assert-InstalledShortcuts $cleanInstallRoot
    Assert-PreservedData $cleanDataRoot $dataHashes
    Invoke-Uninstaller (Join-Path $cleanInstallRoot "unins000.exe")
    if (Test-Path -LiteralPath (Join-Path $cleanInstallRoot "BOTW Companion.exe")) {
        throw "L'exécutable est encore présent après désinstallation."
    }
    Assert-PreservedData $cleanDataRoot $dataHashes
    Assert-CleanTestAccount
}

# A published stable package is mandatory after bootstrap. For the first stable
# release, exercise replacement and compatibility data using the built package.
if (-not $PreviousInstallerPath) {
    if ($metadata.installation_validation -ne "bootstrap") {
        throw "A published stable reference installer is required for upgrade validation."
    }
    $PreviousInstallerPath = $resolvedInstaller
    Write-Host "Bootstrap validation: replace the built package with itself and preserve compatibility data."
} else {
    Write-Host "Upgrade validation: replace the supplied stable reference installation."
}
if ($PreviousInstallerPath) {
    $resolvedPreviousInstaller = Resolve-TestPath $PreviousInstallerPath
    if (-not (Test-Path -LiteralPath $resolvedPreviousInstaller -PathType Leaf)) {
        throw "Installateur de référence introuvable : $resolvedPreviousInstaller"
    }
    $upgradeInstallRoot = Join-Path $testRoot "Installation mise à niveau"
    $upgradeDataRoot = Join-Path $testRoot "Données version précédente"
    New-Item -ItemType Directory -Force -Path $upgradeDataRoot | Out-Null
    Invoke-Installer $resolvedPreviousInstaller @(
        "/LANG=french", "/DIR=`"$upgradeInstallRoot`"", "/TASKS=`"desktopicon`""
    ) $upgradeDataRoot

    & python (Join-Path $projectRoot "tools\seed_installation_data.py") $upgradeDataRoot
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    # Every supported stable package includes the updater and must complete
    # an assisted transition before the installer recovery/reinstallation checks.
    Test-AssistedUpdate $upgradeInstallRoot $upgradeDataRoot $resolvedInstaller 18769
    Assert-InstallerLanguage $upgradeInstallRoot "french"

    # No /DIR or /TASKS: Inno must recover the installation and its choices.
    Invoke-Installer $resolvedInstaller @() $upgradeDataRoot
    Assert-InstalledLayout $upgradeInstallRoot
    Assert-InstallerLanguage $upgradeInstallRoot "french"
    Assert-InstalledShortcuts $upgradeInstallRoot
    Test-InstalledRuntime $upgradeInstallRoot $upgradeDataRoot 18768 -ValidateUpgradeData
    Invoke-Uninstaller (Join-Path $upgradeInstallRoot "unins000.exe")
    foreach ($name in @("manual_tracking.json", "route_sessions.json", "preferences.json", "export-reference.json")) {
        if (-not (Test-Path -LiteralPath (Join-Path $upgradeDataRoot $name) -PathType Leaf)) {
            throw "La désinstallation a supprimé une donnée de la version précédente : $name"
        }
    }
}

Write-Host "English/French installation, language retention, shortcuts, synthetic data, assisted restart, runtime and DSU validated." -ForegroundColor Green
