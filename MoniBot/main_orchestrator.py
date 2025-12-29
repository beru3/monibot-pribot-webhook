#!/usr/bin/env python3
"""
メインオーケストレーター
各モニターシステムを統合管理する（順次ログイン処理版）
- CLIUS監視
- デジカル監視
- モバカル監視
- CLINICS監視
- 医歩監視 (新規追加)
- モバクリ監視 (新規追加)
- 紙カルテ監視
- タスク割り当て
"""

import os
import sys
import asyncio
import signal
import traceback
import configparser
from datetime import datetime, timedelta
import glob
import json

# プロジェクトルートへのパスを追加
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)

from src.utils.logger import get_logger
from src.utils.login_status import LoginStatus
from src.core import clius_monitor, digikar_monitor, movacal_monitor, clinics_monitor
from src.core import ippo_monitor, movacli_monitor  # 新規追加
from src.core import paper_monitor, task_assignment

class ProcessOrchestrator:
    def __init__(self):
        self.setup_logging()
        self.logger.info("プロセスオーケストレーターを初期化しています...")
        
        # 実行状態管理
        self.running = True
        self.shutdown_event = asyncio.Event()
        self.monitor_processes = []
        
        # ログイン状態管理
        self.clius_login_status = LoginStatus("CLIUS")
        self.digikar_login_status = LoginStatus("デジカル")
        self.movacal_login_status = LoginStatus("モバカル")
        self.clinics_login_status = LoginStatus("CLINICS")
        self.ippo_login_status = LoginStatus("医歩")  # 新規追加
        self.movacli_login_status = LoginStatus("モバクリ")  # 新規追加
        
        # PIDファイルパス
        self.pid_file = os.path.join(project_root, 'config', 'pid.txt')
        
        # Bizrobo!連携用
        self.create_bizrobo_summary_on_completion = True
        self.bizrobo_flag_dir = os.path.join(project_root, "bizrobo_flags")
        os.makedirs(self.bizrobo_flag_dir, exist_ok=True)
        
        # 設定ファイル読み込み
        self.load_intervals_from_config()
        
        # PIDファイル初期化
        self.initialize_pid_file()
        
        # シグナルハンドラの設定
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, self.handle_shutdown)

    def initialize_pid_file(self):
        """PIDファイルの初期化"""
        try:
            os.makedirs(os.path.dirname(self.pid_file), exist_ok=True)
            
            if os.path.exists(self.pid_file):
                os.remove(self.pid_file)
                self.logger.info(f"既存のPIDファイル {self.pid_file} を削除しました")
            
            with open(self.pid_file, 'w') as f:
                f.write(str(os.getpid()))
            self.logger.info(f"プロセスID {os.getpid()} を {self.pid_file} に保存しました")
            
        except Exception as e:
            self.logger.error(f"PIDファイルの初期化中にエラーが発生しました: {e}")

    def setup_logging(self):
        """オーケストレーター用のログ設定"""
        from src.utils.logger import get_logger
        self.logger = get_logger('orchestrator')

    def handle_shutdown(self, signum, frame):
        """シャットダウン処理"""
        if not self.running:
            return
            
        self.logger.info(f"シグナル {signal.Signals(signum).name} を受信しました")
        self.running = False
        
        self.remove_pid_file()
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.call_soon_threadsafe(self.shutdown_event.set)
        except Exception as e:
            self.logger.error(f"シャットダウンイベントの設定中にエラー: {e}")

    def remove_pid_file(self):
        """PIDファイルを削除する"""
        if os.path.exists(self.pid_file):
            try:
                os.remove(self.pid_file)
                self.logger.info(f"PIDファイル {self.pid_file} を削除しました")
            except Exception as e:
                self.logger.error(f"PIDファイルの削除中にエラーが発生しました: {e}")

    def load_intervals_from_config(self):
        """設定ファイルからポーリング間隔を読み込む"""
        config = configparser.ConfigParser()
        config_path = os.path.join(project_root, 'config', 'config.ini')
        
        if not os.path.exists(config_path):
            self.logger.error("config.ini が見つかりません")
            sys.exit(1)
        
        config.read(config_path, encoding='utf-8')
        
        self.task_assignment_interval = config.getint('setting', 'task_assignment_interval', fallback=5)
        self.clius_polling_interval = config.getint('setting', 'clius_polling_interval', fallback=10)
        self.digikar_polling_interval = config.getint('setting', 'digikar_polling_interval', fallback=10)
        self.movacal_polling_interval = config.getint('setting', 'movacal_polling_interval', fallback=10)
        self.clinics_polling_interval = config.getint('setting', 'clinics_polling_interval', fallback=10)
        self.ippo_polling_interval = config.getint('setting', 'ippo_polling_interval', fallback=10)  # 新規追加
        self.movacli_polling_interval = config.getint('setting', 'movacli_polling_interval', fallback=10)  # 新規追加
        self.paper_polling_interval = config.getint('setting', 'paper_polling_interval', fallback=30)
        
        self.logger.info(f"CLIUSポーリング間隔を {self.clius_polling_interval} 秒に設定しました")
        self.logger.info(f"デジカルポーリング間隔を {self.digikar_polling_interval} 秒に設定しました")
        self.logger.info(f"モバカルポーリング間隔を {self.movacal_polling_interval} 秒に設定しました")
        self.logger.info(f"CLINICSポーリング間隔を {self.clinics_polling_interval} 秒に設定しました")
        self.logger.info(f"医歩ポーリング間隔を {self.ippo_polling_interval} 秒に設定しました")  # 新規追加
        self.logger.info(f"モバクリポーリング間隔を {self.movacli_polling_interval} 秒に設定しました")  # 新規追加
        self.logger.info(f"紙カルテポーリング間隔を {self.paper_polling_interval} 秒に設定しました")

    def _create_all_systems_bizrobo_summary(self):
        """個別ログインファイルから統合判定ファイルを作成"""
        try:
            login_files = glob.glob(os.path.join(self.bizrobo_flag_dir, "*_login_status.json"))
            
            if not login_files:
                self.logger.warning("ログインステータスファイルが見つかりません")
                return
            
            total_files = len(login_files)
            failed_hospitals = []
            failed_systems = set()
            restart_needed = False
            
            for file_path in login_files:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    if not data.get('login_success', False):
                        hospital_name = data.get('hospital_name', 'Unknown')
                        system_type = data.get('system_type', 'Unknown')
                        failed_hospitals.append({
                            'hospital': hospital_name,
                            'system': system_type,
                            'error': data.get('error_message', '不明なエラー')
                        })
                        failed_systems.add(system_type)
                        restart_needed = True
                        
                except Exception as e:
                    self.logger.error(f"ファイル読み込みエラー: {file_path} - {e}")
            
            summary_data = {
                'check_time': datetime.now().isoformat(),
                'total_login_files': total_files,
                'failed_hospitals_count': len(failed_hospitals),
                'failed_hospitals': failed_hospitals,
                'failed_systems': list(failed_systems),
                'overall_status': 'ERROR' if restart_needed else 'OK',
                'restart_needed': restart_needed,
                'restart_command': 'python main_orchestrator.py'
            }
            
            summary_path = os.path.join(self.bizrobo_flag_dir, "all_systems_summary.json")
            with open(summary_path, 'w', encoding='utf-8') as f:
                json.dump(summary_data, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"統合判定ファイルを作成しました: {summary_path}")
            self.logger.info(f"全体ステータス: {summary_data['overall_status']}")
            self.logger.info(f"再起動必要: {restart_needed}")
            
        except Exception as e:
            self.logger.error(f"統合判定ファイル作成エラー: {e}")
            self.logger.debug(traceback.format_exc())

    def _create_error_bizrobo_summary(self, error_message: str):
        """エラー発生時の統合判定ファイル作成"""
        try:
            summary_data = {
                'check_time': datetime.now().isoformat(),
                'total_login_files': 0,
                'failed_hospitals_count': 0,
                'failed_hospitals': [],
                'failed_systems': [],
                'overall_status': 'CRITICAL_ERROR',
                'restart_needed': True,
                'restart_command': 'python main_orchestrator.py',
                'error_message': error_message
            }
            
            summary_path = os.path.join(self.bizrobo_flag_dir, "all_systems_summary.json")
            with open(summary_path, 'w', encoding='utf-8') as f:
                json.dump(summary_data, f, indent=2, ensure_ascii=False)
            
            self.logger.error(f"エラー用統合判定ファイルを作成しました: {summary_path}")
            
        except Exception as e:
            self.logger.error(f"エラー用統合判定ファイル作成失敗: {e}")

    async def run_clius_monitor(self):
        """CLIUS監視の起動"""
        try:
            self.logger.debug("CLIUSモニタリングを開始します")
            task = asyncio.create_task(
                clius_monitor.main_with_shutdown(self.shutdown_event, self.clius_login_status)
            )
            self.monitor_processes.append(task)
            
            # ログイン完了を待機（最大10分）
            self.logger.info("CLIUS: ログイン完了を待機中...")
            if await self.clius_login_status.wait_for_completion(timeout=600):
                self.logger.info(self.clius_login_status.get_login_summary())
            else:
                self.logger.error("CLIUS: ログイン処理がタイムアウトしました")
                raise TimeoutError("CLIUSログイン処理がタイムアウトしました")
            
            self.logger.debug("CLIUSのモニタリングが開始されました")
        except Exception as e:
            self.logger.error(f"CLIUSモニタリングの起動でエラーが発生しました: {str(e)}")
            self.logger.error(traceback.format_exc())
            raise

    async def run_digikar_monitor(self):
        """デジカル監視の起動"""
        try:
            self.logger.debug("デジカルモニタリングを開始します")
            task = asyncio.create_task(
                digikar_monitor.main_with_shutdown(self.shutdown_event, self.digikar_login_status)
            )
            self.monitor_processes.append(task)
            
            # ログイン完了を待機（最大10分）
            self.logger.info("デジカル: ログイン完了を待機中...")
            if await self.digikar_login_status.wait_for_completion(timeout=600):
                self.logger.info(self.digikar_login_status.get_login_summary())
            else:
                self.logger.error("デジカル: ログイン処理がタイムアウトしました")
                raise TimeoutError("デジカルログイン処理がタイムアウトしました")
            
            self.logger.debug("デジカルのモニタリングが開始されました")
        except Exception as e:
            self.logger.error(f"デジカルモニタリングの起動でエラーが発生しました: {str(e)}")
            self.logger.error(traceback.format_exc())
            raise

    async def run_movacal_monitor(self):
        """モバカル監視の起動"""
        try:
            self.logger.debug("モバカルモニタリングを開始します")
            task = asyncio.create_task(
                movacal_monitor.main_with_shutdown(self.shutdown_event, self.movacal_login_status)
            )
            self.monitor_processes.append(task)
            
            # ログイン完了を待機（最大10分）
            self.logger.info("モバカル: ログイン完了を待機中...")
            if await self.movacal_login_status.wait_for_completion(timeout=600):
                self.logger.info(self.movacal_login_status.get_login_summary())
            else:
                self.logger.error("モバカル: ログイン処理がタイムアウトしました")
                raise TimeoutError("モバカルログイン処理がタイムアウトしました")
            
            self.logger.debug("モバカルのモニタリングが開始されました")
        except Exception as e:
            self.logger.error(f"モバカルモニタリングの起動でエラーが発生しました: {str(e)}")
            self.logger.error(traceback.format_exc())
            raise

    async def run_clinics_monitor(self):
        """CLINICS監視の起動"""
        try:
            self.logger.debug("CLINICSモニタリングを開始します")
            task = asyncio.create_task(
                clinics_monitor.main_with_shutdown(self.shutdown_event, self.clinics_login_status)
            )
            self.monitor_processes.append(task)
            
            # ログイン完了を待機（最大10分）
            self.logger.info("CLINICS: ログイン完了を待機中...")
            if await self.clinics_login_status.wait_for_completion(timeout=600):
                self.logger.info(self.clinics_login_status.get_login_summary())
            else:
                self.logger.error("CLINICS: ログイン処理がタイムアウトしました")
                raise TimeoutError("CLINICSログイン処理がタイムアウトしました")
            
            self.logger.debug("CLINICSのモニタリングが開始されました")
        except Exception as e:
            self.logger.error(f"CLINICSモニタリングの起動でエラーが発生しました: {str(e)}")
            self.logger.error(traceback.format_exc())
            raise

    async def run_ippo_monitor(self):
        """医歩監視の起動（新規追加）"""
        try:
            self.logger.debug("医歩モニタリングを開始します")
            task = asyncio.create_task(
                ippo_monitor.main_with_shutdown(self.shutdown_event, self.ippo_login_status)
            )
            self.monitor_processes.append(task)
            
            # ログイン完了を待機（最大10分）
            self.logger.info("医歩: ログイン完了を待機中...")
            if await self.ippo_login_status.wait_for_completion(timeout=600):
                self.logger.info(self.ippo_login_status.get_login_summary())
            else:
                self.logger.error("医歩: ログイン処理がタイムアウトしました")
                raise TimeoutError("医歩ログイン処理がタイムアウトしました")
            
            self.logger.debug("医歩のモニタリングが開始されました")
        except Exception as e:
            self.logger.error(f"医歩モニタリングの起動でエラーが発生しました: {str(e)}")
            self.logger.error(traceback.format_exc())
            raise

    async def run_movacli_monitor(self):
        """モバクリ監視の起動（新規追加）"""
        try:
            self.logger.debug("モバクリモニタリングを開始します")
            task = asyncio.create_task(
                movacli_monitor.main_with_shutdown(self.shutdown_event, self.movacli_login_status)
            )
            self.monitor_processes.append(task)
            
            # ログイン完了を待機（最大10分）
            self.logger.info("モバクリ: ログイン完了を待機中...")
            if await self.movacli_login_status.wait_for_completion(timeout=600):
                self.logger.info(self.movacli_login_status.get_login_summary())
            else:
                self.logger.error("モバクリ: ログイン処理がタイムアウトしました")
                raise TimeoutError("モバクリログイン処理がタイムアウトしました")
            
            self.logger.debug("モバクリのモニタリングが開始されました")
        except Exception as e:
            self.logger.error(f"モバクリモニタリングの起動でエラーが発生しました: {str(e)}")
            self.logger.error(traceback.format_exc())
            raise

    async def run_paper_monitor(self):
        """紙カルテモニタリングの実行（ログイン不要）"""
        try:
            self.logger.debug("紙カルテモニタリングを開始します")
            init_done = asyncio.Event()
            task = asyncio.create_task(
                paper_monitor.main_with_shutdown(self.shutdown_event, init_done)
            )
            self.monitor_processes.append(task)

            try:
                await asyncio.wait_for(init_done.wait(), timeout=300)
                self.logger.debug("紙カルテモニタリングの初期化が完了しました")
            except asyncio.TimeoutError:
                self.logger.error("紙カルテ: 初期化がタイムアウトしました")
                raise
                
        except Exception as e:
            self.logger.error(f"紙カルテモニタリングの起動でエラーが発生しました: {str(e)}")
            self.logger.error(traceback.format_exc())
            raise

    async def run_task_assignment(self):
        """タスク割り当ての実行"""
        try:
            await asyncio.get_event_loop().run_in_executor(None, task_assignment.main)
            self.logger.debug("タスク割り当て処理が完了しました")
        except Exception as e:
            self.logger.error(f"タスク割り当て処理でエラーが発生しました: {str(e)}")
            self.logger.error(traceback.format_exc())
            raise

    async def orchestrate(self):
        """メインの実行フロー（順次ログイン処理）"""
        self.logger.debug("オーケストレーターを開始します")
        last_task_assignment = None
        last_paper_monitor = None
        
        try:
            while self.running:
                try:
                    current_time = datetime.now()

                    # 電子カルテモニタリング（初回のみ順次実行）
                    if not self.monitor_processes:
                        # CLIUSモニタリング開始
                        await self.run_clius_monitor()
                        self.logger.debug("CLIUSモニタリングの初期化が完了しました")
                        
                        # デジカルモニタリング開始
                        await self.run_digikar_monitor()
                        self.logger.debug("デジカルモニタリングの初期化が完了しました")
                        
                        # モバカルモニタリング開始
                        await self.run_movacal_monitor()
                        self.logger.debug("モバカルモニタリングの初期化が完了しました")

                        # CLINICSモニタリング開始
                        await self.run_clinics_monitor()
                        self.logger.debug("CLINICSモニタリングの初期化が完了しました")

                        # 医歩モニタリング開始（新規追加）
                        await self.run_ippo_monitor()
                        self.logger.debug("医歩モニタリングの初期化が完了しました")

                        # モバクリモニタリング開始（新規追加）
                        await self.run_movacli_monitor()
                        self.logger.debug("モバクリモニタリングの初期化が完了しました")

                        # 紙カルテモニタリング開始
                        await self.run_paper_monitor()
                        self.logger.debug("紙カルテモニタリングの初期化が完了しました")

                        # 全システムログイン完了後、統合サマリー作成
                        if self.create_bizrobo_summary_on_completion:
                            self.logger.info("全システムのログイン処理が完了しました。統合判定ファイルを作成します。")
                            self._create_all_systems_bizrobo_summary()
                            self.create_bizrobo_summary_on_completion = False

                    # タスク割り当て処理の実行（設定された間隔ごと）
                    if last_task_assignment is None or (current_time - last_task_assignment).total_seconds() >= self.task_assignment_interval:
                        await self.run_task_assignment()
                        last_task_assignment = current_time
                        next_run = current_time + timedelta(seconds=self.task_assignment_interval)

                    # 紙カルテモニタリング処理の実行（設定された間隔ごと）
                    if last_paper_monitor is None or (current_time - last_paper_monitor).total_seconds() >= self.paper_polling_interval:
                        await self.run_paper_monitor()
                        last_paper_monitor = current_time
                        next_paper_run = current_time + timedelta(seconds=self.paper_polling_interval)

                    # 短い間隔でシャットダウンチェック
                    if await asyncio.wait_for(self.shutdown_event.wait(), timeout=1):
                        self.logger.info("シャットダウンイベントを検知しました")
                        break

                    # CPU使用率抑制のための短い待機
                    await asyncio.sleep(0.1)
                    
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    self.logger.error(f"処理中にエラーが発生しました: {str(e)}")
                    self.logger.error(traceback.format_exc())
                    last_task_assignment = None
                    last_paper_monitor = None
                    await asyncio.sleep(5)
        
        except Exception as e:
            self.logger.error(f"オーケストレーション処理中にエラーが発生しました: {str(e)}")
            self.logger.error(traceback.format_exc())
            self._create_error_bizrobo_summary(str(e))
            raise
        
        finally:
            await self.cleanup()
            self.logger.info("オーケストレーターを終了します")

    async def cleanup(self):
        """クリーンアップ処理"""
        self.logger.info("クリーンアップを開始します")
        
        # モニタリングプロセスの停止
        for process in self.monitor_processes:
            if not process.done():
                process.cancel()
                try:
                    await process
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    self.logger.error(f"プロセス終了中にエラー: {e}")
        
        self.monitor_processes.clear()
        
        # PIDファイルの削除
        self.remove_pid_file()
        
        self.logger.info("クリーンアップが完了しました")

async def main():
    """エントリーポイント"""
    orchestrator = ProcessOrchestrator()
    
    try:
        await orchestrator.orchestrate()
    except KeyboardInterrupt:
        orchestrator.logger.info("キーボード割り込みを検知しました")
    except Exception as e:
        orchestrator.logger.error(f"予期せぬエラーが発生しました: {e}")
        orchestrator.logger.error(traceback.format_exc())
        sys.exit(1)
    finally:
        orchestrator.logger.info("プログラムを終了します")

if __name__ == "__main__":
    asyncio.run(main())