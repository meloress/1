# -*- coding: utf-8 -*-
"""Telegram Business, 2-bosqich — biznes bilimi va "Yordamchi" rejimi.

Mijoz yozadi → bot javob LOYIHASINI egasiga ko'rsatadi → yuborishni egasi
hal qiladi. Bu test ushlaydigan JIM nosozliklar (REJA.md 2-bosqich):

  ⛔️ Bilim `instructions`'ga tushsa — prompt keshi HAMMA uchun buziladi.
  ⛔️ Mijoz yo'lida tool'lar bo'lsa — mijoz egasining kvotasidan rasm
     chizdiradi, internetga chiqaradi.
  ⛔️ "Yuborish"ni ikki marta bosish — mijozga ikki xabar.
  ⛔️ Rad etilgan yuborish "yuborildi" deb yozilsa — egasi aldanadi.
  ⛔️ Egasi o'zi javob bergach eski loyiha yuborilsa — mijozga ikkinchi,
     eskirgan javob.

Tarmoqsiz va bazasiz ishlaydi.

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_biznes_yordamchi.py
"""
import asyncio
import os
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _manba import kod  # noqa: E402

import handlers.biznes as b              # noqa: E402
from core import config as c             # noqa: E402
from core.memory import text_merge_buffers  # noqa: E402
from db import database                  # noqa: E402
from services import ai                  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EGASI, MIJOZ, DM = 7001, 9002, 7001
BILIM = "Gul do'koni. Atirgul 25 000 so'm. Chilonzor 5. Ish vaqti 9:00-21:00."


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


# ── 1-3. Mijoz yo'li modelga nima yuboradi (haqiqiy get_openai_reply) ──
class FakeFinal:
    status = "completed"
    incomplete_details = None
    usage = None


class FakeStream:
    def __aiter__(self):
        async def gen():
            yield NS(type="response.output_text.delta", delta="Salom!", item=None)
        return gen()

    async def get_final_response(self):
        return FakeFinal()


ushlangan = {}
xotira_chaqirildi = []


async def fake_open(stack, candidate_models, **kw):
    ushlangan.update(kw)
    return FakeStream(), "fake"


async def bosh(*a, **k):
    return []


async def hech(*a, **k):
    return None


async def fake_xotira(*a, **k):
    xotira_chaqirildi.append(a)
    return [], {"role": "developer", "content": "EGASINING SHAXSIY XOTIRASI"}


asl = (ai._open_response_stream, ai.safe_get_chat_history,
       ai.safe_history_summary_message, ai._memory_context)
ai._open_response_stream = fake_open
ai.safe_get_chat_history = bosh
ai.safe_history_summary_message = hech
ai._memory_context = fake_xotira


async def yig(gen):
    return [x async for x in gen]


yoriq = b.mijoz_yoriqnomasi(BILIM)
asyncio.run(yig(ai.get_openai_reply(
    MIJOZ, "atirgul qancha?", user_id=EGASI, is_pro=True, thread_id=-EGASI,
    tools_enabled=True,            # ⚠️ ataylab True: yoriqnoma baribir o'chirishi shart
    biznes_yoriqnoma=yoriq)))
kirish = str(ushlangan.get("input"))
check(1, "bilim instructions'da YO'Q, developer xabarda BOR",
      BILIM not in ushlangan["instructions"] and BILIM in kirish
      and any(m.get("role") == "developer" and BILIM in m.get("content", "")
              for m in ushlangan["input"]))
check(2, "mijoz yo'lida tool schema'lari yo'q (tools_enabled=True bo'lsa ham)",
      not ushlangan.get("tools"))
check(3, "egasining shaxsiy xotirasi mijoz yo'liga qo'shilmaydi",
      xotira_chaqirildi == [] and "EGASINING SHAXSIY XOTIRASI" not in kirish)

# Oddiy yo'l o'zgarmagan: yoriqnomasiz tool'lar bor, xotira o'qiladi.
ushlangan.clear()
asyncio.run(yig(ai.get_openai_reply(1, "salom", user_id=EGASI, is_pro=True)))
check(4, "oddiy yo'l o'zgarmagan (tool'lar bor, xotira o'qiladi)",
      ushlangan.get("tools") and xotira_chaqirildi)
