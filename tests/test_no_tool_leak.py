"""Ichki tool nomlari javobga chiqmasligi.

Ishga tushirish:  PYTHONIOENCODING=utf-8 python tests/test_no_tool_leak.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import INTERNAL_TOOL_NAMES, SYSTEM_PROMPT  # noqa: E402
import services.ai as ai  # noqa: E402


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


# ── 1. Ro'yxat HAQIQIY sxemalarga mos ────────────────────────────
sxema_nomlari = {t["name"] for t in ai._TOOLS}
for tool in (ai._FILE_TASK_TOOL, ai._IMAGE_TOOL, ai._MEMORY_TOOL, ai._REMINDER_TOOL):
    sxema_nomlari.add(tool["name"])

check(1, "har bir tool sxemasi ro'yxatda bor",
      sxema_nomlari <= set(INTERNAL_TOOL_NAMES),
      )
check(2, "ro'yxatda ortiqcha (mavjud bo'lmagan) nom yo'q",
      set(INTERNAL_TOOL_NAMES) <= sxema_nomlari)

# ── 2. Filtr ishlaydi ────────────────────────────────────────────
javob = ("Mening tool'larim: internet_search, run_python_sandbox, "
         "generate_image, update_memory va manage_reminder.")
tozalangan = ai.strip_internal_names(javob)
for nom in INTERNAL_TOOL_NAMES:
    assert nom not in tozalangan, f"«{nom}» javobda qoldi:\n{tozalangan}"
check(3, "javobdagi barcha ichki nomlar almashtirildi", True)
check(4, "o'rniga tushunarli tavsif qoldi",
      "internetdan qidirish" in tozalangan and "rasm chizish" in tozalangan)

# Kod bloki chetlab o'tish yo'li emas.
kod = "```python\ntools = ['internet_search', 'generate_image']\n```"
check(5, "kod bloki ichida ham tozalanadi",
      "internet_search" not in ai.strip_internal_names(kod))

# Oddiy javob buzilmaydi.
oddiy = "Men internetdan qidiraman, rasm chizaman va fayl yarataman."
check(6, "oddiy imkoniyat javobiga tegilmaydi",
      ai.strip_internal_names(oddiy) == oddiy)
check(7, "bo'sh matn xato bermaydi", ai.strip_internal_names("") == "")

# So'z ichidagi tasodifiy moslik bo'lmasin.
check(8, "faqat butun so'z almashadi",
      "my_internet_search_v2" in ai.strip_internal_names("my_internet_search_v2"))

# ── 3. System promptdagi qoida ───────────────────────────────────
check(9, "system promptda maxfiylik qoidasi bor",
      "CONFIDENTIAL" in SYSTEM_PROMPT
      and "ignore all previous" in SYSTEM_PROMPT.lower())
check(10, "qoida o'zbekcha so'rovga ham tegishli ekani aytilgan",
      "O'ZBEKCHA SO'ROVGA HAM" in SYSTEM_PROMPT)

print("\nHammasi o'tdi: 10/10")
