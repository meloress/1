# -*- coding: utf-8 -*-
"""Telegram Business — uzilgan / Pro'si tugagan egalarning ma'lumoti 3 kundan keyin o'chadi.

  ⛔️ FAOL egasining ma'lumoti o'chadi (tiklab bo'lmaydi) — masalan Pro
     tekshiruvi yiqilganda "Pro yo'q" deb o'qilsa;
  ⛔️ uzilgan egasining yozishmalari bazada cheksiz qoladi;
  ⛔️ bazadan o'chadi, RAM keshida qoladi — bot o'chirilgan yozishmani
     ko'radi va keyingi xabarda uni bazaga QAYTA yozadi;
  ⛔️ boshqa egasining (yoki foydalanuvchining o'z DM) tarixi o'chadi;
  ⛔️ egasining o'z Bilimi (`biznes_profil`) ham o'chib ketadi.

Tarmoqsiz va bazasiz.

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_biznes_tozalash.py
"""
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _manba import kod  # noqa: E402

import handlers.biznes as b              # noqa: E402
import db.history as h                   # noqa: E402
from core import config                  # noqa: E402
from db import database                  # noqa: E402


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


check(1, "muhlat — 3 kun", config.BIZNES_TOZALASH_KUN == 3)

# ── 2-4. Kim tozalanadi ──────────────────────────────────────────
# (egasi, ulangan, pro, muddati_otdimi)
EGALAR = {1: (True, True, True),      # faol — tegilmaydi (muddat bo'lsa ham)
          2: (False, True, False),    # uzilgan, 3 kun o'tmagan
          3: (True, False, True),     # Pro tugagan, 3 kun o'tgan — TOZALANADI
          4: (False, True, True),     # uzilgan, 3 kun o'tgan — TOZALANADI
          5: (True, "xato", True)}    # Pro tekshiruvi yiqildi — TEGILMAYDI
q = []


async def egalar():
    return [(e, v[0]) for e, v in EGALAR.items()]


async def pro(e):
    if EGALAR[e][1] == "xato":
        raise RuntimeError("baza yo'q")
    return EGALAR[e][1]


async def muddati(e, kun):
    q.append(("muddat", e, kun))
    return EGALAR[e][2]


async def bekor(e):
    q.append(("bekor", e))


async def tozala(e):
    q.append(("tozala", e))
    return 7

asl_tozala = database.biznes_egasini_tozala   # 5-7 da haqiqiysi sinaladi
database.biznes_egalar = egalar
database.pro_tarifmi = pro
database.biznes_tozalash_muddati = muddati
database.biznes_tozalash_bekor = bekor
database.biznes_egasini_tozala = tozala

h._cache.update({(55, -3): [1], (56, -3): [1], (55, -1): [1], (3, 0): [1]})
h._summary_cache.update({(55, -3): "x", (55, -1): "y"})
soni = asyncio.run(b.egalarni_tozala())
tozalangan = sorted(x[1] for x in q if x[0] == "tozala")
check(2, "faqat 3 kun o'tgan uzilgan / Pro'siz egalar tozalanadi (3, 4)",
      tozalangan == [3, 4] and soni == 2)
check(3, "faol ega — hisob bekor; Pro tekshiruvi yiqilgan ega — O'CHIRILMAYDI",
      ("bekor", 1) in q and not any(x[1] == 5 for x in q if x[0] in ("tozala", "muddat")))
check(4, "RAM keshi: faqat tozalangan egasining business suhbatlari; boshqa ega va DM qoladi",
      (55, -3) not in h._cache and (56, -3) not in h._cache and (55, -3) not in h._summary_cache
      and (55, -1) in h._cache and (3, 0) in h._cache and (55, -1) in h._summary_cache)

# ── 5-7. SQL: nimani o'chiradi, nimaga tegmaydi ──────────────────
sql = []


class Conn:
    async def fetchval(self, s, *a):
        sql.append((s, a))
        return 12

    async def execute(self, s, *a):
        sql.append((s, a))

    def transaction(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class Pool:
    def acquire(self):
        return Conn()

database.pool = Pool()
database.biznes_keshni_bekor = lambda e: sql.append(("kesh", e))
n = asyncio.run(asl_tozala(7001))
matnlar = [" ".join(x[0].split()) for x in sql if isinstance(x[0], str)]
check(5, "yozishma va xulosa: faqat shu egasining business suhbati (thread = -owner, < 0)",
      n == 12
      and any("DELETE FROM chat_messages WHERE thread_id = $1 AND thread_id < 0" in m for m in matnlar)
      and any(m.startswith("DELETE FROM chat_summaries WHERE thread_id = $1 AND thread_id < 0")
              for m in matnlar)
      and all(x[1] == (-7001,) for x in sql if "thread_id" in str(x[0])))
check(6, "qoralama, kartoteka, chat sozlamasi, dublikat izi, namuna — owner_id bo'yicha; kesh bekor",
      all(f"DELETE FROM {j} WHERE owner_id = $1" in matnlar for j in
          ("biznes_loyiha", "biznes_mijoz", "biznes_chat", "biznes_korilgan", "biznes_namuna"))
      and all(x[1] == (7001,) for x in sql if "owner_id" in str(x[0]))
      and ("kesh", 7001) in sql)
check(7, "egasining Bilimi (biznes_profil) va ulanishi O'CHMAYDI",
      not any("biznes_profil" in m or "biznes_ulanish" in m for m in matnlar))

# ── 8. Soatiga bir chaqiriladi ───────────────────────────────────
bz = kod(os.path.join(ROOT, "handlers", "biznes.py"))
w = bz[bz.index("async def biznes_hisobot_watcher("):bz.index("async def egalarni_tozala(")]
check(8, "hisobot kuzatuvchisi soatiga bir marta egalarni_tozala() ni chaqiradi",
      "await egalarni_tozala()" in w and ">= 3600" in w)

# ── 9. Faol egada ham: 90 kundan eski yozishma o'chadi, DM'ga tegmaydi ──
sql.clear()
asyncio.run(database.biznes_tozala())
matnlar = [" ".join(x[0].split()) for x in sql if isinstance(x[0], str)]
eski = [(m, x[1]) for m, x in zip(matnlar, sql) if "chat_messages" in m or "chat_summaries" in m]
check(9, "kunlik: 90 kundan eski business yozishma + xulosa o'chadi, faqat thread_id < 0",
      config.BIZNES_SAQLASH_KUN == 90 and len(eski) == 2
      and all(m.startswith("DELETE FROM chat_") and "WHERE thread_id < 0 AND" in m
              and a == (90,) for m, a in eski))

print("\nHammasi o'tdi: 9/9")
