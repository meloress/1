import time
import asyncio
from aiogram.types import CallbackQuery
from core.config import (MAX_MANUAL_RETRIES, MAX_AUTO_RETRIES, AUTO_BACKOFFS, USER_COOLDOWN,
                         message_cost, pick_reasoning_effort)
from core.loader import logger, bot
from core.memory import (
    failed_requests, user_last_action_ts,
    set_ongoing, is_ongoing, release_ongoing,
    clear_failed_request
)
from services.ai import get_gpt_reply, safe_update_history
from handlers.helpers import make_retry_keyboard, mavzu_kwargs

from handlers.messages import (process_stream_draft, _check_quota, _is_pro, _refund_quota,
                               _send_limit_reached_message, _send_output_files)

# --------------------------------------------------
# 1. RETRY HANDLER (Qayta urinish)
# --------------------------------------------------
async def handle_retry_callback(query: CallbackQuery):
    # ⚠️ query.answer() — BIR MARTA. Ilgari boshida bo'sh answer() turardi,
    # keyingi ogohlantirishlar (kuting, urinish tugadi) esa ikkinchi javob
    # bo'lgani uchun Telegram rad etardi — foydalanuvchi hech narsa ko'rmasdi.
    data = query.data or ""
    try:
        chat_id = int(data.split(":", 1)[1])
    except (IndexError, ValueError):
        await query.answer("Noto'g'ri so'rov.", show_alert=True); return

    fr = failed_requests.get(chat_id)
    if not fr:
        await query.answer()
        try: await query.message.edit_text("⚠️ Qayta yuborish uchun ma'lumot topilmadi.")
        except Exception: pass
        return

    user_id = query.from_user.id
    if fr.get("user_id") != user_id:
        await query.answer("Faqat so'rovni yuborgan foydalanuvchi qayta so'rashi mumkin.", show_alert=True); return

    now = time.time()
    if now - user_last_action_ts.get(user_id, 0) < USER_COOLDOWN:
        await query.answer(f"Iltimos, {USER_COOLDOWN} soniya kuting.", show_alert=True); return
    user_last_action_ts[user_id] = now

    if fr["attempts_manual"] >= MAX_MANUAL_RETRIES:
        await query.answer("Maksimal urinish tugadi.", show_alert=True); return

    if is_ongoing(chat_id):
        await query.answer("Jarayon ketmoqda..."); return

    prompt = fr.get("prompt")
    # MAVZU (topic): so'rov qaysi mavzuda yiqilgan bo'lsa, o'sha yerda
    # qayta ishlanadi. Busiz javob ekranda mavzuda ko'rinib, TARIXGA
    # chatning asosiy oqimiga yozilardi — model keyingi savolda o'z
    # javobini ko'rmasdi va bu hech qayerda xato bermasdi.
    thread_id = fr.get("thread_id") or 0
    if not prompt:
        await query.answer()
        await bot.send_message(chat_id, "⚠️ So'rov topilmadi.",
                               **mavzu_kwargs(thread_id)); return

    # Asl so'rovning bali xato bo'lganda QAYTARILGAN — qayta urinish ham
    # oddiy so'rovdek yechiladi, aks holda «Qayta so'rash» tekin kanal edi.
    cost = message_cost("text", pick_reasoning_effort(prompt))
    quota = await _check_quota(user_id, cost)
    if not quota["allowed"]:
        await query.answer()
        await _send_limit_reached_message(query.message, quota, feature="text")
        return

    await query.answer()
    set_ongoing(chat_id)
    fr["attempts_manual"] += 1
    fr["last_attempt_ts"] = now

    try: await query.message.edit_reply_markup(reply_markup=None)
    except Exception: pass

    success = False
    for attempt_idx in range(MAX_AUTO_RETRIES):
        if attempt_idx > 0:
            wait = AUTO_BACKOFFS[min(attempt_idx - 1, len(AUTO_BACKOFFS) - 1)]
            await asyncio.sleep(wait)

        try:
            fr["attempts_auto"] += 1
            # Oddiy matn yo'li bilan BIR XIL parametrlar: ilgari faqat
            # (chat_id, prompt) berilardi — Pro odam bepul model va
            # vositalarsiz javob olardi, rasm va fayl umuman yo'q edi.
            images: list = []
            output_files: list = []
            quota_box: list = []
            stream_gen = get_gpt_reply(chat_id, prompt, user_id=user_id,
                                       output_files=output_files,
                                       file_quota_out=quota_box,
                                       images_out=images, is_pro=_is_pro(quota),
                                       tg_name=query.from_user.full_name,
                                       thread_id=thread_id)

            reply = await process_stream_draft(query.message, stream_gen, images=images)
            if output_files:
                await _send_output_files(chat_id, output_files, thread_id)

            if not reply and not output_files:
                raise ValueError("Bosh javob qaytdi")

            if reply:
                # Savol HAM yoziladi: faqat javob yozilsa, model keyingi
                # xabarda savolsiz javobni ko'rardi.
                try:
                    await safe_update_history(chat_id, prompt, role="user",
                                              thread_id=thread_id)
                    await safe_update_history(chat_id, reply, role="assistant",
                                              images=images, thread_id=thread_id)
                except Exception: pass

            success = True
            break
        except Exception as e:
            logger.exception(f"Retry failed: {e}")

    release_ongoing(chat_id)
    if success:
        clear_failed_request(chat_id)
    else:
        await _refund_quota(user_id, cost, quota)
        fr["last_attempt_ts"] = time.time()
        try:
            kb = make_retry_keyboard(chat_id, attempts=fr["attempts_manual"])
            await query.message.edit_text("❌ Javob olinmadi.", reply_markup=kb)
        except Exception: pass
