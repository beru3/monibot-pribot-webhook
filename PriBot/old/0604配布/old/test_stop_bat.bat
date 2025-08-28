@echo off
setlocal enabledelayedexpansion

echo ====================================
echo PriBot Stop Test Script
echo ====================================

REM Test lock and PID file paths
set LOCK_FILE=C:\Users\miyake2106\Desktop\wk\PriBot\pribot_test.lock
set PID_FILE=C:\Users\miyake2106\Desktop\wk\PriBot\pribot_test_pids.txt

echo テスト停止実行時刻: %DATE% %TIME%
echo.

echo [INFO] テスト用停止スクリプトを実行します
echo [INFO] 実際のPriBotには影響しません
echo.

REM Method 1: Target the test CMD process directly
echo ====== Method 1: CMDプロセス検索・停止 ======
set FOUND_CMD=0
for /f "tokens=1" %%i in ('wmic process where "CommandLine like '%%PriBot_Test_%%' and Name='cmd.exe'" get ProcessId /format:value 2^>nul ^| find "ProcessId="') do (
    set FULL_LINE=%%i
    set CMD_PID=!FULL_LINE:ProcessId=!
    set CMD_PID=!CMD_PID: =!
    if !CMD_PID! gtr 0 (
        echo [FOUND] テスト用CMD PID: !CMD_PID!
        echo [ACTION] CMDプロセスを停止中...
        taskkill /F /T /PID !CMD_PID!
        echo [RESULT] CMD終了コマンド実行: errorlevel = !errorlevel!
        set FOUND_CMD=1
        
        REM Wait and verify
        timeout /t 2 >nul
        tasklist /fi "PID eq !CMD_PID!" | find "!CMD_PID!" >nul 2>&1
        if !errorlevel! equ 0 (
            echo [WARNING] CMD still running, trying WMIC delete...
            wmic process where "ProcessId=!CMD_PID!" delete
        ) else (
            echo [SUCCESS] CMD process !CMD_PID! terminated (window should close)
        )
    )
)

if !FOUND_CMD! equ 0 (
    echo [INFO] テスト用CMDプロセスは見つかりませんでした
)

echo.

REM Method 2: Target test Python process
echo ====== Method 2: Pythonプロセス検索・停止 ======
set FOUND_PYTHON=0
for /f "tokens=1" %%i in ('wmic process where "CommandLine like '%%test_long_running.py%%' and Name='python.exe'" get ProcessId /format:value 2^>nul ^| find "ProcessId="') do (
    set FULL_LINE=%%i
    set PYTHON_PID=!FULL_LINE:ProcessId=!
    set PYTHON_PID=!PYTHON_PID: =!
    if !PYTHON_PID! gtr 0 (
        echo [FOUND] テスト用Python PID: !PYTHON_PID!
        echo [ACTION] Pythonプロセスを停止中...
        taskkill /F /T /PID !PYTHON_PID!
        echo [RESULT] Python終了コマンド実行: errorlevel = !errorlevel!
        set FOUND_PYTHON=1
        
        REM Wait and verify
        timeout /t 2 >nul
        tasklist /fi "PID eq !PYTHON_PID!" | find "!PYTHON_PID!" >nul 2>&1
        if !errorlevel! equ 0 (
            echo [WARNING] Python still running, trying WMIC delete...
            wmic process where "ProcessId=!PYTHON_PID!" delete
        ) else (
            echo [SUCCESS] Python process !PYTHON_PID! terminated
        )
    )
)

if !FOUND_PYTHON! equ 0 (
    echo [INFO] テスト用Pythonプロセスは見つかりませんでした
)

echo.

REM Method 3: Brute force - kill any process with test_long_running.py in command line
echo ====== Method 3: ブルートフォース停止 ======
set BRUTE_COUNT=0
for /f "tokens=2" %%i in ('wmic process where "CommandLine like '%%test_long_running.py%%'" get ProcessId /format:value 2^>nul ^| find "ProcessId="') do (
    set /a BRUTE_PID=%%i 2>nul
    if !BRUTE_PID! gtr 0 (
        echo [ACTION] ブルートフォース終了 PID: !BRUTE_PID!
        taskkill /F /T /PID !BRUTE_PID!
        wmic process where "ProcessId=!BRUTE_PID!" delete >nul 2>&1
        set /a BRUTE_COUNT+=1
    )
)

