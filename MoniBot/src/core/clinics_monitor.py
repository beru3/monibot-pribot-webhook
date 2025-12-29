# src/core/clinics_monitor.py - シンプル堅牢化版
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
import logging
from typing import List
import subprocess
import json
import requests
from typing import List, Dict, Any
import traceback

# ロガーの初期化
logger = LoggerFactory.setup_logger('clinics_monitor')

# パス定義
LOG_DIR = os.path.join(project_root, 'log')
DEBUG_DIR = os.path.join(LOG_DIR, 'debug')
CONFIG_DIR = os.path.join(project_root, 'config')
SESSION_DIR = os.path.join(project_root, 'session')

async def click_top_return_button_robust(page, hospital_name):
    """堅牢な「トップへ戻る」ボタンクリック"""
    try:
        # 方法1: テキスト内容ベース（最推奨）
        try:
            await page.get_by_role('link', name='トップへ戻る').click(timeout=3000)
            logger.info(f"{hospital_name}: 『トップへ戻る』ボタンをクリックしました（ロールベース）")
            return True
        except:
            logger.debug(f"{hospital_name}: ロールベース失敗、XPathを試行")

        # 方法2: XPathでテキスト検索
        try:
            await page.click('//a[contains(text(), "トップへ戻る") or contains(text(), "トップ")]', timeout=3000)
            logger.info(f"{hospital_name}: 『トップへ戻る』ボタンをクリックしました（XPath）")
            return True
        except:
            logger.debug(f"{hospital_name}: XPath失敗、フォールバックを試行")

        # 方法3: フォールバック（従来のクラス）
        try:
            await page.click("a.button.button-white.button-large", timeout=3000)
            logger.info(f"{hospital_name}: 『トップへ戻る』ボタンをクリックしました（フォールバック）")
            return True
        except:
            logger.debug(f"{hospital_name}: すべての『トップへ戻る』ボタン検出方法が失敗")
            return False

    except Exception as e:
        logger.debug(f"{hospital_name}: 『トップへ戻る』ボタンクリック中にエラー: {e}")
        return False

async def click_back_to_login_robust(page, hospital_name):
    """堅牢な「ログインへ戻る」ボタンクリック"""
    try:
        # 方法1: テキスト内容ベース
        try:
            await page.get_by_role('link', name=lambda text: 'ログイン' in text).click(timeout=5000)
            logger.info(f"{hospital_name}: ログインへ戻るボタンをクリックしました（ロールベース）")
            return True
        except:
            logger.debug(f"{hospital_name}: ロールベース失敗、XPathを試行")

        # 方法2: XPathでテキスト検索
        try:
            await page.click('//a[contains(text(), "ログイン")]', timeout=5000)
            logger.info(f"{hospital_name}: ログインへ戻るボタンをクリックしました（XPath）")
            return True
        except:
            logger.debug(f"{hospital_name}: XPath失敗、フォールバックを試行")

        # 方法3: フォールバック（従来の構造）
        try:
            await page.click('div > div.txt-center > a', timeout=5000)
            logger.info(f"{hospital_name}: ログインへ戻るボタンをクリックしました（フォールバック）")
            return True
        except:
            logger.debug(f"{hospital_name}: すべてのログインへ戻るボタン検出方法が失敗")
            return False

    except Exception as e:
        logger.debug(f"{hospital_name}: ログインへ戻るボタンクリック中にエラー: {e}")
        return False

async def click_today_button_robust(page, hospital_name):
    """堅牢な「今日」ボタンクリック"""
    try:
        # 方法1: Playwrightの現代的なロールベースセレクタ（推奨）
        try:
            await page.get_by_role('button', name='今日').click(timeout=5000)
            logger.info(f"{hospital_name}: 「今日」ボタンをクリックしました（ロールベース）")
            return True
        except:
            logger.debug(f"{hospital_name}: ロールベースセレクタ失敗、XPathを試行")

        # 方法2: XPathによるテキスト内容検索
        try:
            await page.click('//button[contains(text(), "今日")]', timeout=5000)
            logger.info(f"{hospital_name}: 「今日」ボタンをクリックしました（XPath）")
            return True
        except:
            logger.warning(f"{hospital_name}: XPathセレクタも失敗、従来の方法を試行")

        # 方法3: フォールバック（従来のクラス名）
        try:
            await page.click('button.css-2rgteu', timeout=5000)
            logger.info(f"{hospital_name}: 「今日」ボタンをクリックしました（フォールバック）")
            return True
        except:
            logger.error(f"{hospital_name}: すべての「今日」ボタン検出方法が失敗")
            return False

    except Exception as e:
        logger.error(f"{hospital_name}: 「今日」ボタンクリック中にエラー: {e}")
        return False

