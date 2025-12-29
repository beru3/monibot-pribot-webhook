@echo off
setlocal enabledelayedexpansion

echo ====================================
echo PriBot Production Start Script
echo ====================================

REM PriBot production script path settings
set PRIBOT_SCRIPT=C:\Users\monibot\Desktop\wk\PriBot\pribot.py
set VENV_PATH=C:\Users\monibot\Desktop\wk\venv
set PYTHON_EXE=C:\Users\monibot\AppData\Local\Programs\Python\Python311\python.exe
set LOCK_FILE=C:\Users\monibot\Desktop\wk\PriBot\pribot.lock
set PID_FILE=C:\Users\monibot\Desktop\wk\PriBot\pribot_pids.txt

REM Check if files exist
if not exist "%PRIBOT_SCRIPT%" (
    echo [ERROR] PriBot script not found: %PRIBOT_SCRIPT%
    pause
    exit /b 1
)

REM Test Python and modules (using global Python that works)
echo Testing Python environment...
"%PYTHON_EXE%" -c "import requests, pdfplumber, watchdog, configparser, psutil; print('[SUCCESS] All required modules are available')" 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Required modules are missing
    echo [ERROR] Please ensure modules are installed
    pause
    exit /b 1
)

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
        echo To stop, run PriBot_stop.bat
        pause
        exit /b 1
    ) else (
        echo [INFO] PID !EXISTING_PID! process does not exist
        echo Removing orphaned lock file
        del "%LOCK_FILE%" >nul 2>&1
        del "%PID_FILE%" >nul 2>&1
    )
)

echo Starting PriBot Production...
echo Python executable: %PYTHON_EXE%
echo PriBot script: %PRIBOT_SCRIPT%

REM Create unique window title with timestamp
set TIMESTAMP=%DATE:~0,4%%DATE:~5,2%%DATE:~8,2%_%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%
set TIMESTAMP=!TIMESTAMP: =0!
set WINDOW_TITLE=PriBot_Production_!TIMESTAMP!

echo Window title: !WINDOW_TITLE!

REM Change to PriBot directory and start (using working Python path)
cd /d "C:\Users\monibot\Desktop\wk\PriBot"
start "!WINDOW_TITLE!" cmd /k "title !WINDOW_TITLE! && echo PriBot Production Starting [!STARTUP_METHOD!] && call "%VENV_PATH%\Scripts\activate.bat" && python pribot.py"

REM Wait for startup
timeout /t 5 >nul

REM Record all related PIDs for reliable stopping
echo Recording process information...
> "%PID_FILE%" echo # PriBot Production Process Information

REM Find and record Python process
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
echo [INFO] Python executable: %PYTHON_EXE%
echo [INFO] PriBot script: %PRIBOT_SCRIPT%
echo [INFO] Window title: !WINDOW_TITLE!

echo.
echo ====================================
echo Production startup completed
echo Method: !STARTUP_METHOD!
echo ====================================