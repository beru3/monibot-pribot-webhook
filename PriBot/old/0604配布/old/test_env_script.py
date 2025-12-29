#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import platform
import psutil
import logging
import configparser
import requests
from datetime import datetime

# テスト用のプロジェクトルート設定
project_root = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(project_root, "config.ini")
LOG_DIR = os.path.join(project_root, "log")

# ログディレクトリが存在しない場合は作成
os.makedirs(LOG_DIR, exist_ok=True)

def setup_test_logger():
    """テスト用ロガーを設定する"""
    logger = logging.getLogger('pribot_test')
    
    # 既存のハンドラをクリア
    if logger.handlers:
        for handler in logger.handlers:
            logger.removeHandler(handler)
    
    logger.setLevel(logging.INFO)
    
    # ログファイル名（テスト専用）
    current_time = datetime.now()
    log_file = os.path.join(LOG_DIR, f"{current_time.strftime('%Y%m%d_%H%M%S')}_test.log")
    
    # ファイルハンドラー
    file_handler = logging.FileHandler(log_file, encoding='utf-8', mode='w')
    file_handler.setLevel(logging.INFO)
    
    # コンソールハンドラー
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # シンプルなフォーマッター
    class TestFormatter(logging.Formatter):
        GREEN = '\033[92m'  # 成功
        RED = '\033[91m'    # 失敗
        YELLOW = '\033[93m' # 警告
        BLUE = '\033[94m'   # 情報
        RESET = '\033[0m'   # リセット
        
        def __init__(self, use_colors=True):
            super().__init__()
            self.use_colors = use_colors
        
        def format(self, record):
            log_fmt = '%(asctime)s - [TEST] - %(levelname)s - %(message)s'
            
            if self.use_colors:
                if record.levelno == logging.INFO:
                    if '✅' in record.getMessage() or 'SUCCESS' in record.getMessage():
                        log_fmt = f'{self.GREEN}{log_fmt}{self.RESET}'
                    elif '❌' in record.getMessage() or 'ERROR' in record.getMessage():
                        log_fmt = f'{self.RED}{log_fmt}{self.RESET}'
                    elif '⚠️' in record.getMessage() or 'WARNING' in record.getMessage():
                        log_fmt = f'{self.YELLOW}{log_fmt}{self.RESET}'
                    else:
                        log_fmt = f'{self.BLUE}{log_fmt}{self.RESET}'
                elif record.levelno == logging.WARNING:
                    log_fmt = f'{self.YELLOW}{log_fmt}{self.RESET}'
                elif record.levelno == logging.ERROR:
                    log_fmt = f'{self.RED}{log_fmt}{self.RESET}'
            
            formatter = logging.Formatter(log_fmt)
            return formatter.format(record)
    
    # フォーマッタを適用
    console_formatter = TestFormatter(use_colors=True)
    file_formatter = TestFormatter(use_colors=False)

    file_handler.setFormatter(file_formatter)
    console_handler.setFormatter(console_formatter)
    
    # ハンドラーの追加
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# ロガー初期化
logger = setup_test_logger()

def test_python_environment():
    """Python環境のテスト"""
    logger.info("=" * 60)
    logger.info("Python環境テスト開始")
    logger.info("=" * 60)
    
    try:
        # Python基本情報
        logger.info(f"✅ Python バージョン: {sys.version}")
        logger.info(f"✅ Python 実行パス: {sys.executable}")
        logger.info(f"✅ プラットフォーム: {platform.platform()}")
        logger.info(f"✅ CPU アーキテクチャ: {platform.machine()}")
        logger.info(f"✅ プロセッサ: {platform.processor()}")
        
        # メモリ情報
        memory = psutil.virtual_memory()
        logger.info(f"✅ 総メモリ: {memory.total / (1024**3):.2f} GB")
        logger.info(f"✅ 利用可能メモリ: {memory.available / (1024**3):.2f} GB")
        logger.info(f"✅ メモリ使用率: {memory.percent:.1f}%")
        
        # ディスク情報
        disk = psutil.disk_usage(project_root)
        logger.info(f"✅ 総ディスク容量: {disk.total / (1024**3):.2f} GB")
        logger.info(f"✅ 利用可能容量: {disk.free / (1024**3):.2f} GB")
        logger.info(f"✅ ディスク使用率: {(disk.used / disk.total) * 100:.1f}%")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Python環境テストでエラー: {e}")
        return False

