# src/core/digikar_monitor.py
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
logger = LoggerFactory.setup_logger('digikar_monitor')

# パス定義
LOG_DIR = os.path.join(project_root, 'log')
DEBUG_DIR = os.path.join(LOG_DIR, 'debug')
CONFIG_DIR = os.path.join(project_root, 'config')
SESSION_DIR = os.path.join(project_root, 'session')

def select_certificate(cert_order: int):
    """証明書選択ダイアログを処理"""
    try:
        # 画面サイズを取得
        screen_width, screen_height = pyautogui.size()
        
        # 安全のため、処理開始前にマウスを画面中央に移動
        pyautogui.moveTo(screen_width/2, screen_height/2)

        logger.debug(f"証明書選択処理を開始します (順番: {cert_order})...")
        time.sleep(3)  # 証明書ダイアログの表示を待機
        
        # 指定された順番まで下キーを押す
        for _ in range(cert_order - 1):
            time.sleep(0.5)
            pyautogui.press('down')
            
        time.sleep(1)
        pyautogui.press('enter')
        time.sleep(2)  # 証明書選択完了後の待機
        
        # 処理完了後も念のためマウスを画面中央に戻す
        pyautogui.moveTo(screen_width/2, screen_height/2)

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
                # システム種別が "デジカル" であることを確認
                if not issue.get('issueType') or issue['issueType'].get('name') != 'デジカル':
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
                        "system_type": 'デジカル'
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
        logger.info("グループごとのデジカル医療機関数:")
        for team, count in team_counts.items():
            if team:  # グループ未設定は表示しない
                logger.info(f"- {team}: {count}件")

        logger.info(f"取得した全課題数: {len(issues)}")
        logger.info(f"デジカル・ポーリング有効な医療機関数: {filtered_count}")
        
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
    """ログインとページ遷移を実行（XPath対応版）"""
    try:
        # 証明書選択スレッドの準備
        cert_thread = threading.Thread(
            target=select_certificate,
            args=(hospital_info['cert_order'],)
        )
        cert_thread.start()

        logger.info(f"{hospital_info['hospital_name']}: ページにアクセスしています...")
        await page.goto("https://digikar.jp/login", timeout=60000)
        
        # 証明書選択の完了を待つ
        cert_thread.join()

        logger.info(f"{hospital_info['hospital_name']}: ログインフォームの表示を待機中...")
        await page.wait_for_selector('input.form-control.dk-form-login.dk-form-login-top', timeout=10000)

        logger.info(f"{hospital_info['hospital_name']}: ログイン情報を入力中...")
        await page.fill('input.form-control.dk-form-login.dk-form-login-top', hospital_info['username'])
        await page.fill('input.dk-form-login:nth-child(2)', hospital_info['password'])
        await page.click('p:nth-child(3) > input[type="submit"]')

        # 簡単で確実なログイン成功判定
        try:
            logger.info(f"{hospital_info['hospital_name']}: ログイン成功を判定中...")
            
            # ログインボタンクリック後、ページ読み込み完了を待機
            await asyncio.sleep(3)
            try:
                await page.wait_for_load_state('networkidle', timeout=10000)
            except:
                logger.warning(f"{hospital_info['hospital_name']}: networkidle待機タイムアウト、処理続行")
            
            # 最大20秒間、2秒間隔でログイン成功を確認（より現実的な設定）
            for attempt in range(10):
                success = await page.evaluate("""
                    () => {
                        try {
                            // シンプルで確実な判定条件
                            const bodyText = document.body.textContent;
                            
                            // 1. エラーメッセージの確認（最優先）
                            const hasLoginError = bodyText.includes('ログインに失敗') || 
                                                 bodyText.includes('パスワードが正しくありません') ||
                                                 bodyText.includes('ユーザーIDが正しくありません') ||
                                                 bodyText.includes('認証に失敗');
                            
                            // 2. 医療機関の画面かどうか（確実な判定）
                            const isHospitalPage = bodyText.includes('クリニック') || 
                                                  bodyText.includes('病院') || 
                                                  bodyText.includes('医院') ||
                                                  bodyText.includes('診療所');
                            
                            // 3. テーブルの存在確認
                            const hasTable = document.querySelector('table') !== null;
                            
                            // 4. 受付/会計画面の確認
                            const isReceptionPage = bodyText.includes('受付') || 
                                                   bodyText.includes('会計') || 
                                                   bodyText.includes('患者') ||
                                                   bodyText.includes('診療');
                            
                            // 判定: エラーがなく、医療機関ページで、テーブルがあれば成功
                            const success = !hasLoginError && isHospitalPage && hasTable;
                            
                            console.log('ログイン判定 (簡易版):', {
                                hasLoginError,
                                isHospitalPage,
                                hasTable,
                                isReceptionPage,
                                success,
                                url: window.location.href,
                                title: document.title
                            });
                            
                            return success;
                        } catch (error) {
                            console.error('ログイン判定エラー:', error);
                            return false;
                        }
                    }
                """)
                
                if success:
                    logger.info(f"{hospital_info['hospital_name']}: ログイン成功")
                    login_status.update_hospital_status(hospital_info['hospital_name'], True)
                    user_info['ログイン状態'] = '成功'
                    user_info['ログイン方法'] = '新規ログイン'
                    user_info['判定方法'] = '簡易判定'
                    
                    # ページ構造分析を実行
                    logger.info(f"{hospital_info['hospital_name']}: ページ構造分析を実行します")
                    debug_results = await debug_page_structure(page, user_info)
                    logger.info(f"{hospital_info['hospital_name']}: ページ構造分析完了")
                    
                    return True
                
                logger.debug(f"{hospital_info['hospital_name']}: ログイン判定試行 {attempt + 1}/10")
                # 2秒待機して再試行
                await asyncio.sleep(2)
            
            # 20秒経ってもログイン成功を確認できない場合
            error_msg = "簡易ログイン判定でタイムアウト（20秒）"
            login_status.update_hospital_status(hospital_info['hospital_name'], False, error_msg)
            user_info['ログイン状態'] = '失敗'
            user_info['エラー'] = error_msg
            
            return False
                
        except Exception as login_error:
            error_msg = f"ログイン判定中にエラー: {str(login_error)}"
            login_status.update_hospital_status(hospital_info['hospital_name'], False, error_msg)
            user_info['ログイン状態'] = '失敗'
            user_info['エラー'] = error_msg
            logger.error(f"{hospital_info['hospital_name']}: {error_msg}")
            return False

    except Exception as e:
        error_msg = f"ログイン処理中にエラー: {str(e)}"
        login_status.update_hospital_status(hospital_info['hospital_name'], False, error_msg)
        user_info['ログイン状態'] = '失敗'
        user_info['エラー'] = error_msg
        logger.error(f"{hospital_info['hospital_name']}: {error_msg}")
        return False
        
