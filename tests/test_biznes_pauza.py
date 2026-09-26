# -*- coding: utf-8 -*-
"""Telegram Business — uzatishdan keyin jim qolmaslik va alifbo.

Jonli sinov (2026-09-26): bot "10 da CS2 ga borasanmi?" savolini to'g'ri
egasiga uzatdi va "кейин aytaman" (ikki alifbo aralash!) deb yozdi. Keyin
suhbatdosh yana yozdi — javobsiz qoldi. Avval 3 soat pauza + bir marta
"Hozir bandman" qilingan edi; egasi buni ham "javob bermayapti" deb ko'rdi
va so'radi: "Og'abek online bo'lganda o'zi javob beradi" desin, keyin
javob beraversin. Bu test ushlaydigan jim nosozliklar:

  ⛔️ uzatishdan keyin suhbatdosh javobsiz qoladi (pauza qaytib kelgan);
  ⛔️ bazada qolgan eski 'uzatish' pauzasi botni jim qiladi;
  ⛔️ egasi O'ZI yozgan suhbatga bot aralashadi (u pauza qolishi shart);
  ⛔️ lotinda yozgan suhbatdoshga kirill harfli javob ketadi.

Tarmoqsiz va bazasiz ishlaydi.

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_biznes_pauza.py
"""
import asyncio
import os
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import handlers.biznes as b              # noqa: E402
from db import database                  # noqa: E402

EGASI, MIJOZ, DM = 7001, 9002, 7001


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


# ── 1-3. Alifbo ──────────────────────────────────────────────────
L = b.uz_lotinga
check(1, "o'zbek kirill → lotin: ў, ғ, қ, ҳ, ш, ё, е (so'z boshida ye)",
      [L(x) for x in ("кейин aytaman.", "Ўзбекистон", "ғалаба", "Қўқон", "Шаҳар",
                      "Ёшлар", "ер", "кечаси")]
      == ["keyin aytaman.", "O'zbekiston", "g'alaba", "Qo'qon", "Shahar",
          "Yoshlar", "yer", "kechasi"])
check(2, "suhbatdosh lotinda — javobdagi kirill o'giriladi",
      b.alifboga_mosla("кейин aytaman", "bugun borasanmi") == "keyin aytaman")
check(3, "suhbatdosh kirillda (rus/o'zbek) yoki javob toza lotin — TEGILMAYDI",
      b.alifboga_mosla("Завтра напишу", "завтра придешь?") == "Завтра напишу"
      and b.alifboga_mosla("Salom!", "salom") == "Salom!")

# ── Soxta dunyo ──────────────────────────────────────────────────
q = []
holat = {"model": "Salom!", "pauza": None, "band_yuborildi": False, "tanlov": None}


class SoxtaBot:
    async def send_message(self, chat_id, text, business_connection_id=None, **kw):
        q.append(("send", chat_id, text, business_connection_id, kw.get("reply_markup")))
        return NS(chat=NS(id=chat_id), message_id=len(q) + 900)

    async def send_chat_action(self, *a, **k):
        pass

    async def read_business_message(self, *a, **k):
        pass


async def soxta_gpt(chat_id, prompt, **kw):
    yield holat["model"]


async def hech(*a, **k):
    return None


async def rost(*a):
    return True


async def ruxsat(*a):
    return {"allowed": True, "unlimited": False}


async def bosh(*a, **k):
    return {}


async def bilim(_):
    return ""


async def chat_holati(owner, chat):
    p = holat["pauza"]
    return {"ochirilgan": False, "pauza": p is not None, "uzatish": p == "uzatish"}


async def pauza(owner, chat, soat, sabab="egasi"):
    holat["pauza"], holat["band_yuborildi"] = sabab, False
    q.append(("pauza", sabab))


async def band_ol(owner, chat):
    # SQL kabi atomik: faqat uzatish pauzasida va bir marta.
    if holat["pauza"] == "uzatish" and not holat["band_yuborildi"]:
        holat["band_yuborildi"] = True
        return True
    return False


async def kutayotgan(owner, chat):
    return holat["tanlov"]


async def yarat(*a):
    return 1


async def tarix(chat_id, content, role="user", thread_id=0, **kw):
    q.append(("tarix", content, role))


async def birinchi(*a, **k):
    return True

