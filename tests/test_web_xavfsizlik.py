# -*- coding: utf-8 -*-
"""Panel xavfsizligi: klient IP, tezlik chegarasi, sarlavhalar, cookie.

NEGA BOR: bu qoidalarning HAMMASI jim buziladi. Chegara chetlab
o'tilsa hech narsa yiqilmaydi, sarlavha tushib qolsa panel xuddi
shunday ishlayveradi, cookie o'chmay qolsa «chiqish» tugmasi bosilgan
ko'rinadi. Ya'ni ularni faqat shunday tekshiruv ushlab turadi.

ENG MUHIM TEKSHIRUVLAR:
  1-band — IP `X-Forwarded-For` ning BIRINCHI qiymatidan OLINMAYDI.
    Uni mijozning o'zi yozadi: har so'rovda boshqa qiymat yuborib
    chegarani butunlay bekor qilish mumkin edi.
  3-band — `_urinishlar` cheksiz O'SMAYDI. Soxta XFF bilan uni
    o'stirish xotira orqali DoS edi.
  6-band — `X-Frame-Options` YO'Q. U qo'shilsa panel Telegram Web'da
    (iframe) butunlay ochilmay qoladi.
  8-band — `initData` va cookie HECH QAYERDA logga yozilmaydi.

Offline: baza ham, Telegram ham yo'q.
"""
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiohttp import web as aioweb
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


class SoxtaSorov:
    """`_klient_ip()` ga yetarli minimal so'rov."""

    def __init__(self, xff=None, peer="10.0.0.9"):
        self.headers = {} if xff is None else {"X-Forwarded-For": xff}
        self.remote = peer


