import asyncio
import random
from pathlib import Path
import discord
from utils.helpers import get_country, gacha, has_mining_role
from models import wallet
import config.config as config
from config.role_manager import RoleProbabilityManager
from consts import sysmsg as SysMsg
from services.embeds import mining_performance, mining as mining_embed, excellent


def get_excellent_channel_id(country):
    """Excellent通知先を返す。国未所属者は共通雑談チャンネルに送る。"""
    return country["chid"] if country is not None else config.get_excellent_chat()


async def get_channel(client, channel_id):
    """キャッシュを優先し、未取得ならDiscord APIからチャンネルを取得する。"""
    channel = client.get_channel(channel_id)
    if channel is None:
        channel = await client.fetch_channel(channel_id)
    if not callable(getattr(channel, "send", None)):
        raise TypeError(f"Excellent通知先に送信できません: channel_id={channel_id}")
    return channel


async def send_excellent_notification(client, user, country, filename):
    """Excellent結果を国別、または国未所属者用の雑談チャンネルへ送る。"""
    channel_id = get_excellent_channel_id(country)
    channel = await get_channel(client, channel_id)
    img_ex = discord.File(
        fp=f"{config.CWD}/assets/{filename}",
        filename=filename,
    )
    await channel.send(file=img_ex, embed=excellent(user, filename))


async def send_mining_error(interaction):
    """Interactionの応答状況に合わせて採掘エラーを通知する。"""
    kwargs = {"content": "採掘処理中にエラーが発生しました。", "ephemeral": True}
    if interaction.response.is_done():
        await interaction.followup.send(**kwargs)
    else:
        await interaction.response.send_message(**kwargs)


async def mining_zircon(interaction: discord.Interaction, client):
    """ジルコン採掘アクション"""
    credited = False
    try:
        if not config.get_mine_open():
            await interaction.response.send_message(
                content=SysMsg.MINE_CLOSED, ephemeral=True
            )
            return
        # 採掘ロール判定
        if not has_mining_role(interaction.user):
            await interaction.response.send_message(
                content="採掘用のロールを持っていないため採掘できません。", ephemeral=True
            )
            return
        country = get_country(interaction.user)
        # ロール別確率を取得
        role_manager = RoleProbabilityManager()
        user_probability = role_manager.get_user_probability(interaction.user, config.get_probability())
        
        # 採掘ガチャ
        result = gacha(random.random(), user_probability)
        # 採掘結果がエクセレントかどうか判定
        isExcellent = result["id"] == 0
        await interaction.response.defer(thinking=True, ephemeral=True)
        assets = Path(config.CWD) / "assets"
        gifs = sorted(assets.glob("mining[0-9]*.gif"))
        images = sorted(assets.glob(f"{result['msg']}[0-9]*.png"))
        if not gifs or not images:
            raise FileNotFoundError("採掘画像がありません。")
        fn_gif = random.choice(gifs).name
        fn_img = random.choice(images).name
        try:
            total = wallet.claim(interaction.user.id, result["zirnum"], isExcellent, interaction.id)
            credited = True
        except ValueError as error:
            await interaction.followup.send(str(error), ephemeral=True)
            return

        gif_mining = discord.File(
            fp=f"{config.CWD}/assets/{fn_gif}",
            filename=fn_gif
        )
        em1 = mining_performance(interaction.user, fn_gif)
        mining_msg = await interaction.followup.send(embed=em1, file=gif_mining, ephemeral=True)
        await asyncio.sleep(3)

        img_mresult = discord.File(
            fp=f"{config.CWD}/assets/{fn_img}",
            filename=fn_img,
        )
        em2 = mining_embed(result, interaction.user, total, fn_img)
        await mining_msg.edit(embed=em2, attachments=[img_mresult])
        # 採掘結果が「Excellent!!」の場合、各国雑談チャンネルに投稿する
        if isExcellent:
            try:
                await send_excellent_notification(client, interaction.user, country, fn_img)
            except Exception as error:
                print(f"Excellent通知エラー: {error}")
                await interaction.followup.send("採掘・残高更新は完了しましたが、Excellent通知を送信できませんでした。", ephemeral=True)
    except Exception as e:
        print(f"採掘処理エラー ({type(e).__name__}): {e}")
        if credited:
            await interaction.followup.send("採掘・残高更新は完了しています。画像表示に失敗したため、保有数ボタンで確認してください。", ephemeral=True)
        else:
            await send_mining_error(interaction)
