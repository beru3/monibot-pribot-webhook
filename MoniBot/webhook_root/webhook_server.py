#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, request, Response, stream_with_context, render_template, jsonify, send_from_directory, redirect
import json
import time
import threading
import os
from datetime import datetime
import queue
import uuid

app = Flask(__name__)

# イベントキューとクライアント管理
event_queue = queue.Queue(maxsize=100)  # メモリ使用量制限のためにキューサイズを制限
clients = {}  # クライアントIDをキーとしたSSEクライアント管理用辞書

# 静的ファイル配信用のルート設定
@app.route('/assets/<path:path>')
def send_assets(path):
    """アセットファイルの配信"""
    return send_from_directory('assets', path)

@app.route('/')
def index():
    """ホームページへリダイレクト"""
    return render_template('index.html')

# 重要: .htmlサフィックス付きのURLも処理する
@app.route('/index.html')
def index_html():
    return redirect('/')

@app.route('/status')
def status_page():
    """ステータスページ配信"""
    return render_template('status.html')

@app.route('/status.html')
def status_html():
    return redirect('/status')

@app.route('/webhook_monitor')
def monitor():
    """ウェブフックモニターページ配信"""
    return render_template('webhook_monitor.html')

@app.route('/webhook_monitor.html')
def monitor_html():
    return redirect('/webhook_monitor')

@app.route('/webhook_client')
def client():
    """ウェブフックテストクライアントページ配信"""
    return render_template('webhook_client.html')

@app.route('/webhook_client.html')
def client_html():
    return redirect('/webhook_client')

@app.route('/api/stats')
def get_stats():
    """サーバー統計情報API"""
    return jsonify({
        "active_clients": len(clients),
        "events_in_queue": event_queue.qsize(),
        "server_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/events')
def events():
    """SSEエンドポイント - リアルタイムウェブフック監視用"""
    client_id = str(uuid.uuid4())
    
    def event_stream():
        # 初期接続メッセージ送信
        yield f"id: {client_id}\n"
        yield "event: connected\n"
        yield f"data: {json.dumps({'client_id': client_id, 'message': 'ウェブフックストリームに接続しました'})}\n\n"
        
        # このクライアント用のキューを作成
        clients[client_id] = queue.Queue()
        
        try:
            # 既存の履歴イベントを送信（最大20件）
            history_size = min(event_queue.qsize(), 20)
            history = list(event_queue.queue)[-history_size:]
            
            for event in history:
                yield f"event: history\n"
                yield f"data: {json.dumps(event)}\n\n"
            
            # 新しいイベントを監視
            while True:
                try:
                    # ノンブロッキングでクライアント固有のキューを確認
                    event = clients[client_id].get(timeout=0.1)
                    yield f"event: webhook\n"
                    yield f"data: {json.dumps(event)}\n\n"
                except queue.Empty:
                    # キープアライブコメントを送信して接続を維持
                    yield ": keepalive\n\n"
                    time.sleep(5)  # 5秒ごとにチェック
        except GeneratorExit:
            # クライアント切断時の処理
            if client_id in clients:
                del clients[client_id]
                print(f"クライアント {client_id} が切断しました。アクティブクライアント: {len(clients)}")
    
    # SSEレスポンスの作成
    response = Response(stream_with_context(event_stream()),
                        content_type='text/event-stream')
    response.headers.add('Cache-Control', 'no-cache')
    # response.headers.add('Connection', 'keep-alive')
    
    print(f"新しいクライアント接続: {client_id}。 総クライアント数: {len(clients) + 1}")
    return response

@app.route('/webhook/new_ticket', methods=['POST', 'GET'])
def webhook():
    """チケット処理機能を強化したウェブフックエンドポイント"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    client_ip = request.remote_addr
    
    # リクエストメソッドとコンテンツタイプに基づいてデータを処理
    if request.method == 'POST':
        if request.is_json:
            data = request.json
        else:
            data = request.form.to_dict()
    else:  # GET
        data = request.args.to_dict()
    
    # 標準イベントとしてフォーマット
    event = {
        "timestamp": timestamp,
        "data": data,
        "source_ip": client_ip,
        "method": request.method,
        "event_id": str(uuid.uuid4())
    }
    
    # チケット関連イベントの特別処理
    if "event_type" in data and data["event_type"] in ["processing_ticket", "patient_registration", "appointment_scheduled"]:
        # フロントエンド処理用のチケットフラグを追加
        event["is_ticket"] = True
        
    # イベントキューに追加して全クライアントにブロードキャスト
    add_to_queue_and_broadcast(event)
    
    return jsonify({
        "status": "success",
        "message": "ウェブフックを受信し処理しました",
        "timestamp": timestamp,
        "clients": len(clients)
    })

def add_to_queue_and_broadcast(event):
    """イベントをキューに追加し、クライアントにブロードキャストするヘルパー関数"""
    try:
        # キューが満杯の場合は最古のアイテムを削除
        if event_queue.full():
            try:
                event_queue.get_nowait()
            except queue.Empty:
                pass
        event_queue.put(event)
        
        # 接続中の全クライアントにブロードキャスト
        for client_id, client_queue in clients.items():
            try:
                client_queue.put(event)
            except Exception as e:
                print(f"クライアント {client_id} への送信中にエラー: {e}")
    except Exception as e:
        print(f"イベントキューへの追加中にエラー: {e}")


def create_template_dir():
    """テンプレートディレクトリの作成と必要なファイルのチェック"""
    templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
    os.makedirs(templates_dir, exist_ok=True)
    
    # テンプレートの確認と作成
    templates = {
        'index.html': 'index.html',
        'status.html': 'status.html',
        'webhook_monitor.html': 'webhook_monitor.html',
        'webhook_client.html': 'webhook_client.html'
    }
    
    for template_name, source_file in templates.items():
        template_path = os.path.join(templates_dir, template_name)
        if not os.path.exists(template_path):
            # 現在のディレクトリにある既存のファイルをコピー
            source_path = os.path.join(os.path.dirname(__file__), source_file)
            if os.path.exists(source_path):
                with open(source_path, 'r', encoding='utf-8') as src:
                    with open(template_path, 'w', encoding='utf-8') as dest:
                        content = src.read()
                        # パスの修正: ./assets/ → /assets/
                        content = content.replace('./assets/', '/assets/')
                        # 内部リンクの修正は行わない（両方のパターンをサポートするため）
                        dest.write(content)
                print(f"{template_name}をtemplatesディレクトリにコピーしました")
            else:
                print(f"警告: {source_file}が見つかりませんでした")

def create_assets_dir():
    """assetsディレクトリの作成と必要なファイルのチェック"""
    assets_dir = os.path.join(os.path.dirname(__file__), 'assets')
    os.makedirs(assets_dir, exist_ok=True)
    
    # CSSファイルを作成
    css_files = {
        'webhook-monitor.css': """/* 追加のスタイル定義 */
.event-item {
    transition: all 0.3s ease;
}

.event-item:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
}

pre {
    font-family: 'Source Code Pro', Menlo, Monaco, Consolas, monospace;
    font-size: 0.875rem;
}

/* アニメーション */
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}

