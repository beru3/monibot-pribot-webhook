#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import json
import shutil
import logging
import requests
import configparser
import traceback
import platform
import psutil
import atexit
import signal
from datetime import datetime, timedelta
import pdfplumber
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# プロジェクトルートと設定パスを明示的に指定
project_root = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(project_root, "config.ini")
LOG_DIR = os.path.join(project_root, "log")

# ログディレクトリが存在しない場合は作成
os.makedirs(LOG_DIR, exist_ok=True)

class PriBotSingleton:
    """PriBot単一インスタンス制御"""
    
    def __init__(self, lock_file="pribot.lock"):
        self.lock_file = os.path.join(project_root, lock_file)
        self.lock_acquired = False
        
    def acquire_lock(self):
        """ロック取得"""
        if os.path.exists(self.lock_file):
            with open(self.lock_file, 'r') as f:
                existing_pid = f.read().strip()
            
            if self.is_process_running(existing_pid):
                print(f"PriBotは既に実行中です (PID: {existing_pid})")
                return False
            else:
                # 古いロックファイルを削除
                os.remove(self.lock_file)
        
        # 新しいロックファイルを作成
        with open(self.lock_file, 'w') as f:
            f.write(str(os.getpid()))
        
        self.lock_acquired = True
        atexit.register(self.release_lock)
        return True
    
    def release_lock(self):
        """ロック解除"""
        if self.lock_acquired and os.path.exists(self.lock_file):
            os.remove(self.lock_file)
    
    def is_process_running(self, pid):
        """プロセス生存確認"""
        try:
            return psutil.pid_exists(int(pid))
        except:
            # psutil使えない場合のWindows用
            import subprocess
            try:
                result = subprocess.run(
                    f"tasklist /fi \"pid eq {pid}\"", 
                    shell=True, 
                    capture_output=True, 
                    text=True
                )
                return pid in result.stdout
            except:
                return False

def get_log_filename():
    """日付ベースのログファイル名を生成する（1日1ファイル）"""
    current_time = datetime.now()
    return os.path.join(LOG_DIR, f"{current_time.strftime('%Y%m%d')}_pribot.log")

def shorten_path(path):
    """パスを短縮表示する（最後のディレクトリ2つだけ表示）"""
    if not path:
        return path
    try:
        parts = path.replace('\\', '/').split('/')
        if len(parts) <= 2:
            return path
        return f".../{parts[-2]}/{parts[-1]}"
    except:
        return path

def setup_logger():
    """ロガーを設定する（1日1ファイル）"""
    logger = logging.getLogger('pribot')
    
    # 既存のハンドラをクリア
    if logger.handlers:
        for handler in logger.handlers:
            logger.removeHandler(handler)
    
    logger.setLevel(logging.INFO)
    
    # 外部ライブラリのログを抑制
    logging.getLogger('pdfminer').setLevel(logging.ERROR)
    logging.getLogger('PIL').setLevel(logging.ERROR)
    logging.getLogger('watchdog').setLevel(logging.WARNING)
    
    # ログファイル名（日付ベース）
    log_file = get_log_filename()
    file_exists = os.path.exists(log_file)
    
    # ファイルハンドラー（追記モード）
    file_handler = logging.FileHandler(log_file, encoding='utf-8', mode='a')
    file_handler.setLevel(logging.INFO)
    
    # コンソールハンドラー
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # カスタムフォーマッター
    class CustomFormatter(logging.Formatter):
        GREEN = '\033[92m'  # 成功
        RED = '\033[91m'    # 失敗
        YELLOW = '\033[93m' # 警告
        BLUE = '\033[94m'   # 情報
        BOLD = '\033[1m'    # 太字
        RESET = '\033[0m'   # リセット
        
        def __init__(self, use_colors=True):
            super().__init__()
            self.use_colors = use_colors
        
        def format(self, record):
            log_fmt = '%(asctime)s - %(name)s - %(levelname)s - '
            message = record.getMessage()
            
            # 色分け（コンソール出力の場合のみ）
            if self.use_colors:
                if record.levelno == logging.INFO:
                    if 'コピーしました' in message or '移動しました' in message or '成功' in message:
                        log_fmt = f'{log_fmt}{self.GREEN}{self.BOLD}[成功]{self.RESET} %(message)s'
                    else:
                        log_fmt = f'{log_fmt}%(message)s'
                elif record.levelno == logging.WARNING:
                    log_fmt = f'{self.YELLOW}{log_fmt}[警告] %(message)s{self.RESET}'
                elif record.levelno == logging.ERROR:
                    log_fmt = f'{self.RED}{self.BOLD}{log_fmt}[エラー] %(message)s{self.RESET}'
            else:
                # ファイル出力用（色なし）
                if record.levelno == logging.INFO:
                    if 'コピーしました' in message or '移動しました' in message or '成功' in message:
                        log_fmt = f'{log_fmt}[成功] %(message)s'
                    else:
                        log_fmt = f'{log_fmt}%(message)s'
                elif record.levelno == logging.WARNING:
                    log_fmt = f'{log_fmt}[警告] %(message)s'
                elif record.levelno == logging.ERROR:
                    log_fmt = f'{log_fmt}[エラー] %(message)s'
            
            # パスの短縮処理
            if 'パス' in message or 'フォルダ' in message or '->' in message:
                parts = message.split(' -> ')
                if len(parts) > 1:
                    message = f"{parts[0]} -> {shorten_path(parts[1])}"
                    record.args = ()
                    record.msg = message
                    
            formatter = logging.Formatter(log_fmt)
            return formatter.format(record)
    
    # フォーマッタを適用
    console_formatter = CustomFormatter(use_colors=True)
    file_formatter = CustomFormatter(use_colors=False)

    file_handler.setFormatter(file_formatter)
    console_handler.setFormatter(console_formatter)
    
    # ハンドラーの追加
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    if not file_exists:
        logger.info("====== PriBot ログセッション開始 ======")
        
    return logger

