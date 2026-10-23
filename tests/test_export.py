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
        files = export_wallet(wallet.config.DB_USERS, ['RESET_LOG', 'USERS', 'USERS'])
        self.assertEqual([name for name, _ in files], ['wallet_users.csv', 'wallet_reset_log.csv'])
        for tables in ([], ['unknown'], ['USERS; DROP TABLE USERS']):
            with self.assertRaises(ValueError):
                export_wallet(wallet.config.DB_USERS, tables)

    def test_csv_snapshot_includes_headers_history_and_no_wallet_mutation(self):
        self.grant()
        wallet.reset_claims(actor=999, request_id='reset', now=self.now)
        before = Path(wallet.config.DB_USERS).read_bytes()
        files = dict(export_wallet(wallet.config.DB_USERS))
        self.assertEqual(len(files), 5)
        rows = list(csv.DictReader(io.StringIO(files['wallet_users.csv'].decode('utf-8-sig'))))
        self.assertEqual(rows[0]['userid'], '100')
        self.assertEqual(rows[0]['curr_total'], '20')
        resets = list(csv.DictReader(io.StringIO(files['wallet_reset_log.csv'].decode('utf-8-sig'))))
        self.assertEqual(resets[0]['actor'], '999')
        self.assertEqual(Path(wallet.config.DB_USERS).read_bytes(), before)


class ExportPackagingTests(unittest.TestCase):
    def test_direct_csv_zip_fallback_and_size_error(self):
        files = [('wallet_users.csv', b'a' * 10000)]
        self.assertEqual(package_exports(files, 20000), files)
        name, data = package_exports(files, 1000)[0]
        self.assertEqual(name, 'wallet_csv.zip')
        with ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual(archive.read('wallet_users.csv'), files[0][1])
        with self.assertRaises(ValueError):
            package_exports(files, 1)

    def test_missing_database_does_not_create_empty_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'absent.db'
            with self.assertRaises(Exception):
                export_wallet(path)
            self.assertFalse(path.exists())
