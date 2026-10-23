import discord
import traceback



# エラーハンドリング関数
def handle_embed_error(error, function_name):
    """embed作成時のエラーを処理する関数

    Args:
        error (Exception): 発生したエラー
        function_name (str): エラーが発生した関数名
    """
    print(f"EMBED-{function_name} ERROR: {error}")
    print(traceback.format_exc())


# 採掘結果のembed
def mining(result, user, total, filename):
    try:
        embed = discord.Embed(title="", description="", color=0x00FF00)
        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
        embed.add_field(
            name=f":pick: :sparkles: {result['msg']}! **{result['zirnum']}** :gem: 掘れた！",
            value=f"現在の保有数 **{total}** :gem:",
            inline=False,
        )
        embed.set_image(url=f"attachment://{filename}")
        return embed
    except Exception as e:
        handle_embed_error(e, "mining")
        return discord.Embed(title="エラー", description="採掘結果の表示中にエラーが発生しました。", color=0xFF0000)


# 採掘演出のembed (中味はgifのみ)
def mining_performance(user, filename):
    try:
        embed = discord.Embed(title="", description="", color=0x00FF00)
        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
        embed.set_image(url=f"attachment://{filename}")
        return embed
    except Exception as e:
        handle_embed_error(e, "mining_performance")
        return discord.Embed(title="エラー", description="採掘演出の表示中にエラーが発生しました。", color=0xFF0000)


# 採掘結果Excellentを雑談チャネルに投稿するときのembed
def excellent(user, filename):
    try:
        embed = discord.Embed(
            title="Excellent採掘しました！ :gem::gem::gem:", description="", color=0x00FF00
        )
        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
        embed.set_thumbnail(url=f"attachment://{filename}")
        return embed
    except Exception as e:
        handle_embed_error(e, "excellent")
        return discord.Embed(title="エラー", description="Excellent結果の表示中にエラーが発生しました。", color=0xFF0000)
