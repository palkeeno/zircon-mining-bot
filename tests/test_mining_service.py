import os
from contextlib import nullcontext
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from types import ModuleType
from unittest.mock import AsyncMock, Mock, patch

# 単体テストではDiscordへ接続しないため、importに必要な最小APIだけを用意する。
try:
    import discord  # noqa: F401
except ModuleNotFoundError:
    discord_stub = ModuleType("discord")
    discord_stub.Interaction = object
    discord_stub.File = Mock
    sys.modules["discord"] = discord_stub

try:
    import dotenv  # noqa: F401
except ModuleNotFoundError:
    dotenv_stub = ModuleType("dotenv")
    dotenv_stub.load_dotenv = Mock()
    sys.modules["dotenv"] = dotenv_stub

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_DEFAULTS = {
    "DISCORD_TOKEN": "test-token",
    "DB_WALLET": "test-users.db",
    "CWD": str(PROJECT_ROOT),
    "MCH": "1",
    "CHID_MINING": "2",
    "BRAVE_CHAT": "3",
    "FREEDOM_CHAT": "4",
    "GLORY_CHAT": "5",
    "PEACEFUL_CHAT": "6",
    "MINING_EXCELLENT_CHAT": "7",
    "BRAVE_ROLE": "8",
    "FREEDOM_ROLE": "9",
    "GLORY_ROLE": "10",
    "PEACEFUL_ROLE": "11",
    "MINING_ROLE": "12",
}
for env_name, env_value in ENV_DEFAULTS.items():
    os.environ.setdefault(env_name, env_value)

from services import mining_service


from services.asset_catalog import Media

class ExcellentChannelTests(unittest.IsolatedAsyncioTestCase):
    def test_country_member_uses_country_chat(self):
        self.assertEqual(
            123,
            mining_service.get_excellent_channel_id({"chid": 123}),
        )

    def test_unaffiliated_member_uses_common_chat(self):
        with patch.object(mining_service.config, "get_excellent_chat", return_value=456):
            self.assertEqual(456, mining_service.get_excellent_channel_id(None))

    async def test_cached_channel_is_used(self):
        channel = SimpleNamespace(send=AsyncMock())
        client = SimpleNamespace(
            get_channel=Mock(return_value=channel),
            fetch_channel=AsyncMock(),
        )

        result = await mining_service.get_channel(client, 456)

        self.assertIs(result, channel)
        client.fetch_channel.assert_not_awaited()

    async def test_uncached_channel_is_fetched(self):
        channel = SimpleNamespace(send=AsyncMock())
        client = SimpleNamespace(
            get_channel=Mock(return_value=None),
            fetch_channel=AsyncMock(return_value=channel),
        )

        result = await mining_service.get_channel(client, 456)

        self.assertIs(result, channel)
        client.fetch_channel.assert_awaited_once_with(456)

    async def test_unaffiliated_excellent_is_sent_to_common_chat(self):
        channel = SimpleNamespace(send=AsyncMock())
        client = SimpleNamespace(
            get_channel=Mock(return_value=channel),
            fetch_channel=AsyncMock(),
        )
        file = object()
        embed = object()

        with (
            patch.object(mining_service.config, "get_excellent_chat", return_value=456),
            patch.object(mining_service, "media_file", return_value=nullcontext(file)),
            patch.object(mining_service, "excellent", return_value=embed),
        ):
            await mining_service.send_excellent_notification(
                client,
                user=object(),
                country=None,
                media=Media("result", "result", "Excellent2.png", b"picture"),
            )

        client.get_channel.assert_called_once_with(456)
        channel.send.assert_awaited_once_with(file=file, embed=embed)


class MiningErrorTests(unittest.IsolatedAsyncioTestCase):
    async def test_error_uses_initial_response_before_defer(self):
        interaction = SimpleNamespace(
            response=SimpleNamespace(
                is_done=Mock(return_value=False),
                send_message=AsyncMock(),
            ),
            followup=SimpleNamespace(send=AsyncMock()),
        )

        await mining_service.send_mining_error(interaction)

        interaction.response.send_message.assert_awaited_once()
        interaction.followup.send.assert_not_awaited()

    async def test_error_uses_followup_after_defer(self):
        interaction = SimpleNamespace(
            response=SimpleNamespace(
                is_done=Mock(return_value=True),
                send_message=AsyncMock(),
            ),
            followup=SimpleNamespace(send=AsyncMock()),
        )

        await mining_service.send_mining_error(interaction)

        interaction.followup.send.assert_awaited_once()
        interaction.response.send_message.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
