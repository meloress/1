# -*- coding: utf-8 -*-
"""Takroriy so'rov himoyasi (`web/auth.py::bir_marta`).

NEGA BOR: paneldagi «Sovg'a qilish» tugmasi `set_user_premium(...,
extend=True)` ga boradi, ya'ni kunlarni QO'SHADI. Ikki marta bosilsa
30 kun jimgina 60 ga aylanardi va buni hech narsa ko'rsatmasdi.
Tugmani o'chirish (panel.js) buni EKRANDA to'xtatadi, lekin server
uchun himoya emas: sekin tarmoq, sahifa yangilanishi yoki ikkinchi
ilova oynasi baribir ikkita so'rov yuboradi.

ENG MUHIM TEKSHIRUVLAR:
  2-band — IKKI SO'ROV BIR VAQTDA. Haqiqiy ikki bosishda ikkinchi
    so'rov birinchisi HALI TUGAMASDAN keladi, ya'ni «natijani keyin
    saqlash» o'z-o'zicha hech narsa bermaydi. Qulf bo'lmasa ikkalasi
    ham bajariladi va butun himoya bekor bo'ladi.
  4-band — so'rov qatori (`?tur=`) kalitga KIRADI. Usiz
    `/api/export?tur=users` va `?tur=payments` bitta amal bo'lib
    ko'rinardi.
  5-band — XATO JAVOB KESHLANMAYDI. Aks holda admin sababni tuzatib
    qayta bosganda o'sha eski xatoni ko'rardi.
  7-band — dekorator AYNAN tashqi ta'sirli endpointlarda. Yangi
    endpoint qo'shilganda bu band uni tanlashga majbur qiladi.

Offline: baza ham, Telegram ham yo'q — faqat dekorator sinaladi.
"""
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

import web as web_paket
from web import auth

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_xato = 0


def check(n, nom, shart):
    global _xato
    if shart:
        print(f"[{n}] {nom} OK")
    else:
        _xato += 1
        print(f"[{n}] {nom} XATO")


# ── Soxta ilova: bitta handler, har chaqirilganda sanoqni oshiradi ──
BAJARILDI = []


def yasa(kechikish: float = 0.0, status: int = 200):
    BAJARILDI.clear()
    auth._natijalar.clear()
    auth._qulflar.clear()

    @auth.bir_marta
    async def amal(request: web.Request):
        tana = await request.json()
        if kechikish:
            await asyncio.sleep(kechikish)
        BAJARILDI.append(tana)
        return web.json_response({"soni": len(BAJARILDI)}, status=status)

    async def kim(request):
        # `bir_marta` kalitga `request["user_id"]` ni qo'shadi —
        # odatda uni `admin_only` o'rnatadi.
        request["user_id"] = int(request.headers.get("X-Kim", "1"))
        return await amal(request)

    app = web.Application()
    app.router.add_post("/amal", kim)
    return app


