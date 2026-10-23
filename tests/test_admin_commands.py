import unittest
from unittest.mock import AsyncMock, Mock, patch
from discord import app_commands

import test_mining_service
from test_wallet_ui import interaction
from commands.wallet_commands import register_commands
from views.export_view import ExportView


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
        await self.tree.get_command('exportwallet').callback(i)
        view = i.response.send_message.call_args.kwargs['view']
        self.assertTrue(i.response.send_message.call_args.kwargs['ephemeral'])
        self.service.export.assert_not_called()
        self.assertTrue(view.download.disabled)
        view.choose._values = ['wallets']
        await view.choose.callback(i)
        self.assertFalse(view.download.disabled)
        self.service.export.return_value = [('wallets.csv', b'user_id,balance\r\n100,42\r\n')]
        captured = []
        async def receive(*args, **kwargs):
            self.assertTrue(kwargs['ephemeral'])
            self.assertEqual(kwargs['files'][0].filename, 'wallets.csv')
            captured.append(kwargs['files'][0].fp.read())
        i.followup.send.side_effect = receive
        await view.download.callback(i)
        self.service.export.assert_called_once_with(100000, ('wallets',))
        self.assertEqual(captured, [self.service.export.return_value[0][1]])
        self.assertTrue(i.followup.send.call_args.kwargs['files'][0].fp.closed)

    async def test_export_selection_requires_original_admin_in_target_guild(self):
        view = ExportView(100, self.service)
        self.assertTrue(await view.interaction_check(interaction(True)))
        self.assertFalse(await view.interaction_check(interaction(False)))
        other = interaction(True)
        other.user.id = 200
        self.assertFalse(await view.interaction_check(other))
        other = interaction(True)
        other.guild.id = 999
        self.assertFalse(await view.interaction_check(other))

    async def test_export_multiple_selection_and_empty_guard(self):
        view = ExportView(100, self.service)
        i = interaction(True)
        i.guild.filesize_limit = 100000
        await view.download.callback(i)
        self.service.export.assert_not_called()
        view.choose._values = ['wallets', 'wallet_ledger']
        await view.choose.callback(i)
        self.assertEqual([o.value for o in view.choose.options if o.default], ['wallets', 'wallet_ledger'])
        self.assertTrue(all('.csv' not in o.label for o in view.choose.options))
        self.service.export.return_value = [('wallets.csv', b'users'), ('wallet_ledger.csv', b'ledger')]
        await view.download.callback(i)
        self.service.export.assert_called_once_with(100000, ('wallets', 'wallet_ledger'))
        self.assertEqual(len(i.followup.send.call_args.kwargs['files']), 2)
