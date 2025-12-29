@echo off
chcp 65001 > nul

echo ==========================================
echo Webhook Server Stop
echo ==========================================
echo Time: %date% %time%

setlocal enabledelayedexpansion
set STOPPED_COUNT=0

echo Stopping all webhook_server.py processes...

REM Stop all webhook processes dynamically
for /f "tokens=1" %%p in ('powershell "Get-WmiObject Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*webhook_server.py*' } | Select-Object -ExpandProperty ProcessId" 2^>nul') do (
    echo Stopping PID %%p
    taskkill /PID %%p /F >nul 2>&1
    if !errorlevel!==0 (
        set /a STOPPED_COUNT+=1
        echo ✓ Stopped PID %%p
    ) else (
        echo ✗ Failed to stop PID %%p
    )
)

if !STOPPED_COUNT!==0 (
    echo No webhook_server.py processes found
) else (
    echo Successfully stopped !STOPPED_COUNT! webhook process(es)
)

echo Time: %time%
exit /b 0