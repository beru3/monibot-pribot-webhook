@echo off
setlocal enabledelayedexpansion

echo ====================================
echo PriBot Stop Test - Start Script
echo ====================================

REM Test script path settings (本番環境のパスに合わせる)
set TEST_SCRIPT=C:\Users\miyake2106\Desktop\wk\PriBot\test_long_running.py
set PYTHON_EXE=C:\Users\miyake2106\AppData\Local\Programs\Python\Python311\python.exe
set LOCK_FILE=C:\Users\miyake2106\Desktop\wk\PriBot\pribot_test.lock
set PID_FILE=C:\Users\miyake2106\Desktop\wk\PriBot\pribot_test_pids.txt

REM Detect startup method
set STARTUP_METHOD=UNKNOWN
if "%SESSIONNAME%"=="Console" (
    set STARTUP_METHOD=INTERACTIVE
) else (
    set STARTUP_METHOD=SCHEDULED
)

echo Startup method detected: !STARTUP_METHOD!

REM Check existing test processes
if exist "%LOCK_FILE%" (
    echo [WARNING] Test lock file exists
    set /p EXISTING_PID=<"%LOCK_FILE%"
    echo Recorded test PID: !EXISTING_PID!
    
    REM Check if process is actually running
    tasklist /fi "PID eq !EXISTING_PID!" | find "!EXISTING_PID!" >nul 2>&1
    if !errorlevel! equ 0 (
        echo [ERROR] Test process is already running (PID: !EXISTING_PID!)
        echo Preventing duplicate startup
        echo To stop, run test_stop.bat
        exit /b 1
    ) else (
        echo [INFO] PID !EXISTING_PID! process does not exist
        echo Removing orphaned test lock file
        del "%LOCK_FILE%" >nul 2>&1
        del "%PID_FILE%" >nul 2>&1
    )
)

echo Starting PriBot Stop Test with simulated long-running process...

REM Create unique window title with timestamp
set TIMESTAMP=%DATE:~0,4%%DATE:~5,2%%DATE:~8,2%_%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%
set TIMESTAMP=!TIMESTAMP: =0!
set WINDOW_TITLE=PriBot_Test_!TIMESTAMP!

echo Window title: !WINDOW_TITLE!

REM Start with unique identifiable title
start "!WINDOW_TITLE!" cmd /k "title !WINDOW_TITLE! && echo PriBot Stop Test Starting [!STARTUP_METHOD!] && "%PYTHON_EXE%" "%TEST_SCRIPT%""

REM Wait for startup
timeout /t 5 >nul

REM Record all related PIDs for reliable stopping
echo Recording test process information...
> "%PID_FILE%" echo # PriBot Test Process Information

REM Find and record CMD process
for /f "tokens=1" %%i in ('wmic process where "CommandLine like '%%!WINDOW_TITLE!%%' and Name='cmd.exe'" get ProcessId /format:value 2^>nul ^| find "ProcessId="') do (
    set FULL_LINE=%%i
    set CMD_PID=!FULL_LINE:ProcessId=!
    set CMD_PID=!CMD_PID: =!
    if !CMD_PID! gtr 0 (
        echo CMD_PID=!CMD_PID! >> "%PID_FILE%"
        echo [INFO] Test CMD process PID: !CMD_PID!
    )
)

REM Find and record Python process
for /f "tokens=1" %%i in ('wmic process where "CommandLine like '%%test_long_running.py%%' and Name='python.exe'" get ProcessId /format:value 2^>nul ^| find "ProcessId="') do (
    set FULL_LINE=%%i
    set PYTHON_PID=!FULL_LINE:ProcessId=!
    set PYTHON_PID=!PYTHON_PID: =!
    if !PYTHON_PID! gtr 0 (
        echo PYTHON_PID=!PYTHON_PID! >> "%PID_FILE%"
        echo [INFO] Test Python process PID: !PYTHON_PID!
        
        REM Main lock file uses Python PID
        echo !PYTHON_PID! > "%LOCK_FILE%"
    )
)

REM Record window title for identification
echo WINDOW_TITLE=!WINDOW_TITLE! >> "%PID_FILE%"
echo STARTUP_METHOD=!STARTUP_METHOD! >> "%PID_FILE%"
echo START_TIME=!DATE! !TIME! >> "%PID_FILE%"

echo [SUCCESS] PriBot Stop Test started successfully
echo [SUCCESS] Test process information recorded
echo [INFO] Window title: !WINDOW_TITLE!
echo [INFO] PID file: %PID_FILE%
echo [INFO] Lock file: %LOCK_FILE%

echo.
echo ====================================
echo Test startup completed
echo Method: !STARTUP_METHOD!
echo ====================================
echo.
echo The test process will run until stopped with test_stop.bat
echo Press any key to close this startup window (test process continues)...
pause >nul