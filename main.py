import asyncio
from aiogram import types, F, Router
from aiogram.filters import CommandStart
from aiogram.methods import DeleteWebhook
from aiogram.types import BotCommandScopeAllPrivateChats, MessageGenerationStopped
from core.loader import dp, bot, logger
from db.database import create_db_pool, create_users_table, create_history_table
from db import database
from core import config
from handlers import admin as admin_module
from handlers.admin import daily as admin_daily
from handlers.helpers import ensure_pin_column, notify_inactive_users
from handlers import messages as messages_module
from handlers.messages import (
    handle_start, handle_text, handle_photo, handle_document, handle_voice,
    handle_location,
    handle_research,
    router as generating_state_router,
)
from handlers.callbacks import handle_retry_callback
from handlers import capabilities
from db.history import init_db
from core.memory import start_cleanup_task
from aiogram.filters import Command
from handlers.profile import handle_profile
from db.database import ensure_profile_columns

from handlers.guest import router as guest_router
from handlers import pro as pro_module
from handlers import digest as digest_module
from handlers.helpers import premium_expiry_watcher, reminder_watcher
from services import ai as ai_service
from services import menu as menu_module
from services import sandbox

general_router = Router(name="general")


async def main():
    await create_db_pool()
    await create_users_table()
    await create_history_table()
    await ensure_profile_columns()
    await ensure_pin_column()
    await database.load_watch_cache()
    # Admin panelida sozlangan kunlik limitlar. Bazadan BIR MARTA
    # o'qiladi va xotiraga qo'yiladi — `daily_limit()` har xabarda
    # chaqiriladi, u yerdan DB so'rovi qilib bo'lmaydi.
    try:
        config.apply_limit_overrides(await database.get_limit_overrides())
    except Exception:
        logger.exception("limit sozlamalari yuklanmadi — config'dagi qiymat ishlatiladi")
    # AI javobidagi emojilarni animatsiyali nusxasiga almashtiruvchi paket.
    # BIR MARTA o'qiladi — har xabarda so'rov qilib bo'lmaydi. Xato bo'lsa
    # ichida yutiladi va config'dagi eski ro'yxat qoladi, ya'ni bot
    # emoji tufayli ishga tushmay qolmaydi.
    try:
        await ai_service.load_text_emoji_pack()
    except Exception:
        logger.exception("emoji paketi yuklanmadi — oddiy emoji ishlatiladi")
    await init_db()
    asyncio.create_task(start_cleanup_task())

    if not hasattr(dp, "guest_message"):
        logger.error(
            "⚠️ O'rnatilgan aiogram versiyasi Guest Mode (guest_message) ni "
            "qo'llab-quvvatlamaydi. Iltimos, `pip install -U aiogram` orqali "
            "kamida 3.29.0 versiyasiga yangilang, aks holda Guest Mode ishlamaydi."
        )
    else:
        logger.info("✅ Guest Mode (guest_message) aiogram tomonidan qo'llab-quvvatlanadi.")

    # Sandbox kutubxonalari joyidami — hujjat yaratish shularga tayanadi.
    # Yiqilsa bot baribir ishlaydi (tekshiruv hech narsani to'xtatmaydi),
    # lekin sabab logda ANIQ ko'rinadi. Ilgari python-pptx import
    # bo'lmay qolganda model jimgina PDF ga o'tib ketardi.
    try:
        nosozliklar = await sandbox.check_libraries()
        if nosozliklar:
            for satr in nosozliklar:
                logger.error(f"⚠️ [Sandbox] kutubxona ishlamaydi — {satr}")
        else:
            logger.info(f"✅ Sandbox kutubxonalari joyida "
                        f"({len(sandbox.SANDBOX_LIBRARIES)} ta).")
    except Exception as e:
        logger.warning(f"[Sandbox] kutubxona tekshiruvi bajarilmadi: {e}")

    # ═══════════════════════════════════════════════════════════════
    #  ⏹ "TO'XTATISH" TUGMASI (Bot API 10.3)
    # ═══════════════════════════════════════════════════════════════
    # Foydalanuvchi streaming draft ustidagi tugmani bosganda Telegram
    # `stopped_message_generation` update'ini yuboradi.
    #
    # aiogram 3.31.0 bu update turini biladi, ya'ni oddiy observer
    # yetarli. Ro'yxatga olish TARTIBI bu yerda muhim emas — bu alohida
    # observer, `dp.message` zanjiriga umuman tegmaydi. Bundan tashqari
    # handler borligi `resolve_used_update_types()` ga update turini
    # o'zi topish imkonini beradi (pastdagi start_polling'ga qarang).
    @dp.stopped_message_generation()
    async def on_generation_stopped(event: MessageGenerationStopped):
        if not messages_module.request_stop(event.draft_id):
            logger.debug(f"[Stop] noma'lum draft_id={event.draft_id} — "
                         "javob allaqachon tugagan bo'lishi mumkin")

    admin_module.register_admin_handlers(dp, bot)

    # ═══════════════════════════════════════════════════════════════
    #  TO'LOV HANDLERLARI — dp.message'ga TO'G'RIDAN-TO'G'RI
    # ═══════════════════════════════════════════════════════════════
    # ⚠️ Bu qatorlarning JOYI JUDA MUHIM. dp.message'ga to'g'ridan-to'g'ri
    # yozilgan handler include_router() bilan qo'shilgan HAR QANDAY
    # routerdan OLDIN ishlaydi.
    #
    # NEGA SHART: handlers/messages.py'dagi busy_handler
    # (@router.message(GeneratingState.generating)) hech qanday kontent
    # filtriga ega emas. Foydalanuvchi savol berib, javob generatsiya
    # qilinayotgan paytda to'lovni yakunlasa, successful_payment xabari
    # o'sha handlerga tushib "Iltimos kuting..." javobini olardi va
    # YO'QOLIB KETARDI — ya'ni PUL OLINIB, PRO BERILMASDI.
    #
    # Xuddi shu sabab texnik ta'til darvozasiga ham tegishli: to'lov
    # ta'til yoqilgan paytda kelsa ham qabul qilinishi shart.
    dp.message.register(pro_module.handle_successful_payment, F.successful_payment)
    dp.pre_checkout_query.register(pro_module.handle_pre_checkout)

    # FSM holatlari ham oddiy AI handlerlaridan oldin turishi kerak, aks
    # holda "kimga sovg'a qilay?" javobi GPT'ga savol bo'lib ketardi.
    dp.message.register(pro_module.process_gift_recipient,
                        pro_module.GiftStates.waiting_for_recipient)
    dp.message.register(pro_module.process_promo_code,
                        pro_module.PromoStates.waiting_for_code)
    dp.message.register(digest_module.process_digest_topics,
                        digest_module.DigestStates.waiting_for_topics)

    async def non_admin_predicate(message: types.Message):
        try:
            return not await database.is_admin(message.from_user.id)
        except Exception:
            return False

    async def maintenance_gate(message: types.Message):
        try:
            notice = await database.get_maintenance_notice_for(message.from_user.id)
        except Exception:
            return False
        return {"maintenance_notice": notice} if notice else False

    async def handle_maintenance_notice(message: types.Message, maintenance_notice: str):
        await message.answer(maintenance_notice)

    general_router.message.register(handle_start, CommandStart())
    general_router.message.register(handle_profile, Command("profile"))
    # /help — /profile bilan bir xil mantiq: faqat o'qiydi, hech narsa
    # sarflamaydi, shuning uchun texnik ta'til darvozasidan OLDIN turadi.
    # Ta'til paytida ham "bot nima qila oladi" savoliga javob bo'lgani
    # yaxshi.
    general_router.message.register(capabilities.handle_help, Command("help"))
    # Texnik ta'til yoqilganda AI javob handlerlaridan OLDIN ishga tushishi shart —
    # aks holda oddiy foydalanuvchi xabari baribir GPT'ga yuborilib ketadi.
    general_router.message.register(
        handle_maintenance_notice, F.text | F.photo | F.document | F.voice, maintenance_gate
    )
    # /pro, /promo, /gift ATAYLAB maintenance darvozasidan KEYIN: texnik
    # ta'til paytida o'chirilgan botga obuna sotish — refund manbai.
    # (/profile esa yuqorida qoladi — profilni o'qish zararsiz.)
    # ⚠️ handle_text (F.text) dan OLDIN — u noma'lum /buyruqlarni ham
    # yutadi va /research GPT'ga oddiy savol bo'lib ketardi.
    general_router.message.register(handle_research, Command("research"))
    general_router.message.register(digest_module.handle_digest, Command("kunlik"))
    general_router.message.register(pro_module.handle_pro, Command("pro"))
    general_router.message.register(pro_module.handle_promo, Command("promo"))
    general_router.message.register(pro_module.handle_gift, Command("gift"))
    general_router.message.register(handle_text, F.text, non_admin_predicate)
    general_router.message.register(handle_photo, F.photo, non_admin_predicate)
    general_router.message.register(handle_document, F.document, non_admin_predicate)
    general_router.message.register(handle_voice, F.voice, non_admin_predicate)
    # ⚠️ handle_unsupported (pastda) F.location ni ham ushlaydi, shuning
    # uchun bu QATOR UNDAN YUQORIDA turishi SHART — aks holda lokatsiya
    # yana «Joylashuv bilan ishlay olmayman» kartochkasiga tushib ketadi.
    general_router.message.register(handle_location, F.location, non_admin_predicate)
    # ⚠️ ENG OXIRIDA: bu handler qo'llab-quvvatlanmagan turlarni (video,
    # stiker, audio...) ushlaydi va u YUQORIDAGILARDAN KEYIN turishi shart —
    # aks holda o'zi ushlaydigan turlar ro'yxati kengayib ketsa, oddiy
    # rasm/hujjat oqimini bosib qolishi mumkin.
    general_router.message.register(
        capabilities.handle_unsupported,
        F.video | F.video_note | F.animation | F.audio | F.sticker
        | F.contact | F.poll,
        non_admin_predicate,
    )
    dp.include_router(guest_router)
    # GeneratingState uchun spam-guard (busy_handler) ODDIY handlerlardan
    # OLDIN ro'yxatdan o'tishi SHART — aks holda javob kutilayotganda
    # kelgan yangi xabar to'g'ridan-to'g'ri handle_text/photo/... ga tushib,
    # parallel ikkinchi so'rov boshlab yuborardi.
    dp.include_router(generating_state_router)
    dp.include_router(general_router)

    dp.callback_query.register(handle_retry_callback, lambda q: q.data and q.data.startswith("retry:"))
    dp.callback_query.register(pro_module.handle_pro_callback,
                               lambda q: q.data and q.data.startswith("pro:"))
    dp.callback_query.register(digest_module.handle_digest_callback,
                               lambda q: q.data and q.data.startswith("dg:"))
    dp.callback_query.register(capabilities.handle_capabilities_callback,
                               lambda q: q.data and q.data.startswith("cap:"))
    # Ulashish uchun inline rejim (@BotFather /setinline). Yoqilmagan bo'lsa
    # bu handlerga hech qachon update kelmaydi — zarari yo'q.
    dp.inline_query.register(pro_module.handle_inline_share)
    asyncio.create_task(notify_inactive_users())
    asyncio.create_task(premium_expiry_watcher())
    asyncio.create_task(reminder_watcher())
    asyncio.create_task(digest_module.daily_digest_watcher())
    # Admin paneli: kunlik hisobot va rejalashtirilgan tarqatma.
    asyncio.create_task(admin_daily.daily_report_watcher())
    asyncio.create_task(admin_daily.scheduled_broadcast_watcher())

    # Referal va sovg'a havolalari (t.me/<username>?start=ref_...) uchun
    # bot username'i kerak — Telegram'dan bir marta so'raymiz.
    try:
        me = await bot.get_me()
        pro_module.BOT_USERNAME = me.username or ""
        # Inline rejim @BotFather'da /setinline bilan yoqiladi. Yoqilmagan
        # bo'lsa ulashish tugmasi eski matnli usulga tushadi — kod uni
        # o'zi yoqa olmaydi, shuning uchun so'rab olamiz.
        pro_module.INLINE_ENABLED = bool(me.supports_inline_queries)
        if not pro_module.INLINE_ENABLED:
            logger.warning("Inline rejim o'chiq — @BotFather /setinline bilan "
                           "yoqilsa ulashish xabari tugmali bo'ladi.")
    except Exception as e:
        logger.warning(f"get_me() muvaffaqiyatsiz — referal havolalari ishlamaydi: {e}")

    # Bepul buyruqlar ro'yxati — HAMMA shaxsiy chat uchun standart. Pro
    # buyruqlari services/menu.py'da chat darajasida shu ro'yxat USTIDAN
    # yoziladi, chunki Telegram'da aniqroq qamrov ustun turadi. Shu sababli
    # /start uchun alohida bazaga murojaat qilish shart emas: yangi
    # foydalanuvchi birinchi soniyadanoq menyuni ko'radi.
    try:
        await bot.set_my_commands(menu_module.COMMON_COMMANDS,
                                  scope=BotCommandScopeAllPrivateChats())
    except Exception as e:
        logger.warning(f"Buyruqlar menyusi qo'yilmadi: {e}")

    await bot(DeleteWebhook(drop_pending_updates=True))

    # allowed_updates ro'yxatdan o'tgan handlerlardan chiqariladi.
    # `stopped_message_generation` uchun endi haqiqiy observer bor, ya'ni
    # u ro'yxatga o'zi tushadi — qo'lda qo'shish kerak emas.
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
