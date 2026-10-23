"""Persistent mining and personal zircon wallet bot."""
import logging
import os

import discord
from discord import app_commands
from discord.ext import tasks

import config.config as config
from models import wallet
from services.runtime import wallet_service
from utils.backup import perform_backup, create_backup
from services.access import require_guild
from views.settings_view import SettingsView, summary
from views.wallet_view import MiningView, WalletView
from services.panel_service import ensure_panels

log = logging.getLogger(__name__)


class MiningClient(discord.Client):
    async def setup_hook(self):
        channel = await self.fetch_channel(config.CHID_MINING)
        self.mining_guild_id = channel.guild.id
        if config.GUILD_ID and self.mining_guild_id != config.GUILD_ID:
            raise RuntimeError("CHID_MINING is outside the configured GUILD_ID")
        create_backup()
        wallet.initialize()
        self.add_view(MiningView())
        self.add_view(WalletView())
        if config.GUILD_ID:
            guild = discord.Object(id=config.GUILD_ID)
            tree.copy_global_to(guild=guild)
            await tree.sync(guild=guild)
        else:
            await tree.sync()


intents = discord.Intents.default()
intents.members = True
client = MiningClient(intents=intents, allowed_mentions=discord.AllowedMentions.none())
class MiningTree(app_commands.CommandTree):
    async def interaction_check(self, interaction):
        return await require_guild(interaction)


tree = MiningTree(client)


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
        wallet_service.change(amount, actor=interaction.user.id, request_id=interaction.id,
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
        receipt = wallet_service.donate(actor=interaction.user.id,
                                        roles={role.id for role in interaction.user.roles},
                                        amount=amount, request_id=interaction.id)
    except ValueError as error:
        await interaction.followup.send(str(error), ephemeral=True)
        return
    await interaction.followup.send(
        f"{receipt.country}の国庫（<@{receipt.target}>）へ {receipt.amount:,} 💎 寄付しました。", ephemeral=True)


@tree.error
async def command_error(interaction, error):
    if isinstance(error, app_commands.CheckFailure):
        message = "この操作には管理者権限が必要です。"
    else:
        log.error("Command failed", exc_info=(type(error), error, error.__traceback__))
        message = "処理に失敗しました。管理者ログを確認してください。"
    sender = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
    await sender(message, ephemeral=True)


@client.event
async def on_ready():
    try:
        await ensure_panels(client)
    except Exception:
        log.exception("常設投稿の確認に失敗しました。/settings から復旧できます。")
    if not schedule_backup.is_running():
        schedule_backup.start()
    if not refresh_panels.is_running():
        refresh_panels.start()
    log.info("Ready")


@tasks.loop(seconds=5)
async def refresh_panels():
    try:
        await ensure_panels(client, force=False)
    except Exception:
        log.exception("採掘パネルの更新に失敗しました。次の確認時に再試行します。")


@tasks.loop(hours=24)
async def schedule_backup():
    try:
        perform_backup()
    except Exception:
        log.exception("バックアップ失敗")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    os.chdir(config.CWD)
    client.run(config.DISCORD_TOKEN)
