"""Administrator-only selection and download of wallet information."""
import asyncio
import io
from contextlib import ExitStack

import discord

from views.wallet_view import SafeView


EXPORT_OPTIONS = (
    ('wallets', '保有数・採掘実績', 'ユーザーごとのジルコン残高・採掘回数・Excellent回数'),
    ('mining_claims', '期間内の採掘回数', 'ユーザーごとに記録されている採掘期間と使用回数'),
    ('wallet_ledger', 'ジルコンの増減履歴', '採掘・付与・引き去り・転送・寄付の操作履歴'),
    ('mining_state', '採掘リセットの現在状態', '現在の手動リセット期間'),
    ('mining_resets', '手動リセットの履歴', '手動リセットの実行者・実行日時'),
)


class ExportView(SafeView):
    def __init__(self, owner, service):
        super().__init__(timeout=180)
        self.owner = owner
        self.service = service
        self.selected = []
        self.choose.options = [discord.SelectOption(value=value, label=label, description=description)
                               for value, label, description in EXPORT_OPTIONS]

    async def interaction_check(self, interaction):
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id != self.owner or not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message('この操作はコマンドを実行した管理者のみ利用できます。', ephemeral=True)
            return False
        return True

    @discord.ui.select(placeholder='ダウンロードする情報を選択（複数選択可）', min_values=1, max_values=5)
    async def choose(self, interaction, select):
        self.selected = list(select.values)
        for option in select.options:
            option.default = option.value in self.selected
        self.download.disabled = not self.selected
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label='選択した情報をダウンロード', style=discord.ButtonStyle.primary, disabled=True)
    async def download(self, interaction, button):
        if not self.selected:
            await interaction.response.send_message('ダウンロードする情報を選択してください。', ephemeral=True)
            return
        selected = tuple(self.selected)
        await interaction.response.defer(ephemeral=True)
        try:
            files = await asyncio.to_thread(self.service.export, interaction.guild.filesize_limit, selected)
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
            await interaction.followup.send('選択した情報のCSVです。Discord IDは文字列として読み込んでください。',
                                            files=attachments, ephemeral=True)
