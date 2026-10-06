# -*- coding: utf-8 -*-
"""Telegram Business — egasining topshirig'i: «soat 8 da Xusanga salom deb yoz».

Bu test ushlaydigan JIM nosozliklar:

  ⛔️ Model yozgan `chat_id` bilan BEGONA odamga (boshqa egasining
     suhbatdoshiga yoki umuman kartotekada yo'q odamga) xabar ketsa.
  ⛔️ Telegram rad etgan xabar (24 soat qoidasi) "yuborildi" deb aytilsa
     yoki egasiga hech narsa demay yo'qolsa.
  ⛔️ Asbob «💼 Biznes» mavzusidan tashqarida yoki bepul egada biriktirilsa
     (har so'rovga token) yoki dispatch bo'sh `else` dan pastda qolsa
     ("Xusanga yoz" veb qidiruvga aylanardi).
  ⛔️ Manifest Business mavzusida ham "writing on the user's behalf — never"
     desa (model rad etardi), yoki boshqa joyda buni aytmay qo'ysa.
  ⛔️ Eslatmalar ro'yxati UTC'da (09:00 → "04:00") ko'rinsa.

Tarmoqsiz va bazasiz ishlaydi.

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_biznes_topshiriq.py
"""
import asyncio
import inspect
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _manba import kod  # noqa: E402

import handlers.biznes as b              # noqa: E402
from core.config import INTERNAL_TOOL_NAMES  # noqa: E402
from db import database                  # noqa: E402
from services import ai                  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EGASI = 7001
HOZIR = datetime.now(timezone.utc)


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


MIJOZLAR = [
    {"chat_id": 11, "tg_ism": "Хусан", "username": None, "ism": None,
     "oxirgi": HOZIR - timedelta(hours=2)},
    {"chat_id": 12, "tg_ism": "Husan aka", "username": "xusan_99", "ism": None,
     "oxirgi": HOZIR - timedelta(days=3)},
    {"chat_id": 13, "tg_ism": "Anvar", "username": None, "ism": None,
     "oxirgi": HOZIR - timedelta(hours=5)},
]
yuborilgan, tarix, egasiga, rejalar, bekorlar = [], [], [], [], []
holat = {"rad": None, "huquq": {"can_reply": True, "can_read_messages": True},
         "yoqilgan": True}


async def _mijozlar(owner_id, limit=1000):
    return list(MIJOZLAR) if owner_id == EGASI else []


async def _mijozga(chat_id, conn_id, matn, belgi=False):
    if holat["rad"]:
        raise RuntimeError(holat["rad"])
    yuborilgan.append((chat_id, conn_id, matn))
    return NS(message_id=555, chat=NS(id=chat_id))


# Bot egasi nomidan yuborganlari (biznes_yuborilgan) va Telegram chaqiruvlari.
saqlangan, tg = [], []
YUBORILGANLAR = [
    {"id": 81, "chat_id": 12, "message_id": 901, "matn": "salom",
     "vaqt": datetime(2026, 10, 6, 5, 0, tzinfo=timezone.utc)},
    {"id": 80, "chat_id": 13, "message_id": 900, "matn": "Ertaga keling",
     "vaqt": datetime(2026, 10, 6, 4, 0, tzinfo=timezone.utc)},
]


async def _yoz(owner_id, chat_id, message_id, matn):
    saqlangan.append(("yoz", owner_id, chat_id, message_id, matn))


async def _yuborilganlar(owner_id, limit=15):
    return list(YUBORILGANLAR) if owner_id == EGASI else []


async def _y_ochir(owner_id, yid):
    saqlangan.append(("ochir", owner_id, yid))


async def _y_tahrir(owner_id, yid, matn):
    saqlangan.append(("tahrir", owner_id, yid, matn))


async def _tg_ochir(business_connection_id, message_ids):
    if holat["rad"]:
        raise RuntimeError(holat["rad"])
    tg.append(("ochir", business_connection_id, message_ids))
    return True


async def _tg_tahrir(text, business_connection_id, chat_id, message_id, parse_mode=None):
    if holat["rad"]:
        raise RuntimeError(holat["rad"])
    tg.append(("tahrir", business_connection_id, chat_id, message_id, text))
    return True


database.biznes_yuborilgan_yoz = _yoz
database.biznes_yuborilganlar = _yuborilganlar
database.biznes_yuborilgan_ochir = _y_ochir
database.biznes_yuborilgan_tahrir = _y_tahrir
b.bot = NS(delete_business_messages=_tg_ochir, edit_message_text=_tg_tahrir)


