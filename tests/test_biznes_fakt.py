# -*- coding: utf-8 -*-
"""Telegram Business — «💾 Eslab qol», «▶️ Botni qayta yoqish», tanlovdan keyingi pauza.

  ⛔️ egasi tanlovga javob bergach suhbatdoshning keyingi "ok" siga
     "Hozir bandman" ketadi (uzatish pauzasi qolib ketgan);
  ⛔️ eslab qolingan javob Bilimni buzadi: takrorlanadi, chegaradan oshadi,
     karta raqami kiradi, yoki ko'p qatorli bo'lib boshqa qoidaga o'xshaydi;
  ⛔️ oddiy qoralamaga ham «Eslab qol» chiqadi (u bilimdan kelgan — aylanma);
  ⛔️ fakt qoidasi fakt yo'q egalarga ham token yeydi.

Tarmoqsiz va bazasiz.

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_biznes_fakt.py
"""
import asyncio
import os
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import handlers.biznes as b              # noqa: E402
from core.config import BIZNES_BILIM_MAX  # noqa: E402
from db import database                  # noqa: E402

EGASI = 7001


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


# ── 1-4. bilimga_fakt ────────────────────────────────────────────
yangi, xato = b.bilimga_fakt("", "sen chekasanmi?", "yo'q, chekmayman")
check(1, "bo'sh bilim: sarlavha + qator",
      xato is None and yangi == f"{b.FAKT_SARLAVHA}\n- «sen chekasanmi?» → yo'q, chekmayman")
ikki, _ = b.bilimga_fakt("Men Olimjon.", "qayerda ishlaysan", "IT Parkda\n ishlayman")
check(2, "mavjud bilimga qo'shiladi, ko'p qatorli javob bitta qatorga",
      ikki.startswith("Men Olimjon.\n\n" + b.FAKT_SARLAVHA)
      and ikki.endswith("- «qayerda ishlaysan» → IT Parkda ishlayman")
      and b.bilimga_fakt(ikki, "qayerda ishlaysan", "IT Parkda ishlayman") == (ikki, None)
      and ikki.count(b.FAKT_SARLAVHA) == 1
      and b.bilimga_fakt(ikki, "a", "b")[0].count(b.FAKT_SARLAVHA) == 1)
check(3, "chegaradan oshsa — rad (kesilmaydi)",
      b.bilimga_fakt("x" * (BIZNES_BILIM_MAX - 10), "savol", "javob")[1] is not None)
check(4, "karta raqami — rad", b.bilimga_fakt("", "karta?", "8600 1234 5678 9012")[1] is not None)

# ── 5. Prompt qoidasi faqat fakt bo'lsa ──────────────────────────
check(5, "fakt qoidasi faqat sarlavha bor bilimda (qolganlarga 0 token)",
      b._FAKT_QOIDASI in b.mijoz_yoriqnomasi(yangi, avtomat=True)
      and b._FAKT_QOIDASI not in b.mijoz_yoriqnomasi("Men Olimjon.", avtomat=True)
      and b._FAKT_QOIDASI not in b.mijoz_yoriqnomasi(""))

# ── Soxta dunyo ──────────────────────────────────────────────────
q = []
loyihalar = {
    1: dict(id=1, owner_id=EGASI, conn_id="c1", chat_id=55, mijoz_matni="chekasanmi?",
            loyiha="yo'q", variantlar=["yo'q", "ha"], yakuniy=None, holat="kutmoqda"),
    2: dict(id=2, owner_id=EGASI, conn_id="c1", chat_id=56, mijoz_matni="narxi?",
            loyiha="80 000", variantlar=None, yakuniy=None, holat="kutmoqda"),
}
rejim = {"r": "avtomat"}


async def band(lid, owner, holat_="kutmoqda", yangi="yuborilmoqda"):
    r = loyihalar.get(lid)
    if not r or r["owner_id"] != owner or r["holat"] != holat_:
        return None
    r["holat"] = yangi
    return dict(r)


async def yakun(lid, owner, holat_, yakuniy=None):
    loyihalar[lid].update(holat=holat_, yakuniy=yakuniy)


async def ol(lid, owner):
    r = loyihalar.get(lid)
    return dict(r) if r and r["owner_id"] == owner else None


async def pauza(owner, chat, soat, sabab="egasi"):
    q.append(("pauza", chat, soat, sabab))


