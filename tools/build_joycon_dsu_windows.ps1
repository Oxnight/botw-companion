$ErrorActionPreference = "Stop"

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    Write-Error "Cette construction doit être exécutée sous Windows."
    exit 1
}

$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$sourceDirectory = Join-Path $projectRoot "third_party\JoyConDSU"
$buildDirectory = Join-Path $projectRoot "build\joycon-dsu-windows"
$outputDirectory = Join-Path $projectRoot "windows\native-dsu"
$packageDirectory = Join-Path $projectRoot "botw_companion\dsu\windows"

if (-not (Get-Command cmake.exe -ErrorAction SilentlyContinue)) {
    Write-Error "CMake est introuvable. Installe Visual Studio Build Tools avec CMake."
    exit 1
}

cmake.exe `
    -S $sourceDirectory `
    -B $buildDirectory `
    -A x64 `
    -DJOYCON_DSU_FETCH_SDL=ON
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

cmake.exe --build $buildDirectory --config Release --parallel
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$executable = Join-Path $buildDirectory "Release\JoyConDSU.exe"
$sdlLibrary = Join-Path $buildDirectory "Release\SDL3.dll"
if (-not (Test-Path -LiteralPath $executable -PathType Leaf) -or
    -not (Test-Path -LiteralPath $sdlLibrary -PathType Leaf)) {
    Write-Error "La construction n'a pas produit JoyConDSU.exe et SDL3.dll."
    exit 1
}

New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
New-Item -ItemType Directory -Force -Path $packageDirectory | Out-Null
Copy-Item -LiteralPath $executable -Destination $outputDirectory -Force
Copy-Item -LiteralPath $sdlLibrary -Destination $outputDirectory -Force

$manifest = [ordered]@{
    schema_version = 1
    architecture = "x64"
    protocol = 1001
    port = 26760
    sdl_version = "3.4.14"
    executable_sha256 = (Get-FileHash -Algorithm SHA256 $executable).Hash.ToLowerInvariant()
    sdl_sha256 = (Get-FileHash -Algorithm SHA256 $sdlLibrary).Hash.ToLowerInvariant()
}
$manifest | ConvertTo-Json | Set-Content `
    -LiteralPath (Join-Path $outputDirectory "manifest.json") `
    -Encoding UTF8 `
    -NoNewline

Copy-Item -LiteralPath (Join-Path $outputDirectory "JoyConDSU.exe") -Destination $packageDirectory -Force
Copy-Item -LiteralPath (Join-Path $outputDirectory "SDL3.dll") -Destination $packageDirectory -Force
Copy-Item -LiteralPath (Join-Path $outputDirectory "manifest.json") -Destination $packageDirectory -Force

Write-Host "Moteur Windows construit dans $outputDirectory" -ForegroundColor Green