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
qolgan, testlar = v.bloklar_ajrat(BLOK)
check(1, "blok ajratiladi, matnning qolgani joyida",
      len(testlar) == 1 and testlar[0][0] == "test" and "[test]" not in qolgan
      and "Mana test" in qolgan and "Omad" in qolgan)
s = testlar[0][1]
check(2, "buzuq savollar (2 ta '+', 1 variant) tashlanadi, to'g'rilari qoladi",
      [x[0] for x in s] == ["2+2 nechchi?", "O'zbekiston poytaxti?"])
check(3, "aralashtirilgandan keyin ham to'g'ri javob indeksi to'g'ri",
      all(x[1][x[2]] in ("4", "Toshkent") for x in s) and s[0][3] == "Oddiy qo'shish")
check(4, "savollar 10 tadan oshmaydi",
      len(v.test_oqi("\n".join(f"? s{i}\n+ a\n- b" for i in range(15)))) == v.TEST_SAVOL_MAX)
check(5, "bitta ham to'g'ri savoli yo'q blok AJRATILMAYDI",
      v.bloklar_ajrat("[test]\n? s\n+ a\n+ b\n[/test]")[1] == [])
check(6, "yopilmagan blok ham test (model yopishni unutsa)",
      len(v.bloklar_ajrat("[test]\n? s\n+ a\n- b")[1]) == 1)

# ─────────────────────────────────────────────────────────────
# 7-11. VIDJET CHIZILMAYDIGAN JOYLAR
# ─────────────────────────────────────────────────────────────
md = build_rich_markdown(BLOK)
check(7, "rich (guruh/guest): xom belgi yo'q, javoblar yig'iladigan bo'limda",
      "[test]" not in md and "<details" in md and "Javoblar" in md)
oddiy = strip_rich_tokens(BLOK)
check(8, "oddiy zaxira: xom belgi va `[batafsil` qolmaydi",
      "[test]" not in oddiy and "[batafsil" not in oddiy and "A)" in oddiy)
qora = v.bloklar_matnga(BLOK, qoralama=True)
check(9, "draft: javob (`+ 4`) oqim paytida ko'rinmaydi",
      "+ 4" not in qora and "4" not in qora.split("tayyorlanmoqda")[1] and "Mana test" in qora)
check(10, "draft: hali yopilmagan blok ham yashirinadi",
      "Toshkent" not in v.bloklar_matnga("Mana:\n[test]\n? Poytaxt?\n+ Toshkent", qoralama=True))
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
          for x in __import__("re").findall(r"innerHTML\s*=\s*[^;]*", v._TEST_SHABLON + v._KARTOCHKA_SHABLON))
      # profil kartasi: halqa SVG'si (raqamlar) — ism/username/model hech qachon innerHTML'da emas
      and all(x.replace(" ", "") == 'innerHTML=""' or (x.startswith("innerHTML='<svg")
              and not __import__("re").search(r"x\.[nugo]\b", x))
              for x in __import__("re").findall(r"innerHTML\s*=\s*[^;]*", v._KARTA_SHABLON)))
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
asyncio.run(msg._blokni_yubor(_Msg(), "test", s, 42))
m, p = chaqiruvlar[-1]
check(16, "sendWidget: html, izoh va mavzu bor",
      m == "sendWidget" and "var Q=" in p["html"] and p["caption"] == "📝 Test · 2 ta savol"
      and p["message_thread_id"] == 42 and not rich)

msg._telegram_api_request = _api_soxta(None, msg.OUTCOME_REJECTED)
asyncio.run(msg._blokni_yubor(_Msg(), "test", s, None))
check(17, "rad etilsa — test MATN bilan ketadi (savollar yo'qolmaydi)",
      rich and "2+2 nechchi?" in rich[-1]["markdown"])

rich.clear()
msg._telegram_api_request = _api_soxta(None, msg.OUTCOME_UNKNOWN)
asyncio.run(msg._blokni_yubor(_Msg(), "test", s, None))
check(18, "timeout — takror yo'q (vidjet yetib borgan bo'lishi mumkin)", not rich)

