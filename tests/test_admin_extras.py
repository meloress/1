"""Limitlar va kunlik hisobot — botda qolgan mantiq.

⚠️ Bu faylda ILGARI jurnal ekranlarining (audit, xatolar, daromad,
limit tugmalari) tekshiruvlari ham bor edi. 7-bosqichda o'sha ekranlar
webga ko'chdi va bu yerdan o'chirildi — ularning o'rnini
`tests/test_web_journal.py` va `tests/test_web_settings.py` egalladi.
Ikki joyda bir xil narsani tekshirish qo'riqchi emas, yuk.

Qolgani ATAYLAB qoldi:
  * 1-6 — `daily_limit()` limitning YAGONA o'qish nuqtasi ekani. Bu
    config mantig'i, hech qaysi ekranga tegishli emas: kvota ham,
    fayl sanoqlari ham, panel ham shundan oladi.
  * 7-11 — kunlik hisobot matni. Hisobot botda qoladi (REJA 2): u
    push, ya'ni panelga kirmasdan keladi.
  * 12-13 — tuzilish qo'riqchilari.

Ishga tushirish:  PYTHONIOENCODING=utf-8 python tests/test_admin_extras.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _manba import kod

from core import config  # noqa: E402
from handlers.admin import daily  # noqa: E402


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


# ── 1. Limit o'zgartirish HAQIQATAN ta'sir qiladi ────────────────
# `daily_limit()` — limitning yagona o'qish nuqtasi: kvota ham, admin
# paneli ham shundan oladi. Override ishlamasa, panel "o'zgardi" deb
# ko'rsatib, aslida eski limit ishlab turardi.
asl_free = config.daily_limit("free", "points")
config.apply_limit_overrides({"free": {"points": 77}})
check(1, "o'zgartirilgan limit kuchga kiradi",
      config.daily_limit("free", "points") == 77)
check(2, "boshqa tarif tegilmaydi",
      config.daily_limit("pro", "points") == config.PLAN_LIMITS["pro"]["points"])
check(3, "o'zgartirilmagan sanoq config'dan olinadi",
      config.daily_limit("free", "files") == config.PLAN_LIMITS["free"]["files"])

config.apply_limit_overrides({})
check(4, "o'zgartirish olib tashlansa asl qiymat qaytadi",
      config.daily_limit("free", "points") == asl_free)

# Noto'g'ri qiymat (matn, bool) e'tiborga olinmaydi — bazaga qo'lda
# yozilgan axlat butun kvotani buzmasligi kerak.
config.apply_limit_overrides({"free": {"points": "juda ko'p", "files": True}})
check(5, "yaroqsiz qiymat e'tiborsiz qoldiriladi",
      config.daily_limit("free", "points") == asl_free)
config.apply_limit_overrides({})

# `premium` cheksiz — u o'zgartirish jadvalida umuman ko'rsatilmaydi.
# ⚠️ Manba ko'chdi: ilgari `handlers/admin/journal.py::LIMIT_PLANS` edi,
# endi web panelning `LIMIT_TARIFLARI` si — jadval faqat o'sha yerda.
os.environ.setdefault("BOT_TOKEN", "123456:TEST-TOKEN-FOR-ADMIN-EXTRAS")
from web import api as web_api  # noqa: E402
check(6, "cheksiz tarif limit jadvalida yo'q",
      "premium" not in web_api.LIMIT_TARIFLARI)


# ── 2. Kunlik hisobot matni ──────────────────────────────────────
stats = {
    "new_users": 12, "total_users": 340, "active_users": 87, "actions": 512,
    "sales": 3, "stars": 300, "errors": 0, "pro_users": 25,
    "top_types": [("text_message", 400), ("file_task", 12)],
}
matn = daily.build_report(stats)
check(7, "hisobotda asosiy raqamlar bor",
      "12" in matn and "340" in matn and "300" in matn and "25" in matn)
check(8, "faoliyat turi o'zbekcha nom bilan chiqadi",
      "matn" in matn and "fayl yaratish" in matn)
# Xato bo'lmasa qator umuman chiqmaydi — har kuni "0 ta xato" deb
# takrorlanish muhim qatorlarni ko'zdan yashiradi.
check(9, "xato yo'q bo'lsa xato qatori chiqmaydi", "Xatolar" not in matn)
check(10, "xato bo'lsa chiqadi",
      "Xatolar" in daily.build_report({**stats, "errors": 4}))
check(11, "bo'sh ma'lumotda ham yiqilmaydi", daily.build_report({}))


# ── 3. HIMOYA HAMMA JOYDA BIR XIL KO'RINISHDA ────────────────────
# ⚠️ `remove_admin_callback` da qo'riqchi qatori YO'Q edi. Amalda teshik
# ham yo'q edi — himoya `_check_can_remove_admin()` ichida, BOSHQACHA
# yo'l bilan qilingan edi. Lekin yagona joyda boshqacha qilingan himoya
# xavfli: o'sha funksiya kelajakda o'zgarsa, teshik JIMGINA ochilardi.
# (O'sha ekran endi webda, qoida esa `common.py` da — ikkala ekran ham
# aynan o'sha funksiyani chaqiradi.)
import pathlib  # noqa: E402
import re  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
ADMIN_DIR = ROOT / "handlers" / "admin"
# ⚠️ Bular ATAYLAB ochiq — oddiy foydalanuvchi ham ishlatadi
# (CLAUDE.md: admin tekshiruvi filtrda emas, har bir handler ichida).
OCHIQ = {"report_callback", "process_report_message",
         "require_admin_or_deny_query"}

qo_riqsiz = []
topilgan = 0
for fayl in sorted(ADMIN_DIR.glob("*.py")):
    src = kod(fayl)
    for m in re.finditer(r"^async def (\w+)\(query: CallbackQuery", src, re.M):
        nom = m.group(1)
        if nom in OCHIQ or nom.startswith("_"):
            continue
        topilgan += 1
        if "require_admin_or_deny_query" not in src[m.end():m.end() + 700]:
            qo_riqsiz.append(f"{fayl.name}::{nom}")

check(12, f"har bir admin callback qo'riqlangan ({topilgan} ta tekshirildi)",
      not qo_riqsiz and topilgan >= 10)

# ── 4. IKKI SO'ROV BIR XIL TO'PLAMNI SANAYDI ─────────────────────
# Ekranda "jami 100 user" turib, free + pro + premium = 103 chiqardi:
# biri adminlarni chiqarardi, ikkinchisi yo'q. Admin raqamlarga
# ishonmay qo'ysa, butun statistika ekranining ma'nosi qolmaydi.
#
# ⚠️ Shart qo'lda takrorlanmaydi — `_ODDIY_USER` o'zgaruvchisida turadi
# va kerak joyga qo'yiladi, ya'ni "bittasida bor, ikkinchisida yo'q"
# holati tuzilish jihatidan imkonsiz. Test shu tuzilishni qo'riqlaydi.
_db = kod(ROOT / "db" / "database.py")
_fn = _db.split("async def activity_stats")[1].split("\nasync def ")[0]
check(13, "jami va tarif bo'yicha sanoq bir xil to'plamni sanaydi",
      "_ODDIY_USER = " in _db
      and _db.count("NOT IN (SELECT user_id FROM admins)") == 1
      and _fn.count("{_ODDIY_USER}") >= 4)

print("\nHammasi o'tdi: 13/13")
