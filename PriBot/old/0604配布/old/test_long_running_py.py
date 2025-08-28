#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import signal
import platform
import psutil
import logging
from datetime import datetime

# テスト用のプロジェクトルート設定
project_root = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(project_root, "log")

# ログディレクトリが存在しない場合は作成
os.makedirs(LOG_DIR, exist_ok=True)

class TestSingleton:
    """テスト用単一インスタンス制御"""
    
    def __init__(self, lock_file="pribot_test.lock"):
        self.lock_file = os.path.join(project_root, lock_file)
        self.lock_acquired = False
        
    def acquire_lock(self):
        """ロック取得"""
        if os.path.exists(self.lock_file):
            with open(self.lock_file, 'r') as f:
                existing_pid = f.read().strip()
            
            if self.is_process_running(existing_pid):
                print(f"テストプロセスは既に実行中です (PID: {existing_pid})")
                return False
            else:
                # 古いロックファイルを削除
                os.remove(self.lock_file)
        
        # 新しいロックファイルを作成
        with open(self.lock_file, 'w') as f:
            f.write(str(os.getpid()))
        
        self.lock_acquired = True
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
            return False

def setup_test_logger():
    """テスト用ロガーを設定する"""
    logger = logging.getLogger('pribot_stop_test')
    
    # 既存のハンドラをクリア
    if logger.handlers:
        for handler in logger.handlers:
            logger.removeHandler(handler)
    
    logger.setLevel(logging.INFO)
    
    # ログファイル名（テスト専用）
    current_time = datetime.now()
    log_file = os.path.join(LOG_DIR, f"{current_time.strftime('%Y%m%d_%H%M%S')}_stop_test.log")
    
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
            log_fmt = '%(asctime)s - [STOP_TEST] - %(levelname)s - %(message)s'
            
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

class GracefulTestKiller:
    """優雅な終了処理（テスト版）"""
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
        logger.info(f"🛑 終了シグナルを受信しました (シグナル: {signum})")
        self.kill_now = True

def run_long_running_test():
    """長時間実行テストプロセス"""
    try:
        logger.info("🚀 PriBot停止テスト用プロセスを開始します")
        logger.info(f"📅 開始日時: {datetime.now().strftime('%Y年%m月%d日 %H時%M分%S秒')}")
        logger.info(f"🆔 プロセスID: {os.getpid()}")
        logger.info(f"📁 プロジェクトルート: {project_root}")
        
        # プロセス情報の表示
        process = psutil.Process()
        logger.info(f"🖥️ プロセス名: {process.name()}")
        logger.info(f"💾 メモリ使用量: {process.memory_info().rss / (1024*1024):.2f} MB")
        
        # 親プロセス情報
        try:
            parent = process.parent()
            if parent:
                logger.info(f"👨‍👩‍👧‍👦 親プロセス: {parent.name()} (PID: {parent.pid})")
        except:
            logger.info("👨‍👩‍👧‍👦 親プロセス情報取得不可")
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("🔄 継続実行中...")
        logger.info("⏹️ 停止するには test_stop.bat を実行してください")
        logger.info("=" * 60)
        
        # 優雅な終了処理の設定
        killer = GracefulTestKiller()
        
        # メインループ
        loop_count = 0
        start_time = time.time()
        
        try:
            while not killer.kill_now:
                time.sleep(10)  # 10秒間隔
                loop_count += 1
                elapsed_time = time.time() - start_time
                
                # 6回に1回（1分に1回）状態をログ出力
                if loop_count % 6 == 0:
                    logger.info(f"⏰ 実行継続中... (経過時間: {elapsed_time/60:.1f}分)")
                    
                    # プロセス情報の更新
                    try:
                        current_memory = process.memory_info().rss / (1024*1024)
                        logger.info(f"💾 現在のメモリ使用量: {current_memory:.2f} MB")
                    except Exception as e:
                        logger.error(f"❌ プロセス情報取得エラー: {e}")
                        
                # 30回に1回（5分に1回）詳細ログ
                if loop_count % 30 == 0:
                    logger.info("")
                    logger.info("📊 詳細ステータス:")
                    logger.info(f"   実行時間: {elapsed_time/60:.1f}分")
                    logger.info(f"   ループ回数: {loop_count}")
                    logger.info(f"   現在時刻: {datetime.now().strftime('%H:%M:%S')}")
                    logger.info("")
                        
        except KeyboardInterrupt:
            logger.info("⌨️ キーボード割り込みを検知しました")
        
        # 終了処理
        logger.info("")
        logger.info("🛑 テストプロセスを終了します")
        logger.info(f"⏱️ 総実行時間: {(time.time() - start_time)/60:.1f}分")
        logger.info(f"🔄 総ループ回数: {loop_count}")
        
    except Exception as e:
        logger.error(f"❌ テスト実行中にエラー: {e}")
        import traceback
        logger.error(f"詳細: {traceback.format_exc()}")

def main():
    """メイン関数"""
    try:
        logger.info("🎯 PriBot停止テスト用プロセス開始")
        
        # 長時間実行テストの実行
        run_long_running_test()
        
        logger.info("✅ テストプロセスが正常に終了しました")
        return 0
        
    except KeyboardInterrupt:
        logger.warning("⚠️ テストがユーザーによって中断されました")
        return 1
    except Exception as e:
        logger.error(f"❌ 予期しないエラーが発生しました: {e}")
        import traceback
        logger.error(f"詳細: {traceback.format_exc()}")
        return 1

if __name__ == "__main__":
    # シングルトンチェック
    singleton = TestSingleton()
    if not singleton.acquire_lock():
        print("テストプロセスは既に実行中です。先に終了してから起動してください。")
        sys.exit(1)
    
    try:
        exit_code = main()
        
    except KeyboardInterrupt:
        logger.info("⌨️ キーボード割り込みを検知しました")
        exit_code = 1
    except Exception as e:
        logger.error(f"❌ 予期せぬエラー: {e}")
        exit_code = 1
    finally:
        singleton.release_lock()
        logger.info("🏁 PriBot停止テスト用プロセスを終了しました")
    
    sys.exit(exit_code)