pds = kod(ILDIZ / "handlers" / "messages.py")
check(19, "ajratish FAQAT shaxsiy chatda (production'da vidjet faqat u yerda)",
      'message.chat.type == "private":\n        clean_text, bloklar = vidjet.bloklar_ajrat(clean_text)' in pds)

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
asyncio.run(msg._vidjet_yubor(_Msg(), {"tur": "obhavo", "d": d}, None))
m, p = chaqiruvlar[-1]
check(40, "karta: sendWidget, so'rovlar yoqilgan, holatda koordinata",
      m == "sendWidget" and p["allow_queries"] is True
      and json.loads(p["chat_data"])["c"] == [41.26, 69.22] and "16°" in p["caption"])

msg._telegram_api_request = _api_soxta(None, msg.OUTCOME_REJECTED)
mm = _Msg()
asyncio.run(msg._vidjet_yubor(mm, {"tur": "obhavo", "d": d}, None))
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
# 43-44. LaTeX/markdown vidjetga XOM tushmaydi
# ⛔️ JONLI (2026-11-10): vidjetda «$7 \times 8$ nechaga teng?» chiqdi —
# matn faqat textContent, formulani chizadigan hech narsa yo'q.
# ─────────────────────────────────────────────────────────────
_HOLATLAR = [
    (r"$7 \times 8$ nechaga teng?", "7 × 8 nechaga teng?"),
    (r"$\frac{1}{2} + \frac{1}{3}$", "1/2 + 1/3"),
    (r"$\frac{a+b}{2}$", "(a+b)/2"),             # qavs — ma'no o'zgarmasin
    (r"$\frac{x^2}{4}$", "x²/4"),
    (r"$x^2 + y^{10}$", "x² + y¹⁰"),
    (r"$x^{n+1}$", "xⁿ⁺¹"),
    (r"$a^{2b}$", "a^(2b)"),
    (r"$\sqrt{x+1}$", "√(x+1)"),
    (r"$\sqrt[3]{27}$", "³√27"),
    (r"$H_2O$", "H₂O"),
    (r"$\sin 30^{\circ} = \frac{1}{2}$", "sin 30° = 1/2"),
    (r"$90^\circ$", "90°"),
    (r"$x \leq 5$", "x ≤ 5"),
    (r"$$2 \cdot 3 = 6$$", "2 · 3 = 6"),
    (r"\(a \neq b\)", "a ≠ b"),
    (r"7 \times 8 = ?", "7 × 8 = ?"),            # delimitersiz
    (r"$\text{tezlik} = \frac{s}{t}$", "tezlik = s/t"),
    (r"$12\%$ dan", "12% dan"),
    (r"$5 va $10 narx", "$5 va $10 narx"),        # dollar — formula EMAS
    (r"Javob: $56$", "Javob: 56"),                # operatorsiz formula
    (r"$x$ ni toping", "x ni toping"),
    (r"Narxi $20, chegirma bilan $15", "Narxi $20, chegirma bilan $15"),
    ("**Qalin** ==muhim== `kod` *kursiv*", "Qalin muhim kod kursiv"),
    ("2*3*4 = ?", "2*3*4 = ?"),                   # ko'paytma — kursiv EMAS
    ("<b>Qalin</b> &amp; a &lt; b", "Qalin & a < b"),
]
yomonlar = [(k, v.oddiy_matn(k), x) for k, x in _HOLATLAR if v.oddiy_matn(k) != x]
check(43, f"LaTeX/markdown → o'qiladigan matn ({len(_HOLATLAR)} holat)", not yomonlar)
for k, r, x in yomonlar:
    print(f"     {k!r} -> {r!r}, kutilgan {x!r}")

s43 = v.test_oqi("? $7 \\times 8$ nechaga teng?\n+ $56$\n- **54**\n- $\\frac{112}{2}$\n"
                 "! $7 \\times 8 = 56$")[0]
check(44, "test blokida savol, variant va izohda xom belgi qolmaydi",
      s43[0] == "7 × 8 nechaga teng?" and sorted(s43[1]) == ["112/2", "54", "56"]
      and s43[3] == "7 × 8 = 56" and "\\" not in v.test_html([s43]))

