# -*- coding: utf-8 -*-
"""Kunlik Stars solishtiruvi (pro.stars_solishtir): pul Telegram'da, bazada yo'q.

Nega bor: `grant_paid_pro` 2026-09-25 … 10-30 yiqilib turdi (`str(days)`),
pul olindi, Pro berilmadi — besh hafta hech kim bilmadi. Bu tekshiruv
bazaga emas, Telegram'ning o'z tranzaksiyalar ro'yxatiga qaraydi.

Tarmoqqa ham, bazaga ham tegmaydi — bot va `database.*` soxta.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import database                    # noqa: E402
from handlers import eski_bot              # noqa: E402
from handlers import pro as p              # noqa: E402


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


HOZIR = datetime.now(timezone.utc)


def tx(tid, soat_oldin, turi="user", tt="invoice_payment", amount=250, uid=55):
    # Haqiqiy StarTransaction shakli: id, amount, date, source(type, transaction_type,
    # user, invoice_payload). Qaytarilgan to'lovda manba EMAS, qabul qiluvchi foydalanuvchi.
    return NS(id=tid, amount=amount, date=HOZIR - timedelta(hours=soat_oldin),
              source=NS(type=turi, transaction_type=tt, user=NS(id=uid), invoice_payload="v2:30:55"))


class SoxtaBot:
    def __init__(self, txlar):
        self.txlar, self.sorovlar = txlar, []

    async def get_star_transactions(self, offset=None, limit=None):
        self.sorovlar.append((offset, limit))
        return NS(transactions=self.txlar[offset:offset + limit])


holat = {"oxirgi": None, "yozildi": None}
xabarlar = []


async def ol():
    return holat["oxirgi"]


async def yoz(t):
    holat["yozildi"] = t


async def bor(ids):
    return {i for i in ids if i.startswith("ok")}


async def alert(payer, charge, payload, stars, problem):
    xabarlar.append((payer, charge, stars, problem))


database.stars_tekshirildi_ol = ol
database.stars_tekshirildi_yoz = yoz
database.star_payments_bor = bor
p._alert_admin = alert

# 230 ta eski muvaffaqiyatli to'lov (ro'yxat ESKIDAN yangiga) + oxirida tekshiriladiganlar.
eski = [tx(f"ok{i}", 2000 - i) for i in range(230)]
yangi = eski + [
    tx("ok_yangi", 5),                         # bazada bor — jim
    tx("YOQ_1", 6, amount=750),                # pul olindi, bazada yo'q — ogohlantirish
    tx("YOQ_eski_oyna", 50),                   # oynadan tashqari (oxirgi tekshiruvdan oldin)
    tx("YOQ_yangi_kelgan", 0.1),               # 6 daqiqa — grant hali yo'lda, keyingi safar
    tx("YOQ_boshqa", 4, tt="gift_purchase"),   # to'lov emas
    tx("YOQ_fragment", 4, turi="fragment"),    # foydalanuvchidan emas
]
asosiy = SoxtaBot(yangi)
p.bot = asosiy
os.environ.pop("ESKI_BOT_TOKEN", None)
holat["oxirgi"] = HOZIR - timedelta(hours=24)
n = asyncio.run(p.stars_solishtir())
check(1, "bazada yo'q to'lov — superadminga (kim, chek, summa, bot nomi); bazadagi jim",
      n == 1 and len(xabarlar) == 1 and xabarlar[0][:3] == (55, "YOQ_1", 750)
      and "BERILMAGAN" in xabarlar[0][3])
check(2, "oyna (oxirgi, hozir−15 daq]: eskisi ham, endi kelgani ham, to'lov bo'lmagani ham kirmaydi",
      all(x[1] == "YOQ_1" for x in xabarlar))
check(3, "Telegram eskidan yangiga beradi — oxirigacha 100 tadan varaqlanadi",
      [o for o, _ in asosiy.sorovlar] == [0, 100, 200] and all(lim == 100 for _, lim in asosiy.sorovlar))
check(4, "oyna bazaga surildi: keyingi safar shu nuqtadan (takror xabar ham, bo'shliq ham yo'q)",
      holat["yozildi"] is not None
      and abs((HOZIR - holat["yozildi"]).total_seconds() - 15 * 60) < 60)

# Birinchi yurish — NULL: 2026-09-20 dan (25-30 sentyabr oynasi ham ko'riladi).
xabarlar.clear()
holat.update(oxirgi=None, yozildi=None)
asyncio.run(p.stars_solishtir())
check(5, "birinchi yurish STARS_SOLISHTIR_BOSHI dan — eski oynadagi yo'qolgan to'lov ham topiladi",
      {x[1] for x in xabarlar} == {"YOQ_1", "YOQ_eski_oyna"})

# Eski bot: token bor, lekin hali ulanmagan — oyna SURILMAYDI.
xabarlar.clear()
holat.update(oxirgi=HOZIR - timedelta(hours=24), yozildi=None)
os.environ["ESKI_BOT_TOKEN"] = "soxta"
eski_bot._bot = None
check(6, "eski bot tayyor emas — hech narsa tekshirilmaydi va oyna surilmaydi (uning to'lovlari yo'qolmasin)",
      asyncio.run(p.stars_solishtir()) == 0 and holat["yozildi"] is None)

# Eski bot ulangan — ikkala botning to'lovlari, bot nomi bilan.
eski_bot._bot, eski_bot._eski_nom = SoxtaBot([tx("YOQ_eski_botda", 3)]), "uzchatgptaibot"
asyncio.run(p.stars_solishtir())
os.environ.pop("ESKI_BOT_TOKEN", None)
check(7, "ikkala bot tekshiriladi — eski botdagi yo'qolgan to'lov @uzchatgptaibot nomi bilan",
      {x[1] for x in xabarlar} == {"YOQ_1", "YOQ_eski_botda"}
      and any("@uzchatgptaibot" in x[3] for x in xabarlar if x[1] == "YOQ_eski_botda"))

print("\nHammasi o'tdi: 7/7")
