"""Avtomatik texnik ta'til — OpenAI bot'ni HAMMA uchun to'xtatganda.

NEGA BOR: kredit tugasa yoki kalit o'chirilsa, har foydalanuvchi «Xatolik
yuz berdi» oladi, egasi esa buni «xatolar ko'paydi» ogohlantirishidan
soatlab keyin biladi. Shu yerda ta'til O'ZI yoqiladi, egasiga darhol
aytiladi va tuzalgach O'ZI o'chadi.

⛔️ BOT O'ZIDAN-O'ZI TO'XTAB QOLMASIN — yoqish uchun uchta shart, hammasi:
  1. Xato `jiddiy_xato()` ro'yxatida: kredit (429 insufficient_quota),
     kalit (401), ruxsat (403), hamma model yo'q (404). Daqiqalik 429,
     timeout, 5xx, ulanish uzilishi — HECH QACHON: ular o'tkinchi.
  2. Haqiqiy so'rovlarda KETMA-KET `KETMA_KET` ta shunday xato. Oradagi
     bitta muvaffaqiyatli javob hisobni nolga tushiradi.
  3. Nazorat so'rovi (`sinov()`, bir necha token) ham JIDDIY xato
     qaytaradi. Sinov o'tsa yoki noaniq (timeout) bo'lsa — yoqilmaydi.
Kunlik token limiti (TPD) ATAYLAB yo'q: kichik sinov o'tadi, katta suhbat
so'rovi o'tmaydi — ta'til yoqilib-o'chib o'ynab qolardi.

O'chishi: `kuzatuvchi()` har `TIKLANISH` soniyada sinaydi. Faqat O'ZI
yoqqan ta'tilni o'chiradi (`maintenance_avto` ustuni); admin panelda
qo'lda yoqqan yoki o'chirgan bo'lsa — boshqaruv adminda.
"""
import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from html import escape

from openai import (AuthenticationError, NotFoundError, PermissionDeniedError,
                    RateLimitError)

logger = logging.getLogger(__name__)

KETMA_KET = 2                 # haqiqiy so'rovlarda ketma-ket jiddiy xato
SINOV_ORALIGI = 120           # tasdiq sinovlari orasidagi eng kam vaqt, s
TIKLANISH = 300               # yoqilgan ta'tilni qayta sinash, s
ESLATMA = 6 * 3600            # hali ham buzuq bo'lsa — eslatma, s
_TOSHKENT = timezone(timedelta(hours=5))

SABABLAR = {
    "kredit": "OpenAI hisobida kredit (pul) tugagan",
    "kalit": "OpenAI API kaliti yaroqsiz yoki o'chirilgan",
    "ruxsat": "OpenAI hisobi bloklangan yoki modelga ruxsat yo'q",
    "model": "bot ishlatadigan modellarning hammasi o'chirilgan",
}
YECHIM = {
    "kredit": "platform.openai.com → Settings → Billing: balansni to'ldiring.",
    "kalit": "platform.openai.com → API keys: yangi kalit oling va Railway'da "
             "OPENAI_API_KEY ni almashtiring.",
    "ruxsat": "platform.openai.com'ga kiring: hisob/loyiha holatini va OpenAI "
              "yuborgan xatlarni tekshiring.",
    "model": "core/config.py dagi GPT_MODEL / MODEL_FALLBACKS ni mavjud modelga "
             "almashtiring.",
}

_ketma_ket = 0
_oxirgi_sinov = 0.0
_sinov_vazifa: asyncio.Task | None = None
_oxirgi_eslatma = time.monotonic()


def jiddiy_xato(e) -> str | None:
    """`SABABLAR` kaliti yoki None (o'tkinchi / boshqa xato). Sof."""
    if isinstance(e, AuthenticationError):
        return "kalit"
    if isinstance(e, PermissionDeniedError):
        return "ruxsat"
    if isinstance(e, RateLimitError):
        # Daqiqalik limit ham 429 — farqi faqat kodda.
        kod = {getattr(e, "code", None), getattr(e, "type", None)}
        return "kredit" if "insufficient_quota" in kod else None
    if isinstance(e, NotFoundError):
        return "model"
    return None


def yaxshi() -> None:
    """Model javob berdi — ketma-ketlik uzildi."""
    global _ketma_ket
    _ketma_ket = 0


def xato(e) -> None:
    """`get_openai_reply` ushlagan xato. Kutmaydi, istisno tashlamaydi."""
    global _ketma_ket, _sinov_vazifa
    try:
        if jiddiy_xato(e) is None:
            return
        _ketma_ket += 1
        if (_ketma_ket < KETMA_KET
                or (_sinov_vazifa is not None and not _sinov_vazifa.done())
                or time.monotonic() - _oxirgi_sinov < SINOV_ORALIGI):
            return
        _sinov_vazifa = asyncio.get_running_loop().create_task(_tasdiqla())
    except Exception:
        logger.exception("[Ta'til] xatoni hisoblab bo'lmadi")


