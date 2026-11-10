# -*- coding: utf-8 -*-
"""O'zini tiklash: qotib qolgan holat, uzilgan javoblar, deploydan keyingi tekshiruv.

NEGA BOR:
  * javob jarayoni xatosiz osilib qolsa, foydalanuvchi deploygacha har
    xabariga «Iltimos kuting» olardi (`BAND_MAX`, `busy_handler`);
  * deploy yozilayotgan javobni o'ldirsa, foydalanuvchi hech narsa olmasdi,
    ball esa yechilgan qolardi (`handlers/tiklanish.py`);
  * buzuq deploy foydalanuvchilardan oldin bilinsin (`ozini_tekshir`).

ENG MUHIM TEKSHIRUVLAR:
  1-band — haqiqiy aiogram Dispatcher: qotib qolgan holat tozalanib, xabar
    KEYINGI routerga o'tadi; yangi holat esa navbatga (eski xatti-harakat).
  3-band — kech tugagan eski so'rov yangisining holatini O'CHIRMAYDI.
  6-band — bir chatga bitta xabar, ball har uzilgan so'rov uchun qaytadi,
    «Qayta so'rash» mavjud retry yo'liga ulanadi.
  9-band — lokalda (Railway emas) HECH NARSA yozilmaydi va yuborilmaydi.

Tarmoqsiz va bazasiz.

    PYTHONIOENCODING=utf-8 python tests/test_tiklanish.py
"""
import asyncio
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _manba import kod                       # noqa: E402

from aiogram import Bot, Dispatcher, Router  # noqa: E402
from aiogram.fsm.storage.memory import MemoryStorage  # noqa: E402
from aiogram.types import Chat, Message, Update, User  # noqa: E402

import handlers.messages as m                # noqa: E402
from core import memory as mem               # noqa: E402
from db import database                      # noqa: E402
from handlers import tiklanish as tk         # noqa: E402
from services import avto_tatil              # noqa: E402

_n = 0


def check(nom, shart):
    global _n
    _n += 1
    assert shart, f"[{_n}] {nom} — YIQILDI"
    print(f"[{_n}] {nom} OK")


CHAT, USER = 501, 501


def yangilanish(matn, uid=1):
    return Update(update_id=uid, message=Message(
        message_id=uid, date=datetime.now(timezone.utc), text=matn,
        chat=Chat(id=CHAT, type="private"),
        from_user=User(id=USER, is_bot=False, first_name="A")))


class Holat:
    def __init__(self):
        self.d, self.s = {}, None

    async def set_state(self, s):
        self.s = s

    async def update_data(self, **k):
        self.d.update(k)

    async def get_data(self):
        return dict(self.d)

    async def clear(self):
        self.d, self.s = {}, None


