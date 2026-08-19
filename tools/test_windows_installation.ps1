param(
    [string]$InstallerPath = "dist\installer\BOTW_Companion_0.40.0-alpha.15_Setup.exe"
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
foreach ($required in @($application, $uninstaller)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        Write-Error "Installation incomplète : $required"
        exit 1
    }
}

$originalPath = $env:PATH
$originalDataRoot = $env:BOTW_COMPANION_DATA_DIR
try {
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    $env:BOTW_COMPANION_DATA_DIR = $dataRoot
    $selfTest = Start-Process -FilePath $application -ArgumentList "--package-self-test" -Wait -PassThru -NoNewWindow
    if ($selfTest.ExitCode -ne 0) {
        Write-Error "L'application installée dépend encore d'un outil de développement externe."
        exit $selfTest.ExitCode
    }
} finally {
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

Write-Host "Installation autonome sans privilèges et conservation des données validées." -ForegroundColor Green