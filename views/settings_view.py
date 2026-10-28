import math
import discord

import config.config as config
from views.wallet_view import SafeView
from services.panel_service import ensure_panels
from services.access import require_guild


async def require_admin(interaction):
    if not await require_guild(interaction):
        return False
    if interaction.guild and interaction.user.guild_permissions.administrator:
        return True
    await interaction.response.send_message("管理者権限が必要です。", ephemeral=True)
    return False


def summary():
    s = config.settings
    s.load_settings()
    times = [f"{h:02}:{m:02}" for h in config.get_announce_hour() for m in config.get_announce_minute()]
    treasuries = "\n".join(
        f"{c['name']}（<@&{c['role']}>）の国庫："
        + (f"<@{config.get_treasury_user_id(c['id'])}>" if config.get_treasury_user_id(c['id']) else "未設定（暫定値0）")
        for c in config.COUNTRIES
    )
    excellent_chats = '\n'.join(
        f"{c['name']}のExcellent通知先：<#{config.get_country_excellent_chat(c['id'])}>"
        for c in config.COUNTRIES
    )
    return (
        f"**採掘Bot設定**\n営業：{'OPEN' if config.get_mine_open() else 'CLOSE'}\n"
        f"リセット（日本時間）：{', '.join(times[:24])}{' …' if len(times) > 24 else ''}（1日{len(times)}回）\n"
        f"各期間の採掘回数：{s.get('mining_limit', 1)}\n"
        f"採掘ロール：<@&{config.get_mining_role()}>\n"
        f"{treasuries}\n"
        f"{excellent_chats}\n"
        f"未所属Excellent通知先：<#{config.get_excellent_chat()}>\n"
        f"採掘・ランキング投稿先：<#{config.CHID_MINING}>"
    )


class AdminModal(discord.ui.Modal):
    async def interaction_check(self, interaction):
        return await require_admin(interaction)

    async def on_error(self, interaction, error):
        import logging
        logging.exception("Settings update failed", exc_info=error)
        sender = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
        await sender("設定を保存できませんでした。管理者ログを確認してください。", ephemeral=True)


class ScheduleModal(AdminModal, title="リセット時刻・採掘回数"):
    hours = discord.ui.TextInput(label="時（0〜23、カンマ区切り）")
    minutes = discord.ui.TextInput(label="分（0〜59、カンマ区切り）")
    limit = discord.ui.TextInput(label="リセット間の採掘回数（1〜100）")

    def __init__(self):
        super().__init__()
        self.hours.default = ",".join(map(str, config.get_announce_hour()))
        self.minutes.default = ",".join(map(str, config.get_announce_minute()))
        self.limit.default = str(config.settings.get("mining_limit", 1))

    async def on_submit(self, interaction):
        try:
            hours = sorted(set(int(v.strip()) for v in self.hours.value.split(",")))
            minutes = sorted(set(int(v.strip()) for v in self.minutes.value.split(",")))
            limit = int(self.limit.value)
            if not hours or not minutes or not all(0 <= h < 24 for h in hours) or not all(0 <= m < 60 for m in minutes) or not 1 <= limit <= 100:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("時・分・回数の範囲を確認してください。", ephemeral=True)
            return
        config.settings.update({"announce_hour": hours, "announce_minute": minutes, "mining_limit": limit})
        await interaction.response.send_message(summary(), ephemeral=True)


class ProbabilityModal(AdminModal, title="採掘確率と獲得数"):
    excellent = discord.ui.TextInput(label="Excellent確率（%）")
    great = discord.ui.TextInput(label="Great確率（%）")
    amounts = discord.ui.TextInput(label="獲得数（Excellent,Great,Good）")

    def __init__(self):
        super().__init__()
        p = config.get_probability()
        self.excellent.default = str(round(p[0]["prob"] * 100, 5))
        self.great.default = str(round((p[1]["prob"] - p[0]["prob"]) * 100, 5))
        self.amounts.default = ",".join(str(v["zirnum"]) for v in p)

    async def on_submit(self, interaction):
        try:
            ex, gr = float(self.excellent.value), float(self.great.value)
            amounts = [int(v.strip()) for v in self.amounts.value.split(",")]
            if not all(math.isfinite(v) for v in (ex, gr)) or min(ex, gr) < 0 or ex + gr > 100 or len(amounts) != 3 or not all(1 <= v <= 1000000 for v in amounts):
                raise ValueError
        except ValueError:
            await interaction.response.send_message("確率は合計100%以内、獲得数は1〜1,000,000で指定してください。", ephemeral=True)
            return
        config.settings.set_probability([
            {"id": i, "msg": name, "prob": threshold, "zirnum": amount}
            for i, (name, threshold, amount) in enumerate(zip(
                ("Excellent", "Great", "Good"), (ex / 100, (ex + gr) / 100, 1.0), amounts))
        ])
        await interaction.response.send_message("共通確率・獲得数を保存しました。", ephemeral=True)


