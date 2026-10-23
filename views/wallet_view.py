import logging

import discord

import config.config as config
from models import wallet
from services.mining_service import mining_zircon
from utils.helpers import get_country
from services.access import require_guild

log = logging.getLogger(__name__)


class SafeView(discord.ui.View):
    async def interaction_check(self, interaction):
        return await require_guild(interaction)

    async def on_error(self, interaction, error, item):
        log.error("View failed", exc_info=(type(error), error, error.__traceback__))
        sender = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
        await sender("処理に失敗しました。管理者にお問い合わせください。", ephemeral=True)


class RankingView(SafeView):
    def __init__(self, owner, guild, kind):
        super().__init__(timeout=180)
        self.owner, self.guild, self.kind = owner, guild, kind
        self.rows = wallet.ranking(kind)
        self.page = 0
        self.update_buttons()

    async def interaction_check(self, interaction):
        if interaction.user.id == self.owner:
            return True
        await interaction.response.send_message("自分のランキング画面を開いてください。", ephemeral=True)
        return False

    def update_buttons(self):
        self.previous.disabled = self.page == 0
        self.next.disabled = (self.page + 1) * 10 >= len(self.rows)

    def embed(self):
        title = "ジルコン所持数ランキング" if self.kind == "balance" else "Excellentランキング"
        lines = []
        for index, (uid, amount, excellent, count) in enumerate(self.rows[self.page * 10:(self.page + 1) * 10], self.page * 10 + 1):
            member = self.guild.get_member(uid)
            name = discord.utils.escape_markdown(member.display_name) if member else f"ユーザー {uid}"
            country = get_country(member)
            if self.kind == "balance":
                detail = f"{country['stmp'] if country else '—'} {name}：💎 {amount:,}"
            else:
                detail = f"{name}：Excellent {excellent:,}回 / 採掘 {count:,}回"
            lines.append(f"**{index}.** {detail}")
        embed = discord.Embed(title=title, description="\n".join(lines) or "データがありません。")
        embed.set_footer(text=f"{self.page + 1} / {max(1, (len(self.rows) + 9) // 10)} ページ")
        return embed

    @discord.ui.button(label="前へ", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction, button):
        self.page = max(0, self.page - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="次へ", style=discord.ButtonStyle.secondary)
    async def next(self, interaction, button):
        self.page = min(max(0, (len(self.rows) - 1) // 10), self.page + 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embed(), view=self)


class MiningView(SafeView):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="採掘", style=discord.ButtonStyle.primary, custom_id="mining_zircon")
    async def mine(self, interaction, button):
        if interaction.guild is None:
            await interaction.response.send_message("サーバー内で使用してください。", ephemeral=True)
            return
        await mining_zircon(interaction, interaction.client)


class WalletView(SafeView):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="自分の保有数", custom_id="self_stats")
    async def own(self, interaction, button):
        amount, count, excellent = wallet.balance(interaction.user.id)
        await interaction.response.send_message(
            f"💎 保有数：{amount:,}\nExcellent：{excellent:,}回\n採掘：{count:,}回", ephemeral=True)

    async def show_rank(self, interaction, kind):
        view = RankingView(interaction.user.id, interaction.guild, kind)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)

    @discord.ui.button(label="ジルコン所持数ランキング", custom_id="wallet_rank")
    async def balances(self, interaction, button):
        await self.show_rank(interaction, "balance")

    @discord.ui.button(label="Excellentランキング", custom_id="excellent_rank")
    async def excellents(self, interaction, button):
        await self.show_rank(interaction, "excellent")

