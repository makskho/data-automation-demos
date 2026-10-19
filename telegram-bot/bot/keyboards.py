"""Inline-клавиатуры. callback_data: 'n:<id>' - пункт FAQ, 'n:root' - главное меню, 'lead' - форма."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .faq import ROOT_ID, FaqNode, FaqTree

LEAD_CB = "lead"
NODE_PREFIX = "n:"
LEAD_BUTTON = "📝 Оставить заявку"


def _node_btn(node: FaqNode) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=node.title, callback_data=NODE_PREFIX + node.id)


def main_menu(tree: FaqTree) -> InlineKeyboardMarkup:
    rows = [[_node_btn(n)] for n in tree.roots]
    rows.append([InlineKeyboardButton(text=LEAD_BUTTON, callback_data=LEAD_CB)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def node_menu(node: FaqNode) -> InlineKeyboardMarkup:
    rows = [[_node_btn(child)] for child in node.children]
    if not node.children:
        rows.append([InlineKeyboardButton(text=LEAD_BUTTON, callback_data=LEAD_CB)])
    nav = [InlineKeyboardButton(text="⬅️ Назад", callback_data=NODE_PREFIX + node.parent_id)]
    if node.parent_id != ROOT_ID:
        nav.append(InlineKeyboardButton(text="🏠 В меню", callback_data=NODE_PREFIX + ROOT_ID))
    rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)