(ai._open_response_stream, ai.safe_get_chat_history,
 ai.safe_history_summary_message, ai._memory_context) = asl

check(5, "yoriqnoma: mijoz tili, bilimdan tashqarisini to'qimaslik, muqaddimasiz",
      "o'sha tilda" in yoriq and "o'ylab topma" in yoriq
      and b.BUYRUQ_QOIDASI in yoriq and "(egasi hali yozmagan)" in b.mijoz_yoriqnomasi(""))

# ── 6-8. Bilim tozalash ──────────────────────────────────────────
ok, xato = database.clean_biznes_bilim(
    "Tel: +998 90 123 45 67\nNarxlar: 50 000 80 000 120 000 so'm")
check(6, "telefon va narx ro'yxati o'tadi, qatorlar saqlanadi",
      xato is None and "\n" in ok)
check(7, "karta / pasport raqami rad etiladi",
      all(database.clean_biznes_bilim(t)[1] for t in (
          "Kartaga: 8600 1234 5678 9012", "8600123456789012",
          "8600-1234-5678-9012", "pasport AA1234567")))
check(8, "chegaradan uzun — KESILMAYDI, rad etiladi",
      database.clean_biznes_bilim("a" * (c.BIZNES_BILIM_MAX + 1))[0] == ""
      and database.clean_biznes_bilim("   ")[1])


# ── Soxta dunyo (yordamchi oqimi) ────────────────────────────────
q = []
loyihalar = {}


class SoxtaBot:
    xato = None

    async def send_message(self, chat_id, text, business_connection_id=None, **kw):
        await asyncio.sleep(0)
        if business_connection_id and self.xato:
            raise RuntimeError(self.xato)
        q.append(("send", chat_id, text, business_connection_id))


async def soxta_band(lid, owner, holat="kutmoqda", yangi="yuborilmoqda"):
    # Postgres UPDATE ... WHERE holat = $3 RETURNING kabi ATOMIK:
    # kutish OLDIN, tekshir-va-yoz bitta qadamda.
    await asyncio.sleep(0)
    r = loyihalar.get(lid)
    if not r or r["owner_id"] != owner or r["holat"] != holat:
        return None
    r["holat"] = yangi
    return dict(r)


async def soxta_yakun(lid, owner, holat, yakuniy=None):
    loyihalar[lid]["holat"] = holat
    q.append(("yakun", lid, holat))


async def soxta_yarat(owner, conn_id, chat_id, matn, loyiha, variantlar=None):
    lid = len(loyihalar) + 1
    loyihalar[lid] = dict(id=lid, owner_id=owner, conn_id=conn_id, chat_id=chat_id,
                          mijoz_matni=matn, loyiha=loyiha, holat="kutmoqda")
    q.append(("yarat", matn, loyiha))
    return lid


async def soxta_eskirt(owner, chat_id):
    q.append(("eskirt", chat_id))


async def soxta_gpt(chat_id, prompt, **kw):
    q.append(("gpt", prompt, kw.get("biznes_yoriqnoma") is not None))
    yield "Atirgul 25 000 so'm."


async def soxta_tarix(chat_id, content, role="user", thread_id=0, **kw):
    q.append(("tarix", content, role))


async def rost(*a):
    return True


async def bilim(_):
    return BILIM


async def kvota(*a):
    return {"allowed": True, "unlimited": False}


b.bot = SoxtaBot()
b.get_gpt_reply = soxta_gpt
b.safe_update_history = soxta_tarix
b.track_user_activity = lambda *a: q.append(("faollik", a[-1]))
b.TEXT_MERGE_WAIT = 0.01
# «💼 Biznes» mavzusi: bazada yo'q, soxta bot mavzu ocha olmaydi -> mavzusiz.
database.biznes_mavzu_ol = lambda *a, **k: _mavzusiz()


async def _mavzusiz():
    return None


