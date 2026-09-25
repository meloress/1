# -*- coding: utf-8 -*-
"""Telegram Business, 3-bosqich — "Avtomat" rejim.

Bot mijozga O'ZI javob beradi. Bu test ushlaydigan JIM nosozliklar
(REJA.md 3-bosqich):

  ⛔️ `[egasiga: …]` markeri (yoki buzilgani) mijozga ko'rinsa — mijoz
     botning ichki buyrug'ini o'qiydi.
  ⛔️ Texnik xato matni mijozga ketsa.
  ⛔️ Kunlik sanoq tugaganda mijozga "limit tugadi" deyilsa, yoki egasiga
     har xabarda qayta yozilsa.
  ⛔️ Egasi chatga o'zi yozgach bot aralashishda davom etsa (pauza yo'q).
  ⛔️ Ish vaqti yarim tun chegarasida noto'g'ri hisoblansa.
  ⛔️ Bitta chatda ikki parallel javob.

Tarmoqsiz va bazasiz ishlaydi.

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_biznes_avtomat.py
"""
import asyncio
import io
import os
import sys
from datetime import datetime
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _manba import kod  # noqa: E402

import handlers.biznes as b              # noqa: E402
from core import config as c             # noqa: E402
from db import database                  # noqa: E402
from services import ai                  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EGASI, MIJOZ, DM = 7001, 9002, 7001


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


def soat(h, m=0):
    return datetime(2026, 9, 25, h, m, tzinfo=database.TASHKENT_TZ)


# ── 1-3. Ish vaqti (Toshkent, yarim tun) ─────────────────────────
tun = "20:00-09:00"
check(1, "20:00-09:00: 23:00 va 08:59 — ishlaydi; 09:00 va 12:00 — yo'q",
      b.ish_vaqtimi(tun, soat(23)) and b.ish_vaqtimi(tun, soat(8, 59))
      and b.ish_vaqtimi(tun, soat(20)) and b.ish_vaqtimi(tun, soat(0))
      and not b.ish_vaqtimi(tun, soat(9)) and not b.ish_vaqtimi(tun, soat(12))
      and not b.ish_vaqtimi(tun, soat(19, 59)))
check(2, "kunduzgi oraliq va «doim»",
      b.ish_vaqtimi("09:00-18:00", soat(12)) and not b.ish_vaqtimi("09:00-18:00", soat(18))
      and b.ish_vaqtimi(None, soat(3)))
check(3, "vaqt_ajrat: qisqa yozuv, tire turlari, yaroqsiz qiymat",
      b.vaqt_ajrat("20-9") == "20:00-09:00" and b.vaqt_ajrat("21:30 – 08:15") == "21:30-08:15"
      and b.vaqt_ajrat("25-9") is None and b.vaqt_ajrat("9-9") is None
      and b.vaqt_ajrat("salom") is None)

# ── 4. Marker ajratish ───────────────────────────────────────────
check(4, "egasiga_ajrat: to'g'ri, buzilgan, yo'q, bo'sh sabab",
      ai.egasiga_ajrat("[egasiga: chegirma] Aniqlab aytaman.") == ("Aniqlab aytaman.", "chegirma")
      and ai.egasiga_ajrat("Salom! [egasiga: narx") == ("Salom!", None)
      and ai.egasiga_ajrat("Oddiy javob") == ("Oddiy javob", None)
      and ai.egasiga_ajrat("[ EGASIGA : ]")[1] == "—")

yoriq_a = b.mijoz_yoriqnomasi("bilim", avtomat=True)
yoriq_y = b.mijoz_yoriqnomasi("bilim")
check(5, "avtomat yo'riqnomasida marker qoidasi bor, yordamchida yo'q",
      "[egasiga:" in yoriq_a and "TO'G'RIDAN-TO'G'RI" in yoriq_a
      and "[egasiga:" not in yoriq_y and b.BUYRUQ_QOIDASI in yoriq_a)

# ── 6. Rasm yo'li: tool'siz, xotirasiz (haqiqiy get_vision_reply) ──
ushlangan, xotira = {}, []


class FakeStream:
    def __aiter__(self):
        async def gen():
            yield NS(type="response.output_text.delta", delta="Chiroyli gul!", item=None)
        return gen()

    async def get_final_response(self):
        return NS(status="completed", incomplete_details=None, usage=None)


