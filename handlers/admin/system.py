"""Foydalanuvchining adminga xabari (report).

⚠️ Bu faylda ILGARI texnik ta'til, kuzatish va admin qo'shish/o'chirish
ekranlari ham bor edi — 7-bosqichda o'chirildi, ular endi web panelda
(`web/api.py`: `/api/maintenance`, `/api/watch`, `/api/admins`). Qoida
o'zi esa o'chmadi: `_check_can_remove_admin()` `common.py` ga ko'chgan
va web o'shani chaqiradi.

⚠️ `report_callback` va `process_report_message` — YAGONA admin
bo'lmagan handlerlar: ularni FOYDALANUVCHI ishga tushiradi, shuning
uchun ularda admin tekshiruvi ATAYLAB yo'q. Shu sababli ular webga
ko'chmadi ham: web paneli faqat adminlarga ochiq, report esa oddiy
odamdan boshlanadi va javobi ham botdan ketadi (REJA 2).
"""

import logging
import json
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
from core.loader import bot
from db import database as database_module
from handlers.admin.common import _format_user_link, format_dt

logger = logging.getLogger(__name__)


class ReportStates(StatesGroup):
    waiting_for_report_message = State()


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

        # Auditga yozuv.
        #
        # ⚠️ KIM YOZGANI `target_user_id` USTUNIGA tushadi, tafsilotdagi
        # JSON ichiga emas. Ilgari uchala ustun ham bo'sh edi va
        # jurnalda qator «Foydalanuvchi xabari — {"reporter_id": …}»
        # bo'lib ko'rinardi: kim shikoyat qilgani xom JSON ichida
        # yashiringan, `users` jadvaliga ulanmagan, ya'ni @username ham
        # ko'rinmasdi. Endi jurnal uni odam sifatida ko'rsatadi.
        #
        # `admin_id` ATAYLAB `None`: bu amalni admin qilgani yo'q.
        try:
            await database_module.log_admin_action(
                None, "user_report", reporter.id, json.dumps({
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
