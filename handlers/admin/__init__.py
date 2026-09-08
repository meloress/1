"""Admin panel — handlerlarni ro'yxatdan o'tkazish.

⚠️ RO'YXAT TARTIBI FUNKSIONAL TALAB, bezak emas:
  * FSM holatlari tugma handlerlaridan KEYIN — aks holda admin
    promokod holatida qolib, boshqa tugmalarni bosa olmaydi;
  * `waiting_for_button` va `waiting_for_recipients`
    `waiting_for_content` dan OLDIN — konstruktor ochiq turganda
    admin yozgan matn "yangi kontent" bo'lib ketmasligi kerak.

tests/test_admin_registry.py bu tartibni qo'riqlaydi.
"""

from aiogram import F

from handlers.admin.broadcast import (
    BroadcastStates, broadcast_abort_callback,
    broadcast_button_add_callback, broadcast_button_del_callback,
    broadcast_cancel_send_callback, broadcast_color_callback,
    broadcast_confirm_send_callback, broadcast_next_callback,
    broadcast_preview_callback, broadcast_segment_callback,
    capture_broadcast_content, process_broadcast_button,
    process_broadcast_recipients, start_broadcast,
)
from handlers.admin.promo import (
    GiveawayStates, PromoAdminStates, ReferralStates, giveaway_callback,
    process_promo_create, process_promo_recipients, process_ref_recipients,
    process_referral_count, process_referral_days, process_referral_user,
    promo_admin_callback, referral_scope_callback, show_giveaway_menu,
    show_referral_settings,
)
from handlers.admin.users import (
    ManageUserStates, handle_users_list, manage_user_action_callback,
    process_manage_user_identifier, start_manage_user,
    users_list_page_callback,
)
from handlers.admin.stats import (
    handle_top, handle_users_command,
)
from handlers.admin.system import (
    AddAdminStates, MaintenanceStates, RemoveAdminStates, ReportStates,
    WatchStates, maintenance_toggle_callback, process_add_admin,
    process_maintenance_message, process_remove_admin,
    process_report_message, process_watch_group_id,
    process_watch_identifier, remove_admin_callback, report_callback,
    show_maintenance_menu, show_watch_menu, start_add_admin,
    start_remove_admin, watch_menu_callback,
)

# ⚠️ tests/test_broadcast.py shu nomlarni `handlers.admin` dan import
# qiladi — bo'lishdan keyin ham o'sha joyda turishi kerak.
from handlers.admin.broadcast import (          # noqa: F401
    parse_button_spec, build_bcast_keyboard, BCAST_STYLES,
    BCAST_MAX_BUTTONS, _is_markup_error,
)


