"""Ommaviy xabar: konstruktor (kontent -> tugma -> oluvchi -> tasdiq)
va yuborish sikli."""

import logging
import html
import re
import asyncio
from typing import Any, Dict, List, Optional
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.enums import ParseMode
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import (
    TelegramForbiddenError, TelegramNotFound, TelegramRetryAfter, TelegramBadRequest,
)
from core.loader import bot
from db import database as database_module
from handlers import pro as pro_module
from handlers.admin.common import (
    _resolve_recipients, require_admin_or_deny, require_admin_or_deny_query,
)

logger = logging.getLogger(__name__)


# ponytail: global set, bir vaqtda ko'p admin parallel broadcast qilishi hisobga
# olinmagan — kichik bot uchun unlikely, kerak bo'lsa per-broadcast id keyin qo'shiladi.
_broadcast_cancel_flags: set[int] = set()


class BroadcastStates(StatesGroup):
    """Xabar konstruktori: kontent -> tugmalar -> oluvchi -> tasdiq.

    PMStates ("bitta userga") ALOHIDA oqim edi va aynan shu ishni qilardi,
    faqat matn bilan va tugmasiz. Endi u shu yerdagi "tanlangan odamlarga"
    varianti — bitta kod yo'li, ikkita emas.
    """
    waiting_for_content = State()
    waiting_for_button = State()
    waiting_for_recipients = State()
    waiting_for_segment = State()
    waiting_for_schedule = State()
    waiting_for_confirmation = State()


def _filter_users_by_segment(users: List[Dict[str, Any]], segment: str) -> List[Dict[str, Any]]:
    candidates = [u for u in users if not u.get("is_banned")]
    if segment == "free":
        return [u for u in candidates if (u.get("plan_type") or "free") == "free"]
    if segment == "premium":
        return [u for u in candidates if (u.get("plan_type") or "free") != "free"]
    return candidates


# ═══════════════════════════════════════════════════════════════════
#  XABAR KONSTRUKTORI — inline tugmalar
# ═══════════════════════════════════════════════════════════════════
# Reklama xabari uchun: rasm/video + matn + havolali tugmalar. Har bir
# qism IXTIYORIY — faqat matn ham, faqat rasm + tugma ham bo'ladi.

BCAST_MAX_BUTTONS = 6          # ponytail: 6 tadan ortig'i ekranga sig'maydi

# Ranglar pro.py'dagi bilan AYNAN bir xil manbadan — Telegram faqat shu
# uchtasini qabul qiladi, boshqasi butun xabarni yuborilmas qiladi.
BCAST_STYLES = {
    "primary": ("🔵 Ko'k", pro_module.BTN_PRIMARY),
    "success": ("🟢 Yashil", pro_module.BTN_SUCCESS),
    "danger": ("🔴 Qizil", pro_module.BTN_DANGER),
    "plain": ("⚪️ Oddiy", None),
}

_URL_RE = re.compile(r"(https?://\S+|tg://\S+)", re.IGNORECASE)


def parse_button_spec(raw: str) -> tuple[Optional[str], Optional[str], str]:
    """"Kanal 📢 | https://t.me/x" -> ("Kanal 📢", "https://t.me/x", "").

    Xato bo'lsa (None, None, sabab) qaytadi. Ajratgich TALAB QILINMAYDI:
    havola matndan regex bilan topiladi, shuning uchun "Kanal - https://..."
    ham, "Kanal https://..." ham ishlaydi. Admin format eslay olmasa,
    tugma qo'shilmay qolgandan ko'ra shu yaxshi.

    Sof funksiya — tests/test_broadcast.py'da tekshiriladi.
    """
    raw = " ".join(str(raw or "").split())
    if not raw:
        return None, None, "bo'sh"

    match = _URL_RE.search(raw)
    if not match:
        return None, None, ("havola topilmadi — u <code>https://</code> yoki "
                            "<code>tg://</code> bilan boshlanishi kerak")
    url = match.group(1).rstrip(".,;")
    # Havolani olib tashlaymiz, qolgani — tugma nomi. Ajratgich belgilari
    # ("|", "-", "—") nom oxirida osilib qolmasin.
    text = (raw[:match.start()] + " " + raw[match.end():]).strip(" |-–—\t")
    text = " ".join(text.split())
    if not text:
        return None, None, "tugma nomi yo'q — havoladan oldin nom yozing"
    if len(text) > 64:
        return None, None, "tugma nomi 64 belgidan uzun"
    return text, url, ""


