async def require_guild(interaction):
    """Global commands and persistent buttons only operate in the mining guild."""
    expected = getattr(interaction.client, "mining_guild_id", None)
    if expected and interaction.guild and interaction.guild.id == expected:
        return True
    await interaction.response.send_message("採掘Botの対象サーバー内で使用してください。", ephemeral=True)
    return False
