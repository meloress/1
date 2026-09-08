"""Promokod, referal sharti va "Bepul Pro".

⚠️ Bu bo'lim ATAYLAB admin panelida: bepul olish yo'llari ommaviy
ekranlarda ko'rinsa, hech kim sotib olmay bepulini kutib o'tirardi.
Foydalanuvchi bu imkoniyatlar haqida faqat admin unga xabar
yuborgandagina biladi."""

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
from core.keyboards import admin_keyboard
from db import database as database_module
from handlers import pro as pro_module
from core.config import (
    REFERRAL_REQUIRED, REFERRAL_REWARD_DAYS,
)
from handlers.admin.common import (
    format_dt, _report_delivery, _resolve_recipients,
    require_admin_or_deny, require_admin_or_deny_query,
)

logger = logging.getLogger(__name__)


class PromoAdminStates(StatesGroup):
    waiting_for_spec = State()


class ReferralStates(StatesGroup):
    """Referal oqimi: nechta do'st -> necha kun -> kimga -> yuborish.

    Bosqichma-bosqich, chunki bitta qatorda format yozdirish ("3 5 12345")
    adminni har safar formatni eslashga majbur qiladi va xato yozilganda
    boshidan boshlanadi.
    """
    waiting_for_count = State()
    waiting_for_days = State()
    waiting_for_scope = State()
    waiting_for_user = State()


class GiveawayStates(StatesGroup):
    """"Bepul Pro" bo'limi — promokod/referalni ANIQ odamlarga yuborish."""
    waiting_promo_recipients = State()
    waiting_ref_recipients = State()


async def _render_giveaway_menu():
    try:
        s = await database_module.giveaway_stats()
    except Exception:
        logger.exception("giveaway_stats error")
        s = {}
    promo_days = s.get("promo_days", 0) or 0
    ref_rewards = s.get("rewarded", 0) or 0
    ref_days = ref_rewards // REFERRAL_REQUIRED * REFERRAL_REWARD_DAYS

    text = (
        f"🎁 <b>BEPUL PRO BERISH</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<blockquote>Bu imkoniyatlar foydalanuvchilarga "
        f"<b>ko'rinmaydi</b>. Faqat siz yuborgan odam biladi va "
        f"foydalana oladi.</blockquote>\n\n"
        f"🎟 <b>Promokodlar</b>\n"
        f"├ Faol: <b>{s.get('active_codes', 0)}</b> ta "
        f"(jami {s.get('total_codes', 0)})\n"
        f"├ Ishlatilgan: <b>{s.get('redemptions', 0)}</b> marta\n"
        f"└ Berilgan: <b>{promo_days} kun</b>\n\n"
        f"👥 <b>Referal</b>\n"
        f"├ Taklif qilingan: <b>{s.get('invited', 0)}</b>\n"
        f"├ Faol bo'lgan: <b>{s.get('qualified', 0)}</b>\n"
        f"└ Berilgan: <b>{ref_days} kun</b>\n\n"
        f"💸 <b>Jami bepul berilgan: {promo_days + ref_days} kun</b>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎟 Yangi promokod yaratish",
                              callback_data="gv:new", style="primary")],
        [InlineKeyboardButton(text="📨 Promokodni odamga yuborish",
                              callback_data="gv:sendpromo", style="success")],
        [InlineKeyboardButton(text="👥 Referal taklifini yuborish",
                              callback_data="gv:sendref", style="success")],
        [InlineKeyboardButton(text="📋 Kodlar ro'yxati", callback_data="gv:list")],
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

# ── REFERAL: SHART + TAKLIF YUBORISH ───────────────────────────
# Oqim: nechta do'st -> necha kun -> kimga -> yuborish.
# Shart o'rnatish va taklif yuborish ATAYLAB bitta oqimda: admin
# shartni o'zgartirib, odamlarga xabar bermay qo'ysa, o'zgarish hech
# kimga yetib bormaydi va kampaniya ma'nosiz bo'lardi.

_REF_CANCEL_KB = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="refset:cancel")]])

async def _ref_cancelled(message: Message, state: FSMContext) -> bool:
    """Holat ochiq turganda BU handler har qanday matnni yutadi —
    /buyruq general_router'ga yetib bormaydi. Chiqish yo'li shu yerda."""
    if (message.text or "").startswith("/"):
        await state.clear()
        await message.answer("❌ Bekor qilindi.", reply_markup=admin_keyboard)
        return True
    return False