def build_bcast_keyboard(buttons: List[Dict[str, str]], *,
                         plain: bool = False) -> Optional[InlineKeyboardMarkup]:
    """Saqlangan tugmalardan klaviatura. `plain=True` — rangsiz zaxira.

    Zaxira SHART: rang maydonini qabul qilmaydigan mijoz/API'da xabar
    UMUMAN yuborilmaydi. Bitta reklama uchun butun tarqatmani yo'qotish
    qabul qilinmaydi (pro.send_rich'dagi bilan bir xil tamoyil).
    """
    if not buttons:
        return None
    rows = []
    for b in buttons:
        style = None if plain else BCAST_STYLES.get(b.get("style", "plain"), (None, None))[1]
        rows.append([pro_module.btn(b["text"], "noop", style=style, url=b["url"])])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _is_markup_error(exc: Exception) -> bool:
    """Xato KLAVIATURA sababli chiqqanmi yoki oluvchi sababli?

    "chat not found" ham TelegramBadRequest. Ilgari har qanday BadRequest
    rang rad etildi deb hisoblanardi va bitta o'chirilgan akkaunt butun
    tarqatmani rangsizga tushirib yuborardi. Telegram klaviatura xatosini
    doim "button"/"markup" so'zi bilan aytadi ("can't parse
    InlineKeyboardButton: ...", "BUTTON_TYPE_INVALID", "reply markup is
    too long"), oluvchi xatosida bu so'zlar bo'lmaydi.

    Sof funksiya — tests/test_broadcast.py'da tekshiriladi.
    """
    low = str(exc).lower()
    return "button" in low or "markup" in low


def _render_builder(buttons: List[Dict[str, str]]) -> tuple[str, InlineKeyboardMarkup]:
    """Konstruktor ekrani: hozirgi tugmalar ro'yxati + boshqaruv."""
    if buttons:
        lines = "\n".join(
            f"{i}. {BCAST_STYLES.get(b.get('style', 'plain'), ('⚪️', None))[0][0]} "
            f"<b>{html.escape(b['text'])}</b> → <code>{html.escape(b['url'])}</code>"
            for i, b in enumerate(buttons, 1))
        text = f"🔘 <b>Tugmalar ({len(buttons)}/{BCAST_MAX_BUTTONS})</b>\n\n{lines}"
    else:
        text = ("🔘 <b>Tugmalar</b>\n\n<blockquote>Hozircha tugma yo'q. "
                "Xohlasangiz havolali tugma qo'shing — kanal, sayt, "
                "istalgan link.</blockquote>")

    rows = []
    if len(buttons) < BCAST_MAX_BUTTONS:
        rows.append([InlineKeyboardButton(text="➕ Tugma qo'shish",
                                          callback_data="bcast:btnadd")])
    if buttons:
        rows.append([InlineKeyboardButton(text="🗑 Oxirgisini o'chirish",
                                          callback_data="bcast:btndel")])
    rows.append([InlineKeyboardButton(text="👁 Ko'rib chiqish",
                                      callback_data="bcast:preview")])
    rows.append([InlineKeyboardButton(text="➡️ Davom etish",
                                      callback_data="bcast:next")])
    rows.append([InlineKeyboardButton(text="❌ Bekor qilish",
                                      callback_data="bcast:abort")])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


