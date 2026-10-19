"""Проверка полей заявки. Каждая validate_* возвращает (значение, ошибка)."""
from __future__ import annotations

import re

NAME_MIN, NAME_MAX = 2, 60
TASK_MIN, TASK_MAX = 10, 1000

_NAME_CHARS = re.compile(r"^[^\W\d_]+(?:[ '.\-][^\W\d_]+)*\.?$")


def validate_name(raw: str) -> tuple[str | None, str | None]:
    name = " ".join((raw or "").split())
    if len(name) < NAME_MIN:
        return None, "Имя слишком короткое. Напишите, как к вам обращаться."
    if len(name) > NAME_MAX:
        return None, f"Имя длиннее {NAME_MAX} символов. Напишите короче."
    if not _NAME_CHARS.match(name):
        return None, "Имя должно состоять из букв (без цифр и символов). Попробуйте ещё раз."
    return name, None


def normalize_phone(raw: str) -> str | None:
    """Приводит номер к виду +79991234567; None, если номер неверный.

    Принимает российские форматы (8..., 7..., +7..., 9XXXXXXXXX) с пробелами, скобками и
    дефисами и международные номера вида +<от 10 до 15 цифр>.
    """
    text = (raw or "").strip()
    if not re.fullmatch(r"\+?[\d\s()\-.]+", text):
        return None
    digits = re.sub(r"\D", "", text)
    if text.startswith("+") and not digits.startswith("7"):
        return "+" + digits if 10 <= len(digits) <= 15 else None
    if len(digits) == 11 and digits[0] in "78":
        digits = digits[1:]
    elif len(digits) != 10 or text.startswith("+"):
        return None
    if digits[0] not in "34589":  # российские мобильные (9) и городские/федеральные коды
        return None
    return "+7" + digits


def validate_phone(raw: str) -> tuple[str | None, str | None]:
    phone = normalize_phone(raw)
    if phone is None:
        return None, "Не удалось распознать номер. Пример: +7 999 123-45-67 или 8 (999) 123-45-67."
    return phone, None


def validate_task(raw: str) -> tuple[str | None, str | None]:
    task = (raw or "").strip()
    if len(task) < TASK_MIN:
        return None, f"Опишите задачу чуть подробнее (минимум {TASK_MIN} символов)."
    if len(task) > TASK_MAX:
        return None, f"Описание длиннее {TASK_MAX} символов. Сократите, пожалуйста."
    return task, None
