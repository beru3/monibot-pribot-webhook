# src/core/movacal_monitor.py
import os
import sys

# プロジェクトルートへのパスを追加（最初に実行）
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)

# プロジェクト固有のインポート
from src.utils.logger import LoggerFactory
from src.utils.login_status import LoginStatus

# 標準ライブラリとサードパーティのインポート
import asyncio
from playwright.async_api import async_playwright, TimeoutError
import configparser
import threading
import time
import pyautogui
from datetime import datetime
import re
import logging
from typing import List
import subprocess
import json
import requests
import traceback
from typing import List, Dict, Any

# ロガーの初期化
logger = LoggerFactory.setup_logger('movacal_monitor')

# パス定義
LOG_DIR = os.path.join(project_root, 'log')
DEBUG_DIR = os.path.join(LOG_DIR, 'debug')
CONFIG_DIR = os.path.join(project_root, 'config')
SESSION_DIR = os.path.join(project_root, 'session')

def select_certificate(cert_order: int):
    """証明書選択ダイアログを処理"""
    try:
        import pyautogui
        
        # フェイルセーフ設定の調整
        pyautogui.FAILSAFE = False  # フェイルセーフを無効化
        pyautogui.PAUSE = 0.5       # 各アクションの間に0.5秒の待機を入れる
        
        logger.debug(f"証明書選択処理を開始します (順番: {cert_order})...")
        time.sleep(3)  # 証明書ダイアログの表示を待機
        
        # 画面中央にマウスを移動（フェイルセーフ対策）
        screen_width, screen_height = pyautogui.size()
        pyautogui.moveTo(screen_width/2, screen_height/2)
        
        # 指定された順番まで下キーを押す
        for _ in range(cert_order - 1):
            time.sleep(0.5)
            pyautogui.press('down')
            
        time.sleep(1)
        pyautogui.press('enter')
        time.sleep(2)  # 証明書選択完了後の待機
        logger.debug("証明書選択が完了しました")
        
        # 再度画面中央にマウスを移動
        pyautogui.moveTo(screen_width/2, screen_height/2)
        
    except Exception as e:
        logger.error(f"証明書選択処理中にエラー: {e}")
        logger.debug(f"エラーの詳細:\n{traceback.format_exc()}")
        raise

def load_config():
    """設定ファイルの読み込み"""
    config = configparser.ConfigParser()
    config_path = os.path.join(CONFIG_DIR, 'config.ini')
    
    if os.path.exists(config_path):
        config.read(config_path, encoding='utf-8')
        logger.info("設定ファイルを読み込みました")
        return config
    else:
        logger.error("設定ファイルが見つかりません！")
        return None

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
                        return field['value']['name']  # 選択肢型
                    logger.warning(f"未知の辞書型フィールド: {field}")
                    return ''
                
                return str(field['value'])

        logger.debug(f"カスタムフィールド '{name}' が見つかりません")
        return ''
    except Exception as e:
        logger.error(f"カスタムフィールド '{name}' の値取得中にエラー: {e}")
        return ''

