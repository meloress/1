"""Jurnal va sozlamalar: audit, xatolar, daromad, limitlar.

To'rttasi ham "ko'rish" ekrani va bir xil naqshda ishlaydi (sahifalash,
`jr:` callback prefiksi), shuning uchun bitta faylda.

⚠️ Bu ekranlar reply-klaviaturaga ALOHIDA tugma qo'shmaydi: u
allaqachon 11 ta tugmali. Hammasi bitta "📋 Jurnal va sozlamalar"
tugmasi ostidagi inline menyuda.
"""

import logging
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from db import database as database_module
from core.config import PLAN_LIMITS, apply_limit_overrides
from handlers.admin.common import (
    format_dt, _format_user_link,
    require_admin_or_deny, require_admin_or_deny_query,
)

logger = logging.getLogger(__name__)

AUDIT_PAGE = 8
ERROR_PAGE = 6

# Limitlar ekranida ko'rsatiladigan tariflar va sanoqlar. `premium`
# ATAYLAB yo'q — u cheksiz va uni sozlashning ma'nosi yo'q.
LIMIT_PLANS = ("free", "pro")
LIMIT_KEYS = (
    ("points", "Ball"),
    ("files", "Fayl"),
    ("images", "Rasm"),
    ("research", "Tadqiqot"),
)

# Audit yozuvidagi texnik nom -> odam o'qiydigan nom. Ro'yxatda
# bo'lmagan amal xom nomi bilan ko'rsatiladi (yashirilmaydi).
ACTION_LABELS = {
    "ban": "🚫 Ban",
    "unban": "✅ Ban olib tashlandi",
    "set_premium": "💎 Premium berildi",
    "set_free": "🆓 Free qilindi",
    "reset_quota": "🔄 Limit tiklandi",
    "refund": "💸 To'lov qaytarildi",
    "add_admin": "➕ Admin qo'shildi",
    "remove_admin": "➖ Admin o'chirildi",
    "broadcast": "📢 Tarqatma",
    "maintenance": "🛠 Texnik ta'til",
    "promo_create": "🎟 Promokod yaratildi",
    "user_report": "📨 Foydalanuvchi xabari",
    "limit_change": "🎚 Limit o'zgartirildi",
}


class LimitStates(StatesGroup):
    waiting_for_value = State()


def _menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧾 Audit jurnali", callback_data="jr:audit:0")],
        [InlineKeyboardButton(text="⚠️ Xatolar", callback_data="jr:err:0")],
        [InlineKeyboardButton(text="💰 Daromad", callback_data="jr:rev")],
        [InlineKeyboardButton(text="🎚 Limitlar", callback_data="jr:limits")],
        [InlineKeyboardButton(text="🕒 Rejalashtirilgan tarqatmalar",
                              callback_data="jr:sched")],
        [InlineKeyboardButton(text="😴 Faol emas foydalanuvchilar",
                              callback_data="jr:off")],
    ])


def _nav(prefix: str, page: int, has_next: bool) -> list:
    """Sahifalash qatori — `ulist:` dagi bilan bir xil ko'rinish."""
    row = []
    if page > 0:
        row.append(InlineKeyboardButton(text="⬅️", callback_data=f"{prefix}:{page - 1}"))
    row.append(InlineKeyboardButton(text=f"{page + 1}", callback_data="jr:noop"))
    if has_next:
        row.append(InlineKeyboardButton(text="➡️", callback_data=f"{prefix}:{page + 1}"))
    return row


async def show_journal_menu(message: Message):
    if not await require_admin_or_deny(message):
        return
    await message.answer("📋 <b>Jurnal va sozlamalar</b>",
                         reply_markup=_menu_kb(), parse_mode=ParseMode.HTML)


# ── Audit jurnali ─────────────────────────────────────────────────

