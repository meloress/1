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

from core.config import ACTIVITY_TYPES
from core.loader import bot
from db import database as database_module

logger = logging.getLogger(__name__)

TASHKENT = timezone(timedelta(hours=5))
REPORT_HOUR = 9                 # Toshkent vaqti bilan ertalabki hisobot
CHECK_INTERVAL = 300            # rejalashtirilgan tarqatmani tekshirish oralig'i

# ⚠️ Bu yerda ILGARI `ACTIVITY_LABELS` degan QO'LDA yozilgan uchinchi
# nusxa turardi va unda `location_message` YO'Q edi — ya'ni kunlik
# hisobot joylashuv so'rovini «location_message» degan xom satr qilib
# ko'rsatardi. Nomlar endi `core/config.py::ACTIVITY_TYPES` da, bitta
# joyda: SQL filtri, Telegram ekrani, kunlik hisobot va web panel —
# to'rtalasi ham o'shandan o'qiydi.


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
            _emoji, nom, _ball = ACTIVITY_TYPES.get(tur, ("", tur, 0))
            # `.lower()` — hisobotning o'z uslubi: bu qisqa ro'yxat
            # bosh harfsiz yozilgan va shunday qolsin. Umumiy ro'yxatda
            # nomlar bosh harf bilan, chunki u yerda ular jadval
            # sarlavhasi va ustun yorlig'i bo'lib ham ishlatiladi.
            lines.append(f"  {nom.lower()} — {cnt}")
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
        # Token jadvalini shu yerda qirqamiz: kuniga bir marta, va
        # allaqachon uyg'oq turgan vazifada. Alohida kuzatuvchi
        # ochishning ma'nosi yo'q.
        try:
            ochdi = await database_module.token_tozala()
            if ochdi:
                logger.info(f"[Token] {ochdi} ta eski qator o'chirildi")
        except Exception:
            logger.exception("token jadvali tozalanmadi")
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

# ═══════════════════════════════════════════════════════════════════
#  OGOHLANTIRISHLAR
# ═══════════════════════════════════════════════════════════════════
# NEGA KERAK: panel TORTIB OLISH rejimida — admin o'zi ochmaguncha hech
# narsa bilmaydi, kunlik hisobot esa ertalab keladi. Ya'ni kechqurun
# bot javob bermay qolsa, buni ertasi kuni bilamiz. Ogohlantirish shu
# oraliqni yopadi: faqat «nimadir buzildi» darajasidagi ikki holat.
#
# ⚠️ ATAYLAB IKKITA SHART. Uchinchisini qo'shishdan oldin o'ylang:
# tez-tez keladigan ogohlantirish e'tiborsiz qolib ketadi, va o'shanda
# haqiqiysi ham o'tib ketadi.
OGOH_TEKSHIRUV = 15 * 60          # har 15 daqiqada
OGOH_XATO_CHEGARA = 20            # soatiga shuncha xatodan ko'p bo'lsa
OGOH_JIMLIK_SOAT = 3              # shuncha soat hech kim yozmasa

# ⚠️ Takror yubormaslik uchun RAM bayrog'i. Holat o'zgarganda
# («yomon» → «yaxshi») bayroq tushadi va keyingi buzilishda yana
# xabar keladi. Bazaga yozish shart emas: bot qayta ishga tushsa
# baribir qaytadan tekshiradi va bu xato tomon emas.
_ogoh_holat: dict = {}


async def _ogoh_yubor(matn: str) -> None:
    """Kuzatuv guruhiga. Guruh sozlanmagan bo'lsa — jim."""
    guruh = await database_module.get_watch_group_id()
    if not guruh:
        return
    try:
        await bot.send_message(guruh, matn, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"[Ogohlantirish] yuborilmadi: {e}")


async def _ogoh_tekshir() -> None:
    """Bir marta tekshiradi. Istisno tashlamaydi."""
    xulosa = await database_module.error_summary()
    soatlik = await database_module.count_errors(kun=1)

    # 1) Xatolar to'lqini. `kun=1` sutkalik, shuning uchun soatlikka
    #    o'tkazamiz — chegara soat bo'yicha o'qilishi kerak.
    kop = (xulosa.get("day") or 0) >= OGOH_XATO_CHEGARA
    if kop and not _ogoh_holat.get("xato"):
        _ogoh_holat["xato"] = True
        await _ogoh_yubor(
            "🔴 <b>Xatolar ko'payib ketdi</b>\n"
            f"So'nggi 24 soatda <b>{xulosa.get('day')}</b> ta xato "
            f"({xulosa.get('users_day') or 0} kishida).\n"
            "Panel → Jurnal → Xatolar")
    elif not kop:
        _ogoh_holat["xato"] = False

    # 2) Jimlik. Bu «bot o'lgan» ning eng arzon belgisi: polling
    #    yiqilsa ham, OpenAI yiqilsa ham, baza yiqilsa ham amal
    #    yozilmay qoladi.
    #
    #    ⚠️ Kechasi jimlik NORMAL — o'zbek vaqti bilan 02:00–08:00
    #    orasida ogohlantirmaymiz, aks holda har tun yolg'on signal
    #    kelardi va ertalabgacha hech kim unga qaramay qo'yardi.
    soat = datetime.now(TASHKENT).hour
    if 2 <= soat < 8:
        _ogoh_holat["jim"] = False
        return

    oxirgi = await database_module.last_activity_at()
    if oxirgi is None:
        return
    jim_soat = (datetime.now(timezone.utc) - oxirgi).total_seconds() / 3600
    if jim_soat >= OGOH_JIMLIK_SOAT and not _ogoh_holat.get("jim"):
        _ogoh_holat["jim"] = True
        await _ogoh_yubor(
            "🟠 <b>Bot jim</b>\n"
            f"Oxirgi so'rovdan beri <b>{jim_soat:.1f} soat</b> o'tdi.\n"
            "Polling, baza yoki OpenAI yiqilgan bo'lishi mumkin — "
            "Railway loglarini ko'ring.")
    elif jim_soat < OGOH_JIMLIK_SOAT:
        _ogoh_holat["jim"] = False


async def alert_watcher():
    """Ogohlantirish kuzatuvchisi.

    Boshqa kuzatuvchilar bilan bir xil naqsh: oddiy `while + sleep`,
    alohida rejalashtiruvchi kerak emas. Har tekshiruv ikkita yengil
    so'rov, ya'ni 15 daqiqada bir marta bo'lgani uchun narxi nolga yaqin.
    """
    # Ishga tushgan zahoti tekshirmaymiz: deploydan keyin baza hali
    # ulanmagan bo'lishi va birinchi tekshiruv bekorga yiqilishi mumkin.
    await asyncio.sleep(OGOH_TEKSHIRUV)
    while True:
        try:
            await _ogoh_tekshir()
        except Exception:
            logger.exception("ogohlantirish tekshiruvi yiqildi")
        await asyncio.sleep(OGOH_TEKSHIRUV)