async def _tarix(chat_id, matn, role="user", thread_id=0, **kw):
    tarix.append((chat_id, matn, role, thread_id))


async def _egasiga(chat_id, matn, html=True, kb=None):
    egasiga.append((chat_id, matn))
    return True


async def _yarat(user_id, text, when, repeat="once", vazifa=False, thread_id=0,
                 biznes_kimga=0):
    rejalar.append((user_id, text, when, thread_id, biznes_kimga))
    return "qo'yildi: 2026-10-07 08:00"


async def _royxat(user_id, biznes=False):
    assert biznes is True
    return [{"id": 501, "text": "Salom", "biznes_kimga": 11,
             "run_at": datetime(2026, 10, 7, 3, 0, tzinfo=timezone.utc)}]


async def _bekor(user_id, task_id):
    bekorlar.append((user_id, task_id))
    return "bekor qilindi"


database.biznes_mijozlar = _mijozlar
database.biznes_egasi_ulanishi = lambda o: ("conn-1", {
    "yoqilgan": holat["yoqilgan"], "huquqlar": holat["huquq"]}) if o == EGASI else None
database.create_scheduled_task = _yarat
database.list_scheduled_tasks = _royxat
database.cancel_scheduled_task = _bekor
b._mijozga = _mijozga
b.safe_update_history = _tarix
b._egasiga = _egasiga


def run(coro):
    return asyncio.run(coro)


def tozala():
    for x in (yuborilgan, tarix, egasiga, rejalar, bekorlar, saqlangan, tg):
        x.clear()
    holat.update(rad=None, yoqilgan=True,
                 huquq={"can_reply": True, "can_read_messages": True})


# ── 1-2. Ismni topish ────────────────────────────────────────────
ro, topildi = b.mijoz_tanla(MIJOZLAR, "Xusan")
check(1, "Xusan = Хусан = Husan (kirill, x/h), Anvar yo'q",
      topildi and [m["chat_id"] for m in ro] == [11, 12])
ro, topildi = b.mijoz_tanla(MIJOZLAR, "Jamshid")
check(2, "mos topilmasa — oxirgi suhbatdoshlar, model o'zi solishtiradi",
      not topildi and len(ro) == 3)

# ── 3. Har qator 24 soat holatini aytadi ─────────────────────────
natija = run(b.topshiriq(EGASI, {"amal": "qidir", "ism": "xusan"}, 55))
qator11 = next(q for q in natija.splitlines() if "chat_id=11" in q)
qator12 = next(q for q in natija.splitlines() if "chat_id=12" in q)
check(3, "qidir: chat_id, havola va 24 soat holati har birida",
      "hozir yozsa bo'ladi" in qator11 and "24 soatdan oshgan" in qator12
      and "https://t.me/xusan_99" in qator12 and "tg://user?id=11" in qator11)

# ── 4-6. Begona chat_id ──────────────────────────────────────────
tozala()
for n, cid in ((4, 999), (5, True), (6, "11")):
    javob = run(b.topshiriq(EGASI, {"amal": "yubor", "chat_id": cid, "matn": "Salom"}, 55))
    check(n, f"chat_id={cid!r} — kartotekada yo'q/yaroqsiz, hech narsa ketmaydi",
          not yuborilgan and "kartotekasida yo'q" in javob)
javob = run(b.topshiriq(EGASI, {"amal": "yubor", "chat_id": 999, "matn": "x",
                                "vaqt": "2026-10-07 08:00"}, 55))
check("6b", "rejalashtirishda ham begona chat_id bazaga yetmaydi",
      not rejalar and "kartotekasida yo'q" in javob)

# ── 7. Darhol yuborish ──────────────────────────────────────────
tozala()
javob = run(b.topshiriq(EGASI, {"amal": "yubor", "chat_id": 11, "matn": "Salom\nqalaysiz"}, 55))
check(7, "yuborildi: ulanish orqali, qatorlar saqlanadi, tarixga egasi nomidan",
      yuborilgan == [(11, "conn-1", "Salom\nqalaysiz")] and "yuborildi" in javob
      and tarix == [(11, "Salom\nqalaysiz", "assistant", -EGASI)])
check("7b", "yuborilgani message_id bilan bazaga — «o'chir/tuzat» deploy'dan keyin ham",
      saqlangan == [("yoz", EGASI, 11, 555, "Salom\nqalaysiz")])

