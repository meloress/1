# -*- coding: utf-8 -*-
"""Sandbox: model yozgan kod tarmoqqa chiqa olmaydi.

  ⛔️ kod Railway ichki tarmog'idagi Postgres / Web-panel / boshqa botlarga
     ulanadi (prompt-injection bilan «shu manzilni o'qi»);
  ⛔️ himoya fayl yaratishni buzadi — sandbox butunlay ishlamay qoladi;
  ⛔️ traceback boshidan kesiladi — xatoning o'zi modelga yetmaydi;
  ⛔️ qo'riqchi skriptdagi qator raqamlarini siljitadi.

Tarmoqsiz (aksincha — tarmoq yopiqligini tekshiradi).

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_sandbox_tarmoq.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.sandbox import run_in_sandbox  # noqa: E402


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


def yur(kod):
    return asyncio.run(run_in_sandbox(kod))


r = yur("import urllib.request\nurllib.request.urlopen('http://example.com', timeout=3)")
check(1, "HTTP so'rov yopiq, xato matni tushunarli",
      not r.success and "internet yopiq" in r.traceback)
r = yur("import socket\nsocket.socket().connect(('10.0.0.1', 5432))")
check(2, "ichki IP'ga to'g'ridan-to'g'ri socket yopiq",
      not r.success and "internet yopiq" in r.traceback)
r = yur("import socket\nsocket.gethostbyname('postgres.railway.internal')")
check(3, "ichki DNS nomi ham yopiq", not r.success and "internet yopiq" in r.traceback)
r = yur("open('output/a.txt', 'w').write('ok')")
check(4, "fayl yaratish ishlaydi", r.success and r.output_files == [("a.txt", b"ok")])
r = yur("\n".join(f"def f{i}():\n    return f{i + 1}()" for i in range(80))
        + "\ndef f80():\n    raise ValueError('ENG_OXIRI')\nf0()")
check(5, "uzun traceback'da xatoning o'zi (oxiri) qoladi",
      not r.success and "ENG_OXIRI" in r.traceback)
r = yur("x = 1\ny = 2\nraise KeyError('q')")
check(6, "qator raqami o'zgarmagan (script.py, 3-qator)",
      'File "script.py", line 3' in r.traceback)

print("\nHammasi o'tdi: 6/6")
