#!/usr/bin/env python3
import os
import sys

# プロジェクトルートへのパスを追加
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)

import time
import asyncio
import configparser
from datetime import datetime
import logging
from typing import List, Dict, Any
import subprocess
import json
import requests
import traceback

from src.utils.logger import LoggerFactory
from src.core.counter_manager import DailyCounter

# ロガーの初期化
logger = LoggerFactory.setup_logger('paper_monitor')

# パス定義
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG_DIR = os.path.join(SCRIPT_DIR, 'log')
CONFIG_DIR = os.path.join(SCRIPT_DIR, 'config')
SESSION_DIR = os.path.join(SCRIPT_DIR, 'session')

def load_config():
    """設定ファイルの読み込み"""
    config = configparser.ConfigParser()
    config_path = os.path.join(CONFIG_DIR, 'config.ini')
    
    if os.path.exists(config_path):
        config.read(config_path, encoding='utf-8')
        return config
    else:
        logger.error("設定ファイルが見つかりません！")
        return None

def check_directory_permissions(path: str) -> bool:
    """ディレクトリのアクセス権限を確認"""
    try:
        if not os.path.exists(path):
            os.makedirs(path)
        
        test_file = os.path.join(path, ".permission_test")
        with open(test_file, 'w') as f:
            f.write("test")
        os.remove(test_file)
        
        return True
    except Exception as e:
        logger.error(f"ディレクトリ {path} のアクセス権限チェックに失敗: {e}")
        return False

def get_custom_field_value(custom_fields: List[Dict[str, Any]], name: str) -> str:
    """カスタムフィールドから値を取得する"""
    try:
        for field in custom_fields:
            if field['name'] == name:
                if 'value' not in field or field['value'] is None:
                    logger.debug(f"カスタムフィールド '{name}' の値が設定されていません")
                    return ''
                
                if isinstance(field['value'], dict):
                    if 'name' in field['value']:
                        return field['value']['name']
                    logger.warning(f"未知の辞書型フィールド: {field}")
                    return ''
                
                return str(field['value'])

        logger.debug(f"カスタムフィールド '{name}' が見つかりません")
        return ''
    except Exception as e:
        logger.error(f"カスタムフィールド '{name}' の値取得中にエラー: {e}")
        return ''

def get_hospital_info(config: Dict) -> List[Dict[str, Any]]:
    """Backlogから紙カルテ医療機関情報を取得する"""
    try:
        logger.debug("Backlog APIリクエスト開始")
        space_name = config['backlog']['space_name']
        api_key = config['backlog']['api_key']
        project_id = config['backlog']['hospital_project_id']

        base_url = f"https://{space_name}.backlog.com/api/v2"
        project_endpoint = f"{base_url}/projects/{project_id}"
        params = {"apiKey": api_key}

        project_response = requests.get(project_endpoint, params=params)
        project_response.raise_for_status()
        project_info = project_response.json()

        issues_endpoint = f"{base_url}/issues"
        issue_params = {
            "apiKey": api_key,
            "projectId[]": project_id,
            "count": 100,
            "sort": "created",
            "order": "asc"
        }

        response = requests.get(issues_endpoint, params=issue_params)
        response.raise_for_status()
        issues = response.json()

        team_counts = {}
        all_hospitals = []
        filtered_count = 0

        for issue in issues:
            try:
                if not issue.get('issueType') or issue['issueType'].get('name') != '紙カルテ':
                    continue

                custom_fields = issue.get('customFields', [])
                polling = get_custom_field_value(custom_fields, 'ポーリング')
                
                if polling == 'ON':
                    team = get_custom_field_value(custom_fields, 'グループ')
                    folder_path = get_custom_field_value(custom_fields, 'フォルダパス')

                    if not folder_path:
                        logger.warning(f"課題 {issue.get('issueKey')}: フォルダパスが設定されていません")
                        continue

                    hospital_info = {
                        "hospital_name": issue.get('summary', ''),
                        "issue_key": issue.get('issueKey', ''),
                        "team": team,
                        "folder_path": folder_path,
                        "system_type": '紙カルテ'
                    }

                    if team:
                        team_counts[team] = team_counts.get(team, 0) + 1

                    all_hospitals.append(hospital_info)
                    filtered_count += 1

            except Exception as e:
                logger.error(f"課題 {issue.get('issueKey', '不明')} の処理中にエラー: {e}")
                continue

        logger.debug(f"取得した全課題数: {len(issues)}")
        logger.debug(f"紙カルテ・ポーリング有効な医療機関数: {filtered_count}")

        return all_hospitals

    except requests.exceptions.RequestException as e:
        logger.error(f"Backlog APIリクエストエラー: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"レスポンス内容: {e.response.text}")
        return []
    except Exception as e:
        logger.error(f"医療機関情報の取得中にエラー: {e}")
        logger.exception("スタックトレース:")
        return []

def process_and_insert_data(records, hospital_info):
    """データを medical_data_inserter に渡して処理する"""
    try:
        if not records:
            logger.error("処理対象の records が空です。")
            return False

        script_dir = os.path.dirname(os.path.abspath(__file__))
        inserter_path = os.path.join(script_dir, "medical_data_inserter.py")

        if not os.path.exists(inserter_path):
            logger.error(f"medical_data_inserter.py が見つかりません: {inserter_path}")
            return False

        json_data = {
            "hospital_name": hospital_info["hospital_name"],
            "system_type": hospital_info.get("system_type", "紙カルテ"),
            "team": hospital_info["team"],
            "issue_key": hospital_info["issue_key"],
            "patients": records
        }

        try:
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
            process = subprocess.run(
                [sys.executable, inserter_path],
                input=json.dumps(json_data, ensure_ascii=False),
                text=True,
                capture_output=True,
                encoding='utf-8',  # ここを追加
                env={
                    **os.environ,
                    'PYTHONIOENCODING': 'utf-8'
                },
                startupinfo=startupinfo,
                check=True
            )

            if process.stdout.strip():
                logger.info(f"データベース挿入成功: {process.stdout}")
            logger.debug("データベース挿入が完了しました")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"データベース挿入エラー: {e.stderr}")
            return False
            
        except Exception as e:
            logger.error(f"medical_data_inserterの実行中にエラー: {str(e)}")
            logger.error(f"詳細なエラー情報: {traceback.format_exc()}")
            return False

    except Exception as e:
        hospital_name = hospital_info.get('hospital_name', 'Unknown Hospital')
        logger.error(f"医療機関 {hospital_name}: データ処理中にエラー: {str(e)}")
        logger.error(f"詳細なエラー情報: {traceback.format_exc()}")
        return False