async def fake_open(stack, modellar, **kw):
    ushlangan.update(kw)
    return FakeStream(), "fake"


async def bosh(*a, **k):
    return []


async def hech(*a, **k):
    return None


async def fake_xotira(*a, **k):
    xotira.append(a)
    return [], None


asl = (ai._open_response_stream, ai.safe_get_chat_history,
       ai.safe_history_summary_message, ai._memory_context)
(ai._open_response_stream, ai.safe_get_chat_history,
 ai.safe_history_summary_message, ai._memory_context) = (fake_open, bosh, hech, fake_xotira)


async def yig(gen):
    return [x async for x in gen]

chiqish = asyncio.run(yig(ai.get_vision_reply(
    MIJOZ, "QUJBQQ==", "bu nima?", user_id=EGASI, is_pro=True, thread_id=-EGASI,
    output_files=[], biznes_yoriqnoma=yoriq_a)))
check(6, "rasm yo'li: tool yo'q, egasi xotirasi yo'q, yo'riqnoma developer'da",
      not ushlangan.get("tools") and xotira == []
      and yoriq_a not in ushlangan["instructions"]
      and {"role": "developer", "content": yoriq_a} in ushlangan["input"]
      and "".join(chiqish) == "Chiroyli gul!")
(ai._open_response_stream, ai.safe_get_chat_history,
 ai.safe_history_summary_message, ai._memory_context) = asl


# ── Soxta dunyo ──────────────────────────────────────────────────
q = []
holat = {"model": "Atirgul 25 000 so'm.", "model_xato": None, "send_xato": None,
         "sanoq": {"allowed": True, "unlimited": False}, "soat": soat(23),
         "parallel": 0, "eng_kop": 0}
pauza = {}        # (egasi, chat) -> tugash vaqti
ochirilgan = set()
msg_id = [1000]
hamma_mijozga = []   # butun sinov davomida mijozga ketgan HAR BIR matn


class SoxtaBot:
    async def send_message(self, chat_id, text, business_connection_id=None, **kw):
        await asyncio.sleep(0)
        if business_connection_id and holat["send_xato"]:
            raise RuntimeError(holat["send_xato"])
        q.append(("send", chat_id, text, business_connection_id))
        if business_connection_id:
            hamma_mijozga.append(text)
        msg_id[0] += 1
        return NS(chat=NS(id=chat_id), message_id=msg_id[0])

    async def send_chat_action(self, chat_id, action, business_connection_id=None):
        q.append(("typing", chat_id, business_connection_id))

    async def read_business_message(self, conn_id, chat_id, message_id):
        q.append(("read", chat_id, message_id))

    async def get_file(self, file_id):
        return NS(file_path="x")

    async def download_file(self, path, dest=None):
        if dest:
            open(dest, "wb").close()
            return None
        return io.BytesIO(b"rasm")


async def soxta_gpt(chat_id, prompt, **kw):
    holat["parallel"] += 1
    holat["eng_kop"] = max(holat["eng_kop"], holat["parallel"])
    q.append(("gpt", prompt, kw.get("biznes_yoriqnoma")))
    await asyncio.sleep(0.01)
    holat["parallel"] -= 1
    if holat["model_xato"]:
        raise holat["model_xato"]
    yield holat["model"]


async def soxta_vision(chat_id, rasm, matn, **kw):
    q.append(("vision", rasm, kw.get("biznes_yoriqnoma") is not None))
    yield "Chiroyli gul!"


async def soxta_tarix(chat_id, content, role="user", thread_id=0, **kw):
    q.append(("tarix", content, role))


async def soxta_xato(chat_id, message_id, user_id, prompt, **kw):
    q.append(("xato", chat_id, kw.get("kind"), kw.get("retry"), kw.get("reason")))


async def soxta_stt(yol, is_pro):
    return "atirgul bormi?"


async def rost(*a):
    return True


async def bilim(_):
    return "Atirgul 25 000 so'm."


async def sanoq(uid, kind):
    q.append(("sanoq", kind))
    return holat["sanoq"]


async def qaytar(uid, kind):
    q.append(("refund_daily", kind))


async def chat_holati(owner, chat):
    return {"ochirilgan": (owner, chat) in ochirilgan,
            "pauza": pauza.get((owner, chat), soat(0)) > holat["soat"]
            if (owner, chat) in pauza else False}


