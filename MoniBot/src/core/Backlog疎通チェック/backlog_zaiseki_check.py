import os
import sys
import requests
import configparser

# プロジェクトルートへのパスを追加
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # 一つ上の階層を追加
sys.path.append(project_root)

# configの読み込み
config = configparser.ConfigParser()
config_path = os.path.join(project_root, 'config', 'config.ini')

# デバッグ用の出力
print(f"設定ファイルのパス: {config_path}")
print(f"ファイルが存在するか: {os.path.exists(config_path)}")

if not config.read(config_path, encoding='utf-8'):
    raise FileNotFoundError(f"設定ファイルが見つかりません: {config_path}")

print("設定ファイルの内容:")
print(config.sections())

space_name = config['backlog']['space_name']
api_key = config['backlog']['api_key']
project_id = config['backlog']['staff_project_id']  # 在席管理プロジェクトのID

# Backlog APIのエンドポイント
endpoint = f"https://{space_name}.backlog.com/api/v2/projects/{project_id}/statuses"
params = {
    "apiKey": api_key
}

# ステータス一覧を取得
response = requests.get(endpoint, params=params)
statuses = response.json()

# 結果表示
print("\n在席管理プロジェクトのステータス一覧:")
for status in statuses:
    print(f"ID: {status['id']}, 名前: {status['name']}")