# -*- coding: utf-8 -*-
"""Chat javobi: lotinda yozganga kirill aralashmasin (`messages._alifbo`)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handlers.messages import _alifbo  # noqa: E402

# [1] Jonli holat (eval_chat `rahmat`): lotin savol, javob oxiri kirillda.
j = _alifbo("Arzimaydi, xursandman. Кейин яна керак бўлса, ёзаверинг.", "rahmat")
assert j == "Arzimaydi, xursandman. Keyin yana kerak bo'lsa, yozavering.", j
print("[1] aralash kirill lotinga o'girildi OK")

# [2] Kirillda yozgan — uning alifbosi, tegilmaydi.
s = "Кейин яна керак бўлса, ёзаверинг."
assert _alifbo(s, "раҳмат") == s
print("[2] kirill suhbatdosh — o'zgarmaydi OK")

# [3] «kirillda yoz» so'ralgan — javob kirill bo'lishi shart.
s = "Kirillda: **Қишлоқ**"
assert _alifbo(s, "qishloq so'zini kirillda yoz") == s
print("[3] kirill so'ralgan — o'zgarmaydi OK")

# [4] Ruscha iqtibos (o'zbekcha harfsiz) — tegilmaydi.
s = "Basta'ning «Кинолента» qo'shig'i 2024-yilda chiqqan."
assert _alifbo(s, "Kinolenta qachon chiqqan") == s
print("[4] ruscha iqtibos — o'zgarmaydi OK")

# [5] Kirillsiz javob — o'zgarishsiz.
assert _alifbo("Salom!", "salom") == "Salom!"
assert _alifbo("", "salom") == ""
print("[5] lotin javob — o'zgarmaydi OK")

# [6] JONLI (2026-11-05): «krillcha» — i harfisiz. Model to'g'ri kirill
#     yozdi, kod 4 marta lotinga o'girdi.
s = "Жумаева Хилола Убайдулла қизи"
for savol in ("Jumayeva Xilola Ubaydulla qizi\n\nshuni krillcha yozib ber",
              "krillcha yozib ber", "kirilda yoz", "lotincha demadim"):
    assert _alifbo(s, savol) == s, savol
s = "Mana: Жумаева Хилола Убайдулла қизи"
for savol in ("krillcha yozib ber", "eski alifboda yoz"):
    assert _alifbo(s, savol) == s, savol
print("[6] «krillcha», «kirilda» va sof kirill javob — o'zgarmaydi OK")

# [7] Javobning o'zi alifbo haqida gapirsa — tegilmaydi.
s = "Uzr, xato ketdi. To'g'ri kirillchasi: **Жумаева Хилола Убайдулла қизи**"
assert _alifbo(s, "nega yana lotincha yuborayabsan") == s
print("[7] javobda «kirillchasi» — o'zgarmaydi OK")

print("\ntest_alifbo: 7/7 OK")
