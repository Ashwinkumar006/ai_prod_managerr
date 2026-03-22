param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("p1", "p2", "p3", "p4")]
    [string]$Project,

    [switch]$Reload
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$sitePackages = Join-Path $repoRoot ".venv\Lib\site-packages"

if (-not (Test-Path $sitePackages)) {
    throw "Missing dependency path: $sitePackages"
}

$projects = @{
    p1 = @{
        Name = "P1_AstroMarine_CascadeFailureEngine"
        Port = 8001
    }
    p2 = @{
        Name = "P2_PolarSynth_SovereigntyPlatform"
        Port = 8002
    }
    p3 = @{
        Name = "P3_CryptoNova_BiocompoundEngine"
        Port = 8003
    }
    p4 = @{
        Name = "P4_DeepGenome_GeneticMarketplace"
        Port = 8004
    }
}

$selected = $projects[$Project]
$projectPath = Join-Path $repoRoot $selected.Name

if (-not (Test-Path $projectPath)) {
    throw "Project folder not found: $projectPath"
}

$env:PYTHONPATH = $sitePackages
$env:OPENBLAS_NUM_THREADS = "1"
$env:OMP_NUM_THREADS = "1"
$env:UVICORN_RELOAD = if ($Reload) { "true" } else { "false" }

Write-Host "Starting $($selected.Name) on port $($selected.Port)..."
Write-Host "Project path: $projectPath"
Write-Host "Reload: $($env:UVICORN_RELOAD)"

Set-Location $projectPath
python main.py
