# src/core/clius_monitor.py
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
from datetime import datetime
import re
import logging
import traceback
from logging import Formatter
from io import StringIO
from typing import List
import subprocess
import json
from logging.handlers import TimedRotatingFileHandler
import requests
from typing import List, Dict, Any

# ロガーの初期化
logger = LoggerFactory.setup_logger('clius_monitor')

# パス定義
LOG_DIR = os.path.join(project_root, 'log')
DEBUG_DIR = os.path.join(LOG_DIR, 'debug')
CONFIG_DIR = os.path.join(project_root, 'config')
SESSION_DIR = os.path.join(project_root, 'session')

def load_config():
    """INIファイルから設定情報を読み取る"""
    config = configparser.ConfigParser()
    config_path = os.path.join(CONFIG_DIR, 'config.ini')
    
    if os.path.exists(config_path):
        config.read(config_path, encoding='utf-8')
    else:
        logging.error("設定ファイルが見つかりません！")
    
    return config

def clean_old_logs(log_dir, days):
    """指定された日数より古いログファイルを削除する"""
    current_time = datetime.now()
    for filename in os.listdir(log_dir):
        if filename.endswith("_output.log") or filename.endswith("_output_debug.log"):
            file_path = os.path.join(log_dir, filename)
            file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
            if (current_time - file_time).days > days:
                os.remove(file_path)
                logging.info(f"古いログファイルを削除しました: {filename}")

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
    """Backlogから特定条件の医療機関情報を取得する"""
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
                # システム種別が "CLIUS" であることを確認
                if not issue.get('issueType') or issue['issueType'].get('name') != 'CLIUS':
                    continue

                custom_fields = issue.get('customFields', [])
                polling = get_custom_field_value(custom_fields, 'ポーリング')
                
                if polling == 'ON':
                    # グループ情報の取得とデバッグログ
                    team = get_custom_field_value(custom_fields, 'グループ')
                    logger.debug(f"取得したグループ情報: {team} (型: {type(team)})")

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
                        "issue_key": issue.get('issueKey', ''),
                        "team": team,
                        "system_type": 'CLIUS'
                    }

                    # グループ情報の集計
                    if team:
                        team_counts[team] = team_counts.get(team, 0) + 1

                    all_hospitals.append(hospital_info)
                    filtered_count += 1
                    logger.info(f"医療機関を追加: {hospital_info['hospital_name']} (グループ: {team})")

            except Exception as e:
                logger.error(f"課題 {issue.get('issueKey', '不明')} の処理中にエラー: {e}")
                continue

        # グループごとの集計結果を表示
        logger.info("グループごとのCLIUS医療機関数:")
        for team, count in team_counts.items():
            if team:  # グループ未設定は表示しない
                logger.info(f"- {team}: {count}件")

        logger.info(f"取得した全課題数: {len(issues)}")
        logger.info(f"CLIUS・ポーリング有効な医療機関数: {filtered_count}")
        
        if not all_hospitals:
            logger.warning("条件を満たす医療機関が見つかりませんでした")
        
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
      
async def login_with_session(page, hospital_info, index, login_url, user_info):
    '''前回保存のセッションを使用してログイン（非同期関数）'''
    try:
        logging.info(f"ユーザー {index + 1}: セッションを使用してログイン試行中...")
        await page.goto(login_url, timeout=60000)
        
        try:
            await handle_popups(page, index, user_info)
        except Exception as e:
            logging.error(f"ユーザー {index + 1}: ポップアップ処理中にエラーが発生しました(A): {str(e)}")
        
        if await wait_for_login_success(page):
            logging.info(f"ユーザー {index + 1}: 保存されたセッション情報を使用してログインしました")
            user_info['ログイン状態'] = '成功'
            user_info['ログイン方法'] = 'セッション'

            await handle_post_login_actions(page, index, user_info, hospital_info)
            return True
        else:
            logging.info(f"ユーザー {index + 1}: セッションが無効なため、新規ログインを試みます")
            return await perform_login(page, hospital_info, index, user_info)
    except Exception as e:
        logging.error(f"ユーザー {index + 1}: セッションを使用したログイン中にエラーが発生しました: {str(e)}")
        user_info['エラー'] = f"セッションログイン中のエラー: {str(e)}"
        user_info['ログイン状態'] = '失敗'
        return False
    
