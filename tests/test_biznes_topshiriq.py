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
eskirgan = []


async def _eskirt(owner_id, chat_id):
    eskirgan.append((owner_id, chat_id))


database.biznes_loyiha_eskirt = _eskirt   # ⚠️ usiz test .env dagi JONLI bazaga borardi
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
    "yoqilgan": holat["yoqilgan"], "huquqlar": holat["huquq"], "rejim": "yordamchi",
    "ish_vaqti": None}) if o == EGASI else None
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

# ── 7-10. `yubor` — faqat TAKLIF; egasining «ha»si kodda bajaradi ──
# Jonli shikoyat (2026-10-06): «ha» → yana so'radi, «ha yubor» → yana.
import handlers.messages as hm  # noqa: E402
hm._thread_key = lambda m: 55
ERTAGA = (datetime.now(database.TASHKENT_TZ) + timedelta(days=1)).strftime("%Y-%m-%d 08:00")


def xabar(matn, egasi=EGASI):
    javoblar = []

    async def answer(t, **k):
        javoblar.append(t)
    return NS(text=matn, from_user=NS(id=egasi), answer=answer, javoblar=javoblar)


def taklif_va(args, soz):
    """(taklif natijasi, ushlandimi, egasiga javob)."""
    taklif = run(b.topshiriq(EGASI, {"amal": "yubor", **args}, 55))
    m = xabar(soz)
    return taklif, run(b.tasdiq_ushla(m)), m.javoblar


tozala()
b._taklif.clear()
taklif = run(b.topshiriq(EGASI, {"amal": "yubor", "chat_id": 11, "matn": "Salom\nqalaysiz"}, 55))
check(7, "yubor HECH NARSA yubormaydi — bitta tasdiq savolini qaytaradi",
      not yuborilgan and "HALI YUBORILMADI" in taklif and "yuboraymi?" in taklif
      and "tg://user?id=11" in taklif and "hozir" in taklif)
m = xabar("ha yubor")
check("7b", "«ha yubor» — AI'siz, kodda yuboradi; tarixlarga yoziladi",
      run(b.tasdiq_ushla(m)) and yuborilgan == [(11, "conn-1", "Salom\nqalaysiz")]
      and m.javoblar[0].startswith("✅")
      and (11, "Salom\nqalaysiz", "assistant", -EGASI) in tarix
      and (EGASI, "ha yubor", "user", 55) in tarix
      and saqlangan == [("yoz", EGASI, 11, 555, "Salom\nqalaysiz")])
check("7c", "bir taklif — bir yuborish: ikkinchi «ha» AI'ga ketadi",
      not run(b.tasdiq_ushla(xabar("ha"))) and len(yuborilgan) == 1)

tozala()
_, ushlandi, j = taklif_va({"chat_id": 11, "matn": "Salom"}, "Yo‘q")
check(8, "«yo'q» — bekor, hech narsa ketmaydi", ushlandi and not yuborilgan and "Bekor" in j[0])
tozala()
_, ushlandi, _ = taklif_va({"chat_id": 11, "matn": "Salom"}, "yo'q unga soat nechi bo'lganini ayt")
check("8b", "tuzatish — AI'ga o'tadi va eski taklif eskiradi (keyingi «ha» uni yubormaydi)",
      not ushlandi and not run(b.tasdiq_ushla(xabar("ha"))) and not yuborilgan)
tozala()
run(b.topshiriq(EGASI, {"amal": "yubor", "chat_id": 11, "matn": "Salom"}, 55))
check("8c", "boshqa egasining «ha»si begona taklifni yubormaydi",
      not run(b.tasdiq_ushla(xabar("ha", egasi=EGASI + 1))) and not yuborilgan)
b._taklif.clear()

tozala()
holat["rad"] = "Bad Request: BUSINESS_PEER_USAGE_MISSING"
taklif, _, j = taklif_va({"chat_id": 12, "matn": "Salom aka"}, "ha")
check(9, "rad etilsa: 'yuborildi' DEMAYDI, 24 soatni aytadi, tayyor havola beradi",
      j[0].startswith("❗") and "24 soat" in j[0]
      and "https://t.me/xusan_99?text=Salom%20aka" in j[0]
      and not any(r[0] == 12 for r in tarix))
