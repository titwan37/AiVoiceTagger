<#
.SYNOPSIS
    Splits an AiVoiceTagger inventory manifest CSV into N equal worker partitions.
.DESCRIPTION
    Uses round-robin distribution to split audio inventory manifests cleanly across multiple worker nodes (pc-1, pc-2, etc.).
.EXAMPLE
    .\split_manifest.ps1 -ManifestPath "inventory_manifest.csv" -NumWorkers 2
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ManifestPath,

    [int]$NumWorkers = 2,
    [int]$MinYear = 2019,
    [int]$MaxYear = 2024,
    [int]$MaxMB = 500,
    [switch]$Scramble = $true
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $ManifestPath)) {
    Write-Error "Manifest file not found: $ManifestPath"
    exit 1
}

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " AiVoiceTagger Priority Manifest Splitter" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Reading manifest: $ManifestPath..." -ForegroundColor Cyan
$rows = Import-Csv -Path $ManifestPath

# Define Format Categories
$pureAudioExts = @('.mp3', '.m4a', '.wav', '.aac', '.ogg', '.aif')
$videoExts = @('.mp4', '.mkv', '.avi', '.mov')
$maxBytes = [int64]$MaxMB * 1024 * 1024

# Dedicated High Importance Folder Substrings
$priorityFolderKey = "RecordStrike|Select_Sort"

# 1. Filter and Categorize Records
$priorityRows = [System.Collections.Generic.List[PSObject]]::new()
$audioRows = [System.Collections.Generic.List[PSObject]]::new()
$videoRows = [System.Collections.Generic.List[PSObject]]::new()

foreach ($row in $rows) {
    $ext = [System.IO.Path]::GetExtension($row.name).ToLower()
    $size = [int64]$row.length_bytes
    $dir = $row.directory
    
    # Check Year
    $yearMatch = [regex]::Match("$dir $($row.name)", '20\d\d')
    $year = if ($yearMatch.Success) { [int]$yearMatch.Value } else { 0 }

    # Apply Size Cap and Year Filters
    if ($size -gt $maxBytes) { continue }
    if ($year -lt $MinYear -or $year -gt $MaxYear) { continue }

    # Check Priority Folders First (\RecordStrike or \Audio\Select_Sort)
    if ($dir -match $priorityFolderKey) {
        if ($pureAudioExts -contains $ext -or $videoExts -contains $ext) {
            $priorityRows.Add($row)
            continue
        }
    }

    # Categorize remaining by Audio vs Video
    if ($pureAudioExts -contains $ext) {
        $audioRows.Add($row)
    }
    elseif ($videoExts -contains $ext) {
        $videoRows.Add($row)
    }
}

$pCount = $priorityRows.Count
$aCount = $audioRows.Count
$vCount = $videoRows.Count

Write-Host "Found $pCount HIGH PRIORITY records (RecordStrike / Select_Sort)" -ForegroundColor Green
Write-Host "Found $aCount Standard Audio records ($MinYear-$MaxYear, under ${MaxMB} MB)" -ForegroundColor Green
Write-Host "Found $vCount Video records (Deferred priority)" -ForegroundColor Yellow

# 2. Scramble Audio & Video rows independently (to cover whole timeline quickly)
if ($Scramble) {
    Write-Host "Scrambling execution order for temporal distribution..." -ForegroundColor Yellow
    if ($audioRows.Count -gt 0) {
        $audioRows = [System.Collections.Generic.List[PSObject]]($audioRows | Get-Random -Count $audioRows.Count)
    }
    if ($videoRows.Count -gt 0) {
        $videoRows = [System.Collections.Generic.List[PSObject]]($videoRows | Get-Random -Count $videoRows.Count)
    }
}

# 3. Assemble Master Queue: Priority Folders -> Pure Audio -> Video
$finalQueue = [System.Collections.Generic.List[PSObject]]::new()
$finalQueue.AddRange($priorityRows)
$finalQueue.AddRange($audioRows)
$finalQueue.AddRange($videoRows)

$qCount = $finalQueue.Count
Write-Host "Total Ordered Queue Size: $qCount items" -ForegroundColor Cyan

# 4. Round-Robin Distribution Across Workers
$workerBuffers = @()
for ($w = 0; $w -lt $NumWorkers; $w++) {
    $workerBuffers += , ([System.Collections.Generic.List[PSObject]]::new())
}

for ($i = 0; $i -lt $finalQueue.Count; $i++) {
    $targetWorker = $i % $NumWorkers
    $workerBuffers[$targetWorker].Add($finalQueue[$i])
}

# 5. Export Worker Manifests
for ($w = 0; $w -lt $NumWorkers; $w++) {
    $workerId = $w + 1
    $outFile = "inventory_pc${workerId}.csv"
    $workerBuffers[$w] | Export-Csv -Path $outFile -NoTypeInformation -Encoding UTF8
    
    $sumBytes = ($workerBuffers[$w] | Measure-Object -Property length_bytes -Sum).Sum
    $totalGB = [math]::Round(($sumBytes / 1GB), 2)
    $wCount = $workerBuffers[$w].Count
    Write-Host "  Generated $outFile -> $wCount records ($totalGB GB)" -ForegroundColor Green
}

Write-Host "Priority manifest partitioning completed successfully!" -ForegroundColor Green