$ErrorActionPreference = "Stop"

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    Write-Error "Cet installeur doit être exécuté sous Windows 10 ou Windows 11."
    exit 1
}

$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDirectory
$projectManifest = Join-Path $projectRoot "pyproject.toml"
$packageDirectory = Join-Path $projectRoot "botw_companion"

if (-not (Test-Path -LiteralPath $projectManifest -PathType Leaf) -or
    -not (Test-Path -LiteralPath $packageDirectory -PathType Container)) {
    Write-Error "Le clone BOTW Companion est incomplet ou l'installeur n'est plus dans son dossier windows."
    exit 1
}

$pythonCandidates = @(
    (Join-Path $projectRoot "runtime\pythonw.exe"),
    (Join-Path $projectRoot "python\pythonw.exe"),
    (Join-Path $projectRoot ".venv\Scripts\pythonw.exe")
)
$pythonPath = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $pythonPath) {
    Write-Host "Python Windows est introuvable." -ForegroundColor Red
    Write-Host "Depuis PowerShell, exécute d'abord :"
    Write-Host "  py -3.12 -m venv .venv"
    Write-Host "  .\.venv\Scripts\python.exe -m pip install -e ."
    exit 1
}

$dataDirectory = Join-Path $env:LOCALAPPDATA "BOTW Companion"
$launcherDirectory = Join-Path $dataDirectory "Launcher"
$startMenuDirectory = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$desktopDirectory = [Environment]::GetFolderPath("Desktop")
$installedVbs = Join-Path $launcherDirectory "BOTW Companion.vbs"
$installedIcon = Join-Path $launcherDirectory "BOTW Companion.ico"
$configPath = Join-Path $dataDirectory "launcher.json"

New-Item -ItemType Directory -Force -Path $launcherDirectory | Out-Null
New-Item -ItemType Directory -Force -Path $startMenuDirectory | Out-Null
Copy-Item -LiteralPath (Join-Path $scriptDirectory "BOTW Companion.vbs") -Destination $installedVbs -Force
Copy-Item -LiteralPath (Join-Path $scriptDirectory "BOTW Companion.ico") -Destination $installedIcon -Force
[IO.File]::WriteAllText((Join-Path $launcherDirectory "project-root.txt"), $projectRoot, [Text.Encoding]::Unicode)

$configuration = if (Test-Path -LiteralPath $configPath -PathType Leaf) {
    Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
} else {
    [PSCustomObject]@{
        schema_version = 1
        project_root = $projectRoot
        port = 8765
        ryujinx_process_names = @("Ryujinx.exe", "Ryujinx.Ava.exe")
    }
}
if ($null -eq $configuration.PSObject.Properties["project_root"]) {
    $configuration | Add-Member -NotePropertyName project_root -NotePropertyValue $projectRoot
} else {
    $configuration.project_root = $projectRoot
}
$configuration | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $configPath -Encoding UTF8 -NoNewline

$wscript = Join-Path $env:WINDIR "System32\wscript.exe"
$shortcutHost = New-Object -ComObject WScript.Shell
foreach ($shortcutPath in @(
    (Join-Path $desktopDirectory "BOTW Companion.lnk"),
    (Join-Path $startMenuDirectory "BOTW Companion.lnk")
)) {
    $shortcut = $shortcutHost.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $wscript
    $shortcut.Arguments = '"' + $installedVbs + '"'
    $shortcut.WorkingDirectory = $projectRoot
    $shortcut.IconLocation = $installedIcon + ",0"
    $shortcut.Description = "BOTW Companion"
    $shortcut.Save()
}

Write-Host "BOTW Companion est installé." -ForegroundColor Green
Write-Host "Utilise le raccourci du Bureau ou du menu Démarrer."
Write-Host "Le clone doit rester à cet emplacement : $projectRoot"