# src/utils/logger.py
import os
import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime
from typing import Optional, Dict, Any
import sys
import shutil


class BizRoboCompatibleFileHandler(TimedRotatingFileHandler):
    """BizRobo監視に対応したファイルハンドラー"""
    
    def emit(self, record):
        """ログ出力時の処理をオーバーライド"""
        try:
            # 現在のファイル名を保持
            current_file = self.baseFilename
            
            # 一旦ストリームを閉じる
            if self.stream:
                self.stream.close()
                self.stream = None
            
            # ファイルを書き込みモードで開く
            with open(current_file, 'a', encoding=self.encoding) as f:
                # フォーマッターを使用してレコードをフォーマット
                msg = self.format(record)
                f.write(msg + '\n')
                # 確実にディスクに書き込む
                f.flush()
                os.fsync(f.fileno())
            
            # 必要に応じて新しいストリームを開く
            if not self.stream:
                self.stream = open(current_file, 'a', encoding=self.encoding)
                
        except Exception as e:
            self.handleError(record)


class LoggerFactory:
    """集中管理されたロガー生成クラス"""
    
    _loggers = {}  # クラス変数としてロガーを保持
    
    @classmethod
    def _get_project_root(cls):
        """プロジェクトルートのパスを取得"""
        current_file = os.path.abspath(__file__)
        return os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
    
    @classmethod
    def _move_old_logs(cls, log_dir: str, target_name: str) -> None:
        """
        指定されたログディレクトリから古いログファイルをoldサブディレクトリに移動
        
        Args:
            log_dir: ログファイルが存在するディレクトリ
            target_name: 移動対象のログファイル名パターン（例：'orchestrator'）
        """
        try:
            # oldディレクトリを作成
            old_dir = os.path.join(log_dir, "old")
            os.makedirs(old_dir, exist_ok=True)
            
            current_date = datetime.now().strftime("%Y%m%d")
            moved_count = 0
            error_count = 0
            
            # ログファイルの検索と移動
            for filename in os.listdir(log_dir):
                if f"_{target_name}.log" in filename and not filename.startswith(current_date):
                    try:
                        src_path = os.path.join(log_dir, filename)
                        dst_path = os.path.join(old_dir, filename)
                        
                        # 移動先に同名ファイルが存在する場合、上書き
                        if os.path.exists(dst_path):
                            os.remove(dst_path)
                            
                        shutil.move(src_path, dst_path)
                        moved_count += 1
                        
                    except Exception as e:
                        error_count += 1
                        logging.error(f"ログファイル {filename} の移動中にエラー: {e}")
            
            if moved_count > 0 or error_count > 0:
                logging.info(f"ログファイル移動結果: {moved_count}件成功, {error_count}件失敗")
                
        except Exception as e:
            logging.error(f"古いログファイルの移動処理中にエラー: {e}")
    
    @classmethod
    def setup_logger(cls, name: str) -> logging.Logger:
        """ロガーをセットアップまたは既存のロガーを返す"""
        if name in cls._loggers:
            return cls._loggers[name]
        
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        
        # 既存のハンドラーをクリア
        logger.handlers.clear()
        
        # 親ロガーへの伝播を停止
        logger.propagate = False
        
        # フォーマッターを作成
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # ログディレクトリのパスを設定
        log_dir = os.path.join(cls._get_project_root(), "log")
        orchestrator_dir = os.path.join(log_dir, "orchestrator")
        
        # ディレクトリが存在しない場合は作成
        os.makedirs(log_dir, exist_ok=True)
        os.makedirs(orchestrator_dir, exist_ok=True)
        
        current_date = datetime.now().strftime("%Y%m%d")
        
        # orchestratorのログのみBizRoboCompatibleFileHandlerを使用
        if name == 'orchestrator':
            # 古いログファイルの移動処理を実行
            cls._move_old_logs(orchestrator_dir, 'orchestrator')
            
            file_handler = BizRoboCompatibleFileHandler(
                os.path.join(orchestrator_dir, f"{current_date}_orchestrator.log"),
                when="midnight",
                interval=1,
                backupCount=7,
                encoding='utf-8',
                delay=False
            )
        else:
            # その他のログは通常のTimedRotatingFileHandlerを使用
            file_handler = TimedRotatingFileHandler(
                os.path.join(log_dir, f"{current_date}_application.log"),
                when="midnight",
                interval=1,
                backupCount=7,
                encoding='utf-8'
            )
        
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.INFO)
        
        # コンソールハンドラーの設定
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.INFO)
        
        # ハンドラーを追加
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        # ロガーを保存
        cls._loggers[name] = logger
        
        return logger

    @staticmethod
    def clean_old_logs(days: int = 7) -> None:
        """
        指定された日数より古いログファイルを削除する
        
        Args:
            days: 保持する日数（デフォルト7日）
        """
        try:
            # プロジェクトルートからログディレクトリのパスを取得
            current_file = os.path.abspath(__file__)
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
            log_dir = os.path.join(project_root, "log")
            orchestrator_dir = os.path.join(log_dir, "orchestrator")
            
            for dir_path in [log_dir, orchestrator_dir]:
                if not os.path.exists(dir_path):
                    continue

                current_time = datetime.now()
                cleaned_files = 0
                error_files = 0

                for filename in os.listdir(dir_path):
                    if filename.endswith(("_application.log", "_orchestrator.log")):
                        file_path = os.path.join(dir_path, filename)
                        file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                        
                        if (current_time - file_time).days > days:
                            try:
                                os.remove(file_path)
                                cleaned_files += 1
                            except OSError as e:
                                error_files += 1
            
                if cleaned_files > 0 or error_files > 0:
                    logger = logging.getLogger('logger_cleanup')
                    logger.info(f"ディレクトリ {dir_path} のクリーンアップ完了: {cleaned_files} ファイル削除, {error_files} ファイル削除失敗")
        
        except Exception as e:
            logger = logging.getLogger('logger_cleanup')
            logger.error(f"ログクリーンアップ中にエラーが発生: {str(e)}")

    @staticmethod
    def set_log_level(logger_name: str, level: int) -> None:
        """
        指定されたロガーのログレベルを変更する

        Args:
            logger_name: ロガーの名前
            level: 新しいログレベル
        """
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)

    @staticmethod
    def add_file_handler(
        logger: logging.Logger,
        filepath: str,
        level: int = logging.INFO,
        format_str: Optional[str] = None
    ) -> None:
        """
        既存のロガーに新しいファイルハンドラーを追加する

        Args:
            logger: 対象のロガー
            filepath: ログファイルのパス
            level: ログレベル
            format_str: カスタムフォーマット文字列
        """
        if format_str is None:
            format_str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            
        formatter = logging.Formatter(format_str)
        
        # orchestratorのログファイル用のハンドラーを作成
        if 'orchestrator' in filepath:
            handler = BizRoboCompatibleFileHandler(
                filepath,
                when="midnight",
                interval=1,
                backupCount=7,
                encoding='utf-8',
                delay=False
            )
        else:
            handler = TimedRotatingFileHandler(
                filepath,
                when="midnight",
                interval=1,
                backupCount=7,
                encoding='utf-8'
            )
        
        handler.setFormatter(formatter)
        handler.setLevel(level)
        logger.addHandler(handler)

    @staticmethod
    def remove_handlers(logger: logging.Logger) -> None:
        """
        ロガーからすべてのハンドラーを削除する

        Args:
            logger: 対象のロガー
        """
        while logger.handlers:
            handler = logger.handlers[0]
            handler.close()
            logger.removeHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """
    LoggerFactoryを使用して簡単にロガーを取得するためのユーティリティ関数

    Args:
        name: ロガーの名前

    Returns:
        Logger: 設定されたロガーインスタンス
    """
    return LoggerFactory.setup_logger(name)

