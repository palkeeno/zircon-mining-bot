import os
from pathlib import Path

from dotenv import load_dotenv

# 環境変数の設定
ENV = os.getenv("ENV", "development")  # デフォルトは開発環境
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 環境に応じた.envファイルを読み込む
ENV_FILE = ".env.production" if ENV == "production" else ".env.development"
load_dotenv(PROJECT_ROOT / ENV_FILE)

# 設定マネージャーのインポート
from config.settings_manager import settings_manager

# 設定マネージャーのインスタンスを作成
settings = settings_manager

#### Load Env (Sensitive Information) ####
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DB_WALLET = os.getenv("DB_WALLET", str(PROJECT_ROOT / "wallet.db"))
CWD = os.getenv("CWD")
MCH = int(os.getenv("MCH"))

#### Load Config (Public Information) ####
# Channels
CHID_MINING = int(os.getenv("CHID_MINING"))
BRAVE_CHAT = int(os.getenv("BRAVE_CHAT"))
FREEDOM_CHAT = int(os.getenv("FREEDOM_CHAT"))
GLORY_CHAT = int(os.getenv("GLORY_CHAT"))
PEACEFUL_CHAT = int(os.getenv("PEACEFUL_CHAT"))
# 国未所属者用Excellent報告チャンネル
MINING_EXCELLENT_CHAT = int(os.getenv("MINING_EXCELLENT_CHAT"))

# Roles
BRAVE_ROLE = int(os.getenv("BRAVE_ROLE"))
FREEDOM_ROLE = int(os.getenv("FREEDOM_ROLE"))
GLORY_ROLE = int(os.getenv("GLORY_ROLE"))
PEACEFUL_ROLE = int(os.getenv("PEACEFUL_ROLE"))
# 採掘ロール
MINING_ROLE = int(os.getenv("MINING_ROLE"))
TREASURY_USER_IDS = {
    str(i): int(os.getenv(f"{name}_TREASURY_USER_ID", "0"))
    for i, name in enumerate(("BRAVE", "FREEDOM", "GLORY", "PEACEFUL"), 1)
}
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
BACKUP_DIR = os.getenv("BACKUP_DIR", "backups")
ASSET_DATA_DIR = os.getenv('ASSET_DATA_DIR', str(PROJECT_ROOT / 'asset-data'))


def get_mining_role():
    return int(settings.get("mining_role", MINING_ROLE))


def get_treasury_user_id(country_id):
    key = str(country_id)
    if key not in TREASURY_USER_IDS:
        raise ValueError("国を選択してください。")
    return int(settings.get("treasury_user_ids", {}).get(key, TREASURY_USER_IDS[key]))


def set_treasury_user_id(country_id, user_id):
    settings.load_settings()
    key = str(country_id)
    get_treasury_user_id(key)  # Reject unknown countries before saving.
    if user_id and any(get_treasury_user_id(other) == user_id for other in TREASURY_USER_IDS if other != key):
        raise ValueError("このアカウントは別の国の国庫です。国ごとに異なるアカウントを指定してください。")
    values = dict(settings.get("treasury_user_ids", {}))
    values[key] = user_id
    settings.set("treasury_user_ids", values)


def get_excellent_chat():
    return int(settings.get("excellent_chat", MINING_EXCELLENT_CHAT))

# Emojis
BRAVE_EMOJI = os.getenv("BRAVE_EMOJI")
FREEDOM_EMOJI = os.getenv("FREEDOM_EMOJI")
GLORY_EMOJI = os.getenv("GLORY_EMOJI")
PEACEFUL_EMOJI = os.getenv("PEACEFUL_EMOJI")


# country roles id
COUNTRIES = [
    {'id':1, 'role':BRAVE_ROLE, 'name':'Brave',    'chid':BRAVE_CHAT,    'stmp':BRAVE_EMOJI}, # brave
    {'id':2, 'role':FREEDOM_ROLE, 'name':'Freedom',  'chid':FREEDOM_CHAT,    'stmp':FREEDOM_EMOJI}, # freedom
    {'id':3, 'role':GLORY_ROLE, 'name':'Glory',    'chid':GLORY_CHAT,    'stmp':GLORY_EMOJI}, # glory
    {'id':4, 'role':PEACEFUL_ROLE, 'name':'Peaceful', 'chid':PEACEFUL_CHAT,    'stmp':PEACEFUL_EMOJI}  # peaceful
]

# 設定値を動的に取得する関数
def get_mine_open():
    """鉱山の営業状況を動的に取得"""
    return settings.get_mine_open()

def get_announce_hour():
    """アナウンス時間の時を動的に取得"""
    return settings.get_announce_hour()

def get_announce_minute():
    """アナウンス時間の分を動的に取得"""
    return settings.get_announce_minute()

def get_probability():
    """採掘確率設定を動的に取得"""
    return settings.get_probability()
