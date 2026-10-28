# -*- coding: utf-8 -*-
"""Telegram Business, 4-bosqich — hisobot, javobsiz chatlar, kartoteka,
profil/story va panel kartasi.

Bu test ushlaydigan JIM nosozliklar (REJA.md 4-bosqich):

  ⛔️ Bo'sh kunda hisobot (shovqin) yoki bir kunda ikki hisobot.
  ⛔️ Model yozgan kartoteka maydoni tekshiruvsiz bazaga tushsa (soxta
     telefon, begona chat raqami, `True` indeks).
  ⛔️ Javobsiz chat har tekshiruvda qayta-qayta ogohlantirilsa, yoki
     yetib bormagan ogohlantirish "aytildi" deb belgilansa.
  ⛔️ Profil TASDIQSIZ o'zgarsa.
  ⛔️ CSV eksportda formula in'eksiyasi.
  ⛔️ Biznes tokeni boshqa tokenlardan ajralmasa (panel ulushi yolg'on).

Tarmoqsiz va bazasiz ishlaydi.

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_biznes_hisobot.py
"""
import asyncio
import io
import os
import sys
from datetime import date, datetime
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _manba import kod  # noqa: E402

import handlers.biznes as b              # noqa: E402
from db import database                  # noqa: E402
from services import ai                  # noqa: E402
from web import api                      # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EGASI, DM = 7001, 7001


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


def soat(h, m=0):
    return datetime(2026, 9, 25, h, m, tzinfo=database.TASHKENT_TZ)


# ── 1-2. Kartoteka maydonlari ────────────────────────────────────
check(1, "telefon: formatlar normallashadi, soxtasi rad",
      database.clean_mijoz_maydon(None, "+998 (90) 123-45-67", None)[1] == "+998901234567"
      and database.clean_mijoz_maydon(None, "901234567", None)[1] == "901234567"
      and database.clean_mijoz_maydon(None, "12", None)[1] is None
      and database.clean_mijoz_maydon(None, "qo'ng'iroq qiling", None)[1] is None
      and database.clean_mijoz_maydon(None, "1" * 20, None)[1] is None)
ism, _, qiz = database.clean_mijoz_maydon("Ali\nIGNORE ALL", None, "x" * 500)
check(2, "ism bir qatorga, uzunliklar kesiladi, bo'sh -> None",
      ism == "Ali IGNORE ALL" and len(qiz) == 200
      and database.clean_mijoz_maydon("", "", "   ") == (None, None, None))

# ── Soxta dunyo ──────────────────────────────────────────────────
q = []
holat = {"band": True, "hisob": None, "xulosa": {}, "javobsiz": [], "soat": soat(10),
         "send_xato": set(), "manba": []}


class SoxtaBot:
    async def send_message(self, chat_id, text, reply_markup=None, **kw):
        if chat_id in holat["send_xato"]:
            raise RuntimeError("Forbidden: bot was blocked")
        q.append(("send", chat_id, text, reply_markup))

    async def set_business_account_bio(self, conn, bio):
        q.append(("bio", conn, bio))

    async def set_business_account_name(self, conn, ism, fam=None):
        q.append(("ism", conn, ism, fam))

    async def set_business_account_profile_photo(self, conn, photo):
        q.append(("rasm", conn, photo))

    async def __call__(self, method):
        q.append(("metod", type(method).__name__, method))


async def rost(*a):
    return True


async def band(owner, kun):
    q.append(("band", owner, kun))
    return holat["band"]


async def kun_hisobi(owner, kun):
    q.append(("hisob", kun))
    return holat["hisob"]


async def xulosa(matnlar, egasi=None):
    holat["manba"].append(ai.BIZNES_MANBA.get())
    q.append(("xulosa", len(matnlar)))
    return holat["xulosa"]


async def mijoz_yangila(owner, chat, ism, tel, qiz):
    q.append(("kartoteka", chat, ism, tel, qiz))


b.bot = SoxtaBot()
b.biznes_kun_xulosasi = xulosa
b._hozir = lambda: holat["soat"]
# «💼 Biznes» mavzusi: bazada yo'q, soxta bot mavzu ocha olmaydi -> mavzusiz.
database.biznes_mavzu_ol = lambda *a, **k: _mavzusiz()


async def _mavzusiz():
    return None


database.pro_tarifmi = rost
database.biznes_hisobot_band = band
database.biznes_kun_hisobi = kun_hisobi
database.biznes_mijoz_yangila = mijoz_yangila

