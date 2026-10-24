"""Persistent asset catalog and immutable media files, independent of wallets."""
import io
import json
import os
import random
import re
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, UnidentifiedImageError

KINDS = {'character': 'キャラクター', 'mining': '採掘演出', 'excellent': 'Excellent結果',
         'great': 'Great結果', 'good': 'Good結果'}
MAX_BYTES = 1_000_000
RECOMMENDED_BYTES = 500_000


def validate_image(data):
    if len(data) >= MAX_BYTES:
        raise ValueError('1MB以上の画像は登録できません。')
    try:
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            if width != height or width > 600:
                raise ValueError(f'画像は正方形・最大600×600pxです（現在 {width}×{height}px）。')
            image.load()  # Decode only the first frame; no extension or frame-count checks.
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValueError('画像を読み取れません。') from error
    return width, height, len(data) > RECOMMENDED_BYTES


@dataclass(frozen=True)
class Media:
    id: str
    name: str
    filename: str
    data: bytes


class AssetCatalog:
    def __init__(self, directory):
        self.root = Path(directory)
        self.database = self.root / 'catalog.db'

    @contextmanager
    def db(self, write=False):
        connection = sqlite3.connect(self.database, timeout=15)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self, source):
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / 'media').mkdir(exist_ok=True)
        with self.db(True) as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise RuntimeError('未対応のアセットDBです。')
            if not version:
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone():
                    raise RuntimeError('新規のアセット保存先を指定してください。')
                for statement in (
                    '''CREATE TABLE assets(id TEXT PRIMARY KEY,kind TEXT NOT NULL,
                       name TEXT NOT NULL,file_key TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,
                       revision INTEGER NOT NULL DEFAULT 1,width INTEGER NOT NULL,bytes INTEGER NOT NULL)''',
                    '''CREATE TABLE lines(id TEXT PRIMARY KEY,character_id TEXT NOT NULL REFERENCES assets(id)
                       ON DELETE CASCADE,text TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,
                       revision INTEGER NOT NULL DEFAULT 1)''',
                    'CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)',
                    'CREATE TABLE import_issues(file TEXT PRIMARY KEY,reason TEXT NOT NULL)',
                    '''CREATE TABLE history(id INTEGER PRIMARY KEY,actor_id INTEGER NOT NULL,
                       action TEXT NOT NULL,target_id TEXT NOT NULL,created_at TEXT NOT NULL)''',
                ):
                    db.execute(statement)
                db.execute('PRAGMA user_version=1')
            if not db.execute("SELECT 1 FROM meta WHERE key='seeded'").fetchone():
                self._seed(db, Path(source))
                db.execute("INSERT INTO meta VALUES('seeded','1')")

    def _seed(self, db, source):
        from consts.characters import CHARACTERS_LIST, CHARACTERS_MESSAGE
        entries = []
        for character in CHARACTERS_LIST:
            entries.append(('character', character['name'], source / 'assets_character' / f"{character['id']}.png",
                            CHARACTERS_MESSAGE[character['name']]))
        for path in sorted((source / 'assets').iterdir()):
            match = re.fullmatch(r'(mining|Excellent|Great|Good)[0-9]+\.(gif|png)', path.name)
            if match:
                entries.append((match[1].lower(), path.stem, path, []))
        for kind, name, path, lines in entries:
            try:
                data = path.read_bytes()
                width, _, _ = validate_image(data)
                key = self._write(data, path.name)
            except (ValueError, OSError) as error:
                db.execute('INSERT INTO import_issues VALUES (?,?)', (str(path.relative_to(source)), str(error)))
                continue
            asset_id = uuid.uuid4().hex
            db.execute('INSERT INTO assets(id,kind,name,file_key,width,bytes) VALUES (?,?,?,?,?,?)',
                       (asset_id, kind, name, key, width, len(data)))
            for text in lines:
                db.execute('INSERT INTO lines(id,character_id,text) VALUES (?,?,?)', (uuid.uuid4().hex, asset_id, text))

    def _write(self, data, filename):
        suffix = Path(filename).suffix.lower()
        if not re.fullmatch(r'\.[a-z0-9]{1,10}', suffix):
            suffix = '.img'
        key = uuid.uuid4().hex + suffix
        temporary = self.root / 'media' / (key + '.tmp')
        temporary.write_bytes(data)
        os.replace(temporary, self.root / 'media' / key)
        return key

    @staticmethod
    def _audit(db, actor, action, target):
        db.execute('INSERT INTO history(actor_id,action,target_id,created_at) VALUES (?,?,?,?)',
                   (actor, action, target, datetime.now(timezone.utc).isoformat()))

    @staticmethod
    def _ready(db):
        for kind in KINDS:
            query = 'SELECT 1 FROM assets a WHERE kind=? AND enabled=1'
            if kind == 'character':
                query += ' AND EXISTS(SELECT 1 FROM lines l WHERE l.character_id=a.id AND l.enabled=1)'
            if not db.execute(query, (kind,)).fetchone():
                raise ValueError(f'{KINDS[kind]}の有効な登録を最低1件残してください。')

    def upload(self, kind, name, filename, data, actor, target=None, dialogue=None, revision=None):
        if kind not in KINDS or not name.strip() or len(name) > 80:
            raise ValueError('種類と名前（1〜80文字）を確認してください。')
        if kind == 'character' and not target:
            self._text(dialogue)
        width, _, warning = validate_image(data)
        key = self._write(data, filename)
        old_key = None
        try:
            with self.db(True) as db:
                if target:
                    row = self._asset(db, target, revision)
                    if row['kind'] != kind:
                        raise ValueError('差し替え先の種類が一致しません。')
                    old_key = row['file_key']
                    db.execute('UPDATE assets SET name=?,file_key=?,width=?,bytes=?,revision=revision+1 WHERE id=?',
                               (name.strip(), key, width, len(data), target))
                    asset_id = target
                else:
                    asset_id = uuid.uuid4().hex
                    db.execute('INSERT INTO assets(id,kind,name,file_key,width,bytes) VALUES (?,?,?,?,?,?)',
                               (asset_id, kind, name.strip(), key, width, len(data)))
                    if kind == 'character':
                        db.execute('INSERT INTO lines(id,character_id,text) VALUES (?,?,?)',
                                   (uuid.uuid4().hex, asset_id, dialogue.strip()))
                self._audit(db, actor, 'replace' if target else 'create', asset_id)
        except Exception:
            (self.root / 'media' / key).unlink(missing_ok=True)
            raise
        if old_key:
            (self.root / 'media' / old_key).unlink(missing_ok=True)
        return asset_id, warning

    @staticmethod
    def _asset(db, asset_id, revision=None):
        row = db.execute('SELECT * FROM assets WHERE id=?', (asset_id,)).fetchone()
        if not row or revision is not None and row['revision'] != revision:
            raise ValueError('登録が削除・更新されました。一覧を開き直してください。')
        return row

    @staticmethod
    def _text(text):
        if not text or not text.strip() or len(text) > 2000:
            raise ValueError('セリフは1〜2000文字で入力してください。')

    def list(self, kind):
        with self.db() as db:
            return [dict(row) for row in db.execute('SELECT * FROM assets WHERE kind=? ORDER BY name,id', (kind,))]

    def lines(self, character):
        with self.db() as db:
            return [dict(row) for row in db.execute('SELECT * FROM lines WHERE character_id=? ORDER BY rowid', (character,))]

    def issues(self):
        with self.db() as db:
            return [dict(row) for row in db.execute('SELECT * FROM import_issues ORDER BY file')]

    def change(self, asset_id, actor, revision, *, name=None, enabled=None, delete=False):
        key = None
        with self.db(True) as db:
            row = self._asset(db, asset_id, revision)
            if delete:
                key = row['file_key']
                db.execute('DELETE FROM assets WHERE id=?', (asset_id,))
            elif name is not None:
                if not name.strip() or len(name) > 80:
                    raise ValueError('名前は1〜80文字で入力してください。')
                db.execute('UPDATE assets SET name=?,revision=revision+1 WHERE id=?', (name.strip(), asset_id))
            else:
                db.execute('UPDATE assets SET enabled=?,revision=revision+1 WHERE id=?', (int(enabled), asset_id))
            self._ready(db)
            self._audit(db, actor, 'delete' if delete else 'rename' if name is not None else 'visibility', asset_id)
        if key:
            (self.root / 'media' / key).unlink(missing_ok=True)

    def edit_line(self, character, actor, *, text=None, line_id=None, revision=None, enabled=None, delete=False):
        with self.db(True) as db:
            if self._asset(db, character)['kind'] != 'character':
                raise ValueError('キャラクターを選択してください。')
            if line_id:
                row = db.execute('SELECT * FROM lines WHERE id=? AND character_id=?', (line_id, character)).fetchone()
                if not row or row['revision'] != revision:
                    raise ValueError('セリフが削除・更新されました。一覧を開き直してください。')
                if delete:
                    db.execute('DELETE FROM lines WHERE id=?', (line_id,))
                elif text is not None:
                    self._text(text)
                    db.execute('UPDATE lines SET text=?,revision=revision+1 WHERE id=?', (text.strip(), line_id))
                else:
                    db.execute('UPDATE lines SET enabled=?,revision=revision+1 WHERE id=?', (int(enabled), line_id))
            else:
                self._text(text)
                line_id = uuid.uuid4().hex
                db.execute('INSERT INTO lines(id,character_id,text) VALUES (?,?,?)', (line_id, character, text.strip()))
            self._ready(db)
            self._audit(db, actor, 'line_delete' if delete else 'line_edit', line_id)
        return line_id

    def _media(self, row):
        return Media(row['id'], row['name'], row['file_key'], (self.root / 'media' / row['file_key']).read_bytes())

    def preview(self, asset_id):
        with self.db() as db:
            return self._media(self._asset(db, asset_id))

    def choose_media(self, kind):
        with self.db() as db:
            rows = db.execute('SELECT * FROM assets WHERE kind=? AND enabled=1', (kind,)).fetchall()
            if not rows:
                raise ValueError(f'{KINDS[kind]}がありません。')
            return self._media(random.choice(rows))

    def character(self, selection=None, exclude=None):
        with self.db() as db:
            rows = db.execute('''SELECT a.*,l.id AS line_id,l.text,l.revision AS line_revision
                FROM assets a JOIN lines l ON l.character_id=a.id
                WHERE a.kind='character' AND a.enabled=1 AND l.enabled=1 ORDER BY a.id,l.id''').fetchall()
            if not rows:
                raise ValueError('有効なキャラクターとセリフがありません。')
            chosen = next((r for r in rows if selection and r['id'] == selection.get('id')
                           and r['line_id'] == selection.get('line_id')), None)
            if chosen is None:
                candidates = [r for r in rows if r['id'] != exclude] or rows
                chosen = random.choice(candidates)  # One entry per line preserves contribution weighting.
            reference = {k: chosen[k] for k in ('id', 'line_id', 'revision', 'line_revision')}
            return reference, chosen['text'], self._media(chosen)

    def signature(self):
        with self.db() as db:
            return db.execute('SELECT COALESCE(MAX(id),0) FROM history').fetchone()[0]
