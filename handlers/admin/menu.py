"""Reply-klaviaturadagi 12 tugmani 4 taga yig'uvchi inline menyular.

Reply-klaviatura o'sib borardi va yangi admin qaysi tugma nima
qilishini birinchi urinishda topolmasdi. Tugmalar YO'QOLMADI —
mavjud handlerlar o'sha matnga ham yozilgan holicha qoladi (eski
telefonda ochiq turgan klaviatura ishlashda davom etsin), bu yerda
faqat ularga inline yo'l ochiladi.

⚠️ Ekran funksiyalari `Message` kutadi va admin tekshiruvi
`message.from_user` dan oladi. Callback'dagi `query.message` —
BOTNING xabari, ya'ni `from_user` bot bo'ladi va har bir ekran
"faqat admin uchun" deb rad etardi. Shuning uchun xabar nusxasi
haqiqiy bosgan odam bilan almashtiriladi.
"""

import inspect
import logging
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext

from handlers.admin.common import require_admin_or_deny, require_admin_or_deny_query
from handlers.admin.promo import show_giveaway_menu, show_referral_settings
from handlers.admin.stats import handle_top, handle_users_command
from handlers.admin.system import (
    show_maintenance_menu, show_watch_menu, start_add_admin, start_remove_admin,
)
from handlers.admin.users import handle_users_list, start_manage_user

logger = logging.getLogger(__name__)

# Kalit → ekran funksiyasi. Matnli tugma nomlari o'sha ekranlarga
# ro'yxatdan o'tgan, ya'ni bu yerda takroriy mantiq yo'q.
ACTIONS = {
    "stats": handle_users_command,
    "top": handle_top,
    "list": handle_users_list,
    "manage": start_manage_user,
    "giveaway": show_giveaway_menu,
    "ref": show_referral_settings,
    "maint": show_maintenance_menu,
    "watch": show_watch_menu,
    "addadmin": start_add_admin,
    "deladmin": start_remove_admin,
}

USERS_MENU = (
    ("📊 Statistika", "stats"),
    ("🏆 Faol foydalanuvchilar", "top"),
    ("📄 Userlar ro'yxati", "list"),
    ("🔍 Foydalanuvchini boshqarish", "manage"),
)

SETTINGS_MENU = (
    ("🎁 Bepul Pro", "giveaway"),
    ("👥 Referal sharti", "ref"),
    ("🛠 Texnik ta'til", "maint"),
    ("👁 Kuzatish", "watch"),
    ("➕ Admin qo'shish", "addadmin"),
    ("➖ Admin o'chirish", "deladmin"),
)


def _kb(items) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=nom, callback_data=f"am:{kalit}")]
        for nom, kalit in items
    ])


async def show_users_menu(message: Message):
    if not await require_admin_or_deny(message):
        return
    await message.answer("👥 <b>Foydalanuvchilar</b>",
                         reply_markup=_kb(USERS_MENU), parse_mode=ParseMode.HTML)


async def show_settings_menu(message: Message):
    if not await require_admin_or_deny(message):
        return
    await message.answer("⚙️ <b>Sozlamalar</b>",
                         reply_markup=_kb(SETTINGS_MENU), parse_mode=ParseMode.HTML)


async def menu_callback(query: CallbackQuery, state: FSMContext):
    if not await require_admin_or_deny_query(query):
        return
    kalit = (query.data or "").split(":", 1)[1]
    fn = ACTIONS.get(kalit)
    if fn is None or query.message is None:
        await query.answer()
        return
    await query.answer()
    msg = query.message.model_copy(update={"from_user": query.from_user})
    # Ba'zi ekranlar FSM holatini tozalaydi/o'rnatadi, ba'zilari yo'q.
    # Imzodan o'qiladi — qo'lda ro'yxat tutilsa, kelajakda `state`
    # qo'shilgan ekran jimgina TypeError beradi.
    if "state" in inspect.signature(fn).parameters:
        await fn(msg, state)
    else:
        await fn(msg)
