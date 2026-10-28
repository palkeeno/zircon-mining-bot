import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import test_mining_service
from test_wallet_ui import interaction
from config.role_manager import RoleProbabilityManager
from views.settings_view import SettingsView
from views.role_probability_view import RoleProbabilityView, RoleAddView, RoleProbabilityModal, ProbabilitySelect


class RoleProbabilityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'roles.json'
        env = patch.dict(os.environ, ROLE_SETTINGS_FILE=str(self.path))
        env.start()
        self.addCleanup(env.stop)
        self.role = SimpleNamespace(id=123, name='テスト役職')

    def rows(self):
        return RoleProbabilityManager().cache

    def save(self, rows):
        manager = RoleProbabilityManager()
        manager.cache = rows
        manager.save()

    def row(self, name='既存', priority=1):
        return dict(role_name=name, priority=priority, excellent_prob=3, great_prob=25)

    def event(self):
        i = interaction(True)
        i.guild.get_role = lambda uid: self.role if uid == self.role.id else None
        return i

    async def test_settings_has_one_entry_and_initial_list_has_add_change(self):
        labels = [item.label for item in SettingsView().children]
        self.assertEqual([label for label in labels if label.startswith('ロール別')], ['ロール別確率の設定'])
        i = self.event()
        await SettingsView().role_probability.callback(i)
        view = i.response.send_message.call_args.kwargs['view']
        self.assertTrue(i.response.send_message.call_args.kwargs['ephemeral'])
        self.assertIn('設定はありません', view.text())
        self.assertTrue(view.change.disabled)
        await view.add.callback(i)
        self.assertIsInstance(i.response.edit_message.call_args.kwargs['view'], RoleAddView)

    async def test_add_selects_role_then_modal_inserts_and_shifts_priority(self):
        self.save([self.row()])
        view = RoleAddView(100)
        picker = view.children[0]
        picker._values = [self.role]
        i = self.event()
        await picker.callback(i)
        modal = i.response.send_modal.call_args.args[0]
        self.assertEqual(modal.priority.default, '2')
        self.assertFalse(any(item.label == 'ロールID' for item in modal.children))
        modal.priority._value = '1'
        modal.excellent._value = '10'
        modal.great._value = '20'
        await modal.on_submit(i)
        self.assertEqual({row['role_name']:row['priority'] for row in self.rows()}, {'既存':2, self.role.name:1})
        self.assertEqual(self.rows()[-1]['excellent_prob'], 10)
        self.assertIn('保存しました', i.response.edit_message.call_args.kwargs['content'])

    async def test_change_selects_priority_prefills_and_swaps_then_delete_compacts(self):
        self.save([self.row(), self.row('別', 2)])
        view = RoleProbabilityView(100)
        i = self.event()
        await view.change.callback(i)
        editing = i.response.edit_message.call_args.kwargs['view']
        picker = next(item for item in editing.children if isinstance(item, ProbabilitySelect))
        self.assertIn('優先順 1', picker.options[0].label)
        picker._values = ['0']
        await picker.callback(i)
        modal = i.response.send_modal.call_args.args[0]
        self.assertEqual(modal.excellent.default, '3')
        modal.priority._value = '2'
        await modal.on_submit(i)
        self.assertEqual({r['role_name']:r['priority'] for r in self.rows()}, {'既存':2, '別':1})
        view = RoleProbabilityView(100, editing=True)
        modal = RoleProbabilityModal(view, existing=view.rows[0])
        modal.delete._value = '削除'
        # Deletion does not depend on numeric fields, and can remove settings for a deleted Discord role.
        modal.excellent._value = ''
        await modal.on_submit(i)
        self.assertEqual([(r['role_name'],r['priority']) for r in self.rows()], [('既存',1)])
        self.assertIn('削除しました', i.response.edit_message.call_args.kwargs['content'])

    async def test_invalid_probability_priority_and_delete_text_preserve_file(self):
        self.save([self.row()])
        original = self.path.read_bytes()
        for ex, gr, priority, deletion in [('nan','1','1',''), ('90','11','1',''), ('-1','5','1',''),
                                            ('1','1','0',''), ('1','1','1','消す')]:
            modal = RoleProbabilityModal(RoleProbabilityView(100), existing=self.rows()[0])
            modal.excellent._value, modal.great._value = ex, gr
            modal.priority._value, modal.delete._value = priority, deletion
            await modal.on_submit(self.event())
            self.assertEqual(self.path.read_bytes(), original)

    async def test_stale_modal_and_duplicate_role_and_deleted_role_do_not_write(self):
        self.save([self.row()])
        view = RoleProbabilityView(100)
        modal = RoleProbabilityModal(view, existing=view.rows[0])
        self.save([self.row(priority=4)])
        await modal.on_submit(self.event())
        self.assertEqual(self.rows()[0]['priority'], 4)
        self.assertFalse(modal.used)
        self.save([self.row(self.role.name)])
        picker = RoleAddView(100).children[0]
        picker._values = [self.role]
        i = self.event()
        await picker.callback(i)
        i.response.send_modal.assert_not_awaited()
        self.save([])
        modal = RoleProbabilityModal(RoleAddView(100), role=self.role)
        i.guild.get_role = lambda uid: None
        await modal.on_submit(i)
        self.assertEqual(self.rows(), [])

    async def test_all_steps_require_owner_admin_target_guild_and_not_expired(self):
        for view in (RoleProbabilityView(100), RoleAddView(100)):
            modal = RoleProbabilityModal(view, role=self.role)
            for target in (view, modal):
                self.assertFalse(await target.interaction_check(interaction(False)))
                other = self.event()
                other.user.id = 999
                self.assertFalse(await target.interaction_check(other))
                other = self.event()
                other.guild.id = 999
                self.assertFalse(await target.interaction_check(other))
                self.assertTrue(await target.interaction_check(self.event()))
            view.deadline = 0
            await modal.on_submit(self.event())
        self.assertFalse(self.path.exists())

    async def test_pages_cover_more_than_select_limit_and_handle_duplicate_priorities(self):
        self.save([self.row('長い役職名_' * 10 + str(index), index // 2 + 1) for index in range(27)])
        choices = []
        for page in range(6):
            view = RoleProbabilityView(100, page=page, editing=True)
            picker = next(item for item in view.children if isinstance(item, ProbabilitySelect))
            choices.extend(option.value for option in picker.options)
            self.assertLess(len(view.text()), 2000)
            self.assertTrue(all(len(option.label) <= 100 for option in picker.options))
        self.assertEqual(choices, [str(index) for index in range(27)])

    async def test_save_failure_keeps_original_settings_and_modal_not_consumed(self):
        self.save([self.row()])
        original = self.path.read_bytes()
        modal = RoleProbabilityModal(RoleProbabilityView(100), existing=self.rows()[0])
        modal.excellent._value = '10'
        with patch('config.role_manager.os.replace', side_effect=OSError('storage unavailable')):
            with self.assertRaises(OSError):
                await modal.on_submit(self.event())
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse(modal.used)
