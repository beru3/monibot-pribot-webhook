# src/core/medical_data_inserter.py
import os
import sys

# プロジェクトルートへのパスを追加
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)

import mysql.connector
from mysql.connector import Error
import configparser
from datetime import datetime
import json
import requests
import time

from src.utils.logger import LoggerFactory

# ロガーの初期化
logger = LoggerFactory.setup_logger('medical_data_inserter')

# パス定義
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_DIR = os.path.join(SCRIPT_DIR, 'config')

# チケットステータスの定義
TASK_STATUS_UNASSIGNED = '未割当'
TASK_STATUS_ASSIGNED = '割当済'
TASK_STATUS_REVERTED = '差戻'

# APIリクエスト用の定数
MAX_RETRIES = 3  # 最大リトライ回数
RETRY_DELAY = 3  # リトライの基本間隔（秒）

def load_config(filename='config.ini'):
    """設定ファイルを読み込む"""
    config = configparser.ConfigParser()
    config_path = os.path.join(CONFIG_DIR, filename)
    try:
        config.read(config_path, encoding='utf-8')
        db_config = {
            'host': config['mysql']['host'],
            'user': config['mysql']['user'],
            'password': config['mysql']['password'],
            'database': config['mysql']['database']
        }
        return config, db_config
    except Exception as e:
        logger.error(f"設定ファイルの読み込みに失敗しました: {e}")
        return None, None

def mysql_connection(config):
    try:
        connection = mysql.connector.connect(**config)
        return connection if connection.is_connected() else None
    except Error as e:
        logger.error(f"MySQLデータベースへの接続中にエラーが発生しました: {e}")
        return None
    
def get_or_insert_hospital_data(cursor, hospital_name, electronic_medical_record_name, team, issue_key):
    """
    病院データを取得または挿入し、必要に応じてチーム情報を更新する
    
    Args:
        cursor: データベースカーソル
        hospital_name: 病院名
        electronic_medical_record_name: 電子カルテ名
        team: チーム名
        issue_key: Backlogの課題キー
    
    Returns:
        int: 病院ID（処理が成功した場合）
        None: エラーが発生した場合
    """
    try:
        args = (hospital_name, electronic_medical_record_name, team, issue_key)
        cursor.callproc('GetOrInsertHospitalData', args)
        for result in cursor.stored_results():
            row = result.fetchone()
            return row[0] if row else None
    except Error as e:
        logger.error(f"病院データの処理中にエラーが発生しました: {e}")
        return None

def api_request_with_retry(request_func, *args, **kwargs):
    """
    シンプルなリトライロジックを含むAPIリクエスト関数
    
    Args:
        request_func: 実行する関数
        *args, **kwargs: 関数に渡す引数
        
    Returns:
        結果またはNone（失敗時）
    """
    retries = 0
    last_exception = None
    
    while retries < MAX_RETRIES:
        try:
            return request_func(*args, **kwargs)
        except requests.exceptions.RequestException as e:
            last_exception = e
            retries += 1
            
            # レスポンス情報の取得
            status_code = None
            if hasattr(e, 'response') and e.response:
                status_code = e.response.status_code
            
            # 429 Too Many Requestsの場合の特別処理
            if status_code == 429:
                # Retry-Afterヘッダーがあれば使用
                retry_after = None
                if hasattr(e, 'response') and e.response and 'Retry-After' in e.response.headers:
                    retry_after = int(e.response.headers['Retry-After'])
                
                wait_time = retry_after if retry_after else RETRY_DELAY * 5
                logger.warning(f"APIレート制限に達しました (429). {wait_time}秒後にリトライ {retries}/{MAX_RETRIES}...")
                time.sleep(wait_time)
                continue
            
            # リトライするべきエラー（サーバーエラーや接続エラー）
            elif (status_code and 500 <= status_code < 600) or not status_code:
                wait_time = RETRY_DELAY
                logger.warning(f"APIリクエスト中にエラー発生. {wait_time}秒後にリトライ {retries}/{MAX_RETRIES}...")
                time.sleep(wait_time)
                continue
            else:
                # その他のクライアントエラーはリトライしない
                logger.error(f"APIリクエスト中にクライアントエラー発生: {e}")
                break
        except Exception as e:
            last_exception = e
            logger.error(f"予期せぬエラーが発生: {e}")
            break
    
    if last_exception:
        logger.error(f"APIリクエストが {MAX_RETRIES} 回失敗しました: {last_exception}")
    return None