async def perform_login(page, hospital_info, index, user_info):
    '''セッションを使わないログイン処理（非同期関数）'''
    try:
        logging.info(f"ユーザー {index + 1}: ログインフォームの表示を待機中...")
        await page.wait_for_selector("#login-id", state="visible", timeout=10000)
        
        logging.info(f"ユーザー {index + 1}: ログイン情報を入力中...")
        await page.fill("#login-id", hospital_info['username'])
        await page.fill("#login-password", hospital_info['password'])
        
        login_button = await page.query_selector("button:has(img[src*='btn-login.svg'])")
        if login_button:
            await login_button.click()
            try:
                await handle_popups(page, index, user_info)
            except Exception as e:
                logging.error(f"ユーザー {index + 1}: ポップアップ処理中にエラーが発生しました(C): {str(e)}")
        else:
            user_info['ログイン状態'] = '失敗'
            user_info['エラー'] = "ログインボタンが見つかりません"
            return False

        if await wait_for_login_success(page):
            logging.info(f"ユーザー {index + 1}: ログイン成功（セッション不使用）")
            user_info['ログイン状態'] = '成功'
            user_info['ログイン方法'] = '新規ログイン'
            
            await handle_post_login_actions(page, index, user_info, hospital_info)
            return True
        else:
            user_info['ログイン状態'] = '失敗'
            user_info['エラー'] = "ログイン成功の確認ができませんでした"
            return False

    except Exception as e:
        user_info['ログイン状態'] = '失敗'
        user_info['エラー'] = f"ログイン中に予期しないエラーが発生しました: {str(e)}"
        return False

async def detect_popup_or_login(page, index):
    '''ポップアップやページ状況の検出（非同期関数）'''
    try:
        # ダイアログコンテナの存在を確認
        dialog_container = await page.query_selector("mat-dialog-container")
        if not dialog_container:
            return None

        # ダイアログ内のテキストを取得
        content = await dialog_container.inner_text()
        if not content:
            return None

        logger.debug(f"ユーザー {index + 1}: ダイアログ内容を検出: {content[:100]}...")

        # 特定のポップアップタイプを判定
        if "セッションの有効期限が切れました" in content:
            logger.info(f"ユーザー {index + 1}: セッション期限切れを検出")
            return "session_expired"
        elif "マスタダウンロード" in content:
            logger.info(f"ユーザー {index + 1}: マスターダウンロードを検出")
            return "master_download"
        elif "以下のマスターに最新版があります" in content:
            logger.info(f"ユーザー {index + 1}: マスター更新を検出")
            return "master_update"
        elif "お知らせ" in content:
            # お知らせポップアップの追加検証
            notice_title = await page.query_selector("mat-dialog-container .mat-dialog-title")
            if notice_title and await notice_title.inner_text() == "お知らせ":
                logger.info(f"ユーザー {index + 1}: お知らせポップアップを検出")
                return "notification"
        else:
            logger.debug(f"ユーザー {index + 1}: 未知のダイアログを検出")
            return "unknown"

        # ログインフォームの検出
        login_form = await page.query_selector("#login-id")
        if login_form:
            logger.info(f"ユーザー {index + 1}: ログインフォームを検出")
            return "login_required"

        return None
    except Exception as e:
        logger.error(f"ユーザー {index + 1}: ポップアップ検出中にエラー: {e}")
        return None
    
async def handle_post_login_actions(page, index, user_info, hospital_info):
    """ログイン後の共通処理をまとめた関数"""
    try:
        # 最初のポップアップチェックと処理
        popup_type = await detect_popup_or_login(page, index)
        if popup_type:
            await handle_popups(page, index, user_info)
        await page.wait_for_timeout(2000)

        # 病院名の抽出
        await extract_hospital_name(page, user_info, hospital_info.get('hospital_name', ''))
        await page.wait_for_timeout(2000)

        # ステータスのチェックと修正
        status, was_corrected = await check_and_correct_status(page, index)
        if status:
            user_info['ステータス'] = '正常' if status.get('正しい状態', False) else '異常'
            if was_corrected:
                user_info['ステータス'] += '（修正済み）'
        else:
            user_info['ステータス'] = '確認失敗'

        # 最終的な状態確認
        final_popup = await detect_popup_or_login(page, index)
        if final_popup:
            await handle_popups(page, index, user_info)

    except Exception as e:
        logger.error(f"ユーザー {index + 1}: ログイン後の処理中にエラー: {e}")
        # エラー発生時もuser_infoを適切に更新
        user_info.setdefault('ステータス', '確認失敗')