# ── 8. Telegram rad etdi (24 soat) ───────────────────────────────
tozala()
holat["rad"] = "Bad Request: BUSINESS_PEER_USAGE_MISSING"
javob = run(b.topshiriq(EGASI, {"amal": "yubor", "chat_id": 12, "matn": "Salom aka"}, 55))
check(8, "rad etilsa: 'yuborildi' DEMAYDI, 24 soatni aytadi, tayyor havola beradi",
      "yuborilmadi" in javob and "24 soat" in javob and not tarix
      and "https://t.me/xusan_99?text=Salom%20aka" in javob)

# ── 9. Huquq yo'q / ulanmagan ─────────────────────────────────────
tozala()
holat["huquq"] = {"can_reply": False}
javob = run(b.topshiriq(EGASI, {"amal": "yubor", "chat_id": 11, "matn": "Salom"}, 55))
check(9, "javob berish huquqi yo'q — yubormaydi, qayerda yoqishni aytadi",
      not yuborilgan and "huquqi" in javob)
tozala()
holat["yoqilgan"] = False
javob = run(b.topshiriq(EGASI, {"amal": "yubor", "chat_id": 11, "matn": "Salom"}, 55))
check("9b", "ulanish o'chiq — yubormaydi", not yuborilgan and "ulanmagan" in javob)

# ── 10. Rejalashtirish ───────────────────────────────────────────
tozala()
javob = run(b.topshiriq(EGASI, {"amal": "yubor", "chat_id": 11, "matn": "Salom",
                                "vaqt": "2026-10-07 08:00"}, 55))
check(10, "vaqt bilan — eslatma jadvaliga biznes_kimga va mavzu bilan, hozir ketmaydi",
      rejalar == [(EGASI, "Salom", "2026-10-07 08:00", 55, 11)] and not yuborilgan
      and "24 soat" in javob)

# ── 11. Ro'yxat Toshkent vaqtida, bekor indeksi tekshiriladi ──────
javob = run(b.topshiriq(EGASI, {"amal": "royxat"}, 55))
check(11, "ro'yxat: 03:00 UTC = 08:00 Toshkent, ism bilan",
      "08:00" in javob and "Хусан" in javob)
for idx in (True, 0, 2, "1"):
    run(b.topshiriq(EGASI, {"amal": "bekor", "index": idx}, 55))
run(b.topshiriq(EGASI, {"amal": "bekor", "index": 1}, 55))
check(12, "bekor: bool/0/chegaradan tashqari/satr — bazaga tegmaydi; 1 — o'sha id",
      bekorlar == [(EGASI, 501)])

# ── 13. Vaqti kelganda: egasiga natija DOIM ──────────────────────
tozala()
run(b.rejali_yubor(EGASI, 11, "Salom"))
holat["rad"] = "Forbidden"
run(b.rejali_yubor(EGASI, 12, "Salom"))
check(13, "rejali_yubor: muvaffaqiyat ham, rad ham egasiga aytiladi",
      len(egasiga) == 2 and egasiga[0][1].startswith("✅")
      and egasiga[1][1].startswith("❗") and "24 soat" in egasiga[1][1])

# ── 14-17. services/ai.py ulanishi ────────────────────────────────
src = kod(os.path.join(ROOT, "services", "ai.py"))
gor = src[src.index("async def get_openai_reply"):]
check(14, "dispatch bo'sh `else` dan YUQORIDA",
      gor.index('"biznes_xabar"') < gor.index(
          "            else:\n                search_ran = True"))
shart = gor[gor.index("biznes_enabled = ("):gor.index("MAX_BIZNES_ROUNDS")]
check(15, "faqat Pro, shaxsiy chat, mavzu > 0 va Biznes mavzusi",
      all(s in shart for s in ("is_pro", "chat_id == user_id", "thread_id > 0",
                               "_biznes_mavzusimi")))
check(16, "nom INTERNAL_TOOL_NAMES da (sizib chiqmasin)",
      ai._BIZNES_XABAR_TOOL["name"] in INTERNAL_TOOL_NAMES)
bor = str(ai._capability_manifest(file_task_enabled=True, image_enabled=True,
                                  reminder_enabled=True, memory_enabled=True,
                                  biznes_enabled=True))
yoq = str(ai._capability_manifest(file_task_enabled=True, image_enabled=True,
                                  reminder_enabled=True, memory_enabled=True))
check(17, "manifest: Biznes mavzusida asbob bor va 'never on behalf' yo'q; boshqa joyda aksincha",
      "biznes_xabar" in bor and "on the user's behalf" not in bor
      and "biznes_xabar" not in yoq and "on the user's behalf" in yoq)

