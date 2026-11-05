"""Deploydan keyin: uzilgan javoblarni tiklash va botning o'zini tekshirishi.

1) UZILGAN JAVOBLAR. Har push'da shu payt yozilayotgan javoblar o'ladi —
   foydalanuvchi hech narsa olmasdi, ball esa yechilgan qolardi. Endi har
   javob boshida `jarayondagi_javob` ga yoziladi (`boshlandi`), oxirida
   o'chiriladi (`tugadi`). Yangi jarayon `KECHIKISH` dan keyin BOSHQA
   jarayonlarning qolgan qatorlarini oladi: egasiga «uzilib qoldi» +
   «↻ Qayta so'rash» (matnda — `failed_requests` ga qo'yiladi, ya'ni
   mavjud retry tugmasi o'zi ishlaydi) va ball qaytariladi.
   ⚠️ Kechikish SHART: deployda eski va yangi konteyner bir necha soniya
   birga ishlaydi — yangisi darhol qarasa, eskisi hali TUGATAYOTGAN
   javoblarni «uzildi» deb e'lon qilardi.

2) O'ZINI TEKSHIRISH. Baza, OpenAI, Telegram, sandbox, panel — har deployda
   bir marta; superadmin'ga bitta xabar. Hammasi joyida — ovozsiz ✅;
   biror narsa buzuq — ❌ (superadmin + guruh), har biri bir marta qayta
   sinalgandan keyin.

⛔️ FAQAT Railway'da (`RAILWAY_GIT_COMMIT_SHA`): lokal `.env` production
bazasiga qaraydi — lokal ishga tushirish production foydalanuvchilarining
qatorlarini «uzilgan» deb o'qib, ularga boshqa bot nomidan yozardi.
"""
import asyncio
import logging
import os
import uuid
from html import escape

from core.loader import bot
from core.memory import store_failed_request
from db import database
from handlers.helpers import make_retry_keyboard, mavzu_kwargs

logger = logging.getLogger(__name__)

JARAYON = uuid.uuid4().hex          # shu jarayon — har ishga tushishda yangi
RAILWAYDA = bool(os.getenv("RAILWAY_GIT_COMMIT_SHA"))
KECHIKISH = 120                     # s — eski konteyner o'chishiga yetarli
YANGI_DAQIQA = 30                   # bundan eski uzilishga yozilmaydi
_vazifalar: set = set()             # fon o'chirishlari GC'ga yeyilmasin


async def boshlandi(kalit: str, chat_id: int, thread_id: int, user_id: int,
                    prompt: str | None, narx: int) -> None:
    """Javob boshida. Javobni HECH QACHON to'xtatmaydi: baza sekin yoki
    yiqilgan bo'lsa — yozuvsiz davom etadi."""
    if not RAILWAYDA:
        return
    try:
        await asyncio.wait_for(database.jarayon_boshlandi(
            kalit, JARAYON, chat_id, thread_id, user_id,
            (prompt or None) and prompt[:4000], narx), timeout=3)
    except Exception as e:
        logger.warning(f"[Tiklanish] jarayon yozilmadi chat={chat_id}: {e}")


def tugadi(kalit: str | None) -> None:
    """Javob oxirida (`finally`). Kutmaydi."""
    if not RAILWAYDA or kalit is None:
        return

    async def _ochir():
        try:
            await database.jarayon_tugadi(kalit)
        except Exception as e:
            logger.warning(f"[Tiklanish] jarayon o'chirilmadi: {e}")

    try:
        t = asyncio.get_running_loop().create_task(_ochir())
    except RuntimeError:
        return
    _vazifalar.add(t)
    t.add_done_callback(_vazifalar.discard)


async def uzilganlarni_tikla() -> int:
    """Qaytadi: nechta foydalanuvchiga yozildi."""
    qatorlar = await database.uzilgan_javoblar(JARAYON, YANGI_DAQIQA)
    # Bir chatga bitta xabar — eng oxirgisi (`failed_requests` chat bo'yicha).
    oxirgi = {}
    for r in sorted(qatorlar, key=lambda r: r["boshlandi"]):
        oxirgi[r["chat_id"]] = r
    for r in qatorlar:
        if r["narx"] > 0:
            try:
                await database.refund_quota(r["user_id"], r["narx"])
            except Exception as e:
                logger.warning(f"[Tiklanish] ball qaytmadi user={r['user_id']}: {e}")
    n = 0
    for chat_id, r in oxirgi.items():
        matn = "⚠️ Bot yangilanayotgan paytda javobingiz uzilib qoldi — uzr."
        if r["narx"] > 0:
            matn += " Ball qaytarildi."
        prompt = r["prompt"]
        try:
            if prompt:
                qisqa = prompt if len(prompt) <= 120 else prompt[:117] + "…"
                xabar = await bot.send_message(
                    chat_id, f"{matn}\n\nSavolingiz: «{escape(qisqa)}»\n"
                    "Pastdagi tugma bilan qayta so'rang.",
                    reply_markup=make_retry_keyboard(chat_id, attempts=0),
                    **mavzu_kwargs(r["thread_id"]))
                store_failed_request(chat_id, r["user_id"], prompt, prompt,
                                     xabar.message_id, thread_id=r["thread_id"])
            else:
                await bot.send_message(
                    chat_id, f"{matn}\n\nIltimos, xabaringizni qayta yuboring.",
                    **mavzu_kwargs(r["thread_id"]))
            n += 1
        except Exception as e:
            logger.info(f"[Tiklanish] xabar yetmadi chat={chat_id}: {e}")
    if qatorlar:
        logger.info(f"[Tiklanish] {len(qatorlar)} ta uzilgan javob, {n} ta chatga yozildi")
    return n


