@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

echo ========================================
echo   MoniBot Stop Process
echo ========================================

cd /d C:\Users\monibot\Desktop\wk\MoniBot

echo INFO - Starting MoniBot stop process

REM Step1: Check and read PID file
set "pid_file=config\pid.txt"
set "target_pid="

if exist "%pid_file%" (
    echo INFO - PID file found
    for /f %%i in (%pid_file%) do set target_pid=%%i
    echo INFO - Process ID from PID file: !target_pid!
) else (
    echo WARNING - PID file not found
    goto :fallback_method
)

REM Step2: Check process existence
if defined target_pid (
    tasklist /FI "PID eq !target_pid!" 2>nul | find "!target_pid!" >nul
    if errorlevel 1 (
        echo ERROR - Process !target_pid! does not exist
        goto :cleanup_pidfile
    ) else (
        echo INFO - Process !target_pid! confirmed
    )
) else (
    echo ERROR - PID file empty or invalid
    goto :fallback_method
)

REM Step3: Send termination signal
echo INFO - Sending termination signal to process !target_pid!
echo INFO - Attempting graceful shutdown

taskkill /PID !target_pid! >nul 2>&1
if not errorlevel 1 (
    echo INFO - Termination signal sent
) else (
    echo WARNING - Failed to send termination signal
)

REM Step4: Wait for process termination (max 3 seconds)
echo INFO - Waiting for process termination (max 3 seconds)
set /a max_wait=3
set /a counter=0

:wait_loop
ping localhost -n 2 >nul
set /a counter+=1

tasklist /FI "PID eq !target_pid!" 2>nul | find "!target_pid!" >nul
if errorlevel 1 (
    echo INFO - Process !target_pid! terminated successfully
    goto :cleanup_pidfile
)

if !counter! geq !max_wait! (
    echo WARNING - Process !target_pid! did not terminate within 3 seconds
    goto :force_termination
)

goto :wait_loop

:force_termination
echo INFO - Executing force termination
taskkill /PID !target_pid! /F >nul 2>&1
if not errorlevel 1 (
    echo INFO - Process !target_pid! force terminated
) else (
    echo ERROR - Force termination failed
)
ping localhost -n 2 >nul
goto :cleanup_pidfile

:cleanup_pidfile
if exist "%pid_file%" (
    del "%pid_file%" >nul 2>&1
    if not exist "%pid_file%" (
        echo INFO - PID file deleted
    ) else (
        echo WARNING - Failed to delete PID file
    )
)
goto :cleanup_browsers

:fallback_method
echo INFO - Executing fallback method
echo INFO - Searching for main_orchestrator.py process

set "found_process="
for /f "tokens=2" %%i in ('tasklist /fi "imagename eq python.exe" /fo table /nh 2^>nul') do (
    wmic process where "ProcessID=%%i" get CommandLine 2>nul | find "main_orchestrator.py" > nul
    if not errorlevel 1 (
        echo INFO - main_orchestrator.py process found: PID %%i
        set found_process=%%i
        taskkill /PID %%i /F >nul 2>&1
        if not errorlevel 1 (
            echo INFO - Process %%i terminated
        ) else (
            echo ERROR - Failed to terminate process %%i
        )
    )
)

if not defined found_process (
    echo INFO - main_orchestrator.py process not found
)

:cleanup_browsers
echo INFO - Terminating playwright related browser processes

for /f "tokens=2" %%i in ('tasklist /fi "imagename eq msedge.exe" /fo table /nh 2^>nul') do (
    wmic process where "ProcessID=%%i" get CommandLine 2>nul | find "playwright" > nul
    if not errorlevel 1 (
        echo INFO - Terminating playwright Edge process %%i
        taskkill /PID %%i /F >nul 2>&1
    )
)

echo INFO - Browser process cleanup completed

:final_check
echo.
echo ========================================
echo   Final Result Check
echo ========================================

tasklist /fi "imagename eq python.exe" 2>nul | find "python.exe" >nul
if errorlevel 1 (
    echo INFO - All Python processes terminated
) else (
    echo INFO - Some Python processes remain
)

if exist "%pid_file%" (
    echo WARNING - PID file still exists
) else (
    echo INFO - PID file successfully deleted
)

echo.
echo INFO - MoniBot stop process completed
echo ========================================

REM Auto close after 3 seconds
echo.
echo Window will close in 3 seconds...
set /a close_wait=3
set /a close_counter=0

:close_countdown
ping localhost -n 2 >nul
set /a close_counter+=1

echo Remaining !close_counter! seconds...

if !close_counter! geq !close_wait! (
    echo Closing window
    goto :exit_now
)

goto :close_countdown

:exit_now
exit