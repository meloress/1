# -*- coding: utf-8 -*-
"""Telegram Business — AUDIT 2.4, 3.5, 4.2, 4.4, 5.1, 6.2.2, 7.5.

  ⛔️ "rahmat" ga to'liq qoralama (token) — yoki aksincha, "ha" ga qoralama
     yo'q (egasining savoliga javob bo'lishi mumkin);
  ⛔️ kartoteka har xabarda bazaga yoziladi / javob yo'lini kutkazadi;
  ⛔️ osilgan model chat qulfini 180 s ushlaydi;
  ⛔️ vaqt xabari tarixdan oldin — keshlanadigan prefiks 0 ga tushadi.

Tarmoqsiz va bazasiz.

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_biznes_tejash.py
"""
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _manba import kod  # noqa: E402

import handlers.biznes as b              # noqa: E402
from core import config                  # noqa: E402
from db import database                  # noqa: E402


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


# ── 1. Faqat minnatdorchilik (4.2) ───────────────────────────────
ha = ["rahmat", "Katta rahmat!", "raxmat)", "спасибо", "👍", "👍👍", "+", "❤️",
      "rahmat\n👍", "thank you"]
yoq = ["ha", "ok", "mayli", "yaxshi", "rahmat, narxi qancha?", "", "  ",
       "rahmat ertaga kelaman"]
check(1, "faqat rahmat/👍 — qoralamasiz; 'ha', 'ok', savolli gap — qoralama bilan",
      all(b.faqat_rahmatmi(t) for t in ha) and not any(b.faqat_rahmatmi(t) for t in yoq))

manba = kod(os.path.join(ROOT, "handlers", "biznes.py"))
loyiha = manba[manba.index("async def _loyiha("):manba.index("async def _avtojavob(")]
check(2, "rahmat tekshiruvi kvotadan OLDIN (to'lanmaydi) va faqat Yordamchida",
      loyiha.index("faqat_rahmatmi(") < loyiha.index("check_and_consume_quota")
      and "faqat_rahmatmi(" not in manba[manba.index("async def _avtojavob("):])

# ── 3-4. Kartoteka: fonda, o'zgarmagan ism qayta yozilmaydi (2.4, 3.5) ──
yozildi = []


async def korildi(egasi, chat, ism, username):
    yozildi.append((egasi, chat, ism, username))


database.biznes_mijoz_korildi = korildi


class U:
    def __init__(self, ism):
        self.full_name, self.username = ism, "ali"


class Chat:
    id = 55


class Xabar:
    def __init__(self, ism):
        self.from_user, self.chat = U(ism), Chat()


async def kartoteka():
    b._kartoteka.clear()
    b._kartotekaga(1, Xabar("Ali"))
    b._kartotekaga(1, Xabar("Ali"))
    await asyncio.sleep(0.01)
    birinchi = len(yozildi)
    b._kartotekaga(1, Xabar("Ali Valiyev"))
    await asyncio.sleep(0.01)
    return birinchi, len(yozildi)

birinchi, keyin = asyncio.run(kartoteka())
check(3, "kartoteka: bir xil ism ikkinchi marta yozilmaydi, o'zgargani yoziladi",
      birinchi == 1 and keyin == 2)


async def yiqil(*a):
    raise RuntimeError("baza yo'q")


async def xato_keyin():
    database.biznes_mijoz_korildi = yiqil
    b._kartoteka.clear()
    b._kartotekaga(2, Xabar("Vali"))
    await asyncio.sleep(0.01)
    return (2, 55) in b._kartoteka

check(4, "kartoteka yozilmasa RAM belgisi olinadi (keyingi xabar qayta urinadi)",
      asyncio.run(xato_keyin()) is False)

# ── 5. Model muddati (7.5) ───────────────────────────────────────
async def osilgan(*a, **k):
    await asyncio.sleep(5)
    return "kech"

b._model_ichki = osilgan
b.BIZNES_MODEL_TIMEOUT = 0.05


async def muddat():
    try:
        await b._model("salom", 1, -1, 1)
    except TimeoutError:
        return True
    return False

check(5, "osilgan model muddatda uziladi (qulf 180 s ushlanmaydi)", asyncio.run(muddat()))
check(6, "muddat konfiguratsiyada va 60 s dan oshmaydi; debounce DM'nikidan uzun",
      0 < config.BIZNES_MODEL_TIMEOUT <= 60
      and config.BIZNES_MERGE_WAIT > config.TEXT_MERGE_WAIT)

# ── 7. Vaqt xabari tarixdan keyin (5.1) ──────────────────────────
ai = kod(os.path.join(ROOT, "services", "ai.py"))
f = ai[ai.index("async def get_openai_reply("):]
f = f[:f.index("\nasync def ", 1)] if "\nasync def " in f[1:] else f
check(7, "business: vaqt xabari tarixdan KEYIN, yo'riqnomadan oldin",
      f.index("safe_get_chat_history(") < f.index("messages.append(biznes_vaqt)")
      < f.index('"content": biznes_yoriqnoma}'))

# ── 8. biznes_loyiha indekslari (6.2.2) ──────────────────────────
nomlar = {n for n, _ in database._INDEKSLAR}
check(8, "biznes_loyiha: kutayotgan va egasi bo'yicha indeks",
      {"idx_biznes_loyiha_kutmoqda", "idx_biznes_loyiha_egasi"} <= nomlar)

print("\nHammasi o'tdi: 8/8")
