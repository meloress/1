"""Foydalanuvchilarni boshqarish: ro'yxat, kartochka, ban/premium,
limitni tiklash va to'lovni qaytarish."""

import logging
from typing import Any, Dict, List
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.enums import ParseMode
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from core.loader import bot
from db import database as database_module
from core.config import plan_limits
from handlers.admin.common import (
    format_dt, _format_user_link,
    require_admin_or_deny, require_admin_or_deny_query,
)

logger = logging.getLogger(__name__)


class ManageUserStates(StatesGroup):
    waiting_for_identifier = State()


def _render_user_card(profile: Dict[str, Any]) -> str:
    """Admin uchun foydalanuvchining boshqaruv kartochkasini shakllantiradi."""
    username = (
        f"@{profile['username']}"
        if profile.get('username') and profile['username'] != "Mavjud emas"
        else "Mavjud emas"
    )
    if profile.get('is_banned'):
        status = "🚫 Banlangan"
    elif profile.get('is_active', True):
        status = "🟢 Faol"
    else:
        status = "⚠️ Botni bloklagan"

    plan_type = profile.get('plan_type') or 'free'
    if plan_type != 'free':
        premium_until = profile.get('premium_until')
        name = "Pro" if plan_type == 'pro' else "Premium"
        plan_label = (
            f"💎 {name} ({format_dt(premium_until)} gacha)" if premium_until
            else f"💎 {name} (muddatsiz)"
        )
    else:
        plan_label = "🆓 Free"

    # Limit qatori HAR QANDAY limitli tarif uchun ko'rsatiladi. Ilgari faqat
    # 'free' uchun chizilardi — natijada admin pul to'lagan Pro foydalanuvchi
    # kuniga qancha sarflayotganini umuman ko'ra olmasdi.
    point_limit, file_limit = plan_limits(plan_type)
    limit_line = ""
    if point_limit is not None:
        limit_line = (
            f"📊 <b>Bugungi limit:</b> "
            f"<code>{profile.get('daily_requests_used', 0)} / {point_limit}</code> ball"
            f" · <code>{profile.get('daily_files_used', 0)} / {file_limit}</code> fayl\n"
        )

    return (
        f"🛠 <b>Foydalanuvchini boshqarish</b>\n\n"
        f"👤 <b>Profil:</b> {username}\n"
        f"🆔 <b>ID:</b> <code>{profile['user_id']}</code>\n"
        f"💳 <b>Holat:</b> {status}\n"
        f"📦 <b>Reja:</b> {plan_label}\n"
        f"{limit_line}"
        f"✉️ <b>Jami xabarlar:</b> {profile.get('total_messages', 0)}\n"
        f"📅 <b>Ro'yxatdan o'tgan:</b> {format_dt(profile.get('created_at'))}\n"
        f"🕓 <b>Oxirgi faollik:</b> {format_dt(profile.get('last_seen'))}"
    )


def _user_management_keyboard(user_id: int, is_banned_flag: bool, plan_type: str) -> InlineKeyboardMarkup:
    ban_btn = (
        InlineKeyboardButton(text="✅ Ban olib tashlash", callback_data=f"mu:unban:{user_id}")
        if is_banned_flag else
        InlineKeyboardButton(text="🚫 Ban qilish", callback_data=f"mu:ban:{user_id}")
    )
    plan_btn = (
        InlineKeyboardButton(text="🆓 Free qilish", callback_data=f"mu:free:{user_id}")
        if (plan_type or "free") != "free" else
        InlineKeyboardButton(text="💎 Premium qilish", callback_data=f"mu:premiummenu:{user_id}")
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [ban_btn],
        [plan_btn],
        [InlineKeyboardButton(text="🔄 Limitni reset qilish", callback_data=f"mu:resetquota:{user_id}")],
        [InlineKeyboardButton(text="💸 To'lovlar / qaytarish", callback_data=f"mu:pay:{user_id}")],
        [InlineKeyboardButton(text="🔙 Yopish", callback_data=f"mu:close:{user_id}")],
    ])