def get_priority_id(space_name, api_key):
    '''Backlogの優先度リストから「中」優先度のIDを取得する'''
    base_url = f"https://{space_name}.backlog.com/api/v2"
    endpoint = f"{base_url}/priorities"
    params = {"apiKey": api_key}
    
    def _get_priority():
        response = requests.get(endpoint, params=params)
        response.raise_for_status()
        priorities = response.json()
        for priority in priorities:
            if priority['name'] == '中':
                return priority['id']
        return priorities[0]['id'] if priorities else None
    
    return api_request_with_retry(_get_priority)

def get_issue_type_id(space_name, api_key, project_id, issue_type_name):
    '''課題種別リストから、特定の名前の課題種別IDを取得する'''
    base_url = f"https://{space_name}.backlog.com/api/v2"
    endpoint = f"{base_url}/projects/{project_id}/issueTypes"
    params = {"apiKey": api_key}
    
    def _get_issue_type():
        response = requests.get(endpoint, params=params)
        response.raise_for_status()
        issue_types = response.json()
            
        for issue_type in issue_types:
            if issue_type['name'] == issue_type_name:
                return issue_type['id']
        logger.error(f"指定された種別 '{issue_type_name}' が見つかりません")
        return None
    
    return api_request_with_retry(_get_issue_type)
    
def get_custom_field_id(space_name, api_key, project_id):
    '''プロジェクトのカスタムフィールド一覧を取得'''
    base_url = f"https://{space_name}.backlog.com/api/v2"
    endpoint = f"{base_url}/projects/{project_id}/customFields"
    params = {"apiKey": api_key}
    
    def _get_custom_fields():
        response = requests.get(endpoint, params=params)
        response.raise_for_status()
        return response.json()
    
    return api_request_with_retry(_get_custom_fields)