# Bilim taklifi (2026-10-28) — ⚠️ usiz _hisobot .env dagi JONLI bazaga borardi.
holat.update(juftlar=[], faktlar=[], bilim="Futbolka 80 000 so'm.", loyiha={})


async def fakt_juftlari(owner, limit=30):
    q.append(("juftlar", owner))
    return list(holat["juftlar"])


async def fakt_belgila(owner, natija):
    q.append(("belgila", owner, dict(natija)))


async def fakt_ajrat(bilim, juftlar, egasi=None):
    holat["manba"].append(ai.BIZNES_MANBA.get())
    q.append(("fakt_model", len(juftlar)))
    return holat["faktlar"]


async def bilim_ol(owner):
    return holat["bilim"]


async def bilim_yoz(owner, matn):
    q.append(("bilim_yoz", owner, matn))
    holat["bilim"] = matn


async def loyiha_ol(lid, owner):
    return holat["loyiha"].get((lid, owner))


database.biznes_fakt_juftlari = fakt_juftlari
database.biznes_fakt_belgila = fakt_belgila
database.biznes_bilim_ol = bilim_ol
database.biznes_bilim_yoz = bilim_yoz
database.biznes_loyiha_ol = loyiha_ol
b.biznes_fakt_ajrat = fakt_ajrat
database._biznes_kesh.clear()
database._biznes_kesh["c1"] = {
    "owner_id": EGASI, "owner_chat": DM, "yoqilgan": True, "rejim": "yordamchi",
    "ish_vaqti": None, "huquqlar": {"can_reply": True, "can_read_messages": True,
                                    "can_edit_bio": True, "can_edit_name": True}}

BOSH = {"mijozlar": 0, "xabarlar": 0, "javoblar": 0, "uzatish": 0, "loyiha": 0, "chatlar": {}}
TOLIQ = {"mijozlar": 2, "xabarlar": 5, "javoblar": 3, "uzatish": 1, "loyiha": 0,
         "chatlar": {9001: [("user", "atirgul bormi?"), ("assistant", "bor")],
                     9002: [("user", "tel: 90 123 45 67")]}}

# ── 3-4. Hisobot ─────────────────────────────────────────────────
holat["hisob"] = BOSH
q.clear()
asyncio.run(b._hisobot(EGASI, DM))
check(3, "bo'sh kun: hisobot ham, model ham yo'q",
      not [x for x in q if x[0] in ("send", "xulosa")])

holat["band"] = False
holat["hisob"] = TOLIQ
q.clear()
asyncio.run(b._hisobot(EGASI, DM))
check(4, "bugun allaqachon yuborilgan (egallash yutqazdi) -> hech narsa",
      [x[0] for x in q] == ["band"])
holat["band"] = True

holat["xulosa"] = {"xulosa": "Ikki mijoz <b>atirgul</b> so'radi.", "mijozlar": [
    {"n": 2, "ism": "Vali", "telefon": "90 123 45 67", "qiziqish": "atirgul"},
    {"n": True, "ism": "SOXTA"},                     # bool — int emas
    {"n": 3, "ism": "BEGONA"},                       # ro'yxatdan tashqarida
    {"n": "1", "ism": "SATR"},                       # satr
    "buzuq",
]}
holat["javobsiz"] = [{"chat_id": 9002, "owner_id": EGASI, "content": "tel: 90 123 45 67",
                      "tg_ism": "Vali", "username": None}]
q.clear()
asyncio.run(b._hisobot(EGASI, DM))
yuborilgan = [x for x in q if x[0] == "send"]
kartoteka = [x for x in q if x[0] == "kartoteka"]
check(5, "ertalabki hisobot EGASIGA YUBORILMAYDI (egasi, 2026-10-03), kartoteka to'ladi",
      yuborilgan == [] and kartoteka)
check(6, "kartoteka: faqat ro'yxatdagi to'g'ri `n` yoziladi (bool/satr/begona rad)",
      kartoteka == [("kartoteka", 9002, "Vali", "90 123 45 67", "atirgul")])
check(7, "hisobot tokeni biznes deb belgilanadi, mini model BIR marta",
      holat["manba"] == [True] and [x[0] for x in q].count("xulosa") == 1)

holat["xulosa"] = {}
q.clear()
asyncio.run(b._hisobot(EGASI, DM))
check(8, "model bo'sh qaytsa ham yiqilmaydi va hech narsa yuborilmaydi",
      not [x for x in q if x[0] == "send"])