async def main():
    # ── 1) ⭐ IP XFF NING BIRINCHI QIYMATIDAN OLINMAYDI ────────────
    # Proksi haqiqiy IP ni OXIRIGA qo'shadi; birinchi qiymat —
    # mijozning o'zi yozgani, ya'ni unga ishonib bo'lmaydi.
    ip = auth._klient_ip(SoxtaSorov("1.2.3.4, 203.0.113.7"))
    check(1, "soxta XFF prefiksi e'tiborga olinmaydi", ip == "203.0.113.7")

    check("1b", "XFF bitta bo'lsa o'sha olinadi",
          auth._klient_ip(SoxtaSorov("203.0.113.7")) == "203.0.113.7")
    check("1c", "XFF umuman yo'q bo'lsa TCP peer olinadi",
          auth._klient_ip(SoxtaSorov(None, peer="10.0.0.9")) == "10.0.0.9")
    check("1d", "bo'sh XFF ham peer'ga tushadi",
          auth._klient_ip(SoxtaSorov("  ,  ", peer="10.0.0.9")) == "10.0.0.9")

    # ── 2) Chegara ishlaydi va kalit bo'yicha AJRATILGAN ───────────
    auth._urinishlar.clear()
    oshdi = [auth.chastota_oshdimi("a", 3) for _ in range(5)]
    check(2, "chegaradan oshganda True qaytadi",
          oshdi == [False, False, False, True, True])
    check("2b", "boshqa kalit o'z hisobida",
          auth.chastota_oshdimi("b", 3) is False)

    # ── 3) ⭐ `_urinishlar` CHEKSIZ O'SMAYDI ───────────────────────
    # Ilgari bu dict hech qachon tozalanmasdi: har soxta XFF qiymati
    # abadiy kalit qoldirardi — ya'ni xotira orqali DoS vektori.
    auth._urinishlar.clear()
    for i in range(auth.CHASTOTA_MAX + 500):
        auth._urinishlar[f"soxta{i}"] = [__import__("time").time()]
    auth._chastota_tozala()
    check(3, "kalitlar soni CHASTOTA_MAX dan oshmaydi",
          len(auth._urinishlar) <= auth.CHASTOTA_MAX)

    # Muddati o'tgani o'z-o'zidan ketadi.
    auth._urinishlar.clear()
    auth._urinishlar["eski"] = [__import__("time").time() - auth.CHASTOTA_OYNA - 5]
    auth._chastota_tozala()
    check("3b", "muddati o'tgan kalit o'chiriladi",
          "eski" not in auth._urinishlar)

    # ── 4) Yozuv chegarasi FAQAT yozish so'rovida ──────────────────
    src = open(os.path.join(ROOT, "web", "auth.py"), encoding="utf-8").read()
    i = src.index("def admin_only(")
    tana = src[i:i + 2500]
    check(4, "chegara GET'ni chetlab o'tadi, yozuvni sanaydi",
          'request.method != "GET"' in tana
          and "YOZUV_RATE_LIMIT" in tana and "429" in tana)
    # ⚠️ Chegara huquq tekshiruvidan KEYIN: admin bo'lmagan odam
    # boshqa adminning hisobini to'ldira olmasin.
    check("4b", "chegara huquq tekshiruvidan KEYIN turadi",
          tana.index("huquq_bormi") < tana.index("YOZUV_RATE_LIMIT"))

    # ── 5) Sarlavhalar HAR javobda ────────────────────────────────
    asl = web_paket.huquq_bormi
    app = web_paket.build_app()
    async with TestClient(TestServer(app)) as c:
        r = await c.get("/")
        h = r.headers
        check(5, "sahifa xavfsizlik sarlavhalari bilan keladi",
              h.get("X-Content-Type-Options") == "nosniff"
              and h.get("Referrer-Policy") == "strict-origin-when-cross-origin"
              and "Content-Security-Policy-Report-Only" in h)

        # 401 ham sarlavhali bo'lsin — xato javob ham javob.
        r = await c.get("/api/overview")
        check("5b", "401 javobda ham sarlavhalar bor",
              r.status == 401 and r.headers.get("X-Content-Type-Options") == "nosniff")

        # ── 6) ⭐ X-Frame-Options YO'Q, frame-ancestors BOR ────────
        # `X-Frame-Options` qo'shilsa panel Telegram Web'da (iframe)
        # umuman ochilmay qoladi — CSP esa domen ro'yxatini oladi.
        csp = r.headers["Content-Security-Policy-Report-Only"]
        check(6, "X-Frame-Options YO'Q (iframe kerak), frame-ancestors bor",
              "X-Frame-Options" not in r.headers
              and "frame-ancestors" in csp
              and "telegram.org" in csp)

        # ⚠️ REPORT-ONLY. Majburlovchi `Content-Security-Policy`
        # sarlavhasi hali YUBORILMAYDI: inline `style=` va Desktop
        # webview'ining xatti-harakati jonli sinovdan o'tmagan.
        check("6b", "CSP hozircha faqat report-only rejimda",
              "Content-Security-Policy" not in r.headers)
        check("6c", "telegram.org skripti va Google Fonts ruxsat etilgan",
              "script-src 'self' https://telegram.org" in csp
              and "https://fonts.gstatic.com" in csp
              and "https://fonts.googleapis.com" in csp)
        check("6d", "buzilish hisoboti yo'naltirilgan",
              "report-uri /csp-report" in csp)

        # ── 7) CSP hisoboti: himoyasiz, lekin chegarali ────────────
        auth._urinishlar.clear()
        r = await c.post("/csp-report", json={
            "csp-report": {"violated-directive": "img-src",
                           "blocked-uri": "https://x.example/a.png",
                           "document-uri": "https://panel/"}})
        check(7, "CSP hisoboti qabul qilinadi (204)", r.status == 204)
        for _ in range(web_paket.CSP_HISOBOT_LIMIT + 2):
            oxirgi = await c.post("/csp-report", json={})
        check("7b", "CSP hisoboti ham chegaralangan", oxirgi.status == 429)

    # ── 8) ⭐ initData va cookie LOGGA TUSHMAYDI ───────────────────
    # aiohttp'ning standart access log formati faqat Referer va
    # User-Agent ni yozadi, ya'ni sarlavhamiz u yerga tushmaydi.
    # Qolgani — bizning `logger.*` chaqiruvlarimiz.
    from aiohttp.web_log import AccessLogger
    check(8, "access log sarlavhalarni yozmaydi",
          "init" not in AccessLogger.LOG_FORMAT.lower()
          and "Cookie" not in AccessLogger.LOG_FORMAT)

    yomon = []
    for fayl in ("web/__init__.py", "web/auth.py", "web/api.py"):
        matn = open(os.path.join(ROOT, fayl), encoding="utf-8").read()
        for m in re.finditer(r"logger\.\w+\((.{0,200}?)\)\s*$", matn, re.M):
            q = m.group(1)
            if re.search(r"\.headers|\.cookies|init_data|initData|INIT_DATA_HEADER"
                         r"|COOKIE_NAME|sessiya_yasa", q):
                yomon.append(f"{fayl}: {q[:70]}")
    check("8b", "logga imzo/cookie chiqaradigan chaqiruv yo'q", not yomon)
    if yomon:
        for y in yomon:
            print("     ", y)

    # ── 9) Cookie o'chirish — QO'YISH bilan bir xil atributlarda ───
    # aiohttp'ning `del_cookie()` si `Secure`/`SameSite` ni
    # yubormaydi; brauzer mos kelmadi deb cookie'ni qoldirib ketardi.
    ini = open(os.path.join(ROOT, "web", "__init__.py"), encoding="utf-8").read()
    chiq = ini[ini.index("async def chiqish("):]
    chiq = chiq[:chiq.index("async def ", 10)]
    # ⚠️ CHAQIRUV qidiriladi, so'z emas: yuqoridagi izohning o'zida
    # «del_cookie()» yozilgan va oddiy `in` tekshiruvi unga ilinardi.
    check(9, "logout cookie'ni bir xil atributlar bilan o'chiradi",
          "javob.del_cookie(" not in chiq and "max_age=0" in chiq
          and "secure=True" in chiq and "httponly=True" in chiq
          and 'samesite="Lax"' in chiq)

    # ── 10) XFF tekshiruvi ATAYLAB o'chiq turadi ───────────────────
    # U IP manzillarni logga yozadi, ya'ni doimiy yoqilgan qolmasin.
    check(10, "XFF tekshiruvi standart holatda o'chiq",
          auth.XFF_TEKSHIR is False and "XFF_TEKSHIR" in ini)

    web_paket.huquq_bormi = asl
    print()
    print("XATO YO'Q" if not _xato else f"{_xato} TA XATO")
    return 1 if _xato else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
