"""Discord slash-command adapter; wallet policy lives in WalletService."""
import asyncio
import io
import logging
from contextlib import ExitStack

import discord
from discord import app_commands

from services.panel_service import ensure_panels
from views.settings_view import SettingsView, summary

log = logging.getLogger(__name__)


def register_commands(tree, service):
    def administrator():
        async def predicate(interaction):
            return bool(interaction.guild and interaction.user.guild_permissions.administrator)
        return app_commands.check(predicate)


    @tree.command(name="settings", description="採掘Botの設定を確認・変更します")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @administrator()
    async def settings(interaction: discord.Interaction):
        await interaction.response.send_message(summary(), view=SettingsView(), ephemeral=True)


    async def transact(interaction, amount, source=None, target=None, kind="transfer", success_message=None):
        await interaction.response.defer(ephemeral=True)
        try:
            service.change(amount, actor=interaction.user.id, request_id=interaction.id,
                          source=source, target=target, kind=kind)
        except ValueError as error:
            await interaction.followup.send(str(error), ephemeral=True)
            return
        await interaction.followup.send(success_message or f"{amount:,} 💎 の操作が完了しました。", ephemeral=True)


    @tree.command(name="add", description="指定ユーザーにジルコンを付与します")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @administrator()
    async def add(interaction: discord.Interaction, user: discord.Member, amount: app_commands.Range[int, 1, 1000000000]):
        await transact(interaction, amount, target=user.id, kind="grant")


    @tree.command(name="remove", description="指定ユーザーのジルコンを引き去ります")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @administrator()
    async def remove(interaction: discord.Interaction, user: discord.Member, amount: app_commands.Range[int, 1, 1000000000]):
        await transact(interaction, amount, source=user.id, kind="remove")


    @tree.command(name="transfer", description="ユーザー間でジルコンを転送します（管理者専用）")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @administrator()
    async def transfer(interaction: discord.Interaction, source: discord.Member, target: discord.Member,
                       amount: app_commands.Range[int, 1, 1000000000]):
        await transact(interaction, amount, source=source.id, target=target.id)


    @tree.command(name="donate", description="所属国の国庫にジルコンを寄付します")
    @app_commands.guild_only()
    async def donate(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 1000000000]):
        await interaction.response.defer(ephemeral=True)
        try:
            receipt = service.donate(actor=interaction.user.id,
                                            roles={role.id for role in interaction.user.roles},
                                            amount=amount, request_id=interaction.id)
        except ValueError as error:
            await interaction.followup.send(str(error), ephemeral=True)
            return
        await interaction.followup.send(
            f"{receipt.country}の国庫（<@{receipt.target}>）へ {receipt.amount:,} 💎 寄付しました。", ephemeral=True)


    @tree.command(name='resetmining', description='全員の採掘回数を今すぐリセットします（残高・実績は維持）')
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @administrator()
    async def resetmining(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            await asyncio.to_thread(service.reset, actor=interaction.user.id, request_id=interaction.id)
        except ValueError as error:
            await interaction.followup.send(str(error), ephemeral=True)
            return
        try:
            await ensure_panels(interaction.client, force=False)
        except Exception:
            log.exception('Manual reset succeeded, but the panel refresh failed')
            await interaction.followup.send('採掘回数をリセットしました。パネル更新は自動で再試行します。', ephemeral=True)
            return
        await interaction.followup.send('全員の採掘回数をリセットし、採掘パネルを更新しました。残高・実績は保持しています。', ephemeral=True)

    @tree.command(name='exportwallet', description='walletデータベースをCSVでダウンロードします')
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @administrator()
    async def exportwallet(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            files = await asyncio.to_thread(service.export, interaction.guild.filesize_limit)
        except ValueError as error:
            await interaction.followup.send(str(error), ephemeral=True)
            return
        with ExitStack() as stack:
            attachments = []
            for name, data in files:
                stream = stack.enter_context(io.BytesIO(data))
                attachment = discord.File(stream, filename=name)
                stack.callback(attachment.close)
                attachments.append(attachment)
            await interaction.followup.send('walletデータベースのCSVです。Discord IDは文字列として読み込んでください。',
                                            files=attachments, ephemeral=True)

    @tree.error
    async def command_error(interaction, error):
        if isinstance(error, app_commands.CheckFailure):
            message = "この操作には管理者権限が必要です。"
        else:
            log.error("Command failed", exc_info=(type(error), error, error.__traceback__))
            message = "処理に失敗しました。管理者ログを確認してください。"
        sender = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
        await sender(message, ephemeral=True)