# async def extract_patient_data(page, user_info):
#     """XPathベースの患者データ抽出（hospitalName削除版）"""
#     try:
#         logger.debug(f"{user_info['hospital_name']}: XPathベースデータ抽出を開始します")
        
#         results = await page.evaluate("""
#             () => {
#                 const records = [];
                
#                 try {
#                     // XPathで会計待ちの行を検索
#                     const accountWaitingXPath = "//td[contains(text(), '会計待') or contains(text(), '再計待')]/parent::tr";
#                     const result = document.evaluate(accountWaitingXPath, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
                    
#                     console.log('XPathで検出した会計待ち行数:', result.snapshotLength);
                    
#                     // 各対象行からデータを抽出
#                     for (let i = 0; i < result.snapshotLength; i++) {
#                         try {
#                             const row = result.snapshotItem(i);
#                             const cells = Array.from(row.querySelectorAll('td'));
                            
#                             if (cells.length < 4) continue; // 最低限の列数チェック
                            
#                             let patientId = '';
#                             let timeValue = '';
#                             let department = '不明';
#                             let isReAccount = false;
                            
#                             // 再会計フラグの確認（行全体のテキストから）
#                             const rowText = row.textContent;
#                             isReAccount = rowText.includes('再計待');
                            
#                             // 各セルを分析してデータを抽出
#                             cells.forEach((cell, cellIndex) => {
#                                 const text = cell.textContent.trim();
                                
