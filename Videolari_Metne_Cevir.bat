@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title Video -> Metin

set "SCRIPT_DIR=%~dp0"

if "%~1"=="" (
    echo Kullanim: Bu .bat dosyasinin uzerine bir veya birden fazla klasor surukleyip birak.
    echo Klasordeki tum videolar taranir, metinler ayni klasor icindeki "transcripts" klasorune yazilir.
    echo.
    pause
    exit /b 1
)

if not exist "%SCRIPT_DIR%.venv\Scripts\python.exe" (
    echo Ilk kurulum yapiliyor, bu biraz surebilir...
    echo.
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%setup.ps1"
    if errorlevel 1 (
        echo.
        echo HATA: Kurulum basarisiz oldu. Yukaridaki mesaja bak.
        pause
        exit /b 1
    )
    echo.
)

:process_loop
if "%~1"=="" goto done

if exist "%~1\" (
    echo.
    echo ================================================
    echo Islenen klasor: %~1
    echo ================================================
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%run.ps1" -InputDir "%~1"
) else (
    echo Atlaniyor ^(klasor degil^): %~1
)

shift
goto process_loop

:done
echo.
echo Tum klasorler icin islem tamamlandi.
pause
