import csv
import os
import traceback
from datetime import datetime

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


# csvで書き出し
def write_csv(filename, header, data):
    try:
        with open(filename, "w", newline="", encoding="utf8") as f:
            writer = csv.writer(f)
            if header is not None:
                writer.writerow(header)
            writer.writerows(data)
    except Exception as e:
        handle_util_error(e, "write_csv")
        raise


# datetime型からString型に変換
def convertDt2Str(dt: datetime, format):
    try:
        return dt.strftime(format)
    except Exception as e:
        handle_util_error(e, "convertDt2Str")
        return ""


# String型からdatetime型に変換
def convertStr2Dt(dt: str, format):
    try:
        return datetime.strptime(dt, format)
    except Exception as e:
        handle_util_error(e, "convertStr2Dt")
        return datetime.now()


# String型からint型に変換可能か判定
def isInt(s):
    try:
        int(s)
    except ValueError:
        return False  # 例外が発生=変換できない
    else:
        return True  # 例外が発生しない=変換可能


def ordinal(n):
    try:
        if 10 <= n % 100 <= 20:
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        return str(n) + suffix
    except Exception as e:
        handle_util_error(e, "ordinal")
        return str(n)


# ガチャ結果タイプに対応する画像ファイルの枚数を取得
def get_mining_image_count(result_msg: str, file_extension: str = ".png") -> int:
    """ガチャ結果タイプ（Excellent, Great, Goodなど）またはプレフィックス（miningなど）に対応する
    画像ファイルの枚数を動的に取得
    
    Args:
        result_msg (str): ガチャ結果のメッセージまたはファイル名のプレフィックス
                         （例: "Excellent", "Great", "Good", "mining"）
        file_extension (str): 検索するファイルの拡張子（デフォルト: ".png"）
    
    Returns:
        int: 該当する画像ファイルの枚数。見つからない場合は0を返す
    """
    try:
        assets_dir = os.path.join(config.CWD, "assets")
        if not os.path.exists(assets_dir):
            return 0
        
        # 指定されたプレフィックスで始まり、指定された拡張子のファイルを検索
        count = 0
        prefix = result_msg
        ext_len = len(file_extension)
        for filename in os.listdir(assets_dir):
            if filename.startswith(prefix) and filename.endswith(file_extension):
                # ファイル名が "{prefix}{数字}{extension}" の形式かチェック
                # 例: "Excellent0.png", "mining1.gif" など
                remaining = filename[len(prefix):-ext_len]  # 拡張子を除いた残り部分
                if remaining.isdigit():
                    count += 1
        
        return count
    except Exception as e:
        handle_util_error(e, "get_mining_image_count")
        return 0