async def is_file_physically_exists(file_path: str, timeout: int = 30) -> bool:
    """
    ファイルの物理的な存在と読み取り可能性を確認
    
    Args:
        file_path: 確認するファイルのパス
        timeout: タイムアウト時間（秒）
    
    Returns:
        bool: ファイルが存在し読み取り可能な場合はTrue
    """
    try:
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if os.path.exists(file_path):
                try:
                    # ファイルが存在する場合、読み取りテストを実行
                    with open(file_path, 'rb') as f:
                        # 1バイト読んでみる
                        data = f.read(1)
                        if data:  # データが読めれば成功
                            logger.debug(f"ファイル {file_path} は読み取り可能です")
                            return True
                        else:
                            logger.debug(f"ファイル {file_path} は0バイトです")
                    
                except (OSError, IOError) as e:
                    logger.debug(f"ファイル {file_path} の読み取りに失敗: {e}")
                    
                # 読み取りに失敗したら少し待ってリトライ
                await asyncio.sleep(1)
            else:
                logger.debug(f"ファイル {file_path} が見つかりません")
                await asyncio.sleep(1)
                
        logger.warning(f"ファイル {file_path} の読み取り確認がタイムアウトしました")
        return False
        
    except Exception as e:
        logger.error(f"ファイル存在チェック中にエラー: {e}")
        return False
    
# async def run(config: Dict, shutdown_event: asyncio.Event) -> None:
#     try:
#         logger.debug("run関数開始")
#         hospitals = get_hospital_info(config)
#         if not hospitals:
#             logger.debug("処理対象の病院が見つかりません")
#             return

#         logger.debug(f"処理対象病院数: {len(hospitals)}")
#         counter_file = os.path.join(CONFIG_DIR, "counter.json")
#         counter_manager = DailyCounter(counter_file)

#         # 各病院の処理（単一回）
#         for hospital in hospitals:
#             if shutdown_event.is_set():
#                 break

#             logger.debug(f"病院の処理開始: {hospital['hospital_name']}")
#             folder_path = hospital['folder_path']
#             processed_dir = os.path.join(folder_path, "処理済み")

#             try:
#                 os.makedirs(processed_dir, exist_ok=True)
#                 logger.debug(f"監視フォルダをスキャン: {folder_path}")
#                 files = sorted(
#                     [f for f in os.listdir(folder_path) 
#                         if os.path.isfile(os.path.join(folder_path, f))],
#                     key=lambda f: os.path.getctime(os.path.join(folder_path, f))
#                 )
#                 logger.debug(f"検出したファイル数: {len(files)}")

#                 for file in files:
#                     if shutdown_event.is_set():
#                         break

#                     logger.debug(f"ファイル処理開始: {file}")
#                     try:
#                         src_path = os.path.join(folder_path, file)
                        
