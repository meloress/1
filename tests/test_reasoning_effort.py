"""Reasoning darajasi: salomlashuv tanish, suhbat davomi (ha / noto'g'ri).

Ilgari salomlashuv so'z BOSHI bo'yicha tanilardi: "hisobla 17*23",
"noto'g'ri javob berding" ("no"), "haqiqatan shunday?" ("ha") o'ylamasdan
(`none`) javob olardi. Botning «ko'rsataymi?» taklifiga «ha» ham `none` edi.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import (build_request_params, pick_reasoning_effort as p,
                         upgrade_effort_for_pro)

# [1] Faqat haqiqiy salomlashuv o'ylamaydi
for t in ("salom", "Assalomu alaykum!", "rahmat", "katta rahmat 🙏", "xayr",
          "спасибо большое", "thank you"):
    assert p(t) == "none", (t, p(t))
print("[1] salomlashuv/rahmat -> none OK")

# [2] So'z boshi endi aldamaydi (eski xato)
for t in ("hisobla 17*23", "noto'g'ri javob berding", "haqiqatan shunday?",
          "nol nechta?", "oktyabrda nima bor", "hafta kunlari", "ha", "yo'q", "ok"):
    assert p(t) != "none", (t, p(t))
assert p("hisobla 17*23") == "medium"
print("[2] 'ha'/'no'/'hi' bilan boshlangan savollar o'ylaydi OK")

# [3] Taklifga «ha» — oldingi savoldan bir pog'ona yuqori (tavan medium)
assert p("ha", oldingi=["Toshkent qayerda joylashgan?"]) == "medium"
assert p("ha", oldingi=["tenglamani yech: 2x+3=7"]) == "medium"
print("[3] «ha» suhbatdan baholanadi OK")

# [4] Xatoni ko'rsatish — so'z ro'yxatisiz, xuddi shu qoida
for t in ("noto'g'ri", "unday emas", "неправильно", "you are wrong", "🤨",
          "yana bir bor qara"):
    assert p(t, oldingi=["Toshkent qayerda?"]) == "medium", (t, p(t, oldingi=["x"]))
print("[4] e'tiroz (har tilda) -> medium OK")

# [5] Zanjir: hisobla -> ha -> noto'g'ri — daraja yo'qolmaydi
assert p("noto'g'ri", oldingi=["hisobla 17*23", "ha"]) == "medium"
print("[5] zanjirda daraja saqlanadi OK")

# [6] Bepulda davom xabari high'ga chiqmaydi, Pro'da ko'tariladi
assert p("ha", oldingi=["integral hisobla"]) == "medium"
assert upgrade_effort_for_pro(p("ha", oldingi=["integral hisobla"])) == "high"
print("[6] tavan: bepul medium, Pro high OK")

# [7] Uzun yangi savol — kamida oldingi daraja, pog'onasiz
uzun = "Endi boshqa savol: " + "Toshkentdagi eng yaxshi kutubxonalar qaysilar " * 4
assert p(uzun, oldingi=["salom"]) == "low"
assert p(uzun, oldingi=["integral hisobla"]) == "medium"
print("[7] uzun xabar pog'ona olmaydi OK")

# [8] Suhbat salomlashuv bilan boshlangan bo'lsa — davom «low», "medium" emas
assert p("ha", oldingi=["salom"]) == "low"
# Salomlashuv suhbat ichida ham o'ylamaydi
assert p("rahmat", oldingi=["integral hisobla"]) == "none"
print("[8] salomlashuv davomi past OK")

# [9] Suhbatsiz va /think o'zgarmagan
assert p("Toshkent qayerda?") == "low"
assert p("ha", force_deep=True, oldingi=["salom"]) == "high"
print("[9] suhbatsiz / force_deep OK")

# [10] build_request_params oldingi'ni o'tkazadi
assert build_request_params("ha", oldingi=["Toshkent?"])["reasoning"]["effort"] == "medium"
assert build_request_params("ha")["reasoning"]["effort"] == "low"
print("[10] build_request_params OK")

print("\nHammasi o'tdi: 10/10")