async def soxta_pauza(owner, chat, s):
    q.append(("pauza", chat, s))
    pauza[(owner, chat)] = holat["soat"].replace(hour=(holat["soat"].hour + s) % 24) \
        if holat["soat"].hour + s < 24 else soat(23, 59)


b.bot = SoxtaBot()
b.get_gpt_reply = soxta_gpt
b.get_vision_reply = soxta_vision
b.safe_update_history = soxta_tarix
b.send_error_with_retry = soxta_xato
b.speech_to_text_smart = soxta_stt
b.track_user_activity = lambda *a: q.append(("faollik", a[-1]))
b.TEXT_MERGE_WAIT = 0.01
b.BIZNES_AVTOMAT_OCHIQ = True
b._hozir = lambda: holat["soat"]
database.pro_tarifmi = rost
database.get_maintenance_notice_for = hech
database.biznes_mijoz_korildi = hech   # 4-bosqich kartotekasi — bu testda emas
database.check_and_consume_daily = sanoq
database.refund_daily = qaytar
database.biznes_bilim_ol = bilim
database.biznes_chat_holati = chat_holati
database.biznes_pauza = soxta_pauza

UL = {"owner_id": EGASI, "owner_chat": DM, "yoqilgan": True, "rejim": "avtomat",
      "ish_vaqti": None, "huquqlar": {"can_reply": True, "can_read_messages": True}}
database._biznes_kesh["c1"] = UL


async def ulanish_bor(conn_id):
    return database.biznes_ulanish_ol(conn_id)

b._ulanish = ulanish_bor


def xabar(matn, kimdan=MIJOZ, **qosh):
    msg_id[0] += 1
    d = dict(business_connection_id="c1", text=matn, caption=None,
             sender_business_bot=None, voice=None, photo=None,
             from_user=NS(id=kimdan, username="ali", full_name="Ali"),
             chat=NS(id=MIJOZ), message_id=msg_id[0], reply_to_message=None)
    d.update(qosh)
    return NS(**d)


def ishga(*xabarlar):
    q.clear()
    b._aytilgan.clear()

    async def run():
        for x in xabarlar:
            await b.biznes_xabar(x)
        await asyncio.sleep(0.15)
    asyncio.run(run())
    return [x[0] for x in q]


def mijozga():
    """Mijozga (business_connection_id bilan) ketgan matnlar."""
    return [x[2] for x in q if x[0] == "send" and x[3]]


def egasiga():
    return [x[2] for x in q if x[0] == "send" and x[1] == DM and not x[3]]


# ── 7. Asosiy yo'l ───────────────────────────────────────────────
turlar = ishga(xabar("atirgul qancha?"))
check(7, "mijoz yozdi -> bitta javob, «yozmoqda», o'qildi, sanoq, tarix",
      mijozga() == ["Atirgul 25 000 so'm."]
      and turlar.index("typing") < turlar.index("send") < turlar.index("read")
      and ("sanoq", "biznes") in q
      and [x[2] for x in q if x[0] == "tarix"] == ["user", "assistant"]
      and ("faollik", "biznes_avtojavob") in q
      and "[egasiga:" in next(x for x in q if x[0] == "gpt")[2])

# ── 8-10. Marker ─────────────────────────────────────────────────
holat["model"] = "[egasiga: chegirma so'radi] Hozir aniqlab aytaman."
ishga(xabar("10% chegirma bering"))
check(8, "uzatish: mijozga faqat neytral gap, egasiga sabab + tugma, pauza",
      mijozga() == ["Hozir aniqlab aytaman."]
      and any("Sabab: chegirma so" in m for m in egasiga())
      and ("pauza", MIJOZ, c.BIZNES_PAUZA_SOAT) in q
      and ("faollik", "biznes_uzatish") in q)
pauza.clear()

holat["model"] = "[egasiga: sotib olmoqchi]"
ishga(xabar("olaman"))
check(9, "faqat marker -> mijozga standart neytral javob",
      mijozga() == [b.NEYTRAL_JAVOB])
pauza.clear()

holat["model"] = "Salom! [egasiga: narx so'radi"
ishga(xabar("narx?"))
check(10, "buzilgan marker mijozga ko'rinmaydi, uzatish ham emas",
      mijozga() == ["Salom!"] and not egasiga() and not pauza)