class TreasurySelect(discord.ui.UserSelect):
    def __init__(self, country):
        super().__init__(placeholder=f"{country['name']}の国庫アカウント", min_values=1, max_values=1)
        self.country_id = country['id']

    async def callback(self, interaction):
        try:
            config.set_treasury_user_id(self.country_id, self.values[0].id)
        except ValueError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        await interaction.response.edit_message(content=summary(), view=TreasuryView())


class TreasuryView(SafeView):
    def __init__(self):
        super().__init__(timeout=180)
        for country in config.COUNTRIES:
            self.add_item(TreasurySelect(country))

    async def interaction_check(self, interaction):
        return await require_admin(interaction)


class TargetView(SafeView):
    def __init__(self):
        super().__init__(timeout=180)

    async def interaction_check(self, interaction):
        return await require_admin(interaction)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="採掘を許可するロール", min_values=1, max_values=1)
    async def mining_role(self, interaction, select):
        config.settings.set("mining_role", select.values[0].id)
        await interaction.response.send_message(summary(), ephemeral=True)

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="未所属者のExcellent通知先", min_values=1, max_values=1)
    async def excellent_channel(self, interaction, select):
        channel = await excellent_target(interaction, select.values[0].id)
        if channel is None:
            return
        config.settings.set("excellent_chat", channel.id)
        await interaction.response.send_message(summary(), ephemeral=True)


async def excellent_target(interaction, channel_id):
    channel = interaction.guild.get_channel(channel_id)
    permissions = channel.permissions_for(interaction.guild.me) if channel else None
    if (not isinstance(channel, discord.TextChannel) or channel.guild.id != interaction.guild.id
            or not permissions or not all((permissions.view_channel, permissions.send_messages,
                                           permissions.attach_files, permissions.embed_links))):
        await interaction.response.send_message("Botが閲覧・投稿・画像添付・埋め込みできるチャンネルを選んでください。", ephemeral=True)
        return None
    return channel


class CountryExcellentSelect(discord.ui.ChannelSelect):
    def __init__(self, country):
        super().__init__(placeholder=f"{country['name']}のExcellent通知先",
                         channel_types=[discord.ChannelType.text], min_values=1, max_values=1)
        self.country_id = country['id']

    async def callback(self, interaction):
        channel = await excellent_target(interaction, self.values[0].id)
        if channel is None:
            return
        config.set_country_excellent_chat(self.country_id, channel.id)
        await interaction.response.edit_message(content=summary(), view=CountryExcellentView())


class CountryExcellentView(SafeView):
    def __init__(self):
        super().__init__(timeout=180)
        for country in config.COUNTRIES:
            self.add_item(CountryExcellentSelect(country))

    async def interaction_check(self, interaction):
        return await require_admin(interaction)


class SettingsView(SafeView):
    def __init__(self):
        super().__init__(timeout=300)

    async def interaction_check(self, interaction):
        return await require_admin(interaction)

    @discord.ui.button(label="OPEN / CLOSE")
    async def toggle(self, interaction, button):
        config.settings.set_mine_open(not config.get_mine_open())
        await interaction.response.edit_message(content=summary(), view=self)

    @discord.ui.button(label="リセット時刻・回数")
    async def schedule(self, interaction, button):
        await interaction.response.send_modal(ScheduleModal())

    @discord.ui.button(label="ロール・通知先")
    async def targets(self, interaction, button):
        await interaction.response.send_message(summary(), view=TargetView(), ephemeral=True)

    @discord.ui.button(label="4か国の国庫")
    async def treasuries(self, interaction, button):
        await interaction.response.send_message(summary(), view=TreasuryView(), ephemeral=True)

    @discord.ui.button(label="確率・獲得数")
    async def probability(self, interaction, button):
        await interaction.response.send_modal(ProbabilityModal())

    @discord.ui.button(label="ロール別確率の設定", row=1)
    async def role_probability(self, interaction, button):
        from views.role_probability_view import RoleProbabilityView
        view = RoleProbabilityView(interaction.user.id)
        await interaction.response.send_message(view.text(), view=view, ephemeral=True)

    @discord.ui.button(label="常設投稿を確認・復旧", row=1)
    async def panels(self, interaction, button):
        await interaction.response.defer(ephemeral=True)
        await ensure_panels(interaction.client)
        await interaction.followup.send("常設投稿を確認しました。", ephemeral=True)

    @discord.ui.button(label="現在の設定を更新表示", row=1)
    async def refresh(self, interaction, button):
        await interaction.response.edit_message(content=summary(), view=self)

    @discord.ui.button(label="国別Excellent通知先", row=1)
    async def country_excellent(self, interaction, button):
        await interaction.response.send_message(summary(), view=CountryExcellentView(), ephemeral=True)