#                                 // 患者番号の特定（3-4桁の数字）
#                                 if (!patientId) {
#                                     // セル内のリンクをチェック
#                                     const link = cell.querySelector('a');
#                                     if (link) {
#                                         const linkText = link.textContent.trim();
#                                         if (/^\\d{1,4}$/.test(linkText)) {
#                                             patientId = linkText;
#                                             return;
#                                         }
#                                     }
#                                     // セル自体のテキストをチェック
#                                     if (/^\\d{1,4}$/.test(text)) {
#                                         patientId = text;
#                                         return;
#                                     }
#                                 }
                                
#                                 // 時間の特定（HH:MM形式）
#                                 if (!timeValue && /^\\d{1,2}:\\d{2}$/.test(text)) {
#                                     timeValue = text;
#                                     return;
#                                 }
                                
#                                 // 診療科の特定
#                                 if (text && !department || department === '不明') {
#                                     // 診療科のキーワードを含むかチェック
#                                     if (text.includes('科') || text.includes('診療') || text.includes('外来') || 
#                                         text.includes('カウンセリング') || text.includes('訪問')) {
#                                         // 編集ボタンなどのテキストを除去
#                                         let cleanText = text.replace(/編集$/, '').trim();
#                                         cleanText = cleanText.replace(/\\s+/g, ' '); // 複数の空白を1つに
                                        
#                                         if (cleanText && cleanText !== '編集' && cleanText.length > 1) {
#                                             department = cleanText;
#                                             return;
#                                         }
#                                     }
#                                 }
#                             });
                            
#                             // 必要なデータが揃っているかチェック
#                             if (patientId && timeValue) {
#                                 const record = {
#                                     patient_id: patientId,
#                                     department: department,
#                                     end_time: timeValue,
#                                     re_account: isReAccount
#                                 };
                                
#                                 records.push(record);
#                                 console.log('抽出成功:', JSON.stringify(record));
#                             } else {
#                                 console.log('データ不足:', {
#                                     patientId: patientId || 'なし',
#                                     timeValue: timeValue || 'なし',
#                                     department,
#                                     cellCount: cells.length
#                                 });
#                             }
                            
#                         } catch (rowError) {
#                             console.error('行処理エラー:', rowError);
#                         }
#                     }
                    
#                     return {
#                         records: records,
#                         debug: {
#                             extractedCount: records.length,
#                             method: 'XPath',
#                             accountWaitingRows: result.snapshotLength
#                         },
#                         pageTitle: document.title,
#                         url: window.location.href,
#                         timestamp: new Date().toISOString()
#                         // hospitalName ← 削除
#                     };
                    
#                 } catch (error) {
#                     console.error('データ抽出エラー:', error);
#                     return {
#                         error: error.message,
#                         records: [],
#                         debug: { method: 'error' },
#                         analysis_method: error.message ? 'XPath_or_Fallback' : 'no_data',
#                         timestamp: new Date().toISOString()
#                         // hospitalName ← 削除
#                     }
#                 };
#             }
#         """)
        
#         debug_info = results.get('debug', {})
#         extracted_records = results.get('records', [])
        
#         logger.debug(f"{user_info['hospital_name']}: "
#                    f"抽出件数={debug_info.get('extractedCount', 0)}, "
#                    f"方式={debug_info.get('method', 'unknown')}")
        
