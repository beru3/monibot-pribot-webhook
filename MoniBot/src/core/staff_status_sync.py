# src/core/staff_status_sync.py
import os
import sys

# プロジェクトルートへのパスを追加
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)

import requests
import mysql.connector
import configparser
from datetime import datetime
from typing import Optional, Dict, Any
import traceback

from src.utils.logger import LoggerFactory

# ロガーの初期化
logger = LoggerFactory.setup_logger('staff_status_sync')

# パス定義
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_DIR = os.path.join(SCRIPT_DIR, 'config')

def load_config():
    """INIファイルから設定情報を読み取る"""
    config = configparser.ConfigParser()
    config_path = os.path.join(CONFIG_DIR, 'config.ini')
   
    if os.path.exists(config_path):
        config.read(config_path, encoding='utf-8')
    else:
        logger.error("設定ファイルが見つかりません！")
   
    return config

def get_project_name(config: Dict[str, Any], project_id: str) -> str:
    """
    プロジェクト名を取得する関数
    
    Args:
        config: 設定情報
        project_id: プロジェクトID
        
    Returns:
        str: プロジェクト名
    """
    space_name = config['backlog']['space_name']
    api_key = config['backlog']['api_key']
    url = f"https://{space_name}.backlog.com/api/v2/projects/{project_id}"
    params = {
        "apiKey": api_key
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    project_data = response.json()
    return project_data['name']

def get_backlog_issues(config, project_id):
    """Backlogから課題を取得する関数"""
    space_name = config['backlog']['space_name']
    api_key = config['backlog']['api_key']
    url = f"https://{space_name}.backlog.com/api/v2/issues"
    params = {
        "apiKey": api_key,
        "projectId[]": project_id,
        "count": 100
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    
    # プロジェクト名を取得
    project_name = get_project_name(config, project_id)
    
    logger.debug(f"Backlog '{project_name}' (ID: {project_id}) から {len(response.json())} 件の課題を取得しました")
    return response.json()

def get_staff_category(issue):
    """Backlogの課題からカテゴリ（チーム）情報を取得"""
    try:
        categories = issue.get('category', [])
        team_categories = [cat['name'] for cat in categories if cat.get('name')]
        
        # カテゴリが空の場合のログ出力
        if not team_categories:
            logger.debug(f"チーム情報が設定されていません: {issue.get('issueKey', '不明')}")
        else:
            logger.debug(f"取得したチーム情報: {team_categories}")
            
        return team_categories
        
    except Exception as e:
        logger.error(f"カテゴリの取得中にエラーが発生しました: {e}")
        logger.debug(f"課題情報: {issue}")  # デバッグ用の詳細情報
        return []

def get_staff_status(config):
    """スタッフの状態とチーム所属を取得する関数"""
    attendance_project_id = config['backlog']['staff_project_id']
    billing_project_id = config['backlog']['billing_project_id']

    # logger.info("=== スタッフステータス取得開始 ===")
    
    # 在席管理プロジェクトのチケット取得
    attendance_issues = get_backlog_issues(config, attendance_project_id)
    # logger.info(f"在席管理チケット数: {len(attendance_issues)}")
    
    # 請求管理プロジェクトのチケット取得
    billing_issues = get_backlog_issues(config, billing_project_id)
    # logger.info(f"請求管理チケット数: {len(billing_issues)}")

    staff_status = {}
    
    # 在席管理プロジェクトの処理
    # logger.info("在席管理チケットの処理:")
    for issue in attendance_issues:
        if issue.get('assignee'):
            staff_id = issue['assignee']['id']
            status = '在席' if issue['status']['name'] == '在席' else '不在'
            staff_status[staff_id] = {
                'status': status, 
                'name': issue['assignee']['name'],
                'teams': get_staff_category(issue)
            }
            # logger.info(f"スタッフID: {staff_id}, 名前: {issue['assignee']['name']}, "
            #             f"ステータス: {status}, チケット: {issue.get('issueKey')}, "
            #             f"チケットステータス: {issue['status']['name']}")

    # 請求管理プロジェクトの処理中チケットを確認
    # logger.info("\n請求管理チケットの処理:")
    active_billing_staff = {}  # スタッフIDとチケット情報のマッピング
    for issue in billing_issues:
        if issue.get('assignee') and issue['status']['name'] == '処理中':
            staff_id = issue['assignee']['id']
            active_billing_staff[staff_id] = issue.get('issueKey')
            # logger.info(f"処理中チケット - スタッフID: {staff_id}, "
            #             f"名前: {issue['assignee']['name']}, "
            #             f"チケット: {issue.get('issueKey')}")

    # 処理中のスタッフのステータス更新
    # logger.info("\nステータス更新処理:")
    for staff_id in active_billing_staff:
        if staff_id in staff_status and staff_status[staff_id]['status'] == '在席':
            old_status = staff_status[staff_id]['status']
            staff_status[staff_id]['status'] = '在席(処理中)'
            # logger.info(f"ステータス更新 - スタッフID: {staff_id}, "
            #             f"名前: {staff_status[staff_id]['name']}, "
            #             f"旧ステータス: {old_status} -> 新ステータス: 在席(処理中), "
            #             f"関連チケット: {active_billing_staff[staff_id]}")

    # logger.info("\n=== 最終ステータス ===")
    # for staff_id, info in staff_status.items():
    #     logger.info(f"スタッフID: {staff_id}, 名前: {info['name']}, "
    #                 f"最終ステータス: {info['status']}, チーム: {info['teams']}")

    return staff_status

def update_staff_table(config, staff_status):
    """スタッフ情報をデータベースに更新する関数"""
    conn = None
    cursor = None
    try:
        conn = mysql.connector.connect(**config['mysql'])
        cursor = conn.cursor()
        
        for backlog_user_id, info in staff_status.items():
            # まず、スタッフが存在するか確認
            cursor.execute("""
                SELECT スタッフID 
                FROM tbl_staff 
                WHERE BacklogユーザーID = %s
            """, (backlog_user_id,))
            staff_result = cursor.fetchone()
            
            if staff_result:
                # 既存スタッフの更新
                staff_id = staff_result[0]
                cursor.callproc('update_staff_status', 
                            (backlog_user_id, info['name'], info['status'], datetime.now()))
                
                # チーム所属情報の更新
                cursor.execute("DELETE FROM tbl_staff_teams WHERE スタッフID = %s", (staff_id,))
                
                for team in info['teams']:
                    cursor.execute("""
                        INSERT INTO tbl_staff_teams (スタッフID, チーム)
                        VALUES (%s, %s)
                    """, (staff_id, team))
            else:
                # 新規スタッフの追加
                # まずスタッフ基本情報を追加
                cursor.callproc('update_staff_status', 
                            (backlog_user_id, info['name'], info['status'], datetime.now()))
                
                # 追加されたスタッフのIDを取得
                cursor.execute("""
                    SELECT スタッフID 
                    FROM tbl_staff 
                    WHERE BacklogユーザーID = %s
                """, (backlog_user_id,))
                new_staff = cursor.fetchone()
                
                if new_staff:
                    # チーム所属情報を追加
                    for team in info['teams']:
                        cursor.execute("""
                            INSERT INTO tbl_staff_teams (スタッフID, チーム)
                            VALUES (%s, %s)
                        """, (new_staff[0], team))
                    logger.info(f"新規スタッフを追加しました: {info['name']}, BacklogユーザーID: {backlog_user_id}")

        conn.commit()

    except mysql.connector.Error as e:
        if conn:
            conn.rollback()
        logger.error(f"データベース操作中にエラーが発生しました: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
            logger.debug("データベース接続を閉じました")

def main():
    try:
        logger.debug("スタッフステータスの同期を開始します")
        
        config = load_config()
        if config is None:
            logger.error("設定の読み込みに失敗しました")
            return

        staff_status = get_staff_status(config)
        if staff_status is None:
            logger.error("スタッフ状態の更新に失敗しました")
            return

        update_staff_table(config, staff_status)
        
        logger.debug("スタッフステータスの同期が完了しました")
    except requests.exceptions.RequestException as e:
        logger.error(f"Backlog APIへのリクエスト中にエラーが発生しました: {e}")
    except Exception as e:
        logger.error(f"予期せぬエラーが発生しました: {e}")
        logger.exception("スタックトレース:")

if __name__ == "__main__":
    main()