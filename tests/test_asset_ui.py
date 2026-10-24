import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from discord import app_commands
import discord
import test_assets
from test_wallet_ui import interaction
from commands.asset_commands import register_asset_commands
from views.assets_view import AssetsView, LinesView, TextModal, DeleteView


class AssetUITests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        fixture = test_assets.AssetTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.catalog = fixture.catalog

    async def test_admin_owner_and_guild_are_checked_on_views_and_modals(self):
        row = self.catalog.list('character')[0]
        views = [AssetsView(100, self.catalog), LinesView(100, self.catalog, row['id']),
                 TextModal(100, 'edit', 'old', lambda value: None), DeleteView(100, self.catalog, lambda: None)]
        for view in views:
            self.assertTrue(await view.interaction_check(interaction(True)))
            self.assertFalse(await view.interaction_check(interaction(False)))
            other = interaction(True)
            other.user.id = 200
            self.assertFalse(await view.interaction_check(other))
            other = interaction(True)
            other.guild.id = 111
            self.assertFalse(await view.interaction_check(other))

    async def test_pages_selection_and_explicit_permanent_delete_confirmation(self):
        view = AssetsView(100, self.catalog)
        self.assertEqual(len(view.items.options), 25)
        i = interaction(True)
        await view.next.callback(i)
        self.assertEqual(i.response.edit_message.call_args.kwargs['view'].page, 1)
        row = view.rows[0]
        view.items._values = [row['id']]
        await view.items.callback(i)
        await view.remove.callback(i)
        confirmation = i.response.send_message.call_args.kwargs['view']
        self.assertTrue(i.response.send_message.call_args.kwargs['ephemeral'])
        self.assertIsNotNone(self.catalog.preview(row['id']))
        i.edit_original_response = AsyncMock()
        await confirmation.confirm.callback(i)
        with self.assertRaises(ValueError):
            self.catalog.preview(row['id'])
        self.assertTrue(all(child.disabled for child in confirmation.children))

    async def test_text_form_saves_line_and_cancel_does_not_delete(self):
        row = self.catalog.list('character')[0]
        view = LinesView(100, self.catalog, row['id'])
        i = interaction(True)
        await view.add.callback(i)
        modal = i.response.send_modal.call_args.args[0]
        modal.value._value = 'new dialogue'
        await modal.on_submit(i)
        self.assertIn('new dialogue', [r['text'] for r in self.catalog.lines(row['id'])])
        deleted = []
        confirmation = DeleteView(100, self.catalog, lambda: deleted.append(True))
        await confirmation.cancel.callback(i)
        self.assertEqual(deleted, [])

    async def test_upload_rejects_large_before_download_and_warns_over_recommendation(self):
        client = discord.Client(intents=discord.Intents.none())
        tree = app_commands.CommandTree(client)
        register_asset_commands(tree, self.catalog)
        group = tree.get_command('assets')
        self.assertTrue(group.default_permissions.administrator)
        upload = group.get_command('upload')
        self.assertFalse(await upload.checks[0](interaction(False)))
        i = interaction(True)
        file = SimpleNamespace(size=1000000, filename='image.png', read=AsyncMock())
        kind = app_commands.Choice(name='Good', value='good')
        await upload.callback(i, kind, file)
        file.read.assert_not_awaited()
        data = test_assets.picture()
        file.size = 500001
        file.read.return_value = data + b'\0' * (500001-len(data))
        await upload.callback(i, kind, file, name='warning')
        self.assertIn('500KB以下', i.followup.send.call_args.args[0])
        self.assertTrue(i.followup.send.call_args.kwargs['ephemeral'])
