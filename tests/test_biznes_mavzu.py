# -*- coding: utf-8 -*-
"""Telegram Business — egasining bot DM'idagi «💼 Biznes» mavzusi.

Mavzular yoqilgan shaxsiy chatda `message_thread_id` siz yuborilgan xabar
HAR SAFAR yangi mavzu ochadi (jonli ko'rilgan, 2026-09-25): har qoralama,
hisobot va ogohlantirish alohida mavzu bo'lib ketardi. Bu test ushlaydi:

  ⛔️ egasiga ketadigan xabar mavzusiz yuborilsa (yangi mavzu);
  ⛔️ ikki xabar bir vaqtda kelsa ikkita "💼 Biznes" ochilsa;
  ⛔️ egasi mavzuni o'chirsa xabarlar yo'qolsa (qayta ochilmasa);
  ⛔️ mavzu nomlash (`nomla_mavzu`) "💼 Biznes" nomini ustidan yozsa.

Tarmoqsiz va bazasiz ishlaydi.

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_biznes_mavzu.py
"""
import asyncio
import os
import re
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _manba import kod  # noqa: E402

import handlers.biznes as b              # noqa: E402
from db import database                  # noqa: E402
from services import ai                  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DM = 7001


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


baza = {}
q = []


class SoxtaBot:
    mavzu_yoq = False          # bot mavzu ocha olmaydi (mavzular o'chiq)
    ochirilgan = set()         # egasi o'chirgan mavzular
    keyingi = 100

    async def create_forum_topic(self, chat_id, name, **kw):
        q.append(("ochildi", chat_id, name))
        await asyncio.sleep(0.01)
        if self.mavzu_yoq:
            raise RuntimeError("Bad Request: the chat is not a forum")
        SoxtaBot.keyingi += 1
        return NS(message_thread_id=SoxtaBot.keyingi)

    async def send_message(self, chat_id, text, message_thread_id=None, **kw):
        if chat_id == 404:
            raise RuntimeError("Bad Request: chat not found")
        if message_thread_id in self.ochirilgan:
            raise RuntimeError("Bad Request: message thread not found")
        q.append(("send", chat_id, message_thread_id, text))
        return NS(chat=NS(id=chat_id), message_id=1)


async def mavzu_ol(owner):
    return baza.get(owner)


async def mavzu_yoz(owner, tid):
    baza[owner] = tid

b.bot = SoxtaBot()
database.biznes_mavzu_ol = mavzu_ol
database.biznes_mavzu_yoz = mavzu_yoz


def yuborilgan():
    return [x for x in q if x[0] == "send"]


def ochilgan():
    return [x for x in q if x[0] == "ochildi"]


# ── 1-2. Birinchi xabar mavzu ochadi — faqat BITTA ──────────────
async def ikkita():
    await asyncio.gather(b._egasiga(DM, "qoralama 1"), b._egasiga(DM, "qoralama 2"))

asyncio.run(ikkita())
tid = baza.get(DM)
check(1, "bir vaqtdagi ikki xabar — BITTA «💼 Biznes» mavzusi",
      len(ochilgan()) == 1 and ochilgan()[0][2] == b.MAVZU_NOMI and tid)
check(2, "ikkala xabar ham shu mavzuga tushdi",
      [x[2] for x in yuborilgan()] == [tid, tid])

# ── 3. Deploy'dan keyin — bazadagisi, yangi mavzu yo'q ───────────
q.clear()
b._mavzu.clear()
asyncio.run(b._egasiga(DM, "hisobot"))
check(3, "RAM tozalansa bazadagi mavzu ishlatiladi, yangisi ochilmaydi",
      not ochilgan() and yuborilgan()[0][2] == tid)

# ── 4. Egasi mavzuni o'chirdi — yangisi ochiladi, xabar yo'qolmaydi ──
q.clear()
SoxtaBot.ochirilgan.add(tid)
ok = asyncio.run(b._egasiga(DM, "ogohlantirish"))
check(4, "o'chirilgan mavzu — yangisi ochilib, xabar o'sha yerga qayta ketdi",
      ok and len(ochilgan()) == 1 and baza[DM] != tid
      and yuborilgan() == [("send", DM, baza[DM], "ogohlantirish")])

# ── 5. Boshqa xato qayta urinilmaydi ─────────────────────────────
q.clear()
ok = asyncio.run(b._egasiga(404, "x"))
check(5, "mavzuga aloqasiz rad (chat not found) — qayta mavzu ochilmaydi",
      ok is False and len(ochilgan()) == 1)   # 404 uchun birinchi mavzu, xolos

# ── 6. Mavzular o'chiq — oddiy chatga, har xabarda urinmaydi ─────
q.clear()
SoxtaBot.mavzu_yoq = True
asyncio.run(b._egasiga(555, "a"))
asyncio.run(b._egasiga(555, "b"))
check(6, "mavzu ochilmasa — mavzusiz yuboriladi, qayta urinish soatiga bir",
      [x[2] for x in yuborilgan()] == [None, None] and len(ochilgan()) == 1)
SoxtaBot.mavzu_yoq = False

# ── 7. Qoralama va «sizni kutmoqda» ham shu yo'ldan ──────────────
q.clear()
asyncio.run(b._loyiha_korsat(DM, 1, "Ali", "narxi?", "80 ming"))
check(7, "qoralama ham «💼 Biznes» mavzusiga",
      yuborilgan() and yuborilgan()[0][2] == baza[DM])

manba = kod(os.path.join(ROOT, "handlers", "biznes.py"))
xom = [m.start() for m in re.finditer(r"bot\.send_message\(", manba)]
dm_yubor = manba[manba.index("async def _dm_yubor("):manba.index("async def _egasiga(")]
tashqarida = [i for i in xom if not (manba.index("async def _dm_yubor(") <= i
                                      < manba.index("async def _egasiga("))]
check(8, "biznes.py: egasiga xom bot.send_message yo'q (faqat mijozga — conn_id bilan)",
      dm_yubor.count("bot.send_message(") == 2
      and all("business_connection_id" in manba[i:i + 250] for i in tashqarida))

# ── 9-10. Mavzu nomlash «💼 Biznes» ga tegmaydi ─────────────────
chaqirildi = []


class SoxtaResponses:
    async def create(self, **kw):
        chaqirildi.append(kw)
        return NS(output_text="Yangi nom", usage=None)


async def biznes_mavzusi_ha(chat_id, thread_id):
    return True

asl = (ai.openai_client, database.biznes_mavzumi)
ai.openai_client = NS(responses=SoxtaResponses())
database.biznes_mavzumi = biznes_mavzusi_ha
asyncio.run(ai.nomla_mavzu(DM, 101, "narxi qancha"))
check(9, "«💼 Biznes» mavzusi nomlanmaydi (model ham chaqirilmaydi)", chaqirildi == [])
ai.openai_client, database.biznes_mavzumi = asl


async def yiqiladi():
    raise RuntimeError("baza yo'q")

asl_pool = (database.pool, database.create_db_pool)
database.pool, database.create_db_pool = None, yiqiladi
check(10, "baza xatosida biznes_mavzumi True — nomlamaslik xavfsiz tomon",
      asyncio.run(database.biznes_mavzumi(DM, 101)) is True)
database.pool, database.create_db_pool = asl_pool

print("\nHammasi o'tdi: 10/10")
