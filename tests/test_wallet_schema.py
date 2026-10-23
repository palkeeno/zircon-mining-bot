import sqlite3
import unittest

from models.wallet_schema import initialize_schema


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.db.execute('PRAGMA foreign_keys=ON')
        with self.db:
            initialize_schema(self.db)

    def test_fresh_schema_defaults_and_restart_preserve_data(self):
        self.db.execute("INSERT INTO wallets(user_id,updated_at) VALUES(1,'now')")
        self.db.execute('UPDATE wallets SET balance=42 WHERE user_id=1')
        with self.db:
            initialize_schema(self.db)
        self.assertEqual(self.db.execute('SELECT user_id,balance,total_mined,mining_count,excellent_count FROM wallets').fetchone(),
                         (1, 42, 0, 0, 0))
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone(), (1,))

    def test_constraints_reject_invalid_counters_and_history(self):
        self.db.execute("INSERT INTO wallets(user_id,updated_at) VALUES(100,'now')")
        for column, value in [('balance', -1), ('balance', None), ('balance', 1.5),
                              ('total_mined', -1), ('mining_count', -1), ('excellent_count', 1)]:
            with self.subTest(column=column, value=value), self.assertRaises(sqlite3.IntegrityError):
                self.db.execute(f'UPDATE wallets SET {column}=? WHERE user_id=100', (value,))
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO mining_claims VALUES(999,'now',1)")
        for kind, source, target, amount in [('other', None, 100, 1), ('grant', 100, 100, 1),
                                             ('transfer', 100, 100, 1), ('grant', None, 100, 0)]:
            with self.subTest(kind=kind), self.assertRaises(sqlite3.IntegrityError):
                self.db.execute("INSERT INTO wallet_ledger VALUES('op',100,?,?,?,?, 'now')",
                                (source, target, amount, kind))

    def test_existing_unversioned_and_future_database_are_not_changed(self):
        for version in (0, 999):
            with sqlite3.connect(':memory:') as db:
                db.execute('CREATE TABLE old_data(value)')
                db.execute('INSERT INTO old_data VALUES(42)')
                db.execute(f'PRAGMA user_version={version}')
                with self.assertRaises(RuntimeError):
                    initialize_schema(db)
                self.assertEqual(db.execute('SELECT * FROM old_data').fetchall(), [(42,)])
                self.assertEqual(db.execute('PRAGMA user_version').fetchone(), (version,))