def get_hospital_info(config):
    """Backlogから医療機関情報を取得する"""
    try:
        space_name = config['backlog']['space_name']
        api_key = config['backlog']['api_key']
        project_id = config['backlog']['hospital_project_id']

        logger.info(f"Backlog APIリクエストを開始します")
        logger.info(f"プロジェクトID: {project_id}")

        # プロジェクト情報を取得
        base_url = f"https://{space_name}.backlog.com/api/v2"
        project_endpoint = f"{base_url}/projects/{project_id}"
        
        params = {
            "apiKey": api_key
        }

        project_response = requests.get(project_endpoint, params=params)
        
        if project_response.status_code != 200:
            logger.error(f"プロジェクト情報の取得に失敗: ステータスコード {project_response.status_code}")
            logger.error(f"エラー内容: {project_response.text}")
            return []
            
        project_info = project_response.json()
        logger.info(f"プロジェクト名: {project_info.get('name', '不明')}")

        # 課題一覧を取得
        issues_endpoint = f"{base_url}/issues"
        issue_params = {
            "apiKey": api_key,
            "projectId[]": project_id,
            "count": 100,
            "sort": "created",
            "order": "asc"
        }

        response = requests.get(issues_endpoint, params=issue_params)
        
        if response.status_code != 200:
            logger.error(f"課題一覧の取得に失敗: ステータスコード {response.status_code}")
            logger.error(f"エラー内容: {response.text}")
            return []

        issues = response.json()
        logger.info(f"取得した全課題数: {len(issues)}")

        # グループ情報の集計用
        team_counts = {}
        all_hospitals = []
        filtered_count = 0

        # 各課題の情報を処理
        for issue in issues:
            try:
                # システム種別が "モバカル" であることを確認
                if not issue.get('issueType') or issue['issueType'].get('name') != 'モバカル':
                    continue

                custom_fields = issue.get('customFields', [])
                polling = get_custom_field_value(custom_fields, 'ポーリング')
                
                if polling == 'ON':
                    # グループ情報の取得とデバッグログ
                    team = get_custom_field_value(custom_fields, 'グループ')
                    cert_order = get_custom_field_value(custom_fields, '証明書順番')

                    # 証明書順番のバリデーション
                    if not cert_order:
                        logger.warning(f"課題 {issue.get('issueKey')}: 証明書順番が設定されていません")
                        continue

                    try:
                        cert_order = int(cert_order)
                    except ValueError:
                        logger.warning(f"課題 {issue.get('issueKey')}: 証明書順番が数値ではありません: {cert_order}")
                        continue

                    # ログイン情報の取得
                    username = get_custom_field_value(custom_fields, 'ID')
                    password = get_custom_field_value(custom_fields, 'パスワード')

                    # 必須フィールドの検証
                    if not all([username, password]):
                        logger.warning(f"課題 {issue.get('issueKey')}: ID/パスワードが設定されていません")
                        continue

                    hospital_info = {
                        "hospital_name": issue.get('summary', ''),
                        "username": username,
                        "password": password,
                        "cert_order": cert_order,
                        "issue_key": issue.get('issueKey', ''),
                        "team": team,
                        "system_type": 'モバカル'
                    }

                    # グループ情報の集計
                    if team:
                        team_counts[team] = team_counts.get(team, 0) + 1

                    all_hospitals.append(hospital_info)
                    filtered_count += 1
                    logger.info(f"医療機関を追加: {hospital_info['hospital_name']} (グループ: {team}, 証明書順番: {cert_order})")

            except Exception as e:
                logger.error(f"課題 {issue.get('issueKey', '不明')} の処理中にエラー: {e}")
                continue

        # グループごとの集計結果を表示
        logger.info("グループごとのモバカル医療機関数:")
        for team, count in team_counts.items():
            if team:  # グループ未設定は表示しない
                logger.info(f"- {team}: {count}件")

        logger.info(f"取得した全課題数: {len(issues)}")
        logger.info(f"モバカル・ポーリング有効な医療機関数: {filtered_count}")
        
        if not all_hospitals:
            logger.warning("条件を満たす医療機関が見つかりませんでした")
        
        # 証明書順番でソートして返す
        return sorted(all_hospitals, key=lambda x: x['cert_order'])

    except requests.exceptions.RequestException as e:
        logger.error(f"Backlog APIリクエストエラー: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"レスポンス内容: {e.response.text}")
        return []
    except Exception as e:
        logger.error(f"医療機関情報の取得中にエラー: {e}")
        logger.exception("スタックトレース:")
        return []

async def navigate_and_login(page, hospital_info, index, user_info, login_status):
    """ログインとページ遷移を実行"""
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            # 証明書選択スレッドの準備
            cert_thread = threading.Thread(
                target=select_certificate,
                args=(hospital_info['cert_order'],)
            )
            cert_thread.start()

            logger.info(f"{hospital_info['hospital_name']}: ページにアクセスしています... (試行 {retry_count + 1}/{max_retries})")
            
            # タイムアウトを120秒に延長し、ページロードの完了を待機
            await page.goto("https://s2.movacal.net", timeout=120000)
            await page.wait_for_load_state("networkidle", timeout=30000)
            await page.wait_for_load_state("domcontentloaded", timeout=30000)
            
            # 証明書選択の完了を待つ
            cert_thread.join(timeout=30)  # タイムアウトを30秒に設定
            
            if cert_thread.is_alive():
                logger.warning(f"{hospital_info['hospital_name']}: 証明書選択がタイムアウトしました")
                cert_thread.join()  # スレッドの終了を待機
            
            # 重複ログインの警告メッセージとログアウトボタンをチェック
            logout_button = await page.query_selector('body > div.wrapper > div.box > div > form > p > input[type=button]')
            if logout_button:
                logger.info(f"{hospital_info['hospital_name']}: 重複ログインを検出。ログアウト処理を実行...")
                await logout_button.click()
                await page.wait_for_load_state("networkidle", timeout=30000)

                # ログアウト完了画面の処理
                logger.info(f"{hospital_info['hospital_name']}: ログアウト完了画面を確認中...")
                
                try:
                    await page.wait_for_selector('form[action="auth.php"]', timeout=5000)
                    # 「ログイン画面へ」ボタンをクリック
                    login_page_button = await page.query_selector('input[value="ログイン画面へ"]')
                    if login_page_button:
                        logger.info(f"{hospital_info['hospital_name']}: ログイン画面への遷移を実行...")
                        await login_page_button.click()
                        await page.wait_for_load_state("networkidle", timeout=30000)
                    else:
                        logger.warning(f"{hospital_info['hospital_name']}: 'ログイン画面へ'ボタンが見つかりません")
                except TimeoutError:
                    logger.warning(f"{hospital_info['hospital_name']}: ログアウト完了画面が見つかりませんでした")
            
            logger.info(f"{hospital_info['hospital_name']}: ログインフォームの表示を待機中...")
            try:
                await page.wait_for_selector('input[type="text"]', timeout=10000)
            except TimeoutError:
                # セレクタが見つからない場合、ページのコンテンツをログに出力
                content = await page.content()
                logger.error(f"ページの内容: {content[:500]}...")  # 最初の500文字のみログ出力
                raise

            logger.info(f"{hospital_info['hospital_name']}: ログイン情報を入力中...")
            await page.fill('input[type="text"]', hospital_info['username'])
            await page.fill('input[type="password"]', hospital_info['password'])
            await page.click('input[type=submit]')

            await page.wait_for_load_state('networkidle', timeout=30000)
            
            content = await page.content()
            if "ホーム" not in content:
                error_msg = "ログインに失敗しました"
                if retry_count < max_retries - 1:
                    logger.warning(f"{hospital_info['hospital_name']}: {error_msg}. 再試行を行います。")
                    retry_count += 1
                    await asyncio.sleep(5)  # 5秒待機してから再試行
                    continue
                else:
                    login_status.update_hospital_status(hospital_info['hospital_name'], False, error_msg)
                    user_info['ログイン状態'] = '失敗'
                    user_info['エラー'] = error_msg
                    return False

            logger.info(f"{hospital_info['hospital_name']}: メニューページに遷移します...")
            await page.wait_for_selector('#tNavi > li.no7 > a', timeout=10000)
            await page.click('#tNavi > li.no7 > a')
            await page.wait_for_load_state('networkidle', timeout=30000)
            
            logger.info(f"{hospital_info['hospital_name']}: ログインとナビゲーションが完了しました")
            login_status.update_hospital_status(hospital_info['hospital_name'], True)
            user_info['ログイン状態'] = '成功'
            user_info['ログイン方法'] = '新規ログイン'
            return True

        except TimeoutError as e:
            retry_count += 1
            logger.warning(f"{hospital_info['hospital_name']}: タイムアウトが発生しました (試行 {retry_count}/{max_retries})")
            if retry_count < max_retries:
                await asyncio.sleep(5)  # 5秒待機してから再試行
            else:
                error_msg = f"ページアクセスが{max_retries}回タイムアウトしました: {str(e)}"
                login_status.update_hospital_status(hospital_info['hospital_name'], False, error_msg)
                user_info['ログイン状態'] = '失敗'
                user_info['エラー'] = error_msg
                return False
                
        except Exception as e:
            error_msg = f"ログイン処理中にエラー: {str(e)}"
            login_status.update_hospital_status(hospital_info['hospital_name'], False, error_msg)
            user_info['ログイン状態'] = '失敗'
            user_info['エラー'] = error_msg
            logger.error(f"{hospital_info['hospital_name']}: {error_msg}")
            logger.debug(f"エラーの詳細:\n{traceback.format_exc()}")
            return False

async def validate_login_state(page):
    """ログイン状態を検証"""
    try:
        # ホームリンクの存在を確認
        home_link = await page.query_selector('#tNavi > li.no1 > a')
        return home_link is not None
    except Exception:
        return False

async def check_error_messages(page):
    """エラーメッセージの有無をチェック"""
    try:
        error_messages = await page.query_selector_all('.error-message')
        if error_messages:
            messages = []
            for error in error_messages:
                text = await error.inner_text()
                messages.append(text)
            return messages
        return None
    except Exception:
        return None



# async def extract_patient_data(page, user_info):
#     """患者データを抽出"""
#     try:
#         # 医療機関名から抽出ロジックを判断（三宅のみ特殊仕様）
#         is_miyake = "三宅" in user_info['hospital_name']
        
#         records = await page.evaluate("""
#             (config) => {
#                 const records = [];
#                 const rows = document.querySelectorAll('tr:not([style*="display: none"])');
                
#                 for (const row of rows) {
#                     try {
#                         let isTargetRecord = false;
#                         let reAccountFlag = false;
                        
#                         // メモ/コメント列(11列目)のチェック - 「再会計」というテキストがあるか確認
#                         const memoCell = row.querySelector('td:nth-child(11)');
#                         if (memoCell) {
#                             const memoText = memoCell.textContent.trim();
#                             if (memoText.includes('再会計')) {
#                                 reAccountFlag = true;
#                                 isTargetRecord = true; // 「再会計」があれば他の条件に関わらず対象とする
#                             }
#                         }
                        
#                         // 「再会計」が無い場合の通常のフィルタリング
#                         if (!reAccountFlag) {
#                             if (config.isMiyake) {
#                                 // 三宅仕様：処置列の「受付確認」が「済」
#                                 const statusCell = row.querySelector('td:nth-child(9)');
#                                 if (statusCell) {
#                                     const statusSpans = statusCell.querySelectorAll('span');
#                                     for (const span of statusSpans) {
#                                         if (span.textContent.includes('済') && 
#                                             span.textContent.includes('受付確認')) {
#                                             isTargetRecord = true;
#                                             break;
#                                         }
#                                     }
#                                 }
#                             } else {
#                                 // 基本仕様：ステータスが「診察済」
#                                 const statusDiv = row.querySelector('div.gairai_status');
#                                 if (statusDiv && statusDiv.textContent.trim() === '診察済') {
#                                     isTargetRecord = true;
#                                 }
#                             }
                            
#                             // 会計済のレコードはスキップ（再会計フラグがある場合を除く）
#                             if (row.querySelector('div.gairai_status.status_50')) {
#                                 isTargetRecord = false;
#                             }
#                         }
                        
#                         // 抽出対象でなければスキップ
#                         if (!isTargetRecord) {
#                             continue;
#                         }
                        
#                         const idCell = row.querySelector('td:nth-child(2)');
#                         const timeCell = row.querySelector('td:nth-child(13)');
                        
#                         // 診療科情報を取得（7列目）
#                         const deptCell = row.querySelector('td:nth-child(7)');
#                         const deptText = deptCell ? deptCell.textContent.trim() : '';
#                         const department = deptText || '不明';
                        
#                         // メモ/コメント情報を取得（11列目）
#                         const commentText = memoCell ? memoCell.textContent.trim() : '';

#                         if (idCell && timeCell) {
#                             records.push({
#                                 patient_id: idCell.textContent.trim(),
#                                 department: department,
#                                 end_time: timeCell.textContent.trim(),
#                                 comment: commentText,
#                                 re_account: reAccountFlag
#                             });
#                         }
#                     } catch (err) {
#                         console.error('Row processing error:', err);
#                     }
#                 }
#                 return records;
#             }
#         """, {"isMiyake": is_miyake})
        
#         if records:
#             logger.info(f"{user_info['hospital_name']}: {len(records)}件のデータを抽出")
#             for record in records:
#                 re_account_info = "【再会計】" if record.get('re_account', False) else ""
#                 logger.info(f"抽出データ: {re_account_info}ID={record['patient_id']}, "
#                            f"診療科={record['department']}, "
#                            f"時間={record['end_time']}")
        
#         return records
        
#     except Exception as e:
#         logger.error(f"{user_info['hospital_name']}: データ抽出中にエラー: {e}")
#         return []

async def extract_patient_data(page, user_info):
    """患者データを抽出"""
    try:
        # 医療機関名から抽出ロジックを判断（三宅のみ特殊仕様）
        is_miyake = "三宅" in user_info['hospital_name']
        
        records = await page.evaluate("""
            (config) => {
                const records = [];
                const rows = document.querySelectorAll('tr:not([style*="display: none"])');
                
                for (const row of rows) {
                    try {
                        let isTargetRecord = false;
                        let isReAccount = false;
                        
                        if (config.isMiyake) {
                            // 三宅仕様：処置列の「受付確認」が「済」
                            const statusCell = row.querySelector('td:nth-child(9)');
                            if (statusCell) {
                                const statusSpans = statusCell.querySelectorAll('span');
                                for (const span of statusSpans) {
                                    if (span.textContent.includes('済') && 
                                        span.textContent.includes('受付確認')) {
                                        isTargetRecord = true;
                                        // 再会計かどうかを示す要素の検索
                                        isReAccount = span.textContent.includes('再会計') || 
                                                     span.textContent.includes('再算定');
                                        break;
                                    }
                                }
                            }
                        } else {
                            // 基本仕様：ステータスが「診察済」
                            const statusDiv = row.querySelector('div.gairai_status');
                            if (statusDiv) {
                                const statusText = statusDiv.textContent.trim();
                                if (statusText === '診察済') {
                                    isTargetRecord = true;
                                    // 再会計を示す要素を検索
                                    isReAccount = row.textContent.includes('再会計') || 
                                                 row.textContent.includes('再算定');
                                }
                            }
                        }
                        
                        // 抽出対象でない、または会計済のレコードはスキップ
                        if (!isTargetRecord || row.querySelector('div.gairai_status.status_50')) {
                            continue;
                        }
                        
                        const idCell = row.querySelector('td:nth-child(2)');
                        const timeCell = row.querySelector('td:nth-child(13)');
                        
                        // 診療科情報を取得（7列目）
                        const deptCell = row.querySelector('td:nth-child(7)');
                        const deptText = deptCell ? deptCell.textContent.trim() : '';
                        const department = deptText || '不明';  // 空文字列の場合も「不明」を設定

                        if (idCell && timeCell) {
                            records.push({
                                patient_id: idCell.textContent.trim(),
                                department: department,
                                end_time: timeCell.textContent.trim(),
                                re_account: isReAccount  // 再会計フラグを追加
                            });
                        }
                    } catch (err) {
                        console.error('Row processing error:', err);
                    }
                }
                return records;
            }
        """, {"isMiyake": is_miyake})
        
        if records:
            logger.debug(f"{user_info['hospital_name']}: {len(records)}件のデータを抽出")
            for record in records:
                re_account_text = "【再会計】" if record.get('re_account', False) else ""
                logger.debug(f"抽出データ: {re_account_text}ID={record['patient_id']}, "
                           f"診療科={record['department']}, "
                           f"時間={record['end_time']}")
        
        return records
        
    except Exception as e:
        logger.error(f"{user_info['hospital_name']}: データ抽出中にエラー: {e}")
        return []


# async def process_and_insert_data(records, user_info):
#     """データを医療機関情報とともにmedical_data_inserterに渡す"""
#     try:
#         if not records:
#             return

#         json_data = {
#             "hospital_name": user_info['hospital_name'],
#             "system_type": user_info.get('システム種別', 'モバカル'),
#             "team": user_info['team'],
#             "issue_key": user_info['issue_key'],
#             "patients": records
#         }

#         script_dir = os.path.dirname(os.path.abspath(__file__))
#         inserter_path = os.path.join(script_dir, "medical_data_inserter.py")
        
#         try:
#             # Windows環境での文字化け対策
#             startupinfo = None
#             if os.name == 'nt':
#                 startupinfo = subprocess.STARTUPINFO()
#                 startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
#             process = await asyncio.create_subprocess_exec(
#                 sys.executable,
#                 inserter_path,
#                 stdin=asyncio.subprocess.PIPE,
#                 stdout=asyncio.subprocess.PIPE,
#                 stderr=asyncio.subprocess.PIPE,
#                 env={
#                     **os.environ,
#                     'PYTHONIOENCODING': 'utf-8',
#                 },
#                 startupinfo=startupinfo
#             )

#             # JSON文字列に変換してバイト列として送信
#             json_str = json.dumps(json_data, ensure_ascii=False)
#             stdout, stderr = await process.communicate(json_str.encode('utf-8'))
            
#             # Windows環境でのデコード処理
#             def safe_decode(bytes_data):
#                 if not bytes_data:
#                     return ""
#                 try:
#                     return bytes_data.decode('cp932')
#                 except UnicodeDecodeError:
#                     try:
#                         return bytes_data.decode('utf-8')
#                     except UnicodeDecodeError:
#                         logger.warning("デコードに失敗したため、エラーメッセージをバイナリとして処理します")
#                         return str(bytes_data)

#             decoded_stdout = safe_decode(stdout)
#             decoded_stderr = safe_decode(stderr)
            
#             # logger.info(f"医療機関: {json_data['hospital_name']}")
            
#             if process.returncode == 0:
#                 if decoded_stdout.strip():
#                     logger.info(f"データベース挿入成功: {decoded_stdout}")
#                 logger.debug("データベース挿入が完了しました")
#             else:
#                 logger.error(f"データベース挿入エラー")
#                 if decoded_stderr:
#                     logger.error(f"エラー内容: {decoded_stderr}")
#                 if decoded_stdout:
#                     logger.error(f"標準出力: {decoded_stdout}")

#         except Exception as e:
#             logger.error(f"医療機関 {json_data['hospital_name']}: "
#                         f"medical_data_inserterの実行中にエラー: {str(e)}")
#             logger.error(f"詳細なエラー情報: {traceback.format_exc()}")

#     except Exception as e:
#         hospital_name = user_info.get('hospital_name', 'Unknown Hospital')
#         logger.error(f"医療機関 {hospital_name}: データ処理中にエラー: {str(e)}")
#         logger.error(f"詳細なエラー情報: {traceback.format_exc()}")

async def process_and_insert_data(records, user_info):
    """データを医療機関情報とともにmedical_data_inserterに渡す"""
    try:
        if not records:
            return

        json_data = {
            "hospital_name": user_info['hospital_name'],
            "system_type": user_info.get('システム種別', 'モバカル'),
            "team": user_info['team'],
            "issue_key": user_info['issue_key'],
            "patients": records
        }

        script_dir = os.path.dirname(os.path.abspath(__file__))
        inserter_path = os.path.join(script_dir, "medical_data_inserter.py")
        
        try:
            # Windows環境での文字化け対策
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                inserter_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={
                    **os.environ,
                    'PYTHONIOENCODING': 'utf-8',
                },
                startupinfo=startupinfo
            )

            # JSON文字列に変換してバイト列として送信
            json_str = json.dumps(json_data, ensure_ascii=False)
            stdout, stderr = await process.communicate(json_str.encode('utf-8'))
            
            # Windows環境でのデコード処理
            def safe_decode(bytes_data):
                if not bytes_data:
                    return ""
                try:
                    return bytes_data.decode('cp932')
                except UnicodeDecodeError:
                    try:
                        return bytes_data.decode('utf-8')
                    except UnicodeDecodeError:
                        logger.warning("デコードに失敗したため、エラーメッセージをバイナリとして処理します")
                        return str(bytes_data)

            decoded_stdout = safe_decode(stdout)
            decoded_stderr = safe_decode(stderr)
            
            if process.returncode == 0:
                for record in records:
                    if record.get('re_account', False):
                        logger.info(f"【再会計】データベース挿入成功: 病院={user_info['hospital_name']}, 患者ID={record['patient_id']}")
                logger.debug("データベース挿入が完了しました")
            else:
                logger.error(f"データベース挿入エラー")
                if decoded_stderr:
                    logger.error(f"エラー内容: {decoded_stderr}")
                if decoded_stdout:
                    logger.error(f"標準出力: {decoded_stdout}")

        except Exception as e:
            logger.error(f"医療機関 {json_data['hospital_name']}: "
                        f"medical_data_inserterの実行中にエラー: {str(e)}")
            logger.error(f"詳細なエラー情報: {traceback.format_exc()}")

    except Exception as e:
        hospital_name = user_info.get('hospital_name', 'Unknown Hospital')
        logger.error(f"医療機関 {hospital_name}: データ処理中にエラー: {str(e)}")
        logger.error(f"詳細なエラー情報: {traceback.format_exc()}")

