"""System promptdagi xavfsizlik qoidalari joyidami.

Prompt katta matn — bo'lim tahrir paytida jimgina yo'qolib ketishi oson.
Bu tekshiruv aynan shundan qo'riqlaydi (javob sifatini emas, qoidaning
BORLIGINI tekshiradi; sifat jonli sinovda ko'riladi).

Ishga tushirish:  PYTHONIOENCODING=utf-8 python tests/test_safety_prompt.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import SYSTEM_PROMPT  # noqa: E402


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


P = SYSTEM_PROMPT

check(1, "fishing bo'limi mavjud", "PHISHING & SOCIAL ENGINEERING" in P)
check(2, "'trening' niqobi aniq qamrab olingan",
      "security training" in P.lower() and "red team" in P.lower())
check(3, "haqiqiy brend/domen taqiqlangan",
      "real brand" in P and "domain" in P)
check(4, "tayyor, yuborishga shay xabar taqiqlangan",
      "ready-to-send" in P)
check(5, "soxta placeholder va yorliq talab qilinadi",
      "example.test" in P and "SIMULYATSIYA" in P)
check(6, "javob shakli — ANIQLASH (red flag + tekshirish qadamlari)",
      "red flags" in P and "DETECTION" in P)
check(7, "realizmga bosim bo'lsa rad etish qoidasi bor",
      "REALISM" in P)
check(8, "ortiqcha rad etish taqiqlangan (oddiy savol ishlashda davom etadi)",
      "DO NOT OVER-REFUSE" in P and "2FA" in P)

print("\nHammasi o'tdi: 8/8")
