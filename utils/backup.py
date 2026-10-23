import os
import sqlite3
from contextlib import closing
import datetime
from typing import List
import config.config as config
from domain.mining_period import JST

def create_backup() -> List[str]:
    """データベースのバックアップを作成する

    Returns:
        List[str]: バックアップファイルのパスリスト
    """
    backup_dir = config.BACKUP_DIR
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)

    timestamp = datetime.datetime.now(JST).strftime("%Y%m%d_%H%M%S_%f")
    backup_files = []

    # 各データベースファイルのバックアップを作成
    for db_path in [config.DB_MINING, config.DB_USERS]:
        if os.path.exists(db_path):
            backup_path = os.path.join(backup_dir, f"{os.path.basename(db_path)}_{timestamp}")
            with closing(sqlite3.connect(db_path)) as source, closing(sqlite3.connect(backup_path)) as destination:
                source.backup(destination)
            backup_files.append(backup_path)

    return backup_files

def cleanup_old_backups(days_to_keep: int = 10) -> None:
    """古いバックアップファイルを削除する

    Args:
        days_to_keep (int): 保持する日数
    """
    backup_dir = config.BACKUP_DIR
    if not os.path.exists(backup_dir):
        return

    cutoff_date = datetime.datetime.now(JST) - datetime.timedelta(days=days_to_keep)
    for filename in os.listdir(backup_dir):
        file_path = os.path.join(backup_dir, filename)
        file_time = datetime.datetime.fromtimestamp(os.path.getctime(file_path), JST)
        if file_time < cutoff_date:
            try:
                os.remove(file_path)
                print(f"バックアップ削除（期限超過）: {file_path}")
            except Exception as e:
                print(f"バックアップ削除失敗: {file_path} {e}")

def cleanup_excess_backups(max_files: int = 10) -> None:
    """各DBごとにバックアップファイルがmax_files個を超えていたら古いものから削除する"""
    backup_dir = config.BACKUP_DIR
    for db_name in [os.path.basename(config.DB_MINING), os.path.basename(config.DB_USERS)]:
        prefix = db_name + "_"
        db_backups = [f for f in os.listdir(backup_dir) if f.startswith(prefix)]
        if len(db_backups) > max_files:
            db_backups_sorted = sorted(db_backups)
            to_delete = db_backups_sorted[:len(db_backups)-max_files]
            for fname in to_delete:
                try:
                    os.remove(os.path.join(backup_dir, fname))
                    print(f"バックアップ削除（個数超過）: {os.path.join(backup_dir, fname)}")
                except Exception as e:
                    print(f"バックアップ削除失敗: {os.path.join(backup_dir, fname)} {e}")

def perform_backup() -> List[str]:
    """バックアップを実行し、古いバックアップ・個数超過バックアップを削除する

    Returns:
        List[str]: 作成されたバックアップファイルのパスリスト
    """
    backup_files = create_backup()
    cleanup_old_backups()
    cleanup_excess_backups()
    return backup_files
