param(
    [switch]$SkipNative,
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    Write-Error "Cette application doit être construite sous Windows 10 ou Windows 11."
    exit 1
}

$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$buildRoot = Join-Path $projectRoot "build\windows-package"
$environmentRoot = Join-Path $buildRoot "venv"
$environmentPython = Join-Path $environmentRoot "Scripts\python.exe"
$specPath = Join-Path $projectRoot "windows\BOTW Companion.spec"
$applicationDirectory = Join-Path $projectRoot "dist\BOTW Companion"
$applicationExecutable = Join-Path $applicationDirectory "BOTW Companion.exe"
$installerDirectory = Join-Path $projectRoot "dist\installer"
$installerPath = Join-Path $installerDirectory "BOTW_Companion_0.40.0-alpha.20_Setup.exe"

if (-not $SkipNative) {
    & (Join-Path $projectRoot "tools\build_joycon_dsu_windows.ps1")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$dsuDirectory = Join-Path $projectRoot "botw_companion\dsu\windows"
foreach ($required in @("JoyConDSU.exe", "SDL3.dll", "manifest.json")) {
    if (-not (Test-Path -LiteralPath (Join-Path $dsuDirectory $required) -PathType Leaf)) {
        Write-Error "Ressource native manquante : $required"
        exit 1
    }
}

$bootstrapPython = Get-Command python.exe -ErrorAction SilentlyContinue
if (-not (Test-Path -LiteralPath $environmentPython -PathType Leaf)) {
    if ($bootstrapPython) {
        & $bootstrapPython.Source -m venv $environmentRoot
    } else {
        $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
        if (-not $launcher) {
            Write-Error "Python 3.12 est requis uniquement pour construire le paquet."
            exit 1
        }
        & $launcher.Source -3.12 -m venv $environmentRoot
    }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if (-not (Test-Path -LiteralPath $environmentPython -PathType Leaf)) {
    Write-Error "L'environnement de construction Python n'a pas été créé."
    exit 1
}

& $environmentPython -m pip install --disable-pip-version-check --quiet "pyinstaller==6.16.0"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Push-Location $projectRoot
try {
    & $environmentPython -m PyInstaller --noconfirm --clean $specPath
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}

foreach ($required in @(
    $applicationExecutable,
    (Join-Path $applicationDirectory "_internal\botw_companion\dsu\windows\JoyConDSU.exe"),
    (Join-Path $applicationDirectory "_internal\botw_companion\dsu\windows\SDL3.dll"),
    (Join-Path $applicationDirectory "_internal\botw_companion\data\catalog_fr_compiled.json"),
    (Join-Path $applicationDirectory "_internal\botw_companion\data\cartography_reference_fr_compiled.json"),
    (Join-Path $applicationDirectory "_internal\botw_companion\data\korok_reference.json"),
    (Join-Path $applicationDirectory "_internal\botw_companion\web\index.html"),
    (Join-Path $applicationDirectory "_internal\botw_companion\web\hyrule-map.webp")
)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        Write-Error "Paquet incomplet : $required"
        exit 1
    }
}

& $applicationExecutable --package-self-test
if ($LASTEXITCODE -ne 0) {
    Write-Error "L'auto-test du paquet Windows a échoué."
    exit $LASTEXITCODE
}

if (-not $SkipInstaller) {
    $isccCandidates = @(
        (Get-Command ISCC.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) }
    $iscc = $isccCandidates | Select-Object -First 1
    if (-not $iscc) {
        Write-Error "Inno Setup 6 est requis pour produire l'installateur."
        exit 1
    }
    & $iscc (Join-Path $projectRoot "windows\BOTW Companion.iss")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if (-not (Test-Path -LiteralPath $installerPath -PathType Leaf)) {
        Write-Error "L'installateur Windows n'a pas été produit."
        exit 1
    }
}

Write-Host "Application autonome : $applicationDirectory" -ForegroundColor Green
if (-not $SkipInstaller) {
    Write-Host "Installateur : $installerPath" -ForegroundColor Green
}