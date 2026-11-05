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

print("\ntest_alifbo: 5/5 OK")