# ── 9. «N daqiqadan beri javob kutmoqda» — O'CHIRILGAN ─────────────
# Egasi (2026-10-06): "butunlay olib tashla, kerak emas". Qaytib kelmasin:
# na funksiya, na kuzatuvchi, na main.py dagi ishga tushirish.
main_src = kod(os.path.join(ROOT, "main.py"))
check(9, "javob kutmoqda ogohlantirishi yo'q (funksiya, kuzatuvchi, main.py)",
      not hasattr(b, "javobsiz_tekshir") and not hasattr(b, "javobsiz_watcher")
      and "javobsiz_watcher" not in main_src
      and not hasattr(database, "biznes_javobsiz_belgila"))

# ── 14-15. /mijozlar va CSV ──────────────────────────────────────


async def mijozlar(owner, limit=1000):
    return [{"chat_id": 9001, "tg_ism": "=HYPERLINK(\"x\")", "username": "ali",
             "ism": "Ali", "telefon": "+998901234567", "qiziqish": "@SUM(1)",
             "oxirgi": datetime(2026, 9, 25, 5, 0, tzinfo=database.timezone.utc)}]

database.biznes_mijozlar = mijozlar
csv = asyncio.run(b._mijozlar_csv(EGASI)).decode("utf-8")
check(14, "CSV: BOM, formula in'eksiyasi bloklangan, vaqt Toshkentda",
      csv.startswith("﻿") and "'=HYPERLINK" in csv and "'@SUM" in csv
      and "2026-09-25 10:00" in csv)
check(15, "CSV yordamchisi bitta: web/api.py o'zi yozmaydi, umumiy moduldan oladi",
      "def _csv_katak" not in kod(os.path.join(ROOT, "web", "api.py"))
      and api._csv_katak("=1") == "'=1")

# ── 16-21. Profil: tasdiqsiz hech narsa ──────────────────────────


class SoxtaState:
    def __init__(self, data):
        self.data, self.tozalandi = dict(data), False

    async def get_data(self):
        return dict(self.data)

    async def clear(self):
        self.tozalandi = True


javoblar = []


def xabar(matn, uid=EGASI):
    async def answer(t, **kw):
        javoblar.append((t, kw.get("reply_markup")))
    return NS(text=matn, caption=None, photo=None, from_user=NS(id=uid), answer=answer)


async def kvota(*a):
    return {"allowed": True, "unlimited": False}


async def gpt(chat_id, prompt, **kw):
    holat["manba"].append(ai.BIZNES_MANBA.get())
    yield "Mana bio:\nEng yangi gullar — har kuni, Chilonzorda. " * 1

b.get_gpt_reply = gpt
database.check_and_consume_quota = kvota
holat["manba"].clear()
q.clear()
javoblar.clear()
asyncio.run(b.process_profil(xabar("gul do'konim haqida"), SoxtaState({"tur": "bio"})))
token = next(iter(b._tasdiq))
check(16, "bio tayyorlandi: Telegram'ga HECH NARSA yozilmadi, faqat ko'rinish + tugma",
      not [x for x in q if x[0] in ("bio", "ism", "rasm", "metod")]
      and "Eng yangi gullar" in javoblar[0][0] and "Mana bio" not in javoblar[0][0]
      and javoblar[0][1].inline_keyboard[0][0].callback_data == f"bz:ok:{token}"
      and holat["manba"] == [True])

check(17, "begona egasi tasdiqlay olmaydi, egasining so'rovi esa saqlanadi",
      asyncio.run(b._tasdiqla(token, EGASI + 1)).startswith("Bu so'rov eskirgan")
      and token in b._tasdiq and not [x for x in q if x[0] == "bio"])


async def ikki_bosish():
    return await asyncio.gather(b._tasdiqla(token, EGASI), b._tasdiqla(token, EGASI))

javob = asyncio.run(ikki_bosish())
check(18, "tasdiqlangach bio yoziladi — ikki marta bosilsa ham BIR marta, ≤140 belgi",
      sum(j.startswith("✅") for j in javob) == 1
      and len([x for x in q if x[0] == "bio"]) == 1
      and len([x for x in q if x[0] == "bio"][0][2]) <= b.BIO_MAX)

b._tasdiq["eski"] = {"egasi": EGASI, "tur": "bio", "matn": "x", "vaqt": 0}
check(19, "1 soatdan eski tasdiq ishlamaydi",
      asyncio.run(b._tasdiqla("eski", EGASI)).startswith("Bu so'rov eskirgan"))