async def handle_popups(page, index, user_info):
    '''detect_popup_or_login関数の検出内容にあわせて適切に処理を実施（非同期関数）'''
    max_attempts = 5
    for attempt in range(max_attempts):
        logging.info(f"ユーザー {index + 1}: ポップアップチェック試行 {attempt + 1}/{max_attempts}")
        popup_type = await detect_popup_or_login(page, index)
        if popup_type is None:
            logging.info(f"ユーザー {index + 1}: ポップアップは検出されませんでした")
            return

        logging.info(f"ユーザー {index + 1}: タイプ '{popup_type}' を検出しました")

        handlers = {
            "session_expired": handle_session_expired_popup,
            "master_update": handle_master_update_popup,
            "master_download": handle_master_download_popup,
            "notification": handle_notification_popup,
            "unknown": handle_unknown_popup,
            "login_required": handle_login_popup
        }

        handler = handlers.get(popup_type)
        if handler:
            try:
                if popup_type == "login_required":
                    success = await handler(page, index, user_info)
                else:
                    success = await handler(page, index)
                
                if success:
                    logging.info(f"ユーザー {index + 1}: {popup_type} の処理に成功しました")
                    await page.wait_for_timeout(2000)  # 処理後の短い待機時間
                else:
                    logging.warning(f"ユーザー {index + 1}: {popup_type} の処理に失敗しました")
            except Exception as e:
                logging.error(f"ユーザー {index + 1}: {popup_type} の処理中にエラーが発生しました: {str(e)}")
        else:
            logging.warning(f"ユーザー {index + 1}: 未知のタイプです: {popup_type}")

    logging.warning(f"ユーザー {index + 1}: 最大試行回数に達したため、処理を終了します")

async def click_button(page, button_text, index, selector=None, timeout=5000):
    '''ポップアップのボタンをクリック（非同期関数）'''
    try:
        if selector:
            button_selector = f"{selector}:has-text('{button_text}')"
        else:
            button_selector = f"button:has-text('{button_text}')"
        
        button = await page.wait_for_selector(button_selector, state="visible", timeout=timeout)
        if button:
            await button.click()
            logging.info(f"ユーザー {index + 1}: '{button_text}'ボタンをクリックしました")
            return True
        else:
            logging.warning(f"ユーザー {index + 1}: '{button_text}'ボタンが見つかりません")
            return False
    except Exception as e:
        logging.error(f"ユーザー {index + 1}: '{button_text}'ボタンのクリック中にエラーが発生しました: {str(e)}")
        return False

async def handle_session_expired_popup(page, index):
    '''セッションの有効期限が切れました'''
    logging.warning(f"ユーザー {index + 1}: セッション有効期限切れのポップアップが検出されました。OKボタンを探します")
    return await click_button(page, "OK", index, selector="app-button > button")

async def handle_master_update_popup(page, index):
    '''マスター最新版'''
    logging.warning(f"ユーザー {index + 1}: マスター最新版のポップアップが検出されました。設定するボタンを探します")
    return await click_button(page, "設定する", index, selector="app-button > button")

async def handle_master_download_popup(page, index):
    '''マスターダウンロード'''
    logging.warning(f"ユーザー {index + 1}: マスターダウンロードのポップアップが検出されました。閉じるボタンを探します")
    # return await click_button(page, "閉じる", index, selector="#mat-mdc-dialog-2 .footer button", timeout=120000)  # 2分待機してからボタンを押す
    return await click_button(page, "閉じる", index, selector="div.footer button", timeout=120000)  # 2分待機してからボタンを押す

async def handle_notification_popup(page, index):
    '''お知らせ'''
    logging.warning(f"ユーザー {index + 1}: お知らせのポップアップが検出されました。閉じるボタンを探します")
    return await click_button(page, "閉じる", index, selector="footer > div > button")

async def handle_unknown_popup(page, index):
    '''上記以外のポップアップ'''
    logging.warning(f"ユーザー {index + 1}: 未知のポップアップが検出されました。閉じるボタンを探します")
    return await click_button(page, "閉じる", index, selector="app-button > button")

# async def handle_login_popup(page, index, user_info):
#     '''ログインフォーム'''
#     logging.info(f"ユーザー {index + 1}: ログインページが検出されました。再ログインを試みます")
#     return await perform_login(page, user_info['login_info'], index, user_info)

