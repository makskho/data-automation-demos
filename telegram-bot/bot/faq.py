"""Дерево FAQ из YAML/JSON-файла: загрузка и проверка.

Формат файла:

    welcome: "Текст приветствия"
    items:
      - id: prices            # уникальный, a-z 0-9 _ -, до 40 символов
        title: "Цены"         # надпись на кнопке, до 60 символов
        text: "Ответ"         # показывается при нажатии (обязателен для кнопки без вложенных)
        children: [...]       # вложенные кнопки (необязательно)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT_ID = "root"
_ID_RE = re.compile(r"^[a-z0-9_-]{1,40}$")
MAX_TITLE = 60
MAX_TEXT = 4000  # лимит Telegram на сообщение - 4096 символов


class FaqError(ValueError):
    """Файл FAQ составлен неверно; в тексте указано место ошибки."""


@dataclass(frozen=True)
class FaqNode:
    id: str
    title: str
    text: str
    parent_id: str  # ROOT_ID для первого уровня
    children: tuple["FaqNode", ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FaqTree:
    welcome: str
    roots: tuple[FaqNode, ...]
    nodes: dict[str, FaqNode]

    def get(self, node_id: str) -> FaqNode | None:
        return self.nodes.get(node_id)


def load_faq(path: str | Path) -> FaqTree:
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FaqError(f"не удалось прочитать файл FAQ {path}: {exc}") from exc
    try:
        data = json.loads(raw) if path.suffix.lower() == ".json" else yaml.safe_load(raw)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise FaqError(f"файл FAQ {path.name} не разобран: {exc}") from exc
    return parse_faq(data)


def parse_faq(data: Any) -> FaqTree:
    if not isinstance(data, dict):
        raise FaqError("корень файла должен быть словарём с ключами welcome и items")
    welcome = data.get("welcome")
    if not isinstance(welcome, str) or not welcome.strip():
        raise FaqError("нет текста приветствия: ключ welcome должен быть непустой строкой")
    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise FaqError("ключ items должен быть непустым списком кнопок")

    nodes: dict[str, FaqNode] = {}

    def build(raw: Any, where: str, parent_id: str) -> FaqNode:
        if not isinstance(raw, dict):
            raise FaqError(f"{where}: элемент должен быть словарём")
        node_id = raw.get("id")
        if not isinstance(node_id, str) or not _ID_RE.match(node_id):
            raise FaqError(
                f"{where}: id должен состоять из a-z, 0-9, _ и -, до 40 символов (получено {node_id!r})"
            )
        if node_id == ROOT_ID:
            raise FaqError(f"{where}: id '{ROOT_ID}' зарезервирован")
        if node_id in nodes:
            raise FaqError(f"{where}: id '{node_id}' повторяется")
        title = raw.get("title")
        if not isinstance(title, str) or not title.strip():
            raise FaqError(f"{where} ({node_id}): нет title")
        if len(title) > MAX_TITLE:
            raise FaqError(f"{where} ({node_id}): title длиннее {MAX_TITLE} символов")
        text = raw.get("text", "")
        if text is None:
            text = ""
        if not isinstance(text, str):
            raise FaqError(f"{where} ({node_id}): text должен быть строкой")
        if len(text) > MAX_TEXT:
            raise FaqError(f"{where} ({node_id}): text длиннее {MAX_TEXT} символов")
        raw_children = raw.get("children") or []
        if not isinstance(raw_children, list):
            raise FaqError(f"{where} ({node_id}): children должен быть списком")
        if not raw_children and not text.strip():
            raise FaqError(f"{where} ({node_id}): у кнопки без вложенных пунктов должен быть text")
        # id резервируется до обхода детей, чтобы дубликат нашёлся и среди потомков.
        nodes[node_id] = FaqNode(node_id, title.strip(), text.strip(), parent_id)
        children = tuple(
            build(child, f"{where}.children[{i}]", node_id) for i, child in enumerate(raw_children)
        )
        node = FaqNode(node_id, title.strip(), text.strip(), parent_id, children)
        nodes[node_id] = node
        return node

    roots = tuple(build(raw, f"items[{i}]", ROOT_ID) for i, raw in enumerate(items))
    return FaqTree(welcome=welcome.strip(), roots=roots, nodes=nodes)