# ─────────────────────────────────────────────────────────────
# 45-54. VALYUTA (Markaziy bank)
# ─────────────────────────────────────────────────────────────
from services import valyuta as va

# Haqiqiy cbu.uz javobining shakli (2026-11-10) — VND Nominal=10.
_CBU = {"USD": {"kod": "USD", "nom": "AQSH dollari", "kurs": 11994.10, "nominal": 1, "farq": 6.94, "sana": "10.11.2026"},
        "EUR": {"kod": "EUR", "nom": "EVRO", "kurs": 13420.20, "nominal": 1, "farq": 26.95, "sana": "10.11.2026"},
        "VND": {"kod": "VND", "nom": "Vetnam dongi", "kurs": 4.70, "nominal": 10, "farq": 0.01, "sana": "10.11.2026"},
        "IRR": {"kod": "IRR", "nom": "Eron riali", "kurs": 0.06, "nominal": 10, "farq": 0.0, "sana": "10.11.2026"}}


async def _yukla_soxta():
    return _CBU

va._yukla = _yukla_soxta
va._kesh.update(t=0.0, kurslar=None)
check(45, "konvertatsiya: 100 USD = 1 199 410 so'm; Nominal hisobga olinadi (VND /10)",
      va.son(va.hisobla(_CBU, 100, "USD", "UZS")) == "1 199 410"
      and va.son(va.hisobla(_CBU, 1000, "VND", "UZS")) == "470"
      and va.son(va.hisobla(_CBU, 100, "EUR", "USD")) == "111,89"
      and va.hisobla(_CBU, 1, "XYZ", "UZS") is None)
check(46, "son yozuvi: minglik bo'sh joy, vergul, 1 dan kichigi 4 xona, ortiqcha nolsiz",
      [va.son(x) for x in (1199410.0, 11994.1, 0.47, 0.006, 12.0, 83.3724)]
      == ["1 199 410", "11 994,1", "0,47", "0,006", "12", "83,37"])
mt = va.matn(_CBU, ["EUR", "IRR"])
check(47, "matn: BOSH harfli nom tuzatiladi, nol farq «=» (▲ 0 emas)",
      "(Evro)" in mt and "(=)" in mt and "▲ 0)" not in mt)
check(48, "model yozgan kodlar: 3 harfli, takrorsiz, so'm tashlanadi, ko'pi bilan 6",
      va.toza_kodlar(["usd", "Eur", "UZS", "dollar", "EUR", "so'm"]) == ["USD", "EUR"]
      and len(va.toza_kodlar([f"A{c}C" for c in "ABCDEFGH"])) == va.KOD_MAX)

out = []
vm = asyncio.run(ai._run_valyuta_task({"kodlar": ["USD"], "summa": 100, "dan": "USD", "ga": "UZS"}, out))
check(49, "asbob: konvertatsiyani KOD hisoblaydi, rasmiy kurs ekani aytiladi, karta navbatda",
      "100 USD = 1 199 410 so'm" in vm and "RASMIY" in vm and "1-2 gap" in vm
      and out and out[0]["tur"] == "valyuta" and out[0]["d"]["r"][0][0] == "USD")
gv = asyncio.run(ai._run_valyuta_task({"kodlar": ["XYZ"]}, None))


async def _yukla_ishlamaydi():
    raise va.XizmatYoq("timeout")

va._yukla = _yukla_ishlamaydi
va._kesh.update(t=0.0, kurslar=None)
iv = asyncio.run(ai._run_valyuta_task({"kodlar": ["USD"]}, []))
va._yukla = _yukla_soxta
check(50, "noma'lum kod va xizmat ishlamasa — ikki xil javob, kurs o'ylab topilmaydi",
      "topilmadi" in gv and "texnik" in iv and "O'YLAB TOPMANG" in iv)
check(51, "valyuta dispatch'i bare `else` dan OLDIN",
      0 < aik.index('elif call_item.name == "valyuta"')
      < aik.index("            else:\n                search_ran = True"))