# ロガー初期化
logger = setup_logger()

def load_config():
    """設定ファイルを読み込む"""
    config = configparser.ConfigParser()
    
    if not os.path.exists(CONFIG_PATH):
        logger.error(f"設定ファイルが見つかりません: {CONFIG_PATH}")
        return None
        
    try:
        config.read(CONFIG_PATH, encoding='utf-8')
        logger.debug(f"設定ファイルを読み込みました: {CONFIG_PATH}")
        return config
        
    except Exception as e:
        logger.error(f"設定ファイルの読み込み中にエラー: {e}")
        return None

# フォーマット定義
FORMAT_DEFINITIONS = [
    {'id': 1, 'name': '診療費請求書兼領収書(縦)', 'page': 1, 'line': 1, 'pattern': '診療費請求書兼領収書\n診療日', 'use_rect': True, 'x0': 0, 'y0': 440, 'x1': 400, 'y1': 460},
    {'id': 2, 'name': '診療費請求書兼領収書(控え付き)', 'page': 1, 'line': 1, 'pattern': '診療費請求書兼領収書\nNo.', 'use_rect': True, 'x0': 45, 'y0': 375, 'x1': 155, 'y1': 395},
    {'id': 3, 'name': '診療費請求書兼領収書(横)', 'page': 1, 'line': 1, 'pattern': '診療費請求書兼領収書\n患者番号', 'use_rect': True, 'x0': 300, 'y0': 140, 'x1': 530, 'y1': 150},
    {'id': 4, 'name': '診療費明細書(タイプA)', 'page': 1, 'line': 1, 'pattern': '診療費明細書\nNo.', 'use_rect': True, 'x0': 200, 'y0': 80, 'x1': 560, 'y1': 90},
    {'id': 5, 'name': '処方箋', 'page': 1, 'line': 1, 'pattern': '処 方 箋', 'use_rect': True, 'x0': 260, 'y0': 90, 'x1': 420, 'y1': 100},
    {'id': 6, 'name': 'お薬手帳', 'page': 1, 'line': 2, 'pattern': '_処__方__日__', 'use_rect': False, "clinic_name_line": -2},
    {'id': 7, 'name': 'お薬情報', 'page': 1, 'line': 1, 'pattern': 'お薬情報（', 'use_rect': True, 'x0': 0, 'y0': 800, 'x1': 300, 'y1': 820},
    {'id': 8, 'name': '薬袋シール(三宅村)', 'page': 1, 'line': 1, 'pattern': '＊＊＊＊ 用法 ＊＊＊＊', 'use_rect': False, 'clinic_name_line': None, 'hardcoded_hospital': '三宅村'},
    {'id': 9, 'name': '診療費明細書(タイプB)', 'page': 1, 'line': 1, 'pattern': '診療費明細書\n1 頁', 'use_rect': True, 'x0': 83, 'y0': 784, 'x1': 242, 'y1': 795}
]

def get_custom_field_value(custom_fields, name):
    """カスタムフィールドから値を取得する"""
    try:
        for field in custom_fields:
            if field['name'] == name:
                if 'value' not in field or field['value'] is None:
                    return ''
                
                if isinstance(field['value'], dict):
                    if 'name' in field['value']:
                        return field['value']['name']
                    return ''
                
                return str(field['value'])
        return ''
    except Exception as e:
        logger.error(f"カスタムフィールド '{name}' の値取得中にエラー: {e}")
        return ''

