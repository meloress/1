# -*- coding: utf-8 -*-
"""Bir modulda (yoki bir klassda) bir xil nomli ikkita `def` bo'lmasin.

Python ikkinchisini jimgina birinchisining ustiga yozadi: hech narsa
yiqilmaydi, faqat birinchi funksiyani chaqirgan joy endi boshqa kodni
ishlatadi. 3 000 qatorli `handlers/biznes.py` da `_mijoz_nomi` aynan shunday
ikki marta yozilib, `/mijozlar` ni buzgan — testlar yashil turgan.

Tarmoqsiz va bazasiz ishlaydi.

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_takroriy_def.py
"""
import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _manba import kod  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHETLAB = {"venv", ".venv", "__pycache__", ".git", "node_modules"}


def takrorlar(tana, joy):
    korilgan, topildi = {}, []
    for t in tana:
        if isinstance(t, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if t.name in korilgan:
                topildi.append(f"{joy}{t.name} (qator {korilgan[t.name]} va {t.lineno})")
            korilgan[t.name] = t.lineno
        elif isinstance(t, ast.ClassDef):
            topildi += takrorlar(t.body, f"{joy}{t.name}.")
    return topildi


fayllar, xatolar = 0, []
for papka, ichki, nomlar in os.walk(ROOT):
    ichki[:] = [d for d in ichki if d not in CHETLAB]
    for nom in nomlar:
        if nom.endswith(".py"):
            yol = os.path.join(papka, nom)
            fayllar += 1
            nisbiy = os.path.relpath(yol, ROOT)
            xatolar += [f"{nisbiy}: {x}" for x in takrorlar(ast.parse(kod(yol)).body, "")]

assert fayllar > 50, fayllar
print(f"[1] {fayllar} ta fayl o'qildi OK")
assert not xatolar, "takroriy def:\n  " + "\n  ".join(xatolar)
print("[2] takroriy top-level / klass def yo'q OK")

# O'zini tekshirish: test haqiqatan ushlaydimi
namuna = ast.parse("def a(): pass\nclass K:\n    def b(self): pass\n    def b(self): pass\ndef a(): pass\n")
assert len(takrorlar(namuna.body, "")) == 2
print("[3] namunadagi ikkala takror ushlandi OK")

print("\nHammasi o'tdi: 3/3")
