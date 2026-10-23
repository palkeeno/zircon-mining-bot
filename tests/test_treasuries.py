import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_mining_service
import config.config as config
from config.settings_manager import SettingsManager


class TreasuryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings = SettingsManager(Path(self.directory.name) / "settings.json")
        self.patch = patch.object(config, "settings", self.settings)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.defaults = patch.object(config, "TREASURY_USER_IDS", {str(i): 0 for i in range(1, 5)})
        self.defaults.start()
        self.addCleanup(self.defaults.stop)

    def test_four_treasuries_persist_independently(self):
        for country in range(1, 5):
            config.set_treasury_user_id(country, 100 + country)
        self.settings.load_settings()
        self.assertEqual([config.get_treasury_user_id(i) for i in range(1, 5)], [101, 102, 103, 104])
        config.set_treasury_user_id(2, 0)
        self.assertEqual([config.get_treasury_user_id(i) for i in range(1, 5)], [101, 0, 103, 104])

    def test_same_account_cannot_belong_to_two_countries(self):
        config.set_treasury_user_id(1, 101)
        with self.assertRaisesRegex(ValueError, "別の国"):
            config.set_treasury_user_id(2, 101)
        self.assertEqual(config.get_treasury_user_id(2), 0)

    def test_env_defaults_and_explicit_disable(self):
        with patch.object(config, "TREASURY_USER_IDS", {"1": 101, "2": 102, "3": 103, "4": 104}):
            self.assertEqual(config.get_treasury_user_id(1), 101)
            with self.assertRaises(ValueError):
                config.set_treasury_user_id(2, 101)
            config.set_treasury_user_id(1, 0)
            self.assertEqual(config.get_treasury_user_id(1), 0)

    def test_legacy_single_account_is_not_assigned_to_an_arbitrary_country(self):
        self.settings.set("treasury_user_id", 999)
        self.assertEqual([config.get_treasury_user_id(i) for i in range(1, 5)], [0, 0, 0, 0])
        self.assertEqual(self.settings.get("treasury_user_id"), 999)

    def test_unknown_country_is_rejected(self):
        with self.assertRaises(ValueError):
            config.set_treasury_user_id(5, 105)
        self.assertIsNone(self.settings.get("treasury_user_ids"))
