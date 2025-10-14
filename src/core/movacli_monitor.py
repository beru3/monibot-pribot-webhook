#!/usr/bin/env python3
"""
モバクリ監視システム（movacli_monitor.py）
Backlogから医療機関情報を取得し、#OASIS会計タグのデータを監視

注意: これは movacal_monitor.py とは別の新規ファイルです
対象URL: https://c1.movacal.net/home
"""

import os
import sys
import asyncio
import configparser
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import pyautogui
import time
import threading
import traceback
import requests
import subprocess
import json
from typing import List, Dict, Any

# プロジェクトルートへのパスを追加
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)

from src.utils.logger import LoggerFactory
from src.utils.login_status import LoginStatus

# ディレクトリ設定
CONFIG_DIR = os.path.join(project_root, 'config')
SESSION_DIR = os.path.join(project_root, 'session')

# ロガー設定（モバクリ専用）
logger = LoggerFactory.setup_logger('movacli')

def select_certificate(cert_order: int):
    """証明書選択ダイアログを処理（十字キーで選択）"""
    try:
        logger.debug(f"証明書選択処理を開始します (順番: {cert_order})...")
        time.sleep(3)  # 証明書ダイアログの表示を待機
        
        # 指定された順番まで下キーを押す
        for _ in range(cert_order - 1):
            time.sleep(0.5)
            pyautogui.press('down')
            
        time.sleep(1)
        pyautogui.press('enter')
        time.sleep(2)  # 証明書選択完了後の待機
        logger.debug("証明書選択が完了しました")
    except Exception as e:
        logger.error(f"証明書選択処理中にエラー: {e}")
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
    """Backlogからモバクリの医療機関情報を取得する"""
    try:
        space_name = config['backlog']['space_name']
        api_key = config['backlog']['api_key']
        project_id = config['backlog']['hospital_project_id']

        logger.info(f"Backlog APIリクエストを開始します")
        logger.info(f"プロジェクトID: {project_id}")

        base_url = f"https://{space_name}.backlog.com/api/v2"
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
        logger.info(f"取得した課題数: {len(issues)}")

        hospitals = []
        for issue in issues:
            # 種別（issueType）が「モバクリ」であることを確認
            if not issue.get('issueType') or issue['issueType'].get('name') != 'モバクリ':
                continue

            custom_fields = issue.get('customFields', [])
            
            # ポーリングがONの課題のみ
            polling = get_custom_field_value(custom_fields, 'ポーリング')
            
            if polling == 'ON':
                hospital_name = issue.get('summary', '不明')
                login_id = get_custom_field_value(custom_fields, 'ID')
                password = get_custom_field_value(custom_fields, 'パスワード')
                certificate_order = get_custom_field_value(custom_fields, '証明書順番')
                team = get_custom_field_value(custom_fields, 'グループ')
                
                hospital_info = {
                    'hospital_name': hospital_name,
                    'login_id': login_id,
                    'password': password,
                    'certificate_order': certificate_order,
                    'issue_key': issue.get('issueKey', ''),
                    'team': team,
                    'system_type': 'モバクリ'
                }
                
                hospitals.append(hospital_info)
                logger.info(f"医療機関追加: {hospital_name} (ID: {login_id}, 証明書: {certificate_order}, グループ: {team})")

        logger.info(f"モバクリ対象医療機関数: {len(hospitals)}")
        return hospitals

    except Exception as e:
        logger.error(f"医療機関情報取得中にエラー: {e}")
        logger.debug(f"エラーの詳細:\n{traceback.format_exc()}")
        return []

