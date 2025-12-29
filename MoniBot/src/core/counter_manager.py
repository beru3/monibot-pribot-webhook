# src/core/counter_manager.py
from datetime import datetime
import json
import os
from typing import Dict
import logging

logger = logging.getLogger(__name__)

class DailyCounter:
    def __init__(self, save_path: str):
        """
        日付ごとのカウンター管理クラス

        Args:
            save_path (str): カウンター情報を保存するJSONファイルのパス
        """
        self.save_path = save_path
        self.today = datetime.now().strftime('%Y%m%d')
        self.counter = 0
        self._load_counter()

    def _load_counter(self) -> None:
        """保存されているカウンター情報を読み込む"""
        try:
            if os.path.exists(self.save_path):
                with open(self.save_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get('date') == self.today:
                        self.counter = data.get('counter', 0)
                    logger.debug(f"カウンター情報を読み込みました: {self.counter}")
        except Exception as e:
            logger.error(f"カウンター情報の読み込みに失敗しました: {e}")
            self.counter = 0

    def _save_counter(self) -> None:
        """カウンター情報をファイルに保存する"""
        try:
            os.makedirs(os.path.dirname(self.save_path), exist_ok=True)
            with open(self.save_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'date': self.today,
                    'counter': self.counter
                }, f, ensure_ascii=False, indent=2)
            logger.debug(f"カウンター情報を保存しました: {self.counter}")
        except Exception as e:
            logger.error(f"カウンター情報の保存に失敗しました: {e}")

    def get_next_value(self) -> int:
        """
        現在の日付に対応するカウンター値を取得し、インクリメントする

        Returns:
            int: インクリメント前のカウンター値
        """
        current_date = datetime.now().strftime('%Y%m%d')
        if current_date != self.today:
            self.today = current_date
            self.counter = 0

        self.counter += 1
        self._save_counter()
        return self.counter

    def get_current_value(self) -> int:
        """
        現在の日付のカウンター値を取得する（インクリメントなし）

        Returns:
            int: 現在のカウンター値
        """
        return self.counter

    def reset_today(self) -> None:
        """今日のカウンターをリセットする"""
        self.counter = 0
        self._save_counter()
