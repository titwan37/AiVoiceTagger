# AiVoiceTagger CUDA Execution Launcher Script

# 1. Set CUDA Environment Variables for dynamic DLL loading
$cuda_dir = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.3"
if (Test-Path $cuda_dir) {
    $env:CUDA_PATH = $cuda_dir
    $env:CUDA_PATH_V13_3 = $cuda_dir
    $env:PATH = "$cuda_dir\bin\x64;$cuda_dir\bin;" + $env:PATH
} else {
    Write-Host "[WARNING] CUDA 13.3 directory not found at $cuda_dir" -ForegroundColor Yellow
}

# 2. Prompt user for Worker ID number (Default: 1)
$worker_num = Read-Host "Enter Worker ID number [1-4] (Default: 1)"
if ([string]::IsNullOrWhiteSpace($worker_num)) {
    $worker_num = "1"
}

$worker_id = "pc-beta-$worker_num"
$manifest_csv = "export/Focused_Priority_Records.csv"
$config_yaml = "config.yaml"
$exe_path = "target\release\aivoicetagger.exe"

# 3. Check if release binary exists, build if missing
if (-not (Test-Path $exe_path)) {
    Write-Host "[INFO] Release binary not found at $exe_path. Compiling with CUDA support..." -ForegroundColor Cyan
    cargo build --release --features cuda
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Build failed with exit code $LASTEXITCODE" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

# 4. Launch AiVoiceTagger in foreground (keeps process handle attached to terminal for Ctrl+C)
Write-Host "[INFO] Launching AiVoiceTagger ($worker_id) with CUDA acceleration in foreground..." -ForegroundColor Green
& $exe_path --config $config_yaml --from-csv $manifest_csv --worker-id $worker_id
