"""Persistent mining and personal zircon wallet bot."""
import logging
import os

import discord
from discord import app_commands
from commands.wallet_commands import register_commands
from commands.asset_commands import register_asset_commands
from discord.ext import tasks

import config.config as config
from models import wallet
from services.runtime import wallet_service, asset_catalog
from utils.backup import perform_backup, create_backup
from services.access import require_guild
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
        asset_catalog.initialize(config.CWD)
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


register_commands(tree, wallet_service)
register_asset_commands(tree, asset_catalog)

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