#                         # ファイルの存在確認
#                         if not await is_file_physically_exists(src_path):
#                             logger.warning(f"ファイル {file} は読み取り不可能なためスキップします")
#                             continue

#                         current_count = counter_manager.get_next_value()
#                         new_id = f"{datetime.now().strftime('%d')}{str(current_count).zfill(3)}"
#                         dst_path = os.path.join(processed_dir, f"{new_id}{os.path.splitext(file)[1]}")

#                         # ファイル移動を先に試行
#                         try:
#                             os.rename(src_path, dst_path)
#                         except OSError as e:
#                             logger.warning(f"ファイル移動に失敗しました: {e}")
#                             continue

#                         # ファイル移動が成功した後にDBとBacklog登録を実行
#                         current_time = datetime.now()
#                         patient_data = [{
#                             "patient_id": new_id,
#                             "end_time": current_time.strftime("%H:%M:%S"),
#                             "診察日": current_time.strftime("%Y-%m-%d"),
#                             "診察時間": current_time.strftime("%H:%M:%S"),
#                             "作成時間": current_time.strftime("%Y-%m-%d %H:%M:%S")
#                         }]

#                         if process_and_insert_data(patient_data, hospital):
#                             logger.info(f"ファイル処理完了: {file} -> {new_id}")
#                         else:
#                             # DBへの挿入が失敗した場合、ファイルを元に戻す
#                             try:
#                                 os.rename(dst_path, src_path)
#                             except OSError:
#                                 logger.error("ファイルの復元に失敗しました")

#                     except Exception as e:
#                         logger.error(f"ファイル {file} の処理中にエラー: {e}")
#                         logger.error(traceback.format_exc())
#                         continue

#             except FileNotFoundError:
#                 logger.error(f"フォルダが見つかりません: {folder_path}")
#             except PermissionError:
#                 logger.error(f"フォルダへのアクセス権限がありません: {folder_path}")
#             except Exception as e:
#                 logger.error(f"病院 {hospital['hospital_name']} の処理中にエラー: {e}")
#                 logger.error(traceback.format_exc())

#         logger.debug("run関数終了")

#     except Exception as e:
#         logger.error(f"実行中にエラー: {e}")
#         logger.error(traceback.format_exc())

async def run(config: Dict, hospitals: List[Dict[str, Any]], shutdown_event: asyncio.Event) -> None:
    try:
        logger.debug("run関数開始")
        if not hospitals:
            logger.debug("処理対象の病院が見つかりません")
            return

        logger.debug(f"処理対象病院数: {len(hospitals)}")
        counter_file = os.path.join(CONFIG_DIR, "counter.json")
        counter_manager = DailyCounter(counter_file)

        # 紙カルテシステム起動時に各医療機関のlogin_checkファイルを作成
        for hospital in hospitals:
            _create_paper_startup_file(hospital['hospital_name'])
        
        # 各病院の処理（単一回）
        for hospital in hospitals:
            if shutdown_event.is_set():
                break

            logger.debug(f"病院の処理開始: {hospital['hospital_name']}")
            folder_path = hospital['folder_path']
            processed_dir = os.path.join(folder_path, "処理済み")

            try:
                os.makedirs(processed_dir, exist_ok=True)
                logger.debug(f"監視フォルダをスキャン: {folder_path}")
                files = sorted(
                    [f for f in os.listdir(folder_path) 
                        if os.path.isfile(os.path.join(folder_path, f))],
                    key=lambda f: os.path.getctime(os.path.join(folder_path, f))
                )
                logger.debug(f"検出したファイル数: {len(files)}")

                for file in files:
                    if shutdown_event.is_set():
                        break

                    logger.debug(f"ファイル処理開始: {file}")
                    try:
                        src_path = os.path.join(folder_path, file)
                        
                        # ファイルの存在確認
                        if not await is_file_physically_exists(src_path):
                            logger.warning(f"ファイル {file} は読み取り不可能なためスキップします")
                            continue

                        current_count = counter_manager.get_next_value()
                        new_id = f"{datetime.now().strftime('%d')}{str(current_count).zfill(3)}"
                        dst_path = os.path.join(processed_dir, f"{new_id}{os.path.splitext(file)[1]}")

                        # ファイル移動を先に試行
                        try:
                            os.rename(src_path, dst_path)
                        except OSError as e:
                            logger.warning(f"ファイル移動に失敗しました: {e}")
                            continue

                        # ファイル移動が成功した後にDBとBacklog登録を実行
                        current_time = datetime.now()
                        patient_data = [{
                            "patient_id": new_id,
                            "end_time": current_time.strftime("%H:%M:%S"),
                            "診察日": current_time.strftime("%Y-%m-%d"),
                            "診察時間": current_time.strftime("%H:%M:%S"),
                            "作成時間": current_time.strftime("%Y-%m-%d %H:%M:%S")
                        }]

                        if process_and_insert_data(patient_data, hospital):
                            logger.info(f"ファイル処理完了: {file} -> {new_id}")
                        else:
                            # DBへの挿入が失敗した場合、ファイルを元に戻す
                            try:
                                os.rename(dst_path, src_path)
                            except OSError:
                                logger.error("ファイルの復元に失敗しました")

                    except Exception as e:
                        logger.error(f"ファイル {file} の処理中にエラー: {e}")
                        logger.error(traceback.format_exc())
                        continue

            except FileNotFoundError:
                logger.error(f"フォルダが見つかりません: {folder_path}")
            except PermissionError:
                logger.error(f"フォルダへのアクセス権限がありません: {folder_path}")
            except Exception as e:
                logger.error(f"病院 {hospital['hospital_name']} の処理中にエラー: {e}")
                logger.error(traceback.format_exc())

        logger.debug("run関数終了")

    except Exception as e:
        logger.error(f"実行中にエラー: {e}")
        logger.error(traceback.format_exc())

