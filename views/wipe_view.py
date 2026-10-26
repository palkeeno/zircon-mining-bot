"""Two explicit confirmations before clearing the wallet, never assets/settings."""
import asyncio
import logging
import time
from pathlib import Path

import discord

import config.config as config
from views.wallet_view import SafeView

log = logging.getLogger(__name__)
CONFIRMATION = '全員のウォレットを初期化する'


class WipeView(SafeView):
    def __init__(self, owner, service):
        super().__init__(timeout=180)
        self.owner, self.service = owner, service
        self.deadline = time.monotonic() + 180
        self.phase = 'first'

    @staticmethod
    def warning():
        return ('**確認1/2：本当にウォレットDBをまっさらにしますか？**\n'
                '全員（4か国の国庫を含む）の残高・累計獲得量・採掘回数・Excellent実績・'
                '増減履歴・手動リセット履歴を削除し、採掘権を初期状態に戻します。\n'
                'キャラ・画像・セリフ、Bot設定、国庫の指定、常設投稿は保持します。\n'
                '先に `/settings` でCLOSEにし、進行中の採掘の完了を待ってください。\n'
                '次の最終確認で確認文を入力するまで初期化しません。'
                '実行前バックアップに失敗した場合も初期化しません。\n'
                '**この確認は3分で失効します。**')

    async def allowed(self, interaction, phase):
        if not await super().interaction_check(interaction):
            return False
        if interaction.user.id != self.owner or not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message('コマンドを実行した管理者本人のみ操作できます。', ephemeral=True)
            return False
        if self.phase != phase or time.monotonic() >= self.deadline:
            await interaction.response.send_message('確認は終了・失効しています。必要なら /wipewallet を開き直してください。', ephemeral=True)
            return False
        return True

    async def interaction_check(self, interaction):
        return await self.allowed(interaction, 'first')

    @discord.ui.button(label='確認1/2：内容を理解して最終確認へ', style=discord.ButtonStyle.danger)
    async def proceed(self, interaction, button):
        if config.get_mine_open():
            await interaction.response.send_message('先に /settings で採掘をCLOSEにしてください。', ephemeral=True)
            return
        self.phase = 'final'
        await interaction.response.send_modal(WipeModal(self))
        await interaction.edit_original_response(content='最終確認の入力待ちです。フォームを閉じれば初期化されません。', view=None)
        self.stop()

    @discord.ui.button(label='キャンセル')
    async def cancel(self, interaction, button):
        self.phase = 'cancelled'
        await interaction.response.edit_message(content='初期化をキャンセルしました。データは変更していません。', view=None)
        self.stop()


class WipeModal(discord.ui.Modal):
    def __init__(self, session):
        super().__init__(title='確認2/2：本当にまっさらにしますか？', timeout=180)
        self.session = session
        self.confirmation = discord.ui.TextInput(label=f'「{CONFIRMATION}」と入力', max_length=60,
                                                placeholder=CONFIRMATION)
        self.add_item(self.confirmation)

    async def interaction_check(self, interaction):
        return await self.session.allowed(interaction, 'final')

    async def on_submit(self, interaction):
        if not await self.session.allowed(interaction, 'final'):
            return
        if str(self.confirmation) != CONFIRMATION:
            self.session.phase = 'cancelled'
            await interaction.response.send_message('確認文が一致しません。初期化しません。必要なら /wipewallet を開き直してください。', ephemeral=True)
            return
        # Consume before yielding: even concurrent submissions cannot wipe again.
        self.session.phase = 'used'
        await interaction.response.defer(ephemeral=True)
        try:
            receipt = await asyncio.to_thread(self.session.service.wipe,
                                             actor=interaction.user.id, request_id=interaction.id)
        except ValueError as error:
            await interaction.followup.send(str(error), ephemeral=True)
            return
        except Exception:
            log.exception('Wallet initialization failed; no successful receipt')
            await interaction.followup.send('初期化を完了できませんでした。管理者ログを確認してください。', ephemeral=True)
            return
        await interaction.edit_original_response(
            content=f"ウォレットDBを初期化しました（対象：{receipt['users']}アカウント）。\n"
                    f"初期化前バックアップ：`{Path(receipt['backup']).name}`（サーバーのBACKUP_DIR内）\n"
                    '採掘はCLOSEのままです。設定・アセット・常設投稿は保持しています。', view=None)

    async def on_error(self, interaction, error):
        log.error('Wallet initialization form failed', exc_info=(type(error), error, error.__traceback__))
