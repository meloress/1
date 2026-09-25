# -*- coding: utf-8 -*-
"""Telegram Business — bilim/uslub RAM keshi va tezlik (AUDIT §2-3).

Jonli o'lchov: bilim + uslubni o'qish bitta avtojavobda 0,63 s (4 so'rov).
Kesh buni yo'qotadi, lekin o'zi yangi jim xavf olib keladi:

  ⛔️ egasi Bilimni yangilaydi, bot esa ESKI narx bilan javob beraveradi —
     yozuvchi funksiya keshni bekor qilishni unutgan;
  ⛔️ `organ()` (80 namuna) standart (25 namuna) keshni ifloslantiradi;
  ⛔️ bilim va uslub yana ketma-ket o'qiladi (parallel emas).

Bazasiz: soxta hovuz so'rovlarni sanaydi.

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_biznes_kesh.py
"""
import ast
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _manba import kod  # noqa: E402

from db import database                  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EGASI = 7001


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


sorovlar = []


class SoxtaConn:
    async def fetchval(self, sql, *a):
        sorovlar.append(sql)
        return "Futbolka 80 000" if "SELECT bilim" in sql else 1

    async def fetchrow(self, sql, *a):
        sorovlar.append(sql)
        if "RETURNING namuna_jami" in sql:
            return {"namuna_jami": 1, "uslub_jami": 0}
        return {"uslub": "qisqa", "uslub_egasi": None, "namuna_jami": 3}

    async def fetch(self, sql, *a):
        sorovlar.append(sql)
        return []

    async def execute(self, sql, *a):
        sorovlar.append(sql)

    def transaction(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class SoxtaPool:
    def acquire(self):
        return SoxtaConn()

database.pool = SoxtaPool()


def ishga(coro):
    return asyncio.run(coro)


# ── 1-3. Bilim ───────────────────────────────────────────────────
database.biznes_keshni_bekor(EGASI)
sorovlar.clear()
ishga(database.biznes_bilim_ol(EGASI))
ishga(database.biznes_bilim_ol(EGASI))
check(1, "bilim ikkinchi marta keshdan (bitta so'rov)", len(sorovlar) == 1)
ishga(database.biznes_bilim_yoz(EGASI, "yangi narx"))
sorovlar.clear()
ishga(database.biznes_bilim_ol(EGASI))
check(2, "bilim yozilgach kesh bekor — keyingi o'qish bazadan", len(sorovlar) == 1)

asl_ttl = database._BIZNES_KESH_TTL
database._BIZNES_KESH_TTL = -1
sorovlar.clear()
ishga(database.biznes_bilim_ol(EGASI))
check(3, "TTL o'tgach — bazadan (unutilgan bekor qilishga sug'urta)", len(sorovlar) == 1)
database._BIZNES_KESH_TTL = asl_ttl

# ── 4-6. Uslub ───────────────────────────────────────────────────
database.biznes_keshni_bekor(EGASI)
sorovlar.clear()
ishga(database.biznes_uslub_ol(EGASI))
n1 = len(sorovlar)
ishga(database.biznes_uslub_ol(EGASI))
check(4, "uslub (3 so'rov) ikkinchi marta keshdan", n1 == 3 and len(sorovlar) == 3)

sorovlar.clear()
ishga(database.biznes_uslub_ol(EGASI, 80))
ishga(database.biznes_uslub_ol(EGASI))
check(5, "organ() ning 80 talik o'qishi keshga tushmaydi va standartni buzmaydi",
      len(sorovlar) == 3)

bekor_qildi = {}
for nom, chaqir in [
        ("namuna_qosh", lambda: database.biznes_namuna_qosh(EGASI, "salom")),
        ("uslub_yoz", lambda: database.biznes_uslub_yoz(EGASI, "yangi", 5)),
        ("uslub_egasi_yoz", lambda: database.biznes_uslub_egasi_yoz(EGASI, "siz de")),
        ("namunalar_ochir", lambda: database.biznes_namunalar_ochir(EGASI)),
        ("loyiha_yakun_tahrir", lambda: database.biznes_loyiha_yakun(1, EGASI, "tahrirlandi", "x"))]:
    ishga(database.biznes_uslub_ol(EGASI))              # keshni to'ldir
    ishga(chaqir())
    bekor_qildi[nom] = EGASI not in database._uslub_kesh
ishga(database.biznes_uslub_ol(EGASI))
ishga(database.biznes_loyiha_yakun(1, EGASI, "yuborildi"))
check(6, "har uslub yozuvchisi keshni bekor qiladi; oddiy «yuborildi» — tegmaydi",
      all(bekor_qildi.values()) and EGASI in database._uslub_kesh)

# ── 7. Tuzilma: yangi yozuvchi bekor qilishni unutmasin ──────────
daraxt = ast.parse(kod(os.path.join(ROOT, "db", "database.py")))
unutgan = []
for fn in daraxt.body:
    if not isinstance(fn, (ast.AsyncFunctionDef, ast.FunctionDef)):
        continue
    sql = " ".join(n.value for n in ast.walk(fn)
                   if isinstance(n, ast.Constant) and isinstance(n.value, str))
    yozadi = re.search(r"(INSERT INTO|UPDATE|DELETE FROM)\s+biznes_(profil|namuna)\b", sql)
    # dm_mavzu — keshlanmagan ustun.
    if yozadi and fn.name != "biznes_mavzu_yoz":
        chaqiradi = any(isinstance(n, ast.Call) and getattr(n.func, "id", "") == "biznes_keshni_bekor"
                        for n in ast.walk(fn))
        if not chaqiradi:
            unutgan.append(fn.name)
check(7, "biznes_profil/biznes_namuna ga yozadigan HAR funksiya keshni bekor qiladi",
      not unutgan)

# ── 8-9. Handler: parallel o'qish va Pro keshi ───────────────────
import handlers.biznes as b                                   # noqa: E402
manba = kod(os.path.join(ROOT, "handlers", "biznes.py"))
check(8, "bilim va uslub parallel o'qiladi (asyncio.gather) — ikkala yo'lda",
      manba.count("asyncio.gather(database.biznes_bilim_ol(egasi),") == 2)

pro_sorov = []


async def soxta_pro(uid):
    pro_sorov.append(uid)
    return True

database.pro_tarifmi = soxta_pro
b._pro_kesh.clear()


async def uch_marta():
    return [await b._pro(EGASI) for _ in range(3)]

check(9, "Pro tekshiruvi 60 s keshda: 3 xabar — 1 so'rov", ishga(uch_marta()) == [True] * 3
      and len(pro_sorov) == 1)

print("\nHammasi o'tdi: 9/9")