#         if extracted_records:
#             logger.info(f"{user_info['hospital_name']}: {len(extracted_records)}件のデータを抽出しました")
#             for record in extracted_records:
#                 re_account_text = "【再会計】" if record.get('re_account', False) else ""
#                 logger.info(f"抽出データ: {re_account_text}ID={record['patient_id']}, " +
#                           f"診療科={record['department']}, 時間={record['end_time']}")
#         else:
#             logger.info(f"{user_info['hospital_name']}: 抽出対象データはありませんでした")
            
#         return extracted_records
        
#     except Exception as e:
#         logger.error(f"{user_info['hospital_name']}: データ抽出中にエラー: {e}")
#         logger.error(traceback.format_exc())
#         return []

async def extract_patient_data(page, user_info):
    """列名ベースの患者データ抽出（完全版）"""
    try:
        logger.debug(f"{user_info['hospital_name']}: 列名ベースデータ抽出を開始します")
        
        results = await page.evaluate("""
            () => {
                const records = [];
                
                try {
                    // ヘッダー行から列インデックスのマッピングを作成
                    const headerRow = document.querySelector('thead tr');
                    if (!headerRow) {
                        console.error('ヘッダー行が見つかりません');
                        return {
                            error: 'ヘッダー行が見つかりません',
                            records: [],
                            debug: { method: 'error' }
                        };
                    }
                    
                    const headers = Array.from(headerRow.querySelectorAll('th'));
                    const columnMap = {};
                    headers.forEach((th, index) => {
                        const columnName = th.textContent.trim();
                        columnMap[columnName] = index;
                    });
                    
                    console.log('列マッピング:', columnMap);
                    
                    // 必要な列のインデックスを取得
                    const statusIndex = columnMap['ステータス'];
                    const timeIndex = columnMap['時間'];
                    const patientIdIndex = columnMap['患者番号'];
                    const departmentIndex = columnMap['診療科'];
                    
                    if (statusIndex === undefined || timeIndex === undefined || 
                        patientIdIndex === undefined || departmentIndex === undefined) {
                        console.error('必要な列が見つかりません:', {
                            ステータス: statusIndex,
                            時間: timeIndex,
                            患者番号: patientIdIndex,
                            診療科: departmentIndex
                        });
                        return {
                            error: '必要な列が見つかりません',
                            records: [],
                            debug: { method: 'error', columnMap }
                        };
                    }
                    
                    // tbody内の全行を取得
                    const tbody = document.querySelector('tbody');
                    if (!tbody) {
                        console.error('tbody要素が見つかりません');
                        return {
                            error: 'tbody要素が見つかりません',
                            records: [],
                            debug: { method: 'error' }
                        };
                    }
                    
                    const allRows = tbody.querySelectorAll('tr');
                    console.log('全行数:', allRows.length);
                    
                    let accountWaitingCount = 0;
                    
                    // 各行をチェック
                    for (let i = 0; i < allRows.length; i++) {
                        try {
                            const row = allRows[i];
                            const cells = Array.from(row.querySelectorAll('td'));
                            
                            // 必要な列数があるかチェック
                            const maxIndex = Math.max(statusIndex, timeIndex, patientIdIndex, departmentIndex);
                            if (cells.length <= maxIndex) {
                                continue;
                            }
                            
                            // ステータス列をチェック
                            const statusCell = cells[statusIndex];
                            const statusText = statusCell ? statusCell.textContent.trim() : '';
                            
                            // 「会計待」または「再計待」が含まれているかチェック
                            if (!statusText.includes('会計待') && !statusText.includes('再計待')) {
                                continue;  // この行はスキップ
                            }
                            
                            accountWaitingCount++;
                            
                            // 再会計フラグ
                            const isReAccount = statusText.includes('再計待');
                            
                            let patientId = '';
                            let timeValue = '';
                            let department = '不明';
                            
                            // 時間の取得
                            const timeCell = cells[timeIndex];
                            if (timeCell) {
                                const text = timeCell.textContent.trim();
                                if (/^\d{1,2}:\d{2}$/.test(text)) {
                                    timeValue = text;
                                }
                            }
                            
                            // 患者番号の取得
                            const patientCell = cells[patientIdIndex];
                            if (patientCell) {
                                // セル内のリンクをチェック
                                const link = patientCell.querySelector('a');
                                if (link) {
                                    const linkText = link.textContent.trim();
                                    if (/^\d{1,4}$/.test(linkText)) {
                                        patientId = linkText;
                                    }
                                }
                                // リンクがない場合、セル自体のテキストをチェック
                                if (!patientId) {
                                    const text = patientCell.textContent.trim();
                                    if (/^\d{1,4}$/.test(text)) {
                                        patientId = text;
                                    }
                                }
                            }
                            
                            // 診療科の取得
                            const departmentCell = cells[departmentIndex];
                            if (departmentCell) {
                                let deptText = departmentCell.textContent.trim();
                                // 編集ボタンなどの余計なテキストを除去
                                deptText = deptText.replace(/編集$/, '').trim();
                                deptText = deptText.replace(/\s+/g, ' ');
                                
                                if (deptText && deptText !== '編集' && deptText.length > 1) {
                                    department = deptText;
                                }
                            }
                            
                            // 必要なデータが揃っているかチェック
                            if (patientId && timeValue) {
                                const record = {
                                    patient_id: patientId,
                                    department: department,
                                    end_time: timeValue,
                                    re_account: isReAccount
                                };
                                
                                records.push(record);
                                console.log('抽出成功:', JSON.stringify(record));
                            } else {
                                console.log('データ不足:', {
                                    patientId: patientId || 'なし',
                                    timeValue: timeValue || 'なし',
                                    department,
                                    status: statusText,
                                    cellCount: cells.length
                                });
                            }
                            
                        } catch (rowError) {
                            console.error('行処理エラー:', rowError);
                        }
                    }
                    
                    console.log('会計待ち行数:', accountWaitingCount);
                    
                    return {
                        records: records,
                        debug: {
                            extractedCount: records.length,
                            method: 'ColumnName_Status_Based',
                            accountWaitingRows: accountWaitingCount,
                            totalRows: allRows.length,
                            columnMap: columnMap
                        },
                        pageTitle: document.title,
                        url: window.location.href,
                        timestamp: new Date().toISOString()
                    };
                    
                } catch (error) {
                    console.error('データ抽出エラー:', error);
                    return {
                        error: error.message,
                        records: [],
                        debug: { method: 'error' },
                        timestamp: new Date().toISOString()
                    };
                }
            }
        """)
        
        debug_info = results.get('debug', {})
        extracted_records = results.get('records', [])
        
        logger.debug(f"{user_info['hospital_name']}: "
                   f"抽出件数={debug_info.get('extractedCount', 0)}, "
                   f"方式={debug_info.get('method', 'unknown')}, "
                   f"会計待ち行数={debug_info.get('accountWaitingRows', 0)}, "
                   f"全行数={debug_info.get('totalRows', 0)}")
        
        # 列マッピング情報をログ出力
        if 'columnMap' in debug_info:
            logger.debug(f"{user_info['hospital_name']}: 列マッピング={debug_info['columnMap']}")
        
        if extracted_records:
            logger.info(f"{user_info['hospital_name']}: {len(extracted_records)}件のデータを抽出しました")
            for record in extracted_records:
                re_account_text = "【再会計】" if record.get('re_account', False) else ""
                logger.info(f"抽出データ: {re_account_text}ID={record['patient_id']}, " +
                          f"診療科={record['department']}, 時間={record['end_time']}")
        else:
            logger.info(f"{user_info['hospital_name']}: 抽出対象データはありませんでした")
            
        return extracted_records
        
    except Exception as e:
        logger.error(f"{user_info['hospital_name']}: データ抽出中にエラー: {e}")
        logger.error(traceback.format_exc())
        return []

