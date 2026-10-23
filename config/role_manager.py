import json
import os
from datetime import datetime

class RoleProbabilityManager:
    def __init__(self):
        self.cache = []
        self.file_path = os.getenv("ROLE_SETTINGS_FILE", "data/role_probabilities.json")
        self.load()
    
    def load(self):
        """ファイルから読み込み、キャッシュを更新"""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.cache = data.get('role_probabilities', [])
        except FileNotFoundError:
            self.cache = []
        except json.JSONDecodeError:
            self.cache = []
    
    def save(self):
        """キャッシュをファイルに保存"""
        # ディレクトリが存在しない場合は作成
        os.makedirs(os.path.dirname(os.path.abspath(self.file_path)), exist_ok=True)
        data = {'role_probabilities': self.cache}
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def get_next_priority(self):
        """新規追加時に使用する優先度を取得"""
        if not self.cache:
            return 1
        max_priority = max(role["priority"] for role in self.cache)
        return max_priority + 1
    
    def get_applicable_role(self, user):
        """ユーザーが持つ適用可能なロールを取得（優先度順）"""
        user_role_names = [role.name for role in user.roles]
        applicable_roles = []
        
        for role_setting in self.cache:
            if role_setting['role_name'] in user_role_names:
                applicable_roles.append(role_setting)
        
        if not applicable_roles:
            return None
        
        # 優先度の高いロールを返す
        return min(applicable_roles, key=lambda x: x['priority'])
    
    def get_user_probability(self, user, base_probability):
        """ユーザーの適用確率を取得（キャッシュ使用）"""
        applicable_role = self.get_applicable_role(user)
        if not applicable_role:
            return base_probability
        
        # ロール別確率を計算
        great_prob = applicable_role['great_prob'] / 100
        excellent_prob = applicable_role['excellent_prob'] / 100
        good_prob = (100 - applicable_role['great_prob'] - applicable_role['excellent_prob']) / 100
        
        return [
            {'id': 0, 'prob': excellent_prob, 'msg': 'Excellent', 'zirnum': base_probability[0]['zirnum']},
            {'id': 1, 'prob': excellent_prob + great_prob, 'msg': 'Great', 'zirnum': base_probability[1]['zirnum']},
            {'id': 2, 'prob': 1.0, 'msg': 'Good', 'zirnum': base_probability[2]['zirnum']}
        ]
    
    def update_priorities(self, target_role_name, new_priority):
        """優先度変更時の処理"""
        target_role = None
        current_priority = None
        
        # 対象ロールを探す
        for role in self.cache:
            if role['role_name'] == target_role_name:
                target_role = role
                current_priority = role['priority']
                break
        
        if not target_role or current_priority == new_priority:
            return False
        
        # 同じ優先度のロールを探す
        same_priority_role = None
        for role in self.cache:
            if role['priority'] == new_priority and role['role_name'] != target_role_name:
                same_priority_role = role
                break
        
        if same_priority_role:
            # 優先度を入れ替え
            same_priority_role['priority'] = current_priority
            same_priority_role['updated_at'] = datetime.now().isoformat()
        
        # 対象ロールの優先度を更新
        target_role['priority'] = new_priority
        target_role['updated_at'] = datetime.now().isoformat()
        
        return True 

    def remove_role(self, target_role_name):
        """対象ロールを削除し、削除された優先度より下にあるロールの優先度を1つ上げて詰める"""
        target_role = None
        for role in self.cache:
            if role['role_name'] == target_role_name:
                target_role = role
                break

        if not target_role:
            return False

        removed_priority = target_role['priority']

        # Remove the target role
        self.cache = [r for r in self.cache if r['role_name'] != target_role_name]

        # Decrement priority for roles with priority > removed_priority
        changed = False
        for role in self.cache:
            if role.get('priority') and role['priority'] > removed_priority:
                role['priority'] = role['priority'] - 1
                role['updated_at'] = datetime.now().isoformat()
                changed = True

        # If roles changed (or removal happened), consider it successful
        return True