async def _render_audit(page: int) -> tuple[str, InlineKeyboardMarkup]:
    rows = await database_module.get_admin_audit(AUDIT_PAGE, page * AUDIT_PAGE)
    total = await database_module.count_admin_audit()
    if not rows:
        return ("🧾 <b>Audit jurnali</b>\n\nHozircha yozuv yo'q.",
                InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Orqaga", callback_data="jr:menu")]]))

    lines = [f"🧾 <b>Audit jurnali</b> — jami {total} ta\n"]
    for r in rows:
        kim = (_format_user_link(r["admin_id"], r.get("admin_username"))
               if r.get("admin_id") else "<i>tizim</i>")
        amal = ACTION_LABELS.get(r.get("action") or "", r.get("action") or "—")
        satr = f"{format_dt(r.get('action_time'))}\n{kim} → {amal}"
        if r.get("target_user_id"):
            satr += f"\nKim ustida: {_format_user_link(r['target_user_id'], r.get('target_username'))}"
        detail = (r.get("details") or "").strip()
        if detail:
            # Tafsilot ba'zan JSON — uzun bo'lsa kesamiz, aks holda
            # bitta yozuv butun ekranni egallaydi.
            if len(detail) > 120:
                detail = detail[:117] + "…"
            satr += f"\n<i>{detail}</i>"
        lines.append(satr)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        _nav("jr:audit", page, (page + 1) * AUDIT_PAGE < total),
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="jr:menu")],
    ])
    return "\n\n".join(lines), kb


# ── Xatolar ───────────────────────────────────────────────────────

async def _render_errors(page: int) -> tuple[str, InlineKeyboardMarkup]:
    rows = await database_module.recent_errors(ERROR_PAGE, page * ERROR_PAGE)
    xulosa = await database_module.error_summary()
    total = xulosa.get("total") or 0

    bosh = (f"⚠️ <b>Xatolar</b>\n"
            f"24 soat: <b>{xulosa.get('day') or 0}</b> ta "
            f"({xulosa.get('users_day') or 0} ta foydalanuvchida)\n"
            f"7 kun: <b>{xulosa.get('week') or 0}</b> ta · jami {total} ta")
    turlar = xulosa.get("kinds") or []
    if turlar:
        bosh += "\n\n" + " · ".join(f"{k}: {c}" for k, c in turlar)

    if not rows:
        matn = bosh + "\n\n✅ Jurnalda xato yo'q."
    else:
        parts = [bosh, ""]
        for r in rows:
            kim = f" · {_format_user_link(r['user_id'], None)}" if r.get("user_id") else ""
            xabar = (r.get("message") or "").strip()
            if len(xabar) > 200:
                xabar = xabar[:197] + "…"
            parts.append(f"<b>{r.get('kind')}</b> — {format_dt(r.get('created_at'))}{kim}\n"
                         f"<code>{_escape(xabar)}</code>")
        matn = "\n\n".join(parts)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        _nav("jr:err", page, (page + 1) * ERROR_PAGE < total),
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="jr:menu")],
    ])
    return matn, kb


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ── Daromad ───────────────────────────────────────────────────────

async def _render_revenue() -> tuple[str, InlineKeyboardMarkup]:
    r = await database_module.revenue_stats()
    sotuv = r.get("sales_30d") or 0
    stars_30 = r.get("stars_30d") or 0
    ortacha = round(stars_30 / sotuv, 1) if sotuv else 0

    lines = [
        "💰 <b>Daromad</b>\n",
        f"Bugun: <b>{r.get('stars_today') or 0}</b> ⭐",
        f"30 kun: <b>{stars_30}</b> ⭐ ({sotuv} ta sotuv)",
        f"Jami: <b>{r.get('stars_total') or 0}</b> ⭐",
        f"O'rtacha chek: <b>{ortacha}</b> ⭐",
        f"Qaytarilgan: <b>{r.get('refunds') or 0}</b> ta",
    ]
    by_plan = r.get("by_plan") or []
    if by_plan:
        lines.append("\n<b>Tarif bo'yicha:</b>")
        for days, cnt in by_plan:
            lines.append(f"  {days} kun — {cnt} ta")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="jr:menu")]])
    return "\n".join(lines), kb


# ── Limitlar ──────────────────────────────────────────────────────

