# src/utils/login_status.py

import asyncio
import os
from datetime import datetime
from typing import Optional, Dict, List
from dataclasses import dataclass
from enum import Enum

class LoginState(Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILURE = "failure"

@dataclass
class HospitalLoginStatus:
    hospital_name: str
    status: LoginState
    login_time: Optional[datetime] = None
    error_message: Optional[str] = None


class LoginStatus:
    def __init__(self, system_name):
        self.system_name = system_name
        self.total_hospitals = 0
        self.completed_hospitals = 0
        self.completion_event = asyncio.Event()
        self.hospital_statuses = {}
        self._start_time = None
        self._end_time = None
        self.success_count = 0

    def start_login_process(self, total_hospitals):
        self.total_hospitals = total_hospitals
        self.completed_hospitals = 0
        self.completion_event.clear()
        self._start_time = datetime.now()
        self.success_count = 0
        # 医療機関数が0の場合は即座に完了とする
        if self.total_hospitals == 0:
            self._end_time = datetime.now()
            self.completion_event.set()

    def update_hospital_status(self, hospital_name, success, error_message=None):
        """病院ごとのログイン状態を更新"""
        self.hospital_statuses[hospital_name] = {
            'success': success,
            'error': error_message
        }
        # 成功/失敗に関わらず処理完了としてカウント
        self.completed_hospitals += 1

        if success:
            self.success_count += 1
            # ログイン成功時にlogin_checkフォルダにファイルを作成
            self._create_login_success_file(hospital_name)

        # すべての病院の処理が完了したか、医療機関数が0の場合
        if self.completed_hospitals >= self.total_hospitals:
            self._end_time = datetime.now()
            self.completion_event.set()

    def get_login_summary(self) -> str:
        """ログイン状況のサマリーを取得"""
        if not self._start_time:
            return f"{self.system_name}: ログイン処理未開始"

        elapsed_time = ""
        if self._end_time and self._start_time:
            seconds = (self._end_time - self._start_time).total_seconds()
            elapsed_time = f", 所要時間: {seconds:.1f}秒"

        if self.total_hospitals == 0:
            return f"{self.system_name}: ポーリング対象の医療機関なし{elapsed_time}\n"

        summary = f"{self.system_name}: {self.success_count}/{self.total_hospitals} 医療機関のログイン完了{elapsed_time}\n"
        
        # 失敗したケースの詳細を追加
        failed_hospitals = [
            (name, status) for name, status in self.hospital_statuses.items()
            if not status['success']
        ]
        if failed_hospitals:
            summary += "ログイン失敗した医療機関:\n"
            for name, status in failed_hospitals:
                summary += f"- {name}"
                if status['error']:
                    summary += f": {status['error']}"
                summary += "\n"

        return summary

    async def wait_for_completion(self, timeout=None):
        """ログイン完了を待機"""
        try:
            await asyncio.wait_for(self.completion_event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    def _create_login_success_file(self, hospital_name):
        """ログイン成功時にlogin_checkフォルダにテキストファイルを作成"""
        try:
            # プロジェクトルートのパスを取得
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(os.path.dirname(current_dir))
            login_check_dir = os.path.join(project_root, 'login_check')
            
            # login_checkディレクトリが存在しない場合は作成
            if not os.path.exists(login_check_dir):
                os.makedirs(login_check_dir)
            
            # ファイル名から無効な文字を除去
            safe_filename = "".join(c for c in hospital_name if c.isalnum() or c in (' ', '-', '_', '（', '）', 'ー')).rstrip()
            filename = f"{safe_filename}.txt"
            filepath = os.path.join(login_check_dir, filename)
            
            # 現在日時を指定フォーマットで取得
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            
            # ファイルに日時を書き込み
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(current_time)
                
        except Exception as e:
            # エラーが発生してもログイン処理自体は継続させる
            print(f"login_check ファイル作成中にエラーが発生しました: {e}")
