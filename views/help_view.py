"""Read-only Japanese guide to administrator commands."""
import discord


def help_embed():
    embed = discord.Embed(
        title='🔧 採掘Bot 管理コマンド',
        description='管理者向けコマンドの使い方です。`/help` でこの案内を表示します。',
        colour=discord.Colour.blue())
    embed.add_field(name='🔧 管理者：設定・残高操作', inline=False, value=(
        '`/settings` — 開閉、リセット時刻・回数、採掘ロール、国庫、'
        'Excellent通知先、確率・獲得数、常設投稿の復旧。\n'
        '`/add user amount` — 指定ユーザーに付与。\n'
        '`/remove user amount` — 指定ユーザーから引き去り。\n'
        '`/transfer source target amount` — ユーザー間で転送。'))
    embed.add_field(name='🛠 管理者：リセット・データ・アセット', inline=False, value=(
        '`/resetmining` — 全員の採掘回数を即時リセット。残高・実績は保持します。\n'
        '`/exportwallet` — 日本語の複数選択メニューで必要な情報だけCSV取得。\n'
        '`/wipewallet` — **全員・国庫の残高・累計実績・履歴を初期化**。'
        'CLOSE必須、確認2回（確認文の手入力）、3分で失効。'
        '事前バックアップに成功した場合だけ実行し、設定・アセット・常設投稿は保持します。\n'
        '`/assets manage` — 画像・キャラ・セリフの追加・編集・非表示・削除。\n'
        '`/assets upload` — 画像の追加・差し替え。'
        '正方形・最大600×600px・1MB未満、500KB以下推奨。'))
    embed.set_footer(text='この案内はあなただけに表示されています。')
    return embed
