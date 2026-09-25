# -*- coding: utf-8 -*-
"""Ogohlantirishlar: xatolar to'lqini va «bot jim».

NEGA BOR: panel TORTIB OLISH rejimida — admin o'zi ochmaguncha hech
narsa bilmaydi, kunlik hisobot esa ertalab keladi. Kechqurun bot javob
bermay qolsa, buni ertasi kuni bilardik.

ENG MUHIM TEKSHIRUVLAR:
  2-band — bir buzilish uchun BIR ogohlantirish. Har 15 daqiqada
    takrorlansa, admin ularni o'qimay qo'yadi va o'shanda haqiqiysi
    ham o'tib ketadi.
  4-band — kechasi (02:00-08:00) jimlik uchun ogohlantirish YO'Q.
    Usiz har tuni yolg'on signal kelardi.
  6-band — kuzatuv guruhi sozlanmagan bo'lsa jim qoladi, yiqilmaydi.

Offline: baza ham, Telegram ham soxta.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _manba import kod

from handlers.admin import daily as d
from handlers import helpers as _helpers

_xato = 0
# `watch_holat_yoz` ga ketgan chaqiruvlar: (ok, sabab).
HOLAT: list = []


def check(n, nom, shart):
    global _xato
    if shart:
        print(f"[{n}] {nom} OK")
    else:
        _xato += 1
        print(f"[{n}] {nom} XATO")


class SoxtaBot:
    def __init__(self):
        self.xabarlar = []

    async def send_message(self, chat_id, matn, **kw):
        self.xabarlar.append((chat_id, matn))


def sozla(*, xato_kun=0, jim_soat=0.0, guruh=-100500, soat=12):
    """Soxta dunyo: xatolar soni, jimlik davomiyligi, hozirgi soat."""
    d.bot = SoxtaBot()
    d._ogoh_holat.clear()

    async def error_summary():
        return {"day": xato_kun, "week": xato_kun, "total": xato_kun,
                "users_day": 2, "kinds": []}

    async def count_errors(q=None, kun=None):
        return xato_kun

    async def get_watch_group_id():
        return guruh

    async def last_activity_at():
        if jim_soat is None:
            return None
        return datetime.now(timezone.utc) - timedelta(hours=jim_soat)

    for nom, fn in (("error_summary", error_summary),
                    ("count_errors", count_errors),
                    ("get_watch_group_id", get_watch_group_id),
                    ("last_activity_at", last_activity_at)):
        setattr(d.database_module, nom, fn)

    # Kuzatuv holati yozuvi. `kuzatuv_holati()` uni `handlers.helpers`
    # ichidagi `database` orqali chaqiradi, shuning uchun soxta AYNAN
    # o'sha modulga qo'yiladi.
    HOLAT.clear()

    async def watch_holat_yoz(ok, sabab=None):
        HOLAT.append((bool(ok), sabab))
    _helpers.database.watch_holat_yoz = watch_holat_yoz

    # Soatni boshqarish: `datetime.now(TASHKENT).hour` shu orqali o'tadi.
    asl = d.datetime

    class SoxtaVaqt(datetime):
        @classmethod
        def now(cls, tz=None):
            haqiqiy = asl.now(timezone.utc)
            if tz is d.TASHKENT:
                return haqiqiy.astimezone(tz).replace(hour=soat)
            return haqiqiy.astimezone(tz) if tz else haqiqiy

    d.datetime = SoxtaVaqt
    return d.bot, lambda: setattr(d, "datetime", asl)


async def main():
    # ── 1) Xatolar chegaradan oshsa — ogohlantirish ────────────────
    bot, tikla = sozla(xato_kun=d.OGOH_XATO_CHEGARA + 5)
    await d._ogoh_tekshir()
    check(1, "xatolar to'lqinida ogohlantirish keladi",
          any("Xatolar ko'payib" in m for _c, m in bot.xabarlar))

    # ── 2) ⭐ TAKROR YUBORILMAYDI ──────────────────────────────────
    oldin = len(bot.xabarlar)
    await d._ogoh_tekshir()
    await d._ogoh_tekshir()
    check(2, "bir buzilish uchun BIR ogohlantirish",
          len(bot.xabarlar) == oldin)
    tikla()

    # ── 3) Holat tuzalgach bayroq tushadi, keyingi buzilishda yana ─
    bot, tikla = sozla(xato_kun=d.OGOH_XATO_CHEGARA + 5)
    await d._ogoh_tekshir()

    async def tinch():
        return {"day": 0, "week": 0, "total": 0, "users_day": 0, "kinds": []}
    d.database_module.error_summary = tinch
    await d._ogoh_tekshir()          # tuzaldi — bayroq tushadi

    async def yana():
        return {"day": d.OGOH_XATO_CHEGARA + 1, "week": 0, "total": 0,
                "users_day": 1, "kinds": []}
    d.database_module.error_summary = yana
    await d._ogoh_tekshir()
    check(3, "tuzalib qayta buzilsa ogohlantirish qaytadan keladi",
          len([1 for _c, m in bot.xabarlar if "Xatolar ko'payib" in m]) == 2)
    tikla()

    # ── 4) ⭐ KECHASI JIMLIK — OGOHLANTIRISH YO'Q ──────────────────
    bot, tikla = sozla(jim_soat=d.OGOH_JIMLIK_SOAT + 5, soat=4)
    await d._ogoh_tekshir()
    check(4, "kechasi (02:00-08:00) jimlik uchun ogohlantirish yo'q",
          not any("jim" in m for _c, m in bot.xabarlar))
    tikla()

    # ── 5) Kunduzi jimlik — ogohlantirish bor ──────────────────────
    bot, tikla = sozla(jim_soat=d.OGOH_JIMLIK_SOAT + 1, soat=14)
    await d._ogoh_tekshir()
    check(5, "kunduzi uzoq jimlikda ogohlantirish keladi",
          any("Bot jim" in m for _c, m in bot.xabarlar))

    # Qisqa jimlik — hech narsa.
    bot2, _ = sozla(jim_soat=0.5, soat=14)
    await d._ogoh_tekshir()
    check(6, "qisqa jimlik ogohlantirishga sabab emas", not bot2.xabarlar)
    tikla()

    # ── 7) Kuzatuv guruhi yo'q — jim, lekin yiqilmaydi ─────────────
    bot, tikla = sozla(xato_kun=d.OGOH_XATO_CHEGARA + 5, guruh=None)
    await d._ogoh_tekshir()
    check(7, "guruh sozlanmagan bo'lsa jim qoladi, yiqilmaydi",
          not bot.xabarlar)
    tikla()

    # ── 8) Umuman faollik bo'lmasa (bo'sh baza) — jim ──────────────
    # Yangi bot uchun `MAX(...)` NULL qaytaradi; uni «cheksiz jimlik»
    # deb o'qish birinchi kundanoq yolg'on signal bo'lardi.
    bot, tikla = sozla(jim_soat=None, soat=14)
    await d._ogoh_tekshir()
    check(8, "faollik umuman yo'q bo'lsa ogohlantirilmaydi", not bot.xabarlar)
    tikla()

    # ── 9) Kuzatuvchi ro'yxatdan o'tgan ────────────────────────────
    import inspect
    m = kod(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "main.py"))
    check(9, "alert_watcher main.py da ishga tushiriladi",
          "alert_watcher()" in m and "create_task" in m)

    # ── 10) Telegram xatosi butun kuzatuvchini yiqitmaydi ─────────
    bot, tikla = sozla(xato_kun=d.OGOH_XATO_CHEGARA + 5)

    async def yiqiladi(*a, **k):
        raise RuntimeError("chat not found")
    d.bot.send_message = yiqiladi
    try:
        await d._ogoh_tekshir()
        ok = True
    except Exception:
        ok = False
    check(10, "Telegram rad etsa ham tekshiruv yiqilmaydi", ok)
    tikla()

    # ── 11) ⭐ YUBORILMAGAN XABAR UCHUN BAYROQ QO'YILMAYDI ─────────
    # `_ogoh_holat` «bu haqda aytilgan» degani. Yetmagan xabar uchun uni
    # qo'yish — aytilmagan narsani aytilgan deb belgilash, va shart
    # bekor bo'lmaguncha boshqa HECH QACHON urinilmaydi. Ya'ni guruh
    # yiqilgan paytda ogohlantirish BUTUNLAY yo'qolardi.
    bot, tikla = sozla(xato_kun=d.OGOH_XATO_CHEGARA + 5)

    async def yiqiladi(*a, **k):
        raise RuntimeError("Forbidden: bot was kicked from the group chat")
    d.bot.send_message = yiqiladi
    await d._ogoh_tekshir()
    check(11, "yuborish yiqilsa bayroq QO'YILMAYDI",
          d._ogoh_holat.get("xato") is not True)

    # ── 12) Keyingi tekshiruvda QAYTA urinadi ─────────────────────
    urinish = []

    async def sanaydi(*a, **k):
        urinish.append(1)
        raise RuntimeError("Forbidden: bot was kicked from the group chat")
    d.bot.send_message = sanaydi
    await d._ogoh_tekshir()
    await d._ogoh_tekshir()
    check(12, "yiqilgan ogohlantirish keyingi tekshiruvda qayta uriniladi",
          len(urinish) == 2)

    # ── 13) ⭐ GURUH darajasidagi xato banner'ni yoqadi ────────────
    check(13, "guruh xatosi banner holatiga yoziladi",
          HOLAT and HOLAT[-1][0] is False
          and "chiqarib yuborilgan" in (HOLAT[-1][1] or ""))

    # Yetkazilgach bayroq qo'yiladi va banner o'chadi.
    HOLAT.clear()
    # ⚠️ Yangi bot — `d.bot.send_message` yuqorida ustidan yozilgan, ya'ni
    # eski obyektdan asl usulni qaytarib bo'lmaydi. `_ogoh_holat` esa
    # ATAYLAB tozalanmaydi: bayroq hali False, ya'ni bu o'sha qayta
    # urinishning davomi.
    d.bot = SoxtaBot()
    await d._ogoh_tekshir()
    check(14, "yetkazilgach bayroq qo'yiladi va banner o'chadi",
          d._ogoh_holat.get("xato") is True and HOLAT == [(True, None)])
    tikla()

    # ── 15) ⭐ XABARGA XOS xato banner holatiga TEGMAYDI ───────────
    # «matn uzun», «tahlil qilinmadi» keyingi xabarda o'zi tuzaladi.
    # Uni banner'ga chiqarish banner'ni DOIM yonib turadigan qilardi,
    # va doim yonadigan ogohlantirish — o'chirilgan ogohlantirish.
    bot, tikla = sozla(xato_kun=d.OGOH_XATO_CHEGARA + 5)

    async def uzun(*a, **k):
        raise RuntimeError("Bad Request: message is too long")
    d.bot.send_message = uzun
    await d._ogoh_tekshir()
    check(15, "xabarga xos xato banner holatini o'zgartirmaydi", HOLAT == [])
    tikla()

    print()
    print("XATO YO'Q" if not _xato else f"{_xato} TA XATO")
    return 1 if _xato else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
