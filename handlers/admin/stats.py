"""Admin statistikasi: umumiy ko'rsatkichlar va faol foydalanuvchilar.

⚠️ Faoliyat turlarining SQL filtri va `type_labels` — bu yerda.
`user_activity` ga yoziladigan HAR BIR yangi tur shu ikkalasiga ham
qo'shilishi shart, aks holda u statistikadan jimgina yo'qoladi
(tests/test_activity_tracking.py aynan shuni qo'riqlaydi)."""

import logging
from aiogram.types import Message
from db import database as database_module
from core.config import (
    MESSAGE_COST_TEXT, MESSAGE_COST_PHOTO, MESSAGE_COST_DOCUMENT, MESSAGE_COST_VOICE, PRO_PLANS,
)
from handlers.admin.common import (
    format_dt, _format_user_link, require_admin_or_deny,
)

logger = logging.getLogger(__name__)


def _text_bar(value: int, max_value: int, length: int = 10) -> str:
    """Qiymatni unicode blok chiziqcha (text bar) ko'rinishida chizadi."""
    if max_value <= 0:
        return "░" * length
    filled = round(min(value / max_value, 1.0) * length)
    return "█" * filled + "░" * (length - filled)


async def handle_top(message: Message):
    if not await require_admin_or_deny(message):
        return

    try:
        async with database_module.pool.acquire() as conn:
            two_weeks_top = await conn.fetch('''
                SELECT user_id, username, COUNT(*) as activity_count
                FROM user_activity
                WHERE activity_time >= NOW() - INTERVAL '14 days'
                  AND user_id NOT IN (SELECT user_id FROM admins)
                  AND user_id NOT IN (SELECT user_id FROM superadmins)
                GROUP BY user_id, username
                ORDER BY activity_count DESC
                LIMIT 5
            ''')

            one_month_top = await conn.fetch('''
                SELECT user_id, username, COUNT(*) as activity_count
                FROM user_activity
                WHERE activity_time >= NOW() - INTERVAL '30 days'
                  AND user_id NOT IN (SELECT user_id FROM admins)
                  AND user_id NOT IN (SELECT user_id FROM superadmins)
                GROUP BY user_id, username
                ORDER BY activity_count DESC
                LIMIT 10
            ''')
    except Exception:
        logger.exception("handle_top DB error")
        await message.answer("❌ DB xatosi.")
        return

    def format_table(data, title):
        result = f"🏆 <b>{title}</b>\n\n"
        emojis = ["👑", "🥈", "🥉"]
        for i, row in enumerate(data, 1):
            medal = emojis[i-1] if i <= 3 else f"{i}️⃣"
            user_link = _format_user_link(row["user_id"], row["username"])
            result += f"{medal} 👤 {user_link} — <b>{row['activity_count']}</b> marta\n"
        return result

    response = (
        format_table(two_weeks_top, "So'nggi 2 hafta — TOP 5") + "\n\n"
        + format_table(one_month_top, "So'nggi 1 oy — TOP 10")
    )
    await message.answer(response, parse_mode="HTML")

