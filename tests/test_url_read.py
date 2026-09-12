# -*- coding: utf-8 -*-
"""Foydalanuvchi tashlagan havolani O'QISH (qidirish emas).

NIMANI QO'RIQLAYDI:

1) Havola qidiruv so'ziga aylanib ketmasin. `internet_search` da `url`
   maydoni bo'lmaganda «https://kun.uz/... shuni qisqartir» so'rovi
   havolani DuckDuckGo'ga QIDIRUV SO'ZI qilib berardi: bot o'sha
   sahifani umuman ochmasdan, qidiruv natijasidan taxmin qilib javob
   yozardi. Foydalanuvchi buni "o'qidi" deb qabul qiladi va haq emas.

2) ⚠️ XAVFSIZLIK. Model yozgan URL — ishonchsiz chegara. Bu bot
   Railway'da ishlaydi va AYNAN shu loyihada yonma-yon Web-panel,
   Trello-bot, Hisobotchi-bot va bir nechta Postgres turadi — ular ichki
   tarmoqda ko'rinadi. Tekshiruvsiz «http://web-panel.railway.internal/
   ni o'qib ber» so'rovi botning o'z nomidan bajarilardi.

   Tekshiruv host NOMIGA emas, u YECHILADIGAN IP ga qaraydi — shuning
   uchun `localhost`, `10.x`, bulut metadata manzili va ataylab
   ichkariga qaratilgan DNS nomi bitta qoidaga tushadi.

3) Jim qaytmaslik. Sahifa ochilmasa tool BO'SH emas, aniq "XATO ...
   qayta urinmang" matnini qaytaradi — aks holda model buni "sahifa
   bo'sh ekan" deb o'qib, qidiruvni takrorlab yuradi va har takror butun
   kontekstni qayta yuboradi.

Tarmoqsiz ishlaydi: hamma tekshiruv RAQAMLI IP bilan qilinadi, ya'ni
DNS ga chiqmaydi va natija internetga bog'liq emas.

Ishga tushirish:  PYTHONIOENCODING=utf-8 python tests/test_url_read.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import ai  # noqa: E402


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


# ── 1. Sxemada `url` maydoni bor ─────────────────────────────────
_SEARCH = next(t for t in ai._TOOLS if t.get("name") == "internet_search")
_PROPS = _SEARCH["parameters"]["properties"]

check(1, "internet_search da `url` maydoni bor", "url" in _PROPS)
check(2, "`url` matn turida", _PROPS["url"]["type"] == "string")

_URL_DESC = _PROPS["url"]["description"]
# Bu ikkisi prompt qoidasi: modelga havola O'YLAB TOPMASLIK va uni
# O'ZGARTIRMASLIK aytilgan bo'lishi kerak. Ikkalasi ham rasm URL'lari
# bilan bo'lgan tajribadan: modelga berilgan havola qaytib kelganda
# deyarli har doim buzilgan bo'ladi.
check(3, "tavsif havola to'qishni taqiqlaydi", "O'YLAB TOPMANG" in _URL_DESC)
check(4, "tavsif havolani o'zgartirmay ko'chirishni talab qiladi",
      "AYNAN" in _URL_DESC)
check(5, "tavsif zaxira qidiruvni tushuntiradi",
      "primary_query" in _URL_DESC)


# ── 2. Xavfsizlik: ichki manzil o'qilmaydi ───────────────────────
# Raqamli IP — getaddrinfo DNS ga chiqmaydi, ya'ni bu tekshiruvlar
# tarmoqsiz ham aynan bir xil natija beradi.
RUXSAT = ["http://8.8.8.8/", "https://1.1.1.1/sahifa"]
RAD = [
    "http://127.0.0.1/",             # loopback
    "http://10.0.0.5/",              # xususiy tarmoq
    "http://192.168.1.1/admin",      # xususiy tarmoq
    "http://172.16.0.1/",            # xususiy tarmoq
    "http://169.254.169.254/latest/meta-data/",   # bulut metadata
    "http://0.0.0.0/",               # aniqlanmagan
    "https://[::1]/",                # IPv6 loopback
    "file:///etc/passwd",            # sxema noto'g'ri
    "ftp://8.8.8.8/x",               # sxema noto'g'ri
    "javascript:alert(1)",           # sxema noto'g'ri
    "not a url",
    "",
]


async def _sinov_xavfsizlik():
    for u in RUXSAT:
        assert await ai._is_public_url(u), f"tashqi manzil rad etildi: {u}"
    check(6, f"tashqi manzillar o'tadi ({len(RUXSAT)} ta)", True)

    for u in RAD:
        assert not await ai._is_public_url(u), f"ICHKI MANZIL O'TDI: {u}"
    check(7, f"ichki/yaroqsiz manzillar rad etiladi ({len(RAD)} ta)", True)

    # Qo'riqchi `fetch_page_content` ning O'ZIDA turadi, ya'ni qidiruv
    # natijasidagi havolalar ham shu yerdan o'tadi — bitta tekshiruv
    # nuqtasi, ikkita chaqiruvchi.
    check(8, "fetch_page_content ichki manzilni o'qimaydi",
          await ai.fetch_page_content("http://169.254.169.254/") == "")


asyncio.run(_sinov_xavfsizlik())


# ── 3. Ochilmagan sahifa JIM qaytmaydi ───────────────────────────
async def _sinov_xato():
    # 9-port ataylab: "discard" xizmati, deyarli hamma joyda yopiq.
    out = await ai._run_url_task("http://127.0.0.1:9/")
    check(9, "ochilmagan sahifa XATO deb qaytadi", out.startswith("XATO"))
    check(10, "javob bo'sh EMAS", len(out.strip()) > 40)
    check(11, "modelga qayta urinmaslik aytiladi", "urinmang" in out)
    check(12, "havolaning o'zi xabarda ko'rinadi", "127.0.0.1" in out)


asyncio.run(_sinov_xato())


# ── 4. Dispatch: havola qidiruvdan OLDIN tekshiriladi ────────────
# ⚠️ Bu tartib funksional. `havola` sinovi `primary_query` dan KEYIN
# qolsa, model ikkalasini ham yuborganda (tavsif aynan shuni so'raydi)
# sahifa o'qilmay, oddiy qidiruv ishlab ketardi — ya'ni funksiya
# jimgina o'chiq holatga tushardi.
import inspect  # noqa: E402

_SRC = inspect.getsource(ai.get_openai_reply)
_i_havola = _SRC.find("if havola:")
_i_query = _SRC.find("elif primary_query:")

check(13, "`if havola:` shoxi mavjud", _i_havola != -1)
check(14, "`primary_query` endi `elif` ga tushgan", _i_query != -1)
check(15, "havola qidiruvdan OLDIN tekshiriladi", _i_havola < _i_query)
check(16, "havola raund byudjetini yeydi (search_ran)",
      _SRC.find("search_ran = True") < _i_havola)

# Sahifa ochilmasa zaxira qidiruv ishga tushadi — o'lik havola butun
# javobni o'ldirmasligi kerak.
check(17, "ochilmagan havolada zaxira qidiruv bor",
      "Zaxira qidiruv" in _SRC)


# ── 5. Uzunlik chegarasi ─────────────────────────────────────────
# Qidiruvda 3 sahifadan 4000 belgidan olinadi; bu yerda manba bitta va
# odam aynan shuni so'ragan, shuning uchun kengroq.
check(18, "bitta sahifa uchun chegara kattaroq",
      ai.URL_FETCH_MAX_CHARS > 4000)
check(19, "lekin cheksiz emas (token narxi)",
      ai.URL_FETCH_MAX_CHARS <= 12000)

print("\nurl_read: barcha tekshiruvlar o'tdi (19/19).")