async def login_with_retry(page, hospital, max_retries=3):
    """ログイン処理（リトライ機能付き）"""
    for attempt in range(max_retries):
        try:
            logger.info(f"{hospital['hospital_name']}: ログイン試行 {attempt + 1}/{max_retries}")
            
            # 証明書選択が必要な場合、別スレッドで処理
            cert_thread = None
            if hospital.get('certificate_order'):
                cert_order = int(hospital['certificate_order'])
                logger.info(f"証明書選択準備: {cert_order}番目")
                
                # 証明書選択を別スレッドで実行
                cert_thread = threading.Thread(target=select_certificate, args=(cert_order,))
                cert_thread.start()
            
            # モバクリのログインページへ遷移
            await page.goto('https://c1.movacal.net/home', wait_until='domcontentloaded', timeout=60000)
            
            # 証明書選択スレッドの完了を待つ
            if cert_thread:
                cert_thread.join()
            
            await asyncio.sleep(3)
            
            # ID入力
            await page.fill('input#login-id', hospital['login_id'])
            await asyncio.sleep(0.5)
            
            # パスワード入力
            await page.fill('input#login-password', hospital['password'])
            await asyncio.sleep(0.5)
            
            # ログインボタンクリック
            await page.click('button[type="submit"].btn-secondary')
            await asyncio.sleep(5)
            
            # ログイン確認
            current_url = page.url
            if 'home' in current_url:
                logger.info(f"{hospital['hospital_name']}: ログイン成功")
                
                # プルダウンを「全日」に変更
                try:
                    await asyncio.sleep(2)  # ページの読み込みを待つ
                    
                    # プルダウンの現在の値を取得（変更前）
                    current_value_before = await page.evaluate("""
                        () => {
                            const select = document.querySelector('select#outer-home-recept-list-period');
                            if (!select) return null;
                            const selectedOption = select.options[select.selectedIndex];
                            return {
                                value: selectedOption.value,
                                text: selectedOption.text
                            };
                        }
                    """)
                    
                    if current_value_before:
                        logger.info(
                            f"{hospital['hospital_name']}: プルダウン変更前の値: "
                            f"value='{current_value_before['value']}', "
                            f"text='{current_value_before['text']}'"
                        )
                    
                    # プルダウンを「全日」に設定
                    await page.select_option('select#outer-home-recept-list-period', value='')
                    await asyncio.sleep(1)  # 設定反映を待つ
                    
                    # プルダウンの変更後の値を取得
                    current_value_after = await page.evaluate("""
                        () => {
                            const select = document.querySelector('select#outer-home-recept-list-period');
                            if (!select) return null;
                            const selectedOption = select.options[select.selectedIndex];
                            return {
                                value: selectedOption.value,
                                text: selectedOption.text
                            };
                        }
                    """)
                    
                    if current_value_after:
                        logger.info(
                            f"{hospital['hospital_name']}: プルダウン変更後の値: "
                            f"value='{current_value_after['value']}', "
                            f"text='{current_value_after['text']}'"
                        )
                        
                        # 変更が正しく反映されたか確認
                        if current_value_after['value'] == '':
                            logger.info(f"{hospital['hospital_name']}: 時間帯を「全日」に正常に設定しました")
                        else:
                            logger.warning(
                                f"{hospital['hospital_name']}: プルダウンの設定が期待値と異なります "
                                f"(期待: value='', 実際: value='{current_value_after['value']}')"
                            )
                    else:
                        logger.warning(f"{hospital['hospital_name']}: プルダウンの値取得に失敗しました")
                        
                except Exception as e:
                    logger.warning(f"{hospital['hospital_name']}: プルダウン選択エラー（処理は継続）: {e}")
                
                return True
            else:
                logger.warning(f"{hospital['hospital_name']}: ログイン失敗（試行 {attempt + 1}）")
                
        except Exception as e:
            logger.error(f"{hospital['hospital_name']}: ログインエラー（試行 {attempt + 1}）: {e}")
            await asyncio.sleep(2)
    
    logger.error(f"{hospital['hospital_name']}: {max_retries}回の試行後もログイン失敗")
    return False

# async def extract_oasis_data(page, hospital):
#     """OASIS会計データを抽出"""
#     try:
#         logger.debug(f"{hospital['hospital_name']}: データ抽出開始")
        
#         data = await page.evaluate("""
#             () => {
#                 const results = [];
                
#                 // OASIS会計タグを持つ行を取得
#                 const rows = document.querySelectorAll('tr[id^="outer-home-recept-list-item-"]');
                
#                 for (const row of rows) {
#                     // タグ列をチェック
#                     const tagCell = row.querySelector('td[name="tags"]');
#                     if (!tagCell) continue;
                    