async def handle_login_popup(page, index, user_info):
    '''ログインフォーム'''
    logging.info(f"ユーザー {index + 1}: ログインページが検出されました。再ログインを試みます")
    if 'login_info' not in user_info:
        logging.error(f"ユーザー {index + 1}: user_info に 'login_info' が存在しません")
        return False
    return await perform_login(page, user_info['login_info'], index, user_info)

async def wait_for_login_success(page, timeout=60):
    """ログイン成功を待つ"""
    success_selector = "div > div > app-list-header"
    try:
        await page.wait_for_selector(success_selector, timeout=timeout * 1000) # 表のヘッダーが表示されていればログイン成功とみなす
        return True
    except TimeoutError:
        return False

async def check_and_correct_status(page, index):
    '''ログイン後のボタンステータスの確認する（非同期関数）'''
    try:
        buttons = ['予約', '受付', '診察待', '診察終了', 'ORCA送信済']

        async def get_button_status():
            try:
                status = {}
                all_disabled_except_orca = True
                
                button_statuses = await page.evaluate(f"""
                    () => {{
                        const buttons = {buttons};
                        return buttons.map(text => {{
                            const button = Array.from(document.querySelectorAll('button')).find(el => el.textContent.includes(text));
                            if (button) {{
                                const isDisabled = button.disabled || button.classList.contains('disabled');
                                return {{ text, innerText: button.innerText, isDisabled, exists: true }};
                            }}
                            return {{ text, exists: false }};
                        }});
                    }}
                """)

                for button_info in button_statuses:
                    key = button_info['text']
                    if button_info['exists']:
                        if key == 'ORCA送信済':
                            status[key] = not button_info['isDisabled']
                            if button_info['isDisabled']:
                                all_disabled_except_orca = False
                        else:
                            value = int(button_info['innerText'].split(':')[1].strip()) if ':' in button_info['innerText'] else 0
                            status[key] = {'value': value, 'disabled': button_info['isDisabled']}
                            if not button_info['isDisabled']:
                                all_disabled_except_orca = False
                    else:
                        status[key] = {'exists': False}

                status['正しい状態'] = all_disabled_except_orca and status.get('ORCA送信済', False)
                return status
            except Exception as e:
                logging.error(f"ユーザー {index + 1}: ボタン状態の取得中にエラーが発生しました: {str(e)}")
                return None

        status = await get_button_status()
        if status is None:
            logging.warning(f"ユーザー {index + 1}: ステータスの取得に失敗したため、修正を試みます")
            # ステータスが取得できない場合でも、修正を試みる
            for key in buttons:
                await click_button(page, key, index)
                await page.wait_for_timeout(1000)
            
            # 再度ステータスを確認
            status = await get_button_status()
            if status is None:
                return None, True  # 修正を試みたがステータスは不明

        if isinstance(status, dict) and not status.get('正しい状態', False):
            logging.info(f"ユーザー {index + 1}: ステータスが正しくありません。修正を試みます。")
            
            for key in buttons:
                if key not in status or not isinstance(status[key], dict):
                    continue

                if key == 'ORCA送信済':
                    if not status[key]:
                        await click_button(page, key, index)
                elif not status[key].get('disabled', False):
                    await click_button(page, key, index)

                await page.wait_for_timeout(1000)

            new_status = await get_button_status()
            if isinstance(new_status, dict) and new_status.get('正しい状態', False):
                return new_status, True  # 修正が必要だった場合はTrueを返す
            else:
                logging.warning(f"ユーザー {index + 1}: ステータスの修正に失敗しました。手動で確認してください。")
                return new_status, False

        return status, False  # 最初から正しい状態だった場合はFalseを返す

    except Exception as e:
        logging.error(f"ユーザー {index + 1} のステータスチェック/修正に失敗しました: {str(e)}")
        return None, True  # エラーが発生した場合でも修正を試みたとしてTrueを返す

async def extract_hospital_name(page, user_info, expected_name):
    '''病院名をチェックする（非同期関数）'''
    try:
        await page.wait_for_function("() => document.title !== ''", timeout=10000)
        title = await page.title()
        extracted_name = extract_hospital_name_from_title(title)
        user_info['抽出されたページタイトル'] = title
        user_info['抽出された病院名'] = extracted_name

        if expected_name in extracted_name:
            user_info['医療機関名の一致'] = '確認済み'
        else:
            user_info['医療機関名の一致'] = '不一致'
            user_info['警告'] = f"医療機関名が一致しません。期待値: {expected_name}, 抽出された値: {extracted_name}"
    except TimeoutError:
        user_info['エラー'] = "ページタイトルの取得に失敗しました"
        user_info['抽出された病院名'] = 'タイトル取得失敗'
        user_info['医療機関名の一致'] = '確認不可'