tozala()
holat["huquq"] = {"can_reply": False}
_, _, j = taklif_va({"chat_id": 11, "matn": "Salom"}, "ha")
check("9b", "javob berish huquqi yo'q — yubormaydi, qayerda yoqishni aytadi",
      not yuborilgan and "huquqi" in j[0])
tozala()
holat["yoqilgan"] = False
_, _, j = taklif_va({"chat_id": 11, "matn": "Salom"}, "ha")
check("9c", "ulanish o'chiq — yubormaydi", not yuborilgan and "ulanmagan" in j[0])

tozala()
taklif, _, j = taklif_va({"chat_id": 11, "matn": "Salom", "vaqt": ERTAGA}, "✅")
check(10, "vaqt bilan: taklifda «ertaga 08:00», «ha» dan keyin eslatma jadvaliga",
      "ertaga 08:00" in taklif and rejalar == [(EGASI, "Salom", ERTAGA, 55, 11)]
      and not yuborilgan and j[0].startswith("⏰"))
tozala()
javob = run(b.topshiriq(EGASI, {"amal": "yubor", "chat_id": 11, "matn": "Salom",
                                "vaqt": "2020-01-01 08:00"}, 55))
check("10b", "o'tgan vaqt — taklif saqlanmaydi", "yaroqsiz" in javob and not b._taklif)
check("10c", "ha/yo'q aniqlash: kirill, x/h, tutuq; tuzatish — None",
      [b.javob_turi(s) for s in ("xa", "Ha!", "да", "+", "to‘xtat", "нет", "ha, lekin")]
      == ["ha", "ha", "ha", "ha", "yoq", "yoq", None])

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
check(29, "tavsif: yubor — faqat taklif; noto'g'ri odam → o'chir",
      "HECH NARSA QILMAYDI" in tavsif and "Boshqa odamga yozibsan" in tavsif)
m_src = kod(os.path.join(ROOT, "handlers", "messages.py"))
ht = m_src[m_src.index("async def handle_text"):m_src.index("async def _queue_for_ai")]
check(30, "handle_text: tasdiq AI navbatidan OLDIN ushlanadi",
      ht.index("tasdiq_ushla") < ht.index("await _queue_for_ai"))

# ═══ 31-45. Mavzudagi AI biznesni ko'radi va boshqaradi (2026-10-06) ═══
from handlers import biznes_uslub  # noqa: E402

yozuvlar = []                                   # bazaga yozuvchi chaqiruvlar
BILIM = {"matn": "Do'kon: kiyim\nNarx: 40 000\nManzil: Chilonzor"}
model_chaqiruv = []


async def _bilim_ol(o):
    return BILIM["matn"] if o == EGASI else ""


async def _bilim_yoz(o, matn):
    yozuvlar.append(("bilim", o, matn))


async def _yozuvchi(nom):
    async def f(*a):
        yozuvlar.append((nom,) + a)
    return f


async def _model_soxta(prompt, chat_id, thread, egasi, **kw):
    model_chaqiruv.append((prompt, chat_id, thread, egasi, kw))
    return holat.get("model_javob", "Ertaga soat 10 da keling.")


async def _uslub_ol(o):
    return {"uslub_egasi": "doim «siz» deb yoz"}


async def _tarix_ol(chat_id, limit=30, thread_id=0):
    model_chaqiruv.append(("tarix", chat_id, thread_id))
    return [{"role": "user", "content": "narxi qancha?"},
            {"role": "assistant", "content": "40 ming"}]


async def _faol(o, soat=24, limit=15):
    return [{"chat_id": 13, "role": "user", "content": "yetkazib berasizmi?",
             "created_at": HOZIR - timedelta(minutes=20), "soni": 3}]


