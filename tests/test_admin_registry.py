"""Admin panel: ro'yxatdan o'tgan handlerlar TO'LIQ va TARTIBDA.

Bu — avval `handlers/admin.py` ni fayllarga bo'lish uchun xavfsizlik
to'ri edi. 7-bosqichdan keyin u ikkinchi ish ham qiladi: **webga
ko'chgan ekran botga qaytib kelmasligini** qo'riqlaydi. Ikki joyda
turgan bitta ekran — bu loyihada bir necha marta takrorlangan naqsh
(ACTIVITY_LABELS, ACTION_LABELS, LIMIT_KEYS, segment_nom), va uning
eng qimmat ko'rinishi aynan shu: admin botdan limitni o'zgartiradi,
panel esa boshqa raqam ko'rsatadi.

Tartib ham funksional talab — FSM holatlari buyruq handlerlaridan
keyin turishi kerak, aks holda admin biror holatda qolib ketadi.

Ishga tushirish:  PYTHONIOENCODING=utf-8 python tests/test_admin_registry.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _manba import kod

from handlers import admin as admin_module  # noqa: E402


class _Recorder:
    def __init__(self, bucket, kind):
        self._bucket = bucket
        self._kind = kind

    def register(self, handler, *filters, **kwargs):
        self._bucket.append((self._kind, getattr(handler, "__name__", "?"),
                             len(filters)))


class _FakeDp:
    def __init__(self):
        self.calls: list = []
        self.message = _Recorder(self.calls, "message")
        self.callback_query = _Recorder(self.calls, "callback")


dp = _FakeDp()
admin_module.register_admin_handlers(dp, object())

# Botda QOLGANLARI (REJA 2): tarqatma, promokod/referal yuborish, report.
# Boshqa hamma narsa web panelda.
KUTILGAN = [
    # Kirish nuqtalari — endi BUYRUQ, matnli tugma emas.
    ("message", "start_broadcast", 1),
    ("message", "show_giveaway_menu", 1),
    # FSM: tugma va oluvchi holatlari waiting_for_content dan OLDIN.
    ("message", "process_broadcast_schedule", 1),
    ("message", "process_broadcast_button", 1),
    ("message", "process_broadcast_recipients", 1),
    ("message", "capture_broadcast_content", 1),
    ("message", "process_promo_recipients", 1),
    ("message", "process_ref_recipients", 1),
    ("message", "process_report_message", 1),
    ("callback", "report_callback", 1),
    ("callback", "broadcast_button_add_callback", 1),
    ("callback", "broadcast_button_del_callback", 1),
    ("callback", "broadcast_color_callback", 1),
    ("callback", "broadcast_preview_callback", 1),
    ("callback", "broadcast_next_callback", 1),
    ("callback", "broadcast_segment_callback", 1),
    ("callback", "broadcast_confirm_send_callback", 1),
    ("callback", "broadcast_abort_callback", 1),
    ("callback", "broadcast_cancel_send_callback", 1),
    ("callback", "broadcast_later_callback", 1),
    ("callback", "giveaway_callback", 1),
]

if dp.calls != KUTILGAN:
    yoq = [c for c in KUTILGAN if c not in dp.calls]
    ortiqcha = [c for c in dp.calls if c not in KUTILGAN]
    print(f"Kutilgan: {len(KUTILGAN)} ta, topilgan: {len(dp.calls)} ta")
    if yoq:
        print("YO'QOLGAN:", yoq)
    if ortiqcha:
        print("ORTIQCHA:", ortiqcha)
    if not yoq and not ortiqcha:
        print("TARTIB o'zgargan:")
        for i, (a, b) in enumerate(zip(KUTILGAN, dp.calls)):
            if a != b:
                print(f"  {i}: kutilgan {a}, topilgan {b}")
                break
    raise AssertionError("admin handlerlari ro'yxati o'zgargan")

print(f"[1] {len(dp.calls)} ta handler ro'yxatdan o'tdi, tartib to'g'ri OK")

# ── 2. WEBGA KO'CHGANI BOTGA QAYTMASIN ───────────────────────────
# ⚠️ Yuqoridagi ro'yxat o'zi ham buni ushlaydi, lekin XATO XABARI
# tushunarsiz bo'lardi («ORTIQCHA: show_maintenance_menu»). Bu yerda
# sabab aytiladi: bu ekran o'chirilgan emas — u KO'CHGAN, va uni
# qaytarish ikki joyda ikki xil sozlama demakdir.
KOCHGAN = {
    "handle_users_command": "Statistika → /api/stats",
    "handle_top": "Faol foydalanuvchilar → /api/stats",
    "handle_users_list": "Userlar ro'yxati → /api/users",
    "start_manage_user": "Foydalanuvchini boshqarish → /api/users/{id}",
    "manage_user_action_callback": "Foydalanuvchi amallari → /api/users/{id}/*",
    "users_list_page_callback": "Ro'yxat sahifalash → /api/users",
    "show_journal_menu": "Jurnal → /api/journal/*",
    "journal_callback": "Jurnal tugmalari → /api/journal/*",
    "process_limit_value": "Limit o'zgartirish → POST /api/limits",
    "show_maintenance_menu": "Texnik ta'til → /api/maintenance",
    "maintenance_toggle_callback": "Ta'til kalitchasi → POST /api/maintenance",
    "process_maintenance_message": "Ta'til matni → POST /api/maintenance",
    "show_watch_menu": "Kuzatish → /api/watch",
    "watch_menu_callback": "Kuzatish tugmalari → POST /api/watch",
    "process_watch_group_id": "Kuzatuv guruhi → POST /api/watch",
    "process_watch_identifier": "Kuzatuvga qo'shish → POST /api/watch",
    "start_add_admin": "Admin qo'shish → POST /api/admins",
    "process_add_admin": "Admin qo'shish → POST /api/admins",
    "start_remove_admin": "Admin o'chirish → POST /api/admins",
    "process_remove_admin": "Admin o'chirish → POST /api/admins",
    "remove_admin_callback": "Admin o'chirish → POST /api/admins",
    "process_promo_create": "Kod yaratish → POST /api/promo",
    "promo_admin_callback": "Kodlar ro'yxati → /api/promo",
    "show_referral_settings": "Referal sharti → /api/referral",
    "process_referral_count": "Referal sharti → POST /api/referral",
    "process_referral_days": "Referal sharti → POST /api/referral",
    "process_referral_user": "Referal sharti → POST /api/referral",
    "referral_scope_callback": "Referal sharti → POST /api/referral",
    "show_users_menu": "Inline menyu — reply-klaviatura bilan birga ketdi",
    "show_settings_menu": "Inline menyu — reply-klaviatura bilan birga ketdi",
    "menu_callback": "Inline menyu — reply-klaviatura bilan birga ketdi",
}
nomlar = {c[1] for c in dp.calls}
qaytgan = sorted(nomlar & set(KOCHGAN))
assert not qaytgan, "\n".join(
    [f"Webga ko'chgan ekran botga qaytarilgan — ikki joyda ikki xil "
     f"sozlama bo'ladi:"] + [f"  • {n}: {KOCHGAN[n]}" for n in qaytgan])
print(f"[2] webga ko'chgan {len(KOCHGAN)} ta ekrandan bittasi ham qaytmagan OK")

# ── 3. KIRISH NUQTASI BUYRUQ, MATNLI TUGMA EMAS ──────────────────
# ⚠️ Reply-klaviatura o'chirildi, ya'ni `F.text == '📢 Xabar yuborish'`
# ga bog'langan handler endi HECH QACHON ishga tushmasdi: tugma yo'q,
# admin esa matnni qo'lda yozmaydi. Bu jimgina buziladigan xato —
# handler ro'yxatda turadi, lekin o'lik.
import pathlib  # noqa: E402
import re  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
src = kod(ROOT / "handlers" / "admin" / "__init__.py")
assert "F.text ==" not in src, (
    "matnli tugmaga bog'langan handler qolgan — klaviatura yo'q, u o'lik")
buyruqlar = set(re.findall(r'Command\("(\w+)"\)', src))
assert buyruqlar == {"xabar", "kod"}, buyruqlar
# Panel ham, `/start` ham aynan shu ikki buyruqni nomlaydi — nom
# o'zgarsa uchala joy birdan yangilanishi kerak.
msgs = kod(ROOT / "handlers" / "messages.py")
for b in buyruqlar:
    assert f"/{b}" in msgs, f"/start adminlarga /{b} haqida aytmaydi"
html = (ROOT / "web" / "static" / "panel.html").read_text(encoding="utf-8")
assert "/xabar" in html, "panel tarqatma uchun /xabar ni ko'rsatmaydi"
print(f"[3] kirish nuqtasi {sorted(buyruqlar)} buyruqlari, matnli tugma yo'q OK")

# ── 4. ESKI KLAVIATURA TOZALANADI ────────────────────────────────
# ⚠️ Reply-klaviatura adminning telefonida QOLIB KETADI: Telegram uni
# almashtirilgunicha yoki ochiq o'chirilgunicha ko'rsataveradi. Ya'ni
# `ReplyKeyboardRemove` bo'lmasa admin ishlamaydigan to'rtta tugmani
# bosib, hech qanday javob olmasdi va buni «bot buzildi» deb tushunardi.
assert "ReplyKeyboardRemove()" in msgs, (
    "eski reply-klaviatura tozalanmaydi — adminda o'lik tugmalar qoladi")
assert not (ROOT / "core" / "keyboards.py").exists(), (
    "core/keyboards.py qaytib kelgan")
print("[4] eski reply-klaviatura /start da tozalanadi OK")

# Testlar va tashqi kod import qiladigan nomlar joyida turibdimi.
for nom in ("parse_button_spec", "build_bcast_keyboard", "BCAST_STYLES",
            "BCAST_MAX_BUTTONS", "_is_markup_error",
            "register_admin_handlers"):
    assert hasattr(admin_module, nom), f"«{nom}» handlers.admin dan yo'qolgan"
print("[5] tashqi kod import qiladigan nomlar joyida OK")

print("\nHammasi o'tdi: 5/5")
