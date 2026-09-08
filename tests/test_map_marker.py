# -*- coding: utf-8 -*-
"""Xarita belgisi: `[xarita:lat,long,zoom]` → `<tg-map/>`.

NEGA ALOHIDA FAYL: xarita — yagona konstruktsiya bo'lib, unda kod
model yozgan MA'LUMOTNI (koordinatani) tekshiradi, shunchaki matnni
o'girmaydi. Va tekshiruv YARIM: chegaradan chiqqan qiymat tutiladi,
noto'g'ri joy esa YO'Q — 41.9/12.5 Rim, 41.3/69.3 Toshkent, ikkalasi
ham "to'g'ri ko'rinadi". Shuning uchun kod chegaraga qat'iy bo'lishi
kerak, aniqlik esa promptning zimmasida.

⚠️ `<tg-map/>` — yopiluvchi teg. `<tg-map></tg-map>` deb yozilsa butun
xabar rad etiladi.

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_map_marker.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.ai import build_rich_markdown, strip_rich_tokens

xatolar = []


def check(n, label, cond):
    if cond:
        print(f"[{n}] {label} OK")
    else:
        print(f"[{n}] {label} XATO")
        xatolar.append(label)


# ── 1-2. TO'G'RI BELGI ────────────────────────────────────────────
out = build_rich_markdown("Toshkent markazi:\n\n[xarita:41.3111,69.2797,14]")
check(1, "belgi <tg-map/> ga o'girildi",
      '<tg-map lat="41.3111" long="69.2797" zoom="14"/>' in out
      and "[xarita" not in out)

check(2, "yopiluvchi teg (</tg-map> YO'Q — xabarni rad ettirardi)",
      "</tg-map>" not in out and out.count("<tg-map") == 1)

# ── 3. ZOOM IXTIYORIY ─────────────────────────────────────────────
check(3, "zoom yozilmasa standart qiymat qo'yiladi",
      'zoom="13"/>' in build_rich_markdown("[xarita:41.3111,69.2797]"))

# ── 4-5. CHEGARADAN TASHQARI QIYMAT ───────────────────────────────
# `[rasm:N]` bilan bir xil tamoyil: noto'g'ri belgi jimgina tashlanadi,
# javob esa hech qanday holatda buzilmaydi.
yomon = build_rich_markdown(
    "Xato: [xarita:91.5,69.2797,14] va [xarita:41.3,269.2,5] "
    "va [xarita:41.3,69.2,99] oxiri.")
check(4, "chegaradan chiqqan koordinata/zoom belgisi o'chiriladi",
      "<tg-map" not in yomon and "[xarita" not in yomon)
check(5, "javob matni saqlanib qoladi", "Xato:" in yomon and "oxiri." in yomon)

# ── 6. KOD BLOKI ──────────────────────────────────────────────────
kod = '```python\nq = "[xarita:41.3,69.2,14]"\n```'
_kod_out = build_rich_markdown(kod)
check(6, "kod bloki ichidagi belgi tegilmadi",
      # Blokning O'ZI <pre><code> ga o'giriladi (Telegram Web'da ```
      # fence "not supported" bo'lardi) — ichidagi belgiga tegilmaydi.
      _kod_out == ('<pre><code class="language-python">'
                   'q = "[xarita:41.3,69.2,14]"</code></pre>'))

# ── 7. MARKDOWN PARSLANMAYDIGAN JOYLAR ────────────────────────────
# Jadval katagi (<td>) va <aside> ichida media blok chizilmaydi —
# u yerda belgi xom matn bo'lib ekranda qolardi.
iqtibos = build_rich_markdown("[iqtibos: Bu yerda [xarita:41.3,69.2,14] | Kimdir]")
check(7, "iqtibos ichida xarita bloki yaratilmaydi", "<tg-map" not in iqtibos)

# ── 8. ODDIY YO'L (draft va zaxira xabar) ─────────────────────────
oddiy = strip_rich_tokens("Joy [xarita:41.3,69.2,14] shu yerda")
check(8, "oddiy xabarda belgi olib tashlanadi",
      "[xarita" not in oddiy and "shu yerda" in oddiy)


print("─" * 55)
if xatolar:
    print(f"❌ {len(xatolar)} ta tekshiruv yiqildi:")
    for x in xatolar:
        print(f"   • {x}")
    sys.exit(1)
print("✅ map_marker: barcha tekshiruvlar o'tdi (8/8).")
