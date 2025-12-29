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
print(config.sections())  # 読み込んだセクションを表示

space_name = config['backlog']['space_name']
api_key = config['backlog']['api_key']
project_id = config['backlog']['hospital_project_id']

# プロジェクトのキーを取得
project_endpoint = f"https://{space_name}.backlog.com/api/v2/projects/{project_id}"
project_params = {
    "apiKey": api_key
}

project_response = requests.get(project_endpoint, project_params)
project_info = project_response.json()
project_key = project_info['projectKey']

print(f"\nプロジェクト情報:")
print(f"プロジェクトキー: {project_key}")

# ステータス一覧を取得
status_endpoint = f"https://{space_name}.backlog.com/api/v2/projects/{project_id}/statuses"
status_params = {
    "apiKey": api_key
}

status_response = requests.get(status_endpoint, status_params)
statuses = status_response.json()

print("\nステータス一覧:")
for status in statuses:
    print(f"ID: {status['id']}, 名前: {status['name']}")

# 課題一覧を取得してissue keyを表示
issues_endpoint = f"https://{space_name}.backlog.com/api/v2/issues"
issues_params = {
    "apiKey": api_key,
    "projectId[]": project_id,
    "count": 100  # 取得する課題の最大数
}

issues_response = requests.get(issues_endpoint, issues_params)
issues = issues_response.json()

print("\n課題一覧:")
for issue in issues:
    print(f"IssueKey: {issue['issueKey']}, タイトル: {issue['summary']}")