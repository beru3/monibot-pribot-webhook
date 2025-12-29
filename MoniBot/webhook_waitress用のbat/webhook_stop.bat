@echo off
chcp 65001 > nul
REM =======================================================
REM Webhookサーバー自動停止スクリプト（スケジュール用）
REM =======================================================

echo ========================================
echo   Webhookサーバー強制停止処理
echo ========================================

echo 🛑 強制停止処理を開始...

REM 1. ポート5000を使用するプロセスを強制終了
echo 1. ポート5000使用プロセスを強制終了中...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5000') do (
    echo   PID %%a を強制終了中...
    taskkill /PID %%a /F >nul 2>&1
)

REM 2. waitressプロセスを強制終了
echo 2. waitressプロセスを強制終了中...
for /f "tokens=2" %%i in ('tasklist /fi "imagename eq python.exe" /fo table /nh 2^>nul') do (
    wmic process where "ProcessID=%%i" get CommandLine 2>nul | find "waitress" > nul
    if not errorlevel 1 (
        echo   waitressプロセス %%i を終了中...
        taskkill /PID %%i /F >nul 2>&1
    )
)

REM 3. webhook_serverプロセスを強制終了
echo 3. webhook_serverプロセスを強制終了中...
for /f "tokens=2" %%i in ('tasklist /fi "imagename eq python.exe" /fo table /nh 2^>nul') do (
    wmic process where "ProcessID=%%i" get CommandLine 2>nul | find "webhook_server" > nul
    if not errorlevel 1 (
        echo   webhook_serverプロセス %%i を終了中...
        taskkill /PID %%i /F >nul 2>&1
    )
)

REM 4. プロセス終了待機
timeout /t 2 /nobreak >nul

REM 5. 結果確認と表示
echo.
echo 📊 停止結果確認:
netstat -ano | findstr :5000 >nul
if errorlevel 1 (
    echo ✅ ポート5000が解放されました
) else (
    echo ❌ ポート5000がまだ使用中です
)

echo.
echo ========================================
echo   強制停止処理完了
echo ========================================

REM 3秒後に自動終了
echo 3秒後にウィンドウを閉じます...
timeout /t 3 /nobreak >nul

REM ウィンドウを閉じる
exit