def _create_paper_startup_file(hospital_name):
    """紙カルテシステム起動時にlogin_checkフォルダにテキストファイルを作成"""
    try:
        # プロジェクトルートのパスを取得
        current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        login_check_dir = os.path.join(current_dir, 'login_check')
        
        # login_checkディレクトリが存在しない場合は作成
        if not os.path.exists(login_check_dir):
            os.makedirs(login_check_dir)
        
        # ファイル名から無効な文字を除去
        safe_filename = "".join(c for c in hospital_name if c.isalnum() or c in (' ', '-', '_', '（', '）', 'ー')).rstrip()
        filename = f"{safe_filename}.txt"
        filepath = os.path.join(login_check_dir, filename)
        
        # 現在日時を指定フォーマットで取得
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        
        # ファイルに日時を書き込み
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(current_time)
            
    except Exception as e:
        # エラーが発生しても紙カルテ処理自体は継続させる
        logger.error(f"login_check ファイル作成中にエラーが発生しました: {e}")

# async def main_with_shutdown(shutdown_event: asyncio.Event, init_done: asyncio.Event = None) -> None:
#     try:
#         logger.debug("main_with_shutdown開始")
#         config = load_config()
#         if config is None:
#             logger.error("設定の読み込みに失敗しました")
#             if init_done:
#                 init_done.set()
#             return

#         logger.debug("Backlogから病院情報を取得開始")
#         hospitals = get_hospital_info(config)
#         logger.debug(f"取得した病院数: {len(hospitals) if hospitals else 0}")

#         if init_done:
#             init_done.set()

#         logger.debug("run関数の実行開始")
#         await run(config, shutdown_event)
#         logger.debug("run関数の実行完了")

#     except asyncio.CancelledError:
#         logger.debug("メイン処理がキャンセルされました")
#     except Exception as e:
#         logger.error(f"予期せぬエラーが発生しました: {e}")
#         logger.error(traceback.format_exc())
#     finally:
#         if init_done and not init_done.is_set():
#             init_done.set()

async def main_with_shutdown(shutdown_event: asyncio.Event, init_done: asyncio.Event = None) -> None:
    try:
        logger.debug("main_with_shutdown開始")
        config = load_config()
        if config is None:
            logger.error("設定の読み込みに失敗しました")
            if init_done:
                init_done.set()
            return

        logger.debug("Backlogから病院情報を取得開始")
        hospitals = get_hospital_info(config)
        logger.debug(f"取得した病院数: {len(hospitals) if hospitals else 0}")

        if init_done:
            init_done.set()

        logger.debug("run関数の実行開始")
        await run(config, hospitals, shutdown_event)
        logger.debug("run関数の実行完了")

    except asyncio.CancelledError:
        logger.debug("メイン処理がキャンセルされました")
    except Exception as e:
        logger.error(f"予期せぬエラーが発生しました: {e}")
        logger.error(traceback.format_exc())
    finally:
        if init_done and not init_done.is_set():
            init_done.set()

if __name__ == "__main__":
    shutdown_event = asyncio.Event()
    
    try:
        required_dirs = [LOG_DIR, CONFIG_DIR, SESSION_DIR]
        for dir_path in required_dirs:
            if not check_directory_permissions(dir_path):
                logger.error(f"必要なディレクトリ {dir_path} にアクセスできません")
                sys.exit(1)
        
        asyncio.run(main_with_shutdown(shutdown_event))
    except KeyboardInterrupt:
        logger.info("キーボード割り込みを検知しました")
        shutdown_event.set()
    except Exception as e:
        logger.error(f"予期せぬエラーが発生しました: {e}")
        logger.exception("スタックトレース:")
        sys.exit(1)
    finally:
        logger.info("プログラムを終了します")