def test_module_imports():
    """必要なモジュールのインポートテスト"""
    logger.info("=" * 60)
    logger.info("モジュールインポートテスト開始")
    logger.info("=" * 60)
    
    modules_to_test = [
        ('os', 'os'),
        ('sys', 'sys'),
        ('time', 'time'),
        ('json', 'json'),
        ('shutil', 'shutil'),
        ('logging', 'logging'),
        ('requests', 'requests'),
        ('configparser', 'configparser'),
        ('traceback', 'traceback'),
        ('platform', 'platform'),
        ('psutil', 'psutil'),
        ('datetime', 'datetime'),
        ('pdfplumber', 'pdfplumber'),
        ('watchdog.observers', 'watchdog.observers'),
        ('watchdog.events', 'watchdog.events')
    ]
    
    success_count = 0
    total_count = len(modules_to_test)
    
    for module_name, import_name in modules_to_test:
        try:
            __import__(import_name)
            logger.info(f"✅ {module_name}: インポート成功")
            success_count += 1
        except ImportError as e:
            logger.error(f"❌ {module_name}: インポート失敗 - {e}")
        except Exception as e:
            logger.error(f"❌ {module_name}: 予期しないエラー - {e}")
    
    logger.info(f"インポートテスト結果: {success_count}/{total_count} モジュール成功")
    
    return success_count == total_count

def test_config_file():
    """設定ファイルのテスト"""
    logger.info("=" * 60)
    logger.info("設定ファイルテスト開始")
    logger.info("=" * 60)
    
    try:
        if not os.path.exists(CONFIG_PATH):
            logger.error(f"❌ 設定ファイルが見つかりません: {CONFIG_PATH}")
            return False
        
        logger.info(f"✅ 設定ファイル存在確認: {CONFIG_PATH}")
        
        config = configparser.ConfigParser()
        config.read(CONFIG_PATH, encoding='utf-8')
        
        # 必要なセクションの確認
        required_sections = ['backlog']
        for section in required_sections:
            if config.has_section(section):
                logger.info(f"✅ セクション '{section}' 存在確認")
            else:
                logger.error(f"❌ セクション '{section}' が見つかりません")
                return False
        
        # 必要なキーの確認
        required_keys = {
            'backlog': ['space_name', 'api_key', 'pribot_project_id']
        }
        
        for section, keys in required_keys.items():
            for key in keys:
                if config.has_option(section, key):
                    value = config.get(section, key)
                    if value.strip():
                        logger.info(f"✅ 設定項目 '{section}.{key}' 設定済み")
                    else:
                        logger.warning(f"⚠️ 設定項目 '{section}.{key}' が空です")
                else:
                    logger.error(f"❌ 設定項目 '{section}.{key}' が見つかりません")
                    return False
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 設定ファイルテストでエラー: {e}")
        return False