async def _javobsiz(dan, gacha, owner_id=None, faqat_yangi=False):
    return [{"chat_id": 11, "content": "bormi?", "created_at": HOZIR - timedelta(hours=2)}]


async def _kutayotgan(o, limit=5):
    raise RuntimeError("baza uzildi")          # bitta qism yiqilsa ham qolgani chiqsin


database.biznes_bilim_ol = _bilim_ol
database.biznes_bilim_yoz = _bilim_yoz
for _n in ("biznes_rejim_yoz", "biznes_chat_ochir", "biznes_pauza",
           "biznes_ish_vaqti_yoz", "biznes_vaqt_yoz"):
    setattr(database, _n, run(_yozuvchi(_n)))
database.biznes_faol_chatlar = _faol
database.biznes_javobsizlar = _javobsiz
database.biznes_kutayotganlar = _kutayotgan
b._model = _model_soxta
b.get_chat_history = _tarix_ol
biznes_uslub.uslub_ol = _uslub_ol


def tozala2():
    tozala()
    for x in (yozuvlar, model_chaqiruv, eskirgan):
        x.clear()
    b._taklif.clear()
    holat.pop("model_javob", None)


# ── 31. Yuborilgach shu chatdagi qoralama eskiradi (ikki javob ketmasin) ──
tozala2()
taklif_va({"chat_id": 11, "matn": "Salom"}, "ha")
check(31, "yuborilgach o'sha chat qoralamasi eskirtiriladi (keyingi «Yuborish» ikkinchi javob bo'lmasin)",
      eskirgan == [(EGASI, 11)])

# ── 32-33. korsatma: matnni .javob yo'lida yozadi ────────────────────
tozala2()
taklif = run(b.topshiriq(EGASI, {"amal": "yubor", "chat_id": 13,
                                 "korsatma": "ertaga 10 da kelsin"}, 55))
p, cid, th, eg, kw = model_chaqiruv[0]
check(32, "korsatma: o'sha mijoz tarixi (-egasi), Bilim va Uslub bilan; taklifda yozilgan matn",
      cid == 13 and th == -EGASI and "ertaga 10 da kelsin" in p
      and "Narx: 40 000" in kw["biznes_yoriqnoma"] and "«siz»" in kw["biznes_yoriqnoma"]
      and "Ertaga soat 10 da keling." in taklif and not yuborilgan)
tozala2()
holat["model_javob"] = "[tanlov: soat nechida? | 9 | 10]"
javob = run(b.topshiriq(EGASI, {"amal": "yubor", "chat_id": 13, "korsatma": "kelsin"}, 55))
check(33, "model bo'sh/marker qaytarsa — taklif YO'Q, aniq so'z so'raladi",
      "yozib bo'lmadi" in javob and not b._taklif)

# ── 34-37. Bilim ─────────────────────────────────────────────────
yangi, tavsif = b.bilim_ozgartir(BILIM["matn"], "Yetkazib berish: bepul", 2, "Narx: 50 000", None)
check(34, "bilim_ozgartir: faqat ko'rsatilgan qator, qolgani AYNAN qoladi",
      yangi == "Do'kon: kiyim\nNarx: 50 000\nManzil: Chilonzor\nYetkazib berish: bepul"
      and "«Narx: 40 000» → «Narx: 50 000»" in tavsif)
check(35, "bilim_ozgartir: bool/0/chegaradan tashqari/bo'sh o'zgarish — rad",
      all(b.bilim_ozgartir(BILIM["matn"], "", q, "x", None)[0] is None for q in (True, 0, 4))
      and b.bilim_ozgartir(BILIM["matn"], "", None, "", None)[0] is None
      and b.bilim_ozgartir(BILIM["matn"], "", None, "", 3)[0] == "Do'kon: kiyim\nNarx: 40 000")
tozala2()
taklif = run(b.topshiriq(EGASI, {"amal": "bilim_ozgartir", "qator": 2, "matn": "Narx: 50 000"}, 55))
check(36, "bilim: taklif kod yozgan tavsif bilan, hali o'zgarmagan",
      "Saqlaymi?" in taklif and "«Narx: 40 000» → «Narx: 50 000»" in taklif and not yozuvlar)