# async def debug_page_structure(page, user_info):
#     """XPath対応のページ構造デバッグ分析（hospitalName削除版）"""
#     try:
#         logger.info(f"{user_info['hospital_name']}: XPathベースページ構造分析を開始します")
        
#         # XPath 1.0対応の構造分析
#         structure_info = await page.evaluate("""
#             () => {
#                 try {
#                     // 基本的なページ構造の確認
#                     const tables = document.querySelectorAll('table');
#                     const tableCount = tables.length;
                    
#                     // XPath 1.0で会計待ち行を検出
#                     const accountWaitingXPath = "//td[contains(text(), '会計待') or contains(text(), '再計待')]/parent::tr";
#                     const result = document.evaluate(accountWaitingXPath, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
#                     const accountWaitingRows = result.snapshotLength;
                    
#                     // JavaScriptの正規表現で患者番号を検出（XPath 1.0対応）
#                     let patientIdElements = 0;
#                     const allElements = document.querySelectorAll('*');
#                     allElements.forEach(element => {
#                         const text = element.textContent.trim();
#                         // 3-4桁の数字のみを含むテキスト
#                         if (/^\\d{1,4}$/.test(text)) {
#                             patientIdElements++;
#                         }
#                     });
                    
#                     // 時間データの検出（JavaScriptの正規表現使用）
#                     let timeElements = 0;
#                     allElements.forEach(element => {
#                         const text = element.textContent.trim();
#                         // HH:MM形式の時間
#                         if (/^\\d{1,2}:\\d{2}$/.test(text)) {
#                             timeElements++;
#                         }
#                     });
                    
