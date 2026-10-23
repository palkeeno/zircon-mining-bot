"""Application operations shared by commands, buttons and scheduled work."""
from dataclasses import dataclass

from services.wallet_export import export_wallet, package_exports


@dataclass(frozen=True)
class Donation:
    country: str
    target: int
    amount: int


class WalletService:
    def __init__(self, repository, configuration):
        self.repository = repository
        self.configuration = configuration

    def change(self, amount, **operation):
        return self.repository.change(amount, **operation)

    def claim(self, *args, **kwargs):
        return self.repository.claim(*args, **kwargs)

    def balance(self, user_id):
        return self.repository.balance(user_id)

    def ranking(self, kind):
        return self.repository.ranking(kind)

    def current_period(self):
        return self.repository.current_period()

    def reset(self, *, actor, request_id):
        return self.repository.reset_claims(actor=actor, request_id=request_id)

    def export(self, limit, tables):
        return package_exports(export_wallet(self.configuration.DB_WALLET, tables), limit)

    def donate(self, *, actor, roles, amount, request_id):
        config = self.configuration
        config.settings.load_settings()
        countries = [country for country in config.COUNTRIES if country['role'] in roles]
        if len(countries) != 1:
            raise ValueError('所属国を1つに確定できません。国ロールを確認してください。')
        country = countries[0]
        treasury = config.get_treasury_user_id(country['id'])
        if not treasury:
            raise ValueError('寄付先の国庫が未設定です。管理者にお問い合わせください。')
        if any(config.get_treasury_user_id(other['id']) == treasury
               for other in config.COUNTRIES if other['id'] != country['id']):
            raise ValueError('複数国に同じ国庫が設定されています。管理者にお問い合わせください。')
        self.change(amount, actor=actor, request_id=request_id, source=actor, target=treasury, kind='donate')
        return Donation(country['name'], treasury, amount)