async def click_login_button_robust(page, hospital_name):
    """堅牢なログインボタンクリック"""
    try:
        # 方法1: ロールベースセレクタ
        try:
            await page.get_by_role('button', name='ログイン').click(timeout=5000)
            logger.info(f"{hospital_name}: ログインボタンをクリックしました（ロールベース）")
            return True
        except:
            logger.debug(f"{hospital_name}: ロールベースログインボタン失敗、XPathを試行")

        # 方法2: XPathによるテキスト内容検索
        try:
            await page.click('//button[contains(text(), "ログイン")]', timeout=5000)
            logger.info(f"{hospital_name}: ログインボタンをクリックしました（XPath）")
            return True
        except:
            logger.debug(f"{hospital_name}: XPathログインボタン失敗、フォームボタンを試行")

        # 方法3: フォーム内のsubmitボタン
        try:
            await page.click('form button[type="submit"]', timeout=5000)
            logger.info(f"{hospital_name}: ログインボタンをクリックしました（フォームsubmit）")
            return True
        except:
            logger.debug(f"{hospital_name}: フォームsubmitボタン失敗、従来の方法を試行")

        # 方法4: フォールバック（従来のセレクタ）
        try:
            await page.click('form > div > button', timeout=5000)
            logger.info(f"{hospital_name}: ログインボタンをクリックしました（フォールバック）")
            return True
        except:
            logger.error(f"{hospital_name}: すべてのログインボタン検出方法が失敗")
            return False

    except Exception as e:
        logger.error(f"{hospital_name}: ログインボタンクリック中にエラー: {e}")
        return False

def select_certificate(cert_order: int):
    """証明書選択ダイアログを処理"""
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
    """設定ファイルの読み込み"""
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
            
        return config
        
    except Exception as e:
        logger.error(f"設定ファイルの読み込み中にエラー: {e}")
        return None

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
                # システム種別が "クリニクス" であることを確認
                if not issue.get('issueType') or issue['issueType'].get('name') != 'クリニクス':
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
                        "system_type": 'クリニクス'
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
        logger.info("グループごとのクリニクス医療機関数:")
        for team, count in team_counts.items():
            if team:  # グループ未設定は表示しない
                logger.info(f"- {team}: {count}件")

        logger.info(f"取得した全課題数: {len(issues)}")
        logger.info(f"クリニクス・ポーリング有効な医療機関数: {filtered_count}")
        
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
    try:
        # 証明書選択スレッドの準備
        cert_thread = threading.Thread(
            target=select_certificate,
            args=(hospital_info['cert_order'],)
        )
        cert_thread.start()

        logger.info(f"{hospital_info['hospital_name']}: ページにアクセスしています...")
        await page.goto("https://karte.medley.life/d", timeout=60000)
        
        # 証明書選択の完了を待つ
        cert_thread.join()
        await page.wait_for_load_state("networkidle", timeout=30000)
        logger.info(f"{hospital_info['hospital_name']}: 証明書選択完了しました")

        # 証明書選択完了後に、「トップへ戻る」ボタンをクリックする処理（存在する場合）
        success = await click_top_return_button_robust(page, hospital_info['hospital_name'])
        if success:
            await page.wait_for_load_state("networkidle", timeout=10000)

        # まず一覧ページのヘッダーが表示されているか確認
        try:
            header_selector = 'table > thead > tr'
            header_element = await page.wait_for_selector(header_selector, timeout=5000)
            
            if header_element:
                logger.info(f"{hospital_info['hospital_name']}: 既にログイン済みです。ログイン処理をスキップします")
                login_status.update_hospital_status(hospital_info['hospital_name'], True)
                user_info['ログイン状態'] = '成功'
                user_info['ログイン方法'] = 'セッション再利用'

                # セッション再利用時も「今日」ボタンをクリック（堅牢版）
                success = await click_today_button_robust(page, hospital_info['hospital_name'])
                if success:
                    # データの読み込みを待機
                    await page.wait_for_load_state('networkidle', timeout=10000)

                return True

        except TimeoutError:
            logger.debug(f"{hospital_info['hospital_name']}: 一覧ページは表示されていません。ログイン処理を開始します")

        # 以下、通常のログイン処理
        success = await click_back_to_login_robust(page, hospital_info['hospital_name'])
        if success:
            await page.wait_for_load_state("networkidle", timeout=30000)
        
        # ログインフォームの入力
        logger.info(f"{hospital_info['hospital_name']}: ログイン情報を入力中...")
        try:
            await page.wait_for_selector('#email', timeout=10000)
            await page.wait_for_selector('#password', timeout=10000)
            
            await page.fill('#email', hospital_info['username'])
            await page.fill('#password', hospital_info['password'])
            
            # ログインボタンの押下（堅牢版）
            success = await click_login_button_robust(page, hospital_info['hospital_name'])
            if not success:
                error_msg = "ログインボタンのクリックに失敗"
                login_status.update_hospital_status(hospital_info['hospital_name'], False, error_msg)
                user_info['ログイン状態'] = '失敗'
                user_info['エラー'] = error_msg
                return False
            
            # ダッシュボード表示の待機（一覧ページのヘッダーが表示されるまで）
            header_selector = 'table > thead > tr'
            await page.wait_for_selector(header_selector, timeout=30000)
            logger.info(f"{hospital_info['hospital_name']}: 一覧ページが表示されました（ログイン成功）")
            
            # 「今日」ボタンをクリック（堅牢版）
            success = await click_today_button_robust(page, hospital_info['hospital_name'])
            if success:
                # データの読み込みを待機
                await page.wait_for_load_state('networkidle', timeout=10000)

            logger.info(f"{hospital_info['hospital_name']}: ログインとナビゲーションが完了しました")
            login_status.update_hospital_status(hospital_info['hospital_name'], True)
            user_info['ログイン状態'] = '成功'
            user_info['ログイン方法'] = '新規ログイン'
            return True
            
        except TimeoutError:
            error_msg = "ログインフォームまたはダッシュボードの表示待ち中にタイムアウト"
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

