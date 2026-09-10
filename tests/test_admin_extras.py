"""Admin panelning yangi bo'limlari: limitlar, hisobot, jurnal, rejali tarqatma.

DB kerak bo'lgan joylar soxta funksiya bilan almashtiriladi — bu yerda
SQL emas, mantiq tekshiriladi (raqamlar to'g'ri joyga tushishi, limit
o'zgartirishi haqiqatan ta'sir qilishi, ekran matni buzilmasligi).

Ishga tushirish:  PYTHONIOENCODING=utf-8 python tests/test_admin_extras.py
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import config  # noqa: E402
from db import database as db  # noqa: E402
from handlers.admin import journal, daily  # noqa: E402


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


# ── 1. Limit o'zgartirish HAQIQATAN ta'sir qiladi ────────────────
# `daily_limit()` — limitning yagona o'qish nuqtasi: kvota ham, admin
# ekrani ham shundan oladi. Override ishlamasa, panel "o'zgardi" deb
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

# `premium` cheksiz — u ekranda umuman ko'rsatilmaydi.
check(6, "cheksiz tarif limit ekranida yo'q", "premium" not in journal.LIMIT_PLANS)


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


# ── 3. Jurnal ekranlari (DB soxta) ───────────────────────────────
async def _sinov_ekranlar():
    yozuv = {
        "id": 1, "admin_id": 5, "action": "ban", "target_user_id": 9,
        "details": "sabab: spam", "action_time": datetime.now(timezone.utc),
        "admin_username": "boss", "target_username": "spammer",
    }
    db.get_admin_audit = lambda *a, **k: _q([yozuv])
    db.count_admin_audit = lambda *a, **k: _q(1)
    matn, kb = await journal._render_audit(0)
    check(12, "audit yozuvi o'qiladigan ko'rinishda",
          "🚫 Ban" in matn and "@boss" in matn and "@spammer" in matn)
    check(13, "audit ekranida orqaga tugmasi bor",
          any("jr:menu" in b.callback_data for row in kb.inline_keyboard for b in row))

    db.recent_errors = lambda *a, **k: _q([{
        "id": 1, "kind": "timeout", "message": "<script>x</script>",
        "user_id": 7, "created_at": datetime.now(timezone.utc)}])
    db.error_summary = lambda *a, **k: _q(
        {"day": 2, "week": 5, "total": 5, "users_day": 1, "kinds": [("timeout", 5)]})
    matn, _ = await journal._render_errors(0)
    # Xato matni foydalanuvchi yozganidan kelib chiqishi mumkin —
    # HTML qochirilmasa butun xabar Telegram tomonidan rad etiladi.
    check(14, "xato matni HTML sifatida qochiriladi",
          "&lt;script&gt;" in matn and "<script>" not in matn)

    db.revenue_stats = lambda *a, **k: _q({
        "stars_today": 100, "stars_30d": 900, "stars_total": 5000,
        "sales_30d": 9, "refunds": 1, "by_plan": [(30, 7), (90, 2)]})
    matn, _ = await journal._render_revenue()
    check(15, "o'rtacha chek to'g'ri hisoblanadi", "100.0" in matn)
    check(16, "qaytarilganlar ko'rsatiladi", "Qaytarilgan" in matn)

    db.get_limit_overrides = lambda *a, **k: _q({"free": {"points": 500}})
    matn, kb = await journal._render_limits()
    check(17, "o'zgartirilgan limit yulduzcha bilan belgilanadi", "500" in matn and "⭐" in matn)
    check(18, "har bir limit uchun tugma bor",
          sum(1 for row in kb.inline_keyboard for b in row
              if b.callback_data.startswith("jr:lim:")) == 8)


def _q(value):
    async def _inner():
        return value
    return _inner()


asyncio.run(_sinov_ekranlar())


# ── 4. HIMOYA HAMMA JOYDA BIR XIL KO'RINISHDA ────────────────────
# ⚠️ `remove_admin_callback` da qo'riqchi qatori YO'Q edi. Amalda teshik
# ham yo'q edi — himoya `_check_can_remove_admin()` ichida, BOSHQACHA
# yo'l bilan qilingan edi. Lekin yagona joyda boshqacha qilingan himoya
# xavfli: o'sha funksiya kelajakda o'zgarsa, teshik JIMGINA ochilardi va
# buni hech kim payqamasdi.
import pathlib  # noqa: E402
import re  # noqa: E402

ADMIN_DIR = pathlib.Path(__file__).resolve().parent.parent / "handlers" / "admin"
# ⚠️ Bular ATAYLAB ochiq — oddiy foydalanuvchi ham ishlatadi
# (CLAUDE.md: admin tekshiruvi filtrda emas, har bir handler ichida).
OCHIQ = {"report_callback", "process_report_message",
         "require_admin_or_deny_query"}

# `_` bilan boshlanadigan nom — ichki yordamchi, u ro'yxatdan O'TMAYDI va
# qo'riqlangan handler ichidan chaqiriladi (`_confirm_screen`,
# `_show_user_payments`, `_do_refund` — uchalasi tekshirildi). Ro'yxatga
# tushishi mumkin bo'lgan KIRISH nuqtalari `_` siz nomlanadi; agar
# kimdir `_` li funksiyani register qilsa, buni test_admin_registry
# ushlaydi.
qo_riqsiz = []
for fayl in sorted(ADMIN_DIR.glob("*.py")):
    src = fayl.read_text(encoding="utf-8")
    for m in re.finditer(r"^async def (\w+)\(query: CallbackQuery", src, re.M):
        nom = m.group(1)
        if nom in OCHIQ or nom.startswith("_"):
            continue
        if "require_admin_or_deny_query" not in src[m.end():m.end() + 700]:
            qo_riqsiz.append(f"{fayl.name}::{nom}")

check(19, f"har bir admin callback qo'riqlangan ({len(OCHIQ)} tasi ataylab ochiq)",
      not qo_riqsiz)

# ── 5. IKKI SO'ROV BIR XIL TO'PLAMNI SANAYDI ─────────────────────
# Ekranda "jami 100 user" turib, free + pro + premium = 103 chiqardi:
# biri adminlarni chiqarardi, ikkinchisi yo'q. Admin raqamlarga
# ishonmay qo'ysa, butun statistika ekranining ma'nosi qolmaydi.
_stats = (ADMIN_DIR / "stats.py").read_text(encoding="utf-8")
_tana = _stats.split("async def handle_users_command")[1].split("async def ")[0]
check(20, "jami va tarif bo'yicha sanoq bir xil to'plamni sanaydi",
      _tana.count("NOT IN (SELECT user_id FROM admins)") >= 4)

print("\nHammasi o'tdi: 20/20")