def extract_hospital_name_from_title(title):
    '''正規表現で病院名を抽出'''
    # match = re.search(r'\（(.+?)\）', title)
    # return match.team(1).strip() if match else title.strip()

    try:
        match = re.search(r'\（(.+?)\）', title)
        return match.group(1).strip() if match else title.strip()
    except AttributeError:
        return title.strip()

async def extract_text(page, index, user_info):
    """本日の日付をチェックする（非同期関数）"""
    try:
        await page.wait_for_selector("app-calendar-datepicker > div > div > div > div", timeout=5000)
        element = await page.query_selector("app-calendar-datepicker > div > div > div > div")
        text = await element.inner_text()
        user_info['日付確認'] = text

        today = datetime.now().strftime("%Y/%m/%d")
        if today not in text:
            await page.click("div.btn-today")
            await page.wait_for_timeout(1000)
            updated_text = await element.inner_text()
            user_info['日付確認'] = updated_text

        return text
    except TimeoutError:
        logging.error(f"ユーザー {index + 1}: テキスト抽出でタイムアウトが発生しました")
        user_info['エラー'] = "テキスト抽出に失敗しました（タイムアウト）"
        return None
    except Exception as e:
        logging.error(f"ユーザー {index + 1}: テキスト抽出中に予期しないエラーが発生しました: {str(e)}")
        user_info['エラー'] = f"テキスト抽出中のエラー: {str(e)}"
        return None


async def extract_patient_data(page, index):
    """患者IDと診察終了時刻と診療科を抽出する"""
    try:
        results = await page.evaluate("""
            () => {
                const headerSelector = 'app-splitter-pane:nth-child(2) app-list-header > div > div:nth-child(1)';
                const headerElement = document.querySelector(headerSelector);
                if (!headerElement) {
                    console.error('ヘッダー要素が見つかりません');
                    return { error: 'ヘッダー要素が見つかりません' };
                }
                
                const headerColumns = headerElement.querySelectorAll('.column');
                let departmentColumnIndex = -1;
                const allHeaders = [];
                
                headerColumns.forEach((col, index) => {
                    const text = col.textContent.trim();
                    allHeaders.push(text);
                    if (text === '診療科') {
                        departmentColumnIndex = index;
                    }
                });
                
                const rows = Array.from(document.querySelectorAll('div[class*="nopaid ng-tns-c"]'))
                    .map(el => el.closest('div[class*="grid full-width"]'));
                
                const records = rows.map(row => {
                    const columns = row.querySelectorAll('.column.data');
                    if (columns.length > 3) {
                        const endTime = columns[1].innerText.trim();
                        const thirdText = columns[2].innerText.trim();
                        const fourthText = columns[3].innerText.trim();
                        const patientId = thirdText === '' ? fourthText : thirdText;
                        
                        // 診療科情報を動的に取得（診療科列がない場合は「不明」）
                        let department = '不明';
                        if (departmentColumnIndex >= 0 && departmentColumnIndex < columns.length) {
                            const deptText = columns[departmentColumnIndex].innerText.trim();
                            department = deptText || '不明';
                        }
                        
                        return { 
                            patient_id: patientId, 
                            department: department,
                            end_time: endTime 
                        };
                    }
                    return null;
                }).filter(item => item !== null);
                
                return {
                    records: records,
                    debug: {
                        totalRows: rows.length,
                        departmentColumnIndex: departmentColumnIndex,
                        allHeaders: allHeaders,
                        timestamp: new Date().toISOString()
                    }
                };
            }
        """)
        
        if 'error' in results:
            logger.error(f"ユーザー {index + 1}: データ抽出エラー: {results['error']}")
            return []
            
        debug_info = results.get('debug', {})
        if debug_info:
            logger.debug(f"ユーザー {index + 1}: "
                      f"全行数={debug_info.get('totalRows', 0)}, "
                      f"診療科列={debug_info.get('departmentColumnIndex', -1)}, "
                      f"ヘッダー={debug_info.get('allHeaders', [])}, "
                      f"取得時刻={debug_info.get('timestamp')}")

        extracted_records = results.get('records', [])
        if extracted_records:
            for record in extracted_records:
                logger.debug(f"抽出データ - ID: {record['patient_id']}, 診療科: {record['department']}, 時間: {record['end_time']}")
        else:
            logger.debug(f"ユーザー {index + 1}: OASIS会計＆算定待ちのデータはありません")

        return extracted_records
        
    except Exception as e:
        logger.error(f"ユーザー {index + 1}: 患者IDと診察終了時刻と診療科の抽出中にエラーが発生しました: {e}")
        logger.error(traceback.format_exc())
        return []