#                     const tagText = tagCell.textContent || '';
#                     if (!tagText.includes('#OASIS会計')) continue;
                    
#                     // データ抽出
#                     const receptTimeCell = row.querySelector('td[name="recept-time"] span');
#                     const patientIdCell = row.querySelector('td[name="orca-id"]');
#                     const diagdeptCell = row.querySelector('td[name="diagdept"] select');
                    
#                     // 診療科の選択値を取得
#                     let diagdept = '';
#                     if (diagdeptCell) {
#                         const selectedOption = diagdeptCell.options[diagdeptCell.selectedIndex];
#                         if (selectedOption && selectedOption.value) {
#                             diagdept = selectedOption.text;
#                         }
#                     }
                    
#                     const record = {
#                         patient_id: patientIdCell ? patientIdCell.textContent.trim() : '',
#                         department: diagdept,
#                         end_time: receptTimeCell ? receptTimeCell.textContent.trim() : ''
#                     };
                    
#                     // 必須項目チェック
#                     if (record.patient_id) {
#                         results.push(record);
#                     }
#                 }
                
#                 return results;
#             }
#         """)
        
#         if data:
#             logger.info(f"{hospital['hospital_name']}: {len(data)}件のOASIS会計データを抽出")
        
#         return data
        
#     except Exception as e:
#         logger.error(f"{hospital['hospital_name']}: データ抽出エラー: {e}")
#         logger.debug(traceback.format_exc())
#         return []

async def extract_oasis_data(page, hospital, max_retries=3):
    """OASIS会計データを抽出（自動復旧機能付き）"""
    
    for attempt in range(max_retries):
        try:
            logger.debug(f"{hospital['hospital_name']}: データ抽出開始（試行 {attempt + 1}/{max_retries}）")
            
            data = await page.evaluate("""
                () => {
                    const results = [];
                    
                    // OASIS会計タグを持つ行を取得
                    const rows = document.querySelectorAll('tr[id^="outer-home-recept-list-item-"]');
                    
                    for (const row of rows) {
                        // タグ列をチェック
                        const tagCell = row.querySelector('td[name="tags"]');
                        if (!tagCell) continue;
                        
                        const tagText = tagCell.textContent || '';
                        if (!tagText.includes('#OASIS会計')) continue;
                        
                        // データ抽出
                        const receptTimeCell = row.querySelector('td[name="recept-time"] span');
                        const patientIdCell = row.querySelector('td[name="orca-id"]');
                        const diagdeptCell = row.querySelector('td[name="diagdept"] select');
                        
                        // 診療科の選択値を取得
                        let diagdept = '';
                        if (diagdeptCell) {
                            const selectedOption = diagdeptCell.options[diagdeptCell.selectedIndex];
                            if (selectedOption && selectedOption.value) {
                                diagdept = selectedOption.text;
                            }
                        }
                        
                        const record = {
                            patient_id: patientIdCell ? patientIdCell.textContent.trim() : '',
                            department: diagdept,
                            end_time: receptTimeCell ? receptTimeCell.textContent.trim() : ''
                        };
                        
                        // 必須項目チェック
                        if (record.patient_id) {
                            results.push(record);
                        }
                    }
                    
                    return results;
                }
            """)
            
            if data:
                logger.info(f"{hospital['hospital_name']}: {len(data)}件のOASIS会計データを抽出")
            
            # 成功したらリトライ情報をログ
            if attempt > 0:
                logger.info(f"{hospital['hospital_name']}: データ抽出成功（リトライ {attempt + 1}回目で成功）")
            
            return data
            
        except Exception as e:
            error_message = str(e)
            
            # コンテキスト破壊エラーを検知
            if "Execution context was destroyed" in error_message or \
               "navigation" in error_message.lower():
                
                logger.warning(
                    f"{hospital['hospital_name']}: コンテキスト破壊エラーを検知 "
                    f"(試行 {attempt + 1}/{max_retries})"
                )
                
                # 最大リトライ回数に達した場合
                if attempt >= max_retries - 1:
                    logger.error(
                        f"{hospital['hospital_name']}: 最大リトライ回数（{max_retries}回）に達しました"
                    )
                    logger.error(f"{hospital['hospital_name']}: データ抽出エラー: {e}")
                    logger.debug(traceback.format_exc())
                    return []
                
                # 復旧処理を実行
                try:
                    recovery_success = await perform_recovery(page, hospital['hospital_name'], attempt)
                    
                    if not recovery_success:
                        logger.error(f"{hospital['hospital_name']}: 復旧処理が失敗しました")
                        await asyncio.sleep(3)
                        continue
                    
                    # 復旧後の待機時間（徐々に長くする）
                    wait_time = 3 * (attempt + 1)
                    logger.info(f"{hospital['hospital_name']}: {wait_time}秒待機後に再試行します")
                    await asyncio.sleep(wait_time)
                    
                except Exception as recovery_error:
                    logger.error(
                        f"{hospital['hospital_name']}: 復旧処理中にエラー: {recovery_error}"
                    )
                    await asyncio.sleep(5)
                    
            else:
                # コンテキスト破壊以外のエラー
                logger.error(f"{hospital['hospital_name']}: データ抽出エラー: {e}")
                logger.debug(traceback.format_exc())
                return []
    
    # 全リトライ失敗
    logger.error(f"{hospital['hospital_name']}: 全てのリトライが失敗しました")
    return []