async def periodic_extract_all(pages, interval, user_infos):
    """定期的に全てのページから患者データを抽出し、medical_data_inserterを呼び出してデータベースに挿入する"""
    while True:
        for index, (page, user_info) in enumerate(zip(pages, user_infos)):
            try:
                patient_data = await extract_patient_data(page, user_info)
                
                if patient_data:
                    await process_and_insert_data(patient_data, user_info)
            except Exception as e:
                logger.error(f"ユーザー {index + 1} のデータ抽出中にエラー: {e}")
            
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.debug("periodic_extract_allがキャンセルされました")
                break

# async def run(playwright, config, shutdown_event, login_status):
#     """メインの処理を実行する（非同期関数）"""
#     def sanitize_directory_name(name: str) -> str:
#         """ディレクトリ名として使用できない文字を除去する"""
#         invalid_chars = '<>:"/\\|?*'
#         for char in invalid_chars:
#             name = name.replace(char, '_')
#         return name

#     contexts = []
#     pages = []
#     user_infos = []
#     extract_task = None
#     extract_interval = int(config.get('setting', 'movacal_polling_interval', fallback=10))

#     try:
#         # Backlogから医療機関情報を取得
#         hospitals = get_hospital_info(config)
#         if not hospitals:
#             logger.error("医療機関情報を取得できませんでした")
#             return