def get_folder_settings(config):
    """Backlogからフォルダ設定を取得する"""
    try:
        space_name = config['backlog']['space_name']
        api_key = config['backlog']['api_key']
        project_id = config['backlog']['pribot_project_id']
        
        logger.info("Backlog APIからフォルダ設定を取得します")
        
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
            return get_default_folder_settings()
        
        issues = response.json()
        settings = None
        
        for issue in issues:
            if issue.get('issueType') and issue['issueType'].get('name') == 'PriBot設定':
                custom_fields = issue.get('customFields', [])
                watch_dir = get_custom_field_value(custom_fields, '監視フォルダパス')
                error_dir = get_custom_field_value(custom_fields, 'エラーフォルダパス')
                debug_dir = get_custom_field_value(custom_fields, 'デバッグフォルダパス')
                
                settings = {
                    "watch_dir": watch_dir if watch_dir else os.path.join(project_root, 'pribot_watch'),
                    "error_dir": error_dir if error_dir else os.path.join(project_root, 'pribot_error'),
                    "debug_dir": debug_dir if debug_dir else os.path.join(project_root, 'pribot_debug')
                }
                
                logger.info(f"監視フォルダパス: {settings['watch_dir']}")
                logger.info(f"エラーフォルダパス: {settings['error_dir']}")
                logger.info(f"デバッグフォルダパス: {settings['debug_dir']}")
                break
        
        if not settings:
            logger.warning("PriBot設定が見つかりませんでした。デフォルト値を使用します。")
            settings = get_default_folder_settings()
        
        # フォルダ作成
        for dir_key, dir_path in settings.items():
            if not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)
                logger.info(f"{dir_key} ディレクトリを作成しました: {dir_path}")
        
        return settings
        
    except Exception as e:
        logger.error(f"フォルダ設定の取得中にエラー: {e}")
        return get_default_folder_settings()

def get_default_folder_settings():
    """デフォルトフォルダ設定"""
    return {
        "watch_dir": os.path.join(project_root, 'pribot_watch'),
        "error_dir": os.path.join(project_root, 'pribot_error'),
        "debug_dir": os.path.join(project_root, 'pribot_debug')
    }

def get_hospital_info(config):
    """Backlogから医療機関情報を取得する"""
    try:
        space_name = config['backlog']['space_name']
        api_key = config['backlog']['api_key']
        project_id = config['backlog']['pribot_project_id']

        logger.info("Backlog APIリクエストを開始します")

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
            return []

        issues = response.json()
        logger.info(f"取得した全課題数: {len(issues)}")
        
        hospital_dict = {}
        skipped_count = 0
        polling_off_count = 0
        no_settings_count = 0

        for issue in issues:
            try:
                issue_key = issue.get('issueKey', '不明')
                summary = issue.get('summary', '不明')
                issue_type = issue.get('issueType', {}).get('name', '不明')
                
                if issue_type != '医療機関' or issue_type == 'PriBot設定':
                    skipped_count += 1
                    continue

                custom_fields = issue.get('customFields', [])
                polling = get_custom_field_value(custom_fields, 'ポーリング')
                
                if polling != 'ON':
                    polling_off_count += 1
                    continue
                
                setting_type = get_custom_field_value(custom_fields, '振り分け先の設定')
                folder_path = get_custom_field_value(custom_fields, '振り分け先フォルダパス')
                team = get_custom_field_value(custom_fields, 'グループ')
                
                if setting_type and folder_path:
                    if summary not in hospital_dict:
                        hospital_dict[summary] = {
                            "hospital_name": summary,
                            "issue_key": issue_key,
                            "team": team,
                            "distribution_settings": {},
                            "system_type": 'PriBot'
                        }
                    
                    hospital_dict[summary]['distribution_settings'][setting_type] = folder_path
                    logger.info(f"課題 {issue_key}: 振り分け先 '{setting_type}' = '{folder_path}'")
                else:
                    no_settings_count += 1
                    continue

            except Exception as e:
                logger.error(f"課題 {issue.get('issueKey', '不明')} の処理中にエラー: {e}")
                continue
                
        hospital_list = list(hospital_dict.values())
       
        if hospital_list:
            for hospital in hospital_list:
                logger.info(f"PriBot 監視対象の医療機関名: {hospital['hospital_name']}, 振り分け設定数: {len(hospital['distribution_settings'])}")
            
            logger.info(f"監視対象の医療機関数: {len(hospital_list)}")
        else:
            logger.warning("条件を満たす医療機関が見つかりませんでした")
        
        return hospital_list

    except Exception as e:
        logger.error(f"医療機関情報の取得中にエラー: {e}")
        return []

