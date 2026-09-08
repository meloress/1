"""Tizim bo'limi: texnik ta'til, kuzatish, admin qo'shish/o'chirish
va foydalanuvchining adminga xabari (report).

⚠️ `report_callback` va `process_report_message` — YAGONA admin
bo'lmagan handlerlar: ularni foydalanuvchi ishga tushiradi,
shuning uchun ularda admin tekshiruvi ATAYLAB yo'q."""

import logging
import json
from datetime import datetime, timezone, timedelta
from typing import Optional
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.enums import ParseMode
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from core.loader import bot
from db import database as database_module
from handlers.admin.common import (
    format_dt, _format_user_link, TASHKENT_TZ,
    require_admin_or_deny, require_admin_or_deny_query,
)

REMOVE_BLOCK_DAYS = 3

logger = logging.getLogger(__name__)


class AddAdminStates(StatesGroup):
    waiting_for_admin_id = State()


class RemoveAdminStates(StatesGroup):
    waiting_for_admin_id = State()


class MaintenanceStates(StatesGroup):
    waiting_for_message = State()


class WatchStates(StatesGroup):
    waiting_for_group_id = State()
    waiting_for_identifier = State()


# --- Yangi: ReportStates (foydalanuvchi adminga xabar yozganda foydalaniladi) ---
class ReportStates(StatesGroup):
    waiting_for_report_message = State()


async def _check_can_remove_admin(requester_id: int, target_id: int) -> Optional[str]:
    """Shared eligibility check for both the inline and text remove-admin flows.

    Returns an error message to show the requester, or None if the removal
    may proceed.
    """
    try:
        is_super = await database_module.is_superadmin(requester_id)
    except Exception:
        logger.exception("DB error checking is_superadmin")
        is_super = False

    # requester_meta from DB may contain formatted created_at; for time-checking fetch raw created_at directly
    requester_created_at = None
    try:
        async with database_module.pool.acquire() as conn:
            requester_created_at = await conn.fetchval(
                'SELECT created_at FROM admins WHERE user_id = $1', requester_id
            )
    except Exception:
        logger.exception("DB error fetching requester created_at")

    if not is_super and requester_created_at is None:
        return "❌ Bu amal faqat adminlar uchun."

    if target_id == requester_id:
        return "❗ O'zingizni o'chira olmaysiz."

    try:
        if await database_module.is_superadmin(target_id):
            return "❗ Bu foydalanuvchi superadmin. Uni o'chirish faqat DB orqali amalga oshiriladi."
    except Exception:
        logger.exception("DB error checking is_superadmin for target")
        return "❗ Server xatosi. Amal bajarilmadi."

    if not is_super:
        if isinstance(requester_created_at, datetime):
            created_at_dt = requester_created_at
            if created_at_dt.tzinfo is not None:
                created_utc = created_at_dt.astimezone(timezone.utc).replace(tzinfo=None)
            else:
                created_utc = created_at_dt
        else:
            # fallback: deny if we cannot determine created time
            return "❌ Sizning admin vaqtingizni aniqlab bo'lmadi. Amal bajarilmadi."

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        allowed_after = created_utc + timedelta(days=REMOVE_BLOCK_DAYS)
        if now < allowed_after:
            # show allowed time in Tashkent for clarity
            allowed_after_utc = allowed_after.replace(tzinfo=timezone.utc)
            allowed_tz = allowed_after_utc.astimezone(TASHKENT_TZ)
            allowed_str = allowed_tz.strftime("%Y-%m-%d %H:%M:%S %Z")
            return (
                f"❗ Siz yangi admin ekansiz — boshqa adminlarni o'chirish huquqi "
                f"{allowed_str} dan keyin faollashadi."
            )

    if not await database_module.is_admin(target_id):
        return "ℹ️ Bu foydalanuvchi admin emas yoki allaqachon o'chirilgan."

    admins = await database_module.get_admins()
    super_exists = bool(await database_module.get_superadmin_id())
    if len(admins) <= 1 and not super_exists:
        return "❗ Bu oxirgi admin. Avval yangi admin qo'shing, keyin o'chiring."

    return None