async def show_referral_settings(message: Message, state: FSMContext):
    if not await require_admin_or_deny(message):
        return
    await state.clear()
    try:
        cfg = await database_module.get_referral_config()
    except Exception:
        logger.exception("get_referral_config error")
        await message.answer("⚠️ Sozlamani o'qib bo'lmadi.")
        return
    await state.set_state(ReferralStates.waiting_for_count)
    await message.answer(
        f"👥 <b>REFERAL KAMPANIYASI</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<blockquote>Hozirgi shart: har <b>{cfg['required']} ta</b> do'st "
        f"uchun <b>{cfg['reward_days']} kun</b> Pro.</blockquote>\n\n"
        f"<b>1/3 — Nechta do'st chaqirishi kerak?</b>\n"
        f"<i>Faqat raqam yozing. Masalan: 3</i>",
        parse_mode=ParseMode.HTML, reply_markup=_REF_CANCEL_KB)

async def process_referral_count(message: Message, state: FSMContext):
    if not await require_admin_or_deny(message):
        await state.clear()
        return
    if await _ref_cancelled(message, state):
        return
    count, _, err = database_module.clean_referral_config(
        (message.text or "").strip(), 1)
    if err:
        await message.answer(f"⚠️ {err}\n\n<i>Faqat raqam yozing.</i>",
                             parse_mode=ParseMode.HTML)
        return
    await state.update_data(ref_count=count)
    await state.set_state(ReferralStates.waiting_for_days)
    await message.answer(
        f"✅ <b>{count} ta</b> do'st.\n\n"
        f"<b>2/3 — Necha kun Pro berilsin?</b>\n"
        f"<i>Faqat raqam yozing. Masalan: 3</i>",
        parse_mode=ParseMode.HTML, reply_markup=_REF_CANCEL_KB)

async def process_referral_days(message: Message, state: FSMContext):
    if not await require_admin_or_deny(message):
        await state.clear()
        return
    if await _ref_cancelled(message, state):
        return
    data = await state.get_data()
    count = data.get("ref_count")
    count, days, err = database_module.clean_referral_config(
        count, (message.text or "").strip())
    if err:
        await message.answer(f"⚠️ {err}\n\n<i>Faqat raqam yozing.</i>",
                             parse_mode=ParseMode.HTML)
        return
    await state.update_data(ref_days=days)
    await state.set_state(ReferralStates.waiting_for_scope)
    await message.answer(
        f"✅ Shart: <b>{count} ta</b> do'st → <b>{days} kun</b> Pro.\n\n"
        f"<b>3/3 — Kimga tegishli bo'lsin?</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🌍 Hammaga", callback_data="refset:all")],
            [InlineKeyboardButton(text="👤 Bitta userga", callback_data="refset:one")],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="refset:cancel")],
        ]))

async def referral_scope_callback(query: CallbackQuery, state: FSMContext):
    if not await require_admin_or_deny_query(query):
        return
    action = (query.data or "").split(":")[-1]
    if action == "cancel":
        await state.clear()
        await query.answer("Bekor qilindi")
        try:
            await query.message.edit_text("❌ Bekor qilindi.")
        except Exception:
            pass
        return

    data = await state.get_data()
    count, days, err = database_module.clean_referral_config(
        data.get("ref_count"), data.get("ref_days"))
    if err:
        await state.clear()
        await query.answer("Ma'lumot yo'qoldi, boshidan boshlang.", show_alert=True)
        return
    await query.answer()

    if action == "one":
        await state.set_state(ReferralStates.waiting_for_user)
        await query.message.answer(
            "👤 <b>Kimga?</b>\n\n"
            "<code>@username</code> yoki ID raqamini yozing.\n\n"
            "<blockquote>Bir nechtasini probel bilan ajratib ham "
            "yozsangiz bo'ladi.</blockquote>",
            parse_mode=ParseMode.HTML, reply_markup=_REF_CANCEL_KB)
        return

    # ── HAMMAGA ──
    await state.clear()
    try:
        await database_module.set_referral_config(count, days, None)
    except Exception:
        logger.exception("set_referral_config error")
        await query.message.answer("⚠️ Bazaga yozib bo'lmadi.")
        return

    try:
        users = await database_module.get_all_users()
    except Exception:
        logger.exception("get_all_users error")
        await query.message.answer(
            f"✅ Shart o'rnatildi ({count} → {days} kun), lekin "
            f"foydalanuvchilar ro'yxatini olib bo'lmadi — taklif yuborilmadi.")
        return

    target_ids = [u["user_id"] for u in users
                  if u.get("is_active", True) and not u.get("is_banned")]
    progress = await query.message.answer(
        f"📤 Taklif yuborilmoqda: 0/{len(target_ids)}")
    sent = 0
    for i, uid in enumerate(target_ids, 1):
        if await pro_module.send_referral_invite(uid):
            sent += 1
        # Broadcast bilan bir xil sur'at — Telegram flood-controlga
        # tushmaslik uchun.
        await asyncio.sleep(0.05)
        if i % 25 == 0:
            try:
                await progress.edit_text(
                    f"📤 Taklif yuborilmoqda: {i}/{len(target_ids)}")
            except Exception:
                pass

    try:
        await database_module.log_admin_action(
            query.from_user.id, "referral_campaign", None,
            f"{count}/{days}kun, {sent} ta")
    except Exception:
        pass
    try:
        await progress.edit_text(
            f"✅ <b>Kampaniya yakunlandi.</b>\n\n"
            f"<blockquote>Shart: har <b>{count} ta</b> do'st → "
            f"<b>{days} kun</b> Pro (hammaga).</blockquote>\n\n"
            f"📨 Yuborildi: <b>{sent}</b> ta\n"
            f"❌ Yetib bormadi: <b>{len(target_ids) - sent}</b> ta "
            f"<i>(bloklagan yoki chat topilmadi)</i>",
            parse_mode=ParseMode.HTML)
    except Exception:
        pass