async def perform_recovery(page, hospital_name, attempt_number):
    """
    エラー検知時の復旧処理（Playwright版）
    
    Args:
        page: Playwrightのpageインスタンス
        hospital_name: 医療機関名
        attempt_number: 現在の試行回数
    
    Returns:
        bool: 復旧成功ならTrue、失敗ならFalse
    """
    
    logger.info(f"{hospital_name}: 復旧処理を開始します（リロード実行）")
    
    try:
        # 現在のURLを保持
        current_url = None
        try:
            current_url = page.url
            logger.info(f"{hospital_name}: 現在のURL: {current_url}")
        except Exception as e:
            logger.warning(f"{hospital_name}: URLの取得に失敗（コンテキスト完全破壊）: {e}")
        
        # ステップ1: ページリロード
        try:
            await page.reload(wait_until='domcontentloaded', timeout=30000)
            logger.info(f"{hospital_name}: ページリロード実行")
            await asyncio.sleep(2)  # リロード後の安定化待機
        except Exception as e:
            logger.warning(f"{hospital_name}: reload()失敗: {e}、代替方法を試行")
            
            # reload()が失敗した場合の代替策
            if current_url:
                try:
                    await page.goto(current_url, wait_until='domcontentloaded', timeout=30000)
                    logger.info(f"{hospital_name}: goto()でURLを再読み込み")
                    await asyncio.sleep(2)
                except Exception as e2:
                    logger.error(f"{hospital_name}: goto()も失敗: {e2}")
                    return False
            else:
                logger.error(f"{hospital_name}: リロード不可（URL不明）")
                return False
        
        # ステップ2: ページ読み込み完了を確認
        try:
            await wait_for_page_ready(page, timeout=30)
            logger.info(f"{hospital_name}: ページ読み込み完了を確認")
        except Exception as e:
            logger.warning(f"{hospital_name}: ページ読み込み確認失敗: {e}")
            # 警告のみで続行
        
        # ステップ3: コンテキストの健全性確認
        try:
            # 簡単なJavaScriptを実行してコンテキストが生きているか確認
            ready_state = await page.evaluate("document.readyState")
            logger.info(f"{hospital_name}: ページ状態: {ready_state}")
            
            if ready_state != "complete":
                logger.warning(f"{hospital_name}: ページが完全に読み込まれていません")
                await asyncio.sleep(3)  # 追加待機
        except Exception as e:
            logger.error(f"{hospital_name}: コンテキスト確認失敗: {e}")
            return False
        
        # ステップ4: プルダウンを「全日」に再設定
        try:
            # プルダウンの現在の値を取得（変更前）
            current_value_before = await page.evaluate("""
                () => {
                    const select = document.querySelector('select#outer-home-recept-list-period');
                    if (!select) return null;
                    const selectedOption = select.options[select.selectedIndex];
                    return {
                        value: selectedOption.value,
                        text: selectedOption.text
                    };
                }
            """)
            
            if current_value_before:
                logger.info(
                    f"{hospital_name}: プルダウン変更前の値: "
                    f"value='{current_value_before['value']}', "
                    f"text='{current_value_before['text']}'"
                )
            
            # プルダウンを「全日」に設定
            await page.select_option('select#outer-home-recept-list-period', value='')
            await asyncio.sleep(1)  # 設定反映を待つ
            
            # プルダウンの変更後の値を取得
            current_value_after = await page.evaluate("""
                () => {
                    const select = document.querySelector('select#outer-home-recept-list-period');
                    if (!select) return null;
                    const selectedOption = select.options[select.selectedIndex];
                    return {
                        value: selectedOption.value,
                        text: selectedOption.text
                    };
                }
            """)
            
            if current_value_after:
                logger.info(
                    f"{hospital_name}: プルダウン変更後の値: "
                    f"value='{current_value_after['value']}', "
                    f"text='{current_value_after['text']}'"
                )
                
                # 変更が正しく反映されたか確認
                if current_value_after['value'] == '':
                    logger.info(f"{hospital_name}: 時間帯を「全日」に正常に設定しました")
                else:
                    logger.warning(
                        f"{hospital_name}: プルダウンの設定が期待値と異なります "
                        f"(期待: value='', 実際: value='{current_value_after['value']}')"
                    )
            else:
                logger.warning(f"{hospital_name}: プルダウンの値取得に失敗しました")
                
        except Exception as e:
            logger.warning(f"{hospital_name}: プルダウン再設定失敗（処理は継続）: {e}")
        
        logger.info(f"{hospital_name}: 復旧処理が完了しました")
        return True
        
    except Exception as e:
        logger.error(f"{hospital_name}: 復旧処理中に予期しないエラー: {e}")
        logger.debug(traceback.format_exc())
        return False

