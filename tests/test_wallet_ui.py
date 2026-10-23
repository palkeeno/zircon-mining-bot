from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
import unittest
import discord
import test_mining_service
from views.wallet_view import RankingView, MiningView, WalletView
from views.settings_view import SettingsView, ScheduleModal, TargetView, TreasuryView
from services import mining_service
import zrmine


def interaction(admin=False):
    return SimpleNamespace(
        id=12345, guild=SimpleNamespace(id=789, get_member=Mock(return_value=None)),
        client=SimpleNamespace(mining_guild_id=789),
        user=SimpleNamespace(id=100, roles=[], guild_permissions=SimpleNamespace(administrator=admin)),
        response=SimpleNamespace(send_message=AsyncMock(), edit_message=AsyncMock(), defer=AsyncMock(), is_done=Mock(return_value=False)),
        followup=SimpleNamespace(send=AsyncMock()),
    )


class UITests(unittest.IsolatedAsyncioTestCase):
    async def test_both_ranking_buttons_respond_ephemerally(self):
        with patch("views.wallet_view.wallet_service.ranking", return_value=[]):
            for callback in (WalletView().balances, WalletView().excellents):
                i = interaction()
                await callback.callback(i)
                self.assertTrue(i.response.send_message.call_args.kwargs["ephemeral"])

    async def test_invalid_schedule_is_not_saved(self):
        modal = ScheduleModal()
        modal.hours._value = "24"
        modal.minutes._value = "0"
        modal.limit._value = "1"
        with patch.object(zrmine.config.settings, "update") as save:
            await modal.on_submit(interaction(True))
        save.assert_not_called()

    async def test_schedule_saves_all_fields_together(self):
        modal = ScheduleModal()
        modal.hours._value = "12,0,12"
        modal.minutes._value = "30,0"
        modal.limit._value = "2"
        with patch.object(zrmine.config.settings, "update") as save:
            await modal.on_submit(interaction(True))
        save.assert_called_once_with({"announce_hour": [0, 12], "announce_minute": [0, 30], "mining_limit": 2})

    async def test_other_guild_cannot_access_wallet_or_commands(self):
        i = interaction(True)
        i.guild.id = 123
        self.assertFalse(await WalletView().interaction_check(i))
        self.assertFalse(await zrmine.tree.interaction_check(i))
        self.assertFalse(await SettingsView().interaction_check(i))

    async def test_successful_mine_reuses_exact_image_in_notification(self):
        i = interaction()
        i.user.display_name = "Alice"
        i.user.roles = []
        i.user.display_avatar = SimpleNamespace(url="https://example.com/avatar.png")
        message = SimpleNamespace(edit=AsyncMock())
        i.followup.send.return_value = message
        with patch.object(mining_service.config, "get_mine_open", return_value=True), \
             patch.object(mining_service, "has_mining_role", return_value=True), \
             patch.object(mining_service, "gacha", return_value={"id": 0, "msg": "Excellent", "zirnum": 10}), \
             patch.object(mining_service.wallet_service, "claim", return_value=42) as claim, \
             patch.object(mining_service.asyncio, "sleep", new=AsyncMock()), \
             patch.object(mining_service, "send_excellent_notification", new=AsyncMock()) as notify:
            await mining_service.mining_zircon(i, i.client)
        claim.assert_called_once_with(100, 10, True, i.id)
        self.assertTrue(i.response.defer.call_args.kwargs["ephemeral"])
        self.assertTrue(i.followup.send.call_args.kwargs["ephemeral"])
        result = message.edit.call_args.kwargs
        filename = result["attachments"][0].filename
        self.assertEqual(result["embed"].image.url, f"attachment://{filename}")
        self.assertIn("42", result["embed"].fields[0].value)
        notify.assert_awaited_once_with(i.client, i.user, None, filename)
        # Mocked HTTP calls do not close upload files automatically.
        result["attachments"][0].close()
        i.followup.send.call_args.kwargs["file"].close()

    async def test_persistent_views_and_ephemeral_balance(self):
        self.assertTrue(MiningView().is_persistent())
        view = WalletView()
        self.assertTrue(view.is_persistent())
        i = interaction()
        with patch("views.wallet_view.wallet_service.balance", return_value=(42, 3, 1)):
            await view.own.callback(i)
        self.assertTrue(i.response.send_message.call_args.kwargs["ephemeral"])
        self.assertIn("42", i.response.send_message.call_args.args[0])

    async def test_rank_pages_ten_entries_and_boundaries(self):
        rows = [(100 + n, n, n, n * 2) for n in range(21)]
        i = interaction()
        with patch("views.wallet_view.wallet_service.ranking", return_value=rows):
            view = RankingView(100, i.guild, "excellent")
        self.assertEqual(len(view.embed().description.splitlines()), 10)
        self.assertTrue(view.previous.disabled)
        await view.next.callback(i)
        self.assertIn("**11.**", view.embed().description)
        await view.next.callback(i)
        self.assertEqual(len(view.embed().description.splitlines()), 1)
        self.assertTrue(view.next.disabled)
        await view.previous.callback(i)
        self.assertEqual(view.page, 1)
        self.assertTrue(await view.interaction_check(i))
        i.user.id = 200
        self.assertFalse(await view.interaction_check(i))

    async def test_empty_rank_has_no_navigation(self):
        with patch("views.wallet_view.wallet_service.ranking", return_value=[]):
            view = RankingView(100, interaction().guild, "balance")
        self.assertTrue(view.next.disabled)
        self.assertTrue(view.previous.disabled)
        self.assertIn("データがありません", view.embed().description)

    async def test_balance_ranking_has_name_country_and_amount(self):
        member = SimpleNamespace(display_name="Alice", roles=[])
        guild = SimpleNamespace(get_member=Mock(return_value=member))
        with patch("views.wallet_view.wallet_service.ranking", return_value=[(100, 42, 1, 2)]), patch("views.wallet_view.get_country", return_value={"stmp": "🌟"}):
            view = RankingView(100, guild, "balance")
            self.assertIn("🌟 Alice：💎 42", view.embed().description)

    async def test_admin_commands_and_components_recheck_permissions(self):
        for command in (zrmine.add, zrmine.remove, zrmine.transfer, zrmine.settings):
            self.assertTrue(command.default_permissions.administrator)
            self.assertFalse(await command.checks[0](interaction(False)))
            self.assertTrue(await command.checks[0](interaction(True)))
        for component in (SettingsView(), TargetView(), TreasuryView(), ScheduleModal()):
            self.assertFalse(await component.interaction_check(interaction(False)))
            self.assertTrue(await component.interaction_check(interaction(True)))

    async def test_donation_uses_only_configured_treasury(self):
        countries = [dict(id=n, role=200 + n, name=f"Country{n}") for n in range(1, 5)]
        for country in countries:
            i = interaction()
            i.user.roles = [SimpleNamespace(id=country['role'])]
            with patch.object(zrmine.config, "COUNTRIES", countries), patch.object(zrmine.config, "get_treasury_user_id", side_effect=lambda n: 900 + n), patch.object(zrmine.wallet_service, "change") as transact:
                await zrmine.donate.callback(i, 8)
            transact.assert_called_once_with(8, actor=100, request_id=i.id, source=100, target=900 + country['id'], kind="donate")

    async def test_donation_rejects_ambiguous_membership_or_treasuries(self):
        countries = [dict(id=n, role=200 + n) for n in range(1, 5)]
        for role_ids, treasury in (([], 999), ([201, 202], 999), ([201], 0), ([201], 999)):
            i = interaction()
            i.user.roles = [SimpleNamespace(id=role_id) for role_id in role_ids]
            with patch.object(zrmine.config, "COUNTRIES", countries), patch.object(zrmine.config, "get_treasury_user_id", return_value=treasury), patch.object(zrmine.wallet_service, "change") as transact:
                await zrmine.donate.callback(i, 8)
            transact.assert_not_called()
            self.assertTrue(i.followup.send.call_args.kwargs['ephemeral'])

    async def test_excellent_uses_actual_result_image(self):
        user = SimpleNamespace(display_name="Alice", display_avatar=SimpleNamespace(url="https://example.com/avatar.png"))
        channel = SimpleNamespace(send=AsyncMock())
        with patch.object(mining_service, "get_channel", new=AsyncMock(return_value=channel)), patch.object(mining_service.discord, "File") as file:
            await mining_service.send_excellent_notification(Mock(), user, None, "Excellent2.png")
        self.assertEqual(file.call_args.kwargs["filename"], "Excellent2.png")
        self.assertEqual(channel.send.call_args.kwargs["embed"].thumbnail.url, "attachment://Excellent2.png")

    async def test_closed_or_missing_role_does_not_credit(self):
        for opened, role in ((False, True), (True, False)):
            i = interaction()
            with patch.object(mining_service.config, "get_mine_open", return_value=opened), patch.object(mining_service, "has_mining_role", return_value=role), patch.object(mining_service.wallet_service, "claim") as claim:
                await mining_service.mining_zircon(i, Mock())
            claim.assert_not_called()
            self.assertTrue(i.response.send_message.call_args.kwargs["ephemeral"])