def identify_pdf_format(pdf_path):
    """PDFファイルのフォーマットを識別する"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if len(pdf.pages) > 0:
                page = pdf.pages[0]
                text = page.extract_text()

                if text:
                    # パターンの長さでソート（長い方が具体的なので優先）
                    sorted_formats = sorted(FORMAT_DEFINITIONS,
                                          key=lambda f: len(f['pattern']),
                                          reverse=True)

                    for format_def in sorted_formats:
                        # エスケープされた改行を実際の改行に変換
                        pattern = format_def['pattern'].replace('\\n', '\n')

                        if pattern in text[:100]:
                            logger.info(f"フォーマット識別: {format_def['name']} (ID: {format_def['id']})")

                            if 'hardcoded_hospital' in format_def:
                                hardcoded_name = format_def['hardcoded_hospital']
                                logger.info(f"ハードコードされた医療機関名を使用: {hardcoded_name}")
                                return {
                                    'format_id': format_def['id'],
                                    'format_name': format_def['name'],
                                    'clinic_name': hardcoded_name
                                }

                            clinic_name = ""
                            if format_def['use_rect']:
                                target_rect = (
                                    format_def['x0'], 
                                    format_def['y0'],
                                    format_def['x1'], 
                                    format_def['y1']
                                )
                                clinic_name = page.crop(target_rect).extract_text()
                            else:
                                if format_def.get('clinic_name_line') is not None:
                                    lines = text.split('\n')
                                    if len(lines) >= abs(format_def['clinic_name_line']):
                                        clinic_name = lines[format_def['clinic_name_line']]
                            
                            # ID7とID9の場合、スペースを削除
                            if format_def['id'] == 7 or format_def['id'] == 9:
                                clinic_name_original = clinic_name
                                clinic_name = clinic_name.replace(" ", "").replace("　", "")
                                logger.info(f"スペースを削除した医療機関名: '{clinic_name_original}' -> '{clinic_name}'")
                            
                            logger.info(f"抽出された医療機関名: {clinic_name}")
                            
                            return {
                                'format_id': format_def['id'],
                                'format_name': format_def['name'],
                                'clinic_name': clinic_name
                            }
                    
                    logger.warning(f"フォーマットを識別できません: {os.path.basename(pdf_path)}")
                    return None
                else:
                    logger.warning(f"テキストを抽出できません: {os.path.basename(pdf_path)}")
                    return None
            else:
                logger.warning(f"PDFにページがありません: {os.path.basename(pdf_path)}")
                return None
    
    except Exception as e:
        logger.error(f"PDF識別中にエラー: {e}")
        return None

def find_matching_hospital(pdf_info, hospital_list):
    """PDFの情報に基づいてマッチする医療機関を探す"""
    try:
        format_id = pdf_info['format_id']
        format_name = pdf_info['format_name']
        clinic_name = pdf_info['clinic_name']

        format_key = f"{format_id}_{format_name}"

        logger.info(f"マッチング開始 - PDFから抽出: '{clinic_name}'")

        for hospital in hospital_list:
            hospital_name = hospital['hospital_name']

            logger.debug(f"  比較中: Backlog医療機関名='{hospital_name}'")

            is_match = False

            if format_id == 8 and clinic_name == '三宅村':
                is_match = clinic_name in hospital_name
                if is_match:
                    logger.info(f"三宅村薬袋の特別マッチング: '{clinic_name}' が '{hospital_name}' に含まれています")
            else:
                # スペースを除去して比較
                clinic_name_clean = clinic_name.replace(' ', '').replace('　', '')
                hospital_name_clean = hospital_name.replace(' ', '').replace('　', '')

                is_match = hospital_name_clean in clinic_name_clean

                logger.debug(f"    PDF(スペース除去): '{clinic_name_clean}'")
                logger.debug(f"    Backlog(スペース除去): '{hospital_name_clean}'")
                logger.debug(f"    マッチ結果: {is_match}")
            
            if is_match:
                logger.info(f"マッチング成功: Backlog医療機関名='{hospital_name}' <-> PDF抽出名='{clinic_name}'")

                dist_settings = hospital['distribution_settings']
                
                if format_key in dist_settings:
                    return {
                        'hospital': hospital,
                        'folder_path': dist_settings[format_key],
                        'used_setting': format_key
                    }
                elif '0_共通' in dist_settings:
                    return {
                        'hospital': hospital,
                        'folder_path': dist_settings['0_共通'],
                        'used_setting': '0_共通'
                    }
                else:
                    logger.warning(f"医療機関 {hospital_name} に適用可能な振り分け設定がありません")
                    return None
        
        logger.warning(f"PDFのクリニック名 '{clinic_name}' にマッチする医療機関が見つかりませんでした")
        logger.warning(f"登録されているBacklog医療機関一覧:")
        for hospital in hospital_list:
            logger.warning(f"  - '{hospital['hospital_name']}'")
        return None
    
    except Exception as e:
        logger.error(f"医療機関マッチング中にエラー: {e}")
        return None

def simple_should_process_file(file_path):
    """シンプルなファイル処理可否判定"""
    file_name = os.path.basename(file_path)
    
    # 基本的な除外パターンのみ
    exclude_patterns = [
        '.tmp',  # 一時ファイル拡張子
        '.crdownload',  # Chrome一時ダウンロード
        'conflicted copy',  # Dropboxの競合コピー
        'desktop.ini',  # Windowsシステムファイル
        'thumbs.db',  # Windowsサムネイルファイル
    ]
    
    # 隠しファイル（先頭が.）
    if file_name.startswith('.'):
        return False
    
    # 一時ファイル（先頭が~）
    if file_name.startswith('~'):
        return False
    
    file_name_lower = file_name.lower()
    for pattern in exclude_patterns:
        if pattern in file_name_lower:
            logger.debug(f"除外ファイル: {file_name} (パターン: {pattern})")
            return False
    
    # ファイルサイズが0の場合は除外
    try:
        if os.path.exists(file_path) and os.path.getsize(file_path) == 0:
            logger.debug(f"サイズ0のファイルを除外: {file_name}")
            return False
    except (OSError, IOError):
        return False
    
    return True

def create_debug_metadata(debug_path, error_reason, timestamp, original_path):
    """デバッグ用メタデータファイル作成"""
    try:
        metadata = {
            "timestamp": timestamp,
            "original_file": os.path.basename(original_path),
            "debug_file": os.path.basename(debug_path),
            "error_reason": error_reason,
            "file_size": os.path.getsize(debug_path),
            "system_info": {
                "python_version": sys.version,
                "platform": platform.platform(),
                "available_memory": psutil.virtual_memory().available if hasattr(psutil, 'virtual_memory') else 'unknown',
                "disk_usage": shutil.disk_usage(os.path.dirname(debug_path))._asdict()
            },
            "processing_info": {
                "watch_dir": os.path.dirname(original_path),
                "error_time": datetime.now().isoformat()
            }
        }
        
        metadata_path = debug_path.replace('.pdf', '_metadata.json')
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        logger.debug(f"メタデータファイルを作成: {metadata_path}")
        
    except Exception as e:
        logger.error(f"メタデータファイル作成中にエラー: {e}")

def handle_error_with_debug(pdf_path, error_dir, debug_dir, error_reason):
    """エラー時の二重保存処理"""
    try:
        if not os.path.exists(pdf_path):
            logger.warning(f"エラーハンドリング対象ファイルが見つかりません: {pdf_path}")
            return False
        
        base_name = os.path.basename(pdf_path)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 1. ユーザー通知用（errorフォルダ）に移動
        os.makedirs(error_dir, exist_ok=True)
        error_path = os.path.join(error_dir, base_name)
        
        # 同名ファイルが存在する場合はタイムスタンプ付与
        if os.path.exists(error_path):
            name, ext = os.path.splitext(base_name)
            error_path = os.path.join(error_dir, f"{name}_{timestamp}{ext}")
        
        shutil.move(pdf_path, error_path)
        logger.info(f"エラーファイルをユーザーフォルダに移動: {shorten_path(error_path)}")
        
        # 2. 開発者分析用（debugフォルダ）にコピー
        month_dir = os.path.join(debug_dir, datetime.now().strftime('%Y%m'))
        os.makedirs(month_dir, exist_ok=True)
        
        debug_name = f"{timestamp}_{base_name}"
        debug_path = os.path.join(month_dir, debug_name)
        shutil.copy2(error_path, debug_path)
        
        # 3. メタデータファイルの作成
        create_debug_metadata(debug_path, error_reason, timestamp, pdf_path)
        
        logger.info(f"デバッグファイルを保存: {shorten_path(debug_path)}")
        return True
        
    except Exception as e:
        logger.error(f"エラーハンドリング中にエラー: {e}")
        return False

def cleanup_old_debug_files(debug_dir, retention_months=6):
    """古いデバッグファイルの自動削除"""
    try:
        if not os.path.exists(debug_dir):
            return
        
        cutoff_date = datetime.now() - timedelta(days=retention_months * 30)
        cutoff_timestamp = cutoff_date.timestamp()
        
        deleted_count = 0
        total_size = 0
        
        for root, dirs, files in os.walk(debug_dir):
            # 月フォルダ名から判定
            month_folder = os.path.basename(root)
            if len(month_folder) == 6 and month_folder.isdigit():
                try:
                    folder_date = datetime.strptime(month_folder, '%Y%m')
                    if folder_date.timestamp() < cutoff_timestamp:
                        # フォルダ全体を削除
                        folder_size = sum(
                            os.path.getsize(os.path.join(dirpath, filename))
                            for dirpath, dirnames, filenames in os.walk(root)
                            for filename in filenames
                        )
                        
                        shutil.rmtree(root)
                        deleted_count += len(files)
                        total_size += folder_size
                        logger.info(f"古いデバッグフォルダを削除: {month_folder}")
                        continue
                        
                except ValueError:
                    pass
            
            # 個別ファイルの削除（非月フォルダ内）
            for filename in files:
                file_path = os.path.join(root, filename)
                try:
                    file_mtime = os.path.getmtime(file_path)
                    if file_mtime < cutoff_timestamp:
                        file_size = os.path.getsize(file_path)
                        os.remove(file_path)
                        deleted_count += 1
                        total_size += file_size
                        logger.debug(f"古いデバッグファイルを削除: {filename}")
                except OSError:
                    continue
        
        if deleted_count > 0:
            size_mb = total_size / (1024 * 1024)
            logger.info(f"デバッグファイルクリーンアップ完了: {deleted_count}ファイル, {size_mb:.2f}MB削除")
        else:
            logger.debug("削除対象のデバッグファイルはありませんでした")
            
    except Exception as e:
        logger.error(f"デバッグファイルクリーンアップ中にエラー: {e}")

def process_pdf_file(pdf_path, hospital_list, error_dir, debug_dir):
    """PDFファイルを処理して適切な場所に移動する（完全同期版）"""
    try:
        # ファイルの存在確認
        if not os.path.exists(pdf_path):
            logger.warning(f"処理対象ファイルが見つかりません: {pdf_path}")
            return False
        
        base_name = os.path.basename(pdf_path)
        logger.info(f"PDFファイルの処理を開始: {base_name}")
        
        # PDFのフォーマットを識別
        pdf_info = identify_pdf_format(pdf_path)
        
        if not pdf_info:
            logger.warning(f"PDFフォーマットを識別できないため処理をスキップ: {base_name}")
            handle_error_with_debug(pdf_path, error_dir, debug_dir, "フォーマット識別失敗")
            logger.info("")
            return False
        
        # クリニック名に基づいて対象の医療機関を検索
        match_result = find_matching_hospital(pdf_info, hospital_list)
        
        if not match_result:
            logger.warning(f"PDFに対応する医療機関が見つかりません: {base_name}, クリニック名: {pdf_info['clinic_name']}")
            handle_error_with_debug(pdf_path, error_dir, debug_dir, f"医療機関マッチング失敗: {pdf_info['clinic_name']}")
            logger.info("")
            return False
        
        # 移動先のディレクトリパスを取得
        dest_dir = match_result['folder_path']
        hospital_name = match_result['hospital']['hospital_name']
        used_setting = match_result['used_setting']
        
        logger.info(f"振り分け先: {hospital_name} -> {shorten_path(dest_dir)} (設定: {used_setting})")
        
        # ディレクトリが存在しなければ作成
        os.makedirs(dest_dir, exist_ok=True)
        
        # 移動先のファイルパス
        dest_path = os.path.join(dest_dir, base_name)
        
        # 同名ファイルが存在する場合はタイムスタンプを付加
        if os.path.exists(dest_path):
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            name, ext = os.path.splitext(base_name)
            dest_path = os.path.join(dest_dir, f"{name}_{timestamp}{ext}")
            logger.info(f"同名ファイル検出のためタイムスタンプ付与: {os.path.basename(dest_path)}")
        
        # ファイル移動実行
        shutil.move(pdf_path, dest_path)
        logger.info(f"ファイルを移動しました: {base_name} -> {shorten_path(dest_path)}")
        
        # 移動成功の検証
        if not os.path.exists(dest_path):
            logger.error(f"移動後の検証に失敗: {dest_path}")
            return False
        
        if os.path.exists(pdf_path):
            logger.error(f"元ファイルが残存しています: {pdf_path}")
            return False
        
        logger.info(f"PDFファイルの処理が完了しました: {base_name}")
        logger.info("")
        
        return True
    
    except Exception as e:
        logger.error(f"PDFファイル処理中にエラー: {e}")
        logger.exception("スタックトレース:")
        
        # エラー時はデバッグフォルダに保存
        try:
            if os.path.exists(pdf_path):
                handle_error_with_debug(pdf_path, error_dir, debug_dir, f"処理中エラー: {str(e)}")
        except Exception as move_err:
            logger.error(f"エラーハンドリング中にエラー: {move_err}")
        
        logger.info("")
        return False

class FinalSyncPDFHandler(FileSystemEventHandler):
    """完全同期版PDFファイル監視ハンドラ（重複判定なし）"""
    
    def __init__(self, hospital_list, error_dir, debug_dir):
        self.hospital_list = hospital_list
        self.error_dir = error_dir
        self.debug_dir = debug_dir
        # 重複判定機能を完全に削除
        
    def on_created(self, event):
        """ファイル作成イベント"""
        if event.is_directory:
            return
            
        file_path = event.src_path
        
        if not simple_should_process_file(file_path):
            return
            
        if file_path.lower().endswith('.pdf'):
            self._process_file_immediately(file_path)
    
    def on_moved(self, event):
        """ファイル移動イベント"""
        if event.is_directory:
            return
            
        dest_path = event.dest_path
        if dest_path.lower().endswith('.pdf') and simple_should_process_file(dest_path):
            self._process_file_immediately(dest_path)
    
    def _process_file_immediately(self, file_path):
        """ファイル即座処理（重複判定なし）"""
        try:
            # ファイルの実際の存在確認
            if not os.path.exists(file_path):
                logger.debug(f"ファイルが存在しません: {os.path.basename(file_path)}")
                return
            
            # 重複判定を完全に削除
            # 業務上、同じファイル名の再投入は正常な動作として処理
            
            # 短時間の安定化待機
            time.sleep(2)
            
            # ファイルの安定性チェック
            if not self._is_file_stable(file_path):
                logger.debug(f"ファイルが不安定のため処理スキップ: {os.path.basename(file_path)}")
                return
            
            logger.info(f"新しいPDFファイルを検出: {os.path.basename(file_path)}")
            
            # PDFファイル処理（常に実行）
            process_pdf_file(file_path, self.hospital_list, self.error_dir, self.debug_dir)
                
        except Exception as e:
            logger.error(f"ファイル処理中にエラー: {e}")
    
    def _is_file_stable(self, file_path):
        """ファイル安定性チェック"""
        try:
            if not os.path.exists(file_path):
                return False
            
            initial_size = os.path.getsize(file_path)
            if initial_size == 0:
                return False
            
            # 1秒待機して再チェック
            time.sleep(1)
            
            if not os.path.exists(file_path):
                return False
            
            final_size = os.path.getsize(file_path)
            return initial_size == final_size
            
        except Exception:
            return False

class GracefulKiller:
    """優雅な終了処理（完全同期版）"""
    def __init__(self):
        self.kill_now = False
        
        # シグナルハンドラの設定
        if os.name != 'nt':  # Unix系OS
            signal.signal(signal.SIGINT, self._handle_signal)
            signal.signal(signal.SIGTERM, self._handle_signal)
        else:  # Windows
            signal.signal(signal.SIGINT, self._handle_signal)
            try:
                signal.signal(signal.SIGBREAK, self._handle_signal)
            except AttributeError:
                pass
    
    def _handle_signal(self, signum, frame):
        logger.info(f"終了シグナルを受信しました (シグナル: {signum})")
        self.kill_now = True

def setup_final_sync_file_watcher(watch_dir, hospital_list, error_dir, debug_dir):
    """完全同期版ファイル監視の設定"""
    logger.info("完全同期版ファイル監視を設定します（重複判定なし）")
    event_handler = FinalSyncPDFHandler(hospital_list, error_dir, debug_dir)
    observer = Observer()
    observer.schedule(event_handler, watch_dir, recursive=False)
    return observer

def process_existing_files_sync(watch_dir, hospital_list, error_dir, debug_dir):
    """既存ファイルの同期処理"""
    logger.info("既存ファイルの処理を開始します")
    try:
        existing_files = []
        for f in os.listdir(watch_dir):
            file_path = os.path.join(watch_dir, f)
            if os.path.isfile(file_path) and f.lower().endswith('.pdf'):
                logger.info(f"PDFファイル発見: {f}")
                
                # シンプルな除外チェック
                if simple_should_process_file(file_path):
                    existing_files.append(file_path)
                    logger.info(f"  → 処理対象に追加: {f}")
                else:
                    logger.info(f"  → 除外: {f}")
        
        if existing_files:
            logger.info(f"既存のPDFファイル {len(existing_files)} 件を順次処理します")
            
            # 1つずつ順番に処理
            for i, pdf_file in enumerate(existing_files, 1):
                logger.info(f"[{i}/{len(existing_files)}] 処理開始: {os.path.basename(pdf_file)}")
                success = process_pdf_file(pdf_file, hospital_list, error_dir, debug_dir)
                if success:
                    logger.info(f"[{i}/{len(existing_files)}] 処理完了: {os.path.basename(pdf_file)}")
                else:
                    logger.error(f"[{i}/{len(existing_files)}] 処理失敗: {os.path.basename(pdf_file)}")
        else:
            logger.info("処理対象の既存ファイルはありませんでした")
            
    except Exception as e:
        logger.error(f"既存ファイル処理中にエラー: {e}")
        logger.exception("詳細:")

def run_pribot_final_sync(hospital_list, folder_settings):
    """PriBot のメイン実行ループ（完全同期版）"""
    try:
        # 監視対象フォルダの設定
        watch_dir = folder_settings['watch_dir']
        error_dir = folder_settings['error_dir']
        debug_dir = folder_settings['debug_dir']
        
        # 監視フォルダが存在しなければ作成
        os.makedirs(watch_dir, exist_ok=True)
        os.makedirs(error_dir, exist_ok=True)
        os.makedirs(debug_dir, exist_ok=True)
        
        logger.info(f"PriBot 監視フォルダ: {watch_dir}")
        logger.info(f"PriBot エラーフォルダ: {error_dir}")
        logger.info(f"PriBot デバッグフォルダ: {debug_dir}")
        logger.info(f"PriBot 監視対象の医療機関数: {len(hospital_list)}")
        
        # デバッグファイルの自動クリーンアップ
        logger.info("デバッグファイルのクリーンアップを実行します")
        cleanup_old_debug_files(debug_dir, retention_months=6)
        
        # 既存ファイルの処理（同期）
        process_existing_files_sync(watch_dir, hospital_list, error_dir, debug_dir)
        
        # ファイル監視の開始
        observer = setup_final_sync_file_watcher(watch_dir, hospital_list, error_dir, debug_dir)
        observer.start()
        logger.info("完全同期版ファイル監視を開始しました（重複判定なし）")
        
        # 優雅な終了処理の設定
        killer = GracefulKiller()
        
        # メインループ（完全同期版）
        loop_count = 0
        try:
            while not killer.kill_now:
                time.sleep(10)  # 10秒間隔
                loop_count += 1
                
                # 6回に1回（1分に1回）状態をログ出力
                if loop_count % 6 == 0:
                    logger.info(f"監視継続中... (経過時間: {loop_count}分)")
                    
                    # 監視フォルダの状態確認
                    try:
                        current_files = [f for f in os.listdir(watch_dir) 
                                       if f.lower().endswith('.pdf')]
                        if current_files:
                            logger.info(f"監視フォルダ内PDFファイル: {len(current_files)}件")
                            
                            # 5件以上残っている場合は警告
                            if len(current_files) >= 5:
                                logger.warning(f"監視フォルダに多数のファイルが残存: {len(current_files)}件")
                                
                    except Exception as e:
                        logger.error(f"監視フォルダ確認エラー: {e}")
                        
        except KeyboardInterrupt:
            logger.info("キーボード割り込みを検知しました")
        
        # 終了処理
        observer.stop()
        observer.join()
        logger.info("完全同期版ファイル監視を終了しました")
        
    except Exception as e:
        logger.error(f"PriBot 実行中にエラー: {e}")
        logger.exception("スタックトレース:")

def main():
    """メイン関数（完全同期版）"""
    try:
        logger.info("PriBot (完全同期版・重複判定なし) を開始します")
        config = load_config()
        if config is None:
            logger.error("設定の読み込みに失敗しました")
            return

        # Backlogからフォルダ設定を取得
        folder_settings = get_folder_settings(config)
        
        # Backlogから医療機関情報を取得
        hospital_list = get_hospital_info(config)
        if not hospital_list:
            logger.warning("医療機関情報が設定されていません。テスト用に仮の医療機関を作成します。")
            
            # テスト用のディレクトリパス
            test_dir = os.path.join(folder_settings["watch_dir"], "../テスト振り分け先")
            os.makedirs(test_dir, exist_ok=True)
            
            # テスト用のダミー医療機関を作成
            hospital_list = [{
                "hospital_name": "テスト医療機関",
                "issue_key": "TEST-0",
                "team": "テストチーム",
                "distribution_settings": {
                    "0_共通": test_dir
                },
                "system_type": 'PriBot'
            }]
            logger.info(f"テスト用医療機関を作成しました: {hospital_list[0]['hospital_name']}")
            
        run_pribot_final_sync(hospital_list, folder_settings)

    except Exception as e:
        logger.error(f"予期せぬエラーが発生しました: {e}")
        logger.exception("スタックトレース:")

if __name__ == "__main__":
    # シングルトンチェック
    singleton = PriBotSingleton()
    if not singleton.acquire_lock():
        print("PriBotは既に実行中です。先に終了してから起動してください。")
        sys.exit(1)
    
    try:
        main()
        
    except KeyboardInterrupt:
        logger.info("キーボード割り込みを検知しました")
    except Exception as e:
        logger.error(f"予期せぬエラー: {e}")
    finally:
        singleton.release_lock()
        logger.info("PriBot (完全同期版・重複判定なし) を終了しました")