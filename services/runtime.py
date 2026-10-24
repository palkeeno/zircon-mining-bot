"""Wire the SQLite adapter and configuration into application services."""
import config.config as config
from models import wallet
from services.wallet_service import WalletService
from services.asset_catalog import AssetCatalog

wallet_service = WalletService(wallet, config)
asset_catalog = AssetCatalog(config.ASSET_DATA_DIR)