async def process_referral_user(message: Message, state: FSMContext):
    if not await require_admin_or_deny(message):
        await state.clear()
        return
    if await _ref_cancelled(message, state):
        return
    data = await state.get_data()
    count, days, err = database_module.clean_referral_config(
        data.get("ref_count"), data.get("ref_days"))
    if err:
        await state.clear()
        await message.answer("❗️ Ma'lumot yo'qoldi. Boshidan boshlang.",
                             reply_markup=admin_keyboard)
        return

    found, missing = await _resolve_recipients(message.text or "")
    if not found:
        await message.answer(
            "❗️ Bunday foydalanuvchi topilmadi. U botga hech qachon "
            "/start bermagan bo'lishi mumkin. Qayta urinib ko'ring.")
        return
    await state.clear()

    sent, failed, banned = [], [], []
    for uid, name, is_banned_flag in found:
        if is_banned_flag:
            banned.append(name)
            continue
        try:
            # Shaxsiy shart AVVAL yoziladi: taklif xabari shartni
            # o'qib ko'rsatadi, teskari tartibda odam eski shartni
            # ko'rib qolardi.
            await database_module.set_referral_config(count, days, uid)
        except Exception:
            logger.exception("set_referral_config error")
            failed.append(name)
            continue
        ok = await pro_module.send_referral_invite(uid)
        (sent if ok else failed).append(name)
        await asyncio.sleep(0.05)

    try:
        await database_module.log_admin_action(
            message.from_user.id, "referral_campaign", None,
            f"{count}/{days}kun, {len(sent)} ta")
    except Exception:
        pass
    await message.answer(
        f"✅ Shaxsiy shart: har <b>{count} ta</b> do'st → "
        f"<b>{days} kun</b> Pro.", parse_mode=ParseMode.HTML)
    await _report_delivery(message, sent, failed, missing, banned)

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

    if action == "new":
        await query.answer()
        await state.set_state(PromoAdminStates.waiting_for_spec)
        await query.message.answer(_PROMO_HELP, parse_mode=ParseMode.HTML)
        return

    if action == "list":
        await query.answer()
        text, kb = await _render_promo_list()
        await query.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)
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
            await query.message.answer(
                "❗️ Ishlatsa bo'ladigan promokod yo'q.\n"
                "Avval <b>🎟 Yangi promokod yaratish</b> tugmasini bosing.",
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
        await message.answer("❗️ Kod yo'qoldi. 🎁 Bepul Pro dan qayta boshlang.")
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

# --------------------------------------------------
# PROMOKODLAR
# --------------------------------------------------
_PROMO_HELP = (
    "🎟 <b>Promokodlar</b>\n\n"
    "Yangi kod yaratish uchun bitta qatorda yuboring:\n"
    "<code>KOD KUN MAX MUDDAT</code>\n\n"
    "├ <b>KOD</b> — harflar/raqamlar (masalan NEWYEAR)\n"
    "├ <b>KUN</b> — necha kun Pro beriladi\n"
    "├ <b>MAX</b> — necha marta ishlatish mumkin\n"
    "└ <b>MUDDAT</b> — YYYY-MM-DD yoki <code>-</code> (cheksiz)\n\n"
    "<b>Misol:</b> <code>NEWYEAR 30 100 2026-01-31</code>\n"
    "<b>Misol:</b> <code>SORRY 7 1 -</code>"
)

async def _render_promo_list():
    try:
        codes = await database_module.list_promo_codes()
    except Exception:
        logger.exception("list_promo_codes error")
        return "❌ DB xatosi.", None

    if not codes:
        return _PROMO_HELP + "\n\n— Hozircha kod yo'q —", None

    lines = [_PROMO_HELP, "\n<b>Mavjud kodlar:</b>"]
    rows = []
    for c in codes:
        expired = c['expires_at'] is not None and c['expires_at'] <= datetime.now(timezone.utc)
        if c['revoked']:
            mark = "🚫"
        elif expired or c['used_count'] >= c['max_uses']:
            mark = "⌛️"
        else:
            mark = "✅"
        until = format_dt(c['expires_at']) if c['expires_at'] else "cheksiz"
        lines.append(
            f"{mark} <code>{c['code']}</code> — {c['days']} kun · "
            f"{c['used_count']}/{c['max_uses']} · {until}"
        )
        if not c['revoked']:
            rows.append([InlineKeyboardButton(
                text=f"🚫 {c['code']} bekor qilish",
                callback_data=f"promo:revoke:{c['code']}")])

    rows.append([InlineKeyboardButton(text="🔙 Yopish", callback_data="promo:close")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)

async def show_promo_menu(message: Message, state: FSMContext):
    if not await require_admin_or_deny(message):
        return
    text, kb = await _render_promo_list()
    await state.set_state(PromoAdminStates.waiting_for_spec)
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def process_promo_create(message: Message, state: FSMContext):
    if not await require_admin_or_deny(message):
        await state.clear()
        return

    parts = (message.text or "").split()
    if len(parts) != 4:
        await message.answer(
            "❗️ Format: <code>KOD KUN MAX MUDDAT</code>\n"
            "Misol: <code>NEWYEAR 30 100 2026-01-31</code>\n\n"
            "Bekor qilish uchun boshqa tugmani bosing.",
            parse_mode=ParseMode.HTML)
        return

    code, days_raw, max_raw, expiry_raw = parts
    if not code.replace("_", "").isalnum() or len(code) > 32:
        await message.answer("❗️ Kod faqat harf/raqamdan iborat va 32 belgidan qisqa bo'lsin.")
        return
    try:
        days, max_uses = int(days_raw), int(max_raw)
    except ValueError:
        await message.answer("❗️ KUN va MAX butun son bo'lishi kerak.")
        return
    if not (0 < days <= 3650) or not (0 < max_uses <= 100000):
        await message.answer("❗️ KUN 1-3650, MAX 1-100000 oralig'ida bo'lsin.")
        return

    expires_at = None
    if expiry_raw != "-":
        try:
            expires_at = datetime.strptime(expiry_raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            await message.answer("❗️ MUDDAT formati: YYYY-MM-DD yoki <code>-</code>",
                                 parse_mode=ParseMode.HTML)
            return
        if expires_at <= datetime.now(timezone.utc):
            await message.answer("❗️ Muddat kelajakda bo'lishi kerak.")
            return

    admin_id = message.from_user.id
    try:
        created = await database_module.create_promo_code(
            code, days, max_uses, expires_at, admin_id)
    except Exception:
        logger.exception("create_promo_code error")
        await message.answer("❌ DB xatosi.")
        return

    if not created:
        await message.answer(f"❗️ <code>{code.upper()}</code> kodi allaqachon mavjud.",
                             parse_mode=ParseMode.HTML)
        return

    try:
        await database_module.log_admin_action(
            admin_id, "create_promo", None, f"{code.upper()} {days}d x{max_uses}")
    except Exception:
        pass

    # Kod yaratilgach FSM'dan chiqamiz va DARHOL yuborishni taklif
    # qilamiz — admin uchun eng tabiiy keyingi qadam shu.
    await state.clear()
    await message.answer(
        f"✅ <b>PROMOKOD YARATILDI</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<blockquote>"
        f"🎟 Kod: <code>{code.upper()}</code>\n"
        f"💎 Muddat: <b>{days} kun</b> Pro\n"
        f"👥 Necha marta: <b>{max_uses}</b>\n"
        f"⏰ Amal qiladi: <b>"
        f"{format_dt(expires_at) if expires_at else 'cheksiz'}</b>"
        f"</blockquote>\n\n"
        f"<i>Bu kod hech qayerda e'lon qilinmaydi — faqat siz "
        f"yuborgan odam biladi.</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="📨 Shu kodni odamga yuborish",
                callback_data=f"gv:pick:{code.upper()}", style="success")],
            [InlineKeyboardButton(text="🎁 Bepul Pro menyusi",
                                  callback_data="gv:menu")],
        ]))

async def promo_admin_callback(query: CallbackQuery, state: FSMContext):
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

    if action == "revoke" and len(parts) == 3:
        code = parts[2]
        try:
            ok = await database_module.revoke_promo_code(code)
            if ok:
                await database_module.log_admin_action(
                    query.from_user.id, "revoke_promo", None, code)
        except Exception:
            logger.exception("revoke_promo_code error")
            await query.answer("❗ DB xatosi.", show_alert=True)
            return
        await query.answer("✅ Bekor qilindi." if ok else "❌ Kod topilmadi.", show_alert=True)
        text, kb = await _render_promo_list()
        try:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
        return

    await query.answer()

# --------------------------------------------------
# TO'LOVLAR VA REFUND
# --------------------------------------------------