vh = va.holat(_CBU, ["USD", "VND"])
check(52, "karta HTML 4 KB'ga sig'adi, holat 1024 baytdan kichik, izohda birinchi kurs",
      v.sigadimi(v.valyuta_html()) and len(v.valyuta_holati(vh).encode()) < 1024
      and "1 USD = 11 994,1 so'm" in v.valyuta_izohi(vh))

chaqiruvlar.clear()
msg._telegram_api_request = _api_soxta(None, msg.OUTCOME_REJECTED)
qaytdi = asyncio.run(msg.karta_yubor(555, {"tur": "valyuta", "d": vh}, None))
check(53, "valyuta kartasi rad etilsa — kurslar matn bilan qaytadi",
      chaqiruvlar[-1][0] == "sendWidget" and "1 VND (Vetnam dongi) = 0,47 so'm" in (qaytdi or ""))

msg._telegram_api_request = _api_soxta(True)
chaqiruvlar.clear()
for data in ("v:USD,EUR", "v:<script>", "v:"):
    asyncio.run(pf.vidjet_sorovi({"id": data, "from": {"id": 7}, "data": data}))
jv = {p["widget_query_id"]: p for _, p in chaqiruvlar}
check(54, "\"v:USD,EUR\" so'roviga yangi kurs; buzuq yoki bo'sh kodga ma'lumotsiz javob",
      [r[0] for r in json.loads(jv["v:USD,EUR"]["data"])["r"]] == ["USD", "EUR"]
      and "data" not in jv["v:<script>"] and "data" not in jv["v:"])

# ─────────────────────────────────────────────────────────────
# 55-59. LUG'AT KARTOCHKALARI
# ─────────────────────────────────────────────────────────────
k55 = v.kartochka_oqi("apple — olma\nbook – kitob\n1. car - mashina\n- **house** — uy\n"
                      "• water = suv\n2) sun: quyosh\nwell-known — mashhur\n10:30 vaqt\n"
                      "$x^2$ — x kvadrat\nseparatorsiz qator")
check(55, "kartochka: har xil ajratgich, ro'yxat belgisi, markdown/LaTeX tozalanadi",
      k55 == [["apple", "olma"], ["book", "kitob"], ["car", "mashina"], ["house", "uy"],
              ["water", "suv"], ["sun", "quyosh"], ["well-known", "mashhur"], ["x²", "x kvadrat"]])
q56, b56 = v.bloklar_ajrat("Mana:\n[kartochka]\napple — olma\n[/kartochka]\nOmad")
check(56, "kartochka bloki ajratiladi, draftda «tayyorlanmoqda», boshqa joyda matn",
      b56 == [("kartochka", [["apple", "olma"]])] and "[kartochka]" not in q56
      and "olma" not in v.bloklar_matnga("[kartochka]\napple — olma", qoralama=True)
      and "**apple** — olma" in v.bloklar_matnga("[kartochka]\napple — olma\n[/kartochka]"))
check(57, "kartochka HTML: </script> qochiriladi, 30 tadan oshmaydi",
      v.kartochka_html([["</script>", "x"]]).count("</script>") == 1
      and len(v.kartochka_oqi("\n".join(f"s{i} — t{i}" for i in range(50)))) == v.KARTOCHKA_MAX)
chaqiruvlar.clear()
msg._telegram_api_request = _api_soxta({"message_id": 8})
asyncio.run(msg._blokni_yubor(_Msg(), "kartochka", [["apple", "olma"]], None))
check(58, "kartochka vidjeti yuboriladi, izohida soni",
      chaqiruvlar[-1][0] == "sendWidget" and chaqiruvlar[-1][1]["caption"] == "🗂 Kartochkalar · 1 ta")
check(59, "draftda kartochka va test bir xil yashiriladi (ikki tur, bitta mexanizm)",
      set(v.BLOK_TURLARI) == {"test", "kartochka"}
      and all(len(x) == 5 for x in v.BLOK_TURLARI.values()))

# ─────────────────────────────────────────────────────────────
# 60-62. RICH XABARDAN IQTIBOS (Bot API 10.4)
# ─────────────────────────────────────────────────────────────
from aiogram.types import Message as _AM
from handlers.helpers import iqtibos_matni


