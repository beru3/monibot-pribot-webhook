# src/core/task_assignment.py
import os
import sys
import time

# プロジェクトルートへのパスを追加
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)

import requests
import mysql.connector
import configparser
from datetime import datetime
import subprocess
from typing import Optional, Dict, Any
from src.utils.logger import LoggerFactory

# ロガーの初期化
logger = LoggerFactory.setup_logger('task_assignment')
if not logger.handlers:  # ハンドラーが未設定の場合のみ初期化
    logger = LoggerFactory.setup_logger('task_assignment')
logger.propagate = False  # 確実に伝播を無効化

# パス定義
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_DIR = os.path.join(SCRIPT_DIR, 'config')

# チケットステータスの定義
TASK_STATUS_UNASSIGNED = '未割当'
TASK_STATUS_ASSIGNED = '割当済'
TASK_STATUS_REVERTED = '差戻'

def load_config():
    """INIファイルから設定情報を読み取る"""
    config = configparser.ConfigParser()
    config_path = os.path.join(CONFIG_DIR, 'config.ini')
   
    if os.path.exists(config_path):
        config.read(config_path, encoding='utf-8')
    else:
        logger.error("設定ファイルが見つかりません！")
   
    return config

def get_team_pending_accounts(cursor):
    """チームごとの未処理タスクを取得"""
    try:
        # NULLパラメータを明示的に渡す
        args = (None,)
        cursor.callproc('get_team_pending_accounts', args)
        
        # 結果の取得
        for result in cursor.stored_results():
            pending_accounts = result.fetchall()
            if pending_accounts:
                logger.debug(f"未処理タスクを {len(pending_accounts)} 件取得しました")
            else:
                logger.info("未処理タスクはありません")
            return pending_accounts
        return []
    except mysql.connector.Error as e:
        logger.error(f"未処理タスクの取得中にエラーが発生しました: {e}")
        raise

def get_reverted_tickets(config):
    """差し戻しステータスのチケットを取得"""
    try:
        space_name = config['backlog']['space_name']
        api_key = config['backlog']['api_key']
        project_id = config['backlog']['billing_project_id']

        # Backlog APIのエンドポイント
        endpoint = f"https://{space_name}.backlog.com/api/v2/issues"
        params = {
            "apiKey": api_key,
            "projectId[]": project_id,
            "statusId[]": "262863",  # 差し戻しのステータスID
        }

        response = requests.get(endpoint, params=params)
        response.raise_for_status()
        return response.json()

    except Exception as e:
        logger.error(f"差し戻しチケットの取得中にエラーが発生: {e}")
        return []

def update_staff_status_in_backlog(config, backlog_user_id):
    """Backlogの在席管理プロジェクトのステータスを不在に更新"""
    try:
        space_name = config['backlog']['space_name']
        api_key = config['backlog']['api_key']
        project_id = config['backlog']['staff_project_id']
        status_id_not_available = "242353"  # 不在のステータスID

        # 該当ユーザーの在席管理チケットを取得
        issues_url = f"https://{space_name}.backlog.com/api/v2/issues"
        params = {
            "apiKey": api_key,
            "projectId[]": project_id,
            "assigneeId[]": backlog_user_id,
        }
        
        response = requests.get(issues_url, params=params)
        response.raise_for_status()
        issues = response.json()

        if issues:
            issue = issues[0]
            
            # すでに不在の場合は更新をスキップ
            if issue['status']['id'] == int(status_id_not_available):
                logger.info(f"スタッフはすでに不在状態です: ユーザーID {backlog_user_id}")
                return True

            # ステータスを不在に更新
            update_url = f"{issues_url}/{issue['id']}"
            update_params = {
                "apiKey": api_key,
                "statusId": status_id_not_available
            }
            
            response = requests.patch(update_url, params=update_params)
            response.raise_for_status()
            logger.info(f"Backlogの在席状態を不在に更新しました: ユーザーID {backlog_user_id}")
            return True
        else:
            logger.error(f"在席管理チケットが見つかりません: ユーザーID {backlog_user_id}")
            return False
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Backlog API リクエストエラー: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"レスポンス内容: {e.response.content}")
        return False
    except Exception as e:
        logger.error(f"Backlogステータス更新中にエラー: {e}")
        return False

