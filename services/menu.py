"""Foydalanuvchiga KO'RINADIGAN buyruqlar menyusi (chap tarafdagi "/" ro'yxati).

Telegram buyruqlar ro'yxatini har bir chatga ALOHIDA qo'yishga ruxsat
beradi (`BotCommandScopeChat`). Shundan foydalanamiz: Pro buyruqlari
faqat Pro'dagilarda ko'rinadi, tarif tugashi bilan menyudan yo'qoladi.

⚠️ Menyu — BEZAK, darvoza EMAS. Foydalanuvchi menyuni ochmasdan /kunlik
deb qo'lda ham yozishi mumkin, bundan tashqari ro'yxat eskirgan bo'lishi
mumkin (tarif tugagan, lekin u hali bironta xabar yozmagan). Haqiqiy
tekshiruv handlers/digest.py va handlers/messages.py ichida qoladi —
bu yerdagi ro'yxat o'zgarsa ham u yerdagi shartlar o'chirilmasin.
"""

import logging
from aiogram.types import (BotCommand, BotCommandScopeChat, MenuButtonDefault,
                           MenuButtonWebApp, WebAppInfo)

from core.config import WEB_APP_URL
from core.loader import bot

logger = logging.getLogger(__name__)

# Hamma uchun — tarifdan qat'i nazar.
COMMON_COMMANDS = [
    BotCommand(command="help", description="🎯 Nima qila olaman?"),
    BotCommand(command="new", description="🧹 Suhbatni noldan boshlash"),
    BotCommand(command="profile", description="👤 Profilim va limitlarim"),
    BotCommand(command="pro", description="💎 Pro tarif"),
    BotCommand(command="promo", description="🎟 Promokod kiritish"),
    BotCommand(command="gift", description="🎁 Do'stga Pro sovg'a qilish"),
]

# Faqat Pro'da. Yangi Pro buyrug'i qo'shilsa — SHU ro'yxatga bitta qator,
# boshqa hech joyda o'zgarish kerak emas.
PRO_COMMANDS = [
    BotCommand(command="kunlik", description="⏰ Kunlik daydjest"),
    BotCommand(command="research", description="🔬 Chuqur tadqiqot + PDF"),
    # /biznes va /mijozlar ATAYLAB yo'q — sinov davrida menyuda
    # ko'rinmaydi, buyruqlar esa yozib ishlatilsa ishlaydi. Hamma uchun
    # ochilganda shu yerga qo'shiladi.
]

# Faqat adminlarda. 7-bosqichda paydo bo'ldi va sababi aniq: reply
# klaviatura o'chirildi, ya'ni adminning yagona KO'RINADIGAN kirish
# nuqtasi shu ro'yxat bo'lib qoldi. Usiz `/xabar` ni faqat eslab qolgan
# odam topa olardi — `/start` bir marta aytadi, keyin yo'qoladi.
#
# ⚠️ Bu ham BEZAK: haqiqiy tekshiruv `require_admin_or_deny` da. Ro'yxat
# eskirgan bo'lishi mumkin (adminlikdan chiqarilgan, lekin hali hech
# narsa yozmagan), shuning uchun buyruqni ko'rish uni ishlata olish
# degani emas.
ADMIN_COMMANDS = [
    BotCommand(command="xabar", description="📢 Tarqatma"),
    BotCommand(command="kod", description="🎁 Promokod/referal yuborish"),
]

# ponytail: RAM keshi — bot qayta ishga tushganda tozalanadi, ya'ni har
# bir foydalanuvchi uchun bir marta ortiqcha API chaqiruvi bo'ladi.
# Bazaga ustun qo'shishga arzimaydi. Kerak bo'lsa: users'ga bitta bool.
_shown: dict[int, tuple[bool, bool]] = {}


