"""Telegram 429 — yuborish metodi kutib qayta urinadi (`core.loader.FloodKutish`).

Ishga tushirish: PYTHONIOENCODING=utf-8 python tests/test_flood.py

HAQIQIY NOSOZLIK (2026-11-20): bitta chatda 11 ta javob bo'lagi va 2 ta fayl
«Flood control, retry in 12» bilan rad etilib, izsiz yo'qoldi — chaqiruvchilar
429 ni oddiy xato deb ushlardi.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram.exceptions import TelegramRetryAfter  # noqa: E402
from aiogram.methods import EditMessageText, GetUpdates, SendDocument, SendMessage  # noqa: E402
from aiogram.types import BufferedInputFile  # noqa: E402

from core import loader  # noqa: E402


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


kutishlar = []


async def _sleep(s):
    kutishlar.append(s)

loader.asyncio.sleep = _sleep
mw = loader.FloodKutish()


def soxta(rad_soni: int, retry_after: int = 12):
    holat = {"chaqiruv": 0}

    async def make_request(bot_, method):
        holat["chaqiruv"] += 1
        if holat["chaqiruv"] <= rad_soni:
            raise TelegramRetryAfter(method=method, message="Flood control exceeded",
                                     retry_after=retry_after)
        return "yetdi"
    return make_request, holat


async def main():
    xabar = SendMessage(chat_id=1, text="salom")

    mr, h = soxta(1)
    natija = await mw(mr, None, xabar)
    check(1, "sendMessage 429 dan keyin kutib qayta yuboriladi",
          natija == "yetdi" and h["chaqiruv"] == 2 and kutishlar == [12])

    kutishlar.clear()
    mr, h = soxta(2)
    natija = await mw(mr, None, SendDocument(chat_id=1, document=BufferedInputFile(b"x", "a.zip")))
    check(2, "fayl ham — ikki marta 429 bo'lsa ham yetadi",
          natija == "yetdi" and h["chaqiruv"] == 3 and kutishlar == [12, 12])

    for n, nom, metod in ((3, "editMessageText", EditMessageText(chat_id=1, message_id=1, text="x")),
                          (4, "getUpdates", GetUpdates())):
        kutishlar.clear()
        mr, h = soxta(1)
        try:
            await mw(mr, None, metod)
            otdi = False
        except TelegramRetryAfter:
            otdi = True
        check(n, f"{nom} kutilmaydi — 429 darhol chaqiruvchiga", otdi and h["chaqiruv"] == 1 and not kutishlar)

    kutishlar.clear()
    mr, h = soxta(1, retry_after=300)
    try:
        await mw(mr, None, xabar)
        otdi = False
    except TelegramRetryAfter:
        otdi = True
    check(5, "uzoq kutish (300 s) — kutmaydi, xato chaqiruvchiga", otdi and not kutishlar)

    kutishlar.clear()
    mr, h = soxta(10)
    try:
        await mw(mr, None, xabar)
        otdi = False
    except TelegramRetryAfter:
        otdi = True
    check(6, "urinishlar cheklangan — cheksiz aylanmaydi",
          otdi and h["chaqiruv"] == loader.FloodKutish.URINISH + 1)

    check(7, "middleware bot sessiyasiga ulangan",
          any(isinstance(m, loader.FloodKutish) for m in loader.bot.session.middleware._middlewares))

    # Ulanib bo'lmadi — so'rov yetmagan, qayta xavfsiz; timeout — yetgan bo'lishi mumkin.
    from aiohttp import ClientConnectorError
    from aiohttp.client_reqrep import ConnectionKey
    from aiogram.exceptions import TelegramNetworkError

    def tarmoq(asl, rad_soni=1):
        holat = {"chaqiruv": 0}

        async def make_request(bot_, method):
            holat["chaqiruv"] += 1
            if holat["chaqiruv"] <= rad_soni:
                e = TelegramNetworkError(method=method, message="tarmoq")
                e.original = asl
                raise e
            return "yetdi"
        return make_request, holat

    kalit = ConnectionKey("api.telegram.org", 443, True, True, None, None, None)
    ulanmadi = ClientConnectorError(kalit, OSError(101, "Network is unreachable"))
    mr, h = tarmoq(ulanmadi)
    check(8, "ulanib bo'lmasa — qayta yuboriladi",
          await mw(mr, None, xabar) == "yetdi" and h["chaqiruv"] == 2)

    mr, h = tarmoq(TimeoutError())
    try:
        await mw(mr, None, xabar)
        otdi = False
    except TelegramNetworkError:
        otdi = True
    check(9, "timeout — qayta YUBORILMAYDI (yetgan bo'lishi mumkin, takror chiqardi)",
          otdi and h["chaqiruv"] == 1)
    print("\nflood: barcha tekshiruvlar o'tdi (9/9).")


asyncio.run(main())
