# Kurulum scripti - bir kere calistir.
# Python venv olusturur, gerekli paketleri kurar, GPU'yu kontrol eder.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Find-Python {
    foreach ($cmd in @("py -3", "python", "python3")) {
        $parts = $cmd -split " "
        $exe = $parts[0]
        $found = Get-Command $exe -ErrorAction SilentlyContinue
        if ($found) {
            return $cmd
        }
    }
    return $null
}

$pythonCmd = Find-Python
if (-not $pythonCmd) {
    Write-Host "HATA: Python bulunamadi. Once Python 3.10+ kurup PATH'e ekle." -ForegroundColor Red
    Write-Host "https://www.python.org/downloads/ adresinden 'Add python.exe to PATH' secenegiyle kur." -ForegroundColor Yellow
    exit 1
}

Write-Host "Python bulundu: $pythonCmd" -ForegroundColor Green
Invoke-Expression "$pythonCmd --version"

$venvPath = Join-Path $root ".venv"
if (-not (Test-Path $venvPath)) {
    Write-Host "Sanal ortam (venv) olusturuluyor..." -ForegroundColor Cyan
    Invoke-Expression "$pythonCmd -m venv `"$venvPath`""
} else {
    Write-Host "Venv zaten var, atlaniyor." -ForegroundColor Yellow
}

$venvPython = Join-Path $venvPath "Scripts\python.exe"

Write-Host "pip guncelleniyor..." -ForegroundColor Cyan
& $venvPython -m pip install --upgrade pip

Write-Host "Paketler kuruluyor (faster-whisper, imageio-ffmpeg)..." -ForegroundColor Cyan
& $venvPython -m pip install -r (Join-Path $root "requirements.txt")

Write-Host ""
Write-Host "GPU kontrolu (nvidia-smi):" -ForegroundColor Cyan
$nvidiaSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($nvidiaSmi) {
    & nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
} else {
    Write-Host "nvidia-smi bulunamadi. NVIDIA surucusu kurulu degil gibi gorunuyor." -ForegroundColor Yellow
    Write-Host "RTX 5060 icin en guncel surucuyu https://www.nvidia.com/drivers adresinden kur." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Kurulum tamamlandi." -ForegroundColor Green
Write-Host "Kullanim: .\run.ps1 -InputDir 'D:\Videolar'" -ForegroundColor Green