#                     // *** hospitalName関連のコードを削除 ***
#                     // const hospitalXPath = "//*[contains(text(), 'クリニック') or contains(text(), '病院') or contains(text(), '医院')]";
#                     // const hospitalResult = document.evaluate(hospitalXPath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
#                     // const hospitalName = hospitalResult.singleNodeValue ? hospitalResult.singleNodeValue.textContent.trim() : 'なし';
                    
#                     return {
#                         tableCount,
#                         accountWaitingRows,
#                         patientIdElements,
#                         timeElements,
#                         // hospitalName, ← 削除
#                         pageTitle: document.title,
#                         url: window.location.href,
#                         bodyTextLength: document.body.textContent.length,
#                         analysis_method: 'XPath1.0_with_JS_Regex'
#                     };
#                 } catch (error) {
#                     return {
#                         error: error.message,
#                         fallback: {
#                             tableCount: document.querySelectorAll('table').length,
#                             bodyTextLength: document.body ? document.body.textContent.length : 0
#                             // hospitalName ← 削除
#                         }
#                     };
#                 }
#             }
#         """)
        
#         logger.info(f"{user_info['hospital_name']}: ページ構造分析結果: {structure_info}")
#         return structure_info
        
#     except Exception as e:
#         logger.error(f"{user_info['hospital_name']}: ページ構造分析中にエラー: {e}")
#         return {"error": str(e)}
                
