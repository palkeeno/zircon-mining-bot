"""Private, owner-bound administration for media and character dialogue."""
import asyncio
import io
import logging

import discord

from services.asset_catalog import KINDS
from services.asset_delivery import media_file
from views.wallet_view import SafeView
from services.access import require_guild

log = logging.getLogger(__name__)


async def allowed(interaction, owner):
    if not await require_guild(interaction):
        return False
    if interaction.user.id != owner or not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message('この画面は開いた管理者のみ操作できます。', ephemeral=True)
        return False
    return True


class AdminView(SafeView):
    def __init__(self, owner, catalog):
        super().__init__(timeout=300)
        self.owner, self.catalog = owner, catalog

    async def interaction_check(self, interaction):
        return await allowed(interaction, self.owner)


async def perform(interaction, view, action):
    await interaction.response.defer(ephemeral=True)
    try:
        await asyncio.to_thread(action)
    except ValueError as error:
        await interaction.followup.send(str(error), ephemeral=True)
        return
    await interaction.followup.send('保存しました。表示中の採掘パネルは自動更新されます。', ephemeral=True)


class TextModal(discord.ui.Modal):
    def __init__(self, owner, title, value, action, *, long=False):
        super().__init__(title=title)
        self.owner, self.action = owner, action
        self.value = discord.ui.TextInput(label='セリフ' if long else '名前', default=value,
                                         max_length=2000 if long else 80,
                                         style=discord.TextStyle.paragraph if long else discord.TextStyle.short)
        self.add_item(self.value)

    async def interaction_check(self, interaction):
        return await allowed(interaction, self.owner)

    async def on_submit(self, interaction):
        await perform(interaction, self, lambda: self.action(str(self.value)))

    async def on_error(self, interaction, error):
        log.error('Asset form failed', exc_info=(type(error), error, error.__traceback__))
        sender = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
        await sender('保存できませんでした。管理者ログを確認してください。', ephemeral=True)