m = xabar("ha")
run(b.tasdiq_ushla(m))
check("36b", "«ha» — saqlanadi, faqat o'sha qator o'zgaradi",
      yozuvlar == [("bilim", EGASI, "Do'kon: kiyim\nNarx: 50 000\nManzil: Chilonzor")]
      and m.javoblar[0].startswith("✅"))
tozala2()
run(b.topshiriq(EGASI, {"amal": "bilim_ozgartir", "qosh": "Chegirma: 10%"}, 55))
BILIM["matn"] += "\nYangi qator"                       # shu orada /biznes dan o'zgardi
m = xabar("ha")
run(b.tasdiq_ushla(m))
BILIM["matn"] = "Do'kon: kiyim\nNarx: 40 000\nManzil: Chilonzor"
check("36c", "shu orada Bilim o'zgargan bo'lsa — ustidan yozmaydi",
      not yozuvlar and "o'zgardi" in m.javoblar[0])
tozala2()
javob = run(b.topshiriq(EGASI, {"amal": "bilim_ozgartir", "qosh": "Karta: 8600 1234 5678 9012"}, 55))
check(37, "karta raqami Bilimga kirmaydi (clean_biznes_bilim)", "saqlanmaydi" in javob and not b._taklif)

# ── 38-41. Sozlamalar ────────────────────────────────────────────
tozala2()
javob = run(b.topshiriq(EGASI, {"amal": "sozlama", "rejim": "avtomat"}, 55))
m = xabar("ha")
run(b.tasdiq_ushla(m))
check(38, "rejim: taklif → «ha» → biznes_rejim_yoz",
      "Shunday qilaymi?" in javob and yozuvlar == [("biznes_rejim_yoz", EGASI, "avtomat")])
tozala2()
xatolar = [run(b.topshiriq(EGASI, {"amal": "sozlama", **a}, 55)) for a in (
    {"rejim": "turbo"}, {"chat_id": 999, "avtomat": False}, {"chat_id": 11, "pauza_soat": 0},
    {"chat_id": 11, "pauza_soat": True}, {"ish_vaqti": "25-9"}, {"kutish_soniya": 45}, {})]
check(39, "noto'g'ri sozlamalar — taklif ham, yozuv ham yo'q",
      not b._taklif and not yozuvlar and len(xatolar) == 7)
tozala2()
run(b.topshiriq(EGASI, {"amal": "sozlama", "chat_id": 11, "avtomat": False}, 55))
run(b.tasdiq_ushla(xabar("ha")))
run(b.topshiriq(EGASI, {"amal": "sozlama", "chat_id": 13, "pauza_soat": 2}, 55))
run(b.tasdiq_ushla(xabar("ha")))
run(b.topshiriq(EGASI, {"amal": "sozlama", "ish_vaqti": "20-9"}, 55))
run(b.tasdiq_ushla(xabar("ha")))
run(b.topshiriq(EGASI, {"amal": "sozlama", "ish_vaqti": "doim"}, 55))
run(b.tasdiq_ushla(xabar("ha")))
run(b.topshiriq(EGASI, {"amal": "sozlama", "kutish_soniya": 60}, 55))
run(b.tasdiq_ushla(xabar("ha")))
check(40, "chat avtomati, pauza, ish vaqti (20-9 → 20:00-09:00, doim → None), kutish",
      yozuvlar == [("biznes_chat_ochir", EGASI, 11, True), ("biznes_pauza", EGASI, 13, 2),
                   ("biznes_ish_vaqti_yoz", EGASI, "20:00-09:00"),
                   ("biznes_ish_vaqti_yoz", EGASI, None),
                   ("biznes_vaqt_yoz", EGASI, "kutish_soniya", 60)])
