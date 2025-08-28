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
from datetime import datetime
import asyncio
import pdfplumber
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# プロジェクトルートと設定パスを明示的に指定
project_root = os.path.dirname(os.path.abspath(__file__))  # プロジェクトルートのディレクトリを取得する（現在のスクリプトと同じディレクトリ）
CONFIG_PATH = os.path.join(project_root, "config.ini")  # config.iniはプロジェクトルートにある
LOG_DIR = os.path.join(project_root, "log")


# ログディレクトリが存在しない場合は作成
os.makedirs(LOG_DIR, exist_ok=True)

# 日時ベースのログファイル名を生成
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
    
    # pdfplumberの余計なログを抑制
    logging.getLogger('pdfminer').setLevel(logging.ERROR)
    logging.getLogger('PIL').setLevel(logging.ERROR)
    
    # 他の外部ライブラリのログレベルも調整
    logging.getLogger('watchdog').setLevel(logging.WARNING)
    
    # ログファイル名（日付ベース）
    log_file = get_log_filename()
    
    # ファイルが既に存在するかチェック
    file_exists = os.path.exists(log_file)
    
    # ファイルハンドラー（追記モード）
    file_handler = logging.FileHandler(log_file, encoding='utf-8', mode='a')
    file_handler.setLevel(logging.INFO)
    
    # コンソールハンドラー
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # カスタムフォーマッター（成功/失敗を視認しやすく）
    class CustomFormatter(logging.Formatter):
        """カスタムフォーマッタ（成功/失敗を視認しやすくする）"""
        
        # ANSIエスケープシーケンス（色付け）
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
            # 基本フォーマット
            log_fmt = '%(asctime)s - %(name)s - %(levelname)s - '
            
            # メッセージを取得して重複を除去
            message = record.getMessage()
            
            # 重複メッセージのチェック（最後の完了メッセージを削除）
            if "PDFファイルの処理が完了しました" in message and hasattr(record, 'duplicate_check'):
                return ""  # 重複の場合は何も出力しない
            
            # マッチングメッセージを簡略化
            if "マッチング成功" in message:
                # 「〜は〜に含まれています」を簡素化
                parts = message.split(" は ")
                if len(parts) > 1:
                    hospital_name = parts[0].replace("マッチング成功: ", "")
                    message = f"マッチング成功: {hospital_name}"
                    record.args = ()
                    record.msg = message
            
            # レベルに応じた色分け（コンソール出力の場合のみ）
            if self.use_colors:
                if record.levelno == logging.INFO:
                    if 'コピーしました' in message or '成功' in message:
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
                    if 'コピーしました' in message or '成功' in message:
                        log_fmt = f'{log_fmt}[成功] %(message)s'
                    else:
                        log_fmt = f'{log_fmt}%(message)s'
                elif record.levelno == logging.WARNING:
                    log_fmt = f'{log_fmt}[警告] %(message)s'
                elif record.levelno == logging.ERROR:
                    log_fmt = f'{log_fmt}[エラー] %(message)s'

            # 重複するタグを削除 ([成功]が2回表示されるのを防止)
            message = record.getMessage()
            if '[成功]' in message:
                message = message.replace('[成功]', '')
                record.args = ()
                record.msg = message
                
            # パスの短縮処理
            if 'パス' in message or 'フォルダ' in message or '->' in message:
                parts = message.split(' -> ')
                if len(parts) > 1:
                    # コピー先/移動先のパスを短縮
                    message = f"{parts[0]} -> {shorten_path(parts[1])}"
                    record.args = ()
                    record.msg = message
                    
            # フォルダパスの短縮
            if 'フォルダパス:' in message:
                parts = message.split('フォルダパス:')
                if len(parts) > 1:
                    new_message = f"{parts[0]}フォルダパス: {shorten_path(parts[1].strip())}"
                    record.args = ()
                    record.msg = new_message
            
            # 削除メッセージの短縮
            if '元ファイルを削除しました:' in message:
                parts = message.split('元ファイルを削除しました:')
                if len(parts) > 1:
                    new_message = f"元ファイルを削除しました: {shorten_path(parts[1].strip())}"
                    record.args = ()
                    record.msg = new_message
                
            formatter = logging.Formatter(log_fmt)
            return formatter.format(record)
        
    # フォーマッタを適用
    console_formatter = CustomFormatter(use_colors=True)  # コンソール用（色あり）
    file_formatter = CustomFormatter(use_colors=False)    # ファイル用（色なし）

    file_handler.setFormatter(file_formatter)
    console_handler.setFormatter(console_formatter)
    
    # ハンドラーの追加
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # 新しいログファイルの場合、ヘッダー情報を記録
    if not file_exists:
        logger.info("====== PriBot ログセッション開始 ======")
        
    return logger