async def debug_page_structure(page, user_info):
    """列名ベースのページ構造デバッグ分析（完全版）"""
    try:
        logger.info(f"{user_info['hospital_name']}: 列名ベースページ構造分析を開始します")
        
        structure_info = await page.evaluate("""
            () => {
                try {
                    // 基本的なページ構造の確認
                    const tables = document.querySelectorAll('table');
                    const tableCount = tables.length;
                    
                    // ヘッダー行から列インデックスのマッピングを作成
                    const headerRow = document.querySelector('thead tr');
                    if (!headerRow) {
                        return {
                            error: 'ヘッダー行が見つかりません',
                            fallback: {
                                tableCount: tableCount,
                                bodyTextLength: document.body ? document.body.textContent.length : 0
                            }
                        };
                    }
                    
                    const headers = Array.from(headerRow.querySelectorAll('th'));
                    const columnMap = {};
                    headers.forEach((th, index) => {
                        const columnName = th.textContent.trim();
                        columnMap[columnName] = index;
                    });
                    
                    // 必要な列のインデックスを取得
                    const statusIndex = columnMap['ステータス'];
                    const timeIndex = columnMap['時間'];
                    const patientIdIndex = columnMap['患者番号'];
                    const departmentIndex = columnMap['診療科'];
                    
                    // tbody内の全行を取得
                    const tbody = document.querySelector('tbody');
                    if (!tbody) {
                        return {
                            error: 'tbody要素が見つかりません',
                            columnMap: columnMap,
                            tableCount: tableCount
                        };
                    }
                    
                    const allRows = tbody.querySelectorAll('tr');
                    
                    // 会計待ち行をカウント（ステータス列から）
                    let accountWaitingRows = 0;
                    if (statusIndex !== undefined) {
                        allRows.forEach(row => {
                            const cells = Array.from(row.querySelectorAll('td'));
                            if (cells.length > statusIndex) {
                                const statusCell = cells[statusIndex];
                                const statusText = statusCell ? statusCell.textContent.trim() : '';
                                if (statusText.includes('会計待') || statusText.includes('再計待')) {
                                    accountWaitingRows++;
                                }
                            }
                        });
                    }
                    
                    // 患者番号要素をカウント（患者番号列から）
                    let patientIdElements = 0;
                    if (patientIdIndex !== undefined && statusIndex !== undefined) {
                        allRows.forEach(row => {
                            const cells = Array.from(row.querySelectorAll('td'));
                            if (cells.length > Math.max(statusIndex, patientIdIndex)) {
                                // ステータスが会計待ちの行のみカウント
                                const statusCell = cells[statusIndex];
                                const statusText = statusCell ? statusCell.textContent.trim() : '';
                                if (statusText.includes('会計待') || statusText.includes('再計待')) {
                                    const patientCell = cells[patientIdIndex];
                                    const text = patientCell ? patientCell.textContent.trim() : '';
                                    if (/^\d{1,4}$/.test(text)) {
                                        patientIdElements++;
                                    }
                                }
                            }
                        });
                    }
                    
                    // 時間要素をカウント（時間列から）
                    let timeElements = 0;
                    if (timeIndex !== undefined && statusIndex !== undefined) {
                        allRows.forEach(row => {
                            const cells = Array.from(row.querySelectorAll('td'));
                            if (cells.length > Math.max(statusIndex, timeIndex)) {
                                // ステータスが会計待ちの行のみカウント
                                const statusCell = cells[statusIndex];
                                const statusText = statusCell ? statusCell.textContent.trim() : '';
                                if (statusText.includes('会計待') || statusText.includes('再計待')) {
                                    const timeCell = cells[timeIndex];
                                    const text = timeCell ? timeCell.textContent.trim() : '';
                                    if (/^\d{1,2}:\d{2}$/.test(text)) {
                                        timeElements++;
                                    }
                                }
                            }
                        });
                    }
                    
                    // 診療科要素をカウント（診療科列から）
                    let departmentElements = 0;
                    if (departmentIndex !== undefined && statusIndex !== undefined) {
                        allRows.forEach(row => {
                            const cells = Array.from(row.querySelectorAll('td'));
                            if (cells.length > Math.max(statusIndex, departmentIndex)) {
                                // ステータスが会計待ちの行のみカウント
                                const statusCell = cells[statusIndex];
                                const statusText = statusCell ? statusCell.textContent.trim() : '';
                                if (statusText.includes('会計待') || statusText.includes('再計待')) {
                                    const deptCell = cells[departmentIndex];
                                    const text = deptCell ? deptCell.textContent.trim() : '';
                                    if (text && text.length > 1 && text !== '編集') {
                                        departmentElements++;
                                    }
                                }
                            }
                        });
                    }
                    
                    return {
                        tableCount,
                        totalRows: allRows.length,
                        accountWaitingRows,
                        patientIdElements,
                        timeElements,
                        departmentElements,
                        columnMap,
                        pageTitle: document.title,
                        url: window.location.href,
                        bodyTextLength: document.body.textContent.length,
                        analysis_method: 'ColumnName_Status_Based'
                    };
                } catch (error) {
                    return {
                        error: error.message,
                        fallback: {
                            tableCount: document.querySelectorAll('table').length,
                            bodyTextLength: document.body ? document.body.textContent.length : 0
                        }
                    };
                }
            }
        """)
        
        logger.info(f"{user_info['hospital_name']}: ページ構造分析結果: {structure_info}")
        return structure_info
        
    except Exception as e:
        logger.error(f"{user_info['hospital_name']}: ページ構造分析中にエラー: {e}")
        return {"error": str(e)}
    
