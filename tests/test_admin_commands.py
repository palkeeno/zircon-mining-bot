import unittest
from unittest.mock import AsyncMock, Mock, patch
from discord import app_commands

import test_mining_service
from test_wallet_ui import interaction
from commands.wallet_commands import register_commands


class AdminCommandTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # A fresh command tree avoids any live client or registration.
        import discord
        self.client = discord.Client(intents=discord.Intents.none())
        self.tree = app_commands.CommandTree(self.client)
        self.service = Mock()
        register_commands(self.tree, self.service)

    async def test_new_commands_have_runtime_admin_checks_and_default_permissions(self):
        for name in ('resetmining', 'exportwallet'):
            command = self.tree.get_command(name)
            self.assertTrue(command.default_permissions.administrator)
            self.assertTrue(command.guild_only)
            self.assertFalse(await command.checks[0](interaction(False)))
            self.assertTrue(await command.checks[0](interaction(True)))

    async def test_reset_refreshes_panel_and_reports_partial_failure_without_reset_retry(self):
        i = interaction(True)
        with patch('commands.wallet_commands.ensure_panels', new=AsyncMock(side_effect=OSError('offline'))):
            with self.assertLogs('commands.wallet_commands', level='ERROR'):
                await self.tree.get_command('resetmining').callback(i)
        self.service.reset.assert_called_once_with(actor=i.user.id, request_id=i.id)
        self.assertIn('リセットしました', i.followup.send.call_args.args[0])
        self.assertTrue(i.followup.send.call_args.kwargs['ephemeral'])

    async def test_export_returns_csv_files_ephemerally_and_closes_them(self):
        i = interaction(True)
        i.guild.filesize_limit = 100000
        self.service.export.return_value = [('wallet_users.csv', b'userid,balance\r\n100,42\r\n')]
        captured = []
        async def receive(*args, **kwargs):
            self.assertTrue(kwargs['ephemeral'])
            self.assertEqual(kwargs['files'][0].filename, 'wallet_users.csv')
            captured.append(kwargs['files'][0].fp.read())
        i.followup.send.side_effect = receive
        await self.tree.get_command('exportwallet').callback(i)
        self.service.export.assert_called_once_with(100000)
        self.assertEqual(captured, [self.service.export.return_value[0][1]])
        self.assertTrue(i.followup.send.call_args.kwargs['files'][0].fp.closed)
