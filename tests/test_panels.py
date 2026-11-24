import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord
import emoji
import test_mining_service
from config.settings_manager import SettingsManager
from services.asset_catalog import Media
import test_assets
from services import panel_service as panels


class PanelTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        fixture = test_assets.AssetTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.catalog = fixture.catalog
        self.settings = SettingsManager(Path(temporary.name) / 'settings.json')
        self.settings.update({'mining_message_id': 100, 'wallet_message_id': 200})
        self.message = SimpleNamespace(id=100, edit=AsyncMock(), delete=AsyncMock())
        self.new_message = SimpleNamespace(id=101, edit=AsyncMock())
        self.channel = SimpleNamespace(fetch_message=AsyncMock(return_value=self.message),
                                       send=AsyncMock(return_value=self.new_message),
                                       guild=SimpleNamespace(get_role=Mock(return_value=None)))
        self.history = []

        async def channel_history(**kwargs):
            for message in self.history:
                yield message

        self.channel.history = Mock(side_effect=channel_history)
        for target, attr, value in (
            (panels.config, 'settings', self.settings),
            (panels, 'asset_catalog', self.catalog),
            (panels.wallet_service, 'current_period', Mock(return_value='2026-10-23T12:00:00+09:00')),
            (panels, 'get_channel', AsyncMock(return_value=self.channel)),
        ):
            patcher = patch.object(target, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    async def test_reset_replaces_panel_and_same_period_restart_keeps_it(self):
        await panels.ensure_panels(Mock())
        first = self.settings.get('mining_panel_character')
        await panels.ensure_panels(Mock(), force=False)
        self.assertEqual(self.channel.fetch_message.await_count, 2)
        await panels.ensure_panels(Mock())
        self.assertEqual(self.settings.get('mining_panel_character'), first)
        self.channel.send.assert_not_awaited()
        panels.wallet_service.current_period.return_value = '2026-10-24T00:00:00+09:00'
        async def send_after_delete(**kwargs):
            self.message.delete.assert_awaited_once()
            return self.new_message

        self.channel.send.side_effect = send_after_delete
        await panels.ensure_panels(Mock(), force=False)
        self.assertNotEqual(self.settings.get('mining_panel_character')['id'], first['id'])
        self.channel.send.assert_awaited_once()
        self.assertIsNone(self.channel.send.call_args.kwargs['content'])
        self.assertEqual(self.channel.send.call_args.kwargs['allowed_mentions'].to_dict(), {'parse': []})
        self.channel.fetch_message.assert_awaited_with(100)
        self.assertEqual(self.settings.get('mining_message_id'), self.new_message.id)

    async def test_reset_mentions_only_configured_role_and_wallet_failure_does_not_repeat_it(self):
        await panels.ensure_panels(Mock())
        role = SimpleNamespace(id=789, mention='<@&789>', is_default=Mock(return_value=False))
        self.settings.set('mining_reset_mention_role', role.id)
        self.channel.guild.get_role.return_value = role
        self.channel.fetch_message.side_effect = [
            self.message, OSError('wallet offline'), self.new_message, self.message,
        ]
        panels.wallet_service.current_period.return_value = '2026-10-23T13:00:00.000001+09:00'
        with self.assertRaisesRegex(OSError, 'wallet offline'):
            await panels.ensure_panels(Mock())
        await panels.ensure_panels(Mock())
        self.channel.send.assert_awaited_once()
        request = self.channel.send.call_args.kwargs
        self.assertEqual(request['content'], role.mention)
        self.assertEqual(request['allowed_mentions'].to_dict(), {'roles': [role.id], 'parse': []})
        self.new_message.edit.assert_awaited_once()
        self.assertNotIn('content', self.new_message.edit.call_args.kwargs)

    async def test_reset_does_not_post_until_old_panel_is_deleted(self):
        await panels.ensure_panels(Mock())
        panels.wallet_service.current_period.return_value = '2026-10-24T00:00:00+09:00'
        self.message.delete.side_effect = OSError('offline')
        with self.assertRaises(OSError):
            await panels.ensure_panels(Mock(), force=False)
        self.channel.send.assert_not_awaited()
        self.assertEqual(self.settings.get('mining_message_id'), self.message.id)

        self.message.delete.side_effect = None
        self.channel.send.side_effect = OSError('offline')
        with self.assertRaises(OSError):
            await panels.ensure_panels(Mock(), force=False)
        selected = self.settings.get('mining_panel_character')

        self.channel.send.side_effect = None
        self.channel.fetch_message.side_effect = discord.NotFound(
            SimpleNamespace(status=404, reason='not found'), '')
        await panels.ensure_panels(Mock(), force=False)
        self.assertEqual(self.settings.get('mining_panel_character'), selected)
        self.assertEqual(self.settings.get('mining_message_id'), self.new_message.id)
        self.assertEqual(self.message.delete.await_count, 2)

    async def test_reset_recovers_a_post_when_discord_response_was_lost(self):
        client = SimpleNamespace(user=SimpleNamespace(id=789))
        await panels.ensure_panels(client)
        period = '2026-10-24T00:00:00+09:00'
        panels.wallet_service.current_period.return_value = period
        self.channel.send.side_effect = OSError('response lost')
        with self.assertRaises(OSError):
            await panels.ensure_panels(client, force=False)

        new_id = discord.utils.time_snowflake(datetime.fromisoformat(period)) + 1
        self.new_message.id = new_id
        self.new_message.author = client.user
        button = SimpleNamespace(custom_id='mining_zircon')
        self.new_message.components = [SimpleNamespace(children=[button])]
        self.history = [self.new_message]
        self.channel.fetch_message.side_effect = discord.NotFound(
            SimpleNamespace(status=404, reason='not found'), '')
        await panels.ensure_panels(client, force=False)

        self.channel.send.assert_awaited_once()
        self.new_message.edit.assert_awaited_once()
        self.assertEqual(self.settings.get('mining_message_id'), new_id)
        self.assertEqual(self.settings.get('mining_panel_period'), period)

    async def test_missing_panels_are_recreated_but_forbidden_is_not(self):
        self.settings.set('mining_reset_mention_role', 789)
        self.channel.fetch_message.side_effect = discord.NotFound(SimpleNamespace(status=404, reason='not found'), '')
        await panels.ensure_panels(Mock())
        self.assertEqual(self.channel.send.await_count, 2)
        self.channel.guild.get_role.assert_not_called()
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
        media = Media('char', 'name', 'image.png', b'image')
        embed = panels.character_embed('hello :moon:', media)
        self.assertEqual(embed.author.name, media.name)
        self.assertEqual(embed.description, emoji.emojize('hello :moon:', language='alias'))
        self.assertEqual(embed.author.icon_url, embed.thumbnail.url)
        self.assertEqual(embed.thumbnail.url, 'attachment://image.png')

    async def test_asset_edit_updates_current_panel_without_period_reset(self):
        await panels.ensure_panels(Mock())
        reference = self.settings.get('mining_panel_character')
        self.catalog.change(reference['id'], 100, reference['revision'], name='changed')
        self.message.edit.reset_mock()
        await panels.ensure_panels(Mock(), force=False)
        self.assertEqual(self.message.edit.call_args.kwargs['embed'].author.name, 'changed')
        self.assertEqual(self.settings.get('mining_panel_period'), '2026-10-23T12:00:00+09:00')
