@echo off
setlocal enabledelayedexpansion

echo ====================================
echo PriBot Production Environment Test
echo ====================================

REM Environment test script path settings
set TEST_SCRIPT=C:\Users\miyake2106\Desktop\wk\PriBot\test_env_script.py
set PYTHON_EXE=C:\Users\miyake2106\AppData\Local\Programs\Python\Python311\python.exe

echo Test execution time: %DATE% %TIME%
echo.

REM Check if test script exists
if not exist "%TEST_SCRIPT%" (
    echo [ERROR] Test script not found: %TEST_SCRIPT%
    echo Please ensure test_environment.py is in the correct location
    pause
    exit /b 1
)

REM Check if Python executable exists
if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python executable not found: %PYTHON_EXE%
    echo Please verify Python installation path
    pause
    exit /b 1
)

echo [INFO] Test script: %TEST_SCRIPT%
echo [INFO] Python executable: %PYTHON_EXE%
echo.

echo Starting comprehensive environment test...
echo This will test:
echo - Python environment and modules
echo - Configuration file access
echo - Backlog API connectivity
echo - File system operations
echo - Network connectivity
echo - Process management capabilities
echo.

pause

REM Execute the test with explicit window title
title PriBot Environment Test
"%PYTHON_EXE%" "%TEST_SCRIPT%"

REM Capture exit code
set TEST_EXIT_CODE=%errorlevel%

echo.
echo ====================================
if %TEST_EXIT_CODE% equ 0 (
    echo [SUCCESS] Environment test completed successfully
    echo [SUCCESS] Production environment is ready
    echo [INFO] You can proceed with PriBot deployment
) else (
    echo [ERROR] Environment test failed
    echo [ERROR] Please review the test results above
    echo [INFO] Fix any issues before deploying PriBot
)
echo ====================================

echo.
echo Press any key to close this window...
pause >nul

exit /b %TEST_EXIT_CODE%