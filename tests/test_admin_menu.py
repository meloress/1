"""Reply-klaviatura 4 tugmaga yig'ilgandan keyin hech bir ekran
yo'qolmaganini va inline yo'l ishlashini tekshiradi.

Eng muhim tekshiruv — 5-band: callback'dagi `query.message` BOTNING
xabari, ya'ni admin tekshiruvi uni rad etardi. Nusxa almashtirilmasa
har bir tugma "faqat admin uchun" deb javob berardi.

Ishga tushirish:  PYTHONIOENCODING=utf-8 python tests/test_admin_menu.py
"""
import asyncio
import inspect
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Bot  # noqa: E402
from aiogram.types import CallbackQuery, Chat, Message, User  # noqa: E402

from core.keyboards import admin_keyboard  # noqa: E402
from handlers.admin import menu  # noqa: E402


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


matnlar = [b.text for row in admin_keyboard.keyboard for b in row]
check(1, "klaviaturada 4 ta tugma", len(matnlar) == 4)

# Menyulardagi har bir tugma haqiqiy ekranga borishi kerak — havolasi
# yo'q tugma jimgina hech narsa qilmaydi.
kalitlar = [k for _, k in menu.USERS_MENU + menu.SETTINGS_MENU]
check(2, "har bir menyu tugmasining ekrani bor",
      all(k in menu.ACTIONS for k in kalitlar))
check(3, "ortiqcha ekran qolmagan", set(kalitlar) == set(menu.ACTIONS))

# Klaviaturadan olib tashlangan tugmalar hali ham handlerda ro'yxatdan
# o'tgan (eski klaviatura uchun) — nomlar menyuda ham aynan o'sha.
olib_tashlangan = ["📊 Statistika", "🏆 Faol foydalanuvchilar",
                   "📄 Userlar ro'yxati", "🔍 Foydalanuvchini boshqarish",
                   "🎁 Bepul Pro", "👥 Referal sharti", "🛠 Texnik ta'til",
                   "👁 Kuzatish", "➕ Admin qo'shish", "➖ Admin o'chirish"]
menyu_nomlari = [n for n, _ in menu.USERS_MENU + menu.SETTINGS_MENU]
check(4, "olib tashlangan 10 tugmaning hammasi menyuda",
      all(n in menyu_nomlari for n in olib_tashlangan))

# Ekranlar faqat (message) yoki (message, state) qabul qiladi —
# menu_callback shundan kelib chiqib chaqiradi.
check(5, "ekran imzolari kutilganidek", all(
    list(inspect.signature(fn).parameters) in (["message"], ["message", "state"])
    for fn in menu.ACTIONS.values()))


# ── Dispatch: kim bosgani saqlanadimi ────────────────────────────
chaqirilgan = {}


async def soxta_ekran(message):
    chaqirilgan["message"] = message


async def soxta_ekran_state(message, state):
    chaqirilgan["message"] = message
    chaqirilgan["state"] = state


async def _sinov():
    menu.ACTIONS = {"a": soxta_ekran, "b": soxta_ekran_state}
    menu.require_admin_or_deny_query = lambda q: _q(True)
    CallbackQuery.answer = lambda self, *a, **k: _q(None)

    bot = Bot.__new__(Bot)
    bot_msg = Message(message_id=1, date=datetime.now(),
                      chat=Chat(id=500, type="private"),
                      from_user=User(id=1, is_bot=True, first_name="bot")).as_(bot)
    admin = User(id=777, is_bot=False, first_name="admin")
    q = CallbackQuery(id="1", from_user=admin, chat_instance="x",
                      data="am:a", message=bot_msg).as_(bot)

    await menu.menu_callback(q, state=None)
    m = chaqirilgan["message"]
    check(6, "ekranga bosgan ADMIN uzatiladi (bot emas)", m.from_user.id == 777)
    check(7, "chat o'zgarmaydi", m.chat.id == 500)
    check(8, "bot ulanishi saqlanadi", m.bot is bot)

    chaqirilgan.clear()
    await menu.menu_callback(q.model_copy(update={"data": "am:b"}).as_(bot), "HOLAT")
    check(9, "state kutgan ekranga uzatiladi", chaqirilgan.get("state") == "HOLAT")

    chaqirilgan.clear()
    await menu.menu_callback(q.model_copy(update={"data": "am:yoq"}).as_(bot), None)
    check(10, "noma'lum kalit yiqilmaydi", not chaqirilgan)


def _q(value):
    async def _inner():
        return value
    return _inner()


asyncio.run(_sinov())

print("\nHammasi o'tdi: 10/10")