async def show_maintenance_menu(message: Message):
    if not await require_admin_or_deny(message):
        return
    try:
        state_info = await database_module.get_maintenance()
    except Exception:
        logger.exception("get_maintenance error")
        await message.answer("❌ DB xatosi.")
        return

    active = state_info["active"]
    status_line = "🔴 Hozir YOQILGAN" if active else "🟢 Hozir O'CHIRILGAN"
    text = (
        f"🛠 <b>Texnik ta'til rejimi</b>\n\n"
        f"Holat: {status_line}\n"
        f"Xabar: {state_info['message']}"
    )
    toggle_btn = (
        InlineKeyboardButton(text="🟢 O'chirish", callback_data="maint:off")
        if active else
        InlineKeyboardButton(text="🔴 Yoqish", callback_data="maint:on")
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[toggle_btn]])
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def maintenance_toggle_callback(query: CallbackQuery, state: FSMContext):
    if not await require_admin_or_deny_query(query):
        return

    action = (query.data or "").split(":", 1)[-1]
    if action == "off":
        try:
            await database_module.set_maintenance(False)
        except Exception:
            logger.exception("set_maintenance(False) error")
            await query.answer("❗ Xatolik yuz berdi.", show_alert=True)
            return
        await query.answer("✅ Texnik ta'til o'chirildi.")
        try:
            await query.message.edit_text("🟢 Texnik ta'til rejimi o'chirildi. Bot oddiy tartibda ishlamoqda.")
        except Exception:
            pass
        return

    if action == "on":
        await query.answer()
        try:
            await query.message.edit_text(
                "✍️ Foydalanuvchilarga ko'rsatiladigan xabarni yozing "
                "(standart xabar uchun /skip yozing):"
            )
        except Exception:
            pass
        await state.set_state(MaintenanceStates.waiting_for_message)
        return

    await query.answer("❌ Noma'lum amal.", show_alert=True)

async def process_maintenance_message(message: Message, state: FSMContext):
    if not await require_admin_or_deny(message):
        await state.clear()
        return

    text = (message.text or "").strip()
    custom_message = None if text == "/skip" or not text else text
    try:
        await database_module.set_maintenance(True, custom_message)
    except Exception:
        logger.exception("set_maintenance(True) error")
        await message.answer("❗ Xatolik yuz berdi.")
        await state.clear()
        return

    await state.clear()
    await message.answer("🔴 Texnik ta'til rejimi yoqildi. Oddiy foydalanuvchilar endi maxsus xabar ko'radi.")

async def _render_watch_menu():
    """Returns (text, kb) for the configured watch panel, or (None, None) if no group is set yet."""
    group_id = await database_module.get_watch_group_id()
    if not group_id:
        return None, None

    try:
        watchlist = await database_module.get_watchlist()
    except Exception:
        logger.exception("get_watchlist error")
        watchlist = []

    lines = [f"👁 <b>Kuzatuv paneli</b>\n\n📡 Guruh: <code>{group_id}</code>\n"]
    if watchlist:
        lines.append(f"Kuzatilayotganlar ({len(watchlist)}):")
        for w in watchlist:
            lines.append(f"• {_format_user_link(w['user_id'], w.get('username'))} — <code>{w['user_id']}</code>")
    else:
        lines.append("Hozircha hech kim kuzatilmayapti.")
    text = "\n".join(lines)

    rows = []
    for w in watchlist:
        label = f"@{w['username']}" if w.get('username') else f"ID:{w['user_id']}"
        rows.append([InlineKeyboardButton(text=f"❌ {label}", callback_data=f"watch:remove:{w['user_id']}")])
    rows.append([InlineKeyboardButton(text="➕ Yangi user qo'shish", callback_data="watch:add")])
    rows.append([InlineKeyboardButton(text="🔁 Guruhni almashtirish", callback_data="watch:regroup")])
    rows.append([InlineKeyboardButton(text="🔙 Yopish", callback_data="watch:close")])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)

