import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from PIL import Image
from consts.characters import CHARACTERS_LIST
from services.asset_catalog import AssetCatalog, validate_image


def picture(size=(20, 20)):
    output = io.BytesIO()
    Image.new('RGB', size, 'purple').save(output, format='PNG')
    return output.getvalue()


class AssetTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / 'source'
        for folder in ('assets', 'assets_character'):
            (self.source / folder).mkdir(parents=True)
        for char in CHARACTERS_LIST:
            (self.source / 'assets_character' / f"{char['id']}.png").write_bytes(picture())
        for name in ('mining1.gif', 'Excellent1.png', 'Great1.png', 'Good1.png'):
            (self.source / 'assets' / name).write_bytes(picture())
        self.catalog = AssetCatalog(self.root / 'store')
        self.catalog.initialize(self.source)

    def test_dimensions_and_decimal_size_boundaries_ignore_extension(self):
        for size in ((1, 1), (600, 600)):
            validate_image(picture(size))
        for size in ((601, 601), (200, 201)):
            with self.assertRaises(ValueError):
                validate_image(picture(size))
        data = picture()
        self.assertFalse(validate_image(data + b'\0' * (500000 - len(data)))[2])
        self.assertTrue(validate_image(data + b'\0' * (500001 - len(data)))[2])
        with self.assertRaises(ValueError):
            validate_image(data + b'\0' * (1000000 - len(data)))
        asset, _ = self.catalog.upload('good', '新画像', 'anything.xyz', data, 100)
        self.assertTrue(self.catalog.preview(asset).filename.endswith('.xyz'))

    def test_seed_is_once_and_invalid_original_is_reported_without_modifying_it(self):
        path = self.source / 'assets_character' / '0.png'
        path.write_bytes(picture((700, 700)))
        catalog = AssetCatalog(self.root / 'other')
        catalog.initialize(self.source)
        self.assertEqual(len(catalog.issues()), 1)
        self.assertEqual(path.read_bytes(), picture((700, 700)))
        row = catalog.list('good')[0]
        catalog.change(row['id'], 100, row['revision'], name='edited')
        catalog.initialize(self.source)
        self.assertEqual(catalog.list('good')[0]['name'], 'edited')

    def test_hide_restore_delete_and_last_pool_guard(self):
        row = self.catalog.list('good')[0]
        with self.assertRaises(ValueError):
            self.catalog.change(row['id'], 100, row['revision'], delete=True)
        extra, _ = self.catalog.upload('good', 'extra', 'x.png', picture(), 100)
        snapshot = self.catalog.preview(row['id'])
        self.catalog.change(row['id'], 100, row['revision'], enabled=False)
        self.assertEqual(self.catalog.choose_media('good').id, extra)
        self.catalog.change(row['id'], 100, row['revision'] + 1, enabled=True)
        self.catalog.change(row['id'], 100, row['revision'] + 2, delete=True)
        with self.assertRaises(ValueError):
            self.catalog.preview(row['id'])
        self.assertEqual(snapshot.data, picture())
        self.assertFalse((self.catalog.root / 'media' / snapshot.filename).exists())

    def test_character_line_weighting_and_cascade_permanent_delete(self):
        char, _ = self.catalog.upload('character', 'test', 'x.png', picture(), 100, dialogue='one')
        self.catalog.edit_line(char, 100, text='two')
        with patch('services.asset_catalog.random.choice', side_effect=lambda rows: next(r for r in rows if r['id'] == char)) as choose:
            self.catalog.character()
            self.assertEqual(sum(r['id'] == char for r in choose.call_args.args[0]), 2)
        row = next(r for r in self.catalog.list('character') if r['id'] == char)
        self.catalog.change(char, 100, row['revision'], delete=True)
        self.assertEqual(self.catalog.lines(char), [])
        with self.catalog.db() as db:
            self.assertFalse(db.execute('SELECT 1 FROM assets WHERE id=?', (char,)).fetchone())

    def test_stale_edits_are_rejected_and_selected_character_edits_are_visible(self):
        reference, text, media = self.catalog.character()
        self.catalog.change(media.id, 100, reference['revision'], name='changed')
        with self.assertRaises(ValueError):
            self.catalog.change(media.id, 100, reference['revision'], delete=True)
        self.assertEqual(self.catalog.character(reference)[2].name, 'changed')
        self.catalog.edit_line(media.id, 100, line_id=reference['line_id'],
                               revision=reference['line_revision'], text='new text')
        self.assertEqual(self.catalog.character(reference)[1], 'new text')

    def test_replacement_keeps_old_snapshot_and_rejects_wrong_kind(self):
        row = self.catalog.list('good')[0]
        snapshot = self.catalog.preview(row['id'])
        self.catalog.upload('good', 'changed', 'y.png', picture((30, 30)), 100,
                            target=row['id'], revision=row['revision'])
        self.assertEqual(snapshot.data, picture())
        self.assertEqual(self.catalog.preview(row['id']).data, picture((30, 30)))
        with self.assertRaises(ValueError):
            self.catalog.upload('great', 'wrong', 'y.png', picture(), 100, target=row['id'])

    def test_backup_restores_catalog_media_and_hidden_records_together(self):
        row = self.catalog.list('character')[0]
        self.catalog.change(row['id'], 100, row['revision'], enabled=False)
        filename = self.catalog.backup(self.root / 'backups')
        restored = self.root / 'restored'
        with ZipFile(filename) as archive:
            archive.extractall(restored)
        catalog = AssetCatalog(restored)
        self.assertEqual(catalog.list('character'), self.catalog.list('character'))
        self.assertEqual(catalog.preview(row['id']).data, self.catalog.preview(row['id']).data)

    def test_line_visibility_stale_edit_and_last_character_guard(self):
        character = self.catalog.list('character')[0]
        line = self.catalog.lines(character['id'])[0]
        self.catalog.edit_line(character['id'], 100, line_id=line['id'], revision=line['revision'], enabled=False)
        with self.assertRaises(ValueError):
            self.catalog.edit_line(character['id'], 100, line_id=line['id'], revision=line['revision'], delete=True)
        reference, _, _ = self.catalog.character({'id':character['id'], 'line_id':line['id']})
        self.assertNotEqual(reference['line_id'], line['id'])
        # Keep just one active character and one line; the final line cannot be removed.
        with self.catalog.db(True) as db:
            db.execute('UPDATE assets SET enabled=0 WHERE kind=?', ('character',))
            db.execute('UPDATE assets SET enabled=1 WHERE id=?', (character['id'],))
            db.execute('UPDATE lines SET enabled=0 WHERE character_id=?', (character['id'],))
            db.execute('UPDATE lines SET enabled=1 WHERE id=?', (line['id'],))
        with self.assertRaises(ValueError):
            self.catalog.edit_line(character['id'], 100, line_id=line['id'], revision=line['revision']+1, delete=True)