async def wait_for_page_ready(page, timeout=30):
    """
    ページの読み込み完了を待機（Playwright版）
    
    Args:
        page: Playwrightのpageインスタンス
        timeout: タイムアウト時間（秒）
    """
    try:
        await page.wait_for_load_state('domcontentloaded', timeout=timeout * 1000)
        await asyncio.sleep(1)  # 追加の安定化待機
        return True
    except PlaywrightTimeoutError:
        logger.warning(f"ページ読み込みが{timeout}秒以内に完了しませんでした")
        return False
    
async def monitor_hospital(page, hospital, config, shutdown_event):
    """医療機関の監視処理"""
    polling_interval = int(config.get('setting', 'movacli_polling_interval', fallback=10))
    
    logger.info(f"{hospital['hospital_name']}: 監視開始（間隔: {polling_interval}秒）")
    
    while not shutdown_event.is_set():
        try:
            # データ抽出
            oasis_data = await extract_oasis_data(page, hospital)
            
            # データベースに挿入（既存のmedical_data_inserterを呼び出す）
            if oasis_data:
                await process_and_insert_data(oasis_data, hospital)
            
            # 次の監視まで待機
            await asyncio.sleep(polling_interval)
            
        except Exception as e:
            logger.error(f"{hospital['hospital_name']}: 監視処理中にエラー: {e}")
            logger.debug(traceback.format_exc())
            await asyncio.sleep(polling_interval)

