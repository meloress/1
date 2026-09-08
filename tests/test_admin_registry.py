"""Admin panel: ro'yxatdan o'tgan handlerlar TO'LIQ va TARTIBDA.

Bu — `handlers/admin.py` ni fayllarga bo'lish uchun xavfsizlik to'ri.
Bo'lishdan OLDIN va KEYIN bir xil natija berishi shart: bitta handler
ham yo'qolmasligi, tartib ham o'zgarmasligi kerak (tartib bu yerda
funksional talab — FSM holatlari tugma handlerlaridan keyin turishi
kerak, aks holda admin promokod holatida qolib ketadi).

Ishga tushirish:  PYTHONIOENCODING=utf-8 python tests/test_admin_registry.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
KUTILGAN = [
    ("message", "start_broadcast", 1),
    ("message", "handle_top", 1),
    ("message", "handle_users_command", 1),
    ("message", "handle_users_list", 1),
    ("message", "start_add_admin", 1),
    ("message", "start_remove_admin", 1),
    ("message", "start_manage_user", 1),
    ("message", "show_maintenance_menu", 1),
    ("message", "show_watch_menu", 1),
    ("message", "show_giveaway_menu", 1),
    ("message", "show_referral_settings", 1),
    ("message", "process_referral_count", 1),
    ("message", "process_referral_days", 1),
    ("message", "process_referral_user", 1),
    ("callback", "referral_scope_callback", 1),
    ("message", "process_broadcast_button", 1),
    ("message", "process_broadcast_recipients", 1),
    ("message", "capture_broadcast_content", 1),
    ("message", "process_manage_user_identifier", 1),
    ("message", "process_add_admin", 1),
    ("message", "process_remove_admin", 1),
    ("message", "process_maintenance_message", 1),
    ("message", "process_watch_group_id", 1),
    ("message", "process_watch_identifier", 1),
    ("message", "process_promo_create", 1),
    ("message", "process_promo_recipients", 1),
    ("message", "process_ref_recipients", 1),
    ("message", "process_report_message", 1),
    ("callback", "remove_admin_callback", 1),
    ("callback", "report_callback", 1),
    ("callback", "manage_user_action_callback", 1),
    ("callback", "broadcast_button_add_callback", 1),
    ("callback", "broadcast_button_del_callback", 1),
    ("callback", "broadcast_color_callback", 1),
    ("callback", "broadcast_preview_callback", 1),
    ("callback", "broadcast_next_callback", 1),
    ("callback", "broadcast_segment_callback", 1),
    ("callback", "broadcast_confirm_send_callback", 1),
    ("callback", "broadcast_abort_callback", 1),
    ("callback", "broadcast_cancel_send_callback", 1),
    ("callback", "users_list_page_callback", 1),
    ("callback", "maintenance_toggle_callback", 1),
    ("callback", "watch_menu_callback", 1),
    ("callback", "promo_admin_callback", 1),
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

# Testlar va tashqi kod import qiladigan nomlar joyida turibdimi.
for nom in ("parse_button_spec", "build_bcast_keyboard", "BCAST_STYLES",
            "BCAST_MAX_BUTTONS", "_is_markup_error",
            "register_admin_handlers"):
    assert hasattr(admin_module, nom), f"«{nom}» handlers.admin dan yo'qolgan"
print("[2] tashqi kod import qiladigan nomlar joyida OK")

print("\nHammasi o'tdi: 2/2")