# ロガー初期化
logger = setup_logger()

# 設定ファイルを読み込む関数を修正
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

# フォーマット定義（test_pdfplumber.pyより移植）
FORMAT_DEFINITIONS = [
    {'id': 1, 'name': '診療費請求書兼領収書(縦)', 'page': 1, 'line': 1, 'pattern': '診療費請求書兼領収書\n診療日', 'use_rect': True, 'x0': 0, 'y0': 440, 'x1': 400, 'y1': 460},
    {'id': 2, 'name': '診療費請求書兼領収書(控え付き)', 'page': 1, 'line': 1, 'pattern': '診療費請求書兼領収書\nNo.', 'use_rect': True, 'x0': 45, 'y0': 375, 'x1': 155, 'y1': 395},
    {'id': 3, 'name': '診療費請求書兼領収書(横)', 'page': 1, 'line': 1, 'pattern': '診療費請求書兼領収書\n患者番号', 'use_rect': True, 'x0': 300, 'y0': 140, 'x1': 530, 'y1': 150},
    {'id': 4, 'name': '診療費明細書', 'page': 1, 'line': 1, 'pattern': '診療費明細書', 'use_rect': True, 'x0': 200, 'y0': 80, 'x1': 560, 'y1': 90},
    {'id': 5, 'name': '処方箋', 'page': 1, 'line': 1, 'pattern': '処 方 箋', 'use_rect': True, 'x0': 260, 'y0': 90, 'x1': 420, 'y1': 100},
    {'id': 6, 'name': 'お薬手帳', 'page': 1, 'line': 2, 'pattern': '_処__方__日__', 'use_rect': False, "clinic_name_line": -2},
    {'id': 7, 'name': 'お薬情報', 'page': 1, 'line': 1, 'pattern': 'お薬情報（', 'use_rect': True, 'x0': 0, 'y0': 800, 'x1': 300, 'y1': 820},
    {'id': 8, 'name': '薬袋シール(三宅村)', 'page': 1, 'line': 1, 'pattern': '＊＊＊＊ 用法 ＊＊＊＊', 'use_rect': False, 'clinic_name_line': None, 'hardcoded_hospital': '三宅村'}
]


def get_custom_field_value(custom_fields, name):
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