async def process_and_insert_data(records, hospital_info):
    """データをmedical_data_inserterに渡して処理する"""
    try:
        if not records:
            return

        json_data = {
            "hospital_name": hospital_info['hospital_name'],
            "system_type": hospital_info.get('system_type', 'モバクリ'),
            "team": hospital_info.get('team', ''),
            "issue_key": hospital_info['issue_key'],
            "patients": records
        }

        script_dir = os.path.dirname(os.path.abspath(__file__))
        inserter_path = os.path.join(script_dir, "medical_data_inserter.py")
        
        if not os.path.exists(inserter_path):
            logger.error(f"medical_data_inserter.py が見つかりません: {inserter_path}")
            return

        # subprocess でmedical_data_inserter.pyを実行
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
        process = subprocess.run(
            [sys.executable, inserter_path],
            input=json.dumps(json_data, ensure_ascii=False),
            text=True,
            capture_output=True,
            encoding='utf-8',
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

    except subprocess.CalledProcessError as e:
        logger.error(f"データベース挿入エラー: {e.stderr}")
    except Exception as e:
        logger.error(f"データ処理中にエラー: {e}")
        logger.debug(traceback.format_exc())

async def run(playwright, config, shutdown_event, login_status, hospitals):
    """モバクリ監視のメイン処理"""
    
    def sanitize_directory_name(name):
        """ディレクトリ名として使用できない文字を置換"""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, '_')
        return name
    
    contexts = []
    pages = []
    monitor_tasks = []  # 監視タスクを追跡
    
    try:
        # ログイン処理の開始を記録
        login_status.start_login_process(len(hospitals))
        
        # 各医療機関にログイン
        for index, hospital in enumerate(hospitals):
            if shutdown_event.is_set():
                break
            
            try:
                # セッションディレクトリを課題キーベースで作成
                system_type = sanitize_directory_name(hospital['system_type'])
                issue_key = sanitize_directory_name(hospital['issue_key'])
                user_data_dir = os.path.join(SESSION_DIR, f"{system_type}_{issue_key}")
                os.makedirs(user_data_dir, exist_ok=True)
                
                # 永続化コンテキスト作成
                context = await playwright.chromium.launch_persistent_context(
                    user_data_dir,
                    headless=False,
                    viewport={'width': 1200, 'height': 1000},
                    args=['--no-first-run', '--no-default-browser-check']
                )
                
                contexts.append(context)
                page = context.pages[0] if context.pages else await context.new_page()
                pages.append(page)
                
                # ログイン処理
                login_success = await login_with_retry(page, hospital)
                
                # ログイン状態を記録
                login_status.update_hospital_status(
                    hospital_name=hospital['hospital_name'],
                    success=login_success,
                    error_message=None if login_success else "ログイン失敗"
                )
                
                if not login_success:
                    logger.error(f"{hospital['hospital_name']}: ログイン失敗のためスキップ")
                    continue
                
                # 監視タスク開始して追跡
                task = asyncio.create_task(monitor_hospital(page, hospital, config, shutdown_event))
                monitor_tasks.append(task)
                
            except Exception as e:
                logger.error(f"{hospital['hospital_name']}: 初期化エラー: {e}")
                logger.debug(traceback.format_exc())
                login_status.update_hospital_status(
                    hospital_name=hospital['hospital_name'],
                    success=False,
                    error_message=str(e)
                )
        
        # シャットダウンイベントを待機
        logger.info("モバクリ監視システムが稼働中です")
        await shutdown_event.wait()
        
    except Exception as e:
        logger.error(f"モバクリ監視処理中にエラー: {e}")
        logger.debug(traceback.format_exc())
    finally:
        # クリーンアップ
        logger.info("モバクリ監視システムを終了します")
        
        # 監視タスクをキャンセル
        for task in monitor_tasks:
            if not task.done():
                task.cancel()
        
        # タスクの完了を待つ
        if monitor_tasks:
            await asyncio.gather(*monitor_tasks, return_exceptions=True)
        
        # コンテキストを閉じる
        for context in contexts:
            try:
                await context.close()
            except Exception as e:
                logger.debug(f"コンテキストクローズ時のエラー（無視）: {e}")

async def main_with_shutdown(shutdown_event, login_status):
    """シャットダウンイベント対応のメイン関数"""
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
            login_status.update_hospital_status("モバクリ", True)
            return

        async with async_playwright() as playwright:
            await run(playwright, config, shutdown_event, login_status, hospitals)

    except asyncio.CancelledError:
        logger.debug("メイン処理がキャンセルされました")
    except Exception as e:
        logger.error(f"予期せぬエラーが発生しました: {e}")
        logger.debug("スタックトレース:", exc_info=True)

if __name__ == '__main__':
    # テスト実行用
    shutdown_event = asyncio.Event()
    login_status = LoginStatus("モバクリ")
    
    try:
        asyncio.run(main_with_shutdown(shutdown_event, login_status))
    except KeyboardInterrupt:
        logger.info("キーボード割り込みを検出しました")
        shutdown_event.set()