async def periodic_extract_all(pages, interval, user_infos):
    '''定期的に全てのページから患者データを抽出し、medical_data_inserter.pyを呼び出してデータベースに挿入する'''
    script_dir = os.path.dirname(os.path.abspath(__file__))
    inserter_path = os.path.join(script_dir, "medical_data_inserter.py")
    
    while True:
        for index, (page, user_info) in enumerate(zip(pages, user_infos)):
            try:
                logger.debug(f"periodic_extract_all - user_info全体: {user_info}")
                patient_data = await extract_patient_data(page, index)
                
                if patient_data:  # データがある場合のみ処理を実行
                    # issue_keyを取得（login_infoまたは直接user_infoから）
                    issue_key = (user_info.get('login_info', {}).get('issue_key') or 
                               user_info.get('issue_key'))
                    
                    if not issue_key:
                        logger.error(f"課題キーが見つかりません: {user_info.get('医療機関名')}")
                        continue

                    # 患者IDのリストを取得
                    patient_ids = [p["patient_id"] for p in patient_data]

                    # ログのフォーマットを統一して情報を整理
                    # logger.info(f"患者データ検出: 病院名={user_info.get('医療機関名')}, "
                    #             f"チーム={user_info.get('team')}, データ件数={len(patient_data)}, "
                    #             f"患者ID={patient_ids}, Backlogチケット={issue_key}")

                    json_data = json.dumps({
                        "hospital_name": user_info.get('医療機関名', 'Unknown Hospital'),
                        "patients": patient_data,
                        "team": user_info.get('team'),
                        "system_type": user_info.get('システム種別', 'CLIUS'),
                        "issue_key": issue_key
                    })

                    try:
                        result = subprocess.run(
                            [sys.executable, inserter_path],
                            input=json_data,
                            text=True,
                            stdout=sys.stdout,
                            stderr=sys.stderr,
                            check=True
                        )
                    except subprocess.CalledProcessError as e:
                        logger.error(f"データベース挿入エラー: {e}")
            
            except Exception as e:
                logger.error(f"ユーザー {index + 1} のデータ抽出中にエラー: {e}")
        
        await asyncio.sleep(interval)


async def wait_for_page_load(page, timeout=30000):
    '''ページの読み込みが完了するのを待つ（非同期関数）'''
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout)
        return True
    except TimeoutError:
        logging.error(f"ページの読み込みがタイムアウトしました。現在のURL: {page.url}")
        return False

async def print_structured_output(user_infos, clius_polling_interval):
    '''ログイン処理の結果を構造化された形式で出力する関数'''
    output = "# CLIUS自動ログイン処理結果\n\n"
    
    output += "## 概要\n"
    output += f"- 読み込んだログイン情報: {len(user_infos)}件\n"
    output += f"- 処理完了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    
    output += "## ログイン処理結果\n\n"
    for user_info in user_infos:
        output += f"### ユーザー{user_info['ユーザー']} ({user_info.get('医療機関名', 'N/A')})\n"
        output += f"[{user_info.get('ログイン状態', 'N/A')}] ログイン状態\n"
        output += f"- ログイン方法: {user_info.get('ログイン方法', 'N/A')}\n"
        output += f"- 抽出された病院名: {user_info.get('抽出された病院名', 'N/A')}\n"
        output += f"- 医療機関名の一致: {user_info.get('医療機関名の一致', 'N/A')}\n"
        output += f"- 所属グループ: {user_info.get('グループ', '未設定')}\n"
        output += f"- 日付確認: {user_info.get('日付確認', 'N/A')}\n"
        output += f"- ステータス: {user_info.get('ステータス', 'N/A')}\n"
        
        if 'エラー' in user_info:
            output += f"- エラー: {user_info['エラー']}\n"
        
        output += "\n"
    
    output += "## 注意事項\n"
    output += "- 各ブラウザウィンドウは開いたままです\n"
    output += f"- {clius_polling_interval}秒おきにテキスト抽出を行っています\n"
    output += "- プログラムを終了するには、Ctrl + C を押してください\n"

    print(output)
    # 非同期関数として実行を完了させるために空のawaitを入れる
    await asyncio.sleep(0)