async def start_broadcast(message: Message, state: FSMContext):
    if not await require_admin_or_deny(message):
        return
    await state.clear()
    await message.answer(
        "✍️ <b>XABAR YUBORISH</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "<blockquote>Yubormoqchi bo'lgan xabarni shu yerga tashlang.\n"
        "Matn, rasm, video, fayl yoki ovoz — izohi bilan birga.</blockquote>\n\n"
        "Keyingi qadamda havolali tugma qo'shishingiz va kimga "
        "yuborilishini tanlashingiz mumkin.",
        parse_mode=ParseMode.HTML,
    )
    await state.set_state(BroadcastStates.waiting_for_content)

async def _show_builder(target, state: FSMContext, *, edit: bool = False):
    data = await state.get_data()
    text, kb = _render_builder(data.get("buttons") or [])
    try:
        if edit:
            await target.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await target.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    except Exception:
        # "message is not modified" yoki eski xabar — yangisini yuboramiz.
        try:
            await target.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            logger.exception("builder render error")

async def capture_broadcast_content(message: Message, state: FSMContext):
    if not await require_admin_or_deny(message):
        await state.clear()
        return

    # Tugmalar SAQLANADI: admin rasmni almashtirmoqchi bo'lib yangisini
    # tashlasa, allaqachon sozlagan tugmalarini qaytadan yozishi
    # kerak bo'lmasin.
    data = await state.get_data()
    await state.update_data(src_chat_id=message.chat.id,
                            src_message_id=message.message_id,
                            buttons=data.get("buttons") or [])
    await _show_builder(message, state)
    # Holat ATAYLAB o'zgarmaydi: konstruktor callback'lar bilan
    # boshqariladi, admin esa shu payt fikridan qaytib boshqa xabar
    # tashlasa — u yangi kontent bo'lib qabul qilinadi.

async def broadcast_button_add_callback(query: CallbackQuery, state: FSMContext):
    if not await require_admin_or_deny_query(query):
        return
    await query.answer()
    await query.message.answer(
        "🔗 <b>Tugma qo'shish</b>\n\n"
        "<blockquote>Tugma nomini va havolasini bitta xabarda yuboring:\n\n"
        "<code>Kanalga o'tish 📢 | https://t.me/kanalingiz</code>\n"
        "<code>Saytimiz 🌐 | https://example.uz</code></blockquote>\n\n"
        "Nomda emoji ishlatsangiz bo'ladi. Rangni keyingi qadamda tanlaysiz.",
        parse_mode=ParseMode.HTML,
    )
    await state.set_state(BroadcastStates.waiting_for_button)

