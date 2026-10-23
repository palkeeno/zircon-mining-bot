"""Wire the SQLite adapter and configuration into application services."""
import config.config as config
from models import wallet
from services.wallet_service import WalletService

wallet_service = WalletService(wallet, config)