holat["model"] = "Atirgul 25 000 so'm."

# ── 11-12. Pauza ─────────────────────────────────────────────────
ishga(xabar("Kelaveringlar, men shu yerdaman", kimdan=EGASI))
check(11, "egasi o'zi yozdi -> pauza qo'yildi",
      ("pauza", MIJOZ, c.BIZNES_PAUZA_SOAT) in q and not mijozga())
ishga(xabar("rahmat"))
check(12, "pauza davomida javob yo'q (xabar tarixda qoladi)",
      not mijozga() and "gpt" not in [x[0] for x in q]
      and ("tarix", "rahmat", "user") in q)
holat["soat"] = soat(23, 59)
pauza[(EGASI, MIJOZ)] = soat(23, 30)
ishga(xabar("yana savol"))
check(13, "pauza tugagach yana javob beradi", mijozga() == ["Atirgul 25 000 so'm."])
pauza.clear()
holat["soat"] = soat(23)

# ── 14. Sanoq tugadi ─────────────────────────────────────────────
holat["sanoq"] = {"allowed": False, "limit": 50}
ishga(xabar("salom"), xabar("bormisiz?"))
# ikki alohida debounce oynasi uchun ikkinchisini kechiktirib yuboramiz
q.clear()
b._aytilgan.clear()


async def ikki_oyna():
    await b.biznes_xabar(xabar("salom"))
    await asyncio.sleep(0.1)
    await b.biznes_xabar(xabar("bormisiz?"))
    await asyncio.sleep(0.1)
asyncio.run(ikki_oyna())
check(14, "sanoq tugadi: mijozga HECH NARSA, egasiga BIR marta",
      not mijozga() and len(egasiga()) == 1 and "gpt" not in [x[0] for x in q])
holat["sanoq"] = {"allowed": True, "unlimited": False}

# ── 15-16. Xatolar ───────────────────────────────────────────────
holat["model_xato"] = RuntimeError("openai 500: Internal error")
q.clear()
b._aytilgan.clear()


async def ikki_xato():
    await b.biznes_xabar(xabar("salom"))
    await asyncio.sleep(0.1)
    await b.biznes_xabar(xabar("hey"))
    await asyncio.sleep(0.1)
asyncio.run(ikki_xato())
xatolar = [x for x in q if x[0] == "xato"]
check(15, "model xatosi: mijozga hech narsa, sanoq qaytadi, egasiga soatiga bitta",
      not mijozga() and [x[0] for x in q].count("refund_daily") == 2
      and len(xatolar) == 1 and xatolar[0][1:4] == (DM, "biznes", False)
      and "500" in xatolar[0][4])
holat["model_xato"] = None

holat["send_xato"] = "Bad Request: BUSINESS_PEER_USAGE_MISSING"
ishga(xabar("salom"))
check(16, "yuborish rad etildi: sanoq qaytadi, javob tarixga yozilmaydi",
      ("refund_daily", "biznes") in q and any(x[0] == "xato" for x in q)
      and ("tarix", "Atirgul 25 000 so'm.", "assistant") not in q)
holat["send_xato"] = None

# ── 17. Debounce + qulf ──────────────────────────────────────────
holat["eng_kop"] = 0
ishga(xabar("salom"), xabar("atirgul"), xabar("qancha?"))
check(17, "uch tez xabar -> BITTA javob, birlashgan matn bilan",
      len(mijozga()) == 1
      and [x[1] for x in q if x[0] == "gpt"] == ["salom\natirgul\nqancha?"])

q.clear()
holat["eng_kop"] = 0


async def parallel():
    await asyncio.gather(b._avtojavob(xabar("a"), "a", UL),
                         b._avtojavob(xabar("b"), "b", UL))
asyncio.run(parallel())
check(18, "bitta chatda ikki javob parallel YOZILMAYDI (qulf)", holat["eng_kop"] == 1)

# ── 19-21. To'xtash sabablari ────────────────────────────────────
ochirilgan.add((EGASI, MIJOZ))
ishga(xabar("salom"))
check(19, "chatda o'chirilgan -> javob yo'q", not mijozga())
ochirilgan.clear()

UL["ish_vaqti"] = "20:00-09:00"
holat["soat"] = soat(12)
ishga(xabar("salom"))
check(20, "ish vaqtidan tashqarida -> javob yo'q, xabar tarixda",
      not mijozga() and ("tarix", "salom", "user") in q)