#         # ログイン処理の開始を記録
#         login_status.start_login_process(len(hospitals))

#         # 一つずつログイン処理を実行
#         for index, hospital in enumerate(hospitals):
#             if shutdown_event.is_set():
#                 break

#             try:
#                 # セッションディレクトリを課題キーベースで作成
#                 system_type = sanitize_directory_name(hospital['system_type'])
#                 issue_key = sanitize_directory_name(hospital['issue_key'])
#                 user_data_dir = os.path.join(SESSION_DIR, f"{system_type}_{issue_key}")
#                 os.makedirs(user_data_dir, exist_ok=True)
                
#                 context = await playwright.chromium.launch_persistent_context(
#                     user_data_dir,
#                     headless=False,
#                     viewport={'width': 1200, 'height': 1000},
#                     args=[
#                         '--no-first-run',
#                         '--no-default-browser-check'
#                         # '--restore-last-session=true' # 証明書利用の電子カルテの場合、前回セッションを利用してログインする処理は不要
#                     ]
#                 )
#                 contexts.append(context)

#                 # 既存のページがある場合は最初のページを使用し、
#                 # ない場合は新しいページを作成する
#                 if context.pages:
#                     page = context.pages[0]
#                     # 2番目以降のページがあれば閉じる
#                     for extra_page in context.pages[1:]:
#                         await extra_page.close()
#                 else:
#                     page = await context.new_page()

