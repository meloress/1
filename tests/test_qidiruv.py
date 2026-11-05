# -*- coding: utf-8 -*-
"""Veb qidiruv (services/ai.multi_source_deep_search): tizim tanlovi va parallellik.

Nega bor (2026-10-31): ddgs «auto» har so'rovda ikkita tizimni TASODIFAN
tanlardi; production'da Brave (429), Mojeek (403/timeout) va DuckDuckGo
(22%) o'lik — natija bo'sh qaytar yoki 5 s kutardi, so'rovlar esa ketma-ket.

2026-11-05: `bing` ddgs matn qidiruvida YO'Q edi (134 ta «backends do not
exist») — qidiruv jimgina ikki tizimda ishlab yurdi. 1-band endi ddgs'ning
O'Z ro'yxatiga qarshi tekshiradi. Bo'sh natijada endi «auto» emas:
`site:` siz qayta, zaxira (wikipedia) — faqat tizimlar YIQILGANDA.

Tarmoqqa tegmaydi: DDGS va sahifa yuklash soxta.
"""
import asyncio
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ddgs.engines import ENGINES   # noqa: E402

from services import ai   # noqa: E402

_n = 0


def check(nom, shart):
    global _n
    _n += 1
    assert shart, f"[{_n}] {nom} — YIQILDI"
    print(f"[{_n}] {nom} OK")


chaqiruv, bir_vaqtda = [], {"hozir": 0, "max": 0}
qulf = threading.Lock()
BOSH = {"bo'sh so'rov", "x site:imdb.com"}   # tizimlar «No results» deydi
YIQILGAN = {"bloklangan"}                     # tizimlar ulanmaydi


class SoxtaDDGS:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def text(self, query, max_results=None, backend=None):
        with qulf:
            chaqiruv.append((query, backend))
            bir_vaqtda["hozir"] += 1
            bir_vaqtda["max"] = max(bir_vaqtda["max"], bir_vaqtda["hozir"])
        time.sleep(0.3)
        with qulf:
            bir_vaqtda["hozir"] -= 1
        # Haqiqiy ddgs kabi: bo'sh natijada ham ISTISNO.
        if query in BOSH:
            raise Exception("No results found.")
        if query in YIQILGAN and backend == ai.QIDIRUV_BACKEND:
            raise Exception("ConnectError: error sending request")
        return [{"title": f"{query} sarlavha", "href": f"https://{query[:3]}.uz/{backend}",
                 "body": "matn"}]


async def sahifa(url):
    return ""


ai.DDGS = SoxtaDDGS
ai.fetch_page_content = sahifa

# 1 — ddgs'ning O'Z ro'yxati: yo'q tizim jimgina tushib qolmasin
check("har tizim ddgs matn ro'yxatida bor (bing yo'q), «auto» yo'q",
      all(b in ENGINES["text"] for b in ai.QIDIRUV_BACKEND.split(","))
      and ai.QIDIRUV_ZAXIRA in ENGINES["text"]
      and "auto" not in ai.QIDIRUV_BACKEND and "bing" not in ai.QIDIRUV_BACKEND)

t0 = time.perf_counter()
matn = asyncio.run(ai.multi_source_deep_search("birinchi", ["ikkinchi", "uchinchi"],
                                               fetch_pages=0))
dt = time.perf_counter() - t0
check("avval faqat ishlaydigan tizimlar (QIDIRUV_BACKEND)",
      chaqiruv and all(b == ai.QIDIRUV_BACKEND for _, b in chaqiruv))
check("3 so'rov PARALLEL (0.3 s dan 3 tasi ≈0.3 s, ketma-ket bo'lsa 0.9 s)",
      bir_vaqtda["max"] == 3 and dt < 0.75)
check("natijalar so'rovlar tartibida (parallellik tartibni buzmaydi)",
      matn.index("«birinchi»") < matn.index("«ikkinchi»") < matn.index("«uchinchi»"))

chaqiruv.clear()
matn = asyncio.run(ai.multi_source_deep_search("bo'sh so'rov", fetch_pages=0))
check("natija yo'q — bir marta qayta (tasodifiy bo'shlik), zaxiraga O'TILMAYDI, «topilmadi»",
      chaqiruv == [("bo'sh so'rov", ai.QIDIRUV_BACKEND)] * 2 and "topilmadi" in matn)

chaqiruv.clear()
BOSH.add("tasodifiy")
_asl_text = SoxtaDDGS.text


def _bir_marta_bosh(self, query, max_results=None, backend=None):
    if query == "tasodifiy" and len([c for c in chaqiruv if c[0] == "tasodifiy"]) >= 1:
        BOSH.discard("tasodifiy")
    return _asl_text(self, query, max_results, backend)


SoxtaDDGS.text = _bir_marta_bosh
matn = asyncio.run(ai.multi_source_deep_search("tasodifiy", fetch_pages=0))
SoxtaDDGS.text = _asl_text
check("birinchisi tasodifan bo'sh, ikkinchisi natija — javob yo'qolmaydi",
      len(chaqiruv) == 2 and "tasodifiy sarlavha" in matn)

chaqiruv.clear()
matn = asyncio.run(ai.multi_source_deep_search("x site:imdb.com", fetch_pages=0))
check("`site:` bilan bo'sh — cheklovsiz qayta, natija keladi",
      chaqiruv == [("x site:imdb.com", ai.QIDIRUV_BACKEND), ("x", ai.QIDIRUV_BACKEND)]
      and "«x site:imdb.com»" in matn and "x sarlavha" in matn)

chaqiruv.clear()
matn = asyncio.run(ai.multi_source_deep_search("bloklangan", fetch_pages=0))
check("tizimlar YIQILGAN — zaxira (wikipedia), natija yo'qolmaydi",
      chaqiruv == [("bloklangan", ai.QIDIRUV_BACKEND)] * 2
      + [("bloklangan", ai.QIDIRUV_ZAXIRA)]
      and f"/{ai.QIDIRUV_ZAXIRA}" in matn)

# Jonli logdagi haqiqiy so'rovlar
S = ai.site_siz
check("site_siz: logdagi so'rovlar to'g'ri tozalanadi",
      S("AI news October 30 2026 site:theverge.com OR site:arstechnica.com OR "
        "site:venturebeat.com") == "AI news October 30 2026"
      and S("site:help.krafton.com PUBG account recovery") == "PUBG account recovery"
      and S("Toshkent -site:pinterest.com ob-havo") == "Toshkent ob-havo"
      and S("site:imdb.com") == "" and S("oddiy so'rov") == "oddiy so'rov"
      and S("Website design OR site:x.uz") == "Website design")

print(f"\nHammasi o'tdi: {_n}/{_n}")
