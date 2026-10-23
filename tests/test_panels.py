import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord
import test_mining_service
from config.settings_manager import SettingsManager
from consts.characters import CHARACTERS_LIST, get_random_character
from services import panel_service as panels


class PanelTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.settings = SettingsManager(Path(temporary.name) / 'settings.json')
        self.settings.update({'mining_message_id': 100, 'wallet_message_id': 200})
        self.message = SimpleNamespace(id=100, edit=AsyncMock())
        self.channel = SimpleNamespace(fetch_message=AsyncMock(return_value=self.message),
                                       send=AsyncMock(return_value=self.message))
        for target, attr, value in (
            (panels.config, 'settings', self.settings),
            (panels.wallet, 'current_period', Mock(return_value='2026-10-23T12:00:00+09:00')),
            (panels, 'get_channel', AsyncMock(return_value=self.channel)),
        ):
            patcher = patch.object(target, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    async def test_period_rotates_character_in_place_and_restart_keeps_choice(self):
        await panels.ensure_panels(Mock())
        first = self.settings.get('mining_panel_character')
        await panels.ensure_panels(Mock(), force=False)
        self.assertEqual(self.channel.fetch_message.await_count, 2)
        await panels.ensure_panels(Mock())
        self.assertEqual(self.settings.get('mining_panel_character'), first)
        panels.wallet.current_period.return_value = '2026-10-24T00:00:00+09:00'
        await panels.ensure_panels(Mock(), force=False)
        self.assertNotEqual(self.settings.get('mining_panel_character')['id'], first['id'])
        self.channel.send.assert_not_awaited()
        self.channel.fetch_message.assert_awaited_with(100)
        self.assertEqual(self.settings.get('mining_message_id'), 100)

    async def test_missing_panels_are_recreated_but_forbidden_is_not(self):
        self.channel.fetch_message.side_effect = discord.NotFound(SimpleNamespace(status=404, reason='not found'), '')
        await panels.ensure_panels(Mock())
        self.assertEqual(self.channel.send.await_count, 2)
        self.channel.send.reset_mock()
        self.channel.fetch_message.side_effect = discord.Forbidden(SimpleNamespace(status=403, reason='forbidden'), '')
        with self.assertRaises(discord.Forbidden):
            await panels.ensure_panels(Mock())
        self.channel.send.assert_not_awaited()

    async def test_failed_edit_retries_same_character_without_marking_period_done(self):
        self.message.edit.side_effect = OSError('offline')
        with self.assertRaises(OSError):
            await panels.ensure_panels(Mock())
        first = self.settings.get('mining_panel_character')
        self.assertIsNone(self.settings.get('mining_panel_period'))
        self.message.edit.side_effect = None
        await panels.ensure_panels(Mock(), force=False)
        self.assertEqual(self.settings.get('mining_panel_character'), first)

    def test_embed_uses_character_name_dialogue_and_same_image_for_both_slots(self):
        for character in CHARACTERS_LIST:
            self.assertTrue((Path(panels.config.CWD) / 'assets_character' / f"{character['id']}.png").is_file())
        character = get_random_character()
        embed, path = panels.character_embed(character)
        self.assertEqual(embed.author.name, character['name'])
        self.assertEqual(embed.description, character['messages'])
        self.assertEqual(embed.author.icon_url, embed.thumbnail.url)
        self.assertEqual(embed.thumbnail.url, f'attachment://{path.name}')