#                 pages.append(page)

#                 user_info = {
#                     'ユーザー': index + 1,
#                     'セッション情報': user_data_dir,
#                     'hospital_name': hospital['hospital_name'],
#                     'システム種別': hospital['system_type'],
#                     'team': hospital['team'],
#                     'issue_key': hospital['issue_key'],
#                     'login_info': hospital
#                 }
#                 user_infos.append(user_info)

#                 # ログイン処理を実行（リトライ機能付き）
#                 max_retries = 3
#                 retry_count = 0
#                 login_success = False

#                 while not login_success and retry_count < max_retries:
#                     try:
#                         login_success = await navigate_and_login(page, hospital, index, user_info, login_status)
#                         if login_success:
#                             await asyncio.sleep(5)  # 次の医療機関の処理前に待機（証明書選択があるため長めに）
#                             break
#                         else:
#                             retry_count += 1
#                             if retry_count < max_retries:
#                                 logger.info(f"{hospital['hospital_name']}: ログイン再試行 {retry_count}/{max_retries}")
#                                 await asyncio.sleep(5)  # リトライ前の待機
#                     except Exception as e:
#                         retry_count += 1
#                         logger.error(f"{hospital['hospital_name']}: ログイン試行 {retry_count} でエラー: {e}")
#                         if retry_count < max_retries:
#                             await asyncio.sleep(5)