def _premium_duration_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="7 kun", callback_data=f"mu:premdays:{user_id}:7"),
            InlineKeyboardButton(text="30 kun", callback_data=f"mu:premdays:{user_id}:30"),
        ],
        [
            InlineKeyboardButton(text="90 kun", callback_data=f"mu:premdays:{user_id}:90"),
            InlineKeyboardButton(text="♾️ Cheksiz", callback_data=f"mu:premdays:{user_id}:inf"),
        ],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data=f"mu:back:{user_id}")],
    ])


def _render_users_page(users: List[Dict[str, Any]], page: int, page_size: int = 10):
    """Render one page of the users list as (html_text, inline_keyboard).

    Each row links to the user via @username (Telegram auto-links these) or,
    for users without a username, via a tg://user?id= mention — the only
    mechanism Telegram's Bot API offers for that case. Note: Telegram may
    still refuse to open that link depending on the target's privacy
    settings; this is a platform limitation, not something the bot controls.
    """
    total = len(users)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    chunk = users[start:start + page_size]

    lines = [f"📄 <b>Foydalanuvchilar ro'yxati</b> ({total} ta)\n"]
    for u in chunk:
        plan_mark = "💎" if (u.get("plan_type") or "free") != "free" else "🆓"
        status_mark = "🚫" if u.get("is_banned") else "🟢"
        link = _format_user_link(u["user_id"], u.get("username"))
        lines.append(f"{status_mark}{plan_mark} {link} — <code>{u['user_id']}</code>")
    text = "\n".join(lines) if chunk else "— Foydalanuvchi topilmadi —"

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"ulist:{page - 1}"))
    nav_row.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="ulist:noop"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"ulist:{page + 1}"))

    kb = InlineKeyboardMarkup(inline_keyboard=[
        nav_row,
        [InlineKeyboardButton(text="🔙 Yopish", callback_data="ulist:close")],
    ])
    return text, kb


