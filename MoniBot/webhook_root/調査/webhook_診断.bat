@echo off
chcp 65001 > nul

echo ==========================================
echo Webhook Diagnosis Tool - DEBUG VERSION
echo ==========================================
echo This version will show exactly where any errors occur
echo.

REM Enable error logging
echo Starting diagnosis at %date% %time% > debug_log.txt

echo Step 1: Testing basic commands...
echo Step 1: Testing basic commands... >> debug_log.txt

echo Current directory: %CD%
echo Current directory: %CD% >> debug_log.txt

echo User: %USERNAME%
echo User: %USERNAME% >> debug_log.txt

echo.
echo Step 2: Testing tasklist command...
echo Step 2: Testing tasklist command... >> debug_log.txt
tasklist /fi "imagename eq python.exe" /fo table 2>>debug_log.txt
if %errorlevel% neq 0 (
    echo ERROR: tasklist command failed! >> debug_log.txt
    echo ERROR: tasklist command failed!
    pause
    exit /b 1
) else (
    echo tasklist: SUCCESS >> debug_log.txt
    echo tasklist: SUCCESS
)

echo.
echo Step 3: Testing netstat command...
echo Step 3: Testing netstat command... >> debug_log.txt
netstat -ano | findstr ":8080" >nul 2>>debug_log.txt
echo netstat exit code: %errorlevel% >> debug_log.txt
echo netstat: Completed (exit code: %errorlevel%)

echo.
echo Step 4: Testing PowerShell availability...
echo Step 4: Testing PowerShell availability... >> debug_log.txt
powershell -Command "Write-Output 'PowerShell test successful'" 2>>debug_log.txt
if %errorlevel% neq 0 (
    echo ERROR: PowerShell not available or failed! >> debug_log.txt
    echo ERROR: PowerShell not available or failed!
    echo This might be the problem. Checking alternatives...
    pause
) else (
    echo PowerShell: SUCCESS >> debug_log.txt
    echo PowerShell: SUCCESS
)

echo.
echo Step 5: Testing simple PowerShell process query...
echo Step 5: Testing simple PowerShell process query... >> debug_log.txt
powershell -Command "Get-Process python -ErrorAction SilentlyContinue | Select-Object Id, ProcessName" 2>>debug_log.txt
if %errorlevel% neq 0 (
    echo Warning: PowerShell Get-Process failed >> debug_log.txt
    echo Warning: PowerShell Get-Process failed
    echo Trying alternative method...
) else (
    echo PowerShell Get-Process: SUCCESS >> debug_log.txt
    echo PowerShell Get-Process: SUCCESS
)

echo.
echo Step 6: Testing file existence checks...
echo Step 6: Testing file existence checks... >> debug_log.txt
if exist "webhook_server.py" (
    echo File check 1: SUCCESS - webhook_server.py found in current dir >> debug_log.txt
    echo File check 1: SUCCESS - webhook_server.py found in current dir
) else (
    echo File check 1: webhook_server.py not in current dir >> debug_log.txt
    echo File check 1: webhook_server.py not in current dir
)

echo.
echo Step 7: Testing variable operations...
echo Step 7: Testing variable operations... >> debug_log.txt
setlocal enabledelayedexpansion
set TEST_COUNT=0
set /a TEST_COUNT+=1
echo Variable test: Count = !TEST_COUNT! >> debug_log.txt
echo Variable test: Count = !TEST_COUNT!
if !TEST_COUNT!==1 (
    echo Variable operations: SUCCESS >> debug_log.txt
    echo Variable operations: SUCCESS
) else (
    echo ERROR: Variable operations failed! >> debug_log.txt
    echo ERROR: Variable operations failed!
)

echo.
echo ==========================================
echo DEBUG SUMMARY
echo ==========================================
echo All basic tests completed.
echo Check debug_log.txt for detailed error information.
echo.
echo If the script reaches this point, the main diagnosis should work.
echo Press any key to run a simplified diagnosis...
pause

echo.
echo ==========================================
echo SIMPLIFIED DIAGNOSIS
echo ==========================================

echo Python processes:
tasklist /fi "imagename eq python.exe" /fo table

echo.
echo Port 8080 check:
netstat -ano | findstr ":8080"
if %errorlevel%==0 (
    echo Port 8080 is in use
) else (
    echo Port 8080 is free
)

echo.
echo Port 5000 check:
netstat -ano | findstr ":5000"
if %errorlevel%==0 (
    echo Port 5000 is in use  
) else (
    echo Port 5000 is free
)

echo.
echo Diagnosis completed successfully!
echo Check debug_log.txt for any error details.
pause
echo Script ending normally.