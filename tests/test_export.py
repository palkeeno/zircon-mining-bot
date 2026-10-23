import csv
import io
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

import test_wallet
from models import wallet
from services.wallet_export import export_wallet, package_exports


class ExportTests(unittest.TestCase):
    setUp = test_wallet.WalletTests.setUp
    grant = test_wallet.WalletTests.grant

    def test_only_selected_tables_are_exported_and_invalid_selections_are_rejected(self):
        files = export_wallet(wallet.config.DB_WALLET, ['mining_resets', 'wallets', 'wallets'])
        self.assertEqual([name for name, _ in files], ['wallets.csv', 'mining_resets.csv'])
        for tables in ([], ['unknown'], ['wallets; DROP TABLE wallets']):
            with self.assertRaises(ValueError):
                export_wallet(wallet.config.DB_WALLET, tables)

    def test_csv_snapshot_includes_headers_history_and_no_wallet_mutation(self):
        self.grant()
        wallet.reset_claims(actor=999, request_id='reset', now=self.now)
        before = Path(wallet.config.DB_WALLET).read_bytes()
        files = dict(export_wallet(wallet.config.DB_WALLET))
        self.assertEqual(len(files), 5)
        rows = list(csv.DictReader(io.StringIO(files['wallets.csv'].decode('utf-8-sig'))))
        self.assertEqual(rows[0]['user_id'], '100')
        self.assertEqual(rows[0]['balance'], '20')
        resets = list(csv.DictReader(io.StringIO(files['mining_resets.csv'].decode('utf-8-sig'))))
        self.assertEqual(resets[0]['actor_id'], '999')
        self.assertEqual(Path(wallet.config.DB_WALLET).read_bytes(), before)


class ExportPackagingTests(unittest.TestCase):
    def test_direct_csv_zip_fallback_and_size_error(self):
        files = [('wallets.csv', b'a' * 10000)]
        self.assertEqual(package_exports(files, 20000), files)
        name, data = package_exports(files, 1000)[0]
        self.assertEqual(name, 'wallet_csv.zip')
        with ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual(archive.read('wallets.csv'), files[0][1])
        with self.assertRaises(ValueError):
            package_exports(files, 1)

    def test_missing_database_does_not_create_empty_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'absent.db'
            with self.assertRaises(Exception):
                export_wallet(path)
            self.assertFalse(path.exists())
