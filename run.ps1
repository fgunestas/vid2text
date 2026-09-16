# Transkripsiyonu baslatir / kaldigi yerden devam ettirir.
# Kullanim:
#   .\run.ps1 -InputDir "D:\Videolar"
#   .\run.ps1 -InputDir "D:\Videolar" -OutputDir "D:\Videolar\metinler"
#
# Istedigin zaman Ctrl+C ile durdurabilirsin; tekrar calistirdiginda
# kaldigi saniyeden devam eder (hicbir seyi bastan baslatmaz).

param(
    [Parameter(Mandatory = $true)]
    [string]$InputDir,

    [string]$OutputDir = "",

    [string]$Model = "large-v3",

    [ValidateSet("cuda", "cpu")]
    [string]$Device = "cuda",

    [string]$ComputeType = "int8_float16",

    [string]$Language = "tr"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "HATA: venv bulunamadi. Once .\setup.ps1 calistir." -ForegroundColor Red
    exit 1
}

$scriptArgs = @(
    (Join-Path $root "transcribe.py"),
    "--input-dir", $InputDir,
    "--model", $Model,
    "--device", $Device,
    "--compute-type", $ComputeType,
    "--language", $Language
)

if ($OutputDir -ne "") {
    $scriptArgs += @("--output-dir", $OutputDir)
}

& $venvPython @scriptArgs