def get_watch_and_error_folders(config):
    """Backlogから監視フォルダとエラーフォルダのパスを取得する"""
    try:
        space_name = config['backlog']['space_name']
        api_key = config['backlog']['api_key']
        project_id = config['backlog']['pribot_project_id']
        
        logger.info("Backlog APIから監視フォルダとエラーフォルダの設定を取得します")
        
        # 課題一覧を取得
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
            # デフォルト値を返す
            return {
                "watch_dir": os.path.join(project_root, 'pribot_watch'),
                "error_dir": os.path.join(project_root, 'pribot_error')
            }
        
        issues = response.json()
        settings = None
        
        # PriBot設定タイプの課題を探す
        for issue in issues:
            if issue.get('issueType') and issue['issueType'].get('name') == 'PriBot設定':
                custom_fields = issue.get('customFields', [])
                watch_dir = get_custom_field_value(custom_fields, '監視フォルダパス')
                error_dir = get_custom_field_value(custom_fields, 'エラーフォルダパス')
                
                settings = {
                    "watch_dir": watch_dir if watch_dir else os.path.join(project_root, 'pribot_watch'),
                    "error_dir": error_dir if error_dir else os.path.join(project_root, 'pribot_error')
                }
                
                logger.info(f"監視フォルダパス: {settings['watch_dir']}")
                logger.info(f"エラーフォルダパス: {settings['error_dir']}")
                break
        
        if not settings:
            logger.warning("PriBot設定が見つかりませんでした。デフォルト値を使用します。")
            settings = {
                "watch_dir": os.path.join(project_root, 'pribot_watch'),
                "error_dir": os.path.join(project_root, 'pribot_error')
            }
            logger.info(f"デフォルト監視フォルダパス: {settings['watch_dir']}")
            logger.info(f"デフォルトエラーフォルダパス: {settings['error_dir']}")
        
        # フォルダが存在するか確認し、なければ作成
        for dir_key, dir_path in settings.items():
            if not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)
                logger.info(f"{dir_key} ディレクトリを作成しました: {dir_path}")
        
        return settings
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Backlog APIリクエストエラー: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"レスポンス内容: {e.response.text}")
            
        # デフォルト値を返す
        return {
            "watch_dir": os.path.join(project_root, 'pribot_watch'),
            "error_dir": os.path.join(project_root, 'pribot_error')
        }
    except Exception as e:
        logger.error(f"フォルダ設定の取得中にエラー: {e}")
        logger.exception("スタックトレース:")
        
        # デフォルト値を返す
        return {
            "watch_dir": os.path.join(project_root, 'pribot_watch'),
            "error_dir": os.path.join(project_root, 'pribot_error')
        }