async def main():
    # ── 1-2. Qotib qolgan holat — haqiqiy Dispatcher ─────────────
    dp = Dispatcher(storage=MemoryStorage())
    keyingi = Router()
    tushdi = []

    @keyingi.message()
    async def oddiy(message, state):
        tushdi.append((message.text, await state.get_state()))

    dp.include_router(m.router)
    dp.include_router(keyingi)
    bot = Bot("123456:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
    ctx = dp.fsm.get_context(bot, CHAT, USER)
    asl_answer = Message.answer

    async def jim_answer(self, *a, **k):
        return None

    Message.answer = jim_answer
    try:
        await ctx.set_state(m.GeneratingState.generating)
        await ctx.set_data({"band_vaqt": time.time() - m.BAND_MAX - 5, "band_kalit": "a"})
        await dp.feed_update(bot, yangilanish("salom", 1))
        qotgan = list(tushdi)
        holat_keyin = await ctx.get_state()

        tushdi.clear()
        m.text_merge_buffers.clear()
        await ctx.set_state(m.GeneratingState.generating)
        await ctx.set_data({"band_vaqt": time.time(), "band_kalit": "b"})
        await dp.feed_update(bot, yangilanish("ikkinchi", 2))
        navbat = m.text_merge_buffers.get((CHAT, 0), {}).get("parts")
    finally:
        Message.answer = asl_answer
        m.text_merge_buffers.clear()
        await bot.session.close()
    check(f"holat {m.BAND_MAX // 60} daqiqadan eski — tozalandi, xabar KEYINGI handlerga",
          qotgan == [("salom", None)] and holat_keyin is None)
    check("yangi holat — navbatga (eski xatti-harakat), keyingi handler chaqirilmadi",
          tushdi == [] and navbat == ["ikkinchi"])

    # ── 3. Egalik: kech tugagan eski so'rov yangisini o'chirmaydi ─
    tk.RAILWAYDA = False
    h = Holat()
    msg = NS(chat=NS(id=CHAT), from_user=NS(id=USER), message_thread_id=None,
             is_topic_message=False)
    a = await m._band(h, msg, "savol", 3)
    await h.clear()                                 # busy_handler tozaladi
    b = await m._band(h, msg, "yangi savol", 3)
    eski = await m._bosh(h, a)
    qoldi = h.s is not None and h.d.get("band_kalit") == b
    yangi = await m._bosh(h, b)
    check("eski so'rov tugadi — holat yangisiniki qoladi, navbat uyg'otilmaydi; "
          "yangisi tugadi — tozalanadi",
          a != b and eski is False and qoldi and yangi is True and h.s is None)
    check("kalitsiz (hujjat: xato set_state'dan oldin) — eskicha tozalaydi",
          await m._bosh(Holat(), None) is True)

    # ── 5. Railway'da: boshlandi/tugadi bazaga yozadi ────────────
    Q = []

    async def boshla(*a):
        Q.append(("boshla",) + a)

    async def tugat(k):
        Q.append(("tugat", k))

    database.jarayon_boshlandi, database.jarayon_tugadi = boshla, tugat
    tk.RAILWAYDA = True
    await tk.boshlandi("k1", CHAT, 0, USER, "x" * 5000, 3)
    tk.tugadi("k1")
    await asyncio.sleep(0.01)
    check("boshlandi → (kalit, jarayon, chat, mavzu, user, savol ≤4000, narx); tugadi → o'chiradi",
          Q[0][1:3] == ("k1", tk.JARAYON) and len(Q[0][6]) == 4000 and Q[0][7] == 3
          and Q[1] == ("tugat", "k1"))

    # ── 6-7. Uzilganlarni tiklash ────────────────────────────────
    vaqt = datetime.now(timezone.utc)
    qatorlar = [
        dict(chat_id=10, thread_id=0, user_id=10, prompt="birinchi", narx=2,
             boshlandi=vaqt - timedelta(minutes=3)),
        dict(chat_id=10, thread_id=7, user_id=10, prompt="<b>oxirgi</b>", narx=2,
             boshlandi=vaqt - timedelta(minutes=1)),
        dict(chat_id=20, thread_id=0, user_id=20, prompt=None, narx=0,
             boshlandi=vaqt),
    ]
    qaytdi, yuborildi = [], []

    async def uzilgan(jarayon, daqiqa):
        assert jarayon == tk.JARAYON and daqiqa == tk.YANGI_DAQIQA
        return qatorlar

    async def qaytar(uid, narx):
        qaytdi.append((uid, narx))

    class SoxtaBot:
        async def send_message(self, chat_id, text, **kw):
            yuborildi.append((chat_id, text, kw))
            return NS(message_id=777)

        async def get_me(self):
            return NS(username="vexonai")

    database.uzilgan_javoblar, database.refund_quota = uzilgan, qaytar
    tk.bot = SoxtaBot()
    mem.failed_requests.clear()
    n = await tk.uzilganlarni_tikla()
    x10 = next(x for x in yuborildi if x[0] == 10)
    fr = mem.failed_requests.get(10)
    check("bir chatga BITTA xabar (eng oxirgisi), ball HAR so'rov uchun qaytdi",
          n == 2 and len(yuborildi) == 2 and qaytdi == [(10, 2), (10, 2)]
          and "&lt;b&gt;oxirgi" in x10[1] and "Ball qaytarildi" in x10[1])
    check("«Qayta so'rash» — mavjud retry yo'li: failed_requests + retry:<chat> tugmasi, mavzu saqlanadi",
          fr and fr["prompt"] == "<b>oxirgi</b>" and fr["thread_id"] == 7
          and fr["error_message_id"] == 777
          and x10[2]["reply_markup"].inline_keyboard[0][0].callback_data == "retry:10"
          and x10[2].get("message_thread_id") == 7)
    x20 = next(x for x in yuborildi if x[0] == 20)
    check("savolsiz (rasm/ovoz/hujjat) — «qayta yuboring», tugmasiz, ball 0 — qaytarilmaydi",
          "qayta yuboring" in x20[1] and "reply_markup" not in x20[2]
          and "Ball" not in x20[1])

    # ── 9. Lokalda — hech narsa ──────────────────────────────────
    Q.clear()
    tk.RAILWAYDA = False
    await tk.boshlandi("k2", CHAT, 0, USER, "s", 1)
    tk.tugadi("k2")
    yuborildi.clear()
    await tk.ishga_tushganda()
    await asyncio.sleep(0.01)
    check("lokal (RAILWAY_GIT_COMMIT_SHA yo'q) — bazaga ham, Telegram'ga ham hech narsa",
          Q == [] and yuborildi == [])

    # ── 10-11. O'zini tekshirish ─────────────────────────────────
    async def ok():
        return None

    sanoq = {"n": 0}

    async def bir_yiqiladi():
        sanoq["n"] += 1
        if sanoq["n"] == 1:
            raise RuntimeError("birinchi soniyalar")

    async def doim_yiqiladi():
        raise RuntimeError("sandbox ishlamayapti")

    async def superadmin():
        return 555

    async def tatil():
        return {"active": False}

    guruh = []

    async def xabar(matn):
        guruh.append(matn)

    database.get_superadmin_id, database.get_maintenance = superadmin, tatil
    avto_tatil._xabar = xabar
    os.environ["RAILWAY_GIT_COMMIT_SHA"] = "abcdef1234"
    tk.TEKSHIRUVLAR = (("Baza", ok), ("OpenAI", bir_yiqiladi), ("Telegram", ok))
    yuborildi.clear()
    matn = await tk.ozini_tekshir(2, qayta=0)
    check("hammasi joyida (biri 1-urinishda yiqilib, 2-sida o'tdi) — superadmin'ga OVOZLI ✅",
          matn.startswith("✅") and "abcdef1" in matn and "OpenAI ✓" in matn
          and "2 ta uzilgan" in matn and yuborildi[0][0] == 555
          and not yuborildi[0][2].get("disable_notification") and guruh == [])

    tk.TEKSHIRUVLAR = (("Baza", ok), ("Sandbox", doim_yiqiladi))
    yuborildi.clear()
    matn = await tk.ozini_tekshir(None, qayta=0)
    check("biror narsa buzuq — ❌ superadmin + guruhga (ovozli), qaysi biri va nima uchun",
          matn.startswith("❌") and "Sandbox ✗" in matn and "sandbox ishlamayapti" in matn
          and guruh == [matn] and yuborildi == [])


asyncio.run(main())


# ── To'xtash: SIGTERM'dan keyin hamma sessiya yopiladi ────────────
async def yopish_sinovi():
    import main as bosh
    from handlers import eski_bot, guest
    yopildi = []

    class Sessiya:
        closed = False

        def __init__(self, nom):
            self.nom = nom

        async def close(self):
            yopildi.append(self.nom)
            self.closed = True

    class EskiDp:
        async def stop_polling(self):
            yopildi.append("eski polling")
            raise RuntimeError("Polling is not started")   # yiqilsa ham davom

    eski_bot._dp = EskiDp()
    eski_bot._bot = NS(session=Sessiya("eski bot"))
    m._http_session = Sessiya("matn")
    guest._http_session = Sessiya("mehmon")
    await bosh._yopish()
    return yopildi


yopildi = asyncio.run(yopish_sinovi())
check("to'xtashda: eski bot polling + sessiyasi, matn va mehmon sessiyalari yopiladi; "
      "biri yiqilsa ham qolganlari",
      yopildi == ["eski polling", "eski bot", "matn", "mehmon"])
check("main.py: polling `finally` da _yopish() — SIGTERM'dan keyin ham",
      "finally:\n        await _yopish()" in kod("main.py"))

# ── 12-13. Manba qo'riqchilari (izohsiz kod) ─────────────────────
mk = kod("handlers/messages.py")
check("GeneratingState faqat _band() orqali qo'yiladi",
      mk.count("set_state(GeneratingState.generating)") == 1)
check("har 5 javob yo'li: navbat faqat _bosh() True bo'lsa uyg'otiladi",
      mk.count("if await _bosh(state, kalit):") == 5
      and mk.count("_navbatni_uygot(") == 6)        # 5 chaqiruv + ta'rif
check("main.py tiklanishni ishga tushiradi",
      "tiklanish.ishga_tushganda()" in kod("main.py"))

print(f"\nNATIJA: {_n}/{_n} OK")