database.pro_tarifmi = rost
database.get_maintenance_notice_for = hech
database.biznes_mijoz_korildi = hech   # 4-bosqich kartotekasi — bu testda emas
database.check_and_consume_quota = kvota
database.biznes_bilim_ol = bilim
database.biznes_loyiha_band = soxta_band
database.biznes_loyiha_yakun = soxta_yakun
database.biznes_loyiha_yarat = soxta_yarat
database.biznes_loyiha_eskirt = soxta_eskirt
# Uslub (5-bosqich) — test_biznes_uslub.py da; bu yerda bo'sh.
database.biznes_uslub_ol = lambda *a, **k: bilim_uslub()
database.biznes_namuna_qosh = lambda *a, **k: namuna_qosh()


async def bilim_uslub():
    return {}


async def namuna_qosh():
    return 0, 0

UL = {"owner_id": EGASI, "owner_chat": DM, "yoqilgan": True, "rejim": "yordamchi",
      "huquqlar": {"can_reply": True, "can_read_messages": True}}
database._biznes_kesh["c1"] = UL


async def ulanish_bor(conn_id):
    return database.biznes_ulanish_ol(conn_id)

b._ulanish = ulanish_bor


def xabar(matn, kimdan=MIJOZ):
    return NS(business_connection_id="c1", text=matn, caption=None,
              sender_business_bot=None,
              from_user=NS(id=kimdan, username="u", full_name="Ali <b>"),
              chat=NS(id=MIJOZ), message_id=55, reply_to_message=None)


async def ketma_ket(*matnlar):
    for m in matnlar:
        await b.biznes_xabar(xabar(m))
    await asyncio.sleep(0.2)


# ── 9-11. Debounce va loyiha ─────────────────────────────────────
q.clear()
asyncio.run(ketma_ket("salom", "atirgul qancha?"))
turlar = [x[0] for x in q]
check(9, "ikki tez xabar -> BITTA loyiha, birlashgan matn bilan",
      turlar.count("gpt") == 1 and ("yarat", "salom\natirgul qancha?",
                                    "Atirgul 25 000 so'm.") in q)
check(10, "tarix modeldan KEYIN (model xabarni ikki marta ko'rmasin), mijozga hech narsa",
      turlar.index("gpt") < turlar.index("tarix")
      and not any(x[0] == "send" and x[3] for x in q)
      and next(x for x in q if x[0] == "gpt")[2] is True)
dm_xabar = [x for x in q if x[0] == "send" and x[1] == DM]
check(11, "loyiha egasiga (bot DM), ism html-escape qilingan",
      len(dm_xabar) == 1 and "Ali &lt;b&gt;" in dm_xabar[0][2]
      and ("faollik", "biznes_loyiha") in q)
check(12, "debounce bufer manfiy kalit bilan, keyin tozalanadi",
      (MIJOZ, -EGASI) not in text_merge_buffers)

# ── 13. Ikki marta bosish ────────────────────────────────────────
lid = max(loyihalar)
q.clear()


async def ikki_bosish():
    return await asyncio.gather(b.loyihani_yubor(lid, EGASI),
                                b.loyihani_yubor(lid, EGASI))

natija = asyncio.run(ikki_bosish())
yuborilgan = [x for x in q if x[0] == "send"]
check(13, "«Yuborish» parallel ikki marta -> BITTA sendMessage",
      len(yuborilgan) == 1 and yuborilgan[0][3] == "c1"
      and sum(r.startswith("✅") for r in natija) == 1
      and loyihalar[lid]["holat"] == "yuborildi")
check(14, "yuborilgan javob tarixga egasi (assistant) sifatida",
      ("tarix", "Atirgul 25 000 so'm.", "assistant") in q)

# SQL o'zi ham atomik bo'lishi shart — soxta baza buni ko'rsata olmaydi.
manba = kod(os.path.join(ROOT, "db", "database.py"))
band = manba.split("async def biznes_loyiha_band", 1)[1].split("\nasync def ", 1)[0]
check(15, "biznes_loyiha_band: bitta UPDATE ... WHERE holat ... RETURNING, SELECT yo'q",
      "UPDATE biznes_loyiha" in band and "holat = $3" in band
      and "RETURNING" in band and "SELECT" not in band
      and "owner_id = $2" in band and "make_interval(hours" in band)

