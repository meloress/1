# -*- coding: utf-8 -*-
"""Telegram Business — har so'rov egasi (`owner_id`) bo'yicha filtrlangan.

Qat'iy qoida (AUDIT.md §6.1): xabar, profil, loyiha, namuna bilan
ishlaydigan HAR SQL so'rovi `owner_id` ni aytadi. Bugun id ishonchli
joydan kelsa ham, ertaga yangi chaqiruvchi xom id uzatadi — va begona
egasining yozuviga tegadi. `biznes_loyiha_yakun` shunday edi (S1).

Bu test `db/database.py` ni `ast` bilan o'qiydi: `conn.execute/fetch*`
ning birinchi argumenti — SQL. `biznes_*` jadvaliga tegadigan har DML
so'rovda `owner_id` bo'lishi shart; istisnolar quyida SABABI bilan.

Tarmoqsiz, bazasiz.

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_biznes_owner.py
"""
import ast
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _manba import kod  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


JADVAL = re.compile(r"\bbiznes_(loyiha|chat|mijoz|namuna|profil|ulanish|korilgan)\b")
DML = re.compile(r"^\s*(SELECT|UPDATE|DELETE|INSERT|WITH)\b", re.I)

# (funksiya, SQL boshidagi so'z) -> sabab. Faqat ATAYLAB global so'rovlar.
ISTISNO = {
    ("biznes_keshni_yukla", "SELECT"): "ishga tushishda butun kesh yuklanadi",
    ("biznes_panel_stats", "SELECT"): "admin paneli — hamma egalar soni",
    ("biznes_tozala", "DELETE"): "kunlik saqlash muddati (egasi kiritmasi yo'q)",
}

daraxt = ast.parse(kod(os.path.join(ROOT, "db", "database.py")))
sorovlar = []   # (funksiya, sql)
for fn in ast.walk(daraxt):
    if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        continue
    for node in ast.walk(fn):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("execute", "fetch", "fetchrow", "fetchval")
                and node.args and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            sorovlar.append((fn.name, node.args[0].value))

biznes = [(f, q) for f, q in sorovlar if JADVAL.search(q) and DML.match(q)]
check(1, f"biznes_* ga tegadigan {len(biznes)} ta DML so'rov topildi (parser ishlaydi)",
      len(biznes) >= 25)

buzuq, ishlatilgan = [], set()
for f, q in biznes:
    boshi = DML.match(q).group(1).upper()
    # INSERT — qator shu egaga yoziladi (owner_id ustunda). Qolganlarida
    # owner_id FILTR bo'lishi shart: `owner_id = $N` yoki `= -t.thread_id`.
    # Faqat ustun ro'yxatida turishi (`SELECT owner_id …`) hisoblanmaydi.
    if boshi == "INSERT" and "owner_id" in q:
        continue
    if re.search(r"owner_id\s*=\s*(\$\d|-)", q):
        continue
    if (f, boshi) in ISTISNO:
        ishlatilgan.add((f, boshi))
        continue
    buzuq.append((f, " ".join(q.split())[:90]))
check(2, "har biznes_* so'rovida owner_id bor (istisnolar sababli)", not buzuq)
check(3, "istisno ro'yxatida o'lik yozuv yo'q (ko'chirilgan so'rov unutilmasin)",
      ishlatilgan == set(ISTISNO))

yakun = next(q for f, q in sorovlar if f == "biznes_loyiha_yakun")
check(4, "S1: biznes_loyiha_yakun egasi bo'yicha", "owner_id" in yakun and "WHERE" in yakun)

# ── 5. S3: "barcha mavzular" tozalash begona egalarning tarixiga tegmaydi ──
import asyncio                            # noqa: E402
sys.path.insert(0, ROOT)
import db.history as h                    # noqa: E402

sql_lar = []


class Conn:
    async def execute(self, sql, *a):
        sql_lar.append(sql)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class Pool:
    def acquire(self):
        return Conn()


async def pool_():
    return Pool()

h._pool = pool_
h._cache[(5, 0)] = [1]
h._cache[(5, -7001)] = [2]
asyncio.run(h.clear_history(5, thread_id=None))
check(5, "S3: clear_history(thread_id=None) — faqat thread_id >= 0, business keshi qoladi",
      all("thread_id >= 0" in q for q in sql_lar) and len(sql_lar) == 2
      and (5, 0) not in h._cache and (5, -7001) in h._cache)

print("\nHammasi o'tdi: 5/5")