b._tasdiq["st"] = {"egasi": EGASI, "tur": "story", "rasm": b"x", "vaqt": 9e18}
check(20, "huquq yo'q (story) -> Telegram'ga yozilmaydi, qaysi huquq kerakligi aytiladi",
      "Hikoyalarni boshqarish" in asyncio.run(b._tasdiqla("st", EGASI))
      and not [x for x in q if x[0] == "metod"])

check(21, "ism: `Ism|Familiya`, familiyasiz ham; bo'sh -> None; bio bir qator",
      b.profil_matnini_tozala("ism", "Gulnora | Karimova\nortiqcha") == "Gulnora|Karimova"
      and b.profil_matnini_tozala("ism", "Gulnora") == "Gulnora|"
      and b.profil_matnini_tozala("ism", "") is None
      and "\n" not in b.profil_matnini_tozala("bio", "a\nb"))

# Rasm story o'lchamiga (1080x1920) keltiriladi, JPEG bo'ladi.
from PIL import Image                      # noqa: E402
png = io.BytesIO()
Image.new("RGB", (1024, 1536), "red").save(png, "PNG")
jpg = b._jpeg(png.getvalue(), (1080, 1920))
check(22, "story rasmi 1080x1920 JPEG", jpg[:2] == b"\xff\xd8"
      and Image.open(io.BytesIO(jpg)).size == (1080, 1920))

# ── 23-25. Panel va tokenlar ─────────────────────────────────────
check(23, "panel kartasi: ulush jami tokenga nisbatan, token yo'q -> None (0% emas)",
      api._biznes_kpi({"ulanishlar": 3, "sorovlar": 41, "token": 460_000,
                       "token_jami": 1_840_000})["ulush"] == 25
      and api._biznes_kpi({})["ulush"] is None)

manba = kod(os.path.join(ROOT, "db", "database.py"))
panel = manba.split("async def biznes_panel_stats", 1)[1].split("\nasync def ", 1)[0]
javobsiz = manba.split("async def biznes_javobsizlar", 1)[1].split("\nasync def ", 1)[0]
check(24, "SQL: SUM ::bigint (Decimal emas), make_interval, manba ustuni va indeks",
      panel.count("::bigint") == 2 and "manba = 'biznes'" in panel
      and "make_interval(mins => $1::int)" in javobsiz
      and "manba VARCHAR(20)" in manba
      and "chat_messages (created_at) WHERE thread_id < 0" in manba)

main = kod(os.path.join(ROOT, "main.py"))
check(25, "main.py: kartoteka kuzatuvchisi ishga tushadi, profil FSM AI'dan oldin, /mijozlar",
      "biznes_hisobot_watcher()" in main
      and main.index("process_profil") < main.index("register(handle_text")
      and 'Command("mijozlar")' in main)

# ── 26-30. Bilim o'zi to'plansin — TAKLIF, egasi tanlaydi (BIZNES.md) ──
JUFT = [{"id": 11, "mijoz_matni": "yetkazib berasizmi?", "yakuniy": "Ha, Toshkent bo'ylab 20 ming"},
        {"id": 12, "mijoz_matni": "menga chegirma bormi", "yakuniy": "Sizga 45 mingga beraman"},
        {"id": 13, "mijoz_matni": "shanba ishlaysizmi", "yakuniy": "Shanba 10 dan 18 gacha"}]
ft = b.fakt_takliflari
check(26, "model natijasi ishonchsiz: n chegarada, bool emas, bo'sh/karta yo'q, bitta juftga bitta",
      ft([{"n": 0, "savol": "a", "javob": "b"}, {"n": 4, "savol": "a", "javob": "b"},
          {"n": True, "savol": "a", "javob": "b"}, {"n": 1, "savol": "", "javob": "b"},
          {"n": 2, "savol": "karta?", "javob": "8600 1234 5678 9012"},
          # Jonli xato (eval_bilim): bilimdagi narx boshqa juftlikka bog'landi —
          # egasining 2-javobida «80 000» ham, «futbolka» ham yo'q: rad.
          {"n": 2, "savol": "futbolka necha pul?", "javob": "Futbolka 80 000 so'm"},
          {"n": 3, "savol": "shanba ishlaysizmi?", "javob": "10:00-18:00"},
          {"n": 3, "savol": "takror", "javob": "takror"}, "buzuq"], JUFT)
      == {13: {"savol": "shanba ishlaysizmi?", "javob": "10:00-18:00"}}
      and len(ft([{"n": 1, "savol": f"s{i}", "javob": "j"} for i in range(9)]
                 + [{"n": i, "savol": "s", "javob": "j"} for i in range(1, 4)], JUFT * 3)) <= 3)

