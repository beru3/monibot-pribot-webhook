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
            logger.debug(f"{hospital['hospital_name']}: page.goto開始")
            await page.goto('https://c1.movacal.net/home', wait_until='domcontentloaded', timeout=60000)
            logger.debug(f"{hospital['hospital_name']}: page.goto完了")

            # 証明書選択スレッドの完了を待つ
            if cert_thread:
                logger.debug(f"{hospital['hospital_name']}: 証明書選択スレッド完了待ち開始")
                cert_thread.join()
                logger.debug(f"{hospital['hospital_name']}: 証明書選択スレッド完了")

            await asyncio.sleep(3)

            # ID入力
            logger.debug(f"{hospital['hospital_name']}: ID入力開始")
            await page.fill('input#login-id', hospital['login_id'])
            logger.debug(f"{hospital['hospital_name']}: ID入力完了")
            await asyncio.sleep(0.5)

            # パスワード入力
            logger.debug(f"{hospital['hospital_name']}: パスワード入力開始")
            await page.fill('input#login-password', hospital['password'])
            logger.debug(f"{hospital['hospital_name']}: パスワード入力完了")
            await asyncio.sleep(0.5)

            # ログインボタンクリック
            logger.debug(f"{hospital['hospital_name']}: ログインボタンクリック開始")
            await page.click('button[type="submit"].btn-secondary')
            logger.debug(f"{hospital['hospital_name']}: ログインボタンクリック完了")
            await asyncio.sleep(5)

            # ログイン確認
            current_url = page.url
            logger.debug(f"{hospital['hospital_name']}: ログイン後のURL: {current_url}")
            if 'home' in current_url:
                logger.info(f"{hospital['hospital_name']}: ログイン成功")
                
                # プルダウンを「全日」に変更
                try:
                    await asyncio.sleep(2)  # ページの読み込みを待つ
                    
                    # プルダウンの現在の値を取得（変更前）
                    current_value_before = await page.evaluate("""
                        () => {
                            const select = document.querySelector('select#outer-home-recept-list-period');
                            if (!select) return { error: 'select要素なし' };
                            if (select.selectedIndex < 0) return { error: 'selectedIndex無効' };
                            const selectedOption = select.options[select.selectedIndex];
                            if (!selectedOption) return { error: 'selectedOption無効' };
                            return {
                                value: selectedOption.value || '',
                                text: selectedOption.text || '',
                                selectedIndex: select.selectedIndex
                            };
                        }
                    """)
                    
                    if current_value_before and 'error' not in current_value_before:
                        logger.info(
                            f"{hospital['hospital_name']}: プルダウン変更前の値: "
                            f"value='{current_value_before['value']}', "
                            f"text='{current_value_before['text']}', "
                            f"index={current_value_before['selectedIndex']}"
                        )
                        
                        # 既に「全日」（value=''）が選択されている場合
                        if current_value_before['value'] == '':
                            logger.info(f"{hospital['hospital_name']}: 既に「全日」が選択されているため、変更をスキップします")
                            # 変更後の確認のみ実行
                            await asyncio.sleep(0.5)
                        else:
                            # プルダウンを「全日」に設定
                            logger.info(f"{hospital['hospital_name']}: プルダウンを「全日」に変更します")
                            try:
                                await page.select_option('select#outer-home-recept-list-period', value='')
                                await asyncio.sleep(1.5)  # 設定反映を待つ（長めに）
                            except Exception as select_error:
                                # select_optionでエラー時にスクリーンショット保存
                                import datetime
                                screenshot_dir = os.path.join(project_root, 'logs', 'screenshots')
                                os.makedirs(screenshot_dir, exist_ok=True)
                                screenshot_path = os.path.join(
                                    screenshot_dir,
                                    f"dropdown_select_error_{hospital['hospital_name'].replace(' ', '_')}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                                )
                                await page.screenshot(path=screenshot_path)
                                logger.error(
                                    f"{hospital['hospital_name']}: プルダウン選択でエラー、"
                                    f"スクリーンショット保存: {screenshot_path}\n"
                                    f"エラー内容: {select_error}"
                                )
                                raise
                    else:
                        logger.warning(f"{hospital['hospital_name']}: プルダウンの現在値を取得できませんでした: {current_value_before}")
                        
                        # 取得失敗時もスクリーンショット保存
                        import datetime
                        screenshot_dir = os.path.join(project_root, 'logs', 'screenshots')
                        os.makedirs(screenshot_dir, exist_ok=True)
                        screenshot_path = os.path.join(
                            screenshot_dir,
                            f"dropdown_before_error_{hospital['hospital_name'].replace(' ', '_')}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                        )
                        await page.screenshot(path=screenshot_path)
                        logger.warning(f"{hospital['hospital_name']}: スクリーンショット保存: {screenshot_path}")
                    
                    # プルダウンの変更後の値を取得（リトライ付き）
                    verify_success = False
                    for verify_attempt in range(3):
                        await asyncio.sleep(0.5)  # 少し待機
                        
                        current_value_after = await page.evaluate("""
                            () => {
                                const select = document.querySelector('select#outer-home-recept-list-period');
                                if (!select) return { error: 'select要素なし' };
                                if (select.selectedIndex < 0) return { error: 'selectedIndex無効', selectedIndex: select.selectedIndex };
                                const selectedOption = select.options[select.selectedIndex];
                                if (!selectedOption) return { error: 'selectedOption無効', selectedIndex: select.selectedIndex };
                                return {
                                    value: selectedOption.value || '',
                                    text: selectedOption.text || '',
                                    selectedIndex: select.selectedIndex
                                };
                            }
                        """)
                        
                        if current_value_after and 'error' not in current_value_after:
                            logger.info(
                                f"{hospital['hospital_name']}: プルダウン変更後の値: "
                                f"value='{current_value_after['value']}', "
                                f"text='{current_value_after['text']}', "
                                f"index={current_value_after['selectedIndex']}"
                            )
                            
                            # 変更が正しく反映されたか確認
                            if current_value_after['value'] == '':
                                logger.info(f"{hospital['hospital_name']}: 時間帯を「全日」に正常に設定しました")
                                verify_success = True
                                break
                            else:
                                logger.warning(
                                    f"{hospital['hospital_name']}: プルダウンの設定が期待値と異なります "
                                    f"(期待: value='', 実際: value='{current_value_after['value']}')"
                                )
                        else:
                            logger.warning(
                                f"{hospital['hospital_name']}: プルダウンの値取得失敗（試行 {verify_attempt + 1}/3）: "
                                f"{current_value_after}"
                            )
                            
                            if verify_attempt == 2:  # 最後の試行
                                logger.error(f"{hospital['hospital_name']}: プルダウンの値を3回試行しても取得できませんでした")
                                
                                # 3回失敗時にスクリーンショット保存
                                import datetime
                                screenshot_dir = os.path.join(project_root, 'logs', 'screenshots')
                                os.makedirs(screenshot_dir, exist_ok=True)
                                screenshot_path = os.path.join(
                                    screenshot_dir,
                                    f"dropdown_after_error_{hospital['hospital_name'].replace(' ', '_')}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                                )
                                await page.screenshot(path=screenshot_path)
                                logger.error(f"{hospital['hospital_name']}: スクリーンショット保存: {screenshot_path}")
                        
                except Exception as e:
                    logger.warning(f"{hospital['hospital_name']}: プルダウン選択エラー（処理は継続）: {e}")
                    
                    # 例外発生時もスクリーンショット保存
                    try:
                        import datetime
                        screenshot_dir = os.path.join(project_root, 'logs', 'screenshots')
                        os.makedirs(screenshot_dir, exist_ok=True)
                        screenshot_path = os.path.join(
                            screenshot_dir,
                            f"dropdown_exception_{hospital['hospital_name'].replace(' ', '_')}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                        )
                        await page.screenshot(path=screenshot_path)
                        logger.warning(f"{hospital['hospital_name']}: 例外発生時のスクリーンショット保存: {screenshot_path}")
                    except Exception as screenshot_error:
                        logger.debug(f"{hospital['hospital_name']}: スクリーンショット保存失敗: {screenshot_error}")
                
                return True
            else:
                logger.warning(f"{hospital['hospital_name']}: ログイン失敗（試行 {attempt + 1}）")
                
        except Exception as e:
            logger.error(f"{hospital['hospital_name']}: ログインエラー（試行 {attempt + 1}）: {e}")
            logger.debug(f"{hospital['hospital_name']}: スタックトレース:\n{traceback.format_exc()}")
            await asyncio.sleep(2)

    logger.error(f"{hospital['hospital_name']}: {max_retries}回の試行後もログイン失敗")
    return False

async def check_page_health(page, hospital_name):
    """
    ページが正常に表示されているか確認
    正常時に表示される要素の存在で判断

    Returns:
        dict: {'healthy': bool, 'reason': str} 健全性と異常理由
    """
    try:
        health_check = await asyncio.wait_for(
            page.evaluate("""
                () => {
                    // 正常時に必ず存在する要素をチェック
                    const select = document.querySelector('select#outer-home-recept-list-period');
                    const table = document.querySelector('table');

                    return {
                        hasSelect: !!select,
                        hasTable: !!table,
                        url: window.location.href,
                        title: document.title,
                        bodyTextLength: document.body.innerText.length,
                        readyState: document.readyState
                    };
                }
            """),
            timeout=5.0
        )

        # 必須要素が揃っているか確認
        if health_check['hasSelect'] and health_check['hasTable']:
            logger.debug(
                f"{hospital_name}: ページ正常(必須要素確認済み) - "
                f"readyState: {health_check.get('readyState', 'unknown')}"
            )
            return {'healthy': True, 'reason': ''}
        else:
            # 欠けている要素を特定
            missing_elements = []
            if not health_check['hasSelect']:
                missing_elements.append('プルダウン(select#outer-home-recept-list-period)')
            if not health_check['hasTable']:
                missing_elements.append('テーブル要素')

            reason = f"必須要素が見つかりません: {', '.join(missing_elements)}"
            logger.error(
                f"{hospital_name}: 🚨 ページクラッシュを検知 - {reason} | "
                f"URL: {health_check['url']}, readyState: {health_check.get('readyState', 'unknown')}"
            )
            return {'healthy': False, 'reason': reason}

    except asyncio.TimeoutError:
        reason = "ページ健全性チェックがタイムアウト(5秒超過)"
        logger.error(f"{hospital_name}: 🚨 ページクラッシュを検知 - {reason}")
        return {'healthy': False, 'reason': reason}
    except Exception as e:
        # page.evaluate自体が失敗した場合も異常と判断
        reason = f"JavaScript実行エラー: {str(e)}"
        logger.error(f"{hospital_name}: 🚨 ページクラッシュを検知 - {reason}")
        return {'healthy': False, 'reason': reason}
    
async def extract_oasis_data(page, hospital, max_retries=3):
    """OASIS会計データを抽出（自動復旧機能付き）"""

    for attempt in range(max_retries):
        try:
            logger.debug(f"{hospital['hospital_name']}: データ抽出開始（試行 {attempt + 1}/{max_retries}）")

            # page.evaluate()にタイムアウトを設定（10秒）
            # ページクラッシュ時の無限ハングを防ぐ
            data = await asyncio.wait_for(
                page.evaluate("""
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
                """),
                timeout=10.0
            )
            
            if data:
                logger.info(f"{hospital['hospital_name']}: {len(data)}件のOASIS会計データを抽出")
            
            # 成功したらリトライ情報をログ
            if attempt > 0:
                logger.info(f"{hospital['hospital_name']}: データ抽出成功（リトライ {attempt + 1}回目で成功）")
            
            return data
            
        except asyncio.TimeoutError:
            # page.evaluate()のタイムアウト（ページクラッシュの可能性が高い）
            logger.warning(
                f"{hospital['hospital_name']}: データ抽出がタイムアウトしました（10秒超過） "
                f"(試行 {attempt + 1}/{max_retries}) - ページクラッシュの可能性"
            )

            # タイムアウトはページクラッシュとして扱い、次のループでcheck_page_healthに任せる
            # 空配列を返して、次の監視サイクルで健全性チェックが実行されるようにする
            return []

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
                
                try:
                    recovery_success = await perform_recovery(page, hospital['hospital_name'], attempt)
                    
                    if not recovery_success:
                        logger.error(f"{hospital['hospital_name']}: 復旧処理が失敗しました")
                        
                        # 復旧失敗時は追加で強制リロードを試行
                        logger.warning(f"{hospital['hospital_name']}: 強制的に再読み込みを試行します")
                        try:
                            await asyncio.wait_for(
                                page.goto('https://c1.movacal.net/home', wait_until='domcontentloaded', timeout=15000),
                                timeout=20.0
                            )
                            await asyncio.sleep(2)

                            # 再度検証（タイムアウト付き）
                            revalidation = await asyncio.wait_for(
                                page.evaluate("""
                                    () => {
                                        const select = document.querySelector('select#outer-home-recept-list-period');
                                        return !!select;
                                    }
                                """),
                                timeout=5.0
                            )

                            if revalidation:
                                logger.info(f"{hospital['hospital_name']}: 強制リロードで復旧しました")
                            else:
                                logger.error(f"{hospital['hospital_name']}: 強制リロードも失敗しました")
                                return []
                        except (asyncio.TimeoutError, Exception) as force_reload_error:
                            logger.error(f"{hospital['hospital_name']}: 強制リロード中にエラー: {force_reload_error}")
                            return []
                    
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
    エラー検知時の復旧処理(Playwrightバージョン)
    
    Args:
        page: Playwrightのpageインスタンス
        hospital_name: 医療機関名
        attempt_number: 現在の試行回数
    
    Returns:
        bool: 復旧成功ならTrue、失敗ならFalse
    """
    
    logger.info(f"{hospital_name}: 復旧処理を開始します(リロード実行)")
    
    try:
        # 現在のURLを保持
        current_url = None
        try:
            current_url = page.url
            logger.info(f"{hospital_name}: 現在のURL: {current_url}")
        except Exception as e:
            logger.warning(f"{hospital_name}: URLの取得に失敗(コンテキスト完全破壊): {e}")
        
        # ステップ1: ページリロード
        try:
            await asyncio.wait_for(
                page.reload(wait_until='domcontentloaded', timeout=15000),
                timeout=20.0
            )
            logger.info(f"{hospital_name}: ページリロード実行")
            await asyncio.sleep(2)  # リロード後の安定化待機
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"{hospital_name}: reload()失敗: {e}、代替方法を試行")

            # reload()が失敗した場合の代替策
            if current_url:
                try:
                    await asyncio.wait_for(
                        page.goto(current_url, wait_until='domcontentloaded', timeout=15000),
                        timeout=20.0
                    )
                    logger.info(f"{hospital_name}: goto()でURLを再読み込み")
                    await asyncio.sleep(2)
                except (asyncio.TimeoutError, Exception) as e2:
                    logger.error(f"{hospital_name}: goto()も失敗: {e2}")
                    return False
            else:
                logger.error(f"{hospital_name}: リロード不可(URL不明)")
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
            ready_state = await asyncio.wait_for(
                page.evaluate("document.readyState"),
                timeout=5.0
            )
            logger.info(f"{hospital_name}: ページ状態: {ready_state}")

            if ready_state != "complete":
                logger.warning(f"{hospital_name}: ページが完全に読み込まれていません")
                await asyncio.sleep(3)  # 追加待機
        except (asyncio.TimeoutError, Exception) as e:
            logger.error(f"{hospital_name}: コンテキスト確認失敗: {e}")
            return False
        
        # ステップ4: ページの健全性チェック(正常な要素の存在確認)
        health_result = await check_page_health(page, hospital_name)
        if not health_result['healthy']:
            logger.error(f"{hospital_name}: リロード後もページが正常ではありません - 理由: {health_result['reason']}")
            return False
        
        logger.info(f"{hospital_name}: ページ検証成功 - 正常なページです")
        
        # ステップ5: プルダウンを「全日」に再設定
        try:
            # プルダウンの現在の値を取得(変更前)
            current_value_before = await asyncio.wait_for(
                page.evaluate("""
                    () => {
                        const select = document.querySelector('select#outer-home-recept-list-period');
                        if (!select) return null;
                        if (select.selectedIndex < 0) return null;
                        const selectedOption = select.options[select.selectedIndex];
                        if (!selectedOption) return null;
                        return {
                            value: selectedOption.value || '',
                            text: selectedOption.text || ''
                        };
                    }
                """),
                timeout=5.0
            )
            
            if current_value_before:
                logger.info(
                    f"{hospital_name}: プルダウン変更前の値: "
                    f"value='{current_value_before['value']}', "
                    f"text='{current_value_before['text']}'"
                )
            else:
                logger.warning(f"{hospital_name}: プルダウンの現在値を取得できませんでした")
            
            # プルダウンを「全日」に設定
            await asyncio.wait_for(
                page.select_option('select#outer-home-recept-list-period', value=''),
                timeout=5.0
            )
            await asyncio.sleep(1)  # 設定反映を待つ

            # プルダウンの変更後の値を取得
            current_value_after = await asyncio.wait_for(
                page.evaluate("""
                    () => {
                        const select = document.querySelector('select#outer-home-recept-list-period');
                        if (!select) return null;
                        if (select.selectedIndex < 0) return null;
                        const selectedOption = select.options[select.selectedIndex];
                        if (!selectedOption) return null;
                        return {
                            value: selectedOption.value || '',
                            text: selectedOption.text || ''
                        };
                    }
                """),
                timeout=5.0
            )
            
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
            logger.warning(f"{hospital_name}: プルダウン再設定失敗(処理は継続): {e}")
        
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
    
async def log_memory_usage(page, hospital_name, context_label=""):
    """
    ページのメモリ使用量をログに出力
    """
    label_text = f"[{context_label}] " if context_label else ""

    try:
        memory_info = await asyncio.wait_for(
            page.evaluate("""
                () => {
                    const info = {
                        // JavaScriptヒープメモリ
                        jsHeapSizeLimit: 0,
                        totalJSHeapSize: 0,
                        usedJSHeapSize: 0,

                        // DOM要素数
                        domNodes: document.querySelectorAll('*').length,

                        // 患者レコード数
                        patientRows: document.querySelectorAll('tr[id^="outer-home-recept-list-item-"]').length,

                        // プルダウンの選択値（追加）
                        dropdownValue: '',
                        dropdownText: '',

                        // パフォーマンス情報
                        timestamp: Date.now()
                    };

                    // performance.memory APIが利用可能な場合
                    if (performance.memory) {
                        info.jsHeapSizeLimit = performance.memory.jsHeapSizeLimit;
                        info.totalJSHeapSize = performance.memory.totalJSHeapSize;
                        info.usedJSHeapSize = performance.memory.usedJSHeapSize;
                    }

                    // プルダウンの値を取得
                    const select = document.querySelector('select#outer-home-recept-list-period');
                    if (select && select.selectedIndex >= 0) {
                        const selectedOption = select.options[select.selectedIndex];
                        if (selectedOption) {
                            info.dropdownValue = selectedOption.value || '';
                            info.dropdownText = selectedOption.text || '';
                        }
                    }

                    return info;
                }
            """),
            timeout=5.0
        )

        # メモリ使用量をMB単位に変換
        heap_limit_mb = memory_info['jsHeapSizeLimit'] / (1024 * 1024) if memory_info['jsHeapSizeLimit'] > 0 else 0
        total_heap_mb = memory_info['totalJSHeapSize'] / (1024 * 1024) if memory_info['totalJSHeapSize'] > 0 else 0
        used_heap_mb = memory_info['usedJSHeapSize'] / (1024 * 1024) if memory_info['usedJSHeapSize'] > 0 else 0

        # 使用率を計算
        heap_usage_percent = (used_heap_mb / heap_limit_mb * 100) if heap_limit_mb > 0 else 0

        if memory_info['jsHeapSizeLimit'] > 0:
            logger.info(
                f"{hospital_name}: {label_text}メモリ使用状況:\n"
                f"  - JSヒープ使用量: {used_heap_mb:.2f} MB / {heap_limit_mb:.2f} MB ({heap_usage_percent:.1f}%)\n"
                f"  - JSヒープ合計: {total_heap_mb:.2f} MB\n"
                f"  - DOM要素数: {memory_info['domNodes']:,}\n"
                f"  - 患者レコード数: {memory_info['patientRows']}\n"
                f"  - プルダウン: value='{memory_info['dropdownValue']}', text='{memory_info['dropdownText']}'"
            )
        else:
            logger.info(
                f"{hospital_name}: {label_text}メモリ情報:\n"
                f"  - performance.memory API利用不可（Chromium起動オプション要確認）\n"
                f"  - DOM要素数: {memory_info['domNodes']:,}\n"
                f"  - 患者レコード数: {memory_info['patientRows']}\n"
                f"  - プルダウン: value='{memory_info['dropdownValue']}', text='{memory_info['dropdownText']}'"
            )

        return memory_info

    except asyncio.TimeoutError:
        logger.warning(f"{hospital_name}: {label_text}メモリ使用量の取得がタイムアウト")
        return None
    except Exception as e:
        logger.warning(f"{hospital_name}: {label_text}メモリ使用量の取得に失敗: {e}")
        return None
    
async def monitor_hospital(page, hospital, config, shutdown_event):
    """医療機関の監視処理"""
    polling_interval = int(config.get('setting', 'movacli_polling_interval', fallback=10))
    consecutive_errors = 0
    max_consecutive_errors = 3
    
    logger.info(f"{hospital['hospital_name']}: 監視開始（間隔: {polling_interval}秒）")
    
    # 初回のメモリ使用量を記録
    await log_memory_usage(page, hospital['hospital_name'], "監視開始時")
    
    monitoring_count = 0  # 監視回数をカウント
    
    while not shutdown_event.is_set():
        try:
            monitoring_count += 1
            
            # 10回に1回、詳細なメモリログを出力（監視のみ、リロードなし）
            if monitoring_count % 10 == 1:
                await log_memory_usage(page, hospital['hospital_name'], f"監視{monitoring_count}回目")

            # ステップ0: プルダウンを「全日」に強制設定（毎回）
            await ensure_dropdown_all_day(page, hospital['hospital_name'])
            
            # ステップ1: ページの健全性チェック
            health_result = await check_page_health(page, hospital['hospital_name'])

            if not health_result['healthy']:
                consecutive_errors += 1
                logger.warning(
                    f"{hospital['hospital_name']}: ページ異常を検出 "
                    f"(連続{consecutive_errors}回目/{max_consecutive_errors}回) - 理由: {health_result['reason']}"
                )

                # 異常時のメモリ状態を記録（エラーが出ても復旧処理は継続）
                try:
                    await log_memory_usage(page, hospital['hospital_name'], "異常検出時")
                except Exception as mem_error:
                    logger.warning(f"{hospital['hospital_name']}: メモリログ取得でエラー（処理継続）: {mem_error}")

                # スクリーンショット保存（エラーが出ても復旧処理は継続）
                try:
                    import datetime
                    screenshot_dir = os.path.join(project_root, 'logs', 'screenshots')
                    os.makedirs(screenshot_dir, exist_ok=True)
                    screenshot_path = os.path.join(
                        screenshot_dir,
                        f"page_crash_{hospital['hospital_name'].replace(' ', '_')}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                    )
                    await page.screenshot(path=screenshot_path)
                    logger.info(f"{hospital['hospital_name']}: 異常画面のスクリーンショット保存: {screenshot_path}")
                except Exception as screenshot_error:
                    logger.warning(f"{hospital['hospital_name']}: スクリーンショット保存失敗: {screenshot_error}")

                # 自動復旧を試行（ここは確実に実行される）
                if consecutive_errors <= max_consecutive_errors:
                    logger.info(f"{hospital['hospital_name']}: ページリロードを実行します")
                    recovery_success = await perform_page_reload(page, hospital['hospital_name'])

                    if recovery_success:
                        logger.info(f"{hospital['hospital_name']}: ページリロード成功")
                        consecutive_errors = 0

                        # リロード後のメモリ状態を記録（エラーが出ても処理継続）
                        try:
                            await log_memory_usage(page, hospital['hospital_name'], "リロード後")
                        except Exception as mem_error:
                            logger.warning(f"{hospital['hospital_name']}: リロード後のメモリログ取得でエラー（処理継続）: {mem_error}")

                        # リロード後、プルダウンを「全日」に再設定
                        await asyncio.sleep(2)
                        try:
                            # プルダウンの現在の値を取得（変更前）
                            current_value_before = await page.evaluate("""
                                () => {
                                    const select = document.querySelector('select#outer-home-recept-list-period');
                                    if (!select) return { error: 'select要素なし' };
                                    if (select.selectedIndex < 0) return { error: 'selectedIndex無効' };
                                    const selectedOption = select.options[select.selectedIndex];
                                    if (!selectedOption) return { error: 'selectedOption無効' };
                                    return {
                                        value: selectedOption.value || '',
                                        text: selectedOption.text || '',
                                        selectedIndex: select.selectedIndex
                                    };
                                }
                            """)

                            if current_value_before and 'error' not in current_value_before:
                                logger.info(
                                    f"{hospital['hospital_name']}: プルダウン変更前の値: "
                                    f"value='{current_value_before['value']}', "
                                    f"text='{current_value_before['text']}', "
                                    f"index={current_value_before['selectedIndex']}"
                                )

                                # 既に「全日」（value=''）が選択されている場合
                                if current_value_before['value'] == '':
                                    logger.info(f"{hospital['hospital_name']}: 既に「全日」が選択されているため、変更をスキップします")
                                    # 変更後の確認のみ実行
                                    await asyncio.sleep(0.5)
                                else:
                                    # プルダウンを「全日」に設定
                                    logger.info(f"{hospital['hospital_name']}: プルダウンを「全日」に変更します")
                                    try:
                                        # JavaScript経由で直接変更し、changeイベントをトリガー
                                        change_result = await page.evaluate("""
                                            () => {
                                                const select = document.querySelector('select#outer-home-recept-list-period');
                                                if (!select) return { success: false, error: 'select要素なし' };

                                                // value=''のoptionのindexを探す
                                                let targetIndex = -1;
                                                for (let i = 0; i < select.options.length; i++) {
                                                    if (select.options[i].value === '') {
                                                        targetIndex = i;
                                                        break;
                                                    }
                                                }

                                                if (targetIndex < 0) return { success: false, error: 'value空のoption未発見', optionsCount: select.options.length };

                                                // selectedIndexを直接設定
                                                select.selectedIndex = targetIndex;

                                                // changeイベントを発火
                                                const event = new Event('change', { bubbles: true });
                                                select.dispatchEvent(event);

                                                return { success: true, selectedIndex: select.selectedIndex, optionsCount: select.options.length };
                                            }
                                        """)

                                        if change_result.get('success'):
                                            logger.info(f"{hospital['hospital_name']}: プルダウン変更実行完了 (selectedIndex={change_result.get('selectedIndex')})")
                                        else:
                                            logger.warning(f"{hospital['hospital_name']}: プルダウン変更に失敗: {change_result}")

                                        await asyncio.sleep(2.5)  # 設定反映を待つ（より長めに）
                                    except Exception as select_error:
                                        # select_optionでエラー時にスクリーンショット保存
                                        import datetime
                                        screenshot_dir = os.path.join(project_root, 'logs', 'screenshots')
                                        os.makedirs(screenshot_dir, exist_ok=True)
                                        screenshot_path = os.path.join(
                                            screenshot_dir,
                                            f"dropdown_select_error_reload_{hospital['hospital_name'].replace(' ', '_')}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                                        )
                                        await page.screenshot(path=screenshot_path)
                                        logger.error(
                                            f"{hospital['hospital_name']}: プルダウン選択でエラー、"
                                            f"スクリーンショット保存: {screenshot_path}\n"
                                            f"エラー内容: {select_error}"
                                        )
                                        raise
                            else:
                                logger.warning(f"{hospital['hospital_name']}: プルダウンの現在値を取得できませんでした: {current_value_before}")

                                # 取得失敗時もスクリーンショット保存
                                import datetime
                                screenshot_dir = os.path.join(project_root, 'logs', 'screenshots')
                                os.makedirs(screenshot_dir, exist_ok=True)
                                screenshot_path = os.path.join(
                                    screenshot_dir,
                                    f"dropdown_before_error_reload_{hospital['hospital_name'].replace(' ', '_')}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                                )
                                await page.screenshot(path=screenshot_path)
                                logger.warning(f"{hospital['hospital_name']}: スクリーンショット保存: {screenshot_path}")

                            # プルダウンの変更後の値を取得（リトライ付き）
                            verify_success = False
                            for verify_attempt in range(3):
                                await asyncio.sleep(1.0)  # 待機時間を延長

                                current_value_after = await page.evaluate("""
                                    () => {
                                        const select = document.querySelector('select#outer-home-recept-list-period');
                                        if (!select) return { error: 'select要素なし' };
                                        if (!select.options || select.options.length === 0) return { error: 'options未読み込み', optionsLength: 0 };
                                        if (select.selectedIndex < 0) return { error: 'selectedIndex無効', selectedIndex: select.selectedIndex, optionsLength: select.options.length };
                                        const selectedOption = select.options[select.selectedIndex];
                                        if (!selectedOption) return { error: 'selectedOption無効', selectedIndex: select.selectedIndex };
                                        return {
                                            value: selectedOption.value || '',
                                            text: selectedOption.text || '',
                                            selectedIndex: select.selectedIndex,
                                            optionsLength: select.options.length
                                        };
                                    }
                                """)

                                if current_value_after and 'error' not in current_value_after:
                                    logger.info(
                                        f"{hospital['hospital_name']}: プルダウン変更後の値: "
                                        f"value='{current_value_after['value']}', "
                                        f"text='{current_value_after['text']}', "
                                        f"index={current_value_after['selectedIndex']}"
                                    )

                                    # 変更が正しく反映されたか確認
                                    if current_value_after['value'] == '':
                                        logger.info(f"{hospital['hospital_name']}: 時間帯を「全日」に正常に設定しました")
                                        verify_success = True
                                        break
                                    else:
                                        logger.warning(
                                            f"{hospital['hospital_name']}: プルダウンの設定が期待値と異なります "
                                            f"(期待: value='', 実際: value='{current_value_after['value']}')"
                                        )
                                else:
                                    logger.warning(
                                        f"{hospital['hospital_name']}: プルダウンの値取得失敗（試行 {verify_attempt + 1}/3）: "
                                        f"{current_value_after}"
                                    )

                                    if verify_attempt == 2:  # 最後の試行
                                        logger.error(f"{hospital['hospital_name']}: プルダウンの値を3回試行しても取得できませんでした")

                                        # 3回失敗時にスクリーンショット保存
                                        import datetime
                                        screenshot_dir = os.path.join(project_root, 'logs', 'screenshots')
                                        os.makedirs(screenshot_dir, exist_ok=True)
                                        screenshot_path = os.path.join(
                                            screenshot_dir,
                                            f"dropdown_after_error_reload_{hospital['hospital_name'].replace(' ', '_')}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                                        )
                                        await page.screenshot(path=screenshot_path)
                                        logger.error(f"{hospital['hospital_name']}: スクリーンショット保存: {screenshot_path}")

                        except Exception as dropdown_error:
                            logger.warning(f"{hospital['hospital_name']}: プルダウン選択エラー（処理は継続）: {dropdown_error}")

                            # 例外発生時もスクリーンショット保存
                            try:
                                import datetime
                                screenshot_dir = os.path.join(project_root, 'logs', 'screenshots')
                                os.makedirs(screenshot_dir, exist_ok=True)
                                screenshot_path = os.path.join(
                                    screenshot_dir,
                                    f"dropdown_exception_reload_{hospital['hospital_name'].replace(' ', '_')}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                                )
                                await page.screenshot(path=screenshot_path)
                                logger.warning(f"{hospital['hospital_name']}: 例外発生時のスクリーンショット保存: {screenshot_path}")
                            except Exception as screenshot_error:
                                logger.debug(f"{hospital['hospital_name']}: スクリーンショット保存失敗: {screenshot_error}")

                        # リロード成功後は即座にデータ抽出を再開（待機せずcontinue）
                        logger.info(f"{hospital['hospital_name']}: リロード完了、即座に監視を再開します")
                        continue
                    else:
                        logger.error(f"{hospital['hospital_name']}: ページリロード失敗")
                        # リロード失敗時のみ待機
                        await asyncio.sleep(polling_interval)
                        continue
                else:
                    logger.error(
                        f"{hospital['hospital_name']}: "
                        f"連続{max_consecutive_errors}回のエラーが発生。自動復旧を停止します。"
                    )
                    # 最大エラー回数到達時のみ待機
                    await asyncio.sleep(polling_interval)
                    continue
            
            # ステップ2: ページが正常な場合のみデータ抽出
            consecutive_errors = 0
            
            # データ抽出前のメモリ使用量を記録（詳細ログモード時のみ）
            if monitoring_count % 10 == 1:
                await log_memory_usage(page, hospital['hospital_name'], "データ抽出前")
            
            oasis_data = await extract_oasis_data(page, hospital)
            
            # データ抽出後のメモリ使用量を記録（詳細ログモード時のみ）
            if monitoring_count % 10 == 1:
                await log_memory_usage(page, hospital['hospital_name'], "データ抽出後")
            
            # ステップ3: データベースに挿入（timeout=30付き）
            if oasis_data:
                await process_and_insert_data(oasis_data, hospital)
            
            # 次の監視まで待機
            await asyncio.sleep(polling_interval)
            
        except Exception as e:
            consecutive_errors += 1
            logger.error(
                f"{hospital['hospital_name']}: 監視処理中にエラー (連続{consecutive_errors}回目): {e}"
            )
            logger.debug(traceback.format_exc())

            # エラー時のメモリ状態を記録（エラーが出ても処理継続）
            try:
                await log_memory_usage(page, hospital['hospital_name'], "エラー発生時")
            except Exception as mem_error:
                logger.warning(f"{hospital['hospital_name']}: エラー時のメモリログ取得でエラー（処理継続）: {mem_error}")

            await asyncio.sleep(polling_interval)

async def ensure_dropdown_all_day(page, hospital_name):
    """
    プルダウンを「全日」に強制設定する関数
    監視ループの毎回実行される
    """
    try:
        # 現在の値を確認
        current_value = await asyncio.wait_for(
            page.evaluate("""
                () => {
                    const select = document.querySelector('select#outer-home-recept-list-period');
                    if (!select || select.selectedIndex < 0) return null;
                    const selectedOption = select.options[select.selectedIndex];
                    return selectedOption ? (selectedOption.value || '') : null;
                }
            """),
            timeout=3.0
        )
        
        # select要素が見つからない場合
        if current_value is None:
            logger.warning(f"{hospital_name}: プルダウン要素が見つかりません")
            return False

        # すでに「全日」(value='')なら何もしない
        if current_value == '':
            return True
        
        # 「全日」でない場合は設定を変更
        logger.info(f"{hospital_name}: プルダウンが「全日」ではないため再設定します (現在値: '{current_value}')")
        
        await page.select_option('select#outer-home-recept-list-period', value='')
        await asyncio.sleep(1)
        
        # 変更を確認
        verify_value = await page.evaluate("""
            () => {
                const select = document.querySelector('select#outer-home-recept-list-period');
                if (!select || select.selectedIndex < 0) return null;
                const selectedOption = select.options[select.selectedIndex];
                return selectedOption ? (selectedOption.value || '') : null;
            }
        """)
        
        if verify_value == '':
            logger.info(f"{hospital_name}: プルダウンを「全日」に再設定しました")
            return True
        else:
            logger.warning(f"{hospital_name}: プルダウンの再設定に失敗 (設定後: '{verify_value}')")
            return False
            
    except Exception as e:
        logger.warning(f"{hospital_name}: プルダウン確認中にエラー（処理継続）: {e}")
        return False

async def perform_page_reload(page, hospital_name):
    """
    ページリロードを実行（クラッシュからの復旧用）
    
    Args:
        page: Playwrightのpageインスタンス
        hospital_name: 医療機関名
    
    Returns:
        bool: リロード成功ならTrue、失敗ならFalse
    """
    
    logger.info(f"{hospital_name}: ページリロードを開始します")
    
    try:
        # 現在のURLを保持
        current_url = None
        try:
            current_url = page.url
            logger.debug(f"{hospital_name}: 現在のURL: {current_url}")
        except Exception as e:
            logger.warning(f"{hospital_name}: URLの取得に失敗: {e}")
        
        # リロード実行
        try:
            await asyncio.wait_for(
                page.reload(wait_until='domcontentloaded', timeout=15000),
                timeout=20.0
            )
            logger.info(f"{hospital_name}: reload()実行完了")
            await asyncio.sleep(3)  # リロード後の安定化待機
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"{hospital_name}: reload()失敗: {e}、代替方法を試行")

            # reload()が失敗した場合、goto()で再読み込み
            if current_url and 'movacal.net' in current_url:
                try:
                    await asyncio.wait_for(
                        page.goto(current_url, wait_until='domcontentloaded', timeout=15000),
                        timeout=20.0
                    )
                    logger.info(f"{hospital_name}: goto()で再読み込み完了")
                    await asyncio.sleep(3)
                except (asyncio.TimeoutError, Exception) as e2:
                    logger.error(f"{hospital_name}: goto()も失敗: {e2}")
                    return False
            else:
                # URLが不明または不正な場合は、ホームページへ
                try:
                    await asyncio.wait_for(
                        page.goto('https://c1.movacal.net/home', wait_until='domcontentloaded', timeout=15000),
                        timeout=20.0
                    )
                    logger.info(f"{hospital_name}: ホームページへ移動完了")
                    await asyncio.sleep(3)
                except (asyncio.TimeoutError, Exception) as e3:
                    logger.error(f"{hospital_name}: ホームページへの移動も失敗: {e3}")
                    return False
        
        # リロード後の健全性確認
        await asyncio.sleep(2)
        health_result = await check_page_health(page, hospital_name)

        if health_result['healthy']:
            logger.info(f"{hospital_name}: リロード後のページ正常確認完了")
            return True
        else:
            logger.error(f"{hospital_name}: リロード後もページが正常ではありません - 理由: {health_result['reason']}")
            return False
        
    except Exception as e:
        logger.error(f"{hospital_name}: ページリロード処理中に予期しないエラー: {e}")
        logger.debug(traceback.format_exc())
        return False

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

        # subprocess 実行
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
            timeout=30,  # ← 30秒のタイムアウトを追加
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

    except subprocess.TimeoutExpired as e:
        logger.error(
            f"データベース挿入がタイムアウトしました（30秒超過）\n"
            f"病院: {hospital_info.get('hospital_name', '不明')}\n"
            f"患者数: {len(records)}件"
        )
        logger.debug(f"タイムアウト詳細:\n{traceback.format_exc()}")
        # タイムアウトでもタスクは継続
        
    except subprocess.CalledProcessError as e:
        logger.error(
            f"データベース挿入エラー\n"
            f"病院: {hospital_info.get('hospital_name', '不明')}\n"
            f"患者数: {len(records)}件\n"
            f"エラー内容: {e.stderr}"
        )
        logger.debug(f"エラー詳細:\n{traceback.format_exc()}")
        # エラーでもタスクは継続
        
    except Exception as e:
        logger.error(
            f"データ処理中に予期しないエラー\n"
            f"病院: {hospital_info.get('hospital_name', '不明')}\n"
            f"患者数: {len(records)}件\n"
            f"エラー: {e}"
        )
        logger.debug(f"エラー詳細:\n{traceback.format_exc()}")
        # エラーでもタスクは継続

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
    monitor_tasks = []
    
    try:
        login_status.start_login_process(len(hospitals))
        
        for index, hospital in enumerate(hospitals):
            if shutdown_event.is_set():
                break
            
            try:
                system_type = sanitize_directory_name(hospital['system_type'])
                issue_key = sanitize_directory_name(hospital['issue_key'])
                user_data_dir = os.path.join(SESSION_DIR, f"{system_type}_{issue_key}")
                os.makedirs(user_data_dir, exist_ok=True)
                
                # 永続化コンテキスト作成
                context = await playwright.chromium.launch_persistent_context(
                    user_data_dir,
                    headless=False,
                    viewport={'width': 1200, 'height': 1000},
                    args=[
                        '--no-first-run',
                        '--no-default-browser-check',
                        '--enable-precise-memory-info',  # メモリ情報API有効化
                        '--js-flags=--expose-gc'         # ガベージコレクション有効化（オプション）
                    ]
                )
                
                contexts.append(context)
                page = context.pages[0] if context.pages else await context.new_page()
                pages.append(page)
                
                # ログイン処理
                login_success = await login_with_retry(page, hospital)
                
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
        
        logger.info("モバクリ監視システムが稼働中です")
        await shutdown_event.wait()
        
    except Exception as e:
        logger.error(f"モバクリ監視処理中にエラー: {e}")
        logger.debug(traceback.format_exc())
    finally:
        # クリーンアップ
        logger.info("モバクリ監視システムを終了します")
        
        for task in monitor_tasks:
            if not task.done():
                task.cancel()
        
        if monitor_tasks:
            await asyncio.gather(*monitor_tasks, return_exceptions=True)
        
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