b.bot = SoxtaBot()
b.get_gpt_reply = soxta_gpt
b.safe_update_history = tarix
b.track_user_activity = lambda *a: None
b.BIZNES_MERGE_WAIT = 0.01
b._birinchi_marta = birinchi
for nom, f in dict(pro_tarifmi=rost, get_maintenance_notice_for=hech,
                   biznes_mijoz_korildi=hech, check_and_consume_daily=ruxsat,
                   refund_daily=hech, biznes_bilim_ol=bilim, biznes_uslub_ol=bosh,
                   biznes_namuna_qosh=bosh, biznes_chat_holati=chat_holati,
                   biznes_pauza=pauza,
                   biznes_kutayotgan_tanlov=kutayotgan, biznes_loyiha_eskirt=hech,
                   biznes_loyiha_yarat=yarat, biznes_mavzu_ol=hech).items():
    setattr(database, nom, f)

UL = {"owner_id": EGASI, "owner_chat": DM, "yoqilgan": True, "rejim": "avtomat",
      "ish_vaqti": None, "avto_belgi": False,
      "huquqlar": {"can_reply": True, "can_read_messages": True}}
database._biznes_kesh["c1"] = UL


async def ulanish_bor(conn_id):
    return database.biznes_ulanish_ol(conn_id)

b._ulanish = ulanish_bor
mid = [100]


def xabar(matn, kimdan=MIJOZ):
    mid[0] += 1
    return NS(business_connection_id="c1", text=matn, caption=None,
              sender_business_bot=None, voice=None, photo=None,
              from_user=NS(id=kimdan, username="ali", full_name="Ali"),
              chat=NS(id=MIJOZ), message_id=mid[0], reply_to_message=None)


def ishga(*xabarlar):
    q.clear()

    async def run():
        for x in xabarlar:
            await b.biznes_xabar(x)
            await asyncio.sleep(0.05)
    asyncio.run(run())


def mijozga():
    return [x[2] for x in q if x[0] == "send" and x[3]]


def egasiga():
    return [x for x in q if x[0] == "send" and not x[3]]


# ── 4-5. Uzatish: kirill neytral gap lotinga, pauza YO'Q ─────────
holat["model"] = "[tanlov: 10 da borasizmi? | boraman | bugun yo'q] кейин aytaman."
ishga(xabar("bugun kech 10 larda cs2 ga borasanmi?"))
check(4, "uzatishdagi neytral gap lotinga o'girildi (suhbatdosh lotinda yozgan)",
      mijozga() == ["keyin aytaman."])
check(5, "uzatishdan keyin pauza qo'yilmaydi", not any(x[0] == "pauza" for x in q))

# ── 6. Uzatishdan keyin yana yozdi — har biriga javob ────────────
holat["model"] = "Salom!"
ishga(xabar("nimaga sen kimsan"), xabar("aloo"))
check(6, "uzatishdan keyin suhbatdosh yana yozsa — bot javob beraveradi",
      mijozga() == ["Salom!", "Salom!"])

# ── 7. Bazada qolgan eski 'uzatish' pauzasi e'tiborsiz ───────────
holat["pauza"] = "uzatish"
ishga(xabar("hali ham?"))
check(7, "eski 'uzatish' pauzasi botni jim qilmaydi", mijozga() == ["Salom!"])

# ── 8. Egasi o'zi yozgan pauza — jimlik ──────────────────────────
holat["pauza"] = None
ishga(xabar("kelaman", kimdan=EGASI), xabar("zo'r, kutaman"))
check(8, "egasi o'zi yozgan (uning qo'lidagi) suhbat: bot JIM",
      ("pauza", "egasi") in q and mijozga() == [])

# ── 9. Neytral gap ───────────────────────────────────────────────
check(9, "neytral gap egasining ismi bilan, hech narsa va'da qilmaydi",
      b.neytral_gap("Og'abek") == "Og'abek online bo'lganda o'zi javob beradi."
      and b.neytral_gap(None).startswith("Akkaunt egasi")
      and "Og'abek online" in b.mijoz_yoriqnomasi("", avtomat=True, ism="Og'abek"))

check(10, "variantdan neytral gap va egasining ismi olib tashlanadi (egasi bosadi)",
      b.egasi_variantlari(["Ha, boraman", "Og'abek online bo'lganda o'zi javob beradi.",
                           "Og'abek bormaydi", "Олимжон онлайн будет"], "Og'abek")
      == ["Ha, boraman"])

print("\nHammasi o'tdi: 10/10")