async def extract_patient_data(page, user_info):
    """患者データを抽出（堅牢版：列番号非依存）- クリニクス会員対応版"""
    try:
        # JavaScriptを使用してデータを抽出
        results = await page.evaluate("""
            () => {
                const records = [];
                
                // すべてのテーブル行を取得（クラス名に依存しない）
                const allRows = document.querySelectorAll('tr');
                
                for (const row of allRows) {
                    try {
                        // 行全体のテキストを取得
                        const rowText = row.textContent || row.innerText || '';
                        
                        // 必須条件：OASIS会計 AND 算定待ち の両方が含まれる
                        if (!rowText.includes('OASIS会計') || !rowText.includes('算定待ち')) {
                            continue;
                        }
                        
                        // 行内のすべてのセルを取得
                        const cells = Array.from(row.querySelectorAll('td, th'));
                        
                        // データ抽出：各セルのテキストを解析
                        let chartNumber = '';
                        let time = '';
                        let department = '不明';
                        
                        // カルテ番号検索（5桁以上の数字）- クリニクス会員対応版
                        for (const cell of cells) {
                            const cellText = (cell.textContent || '').trim();
                            
                            // まず従来の完全数字パターンを試す（優先）
                            let numericMatch = cellText.match(/^\\d{5,}$/);
                            if (numericMatch) {
                                chartNumber = numericMatch[0];
                                break;
                            }
                            
                            // 完全数字でない場合、部分的な数字抽出を試す（クリニクス会員対応）
                            numericMatch = cellText.match(/(\\d{5,})/);
                            if (numericMatch) {
                                chartNumber = numericMatch[1];
                                // ログ出力で特殊パターンを記録
                                console.log(`特殊パターン検出: "${cellText}" から "${chartNumber}" を抽出`);
                                break;
                            }
                        }
                        
                        // 時刻検索（複数パターンに対応）
                        for (const cell of cells) {
                            const cellText = (cell.textContent || '').trim();
                            
                            // HH:MM 形式（24時間表記）
                            const timeMatch = cellText.match(/^([01]?\\d|2[0-3]):[0-5]\\d$/);
                            if (timeMatch && !cellText.includes('〜')) {
                                time = timeMatch[0];
                                break;
                            }
                        }
                        
                        // 診療科検索（キーワードベース）
                        const medicalKeywords = [
                            '検査', '診察', 'エコー', 'レントゲン', 'CT', 'MRI', 
                            '内科', '外科', '整形外科', '皮膚科', '眼科', '耳鼻科',
                            '小児科', '産婦人科', '泌尿器科', '脳神経外科',
                            '心臓血管外科', '呼吸器科', '消化器科', '循環器科',
                            '外来', '初診', '再診', '健診', '予防接種'
                        ];
                        
                        for (const cell of cells) {
                            const cellText = (cell.textContent || '').trim();
                            
                            // 医療関連キーワードを含むセルを診療科とする
                            if (cellText && medicalKeywords.some(keyword => 
                                cellText.includes(keyword))) {
                                department = cellText;
                                break;
                            }
                        }
                        
                        // データの妥当性チェック
                        if (chartNumber && time) {
                            // 重複チェック（同じカルテ番号が既に存在しないか）
                            const exists = records.some(record => 
                                record.patient_id === chartNumber);
                            
                            if (!exists) {
                                const record = {
                                    patient_id: chartNumber,     // 既存システムとの互換性維持
                                    chart_number: chartNumber,   // 正式名称
                                    department: department,
                                    end_time: time
                                };
                                records.push(record);
                                console.log(`Found record - ID: ${chartNumber}, Dept: ${department}, Time: ${time}`);
                            }
                        }
                        
                    } catch (rowError) {
                        console.error('行の処理中にエラー:', rowError);
                        continue;
                    }
                }
                
                return {
                    records: records,
                    debug: {
                        totalRows: allRows.length,
                        extractedCount: records.length,
                        method: 'robust_text_based_with_clinics_member_support',
                        timestamp: new Date().toISOString()
                    }
                };
            }
        """)
        
        debug_info = results.get('debug', {})
        if debug_info:
            logger.debug(f"{user_info.get('hospital_name', 'Unknown')}: "
                      f"方式={debug_info.get('method', 'unknown')}, "
                      f"全行数={debug_info.get('totalRows', 0)}, "
                      f"抽出件数={debug_info.get('extractedCount', 0)}, "
                      f"取得時刻={debug_info.get('timestamp')}")

        extracted_records = results.get('records', [])
        if extracted_records:
            for record in extracted_records:
                logger.info(f"抽出データ - カルテ番号: {record['patient_id']}, 診療科: {record['department']}, 時間: {record['end_time']}")
        else:
            logger.debug(f"{user_info.get('hospital_name', 'Unknown')}: OASIS会計＆算定待ちのデータはありません")

        return extracted_records
        
    except Exception as e:
        logger.error(f"{user_info.get('hospital_name', 'Unknown')}: データ抽出中にエラー: {e}")
        logger.error(traceback.format_exc())
        return []
        
