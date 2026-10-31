# -*- coding: utf-8 -*-
"""Veb qidiruv (services/ai.multi_source_deep_search): tizim tanlovi va parallellik.

Nega bor (2026-10-31): ddgs «auto» har so'rovda ikkita tizimni TASODIFAN
tanlardi; production'da Brave (429), Mojeek (403/timeout) va DuckDuckGo
(22%) o'lik — natija bo'sh qaytar yoki 5 s kutardi, so'rovlar esa ketma-ket.
Tarmoqqa tegmaydi: DDGS va sahifa yuklash soxta.
"""
import asyncio
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import ai   # noqa: E402


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


chaqiruv, bir_vaqtda = [], {"hozir": 0, "max": 0}
qulf = threading.Lock()
BOSH = {"bo'sh so'rov"}


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
        if query in BOSH and backend != "auto":
            return []
        return [{"title": f"{query} sarlavha", "href": f"https://{query[:3]}.uz/{backend}",
                 "body": "matn"}]


async def sahifa(url):
    return ""


ai.DDGS = SoxtaDDGS
ai.fetch_page_content = sahifa

t0 = time.perf_counter()
matn = asyncio.run(ai.multi_source_deep_search("birinchi", ["ikkinchi", "uchinchi"],
                                               fetch_pages=0))
dt = time.perf_counter() - t0
check(1, "avval faqat ishlaydigan tizimlar (QIDIRUV_BACKEND), «auto» emas",
      chaqiruv and all(b == ai.QIDIRUV_BACKEND for _, b in chaqiruv)
      and "auto" not in ai.QIDIRUV_BACKEND.split(","))
check(2, "3 so'rov PARALLEL (0.3 s dan 3 tasi ≈0.3 s, ketma-ket bo'lsa 0.9 s)",
      bir_vaqtda["max"] == 3 and dt < 0.75)
check(3, "natijalar so'rovlar tartibida (parallellik tartibni buzmaydi)",
      matn.index("«birinchi»") < matn.index("«ikkinchi»") < matn.index("«uchinchi»"))

chaqiruv.clear()
matn = asyncio.run(ai.multi_source_deep_search("bo'sh so'rov", fetch_pages=0))
check(4, "ishlaydigan tizimlar bo'sh qaytsa — bir marta «auto» bilan qayta, natija yo'qolmaydi",
      [b for _, b in chaqiruv] == [ai.QIDIRUV_BACKEND, "auto"] and "/auto" in matn)

print("\nHammasi o'tdi: 4/4")
