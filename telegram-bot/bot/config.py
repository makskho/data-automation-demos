"""Настройки из переменных окружения (.env)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


class ConfigError(ValueError):
    """Понятная человеку ошибка настроек."""


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_chat_id: int
    db_path: str = "leads.db"
    faq_path: str = "faq.yaml"
    flood_minutes: int = 10


def load_settings(env: Mapping[str, str]) -> Settings:
    token = (env.get("BOT_TOKEN") or "").strip()
    if not token:
        raise ConfigError("BOT_TOKEN не задан: впишите токен от @BotFather в файл .env")
    if ":" not in token:
        raise ConfigError("BOT_TOKEN выглядит неверно: ожидается формат 123456789:AAA...")

    raw_admin = (env.get("ADMIN_CHAT_ID") or "").strip()
    if not raw_admin:
        raise ConfigError("ADMIN_CHAT_ID не задан: впишите числовой ID чата для заявок в файл .env")
    try:
        admin_chat_id = int(raw_admin)
    except ValueError:
        raise ConfigError(f"ADMIN_CHAT_ID должен быть числом, получено: {raw_admin!r}") from None

    raw_flood = (env.get("FLOOD_MINUTES") or "10").strip()
    try:
        flood_minutes = int(raw_flood)
    except ValueError:
        raise ConfigError(f"FLOOD_MINUTES должен быть целым числом, получено: {raw_flood!r}") from None
    if flood_minutes < 0:
        raise ConfigError("FLOOD_MINUTES не может быть отрицательным")

    return Settings(
        bot_token=token,
        admin_chat_id=admin_chat_id,
        db_path=(env.get("DB_PATH") or "leads.db").strip(),
        faq_path=(env.get("FAQ_PATH") or "faq.yaml").strip(),
        flood_minutes=flood_minutes,
    )