def get_hospital_info(config):
    """Backlogから医療機関情報を取得する（新仕様）"""
    try:
        space_name = config['backlog']['space_name']
        api_key = config['backlog']['api_key']
        project_id = config['backlog']['pribot_project_id']

        logger.info("Backlog APIリクエストを開始します")
        logger.debug(f"プロジェクトID: {project_id}")

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
        
        # 課題タイプの一覧をログに出力
        issue_types = set()
        for issue in issues:
            if issue.get('issueType'):
                issue_types.add(issue['issueType'].get('name', '不明'))
        logger.info(f"存在する課題タイプ: {', '.join(issue_types)}")

        # 医療機関情報を集約するためのディクショナリ（医療機関名をキーとする）
        hospital_dict = {}
        
        # スキップカウンター
        skipped_count = 0
        polling_off_count = 0
        no_settings_count = 0

        for issue in issues:
            try:
                # 課題の基本情報をログ出力
                issue_key = issue.get('issueKey', '不明')
                summary = issue.get('summary', '不明')
                issue_type = issue.get('issueType', {}).get('name', '不明')
                
                logger.debug(f"課題処理: [{issue_key}] {summary} (タイプ: {issue_type})")
                
                # 種別が「医療機関」のみを対象とし、「PriBot設定」は除外する
                if issue_type != '医療機関' or issue_type == 'PriBot設定':
                    logger.debug(f"課題 {issue_key}: 対象外のタイプのためスキップ: {issue_type}")
                    skipped_count += 1
                    continue

                # カスタムフィールドの情報を表示
                custom_fields = issue.get('customFields', [])
                logger.debug(f"課題 {issue_key}: カスタムフィールド数: {len(custom_fields)}")
                
                if len(custom_fields) > 0:
                    field_names = [field.get('name', '不明') for field in custom_fields]
                    logger.debug(f"課題 {issue_key}: カスタムフィールド名: {', '.join(field_names)}")
                
                # ポーリング設定の確認
                polling = get_custom_field_value(custom_fields, 'ポーリング')
                logger.debug(f"課題 {issue_key}: ポーリング設定値: '{polling}'")
                
                if polling != 'ON':
                    logger.debug(f"課題 {issue_key}: ポーリング設定がONではないためスキップ")
                    polling_off_count += 1
                    continue
                
                # 設定タイプ（0_共通、1_請求書など）と実際のパスを取得
                setting_type = get_custom_field_value(custom_fields, '振り分け先の設定')
                folder_path = get_custom_field_value(custom_fields, '振り分け先フォルダパス')
                
                logger.debug(f"課題 {issue_key}: 振り分け先設定: '{setting_type}', パス: '{folder_path}'")
                
                # グループ情報を取得
                team = get_custom_field_value(custom_fields, 'グループ')
                logger.debug(f"課題 {issue_key}: グループ設定: '{team}'")
                
                # 設定とパスが両方有効な場合のみ追加
                if setting_type and folder_path:
                    # 医療機関名をキーとして使用
                    if summary not in hospital_dict:
                        # 新しい医療機関の場合、初期化
                        hospital_dict[summary] = {
                            "hospital_name": summary,
                            "issue_key": issue_key,
                            "team": team,
                            "distribution_settings": {},
                            "system_type": 'PriBot'
                        }
                    
                    # この課題の振り分け設定を追加
                    hospital_dict[summary]['distribution_settings'][setting_type] = folder_path
                    logger.info(f"課題 {issue_key}: 振り分け先 '{setting_type}' = '{folder_path}'")
                else:
                    logger.warning(f"課題 {issue_key}: 振り分け先設定またはパスが不足しています")
                    no_settings_count += 1
                    continue

            except Exception as e:
                logger.error(f"課題 {issue.get('issueKey', '不明')} の処理中にエラー: {e}")
                logger.exception("スタックトレース:")
                continue
                
        # 集約したディクショナリからリストを作成
        hospital_list = list(hospital_dict.values())
       
        if not hospital_list:
            logger.warning("条件を満たす医療機関が見つかりませんでした")
            logger.info(f"スキップした課題数: {skipped_count} (タイプ不一致), {polling_off_count} (ポーリングOFF), {no_settings_count} (振り分け先なし)")
        else:
            # 医療機関ごとの振り分け設定数を出力
            for hospital in hospital_list:
                logger.info(f"PriBot 監視対象の医療機関名: {hospital['hospital_name']}, 振り分け設定数: {len(hospital['distribution_settings'])}")
                
                # 振り分け設定の詳細をデバッグ出力
                for setting_type, folder_path in hospital['distribution_settings'].items():
                    logger.debug(f"  - '{setting_type}': '{folder_path}'")
            
            logger.info(f"監視対象の医療機関数: {len(hospital_list)}, スキップした課題数: {skipped_count + polling_off_count + no_settings_count}")
        
        return hospital_list

    except requests.exceptions.RequestException as e:
        logger.error(f"Backlog APIリクエストエラー: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"レスポンス内容: {e.response.text}")
        return []
    except Exception as e:
        logger.error(f"医療機関情報の取得中にエラー: {e}")
        logger.exception("スタックトレース:")
        return []

def identify_pdf_format(pdf_path):
    """PDFファイルのフォーマットを識別する"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            # 1ページ目のみ処理（すべてのフォーマットが1ページ目で識別可能）
            if len(pdf.pages) > 0:
                page = pdf.pages[0]
                text = page.extract_text()

                if text:
                    # 各フォーマット定義に対して照合
                    for format_def in FORMAT_DEFINITIONS:
                        if format_def['pattern'] in text[:100]:
                            logger.info(f"フォーマット識別: {format_def['name']} (ID: {format_def['id']})")

                            # ハードコードされた医療機関名がある場合
                            if 'hardcoded_hospital' in format_def:
                                hardcoded_name = format_def['hardcoded_hospital']
                                logger.info(f"ハードコードされた医療機関名を使用: {hardcoded_name}")
                                return {
                                    'format_id': format_def['id'],
                                    'format_name': format_def['name'],
                                    'clinic_name': hardcoded_name
                                }

                            # 通常の医療機関名抽出処理
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
                                # テキストを改行で分割して指定行を取得
                                if format_def.get('clinic_name_line') is not None:
                                    lines = text.split('\n')
                                    if len(lines) >= abs(format_def['clinic_name_line']):
                                        clinic_name = lines[format_def['clinic_name_line']]
                            
                            # 薬情フォーマットの場合、半角スペースを削除
                            if format_def['id'] == 7:
                                clinic_name = clinic_name.replace(" ", "")
                                logger.info(f"半角スペースを削除した医療機関名: {clinic_name}")
                            
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
        logger.exception("スタックトレース:")
        return None

def find_matching_hospital(pdf_info, hospital_list):
    """PDFの情報に基づいてマッチする医療機関を探す"""
    try:
        format_id = pdf_info['format_id']
        format_name = pdf_info['format_name']
        clinic_name = pdf_info['clinic_name']
        
        # 特定フォーマット用の設定キー
        format_key = f"{format_id}_{format_name}"
        logger.debug(f"検索するフォーマットキー: '{format_key}'")
        
        # 通常の医療機関マッチング処理
        for hospital in hospital_list:
            hospital_name = hospital['hospital_name']
            
            # マッチング条件
            is_match = False
            
            # 特殊薬袋（三宅村）の場合は逆方向でもマッチングを試行
            if format_id == 8 and clinic_name == '三宅村':
                # 三宅村薬袋の場合: PDFのクリニック名が医療機関名に含まれるか
                is_match = clinic_name in hospital_name
                if is_match:
                    logger.info(f"三宅村薬袋の特別マッチング: '{clinic_name}' が '{hospital_name}' に含まれています")
            else:
                # 通常の場合: 医療機関名がPDFのクリニック名に含まれるか（従来通り）
                is_match = hospital_name in clinic_name
            
            if is_match:
                logger.info(f"マッチング成功: {hospital_name}")
                
                # 振り分け設定を取得
                dist_settings = hospital['distribution_settings']
                logger.debug(f"利用可能な振り分け設定: {list(dist_settings.keys())}")
                
                # キーのマッチングをデバッグ
                for key in dist_settings.keys():
                    logger.debug(f"振り分け設定キー: '{key}', 比較対象: '{format_key}', 一致: {key == format_key}")
                
                # 優先順位: 1. 特定フォーマット用の設定 2. 共通設定
                if format_key in dist_settings:
                    logger.debug(f"フォーマット別設定を使用: {format_key}")
                    return {
                        'hospital': hospital,
                        'folder_path': dist_settings[format_key],
                        'used_setting': format_key
                    }
                elif '0_共通' in dist_settings:
                    logger.debug(f"共通設定を使用: 0_共通")
                    return {
                        'hospital': hospital,
                        'folder_path': dist_settings['0_共通'],
                        'used_setting': '0_共通'
                    }
                else:
                    logger.warning(f"医療機関 {hospital_name} に適用可能な振り分け設定がありません")
                    return None
        
        logger.warning(f"PDFのクリニック名 '{clinic_name}' にマッチする医療機関が見つかりませんでした")
        
        # デバッグ用: 登録されている医療機関名を表示
        logger.debug(f"登録されている医療機関名一覧:")
        for hospital in hospital_list:
            logger.debug(f"  - {hospital['hospital_name']}")
        
        return None
    
    except Exception as e:
        logger.error(f"医療機関マッチング中にエラー: {e}")
        logger.exception("スタックトレース:")
        return None
    
def process_pdf_file(pdf_path, hospital_list, error_dir):
    """PDFファイルを処理して適切な場所に移動する（新仕様）"""
    try:
        # ファイル名から拡張子を除いたベース名を取得
        base_name = os.path.basename(pdf_path)
        
        # PDFのフォーマットを識別
        pdf_info = identify_pdf_format(pdf_path)
        
        if not pdf_info:
            logger.warning(f"PDFフォーマットを識別できないため処理をスキップ: {base_name}")
            # エラーディレクトリに移動
            move_to_error_dir(pdf_path, error_dir)
            
            # 処理失敗時に空白行を追加
            logger.info("")
            return False
        
        # クリニック名に基づいて対象の医療機関を検索（新ロジック）
        match_result = find_matching_hospital(pdf_info, hospital_list)
        
        if not match_result:
            logger.warning(f"PDFに対応する医療機関が見つかりません: {base_name}, クリニック名: {pdf_info['clinic_name']}")
            # エラーディレクトリに移動
            move_to_error_dir(pdf_path, error_dir)
            
            # 処理失敗時に空白行を追加
            logger.info("")
            return False
        
        # 移動先のディレクトリパスを取得
        dest_dir = match_result['folder_path']
        hospital_name = match_result['hospital']['hospital_name']
        used_setting = match_result['used_setting']
        
        logger.info(f"振り分け先: {hospital_name} -> {dest_dir} (設定: {used_setting})")
        
        # ディレクトリが存在しなければ作成
        os.makedirs(dest_dir, exist_ok=True)
        
        # 移動先のファイルパス
        dest_path = os.path.join(dest_dir, base_name)
        
        # ファイルをコピー
        shutil.copy2(pdf_path, dest_path)
        logger.info(f"ファイルをコピーしました: {base_name} -> {dest_path}")
        
        # 元のファイルを削除（オプション）
        os.remove(pdf_path)
        logger.info(f"元ファイルを削除しました: {pdf_path}")
        
        # 処理完了時に空白行を追加
        logger.info(f"PDFファイルの処理が完了しました: {base_name}")
        # 処理完了後に空白行を追加
        logger.info("")  # 空白行を追加
        
        return True
    
    except Exception as e:
        logger.error(f"PDFファイル処理中にエラー: {e}")
        logger.exception("スタックトレース:")
        
        # エラー時もエラーディレクトリに移動
        try:
            move_to_error_dir(pdf_path, error_dir)
        except Exception as move_err:
            logger.error(f"エラーディレクトリへの移動中にエラー: {move_err}")
        
        # 処理失敗時も空白行を追加
        logger.info("")  # 空白行を追加
        
        return False

def move_to_error_dir(pdf_path, error_dir):
    """PDFファイルをエラーディレクトリに移動する"""
    try:
        # ディレクトリが存在しなければ作成
        os.makedirs(error_dir, exist_ok=True)
        
        # ファイル名を取得
        base_name = os.path.basename(pdf_path)
        
        # 移動先のファイルパス
        dest_path = os.path.join(error_dir, base_name)
        
        # 同名ファイルが存在する場合はタイムスタンプを付加
        if os.path.exists(dest_path):
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            base_name_without_ext, ext = os.path.splitext(base_name)
            new_base_name = f"{base_name_without_ext}_{timestamp}{ext}"
            dest_path = os.path.join(error_dir, new_base_name)
        
        # ファイルをコピー
        shutil.copy2(pdf_path, dest_path)
        logger.info(f"ファイルをエラーディレクトリに移動しました: {base_name} -> {shorten_path(dest_path)}")
        
        # 元のファイルを削除
        os.remove(pdf_path)
        
        return True
    except Exception as e:
        logger.error(f"エラーディレクトリへの移動中にエラー: {e}")
        logger.exception("スタックトレース:")
        return False

class PDFHandler(FileSystemEventHandler):
    """ファイルシステムイベント処理用のハンドラクラス"""
    
    def __init__(self, hospital_list, error_dir):
        self.hospital_list = hospital_list
        self.error_dir = error_dir
        self.processing = set()  # 処理中のファイル追跡用
    
    def on_created(self, event):
        """ファイル作成イベントのハンドラ"""
        if event.is_directory:
            return
        
        # PDFファイルか確認
        if event.src_path.lower().endswith('.pdf'):
            self.process_new_pdf(event.src_path)
    
    def process_new_pdf(self, file_path):
        """新しいPDFファイルの処理"""
        try:
            if file_path in self.processing:
                logger.debug(f"すでに処理中のファイル: {os.path.basename(file_path)}")
                return
                    
            self.processing.add(file_path)
            
            # ファイルが完全に書き込まれるまで少し待機
            time.sleep(1)
            
            if not os.path.exists(file_path):
                logger.warning(f"ファイルが見つかりません: {file_path}")
                self.processing.remove(file_path)
                return
                    
            # ファイルのサイズが安定するまで待機
            initial_size = os.path.getsize(file_path)
            time.sleep(2)  # 2秒待機
            
            if os.path.getsize(file_path) != initial_size:
                logger.debug(f"ファイルのサイズが変化しています。処理を延期: {os.path.basename(file_path)}")
                self.processing.remove(file_path)
                return
            
            logger.info(f"新しいPDFファイルを検出: {os.path.basename(file_path)}")
            
            # PDFファイルを処理（新仕様）
            process_pdf_file(file_path, self.hospital_list, self.error_dir)
            
            # 完了メッセージは process_pdf_file 内で出力されるので
            # ここでは追加で出力しない
                    
        except Exception as e:
            logger.error(f"PDFファイル処理中にエラー: {e}")
            logger.exception("スタックトレース:")
            # 空白行でログエントリを区切る
            logger.info("")
        finally:
            # 処理済みリストから削除
            if file_path in self.processing:
                self.processing.remove(file_path)

def setup_file_watcher(watch_dir, hospital_list, error_dir):
    """ファイル監視の設定"""
    event_handler = PDFHandler(hospital_list, error_dir)
    observer = Observer()
    observer.schedule(event_handler, watch_dir, recursive=False)
    return observer

async def run_pribot(hospital_list, folder_settings, shutdown_event):
    """PriBot のメイン実行ループ（新仕様）"""
    try:
        # 監視対象フォルダの設定
        watch_dir = folder_settings['watch_dir']
        error_dir = folder_settings['error_dir']
        
        # 監視フォルダが存在しなければ作成
        os.makedirs(watch_dir, exist_ok=True)
        os.makedirs(error_dir, exist_ok=True)
        
        logger.info(f"PriBot 監視フォルダ: {watch_dir}")
        logger.info(f"PriBot エラーフォルダ: {error_dir}")
        logger.info(f"PriBot 監視対象の医療機関数: {len(hospital_list)}")
        
        # ファイル監視の開始
        observer = setup_file_watcher(watch_dir, hospital_list, error_dir)
        observer.start()
        logger.info("ファイル監視を開始しました")
        
        # 既存ファイルの処理
        existing_files = [os.path.join(watch_dir, f) for f in os.listdir(watch_dir) 
                        if os.path.isfile(os.path.join(watch_dir, f)) and f.lower().endswith('.pdf')]

        if existing_files:
            logger.info(f"既存のPDFファイル {len(existing_files)} 件を処理します")
            for pdf_file in existing_files:
                process_pdf_file(pdf_file, hospital_list, error_dir)
        
        # メインループ
        while not shutdown_event.is_set():
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
        
        # 終了処理
        observer.stop()
        observer.join()
        logger.info("ファイル監視を終了しました")
        
    except Exception as e:
        logger.error(f"PriBot 実行中にエラー: {e}")
        logger.exception("スタックトレース:")

async def main_with_shutdown(shutdown_event=None):
    """シャットダウンイベントに対応したメイン関数"""
    if shutdown_event is None:
        shutdown_event = asyncio.Event()
        
    try:
        logger.info("PriBot を開始します")
        config = load_config()
        if config is None:
            logger.error("設定の読み込みに失敗しました")
            return

        # Backlogから監視フォルダとエラーフォルダの設定を取得
        folder_settings = get_watch_and_error_folders(config)
        
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
            
        await run_pribot(hospital_list, folder_settings, shutdown_event)

    except asyncio.CancelledError:
        logger.debug("メイン処理がキャンセルされました")
    except Exception as e:
        logger.error(f"予期せぬエラーが発生しました: {e}")
        logger.exception("スタックトレース:")

if __name__ == "__main__":
    try:
        # シャットダウンイベントの作成
        shutdown_event = asyncio.Event()
        
        # シグナルハンドラの設定（Unix系OSのみ）
        if os.name != 'nt':
            import signal
            
            def signal_handler(sig, frame):
                logger.info(f"シグナル {sig} を受信しました")
                shutdown_event.set()
            
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
        
        # メイン処理の実行
        asyncio.run(main_with_shutdown(shutdown_event))
        
    except KeyboardInterrupt:
        logger.info("キーボード割り込みを検知しました")
        # asyncioループが終了した後のクリーンアップ処理がある場合はここに追加