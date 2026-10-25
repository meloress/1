# -*- coding: utf-8 -*-
"""Bot almashganda (@uzchatgptaibot -> @vexonai) Business sozlamalari yo'qolmaydi.

Jonli shikoyat (2026-10-25): egasi yangi botni ulagan, bot mijozlarga JIM.
Sabab — yangi ulanish yangi `conn_id` bilan keladi, sozlamalar (rejim, ish
vaqti) esa eski `conn_id` da qolgan; yangisi `buyruq` rejimida ochilgan.

Eng o'tkir tekshiruv — 1: yoqilgan ulanish kelganda ko'chirish CHAQIRILADI
va egaga qaytgan yozuv ko'chirilgan rejimni ko'rsatadi.

Oflayn: baza soxta. SQL'ning o'zi lokal Postgres'da sinalgan (pgserver).
"""
import asyncio
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram.types import BusinessBotRights, BusinessConnection, User

from db import database as db
from handlers import biznes as b
from tests._manba import kod

_xato = 0


def check(n, nom, shart):
    global _xato
    if shart:
        print(f"[{n}] {nom} OK")
    else:
        _xato += 1
        print(f"[{n}] {nom} XATO")


def ulanish(yoqilgan=True):
    return BusinessConnection(
        id="yangi", user=User(id=700, is_bot=False, first_name="Ega"), user_chat_id=7000,
        date=datetime.now(), is_enabled=yoqilgan, rights=BusinessBotRights(can_reply=True))


async def asosiy():
    chaqirildi = []
    kesh = {"yangi": {"rejim": "buyruq", "yoqilgan": True}}

    async def yoz(conn_id, *a):
        return dict(kesh[conn_id])

    async def almashdi(owner_id, conn_id):
        chaqirildi.append((owner_id, conn_id))
        kesh[conn_id]["rejim"] = "avtomat"   # eskisidan ko'chdi
        return True

    db.biznes_ulanish_yoz = yoz
    db.biznes_telegram_almashdi = almashdi
    db.biznes_ulanish_ol = lambda k: dict(kesh[k]) if k in kesh else None

    ul = await b._saqla(ulanish(True))
    check(1, "yoqilgan ulanish — sozlama eskisidan ko'chadi va qaytgan yozuvda ko'rinadi",
          chaqirildi == [(700, "yangi")] and ul["rejim"] == "avtomat")

    chaqirildi.clear()
    await b._saqla(ulanish(False))
    check(2, "uzilgan ulanishda ko'chirish chaqirilmaydi", chaqirildi == [])

    async def yiqil(*a):
        raise RuntimeError("baza yo'q")

    db.biznes_telegram_almashdi = yiqil
    kesh["yangi"]["rejim"] = "buyruq"
    ul = await b._saqla(ulanish(True))
    check(3, "ko'chirish yiqilsa ham ulanish yoziladi (egasi xabarsiz qolmaydi)",
          ul is not None and ul["rejim"] == "buyruq")

    s = kod("db/database.py")
    f = s[s.index("async def biznes_telegram_almashdi"):s.index("async def biznes_almashuvni_tuzat")]
    check(4, "Instagram ulanishi eski deb olinmaydi", "NOT LIKE 'ig:%'" in f)
    check(5, "faqat kutayotgan qoralamalar ko'chadi", "holat = 'kutmoqda'" in f)
    check(6, "eski ulanish o'chiriladi va hammasi bitta tranzaksiyada",
          "yoqilgan = FALSE" in f and "conn.transaction()" in f)
    m = kod("main.py")
    check(7, "ishga tushishda tuzatish keshdan KEYIN chaqiriladi",
          m.index("biznes_keshni_yukla()") < m.index("biznes_almashuvni_tuzat()"))


asyncio.run(asosiy())
print(f"\nbiznes_almashuv: {7 - _xato}/7 o'tdi.")
sys.exit(1 if _xato else 0)