def register_admin_handlers(dp, bot=None):
    """Admin handlerlarini ro'yxatdan o'tkazadi.

    `bot` ATAYLAB ishlatilmaydi: modullar uni `core.loader` dan
    to'g'ridan-to'g'ri oladi (handlers/messages.py bilan bir xil).
    Parametr `main.py` ni o'zgartirmaslik uchun qoldirilgan.
    """
    dp.message.register(start_broadcast, F.text == '📢 Xabar yuborish')
    dp.message.register(handle_top, F.text == '🏆 Faol foydalanuvchilar')
    dp.message.register(handle_users_command, F.text == '📊 Statistika')
    dp.message.register(handle_users_list, F.text == "📄 Userlar ro'yxati")
    dp.message.register(start_add_admin, F.text == "➕ Admin qo'shish")
    dp.message.register(start_remove_admin, F.text == "➖ Admin o'chirish")
    dp.message.register(start_manage_user, F.text == "🔍 Foydalanuvchini boshqarish")
    dp.message.register(show_maintenance_menu, F.text == "🛠 Texnik ta'til")
    dp.message.register(show_watch_menu, F.text == "👁 Kuzatish")
    dp.message.register(show_giveaway_menu, F.text == "🎁 Bepul Pro")
    dp.message.register(show_referral_settings, F.text == "👥 Referal sharti")
    dp.message.register(process_referral_count, ReferralStates.waiting_for_count)
    dp.message.register(process_referral_days, ReferralStates.waiting_for_days)
    dp.message.register(process_referral_user, ReferralStates.waiting_for_user)
    dp.callback_query.register(referral_scope_callback,
                               lambda q: q.data and q.data.startswith("refset:"))
    # ⚠️ TARTIB: tugma va oluvchi holatlari waiting_for_content dan OLDIN.
    # Konstruktor ochiq turganda admin yozgan matn "yangi kontent" bo'lib
    # ketmasligi kerak — u tugma nomi yoki oluvchilar ro'yxati.
    dp.message.register(process_broadcast_button, BroadcastStates.waiting_for_button)
    dp.message.register(process_broadcast_recipients, BroadcastStates.waiting_for_recipients)
    dp.message.register(capture_broadcast_content, BroadcastStates.waiting_for_content)
    dp.message.register(process_manage_user_identifier, ManageUserStates.waiting_for_identifier)
    dp.message.register(process_add_admin, AddAdminStates.waiting_for_admin_id)
    dp.message.register(process_remove_admin, RemoveAdminStates.waiting_for_admin_id)
    dp.message.register(process_maintenance_message, MaintenanceStates.waiting_for_message)
    dp.message.register(process_watch_group_id, WatchStates.waiting_for_group_id)
    dp.message.register(process_watch_identifier, WatchStates.waiting_for_identifier)
    # DIQQAT: FSM handlerlari tugma handlerlaridan KEYIN ro'yxatdan o'tadi —
    # aks holda admin promokod holatida qolib, boshqa tugmalarni bosa olmasdi.
    dp.message.register(process_promo_create, PromoAdminStates.waiting_for_spec)
    dp.message.register(process_promo_recipients, GiveawayStates.waiting_promo_recipients)
    dp.message.register(process_ref_recipients, GiveawayStates.waiting_ref_recipients)

    # register report message handler (user types the report text after pressing report button)
    dp.message.register(process_report_message, ReportStates.waiting_for_report_message)

    # callback handlers
    dp.callback_query.register(remove_admin_callback, lambda q: q.data and q.data.startswith("remove_admin:"))
    # register report callback (this allows the inline "Adminga xabar" button to trigger report flow)
    dp.callback_query.register(report_callback, lambda q: q.data and q.data.startswith("report:"))
    dp.callback_query.register(manage_user_action_callback, lambda q: q.data and q.data.startswith("mu:"))
    dp.callback_query.register(broadcast_button_add_callback, lambda q: q.data == "bcast:btnadd")
    dp.callback_query.register(broadcast_button_del_callback, lambda q: q.data == "bcast:btndel")
    dp.callback_query.register(broadcast_color_callback, lambda q: q.data and q.data.startswith("bcast:color:"))
    dp.callback_query.register(broadcast_preview_callback, lambda q: q.data == "bcast:preview")
    dp.callback_query.register(broadcast_next_callback, lambda q: q.data == "bcast:next")
    dp.callback_query.register(broadcast_segment_callback, lambda q: q.data and q.data.startswith("bcast:seg:"))
    dp.callback_query.register(broadcast_confirm_send_callback, lambda q: q.data == "bcast:send")
    dp.callback_query.register(broadcast_abort_callback, lambda q: q.data == "bcast:abort")
    dp.callback_query.register(broadcast_cancel_send_callback, lambda q: q.data == "bcast:cancel")
    dp.callback_query.register(users_list_page_callback, lambda q: q.data and q.data.startswith("ulist:"))
    dp.callback_query.register(maintenance_toggle_callback, lambda q: q.data and q.data.startswith("maint:"))
    dp.callback_query.register(watch_menu_callback, lambda q: q.data and q.data.startswith("watch:"))
    dp.callback_query.register(promo_admin_callback, lambda q: q.data and q.data.startswith("promo:"))
    dp.callback_query.register(giveaway_callback, lambda q: q.data and q.data.startswith("gv:"))
