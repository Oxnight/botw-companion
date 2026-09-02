param(
    [string]$Version = "6.7.3",
    [string]$ReleaseTag = "is-6_7_3"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    Write-Error "Inno Setup doit être installé sur un runner Windows."
    exit 1
}

$existingCandidates = @(
    (Get-Command ISCC.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) }
$existing = $existingCandidates | Select-Object -First 1
if ($existing) {
    $existingDirectory = Split-Path -Parent $existing
    if ($env:GITHUB_PATH) {
        $existingDirectory | Out-File -FilePath $env:GITHUB_PATH -Append -Encoding utf8
    }
    Write-Host "Inno Setup déjà disponible : $existing" -ForegroundColor Green
    exit 0
}

if (-not (Get-Command gh.exe -ErrorAction SilentlyContinue)) {
    Write-Error "GitHub CLI est requis pour télécharger et vérifier Inno Setup."
    exit 1
}

$temporaryRoot = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { [IO.Path]::GetTempPath() }
$downloadRoot = Join-Path $temporaryRoot "inno-setup-$Version"
$assetName = "innosetup-$Version.exe"
$installer = Join-Path $downloadRoot $assetName
New-Item -ItemType Directory -Force -Path $downloadRoot | Out-Null

& gh.exe release download $ReleaseTag `
    --repo "jrsoftware/issrc" `
    --pattern $assetName `
    --dir $downloadRoot `
    --clobber
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $installer -PathType Leaf)) {
    Write-Error "Téléchargement officiel d'Inno Setup impossible."
    exit 1
}

& gh.exe release verify-asset $installer --repo "jrsoftware/issrc"
if ($LASTEXITCODE -ne 0) {
    Write-Error "L'attestation GitHub de l'installateur Inno Setup est invalide."
    exit 1
}

$signature = Get-AuthenticodeSignature -LiteralPath $installer
if ($signature.Status -ne [Management.Automation.SignatureStatus]::Valid -or
    $signature.SignerCertificate.Subject -notmatch "Pyrsys B\.V\.") {
    Write-Error "La signature Authenticode officielle d'Inno Setup est invalide."
    exit 1
}

$process = Start-Process -FilePath $installer -ArgumentList @(
    "/VERYSILENT",
    "/SUPPRESSMSGBOXES",
    "/NORESTART",
    "/SP-"
) -Wait -PassThru
if ($process.ExitCode -ne 0) {
    Write-Error "Installation d'Inno Setup échouée avec le code $($process.ExitCode)."
    exit $process.ExitCode
}

$candidates = @(
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf }
$compiler = $candidates | Select-Object -First 1
if (-not $compiler) {
    Write-Error "ISCC.exe reste introuvable après l'installation."
    exit 1
}

$compilerDirectory = Split-Path -Parent $compiler
if ($env:GITHUB_PATH) {
    $compilerDirectory | Out-File -FilePath $env:GITHUB_PATH -Append -Encoding utf8
}
Write-Host "Inno Setup vérifié et installé : $compiler" -ForegroundColor Green
