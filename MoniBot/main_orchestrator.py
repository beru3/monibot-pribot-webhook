#!/usr/bin/env python3
import os
import sys
import configparser

# プロジェクトルートへのパスを追加
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)

import asyncio
import logging
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
import traceback
import signal

from src.utils.logger import LoggerFactory
from src.core import task_assignment
from src.core import clius_monitor
from src.core import digikar_monitor
from src.core import movacal_monitor
from src.core import clinics_monitor
from src.core import paper_monitor
from src.utils.login_status import LoginStatus


class ProcessOrchestrator:
    def __init__(self):
        self.setup_logging()
        self.monitor_processes = []
        self.running = True
        self.shutdown_event = asyncio.Event()
        
        # 各システムのログイン状態管理
        self.clius_login_status = LoginStatus("CLIUS")
        self.digikar_login_status = LoginStatus("デジカル")
        self.movacal_login_status = LoginStatus("モバカル")
        self.clinics_login_status = LoginStatus("CLINICS")
        
        # PIDファイルのパスを設定と初期化
        self.pid_file = os.path.join(project_root, "config", "pid.txt")
        self.initialize_pid_file()
        
        # 設定ファイルを読み込む
        config = configparser.ConfigParser()
        config_path = os.path.join(project_root, "config", "config.ini")
        config.read(config_path, encoding='utf-8')
        
        # タスク割り当て間隔を設定から読み込む（デフォルト値：30秒）
        self.task_assignment_interval = config.getint('setting', 'task_assignment_interval', fallback=30)
        self.logger.info(f"タスク割り当て間隔を {self.task_assignment_interval} 秒に設定しました")

        # 各システムのポーリング間隔を設定から読み込む
        self.clius_polling_interval = config.getint('setting', 'clius_polling_interval', fallback=30)
        self.digikar_polling_interval = config.getint('setting', 'digikar_polling_interval', fallback=30)
        self.movacal_polling_interval = config.getint('setting', 'movacal_polling_interval', fallback=30)
        self.clinics_polling_interval = config.getint('setting', 'clinics_polling_interval', fallback=30)
        self.paper_polling_interval = config.getint('setting', 'paper_polling_interval', fallback=30)
        
        self.logger.info(f"CLIUSポーリング間隔を {self.clius_polling_interval} 秒に設定しました")
        self.logger.info(f"デジカルポーリング間隔を {self.digikar_polling_interval} 秒に設定しました")
        self.logger.info(f"モバカルポーリング間隔を {self.movacal_polling_interval} 秒に設定しました")
        self.logger.info(f"CLINICSポーリング間隔を {self.clinics_polling_interval} 秒に設定しました")
        self.logger.info(f"紙カルテポーリング間隔を {self.paper_polling_interval} 秒に設定しました")
        
        # シグナルハンドラの設定
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, self.handle_shutdown)

    def initialize_pid_file(self):
        """PIDファイルの初期化"""
        try:
            # configディレクトリが存在することを確認
            os.makedirs(os.path.dirname(self.pid_file), exist_ok=True)
            
            # 既存のPIDファイルがあれば削除
            if os.path.exists(self.pid_file):
                os.remove(self.pid_file)
                self.logger.info(f"既存のPIDファイル {self.pid_file} を削除しました")
            
            # 新しいPIDファイルを作成
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
        if not self.running:  # 既にシャットダウン中の場合は無視
            return
            
        self.logger.info(f"シグナル {signal.Signals(signum).name} を受信しました")
        self.running = False
        
        # PIDファイルを削除
        self.remove_pid_file()
        
        # イベントループがある場合のみイベントをセット
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.call_soon_threadsafe(self.shutdown_event.set)
        except Exception as e:
            self.logger.error(f"シャットダウンイベントの設定中にエラー: {e}")

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

    async def run_task_assignment(self):
        """タスク割り当ての実行"""
        try:
            await asyncio.get_event_loop().run_in_executor(None, task_assignment.main)
            self.logger.debug("タスク割り当て処理が完了しました")
        except Exception as e:
            self.logger.error(f"タスク割り当て処理でエラーが発生しました: {str(e)}")
            self.logger.error(traceback.format_exc())
            raise

    async def run_clius_monitor(self):
        """CLIUSモニタリングの実行"""
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
        """デジカルモニタリングの実行"""
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
        """モバカルモニタリングの実行"""
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
            """CLINICSモニタリングの実行"""
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

    # async def run_paper_monitor(self):
    #     """紙カルテモニタリングの実行（ログイン不要）"""
    #     try:
    #         self.logger.debug("紙カルテモニタリングを開始します")
    #         task = asyncio.create_task(
    #             paper_monitor.main_with_shutdown(self.shutdown_event)
    #         )
    #         self.monitor_processes.append(task)
    #         self.logger.debug("紙カルテのモニタリングが開始されました")
            
    #     except Exception as e:
    #         self.logger.error(f"紙カルテモニタリングの起動でエラーが発生しました: {str(e)}")
    #         self.logger.error(traceback.format_exc())
    #         raise
    
    # async def run_paper_monitor(self):
    #     """紙カルテモニタリングの実行"""
    #     try:
    #         self.logger.debug("紙カルテモニタリングを開始します")
    #         task = asyncio.create_task(
    #             paper_monitor.main_with_shutdown(self.shutdown_event)
    #         )
    #         self.monitor_processes.append(task)
            
    #         # 初期化完了を待機
    #         try:
    #             # 初期化が完了するまで待機（最大5分）
    #             await asyncio.wait_for(task, timeout=300)
    #             self.logger.debug("紙カルテの初期化が完了しました")
    #         except asyncio.TimeoutError:
    #             self.logger.error("紙カルテ: 初期化処理がタイムアウトしました")
    #             raise TimeoutError("紙カルテ初期化処理がタイムアウトしました")
            
    #     except Exception as e:
    #         self.logger.error(f"紙カルテモニタリングの起動でエラーが発生しました: {str(e)}")
    #         self.logger.error(traceback.format_exc())
    #         raise

    async def run_paper_monitor(self):
        """紙カルテモニタリングの実行（ログイン不要）"""
        try:
            self.logger.debug("紙カルテモニタリングを開始します")
            # 初期化完了を待機
            init_done = asyncio.Event()
            task = asyncio.create_task(
                paper_monitor.main_with_shutdown(self.shutdown_event, init_done)
            )
            self.monitor_processes.append(task)

            try:
                # 初期化完了を待機（最大5分）
                await asyncio.wait_for(init_done.wait(), timeout=300)
                self.logger.debug("紙カルテモニタリングの初期化が完了しました")
            except asyncio.TimeoutError:
                self.logger.error("紙カルテ: 初期化がタイムアウトしました")
                raise
                
        except Exception as e:
            self.logger.error(f"紙カルテモニタリングの起動でエラーが発生しました: {str(e)}")
            self.logger.error(traceback.format_exc())
            raise

    async def orchestrate(self):
        """メインの実行フロー"""
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

                        # # 紙カルテモニタリング開始
                        await self.run_paper_monitor()
                        self.logger.debug("紙カルテモニタリングの初期化が完了しました")


                    # タスク割り当て処理の実行（設定された間隔ごと）
                    if last_task_assignment is None or (current_time - last_task_assignment).total_seconds() >= self.task_assignment_interval:
                        # self.logger.info("タスクの割り当て処理を開始します")
                        await self.run_task_assignment()
                        last_task_assignment = current_time
                        next_run = current_time + timedelta(seconds=self.task_assignment_interval)
                        self.logger.info(f"次回のタスク割り当て時刻: {next_run.strftime('%H:%M:%S')}")

                    # 紙カルテモニタリング処理の実行（設定された間隔ごと）
                    if last_paper_monitor is None or (current_time - last_paper_monitor).total_seconds() >= self.paper_polling_interval:
                        # self.logger.info("紙カルテのファイル監視を開始します")
                        await self.run_paper_monitor()
                        last_paper_monitor = current_time
                        next_paper_run = current_time + timedelta(seconds=self.paper_polling_interval)
                        # self.logger.info(f"次回の紙カルテ監視時刻: {next_paper_run.strftime('%H:%M:%S')}")

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
        
        finally:
            await self.cleanup()
            self.logger.info("オーケストレーターを終了します")
            
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