async def show_watch_menu(message: Message, state: FSMContext):
    if not await require_admin_or_deny(message):
        return
    try:
        text, kb = await _render_watch_menu()
    except Exception:
        logger.exception("show_watch_menu error")
        await message.answer("❌ DB xatosi.")
        return

    if text is None:
        await message.answer(
            "👁 Hali kuzatuv guruhi sozlanmagan.\n\n"
            "Botni kuzatuv uchun ishlatmoqchi bo'lgan guruhga (admin sifatida) qo'shing, "
            "so'ng o'sha guruhning ID sini yuboring:"
        )
        await state.set_state(WatchStates.waiting_for_group_id)
        return

    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def process_watch_group_id(message: Message, state: FSMContext):
    if not await require_admin_or_deny(message):
        await state.clear()
        return

    text = (message.text or "").strip()
    try:
        group_id = int(text)
    except ValueError:
        await message.answer("❗ Iltimos, guruh ID sini raqam sifatida yuboring (masalan -1001234567890).")
        return

    try:
        await bot.send_message(group_id, "✅ Bu guruh kuzatuv uchun ulandi.")
    except Exception:
        await message.answer(
            "❌ Guruhga xabar yubora olmadim. Botni shu guruhga (admin sifatida) qo'shganingizga "
            "va ID to'g'ri ekanligiga ishonch hosil qiling, so'ng qayta yuboring."
        )
        return

    try:
        await database_module.set_watch_group_id(group_id)
    except Exception:
        logger.exception("set_watch_group_id error")
        await message.answer("❗ Xatolik yuz berdi.")
        await state.clear()
        return

    await state.clear()
    await message.answer(f"✅ Kuzatuv guruhi sozlandi: <code>{group_id}</code>", parse_mode=ParseMode.HTML)

async def process_watch_identifier(message: Message, state: FSMContext):
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
        logger.exception("DB error in process_watch_identifier")
        await message.answer("❌ DB xatosi.")
        await state.clear()
        return

    if not user_id:
        await message.answer("❌ Foydalanuvchi topilmadi. Qayta urinib ko'ring:")
        return

    try:
        await database_module.add_watch(user_id, message.from_user.id)
    except Exception:
        logger.exception("add_watch error")
        await message.answer("❗ Xatolik yuz berdi.")
        await state.clear()
        return

    await state.clear()
    await message.answer(f"✅ Endi kuzatuvda: <code>{user_id}</code>", parse_mode=ParseMode.HTML)

async def watch_menu_callback(query: CallbackQuery, state: FSMContext):
    if not await require_admin_or_deny_query(query):
        return

    parts = (query.data or "").split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "close":
        await query.answer()
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    if action == "add":
        await query.answer()
        try:
            await query.message.edit_text("🔍 Kuzatmoqchi bo'lgan foydalanuvchi ID yoki @username kiriting:")
        except Exception:
            pass
        await state.set_state(WatchStates.waiting_for_identifier)
        return

    if action == "regroup":
        await query.answer()
        try:
            await query.message.edit_text(
                "Botni yangi guruhga (admin sifatida) qo'shing, so'ng o'sha guruhning ID sini yuboring:"
            )
        except Exception:
            pass
        await state.set_state(WatchStates.waiting_for_group_id)
        return

    if action == "remove":
        if len(parts) != 3:
            await query.answer("❌ Noto'g'ri so'rov.", show_alert=True)
            return
        try:
            target_id = int(parts[2])
        except ValueError:
            await query.answer("❌ Noto'g'ri ID.", show_alert=True)
            return
        try:
            await database_module.remove_watch(target_id)
        except Exception:
            logger.exception("remove_watch error")
            await query.answer("❗ Xatolik yuz berdi.", show_alert=True)
            return
        await query.answer("✅ Kuzatuvdan olib tashlandi.")
        text, kb = await _render_watch_menu()
        try:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
        return

    await query.answer("❌ Noma'lum amal.", show_alert=True)

async def start_add_admin(message: Message, state: FSMContext):
    if not await require_admin_or_deny(message):
        return
    await message.answer("➕ Iltimos, yangi admin qilmoqchi bo'lgan foydalanuvchi ID sini kiriting:")
    await state.set_state(AddAdminStates.waiting_for_admin_id)