def commands_for(is_pro: bool, is_admin: bool = False) -> list[BotCommand]:
    """Tarifga mos ro'yxat. Sof funksiya — tests/test_menu.py'da tekshiriladi.

    Admin buyruqlari OXIRIDA: ro'yxatni foydalanuvchi ham, admin ham
    bir xil boshlaydi va ko'z o'rgangan tartib buzilmaydi.
    """
    out = COMMON_COMMANDS + PRO_COMMANDS if is_pro else list(COMMON_COMMANDS)
    return out + ADMIN_COMMANDS if is_admin else out


async def sync_commands(user_id: int, is_pro: bool, is_admin: bool = False) -> None:
    """Chat menyusini tarifga moslaydi.

    O'zgarish bo'lmasa Telegram'ga UMUMAN murojaat qilinmaydi — bu har bir
    xabarda chaqirilgani uchun muhim.

    `bot` ATAYLAB parametr emas: u chaqiruvchilardan uzatilganda bitta
    joyda o'zgaruvchi nomi boshqacha bo'lib (`last_message`), NameError
    keng `except` ichida yutilib ketdi va matnli xabarlar javobsiz qoldi.
    Umumiy singletonda bunday xato bo'lishi mumkin emas.
    """
    # ⚠️ Kesh endi JUFTLIK bo'yicha. Ilgari `is` bilan bitta bool
    # solishtirilardi; admin bayrog'i qo'shilgach o'sha tekshiruv
    # adminlikdagi o'zgarishni umuman ko'rmay qolardi — odam admin
    # bo'ladi, buyruqlar esa eski ro'yxatda qolib ketardi.
    holat = (is_pro, is_admin)
    if _shown.get(user_id) == holat:
        return
    try:
        await bot.set_my_commands(
            commands_for(is_pro, is_admin),
            scope=BotCommandScopeChat(chat_id=user_id))
    except Exception as exc:
        # Menyu qo'yilmagani uchun foydalanuvchining xabari yo'qolishi yoki
        # javob berilmay qolishi MUMKIN EMAS — shuning uchun yutamiz.
        # Keshga yozmaymiz, keyingi xabarda qayta urinib ko'riladi.
        logger.debug(f"[menyu] {user_id} uchun qo'yilmadi: {exc}")
        return
    _shown[user_id] = holat


# ═══════════════════════════════════════════════════════════════════
#  WEB PANEL TUGMASI (ko'k "Panel" tugmasi chat yonida)
# ═══════════════════════════════════════════════════════════════════
# `setChatMenuButton` chat_id qabul qiladi, ya'ni tugma HAR CHATGA
# alohida qo'yiladi — xuddi yuqoridagi buyruqlar ro'yxati kabi.
#
# ⚠️ Bu ham BEZAK, darvoza EMAS. Havolani qo'lda ochish mumkin, shuning
# uchun haqiqiy tekshiruv `web/auth.py` da: imzo + har so'rovda
# `is_admin()`. Tugmani olib tashlash ma'lumotni yashirmaydi — panelning
# o'zi 403 qaytaradi.
_menu_button: dict[int, bool] = {}


async def sync_menu_button(user_id: int, is_admin: bool) -> None:
    """Adminda — "Panel" tugmasi, qolganlarda — standart "/" ro'yxati.

    Keshlanadi: `/start` va har admin o'zgarishida chaqiriladi, o'zgarish
    bo'lmasa Telegram'ga murojaat qilinmaydi.
    """
    if not WEB_APP_URL:
        return
    if _menu_button.get(user_id) is is_admin:
        return
    tugma = (MenuButtonWebApp(text="Panel", web_app=WebAppInfo(url=WEB_APP_URL))
             if is_admin else MenuButtonDefault())
    try:
        await bot.set_chat_menu_button(chat_id=user_id, menu_button=tugma)
    except Exception as exc:
        # Menyu qo'yilmagani uchun xabar yo'qolmaydi — yutamiz va keshga
        # yozmaymiz, keyingi safar qayta urinib ko'riladi.
        logger.debug(f"[panel tugmasi] {user_id} uchun qo'yilmadi: {exc}")
        return
    _menu_button[user_id] = is_admin