async def process_broadcast_button(message: Message, state: FSMContext):
    if not await require_admin_or_deny(message):
        await state.clear()
        return

    text, url, err = parse_button_spec(message.text or "")
    if err:
        await message.answer(
            f"⚠️ {err}.\n\nNamuna: <code>Kanal 📢 | https://t.me/kanal</code>",
            parse_mode=ParseMode.HTML)
        return

    await state.update_data(pending_btn={"text": text, "url": url})
    rows = [[InlineKeyboardButton(text=label, callback_data=f"bcast:color:{key}")]
            for key, (label, _) in BCAST_STYLES.items()]
    await message.answer(
        f"🎨 <b>«{html.escape(text)}»</b> tugmasi qanday rangda bo'lsin?",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

async def broadcast_color_callback(query: CallbackQuery, state: FSMContext):
    if not await require_admin_or_deny_query(query):
        return

    style = (query.data or "").rsplit(":", 1)[-1]
    if style not in BCAST_STYLES:
        await query.answer("❌ Noma'lum rang.", show_alert=True)
        return

    data = await state.get_data()
    pending = data.get("pending_btn")
    if not pending:
        await query.answer("⚠️ Tugma topilmadi, qaytadan qo'shing.", show_alert=True)
        return

    buttons = list(data.get("buttons") or [])
    if len(buttons) >= BCAST_MAX_BUTTONS:
        await query.answer(f"❌ Eng ko'pi {BCAST_MAX_BUTTONS} ta tugma.", show_alert=True)
        return

    buttons.append({**pending, "style": style})
    await state.update_data(buttons=buttons, pending_btn=None)
    await state.set_state(BroadcastStates.waiting_for_content)
    await query.answer("✅ Qo'shildi")
    try:
        await query.message.delete()
    except Exception:
        pass
    await _show_builder(query.message, state)

async def broadcast_button_del_callback(query: CallbackQuery, state: FSMContext):
    if not await require_admin_or_deny_query(query):
        return
    data = await state.get_data()
    buttons = list(data.get("buttons") or [])
    if buttons:
        buttons.pop()
        await state.update_data(buttons=buttons)
    await query.answer("🗑 O'chirildi")
    await _show_builder(query.message, state, edit=True)

async def broadcast_preview_callback(query: CallbackQuery, state: FSMContext):
    """Xabarni AYNAN foydalanuvchi ko'radigan holatda ko'rsatadi."""
    if not await require_admin_or_deny_query(query):
        return
    data = await state.get_data()
    src_chat_id, src_message_id = data.get("src_chat_id"), data.get("src_message_id")
    if not src_chat_id or not src_message_id:
        await query.answer("⚠️ Xabar topilmadi, boshidan boshlang.", show_alert=True)
        return
    await query.answer()
    kb = build_bcast_keyboard(data.get("buttons") or [])
    try:
        await bot.copy_message(chat_id=query.from_user.id, from_chat_id=src_chat_id,
                               message_id=src_message_id, reply_markup=kb)
    except Exception as e:
        # Rangni qabul qilmasa — rangsiz ko'rsatamiz va ogohlantiramiz.
        logger.warning(f"Preview rangli klaviatura bilan yuborilmadi: {e}")
        try:
            await bot.copy_message(
                chat_id=query.from_user.id, from_chat_id=src_chat_id,
                message_id=src_message_id,
                reply_markup=build_bcast_keyboard(data.get("buttons") or [], plain=True))
            await query.message.answer(
                "⚠️ Ranglar bu yerda qo'llanmadi — tugmalar oddiy ko'rinishda ketadi.")
        except Exception:
            logger.exception("Preview copy error")

async def broadcast_next_callback(query: CallbackQuery, state: FSMContext):
    if not await require_admin_or_deny_query(query):
        return
    await query.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Hammaga", callback_data="bcast:seg:all")],
        [InlineKeyboardButton(text="🆓 Faqat Free", callback_data="bcast:seg:free")],
        [InlineKeyboardButton(text="💎 Faqat Pro", callback_data="bcast:seg:premium")],
        [InlineKeyboardButton(text="👤 Tanlangan odamlarga", callback_data="bcast:seg:pick")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="bcast:abort")],
    ])
    try:
        await query.message.edit_text("👥 <b>Kimga yuborilsin?</b>",
                                      parse_mode=ParseMode.HTML, reply_markup=kb)
    except Exception:
        await query.message.answer("👥 <b>Kimga yuborilsin?</b>",
                                   parse_mode=ParseMode.HTML, reply_markup=kb)
    await state.set_state(BroadcastStates.waiting_for_segment)