def test_backlog_api():
    """Backlog API接続テスト"""
    logger.info("=" * 60)
    logger.info("Backlog API接続テスト開始")
    logger.info("=" * 60)
    
    try:
        config = configparser.ConfigParser()
        config.read(CONFIG_PATH, encoding='utf-8')
        
        space_name = config['backlog']['space_name']
        api_key = config['backlog']['api_key']
        project_id = config['backlog']['pribot_project_id']
        
        logger.info(f"スペース名: {space_name}")
        logger.info(f"プロジェクトID: {project_id}")
        
        # プロジェクト情報取得テスト
        base_url = f"https://{space_name}.backlog.com/api/v2"
        project_endpoint = f"{base_url}/projects/{project_id}"
        
        params = {"apiKey": api_key}
        
        logger.info("プロジェクト情報を取得中...")
        response = requests.get(project_endpoint, params=params, timeout=10)
        
        if response.status_code == 200:
            project_info = response.json()
            logger.info(f"✅ プロジェクト情報取得成功")
            logger.info(f"  プロジェクト名: {project_info.get('name', '不明')}")
            logger.info(f"  プロジェクトキー: {project_info.get('projectKey', '不明')}")
        else:
            logger.error(f"❌ プロジェクト情報取得失敗: ステータスコード {response.status_code}")
            logger.error(f"  エラー内容: {response.text}")
            return False
        
        # 課題一覧取得テスト
        issues_endpoint = f"{base_url}/issues"
        issue_params = {
            "apiKey": api_key,
            "projectId[]": project_id,
            "count": 5  # テスト用に5件のみ
        }
        
        logger.info("課題一覧を取得中...")
        response = requests.get(issues_endpoint, params=issue_params, timeout=10)
        
        if response.status_code == 200:
            issues = response.json()
            logger.info(f"✅ 課題一覧取得成功: {len(issues)}件")
            
            # 課題タイプの確認
            issue_types = set()
            for issue in issues:
                if issue.get('issueType'):
                    issue_types.add(issue['issueType'].get('name', '不明'))
            
            logger.info(f"  課題タイプ: {', '.join(issue_types)}")
            
        else:
            logger.error(f"❌ 課題一覧取得失敗: ステータスコード {response.status_code}")
            logger.error(f"  エラー内容: {response.text}")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Backlog API接続テストでエラー: {e}")
        return False

def test_file_operations():
    """ファイル操作テスト"""
    logger.info("=" * 60)
    logger.info("ファイル操作テスト開始")
    logger.info("=" * 60)
    
    try:
        # テスト用ディレクトリの作成
        test_dir = os.path.join(project_root, "test_temp")
        os.makedirs(test_dir, exist_ok=True)
        logger.info(f"✅ テストディレクトリ作成: {test_dir}")
        
        # ファイル作成テスト
        test_file = os.path.join(test_dir, "test_file.txt")
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write("これはテストファイルです。\nテスト日時: " + datetime.now().isoformat())
        logger.info(f"✅ ファイル作成成功: {test_file}")
        
        # ファイル読み取りテスト
        with open(test_file, 'r', encoding='utf-8') as f:
            content = f.read()
        logger.info(f"✅ ファイル読み取り成功: {len(content)}文字")
        
        # ファイルコピーテスト
        import shutil
        copy_file = os.path.join(test_dir, "test_file_copy.txt")
        shutil.copy2(test_file, copy_file)
        logger.info(f"✅ ファイルコピー成功: {copy_file}")
        
        # ファイル移動テスト
        move_file = os.path.join(test_dir, "test_file_moved.txt")
        shutil.move(copy_file, move_file)
        logger.info(f"✅ ファイル移動成功: {move_file}")
        
        # ファイル削除テスト
        os.remove(test_file)
        os.remove(move_file)
        logger.info(f"✅ ファイル削除成功")
        
        # ディレクトリ削除テスト
        os.rmdir(test_dir)
        logger.info(f"✅ ディレクトリ削除成功")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ ファイル操作テストでエラー: {e}")
        return False

def test_process_info():
    """プロセス情報テスト"""
    logger.info("=" * 60)
    logger.info("プロセス情報テスト開始")
    logger.info("=" * 60)
    
    try:
        # 現在のプロセス情報
        current_pid = os.getpid()
        logger.info(f"✅ 現在のプロセスID: {current_pid}")
        
        # psutilを使用したプロセス情報
        process = psutil.Process(current_pid)
        logger.info(f"✅ プロセス名: {process.name()}")
        logger.info(f"✅ プロセス開始時刻: {datetime.fromtimestamp(process.create_time())}")
        logger.info(f"✅ メモリ使用量: {process.memory_info().rss / (1024*1024):.2f} MB")
        logger.info(f"✅ CPU使用率: {process.cpu_percent()}%")
        
        # 親プロセス情報
        try:
            parent = process.parent()
            if parent:
                logger.info(f"✅ 親プロセス: {parent.name()} (PID: {parent.pid})")
            else:
                logger.info("✅ 親プロセス: なし")
        except:
            logger.info("⚠️ 親プロセス情報取得不可")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ プロセス情報テストでエラー: {e}")
        return False