def _iq(quote):
    d = {"message_id": 1, "date": 0, "chat": {"id": 1, "type": "private"},
         "from": {"id": 1, "is_bot": False, "first_name": "a"}, "text": "shuni tushuntir"}
    if quote is not None:
        d["quote"] = quote
    return _AM.model_validate(d)

rich_q = _iq({"text": "", "position": 0, "rich_texts": [
    "Tezlik ", {"type": "bold", "text": "formulasi"}, ": ",
    {"type": "mathematical_expression", "expression": "v=s/t"},
    {"type": "custom_emoji", "custom_emoji_id": "1", "alternative_text": "🚀"}]})
check(60, "rich iqtibos: text BO'SH, matn rich_texts'dan (qalin, formula, emoji)",
      iqtibos_matni(rich_q) == "Tezlik formulasi: $v=s/t$🚀")
check(61, "oddiy iqtibos o'zgarmaydi, iqtibossiz — bo'sh",
      iqtibos_matni(_iq({"text": "oddiy parcha", "position": 0})) == "oddiy parcha"
      and iqtibos_matni(_iq(None)) == "")
check(62, "DM: parcha so'rovga qo'shiladi, iqtibossiz so'rov O'ZGARMAYDI (0 token)",
      msg._iqtibosli(rich_q, "shuni tushuntir").startswith("[Foydalanuvchi shu parchani")
      and msg._iqtibosli(_iq(None), "salom") == "salom")

# ─────────────────────────────────────────────────────────────
# 63-64. /kunlik — daydjestdan keyin karta
# ─────────────────────────────────────────────────────────────
from handlers import digest as dg

dm_ketdi, kartalar = [], []


async def _karta_soxta(uid, vv, thread_id=None):
    kartalar.append((uid, vv["tur"], thread_id))
    return None if vv["tur"] == "obhavo" else "ZAXIRA MATN"


async def _dm_soxta(uid, text, kb=None, thread_id=0):
    dm_ketdi.append((uid, text, thread_id))

dg.karta_yubor, dg._dm_or_deactivate = _karta_soxta, _dm_soxta
asyncio.run(dg._kartalar(9, [{"tur": "obhavo", "d": d}, {"tur": "valyuta", "d": vh}], 0))
check(63, "daydjest: karta yetsa matn yo'q; rad etilsa raqamlar MATN bilan",
      [x[1] for x in kartalar] == ["obhavo", "valyuta"] and dm_ketdi == [(9, "ZAXIRA MATN", 0)])
dgk = kod(ILDIZ / "handlers" / "digest.py")
check(64, "daydjest asbobga vidjet ro'yxatini beradi va kartalarni yuboradi",
      "vidjet_out=vidjet_out" in dgk and "await _kartalar(uid, vidjetlar, thread)" in dgk)

# ─────────────────────────────────────────────────────────────
# 65-70. ESLATMA SANOQ KARTASI
# ─────────────────────────────────────────────────────────────
# Shakl — db/database.py::list_scheduled_tasks SELECT'i: id, text, run_at,
# repeat, vazifa, biznes_kimga (run_at — asyncpg'dagidek UTC'da).
_UTC = timezone.utc
_QATORLAR = [
    {"id": 4, "text": "Eski", "run_at": datetime(2026, 11, 11, 13, 0, tzinfo=_UTC),
     "repeat": "once", "vazifa": False, "biznes_kimga": 0},
    {"id": 9, "text": "Onamga qo'ng'iroq", "run_at": datetime(2026, 11, 11, 13, 0, tzinfo=_UTC),
     "repeat": "daily", "vazifa": False, "biznes_kimga": 0},
    {"id": 7, "text": "Boshqa", "run_at": datetime(2026, 11, 12, 4, 0, tzinfo=_UTC),
     "repeat": "once", "vazifa": False, "biznes_kimga": 0},
]


async def _royxat(uid, biznes=False):
    return [dict(r) for r in _QATORLAR] if uid == 777 else []


async def _yarat(uid, text, when, repeat="once", vazifa=False, thread_id=0):
    return f"qo'yildi: {when}"

