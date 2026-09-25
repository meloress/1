# -*- coding: utf-8 -*-
"""Business o'lchovi (`core/olchov.py`, AUDIT.md 2-bosqich).

O'lchov XULQQA TEGMASLIGI shart — bu test ushlaydigan jim xatolar:

  ⛔️ dekorator istisnoni yutsa yoki o'zgartirsa — oqim boshqacha tugaydi;
  ⛔️ logga xabar matni tushsa — maxfiylik buzilishi (qat'iy qoida);
  ⛔️ o'ralgan handler imzosi buzilsa — aiogram unga keraksiz kwarg
     uzatib, HAR business xabar yiqiladi;
  ⛔️ ichki oqim tokeni tashqisiga qo'shilsa — o'lchov yolg'on.

Tarmoqsiz va bazasiz ishlaydi.

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_olchov.py
"""
import asyncio
import json
import logging
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _manba import kod  # noqa: E402

from core import olchov                  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


qatorlar = []


class Ushla(logging.Handler):
    def emit(self, r):
        qatorlar.append(r.getMessage())

olchov.logger.addHandler(Ushla())
olchov.logger.setLevel(logging.INFO)


def oxirgi():
    return json.loads(qatorlar[-1].split("OLCHOV ", 1)[1])


# ── 1-2. Istisno o'zgarishsiz, natija logda ─────────────────────
class MeningXatom(Exception):
    pass


@olchov.oqim("sinov")
async def yiqiladi():
    olchov.belgi("birinchi")
    raise MeningXatom("ichki")

try:
    asyncio.run(yiqiladi())
    ushlandi = None
except MeningXatom as e:
    ushlandi = e
check(1, "istisno AYNAN o'zi qayta ko'tariladi (yutilmaydi, almashmaydi)",
      isinstance(ushlandi, MeningXatom) and str(ushlandi) == "ichki")
check(2, "istisnoda ham bitta JSON qator, natija = istisno nomi",
      oxirgi()["oqim"] == "sinov" and oxirgi()["natija"] == "MeningXatom"
      and "birinchi" in oxirgi()["bosqichlar"])


# ── 3. Qaytgan qiymat o'zgarmaydi ───────────────────────────────
@olchov.oqim("sinov")
async def qaytaradi(x, *, y):
    return (x, y)

check(3, "qaytgan qiymat va argumentlar o'zgarishsiz",
      asyncio.run(qaytaradi(1, y=2)) == (1, 2))

# ── 4. Matn logga tushmaydi ─────────────────────────────────────
MAXFIY = "Kartam 8600 1234 5678 9012, manzil Chilonzor 5-uy"


@olchov.oqim("sinov")
async def sizdiradi():
    olchov.qosh(matn=MAXFIY, qisqa="ok", kop_qator="a\nb", son=5)

asyncio.run(sizdiradi())
q = oxirgi()
check(4, "uzun/ko'p qatorli satr tashlanadi, qisqa id va son qoladi",
      MAXFIY not in qatorlar[-1] and q["matn"] is None and q["kop_qator"] is None
      and q["qisqa"] == "ok" and q["son"] == 5)

# ── 5. Ichki oqim tokeni tashqisiga qo'shilmaydi ─────────────────
@olchov.oqim("ichki")
async def ichki():
    olchov.token(100, 0, 10, "m")


@olchov.oqim("tashqi")
async def tashqi():
    olchov.token(5, 0, 1, "m")
    await ichki()
    olchov.belgi("keyin")

qatorlar.clear()
asyncio.run(tashqi())
ic, ts = (json.loads(x.split("OLCHOV ", 1)[1]) for x in qatorlar)
check(5, "ichma-ich oqim: har biri o'z tokeni, tashqisi qayta tiklanadi",
      ic["kirish"] == 100 and ts["kirish"] == 5 and ts["llm"] == 1
      and "keyin" in ts["bosqichlar"])

# ── 6. Oqimsiz — hech narsa, xato ham yo'q ──────────────────────
qatorlar.clear()
olchov.belgi("x")
olchov.qosh(a=1)
olchov.token(1, 1, 1)
check(6, "oqimdan tashqarida belgi/qosh/token jim (oddiy DM trafigi)", qatorlar == [])


# ── 7. Korrelyatsiya id'si fon vazifasiga o'tadi ────────────────
@olchov.oqim("fon")
async def fon():
    pass


async def kirish():
    sid = olchov.yangi_sorov()
    await asyncio.create_task(fon())
    return sid

qatorlar.clear()
sid = asyncio.run(kirish())
check(7, "debounce taymeri (create_task) xabar id'sini oladi", oxirgi()["id"] == sid)

# ── 8. aiogram handler imzosi buzilmagan ────────────────────────
from aiogram.dispatcher.event.handler import CallableObject  # noqa: E402
import handlers.biznes as b                                   # noqa: E402

co = CallableObject(b.biznes_xabar)
check(8, "o'ralgan biznes_xabar: aiogram faqat `message` ni ko'radi",
      co.params == {"message"} and not co.varkw and co.awaitable)

# ── 9. Manbada matn o'zgaruvchisi o'lchovga uzatilmaydi ─────────
TAQIQ = {"matn", "text", "content", "loyiha", "javob", "toza", "natija_matni",
         "caption", "prompt", "bilim", "uslub", "yoriq", "arg"}
buzuq = []
for fayl in ("handlers/biznes.py", "handlers/biznes_uslub.py"):
    manba = kod(os.path.join(ROOT, fayl))
    for m in re.finditer(r"olchov\.(qosh|yoz)\(", manba):
        i, chuqur = m.end(), 1
        while chuqur:
            chuqur += {"(": 1, ")": -1}.get(manba[i], 0)
            i += 1
        argl = manba[m.end():i - 1]
        # `kalit=qiymat` ning QIYMAT tomonidagi identifikatorlar
        # (qo'shtirnoqdagi literal — `natija="javob"` — o'zgaruvchi emas).
        for qiymat in re.findall(r"=\s*([^,]+)", argl):
            qiymat = re.sub(r"\"[^\"]*\"|'[^']*'", "", qiymat)
            if set(re.findall(r"\b[a-z_]+\b", qiymat)) & TAQIQ:
                buzuq.append((fayl, argl.strip()[:60]))
check(9, "olchov.qosh/yoz ga matn saqlaydigan o'zgaruvchi berilmagan", not buzuq)

print("\nHammasi o'tdi: 9/9")