async def process_add_admin(message: Message, state: FSMContext):
    if not await require_admin_or_deny(message):
        await state.clear()
        return
    text = (message.text or "").strip()
    try:
        new_admin_id = int(text)
    except ValueError:
        await message.answer("❗ Iltimos faqat sonli ID kiriting. Masalan: 123456789")
        await state.clear()
        return

    username = None
    try:
        async with database_module.pool.acquire() as conn:
            username = await conn.fetchval('SELECT username FROM users WHERE user_id = $1', new_admin_id)
    except Exception:
        logger.exception("DB error while fetching username for new admin")

    try:
        if await database_module.is_admin(new_admin_id):
            await message.answer(f"ℹ️ {new_admin_id} allaqachon admin sifatida mavjud.")
            await state.clear()
            return

        await database_module.add_admin(new_admin_id, username=username)
        await database_module.log_admin_action(message.from_user.id, "add_admin", new_admin_id, f"added by {message.from_user.id}")
        await message.answer(f"✅ {new_admin_id} admin qilindi")
    except Exception:
        logger.exception("process_add_admin error")
        await message.answer("❗ Xatolik yuz berdi: DB yoki server xatosi")
    finally:
        await state.clear()

async def start_remove_admin(message: Message, state: FSMContext):
    if not await require_admin_or_deny(message):
        return

    try:
        admins = await database_module.get_admins()
    except Exception:
        logger.exception("DB error in start_remove_admin")
        await message.answer("❌ DB xatosi.")
        return

    if not admins:
        try:
            super_id = await database_module.get_superadmin_id()
        except Exception:
            super_id = None

        if super_id:
            await message.answer("ℹ️ Adminlar ro'yxati hozir bo'sh — faqat superadmin mavjud (u faqat DB orqali boshqariladi).")
        else:
            await message.answer("ℹ️ Hech qanday admin mavjud emas.")
        return

    rows = []
    for a in admins:
        uid = a.get('user_id')
        uname = a.get('username')
        label = f"{uid}"
        if uname:
            label += f" — @{uname}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"remove_admin:{uid}")])

    kb = InlineKeyboardMarkup(inline_keyboard=rows)

    await message.answer("➖ Qaysi adminni o'chirmoqchisiz? Quyidagilardan birini bosing:", reply_markup=kb)

async def remove_admin_callback(query: CallbackQuery):
    try:
        requester_id = query.from_user.id

        data = query.data or ""
        if not data.startswith("remove_admin:"):
            await query.answer("❌ Noto'g'ri so'rov.", show_alert=True)
            return

        try:
            target_id = int(data.split(":", 1)[1])
        except Exception:
            await query.answer("❌ Noto'g'ri ID.", show_alert=True)
            return

        error = await _check_can_remove_admin(requester_id, target_id)
        if error:
            await query.answer(error, show_alert=True)
            return

        await database_module.remove_admin(target_id)
        await database_module.log_admin_action(requester_id, "remove_admin", target_id, "removed via inline")
        await query.answer("✅ Admin o'chirildi.", show_alert=True)
        try:
            await query.message.edit_text("✅ Tanlangan admin o'chirildi.")
        except Exception:
            pass
    except Exception:
        logger.exception("remove_admin_callback error")
        try:
            await query.answer("❗ Xatolik yuz berdi.", show_alert=True)
        except Exception:
            pass

async def process_remove_admin(message: Message, state: FSMContext):
    if not await require_admin_or_deny(message):
        await state.clear()
        return

    text = (message.text or "").strip()
    try:
        target_id = int(text)
    except ValueError:
        await message.answer("❗ Iltimos faqat sonli ID kiriting.")
        await state.clear()
        return

    requester = message.from_user.id

    try:
        error = await _check_can_remove_admin(requester, target_id)
        if error:
            await message.answer(error)
            await state.clear()
            return

        await database_module.remove_admin(target_id)
        await database_module.log_admin_action(requester, "remove_admin", target_id, "removed via text")
        await message.answer(f"✅ {target_id} adminlar ro'yxatidan o'chirildi.")
    except Exception:
        logger.exception("process_remove_admin error")
        await message.answer("❗ Xatolik yuz berdi: DB yoki server xatosi")
    finally:
        await state.clear()