# ── O'zini tekshirish ─────────────────────────────────────────────────
async def _baza():
    await database.get_maintenance()


async def _openai():
    from services import avto_tatil
    holat, matn = await avto_tatil.sinov()
    if holat != "ok":
        raise RuntimeError(avto_tatil.SABABLAR.get(holat, matn or "javob yo'q"))


async def _telegram():
    await bot.get_me()


async def _sandbox():
    from services.sandbox import run_in_sandbox
    r = await run_in_sandbox("print(6*7)")
    if not r.success or "42" not in r.stdout:
        raise RuntimeError((r.stderr or r.traceback or "natija yo'q")[-150:])


async def _panel():
    import aiohttp
    port = int(os.getenv("PORT", "8080"))
    async with aiohttp.ClientSession() as s:
        async with s.get(f"http://127.0.0.1:{port}/",
                         timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status != 200:
                raise RuntimeError(f"HTTP {r.status}")


TEKSHIRUVLAR = (("Baza", _baza), ("OpenAI", _openai), ("Telegram", _telegram),
                ("Sandbox", _sandbox), ("Panel", _panel))


async def _sina(fn, qayta: float = 20) -> str | None:
    """None — ishlaydi; matn — xato. Bir marta qayta sinaladi: deploydan
    keyingi birinchi soniyalarda bitta yiqilish hali buzilish emas."""
    for urinish in range(2):
        try:
            await asyncio.wait_for(fn(), timeout=60)
            return None
        except Exception as e:
            xato = (str(e) or type(e).__name__)[:150]
        if urinish == 0:
            await asyncio.sleep(qayta)
    return xato


async def ozini_tekshir(tiklandi: int | None, qayta: float = 20) -> str:
    """Hisobot matni (yuboradi ham). Istisno tashlamaydi."""
    natija = await asyncio.gather(*(_sina(fn, qayta) for _, fn in TEKSHIRUVLAR))
    xatolar = [(nom, x) for (nom, _), x in zip(TEKSHIRUVLAR, natija) if x]
    commit = (os.getenv("RAILWAY_GIT_COMMIT_SHA") or "")[:7] or "?"
    izoh = (os.getenv("RAILWAY_GIT_COMMIT_MESSAGE") or "").strip().splitlines()
    qatorlar = [("✅ <b>Deploy ishga tushdi</b>" if not xatolar
                 else "❌ <b>Deploydan keyin muammo</b>") + f" · <code>{commit}</code>"]
    if izoh:
        qatorlar.append(f"<i>{escape(izoh[0][:80])}</i>")
    qatorlar.append(" · ".join(f"{nom} {'✗' if x else '✓'}"
                               for (nom, _), x in zip(TEKSHIRUVLAR, natija)))
    for nom, x in xatolar:
        qatorlar.append(f"• <b>{nom}</b>: <code>{escape(x)}</code>")
    if tiklandi:
        qatorlar.append(f"↻ {tiklandi} ta uzilgan javob egasiga «Qayta so'rash» yuborildi")
    try:
        t = await database.get_maintenance()
        if t.get("active"):
            qatorlar.append("🛠 Texnik ta'til YOQILGAN" +
                            (" (avtomatik)" if t.get("avto") else ""))
    except Exception:
        pass
    matn = "\n".join(qatorlar)
    try:
        if xatolar:
            from services import avto_tatil
            await avto_tatil._xabar(matn)
        else:
            sid = await database.get_superadmin_id()
            if sid:
                await bot.send_message(sid, matn, parse_mode="HTML",
                                       disable_notification=True)
    except Exception as e:
        logger.warning(f"[Tiklanish] hisobot yuborilmadi: {e}")
    logger.info(f"[Tiklanish] o'zini tekshirish: {len(xatolar)} ta xato")
    return matn


async def ishga_tushganda() -> None:
    """Fon vazifasi (`main.py`), bir marta."""
    if not RAILWAYDA:
        return
    await asyncio.sleep(KECHIKISH)
    tiklandi = None
    try:
        tiklandi = await uzilganlarni_tikla()
    except Exception:
        logger.exception("[Tiklanish] uzilgan javoblar tiklanmadi")
    try:
        await ozini_tekshir(tiklandi)
    except Exception:
        logger.exception("[Tiklanish] o'zini tekshirish yiqildi")
