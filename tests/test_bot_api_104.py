"""Bot API 10.4 imkoniyatlari uchun tekshiruvlar.

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_bot_api_104.py

Tarmoqqa ham, bazaga ham murojaat qilmaydi — hamma tashqi chaqiruv
o'rniga soxta (fake) funksiya qo'yiladi.
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _manba import kod
from handlers import biznes as b
from handlers import messages as msg
from handlers import pro as pro_module

failures = []


def check(n, label, cond):
    if cond:
        print(f"[{n}] {label} OK")
    else:
        print(f"[{n}] {label} XATO")
        failures.append(label)


class _Chat:
    def __init__(self, t, cid=555):
        self.type = t
        self.id = cid


class _User:
    def __init__(self, uid):
        self.id = uid


class _Msg:
    def __init__(self, chat_type, uid=777, thread=None):
        self.chat = _Chat(chat_type, uid if chat_type == "private" else -100)
        self.from_user = _User(uid)
        self.message_thread_id = thread
        self.is_topic_message = thread is not None


class _Query:
    id = "cbq-42"

    def __init__(self, uid):
        self.from_user = _User(uid)


BOT_ID = 999   # guruhdagi tugma xabarining `from_user` i — botning o'zi


# ─────────────────────────────────────────────────────────────
# 1-4. TUGMAGA EPHEMERAL JAVOB — oluvchi tugmani bosgan odam
# ─────────────────────────────────────────────────────────────
bot_xabari = _Msg("supergroup", uid=BOT_ID)
q = _Query(777)
check(1, "tugmadan: oluvchi — bosgan odam, bot EMAS, callback_query_id bor",
      msg.ephemeral_params(bot_xabari, q)
      == {"ephemeral_message_parameters": {"receiver_user_id": 777,
                                           "callback_query_id": "cbq-42"}})
check(2, "shaxsiy chatda tugmadan ham ephemeral QO'YILMAYDI",
      msg.ephemeral_params(_Msg("private"), q) == {})
check(3, "query'siz eski xatti-harakat o'zgarmagan",
      msg.ephemeral_params(_Msg("supergroup"))
      == {"ephemeral_message_parameters": {"receiver_user_id": 777}})

# Limit xabari haqiqatda bosgan odamga ketadimi — `send_rich` ushlanadi.
_yuborilgan = []


async def _fake_send_rich(target, text, kb=None, **extra):
    _yuborilgan.append(extra)


pro_module.send_rich = _fake_send_rich
asyncio.run(msg._send_limit_reached_message(
    bot_xabari, {"used": 30, "limit": 30, "plan": "free"}, feature="text", query=q))
check(4, "limit xabari (tugmadan) bosgan odamga ephemeral ketadi",
      _yuborilgan
      and _yuborilgan[-1]["ephemeral_message_parameters"]["receiver_user_id"] == 777)

check(5, "«Qayta so'rash» limit xabariga query'ni uzatadi",
      "query=query" in kod(Path(__file__).parent.parent / "handlers" / "callbacks.py"))


# ─────────────────────────────────────────────────────────────
# 6-9. /biznes — «💼 Biznes» mavzusiga havola
# ─────────────────────────────────────────────────────────────
_mavzu_chaqirildi = []


async def _fake_mavzu(dm, yangi=False):
    _mavzu_chaqirildi.append(dm)
    return 88


b.biznes_mavzusi = _fake_mavzu
pro_module.BOT_USERNAME = "vexonai"
b.database.biznes_egasi_ulanishi = lambda uid, **kw: (1, {"yoqilgan": True})

qator = asyncio.run(b._mavzu_tugmasi(_Msg("private")))
check(6, "mavzudan tashqarida — t.me/<bot>/<thread_id> tugmasi",
      qator and qator[0].url == "https://t.me/vexonai/88")
check(7, "mavzuning o'zida — tugma yo'q",
      asyncio.run(b._mavzu_tugmasi(_Msg("private", thread=88))) is None)
check(8, "boshqa mavzuda — tugma bor",
      asyncio.run(b._mavzu_tugmasi(_Msg("private", thread=5))) is not None)

b.database.biznes_egasi_ulanishi = lambda uid, **kw: None
_mavzu_chaqirildi.clear()
check(9, "ulanmagan egaga — tugma yo'q va mavzu OCHILMAYDI",
      asyncio.run(b._mavzu_tugmasi(_Msg("private"))) is None and not _mavzu_chaqirildi)


# ─────────────────────────────────────────────────────────────
# 10-12. «💎 Pro tarifga o'tish» guruhda — faqat bosganga, xarid DM'da
# ─────────────────────────────────────────────────────────────
class _State:
    async def clear(self):
        pass


class _ProQuery:
    def __init__(self, chat_type):
        self.id = "cbq-7"
        self.data = "pro:open"
        self.from_user = _User(777)
        self.message = _Msg(chat_type, uid=BOT_ID)

    async def answer(self, *a, **k):
        pass


_rich_chaqiruv, _ekran_chizildi = [], []


async def _send_rich_soxta(target, text, kb=None, effect=None, **extra):
    _rich_chaqiruv.append((text, kb, extra))


async def _ekran_soxta(uid):
    _ekran_chizildi.append(uid)
    return "PRO EKRANI", None

pro_module.send_rich = _send_rich_soxta
pro_module._render_pro_screen = _ekran_soxta
asyncio.run(pro_module.handle_pro_callback(_ProQuery("supergroup"), _State()))
matn, kb, extra = _rich_chaqiruv[-1]
url = kb.inline_keyboard[0][0].url if kb else ""
check(10, "guruhda Pro ekrani CHIZILMAYDI — bosganga ephemeral havola (?start=pro)",
      not _ekran_chizildi and url == "https://t.me/vexonai?start=pro"
      and extra["ephemeral_message_parameters"] == {"receiver_user_id": 777,
                                                    "callback_query_id": "cbq-7"})
asyncio.run(pro_module.handle_pro_callback(_ProQuery("private"), _State()))
check(11, "shaxsiy chatda — Pro ekrani odatdagidek, ephemeral'siz",
      _ekran_chizildi == [777] and _rich_chaqiruv[-1][0] == "PRO EKRANI"
      and not _rich_chaqiruv[-1][2])

start = kod(Path(__file__).parent.parent / "handlers" / "messages.py")
i_pro = start.find('if start_payload == "pro" and message.chat.type == "private":')
check(12, "/start pro — Pro ekrani, salomlashuvdan OLDIN va ban/admin tekshiruvidan KEYIN",
      0 < start.find("if await is_banned(message.from_user.id):") < i_pro
      < start.find("await message.answer(_greeting_text(premium=True)"))

# ─────────────────────────────────────────────────────────────
print("─" * 55)
if failures:
    print(f"❌ {len(failures)} ta tekshiruv yiqildi:")
    for f in failures:
        print(f"   • {f}")
    sys.exit(1)
print("✅ Bot API 10.4 tekshiruvlari — hammasi o'tdi")
