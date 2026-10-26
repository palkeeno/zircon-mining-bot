import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import discord
import test_mining_service
import config.config as config
from config.settings_manager import SettingsManager
from services.mining_service import get_excellent_channel_id
from test_wallet_ui import interaction
from views.settings_view import CountryExcellentView, SettingsView, TargetView, summary


class CountryExcellentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'settings.json'
        self.settings = SettingsManager(self.path)
        self.patch = patch.object(config, 'settings', self.settings)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def channel(self, i, channel_id=123):
        channel = Mock(spec=discord.TextChannel)
        channel.id = channel_id
        channel.guild = i.guild
        channel.permissions_for.return_value = SimpleNamespace(
            view_channel=True, send_messages=True, attach_files=True, embed_links=True)
        i.guild.me = object()
        i.guild.get_channel = Mock(return_value=channel)
        return channel

    async def test_independent_settings_persist_and_keep_environment_fallback(self):
        self.settings.set('excellent_chat', 777)
        for c in config.COUNTRIES:
            self.assertEqual(config.get_country_excellent_chat(c['id']), c['chid'])
        for c in config.COUNTRIES:
            config.set_country_excellent_chat(c['id'], 1000 + c['id'])
        with patch.object(config, 'settings', SettingsManager(self.path)):
            for c in config.COUNTRIES:
                self.assertEqual(get_excellent_channel_id(c), 1000 + c['id'])
            self.assertEqual(get_excellent_channel_id(None), 777)
        config.set_country_excellent_chat(1, 2001)
        self.assertEqual(config.get_country_excellent_chat(2), 1002)
        self.assertEqual(config.get_excellent_chat(), 777)

    async def test_invalid_keys_and_ids_do_not_modify_settings(self):
        before = self.path.read_bytes()
        for country, channel in ((5, 100), (1, 0), (1, -1)):
            with self.assertRaises(ValueError):
                config.set_country_excellent_chat(country, channel)
        self.assertEqual(self.path.read_bytes(), before)

    async def test_button_opens_private_view_and_all_countries_save_independently(self):
        i = interaction(True)
        await SettingsView().country_excellent.callback(i)
        view = i.response.send_message.call_args.kwargs['view']
        self.assertTrue(i.response.send_message.call_args.kwargs['ephemeral'])
        self.assertEqual([s.country_id for s in view.children], [1, 2, 3, 4])
        for select in view.children:
            channel = self.channel(i, 1000 + select.country_id)
            select._values = [SimpleNamespace(id=channel.id)]
            await select.callback(i)
            self.assertEqual(config.get_country_excellent_chat(select.country_id), channel.id)
            self.assertIn(f'<#{channel.id}>', i.response.edit_message.call_args.kwargs['content'])
        self.assertLessEqual(len(summary()), 2000)

    async def test_missing_permissions_or_unusable_channel_do_not_save(self):
        for permission in ('view_channel', 'send_messages', 'attach_files', 'embed_links', None, 'foreign', 'missing', 'voice'):
            i = interaction(True)
            channel = self.channel(i)
            if permission == 'foreign':
                channel.guild = SimpleNamespace(id=111)
            elif permission == 'missing':
                i.guild.get_channel.return_value = None
            elif permission == 'voice':
                i.guild.get_channel.return_value = Mock(spec=discord.VoiceChannel)
            elif permission is None:
                channel.permissions_for.return_value = None
            else:
                setattr(channel.permissions_for.return_value, permission, False)
            select = CountryExcellentView().children[0]
            select._values = [SimpleNamespace(id=123)]
            await select.callback(i)
            self.assertIsNone(self.settings.get('country_excellent_chats'))
            self.assertTrue(i.response.send_message.call_args.kwargs['ephemeral'])

    async def test_new_view_requires_administrator_and_target_guild(self):
        view = CountryExcellentView()
        self.assertTrue(await view.interaction_check(interaction(True)))
        self.assertFalse(await view.interaction_check(interaction(False)))
        i = interaction(True)
        i.guild.id = 111
        self.assertFalse(await view.interaction_check(i))

    async def test_unaffiliated_picker_still_saves_its_own_destination(self):
        i = interaction(True)
        self.channel(i)
        select = TargetView().excellent_channel
        select._values = [SimpleNamespace(id=123)]
        await select.callback(i)
        self.assertEqual(config.get_excellent_chat(), 123)
        self.assertIsNone(self.settings.get('country_excellent_chats'))
