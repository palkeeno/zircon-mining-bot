"""Maintain Discord panels in place; rotate the host once per mining period."""
import asyncio

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


async def ensure_panels(client, *, force=True):
    async with panel_lock:
        config.settings.load_settings()
        period = wallet_service.current_period()
        signature = asset_catalog.signature()
        changed = (config.settings.get('mining_panel_period') != period
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
            if config.settings.get(key):
                try:
                    message = await channel.fetch_message(int(config.settings.get(key)))
                except discord.NotFound:
                    pass
                # Forbidden/network errors propagate; they never trigger duplicate posts.
            if key == 'mining_message_id':
                embed = character_embed(text, media)
                with media_file(media) as image:
                    if message:
                        await message.edit(content=None, embed=embed, attachments=[image], view=view)
                    else:
                        message = await channel.send(embed=embed, file=image, view=view)
            else:
                text = '💎 保有数・ランキング\n結果は操作した本人にだけ表示されます。'
                if message:
                    await message.edit(content=text, view=view)
                else:
                    message = await channel.send(content=text, view=view)
            config.settings.set(key, message.id)
        config.settings.update({'mining_panel_period': period, 'mining_asset_signature': signature})
