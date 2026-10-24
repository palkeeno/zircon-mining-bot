"""Asset administration is separate from mining settings."""
import asyncio
from pathlib import Path

import discord
from discord import app_commands

from services.asset_catalog import KINDS, MAX_BYTES
from views.assets_view import AssetsView


def register_asset_commands(tree, catalog):
    group = app_commands.Group(name='assets', description='画像・キャラクター・セリフの管理',
                               guild_only=True, default_permissions=discord.Permissions(administrator=True))

    def administrator():
        async def check(interaction):
            return bool(interaction.guild and interaction.user.guild_permissions.administrator)
        return app_commands.check(check)

    @group.command(name='manage', description='アセット管理画面を開きます')
    @administrator()
    async def manage(interaction: discord.Interaction):
        view = AssetsView(interaction.user.id, catalog)
        await interaction.response.send_message(view.text(), view=view, ephemeral=True)

    @group.command(name='upload', description='画像を追加・差し替えます。新規キャラには最初のセリフを指定してください')
    @app_commands.choices(kind=[app_commands.Choice(name=label, value=key) for key, label in KINDS.items()])
    @app_commands.describe(kind='登録先の種類', file='正方形・最大600px・1MB未満（500KB以下推奨）',
                           name='登録名。差し替えでは省略すると現在名を維持', target='差し替え先。新規追加では空欄',
                           dialogue='新規キャラクターの最初のセリフ（既存キャラへの追加は管理画面から）')
    @administrator()
    async def upload(interaction: discord.Interaction, kind: app_commands.Choice[str], file: discord.Attachment,
                     name: str = None, target: str = None, dialogue: str = None):
        await interaction.response.defer(ephemeral=True)
        if file.size >= MAX_BYTES:
            await interaction.followup.send('1MB以上の画像は登録できません。', ephemeral=True)
            return
        row = None
        if target:
            row = next((r for r in catalog.list(kind.value) if r['id'] == target), None)
            if row is None:
                await interaction.followup.send('差し替え先を選択し直してください。', ephemeral=True)
                return
        label = name or (row['name'] if row else Path(file.filename).stem)
        try:
            data = await file.read()
            asset_id, warning = await asyncio.to_thread(catalog.upload, kind.value, label, file.filename,
                data, interaction.user.id, target=target, dialogue=dialogue,
                revision=row['revision'] if row else None)
        except ValueError as error:
            await interaction.followup.send(str(error), ephemeral=True)
            return
        text = f'登録しました：{label}\nID：`{asset_id}`'
        if warning:
            text += f'\n⚠ {len(data)/1000:.1f}KBです。表示速度のため500KB以下を推奨します。'
        view = AssetsView(interaction.user.id, catalog, kind.value)
        await interaction.followup.send(text, view=view, ephemeral=True)

    @upload.autocomplete('target')
    async def targets(interaction, current):
        if (not interaction.guild or interaction.guild.id != getattr(interaction.client, 'mining_guild_id', None)
                or not interaction.user.guild_permissions.administrator):
            return []
        kind = getattr(interaction.namespace, 'kind', '')
        kind = getattr(kind, 'value', kind)
        return [app_commands.Choice(name=row['name'][:100], value=row['id'])
                for row in catalog.list(kind) if current.casefold() in row['name'].casefold()][:25]

    tree.add_command(group)
