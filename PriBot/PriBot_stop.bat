@echo off
echo ====================================
echo PriBot Minimal Stop (PowerShell Only)
echo ====================================

echo Stopping PriBot...
powershell -Command "Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like '*pribot.py*' } | ForEach-Object { Write-Host 'Stopping PID:' $_.ProcessId; $_.Terminate(); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

timeout /t 2 >nul

echo Cleaning up...
del "C:\Users\monibot\Desktop\wk\PriBot\pribot.lock" >nul 2>&1
del "C:\Users\monibot\Desktop\wk\PriBot\pribot_pids.txt" >nul 2>&1

echo Verification...
wmic process where "CommandLine like '%%pribot.py%%'" get ProcessId /format:value 2>nul | find "ProcessId=" >nul 2>&1
if %errorlevel% equ 0 (
    echo [WARNING] Some processes may still be running
) else (
    echo [SUCCESS] PriBot stopped
)

echo.
echo ====================================
echo Production stop completed
echo ====================================
echo.
echo This window will close in 3 seconds...
timeout /t 3 >nul