def _limit_value(plan: str, key: str, overrides: dict):
    """(qiymat, o'zgartirilganmi)."""
    o = (overrides.get(plan) or {})
    if key in o:
        return o[key], True
    return PLAN_LIMITS.get(plan, {}).get(key), False


async def _render_limits() -> tuple[str, InlineKeyboardMarkup]:
    overrides = await database_module.get_limit_overrides()
    lines = ["🎚 <b>Kunlik limitlar</b>\n",
             "<i>Yulduzcha — panelda o'zgartirilgan qiymat.</i>\n"]
    rows = []
    for plan in LIMIT_PLANS:
        nom = "🆓 Free" if plan == "free" else "💎 Pro"
        lines.append(f"<b>{nom}</b>")
        qator = []
        for key, label in LIMIT_KEYS:
            qiymat, uzgargan = _limit_value(plan, key, overrides)
            korinish = "cheksiz" if qiymat is None else str(qiymat)
            lines.append(f"  {label}: <b>{korinish}</b>{' ⭐' if uzgargan else ''}")
            qator.append(InlineKeyboardButton(
                text=f"{label}", callback_data=f"jr:lim:{plan}:{key}"))
            if len(qator) == 2:
                rows.append(qator)
                qator = []
        if qator:
            rows.append(qator)
        lines.append("")
    rows.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="jr:menu")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


async def process_limit_value(message: Message, state: FSMContext):
    if not await require_admin_or_deny(message):
        await state.clear()
        return
    data = await state.get_data()
    plan, key = data.get("plan"), data.get("key")
    await state.clear()
    if not plan or not key:
        return

    raw = (message.text or "").strip().lower()
    if raw in ("bekor", "/cancel", "otmen"):
        await message.answer("❌ Bekor qilindi.")
        return

    # "asl" — o'zgartirishni olib tashlash, ya'ni config'dagi qiymatga
    # qaytish. Cheksizlik ATAYLAB yo'q: cheksiz uchun premium tarifi bor
    # va bepul tarifni cheksiz qilish botni bir kunda sindiradi.
    if raw in ("asl", "default", "-"):
        qiymat = None
    elif raw.isdigit():
        qiymat = int(raw)
        if qiymat > 1_000_000:
            await message.answer("⚠️ Juda katta qiymat. 0 dan 1000000 gacha yozing.")
            return
    else:
        await message.answer("⚠️ Faqat butun son yoki «asl» deb yozing.")
        return

    yangi = await database_module.set_limit_override(plan, key, qiymat)
    apply_limit_overrides(yangi)
    try:
        await database_module.log_admin_action(
            message.from_user.id, "limit_change", None,
            f"{plan}.{key} = {'asl' if qiymat is None else qiymat}")
    except Exception:
        logger.exception("limit_change auditga yozilmadi")

    matn, kb = await _render_limits()
    await message.answer("✅ Limit yangilandi.\n\n" + matn,
                         reply_markup=kb, parse_mode=ParseMode.HTML)


# ── Rejalashtirilgan tarqatmalar va faol emas foydalanuvchilar ─────

async def _render_scheduled() -> tuple[str, InlineKeyboardMarkup]:
    rows = await database_module.list_scheduled_broadcasts()
    if not rows:
        matn = ("🕒 <b>Rejalashtirilgan tarqatmalar</b>\n\nHozircha yo'q.\n"
                "<i>Tarqatma tasdiqlash ekranida «Keyinroq yuborish» tugmasi bor.</i>")
        kb = [[InlineKeyboardButton(text="🔙 Orqaga", callback_data="jr:menu")]]
        return matn, InlineKeyboardMarkup(inline_keyboard=kb)

    lines = ["🕒 <b>Rejalashtirilgan tarqatmalar</b>\n"]
    kb = []
    segment_nom = {"all": "hammaga", "free": "Free", "premium": "Pro"}
    for r in rows:
        lines.append(f"#{r['id']} — {format_dt(r['run_at'])} · "
                     f"{segment_nom.get(r['segment'], r['segment'])}")
        kb.append([InlineKeyboardButton(
            text=f"🗑 #{r['id']} bekor qilish",
            callback_data=f"jr:schedel:{r['id']}")])
    kb.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="jr:menu")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=kb)


