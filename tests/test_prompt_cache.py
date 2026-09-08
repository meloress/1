"""Prompt caching sozlamalari: kesh kaliti ULASHILADIGAN bo'lishi kerak.

NEGA MUHIM: keshlanadigan prefiks = instructions (~6 200 token) + tool
sxemalari (bepulda ~1 600, Pro'da ~6 800). Bu har bir so'rovning katta
qismi. Kesh kaliti foydalanuvchi bo'yicha berilsa, har bir odam o'ziga
alohida kesh "isitib" yurardi va ulashishdan foyda qolmasdi.

Ishga tushirish:  PYTHONIOENCODING=utf-8 python tests/test_prompt_cache.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import config  # noqa: E402


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


free_a = config.build_request_params("salom", is_pro=False)
free_b = config.build_request_params("butunlay boshqa uzun savol", is_pro=False)
pro = config.build_request_params("salom", is_pro=True)

check(1, "kesh kaliti berilgan", free_a.get("prompt_cache_key"))
# ⚠️ ENG MUHIM TEKSHIRUV: xabar matni kalitga TA'SIR QILMASLIGI kerak.
check(2, "kalit foydalanuvchi/xabar bo'yicha o'zgarmaydi",
      free_a["prompt_cache_key"] == free_b["prompt_cache_key"])
# Tarif tool ro'yxatini o'zgartiradi, ya'ni prefiks ham boshqa —
# bitta kalit ostiga qo'shilsa yo'naltirish noto'g'ri bo'lardi.
check(3, "tarif bo'yicha alohida kalit",
      pro["prompt_cache_key"] != free_a["prompt_cache_key"])
check(4, "kalitda foydalanuvchi ma'lumoti yo'q",
      "@" not in free_a["prompt_cache_key"]
      and not any(c.isdigit() for c in free_a["prompt_cache_key"]))

# `24h` saqlash — ataylab o'chiq: yozish narxi qimmatroq va bepul
# grant uni qanday hisoblashi hujjatda yo'q.
check(5, "uzoq saqlash standart holda o'chiq",
      config.PROMPT_CACHE_RETENTION is None
      and "prompt_cache_retention" not in free_a)

# Yoqilsa — parametr haqiqatan uzatilishi kerak.
config.PROMPT_CACHE_RETENTION = "24h"
try:
    check(6, "yoqilsa parametr uzatiladi",
          config.build_request_params("x").get("prompt_cache_retention") == "24h")
finally:
    config.PROMPT_CACHE_RETENTION = None

# Kesh prefiksining o'zi kun bo'yi bir xil bo'lishi shart — aks holda
# kalit qanchalik to'g'ri bo'lmasin, mos kelish bo'lmaydi.
p1 = config.build_system_prompt()
p2 = config.build_system_prompt()
check(7, "tizim prompti chaqiruvdan chaqiruvga o'zgarmaydi", p1 == p2)
check(8, "promptda soat/daqiqa yo'q (kun aniqligi)",
      ":" not in p1.split("\n")[0] or "cutoff" in p1.lower())

print("\nHammasi o'tdi: 8/8")