def create_initial_backlog_issue(connection, config, hospital_info, account_info):
    """医療機関データ取り込み時にBacklogチケットを作成"""
    space_name = config['backlog']['space_name']
    api_key = config['backlog']['api_key']
    project_id = config['backlog']['billing_project_id']

    # カスタムフィールド情報の取得
    custom_fields = get_custom_field_id(space_name, api_key, project_id)
    if custom_fields is None:
        logger.error("カスタムフィールド情報の取得に失敗しました")
        return None
        
    # 優先度IDの取得
    priority_id = get_priority_id(space_name, api_key)
    if priority_id is None:
        logger.error("優先度IDの取得に失敗しました")
        return None
        
    # 課題種別IDの取得
    issue_type_id = get_issue_type_id(space_name, api_key, project_id, hospital_info['電子カルテ名'])
    if issue_type_id is None:
        logger.error(f"課題種別 '{hospital_info['電子カルテ名']}' のIDの取得に失敗しました")
        return None
    
    base_url = f"https://{space_name}.backlog.com/api/v2"
    endpoint = f"{base_url}/issues"
    
    # 時間のみを抽出（HH:MM:SS形式）
    time_only = datetime.strptime(account_info['作成時間'], "%Y-%m-%d %H:%M:%S").strftime("%H:%M:%S")
    
    # 診療科情報の取得
    department = account_info.get('診療科', '')
    
    # 再会計フラグに基づいてタイトルを設定
    re_account_flag = account_info.get('再会計フラグ', 0)
    re_account_prefix = "（再会計）" if re_account_flag == 1 else ""
    
    # タイトルの設定（再会計の場合はプレフィックスを追加）
    summary = f"{hospital_info['病院名']} - {account_info['患者ID']}{re_account_prefix}"
    
    params = {
        "apiKey": api_key,
        "projectId": project_id,
        "summary": summary,
        "issueTypeId": issue_type_id,
        "priorityId": priority_id,
        "description": (
            f"電子カルテ名: {hospital_info['電子カルテ名']}\n"
            f"病院名: {hospital_info['病院名']}\n"
            f"患者ID: {account_info['患者ID']}\n"
        )
    }
    
    # 診療科情報がある場合は説明に追加
    if department:
        params["description"] += f"診療科: {department}\n"
    
    # 残りの情報を追加
    params["description"] += (
        f"診察日: {account_info['診察日']}\n"
        f"取得時間: {account_info['作成時間']}"
    )

    # カスタムフィールドIDが取得できた場合のみ追加
    if custom_fields:
        for field in custom_fields:
            if field['name'] == '取得時間':
                params[f"customField_{field['id']}"] = time_only
                break
            # 再会計用のカスタムフィールドがある場合
            if field['name'] == '再会計' and re_account_flag == 1:
                params[f"customField_{field['id']}"] = "はい"

    def _create_issue():
        response = requests.post(endpoint, params=params)
        response.raise_for_status()
        return response.json()

    # APIリクエストを実行し、成功したらチケット番号を保存
    issue = api_request_with_retry(_create_issue)
    if issue:
        # 作成したチケット番号をDBに保存
        update_backlog_ticket_number(connection, account_info['会計ID'], issue['issueKey'])
        return issue
    
    return None

def update_backlog_ticket_number(connection, account_id, ticket_number):
    """会計データにBacklogチケット番号を保存"""
    cursor = connection.cursor()
    try:
        cursor.execute("""
            UPDATE tbl_pendingaccounts 
            SET Backlogチケット番号 = %s 
            WHERE 会計ID = %s
        """, (ticket_number, account_id))
        connection.commit()
    except Exception as e:
        logger.error(f"チケット番号更新中にエラー: {str(e)}")
        connection.rollback()
    finally:
        cursor.close()

def insert_pending_account(cursor, hospital_id, patient_id, department, exam_date, exam_time, re_account_flag=0):
    """会計データの挿入を行う。既存データの場合は既存レコードの会計IDと更新フラグを返す。"""
    try:
        args = (hospital_id, patient_id, department, exam_date, exam_time, re_account_flag)
        cursor.callproc('InsertPendingAccount', args)
       
        for result in cursor.stored_results():
            row = result.fetchone()
            if row:
                account_id = row[0]
                # 2番目、3番目の要素があれば取得（新規挿入時は updated_existing=0、既存なら例:2）
                message = row[1] if len(row) > 1 else ""
                updated_existing = row[2] if len(row) > 2 else 0
                if account_id > 0:
                    logger.info(f"処理結果: {message}")
                return account_id, updated_existing
            return 0, 0  # データが無い場合
    except Error as e:
        logger.error(f"処理中にエラーが発生しました: {e}")
        return None, 0