#             except Exception as e:
#                 logger.error(f"ブラウザ {index + 1} の初期化中にエラー: {e}")
#                 login_status.update_hospital_status(hospital['hospital_name'], False, str(e))
#                 continue

#         # 定期的なデータ抽出の実行
#         if not shutdown_event.is_set():
#             extract_task = asyncio.create_task(
#                 periodic_extract_all(pages, extract_interval, user_infos)
#             )

#         # メインループ
#         while not shutdown_event.is_set():
#             try:
#                 await asyncio.wait_for(shutdown_event.wait(), timeout=1.0)
#             except asyncio.TimeoutError:
#                 continue
#             except Exception as e:
#                 logger.error(f"メインループでエラー: {e}")
#                 break

#     except asyncio.CancelledError:
#         logger.debug("実行がキャンセルされました")
#     except Exception as e:
#         logger.error(f"実行中にエラーが発生しました: {e}")
#         logger.debug("スタックトレース:", exc_info=True)
#     finally:
#         if extract_task and not extract_task.done():
#             extract_task.cancel()
#             try:
#                 await extract_task
#             except asyncio.CancelledError:
#                 pass

#         # コンテキストの安全な終了
#         for context in reversed(contexts):
#             try:
#                 if context:
#                     await asyncio.shield(context.close())
#             except Exception as e:
#                 logger.debug(f"コンテキスト終了中の無視可能なエラー: {e}")
        