async def hech(*a, **k):
    return None


bilim = {"t": "Men Olimjon."}


async def bilim_ol(_):
    return bilim["t"]


async def bilim_yoz(_, t):
    bilim["t"] = t


class Bot:
    async def send_message(self, chat_id, text, **kw):
        q.append(("send", chat_id, text))
        return NS(chat=NS(id=chat_id), message_id=1)


database.biznes_loyiha_band = band
database.biznes_loyiha_yakun = yakun
database.biznes_loyiha_ol = ol
database.biznes_pauza = pauza
database.biznes_bilim_ol = bilim_ol
database.biznes_bilim_yoz = bilim_yoz
database.biznes_ulanish_ol = lambda c: {"rejim": rejim["r"], "huquqlar": {}}
b.bot = Bot()
b.safe_update_history = hech
b.track_user_activity = lambda *a, **k: None
b.biznes_uslub.namuna_saqla = hech


def ishga(c):
    return asyncio.run(c)


# ── 6-7. Tanlovga javob: pauza 'egasi' ga ────────────────────────
check(6, "avtomat: tanlov yuborilgach pauza 'egasi' (jim), 'bandman' emas",
      ishga(b.loyihani_yubor(1, EGASI, variant=0)).startswith("✅")
      and ("pauza", 55, b.BIZNES_PAUZA_SOAT, "egasi") in q)
q.clear()
check(7, "oddiy qoralama (tanlov emas) pauzaga tegmaydi",
      ishga(b.loyihani_yubor(2, EGASI)).startswith("✅")
      and not any(x[0] == "pauza" for x in q))

# ── 8-10. «💾 Eslab qol» ─────────────────────────────────────────
kb = ishga(b._fakt_kb(1, EGASI))
check(8, "tanlov javobi — «Eslab qol» tugmasi; oddiy qoralama va begona ega — yo'q",
      kb is not None and kb.inline_keyboard[0][0].callback_data == "bz:fk:1"
      and ishga(b._fakt_kb(2, EGASI)) is None and ishga(b._fakt_kb(1, 999)) is None)
check(9, "saqlash: Bilim oxiriga savol → javob",
      ishga(b._fakt_saqla(1, EGASI)).startswith("✅")
      and bilim["t"].endswith("- «chekasanmi?» → yo'q"))
loyihalar[1]["holat"] = "bekor"
check(10, "yuborilmagan (bekor) javob saqlanmaydi; begona ega — ham",
      not ishga(b._fakt_saqla(1, EGASI)).startswith("✅")
      and not ishga(b._fakt_saqla(1, 999)).startswith("✅"))

# ── 11. «▶️ Botni qayta yoqish» uzatish xabarida ─────────────────
yuborilgan = []


async def dm_yubor(dm, matn, **kw):
    yuborilgan.append(kw.get("reply_markup"))

b._dm_yubor = dm_yubor
xabar = NS(from_user=NS(full_name="Ali", username=None), chat=NS(id=55))
ishga(b._uzatish_xabari(EGASI, xabar, "salom", "xarid"))
tugmalar = [t.callback_data for r in yuborilgan[0].inline_keyboard for t in r]
check(11, "uzatish xabarida «▶️ Botni qayta yoqish» (bz:pz:<chat>)", "bz:pz:55" in tugmalar)

# ── 12. Egasi tanlovga CHATDA o'zi javob berdi ───────────────────
loyihalar[3] = dict(id=3, owner_id=EGASI, conn_id="c1", chat_id=57,
                    mijoz_matni="qayerda ishlaysan?", loyiha="", variantlar=[],
                    yakuniy=None, holat="eskirgan")
yuborilgan.clear()
ishga(b._egasi_tanlovga_javob(EGASI, EGASI, 3, "IT Parkda"))
check(12, "chatdagi javob: tanlov «tahrirlandi», egasiga «Eslab qol» taklifi, saqlanadi",
      loyihalar[3]["holat"] == "tahrirlandi" and loyihalar[3]["yakuniy"] == "IT Parkda"
      and yuborilgan and yuborilgan[0].inline_keyboard[0][0].callback_data == "bz:fk:3"
      and ishga(b._fakt_saqla(3, EGASI)).startswith("✅")
      and bilim["t"].endswith("- «qayerda ishlaysan?» → IT Parkda"))

print("\nHammasi o'tdi: 12/12")