def process_patient_data(connection, cursor, data):
    """
    患者データを処理し、DBとBacklogに登録する
    トランザクション管理を強化し、Backlog APIエラー時はロールバックする
    """
    try:
        logger.debug(f"受信データの詳細: {json.dumps(data, ensure_ascii=False, indent=2)}")
        
        hospital_name = data.get('hospital_name')
        system_type = data.get('system_type')
        team = data.get('team', '')
        issue_key = data.get('issue_key', '')
        patients = data.get('patients', [])

        if not all([hospital_name, system_type, issue_key]):
            logger.error("必須データが不足しています")
            return

        # 病院データの取得または挿入
        hospital_id = get_or_insert_hospital_data(cursor, hospital_name, system_type, team, issue_key)
        if not hospital_id:
            logger.error(f"病院データの取得または挿入に失敗しました: {hospital_name}")
            return

        # 病院データをコミット
        connection.commit()

        if not patients:
            logger.debug("処理対象の患者データが空です")
            return

        config = load_config()[0]
        
        # 各患者データの処理をトランザクションで管理
        for patient in patients:
            # 既存のトランザクションがあればロールバック
            if connection.in_transaction:
                connection.rollback()
            connection.start_transaction()
            
            try:
                logger.debug(f"患者データを処理: {json.dumps(patient, ensure_ascii=False)}")
                exam_date = datetime.now().strftime("%Y-%m-%d")
                department = patient.get('department', '不明')
                re_account_flag = 1 if 're_account' in patient and patient['re_account'] else 0
                
                account_id, updated_existing = insert_pending_account(
                    cursor, hospital_id, patient['patient_id'], 
                    department, exam_date, patient['end_time'], re_account_flag
                )

                if account_id is None or account_id == 0:
                    logger.error(f"会計データの挿入に失敗しました: {patient['patient_id']}")
                    connection.rollback()
                    continue

                # 新規データの場合のみBacklogチケットを作成
                if account_id > 0 and updated_existing == 0:
                    logger.info(f"新規データを登録しました: 病院ID {hospital_id}, "
                              f"患者ID {patient['patient_id']}, 会計ID {account_id}, "
                              f"診療科 {department}, 診察終了時間 {patient['end_time']}, "
                              f"再会計フラグ: {re_account_flag}")

                    hospital_info = {
                        "病院名": hospital_name,
                        "電子カルテ名": system_type
                    }
                    account_info = {
                        "会計ID": account_id,
                        "患者ID": patient['patient_id'],
                        "診療科": department,
                        "診察日": exam_date,
                        "作成時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "再会計フラグ": re_account_flag
                    }
                    
                    backlog_issue = create_initial_backlog_issue(connection, config, hospital_info, account_info)
                    
                    if backlog_issue is None:
                        logger.error(f"Backlogチケット作成に失敗したため、トランザクションをロールバックします: 患者ID {patient['patient_id']}")
                        connection.rollback()
                        continue
                else:
                    logger.info(f"既存レコードが検出されました: 患者ID {patient['patient_id']}, 会計ID {account_id}")
                
                connection.commit()
                logger.debug(f"患者ID {patient['patient_id']} の処理が完了し、トランザクションをコミットしました")
                
            except Exception as e:
                connection.rollback()
                logger.error(f"患者ID {patient.get('patient_id', 'Unknown')} の処理中にエラー発生: {e}")
                logger.error(f"トランザクションをロールバックしました")

    except Exception as e:
        logger.error(f"患者データの処理中にエラーが発生しました: {e}")
        raise

def main():
    """メインの実行フロー"""
    try:
        # 設定の読み込み
        config, db_config = load_config()
        if not db_config:
            return

        # データベース接続
        connection = mysql_connection(db_config)
        if not connection:
            return

        try:
            # 自動コミットを無効にする
            connection.autocommit = False
            cursor = connection.cursor(buffered=True)
            
            # 標準入力からJSONデータを読み込む
            input_data = json.loads(sys.stdin.read())
            
            # データ処理
            process_patient_data(connection, cursor, input_data)
            logger.debug("データ処理が完了しました")

        except json.JSONDecodeError as e:
            logger.error(f"JSONデータの解析に失敗しました: {e}")
        except Error as e:
            logger.error(f"データ処理中にエラーが発生しました: {e}")
            if connection.is_connected() and connection.in_transaction:
                connection.rollback()
        finally:
            if connection.is_connected():
                # 残っているトランザクションがあればロールバック
                if connection.in_transaction:
                    connection.rollback()
                cursor.close()
                connection.close()
                logger.debug("MySQL接続を閉じました")

    except Exception as e:
        logger.error(f"予期せぬエラーが発生しました: {e}")
        logger.exception("スタックトレース:")

if __name__ == "__main__":
    main()