# import os
# import logging
# from logging.handlers import TimedRotatingFileHandler
# from datetime import datetime
# from typing import Optional, Dict, Any
# import sys


# class BizRoboCompatibleFileHandler(TimedRotatingFileHandler):
#     """BizRobo監視に対応したファイルハンドラー"""
    
#     def emit(self, record):
#         """ログ出力時の処理をオーバーライド"""
#         try:
#             # 現在のファイル名を保持
#             current_file = self.baseFilename
            
#             # 一旦ストリームを閉じる
#             if self.stream:
#                 self.stream.close()
#                 self.stream = None
            
#             # ファイルを書き込みモードで開く
#             with open(current_file, 'a', encoding=self.encoding) as f:
#                 # フォーマッターを使用してレコードをフォーマット
#                 msg = self.format(record)
#                 f.write(msg + '\n')
#                 # 確実にディスクに書き込む
#                 f.flush()
#                 os.fsync(f.fileno())
            
#             # 必要に応じて新しいストリームを開く
#             if not self.stream:
#                 self.stream = open(current_file, 'a', encoding=self.encoding)
                
#         except Exception as e:
#             self.handleError(record)


# class LoggerFactory:
#     """集中管理されたロガー生成クラス"""
    
#     _loggers = {}  # クラス変数としてロガーを保持
    
#     @classmethod
#     def _get_project_root(cls):
#         """プロジェクトルートのパスを取得"""
#         current_file = os.path.abspath(__file__)
#         return os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
    
#     @classmethod
#     def setup_logger(cls, name: str) -> logging.Logger:
#         """ロガーをセットアップまたは既存のロガーを返す"""
#         if name in cls._loggers:
#             return cls._loggers[name]
        
#         logger = logging.getLogger(name)
#         logger.setLevel(logging.INFO)
        
#         # 既存のハンドラーをクリア
#         logger.handlers.clear()
        
#         # 親ロガーへの伝播を停止
#         logger.propagate = False
        
#         # フォーマッターを作成
#         formatter = logging.Formatter(
#             '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
#         )
        
#         # ログディレクトリのパスを設定
#         log_dir = os.path.join(cls._get_project_root(), "log")
#         orchestrator_dir = os.path.join(log_dir, "orchestrator")
        
