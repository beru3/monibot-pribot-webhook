#!/usr/bin/env python3
"""
医歩（ippo）監視システム
Backlogから医療機関情報を取得し、会計待ちデータを監視
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
SCREENSHOT_DIR = os.path.join(project_root, 'src', 'core', 'screenshots')

# ロガー設定
logger = LoggerFactory.setup_logger('ippo')

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
    """Backlogから医歩の医療機関情報を取得する"""
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
            # 種別（issueType）が「医歩」であることを確認
            if not issue.get('issueType') or issue['issueType'].get('name') != '医歩':
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
                    'system_type': '医歩'
                }
                
                hospitals.append(hospital_info)
                logger.info(f"医療機関追加: {hospital_name} (ID: {login_id}, 証明書: {certificate_order}, グループ: {team})")

        logger.info(f"医歩対象医療機関数: {len(hospitals)}")
        return hospitals

    except Exception as e:
        logger.error(f"医療機関情報取得中にエラー: {e}")
        logger.debug(f"エラーの詳細:\n{traceback.format_exc()}")
        return []

async def click_ok_button_with_retry(page, hospital, max_retries=3):
    """OKボタンをクリック（リトライ機能付き、医師選択ダイアログ限定版）"""
    for attempt in range(max_retries):
        try:
            logger.info(f"{hospital['hospital_name']}: OKボタンクリック試行 {attempt + 1}/{max_retries}")

            # --- 「医師選択」ダイアログを待機 ---
            dialog = page.locator("div.x-window:visible", has_text="医師選択")
            await dialog.wait_for(timeout=15000)

            # --- マスク解除を待機 ---
            try:
                await page.wait_for_selector("div.ext-el-mask", state="hidden", timeout=10000)
                logger.debug(f"{hospital['hospital_name']}: マスクが非表示になりました")
            except:
                logger.debug(f"{hospital['hospital_name']}: マスク解除待機でタイムアウト、続行します")

            ok_clicked = False

            # === 方法A: 「医師選択」ダイアログ内のOKボタンを直接クリック ===
            try:
                ok_btn = dialog.locator("button", has_text="OK")
                await ok_btn.wait_for(state="visible", timeout=5000)
                await ok_btn.click(force=True)
                ok_clicked = True
                logger.info(f"{hospital['hospital_name']}: 医師選択ダイアログ内のOKをクリック成功")
            except Exception as e:
                logger.debug(f"{hospital['hospital_name']}: 方法A失敗（Playwright直接）: {e}")

            # === 方法B: ExtJSハンドラを直接呼び出す ===
            if not ok_clicked:
                try:
                    handled = await page.evaluate("""
                        (() => {
                            if (!(window.Ext && (Ext.WindowMgr || Ext.WindowManager))) return false;
                            const mgr = Ext.WindowMgr || Ext.WindowManager;
                            const win = mgr.getActive ? mgr.getActive() : (mgr.getActiveWindow && mgr.getActiveWindow());
                            if (!win || !win.buttons) return false;
                            const ok = win.buttons.find(b => (b.text || '').trim() === 'OK');
                            if (!ok) return false;
                            if (ok.fireEvent) ok.fireEvent('click', ok);
                            if (ok.handler) ok.handler.call(ok, ok, {});
                            return true;
                        })()
                    """)
                    if handled:
                        ok_clicked = True
                        logger.info(f"{hospital['hospital_name']}: ExtJSハンドラ呼び出しでOKを実行")
                except Exception as e:
                    logger.debug(f"{hospital['hospital_name']}: 方法B失敗（ExtJSハンドラ）: {e}")

            # === 方法C: Enterキー ===
            if not ok_clicked:
                try:
                    await page.keyboard.press("Enter")
                    ok_clicked = True
                    logger.info(f"{hospital['hospital_name']}: EnterキーでOKを実行")
                except Exception as e:
                    logger.debug(f"{hospital['hospital_name']}: 方法C失敗: {e}")

            # === OKクリック後の確認 ===
            if ok_clicked:
                await asyncio.sleep(2)
                dialog_closed = await page.evaluate("""
                    () => {
                        const dialogs = document.querySelectorAll('div.x-window');
                        const visibleDialogs = Array.from(dialogs).filter(d => d.offsetParent !== null);
                        return visibleDialogs.length === 0;
                    }
                """)
                if dialog_closed:
                    logger.info(f"{hospital['hospital_name']}: ダイアログが正常に閉じました")
                else:
                    logger.warning(f"{hospital['hospital_name']}: ダイアログがまだ表示されています")
                return True

        except Exception as e:
            logger.error(f"{hospital['hospital_name']}: OKボタンクリックエラー（試行 {attempt + 1}）: {e}")
            logger.debug(traceback.format_exc())
            await asyncio.sleep(2)

    logger.error(f"{hospital['hospital_name']}: {max_retries}回の試行後もOKボタンをクリックできませんでした")
    return False

async def login_with_retry(page, hospital, max_retries=3):
    """ログイン処理（OKボタンのみリトライ）"""
    try:
        logger.info(f"{hospital['hospital_name']}: ログイン処理を開始します")
        
        # 証明書選択が必要な場合、別スレッドで処理
        cert_thread = None
        if hospital.get('certificate_order'):
            cert_order = int(hospital['certificate_order'])
            logger.info(f"証明書選択準備: {cert_order}番目")
            
            # 証明書選択を別スレッドで実行
            cert_thread = threading.Thread(target=select_certificate, args=(cert_order,))
            cert_thread.start()
        
        # 医歩のログインページへ遷移
        await page.goto('https://kyogoku.ippo.co.jp/Karte/', wait_until='domcontentloaded', timeout=60000)
        
        # 証明書選択スレッドの完了を待つ
        if cert_thread:
            cert_thread.join()
        
        await asyncio.sleep(3)
        
        # マスクが消えるまで待機
        try:
            await page.wait_for_selector('div.ext-el-mask', state='hidden', timeout=5000)
            logger.debug(f"{hospital['hospital_name']}: マスクが非表示になりました")
        except:
            logger.debug(f"{hospital['hospital_name']}: マスクの待機タイムアウト（続行）")
        
        # ID入力
        await page.fill('input#ext-comp-1007', hospital['login_id'])
        await asyncio.sleep(0.5)
        
        # パスワード入力
        await page.fill('input#ext-comp-1008', hospital['password'])
        await asyncio.sleep(0.5)
        
        # ログインボタンをJavaScriptで強制クリック（マスクを回避）
        logger.debug(f"{hospital['hospital_name']}: ログインボタンをクリックします")
        login_clicked = await page.evaluate("""
            () => {
                const loginButton = document.querySelector('div#ext-comp-1011');
                if (loginButton) {
                    console.log('ログインボタンを発見');
                    loginButton.click();
                    return true;
                }
                return false;
            }
        """)
        
        if not login_clicked:
            logger.error(f"{hospital['hospital_name']}: ログインボタンが見つかりません")
            return False
        
        logger.info(f"{hospital['hospital_name']}: ログインボタンをクリックしました")
        await asyncio.sleep(8)  # ダイアログ表示を待つ（5秒→8秒に延長）
        
        # 「本人」選択ダイアログのOKボタンクリック（リトライ機能付き）
        ok_success = await click_ok_button_with_retry(page, hospital, max_retries=max_retries)
        
        if not ok_success:
            logger.error(f"{hospital['hospital_name']}: OKボタンのクリックに失敗しました")
            return False
        
        # ログイン確認（患者リスト画面が表示されるか）
        try:
            await page.wait_for_selector('div.x-grid3-body', timeout=20000)
            logger.info(f"{hospital['hospital_name']}: ログイン成功")
            
            # さらに待機して画面が完全にロードされるのを待つ
            await asyncio.sleep(3)
            
            # フィルタ設定：会計待ちをアクティブにする
            await set_filter_accounting_wait(page, hospital)
            
            return True
        except:
            logger.error(f"{hospital['hospital_name']}: ログイン失敗（患者リスト画面が表示されませんでした）")
            
            # デバッグ: 現在の状態を詳細確認
            try:
                current_url = page.url
                logger.debug(f"現在のURL: {current_url}")
                
                # 現在表示されている要素を確認
                page_state = await page.evaluate("""
                    () => {
                        return {
                            hasGrid: !!document.querySelector('div.x-grid3-body'),
                            hasDialog: !!document.querySelector('div.x-window'),
                            bodyText: document.body.textContent.substring(0, 500)
                        };
                    }
                """)
                logger.debug(f"ページ状態: {page_state}")
                
            except:
                pass
            return False
            
    except Exception as e:
        logger.error(f"{hospital['hospital_name']}: ログインエラー: {e}")
        logger.debug(traceback.format_exc())
        return False

async def set_filter_accounting_wait(page, hospital):
    """会計待ちフィルタのみをアクティブに設定（他のフィルタは非アクティブ化）"""
    try:
        logger.info(f"{hospital['hospital_name']}: フィルタ状態を確認・調整します")
        
        # 全フィルタの現在状態を確認（画像URLで識別）
        filters_state = await page.evaluate("""
            () => {
                // フィルタボタンを画像URLで直接検索
                const allDivs = document.querySelectorAll('div.x-box-item[style*="cursor: pointer"]');
                const states = [];
                
                for (const element of allDivs) {
                    const style = element.style;
                    const bgImage = style.backgroundImage;
                    
                    // フィルタボタンかどうか判定（receipt-search-btn を含む画像のみ）
                    if (!bgImage || !bgImage.includes('receipt-search-btn')) {
                        continue;
                    }
                    
                    const bgPos = style.backgroundPosition;
                    const isActive = bgPos === '0px -40px';
                    
                    // 画像URLからフィルタ種類を判定
                    let filterName = '不明';
                    let isAccountingWait = false;
                    
                    if (bgImage.includes('receipt-search-btn-wait-check.png')) {
                        filterName = '会計待ち';
                        isAccountingWait = true;
                    } else if (bgImage.includes('receipt-search-btn-wait.png')) {
                        filterName = '受付待ち';
                    } else if (bgImage.includes('receipt-search-btn-consult.png')) {
                        filterName = '診察中';
                    } else if (bgImage.includes('receipt-search-btn-proceeding.png')) {
                        filterName = '処置中';
                    } else if (bgImage.includes('receipt-search-btn-rehab.png')) {
                        filterName = 'リハビリ中';
                    } else if (bgImage.includes('receipt-search-btn-cancel.png')) {
                        filterName = 'キャンセル';
                    } else if (bgImage.includes('receipt-search-btn-end.png')) {
                        filterName = '終了';
                    } else if (bgImage.includes('receipt-search-btn-check.png')) {
                        filterName = '会計済';
                    }
                    
                    states.push({
                        id: element.id,
                        name: filterName,
                        isActive: isActive,
                        isAccountingWait: isAccountingWait,
                        backgroundPosition: bgPos,
                        backgroundImage: bgImage
                    });
                }
                
                return states;
            }
        """)
        
        if not filters_state or len(filters_state) == 0:
            logger.error(f"{hospital['hospital_name']}: フィルタボタンが見つかりません")
            return
        
        logger.info(f"{hospital['hospital_name']}: 検出したフィルタ数: {len(filters_state)}")
        
        # 現在の状態をログ出力
        logger.info(f"{hospital['hospital_name']}: 現在のフィルタ状態:")
        for filter_info in filters_state:
            status = "アクティブ" if filter_info['isActive'] else "非アクティブ"
            logger.info(f"  - {filter_info['name']} (ID: {filter_info['id']}): {status}")
        
        # 調整が必要なフィルタを特定
        needs_adjustment = False
        filters_to_adjust = []
        
        for filter_info in filters_state:
            if filter_info['isAccountingWait']:  # 会計待ち
                if not filter_info['isActive']:
                    needs_adjustment = True
                    filters_to_adjust.append({
                        'id': filter_info['id'],
                        'name': filter_info['name'],
                        'action': 'アクティブ化'
                    })
                    logger.info(f"{hospital['hospital_name']}: 会計待ち({filter_info['id']})をアクティブ化する必要があります")
            else:  # その他のフィルタ
                if filter_info['isActive']:
                    needs_adjustment = True
                    filters_to_adjust.append({
                        'id': filter_info['id'],
                        'name': filter_info['name'],
                        'action': '非アクティブ化'
                    })
                    logger.info(f"{hospital['hospital_name']}: {filter_info['name']}({filter_info['id']})を非アクティブ化する必要があります")
        
        if not needs_adjustment:
            logger.info(f"{hospital['hospital_name']}: フィルタ状態は既に正しく設定されています")
            return
        
        # フィルタをクリックして調整
        logger.info(f"{hospital['hospital_name']}: {len(filters_to_adjust)}個のフィルタを調整します")
        for filter_adjust in filters_to_adjust:
            try:
                await page.click(f'div#{filter_adjust["id"]}')
                await asyncio.sleep(0.5)  # クリック間隔
                logger.info(f"{hospital['hospital_name']}: {filter_adjust['name']}を{filter_adjust['action']}しました")
            except Exception as e:
                logger.warning(f"{hospital['hospital_name']}: {filter_adjust['name']}のクリック失敗: {e}")
        
        # 最後に1秒待機
        await asyncio.sleep(1)
        
        # 調整後の状態を確認
        after_state = await page.evaluate("""
            () => {
                const allDivs = document.querySelectorAll('div.x-box-item[style*="cursor: pointer"]');
                const states = [];
                
                for (const element of allDivs) {
                    const style = element.style;
                    const bgImage = style.backgroundImage;
                    
                    if (!bgImage || !bgImage.includes('receipt-search-btn')) {
                        continue;
                    }
                    
                    const bgPos = style.backgroundPosition;
                    const isActive = bgPos === '0px -40px';
                    
                    let filterName = '不明';
                    let isAccountingWait = false;
                    
                    if (bgImage.includes('receipt-search-btn-wait-check.png')) {
                        filterName = '会計待ち';
                        isAccountingWait = true;
                    } else if (bgImage.includes('receipt-search-btn-wait.png')) {
                        filterName = '受付待ち';
                    } else if (bgImage.includes('receipt-search-btn-consult.png')) {
                        filterName = '診察中';
                    } else if (bgImage.includes('receipt-search-btn-proceeding.png')) {
                        filterName = '処置中';
                    } else if (bgImage.includes('receipt-search-btn-rehab.png')) {
                        filterName = 'リハビリ中';
                    } else if (bgImage.includes('receipt-search-btn-cancel.png')) {
                        filterName = 'キャンセル';
                    } else if (bgImage.includes('receipt-search-btn-end.png')) {
                        filterName = '終了';
                    } else if (bgImage.includes('receipt-search-btn-check.png')) {
                        filterName = '会計済';
                    }
                    
                    states.push({
                        name: filterName,
                        isActive: isActive,
                        isAccountingWait: isAccountingWait
                    });
                }
                
                return states;
            }
        """)
        
        # 結果確認
        logger.info(f"{hospital['hospital_name']}: 調整後のフィルタ状態:")
        accounting_wait_active = False
        other_filters_inactive = True
        
        for filter_info in after_state:
            status = "アクティブ" if filter_info['isActive'] else "非アクティブ"
            logger.info(f"  - {filter_info['name']}: {status}")
            
            if filter_info['isAccountingWait']:
                accounting_wait_active = filter_info['isActive']
            else:
                if filter_info['isActive']:
                    other_filters_inactive = False
        
        if accounting_wait_active and other_filters_inactive:
            logger.info(f"{hospital['hospital_name']}: ✓ フィルタ設定完了（会計待ちのみアクティブ）")
        else:
            logger.warning(f"{hospital['hospital_name']}: ⚠ フィルタ設定に問題がある可能性があります")
            
    except Exception as e:
        logger.error(f"{hospital['hospital_name']}: フィルタ設定エラー: {e}")
        logger.debug(traceback.format_exc())

async def extract_accounting_wait_data(page, hospital):
    """会計待ちデータを抽出"""
    try:
        logger.debug(f"{hospital['hospital_name']}: データ抽出開始")
        
        data = await page.evaluate("""
            () => {
                const results = [];
                
                // 左側のテーブル（患者番号、受付状態を含む）
                const leftRows = document.querySelectorAll('div.x-grid3-body')[0]?.querySelectorAll('div.x-grid3-row');
                // 右側のテーブル（診療科、受付時間を含む）
                const rightRows = document.querySelectorAll('div.x-grid3-body')[1]?.querySelectorAll('div.x-grid3-row');
                
                if (!leftRows || !rightRows) return results;
                
                for (let i = 0; i < leftRows.length; i++) {
                    try {
                        const leftRow = leftRows[i];
                        const rightRow = rightRows[i];
                        
                        // 受付状態が「会計待ち」かチェック
                        const statusCell = leftRow.querySelector('td.x-grid3-td-btnChangeStatus div');
                        if (!statusCell || !statusCell.textContent.includes('会計待ち')) continue;
                        
                        // 患者番号（左側）
                        const patientNoCell = leftRow.querySelector('td.x-grid3-td-patientNo div');
                        const patientNo = patientNoCell ? patientNoCell.textContent.trim() : '';
                        
                        // 診療科（右側）
                        const departmentCell = rightRow.querySelector('td.x-grid3-td-departmentName div');
                        const department = departmentCell ? departmentCell.textContent.trim() : '';
                        
                        // 受付時間（右側）
                        const receptionTimeCell = rightRow.querySelector('td.x-grid3-td-receptionDate div');
                        const receptionTime = receptionTimeCell ? receptionTimeCell.textContent.trim() : '';
                        
                        if (patientNo) {
                            results.push({
                                patient_id: patientNo,
                                department: department,
                                end_time: receptionTime
                            });
                        }
                    } catch (err) {
                        console.error('Row processing error:', err);
                    }
                }
                
                return results;
            }
        """)
        
        if data:
            logger.info(f"{hospital['hospital_name']}: {len(data)}件の会計待ちデータを抽出")
        
        return data
        
    except Exception as e:
        logger.error(f"{hospital['hospital_name']}: データ抽出エラー: {e}")
        logger.debug(traceback.format_exc())
        return []

async def monitor_hospital(page, hospital, config, shutdown_event):
    """医療機関の監視処理"""
    polling_interval = int(config.get('setting', 'ippo_polling_interval', fallback=10))
    
    logger.info(f"{hospital['hospital_name']}: 監視開始（間隔: {polling_interval}秒）")
    
    while not shutdown_event.is_set():
        try:
            # データ抽出
            accounting_data = await extract_accounting_wait_data(page, hospital)
            
            # データベースに挿入
            if accounting_data:
                await process_and_insert_data(accounting_data, hospital)
            
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
            "system_type": hospital_info.get('system_type', '医歩'),
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
    """医歩監視のメイン処理"""
    
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
                    viewport={'width': 1920, 'height': 1080},
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
        logger.info("医歩監視システムが稼働中です")
        await shutdown_event.wait()
        
    except Exception as e:
        logger.error(f"医歩監視処理中にエラー: {e}")
        logger.debug(traceback.format_exc())
    finally:
        # クリーンアップ
        logger.info("医歩監視システムを終了します")
        
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
            login_status.update_hospital_status("医歩", True)
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
    login_status = LoginStatus("医歩")
    
    try:
        asyncio.run(main_with_shutdown(shutdown_event, login_status))
    except KeyboardInterrupt:
        logger.info("キーボード割り込みを検出しました")
        shutdown_event.set()