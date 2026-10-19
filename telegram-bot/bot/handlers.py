"""Обработчики: меню FAQ, форма заявки, /export для администратора."""
from __future__ import annotations

import logging
import math
from datetime import timedelta

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from .config import Settings
from .db import Lead, LeadRepo
from .export import build_xlsx
from .faq import ROOT_ID, FaqTree
from .keyboards import LEAD_CB, NODE_PREFIX, main_menu, node_menu
from .validators import validate_name, validate_phone, validate_task

log = logging.getLogger(__name__)


class LeadForm(StatesGroup):
    name = State()
    phone = State()
    task = State()


FORM_STATES = (LeadForm.name, LeadForm.phone, LeadForm.task)


def flood_text(wait: timedelta) -> str:
    minutes = max(1, math.ceil(wait.total_seconds() / 60))
    return (
        "Ваша заявка уже у нас, мы с вами свяжемся. "
        f"Отправить новую можно через {minutes} мин."
    )


def admin_text(lead: Lead) -> str:
    who = f"@{lead.username}" if lead.username else f"id {lead.user_id}"
    return (
        f"📩 Новая заявка №{lead.id}\n"
        f"Имя: {lead.name}\n"
        f"Телефон: {lead.phone}\n"
        f"Задача: {lead.task}\n"
        f"Telegram: {who}"
    )


def is_admin(message: Message, settings: Settings) -> bool:
    if message.chat.id == settings.admin_chat_id:
        return True
    return message.from_user is not None and message.from_user.id == settings.admin_chat_id


def create_router() -> Router:
    router = Router(name="leads")

    # ---- команды -------------------------------------------------------
    @router.message(Command("start"))
    async def cmd_start(message: Message, state: FSMContext, faq: FaqTree) -> None:
        await state.clear()
        await message.answer(faq.welcome, reply_markup=main_menu(faq))

    @router.message(Command("cancel"))
    async def cmd_cancel(message: Message, state: FSMContext, faq: FaqTree) -> None:
        current = await state.get_state()
        await state.clear()
        text = "Заявка отменена." if current else "Отменять нечего."
        await message.answer(text, reply_markup=main_menu(faq))

    @router.message(Command("export"))
    async def cmd_export(message: Message, repo: LeadRepo, settings: Settings) -> None:
        if not is_admin(message, settings):
            await message.answer("Эта команда доступна только администратору.")
            return
        leads = repo.all()
        if not leads:
            await message.answer("Заявок пока нет.")
            return
        document = BufferedInputFile(build_xlsx(leads), filename="leads.xlsx")
        await message.answer_document(document, caption=f"Заявок: {len(leads)}")

    # ---- меню FAQ ------------------------------------------------------
    @router.callback_query(F.data.startswith(NODE_PREFIX))
    async def cb_node(callback: CallbackQuery, state: FSMContext, faq: FaqTree) -> None:
        await state.clear()
        node_id = (callback.data or "")[len(NODE_PREFIX):]
        if node_id == ROOT_ID:
            text, markup = faq.welcome, main_menu(faq)
        else:
            node = faq.get(node_id)
            if node is None:  # кнопка из старого сообщения, которой уже нет в файле
                text, markup = faq.welcome, main_menu(faq)
            else:
                text, markup = node.text or node.title, node_menu(node)
        await callback.answer()
        if isinstance(callback.message, Message):
            try:
                await callback.message.edit_text(text, reply_markup=markup)
            except TelegramBadRequest as exc:
                if "not modified" not in str(exc):
                    raise

    # ---- форма заявки --------------------------------------------------
    @router.callback_query(F.data == LEAD_CB)
    async def cb_lead(callback: CallbackQuery, state: FSMContext, repo: LeadRepo, settings: Settings) -> None:
        await callback.answer()
        if not isinstance(callback.message, Message):
            return
        wait = repo.flood_wait(callback.from_user.id, settings.flood_minutes)
        if wait:
            await callback.message.answer(flood_text(wait))
            return
        await state.set_state(LeadForm.name)
        await callback.message.answer("Как вас зовут? (для отмены - /cancel)")

    @router.message(LeadForm.name, F.text)
    async def form_name(message: Message, state: FSMContext) -> None:
        name, error = validate_name(message.text or "")
        if error:
            await message.answer(error)
            return
        await state.update_data(name=name)
        await state.set_state(LeadForm.phone)
        await message.answer("Укажите телефон для связи, например +7 999 123-45-67.")

    @router.message(LeadForm.phone, F.text)
    async def form_phone(message: Message, state: FSMContext) -> None:
        phone, error = validate_phone(message.text or "")
        if error:
            await message.answer(error)
            return
        await state.update_data(phone=phone)
        await state.set_state(LeadForm.task)
        await message.answer("Коротко опишите задачу: что нужно сделать и к какому сроку.")

    @router.message(LeadForm.task, F.text)
    async def form_task(
        message: Message,
        state: FSMContext,
        bot: Bot,
        repo: LeadRepo,
        settings: Settings,
        faq: FaqTree,
    ) -> None:
        task, error = validate_task(message.text or "")
        if error:
            await message.answer(error)
            return
        user = message.from_user
        if user is None:
            return
        # Повторная проверка: за время заполнения формы заявка могла уйти из другого диалога.
        wait = repo.flood_wait(user.id, settings.flood_minutes)
        if wait:
            await state.clear()
            await message.answer(flood_text(wait), reply_markup=main_menu(faq))
            return
        data = await state.get_data()
        lead = repo.add(user.id, user.username, data["name"], data["phone"], task)
        await state.clear()
        await message.answer(
            f"Спасибо, {lead.name}! Заявка №{lead.id} принята, мы свяжемся с вами по номеру {lead.phone}.",
            reply_markup=main_menu(faq),
        )
        try:
            await bot.send_message(settings.admin_chat_id, admin_text(lead))
        except Exception:  # заявка уже сохранена, сбой уведомления не должен её терять
            log.exception("Не удалось отправить уведомление администратору (заявка №%s)", lead.id)

    @router.message(StateFilter(*FORM_STATES))
    async def form_not_text(message: Message) -> None:
        await message.answer("Пожалуйста, ответьте текстом. Для отмены - /cancel.")

    # ---- всё остальное -------------------------------------------------
    @router.message()
    async def fallback(message: Message) -> None:
        await message.answer("Нажмите /start, чтобы открыть меню.")

    return router
