@echo off
chcp 65001 > nul

REM 変数設定 - Pythonファイル名
set WEBHOOK_SCRIPT=webhook_server.py

echo %WEBHOOK_SCRIPT% を実行しているサーバーを停止しています...

REM Python関連のプロセスを検索し、指定されたスクリプトを実行しているプロセスを終了
for /f "tokens=2" %%i in ('tasklist /fi "imagename eq python3.11.exe" /fo table /nh') do (
    wmic process where "ProcessID=%%i" get CommandLine | find "%WEBHOOK_SCRIPT%" > nul
    if not errorlevel 1 (
        echo プロセスID: %%i を終了します...
        taskkill /PID %%i /F
        echo サーバーを停止しました。
    )
)

REM 念のためPythonプロセスをチェック（複数ある場合に備えて）
for /f "tokens=2" %%i in ('tasklist /fi "imagename eq python.exe" /fo table /nh') do (
    wmic process where "ProcessID=%%i" get CommandLine | find "%WEBHOOK_SCRIPT%" > nul
    if not errorlevel 1 (
        echo プロセスID: %%i を終了します...
        taskkill /PID %%i /F
        echo サーバーを停止しました。
    )
)

REM wmicエラーを回避するためのより単純な方法
echo.
echo 別の方法でPythonプロセスを確認しています...
for /f "tokens=1,2" %%a in ('tasklist /v /fi "imagename eq python3.11.exe" /fo csv ^| findstr /i "%WEBHOOK_SCRIPT%"') do (
    echo 追加プロセスを検出: %%b を終了します...
    taskkill /PID %%b /F
)

for /f "tokens=1,2" %%a in ('tasklist /v /fi "imagename eq python.exe" /fo csv ^| findstr /i "%WEBHOOK_SCRIPT%"') do (
    echo 追加プロセスを検出: %%b を終了します...
    taskkill /PID %%b /F
)

echo.
echo 処理が完了しました。