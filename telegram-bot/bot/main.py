"""Сборка и запуск бота."""
from __future__ import annotations

import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

from .config import ConfigError, Settings, load_settings
from .db import LeadRepo
from .faq import FaqError, FaqTree, load_faq
from .handlers import create_router


def build_dispatcher(settings: Settings, faq: FaqTree, repo: LeadRepo) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage(), settings=settings, faq=faq, repo=repo)
    dp.include_router(create_router())
    return dp


async def main() -> None:
    load_dotenv()
    settings = load_settings(os.environ)
    faq = load_faq(settings.faq_path)
    repo = LeadRepo(settings.db_path)
    bot = Bot(settings.bot_token)
    dp = build_dispatcher(settings, faq, repo)
    logging.getLogger(__name__).info("Бот запущен, FAQ: %d пунктов", len(faq.nodes))
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        asyncio.run(main())
    except (ConfigError, FaqError) as exc:
        sys.exit(f"Ошибка настройки: {exc}")
    except KeyboardInterrupt:
        pass