async def sinov() -> tuple[str | None, str]:
    """Kichik nazorat so'rovi, `_open_response_stream` bilan bir xil zaxira
    tartibida (404/429 da keyingi model). Qaytadi: ("ok", "") |
    (jiddiy sabab, xato matni) | (None, matn) — noaniq (timeout, 5xx...)."""
    from core.config import GPT_MODEL, MODEL_FALLBACKS
    from services import ai
    oxirgi = None
    for model in dict.fromkeys([GPT_MODEL, *MODEL_FALLBACKS]):
        try:
            await ai.openai_client.responses.create(
                model=model, input="ok", max_output_tokens=16, store=False,
                timeout=30)
            return "ok", ""
        except (NotFoundError, RateLimitError) as e:
            oxirgi = e
        except Exception as e:
            oxirgi = e
            break
    return jiddiy_xato(oxirgi), str(oxirgi)[:300]


async def _tasdiqla() -> None:
    global _oxirgi_sinov, _ketma_ket
    _oxirgi_sinov = time.monotonic()
    try:
        holat, matn = await sinov()
        if holat == "ok":
            logger.info("[Ta'til] jiddiy xato bor edi, lekin sinov o'tdi — yoqilmadi")
            _ketma_ket = 0
            return
        if holat is None:
            logger.warning(f"[Ta'til] sinov noaniq, yoqilmadi: {matn}")
            return
        await _yoq(holat, matn)
    except Exception:
        logger.exception("[Ta'til] tasdiqlash yiqildi")


async def _yoq(sabab: str, matn: str) -> None:
    global _oxirgi_eslatma
    from db import database
    if not await database.maintenance_avto_yoq(sabab):
        logger.info("[Ta'til] allaqachon yoqilgan — tegilmadi")
        return
    _oxirgi_eslatma = time.monotonic()
    logger.error(f"[Ta'til] AVTOMATIK YOQILDI: {sabab} — {matn}")
    await database.log_error("tatil", f"avtomatik yoqildi: {SABABLAR[sabab]} — {matn}")
    await _xabar(
        "🔴 <b>Texnik ta'til avtomatik yoqildi</b>\n"
        f"Sabab: <b>{SABABLAR[sabab]}</b>\n"
        f"Vaqt: {datetime.now(_TOSHKENT):%d.%m %H:%M}\n"
        f"Xato: <code>{escape(matn[:200])}</code>\n\n"
        f"Nima qilish kerak: {YECHIM[sabab]}\n\n"
        "Foydalanuvchilar va Business mijozlari paneldagi ta'til matnini "
        f"ko'rmoqda. Tuzalgach bot ko'pi bilan {TIKLANISH // 60} daqiqada "
        "ta'tilni O'ZI o'chiradi va sizga yozadi. Qo'lda: Panel → Texnik ta'til.")


async def _xabar(matn: str) -> None:
    """Superadmin'ga shaxsan + kuzatuv guruhiga. Istisno tashlamaydi."""
    from core.loader import bot
    from db import database
    from handlers.admin import daily
    yetdi = False
    try:
        sid = await database.get_superadmin_id()
        if sid:
            await bot.send_message(sid, matn, parse_mode="HTML")
            yetdi = True
    except Exception as e:
        logger.warning(f"[Ta'til] superadmin'ga yuborilmadi: {e}")
    try:
        yetdi = await daily._ogoh_yubor(matn) or yetdi
    except Exception as e:
        logger.warning(f"[Ta'til] guruhga yuborilmadi: {e}")
    if not yetdi:
        logger.error(f"[Ta'til] ogohlantirish HECH KIMGA yetmadi: {matn}")


async def _tiklanish() -> None:
    """Bir marta: o'zimiz yoqqan ta'til hali kerakmi."""
    global _oxirgi_eslatma
    from db import database
    t = await database.get_maintenance()
    sabab = t.get("avto")
    if not (t.get("active") and sabab):
        return
    holat, matn = await sinov()
    if holat == "ok":
        if await database.maintenance_avto_ochir():
            yaxshi()
            logger.info("[Ta'til] tiklandi — avtomatik o'chirildi")
            await _xabar("✅ <b>Bot qayta ishlayapti</b>\n"
                         "Texnik ta'til avtomatik o'chirildi — foydalanuvchilar "
                         "va Business avtojavoblari odatdagidek.")
        return
    if time.monotonic() - _oxirgi_eslatma >= ESLATMA:
        _oxirgi_eslatma = time.monotonic()
        await _xabar("🟠 <b>Texnik ta'til hali ham yoqilgan</b>\n"
                     f"Sabab: <b>{SABABLAR.get(sabab, sabab)}</b>\n"
                     f"Nima qilish kerak: {YECHIM.get(sabab, '')}")


async def kuzatuvchi() -> None:
    """Fon vazifasi (`main.py`). Deploydan keyin ham ishlaydi: belgi bazada."""
    await asyncio.sleep(60)
    while True:
        try:
            await _tiklanish()
        except Exception:
            logger.exception("[Ta'til] tiklanish tekshiruvi yiqildi")
        await asyncio.sleep(TIKLANISH)
