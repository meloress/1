"""Promokod va referal taklifini ANIQ odamlarga yuborish (`/kod`).

⚠️ 7-bosqichda bu fayldan ko'pchiligi o'chdi va sabab aniq: kod
YARATISH, ro'yxatini ko'rish, bekor qilish va referal shartini sozlash
— hammasi endi web panelda (`/api/promo`, `/api/referral`). Ikki joyda
turgan sozlama ertami-kech ikki xil bo'lib qoladi.

⚠️ YUBORISH esa ATAYLAB botda qoldi. Sabab tarqatmanikiga aynan
o'xshash (REJA 2): bu — odamga xabar jo'natish, ya'ni botning ishi.
`send_promo_gift()` tayyor tugmali xabar yuboradi, `send_referral_invite()`
esa har kimga O'ZINING shaxsiy havolasini yasaydi — webda qayta
yig'ilgan xabar bularning ikkalasini ham yo'qotardi. Web panelning
promokod ekrani shu sababli «Botda /kod» deb yo'naltiradi.

⚠️ Bepul olish yo'llari ommaviy ekranlarda ko'rinmaydi: ko'rinsa hech
kim sotib olmay bepulini kutib o'tirardi. Foydalanuvchi bu imkoniyat
haqida faqat admin unga xabar yuborgandagina biladi.
"""

import logging
import asyncio
from datetime import datetime, timezone
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.enums import ParseMode
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from db import database as database_module
from handlers import pro as pro_module
from handlers.admin.common import (
    _report_delivery, _resolve_recipients,
    require_admin_or_deny, require_admin_or_deny_query,
)

logger = logging.getLogger(__name__)


class GiveawayStates(StatesGroup):
    """Promokod/referalni ANIQ odamlarga yuborish."""
    waiting_promo_recipients = State()
    waiting_ref_recipients = State()


async def _render_giveaway_menu():
    """`/kod` menyusi — ikkita yuborish amali.

    ⚠️ Raqamlar (nechta kod faol, qancha kun bepul berilgan) ataylab
    YO'Q: ular web panelning «Promo va sovg'a» ekranida, va shu yerda
    takrorlansa ikki joyda ikki xil hisoblanish xavfi paydo bo'lardi.
    Bu menyu bitta ish qiladi — yuboradi.
    """
    text = (
        "🎁 <b>YUBORISH</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "<blockquote>Kod yaratish, bekor qilish va referal shartini "
        "sozlash — <b>panelda</b> (ko'k «Panel» tugmasi). Bu yerda "
        "faqat odamlarga yuboriladi.</blockquote>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📨 Promokodni odamga yuborish",
                              callback_data="gv:sendpromo", style="success")],
        [InlineKeyboardButton(text="👥 Referal taklifini yuborish",
                              callback_data="gv:sendref", style="success")],
        [InlineKeyboardButton(text="✖️ Yopish", callback_data="gv:close",
                              style="danger")],
    ])
    return text, kb