#         # ディレクトリが存在しない場合は作成
#         os.makedirs(log_dir, exist_ok=True)
#         os.makedirs(orchestrator_dir, exist_ok=True)
        
#         current_date = datetime.now().strftime("%Y%m%d")
        
#         # orchestratorのログのみBizRoboCompatibleFileHandlerを使用
#         if name == 'orchestrator':
#             file_handler = BizRoboCompatibleFileHandler(
#                 os.path.join(orchestrator_dir, f"{current_date}_orchestrator.log"),
#                 when="midnight",
#                 interval=1,
#                 backupCount=7,
#                 encoding='utf-8',
#                 delay=False
#             )
#         else:
#             # その他のログは通常のTimedRotatingFileHandlerを使用
#             file_handler = TimedRotatingFileHandler(
#                 os.path.join(log_dir, f"{current_date}_application.log"),
#                 when="midnight",
#                 interval=1,
#                 backupCount=7,
#                 encoding='utf-8'
#             )
        
#         file_handler.setFormatter(formatter)
#         file_handler.setLevel(logging.INFO)
        
#         # コンソールハンドラーの設定
#         console_handler = logging.StreamHandler()
#         console_handler.setFormatter(formatter)
#         console_handler.setLevel(logging.INFO)
        
#         # ハンドラーを追加
#         logger.addHandler(file_handler)
#         logger.addHandler(console_handler)
        
#         # ロガーを保存
#         cls._loggers[name] = logger
        
#         return logger

#     @staticmethod
#     def clean_old_logs(days: int = 7) -> None:
#         """
#         指定された日数より古いログファイルを削除する
        
#         Args:
#             days: 保持する日数（デフォルト7日）
#         """
#         try:
#             # プロジェクトルートからログディレクトリのパスを取得
#             current_file = os.path.abspath(__file__)
#             project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
#             log_dir = os.path.join(project_root, "log")
#             orchestrator_dir = os.path.join(log_dir, "orchestrator")
            
#             for dir_path in [log_dir, orchestrator_dir]:
#                 if not os.path.exists(dir_path):
#                     continue

#                 current_time = datetime.now()
#                 cleaned_files = 0
#                 error_files = 0

#                 for filename in os.listdir(dir_path):
#                     if filename.endswith(("_application.log", "_orchestrator.log")):
#                         file_path = os.path.join(dir_path, filename)
#                         file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                        
#                         if (current_time - file_time).days > days:
#                             try:
#                                 os.remove(file_path)
#                                 cleaned_files += 1
#                             except OSError as e:
#                                 error_files += 1
            
#                 if cleaned_files > 0 or error_files > 0:
#                     logger = logging.getLogger('logger_cleanup')
#                     logger.info(f"ディレクトリ {dir_path} のクリーンアップ完了: {cleaned_files} ファイル削除, {error_files} ファイル削除失敗")
        
#         except Exception as e:
#             logger = logging.getLogger('logger_cleanup')
#             logger.error(f"ログクリーンアップ中にエラーが発生: {str(e)}")

#     @staticmethod
#     def set_log_level(logger_name: str, level: int) -> None:
#         """
#         指定されたロガーのログレベルを変更する

#         Args:
#             logger_name: ロガーの名前
#             level: 新しいログレベル
#         """
#         logger = logging.getLogger(logger_name)
#         logger.setLevel(level)

#     @staticmethod
#     def add_file_handler(
#         logger: logging.Logger,
#         filepath: str,
#         level: int = logging.INFO,
#         format_str: Optional[str] = None
#     ) -> None:
#         """
#         既存のロガーに新しいファイルハンドラーを追加する

#         Args:
#             logger: 対象のロガー
#             filepath: ログファイルのパス
#             level: ログレベル
#             format_str: カスタムフォーマット文字列
#         """
#         if format_str is None:
#             format_str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            
#         formatter = logging.Formatter(format_str)
        
#         # orchestratorのログファイル用のハンドラーを作成
#         if 'orchestrator' in filepath:
#             handler = BizRoboCompatibleFileHandler(
#                 filepath,
#                 when="midnight",
#                 interval=1,
#                 backupCount=7,
#                 encoding='utf-8',
#                 delay=False
#             )
#         else:
#             handler = TimedRotatingFileHandler(
#                 filepath,
#                 when="midnight",
#                 interval=1,
#                 backupCount=7,
#                 encoding='utf-8'
#             )
        
#         handler.setFormatter(formatter)
#         handler.setLevel(level)
#         logger.addHandler(handler)

#     @staticmethod
#     def remove_handlers(logger: logging.Logger) -> None:
#         """
#         ロガーからすべてのハンドラーを削除する

#         Args:
#             logger: 対象のロガー
#         """
#         while logger.handlers:
#             handler = logger.handlers[0]
#             handler.close()
#             logger.removeHandler(handler)


# def get_logger(name: str) -> logging.Logger:
#     """
#     LoggerFactoryを使用して簡単にロガーを取得するためのユーティリティ関数

#     Args:
#         name: ロガーの名前

#     Returns:
#         Logger: 設定されたロガーインスタンス
#     """
#     return LoggerFactory.setup_logger(name)