if !BRUTE_COUNT! gtr 0 (
    echo [INFO] ブルートフォースで !BRUTE_COUNT! 個のプロセスを停止
) else (
    echo [INFO] ブルートフォース対象のプロセスはありませんでした
)

echo.

REM Method 4: PowerShell backup method
echo ====== Method 4: PowerShell停止 ======
echo [ACTION] PowerShellバックアップ停止を実行中...
powershell -Command "Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like '*test_long_running.py*' } | ForEach-Object { Write-Host '[POWERSHELL] Killing PID' $_.ProcessId; try { $_.Terminate(); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } catch { } }" 2>nul

echo.

REM Clean up test files
echo ====== ファイルクリーンアップ ======
if exist "%LOCK_FILE%" (
    echo [ACTION] テスト用ロックファイル削除中...
    del "%LOCK_FILE%" >nul 2>&1
    attrib -r -h -s "%LOCK_FILE%" >nul 2>&1
    del /f /q "%LOCK_FILE%" >nul 2>&1
    powershell -Command "Remove-Item '%LOCK_FILE%' -Force -ErrorAction SilentlyContinue" >nul 2>&1
    
    if exist "%LOCK_FILE%" (
        echo [WARNING] ロックファイル削除失敗: %LOCK_FILE%
    ) else (
        echo [SUCCESS] ロックファイル削除成功
    )
) else (
    echo [INFO] テスト用ロックファイルは存在しませんでした
)

if exist "%PID_FILE%" (
    echo [ACTION] テスト用PIDファイル削除中...
    del "%PID_FILE%" >nul 2>&1
    attrib -r -h -s "%PID_FILE%" >nul 2>&1
    del /f /q "%PID_FILE%" >nul 2>&1
    powershell -Command "Remove-Item '%PID_FILE%' -Force -ErrorAction SilentlyContinue" >nul 2>&1
    
    if exist "%PID_FILE%" (
        echo [WARNING] PIDファイル削除失敗: %PID_FILE%
    ) else (
        echo [SUCCESS] PIDファイル削除成功
    )
) else (
    echo [INFO] テスト用PIDファイルは存在しませんでした
)

echo.

REM Final verification
echo ====== 最終確認 ======
timeout /t 3 >nul

wmic process where "CommandLine like '%%test_long_running.py%%'" get ProcessId /format:value 2>nul | find "ProcessId=" >nul 2>&1
if !errorlevel! equ 0 (
    echo [WARNING] まだ実行中のテストプロセスがあります:
    wmic process where "CommandLine like '%%test_long_running.py%%'" get ProcessId,CommandLine
    echo.
    echo [MANUAL] テストウィンドウが開いている場合は、Xボタンで手動で閉じてください
    set FINAL_RESULT=PARTIAL
) else (
    echo [SUCCESS] すべてのテストプロセスが停止されました
    echo [SUCCESS] テストウィンドウは閉じられました
    set FINAL_RESULT=SUCCESS
)

echo.

REM Test result summary
echo ====================================
echo テスト結果サマリー
echo ====================================

echo テスト対象プロセス:
if !FOUND_CMD! equ 1 (
    echo ✅ CMD プロセス: 発見・停止
) else (
    echo ❌ CMD プロセス: 見つからず
)

if !FOUND_PYTHON! equ 1 (
    echo ✅ Python プロセス: 発見・停止
) else (
    echo ❌ Python プロセス: 見つからず
)

echo.
echo 停止テスト結果:
if "!FINAL_RESULT!"=="SUCCESS" (
    echo ✅ 完全成功: すべてのテストプロセスが停止
    echo ✅ 停止スクリプトは正常に動作します
    echo.
    echo [評価] 本番のPriBot停止も正常に実行できると予想されます
) else (
    echo ⚠️ 部分成功: 一部プロセスが残存している可能性
    echo ⚠️ 手動での確認・停止が必要です
    echo.
    echo [評価] 本番でも手動での補助が必要になる可能性があります
)

echo.
echo ====================================
echo テスト停止スクリプト完了
echo ====================================

echo.
echo Press any key to close this window...
pause >nul