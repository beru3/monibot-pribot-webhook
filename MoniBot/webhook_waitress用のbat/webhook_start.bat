@echo off
REM =======================================================
REM Webhookサーバー起動スクリプト（Y/N確認完全回避版）
REM =======================================================

REM 文字コードをUTF-8に設定
chcp 65001 > nul

REM 作業ディレクトリに移動
cd /d C:\Users\monibot\Desktop\wk\MoniBot\webhook_root

echo ========================================
echo   Webhookサーバー起動中...
echo ========================================
echo.
echo 📋 サーバー設定:
echo    ホスト名: SVR-MONIBOT
echo    IPアドレス: 192.168.250.220
echo    待受ホスト: 0.0.0.0 (全IP対応)
echo    ポート: 5000
echo    スレッド数: 8
echo.
echo 🌐 アクセスURL (SVR-MONIBOT):
echo    ダッシュボード: http://192.168.250.220:5000/webhook_monitor
echo    テストクライアント: http://192.168.250.220:5000/webhook_client
echo    Webhookエンドポイント: http://192.168.250.220:5000/webhook/new_ticket
echo.
echo 🌐 ローカルアクセスURL:
echo    ダッシュボード: http://localhost:5000/webhook_monitor
echo    テストクライアント: http://localhost:5000/webhook_client
echo    Webhookエンドポイント: http://localhost:5000/webhook/new_ticket
echo.
echo 🚀 サーバーを起動します...
echo    ウィンドウを閉じるとサーバーが停止します
echo.
echo ========================================

REM waitressでサーバー起動（1ウィンドウ版）
python -m waitress --host=0.0.0.0 --port=5000 --threads=8 webhook_server:app

REM サーバー停止時の処理（自動で到達）
echo.
echo ========================================
echo   サーバーが停止しました
echo ========================================
echo.
echo 3秒後にウィンドウを閉じます...
timeout /t 3 /nobreak >nul
exit