"""Admin panelning umumiy qismi: qo'riqchilar va bir necha bo'limda
ishlatiladigan yordamchilar.

Bu yerga FAQAT bir nechta bo'lim ishlatadigan narsa tushadi —
`_resolve_recipients` broadcast'da ham, promo'da ham kerak.
Bitta bo'limga tegishlisi o'sha bo'lim faylida qoladi."""

import logging
import html
import re
from datetime import datetime, timezone
from typing import Optional
from aiogram.types import Message, CallbackQuery
from aiogram.enums import ParseMode
from zoneinfo import ZoneInfo
from db import database as database_module

TASHKENT_TZ = ZoneInfo("Asia/Tashkent")

logger = logging.getLogger(__name__)


def format_dt(dt: datetime) -> str:
    """Format datetime to Asia/Tashkent human-friendly string. Accepts tz-aware or naive (assumed UTC)."""
    if dt is None:
        return "—"
    if not isinstance(dt, datetime):
        return str(dt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        dt_tz = dt.astimezone(TASHKENT_TZ)
    except Exception:
        dt = dt.replace(tzinfo=timezone.utc)
        dt_tz = dt.astimezone(TASHKENT_TZ)
    return dt_tz.strftime("%Y-%m-%d %H:%M:%S %Z")


def _format_user_link(user_id: int, username: Optional[str]) -> str:
    """Mention link for the given user, or @username if known."""
    if username:
        return f"@{username}"
    return f'<a href="tg://user?id={user_id}">User {user_id}</a>'


async def require_admin_or_deny(message: Message) -> bool:
    try:
        if await database_module.is_admin(message.from_user.id):
            return True
        if await database_module.is_superadmin(message.from_user.id):
            return True
        await message.answer("❌ Bu buyruq faqat admin uchun.")
        return False
    except Exception:
        logger.exception("is_admin tekshiruvida xato")
        await message.answer("❌ Server xatosi. Keyinroq urinib ko'ring.")
        return False

async def require_admin_or_deny_query(query: CallbackQuery) -> bool:
    try:
        if await database_module.is_admin(query.from_user.id):
            return True
        if await database_module.is_superadmin(query.from_user.id):
            return True
        await query.answer("❌ Bu amal faqat admin uchun.", show_alert=True)
        return False
    except Exception:
        logger.exception("is_admin tekshiruvida xato (callback)")
        await query.answer("❗ Server xatosi. Keyinroq urinib ko'ring.", show_alert=True)
        return False


async def _resolve_recipients(raw: str):
    """"@ali 123456 @vali" satrini foydalanuvchilarga aylantiradi.

    Qaytaradi: (topilganlar[(id, ko'rinadigan nom)], topilmaganlar[str])
    Bir marta ko'p odamga yuborish — kampaniya uchun ham, bitta odam
    uchun ham bir xil ishlaydi, alohida rejim kerak emas.
    """
    tokens = [t.strip(" ,\n\t") for t in re.split(r"[\s,]+", raw or "") if t.strip(" ,\n\t")]
    found, missing, seen = [], [], set()
    for token in tokens[:50]:            # ponytail: bir martada 50 ta yetadi
        try:
            uid = await database_module.get_user_by_identifier(token)
        except Exception:
            uid = None
        if not uid or uid in seen:
            if not uid:
                missing.append(html.escape(token))
            continue
        seen.add(uid)
        try:
            prof = await database_module.get_full_user_profile(uid)
        except Exception:
            prof = None
        # html.escape: token — admin yozgan erkin matn. Ichida "<" bo'lsa
        # HTML parse xatosi butun hisobotni yuborilmas qilardi.
        name = html.escape(token) if token.startswith("@") else f"<code>{uid}</code>"
        if prof and prof.get("username") and prof["username"] != "Mavjud emas":
            name = f"@{prof['username']}"
        found.append((uid, name, bool(prof and prof.get("is_banned"))))
    return found, missing

async def _report_delivery(message: Message, sent, failed, missing, banned):
    lines = [f"📨 <b>Yuborish yakunlandi</b>\n"]
    if sent:
        lines.append(f"✅ <b>Yuborildi ({len(sent)}):</b> " + ", ".join(sent))
    if failed:
        lines.append(f"🚫 <b>Yetmadi ({len(failed)}):</b> " + ", ".join(failed)
                     + "\n<i>Botni bloklagan bo'lishi mumkin.</i>")
    if banned:
        lines.append(f"⛔️ <b>Banlangan, o'tkazib yuborildi:</b> " + ", ".join(banned))
    if missing:
        lines.append(f"❓ <b>Topilmadi ({len(missing)}):</b> " + ", ".join(missing)
                     + "\n<i>Ular botga /start bermagan.</i>")
    await message.answer("\n\n".join(lines), parse_mode=ParseMode.HTML)
