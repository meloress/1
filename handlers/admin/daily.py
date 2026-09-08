"""Kunlik avtomatik hisobot va rejalashtirilgan tarqatma yuboruvchi.

⚠️ NEGA HISOBOT O'ZI KELADI: ochish kerak bo'lgan panel — ochilmaydigan
panel. Admin statistikani har kuni qo'lda ochmaydi, ya'ni foydalanuvchi
soni tushib ketgani yoki sotuv to'xtaganini haftadan keyin biladi.

Naqsh `handlers/helpers.py` dagi watcher'lar bilan bir xil: oddiy
while+sleep, alohida cron kerak emas.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram.enums import ParseMode

from core.loader import bot
from db import database as database_module

logger = logging.getLogger(__name__)

TASHKENT = timezone(timedelta(hours=5))
REPORT_HOUR = 9                 # Toshkent vaqti bilan ertalabki hisobot
CHECK_INTERVAL = 300            # rejalashtirilgan tarqatmani tekshirish oralig'i

ACTIVITY_LABELS = {
    "text_message": "matn",
    "photo_message": "rasm",
    "document_message": "hujjat",
    "voice_message": "ovoz",
    "guest_text_message": "guruh matn",
    "guest_photo_message": "guruh rasm",
    "guest_document_message": "guruh hujjat",
    "guest_voice_message": "guruh ovoz",
    "file_task": "fayl yaratish",
    "research": "tadqiqot",
}


def build_report(s: dict) -> str:
    """Hisobot matni. Raqamlar `daily_report_stats()` dan."""
    yangi = s.get("new_users") or 0
    faol = s.get("active_users") or 0
    jami = s.get("total_users") or 0
    sotuv = s.get("sales") or 0
    stars = s.get("stars") or 0
    xato = s.get("errors") or 0

    lines = [
        "📊 <b>Kunlik hisobot</b>",
        f"<i>{datetime.now(TASHKENT).strftime('%Y-%m-%d')} · so'nggi 24 soat</i>",
        "",
        f"👥 Yangi: <b>{yangi}</b> · faol: <b>{faol}</b> · jami: <b>{jami}</b>",
        f"💎 Pro: <b>{s.get('pro_users') or 0}</b>",
        f"💰 Sotuv: <b>{sotuv}</b> ta · <b>{stars}</b> ⭐",
        f"⚡ Amallar: <b>{s.get('actions') or 0}</b>",
    ]
    # Xato qatori faqat xato BO'LSA — "0 ta xato" har kuni takrorlanib,
    # muhim qatorlarni ko'zdan yashiradi.
    if xato:
        lines.append(f"⚠️ Xatolar: <b>{xato}</b> ta")

    top = s.get("top_types") or []
    if top:
        lines.append("")
        lines.append("<b>Eng ko'p ishlatilgani:</b>")
        for tur, cnt in top:
            lines.append(f"  {ACTIVITY_LABELS.get(tur, tur)} — {cnt}")
    return "\n".join(lines)


async def _admin_ids() -> list[int]:
    try:
        admins = [a["user_id"] for a in await database_module.get_admins()]
    except Exception:
        logger.exception("get_admins error (kunlik hisobot)")
        admins = []
    try:
        super_id = await database_module.get_superadmin_id()
        if super_id and super_id not in admins:
            admins.append(super_id)
    except Exception:
        logger.exception("get_superadmin_id error (kunlik hisobot)")
    return admins


async def send_daily_report() -> int:
    """Hisobotni hamma adminga yuboradi. Qaytaradi: yetkazilganlar soni."""
    stats = await database_module.daily_report_stats()
    matn = build_report(stats)
    yetdi = 0
    for uid in await _admin_ids():
        try:
            await bot.send_message(uid, matn, parse_mode=ParseMode.HTML)
            yetdi += 1
        except Exception:
            logger.warning(f"Kunlik hisobot yetkazilmadi: {uid}")
    return yetdi


def _seconds_until_report() -> float:
    """REPORT_HOUR gacha qolgan soniya (Toshkent vaqti bo'yicha)."""
    now = datetime.now(TASHKENT)
    keyingi = now.replace(hour=REPORT_HOUR, minute=0, second=0, microsecond=0)
    if keyingi <= now:
        keyingi += timedelta(days=1)
    return (keyingi - now).total_seconds()


async def daily_report_watcher():
    """Har kuni REPORT_HOUR da hisobot yuboradi.

    ⚠️ Soniyalab hisoblanadi, `sleep(24*3600)` emas: bot qayta ishga
    tushganda vaqt siljib ketmasligi kerak (deploy kuniga bir necha
    marta bo'ladi, ya'ni surilish tez to'planardi).
    """
    while True:
        await asyncio.sleep(_seconds_until_report())
        try:
            n = await send_daily_report()
            logger.info(f"[Kunlik hisobot] {n} ta adminga yuborildi")
        except Exception:
            logger.exception("kunlik hisobot yuborilmadi")
        # Bir soat uxlaymiz, aks holda o'sha daqiqada sikl qayta
        # aylanib, hisobot ikkinchi marta ketishi mumkin.
        await asyncio.sleep(3600)


async def scheduled_broadcast_watcher():
    """Vaqti kelgan tarqatmalarni yuboradi.

    Oluvchilar SHU YERDA hisoblanadi (bazada saqlanmaydi): tarqatma bir
    kun oldin rejalashtirilgan bo'lsa, o'shandagi ro'yxat eskirgan
    bo'lardi — yangi qo'shilganlar xabarni olmasdi.
    """
    from handlers.admin.broadcast import run_broadcast

    while True:
        await asyncio.sleep(CHECK_INTERVAL)
        try:
            for item in await database_module.due_scheduled_broadcasts():
                # Avval "yuborildi" deb belgilaymiz: yuborish bir necha
                # daqiqa davom etadi va shu paytda watcher yana aylanib,
                # xabarni IKKINCHI marta yuborishi mumkin edi.
                await database_module.mark_broadcast_sent(item["id"])
                natija = await run_broadcast(
                    src_chat_id=item["src_chat_id"],
                    src_message_id=item["src_message_id"],
                    buttons=item.get("buttons") or [],
                    segment=item.get("segment") or "all",
                )
                logger.info(f"[Rejali tarqatma] #{item['id']} — {natija}")
                try:
                    await bot.send_message(
                        item["admin_id"],
                        f"🕒 Rejalashtirilgan tarqatma yuborildi.\n"
                        f"✅ {natija[0]} ta · ❌ {natija[1]} ta")
                except Exception:
                    pass
        except Exception:
            logger.exception("rejalashtirilgan tarqatma yuborilmadi")