async def _render_inactive() -> tuple[str, InlineKeyboardMarkup]:
    rows = await database_module.inactive_users(20)
    total = await database_module.count_inactive_users()
    lines = [f"😴 <b>Faol emas foydalanuvchilar</b> — jami {total} ta\n",
             "<i>Botni bloklagan yoki o'chirgan. Tarqatma paytida aniqlanadi.</i>\n"]
    for r in rows:
        lines.append(f"{_format_user_link(r['user_id'], r.get('username'))} · "
                     f"{r.get('plan_type') or 'free'} · "
                     f"{format_dt(r.get('last_seen'))}")
    if not rows:
        lines.append("✅ Hammasi faol.")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="jr:menu")]])
    return "\n".join(lines), kb


# ── Yagona callback ───────────────────────────────────────────────

async def journal_callback(query: CallbackQuery, state: FSMContext):
    if not await require_admin_or_deny_query(query):
        return
    data = (query.data or "")[3:]          # "jr:" ni kesamiz

    try:
        if data == "noop":
            await query.answer()
            return

        if data == "menu":
            await query.message.edit_text("📋 <b>Jurnal va sozlamalar</b>",
                                          reply_markup=_menu_kb(),
                                          parse_mode=ParseMode.HTML)
        elif data.startswith("audit:"):
            matn, kb = await _render_audit(int(data.split(":")[1]))
            await query.message.edit_text(matn, reply_markup=kb,
                                          parse_mode=ParseMode.HTML,
                                          disable_web_page_preview=True)
        elif data.startswith("err:"):
            matn, kb = await _render_errors(int(data.split(":")[1]))
            await query.message.edit_text(matn, reply_markup=kb,
                                          parse_mode=ParseMode.HTML,
                                          disable_web_page_preview=True)
        elif data == "rev":
            matn, kb = await _render_revenue()
            await query.message.edit_text(matn, reply_markup=kb,
                                          parse_mode=ParseMode.HTML)
        elif data == "limits":
            matn, kb = await _render_limits()
            await query.message.edit_text(matn, reply_markup=kb,
                                          parse_mode=ParseMode.HTML)
        elif data.startswith("lim:"):
            _, plan, key = data.split(":")
            overrides = await database_module.get_limit_overrides()
            hozir, _ = _limit_value(plan, key, overrides)
            label = dict(LIMIT_KEYS).get(key, key)
            await state.set_state(LimitStates.waiting_for_value)
            await state.update_data(plan=plan, key=key)
            await query.message.answer(
                f"🎚 <b>{label}</b> ({plan}) — hozir: "
                f"<b>{'cheksiz' if hozir is None else hozir}</b>\n\n"
                "Yangi qiymatni son bilan yozing.\n"
                "«asl» — config'dagi qiymatga qaytarish, «bekor» — bekor qilish.",
                parse_mode=ParseMode.HTML)
            await query.answer()
            return
        elif data == "sched":
            matn, kb = await _render_scheduled()
            await query.message.edit_text(matn, reply_markup=kb,
                                          parse_mode=ParseMode.HTML)
        elif data.startswith("schedel:"):
            ok = await database_module.cancel_scheduled_broadcast(int(data.split(":")[1]))
            await query.answer("🗑 Bekor qilindi." if ok else "Topilmadi.",
                               show_alert=not ok)
            matn, kb = await _render_scheduled()
            await query.message.edit_text(matn, reply_markup=kb,
                                          parse_mode=ParseMode.HTML)
            return
        elif data == "off":
            matn, kb = await _render_inactive()
            await query.message.edit_text(matn, reply_markup=kb,
                                          parse_mode=ParseMode.HTML,
                                          disable_web_page_preview=True)
        await query.answer()
    except Exception:
        logger.exception("journal_callback error")
        try:
            await query.answer("❗ Xatolik yuz berdi.", show_alert=True)
        except Exception:
            pass