tozala2()
run(b.topshiriq(EGASI, {"amal": "sozlama", "rejim": "kuzatuv"}, 55))
run(b.tasdiq_ushla(xabar("yo'q")))
check(41, "«yo'q» — sozlama o'zgarmaydi", not yozuvlar)

# ── 42-43. Yozishma va bugungi chatlar ────────────────────────────
tozala2()
javob = run(b.topshiriq(EGASI, {"amal": "suhbat", "chat_id": 11}, 55))
check(42, "suhbat: faqat shu egasining kaliti (-egasi), mijoz ismi bilan",
      model_chaqiruv == [("tarix", 11, -EGASI)] and "Хусан: narxi qancha?" in javob
      and "Egasi: 40 ming" in javob)
tozala2()
javob = run(b.topshiriq(EGASI, {"amal": "suhbat", "chat_id": 999}, 55))
check("42b", "begona chat_id — yozishma O'QILMAYDI", not model_chaqiruv and "kartotekasida yo'q" in javob)
javob = run(b.topshiriq(EGASI, {"amal": "bugun"}, 55))
check(43, "bugun: kim javob kutmoqda", "Anvar" in javob and "JAVOB KUTMOQDA" in javob)

# ── 44. Holat bloki ──────────────────────────────────────────────
tozala2()
run(b.topshiriq(EGASI, {"amal": "yubor", "chat_id": 13, "matn": "Salom"}, 55))
blok = run(b.holat_bloki(EGASI))
check(44, "holat: taklif, javob kutayotgan, yuborilgan, reja, rejim; yiqilgan qism boshqalarni to'xtatmaydi",
      "[BIZNES HOLATI" in blok and "Tasdiq kutayotgan taklif" in blok
      and "Хусан (chat_id=11)" in blok and "Oxirgi yuborilganlar" in blok
      and "Rejalashtirilgan" in blok and "Rejim: Yordamchi" in blok
      and "Hal qilinmagan" not in blok)

# ── 45. Reply konteksti ──────────────────────────────────────────
mavzumi = {"javob": True}


async def _mavzumi(o, t):
    return mavzumi["javob"]


database.biznes_mavzumi = _mavzumi
BOT_ID = 555000


def reply(matn, javob):
    return NS(text=matn, chat=NS(id=EGASI), from_user=NS(id=EGASI), bot=NS(id=BOT_ID),
              reply_to_message=javob)


bot_xabari = NS(from_user=NS(id=BOT_ID), text="✍️ Хусан yozdi: bormi?", caption=None)
ildiz = NS(from_user=NS(id=BOT_ID), text=None, caption=None)      # mavzu ochilish xabari
begona = NS(from_user=NS(id=EGASI), text="o'zimning xabarim", caption=None)
r1 = run(hm._biznes_iqtibos(reply("unga javob ber", bot_xabari)))
r2 = run(hm._biznes_iqtibos(reply("salom", ildiz)))
r3 = run(hm._biznes_iqtibos(reply("salom", begona)))
mavzumi["javob"] = False
r4 = run(hm._biznes_iqtibos(reply("unga javob ber", bot_xabari)))
check(45, "reply: bot xabari iqtibos bo'ladi; mavzu ildizi, o'z xabari, boshqa mavzu — o'zgarmaydi",
      r1.startswith("[Egasi botning shu xabariga javob yozmoqda: «✍️ Хусан yozdi: bormi?»]")
      and r1.endswith("unga javob ber") and r2 == "salom" and r3 == "salom"
      and r4 == "unga javob ber")

# ── 46. AI: holat bloki faqat Biznes mavzusida, foydalanuvchi xabaridan oldin ──
gor = src[src.index("async def get_openai_reply"):]
check(46, "holat bloki: biznes_enabled bilan, user xabaridan OLDIN, mijoz yo'lida emas",
      gor.index("holat_bloki") < gor.index('messages.append({"role": "user"')
      and "and not biznes" in gor[gor.index("biznes_enabled = ("):gor.index("holat_bloki")])

print("\nbiznes_topshiriq: barcha tekshiruvlar o'tdi (61/61).")