async def process_and_insert_data(records, user_info):
    """データを医療機関情報とともにmedical_data_inserterに渡す"""
    try:
        if not records:
            return

        json_data = {
            "hospital_name": user_info['hospital_name'],
            "system_type": user_info.get('システム種別', 'クリニクス'),
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
                if decoded_stdout.strip():
                    logger.info(f"データベース挿入成功: {decoded_stdout}")
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
    """定期的に全てのページから患者データを抽出し、データベースに挿入する"""
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
    extract_interval = int(config.get('setting', 'clinics_polling_interval', fallback=10))

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

                # 既存のページを使用するか新しいページを作成する
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
            login_status.update_hospital_status("CLINICS", True)
            login_status.get_login_summary()  # ログ出力
            return

        async with async_playwright() as playwright:
            await run(playwright, config, shutdown_event, login_status, hospitals)

    except asyncio.CancelledError:
        logger.debug("メイン処理がキャンセルされました")
    except Exception as e:
        logger.error(f"予期せぬエラーが発生しました: {e}")
        logger.debug("スタックトレース:", exc_info=True)

if __name__ == "__main__":
    # 直接実行時用のシャットダウンイベントとログイン状態管理
    shutdown_event = asyncio.Event()
    login_status = LoginStatus("CLINICS")  # システム名を指定してLoginStatusを初期化
    try:
        asyncio.run(main_with_shutdown(shutdown_event, login_status))
    except KeyboardInterrupt:
        logger.info("キーボード割り込みを検知しました")