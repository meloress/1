"""Bot API 10.4 vidjetlari: interaktiv test va /profile jonli kartasi.

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_vidjet.py

Tarmoqqa ham, bazaga ham murojaat qilmaydi — Telegram so'rovi va
`get_full_user_profile` o'rniga soxta funksiya qo'yiladi.
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _manba import kod
from services import vidjet as v
from services.ai import build_rich_markdown, clean_text_for_speech, strip_rich_tokens
from handlers import messages as msg
from handlers import profile as pf

ILDIZ = Path(__file__).parent.parent
failures = []


def check(n, label, cond):
    if cond:
        print(f"[{n}] {label} OK")
    else:
        print(f"[{n}] {label} XATO")
        failures.append(label)


BLOK = """Mana test:

[test]
? 2+2 nechchi?
- 5
+ 4
- 3
! Oddiy qo'shish
? Ikkita to'g'ri javob — buzuq
+ a
+ b
? Bitta variant — buzuq
+ a
? O'zbekiston poytaxti?
+ Toshkent
- Samarqand
[/test]

Omad!"""

# ─────────────────────────────────────────────────────────────
# 1-6. BELGINI O'QISH
# ─────────────────────────────────────────────────────────────
qolgan, testlar = v.test_ajrat(BLOK)
check(1, "blok ajratiladi, matnning qolgani joyida",
      len(testlar) == 1 and "[test]" not in qolgan and "Mana test" in qolgan and "Omad" in qolgan)
s = testlar[0]
check(2, "buzuq savollar (2 ta '+', 1 variant) tashlanadi, to'g'rilari qoladi",
      [x[0] for x in s] == ["2+2 nechchi?", "O'zbekiston poytaxti?"])
check(3, "aralashtirilgandan keyin ham to'g'ri javob indeksi to'g'ri",
      all(x[1][x[2]] in ("4", "Toshkent") for x in s) and s[0][3] == "Oddiy qo'shish")
check(4, "savollar 10 tadan oshmaydi",
      len(v.test_oqi("\n".join(f"? s{i}\n+ a\n- b" for i in range(15)))) == v.TEST_SAVOL_MAX)
check(5, "bitta ham to'g'ri savoli yo'q blok AJRATILMAYDI",
      v.test_ajrat("[test]\n? s\n+ a\n+ b\n[/test]")[1] == [])
check(6, "yopilmagan blok ham test (model yopishni unutsa)",
      len(v.test_ajrat("[test]\n? s\n+ a\n- b")[1]) == 1)

# ─────────────────────────────────────────────────────────────
# 7-11. VIDJET CHIZILMAYDIGAN JOYLAR
# ─────────────────────────────────────────────────────────────
md = build_rich_markdown(BLOK)
check(7, "rich (guruh/guest): xom belgi yo'q, javoblar yig'iladigan bo'limda",
      "[test]" not in md and "<details" in md and "Javoblar" in md)
oddiy = strip_rich_tokens(BLOK)
check(8, "oddiy zaxira: xom belgi va `[batafsil` qolmaydi",
      "[test]" not in oddiy and "[batafsil" not in oddiy and "A)" in oddiy)
qora = v.test_matnga(BLOK, qoralama=True)
check(9, "draft: javob (`+ 4`) oqim paytida ko'rinmaydi",
      "+ 4" not in qora and "4" not in qora.split("tayyorlanmoqda")[1] and "Mana test" in qora)
check(10, "draft: hali yopilmagan blok ham yashirinadi",
      "Toshkent" not in v.test_matnga("Mana:\n[test]\n? Poytaxt?\n+ Toshkent", qoralama=True))
nutq = clean_text_for_speech(BLOK)
check(11, "ovoz: belgilar o'qilmaydi", "[test]" not in nutq and "batafsil" not in nutq)

# ─────────────────────────────────────────────────────────────
# 12-15. HTML — xavfsizlik va hajm
# ─────────────────────────────────────────────────────────────
yomon = [["</script><script>alert(1)</script>", ["<b>x</b>", "y"], 0, "<img>"]]
h = v.test_html(yomon)
check(12, "model matnidagi </script> skriptni yopmaydi",
      h is not None and h.count("</script>") == 1 and "<b>x" not in h)
check(13, "model matni faqat textContent orqali (innerHTML faqat tozalash)",
      all(x.replace(" ", "") in ('innerHTML=""',)
          for x in __import__("re").findall(r"innerHTML\s*=\s*[^;]*", v._TEST_SHABLON + v._KARTA_SHABLON)))
katta = [[f"Juda uzun savol {i} " + "x" * 290, [f"variant {j} {i} " + "y" * 140 for j in range(6)], 0,
          "z" * 300] for i in range(10)]
import random as _r
_r.seed(1)
katta = [[q[0] + "".join(_r.choice("abcdefghijklmnop") for _ in range(250)),
          [x + "".join(_r.choice("qrstuvwxyz") for _ in range(120)) for x in q[1]], 0, q[3]] for q in katta]
check(14, "4 KB'ga sig'magan test — None (matn bilan ketadi, kesilmaydi)", v.test_html(katta) is None)
check(15, "oddiy 10 savollik test sig'adi",
      v.test_html(v.test_oqi("\n".join(f"? Savol {i}: poytaxt qaysi?\n+ Toshkent\n- Samarqand\n- Buxoro\n! Izoh {i}"
                                       for i in range(10)))) is not None)

# ─────────────────────────────────────────────────────────────
# 16-19. TESTNI YUBORISH (shaxsiy chat)
# ─────────────────────────────────────────────────────────────
class _Chat:
    def __init__(self, t="private"):
        self.id, self.type = 555, t


class _Msg:
    def __init__(self, t="private"):
        self.chat = _Chat(t)
        self.from_user = type("U", (), {"id": 777})()
        self.message_thread_id, self.is_topic_message = None, False
        self.javoblar = []

    async def answer(self, text, **kw):
        self.javoblar.append((text, kw))


chaqiruvlar, rich = [], []


def _api_soxta(natija, outcome_qiymati=None):
    async def f(method, payload, *, outcome=None, timeout=None):
        chaqiruvlar.append((method, payload))
        if natija is None and outcome is not None and outcome_qiymati:
            outcome.append(outcome_qiymati)
        return natija
    return f


async def _rich_soxta(chat_id, **kw):
    rich.append(kw)
    return {"message_id": 1}


msg._send_rich_message = _rich_soxta
msg._telegram_api_request = _api_soxta({"message_id": 9})
asyncio.run(msg._testni_yubor(_Msg(), s, 42))
m, p = chaqiruvlar[-1]
check(16, "sendWidget: html, izoh va mavzu bor",
      m == "sendWidget" and "var Q=" in p["html"] and p["caption"] == "📝 Test · 2 ta savol"
      and p["message_thread_id"] == 42 and not rich)

msg._telegram_api_request = _api_soxta(None, msg.OUTCOME_REJECTED)
asyncio.run(msg._testni_yubor(_Msg(), s, None))
check(17, "rad etilsa — test MATN bilan ketadi (savollar yo'qolmaydi)",
      rich and "2+2 nechchi?" in rich[-1]["markdown"])

rich.clear()
msg._telegram_api_request = _api_soxta(None, msg.OUTCOME_UNKNOWN)
asyncio.run(msg._testni_yubor(_Msg(), s, None))
check(18, "timeout — takror yo'q (vidjet yetib borgan bo'lishi mumkin)", not rich)

pds = kod(ILDIZ / "handlers" / "messages.py")
check(19, "ajratish FAQAT shaxsiy chatda (production'da vidjet faqat u yerda)",
      'message.chat.type == "private":\n        clean_text, testlar = vidjet.test_ajrat(clean_text)' in pds)

# ─────────────────────────────────────────────────────────────
# 20-24. /profile KARTASI
# ─────────────────────────────────────────────────────────────
def _profil(plan="free", until=None, **kw):
    # get_full_user_profile() qaytaradigan kalitlar (db/database.py)
    p = {"user_id": 777, "username": "ali", "is_active": True, "is_banned": False,
         "plan_type": plan, "premium_until": until, "current_model": "GPT",
         "media_analysis_active": True, "daily_requests_used": 12, "daily_files_used": 1,
         "daily_images_used": 0, "daily_research_used": 0, "daily_biznes_used": 0,
         "digest_hour": None, "digest_hours": None, "digest_topics": None,
         "total_tokens_used": 0, "total_messages": 40, "created_at": None, "last_seen": None}
    p.update(kw)
    return p


free = pf.karta_raqamlari(_profil())
check(20, "bepul: ball va fayl bor, rasm/tadqiqot yo'q (chegara 0)",
      set(free) == {"b", "f"} and free["b"][0] == 12)
kel = datetime.now(timezone.utc) + timedelta(days=5)
pro = pf.karta_raqamlari(_profil("pro", kel))
otgan = pf.karta_raqamlari(_profil("pro", datetime.now(timezone.utc) - timedelta(days=1)))
check(21, "Pro'da rasm va tadqiqot; muddati o'tgan Pro — bepul bo'lib ko'rinadi",
      {"r", "t"} <= set(pro) and set(otgan) == {"b", "f"})
check(22, "holat 1024 baytdan kichik va JSON",
      len(v.karta_holati(pro).encode()) < 1024 and json.loads(v.karta_holati(pro))["b"][1] > 0)

chaqiruvlar.clear()
msg._telegram_api_request = _api_soxta(True)


async def _prof_soxta(uid):
    return _profil(user_id=uid)

pf.get_full_user_profile = _prof_soxta
asyncio.run(pf.vidjet_sorovi({"id": "q1", "from": {"id": 777}, "data": "y"}))
m, p = chaqiruvlar[-1]
check(23, "\"y\" so'roviga — so'ragan odamning yangi raqamlari",
      m == "answerWidgetQuery" and p["widget_query_id"] == "q1" and json.loads(p["data"])["b"][0] == 12)


async def _prof_xato(uid):
    raise RuntimeError("baza")

pf.get_full_user_profile = _prof_xato
asyncio.run(pf.vidjet_sorovi({"id": "q2", "from": {"id": 777}, "data": "y"}))
check(24, "baza xatosida ham javob beriladi (aks holda vidjetda TIMEOUT)",
      chaqiruvlar[-1] == ("answerWidgetQuery", {"widget_query_id": "q2"}))

# ─────────────────────────────────────────────────────────────
# 25-28. handle_profile: karta va zaxira
# ─────────────────────────────────────────────────────────────
pf.get_full_user_profile = _prof_soxta
chaqiruvlar.clear()
msg._telegram_api_request = _api_soxta({"message_id": 3})
mm = _Msg()
asyncio.run(pf.handle_profile(mm, user_id=777))
m, p = chaqiruvlar[-1]
check(25, "shaxsiy chatda — karta vidjeti, so'rovlar yoqilgan, matnli profil YO'Q",
      m == "sendWidget" and p["allow_queries"] is True and not mm.javoblar
      and json.loads(p["chat_data"])["b"][0] == 12 and "SHAXSIY KABINET" in p["caption"]
      and "12 / " in p["caption"] and len(p["caption"]) <= v.CAPTION_MAX)

msg._telegram_api_request = _api_soxta(None, msg.OUTCOME_REJECTED)
mm = _Msg()
asyncio.run(pf.handle_profile(mm, user_id=777))
check(26, "vidjet rad etilsa — oldingi matnli profil",
      len(mm.javoblar) == 1 and "Bugungi AI Creditlar" in mm.javoblar[0][0])

chaqiruvlar.clear()
mm = _Msg("supergroup")
asyncio.run(pf.handle_profile(mm, user_id=777))
check(27, "guruhda vidjet urinilmaydi", not chaqiruvlar and len(mm.javoblar) == 1)

mn = kod(ILDIZ / "main.py")
check(28, "main: widget_query allowed_updates'da va middleware ulangan",
      '"widget_query"' in mn and "dp.update.outer_middleware(vidjet_mw)" in mn)

# ─────────────────────────────────────────────────────────────
# 29-30. HAQIQIY aiogram Dispatcher orqali
# ─────────────────────────────────────────────────────────────
from aiogram import Bot, Dispatcher
from aiogram.types import Update

olingan, otdi = [], []


async def _sorov_soxta(sorov):
    olingan.append(sorov)

_asl_sorov = pf.vidjet_sorovi
pf.vidjet_sorovi = _sorov_soxta
dp = Dispatcher()
dp.update.outer_middleware(pf.vidjet_mw)


@dp.message()
async def _h(message):
    otdi.append(message.text)

bot = Bot("123:abc")
asyncio.run(dp.feed_update(bot, Update.model_validate({
    "update_id": 1, "widget_query": {"id": "q9", "from": {"id": 7, "is_bot": False, "first_name": "a"},
                                     "chat": {"id": 7, "type": "private"}, "message_id": 5, "data": "y"}})))
check(29, "widget_query aiogram'da yiqilmaydi va bizga yetadi",
      olingan and olingan[0]["id"] == "q9" and olingan[0]["from"]["id"] == 7)
asyncio.run(dp.feed_update(bot, Update.model_validate({
    "update_id": 2, "message": {"message_id": 1, "date": 0, "chat": {"id": 7, "type": "private"},
                                "from": {"id": 7, "is_bot": False, "first_name": "a"}, "text": "salom"}})))
check(30, "oddiy xabar middleware'dan o'tib handlerga yetadi", otdi == ["salom"])

# ─────────────────────────────────────────────────────────────
# 31-42. OB-HAVO (asbob + karta)
# ─────────────────────────────────────────────────────────────
from services import obhavo
import services.ai as ai

# Haqiqiy Open-Meteo javobining shakli (2026-11-10, Toshkent) — qisqartirilgan.
_OM = {"current": {"time": "2026-11-10T11:00", "temperature_2m": 16.5, "apparent_temperature": 15.4,
                   "relative_humidity_2m": 75, "wind_speed_10m": 11.2, "weather_code": 51, "is_day": 1},
       "hourly": {"time": [f"2026-11-10T{h:02d}:00" for h in range(11, 24)],
                  "temperature_2m": [16.5, 16.5, 15.3, 15.5, 15.2, 14.0, 12.6, 12.2, 11.5, 10.8, 10.2, 10.2, 9.7],
                  "weather_code": [51, 55, 80, 2, 3, 3, 53, 80, 81, 80, 61, 61, 53],
                  "is_day": [1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0]},
       "daily": {"time": ["2026-11-10", "2026-11-11", "2026-11-12"], "weather_code": [81, 53, 3],
                 "temperature_2m_max": [17.1, 9.2, 10.6], "temperature_2m_min": [9.2, 2.3, 0.3]}}


async def _get_soxta(url, params):
    if "geocoding" in url:
        return {"results": [{"name": "Toshkent", "country": "O‘zbekiston",
                             "latitude": 41.26, "longitude": 69.22}]} if params["name"] == "Toshkent" else {}
    return _OM


obhavo._get = _get_soxta
d = asyncio.run(obhavo.ob_havo("Toshkent"))
check(31, "Open-Meteo javobi o'qiladi: 6 soat, 3 kun, holat o'zbekcha",
      d["h"] == 16 and d["s"] == "Mayda yomg'ir" and len(d["s2"]) == 6 and d["s2"][0][0] == "13:00"
      and [k[0] for k in d["k3"]][:2] == ["Bugun", "Ertaga"] and d["c"] == [41.26, 69.22]
      and d["s2"][3][3] == 1)        # 19:00 — tun belgisi
check(32, "holat 1024 baytdan kichik, HTML 4 KB'ga sig'adi",
      len(v.obhavo_holati(d).encode()) < 1024 and v.sigadimi(v.obhavo_html()))
check(33, "model yozgan joy nomi bir qatorli va qisqa",
      obhavo.toza_joy("Tosh\nkent  " + "x" * 200) == ("Tosh kent " + "x" * 200)[:obhavo.JOY_UZUN])


async def _get_buzuq(url, params):
    return {"current": {}}

obhavo._get = _get_buzuq
try:
    asyncio.run(obhavo.prognoz(41, 69))
    buzuq = False
except obhavo.XizmatYoq:
    buzuq = True
check(34, "kutilmagan javob shakli — XizmatYoq (KeyError emas)", buzuq)
obhavo._get = _get_soxta

out = []
dm = asyncio.run(ai._run_obhavo_task({"joy": "Toshkent"}, out))
guruh = asyncio.run(ai._run_obhavo_task({"joy": "Toshkent"}, None))
check(35, "shaxsiy chat: karta navbatga, model javobni QISQA yozadi",
      out and out[0]["tur"] == "obhavo" and "1-2 gap" in dm and "16°" in dm)
check(36, "guruh/guest: karta yo'q, raqamlar modelga to'liq",
      "16°" in guruh and "kartada" not in guruh)
yoq = asyncio.run(ai._run_obhavo_task({"joy": "Qwerty"}, None))


async def _get_ishlamaydi(url, params):
    raise obhavo.XizmatYoq("timeout")

obhavo._get = _get_ishlamaydi
ishlamadi = asyncio.run(ai._run_obhavo_task({"joy": "Toshkent"}, []))
obhavo._get = _get_soxta
check(37, "\"joy topilmadi\" va \"xizmat javob bermadi\" — ikki xil javob, raqam o'ylab topilmaydi",
      "topilmadi" in yoq and "texnik" in ishlamadi and "O'YLAB TOPMANG" in ishlamadi)

aik = kod(ILDIZ / "services" / "ai.py")
check(38, "ob_havo dispatch'i bare `else` (veb-qidiruv) dan OLDIN",
      0 < aik.index('elif call_item.name == "ob_havo"')
      < aik.index("            else:\n                search_ran = True"))

check(39, "guruhda vidjet ro'yxati None (asbob raqamni matnga yozadi)",
      msg._vidjet_royxati(_Msg()) == [] and msg._vidjet_royxati(_Msg("supergroup")) is None)

chaqiruvlar.clear()
msg._telegram_api_request = _api_soxta({"message_id": 5})
asyncio.run(msg._obhavo_yubor(_Msg(), d, None))
m, p = chaqiruvlar[-1]
check(40, "karta: sendWidget, so'rovlar yoqilgan, holatda koordinata",
      m == "sendWidget" and p["allow_queries"] is True
      and json.loads(p["chat_data"])["c"] == [41.26, 69.22] and "16°" in p["caption"])

msg._telegram_api_request = _api_soxta(None, msg.OUTCOME_REJECTED)
mm = _Msg()
asyncio.run(msg._obhavo_yubor(mm, d, None))
check(41, "karta rad etilsa — raqamlar matn bilan (model javobi qisqa edi)",
      len(mm.javoblar) == 1 and "16°" in mm.javoblar[0][0])

pf.vidjet_sorovi = _asl_sorov
chaqiruvlar.clear()
msg._telegram_api_request = _api_soxta(True)
for data in ("w:41.26,69.22", "w:999,1", "w:abc"):
    asyncio.run(pf.vidjet_sorovi({"id": data, "from": {"id": 7}, "data": data}))
javoblar = {p["widget_query_id"]: p for _, p in chaqiruvlar}
check(42, "\"w:lat,lon\" so'roviga yangi prognoz; buzuq koordinataga ma'lumotsiz javob",
      json.loads(javoblar["w:41.26,69.22"]["data"])["h"] == 16
      and "data" not in javoblar["w:999,1"] and "data" not in javoblar["w:abc"])

# ─────────────────────────────────────────────────────────────
print("─" * 55)
if failures:
    print(f"❌ {len(failures)} ta tekshiruv yiqildi:")
    for f in failures:
        print(f"   • {f}")
    sys.exit(1)
print("✅ Vidjet tekshiruvlari — hammasi o'tdi")