# Jonli xatolar (eval_bilim, 2026-10-28) — prompt taqiqlasa ham model oldi:
VJ = [{"id": 21, "yakuniy": "Shu hafta hamma narsaga 10% chegirma"},
      {"id": 22, "yakuniy": "Ertaga kechgacha olib boramiz"},
      {"id": 23, "yakuniy": "80 ming"},
      {"id": 24, "yakuniy": "Chilonzor 9-kvartal, Korzinka yonida"}]
check(31, "vaqtli («shu hafta», «ertaga») va bilimda bor («80 ming» = «80 000») — rad; yangi — o'tadi",
      ft([{"n": 1, "savol": "chegirma bormi?", "javob": "hamma narsaga 10% chegirma"},
          {"n": 2, "savol": "qachon keladi?", "javob": "kechgacha olib boramiz"},
          {"n": 3, "savol": "futbolka necha pul?", "javob": "80 ming"},
          {"n": 4, "savol": "manzil?", "javob": "Chilonzor 9-kvartal"}],
         VJ, "Futbolka 80 000 so'm.")
      == {24: {"savol": "manzil?", "javob": "Chilonzor 9-kvartal"}})

# Kunlik tahlil: juftlik bor, model 2 fakt topdi → BITTA xabar, har biriga tugma.
holat.update(juftlar=JUFT, hisob=BOSH, band=True,
             faktlar=[{"n": 1, "savol": "yetkazib berish bormi?", "javob": "Toshkent bo'ylab, 20 000 so'm"},
                      {"n": 3, "savol": "shanba ishlaysizmi?", "javob": "10:00-18:00"}])
holat["manba"].clear()
q.clear()
asyncio.run(b._hisobot(EGASI, DM))
yub = [x for x in q if x[0] == "send"]
belg = [x for x in q if x[0] == "belgila"]
tugmalar = [r[0].callback_data for r in yub[0][3].inline_keyboard] if yub else []
check(27, "fakt topilsa — bitta xabar, har faktga «✅ Qo'shish»; bilimga O'ZI yozilmaydi",
      len(yub) == 1 and "«yetkazib berish bormi?»" in yub[0][2] and "45" not in yub[0][2]
      and tugmalar == ["bz:fq:11", "bz:fq:13"]
      and not [x for x in q if x[0] == "bilim_yoz"]
      and holat["manba"] == [True])
check(28, "ko'rilgan HAMMA juftlik belgilanadi (faktsizi None) — ertaga qayta kelmaydi",
      len(belg) == 1 and set(belg[0][2]) == {11, 12, 13} and belg[0][2][12] is None
      and belg[0][2][13] == {"savol": "shanba ishlaysizmi?", "javob": "10:00-18:00"})

holat.update(juftlar=[])
q.clear()
asyncio.run(b._hisobot(EGASI, DM))
check(29, "juftlik yo'q — model chaqirilmaydi, xabar yo'q (kunlik shovqin emas)",
      not [x for x in q if x[0] in ("fakt_model", "send")])

# «✅ Qo'shish» — FAQAT shunda bilimga tushadi; begona yoki ko'rilmagan — yo'q.
holat["loyiha"] = {(13, EGASI): {"fakt_taklif": {"savol": "shanba ishlaysizmi?", "javob": "10:00-18:00"}},
                   (12, EGASI): {"fakt_taklif": {}}}
q.clear()
ok = asyncio.run(b._fakt_taklif_saqla(13, EGASI))
yozildi = [x for x in q if x[0] == "bilim_yoz"]
check(30, "«✅ Qo'shish» — bilim oxiriga «savol» → javob; faktsiz/begona — yozilmaydi",
      ok.startswith("✅") and yozildi and "- «shanba ishlaysizmi?» → 10:00-18:00" in yozildi[0][2]
      and b.FAKT_SARLAVHA in yozildi[0][2]
      and not asyncio.run(b._fakt_taklif_saqla(12, EGASI)).startswith("✅")
      and not asyncio.run(b._fakt_taklif_saqla(13, EGASI + 1)).startswith("✅"))

print("\nHammasi o'tdi.")