holat["soat"] = soat(23)
ishga(xabar("salom"))
check(21, "ish vaqti ichida -> javob bor", len(mijozga()) == 1)
UL["ish_vaqti"] = None

b.BIZNES_AVTOMAT_OCHIQ = False
ishga(xabar("salom"))
kb = b._ekran_kb(dict(UL, rejim="buyruq"))
tugmalar = [t.callback_data for qator in kb.inline_keyboard for t in qator]
check(22, "bayroq yopiq: javob yo'q va «Avtomat» tugmasi ko'rinmaydi",
      not mijozga() and "bz:r:avtomat" not in tugmalar and "bz:r:yordamchi" in tugmalar)
b.BIZNES_AVTOMAT_OCHIQ = True
kb = b._ekran_kb(UL)
tugmalar = [t.callback_data for qator in kb.inline_keyboard for t in qator]
check(23, "avtomat ekrani: ish vaqti va chatlar tugmalari",
      {"bz:r:avtomat", "bz:w", "bz:c"} <= set(tugmalar))

# ── 24. Bot o'z xabarini taniydi ─────────────────────────────────
ishga(xabar("salom"))
yuborilgan_id = b._yuborilgan[-1]
qaytgan = xabar("Atirgul 25 000 so'm.", kimdan=EGASI, message_id=yuborilgan_id[1])
check(24, "sender_business_bot yo'q bo'lsa ham bot yuborgani «bot» (pauza qo'yilmaydi)",
      b.biznes_kimdan(qaytgan, UL) == "bot"
      and ishga(qaytgan) == [])

# ── 25-26. Ovoz va rasm ──────────────────────────────────────────
ishga(xabar(None, voice=NS(file_id="v1")))
check(25, "ovoz -> matn -> javob matnda",
      [x[1] for x in q if x[0] == "gpt"] == ["atirgul bormi?"] and len(mijozga()) == 1)
ishga(xabar(None, photo=[NS(file_id="p1")], caption="shu bormi?"))
check(26, "rasm -> vision (yo'riqnoma bilan) -> javob",
      any(x[0] == "vision" and x[2] for x in q) and mijozga() == ["Chiroyli gul!"])

UL["rejim"] = "yordamchi"
ishga(xabar(None, voice=NS(file_id="v1")))
check(27, "ovoz boshqa rejimda qayta ishlanmaydi (STT puli behuda)", q == [])
UL["rejim"] = "avtomat"

# ── 28. Mijozga hech qachon texnik matn ──────────────────────────
taqiq = ("egasiga", "❌", "Xatolik", "500", "BUSINESS_PEER", "limit", "Sabab")
check(28, f"mijozga ketgan {len(hamma_mijozga)} ta matnda xato/marker/limit izi yo'q",
      len(hamma_mijozga) >= 10
      and not [m for m in hamma_mijozga if any(t.lower() in m.lower() for t in taqiq)])

# ── 29-30. Sanoq tuzilishi ───────────────────────────────────────
check(29, "biznes sanog'i: DAILY_COUNTERS, PLAN_LIMITS (bepul 0), LIMIT_NOMI, LIMIT_IZOHI",
      c.DAILY_COUNTERS["biznes"] == ("daily_biznes_used", "daily_biznes_date", "biznes")
      and c.PLAN_LIMITS["free"]["biznes"] == 0 and c.PLAN_LIMITS["premium"]["biznes"] is None
      and c.PLAN_LIMITS["pro"]["biznes"] > 0
      and "biznes" in c.LIMIT_NOMI and "biznes" in c.LIMIT_IZOHI
      and {"biznes_avtojavob", "biznes_uzatish"} <= set(c.ACTIVITY_TYPES))
manba = kod(os.path.join(ROOT, "db", "database.py"))
check(30, "ustunlar migratsiyada, pauza SQL'da NOW() bilan solishtiriladi",
      "daily_biznes_used INTEGER" in manba and "daily_biznes_date DATE" in manba
      and "pauza_gacha > NOW()" in manba and "make_interval(hours => $3::int)" in manba)
check(31, "avtomat bayrog'i asl holda YOPIQ (REJA: o'lchovsiz ochilmaydi)",
      c.BIZNES_AVTOMAT_OCHIQ is False)

print("\nHammasi o'tdi: 31/31")