# ── 16. 24 soat rad etildi ───────────────────────────────────────
lid2 = asyncio.run(soxta_yarat(EGASI, "c1", MIJOZ, "hali bormi?", "Ha, bor."))
b.bot.xato = "Bad Request: BUSINESS_PEER_USAGE_MISSING"
q.clear()
javob = asyncio.run(b.loyihani_yubor(lid2, EGASI))
check(16, "rad etilsa egasiga aniq sabab, holat «yuborildi» EMAS (qayta bosish mumkin)",
      javob.startswith("⚠️") and "BUSINESS_PEER_USAGE_MISSING" in javob
      and loyihalar[lid2]["holat"] == "kutmoqda"
      and not any(x[0] == "tarix" for x in q))
b.bot.xato = None

# ── 17. Tahrirlash ───────────────────────────────────────────────
q.clear()
javob = asyncio.run(b.loyihani_yubor(lid2, EGASI, "Ha, ertaga ham bor."))
check(17, "tahrir: egasining matni ketadi, holat «tahrirlandi» (o'lchov uchun)",
      javob.startswith("✅") and loyihalar[lid2]["holat"] == "tahrirlandi"
      and ("send", MIJOZ, "Ha, ertaga ham bor.", "c1") in q)
check(18, "begona egasi loyihani yubora olmaydi",
      asyncio.run(b.loyihani_yubor(lid2, EGASI + 1)).startswith("Bu loyiha"))

# ── 19. Egasi o'zi yozdi ─────────────────────────────────────────
q.clear()
asyncio.run(b.biznes_xabar(xabar("Ha, bor, keling", kimdan=EGASI)))
turlar = [x[0] for x in q]
check(19, "egasi o'zi yozsa: loyiha eskiradi, yangi loyiha yozilmaydi",
      ("eskirt", MIJOZ) in q and "gpt" not in turlar
      and ("tarix", "Ha, bor, keling", "assistant") in q)

# ── 20-21. Boshqa rejimlar ───────────────────────────────────────
UL["rejim"] = "kuzatuv"
q.clear()
asyncio.run(ketma_ket("salom"))
check(20, "kuzatuv: faqat tarix — na model, na loyiha, na eskirtish",
      [x[0] for x in q] == ["tarix"])
UL["rejim"] = "yordamchi"
UL["huquqlar"] = {"can_read_messages": True}
q.clear()
b._aytilgan.clear()
asyncio.run(ketma_ket("salom"))
check(21, "can_reply yo'q: loyiha yozilmaydi, egasiga bir marta tushuntirish",
      "gpt" not in [x[0] for x in q]
      and any(x[0] == "send" and x[1] == DM for x in q))
UL["huquqlar"] = {"can_reply": True, "can_read_messages": True}

# ── 22-24. Ekran, ro'yxatga olish, uyg'otish himoyasi ────────────
check(22, "ekran: rejim, bilim uzunligi, bilimsiz ogohlantirish",
      "Yordamchi" in b.ekran_matni(UL, BILIM) and str(len(BILIM)) in b.ekran_matni(UL, BILIM)
      and "hech narsa bilmayman" in b.ekran_matni(UL, "")
      and "Ulanmagan" in b.ekran_matni(None, ""))

main = kod(os.path.join(ROOT, "main.py"))
check(23, "bilim/tahrir FSM'lari AI handlerlaridan OLDIN ro'yxatda",
      main.index("process_bilim") < main.index("register(handle_text")
      and main.index("process_tahrir") < main.index("register(handle_text")
      and 'Command("biznes")' in main and 'startswith("bz:")' in main)

msg = kod(os.path.join(ROOT, "handlers", "messages.py"))
uygot = msg.split("keyingi = next(", 1)[1][:200]
check(24, "DM navbati business (manfiy) buferini uyg'otmaydi",
      "k[1] >= 0" in uygot)

check(25, "yangi faollik turlari ACTIVITY_TYPES'da",
      {"biznes_loyiha", "biznes_yuborildi"} <= set(c.ACTIVITY_TYPES))

print("\nHammasi o'tdi: 25/25")