async def navigate_and_login(page, hospital_info, index, user_info, login_status):
    """ログインとページ遷移を実行"""
    try:
        # まずセッションでのログインを試みる
        logger.info(f"{hospital_info['hospital_name']}: セッションでのログインを試行中...")
        
        # ページ遷移前のボタンチェックと押下処理（繰り返し）
        max_button_attempts = 5  # 最大試行回数
        button_check_interval = 2  # チェック間隔（秒）
        
        for attempt in range(max_button_attempts):
            try:
                button = await page.query_selector("app-button > button")
                if not button:
                    logger.info(f"{hospital_info['hospital_name']}: 初期ボタンが見つからないためループを終了します")
                    break
                
                logger.info(f"{hospital_info['hospital_name']}: 初期画面でボタンを検出しました (試行 {attempt + 1})")
                await button.click()
                await page.wait_for_timeout(2000)  # ボタン押下後の待機
                logger.info(f"{hospital_info['hospital_name']}: 初期画面のボタンを押下しました")
                
                # ポップアップ処理の繰り返し
                popup_max_attempts = 5
                for popup_attempt in range(popup_max_attempts):
                    try:
                        popup_type = await detect_popup_or_login(page, index)
                        if not popup_type:
                            logger.info(f"{hospital_info['hospital_name']}: ポップアップが検出されないためループを終了します")
                            break
                        
                        logger.info(f"{hospital_info['hospital_name']}: ポップアップを検出 (種類: {popup_type}, 試行 {popup_attempt + 1})")
                        await handle_popups(page, index, user_info)
                        await page.wait_for_timeout(1000)  # ポップアップ処理後の待機
                        
                    except Exception as e:
                        logger.debug(f"{hospital_info['hospital_name']}: ポップアップ処理中の無視可能なエラー: {str(e)}")
                        break
                
                await page.wait_for_timeout(button_check_interval * 1000)
                
            except Exception as e:
                logger.debug(f"{hospital_info['hospital_name']}: 初期ボタンチェック中の無視可能なエラー: {str(e)}")
                break

        await page.goto("https://web.clius.jp/log-in-system", timeout=60000)
        await page.wait_for_load_state("networkidle", timeout=30000)
        await asyncio.sleep(2)

        # ログインの成功を確認
        if await wait_for_login_success(page, timeout=10):
            logger.info(f"{hospital_info['hospital_name']}: セッションを使用してログイン成功")
            login_status.update_hospital_status(hospital_info['hospital_name'], True)
            user_info['ログイン状態'] = '成功'
            user_info['ログイン方法'] = 'セッション'
            return True

        # セッションログインが失敗した場合、通常のログインを試みる
        logger.info(f"{hospital_info['hospital_name']}: セッションログイン失敗。通常のログインを試行...")

        # ログインフォームの表示を待機
        try:
            await page.wait_for_selector("#login-id", state="visible", timeout=20000)
        except TimeoutError:
            content = await page.content()
            logger.error(f"ページの内容: {content[:500]}...")  # 最初の500文字のみログ出力
            raise

        logger.info(f"{hospital_info['hospital_name']}: ログイン情報を入力中...")
        await page.fill("#login-id", hospital_info['username'])
        await page.fill("#login-password", hospital_info['password'])

        login_button = await page.query_selector("button:has(img[src*='btn-login.svg'])")
        if login_button:
            await login_button.click()
            
            # ログインボタン押下後のポップアップ処理（繰り返し）
            popup_max_attempts = 5
            for popup_attempt in range(popup_max_attempts):
                try:
                    popup_type = await detect_popup_or_login(page, index)
                    if not popup_type:
                        logger.info(f"{hospital_info['hospital_name']}: ポップアップが検出されないためループを終了します")
                        break
                    
                    logger.info(f"{hospital_info['hospital_name']}: ポップアップを検出 (種類: {popup_type}, 試行 {popup_attempt + 1})")
                    await handle_popups(page, index, user_info)
                    await page.wait_for_timeout(1000)  # ポップアップ処理後の待機
                    
                except Exception as e:
                    logger.error(f"ユーザー {index + 1}: ポップアップ処理中にエラー: {str(e)}")
                    break
        else:
            error_msg = "ログインボタンが見つかりません"
            login_status.update_hospital_status(hospital_info['hospital_name'], False, error_msg)
            user_info['ログイン状態'] = '失敗'
            user_info['エラー'] = error_msg
            return False

        if await wait_for_login_success(page):
            logger.info(f"{hospital_info['hospital_name']}: 通常のログインに成功")
            login_status.update_hospital_status(hospital_info['hospital_name'], True)
            user_info['ログイン状態'] = '成功'
            user_info['ログイン方法'] = '新規ログイン'
            return True
        else:
            error_msg = "ログイン成功の確認ができませんでした"
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
        return False

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
    extract_task = None  # 初期化を追加
    extract_interval = int(config.get('setting', 'clius_polling_interval', fallback=10))

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
                        '--no-default-browser-check',
                        '--restore-last-session=false'
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
                    '医療機関名': hospital['hospital_name'],
                    'システム種別': hospital['system_type'],
                    'グループ': hospital['team'],
                    'team': hospital['team'],
                    'login_info': hospital,
                    'issue_key': hospital['issue_key']
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
                            await handle_post_login_actions(page, index, user_info, hospital)
                            await asyncio.sleep(2)  # 次の医療機関の処理前に少し待機
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
        if not shutdown_event.is_set() and hospitals:  # hospitalsが空でない場合のみ実行
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
            # 医療機関数0として処理を完了
            login_status.start_login_process(0)
            # 完了のマークを付ける（医療機関数0なので追加の処理は不要）
            login_status.update_hospital_status("CLIUS", True)  # システム名だけ渡して成功を報告
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

