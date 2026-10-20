import discord
import traceback

from utils.helpers import ordinal


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


# 指定国の統計データembed(ジェム数、採掘回数、自分のランク、Top10)
def stats_country(res_country, country_name, res_rank, rank_self):
    try:
        rank = ordinal(rank_self) if rank_self != 0 else "None"
        embed = discord.Embed(
            title=f"{country_name}国 サマリ", description="", color=0x0000FF
        )
        embed.set_thumbnail(url=f"attachment://{country_name}.jpg")
        # 統計データ表示
        embed.add_field(
            name=f"""
ジルコン : {int(res_country[1])} :gem:
採掘回数 : {int(res_country[2])} :pick:
            """,
            value="",
            inline=False,
        )

        # ランキング表示
        embed.add_field(name="ランキングTOP10", value=f"Your Rank: {rank}", inline=False)
        # res_rank[[user_mention1, zirnum1,...], [user_mention2, zirnum2,...],...]
        top10List = []
        for index in range(min(10, len(res_rank))):
            top10List.append(
                f"**{res_rank[index][0]}.** `{res_rank[index][1]}` • :gem: {res_rank[index][2]}"
            )
        top10Str = "\n".join(top10List)

        embed.add_field(name="", value=f"{top10Str}", inline=False)
        return embed
    except Exception as e:
        handle_embed_error(e, "stats_country")
        return discord.Embed(title="エラー", description="国統計情報の表示中にエラーが発生しました。", color=0xFF0000)


# 自分の統計データembed(ジェム数、採掘回数、Ex数、国内順位)
def stats_self(result_mining, result_lifetime, usr, rank_self):
    try:
        rank = ordinal(rank_self) if rank_self != 0 else "None"
        embed = discord.Embed(title="", description="", color=0x0000FF)
        embed.set_author(
            name=f"{usr.display_name} 採掘データ", icon_url=usr.display_avatar.url
        )

        embed.add_field(
            name=f"""
ジルコン : {int(result_mining[3])} :gem: （累積 {int(result_lifetime[2])}）
採掘回数 : {int(result_mining[4])} :pick: （累積 {int(result_lifetime[4])}）
Excellent : {int(result_mining[5])} :tada: （累積 {int(result_lifetime[5])}）
            """,
            value=f"国内順位 {rank}",
            inline=False,
        )
        return embed
    except Exception as e:
        handle_embed_error(e, "stats_self")
        return discord.Embed(title="エラー", description="個人統計情報の表示中にエラーが発生しました。", color=0xFF0000)


# 国対抗ランキングのembed
def rank_country(result):
    try:
        embed = discord.Embed(title="国対抗ランキング", description="", color=0x0000FF)
        for rank, res in enumerate(result):
            embed.add_field(
                name=f"{rank+1} : {res[0]['stmp']} {res[0]['name']} : {res[1]} :gem:",
                value="",
                inline=False,
            )
        return embed
    except Exception as e:
        handle_embed_error(e, "rank_country")
        return discord.Embed(title="エラー", description="国ランキング情報の表示中にエラーが発生しました。", color=0xFF0000)