async def process_and_insert_data(records, hospital_info):
    """データを医療機関情報とともにmedical_data_inserterに渡す"""
    try:
        if not records:
            return

        # medical_data_inserterが期待する形式でデータを準備
        json_data = {
            "hospital_name": hospital_info['hospital_name'],
            "system_type": hospital_info.get('system_type', 'デジカル'),
            "team": hospital_info['team'],
            "issue_key": hospital_info['issue_key'],
            "patients": records
        }

        # medical_data_inserter.pyのパスを取得
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
            
            # logger.info(f"医療機関: {json_data['hospital_name']}")
            
            if process.returncode == 0:
                if decoded_stdout.strip():
                    logger.info(f"データベース挿入成功: {decoded_stdout}")
                # logger.info("データベース挿入が完了しました")
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
        hospital_name = hospital_info.get('hospital_name', 'Unknown Hospital')
        logger.error(f"医療機関 {hospital_name}: データ処理中にエラー: {str(e)}")
        logger.error(f"詳細なエラー情報: {traceback.format_exc()}")

async def periodic_extract_all(pages, interval, user_infos):
    while True:
        try:
            for index, (page, user_info) in enumerate(zip(pages, user_infos)):
                logger.debug(f"データ抽出を開始: {user_info.get('hospital_name', 'Unknown')}")
                try:
                    patient_data = await extract_patient_data(page, user_info)
                    if patient_data:
                        await process_and_insert_data(patient_data, user_info)
                except Exception as e:
                    logger.error(f"データ抽出中のエラー: {e}")
                
                await asyncio.sleep(interval)
        except Exception as e:
            logger.error(f"periodic_extract_all でエラー: {e}")
            await asyncio.sleep(5)  # エラー時は少し待機

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
    extract_interval = int(config.get('setting', 'digikar_polling_interval', fallback=10))

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
                            logger.debug(f"{hospital['hospital_name']}: ログイン成功後の待機を開始")
                            await asyncio.sleep(2)  # 次の医療機関の処理前に少し待機
                            logger.debug(f"{hospital['hospital_name']}: ログイン成功後の待機が完了")
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
        extract_task = None
        if not shutdown_event.is_set():
            logger.info("定期的なデータ抽出を開始します")
            extract_task = asyncio.create_task(
                periodic_extract_all(pages, extract_interval, user_infos)
            )
            logger.debug("データ抽出タスクを作成しました")

        # メインループ
        logger.info("メインループを開始します")
        while not shutdown_event.is_set():
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"メインループでエラー: {e}")
                break

        logger.info("メインループを終了します")

    except asyncio.CancelledError:
        logger.debug("実行がキャンセルされました")
    except Exception as e:
        logger.error(f"実行中にエラーが発生しました: {e}")
        logger.debug("スタックトレース:", exc_info=True)
    finally:
        if extract_task and not extract_task.done():  # extract_taskがNoneでない場合のみキャンセル
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
            # 完了のマークを付ける（医療機関数0なので追加の処理は不要）
            login_status.update_hospital_status("デジカル", True)
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

if __name__ == "__main__":
    # 直接実行時用のシャットダウンイベントとログイン状態管理
    shutdown_event = asyncio.Event()
    login_status = LoginStatus("デジカル")  # システム名を指定してLoginStatusを初期化
    try:
        asyncio.run(main_with_shutdown(shutdown_event, login_status))
    except KeyboardInterrupt:
        logger.info("キーボード割り込みを検知しました")