param(
    [int]$Port = 18765
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$server = $null

Push-Location $projectRoot
try {
    foreach ($browser in @("chrome", "edge", "firefox")) {
        # A browser context isolates cookies/storage, not the server's files.
        # Give every engine fresh routes, notes, preferences and update state.
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
            if ($browser -eq "chrome") {
                $env:BOTW_CAPTURE_BLOOD_MOON = "1"
            } else {
                Remove-Item Env:BOTW_CAPTURE_BLOOD_MOON -ErrorAction SilentlyContinue
            }
            & node.exe "tools/browser_smoke.js" "http://127.0.0.1:$Port" $browser
            if ($LASTEXITCODE -ne 0) {
                throw "Le parcours $browser a échoué."
            }
        } finally {
            if ($server) {
                if (-not $server.HasExited) {
                    $server.Kill()
                    $server.WaitForExit()
                }
                $server.Dispose()
                $server = $null
            }
        }
    }
} finally {
    Remove-Item Env:BOTW_CAPTURE_BLOOD_MOON -ErrorAction SilentlyContinue
    Pop-Location
}