async def _show_user_payments(query: CallbackQuery, target_id: int):
    try:
        payments = await database_module.get_user_payments(target_id)
    except Exception:
        logger.exception("get_user_payments error")
        await query.message.answer("❌ DB xatosi.")
        return

    if not payments:
        await query.message.answer("💸 Bu foydalanuvchida Stars to'lovlari yo'q.")
        return

    lines = [f"💸 <b>To'lovlar</b> (<code>{target_id}</code>)\n"]
    rows = []
    for p in payments:
        mark = "↩️ qaytarilgan" if p['refunded_at'] else "✅"
        gift = " 🎁" if p['payer_id'] != p['beneficiary_id'] else ""
        lines.append(
            f"{mark} <b>{p['stars']} ⭐</b> · {p['days']} kun{gift} · "
            f"{format_dt(p['created_at'])}"
        )
        if not p['refunded_at']:
            # ⚠️ callback_data 64 bayt bilan cheklangan, Telegram'ning
            # charge_id'si esa unga sig'maydi — shuning uchun ichki
            # SERIAL id ishlatiladi, charge_id server tomonda topiladi.
            rows.append([InlineKeyboardButton(
                text=f"↩️ {p['stars']} ⭐ qaytarish",
                callback_data=f"mu:refund:{target_id}:{p['id']}")])

    rows.append([InlineKeyboardButton(text="🔙 Yopish", callback_data=f"mu:close:{target_id}")])
    await query.message.answer(
        "\n".join(lines), parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

async def _do_refund(query: CallbackQuery, admin_id: int, payment_id_raw: str):
    try:
        payment = await database_module.get_payment_by_id(int(payment_id_raw))
    except Exception:
        logger.exception("get_payment_by_id error")
        await query.answer("❗ DB xatosi.", show_alert=True)
        return

    if payment is None:
        await query.answer("❌ To'lov topilmadi.", show_alert=True)
        return
    if payment['refunded_at']:
        await query.answer("ℹ️ Bu to'lov allaqachon qaytarilgan.", show_alert=True)
        return

    # ⚠️ TARTIB: AVVAL Telegram, KEYIN baza. Telegram refund'ni rad
    # etishi mumkin (muddat o'tgan, allaqachon qaytarilgan) — bunday
    # holatda foydalanuvchidan tarif olib qo'yilmasligi kerak.
    try:
        await bot.refund_star_payment(
            user_id=payment['payer_id'],                 # PULNI TO'LAGAN odam
            telegram_payment_charge_id=payment['charge_id'],
        )
    except TelegramBadRequest as e:
        # Telegram'ning o'z sababini aynan ko'rsatamiz — "Xatolik"
        # degan umumiy matn admin uchun foydasiz.
        await query.answer(f"❌ Telegram rad etdi: {e.message}", show_alert=True)
        return
    except Exception:
        logger.exception("refund_star_payment error")
        await query.answer("❗ Telegram bilan bog'lanishda xatolik.", show_alert=True)
        return

    try:
        await database_module.mark_payment_refunded(payment['charge_id'], admin_id)
        await database_module.log_admin_action(
            admin_id, "refund_stars", payment['beneficiary_id'], payment['charge_id'])
    except Exception:
        # Pul QAYTARILDI, lekin baza yozilmadi — bu holatni log'da
        # aniq qoldiramiz, chunki tarif hali ham foydalanuvchida turadi.
        logger.exception(
            f"REFUND QILINDI, LEKIN BAZAGA YOZILMADI: charge={payment['charge_id']}")
        await query.answer(
            "⚠️ Pul qaytarildi, lekin bazada belgilanmadi. Log'ni tekshiring.",
            show_alert=True)
        return

    await query.answer("✅ Pul qaytarildi va tarif olib tashlandi.", show_alert=True)
    try:
        await bot.send_message(payment['payer_id'], (
            f"↩️ <b>To'lovingiz qaytarildi</b>\n\n"
            f"💰 {payment['stars']} ⭐ hisobingizga qaytarildi.\n"
            f"🧾 Chek: <code>{payment['charge_id']}</code>"
        ), parse_mode=ParseMode.HTML)
    except Exception:
        pass

# --------------------------------------------------
# FOYDALANUVCHINI BOSHQARISH
# --------------------------------------------------
async def start_manage_user(message: Message, state: FSMContext):
    if not await require_admin_or_deny(message):
        return
    await message.answer("🔍 Foydalanuvchi ID yoki @username kiriting:")
    await state.set_state(ManageUserStates.waiting_for_identifier)

async def process_manage_user_identifier(message: Message, state: FSMContext):
    if not await require_admin_or_deny(message):
        await state.clear()
        return

    identifier = (message.text or "").strip()
    if not identifier:
        await message.answer("❗ Iltimos ID yoki @username kiriting.")
        return

    try:
        user_id = await database_module.get_user_by_identifier(identifier)
    except Exception:
        logger.exception("DB error in process_manage_user_identifier")
        await message.answer("❌ DB xatosi.")
        await state.clear()
        return

    if not user_id:
        await message.answer("❌ Foydalanuvchi topilmadi. Qayta urinib ko'ring:")
        return

    await state.clear()

    try:
        profile = await database_module.get_full_user_profile(user_id)
    except Exception:
        logger.exception("get_full_user_profile error")
        await message.answer("❌ DB xatosi.")
        return

    if not profile:
        await message.answer("❌ Profil topilmadi.")
        return

    text = _render_user_card(profile)
    kb = _user_management_keyboard(user_id, profile.get('is_banned', False), profile.get('plan_type', 'free'))
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def manage_user_action_callback(query: CallbackQuery):
    if not await require_admin_or_deny_query(query):
        return

    parts = (query.data or "").split(":")
    if len(parts) < 3:
        await query.answer("❌ Noto'g'ri so'rov.", show_alert=True)
        return

    action = parts[1]
    try:
        target_id = int(parts[2])
    except ValueError:
        await query.answer("❌ Noto'g'ri ID.", show_alert=True)
        return

    if action == "close":
        await query.answer()
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    if action == "premiummenu":
        await query.answer()
        try:
            await query.message.edit_reply_markup(reply_markup=_premium_duration_keyboard(target_id))
        except Exception:
            pass
        return

    if action == "back":
        await query.answer()
        try:
            profile = await database_module.get_full_user_profile(target_id)
        except Exception:
            profile = None
        if profile:
            kb = _user_management_keyboard(target_id, profile.get('is_banned', False), profile.get('plan_type', 'free'))
            try:
                await query.message.edit_reply_markup(reply_markup=kb)
            except Exception:
                pass
        return

    admin_id = query.from_user.id

    if action == "pay":
        await query.answer()
        await _show_user_payments(query, target_id)
        return

    if action == "refund":
        # parts: mu:refund:<target_id>:<payment_id>
        if len(parts) != 4:
            await query.answer("❌ Noto'g'ri so'rov.", show_alert=True)
            return
        await _do_refund(query, admin_id, parts[3])
        return
    try:
        if action == "ban":
            await database_module.ban_user(target_id)
            await database_module.log_admin_action(admin_id, "ban_user", target_id)
        elif action == "unban":
            await database_module.unban_user(target_id)
            await database_module.log_admin_action(admin_id, "unban_user", target_id)
        elif action == "premdays":
            if len(parts) != 4:
                await query.answer("❌ Noto'g'ri so'rov.", show_alert=True)
                return
            days_token = parts[3]
            days = None if days_token == "inf" else int(days_token)
            await database_module.set_user_premium(target_id, days)
            await database_module.log_admin_action(admin_id, "set_premium", target_id, days_token)
        elif action == "free":
            await database_module.set_user_plan(target_id, "free")
            await database_module.log_admin_action(admin_id, "set_plan", target_id, "free")
        elif action == "resetquota":
            await database_module.reset_user_quota(target_id)
            await database_module.log_admin_action(admin_id, "reset_quota", target_id)
        else:
            await query.answer("❌ Noma'lum amal.", show_alert=True)
            return
    except Exception:
        logger.exception(f"manage_user_action_callback error: {action} -> {target_id}")
        await query.answer("❗ Xatolik yuz berdi.", show_alert=True)
        return

    await query.answer("✅ Bajarildi.")

    try:
        profile = await database_module.get_full_user_profile(target_id)
    except Exception:
        profile = None

    if profile:
        text = _render_user_card(profile)
        kb = _user_management_keyboard(target_id, profile.get('is_banned', False), profile.get('plan_type', 'free'))
        try:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass


async def handle_users_list(message: Message):
    if not await require_admin_or_deny(message):
        return
    try:
        users = await database_module.get_all_users()
    except Exception:
        logger.exception("handle_users_list error")
        await message.answer("❌ DB xatosi.")
        return
    text, kb = _render_users_page(users, 0)
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def users_list_page_callback(query: CallbackQuery):
    if not await require_admin_or_deny_query(query):
        return

    suffix = (query.data or "").split(":", 1)[-1]
    if suffix == "close":
        await query.answer()
        try:
            await query.message.delete()
        except Exception:
            pass
        return
    if suffix == "noop":
        await query.answer()
        return

    try:
        page = int(suffix)
    except ValueError:
        await query.answer("❌ Noto'g'ri so'rov.", show_alert=True)
        return

    try:
        users = await database_module.get_all_users()
    except Exception:
        logger.exception("users_list_page_callback error")
        await query.answer("❌ DB xatosi.", show_alert=True)
        return

    await query.answer()
    text, kb = _render_users_page(users, page)
    try:
        await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    except Exception:
        pass