class DeleteView(AdminView):
    def __init__(self, owner, catalog, action):
        super().__init__(owner, catalog)
        self.action = action

    @discord.ui.button(label='完全削除する（復元不可）', style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        await interaction.response.defer(ephemeral=True)
        try:
            await asyncio.to_thread(self.action)
        except ValueError as error:
            await interaction.followup.send(str(error), ephemeral=True)
            return
        for child in self.children:
            child.disabled = True
        await interaction.edit_original_response(content='DBから完全削除しました。', view=self)
        self.stop()

    @discord.ui.button(label='キャンセル')
    async def cancel(self, interaction, button):
        await interaction.response.edit_message(content='削除をキャンセルしました。', view=None)
        self.stop()


class AssetsView(AdminView):
    def __init__(self, owner, catalog, kind='character', page=0):
        super().__init__(owner, catalog)
        self.kind, self.page, self.selected = kind, page, None
        self.category.options = [discord.SelectOption(label=label, value=kind, default=kind == self.kind)
                                 for kind, label in KINDS.items()]
        self.load()

    def load(self):
        self.rows = self.catalog.list(self.kind)
        self.page = min(self.page, max(0, (len(self.rows) - 1) // 25))
        self.items.options = [discord.SelectOption(label=('表示中：' if r['enabled'] else '非表示：') + r['name'],
                                                   value=r['id'], description=f"{r['width']}×{r['width']}px / {r['bytes']/1000:.1f}KB")
                              for r in self.rows[self.page * 25:(self.page + 1) * 25]] or [discord.SelectOption(label='登録なし', value='none')]
        self.items.disabled = not self.rows
        self.previous.disabled = self.page == 0
        self.next.disabled = (self.page + 1) * 25 >= len(self.rows)
        for button in (self.preview, self.rename, self.visibility, self.remove, self.dialogue):
            button.disabled = self.selected is None
        self.dialogue.disabled = self.selected is None or self.kind != 'character'

    def text(self):
        selected = f"\n選択中：{self.selected['name']}\nID：`{self.selected['id']}`" if self.selected else ''
        return (f"アセット管理：{KINDS[self.kind]}（{len(self.rows)}件、{self.page+1}ページ）{selected}\n"
                '画像追加・差し替え：`/assets upload`（差し替え先は名前で検索できます）\n'
                '編集後は「一覧を更新」で最新状態を取得してください。無操作5分で終了します。')

    @discord.ui.select(placeholder='管理する種類', row=0)
    async def category(self, interaction, select):
        view = AssetsView(self.owner, self.catalog, select.values[0])
        await interaction.response.edit_message(content=view.text(), view=view)

    @discord.ui.select(placeholder='画像・キャラクターを選択', row=1)
    async def items(self, interaction, select):
        self.selected = next((r for r in self.rows if r['id'] == select.values[0]), None)
        self.load()
        for option in self.items.options:
            option.default = option.value == select.values[0]
        await interaction.response.edit_message(content=self.text(), view=self)

    async def navigate(self, interaction, page):
        view = AssetsView(self.owner, self.catalog, self.kind, page)
        await interaction.response.edit_message(content=view.text(), view=view)

    @discord.ui.button(label='前へ', row=2)
    async def previous(self, interaction, button):
        await self.navigate(interaction, self.page - 1)

    @discord.ui.button(label='次へ', row=2)
    async def next(self, interaction, button):
        await self.navigate(interaction, self.page + 1)

    @discord.ui.button(label='プレビュー', row=2)
    async def preview(self, interaction, button):
        await interaction.response.defer(ephemeral=True)
        try:
            media = await asyncio.to_thread(self.catalog.preview, self.selected['id'])
        except ValueError as error:
            await interaction.followup.send(str(error), ephemeral=True)
            return
        with media_file(media) as file:
            embed = discord.Embed(title=media.name)
            embed.set_image(url=f'attachment://{media.filename}')
            await interaction.followup.send(embed=embed, file=file, ephemeral=True)

    @discord.ui.button(label='名前を編集', row=2)
    async def rename(self, interaction, button):
        row = dict(self.selected)
        await interaction.response.send_modal(TextModal(self.owner, '名前を編集', row['name'],
            lambda value: self.catalog.change(row['id'], self.owner, row['revision'], name=value)))

    @discord.ui.button(label='表示／非表示', row=2)
    async def visibility(self, interaction, button):
        row = dict(self.selected)
        await perform(interaction, self, lambda: self.catalog.change(
            row['id'], self.owner, row['revision'], enabled=not row['enabled']))

    @discord.ui.button(label='完全削除', row=3, style=discord.ButtonStyle.danger)
    async def remove(self, interaction, button):
        row = dict(self.selected)
        view = DeleteView(self.owner, self.catalog, lambda: self.catalog.change(
            row['id'], self.owner, row['revision'], delete=True))
        await interaction.response.send_message(
            f"「{row['name']}」をDBから完全削除します。キャラのセリフも削除されます。復元できません。", view=view, ephemeral=True)

    @discord.ui.button(label='セリフ管理', row=3)
    async def dialogue(self, interaction, button):
        view = LinesView(self.owner, self.catalog, self.selected['id'])
        await interaction.response.send_message(view.text(), view=view, ephemeral=True)

    @discord.ui.button(label='一覧を更新', row=3)
    async def refresh(self, interaction, button):
        await self.navigate(interaction, self.page)

    @discord.ui.button(label='取り込み対象外の一覧', row=3)
    async def issues(self, interaction, button):
        await interaction.response.defer(ephemeral=True)
        rows = await asyncio.to_thread(self.catalog.issues)
        text = '\n'.join(f"{r['file']}: {r['reason']}" for r in rows) or '対象外の画像はありません。'
        with io.BytesIO(text.encode('utf-8-sig')) as stream:
            file = discord.File(stream, filename='asset-import-report.txt')
            try:
                await interaction.followup.send(f'初回取り込み対象外：{len(rows)}件。元ファイルは変更していません。', file=file, ephemeral=True)
            finally:
                file.close()


class LinesView(AdminView):
    def __init__(self, owner, catalog, character, page=0):
        super().__init__(owner, catalog)
        self.character, self.page, self.selected = character, page, None
        self.rows = catalog.lines(character)
        self.page = min(page, max(0, (len(self.rows)-1)//25))
        self.items.options = [discord.SelectOption(label=('表示中：' if r['enabled'] else '非表示：')+r['text'][:80], value=r['id'])
                              for r in self.rows[self.page*25:(self.page+1)*25]] or [discord.SelectOption(label='セリフなし', value='none')]
        self.items.disabled = not self.rows
        self.previous.disabled = self.page == 0
        self.next.disabled = (self.page+1)*25 >= len(self.rows)
        for button in (self.edit, self.visibility, self.remove):
            button.disabled = True

    def text(self):
        return f'セリフ管理：{len(self.rows)}件 / {self.page+1}ページ\n編集後は一覧を更新してください。'

    @discord.ui.select(placeholder='セリフを選択', row=0)
    async def items(self, interaction, select):
        self.selected = next(r for r in self.rows if r['id'] == select.values[0])
        for button in (self.edit, self.visibility, self.remove):
            button.disabled = False
        for option in select.options:
            option.default = option.value == self.selected['id']
        await interaction.response.edit_message(content=self.text()+'\n選択：'+self.selected['text'][:1800], view=self)

    async def navigate(self, interaction, page):
        view = LinesView(self.owner, self.catalog, self.character, page)
        await interaction.response.edit_message(content=view.text(), view=view)

    @discord.ui.button(label='前へ', row=1)
    async def previous(self, interaction, button):
        await self.navigate(interaction, self.page-1)

    @discord.ui.button(label='次へ', row=1)
    async def next(self, interaction, button):
        await self.navigate(interaction, self.page+1)

    @discord.ui.button(label='セリフ追加', row=1)
    async def add(self, interaction, button):
        await interaction.response.send_modal(TextModal(self.owner, 'セリフ追加', '',
            lambda value: self.catalog.edit_line(self.character, self.owner, text=value), long=True))

    @discord.ui.button(label='編集', row=1)
    async def edit(self, interaction, button):
        row = dict(self.selected)
        await interaction.response.send_modal(TextModal(self.owner, 'セリフ編集', row['text'],
            lambda value: self.catalog.edit_line(self.character, self.owner, text=value,
                                                line_id=row['id'], revision=row['revision']), long=True))

    @discord.ui.button(label='表示／非表示', row=1)
    async def visibility(self, interaction, button):
        row = dict(self.selected)
        await perform(interaction, self, lambda: self.catalog.edit_line(self.character, self.owner,
            line_id=row['id'], revision=row['revision'], enabled=not row['enabled']))

    @discord.ui.button(label='完全削除', row=2, style=discord.ButtonStyle.danger)
    async def remove(self, interaction, button):
        row = dict(self.selected)
        view = DeleteView(self.owner, self.catalog, lambda: self.catalog.edit_line(self.character, self.owner,
            line_id=row['id'], revision=row['revision'], delete=True))
        await interaction.response.send_message('選択したセリフをDBから完全削除します。復元できません。', view=view, ephemeral=True)

    @discord.ui.button(label='一覧を更新', row=2)
    async def refresh(self, interaction, button):
        await self.navigate(interaction, self.page)
