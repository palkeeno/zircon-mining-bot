"""Maintain Discord panels in place; rotate the host once per mining period."""
import asyncio
from contextlib import closing
from pathlib import Path

import discord

import config.config as config
from consts.characters import get_random_character
from models import wallet
from services.mining_service import get_channel
from views.wallet_view import MiningView, WalletView

panel_lock = asyncio.Lock()


def character_embed(character):
    filename = f"{character['id']}.png"
    embed = discord.Embed(description=character['messages'])
    embed.set_author(name=character['name'], icon_url=f"attachment://{filename}")
    embed.set_thumbnail(url=f"attachment://{filename}")
    return embed, Path(config.CWD) / 'assets_character' / filename


async def ensure_panels(client, *, force=True):
    async with panel_lock:
        config.settings.load_settings()
        period = wallet.current_period()
        changed = config.settings.get('mining_panel_period') != period
        if not force and not changed and all(config.settings.get(k) for k in ('mining_message_id', 'wallet_message_id')):
            return
        character = config.settings.get('mining_panel_character')
        if not character or config.settings.get('mining_character_period') != period:
            character = get_random_character(exclude_id=character['id'] if character else None)
            # Persist the choice before HTTP so failed edits and restarts retry the same host.
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
                embed, path = character_embed(character)
                with closing(discord.File(path, filename=path.name)) as image:
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
        config.settings.set('mining_panel_period', period)