async def show_giveaway_menu(message: Message, state: FSMContext):
    if not await require_admin_or_deny(message):
        return
    await state.clear()
    text, kb = await _render_giveaway_menu()
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def _promo_picker_kb(action: str):
    """Yuborish uchun kod tanlash — faqat ISHLATSA BO'LADIGAN kodlar."""
    try:
        codes = await database_module.list_promo_codes()
    except Exception:
        logger.exception("list_promo_codes error")
        return None
    now = datetime.now(timezone.utc)
    usable = [
        c for c in codes
        if not c['revoked']
        and c['used_count'] < c['max_uses']
        and (c['expires_at'] is None or c['expires_at'] > now)
    ]
    if not usable:
        return None
    rows = [[InlineKeyboardButton(
        text=f"{c['code']} · {c['days']} kun · {c['used_count']}/{c['max_uses']}",
        callback_data=f"gv:{action}:{c['code']}")] for c in usable[:20]]
    rows.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="gv:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def giveaway_callback(query: CallbackQuery, state: FSMContext):
    if not await require_admin_or_deny_query(query):
        return
    parts = (query.data or "").split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "close":
        await state.clear()
        await query.answer()
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    if action == "menu":
        await state.clear()
        await query.answer()
        text, kb = await _render_giveaway_menu()
        try:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML,
                                          reply_markup=kb)
        except Exception:
            pass
        return

    if action in ("sendpromo", "sendref") and len(parts) == 2:
        await query.answer()
        if action == "sendref":
            await state.set_state(GiveawayStates.waiting_ref_recipients)
            await query.message.answer(
                "👥 <b>Referal taklifini yuborish</b>\n\n"
                "Kimga yuboray? @username yoki ID — bir nechtasini "
                "probel/vergul bilan ajratib yozing.\n\n"
                "<blockquote>Misol: <code>@ali @vali 123456789</code></blockquote>\n\n"
                "Har biriga <b>o'zining shaxsiy havolasi</b> yuboriladi.",
                parse_mode=ParseMode.HTML)
            return
        kb = await _promo_picker_kb("pick")
        if kb is None:
            # ⚠️ Yaratish endi shu yerda emas — panelga yo'naltiriladi.
            await query.message.answer(
                "❗️ Ishlatsa bo'ladigan promokod yo'q.\n"
                "Avval <b>panelda</b> («Promo va sovg'a» → «Yangi kod») "
                "kod yarating.",
                parse_mode=ParseMode.HTML)
            return
        await query.message.answer("🎟 <b>Qaysi kodni yuboray?</b>",
                                   parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if action == "pick" and len(parts) == 3:
        code = parts[2]
        await query.answer()
        await state.set_state(GiveawayStates.waiting_promo_recipients)
        await state.update_data(promo_code=code)
        await query.message.answer(
            f"📨 <b>{code}</b> kodi kimga yuborilsin?\n\n"
            f"@username yoki ID — bir nechtasini probel/vergul bilan "
            f"ajratib yozing.\n\n"
            f"<blockquote>Misol: <code>@ali @vali 123456789</code></blockquote>\n\n"
            f"<i>Ular bir bosishda faollashtira oladi.</i>",
            parse_mode=ParseMode.HTML)
        return

    await query.answer()


async def process_promo_recipients(message: Message, state: FSMContext):
    if not await require_admin_or_deny(message):
        await state.clear()
        return
    data = await state.get_data()
    code = data.get("promo_code")
    await state.clear()
    if not code:
        await message.answer("❗️ Kod yo'qoldi. /kod dan qayta boshlang.")
        return

    try:
        info = await database_module.get_promo_code(code)
    except Exception:
        logger.exception("get_promo_code error")
        await message.answer("❌ DB xatosi.")
        return
    if info is None:
        await message.answer("❗️ Bu kod endi mavjud emas.")
        return

    found, missing = await _resolve_recipients(message.text or "")
    if not found and not missing:
        await message.answer("❗️ Hech kim ko'rsatilmadi. Qayta urinib ko'ring.")
        return

    # ⚠️ Kod nechta odamga yuborilayotganini max_uses bilan solishtiramiz:
    # 1 martalik kodni 10 kishiga yuborsak, 9 tasi "kod ishlatilgan"
    # degan xafa qiluvchi javob olardi.
    active = [f for f in found if not f[2]]
    remaining = info['max_uses'] - info['used_count']
    if len(active) > remaining:
        await message.answer(
            f"⚠️ <b>Diqqat:</b> <code>{code}</code> kodidan yana "
            f"<b>{remaining} marta</b> foydalanish mumkin, siz esa "
            f"<b>{len(active)} kishiga</b> yubormoqchisiz.\n\n"
            f"Kodning <b>MAX</b> qiymatini oshiring yoki kamroq odamga "
            f"yuboring — aks holda ortiqchasi kodni ishlata olmaydi.",
            parse_mode=ParseMode.HTML)
        return

    sent, failed, banned = [], [], []
    for uid, name, is_banned_flag in found:
        if is_banned_flag:
            banned.append(name)
            continue
        ok = await pro_module.send_promo_gift(
            uid, info['code'], info['days'], info['expires_at'])
        (sent if ok else failed).append(name)
        await asyncio.sleep(0.05)      # flood-control

    try:
        await database_module.log_admin_action(
            message.from_user.id, "send_promo", None,
            f"{code} -> {len(sent)} ta")
    except Exception:
        pass
    await _report_delivery(message, sent, failed, missing, banned)

async def process_ref_recipients(message: Message, state: FSMContext):
    if not await require_admin_or_deny(message):
        await state.clear()
        return
    await state.clear()

    if not pro_module.BOT_USERNAME:
        await message.answer(
            "❌ Bot username aniqlanmagan — referal havolasi yasab bo'lmaydi. "
            "Botni qayta ishga tushiring.")
        return

    found, missing = await _resolve_recipients(message.text or "")
    if not found and not missing:
        await message.answer("❗️ Hech kim ko'rsatilmadi. Qayta urinib ko'ring.")
        return

    sent, failed, banned = [], [], []
    for uid, name, is_banned_flag in found:
        if is_banned_flag:
            banned.append(name)
            continue
        ok = await pro_module.send_referral_invite(uid)
        (sent if ok else failed).append(name)
        await asyncio.sleep(0.05)

    try:
        await database_module.log_admin_action(
            message.from_user.id, "send_referral", None, f"{len(sent)} ta")
    except Exception:
        pass
    await _report_delivery(message, sent, failed, missing, banned)