.fade-in {
    animation: fadeIn 0.3s ease-in-out;
}
""",
        'webhook-client.css': """/* ウェブフッククライアント専用スタイル */
textarea {
    font-family: 'Source Code Pro', Menlo, Monaco, Consolas, monospace;
    resize: vertical;
}

pre {
    font-family: 'Source Code Pro', Menlo, Monaco, Consolas, monospace;
    font-size: 0.875rem;
}

/* 送信結果のアニメーション */
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}

#result {
    animation: fadeIn 0.3s ease-in-out;
}

/* 自動送信ステータスのカウンター色 */
#auto-count {
    color: #2563eb; /* Tailwind の blue-600 */
}

/* カウントアップアニメーション */
@keyframes pulse {
    0% { transform: scale(1); }
    50% { transform: scale(1.05); }
    100% { transform: scale(1); }
}

.count-pulse {
    animation: pulse 0.5s ease-in-out;
}
"""
    }
    
    for filename, content in css_files.items():
        css_path = os.path.join(assets_dir, filename)
        if not os.path.exists(css_path):
            with open(css_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"{filename}を作成しました")

# サーバー起動関数
def start_server(host='0.0.0.0', port=8080):
    """ウェブフックサーバーを起動"""
    print(f"ウェブフックサーバーを起動: {host}:{port}")
    print(f"ダッシュボード: http://{host if host != '0.0.0.0' else 'localhost'}:{port}/webhook_monitor")
    print(f"テストクライアント: http://{host if host != '0.0.0.0' else 'localhost'}:{port}/webhook_client")
    print(f"ウェブフックエンドポイント: http://{host if host != '0.0.0.0' else 'localhost'}:{port}/webhook/new_ticket")
    
    app.run(host=host, port=port, threaded=True, debug=True)

if __name__ == '__main__':
    # 必要なディレクトリとファイルを確認・作成
    create_template_dir()
    create_assets_dir()
    
    # サーバー起動
    try:
        start_server()
    except KeyboardInterrupt:
        print("\nサーバーをシャットダウンします...")