def update_billing_ticket_status(config, ticket_id):
    """請求管理の差し戻しチケットのステータスを差し戻し済みに更新"""
    try:
        space_name = config['backlog']['space_name']
        api_key = config['backlog']['api_key']
        status_id_reverted = "263209"  # 差し戻し済みのステータスID

        # チケットのステータスを更新
        issues_url = f"https://{space_name}.backlog.com/api/v2/issues/{ticket_id}"
        update_params = {
            "apiKey": api_key,
            "statusId": status_id_reverted
        }
        
        response = requests.patch(issues_url, params=update_params)
        response.raise_for_status()
        logger.info(f"請求管理チケット {ticket_id} のステータスを差し戻し済みに更新しました")
        return True
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Backlog API リクエストエラー: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"レスポンス内容: {e.response.content}")
        return False
    except Exception as e:
        logger.error(f"請求管理チケットの更新中にエラー: {e}")
        return False

def handle_reverted_ticket(cursor, ticket, conn, config):
    """差し戻しチケットの処理"""
    try:
        # BacklogユーザーIDからスタッフIDを取得
        backlog_user_id = ticket['assignee']['id']
        cursor.execute("""
            SELECT スタッフID 
            FROM tbl_staff 
            WHERE BacklogユーザーID = %s
        """, (str(backlog_user_id),))
        
        staff_result = cursor.fetchone()
        if not staff_result:
            logger.error(f"BacklogユーザーID {backlog_user_id} に対応するスタッフが見つかりません")
            return
            
        staff_id = staff_result[0]
        ticket_id = ticket['issueKey']
        
        # revert_assignmentプロシージャを呼び出し
        assignment_id = get_assignment_id(cursor, ticket_id)
        
        if assignment_id:
            cursor.execute("START TRANSACTION")
            
            try:
                # 1. revert_assignmentプロシージャ実行
                cursor.callproc('revert_assignment', (staff_id, assignment_id, ticket_id))
                
                # 2. Backlogの在席状態を不在に更新
                backlog_status_updated = update_staff_status_in_backlog(config, backlog_user_id)
                # backlog_status_updated = update_backlog_status(config, backlog_user_id)
                if not backlog_status_updated:
                    logger.warning(f"Backlogの在席状態の更新に失敗しました: ユーザーID {backlog_user_id}")

                # 3. 請求管理チケットのステータスを差し戻し済みに更新
                billing_status_updated = update_billing_ticket_status(config, ticket_id)
                if not billing_status_updated:
                    logger.warning(f"請求管理チケット {ticket_id} のステータス更新に失敗しました")
                
                cursor.execute("COMMIT")
                logger.info(f"チケット {ticket_id} の差し戻し処理が完了しました")
                logger.info(f"スタッフID {staff_id} のステータスを不在に更新しました")
                
            except Exception as e:
                cursor.execute("ROLLBACK")
                logger.error(f"差し戻し処理中にエラー発生: {e}")
                raise e
                
    except KeyError as e:
        logger.error(f"チケット情報の取得中にエラー: キー {e} が見つかりません")
        logger.debug(f"チケット情報: {ticket}")
    except Exception as e:
        logger.error(f"差し戻し処理中にエラー: {e}")

def get_assignment_id(cursor, ticket_number):
    """
    Backlogチケット番号から割り当てIDを取得する
    
    Args:
        cursor: データベースカーソル
        ticket_number: Backlogチケット番号
        
    Returns:
        int: 割り当てID
        None: 割り当てが見つからない場合
    """
    try:
        cursor.execute("""
            SELECT 割り当てID 
            FROM tbl_assignmenthistory 
            WHERE Backlogチケット番号 = %s
            ORDER BY 割り当て時間 DESC 
            LIMIT 1
        """, (ticket_number,))
        
        result = cursor.fetchone()
        return result[0] if result else None
        
    except Exception as e:
        logger.error(f"割り当てID取得中にエラー: {e}")
        return None

