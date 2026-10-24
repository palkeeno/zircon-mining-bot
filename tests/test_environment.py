import os
import io
from contextlib import closing, redirect_stdout
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

import test_mining_service  # Initializes isolated configuration before bot imports.
from config.settings_manager import SettingsManager
from config.role_manager import RoleProbabilityManager
from utils import backup
import zrmine


class EnvironmentTests(unittest.TestCase):
    def test_backup_cleanup_ignores_old_database_and_unrelated_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('wallet.db_20200101', 'mining.db_20200101', 'notes.txt'):
                (root / name).write_text('keep unless wallet backup')
            with patch.object(backup.config, 'DB_WALLET', 'wallet.db'), \
                 patch.object(backup.config, 'BACKUP_DIR', str(root)), \
                 patch.object(backup.os.path, 'getctime', return_value=0):
                # Windows CI uses a Western code page: cleanup must not depend on Japanese stdout.
                with io.TextIOWrapper(io.BytesIO(), encoding='cp1252') as output, redirect_stdout(output):
                    backup.cleanup_old_backups()
                    backup.cleanup_excess_backups(0)
            self.assertFalse((root / 'wallet.db_20200101').exists())
            self.assertTrue((root / 'mining.db_20200101').exists())
            self.assertTrue((root / 'notes.txt').exists())

    def test_settings_and_role_writes_are_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, {
                'SETTINGS_FILE': str(root / 'settings.json'),
                'ROLE_SETTINGS_FILE': str(root / 'roles.json'),
            }):
                settings = SettingsManager()
                settings.set('mining_limit', 7)
                roles = RoleProbabilityManager()
                roles.cache = [{'role_name': 'test', 'priority': 1}]
                roles.save()
                self.assertEqual(SettingsManager().get('mining_limit'), 7)
                self.assertEqual(RoleProbabilityManager().cache, roles.cache)
                explicit = SettingsManager(root / 'explicit.json')
                self.assertEqual(explicit.get('mining_limit', 1), 1)

    def test_backup_uses_configured_directory_and_keeps_database(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / 'users.db'
            with closing(sqlite3.connect(database)) as connection, connection:
                connection.execute('CREATE TABLE evidence(value INTEGER)')
                connection.execute('INSERT INTO evidence VALUES(42)')
            with patch.object(backup.config, 'DB_WALLET', str(database)), \
                 patch.object(backup.config, 'BACKUP_DIR', str(root / 'backups')):
                files = backup.perform_backup()
            self.assertEqual(len(files), 1)
            self.assertEqual(Path(files[0]).parent, root / 'backups')
            with closing(sqlite3.connect(files[0])) as connection:
                self.assertEqual(connection.execute('SELECT value FROM evidence').fetchone(), (42,))


class GuildStartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_wrong_guild_stops_before_backup_initialization_or_sync(self):
        client = SimpleNamespace(fetch_channel=AsyncMock(return_value=SimpleNamespace(guild=SimpleNamespace(id=222))))
        with patch.object(zrmine.config, 'GUILD_ID', 111), \
             patch.object(zrmine, 'create_backup') as backup_mock, \
             patch.object(zrmine.wallet, 'initialize') as migrate, \
             patch.object(zrmine.tree, 'sync', new=AsyncMock()) as sync:
            with self.assertRaisesRegex(RuntimeError, 'GUILD_ID'):
                await zrmine.MiningClient.setup_hook(client)
        backup_mock.assert_not_called()
        migrate.assert_not_called()
        sync.assert_not_awaited()

    async def test_test_server_sync_never_syncs_global_commands(self):
        client = SimpleNamespace(fetch_channel=AsyncMock(return_value=SimpleNamespace(guild=SimpleNamespace(id=111))), add_view=Mock())
        with patch.object(zrmine.config, 'GUILD_ID', 111), \
             patch.object(zrmine, 'create_backup'), \
             patch.object(zrmine.wallet, 'initialize'), \
             patch.object(zrmine.asset_catalog, 'initialize'), \
             patch.object(zrmine.tree, 'copy_global_to') as copy, \
             patch.object(zrmine.tree, 'sync', new=AsyncMock()) as sync:
            await zrmine.MiningClient.setup_hook(client)
        self.assertEqual(sync.call_args.kwargs['guild'].id, 111)
        self.assertEqual(copy.call_args.kwargs['guild'].id, 111)
        self.assertEqual(client.add_view.call_count, 2)
