param(
    [int]$Port = 18765
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$server = $null

Push-Location $projectRoot
try {
    $server = Start-Process -FilePath "python.exe" -ArgumentList @(
        "tools/browser_test_server.py",
        "--port",
        "$Port"
    ) -PassThru
    $ready = $false
    for ($attempt = 0; $attempt -lt 120; $attempt++) {
        if ($server.HasExited) {
            throw "Le serveur de test navigateur s'est arrêté prématurément."
        }
        try {
            Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/version" -TimeoutSec 1 | Out-Null
            $ready = $true
            break
        } catch {
            Start-Sleep -Milliseconds 250
        }
    }
    if (-not $ready) {
        throw "Le serveur de test navigateur ne répond pas."
    }
    foreach ($browser in @("chrome", "edge", "firefox")) {
        & node.exe "tools/browser_smoke.js" "http://127.0.0.1:$Port" $browser
        if ($LASTEXITCODE -ne 0) {
            throw "Le parcours $browser a échoué."
        }
    }
} finally {
    if ($server -and -not $server.HasExited) {
        $server.Kill()
        $server.WaitForExit()
    }
    Pop-Location
}