async def _confirm_screen(query: CallbackQuery, state: FSMContext,
                          target_ids: List[int], label: str):
    """Preview + tasdiqlash. Yuborishdan oldingi OXIRGI to'xtash nuqtasi."""
    data = await state.get_data()
    await state.update_data(target_ids=target_ids)
    try:
        await bot.copy_message(
            chat_id=query.from_user.id, from_chat_id=data["src_chat_id"],
            message_id=data["src_message_id"],
            reply_markup=build_bcast_keyboard(data.get("buttons") or []))
    except Exception:
        try:
            await bot.copy_message(
                chat_id=query.from_user.id, from_chat_id=data["src_chat_id"],
                message_id=data["src_message_id"],
                reply_markup=build_bcast_keyboard(data.get("buttons") or [], plain=True))
        except Exception:
            logger.exception("Confirm preview copy error")

    rows = [[InlineKeyboardButton(text="✅ Yuborish", callback_data="bcast:send")]]
    # "Keyinroq" FAQAT segment bo'yicha tarqatmada: bazada oluvchilar
    # ro'yxati emas, segment saqlanadi, ya'ni qo'lda tanlangan
    # odamlarni rejalashtirib bo'lmaydi.
    if data.get("segment") in ("all", "free", "premium"):
        rows.append([InlineKeyboardButton(text="🕒 Keyinroq yuborish",
                                          callback_data="bcast:later")])
    rows.append([InlineKeyboardButton(text="❌ Bekor qilish",
                                      callback_data="bcast:abort")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await query.message.answer(
        f"👆 Yuqorida — foydalanuvchi ko'radigan ko'rinish.\n\n"
        f"{label}: <b>{len(target_ids)}</b> ta oluvchi. Tasdiqlaysizmi?",
        parse_mode=ParseMode.HTML, reply_markup=kb)
    await state.set_state(BroadcastStates.waiting_for_confirmation)

async def broadcast_segment_callback(query: CallbackQuery, state: FSMContext):
    if not await require_admin_or_deny_query(query):
        return

    segment = (query.data or "").rsplit(":", 1)[-1]
    data = await state.get_data()
    if not data.get("src_chat_id") or not data.get("src_message_id"):
        await query.answer("⚠️ Xabar topilmadi, boshidan boshlang.", show_alert=True)
        await state.clear()
        return

    await query.answer()

    if segment == "pick":
        await query.message.answer(
            "👤 <b>Kimlarga?</b>\n\n"
            "<blockquote>@username yoki ID yuboring — bittasi ham, "
            "bir nechtasi ham bo'ladi (probel, vergul yoki yangi qatordan "
            "ajratib). Bir martada 50 tagacha.</blockquote>",
            parse_mode=ParseMode.HTML)
        await state.set_state(BroadcastStates.waiting_for_recipients)
        return

    try:
        users = await database_module.get_all_users()
    except Exception:
        logger.exception("get_all_users error in broadcast_segment_callback")
        await query.message.edit_text("❌ DB xatosi.")
        await state.clear()
        return

    target_ids = [u["user_id"] for u in _filter_users_by_segment(users, segment)]
    label = {"all": "Hammaga", "free": "Faqat Free",
             "premium": "Faqat Pro"}.get(segment, segment)
    # Segment SAQLANADI: rejalashtirilgan tarqatmada oluvchilar
    # ro'yxati emas, aynan segment kerak (yuborish paytida qaytadan
    # hisoblanadi), audit yozuvida ham shu ko'rsatiladi.
    await state.update_data(segment=segment)
    await _confirm_screen(query, state, target_ids, label)

async def process_broadcast_recipients(message: Message, state: FSMContext):
    if not await require_admin_or_deny(message):
        await state.clear()
        return

    data = await state.get_data()
    if not data.get("src_chat_id") or not data.get("src_message_id"):
        await state.clear()
        await message.answer("⚠️ Xabar topilmadi, boshidan boshlang.")
        return

    found, missing = await _resolve_recipients(message.text or "")
    if not found:
        await message.answer(
            "❌ Hech kim topilmadi. @username yoki ID yuboring.\n"
            + (f"Topilmadi: {', '.join(missing)}" if missing else ""),
            parse_mode=ParseMode.HTML)
        return

    # Banlangan foydalanuvchiga reklama yuborish ma'nosiz — chetlanadi,
    # lekin admin buni ko'rib tursin.
    target_ids = [uid for uid, _name, banned in found if not banned]
    skipped = [name for _uid, name, banned in found if banned]

    note = ""
    if missing:
        note += f"\n⚠️ Topilmadi: {', '.join(missing)}"
    if skipped:
        note += f"\n🚫 Banlangan (chetlandi): {', '.join(skipped)}"

    try:
        await bot.copy_message(
            chat_id=message.from_user.id, from_chat_id=data["src_chat_id"],
            message_id=data["src_message_id"],
            reply_markup=build_bcast_keyboard(data.get("buttons") or []))
    except Exception:
        try:
            await bot.copy_message(
                chat_id=message.from_user.id, from_chat_id=data["src_chat_id"],
                message_id=data["src_message_id"],
                reply_markup=build_bcast_keyboard(data.get("buttons") or [], plain=True))
        except Exception:
            logger.exception("Recipients preview copy error")

    await state.update_data(target_ids=target_ids)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Yuborish", callback_data="bcast:send")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="bcast:abort")],
    ])
    await message.answer(
        f"👆 Yuqorida — foydalanuvchi ko'radigan ko'rinish.\n\n"
        f"Tanlangan: <b>{len(target_ids)}</b> ta oluvchi.{note}\n\nTasdiqlaysizmi?",
        parse_mode=ParseMode.HTML, reply_markup=kb)
    await state.set_state(BroadcastStates.waiting_for_confirmation)

