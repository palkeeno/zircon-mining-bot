"""Export a consistent, read-only SQLite snapshot as UTF-8 CSV files."""
import csv
import io
import sqlite3
from contextlib import closing
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

TABLES = ('USERS', 'CLAIMS', 'LEDGER', 'WALLET_META', 'RESET_LOG')


def csv_value(value):
    # Spreadsheet applications must not execute text from the database as formulas.
    if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
        return "'" + value
    return value


def export_wallet(database):
    files = []
    uri = Path(database).resolve().as_uri() + '?mode=ro'
    with closing(sqlite3.connect(uri, uri=True)) as db:
        db.execute('BEGIN')
        for table in TABLES:
            cursor = db.execute(f'SELECT * FROM {table} ORDER BY rowid')
            output = io.StringIO(newline='')
            writer = csv.writer(output)
            writer.writerow([column[0] for column in cursor.description])
            for row in cursor:
                writer.writerow([csv_value(value) for value in row])
            files.append((f'wallet_{table.lower()}.csv', output.getvalue().encode('utf-8-sig')))
    return files


def package_exports(files, limit):
    """Prefer direct CSV downloads; compress only if an attachment exceeds the limit."""
    if all(len(data) <= limit for _, data in files):
        return files
    output = io.BytesIO()
    with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
        for name, data in files:
            archive.writestr(name, data)
    if output.tell() > limit:
        raise ValueError('CSVの容量がDiscordの添付上限を超えています。管理者がサーバー上のDBから取得してください。')
    return [('wallet_csv.zip', output.getvalue())]
