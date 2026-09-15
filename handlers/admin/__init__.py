"""Admin panel — handlerlarni ro'yxatdan o'tkazish.

⚠️ 7-BOSQICH: ekranlarning ko'pi o'chirildi, ular endi web panelda.
Bu yerda faqat **botda qolishi shart bo'lganlari** turibdi (REJA 2):

  * 📢 **Tarqatma** (`/xabar`) — `copy_message` bilan ishlaydi, ya'ni
    admin botga nima yuborsa odamlarga AYNAN o'sha yetadi (albom,
    formatlash, premium emoji). Webda qayta yig'ilgan xabar buni
    yo'qotardi.
  * 🎁 **Promokod/referal yuborish** (`/kod`) — shu sabab: bu ham
    odamga xabar jo'natish. Kod YARATISH esa panelda.
  * 📨 **Report** — foydalanuvchi boshlaydi, ya'ni panelga umuman
    kirmaydi; javob ham botdan ketadi.

To'lov handlerlari `main.py` da, routerdan OLDIN — u yerga tegilmaydi.
Kunlik hisobot `daily.py` da, fon vazifasi sifatida.

⚠️ RO'YXAT TARTIBI FUNKSIONAL TALAB, bezak emas:
  * FSM holatlari tugma/buyruq handlerlaridan KEYIN — aks holda admin
    biror holatda qolib, boshqa hech narsani bosa olmaydi;
  * `waiting_for_button` va `waiting_for_recipients`
    `waiting_for_content` dan OLDIN — konstruktor ochiq turganda
    admin yozgan matn "yangi kontent" bo'lib ketmasligi kerak.

tests/test_admin_registry.py bu tartibni qo'riqlaydi.
"""

from aiogram.filters import Command

from handlers.admin.broadcast import (
    BroadcastStates, broadcast_abort_callback,
    broadcast_button_add_callback, broadcast_button_del_callback,
    broadcast_cancel_send_callback, broadcast_color_callback,
    broadcast_confirm_send_callback, broadcast_later_callback,
    broadcast_next_callback, process_broadcast_schedule,
    broadcast_preview_callback, broadcast_segment_callback,
    capture_broadcast_content, process_broadcast_button,
    process_broadcast_recipients, start_broadcast,
)
from handlers.admin.promo import (
    GiveawayStates, giveaway_callback, process_promo_recipients,
    process_ref_recipients, show_giveaway_menu,
)
from handlers.admin.system import (
    ReportStates, process_report_message, report_callback,
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
    # ⚠️ Kirish nuqtasi endi BUYRUQ, matnli tugma emas: reply-klaviatura
    # 7-bosqichda olib tashlandi (`/start` uni `ReplyKeyboardRemove` bilan
    # tozalaydi). Buyruq afzal, chunki u adminning telefonida eskirib
    # qolmaydi — klaviatura esa `/start` bosilgunicha ekranda turardi.
    dp.message.register(start_broadcast, Command("xabar"))
    dp.message.register(show_giveaway_menu, Command("kod"))

    # ⚠️ TARTIB: tugma va oluvchi holatlari waiting_for_content dan OLDIN.
    # Konstruktor ochiq turganda admin yozgan matn "yangi kontent" bo'lib
    # ketmasligi kerak — u tugma nomi yoki oluvchilar ro'yxati.
    dp.message.register(process_broadcast_schedule, BroadcastStates.waiting_for_schedule)
    dp.message.register(process_broadcast_button, BroadcastStates.waiting_for_button)
    dp.message.register(process_broadcast_recipients, BroadcastStates.waiting_for_recipients)
    dp.message.register(capture_broadcast_content, BroadcastStates.waiting_for_content)
    # DIQQAT: FSM handlerlari buyruq handlerlaridan KEYIN ro'yxatdan o'tadi.
    dp.message.register(process_promo_recipients, GiveawayStates.waiting_promo_recipients)
    dp.message.register(process_ref_recipients, GiveawayStates.waiting_ref_recipients)

    # Report — foydalanuvchi tugmani bosgandan keyin matnini yozadi.
    dp.message.register(process_report_message, ReportStates.waiting_for_report_message)

    # callback handlerlari
    dp.callback_query.register(report_callback, lambda q: q.data and q.data.startswith("report:"))
    dp.callback_query.register(broadcast_button_add_callback, lambda q: q.data == "bcast:btnadd")
    dp.callback_query.register(broadcast_button_del_callback, lambda q: q.data == "bcast:btndel")
    dp.callback_query.register(broadcast_color_callback, lambda q: q.data and q.data.startswith("bcast:color:"))
    dp.callback_query.register(broadcast_preview_callback, lambda q: q.data == "bcast:preview")
    dp.callback_query.register(broadcast_next_callback, lambda q: q.data == "bcast:next")
    dp.callback_query.register(broadcast_segment_callback, lambda q: q.data and q.data.startswith("bcast:seg:"))
    dp.callback_query.register(broadcast_confirm_send_callback, lambda q: q.data == "bcast:send")
    dp.callback_query.register(broadcast_abort_callback, lambda q: q.data == "bcast:abort")
    dp.callback_query.register(broadcast_cancel_send_callback, lambda q: q.data == "bcast:cancel")
    dp.callback_query.register(broadcast_later_callback, lambda q: q.data == "bcast:later")
    dp.callback_query.register(giveaway_callback, lambda q: q.data and q.data.startswith("gv:"))