async def broadcast_abort_callback(query: CallbackQuery, state: FSMContext):
    if not await require_admin_or_deny_query(query):
        return
    await state.clear()
    await query.answer()
    try:
        await query.message.edit_text("❌ Bekor qilindi.")
    except Exception:
        pass

async def broadcast_cancel_send_callback(query: CallbackQuery):
    if not await require_admin_or_deny_query(query):
        return
    _broadcast_cancel_flags.add(query.from_user.id)
    await query.answer("🛑 Bekor qilinmoqda...")

async def _send_to_many(src_chat_id: int, src_message_id: int, buttons: list,
                        target_ids: list, *, admin_id=None, progress=None):
    """Tarqatmaning YAGONA yuborish yadrosi.

    Interaktiv yo'l ham, rejalashtirilgan yo'l ham shu yerdan o'tadi:
    flood-control, klaviaturaning rangsiz zaxirasi va bloklagan
    foydalanuvchini o'chirish mantiqi ikki nusxada bo'lmasligi kerak.

    `admin_id` — bekor qilish belgisini shu admin bo'yicha tekshiradi
    (rejali tarqatmada bekor qilish yo'q, shuning uchun None).
    `progress(i, total)` — ixtiyoriy, ekranni yangilash uchun.

    Qaytaradi: (yuborildi, yuborilmadi, bekor_qilindimi, rang_tushdimi).
    """
    kb_rich = build_bcast_keyboard(buttons)
    kb_plain = build_bcast_keyboard(buttons, plain=True)
    kb = kb_rich
    style_downgraded = False

    async def _deliver(uid: int):
        """Bitta oluvchiga yuboradi; rang rad etilsa rangsizga tushadi."""
        nonlocal kb, style_downgraded
        try:
            await bot.copy_message(chat_id=uid, from_chat_id=src_chat_id,
                                   message_id=src_message_id, reply_markup=kb)
        except TelegramBadRequest as exc:
            if kb is kb_rich and kb_plain is not None and _is_markup_error(exc):
                logger.warning(f"Klaviatura rad etildi — rangsiz rejimga o'tildi: {exc}")
                kb, style_downgraded = kb_plain, True
                await bot.copy_message(chat_id=uid, from_chat_id=src_chat_id,
                                       message_id=src_message_id, reply_markup=kb)
            else:
                raise

    success, fail, cancelled = 0, 0, False
    total = len(target_ids)
    for i, user_id in enumerate(target_ids, 1):
        if admin_id is not None and admin_id in _broadcast_cancel_flags:
            cancelled = True
            break
        try:
            await _deliver(user_id)
            success += 1
        except (TelegramForbiddenError, TelegramNotFound):
            logger.warning(f"❌ Foydalanuvchi topilmadi yoki bloklangan: {user_id}")
            try:
                await database_module.deactivate_user(user_id)
            except Exception:
                logger.exception("DB deactivate error")
            fail += 1
        except TelegramRetryAfter as e:
            # Telegram flood-control: shuncha soniya kutmasdan davom etsak,
            # qolgan HAMMA xabar "xatolik" deb hisoblanib, aslida
            # yetkazilmagan bo'lib qolardi. Ko'rsatilgan vaqtni kutib,
            # aynan shu foydalanuvchiga bir marta qayta urinamiz.
            logger.warning(f"⏳ Flood control: {e.retry_after}s kutilmoqda...")
            await asyncio.sleep(e.retry_after + 0.5)
            try:
                await _deliver(user_id)
                success += 1
            except Exception as e2:
                logger.warning(f"⚠️ Flood-dan keyin ham xatolik: {user_id} - {e2}")
                fail += 1
        except Exception as e:
            logger.warning(f"⚠️ Xatolik: {user_id} - {e}")
            fail += 1

        if progress is not None:
            await progress(i, total)
        await asyncio.sleep(0.05)

    return success, fail, cancelled, style_downgraded


