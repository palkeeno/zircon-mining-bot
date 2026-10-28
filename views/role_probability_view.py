"""Role picker and priority-based editing for the existing role-name settings."""
import math
import time
from copy import deepcopy

import discord

from config.role_manager import RoleProbabilityManager
from views.settings_view import AdminModal, require_admin
from views.wallet_view import SafeView


class RoleProbabilityView(SafeView):
    def __init__(self, owner, *, page=0, editing=False):
        super().__init__(timeout=180)
        self.owner = owner
        self.deadline = time.monotonic() + 180
        self.rows = sorted(RoleProbabilityManager().cache, key=lambda row: row['priority'])
        # Keep each page within both message and select-menu limits, even for long role names.
        self.page = max(0, min(page, max(0, (len(self.rows) - 1) // 5)))
        self.editing = editing
        self.change.disabled = not self.rows
        self.previous.disabled = self.page == 0
        self.next.disabled = (self.page + 1) * 5 >= len(self.rows)
        if editing and self.rows:
            self.add_item(ProbabilitySelect(self))

    def text(self):
        lines = ['**ロール別確率の設定**', '優先順位の小さい設定を適用します。Goodは残りの確率です。']
        for row in self.rows[self.page * 5:(self.page + 1) * 5]:
            name = discord.utils.escape_markdown(row['role_name'])
            lines.append(f"{row['priority']}. {name}：Excellent {row['excellent_prob']}% / Great {row['great_prob']}%")
        if not self.rows:
            lines.append('ロール別設定はありません。「追加」からロールを選んでください。')
        lines.append(f'{self.page + 1} / {max(1, (len(self.rows) + 9) // 5)} ページ')
        if self.editing and self.rows:
            lines.append('下のプルダウンで変更する優先順を選んでください。')
        return '\n'.join(lines)

    async def interaction_check(self, interaction):
        if not await require_admin(interaction):
            return False
        if interaction.user.id != self.owner or time.monotonic() >= self.deadline:
            await interaction.response.send_message('実行した本人のみ操作できます。期限切れの場合は設定を開き直してください。', ephemeral=True)
            return False
        return True

    @discord.ui.button(label='追加', row=1)
    async def add(self, interaction, button):
        view = RoleAddView(self.owner)
        await interaction.response.edit_message(content=self.text() + '\n追加するロールを選んでください。', view=view)

    @discord.ui.button(label='変更', row=1)
    async def change(self, interaction, button):
        await self.refresh(interaction, editing=True)

    async def refresh(self, interaction, *, page=None, editing=None):
        view = RoleProbabilityView(self.owner, page=self.page if page is None else page,
                                   editing=self.editing if editing is None else editing)
        await interaction.response.edit_message(content=view.text(), view=view)

    @discord.ui.button(label='前へ', row=2)
    async def previous(self, interaction, button):
        await self.refresh(interaction, page=self.page - 1)

    @discord.ui.button(label='次へ', row=2)
    async def next(self, interaction, button):
        await self.refresh(interaction, page=self.page + 1)


class RoleAddView(RoleProbabilityView):
    def __init__(self, owner):
        super().__init__(owner)
        self.clear_items()
        self.add_item(NewRoleSelect(self))
        back = discord.ui.Button(label='一覧に戻る', row=1)
        back.callback = self.back
        self.add_item(back)

    async def back(self, interaction):
        await self.refresh(interaction, editing=False)


class NewRoleSelect(discord.ui.RoleSelect):
    def __init__(self, session):
        super().__init__(placeholder='追加するロール', min_values=1, max_values=1)
        self.session = session

    async def callback(self, interaction):
        role = self.values[0]
        manager = RoleProbabilityManager()
        if any(row['role_name'] == role.name for row in manager.cache):
            await interaction.response.send_message('同じロール名は登録済みです。「変更」から編集してください。', ephemeral=True)
            return
        await interaction.response.send_modal(RoleProbabilityModal(self.session, role=role))


class ProbabilitySelect(discord.ui.Select):
    def __init__(self, session):
        self.session = session
        start = session.page * 5
        super().__init__(placeholder='変更する優先順を選択', row=0, options=[
            discord.SelectOption(label=f"優先順 {row['priority']}：{row['role_name']}"[:100], value=str(index),
                                 description=f"Excellent {row['excellent_prob']}% / Great {row['great_prob']}%"[:100])
            for index, row in enumerate(session.rows[start:start + 5], start)])

    async def callback(self, interaction):
        row = self.session.rows[int(self.values[0])]
        await interaction.response.send_modal(RoleProbabilityModal(self.session, existing=row))


class RoleProbabilityModal(AdminModal):
    def __init__(self, session, *, role=None, existing=None):
        super().__init__(title=(('変更・削除：' + existing['role_name']) if existing else ('追加：' + role.name))[:45], timeout=180)
        self.session, self.role = session, role
        self.existing = deepcopy(existing)
        self.snapshot = deepcopy(RoleProbabilityManager().cache)
        self.used = False
        defaults = existing or {'excellent_prob': 0, 'great_prob': 0,
                                'priority': max((row['priority'] for row in self.snapshot), default=0) + 1}
        self.excellent = discord.ui.TextInput(label='Excellent確率（%）', default=str(defaults['excellent_prob']))
        self.great = discord.ui.TextInput(label='Great確率（%）', default=str(defaults['great_prob']))
        self.priority = discord.ui.TextInput(label='優先順位（1以上、小さいほど優先）', default=str(defaults['priority']))
        for item in (self.excellent, self.great, self.priority):
            self.add_item(item)
        if existing:
            self.delete = discord.ui.TextInput(label='この設定を削除する場合だけ「削除」と入力', required=False, max_length=10)
            self.add_item(self.delete)

    async def interaction_check(self, interaction):
        return await self.session.interaction_check(interaction)

    async def on_submit(self, interaction):
        if not await self.interaction_check(interaction):
            return
        if self.used:
            await interaction.response.send_message('この入力は処理済みです。設定を開き直してください。', ephemeral=True)
            return
        manager = RoleProbabilityManager()
        if manager.cache != self.snapshot or (self.existing and self.existing not in manager.cache):
            await interaction.response.send_message('設定が変更されています。一覧を開き直してください。', ephemeral=True)
            return
        if self.role is not None:
            current = interaction.guild.get_role(self.role.id)
            if current is None or current.name != self.role.name:
                await interaction.response.send_message('ロールが削除・改名されています。選び直してください。', ephemeral=True)
                return
            if any(row['role_name'] == current.name for row in manager.cache):
                await interaction.response.send_message('同じロール名は登録済みです。「変更」から編集してください。', ephemeral=True)
                return
        deletion = self.delete.value if self.existing else ''
        if deletion and deletion != '削除':
            await interaction.response.send_message('削除する場合は「削除」と正確に入力してください。保存していません。', ephemeral=True)
            return
        if deletion:
            manager.remove_role(self.existing['role_name'])
        else:
            try:
                ex, gr, priority = float(self.excellent.value), float(self.great.value), int(self.priority.value)
                if not all(math.isfinite(v) for v in (ex, gr)) or min(ex, gr) < 0 or ex + gr > 100 or priority < 1:
                    raise ValueError
            except ValueError:
                await interaction.response.send_message('確率は0%以上・合計100%以内、優先順位は1以上の整数で指定してください。', ephemeral=True)
                return
            if self.existing:
                manager.update_priorities(self.existing['role_name'], priority)
                row = next(row for row in manager.cache if row['role_name'] == self.existing['role_name'])
                row.update(excellent_prob=ex, great_prob=gr)
            else:
                for row in manager.cache:
                    if row['priority'] >= priority:
                        row['priority'] += 1
                manager.cache.append(dict(role_name=self.role.name, excellent_prob=ex, great_prob=gr, priority=priority))
        manager.save()
        self.used = True
        view = RoleProbabilityView(self.session.owner, page=self.session.page, editing=self.session.editing)
        await interaction.response.edit_message(content=('設定を削除しました。\n' if deletion else '設定を保存しました。\n') + view.text(), view=view)
