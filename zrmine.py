"""Persistent mining and personal zircon wallet bot."""
import logging
import os

import discord
from discord import app_commands
from discord.ext import tasks

import config.config as config
from models import wallet
from utils.backup import perform_backup, create_backup
from services.access import require_guild
from views.settings_view import SettingsView, summary
from views.wallet_view import MiningView, WalletView, ensure_panels

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


@tree.command(name="zmsettings", description="採掘Botの設定を確認・変更します")
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
@administrator()
async def settings(interaction: discord.Interaction):
    await interaction.response.send_message(summary(), view=SettingsView(), ephemeral=True)


async def transact(interaction, amount, source=None, target=None, kind="transfer"):
    await interaction.response.defer(ephemeral=True)
    try:
        wallet.change(amount, actor=interaction.user.id, request_id=interaction.id,
                      source=source, target=target, kind=kind)
    except ValueError as error:
        await interaction.followup.send(str(error), ephemeral=True)
        return
    await interaction.followup.send(f"{amount:,} 💎 の操作が完了しました。", ephemeral=True)


@tree.command(name="zmadd", description="指定ユーザーにジルコンを付与します")
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
@administrator()
async def add(interaction: discord.Interaction, user: discord.Member, amount: app_commands.Range[int, 1, 1000000000]):
    await transact(interaction, amount, target=user.id, kind="grant")


@tree.command(name="zmremove", description="指定ユーザーのジルコンを引き去ります")
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
@administrator()
async def remove(interaction: discord.Interaction, user: discord.Member, amount: app_commands.Range[int, 1, 1000000000]):
    await transact(interaction, amount, source=user.id, kind="remove")


@tree.command(name="zmtransfer", description="ユーザー間でジルコンを転送します（管理者専用）")
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
@administrator()
async def transfer(interaction: discord.Interaction, source: discord.Member, target: discord.Member,
                   amount: app_commands.Range[int, 1, 1000000000]):
    await transact(interaction, amount, source=source.id, target=target.id)


@tree.command(name="zmdonate", description="設定された国庫にジルコンを寄付します")
@app_commands.guild_only()
async def donate(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 1000000000]):
    config.settings.load_settings()
    treasury = config.get_treasury_user_id()
    if not treasury:
        await interaction.response.send_message("寄付先の国庫が未設定です。管理者にお問い合わせください。", ephemeral=True)
        return
    await transact(interaction, amount, source=interaction.user.id, target=treasury, kind="donate")


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
        log.exception("常設投稿の確認に失敗しました。/zmsettings から復旧できます。")
    if not schedule_backup.is_running():
        schedule_backup.start()
    log.info("Ready")


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