#         pages.clear()
#         contexts.clear()

async def run(playwright, config, shutdown_event, login_status, hospitals):
    """メインの処理を実行する（非同期関数）"""
    def sanitize_directory_name(name: str) -> str:
        """ディレクトリ名として使用できない文字を除去する"""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, '_')
        return name

    contexts = []
    pages = []
    user_infos = []
    extract_task = None
    extract_interval = int(config.get('setting', 'movacal_polling_interval', fallback=10))

    try:
        # ログイン処理の開始を記録
        login_status.start_login_process(len(hospitals))

        # 一つずつログイン処理を実行
        for index, hospital in enumerate(hospitals):
            if shutdown_event.is_set():
                break

            try:
                # セッションディレクトリを課題キーベースで作成
                system_type = sanitize_directory_name(hospital['system_type'])
                issue_key = sanitize_directory_name(hospital['issue_key'])
                user_data_dir = os.path.join(SESSION_DIR, f"{system_type}_{issue_key}")
                os.makedirs(user_data_dir, exist_ok=True)
                
                context = await playwright.chromium.launch_persistent_context(
                    user_data_dir,
                    headless=False,
                    viewport={'width': 1200, 'height': 1000},
                    args=[
                        '--no-first-run',
                        '--no-default-browser-check'
                        # '--restore-last-session=true' # 証明書利用の電子カルテの場合、前回セッションを利用してログインする処理は不要
                    ]
                )
                contexts.append(context)

                # 既存のページがある場合は最初のページを使用し、
                # ない場合は新しいページを作成する
                if context.pages:
                    page = context.pages[0]
                    # 2番目以降のページがあれば閉じる
                    for extra_page in context.pages[1:]:
                        await extra_page.close()
                else:
                    page = await context.new_page()

                pages.append(page)

                user_info = {
                    'ユーザー': index + 1,
                    'セッション情報': user_data_dir,
                    'hospital_name': hospital['hospital_name'],
                    'システム種別': hospital['system_type'],
                    'team': hospital['team'],
                    'issue_key': hospital['issue_key'],
                    'login_info': hospital
                }
                user_infos.append(user_info)

                # ログイン処理を実行（リトライ機能付き）
                max_retries = 3
                retry_count = 0
                login_success = False

                while not login_success and retry_count < max_retries:
                    try:
                        login_success = await navigate_and_login(page, hospital, index, user_info, login_status)
                        if login_success:
                            await asyncio.sleep(5)  # 次の医療機関の処理前に待機（証明書選択があるため長めに）
                            break
                        else:
                            retry_count += 1
                            if retry_count < max_retries:
                                logger.info(f"{hospital['hospital_name']}: ログイン再試行 {retry_count}/{max_retries}")
                                await asyncio.sleep(5)  # リトライ前の待機
                    except Exception as e:
                        retry_count += 1
                        logger.error(f"{hospital['hospital_name']}: ログイン試行 {retry_count} でエラー: {e}")
                        if retry_count < max_retries:
                            await asyncio.sleep(5)

            except Exception as e:
                logger.error(f"ブラウザ {index + 1} の初期化中にエラー: {e}")
                login_status.update_hospital_status(hospital['hospital_name'], False, str(e))
                continue

        # 定期的なデータ抽出の実行
        if not shutdown_event.is_set():
            extract_task = asyncio.create_task(
                periodic_extract_all(pages, extract_interval, user_infos)
            )

        # メインループ
        while not shutdown_event.is_set():
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"メインループでエラー: {e}")
                break

    except asyncio.CancelledError:
        logger.debug("実行がキャンセルされました")
    except Exception as e:
        logger.error(f"実行中にエラーが発生しました: {e}")
        logger.debug("スタックトレース:", exc_info=True)
    finally:
        if extract_task and not extract_task.done():
            extract_task.cancel()
            try:
                await extract_task
            except asyncio.CancelledError:
                pass

        # コンテキストの安全な終了
        for context in reversed(contexts):
            try:
                if context:
                    await asyncio.shield(context.close())
            except Exception as e:
                logger.debug(f"コンテキスト終了中の無視可能なエラー: {e}")
        
        pages.clear()
        contexts.clear()

