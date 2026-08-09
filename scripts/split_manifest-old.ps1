<#
.SYNOPSIS
    Splits an AiVoiceTagger inventory manifest CSV into N equal worker partitions.
.DESCRIPTION
    Uses round-robin distribution to split audio inventory manifests cleanly across multiple worker nodes (pc-1, pc-2, etc.).
.EXAMPLE
    .\split_manifest.ps1 -ManifestPath "inventory_manifest.csv" -NumWorkers 2
#>

param (
    [Parameter(Mandatory=$false)]
    [string]$ManifestPath = "inventory_manifest.csv",

    [Parameter(Mandatory=$false)]
    [int]$NumWorkers = 2,

    [Parameter(Mandatory=$false)]
    [string]$OutputDir = "."
)

if (-not (Test-Path $ManifestPath)) {
    Write-Error "❌ Manifest CSV file not found at '$ManifestPath'."
    exit 1
}

if ($NumWorkers -lt 1) {
    Write-Error "❌ NumWorkers must be at least 1."
    exit 1
}

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " 📦 AiVoiceTagger Manifest Splitter Utility" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Manifest:    $ManifestPath"
Write-Host "Num Workers: $NumWorkers"

$lines = Get-Content $ManifestPath
if ($lines.Count -le 1) {
    Write-Host "⚠️ Manifest contains no record rows." -ForegroundColor Yellow
    exit 0
}

$header = $lines[0]
$recordLines = $lines[1..($lines.Count - 1)]
$totalRecords = $recordLines.Count

Write-Host "Total audio records found: $totalRecords`n"

# Initialize worker buffers
$workerBuffers = @()
for ($w = 0; $w -lt $NumWorkers; $w++) {
    $workerBuffers += ,(New-Object System.Collections.Generic.List[string])
}

# Round-robin distribution
for ($i = 0; $i -lt $totalRecords; $i++) {
    $workerIndex = $i % $NumWorkers
    $workerBuffers[$workerIndex].Add($recordLines[$i])
}

# Write partition files
Ensure-DirectoryExists $OutputDir | Out-Null
for ($w = 0; $w -lt $NumWorkers; $w++) {
    $workerId = $w + 1
    $outFile = Join-Path $OutputDir "inventory_pc${workerId}.csv"
    
    $fileContent = @($header) + $workerBuffers[$w]
    Set-Content -Path $outFile -Value $fileContent -Encoding UTF8

    Write-Host "  ✅ Generated partition 'inventory_pc${workerId}.csv': $($workerBuffers[$w].Count) records -> $outFile" -ForegroundColor Green
}

Write-Host "`n🎉 Manifest split completed successfully!" -ForegroundColor Green
