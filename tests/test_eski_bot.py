# -*- coding: utf-8 -*-
"""Eski bot (@uzchatgptaibot) — faqat @vexonai ga yo'naltiradi.

Eng o'tkir tekshiruv — 2: Business mijoziga HECH NARSA ketmaydi. Mijoz
egasi bilan gaplashyapman deb o'ylaydi; «bot to'xtatildi» xabari egasining
obro'sini to'kardi va buni hech narsa log qilmasdi.

Offline: Telegram soxta sessiya, baza umuman chaqirilmaydi.
"""
import asyncio
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import (
    AnswerCallbackQuery, AnswerPreCheckoutQuery, GetBusinessConnection,
    SendMessage, SendPhoto,
)
from aiogram.types import BusinessBotRights, BusinessConnection, Chat, Message, PhotoSize, Update, User

from handlers import eski_bot as eb
from tests._manba import kod

_xato = 0


def check(n, nom, shart):
    global _xato
    if shart:
        print(f"[{n}] {nom} OK")
    else:
        _xato += 1
        print(f"[{n}] {nom} XATO")


EGASI, EGASI_CHAT, MIJOZ = 700, 7000, 900


class Sessiya(BaseSession):
    """Har chaqiruvni yozib oladi; rasmni xohlasa rad etadi."""

    def __init__(self, rasm_rad=False):
        super().__init__()
        self.chaqiruvlar = []
        self.rasm_rad = rasm_rad

    async def make_request(self, bot, method, timeout=None):
        self.chaqiruvlar.append(method)
        chat = Chat(id=getattr(method, "chat_id", 0) or 0, type="private")
        if isinstance(method, SendPhoto):
            if self.rasm_rad:
                raise RuntimeError("rasm o'tmadi")
            return Message(message_id=1, date=datetime.now(), chat=chat,
                           photo=[PhotoSize(file_id="F1", file_unique_id="u", width=1, height=1)])
        if isinstance(method, SendMessage):
            return Message(message_id=2, date=datetime.now(), chat=chat, text=method.text)
        if isinstance(method, GetBusinessConnection):
            return BusinessConnection(
                id="c1", user=User(id=EGASI, is_bot=False, first_name="Ega"),
                user_chat_id=EGASI_CHAT, date=datetime.now(), is_enabled=True,
                rights=BusinessBotRights(can_reply=True))
        return True

    async def close(self):
        pass

    async def stream_content(self, *a, **k):
        yield b""


def _tozala():
    eb._oxirgi.clear()
    eb._tozalangan.clear()
    eb._egasiga_aytilgan.clear()
    eb._logo_id = None


def yuborilgan(s, tur):
    return [m for m in s.chaqiruvlar if isinstance(m, tur)]


def xabar_update(uid, n=1, **qo_shimcha):
    return Update(update_id=n, message=Message(
        message_id=n, date=datetime.now(), chat=Chat(id=uid, type="private"),
        from_user=User(id=uid, is_bot=False, first_name="U"), text="salom", **qo_shimcha))


async def asosiy():
    dp = eb._dispatcher()

    # 1. Oddiy xabar — logo + matn + @vexonai tugmasi, bitta marta
    _tozala()
    s = Sessiya()
    bot = Bot("1:a", session=s)
    await dp.feed_update(bot, xabar_update(MIJOZ, 1))
    await dp.feed_update(bot, xabar_update(MIJOZ, 2))   # 10 soniya ichida — jim
    rasmlar = yuborilgan(s, SendPhoto)
    check(1, "xabarga logo + yo'naltirish, takroriga jim",
          len(rasmlar) == 1 and rasmlar[0].chat_id == MIJOZ
          and "vexonai" in rasmlar[0].caption
          and rasmlar[0].reply_markup.inline_keyboard[0][0].url == "https://t.me/vexonai")

    # 2. Business: mijozga HECH NARSA, egasiga bir marta
    _tozala()
    s = Sessiya()
    bot = Bot("1:a", session=s)
    for n in (10, 11, 12):
        await dp.feed_update(bot, Update(update_id=n, business_message=Message(
            message_id=n, date=datetime.now(), chat=Chat(id=MIJOZ, type="private"),
            from_user=User(id=MIJOZ, is_bot=False, first_name="Mijoz"), text="narxi?",
            business_connection_id="c1")))
    manzillar = [m.chat_id for m in s.chaqiruvlar if isinstance(m, (SendMessage, SendPhoto))]
    check(2, "Business mijoziga hech narsa ketmaydi, egasiga bitta ogohlantirish",
          MIJOZ not in manzillar and manzillar == [EGASI_CHAT])

    # 3. To'lov rad etiladi
    _tozala()
    s = Sessiya()
    bot = Bot("1:a", session=s)
    await dp.feed_update(bot, Update.model_validate({"update_id": 20, "pre_checkout_query": {
        "id": "q", "from": {"id": MIJOZ, "is_bot": False, "first_name": "U"},
        "currency": "XTR", "total_amount": 499, "invoice_payload": "pro"}}))
    javob = yuborilgan(s, AnswerPreCheckoutQuery)
    check(3, "eski botda to'lov rad etiladi", len(javob) == 1 and javob[0].ok is False)

    # 4. Rasm o'tmasa ham matn yetib boradi
    _tozala()
    s = Sessiya(rasm_rad=True)
    bot = Bot("1:a", session=s)
    await dp.feed_update(bot, xabar_update(MIJOZ, 30))
    matnlar = yuborilgan(s, SendMessage)
    check(4, "rasm rad etilsa — matnli zaxira", len(matnlar) == 1 and "vexonai" in matnlar[0].text)

    # 5. Tugma bosilsa — alert + yo'naltirish
    _tozala()
    s = Sessiya()
    bot = Bot("1:a", session=s)
    await dp.feed_update(bot, Update.model_validate({"update_id": 40, "callback_query": {
        "id": "cb", "chat_instance": "x", "data": "pro_buy",
        "from": {"id": MIJOZ, "is_bot": False, "first_name": "U"}}}))
    check(5, "eski tugma bosilsa — alert va yo'naltirish",
          len(yuborilgan(s, AnswerCallbackQuery)) == 1 and len(yuborilgan(s, SendPhoto)) == 1)

    # 6. Guruhdagi oddiy xabarga javob yo'q (guruhni spam qilmaslik)
    _tozala()
    s = Sessiya()
    bot = Bot("1:a", session=s)
    await dp.feed_update(bot, Update(update_id=50, message=Message(
        message_id=50, date=datetime.now(), chat=Chat(id=-100, type="supergroup"),
        from_user=User(id=MIJOZ, is_bot=False, first_name="U"), text="salom")))
    check(6, "guruhdagi oddiy xabarga javob yo'q",
          not yuborilgan(s, SendPhoto) and not yuborilgan(s, SendMessage))

    # 7. main.py: bir xil token bilan eski bot ishga tushirilmaydi
    m = kod("main.py")
    check(7, "main.py: ESKI_BOT_TOKEN != BOT_TOKEN sharti",
          "eski_token != config.BOT_TOKEN" in m and "eski_bot.ishga_tushir" in m)

    # 8. Eski bot bazaga tegmaydi
    e = kod("handlers/eski_bot.py")
    check(8, "eski bot bazani import qilmaydi", "database" not in e and "db." not in e)


asyncio.run(asosiy())
print(f"\neski_bot: {8 - _xato}/8 o'tdi.")
sys.exit(1 if _xato else 0)