# async def main_with_shutdown(shutdown_event, login_status):
#     """シャットダウンイベントに対応したメイン関数"""
#     try:
#         logger.info("プログラムを開始します")
#         config = load_config()
#         if config is None:
#             logger.error("設定の読み込みに失敗しました")
#             return

#         # 医療機関情報を取得
#         hospitals = get_hospital_info(config)
#         if not hospitals:
#             logger.info("ポーリング対象の医療機関がないため、モニタリングをスキップします")
#             # ログイン状態を完了に設定（医療機関数0として）
#             login_status.start_login_process(0)
#             # 完了のマークを付ける
#             login_status.update_hospital_status("モバカル", True)
#             login_status.get_login_summary()  # ログ出力
#             return

#         async with async_playwright() as playwright:
#             await run(playwright, config, shutdown_event, login_status)

#     except asyncio.CancelledError:
#         logger.debug("メイン処理がキャンセルされました")
#     except Exception as e:
#         logger.error(f"予期せぬエラーが発生しました: {e}")
#         logger.debug("スタックトレース:", exc_info=True)

async def main_with_shutdown(shutdown_event, login_status):
    """シャットダウンイベントに対応したメイン関数"""
    try:
        logger.info("プログラムを開始します")
        config = load_config()
        if config is None:
            logger.error("設定の読み込みに失敗しました")
            return

        # 医療機関情報を取得
        hospitals = get_hospital_info(config)
        if not hospitals:
            logger.info("ポーリング対象の医療機関がないため、モニタリングをスキップします")
            # ログイン状態を完了に設定（医療機関数0として）
            login_status.start_login_process(0)
            # 完了のマークを付ける
            login_status.update_hospital_status("モバカル", True)
            login_status.get_login_summary()  # ログ出力
            return

        async with async_playwright() as playwright:
            await run(playwright, config, shutdown_event, login_status, hospitals)

    except asyncio.CancelledError:
        logger.debug("メイン処理がキャンセルされました")
    except Exception as e:
        logger.error(f"予期せぬエラーが発生しました: {e}")
        logger.debug("スタックトレース:", exc_info=True)

def validate_config(config):
    """設定値の検証"""
    required_settings = {
        'backlog': ['space_name', 'api_key', 'hospital_project_id']
    }
    
    for section, keys in required_settings.items():
        if section not in config:
            logger.error(f"設定セクション '{section}' が見つかりません")
            return False
            
        for key in keys:
            if key not in config[section]:
                logger.error(f"設定項目 '{key}' が {section} セクションに見つかりません")
                return False
            if not config[section][key]:
                logger.error(f"設定項目 '{key}' が空です")
                return False
    
    return True

if __name__ == "__main__":
    # 直接実行時用のシャットダウンイベントとログイン状態管理
    shutdown_event = asyncio.Event()
    login_status = LoginStatus("モバカル")  # システム名を指定してLoginStatusを初期化
    try:
        asyncio.run(main_with_shutdown(shutdown_event, login_status))
    except KeyboardInterrupt:
        logger.info("キーボード割り込みを検知しました")