def test_network_connectivity():
    """ネットワーク接続テスト"""
    logger.info("=" * 60)
    logger.info("ネットワーク接続テスト開始")
    logger.info("=" * 60)
    
    test_urls = [
        "https://www.google.com",
        "https://httpbin.org/get"
    ]
    
    success_count = 0
    
    for url in test_urls:
        try:
            logger.info(f"接続テスト: {url}")
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                logger.info(f"✅ 接続成功: {url} (ステータス: {response.status_code})")
                success_count += 1
            else:
                logger.warning(f"⚠️ 接続失敗: {url} (ステータス: {response.status_code})")
        except Exception as e:
            logger.error(f"❌ 接続エラー: {url} - {e}")
    
    logger.info(f"ネットワークテスト結果: {success_count}/{len(test_urls)} 成功")
    return success_count > 0

def run_comprehensive_test():
    """包括的なテストの実行"""
    logger.info("🚀 PriBot本番環境テスト開始")
    logger.info(f"📅 テスト実行日時: {datetime.now().strftime('%Y年%m月%d日 %H時%M分%S秒')}")
    logger.info(f"📁 プロジェクトルート: {project_root}")
    
    test_results = {}
    
    # 各テストの実行
    test_functions = [
        ("Python環境", test_python_environment),
        ("モジュールインポート", test_module_imports),
        ("設定ファイル", test_config_file),
        ("Backlog API", test_backlog_api),
        ("ファイル操作", test_file_operations),
        ("プロセス情報", test_process_info),
        ("ネットワーク接続", test_network_connectivity)
    ]
    
    for test_name, test_func in test_functions:
        logger.info("")
        try:
            result = test_func()
            test_results[test_name] = result
            if result:
                logger.info(f"✅ {test_name}テスト: 成功")
            else:
                logger.error(f"❌ {test_name}テスト: 失敗")
        except Exception as e:
            logger.error(f"❌ {test_name}テストで予期しないエラー: {e}")
            test_results[test_name] = False
    
    # 結果サマリー
    logger.info("")
    logger.info("=" * 60)
    logger.info("テスト結果サマリー")
    logger.info("=" * 60)
    
    passed_tests = sum(1 for result in test_results.values() if result)
    total_tests = len(test_results)
    
    for test_name, result in test_results.items():
        status = "✅ 成功" if result else "❌ 失敗"
        logger.info(f"{test_name}: {status}")
    
    logger.info("")
    logger.info(f"総合結果: {passed_tests}/{total_tests} テスト成功")
    
    if passed_tests == total_tests:
        logger.info("🎉 すべてのテストが成功しました！本番環境は正常です。")
        return True
    else:
        logger.error(f"⚠️ {total_tests - passed_tests}個のテストが失敗しました。問題を確認してください。")
        return False

def main():
    """メイン関数"""
    try:
        # テスト開始のお知らせ
        print("PriBot本番環境テストを開始します...")
        time.sleep(1)
        
        # 包括的なテストの実行
        success = run_comprehensive_test()
        
        # 終了処理
        logger.info("")
        logger.info("=" * 60)
        if success:
            logger.info("🎯 テスト完了: 本番環境は正常に動作可能です")
            logger.info("✅ PriBot新バージョンの展開準備が整いました")
        else:
            logger.error("⚠️ テスト完了: 問題が検出されました")
            logger.error("❌ 問題を解決してから新バージョンを展開してください")
        
        logger.info("=" * 60)
        
        # 5秒待機してから終了
        logger.info("5秒後にテストを終了します...")
        time.sleep(5)
        
        return 0 if success else 1
        
    except KeyboardInterrupt:
        logger.warning("⚠️ テストがユーザーによって中断されました")
        return 1
    except Exception as e:
        logger.error(f"❌ 予期しないエラーが発生しました: {e}")
        import traceback
        logger.error(f"詳細: {traceback.format_exc()}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)