def update_billing_task_status_in_backlog(conn, config, account_info, staff_info):
# def update_backlog_status(conn, config, account_info, staff_info):
    """Backlogのチケットステータスを更新"""
    space_name = config['backlog']['space_name']
    api_key = config['backlog']['api_key']
    
    # チケット番号を取得
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT Backlogチケット番号
        FROM tbl_pendingaccounts
        WHERE 会計ID = %s
    """, (account_info[0],))
    result = cursor.fetchone()
    cursor.close()
    
    if not result or not result['Backlogチケット番号']:
        logger.error(f"会計ID {account_info[0]} のBacklogチケット番号が見つかりません")
        return False
    
    ticket_number = result['Backlogチケット番号']
    
    # 処理中ステータスのID
    in_progress_status_id = "2"  # Backlogの処理中ステータスID
    
    # チケットの更新
    endpoint = f"https://{space_name}.backlog.com/api/v2/issues/{ticket_number}"
    params = {
        "apiKey": api_key,
        "statusId": in_progress_status_id,
        "assigneeId": staff_info[2]  # BacklogユーザーID
    }
    
    try:
        response = requests.patch(endpoint, params=params)
        response.raise_for_status()
        # logger.info(f"Backlogチケット {ticket_number} のステータスを更新しました")
        return True
    except Exception as e:
        logger.error(f"Backlogチケットの更新中にエラー: {str(e)}")
        return False

def get_hospital_info(conn, hospital_id):
    '''病院情報を取得する'''
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.callproc('get_hospital_info', (hospital_id,))
        for result in cursor.stored_results():
            hospital_info = result.fetchone()
        
        if hospital_info:
            return hospital_info
        else:
            logger.warning(f"病院ID {hospital_id} に対応する情報が見つかりません")
            return {"病院名": "不明な病院", "電子カルテ名": "CLIUS"}  # デフォルト値を設定
    except mysql.connector.Error as e:
        logger.error(f"病院情報の取得中にエラーが発生しました: {e}")
        return {"病院名": "エラー", "電子カルテ名": "CLIUS"}  # エラー時もデフォルト値を設定
    finally:
        cursor.close()

def update_databases(conn, cursor, account_id, staff_id, backlog_issue_id):
    try:
        # デバッグログでbacklog_issue_idを確認
        logger.debug(f"バックログチケットID: {backlog_issue_id}")
        
        # backlog_issue_idがNoneの場合、tbl_pendingaccountsから取得
        if not backlog_issue_id:
            cursor.execute("""
                SELECT Backlogチケット番号
                FROM tbl_pendingaccounts
                WHERE 会計ID = %s
            """, (account_id,))
            result = cursor.fetchone()
            backlog_issue_id = result[0] if result else 'Unknown'
            logger.debug(f"会計ID {account_id} のバックログチケットIDを取得: {backlog_issue_id}")

        # 差し戻しタスクかどうかを確認し、元チケット番号を取得
        cursor.execute("""
            SELECT Backlogチケット番号
            FROM tbl_assignmenthistory
            WHERE 会計ID = %s AND 差戻時間 IS NOT NULL
            ORDER BY 差戻時間 DESC
            LIMIT 1
        """, (account_id,))
        result = cursor.fetchone()
        original_ticket_id = result[0] if result else None

        # プロシージャ呼び出し（元チケット番号を追加）
        cursor.callproc('update_assignment', (
            account_id,
            staff_id,
            str(backlog_issue_id),
            original_ticket_id
        ))
        conn.commit()
        # logger.info(f"データベースが正常に更新されました: 会計ID={account_id}, BacklogチケットID={backlog_issue_id}")
    except mysql.connector.Error as e:
        logger.error(f"データベース更新中にエラーが発生しました: {e}")
        conn.rollback()


def sync_staff_status():
    try:
        # スクリプトの絶対パスを使用
        script_dir = os.path.dirname(os.path.abspath(__file__))
        staff_status_sync_path = os.path.join(script_dir, "staff_status_sync.py")
        
        subprocess.run([sys.executable, staff_status_sync_path], check=True)
        logger.debug("スタッフステータスの同期が完了しました")
    except subprocess.CalledProcessError as e:
        logger.error(f"スタッフステータスの同期中にエラーが発生しました: {e}")
    except FileNotFoundError:
        logger.error(f"staff_status_sync.pyファイルが見つかりません パス: {staff_status_sync_path}")

def get_acquisition_time_from_db(conn, account_id):
    """DBから実際の取得時間（作成時間）を取得"""
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 作成時間 FROM tbl_pendingaccounts WHERE 会計ID = %s", (account_id,))
        result = cursor.fetchone()
        return result[0] if result else None
    except Exception as e:
        logger.error(f"DB取得時間の取得エラー: {e}")
        return None
    finally:
        cursor.close()

def send_webhook_notification(config, staff_info, ticket_number, account_id, hospital_name, patient_id, hospital_info=None):
    """タスク割り当て完了時にWebhookサーバーに通知を送信する（DB作成時間使用版）"""
    try:
        # Webhookサーバーの設定を読み込む
        webhook_url = config.get('webhook', 'url', fallback='http://localhost:5000/webhook/new_ticket')
        
        # ★修正: DBから実際の取得時間を取得
        # グローバルなconnectionを取得する必要があります
        # process_pending_accounts関数内でconnectionを渡すように修正が必要
        
        # 現在の時刻（タスク割り当て時刻）
        assignment_time = datetime.now().isoformat()
        
        # 送信するデータを準備
        data = {
            "event_type": "processing_ticket",  # Web画面での検出キー
            "timestamp": assignment_time,  # タスク割り当て時刻
            
            # Backlogチケット情報
            "id": ticket_number,
            "issueKey": ticket_number,
            "assigneeId": str(staff_info[2]),  # BacklogユーザーIDを文字列に変換
            
            # プロジェクト情報
            "projectId": config['backlog']['billing_project_id'],
            "summary": f"{hospital_name} - {patient_id}",
            
            # ★修正: DBの作成時間を使用した説明文
            # この部分は後で acquisition_time を使って生成
            "description": "",  # 一旦空にして後で設定
            
            # ステータス情報
            "status": {
                "id": 2,  # 処理中ステータスID
                "name": "処理中"
            }
        }
        
        # POSTリクエストでWebhookを送信
        response = requests.post(webhook_url, json=data)
        
        if response.status_code >= 200 and response.status_code < 300:
            logger.info(f"Webhook通知の送信に成功しました: {ticket_number}")
            return True
        else:
            logger.warning(f"Webhook通知の送信に失敗しました: ステータスコード {response.status_code}, レスポンス: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Webhook通知の送信中にエラーが発生しました: {e}")
        return False

def process_pending_accounts(config):
    conn = mysql.connector.connect(
        host=config['mysql']['host'],
        user=config['mysql']['user'],
        password=config['mysql']['password'],
        database=config['mysql']['database']
    )
    cursor = conn.cursor()

    try:
        # 1. 差戻ステータスのチケットを検知して処理
        reverted_tickets = get_reverted_tickets(config)
        logger.info(f"差戻しチケット数: {len(reverted_tickets)}")
        
        for ticket in reverted_tickets:
            handle_reverted_ticket(cursor, ticket, conn, config)
        
        # 差戻し処理の確実なコミット
        conn.commit()
        
        # 少し待機して、状態の反映を待つ
        time.sleep(2)

        # 初期スタッフステータスを同期
        sync_staff_status()

        # 2. 未割当タスクを取得
        pending_accounts = get_team_pending_accounts(cursor)
        
        # チームごとの件数を集計
        team_counts = {}
        total_pending_accounts = 0
        
        if pending_accounts:
            for account in pending_accounts:
                team = account[5]
                team_counts[team] = team_counts.get(team, 0) + 1
                total_pending_accounts += 1

        # 集計結果をログ出力
        logger.info(f"未割当チケットの総件数: {total_pending_accounts}件")
        logger.info(f"グループ別の内訳:")
        if team_counts:
            for team, count in team_counts.items():
                team_name = team if team else '未分類'
                logger.info(f"- {team_name}: {count}件")
        else:
            logger.info("- 未割当タスクはありません")

        if total_pending_accounts == 0:
            logger.info("未割当のタスクがないため、割り当て処理を終了します")
            return

        # 1. ループの外でスタッフステータスを同期
        sync_staff_status()

        # 2. 各タスクに対して処理
        for account in pending_accounts:
            try:
                # トランザクション開始
                cursor.execute("START TRANSACTION")

                team = account[5]
                hospital_id = account[1]

                cursor.execute("""
                    SELECT s.スタッフID, s.名前, s.BacklogユーザーID, s.ステータス, s.最終割り当て時間,
                        COUNT(DISTINCT h.病院ID) as 担当医療機関数
                    FROM tbl_staff s
                    JOIN tbl_staff_teams st ON s.スタッフID = st.スタッフID
                    JOIN tbl_staff_teams st2 ON s.スタッフID = st2.スタッフID
                    JOIN tbl_hospital h ON st2.チーム = h.チーム
                    WHERE s.ステータス = '在席'  -- 厳密に「在席」のみ
                    AND st.チーム = %s
                    GROUP BY s.スタッフID, s.名前, s.BacklogユーザーID, s.ステータス, s.最終割り当て時間
                    ORDER BY 担当医療機関数 ASC, s.最終割り当て時間 ASC
                    FOR UPDATE
                """, (team,))

                available_staff = cursor.fetchall()

                if not available_staff:
                    cursor.execute("ROLLBACK")
                    continue

                selected_staff = available_staff[0]
                
                # 再度状態を確認
                cursor.execute("""
                    SELECT ステータス 
                    FROM tbl_staff 
                    WHERE スタッフID = %s 
                    AND ステータス = '在席'
                    FOR UPDATE
                """, (selected_staff[0],))
                
                if not cursor.fetchone():
                    logger.warning(f"スタッフ {selected_staff[1]} の状態が変更されたため、割り当てをスキップします")
                    cursor.execute("ROLLBACK")
                    continue

                # Backlogの更新
                if update_billing_task_status_in_backlog(conn, config, account, selected_staff):
                    cursor.execute("""
                        SELECT Backlogチケット番号
                        FROM tbl_pendingaccounts
                        WHERE 会計ID = %s
                        FOR UPDATE
                    """, (account[0],))
                    ticket_result = cursor.fetchone()
                    ticket_number = ticket_result[0] if ticket_result else 'Unknown'

                    # 病院名取得
                    cursor.execute("""
                        SELECT 病院名 
                        FROM tbl_hospital 
                        WHERE 病院ID = %s
                    """, (hospital_id,))
                    hospital_name_result = cursor.fetchone()
                    hospital_name = hospital_name_result[0] if hospital_name_result else "不明な病院"

                    # データベースの更新
                    update_databases(conn, cursor, account[0], selected_staff[0], None)

                    # 3. スタッフのステータスを "在席(処理中)" に更新
                    cursor.execute("""
                        UPDATE tbl_staff
                        SET ステータス = '在席(処理中)', 最終割り当て時間 = NOW()
                        WHERE スタッフID = %s
                    """, (selected_staff[0],))

                    # すべての処理が成功したらコミット
                    conn.commit()
                    logger.info(f"🔥 タスク割当完了: スタッフ:{selected_staff[1]}, Backlog:{ticket_number}, "
                                f"病院名:{hospital_name}, 患者ID:{account[2]}")
                    
                    # 病院情報を取得
                    hospital_info = get_hospital_info(conn, hospital_id)

                    # ★修正: DBから取得時間を取得してWebhook送信
                    acquisition_time = get_acquisition_time_from_db(conn, account[0])
                    
                    if acquisition_time:
                        # 正しい取得時間で説明文を生成
                        description = (
                            f"電子カルテ名: {hospital_info.get('電子カルテ名', 'Unknown')}\n"
                            f"病院名: {hospital_name}\n"
                            f"患者ID: {account[2]}\n"
                            f"診察日: {acquisition_time.strftime('%Y-%m-%d')}\n"
                            f"取得時間: {acquisition_time.strftime('%Y-%m-%d %H:%M:%S')}"
                        )
                        
                        # Webhook通知を送信（修正版）
                        send_webhook_notification_with_description(
                            config, selected_staff, ticket_number, account[0], 
                            hospital_name, account[2], description
                        )
                    else:
                        logger.warning(f"会計ID {account[0]} の取得時間が見つかりません")
                        # フォールバック: 従来の方法でWebhook送信
                        send_webhook_notification(
                            config,
                            selected_staff,
                            ticket_number,
                            account[0],
                            hospital_name,
                            account[2],
                            hospital_info
                        )
                else:
                    cursor.execute("ROLLBACK")
                    logger.error("Backlog更新に失敗したため、割り当てをロールバックしました")

            except Exception as e:
                logger.error(f"会計ID {account[0]} の処理中にエラーが発生しました: {e}")
                cursor.execute("ROLLBACK")

    except mysql.connector.Error as e:
        logger.error(f"データベース操作中にエラーが発生しました: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


def send_webhook_notification_with_description(config, staff_info, ticket_number, account_id, hospital_name, patient_id, description):
    """説明文を指定してWebhook通知を送信"""
    try:
        webhook_url = config.get('webhook', 'url', fallback='http://localhost:5000/webhook/new_ticket')
        assignment_time = datetime.now().isoformat()
        
        data = {
            "event_type": "processing_ticket",
            "timestamp": assignment_time,
            "id": ticket_number,
            "issueKey": ticket_number,
            "assigneeId": str(staff_info[2]),
            "projectId": config['backlog']['billing_project_id'],
            "summary": f"{hospital_name} - {patient_id}",
            "description": description,  # ★正しい取得時間を含む説明文
            "status": {
                "id": 2,
                "name": "処理中"
            }
        }
        
        response = requests.post(webhook_url, json=data)
        
        if response.status_code >= 200 and response.status_code < 300:
            logger.info(f"Webhook通知の送信に成功しました: {ticket_number}")
            return True
        else:
            logger.warning(f"Webhook通知の送信に失敗しました: ステータスコード {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"Webhook通知の送信中にエラーが発生しました: {e}")
        return False
    
def main():
    '''エントリーポイント'''
    try:
        config = load_config()
        if config is None:
            logger.error("設定の読み込みに失敗しました")
            return

        process_pending_accounts(config)
    except Exception as e:
        logger.error(f"予期せぬエラーが発生しました: {e}")
        logger.exception("スタックトレース:")

if __name__ == "__main__":
    main()