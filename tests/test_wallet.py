import concurrent.futures
from contextlib import closing
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import test_mining_service  # installs safe environment defaults
from config.settings_manager import SettingsManager
from models import wallet


class WalletTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        settings = SettingsManager(Path(self.temp.name) / "settings.json")
        settings.update({"announce_hour": [0, 12], "announce_minute": [0], "mining_limit": 1})
        for key, value in {
            "DB_USERS": str(Path(self.temp.name) / "users.db"),
            "settings": settings,
        }.items():
            p = patch.object(wallet.config, key, value)
            p.start()
            self.addCleanup(p.stop)
        wallet.initialize()
        self.now = datetime(2026, 10, 20, 10, tzinfo=wallet.JST)

    def grant(self, uid=100, amount=20, request="grant"):
        wallet.change(amount, actor=999, request_id=request, target=uid, kind="grant")

    def test_grant_remove_transfer_preserve_mining_statistics(self):
        wallet.claim(100, 10, True, "mine", self.now)
        self.grant()
        wallet.change(7, actor=999, request_id="transfer", source=100, target=200)
        wallet.change(3, actor=999, request_id="remove", source=200)
        self.assertEqual(wallet.balance(100), (23, 1, 1))
        self.assertEqual(wallet.balance(200), (4, 0, 0))
        with closing(sqlite3.connect(wallet.config.DB_USERS)) as db, db:
            self.assertEqual(db.execute("SELECT lt_total FROM USERS WHERE userid=100").fetchone()[0], 10)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM LEDGER").fetchone()[0], 4)

    def test_insufficient_funds_rolls_back_entire_transfer(self):
        self.grant()
        with self.assertRaises(ValueError):
            wallet.change(21, actor=100, request_id="bad", source=100, target=200)
        self.assertEqual(wallet.balance(100)[0], 20)
        with closing(sqlite3.connect(wallet.config.DB_USERS)) as db, db:
            self.assertIsNone(db.execute("SELECT 1 FROM USERS WHERE userid=200").fetchone())
            self.assertIsNone(db.execute("SELECT 1 FROM LEDGER WHERE request_id='bad'").fetchone())

    def test_duplicate_request_is_not_applied_twice(self):
        self.grant()
        with self.assertRaises(ValueError):
            self.grant()
        self.assertEqual(wallet.balance(100)[0], 20)

    def test_invalid_amount_self_transfer_and_overflow(self):
        for amount in (0, -1, 1.5, True, 2**63):
            with self.assertRaises(ValueError):
                self.grant(amount=amount)
        self.grant(amount=wallet.MAX_AMOUNT)
        with self.assertRaises(ValueError):
            self.grant(amount=1, request="overflow")
        with self.assertRaises(ValueError):
            wallet.change(1, actor=100, request_id="self", source=100, target=100)
        self.assertEqual(wallet.balance(100)[0], wallet.MAX_AMOUNT)

    def test_claim_limit_and_reset_boundary_survive_restart(self):
        self.assertEqual(wallet.claim(100, 3, False, "a", self.now), 3)
        wallet.initialize()
        with self.assertRaises(ValueError):
            wallet.claim(100, 3, False, "b", self.now)
        self.assertEqual(wallet.claim(100, 10, True, "c", self.now.replace(hour=12)), 13)
        self.assertEqual(wallet.balance(100), (13, 2, 1))

    def test_configurable_limit_and_missed_resets(self):
        wallet.config.settings.set("mining_limit", 2)
        wallet.claim(100, 1, False, "a", self.now)
        wallet.claim(100, 1, False, "b", self.now)
        with self.assertRaises(ValueError):
            wallet.claim(100, 1, False, "c", self.now)
        wallet.claim(100, 1, False, "d", self.now.replace(day=23))
        self.assertEqual(wallet.balance(100)[0], 3)

    def test_parallel_claims_credit_once(self):
        def mine(index):
            try:
                wallet.claim(100, 10, True, f"mine-{index}", self.now)
                return True
            except ValueError:
                return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(mine, range(8)))
        self.assertEqual(sum(outcomes), 1)
        self.assertEqual(wallet.balance(100), (10, 1, 1))

    def test_parallel_transfers_never_overspend(self):
        self.grant(amount=10)
        def transfer(index):
            try:
                wallet.change(7, actor=100, request_id=f"t-{index}", source=100, target=200 + index)
                return True
            except ValueError:
                return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            outcomes = list(pool.map(transfer, range(4)))
        self.assertEqual(sum(outcomes), 1)
        self.assertEqual(wallet.balance(100)[0], 3)
        self.assertEqual(sum(row[1] for row in wallet.ranking("balance")), 10)

    def test_ranking_uses_balance_and_excellent_with_stable_ties(self):
        self.grant(100, 10)
        wallet.claim(200, 3, True, "b", self.now)
        self.grant(300, 10, "c")
        self.assertEqual([row[0] for row in wallet.ranking("balance")], [100, 300, 200])
        self.assertEqual(wallet.ranking("excellent")[0], (200, 3, 1, 1))

    def test_period_before_first_daily_reset(self):
        wallet.config.settings.update({"announce_hour": [6, 18], "announce_minute": [30]})
        self.assertEqual(wallet.period_start(self.now.replace(hour=1)), "2026-10-19T18:30:00+09:00")

    def test_manual_reset_preserves_wallet_and_next_scheduled_boundary(self):
        wallet.claim(100, 10, True, 'before', self.now)
        self.grant(200, 7)
        reset_time = self.now.replace(hour=11)
        wallet.reset_claims(actor=999, request_id='reset', now=reset_time)
        self.assertEqual(wallet.balance(100), (10, 1, 1))
        self.assertEqual(wallet.balance(200), (7, 0, 0))
        wallet.initialize()
        wallet.claim(100, 1, False, 'after', reset_time)
        with self.assertRaises(ValueError):
            wallet.claim(100, 1, False, 'denied', reset_time)
        with self.assertRaises(ValueError):
            wallet.reset_claims(actor=999, request_id='reset', now=reset_time)
        with self.assertRaises(ValueError):
            wallet.claim(100, 1, False, 'still-denied', reset_time)
        wallet.claim(100, 1, False, 'noon', self.now.replace(hour=12))
        self.assertEqual(wallet.balance(100), (12, 3, 1))
        with closing(sqlite3.connect(wallet.config.DB_USERS)) as db:
            self.assertEqual(db.execute('SELECT actor FROM RESET_LOG').fetchall(), [(999,)])

    def test_repeated_manual_resets_at_same_time_have_distinct_periods(self):
        first = wallet.reset_claims(actor=999, request_id='reset1', now=self.now)
        wallet.claim(100, 1, False, 'one', self.now)
        second = wallet.reset_claims(actor=999, request_id='reset2', now=self.now)
        self.assertGreater(second, first)
        wallet.claim(100, 1, False, 'two', self.now)
        self.assertEqual(wallet.balance(100), (2, 2, 0))

    def test_settings_persist_and_failed_write_preserves_previous_value(self):
        settings = wallet.config.settings
        settings.update({"mining_role": 987, "treasury_user_id": 654, "excellent_chat": 321})
        loaded = SettingsManager(settings.settings_file)
        self.assertEqual(loaded.get("treasury_user_id"), 654)
        with patch("config.settings_manager.os.replace", side_effect=OSError("disk error")):
            with self.assertRaises(OSError):
                settings.set("treasury_user_id", 123)
        self.assertEqual(settings.get("treasury_user_id"), 654)
        self.assertEqual(SettingsManager(settings.settings_file).get("treasury_user_id"), 654)

    def test_corrupt_settings_fail_instead_of_reopening_mine(self):
        settings = wallet.config.settings
        Path(settings.settings_file).write_text("{broken", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            settings.get_mine_open()
