"""Общие заготовки тестов. Сеть не нужна: Bot работает через подмену HTTP-сессии."""
from __future__ import annotations

import itertools
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendDocument, SendMessage
from aiogram.types import Chat, Message, Update

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config import Settings  # noqa: E402
from bot.db import LeadRepo  # noqa: E402
from bot.faq import load_faq  # noqa: E402
from bot.main import build_dispatcher  # noqa: E402

FAQ_PATH = Path(__file__).resolve().parent.parent / "faq.yaml"
ADMIN_ID = 777
USER_ID = 1001


class FakeSession(BaseSession):
    """Запоминает вызовы Bot API и отвечает заглушками."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list = []
        self._ids = itertools.count(5000)
        self.fail_chat_ids: set[int] = set()

    async def close(self) -> None:
        pass

    async def stream_content(self, *args, **kwargs):  # pragma: no cover
        yield b""

    async def make_request(self, bot, method, timeout=None):
        chat_id = getattr(method, "chat_id", None)
        if chat_id in self.fail_chat_ids:
            raise RuntimeError("chat unavailable")
        self.calls.append(method)
        if isinstance(method, AnswerCallbackQuery):
            return True
        if isinstance(method, (SendMessage, SendDocument, EditMessageText)):
            return Message(
                message_id=next(self._ids),
                date=datetime.now(timezone.utc),
                chat=Chat(id=chat_id or 0, type="private"),
                text=getattr(method, "text", None),
            )
        raise AssertionError(f"неожиданный вызов Bot API: {type(method).__name__}")

    def sent(self, kind: type, chat_id: int | None = None) -> list:
        return [
            c for c in self.calls
            if isinstance(c, kind) and (chat_id is None or getattr(c, "chat_id", None) == chat_id)
        ]

    def texts(self, chat_id: int) -> list[str]:
        return [c.text for c in self.sent(SendMessage, chat_id)]


class Harness:
    """Диспетчер + бот с подменённой сессией + помощники для отправки обновлений."""

    def __init__(self, repo: LeadRepo, settings: Settings) -> None:
        self.session = FakeSession()
        self.bot = Bot("123456:TEST", session=self.session)
        self.repo = repo
        self.settings = settings
        self.faq = load_faq(FAQ_PATH)
        self.dp = build_dispatcher(settings, self.faq, repo)
        self._update_id = itertools.count(1)
        self._msg_id = itertools.count(1)

    async def _feed(self, **payload) -> None:
        update = Update.model_validate({"update_id": next(self._update_id), **payload}, context={"bot": self.bot})
        await self.dp.feed_update(self.bot, update)

    @staticmethod
    def _user(user_id: int, username: str | None) -> dict:
        user = {"id": user_id, "is_bot": False, "first_name": "Тест"}
        if username:
            user["username"] = username
        return user

    async def say(self, text: str, user_id: int = USER_ID, username: str | None = "client") -> None:
        message = {
            "message_id": next(self._msg_id),
            "date": 1_700_000_000,
            "chat": {"id": user_id, "type": "private"},
            "from": self._user(user_id, username),
            "text": text,
        }
        if text.startswith("/"):
            command = text.split()[0]
            message["entities"] = [{"type": "bot_command", "offset": 0, "length": len(command)}]
        await self._feed(message=message)

    async def say_photo(self, user_id: int = USER_ID) -> None:
        await self._feed(
            message={
                "message_id": next(self._msg_id),
                "date": 1_700_000_000,
                "chat": {"id": user_id, "type": "private"},
                "from": self._user(user_id, "client"),
                "photo": [{"file_id": "x", "file_unique_id": "y", "width": 1, "height": 1}],
            }
        )

    async def press(self, data: str, user_id: int = USER_ID, username: str | None = "client") -> None:
        await self._feed(
            callback_query={
                "id": str(next(self._msg_id)),
                "from": self._user(user_id, username),
                "chat_instance": "ci",
                "data": data,
                "message": {
                    "message_id": next(self._msg_id),
                    "date": 1_700_000_000,
                    "chat": {"id": user_id, "type": "private"},
                    "from": {"id": 1, "is_bot": True, "first_name": "Bot"},
                    "text": "menu",
                },
            }
        )


@pytest.fixture
def repo(tmp_path) -> LeadRepo:
    return LeadRepo(str(tmp_path / "leads.db"))


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        bot_token="123456:TEST",
        admin_chat_id=ADMIN_ID,
        db_path=str(tmp_path / "leads.db"),
        faq_path=str(FAQ_PATH),
        flood_minutes=10,
    )


@pytest.fixture
def harness(repo, settings) -> Harness:
    return Harness(repo, settings)