async def handle_users_command(message: Message):
    if not await require_admin_or_deny(message):
        return

    try:
        async with database_module.pool.acquire() as conn:
            total_users = await conn.fetchval('''
                SELECT COUNT(*) FROM users
                WHERE is_active = TRUE
                  AND user_id NOT IN (SELECT user_id FROM admins)
                  AND user_id NOT IN (SELECT user_id FROM superadmins)
            ''')

            most_active_30days = await conn.fetchrow('''
                SELECT user_id, username, COUNT(*) AS activity_count
                FROM user_activity
                WHERE activity_time >= NOW() - INTERVAL '30 days'
                  AND user_id NOT IN (SELECT user_id FROM admins)
                  AND user_id NOT IN (SELECT user_id FROM superadmins)
                GROUP BY user_id, username
                ORDER BY activity_count DESC
                LIMIT 1
            ''')

            most_active_today = await conn.fetchrow('''
                SELECT user_id, username, COUNT(*) AS activity_count
                FROM user_activity
                WHERE activity_time >= CURRENT_DATE
                  AND user_id NOT IN (SELECT user_id FROM admins)
                  AND user_id NOT IN (SELECT user_id FROM superadmins)
                GROUP BY user_id, username
                ORDER BY activity_count DESC
                LIMIT 1
            ''')

            last_user = await conn.fetchrow('''
                SELECT user_id, username, created_at
                FROM users
                WHERE user_id NOT IN (SELECT user_id FROM admins)
                  AND user_id NOT IN (SELECT user_id FROM superadmins)
                ORDER BY created_at DESC
                LIMIT 1
            ''')

            daily_activity = await conn.fetch('''
                SELECT (activity_time AT TIME ZONE 'Asia/Tashkent')::date AS day,
                       COUNT(*) AS total, COUNT(DISTINCT user_id) AS uniq_users
                FROM user_activity
                WHERE activity_time >= NOW() - INTERVAL '7 days'
                GROUP BY day ORDER BY day
            ''')

            type_breakdown = await conn.fetch('''
                SELECT activity_type, COUNT(*) AS cnt
                FROM user_activity
                WHERE activity_time >= NOW() - INTERVAL '30 days'
                  AND activity_type IN (
                      'text_message','photo_message','document_message','voice_message',
                      'guest_text_message','guest_photo_message',
                      'guest_document_message','guest_voice_message',
                      'location_message',
                      'file_task','research'
                  )
                GROUP BY activity_type ORDER BY cnt DESC
            ''')

            # ⚠️ ADMINLAR SHU YERDA HAM CHIQARIB TASHLANADI. Yuqoridagi
            # `total_users` ularni chiqarardi, bu so'rov esa yo'q — natijada
            # ekranda "jami 100" turib, free + pro + premium = 103 chiqardi
            # va admin raqamlarga ishonmay qolardi. Bu ikki so'rov BIR XIL
            # to'plamni sanashi shart; birini o'zgartirsangiz ikkinchisini
            # ham o'zgartiring.
            plan_counts = await conn.fetchrow('''
                SELECT
                    COUNT(*) FILTER (WHERE plan_type = 'free' OR plan_type IS NULL) AS free_count,
                    COUNT(*) FILTER (WHERE plan_type = 'pro') AS pro_count,
                    COUNT(*) FILTER (WHERE plan_type IS NOT NULL AND plan_type NOT IN ('free', 'pro')) AS premium_count
                FROM users
                WHERE is_active = TRUE
                  AND user_id NOT IN (SELECT user_id FROM admins)
                  AND user_id NOT IN (SELECT user_id FROM superadmins)
            ''')

        revenue = await database_module.revenue_stats()
    except Exception:
        logger.exception("handle_users_command error")
        await message.answer("❌ DB xatosi.")
        return

    def format_user(user):
        return _format_user_link(user["user_id"], user["username"]) if user else "—"

    last_created_str = "—"
    if last_user and last_user.get('created_at'):
        last_created_str = format_dt(last_user['created_at'])

    weekday_names = ["Dush", "Sesh", "Chor", "Pay", "Juma", "Shan", "Yak"]
    max_daily = max((r["total"] for r in daily_activity), default=0)
    daily_lines = [
        f"{weekday_names[r['day'].weekday()]} {r['day'].strftime('%d.%m')} "
        f"{_text_bar(r['total'], max_daily)} {r['total']} ({r['uniq_users']} kishi)"
        for r in daily_activity
    ]
    daily_block = "\n".join(daily_lines) if daily_lines else "— Ma'lumot yo'q —"

    # Guest Mode alohida turlar bilan yoziladi ("guest_..."), shuning
    # uchun botdagi va guest'dagi foydalanish nisbati ko'rinib turadi.
    # Fayl yaratish esa ball emas, alohida kunlik sanoqdan yechiladi —
    # shuning uchun uning ball bahosi yo'q (0).
    type_labels = {
        "text_message": ("✉️ Matn", MESSAGE_COST_TEXT),
        "photo_message": ("🖼 Rasm", MESSAGE_COST_PHOTO),
        "document_message": ("📄 Hujjat", MESSAGE_COST_DOCUMENT),
        "voice_message": ("🎤 Ovoz", MESSAGE_COST_VOICE),
        # Joylashuv o'zi ball yechmaydi — u savol emas, keyingi matnli
        # so'rov uchun kontekst. Ball o'sha matndan yechiladi.
        "location_message": ("📍 Joylashuv", 0),
        "guest_text_message": ("✉️ Matn · guest", MESSAGE_COST_TEXT),
        "guest_photo_message": ("🖼 Rasm · guest", MESSAGE_COST_PHOTO),
        "guest_document_message": ("📄 Hujjat · guest", MESSAGE_COST_DOCUMENT),
        "guest_voice_message": ("🎤 Ovoz · guest", MESSAGE_COST_VOICE),
        "file_task": ("🛠 Fayl yaratish", 0),
        # Rasm va tadqiqot ball emas, alohida kunlik sanoqdan yechiladi —
        # shuning uchun ball bahosi 0 (fayl vazifasi kabi).
        "research": ("🔎 Chuqur tadqiqot", 0),
    }
    total_cost_estimate = 0
    total_actions = 0
    guest_actions = 0
    type_lines = []
    for r in type_breakdown:
        label, cost = type_labels.get(r["activity_type"], (r["activity_type"], 0))
        estimate = r["cnt"] * cost
        total_cost_estimate += estimate
        total_actions += r["cnt"]
        if r["activity_type"].startswith("guest_"):
            guest_actions += r["cnt"]
        suffix = f" (≈{estimate} ball)" if cost else ""
        type_lines.append(f"├ {label}: <b>{r['cnt']}</b> ta{suffix}")
    type_block = "\n".join(type_lines) if type_lines else "— Ma'lumot yo'q —"

    guest_share = round(guest_actions / total_actions * 100) if total_actions else 0

    free_count = plan_counts["free_count"] if plan_counts else 0
    pro_count = plan_counts["pro_count"] if plan_counts else 0
    premium_count = plan_counts["premium_count"] if plan_counts else 0

    # Daromad qaytarilgan to'lovlarsiz hisoblanadi (revenue_stats()
    # ichida FILTER refunded_at IS NULL) — ya'ni bu netto raqam.
    plan_names = {d: t for d, _s, t, _b in PRO_PLANS}
    by_plan = " · ".join(
        f"{plan_names.get(days, f'{days} kun')}: <b>{cnt}</b>"
        for days, cnt in revenue.get('by_plan', [])
    ) or "—"

    text = (
        "👥 <b>Bot foydalanuvchilari statistikasi</b>\n\n"
        f"📌 Umumiy foydalanuvchilar: <b>{total_users}</b>\n\n"
        f"🏆 Oxirgi 30 kun eng faol:\n"
        f"├ 👤 {format_user(most_active_30days)}\n"
        f"└ 🔢 Faollik: {most_active_30days['activity_count'] if most_active_30days else 0}\n\n"
        f"🔥 Bugungi eng faol:\n"
        f"├ 👤 {format_user(most_active_today)}\n"
        f"└ 🔢 Faollik: {most_active_today['activity_count'] if most_active_today else 0}\n\n"
        f"🆕 Oxirgi foydalanuvchi:\n"
        f"├ 👤 {format_user(last_user)}\n"
        f"└ 📅 Qo'shilgan: {last_created_str}\n\n"
        f"📈 <b>So'nggi 7 kun faolligi</b>\n<pre>{daily_block}</pre>\n\n"
        f"🧩 <b>Turlar bo'yicha (30 kun)</b>\n{type_block}\n"
        f"└ Jami taxminiy xarajat: ≈<b>{total_cost_estimate}</b> ball\n"
        f"👥 Shundan Guest Mode: <b>{guest_actions}</b> ta ({guest_share}%)\n\n"
        f"📦 <b>Rejalar bo'yicha</b>\n"
        f"├ 🆓 Free: <b>{free_count}</b>\n"
        f"├ 💎 Pro (sotib olingan): <b>{pro_count}</b>\n"
        f"└ ♾️ Premium (qo'lda): <b>{premium_count}</b>\n\n"
        f"💰 <b>Daromad (Stars)</b>\n"
        f"├ Bugun: <b>{revenue.get('stars_today', 0)}</b> ⭐\n"
        f"├ 30 kun: <b>{revenue.get('stars_30d', 0)}</b> ⭐ "
        f"({revenue.get('sales_30d', 0)} ta sotuv)\n"
        f"├ Jami: <b>{revenue.get('stars_total', 0)}</b> ⭐\n"
        f"└ Qaytarilgan: <b>{revenue.get('refunds', 0)}</b> ta\n"
        f"📊 {by_plan}"
    )
    await message.answer(text, parse_mode="HTML")