def load_config():
    """INIファイルから設定情報を読み取る"""
    config = configparser.ConfigParser()
    config_path = os.path.join(CONFIG_DIR, 'config.ini')
    
    if not os.path.exists(config_path):
        logger.error(f"設定ファイルが見つかりません: {config_path}")
        return None
        
    try:
        config.read(config_path, encoding='utf-8')
        logger.info("設定ファイルを読み込みました")
        
        if not validate_config(config):
            logger.error("設定値の検証に失敗しました")
            return None
            
        logger.debug(f"space_name: {config['backlog']['space_name']}")
        logger.debug(f"hospital_project_id: {config['backlog']['hospital_project_id']}")
        # API keyはセキュリティのため最初の10文字のみ表示
        logger.debug(f"api_key: {config['backlog']['api_key'][:10]}...")
        
        return config
        
    except Exception as e:
        logger.error(f"設定ファイルの読み込み中にエラー: {e}")
        return None

async def main():
    try:
        logger.info("プログラムを開始します")
        config = load_config()
        if config is None:
            logger.error("設定の読み込みに失敗しました")
            return

        # プロジェクト一覧を取得して確認
        space_name = config['backlog']['space_name']
        api_key = config['backlog']['api_key']
        projects_url = f"https://{space_name}.backlog.com/api/v2/projects"
        params = {"apiKey": api_key}
        
        try:
            logger.info("アクセス可能なプロジェクト一覧を取得中...")
            response = requests.get(projects_url, params=params)
            response.raise_for_status()
            projects = response.json()
            
            logger.info("アクセス可能なプロジェクト:")
            for project in projects:
                logger.info(f"- {project['name']} (ID: {project['id']})")
                
        except Exception as e:
            logger.error(f"プロジェクト一覧の取得に失敗: {e}")
            if hasattr(e, 'response'):
                logger.error(f"エラー詳細: {e.response.text}")
            return

        async with async_playwright() as playwright:
            await run(playwright, config)
    except Exception as e:
        logger.error(f"予期せぬエラーが発生しました: {e}")
        logger.exception("スタックトレース:")


if __name__ == "__main__":
    # 直接実行時用のシャットダウンイベントとログイン状態管理
    shutdown_event = asyncio.Event()
    login_status = LoginStatus("CLIUS")  # システム名を指定してLoginStatusを初期化
    try:
        asyncio.run(main_with_shutdown(shutdown_event, login_status))
    except KeyboardInterrupt:
        logger.info("キーボード割り込みを検知しました")
