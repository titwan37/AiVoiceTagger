Here is the updated guidance incorporating your new file rules, priority rules, and dedicated high-priority folder locations.

---

## 🎯 Updated Guidance & System Rules

### 1. File Type & Format Rules

* **Strict Audio Only:** Only pure audio files (e.g., `.mp3`, `.m4a`, `.wav`, `.aac`, `.ogg`, `.aif`) should be processed.
* **Audio Over Video:** Pure audio files must **always take precedence** over video files (e.g., `.mp4`, `.mkv`). Video files should be deferred to a secondary low-priority queue or skipped if audio workload exists.
* **Non-Media Exclusion:** Non-media sidecars (`.apk`, `.pdf`, `.zip`, `.txt`, `.pk`, `.lst`) are strictly excluded from pipeline processing.

---

### 2. High-Importance & Priority Folder Strategy

Files designated as high importance, priority, or manually sorted must be stored in dedicated folders:

* **`\\SyNAS\Records\RecordStrike`**

* **`\\SyNAS\Records\Audio\Select_Sort`**

> **Priority Rule:** Workers must process files inside these dedicated priority folders **before** scanning general or archived collection folders (`#recycle`, general years).

---

### 3. Updated PowerShell Partitioning Script (`split_manifest.ps1`)

The partitioning script has been updated to incorporate:

1. **Dedicated Priority Folders First** (`RecordStrike`, `Select_Sort`).

2. **Audio vs. Video Hierarchy** (Pure audio prioritized over video formats like `.mp4`).
3. **Target Year Filter (2019–2024)**.
4. **File Size Cap ($\le 500$ MB)** to prevent single monster files from locking workers.
5. **Random Scramble / Shuffle** for temporal coverage across years.
6. **Round-Robin Worker Distribution**.

Save the updated code to `scripts/split_manifest.ps1`:

```powershell
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$ManifestPath,

    [int]$NumWorkers = 2,
    [int]$MinYear = 2019,
    [int]$MaxYear = 2024,
    [int]$MaxMB = 500,
    [switch]$Scramble = $true
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $ManifestPath)) {
    Write-Error "❌ Manifest file not found: $ManifestPath"
    exit 1
}

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " 📦 AiVoiceTagger Priority Manifest Splitter" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Reading manifest: $ManifestPath..." -ForegroundColor Cyan
$rows = Import-Csv -Path $ManifestPath

# Define Format Categories
$pureAudioExts = @('.mp3', '.m4a', '.wav', '.aac', '.ogg', '.aif')
$videoExts     = @('.mp4', '.mkv', '.avi', '.mov')
$maxBytes      = $MaxMB * 1024 * 1024

# Dedicated High Importance Folder Substrings
$priorityFolderKey = "RecordStrike|Select_Sort"

# 1. Filter and Categorize Records
$priorityRows  = [System.Collections.Generic.List[PSObject]]::new()
$audioRows     = [System.Collections.Generic.List[PSObject]]::new()
$videoRows     = [System.Collections.Generic.List[PSObject]]::new()

foreach ($row in $rows) {
    $ext  = [System.IO.Path]::GetExtension($row.name).ToLower()
    $size = [int64]$row.length_bytes
    $dir  = $row.directory
    
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
    } elseif ($videoExts -contains $ext) {
        $videoRows.Add($row)
    }
}

Write-Host "Found $($priorityRows.Count) HIGH PRIORITY records (RecordStrike / Select_Sort)" -ForegroundColor Green
Write-Host "Found $($audioRows.Count) Standard Audio records ($MinYear-$MaxYear, <= $MaxMB MB)" -ForegroundColor Green
Write-Host "Found $($videoRows.Count) Video records (Deferred priority)" -ForegroundColor Yellow

# 2. Scramble Audio & Video rows independently (to cover whole timeline quickly)
if ($Scramble) {
    Write-Host "Scrambling execution order for temporal distribution..." -ForegroundColor Yellow
    $audioRows = [System.Collections.Generic.List[PSObject]]($audioRows | Get-Random -Count $audioRows.Count)
    $videoRows = [System.Collections.Generic.List[PSObject]]($videoRows | Get-Random -Count $videoRows.Count)
}

# 3. Assemble Master Queue: Priority Folders -> Pure Audio -> Video
$finalQueue = [System.Collections.Generic.List[PSObject]]::new()
$finalQueue.AddRange($priorityRows)
$finalQueue.AddRange($audioRows)
$finalQueue.AddRange($videoRows)

Write-Host "Total Ordered Queue Size: $($finalQueue.Count) items" -ForegroundColor Cyan

# 4. Round-Robin Distribution Across Workers
$workerBuffers = @()
for ($w = 0; $w -lt $NumWorkers; $w++) {
    $workerBuffers += ,([System.Collections.Generic.List[PSObject]]::new())
}

for ($i = 0; $i -lt $finalQueue.Count; $i++) {
    $targetWorker = $i % $NumWorkers
    $workerBuffers[$targetWorker].Add($finalQueue[$i])
}

# 5. Export Worker Manifests
for ($w = 0; $w -lt $NumWorkers; $w++) {
    $workerId = $w + 1
    $outFile  = "inventory_pc${workerId}.csv"
    $workerBuffers[$w] | Export-Csv -Path $outFile -NoTypeInformation -Encoding UTF8
    
    $totalGB = ($workerBuffers[$w] | Measure-Object -Property length_bytes -Sum).Sum / 1GB
    Write-Host "  ✅ Generated $outFile -> $($workerBuffers[$w].Count) records ($([math]::Round($totalGB, 2)) GB)" -ForegroundColor Green
}

Write-Host "`n🎉 Priority manifest partitioning completed successfully!" -ForegroundColor Green

```

---

### 🚀 Execution Summary

Run the script to generate the updated priority manifests:

```powershell
.\scripts\split_manifest.ps1 -ManifestPath inventory_manifest.csv -NumWorkers 2 -MinYear 2019 -MaxYear 2024 -MaxMB 500 -Scramble

```

This ensures both workers will process:

1. Files in `\RecordStrike` & `\Audio\Select_Sort` **first**.

2. Scrambled **pure audio files** across 2019–2024 **second**.
3. **Video files** (`.mp4`) **last**.
