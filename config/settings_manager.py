import json
import os
from pathlib import Path
from typing import List, Dict, Any

class SettingsManager:
    """設定値を管理するクラス"""
    
    def __init__(self, settings_file=None):
        self.settings_file = str(settings_file or Path(__file__).resolve().parent.parent / "data/user_setting.json")
        self._settings = {}
        self.load_settings()
    
    def load_settings(self):
        """設定ファイルから設定値を読み込む"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    self._settings = json.load(f)
            else:
                # デフォルト設定で初期化
                self._settings = {
                    "mine_open": True,
                    "announce_hour": [0, 12],
                    "announce_minute": [0],
                    "probability": [
                        {"id": 0, "msg": "Excellent", "prob": 0.03, "zirnum": 10},
                        {"id": 1, "msg": "Great", "prob": 0.25, "zirnum": 3},
                        {"id": 2, "msg": "Good", "prob": 1, "zirnum": 1}
                    ]
                }
                self.save_settings()
        except Exception as e:
            raise RuntimeError(f"設定ファイルを読み込めません: {self.settings_file}") from e

    def save_settings(self):
        """設定値をファイルに保存する"""
        os.makedirs(os.path.dirname(os.path.abspath(self.settings_file)), exist_ok=True)
        temporary = self.settings_file + ".tmp"
        with open(temporary, 'w', encoding='utf-8') as f:
            json.dump(self._settings, f, ensure_ascii=False, indent=4)
        os.replace(temporary, self.settings_file)
    
    def get(self, key: str, default=None):
        """設定値を取得する"""
        return self._settings.get(key, default)
    
    def set(self, key: str, value: Any):
        """設定値を設定し、ファイルに保存する"""
        self.update({key: value})

    def update(self, values):
        self.load_settings()
        previous = self._settings.copy()
        self._settings.update(values)
        try:
            self.save_settings()
        except Exception:
            self._settings = previous
            raise
    
    def get_mine_open(self) -> bool:
        """鉱山の営業状況を取得（毎回ファイル再読込）"""
        self.load_settings()
        return self.get("mine_open", True)
    
    def set_mine_open(self, value: bool):
        """鉱山の営業状況を設定"""
        self.set("mine_open", value)
    
    def get_announce_hour(self) -> List[int]:
        """アナウンス時間の時を取得"""
        return self.get("announce_hour", [0, 12])
    
    def set_announce_hour(self, value: List[int]):
        """アナウンス時間の時を設定"""
        self.set("announce_hour", value)
    
    def get_announce_minute(self) -> List[int]:
        """アナウンス時間の分を取得"""
        return self.get("announce_minute", [0])
    
    def set_announce_minute(self, value: List[int]):
        """アナウンス時間の分を設定"""
        self.set("announce_minute", value)
    
    def get_probability(self) -> List[Dict[str, Any]]:
        """採掘確率設定を取得"""
        return self.get("probability", [
            {"id": 0, "msg": "Excellent", "prob": 0.03, "zirnum": 10},
            {"id": 1, "msg": "Great", "prob": 0.25, "zirnum": 3},
            {"id": 2, "msg": "Good", "prob": 1, "zirnum": 1}
        ])
    
    def set_probability(self, value: List[Dict[str, Any]]):
        """採掘確率設定を設定"""
        self.set("probability", value)
    
    def update_probability_item(self, item_id: int, prob: float = None, zirnum: int = None):
        """採掘確率の特定アイテムを更新"""
        probability = self.get_probability()
        
        # アイテムを検索して更新
        for item in probability:
            if item["id"] == item_id:
                if prob is not None:
                    item["prob"] = prob
                if zirnum is not None:
                    item["zirnum"] = zirnum
                break
        
        self.set_probability(probability)

# グローバルインスタンス
settings_manager = SettingsManager()
