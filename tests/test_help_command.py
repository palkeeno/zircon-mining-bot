import unittest
from unittest.mock import Mock

import discord
from discord import app_commands

import test_mining_service
from commands.wallet_commands import register_commands
from commands.asset_commands import register_asset_commands
from test_wallet_ui import interaction


class HelpCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_help_is_private_and_matches_current_permissions_and_commands(self):
        client = discord.Client(intents=discord.Intents.none())
        tree = app_commands.CommandTree(client)
        service = Mock()
        register_commands(tree, service)
        register_asset_commands(tree, Mock())
        command = tree.get_command('help')
        self.assertTrue(command.guild_only)
        self.assertTrue(command.default_permissions.administrator)
        self.assertFalse(await command.checks[0](interaction(False)))
        self.assertTrue(await command.checks[0](interaction(True)))
        i = interaction(True)
        await command.callback(i)
        kwargs = i.response.send_message.call_args.kwargs
        self.assertTrue(kwargs['ephemeral'])
        embed = kwargs['embed']
        text = str(embed.to_dict())
        self.assertNotIn('/donate', text)
        self.assertNotIn('10件', text)
        self.assertNotIn('採掘する', text)
        self.assertLessEqual(len(embed), 6000)
        self.assertTrue(all(len(field.value) <= 1024 for field in embed.fields))
        for item in tree.walk_commands():
            if not isinstance(item, app_commands.Group) and item.qualified_name != 'donate':
                self.assertIn('/' + item.qualified_name, text)
        self.assertIn('残高・実績は保持', text)
        self.assertIn('確認2回', text)
        self.assertEqual(service.mock_calls, [])
