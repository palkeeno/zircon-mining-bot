import asyncio
from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

import test_mining_service
import config.config as config
from config.settings_manager import SettingsManager
from models import wallet
from services.wallet_service import WalletService
from test_wallet_ui import interaction
from views.wipe_view import WipeView, WipeModal, CONFIRMATION


class WipeDatabaseTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.database = self.root / 'wallet.db'
        self.settings = SettingsManager(self.root / 'settings.json')
        self.settings.set_mine_open(False)
        for key, value in {'DB_WALLET': str(self.database), 'BACKUP_DIR': str(self.root / 'backups'), 'settings': self.settings}.items():
            p = patch.object(config, key, value)
            p.start()
            self.addCleanup(p.stop)
        wallet.initialize()
        wallet.claim(100, 10, True, 'mine')
        wallet.change(5, actor=100, request_id='grant', target=200, kind='grant')
        wallet.reset_claims(actor=100, request_id='reset')
        wallet.claim(100, 10, False, 'mine2')

    def contents(self, path=None):
        with closing(sqlite3.connect(path or self.database)) as db:
            return {t: db.execute(f'SELECT * FROM {t}').fetchall() for t in
                    ('wallets', 'mining_claims', 'wallet_ledger', 'mining_resets', 'mining_state')}

    def test_backup_matches_pre_wipe_and_db_is_fresh_and_reusable(self):
        before = self.contents()
        settings = self.settings.settings_file
        settings_bytes = Path(settings).read_bytes()
        asset = self.root / 'catalog.db'
        asset.write_bytes(b'unrelated assets')
        result = wallet.wipe(actor=100, request_id=1234)
        self.assertEqual(result['users'], 2)
        self.assertEqual(self.contents(result['backup']), before)
        after = self.contents()
        for t in ('wallets', 'mining_claims', 'wallet_ledger', 'mining_resets'):
            self.assertEqual(after[t], [])
        self.assertEqual(after['mining_state'], [(1, None)])
        self.assertEqual(Path(settings).read_bytes(), settings_bytes)
        self.assertEqual(asset.read_bytes(), b'unrelated assets')
        with closing(sqlite3.connect(self.database)) as db, db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 1)
        wallet.initialize()
        self.assertEqual(wallet.balance(100), (0, 0, 0))
        self.assertEqual(wallet.claim(100, 10, True, 'after'), 10)

    def test_backup_failure_preserves_every_table(self):
        before = self.contents()
        with patch('models.wallet.os.replace', side_effect=PermissionError('backup storage denied')):
            with self.assertRaises(PermissionError):
                wallet.wipe(actor=100, request_id=1234)
        self.assertEqual(self.contents(), before)

    def test_delete_failure_rolls_back_all_tables_and_keeps_backup(self):
        before = self.contents()
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("CREATE TRIGGER stop_delete BEFORE DELETE ON wallets BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            wallet.wipe(actor=100, request_id=1234)
        self.assertEqual(self.contents(), before)
        backups = list((self.root / 'backups').glob('wallet-wipe-*.db'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.contents(backups[0]), before)

    def test_open_mine_and_invalid_identity_do_not_wipe(self):
        before = self.contents()
        self.settings.set_mine_open(True)
        with self.assertRaisesRegex(ValueError, 'CLOSE'):
            wallet.wipe(actor=100, request_id=1234)
        with self.assertRaises(ValueError):
            wallet.wipe(actor=0, request_id=1234)
        self.assertEqual(self.contents(), before)
        self.assertFalse((self.root / 'backups').exists())


class WipeViewTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = Mock()
        self.service.wipe.return_value = {'users': 2, 'backup': '/backups/wallet-wipe-example.db'}

    def modal(self):
        session = WipeView(100, self.service)
        session.phase = 'final'
        modal = WipeModal(session)
        modal.confirmation._value = CONFIRMATION
        return session, modal

    async def test_both_stages_require_original_admin_target_guild_and_live_deadline(self):
        for phase in ('first', 'final'):
            session = WipeView(100, self.service)
            session.phase = phase
            stage = session if phase == 'first' else WipeModal(session)
            self.assertTrue(await stage.interaction_check(interaction(True)))
            self.assertFalse(await stage.interaction_check(interaction(False)))
            i = interaction(True)
            i.user.id = 200
            self.assertFalse(await stage.interaction_check(i))
            i = interaction(True)
            i.guild.id = 111
            self.assertFalse(await stage.interaction_check(i))
            session.deadline = 0
            self.assertFalse(await stage.interaction_check(interaction(True)))
        self.service.wipe.assert_not_called()

    async def test_first_confirmation_only_opens_modal_and_requires_closed_mine(self):
        view = WipeView(100, self.service)
        i = interaction(True)
        i.edit_original_response = AsyncMock()
        with patch.object(config, 'get_mine_open', return_value=True):
            await view.proceed.callback(i)
        i.response.send_modal.assert_not_awaited()
        with patch.object(config, 'get_mine_open', return_value=False):
            await view.proceed.callback(i)
        self.assertIsInstance(i.response.send_modal.call_args.args[0], WipeModal)
        self.assertEqual(view.phase, 'final')
        self.service.wipe.assert_not_called()

    async def test_cancel_wrong_phrase_and_expiry_never_execute(self):
        view = WipeView(100, self.service)
        await view.cancel.callback(interaction(True))
        self.assertEqual(view.phase, 'cancelled')
        session, modal = self.modal()
        modal.confirmation._value = '初期化'
        await modal.on_submit(interaction(True))
        self.assertEqual(session.phase, 'cancelled')
        session, modal = self.modal()
        session.deadline = 0
        await modal.on_submit(interaction(True))
        self.service.wipe.assert_not_called()

    async def test_final_submit_runs_once_even_for_concurrent_submissions(self):
        session, modal = self.modal()
        i = interaction(True)
        i.edit_original_response = AsyncMock()
        await asyncio.gather(modal.on_submit(i), modal.on_submit(interaction(True)))
        self.service.wipe.assert_called_once_with(actor=100, request_id=12345)
        self.assertEqual(session.phase, 'used')
        self.assertIn('バックアップ', i.edit_original_response.call_args.kwargs['content'])

    async def test_backup_error_is_reported_without_success_or_second_attempt(self):
        session, modal = self.modal()
        self.service.wipe.side_effect = PermissionError('backup denied')
        i = interaction(True)
        i.edit_original_response = AsyncMock()
        with self.assertLogs('views.wipe_view', level='ERROR'):
            await modal.on_submit(i)
        i.edit_original_response.assert_not_awaited()
        self.assertIn('完了できません', i.followup.send.call_args.args[0])
        await modal.on_submit(interaction(True))
        self.service.wipe.assert_called_once()
