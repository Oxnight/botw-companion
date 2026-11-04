$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$scriptPath = Join-Path $projectRoot "tools/test_windows_installation.ps1"
$tokens = $null
$parseErrors = $null
$tree = [System.Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors) { throw ($parseErrors | Out-String) }
$definition = $tree.Find({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq "Test-ApplicationLineage"
}, $true)
if (-not $definition) { throw "The native lineage validator is missing." }
# Load only the pure validator; never execute the native installation script.
. ([scriptblock]::Create($definition.Extent.Text))

function New-ProcessStart([long]$Id, [long]$ParentId, [string]$Name = "BOTW Companion Updater.exe") {
    return @{ name = $Name; id = $Id; parent_id = $ParentId }
}

$root = New-ProcessStart 4136 100
$child = New-ProcessStart 4284 4136
$direct = New-ProcessStart 8140 4136 "BOTW Companion.exe"
$onefile = New-ProcessStart 8140 4284 "BOTW Companion.exe"
$cases = @(
    @{ name = "direct parent"; starts = @($root, $direct); count = 1; valid = $true },
    @{ name = "onefile child"; starts = @($root, $child, $onefile); count = 1; valid = $true },
    @{ name = "multiple intermediates"; starts = @($root, $child, (New-ProcessStart 5000 4284),
        (New-ProcessStart 8140 5000 "BOTW Companion.exe")); count = 1; valid = $true },
    @{ name = "unknown parent"; starts = @($root, $onefile); count = 1; valid = $false },
    @{ name = "unrelated updater"; starts = @($root, (New-ProcessStart 4284 9999), $onefile);
        count = 1; valid = $false },
    @{ name = "unrelated updater alongside valid application"; starts = @($root, $direct, (New-ProcessStart 5000 100));
        count = 1; valid = $false },
    @{ name = "missing root event"; starts = @($child, $onefile); count = 1; valid = $false },
    @{ name = "missing intermediate"; starts = @($root, (New-ProcessStart 4284 5000), $onefile);
        count = 1; valid = $false },
    @{ name = "cycle"; starts = @($root, (New-ProcessStart 4284 5000),
        (New-ProcessStart 5000 4284), $onefile); count = 1; valid = $false },
    @{ name = "cycle through root"; starts = @((New-ProcessStart 4136 4284), $child, $onefile);
        count = 1; valid = $false },
    @{ name = "self cycle"; starts = @($root, (New-ProcessStart 4284 4284), $onefile);
        count = 1; valid = $false },
    @{ name = "two applications"; starts = @($root, $direct, (New-ProcessStart 8141 4136 "BOTW Companion.exe"));
        count = 1; valid = $false },
    @{ name = "ambiguous PID"; starts = @($root, $child, (New-ProcessStart 4284 9999), $onefile);
        count = 1; valid = $false },
    @{ name = "wrong intermediate executable"; starts = @($root, (New-ProcessStart 4284 4136 "other.exe"), $onefile);
        count = 1; valid = $false },
    @{ name = "silent install"; starts = @(); count = 0; valid = $true },
    @{ name = "no application despite updater starts"; starts = @($root, $child); count = 0; valid = $true },
    @{ name = "silent or interactive-assisted application launch"; starts = @($root, $direct);
        count = 0; valid = $false }
)
$events = @($root, $child, $onefile)
foreach ($order in @(@(0, 1, 2), @(0, 2, 1), @(1, 0, 2), @(1, 2, 0), @(2, 0, 1), @(2, 1, 0))) {
    $cases += @{ name = "delivery order $($order -join ',')";
        starts = @($events[$order[0]], $events[$order[1]], $events[$order[2]]); count = 1; valid = $true }
}
foreach ($case in $cases) {
    $actual = Test-ApplicationLineage -Processes $case.starts -ExpectedCount $case["count"] -ParentProcessId 4136
    if ($actual -isnot [bool] -or $actual -ne $case.valid) {
        throw "Lineage regression '$($case.name)': expected $($case.valid), got $actual."
    }
    Write-Host "Process lineage passed: $($case.name)"
}
Write-Host "$($cases.Count) deterministic process-lineage cases passed."
