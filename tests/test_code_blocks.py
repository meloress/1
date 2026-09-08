"""Kod bloklari: Telegram Web'da ko'rinadigan <pre> + uzun kod -> fayl.

Ishga tushirish:  PYTHONIOENCODING=utf-8 python tests/test_code_blocks.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.ai import code_fences_to_html, build_rich_markdown  # noqa: E402
from handlers.messages import _extract_long_code, LONG_CODE_LINES  # noqa: E402


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


kod = "```python\nprint('salom')\nx = 1 < 2 & 3\n```"

html = code_fences_to_html(kod)
check(1, "fence -> <pre><code class=language-python>",
      html.startswith('<pre><code class="language-python">') and html.endswith("</code></pre>"))
check(2, "``` qolmaydi (copyable-code turiga aylanmaydi)", "```" not in html)
check(3, "kod matni html_escape qilinadi", "&lt; 2 &amp; 3" in html)

check(4, "tilsiz fence ham o'giriladi",
      code_fences_to_html("```\nabc\n```") == "<pre><code>abc</code></pre>")

check(5, "build_rich_markdown ham <pre> qaytaradi",
      "<pre><code" in build_rich_markdown("Mana kod:\n\n" + kod))

# Kod ichidagi `|` jadval bo'lib qolmasligi kerak (himoya ichida o'giriladi).
jadval_kod = "```py\na | b\n---|---\n1 | 2\n```"
check(6, "kod ichidagi | jadvalga aylanmaydi",
      "<table" not in build_rich_markdown(jadval_kod))

# Uzun kod -> fayl
uzun = "```python\n" + "\n".join(f"x{i} = {i}" for i in range(LONG_CODE_LINES + 5)) + "\n```"
matn, fayllar = _extract_long_code("Kod:\n\n" + uzun)
check(7, "uzun kod matndan chiqariladi", "```" not in matn and "📎" in matn)
check(8, "fayl .py kengaytmasi bilan yasaladi",
      len(fayllar) == 1 and fayllar[0][0] == "kod_1.py" and b"x0 = 0" in fayllar[0][1])

qisqa_matn, qisqa_fayl = _extract_long_code("Kod:\n\n" + kod)
check(9, "qisqa kod tegilmaydi", qisqa_fayl == [] and qisqa_matn.count("```") == 2)

check(10, "noma'lum til -> .txt",
      _extract_long_code("```qwerty\n" + "a\n" * (LONG_CODE_LINES + 2) + "```")[1][0][0]
      == "kod_1.txt")

print("\nHammasi o'tdi: 10/10")