async def main():
    # ── 1) Bir xil so'rov IKKINCHI marta bajarilmaydi ──────────────
    app = yasa()
    async with TestClient(TestServer(app)) as c:
        a = await c.post("/amal", json={"kim": "7", "kun": 30})
        b = await c.post("/amal", json={"kim": "7", "kun": 30})
        check(1, "bir xil so'rov bir marta bajariladi",
              len(BAJARILDI) == 1 and a.status == b.status == 200)
        check("1b", "takrorga BIRINCHI javob qaytadi",
              (await a.json()) == (await b.json()) == {"soni": 1})

    # ── 2) ⭐ IKKI SO'ROV BIR VAQTDA ───────────────────────────────
    # Haqiqiy ikki bosish shunday ko'rinadi: ikkinchisi birinchisi
    # hali ishlayotganda keladi. Qulf bo'lmasa ikkalasi ham o'tardi.
    app = yasa(kechikish=0.15)
    async with TestClient(TestServer(app)) as c:
        a, b = await asyncio.gather(
            c.post("/amal", json={"kim": "7", "kun": 30}),
            c.post("/amal", json={"kim": "7", "kun": 30}))
        check(2, "PARALLEL ikki so'rovdan faqat bittasi bajariladi",
              len(BAJARILDI) == 1)
        check("2b", "ikkalasi ham bir xil javob oladi",
              (await a.json()) == (await b.json()))

    # ── 3) Boshqa tana — boshqa amal ───────────────────────────────
    app = yasa()
    async with TestClient(TestServer(app)) as c:
        await c.post("/amal", json={"kim": "7", "kun": 30})
        await c.post("/amal", json={"kim": "7", "kun": 60})
        await c.post("/amal", json={"kim": "8", "kun": 30})
        check(3, "tana o'zgarsa amal qaytadan bajariladi",
              len(BAJARILDI) == 3)

    # ── 4) ⭐ SO'ROV QATORI KALITGA KIRADI ─────────────────────────
    app = yasa()
    async with TestClient(TestServer(app)) as c:
        await c.post("/amal?tur=users", json={})
        await c.post("/amal?tur=payments", json={})
        check(4, "?tur= boshqa bo'lsa boshqa amal (path_qs)",
              len(BAJARILDI) == 2)

    # ── 5) ⭐ XATO JAVOB KESHLANMAYDI ──────────────────────────────
    app = yasa(status=400)
    async with TestClient(TestServer(app)) as c:
        await c.post("/amal", json={"x": 1})
        await c.post("/amal", json={"x": 1})
        check(5, "xato javob keshlanmaydi — qayta urinish o'tadi",
              len(BAJARILDI) == 2)

    # ── 6) Har adminning kaliti O'ZINIKI ───────────────────────────
    # Ikki admin bir vaqtda bir xil amalni qilsa, bu IKKI amal.
    app = yasa()
    async with TestClient(TestServer(app)) as c:
        await c.post("/amal", json={"kun": 30}, headers={"X-Kim": "1"})
        await c.post("/amal", json={"kun": 30}, headers={"X-Kim": "2"})
        check(6, "boshqa admin — boshqa kalit", len(BAJARILDI) == 2)

    # ── 6b) Muddat o'tsa qaytadan bajariladi ───────────────────────
    app = yasa()
    async with TestClient(TestServer(app)) as c:
        await c.post("/amal", json={"kun": 30})
        for k in list(auth._natijalar):
            v = auth._natijalar[k]
            auth._natijalar[k] = (v[0] - auth.BIR_MARTA_OYNA - 1,) + v[1:]
        await c.post("/amal", json={"kun": 30})
        check("6b", "oyna o'tgach amal qaytadan bajariladi",
              len(BAJARILDI) == 2)

    # ── 7) ⭐ DEKORATOR QAMROVI ────────────────────────────────────
    # Qoida: takrorlansa TASHQI TA'SIR beradigan endpoint himoyalanadi
    # (foydalanuvchiga xabar, hujjat, kun qo'shish). Holatni shunchaki
    # qayta yozadiganiga kerak emas — ikkinchi marta bajarilsa ham
    # natija bir xil.
    api = open(os.path.join(ROOT, "web", "api.py"), encoding="utf-8").read()
    yoz = re.findall(r'app\.router\.add_(?:post|delete)\("[^"]+",\s*(\w+)\)', api)
    assert len(yoz) >= 14, yoz

    # ⛔️ `refund` ATAYLAB istisno: u yerda himoya keshdan KUCHLIROQ va
    # DOIMIY — `refunded_at` ustuni (atomik UPDATE), 409 tekshiruvi va
    # Telegram'ning o'z rad javobi. Kesh faqat 409 ni 200 bilan
    # yashirardi, pul yo'lida esa bu noto'g'ri savdo.
    ISTISNO = {"refund"}

    kutilgan, bor = set(), set()
    for fn in yoz:
        i = api.index(f"async def {fn}(")
        j = api.find("\n@", i)
        tana = api[i:j if j > 0 else len(api)]
        if ("_xabar(" in tana or "_hujjat(" in tana or "extend=True" in tana):
            kutilgan.add(fn)
        # Dekoratorlar to'plami. Izoh qatorlari ham o'tkaziladi —
        # `refund` ustida sababni tushuntiruvchi izoh turibdi.
        # ⚠️ Faqat DEKORATOR qatorlari sanaladi, izohlar emas: `refund`
        # ustidagi izohning o'zida «@bir_marta» so'zi bor va oddiy
        # `in` tekshiruvi uni dekorator deb o'qib yuborardi.
        naqsh = "((?:(?:@" + r"\w+" + "|#)[^" + r"\n" + "]*" + r"\n" + ")+)"
        d = re.search(naqsh + "async def " + fn + r"\(", api)
        if d and any(L.strip() == "@bir_marta" for L in d.group(1).splitlines()):
            bor.add(fn)

    check(7, "dekorator aynan tashqi ta'sirli endpointlarda",
          bor == kutilgan - ISTISNO)
    if bor != kutilgan - ISTISNO:
        print(f"     kutilgan: {sorted(kutilgan - ISTISNO)}")
        print(f"     bor     : {sorted(bor)}")

    # ── 8) Kalitlar cheksiz o'smaydi ──────────────────────────────
    # `web/auth.py::_urinishlar` bir marta shu xatoni qilgan: har yangi
    # IP abadiy kalit qoldirardi.
    auth._natijalar.clear()
    auth._qulflar.clear()
    for i in range(auth.BIR_MARTA_MAX + 50):
        auth._natijalar[f"k{i}"] = (__import__("time").time(), 200, b"{}", "application/json")
    auth._bir_marta_tozala()
    check(8, "kalitlar soni chegaradan oshmaydi",
          len(auth._natijalar) <= auth.BIR_MARTA_MAX)

    print()
    print("XATO YO'Q" if not _xato else f"{_xato} TA XATO")
    return 1 if _xato else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