async def run_broadcast(*, src_chat_id: int, src_message_id: int,
                        buttons: list, segment: str):
    """Rejalashtirilgan tarqatma uchun: oluvchini O'ZI hisoblab yuboradi.

    ⚠️ Oluvchilar ro'yxati bazada saqlanmaydi va aynan SHU YERDA
    hisoblanadi: tarqatma bir kun oldin rejalashtirilgan bo'lsa,
    o'shandagi ro'yxatga keyin qo'shilganlar kirmay qolardi.
    """
    try:
        users = await database_module.get_all_users()
    except Exception:
        logger.exception("get_all_users error (rejali tarqatma)")
        return 0, 0
    target_ids = [u["user_id"] for u in _filter_users_by_segment(users, segment)]
    success, fail, _, _ = await _send_to_many(
        src_chat_id, src_message_id, buttons, target_ids)
    return success, fail


async def broadcast_confirm_send_callback(query: CallbackQuery, state: FSMContext):
    if not await require_admin_or_deny_query(query):
        return

    data = await state.get_data()
    src_chat_id = data.get("src_chat_id")
    src_message_id = data.get("src_message_id")
    target_ids = data.get("target_ids") or []
    buttons = data.get("buttons") or []
    await state.clear()

    if not src_chat_id or not src_message_id or not target_ids:
        await query.answer("⚠️ Ma'lumot topilmadi, boshidan boshlang.", show_alert=True)
        return

    await query.answer()
    admin_id = query.from_user.id
    _broadcast_cancel_flags.discard(admin_id)

    stop_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛑 Bekor qilish", callback_data="bcast:cancel")],
    ])
    progress_message = query.message
    try:
        await progress_message.edit_text("📤 Xabar yuborilmoqda: 0%", reply_markup=stop_kb)
    except Exception:
        pass

    # ⚠️ Ekran FOIZ O'ZGARGANDAGINA yangilanadi. Ilgari har bir
    # oluvchidan keyin edit_text ketardi: 1000 ta oluvchi = 1000 ta
    # ortiqcha so'rov, aksariyati "message is not modified" xatosi bilan
    # jimgina yutilardi — va ular aynan tarqatmaning o'ziga kerak
    # bo'lgan Telegram limitini yeb qo'yardi.
    oxirgi_foiz = -1

    async def _progress(i, total):
        nonlocal oxirgi_foiz
        foiz = int(i / total * 100) if total else 100
        if foiz == oxirgi_foiz:
            return
        oxirgi_foiz = foiz
        try:
            await progress_message.edit_text(
                f"📤 Xabar yuborilmoqda: {foiz}%", reply_markup=stop_kb)
        except Exception:
            pass

    success, fail, cancelled, style_downgraded = await _send_to_many(
        src_chat_id, src_message_id, buttons, target_ids,
        admin_id=admin_id, progress=_progress)

    _broadcast_cancel_flags.discard(admin_id)

    try:
        await database_module.log_admin_action(
            admin_id, "broadcast", None,
            f"segment={data.get('segment') or '?'} yuborildi={success} xato={fail}")
    except Exception:
        logger.exception("broadcast auditga yozilmadi")

    status = "🛑 Bekor qilindi." if cancelled else "✅ Yakunlandi."
    try:
        await progress_message.edit_text(
            f"{status}\n"
            f"✅ {success} ta foydalanuvchiga yuborildi.\n"
            f"❌ {fail} ta foydalanuvchiga yuborilmadi (bloklagan yoki mavjud emas)."
            + ("\n⚠️ Tugma ranglari qo'llanmadi — oddiy ko'rinishda ketdi."
               if style_downgraded else "")
        )
    except Exception:
        pass


