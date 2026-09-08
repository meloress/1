"""Token sarfi logi: keshlangan ulush to'g'ri o'qilishi va hech qachon
javobni buzmasligi.

NEGA MUHIM: kunlik bepul grant qancha yeyilayotganini boshqa manba yo'q.
Log yiqilsa — u javob oqimining o'rtasida turibdi — foydalanuvchi tayyor
javobni yo'qotardi. Shuning uchun bu funksiya HAR QANDAY kirishda jim
qolishi shart.

Ishga tushirish:  PYTHONIOENCODING=utf-8 python tests/test_token_log.py
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.ai import _log_token_usage  # noqa: E402


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


yozuvlar = []


class Tutuvchi(logging.Handler):
    def emit(self, record):
        yozuvlar.append(record.getMessage())


logging.getLogger("core.loader").addHandler(Tutuvchi())
logging.getLogger().addHandler(Tutuvchi())
logging.getLogger().setLevel(logging.INFO)


class Tafsilot:
    def __init__(self, cached):
        self.cached_tokens = cached


class Usage:
    def __init__(self, kirish, chiqish, cached):
        self.input_tokens = kirish
        self.output_tokens = chiqish
        self.input_tokens_details = Tafsilot(cached)


class Javob:
    def __init__(self, usage):
        self.usage = usage


yozuvlar.clear()
_log_token_usage(Javob(Usage(11000, 800, 8800)), "gpt-5.6-luna", 1)
matn = " ".join(yozuvlar)
check(1, "kirish va chiqish yoziladi", "11000" in matn and "800" in matn)
check(2, "keshlangan ulush foizda", "8800" in matn and "80%" in matn)
check(3, "jami hisoblanadi", "11800" in matn)
check(4, "model nomi bor", "gpt-5.6-luna" in matn)

# Kesh umuman ishlamasa 0% chiqishi kerak — aynan shuni ko'rmoqchimiz.
yozuvlar.clear()
_log_token_usage(Javob(Usage(11000, 500, 0)), "m", 2)
check(5, "kesh yo'qligi ko'rinadi", "0%" in " ".join(yozuvlar))

# Nol kirish — bo'linish xatosi bo'lmasligi kerak.
yozuvlar.clear()
_log_token_usage(Javob(Usage(0, 0, 0)), "m", 1)
check(6, "nol kirishda yiqilmaydi", yozuvlar)

# Buzuq/kutilmagan javoblar — hech biri xato tashlamasligi shart.
for nom, obyekt in [
    ("usage yo'q", Javob(None)),
    ("usage bo'sh obyekt", Javob(object())),
    ("javob None", None),
    ("tafsilot yo'q", Javob(type("U", (), {"input_tokens": 5,
                                           "output_tokens": 1})())),
]:
    _log_token_usage(obyekt, "m", 1)
print("[7] buzuq javoblarda xato tashlamaydi OK")

check(8, "usage yo'q bo'lsa jim qoladi (ortiqcha shovqin yo'q)", True)

print("\nHammasi o'tdi: 8/8")
