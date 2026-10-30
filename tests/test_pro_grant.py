"""
To'lov grant'i va tarif uzaytirish SQL'i uchun tekshiruv.
Ishga tushirish: python tests/test_pro_grant.py

ENG QIMMATLI ASSERT — 2-band: takroriy successful_payment update'i kelganda
tarif IKKI MARTA berilmasligi. Telegram bir xil update'ni qayta yuborishi
odatiy hol; himoya charge_id UNIQUE cheklovida (kodda emas), shuning uchun
bu testni sindirmasdan uni olib tashlab bo'lmaydi.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio
from contextlib import asynccontextmanager

from db import database


class FakeConn:
    def __init__(self, insert_result):
        self._insert_result = insert_result
        self.executed = []
        self.fetchrows = []

    async def fetchrow(self, query, *args):
        self.fetchrows.append((query, args))
        return self._insert_result

    async def execute(self, query, *args):
        self.executed.append((query, args))

    @asynccontextmanager
    async def transaction(self):
        yield


class FakePool:
    def __init__(self, insert_result):
        self.conn = FakeConn(insert_result)

    @asynccontextmanager
    async def acquire(self):
        yield self.conn


async def _grant(insert_result):
    database.pool = FakePool(insert_result)
    ok = await database.grant_paid_pro(
        charge_id="stars_abc123", payer_id=111, beneficiary_id=222,
        stars=150, days=30, payload="pro:v1:30:222",
    )
    return ok, database.pool.conn


async def _set_premium(**kwargs):
    database.pool = FakePool(None)
    await database.set_user_premium(777, 30, **kwargs)
    return database.pool.conn.executed


async def main():
    # ── 1) Birinchi yetkazish: tarif beriladi ───────────────────────
    ok, conn = await _grant({"id": 1})
    assert ok is True, "yangi to'lov qabul qilinishi kerak edi"
    user_updates = [q for q, _ in conn.executed if "UPDATE users" in q]
    assert len(user_updates) == 1, (
        f"aynan bitta UPDATE users kutilgan edi, {len(user_updates)} ta bo'ldi"
    )
    # INSERT ... ON CONFLICT DO NOTHING bo'lmasa takrorlanish himoyasi yo'q
    insert_sql = conn.fetchrows[0][0]
    assert "ON CONFLICT (charge_id) DO NOTHING" in insert_sql, (
        "charge_id bo'yicha takrorlanish himoyasi yo'qolgan"
    )

    # ── 2) TAKRORIY yetkazish: hech narsa qilinmaydi ────────────────
    ok, conn = await _grant(None)     # ON CONFLICT -> RETURNING bo'sh
    assert ok is False, "takroriy charge_id rad etilishi kerak edi"
    assert [q for q, _ in conn.executed if "UPDATE users" in q] == [], (
        "KRITIK: takroriy to'lovda tarif QAYTA BERILDI — pul bir marta "
        "olinib, xizmat ikki marta berilmoqda"
    )

    # ── 3) Uzaytirish SQL'idagi uchta ehtiyot chorasi ───────────────
    # Bularning har biri haqiqiy pul yo'qotish holatini yopadi, shuning
    # uchun SQL "soddalashtirilib" ustidan yozishga qaytarilmasin.
    sql = database._EXTEND_PLAN_SQL
    assert "GREATEST" in sql, (
        "GREATEST(..., NOW()) yo'qolgan: muddati o'tgan foydalanuvchining "
        "kunlari o'tmishdagi sanaga qo'shilib, u pul to'lab hech narsa olmaydi"
    )
    assert "premium_until IS NULL THEN NULL" in sql, (
        "muddatsiz tarif himoyasi yo'qolgan: cheksiz obuna 30 kunlikka almashadi"
    )
    assert "WHEN plan_type = 'premium' THEN 'premium'" in sql, (
        "tarif pasayishdan himoya yo'qolgan"
    )

    # ── 4) Admin paneli xatti-harakati MUZLATILGAN ──────────────────
    # set_user_premium(uid, days) kwargs'siz — handlers/admin.py aynan
    # shunday chaqiradi va u USTIDAN YOZISHI kerak, qo'shishi emas.
    executed = await _set_premium()
    assert len(executed) == 1
    admin_sql = executed[0][0]
    assert "NOW() + " in admin_sql, "admin grant'i NOW() dan boshlashi kerak"
    assert "GREATEST" not in admin_sql, (
        "admin paneli xatti-harakati o'zgarib ketdi — u muddatni USTIDAN "
        "yozishi kerak (qo'shmasligi)"
    )

    # ── 5) extend=True esa qo'shadi ─────────────────────────────────
    executed = await _set_premium(plan='pro', extend=True)
    assert "GREATEST" in executed[0][0], "extend=True qo'shish SQL'ini ishlatishi kerak"

    # ── 6) `$3` — int, HAR chaqiruvchida ────────────────────────────
    # 3ba4744 SQL'ni `make_interval(days => $3::int)` qildi, to'rt chaqiruvchi
    # `str(days)` da qoldi: asyncpg DataError — Stars xaridi, promokod, referal
    # Pro bermay yiqilardi. Soxta ulanish turini bilmaydi, shuning uchun manbadan.
    import ast
    from tests._manba import kod
    daraxt = ast.parse(kod(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "db", "database.py")))
    chaqiruvlar = [n for n in ast.walk(daraxt) if isinstance(n, ast.Call) and n.args
                   and isinstance(n.args[0], ast.Name) and n.args[0].id == "_EXTEND_PLAN_SQL"]
    assert len(chaqiruvlar) >= 5, f"chaqiruvlar topilmadi: {len(chaqiruvlar)}"
    yomon = [n.lineno for n in chaqiruvlar if not (
        len(n.args) == 4 and isinstance(n.args[3], ast.Call)
        and getattr(n.args[3].func, "id", None) == "int")]
    assert not yomon, f"_EXTEND_PLAN_SQL ga kun int(...) bo'lib uzatilmagan, qatorlar: {yomon}"

    print("pro_grant: barcha tekshiruvlar o'tdi.")


if __name__ == "__main__":
    asyncio.run(main())
