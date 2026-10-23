import traceback

import config.config as config


# エラーハンドリング関数
def handle_util_error(error, function_name):
    """ユーティリティ関数のエラーを処理する関数

    Args:
        error (Exception): 発生したエラー
        function_name (str): エラーが発生した関数名
    """
    print(f"UTIL-{function_name} ERROR: {error}")
    print(traceback.format_exc())


# ガチャシステム
def gacha(rval, conf):
    try:
        for item in conf:
            if rval < item["prob"]:
                return item
        return conf[-1]  # 最後のアイテムを返す（確率の合計が1未満の場合）
    except Exception as e:
        handle_util_error(e, "gacha")
        return {"id": 0, "msg": "エラー", "zirnum": 0, "prob": 1.0}


# 送信者の国ロールを取得する
def get_country(user):
    try:
        if user is None:
            return None
        for usr_role in user.roles:
            for country in config.COUNTRIES:
                if usr_role.id == country["role"]:
                    return country
        return None
    except Exception as e:
        handle_util_error(e, "get_country")
        return None


# roleid から country を特定
def get_country_by_roleid(roleid):
    try:
        if roleid is None:
            return None
        for country in config.COUNTRIES:
            if roleid == country["role"]:
                return country
        return None
    except Exception as e:
        handle_util_error(e, "get_country_by_roleid")
        return None

# 採掘ロールを持っているか判定
def has_mining_role(user):
    try:
        if user is None:
            return False
        for usr_role in user.roles:
            if usr_role.id == config.get_mining_role():
                return True
        return False
    except Exception as e:
        handle_util_error(e, "has_mining_role")
        return False
