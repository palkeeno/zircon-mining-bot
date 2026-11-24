"""Maintain Discord panels and publish a new mining panel at each reset."""
import asyncio
from datetime import datetime

import discord
import emoji

import config.config as config
from services.runtime import wallet_service, asset_catalog
from services.asset_delivery import media_file
from services.mining_service import get_channel
from views.wallet_view import MiningView, WalletView

panel_lock = asyncio.Lock()


def character_embed(text, media):
    embed = discord.Embed(description=emoji.emojize(text, language='alias'))
    embed.set_author(name=media.name, icon_url=f'attachment://{media.filename}')
    embed.set_thumbnail(url=f'attachment://{media.filename}')
    return embed


async def find_reposted_panel(channel, bot_id, old_id, button_id):
    # A send may succeed on Discord without returning a response to the bot.
    async for candidate in channel.history(after=discord.Object(id=old_id), limit=None, oldest_first=False):
        if candidate.author.id == bot_id and any(
                getattr(component, 'custom_id', None) == button_id
                for row in candidate.components for component in row.children):
            return candidate
    return None


async def ensure_panels(client, *, force=True):
    async with panel_lock:
        config.settings.load_settings()
        period = wallet_service.current_period()
        signature = asset_catalog.signature()
        previous_period = config.settings.get('mining_panel_period')
        reset = previous_period is not None and period > previous_period
        changed = (previous_period != period
                   or config.settings.get('mining_asset_signature') != signature)
        if not force and not changed and all(config.settings.get(k) for k in ('mining_message_id', 'wallet_message_id')):
            return
        previous = config.settings.get('mining_panel_character')
        same_period = config.settings.get('mining_character_period') == period
        character, text, media = asset_catalog.character(
            previous if same_period else None,
            exclude=previous.get('id') if previous and not same_period else None)
        config.settings.update({'mining_panel_character': character, 'mining_character_period': period})
        channel = await get_channel(client, config.CHID_MINING)
        for key, view in (('mining_message_id', MiningView()), ('wallet_message_id', WalletView())):
            if key == 'wallet_message_id' and not force and config.settings.get(key):
                continue
            message = None
            message_id = config.settings.get(key)
            if message_id:
                message_id = int(message_id)
                try:
                    message = await channel.fetch_message(message_id)
                except discord.NotFound:
                    pass
                # Forbidden/network errors propagate; they never trigger duplicate posts.
            if key == 'mining_message_id':
                if reset and message is None and message_id:
                    message = await find_reposted_panel(channel, client.user.id, message_id, view.mine.custom_id)
                    if message and message.id >= discord.utils.time_snowflake(datetime.fromisoformat(period)):
                        reset = False
                embed = character_embed(text, media)
                # setup_hook registers the persistent handler for all mining messages.
                # Serialize the button without retaining a handler for every repost.
                view.stop()
                with media_file(media) as image:
                    if reset and message:
                        try:
                            await message.delete()
                        except discord.NotFound:
                            pass
                        message = None
                    if message:
                        await message.edit(embed=embed, attachments=[image], view=view)
                    else:
                        role_id = config.settings.get('mining_reset_mention_role')
                        role = channel.guild.get_role(role_id) if reset and role_id else None
                        content = None
                        mentions = discord.AllowedMentions.none()
                        if role and not role.is_default():
                            content = role.mention
                            mentions.roles = [role]
                        message = await channel.send(content=content, allowed_mentions=mentions,
                                                     embed=embed, file=image, view=view)
                config.settings.update({
                    key: message.id,
                    'mining_panel_period': period,
                    'mining_asset_signature': signature,
                })
            else:
                text = '💎 保有数・ランキング\n結果は操作した本人にだけ表示されます。'
                if message:
                    await message.edit(content=text, view=view)
                else:
                    message = await channel.send(content=text, view=view)
                config.settings.set(key, message.id)
