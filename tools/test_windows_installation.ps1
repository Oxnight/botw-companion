param(
    [string]$InstallerPath = "dist\installer\BOTW_Companion_0.40.0-alpha.23_Setup.exe"
)

$ErrorActionPreference = "Stop"

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    Write-Error "Ce test d'installation doit être exécuté sous Windows."
    exit 1
}

$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$resolvedInstaller = Join-Path $projectRoot $InstallerPath
$temporaryRoot = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { [IO.Path]::GetTempPath() }
$testRoot = Join-Path $temporaryRoot "BOTW Companion installation test"
$installRoot = Join-Path $testRoot "Programme autonome"
$dataRoot = Join-Path $testRoot "Données utilisateur"
$sentinel = Join-Path $dataRoot "donnees-a-conserver.json"
$expectedVersion = "0.40.0a23"
$testPort = 18766

if (-not (Test-Path -LiteralPath $resolvedInstaller -PathType Leaf)) {
    Write-Error "Installateur introuvable : $resolvedInstaller"
    exit 1
}

New-Item -ItemType Directory -Force -Path $dataRoot | Out-Null
Set-Content -LiteralPath $sentinel -Value '{"preserver":true}' -Encoding ASCII -NoNewline

$installArguments = @(
    "/VERYSILENT",
    "/SUPPRESSMSGBOXES",
    "/NORESTART",
    "/SP-",
    "/DIR=`"$installRoot`""
)
$installer = Start-Process -FilePath $resolvedInstaller -ArgumentList $installArguments -Wait -PassThru
if ($installer.ExitCode -ne 0) {
    Write-Error "Installation silencieuse échouée avec le code $($installer.ExitCode)."
    exit $installer.ExitCode
}

$application = Join-Path $installRoot "BOTW Companion.exe"
$uninstaller = Join-Path $installRoot "unins000.exe"
$dsuRoot = Join-Path $installRoot "_internal\botw_companion\dsu\windows"
$dsuExecutable = Join-Path $dsuRoot "JoyConDSU.exe"
$sdlLibrary = Join-Path $dsuRoot "SDL3.dll"
$dsuManifest = Join-Path $dsuRoot "manifest.json"
$sdlLicense = Join-Path $dsuRoot "SDL3-LICENSE.txt"
$desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "BOTW Companion.lnk"
$startMenuShortcut = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\BOTW Companion\BOTW Companion.lnk"
foreach ($required in @(
    $application,
    $uninstaller,
    $dsuExecutable,
    $sdlLibrary,
    $dsuManifest,
    $sdlLicense,
    $desktopShortcut,
    $startMenuShortcut
)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        Write-Error "Installation incomplète : $required"
        exit 1
    }
}

$originalPath = $env:PATH
$originalDataRoot = $env:BOTW_COMPANION_DATA_DIR
$server = $null
try {
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    $env:BOTW_COMPANION_DATA_DIR = $dataRoot
    $selfTest = Start-Process -FilePath $application -ArgumentList "--package-self-test" -Wait -PassThru -NoNewWindow
    if ($selfTest.ExitCode -ne 0) {
        Write-Error "L'application installée dépend encore d'un outil de développement externe."
        exit $selfTest.ExitCode
    }

    & $dsuExecutable --list-controllers | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Le moteur JoyConDSU installé ne charge pas SDL3 de manière autonome."
        exit $LASTEXITCODE
    }

    $server = Start-Process -FilePath $application -ArgumentList @(
        "--server",
        "--port",
        "$testPort"
    ) -PassThru
    $identity = $null
    for ($attempt = 0; $attempt -lt 120; $attempt++) {
        if ($server.HasExited) {
            Write-Error "Le serveur installé s'est arrêté avant de répondre."
            exit 1
        }
        try {
            $identity = Invoke-RestMethod `
                -Uri "http://127.0.0.1:$testPort/api/version" `
                -TimeoutSec 1
            break
        } catch {
            Start-Sleep -Milliseconds 250
        }
    }
    if (-not $identity -or
        $identity.application -ne "BOTW Companion" -or
        $identity.version -ne $expectedVersion) {
        Write-Error "Le serveur installé n'expose pas l'identité attendue."
        exit 1
    }
    Invoke-RestMethod `
        -Method Post `
        -Uri "http://127.0.0.1:$testPort/api/shutdown" `
        -TimeoutSec 2 | Out-Null
    if (-not $server.WaitForExit(10000)) {
        $server.Kill()
        Write-Error "Le serveur installé ne s'arrête pas proprement."
        exit 1
    }
} finally {
    if ($server -and -not $server.HasExited) {
        $server.Kill()
        $server.WaitForExit()
    }
    $env:PATH = $originalPath
    $env:BOTW_COMPANION_DATA_DIR = $originalDataRoot
}

$uninstall = Start-Process -FilePath $uninstaller -ArgumentList @(
    "/VERYSILENT",
    "/SUPPRESSMSGBOXES",
    "/NORESTART"
) -Wait -PassThru
if ($uninstall.ExitCode -ne 0) {
    Write-Error "Désinstallation silencieuse échouée avec le code $($uninstall.ExitCode)."
    exit $uninstall.ExitCode
}

if (Test-Path -LiteralPath $application) {
    Write-Error "L'exécutable est encore présent après désinstallation."
    exit 1
}
if (-not (Test-Path -LiteralPath $sentinel -PathType Leaf)) {
    Write-Error "La désinstallation a supprimé les données personnelles."
    exit 1
}

Write-Host "Installation, raccourcis, runtime Python, serveur et DSU autonomes validés." -ForegroundColor Green