# ── 18-20. Baza va kuzatuvchi (manba matni) ───────────────────────
db_src = kod(os.path.join(ROOT, "db", "database.py"))
royxat = db_src[db_src.index("async def list_scheduled_tasks"):]
royxat = royxat[:royxat.index("\n\n\n")]
check(18, "eslatmalar ro'yxati va topshiriqlar ro'yxati ajralgan (raqamlar aralashmaydi)",
      "(biznes_kimga <> 0) = $2" in royxat)
yarat = db_src[db_src.index("async def create_scheduled_task"):]
yarat = yarat[:yarat.index("\n\n\n")]
check(19, "topshiriq matni eslatmadek bir qatorga/200 belgiga qisilmaydi",
      "BIZNES_TOPSHIRIQ_MAX] if biznes_kimga" in yarat and "biznes_kimga)" in yarat)
h_src = kod(os.path.join(ROOT, "handlers", "helpers.py"))
kuz = h_src[h_src.index("async def reminder_watcher"):]
check(20, "kuzatuvchi: biznes_kimga — egasi nomidan yuboradi, vazifadan OLDIN",
      kuz.index('row.get("biznes_kimga")') < kuz.index('row.get("vazifa")')
      and "rejali_yubor" in kuz)
check(21, "oddiy eslatmalar ro'yxati ham Toshkent vaqtida (UTC emas)",
      "r['run_at'].astimezone(TASHKENT_TZ)" in src)

# ── 22-27. Yuborilganini o'chirish / tahrirlash ───────────────────
tozala()
javob = run(b.topshiriq(EGASI, {"amal": "yuborilganlar"}, 55))
check(22, "yuborilganlar: Toshkent vaqtida, ism bilan, yangisi birinchi",
      javob.startswith("1. 10-06 10:00 — Husan aka: «salom»") and "2. 10-06 09:00 — Anvar" in javob)
for idx in (True, 0, 3, "1"):
    run(b.topshiriq(EGASI, {"amal": "ochir", "index": idx}, 55))
    run(b.topshiriq(EGASI, {"amal": "tahrir", "index": idx, "matn": "x"}, 55))
check(23, "ochir/tahrir: yaroqsiz indeks — Telegram'ga ham, bazaga ham tegmaydi",
      not tg and not saqlangan)
javob = run(b.topshiriq(EGASI, {"amal": "ochir", "index": 1}, 55))
check(24, "o'chirish huquqi yo'q — tegmaydi, huquq nomini va yo'lini aytadi",
      not tg and not saqlangan and "Yuborilgan xabarlarni o'chirish" in javob)
holat["huquq"] = {"can_reply": True, "can_delete_sent_messages": True}
javob = run(b.topshiriq(EGASI, {"amal": "ochir", "index": 1}, 55))
check(25, "o'chirildi: o'sha message_id, keyin bazadan (avval Telegram)",
      tg == [("ochir", "conn-1", [901])] and saqlangan == [("ochir", EGASI, 81)]
      and "o'chirildi" in javob)
tozala()
holat["huquq"] = {"can_reply": True}
javob = run(b.topshiriq(EGASI, {"amal": "tahrir", "index": 2, "matn": "Soat 11 da keling"}, 55))
check(26, "tahrirlandi: o'sha chat va xabar, bazadagi matn yangilanadi",
      tg == [("tahrir", "conn-1", 13, 900, "Soat 11 da keling")]
      and saqlangan == [("tahrir", EGASI, 80, "Soat 11 da keling")])
tozala()
holat["rad"] = "Bad Request: message can't be edited"
javob = run(b.topshiriq(EGASI, {"amal": "tahrir", "index": 2, "matn": "x"}, 55))
check(27, "Telegram rad etsa — 'tahrirlandi' DEMAYDI, baza o'zgarmaydi",
      "tahrirlanmadi" in javob and not saqlangan)
check(28, "o'chirish huquqining rasmiy nomi uch tilda",
      b.HUQUQ_NOMI["can_delete_sent_messages"] == "Yuborilgan xabarlarni o'chirish"
      and b._HUQUQ_TIL["en"]["can_delete_sent_messages"] == "Delete Sent Messages"
      and b._HUQUQ_TIL["ru"]["can_delete_sent_messages"] == "Удаление исходящих")
tavsif = ai._BIZNES_XABAR_TOOL["description"]
check(29, "tavsif: «shu odammi?» tasdig'i va noto'g'ri odam → o'chir",
      "shu odammi" in tavsif and "Boshqa odamga yozibsan" in tavsif)

print("\nbiznes_topshiriq: barcha tekshiruvlar o'tdi (32/32).")