asl_royxat, asl_yarat = ai.list_scheduled_tasks, ai.create_scheduled_task
ai.list_scheduled_tasks, ai.create_scheduled_task = _royxat, _yarat
k65 = asyncio.run(ai._eslatma_kartasi(777, datetime(2026, 11, 11, 18, 0)))
check(65, "karta holati: shu vaqtdagi ENG YANGI eslatma (Toshkent vaqti), takror bilan",
      k65 == {"tur": "eslatma", "d": {"m": "Onamga qo'ng'iroq", "r": "daily", "id": 9,
                                      "at": int(_QATORLAR[1]["run_at"].timestamp())}}
      and asyncio.run(ai._eslatma_kartasi(777, datetime(2026, 11, 11, 19, 0))) is None)


async def _royxat_yiqiladi(uid, biznes=False):
    raise ConnectionError("baza")

ai.list_scheduled_tasks = _royxat_yiqiladi
check(66, "ro'yxat o'qilmasa karta yo'q, xato chiqmaydi (bezak eslatmani yiqitmaydi)",
      asyncio.run(ai._eslatma_kartasi(777, datetime(2026, 11, 11, 18, 0))) is None)
ai.list_scheduled_tasks = _royxat

o67 = []
dm67 = asyncio.run(ai._run_reminder_task(
    777, {"action": "create", "text": "x", "when": "2026-11-11 18:00"}, vidjet_out=o67))
gr67 = asyncio.run(ai._run_reminder_task(
    777, {"action": "create", "text": "x", "when": "2026-11-11 18:00"}))
check(67, "shaxsiy chat: eslatma qo'yilgach karta navbatda, javob qisqa; guruhda karta yo'q",
      len(o67) == 1 and o67[0]["d"]["id"] == 9 and "qisqa gap" in dm67
      and "11.11.2026 18:00" in dm67 and "kartasi" not in gr67)
ai.list_scheduled_tasks, ai.create_scheduled_task = asl_royxat, asl_yarat

asl_pf_royxat = pf.list_scheduled_tasks
pf.list_scheduled_tasks = _royxat
chaqiruvlar.clear()
msg._telegram_api_request = _api_soxta(True)
for data in ("e:9", "e:123", "e:abc"):
    asyncio.run(pf.vidjet_sorovi({"id": data, "from": {"id": 777}, "data": data}))
asyncio.run(pf.vidjet_sorovi({"id": "begona", "from": {"id": 5}, "data": "e:9"}))
pf.list_scheduled_tasks = asl_pf_royxat
je = {p["widget_query_id"]: p for _, p in chaqiruvlar}
check(68, "\"e:<id>\": faol — keyingi vaqt; yo'q yoki BOSHQA odamniki — {x:1}; buzuq — ma'lumotsiz",
      json.loads(je["e:9"]["data"]) == {"at": int(_QATORLAR[1]["run_at"].timestamp())}
      and json.loads(je["e:123"]["data"]) == {"x": 1} and "data" not in je["e:abc"]
      and json.loads(je["begona"]["data"]) == {"x": 1} and len(je) == 4)

chaqiruvlar.clear()
msg._telegram_api_request = _api_soxta(None, msg.OUTCOME_REJECTED)
mm69 = _Msg()
asyncio.run(msg._vidjet_yubor(mm69, k65, None))
check(69, "eslatma kartasi rad etilsa — qo'shimcha matn YO'Q (vaqt javobda aytilgan)",
      chaqiruvlar[-1][0] == "sendWidget" and chaqiruvlar[-1][1]["allow_queries"] is True
      and mm69.javoblar == [] and "Onamga" in chaqiruvlar[-1][1]["caption"])
check(70, "eslatma kartasi HTML 4 KB'ga sig'adi; matn faqat textContent orqali",
      v.sigadimi(v.eslatma_html()) and "D.m)" in v.eslatma_html()
      and "innerHTML=\"\"" in v.eslatma_html() and v.eslatma_html().count("innerHTML") == 1)

# ─────────────────────────────────────────────────────────────
print("─" * 55)
if failures:
    print(f"❌ {len(failures)} ta tekshiruv yiqildi:")
    for f in failures:
        print(f"   • {f}")
    sys.exit(1)
print("✅ Vidjet tekshiruvlari — hammasi o'tdi")