async def broadcast_later_callback(query: CallbackQuery, state: FSMContext):
    """«Keyinroq yuborish» — vaqtni so'raydi."""
    if not await require_admin_or_deny_query(query):
        return
    data = await state.get_data()
    if data.get("segment") not in ("all", "free", "premium"):
        await query.answer("Faqat segment bo'yicha tarqatmani rejalashtirish mumkin.",
                           show_alert=True)
        return
    await query.answer()
    await state.set_state(BroadcastStates.waiting_for_schedule)
    await query.message.answer(
        "🕒 <b>Qachon yuborilsin?</b>\n\n"
        "<blockquote>Masalan: <code>ertaga 09:00</code>, "
        "<code>2 soatdan keyin</code>, <code>2026-09-10 18:30</code>.</blockquote>\n\n"
        "«bekor» — bekor qilish.",
        parse_mode=ParseMode.HTML)


async def process_broadcast_schedule(message: Message, state: FSMContext):
    if not await require_admin_or_deny(message):
        await state.clear()
        return

    raw = (message.text or "").strip()
    if raw.lower() in ("bekor", "/cancel"):
        await state.clear()
        await message.answer("❌ Bekor qilindi.")
        return

    # Vaqtni ESLATMA bilan bir xil parser o'qiydi (db.parse_run_at):
    # u o'tgan vaqtni va juda uzoq kelajakni allaqachon rad etadi,
    # ikkinchi parser yozishning ma'nosi yo'q.
    run_at = database_module.parse_run_at(raw)
    if run_at is None:
        await message.answer(
            "⚠️ Vaqtni tushunmadim. Masalan: <code>ertaga 09:00</code> "
            "yoki <code>2026-09-10 18:30</code>.",
            parse_mode=ParseMode.HTML)
        return

    data = await state.get_data()
    src_chat_id = data.get("src_chat_id")
    src_message_id = data.get("src_message_id")
    segment = data.get("segment") or "all"
    buttons = data.get("buttons") or []
    await state.clear()

    if not src_chat_id or not src_message_id:
        await message.answer("⚠️ Xabar topilmadi, boshidan boshlang.")
        return

    try:
        bid = await database_module.create_scheduled_broadcast(
            message.from_user.id, src_chat_id, src_message_id,
            buttons, segment, run_at)
    except Exception:
        logger.exception("rejalashtirilgan tarqatma saqlanmadi")
        await message.answer("❌ Saqlab bo'lmadi. Qaytadan urinib ko'ring.")
        return

    try:
        await database_module.log_admin_action(
            message.from_user.id, "broadcast", None,
            f"rejalashtirildi #{bid} segment={segment}")
    except Exception:
        logger.exception("rejali tarqatma auditga yozilmadi")

    nom = {"all": "hammaga", "free": "Free", "premium": "Pro"}.get(segment, segment)
    await message.answer(
        f"🕒 Rejalashtirildi: <b>#{bid}</b>\n"
        f"Vaqt: <b>{database_module.format_dt_for_tashkent(run_at)}</b>\n"
        f"Kimga: {nom}\n\n"
        "<i>«📋 Jurnal va sozlamalar» → «Rejalashtirilgan tarqatmalar» "
        "bo'limidan bekor qilsa bo'ladi.</i>",
        parse_mode=ParseMode.HTML)