# --- Yangi: report callback (foydalanuvchi reporting tugmasini bosganda) ---
async def report_callback(query: CallbackQuery, state: FSMContext):
    """
    Callback data: report:{chat_id}
    Bu callback foydalanuvchiga 'Adminga xabar yozing' deb so'raydi va keyin xabarni superadminga yuboradi.
    """
    try:
        data = query.data or ""
        if not data.startswith("report:"):
            await query.answer("Noto'g'ri so'rov.", show_alert=True)
            return

        # extract reported chat id (original chat for which user reported an error)
        try:
            reported_chat_id = int(data.split(":", 1)[1])
        except Exception:
            reported_chat_id = None

        # Acknowledge callback quickly
        await query.answer()

        # Save context: we will ask the user to type the message now
        await query.message.answer(
            "✉️ Adminga yuborish uchun xabar matnini kiriting. Iltimos, muammoni qisqacha tushuntiring.\n\n"
            "Agar shaxsiy ma'lumotlar bo'lsa, ularni kiritmang. Yuborganingizdan so'ng superadminga yetib boradi."
        )
        await state.set_state(ReportStates.waiting_for_report_message)
        # store reported_chat_id so we can include it in the forwarded report
        await state.update_data(reported_chat_id=reported_chat_id, reporter_chat_id=query.message.chat.id)
    except Exception:
        logger.exception("report_callback error")
        try:
            await query.answer("❗ Xatolik yuz berdi. Keyinroq urinib ko'ring.", show_alert=True)
        except Exception:
            pass

async def process_report_message(message: Message, state: FSMContext):
    """
    Foydalanuvchi adminga yuborish uchun yozgan matn shu yerga keladi.
    Biz uni superadminga yuboramiz (agar mavjud bo'lsa) yoki barcha adminlarga.
    """
    try:
        data = await state.get_data()
        reported_chat_id = data.get("reported_chat_id")
        reporter_chat_id = data.get("reporter_chat_id") or message.chat.id

        report_text = (message.text or "").strip()
        if not report_text:
            await message.answer("❗ Xabar bo'sh. Iltimos, matn kiriting yoki amalni bekor qilish uchun /cancel yozing.")
            return

        # prepare message for admin
        reporter = message.from_user
        reporter_name = f"@{reporter.username}" if reporter.username else f"User {reporter.id}"
        reporter_link = f'<a href="tg://user?id={reporter.id}">{reporter.first_name}</a>'

        report_payload = (
            f"📣 <b>Foydalanuvchi xabari</b>\n\n"
            f"👤 Yuborgan: {reporter_name} ({reporter.id})\n"
            f"🔗 Profil: {reporter_link}\n"
        )
        if reported_chat_id:
            report_payload += f"🆔 Asosiy chat id: <code>{reported_chat_id}</code>\n"
        report_payload += f"🕒 Vaqt: {format_dt(datetime.now(timezone.utc))}\n\n"
        report_payload += f"✏️ Xabar:\n{report_text}"

        # Try to send to superadmin first
        try:
            super_id = await database_module.get_superadmin_id()
        except Exception:
            logger.exception("get_superadmin_id error")
            super_id = None

        sent_to = []
        failed_to = []

        if super_id:
            try:
                await bot.send_message(super_id, report_payload, parse_mode=ParseMode.HTML)
                sent_to.append(super_id)
            except Exception:
                logger.exception("Send to superadmin failed")
                failed_to.append(super_id)

        # If no superadmin or sending failed, fallback to sending to all admins
        if not sent_to:
            try:
                admins = await database_module.get_admins()
            except Exception:
                logger.exception("get_admins error")
                admins = []

            for a in admins:
                aid = a.get("user_id")
                try:
                    await bot.send_message(aid, report_payload, parse_mode=ParseMode.HTML)
                    sent_to.append(aid)
                except Exception:
                    logger.exception(f"Failed to send report to admin {aid}")
                    failed_to.append(aid)

        # Notify reporter
        if sent_to:
            await message.answer("✅ Xabaringiz adminga yuborildi. Tez orada tekshiriladi. Rahmat!")
        else:
            await message.answer("❌ Afsus, xabaringizni adminga yuborib bo'lmadi. Iltimos keyinroq urinib ko'ring.")

        # Optionally log this action
        try:
            await database_module.log_admin_action(None, "user_report", None, json.dumps({
                "reporter_id": reporter.id,
                "reported_chat_id": reported_chat_id,
                "text": report_text,
                "sent_to": sent_to,
                "failed": failed_to,
            }, ensure_ascii=False))
        except Exception:
            logger.exception("log_admin_action (report) failed")
    except Exception:
        logger.exception("process_report_message error")
        try:
            await message.answer("❗ Xatolik yuz berdi. Keyinroq urinib ko'ring.")
        except Exception:
            pass
    finally:
        await state.clear()
