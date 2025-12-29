@echo off
setlocal enabledelayedexpansion

echo ====================================
echo PriBot Production Start Script
echo ====================================

REM PriBot production script path settings
set PRIBOT_SCRIPT=C:\Users\miyake2106\Desktop\wk\PriBot\pribot.py
set PYTHON_EXE=C:\Users\miyake2106\AppData\Local\Programs\Python\Python311\python.exe
set LOCK_FILE=C:\Users\miyake2106\Desktop\wk\PriBot\pribot.lock
set PID_FILE=C:\Users\miyake2106\Desktop\wk\PriBot\pribot_pids.txt

REM Detect startup method
set STARTUP_METHOD=UNKNOWN
if "%SESSIONNAME%"=="Console" (
    set STARTUP_METHOD=INTERACTIVE
) else (
    set STARTUP_METHOD=SCHEDULED
)

echo Startup method detected: !STARTUP_METHOD!

REM Check existing processes
if exist "%LOCK_FILE%" (
    echo [WARNING] Lock file exists
    set /p EXISTING_PID=<"%LOCK_FILE%"
    echo Recorded PID: !EXISTING_PID!
    
    REM Check if process is actually running
    tasklist /fi "PID eq !EXISTING_PID!" | find "!EXISTING_PID!" >nul 2>&1
    if !errorlevel! equ 0 (
        echo [ERROR] PriBot is already running (PID: !EXISTING_PID!)
        echo Preventing duplicate startup
        echo To stop, run pribot_production_stop.bat
        exit /b 1
    ) else (
        echo [INFO] PID !EXISTING_PID! process does not exist
        echo Removing orphaned lock file
        del "%LOCK_FILE%" >nul 2>&1
        del "%PID_FILE%" >nul 2>&1
    )
)

echo Starting PriBot Production with universal compatibility...

REM Create unique window title with timestamp
set TIMESTAMP=%DATE:~0,4%%DATE:~5,2%%DATE:~8,2%_%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%
set TIMESTAMP=!TIMESTAMP: =0!
set WINDOW_TITLE=PriBot_Production_!TIMESTAMP!

echo Window title: !WINDOW_TITLE!

REM Start with unique identifiable title
start "!WINDOW_TITLE!" cmd /k "title !WINDOW_TITLE! && echo PriBot Production Starting [!STARTUP_METHOD!] && "%PYTHON_EXE%" "%PRIBOT_SCRIPT%""

REM Wait for startup
timeout /t 5 >nul

REM Record all related PIDs for reliable stopping
echo Recording process information...
> "%PID_FILE%" echo # PriBot Production Process Information

REM Find and record CMD process (improved detection)
for /f "tokens=1" %%i in ('wmic process where "CommandLine like '%%!WINDOW_TITLE!%%' and Name='cmd.exe'" get ProcessId /format:value 2^>nul ^| find "ProcessId="') do (
    set FULL_LINE=%%i
    set CMD_PID=!FULL_LINE:ProcessId=!
    set CMD_PID=!CMD_PID: =!
    if !CMD_PID! gtr 0 (
        echo CMD_PID=!CMD_PID! >> "%PID_FILE%"
        echo [INFO] CMD process PID: !CMD_PID!
    )
)

REM Find and record Python process (improved detection)
for /f "tokens=1" %%i in ('wmic process where "CommandLine like '%%pribot.py%%' and Name='python.exe'" get ProcessId /format:value 2^>nul ^| find "ProcessId="') do (
    set FULL_LINE=%%i
    set PYTHON_PID=!FULL_LINE:ProcessId=!
    set PYTHON_PID=!PYTHON_PID: =!
    if !PYTHON_PID! gtr 0 (
        echo PYTHON_PID=!PYTHON_PID! >> "%PID_FILE%"
        echo [INFO] Python process PID: !PYTHON_PID!
        
        REM Main lock file uses Python PID
        echo !PYTHON_PID! > "%LOCK_FILE%"
    )
)

REM Record window title for identification
echo WINDOW_TITLE=!WINDOW_TITLE! >> "%PID_FILE%"
echo STARTUP_METHOD=!STARTUP_METHOD! >> "%PID_FILE%"
echo START_TIME=!DATE! !TIME! >> "%PID_FILE%"

echo [SUCCESS] PriBot Production started successfully
echo [SUCCESS] Process information recorded
echo [INFO] Window title: !WINDOW_TITLE!
echo [INFO] PID file: %PID_FILE%
echo [INFO] Lock file: %LOCK_FILE%

echo.
echo ====================================
echo Production startup completed
echo Method: !STARTUP_METHOD!
echo ====================================