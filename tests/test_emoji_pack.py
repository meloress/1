"""AI javobidagi emojilarni animatsiyali paketdan almashtirish.

NEGA PAKET NOMI BILAN: ilgari moslik QO'LDA yozilgan edi va Telegram'dan
tekshirganda oltitadan BESHTASI boshqa emojiga ishora qilardi —
model "🤖" deb yozsa, o'quvchi 🌟 ko'rardi (🧠→🙂, 📄→📝, ⏰→📆, 🧹→🗑).
Paketdagi har bir stiker o'zi qaysi emojiga tegishli ekanini aytadi,
ya'ni moslikni Telegram tuzadi va bunday xato bo'lmaydi.

⚠️ Bu FAQAT model erkin yozgan emojilarga tegishli. Tugma va tizim
xabarlaridagi qo'lda qo'yilgan CUSTOM_EMOJI ID'lariga tegilmaydi.

Ishga tushirish:  PYTHONIOENCODING=utf-8 python tests/test_emoji_pack.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import config  # noqa: E402
from services import ai  # noqa: E402


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


asl = dict(ai._EMOJI_IDS)

# ── 1. Moslikni almashtirish uchta jadvalni ham yangilaydi ───────
# Biri eskirib qolsa, xabar rad etilgandan keyin ekranda xom
# `![ ](tg://emoji?id=...)` matni qolardi.
soni = ai.apply_emoji_pack({"🔥": "111", "🚀": "222", "✍️": "333"})
check(1, "moslik o'lchami to'g'ri", soni == 3)
check(2, "qidiruv jadvali yangilandi", ai._EMOJI_IDS.get("🔥") == "111")
check(3, "teskari jadval yangilandi", ai._ID_TO_EMOJI.get("111") == "🔥")
check(4, "regex yangilandi", bool(ai._TEXT_EMOJI_RE.search("bugun 🚀 uchdi")))

# ── 2. Almashtirish va TESKARI qaytarish ────────────────────────
matn = ai.build_rich_markdown("Tayyor 🔥 va 🚀 ketdi")
check(5, "emoji custom emojiga aylandi", matn.count("tg://emoji") == 2)
check(6, "zaxira yo'l matnni AYNAN tiklaydi",
      ai.strip_custom_emoji(matn) == "Tayyor 🔥 va 🚀 ketdi")

# ── 3. VS16 (U+FE0F) tanlagichi ─────────────────────────────────
# Model "✍️" deb ham, "✍" deb ham yozadi; paket esa ikkalasidan
# birini saqlagan bo'ladi. Ikkalasi ham topilishi shart.
check(7, "VS16 bilan yozilgani topiladi",
      "tg://emoji" in ai.build_rich_markdown("yozaman ✍️ hozir"))
check(8, "VS16 siz yozilgani ham topiladi",
      "tg://emoji" in ai.build_rich_markdown("yozaman ✍ hozir"))

# ── 4. Paketda yo'q emoji tegilmaydi ────────────────────────────
check(9, "notanish emoji oddiy holicha qoladi",
      "tg://emoji" not in ai.build_rich_markdown("mana 🥔 kartoshka"))

# ── 5. Chegara: bitta javobda cheklangan son ────────────────────
ai.apply_emoji_pack({"🔥": "111"})
# Chegaradan ANIQ ko'p emoji bilan sinaladi — aks holda test chegara
# ko'tarilganda jimgina "o'tib ketardi" va uni qo'riqlamay qo'yardi.
kop = ai.build_rich_markdown("🔥 " * (config.TEXT_CUSTOM_EMOJI_MAX + 10))
check(10, f"chegara ishlaydi ({config.TEXT_CUSTOM_EMOJI_MAX} ta)",
      kop.count("tg://emoji") == config.TEXT_CUSTOM_EMOJI_MAX)
# ⚠️ Chegara 12 edi va emoji ko'p javobda (30+ emoji) ko'zga tashlanardi:
# yuqoridagi emoji qimirlab, xuddi o'shanisi pastda qotib turardi.
check("10b", "chegara real javoblarni qamraydi",
      config.TEXT_CUSTOM_EMOJI_MAX >= 50)

# ── 6. Markdown parslanmaydigan joylar ──────────────────────────
# Jadval katagi va <aside> ichida markdown parslanmaydi — u yerda
# almashtirish ekranga XOM matn chiqarardi.
jadval = ai.build_rich_markdown("| a | b |\n|---|---|\n| 🔥 | x |")
check(11, "jadval katagida emoji tegilmaydi",
      "tg://emoji" not in jadval and "🔥" in jadval)

# ── 7. Bo'sh paket — hech narsa buzilmaydi ──────────────────────
ai.apply_emoji_pack({})
check(12, "bo'sh moslikda almashtirish yo'q",
      "tg://emoji" not in ai.build_rich_markdown("🔥 🚀 ✍️"))
check(13, "bo'sh moslikda matn buzilmaydi",
      "🔥" in ai.build_rich_markdown("🔥 🚀 ✍️"))

# ── 8. Sozlama va qo'lda qo'yilgan ID'lar ───────────────────────
check(14, "paket nomi sozlangan", bool(config.TEXT_EMOJI_PACK))
# ⚠️ Qo'lda qo'yilgan ID'lar aniq joylarda (tugma, tizim xabari)
# ishlatiladi — paket ularga TEGMASLIGI kerak.
check(15, "CUSTOM_EMOJI ro'yxati joyida",
      isinstance(config.CUSTOM_EMOJI, dict) and len(config.CUSTOM_EMOJI) > 0)

ai.apply_emoji_pack(asl)
print("\nHammasi o'tdi: 16/16")
