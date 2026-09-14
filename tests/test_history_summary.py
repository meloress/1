# -*- coding: utf-8 -*-
"""Eski suhbat O'CHIRILMAYDI, SIQILADI.

NIMA O'ZGARDI: ilgari oynadan (80 ta xabar) chiqqan hamma narsa
`DELETE` bilan yo'q qilinardi. Uzun suhbatning boshi abadiy yo'qolardi
va bot buni foydalanuvchiga aytmasdi ham — u "o'tgan hafta aytgandim-ku"
deganda bot bilmasdi va bilmasligini ham bilmasdi.

Endi eskisi o'chirilishdan OLDIN qisqa xulosaga aylanadi.

⛔️ ENG MUHIM KAFOLAT (4-6 tekshiruvlar): XULOSA CHIQMASA, XABARLAR
O'CHIRILMAYDI. Aks holda tuzatishning o'zi biz tuzatayotgan nosozlikni
takrorlardi — suhbat boshi jimgina yo'qolardi. Shuning uchun tartib
qat'iy: xulosa olinadi -> saqlanadi -> va faqat keyin xom qatorlar
o'chiriladi.

Tarmoqsiz va bazasiz ishlaydi — hammasi soxta.

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_history_summary.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import config  # noqa: E402
import db.history as h  # noqa: E402
import services.ai as ai  # noqa: E402


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


# Testlar `ai.summarize_history_chunk` ni soxta bilan almashtiradi, lekin
# 6-tekshiruv aynan HAQIQIYSINI sinashi kerak — shuning uchun asl nusxa
# almashtirishdan oldin olib qo'yiladi.
_ASL_XULOSA = ai.summarize_history_chunk


# ── Soxta baza ───────────────────────────────────────────────────
class SoxtaConn:
    def __init__(self, db):
        self.db = db

    async def fetchval(self, sql, *a):
        if "COUNT(*)" in sql:
            return len(self.db["rows"])
        if "SELECT summary" in sql:
            return self.db["summary"]
        return None

    async def fetch(self, sql, *a):
        # `_compress_old` oynadan TASHQARIDAGI eng eskilarini so'raydi.
        chiqqan = self.db["rows"][:-h._STORE_LIMIT] if len(
            self.db["rows"]) > h._STORE_LIMIT else []
        return chiqqan[:config.HISTORY_SUMMARY_BATCH]

    async def execute(self, sql, *a):
        self.db["sql"].append(sql.strip().split()[0].upper())
        if sql.strip().upper().startswith("DELETE FROM CHAT_MESSAGES"):
            self.db["ochirildi"] = True
            oxirgi = a[1] if len(a) > 1 else 0
            self.db["rows"] = [r for r in self.db["rows"] if r["id"] > oxirgi]
        elif "INSERT INTO chat_summaries" in sql:
            self.db["summary"] = a[1]

    def transaction(self):
        conn = self

        class T:
            async def __aenter__(self): return conn
            async def __aexit__(self, *a): return False
        return T()


class SoxtaPool:
    def __init__(self, db):
        self.db = db

    def acquire(self):
        db = self.db

        class A:
            async def __aenter__(self): return SoxtaConn(db)
            async def __aexit__(self, *a): return False
        return A()


def yangi_db(n=100):
    return {"rows": [{"id": i, "role": "user", "content": f"xabar {i}"}
                     for i in range(1, n + 1)],
            "summary": None, "sql": [], "ochirildi": False}


def ulash(db):
    async def _p():
        return SoxtaPool(db)
    h._pool = _p


# ── 1-3. Muvaffaqiyatli siqish ───────────────────────────────────
async def _sinov_siqish():
    db = yangi_db(100)
    ulash(db)
    h._summary_cache.clear()
    h._summary_locks.clear()

    async def soxta_xulosa(eski, rows):
        return "Foydalanuvchi BMW M5 haqida so'radi."
    ai.summarize_history_chunk = soxta_xulosa

    await h._compress_old(777)

    check(1, "xulosa saqlandi", db["summary"] == "Foydalanuvchi BMW M5 haqida so'radi.")
    check(2, "xom qatorlar o'chirildi", db["ochirildi"] is True)
    check(3, f"oyna saqlanib qoldi ({len(db['rows'])} qator)",
          len(db["rows"]) == 100 - config.HISTORY_SUMMARY_BATCH)


asyncio.run(_sinov_siqish())


# ── 4-6. ⛔️ XULOSA CHIQMASA — HECH NARSA O'CHMAYDI ───────────────
async def _sinov_yiqilish():
    for nom, natija in (("bo'sh satr", ""), ("None", None)):
        db = yangi_db(100)
        ulash(db)
        h._summary_cache.clear()
        h._summary_locks.clear()

        async def soxta_yiqil(eski, rows, _n=natija):
            return _n
        ai.summarize_history_chunk = soxta_yiqil

        await h._compress_old(777)
        assert db["ochirildi"] is False, f"{nom}: XABARLAR O'CHIRILDI!"
        assert len(db["rows"]) == 100, nom
        assert db["summary"] is None, nom
    check(4, "xulosa chiqmasa xabarlar O'CHIRILMAYDI", True)

    # Model istisno otsa ham — xuddi shunday.
    db = yangi_db(100)
    ulash(db)
    h._summary_cache.clear()
    h._summary_locks.clear()

    async def portla(eski, rows):
        raise RuntimeError("model yo'q")
    ai.summarize_history_chunk = portla
    try:
        await h._compress_old(777)
    except RuntimeError:
        pass
    check(5, "model xatosida ham xabarlar joyida", db["ochirildi"] is False)

    # ⚠️ `summarize_history_chunk` ning O'ZI ham istisno otmasligi kerak —
    # u bo'sh satr qaytarishi shart, aks holda fon vazifasi yiqiladi va
    # yuqoridagi "o'chirmaslik" kafolati ham ishlamay qolardi.
    # HAQIQIY funksiya chaqiriladi (yuqorida u soxta bilan almashtirilgan).
    asl = ai.openai_client.responses.create

    def _portla(**k):
        raise RuntimeError("kvota tugadi")
    ai.openai_client.responses.create = _portla
    try:
        natija = await _ASL_XULOSA("", [{"role": "user", "content": "a"}])
        check(6, "xulosa yozuvchi xatoda BO'SH SATR qaytaradi", natija == "")
    finally:
        ai.openai_client.responses.create = asl


asyncio.run(_sinov_yiqilish())


# ── 7. Bir vaqtda ikki marta siqilmasin ──────────────────────────
async def _sinov_qulf():
    db = yangi_db(100)
    ulash(db)
    h._summary_cache.clear()
    h._summary_locks.clear()
    chaqiruvlar = []

    async def sekin(eski, rows):
        chaqiruvlar.append(1)
        await asyncio.sleep(0.2)
        return "xulosa"
    ai.summarize_history_chunk = sekin

    await asyncio.gather(h._compress_old(777), h._compress_old(777))
    check(7, "qulf takroriy siqishni to'xtatdi", len(chaqiruvlar) == 1)


asyncio.run(_sinov_qulf())


# ── 8-9. Xulosa modelga QANDAY yetadi ────────────────────────────
async def _sinov_xabar():
    h._summary_cache.clear()

    async def soxta_get(chat_id):
        return "Foydalanuvchining ismi Ali, u dasturchi."
    import db.history
    db.history.get_chat_summary = soxta_get

    msg = await ai.safe_history_summary_message(777)
    check(8, "xulosa `developer` xabari sifatida ketadi",
          msg is not None and msg["role"] == "developer")
    # Model uni foydalanuvchining HOZIRGI gapi deb o'qimasligi kerak.
    check(9, "siqilgan va eski ekani aytilgan",
          "siqilgan" in msg["content"] and "iqtibos qilmang" in msg["content"])

    # Xulosa bo'lmasa — ortiqcha xabar yuborilmaydi (token bekorga ketmasin).
    async def bosh(chat_id):
        return ""
    db.history.get_chat_summary = bosh
    check(10, "xulosa yo'q bo'lsa xabar ham yo'q",
          await ai.safe_history_summary_message(777) is None)


asyncio.run(_sinov_xabar())


# ── 11-12. Tartib va /new ────────────────────────────────────────
import inspect  # noqa: E402

_SRC = inspect.getsource(ai.get_openai_reply)
check(11, "xulosa xom tarixdan OLDIN qo'shiladi",
      _SRC.index("safe_history_summary_message") < _SRC.index("safe_get_chat_history"))

# ⚠️ `/new` xulosani ham o'chirishi SHART: aks holda "tarix tozalandi"
# degan xabar yolg'on bo'lardi va bot eski suhbatni ishlatishda davom
# etardi.
_CLEAR = inspect.getsource(h.clear_history)
check(12, "/new xulosani ham o'chiradi",
      "chat_summaries" in _CLEAR and "_summary_cache.pop" in _CLEAR)


# ── 13-15. Model tanlovi va chegaralar ───────────────────────────
from test_free_models import FREE_ALL, FREE_MINI  # noqa: E402

check(13, "xulosa modeli bepul ro'yxatda",
      config.HISTORY_SUMMARY_MODEL in FREE_ALL)
# ⚠️ Bepul kvota IKKITA ayri chelakda: katta modellar ~250k token/kun,
# mini ~2.5M. Xulosa yozish — mexanik ish; uni katta chelakdan yechish
# javoblar uchun qolgan joyni yeb qo'yardi.
check(14, f"va aynan MINI chelakda ({config.HISTORY_SUMMARY_MODEL})",
      config.HISTORY_SUMMARY_MODEL in FREE_MINI)
check(15, "qattiq chegara siqish chegarasidan katta",
      config.HISTORY_HARD_LIMIT >
      h._STORE_LIMIT + config.HISTORY_SUMMARY_BATCH)

print("\nhistory_summary: barcha tekshiruvlar o'tdi (15/15).")
