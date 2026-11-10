"""Brend kartalari (Bot API 10.4 vidjetlari): /start, /pro, /kunlik, /research.

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_brend_kartalar.py

Tarmoqqa ham, bazaga ham murojaat qilmaydi — Telegram so'rovi va
`database.*` o'rniga soxta funksiya (shakli haqiqiy SELECT'dan).
"""
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _manba import kod
from core.config import daily_limit, MESSAGE_COST_TEXT, MESSAGE_COST_PHOTO
from services import ai
from services import vidjet as v
from handlers import digest as dg
from handlers import messages as msg
from handlers import pro
from handlers import profile as pf

ILDIZ = Path(__file__).parent.parent
failures = []


def check(n, label, cond):
    if cond:
        print(f"[{n}] {label} OK")
    else:
        print(f"[{n}] {label} XATO")
        failures.append(label)


chaqiruvlar = []


def _api(natija, outcome_qiymati=None):
    async def f(method, payload, *, outcome=None, timeout=None):
        chaqiruvlar.append((method, payload))
        if natija is None and outcome is not None and outcome_qiymati:
            outcome.append(outcome_qiymati)
        return natija
    return f


class _Chat:
    def __init__(self, t="private"):
        self.type, self.id = t, 555


class _Msg:
    def __init__(self, t="private"):
        self.chat = _Chat(t)
        self.from_user = type("U", (), {"id": 777, "username": "u", "full_name": "U"})()
        self.message_thread_id, self.is_topic_message = None, False


# ─────────────────────────────────────────────────────────────
# 1-3. SHABLONLAR
# ─────────────────────────────────────────────────────────────
HTMLLAR = {"start": v.start_html(), "pro": v.pro_html(), "kunlik": v.kunlik_html(),
           "tadqiqot": v.tadqiqot_html(), "profil": v.karta_html()}
check(1, "5 karta ham 4 KB (siqilgan) ga sig'adi va hammasida Vexon logosi bor",
      all(v.sigadimi(h) and 'class="lg"' in h and "url(#la)" in h for h in HTMLLAR.values()))
# Vidjet `opacity` va `filter` ni "og'ir" element deb sanaydi (16 tadan oshsa
# to'xtatadi) — logo shaffoflikni faqat fill-/stop-opacity bilan beradi.
# `background-clip:text` — Telegram vidjeti qo'llamaydi: jonli (2026-11-10)
# «VEXON AI» o'rnida gradient to'rtburchak chiqdi, matn ko'rinmadi.
# Brend sarlavhasi yo'q kartalar — pastida kichik logo va «VEXON AI» imzosi.
IMZOLI = {"obhavo": v.obhavo_html(), "valyuta": v.valyuta_html(), "namoz": v.namoz_html(),
          "eslatma": v.eslatma_html(), "test": v.test_html([["s", ["a", "b"], 0, ""]]),
          "kartochka": v.kartochka_html([["a", "b"]])}
og_ir = [n for n, h in {**HTMLLAR, **IMZOLI}.items()
         if re.search(r"(?<![-\w])opacity\s*[:=]|filter\s*:|background-clip", h)]
check(2, "kartalarda `opacity`/`filter`/`background-clip` yo'q (vidjet qo'llamaydi yoki og'ir)",
      not og_ir)
# CSS ichidagi `url(#gradient)` iPhone Telegram'ida ishlamaydi (jonli
# 2026-11-10: /start ikonkalari bo'sh doira) — gradient faqat SVG ATRIBUTIDA.
# Kompyuterdagi Chrome ham, WebKit ham buni ko'rsatmadi — shuning uchun qo'riqchi.
from services import vidjet as _v  # noqa: E402
css_url = [n for n, h in {**HTMLLAR, "obhavo": _v.obhavo_html(), "valyuta": _v.valyuta_html(),
                          "namoz": _v.namoz_html(), "eslatma": _v.eslatma_html()}.items()
           if re.search(r"url\(#", " ".join(re.findall(r"<style>(.*?)</style>", h, re.S)))]
check(21, "hech bir kartaning CSS'ida `url(#…)` yo'q (iPhone'da ishlamaydi)", not css_url)
check(22, "/start ikonkalari gradientni o'z atributida, zaxira rang bilan oladi; logoda animatsiya yo'q",
      "stroke=\"url(#g'+i+') #" in v.start_html() and ".lc .lg{width:108px;height:108px}" in v.start_html())
check(23, "ob-havo, valyuta, namoz, eslatma, test, kartochka: 4 KB ichida, pastida logo + «VEXON AI»",
      all(h and v.sigadimi(h) and "VEXON AI</div>" in h and "url(#va) #" in h and 'class="lg"' not in h
          for h in IMZOLI.values()))
check(24, "brend sarlavhasida nomi boshqa kartada (kunlik, tadqiqot) «VEXON AI» satri; profil ham",
      all('class="vk">VEXON' in HTMLLAR[n] for n in ("kunlik", "tadqiqot", "profil"))
      and 'class="vk"' not in v.pro_html())
check(3, "/start slaydlari bepul foydalanuvchiga yo'q narsani va'da qilmaydi (rasm chizish)",
      "chiz" not in json.dumps(v.START_SLAYDLAR, ensure_ascii=False).lower()
      and len(v.START_SLAYDLAR) >= 5)

# ─────────────────────────────────────────────────────────────
# 4-9. /pro
# ─────────────────────────────────────────────────────────────
q = {r[1]: r for r in pro.pro_qatorlari()}
check(4, "taqqoslash raqamlari PLAN_LIMITS dan (ball, savol = ball // narx, fayl, tadqiqot)",
      q["Ball / kun"][3] == f"{daily_limit('pro', 'points'):,}".replace(",", " ")
      and q["Matnli savol"][2] == str(daily_limit('free', 'points') // MESSAGE_COST_TEXT)
      and q["Rasm tahlili"][3] == str(daily_limit('pro', 'points') // MESSAGE_COST_PHOTO)
      and q["Fayl yaratish"][3] == str(daily_limit('pro', 'files'))
      and q["Tadqiqot (PDF)"][2] == ("—" if not daily_limit('free', 'research') else "")
      and q["Business"][2:] == ["—", "✓"])

_hozir = datetime.now(timezone.utc)
PROFIL = {}
OBUNA = {}


async def _profil(uid):
    return dict(PROFIL)


async def _obuna(uid):
    return OBUNA.get("v")

asl = (pro.database.get_full_user_profile, pro._obuna, pro._karta, pro.database.karta_faol_sorov)
pro.database.get_full_user_profile, pro._obuna = _profil, _obuna


async def _karta_yoq():
    return None


async def _sorov_yoq(*a):
    return None

pro._karta, pro.database.karta_faol_sorov = _karta_yoq, _sorov_yoq

PROFIL.update(plan_type="free", premium_until=None)
f = asyncio.run(pro.pro_kartasi(777))
PROFIL.update(plan_type="pro", premium_until=_hozir - timedelta(days=1))
otgan = asyncio.run(pro.pro_kartasi(777))
PROFIL.update(plan_type="pro", premium_until=None)
m = asyncio.run(pro.pro_kartasi(777))
PROFIL.update(plan_type="pro", premium_until=_hozir + timedelta(days=12, hours=3))
p = asyncio.run(pro.pro_kartasi(777))
OBUNA["v"] = {"holat": "faol", "keyingi": datetime(2026, 12, 3, 20, 0, tzinfo=timezone.utc),
              "narx": 250, "charge_id": "x", "oxirgi_charge": None}
po = asyncio.run(pro.pro_kartasi(777))
OBUNA.clear()
check(5, "karta holati: bepul, muddati o'tgan → bepul, muddatsiz, Pro (kun, tugash), obuna (keyingi to'lov)",
      f["h"] == "f" and otgan["h"] == "f" and m["h"] == "m"
      and p["h"] == "p" and p["k"] == 12 and "o" not in p
      and po["o"] == 1 and po["n"] == "04.12.2026"     # 20:00 UTC = 01:00 Toshkent
      and len(v.pro_holati(po).encode()) < 1024)

PROFIL.update(plan_type="free", premium_until=None)
chaqiruvlar.clear()
msg._telegram_api_request = _api({"message_id": 1})
mm = _Msg()
ok = asyncio.run(pro._pro_vidjeti(mm, 777))
mt, pl = chaqiruvlar[-1]
_, oddiy_kb = asyncio.run(pro._render_pro_screen(777))
check(6, "shaxsiy chat: sendWidget, izoh ixcham (jadval kartada), tugmalar ODDIY ekrandagining o'zi",
      ok and mt == "sendWidget" and "blockquote expandable" in pl["caption"]
      and "Kunlik hisobda" not in pl["caption"]
      and pl["reply_markup"] == oddiy_kb.model_dump(exclude_none=True)
      and json.loads(pl["chat_data"])["h"] == "f")

izohlar = []
for plan, muddat in (("free", None), ("pro", _hozir + timedelta(days=5)), ("pro", None)):
    PROFIL.update(plan_type=plan, premium_until=muddat)
    for obuna in (None, {"holat": "faol", "keyingi": _hozir, "narx": 250}):
        OBUNA["v"] = obuna
        izohlar.append(pro._korinadigan(asyncio.run(pro._render_pro_screen(777, ixcham=True))[0]))
OBUNA.clear()
check(7, f"har holatda izoh 1024 belgidan qisqa (eng uzuni {max(izohlar)})",
      max(izohlar) <= v.CAPTION_MAX)

yuborildi = []


async def _rich(target, text, kb=None, effect=None, **extra):
    yuborildi.append(text)

asl_rich = pro.send_rich
pro.send_rich = _rich
PROFIL.update(plan_type="free", premium_until=None)
msg._telegram_api_request = _api(None, msg.OUTCOME_REJECTED)
asyncio.run(pro.pro_ekranini_yubor(_Msg(), 777))
rad = list(yuborildi)
yuborildi.clear()
chaqiruvlar.clear()
asyncio.run(pro.pro_ekranini_yubor(_Msg("supergroup"), 777))
check(8, "karta rad etilsa — TO'LIQ matnli ekran; guruhda karta urinilmaydi",
      len(rad) == 1 and "Kunlik hisobda" in rad[0] and not chaqiruvlar and len(yuborildi) == 1)
pro.send_rich = asl_rich

prk = kod(ILDIZ / "handlers" / "pro.py")
msk = kod(ILDIZ / "handlers" / "messages.py")
check(9, "/pro, «Pro'ga o'tish» tugmasi, /start pro — hammasi bitta `pro_ekranini_yubor` dan",
      "await pro_ekranini_yubor(message, message.from_user.id)" in prk
      and "await pro_ekranini_yubor(query.message, user_id)" in prk
      and "await pro_module.pro_ekranini_yubor(message, user_id)" in msk)

# ─────────────────────────────────────────────────────────────
# 10-11. /start
# ─────────────────────────────────────────────────────────────
from aiogram.types import InlineKeyboardMarkup  # noqa: E402
from handlers.capabilities import menu_button  # noqa: E402
kb = InlineKeyboardMarkup(inline_keyboard=[[menu_button()]])
chaqiruvlar.clear()
msg._telegram_api_request = _api({"message_id": 1})
s_ok = asyncio.run(msg._start_vidjeti(_Msg(), kb))
s_pl = chaqiruvlar[-1][1]
msg._telegram_api_request = _api(None, msg.OUTCOME_REJECTED)
s_rad = asyncio.run(msg._start_vidjeti(_Msg(), kb))


async def _portlaydi(*a, **k):
    raise RuntimeError("tarmoq")

msg._telegram_api_request = _portlaydi
s_xato = asyncio.run(msg._start_vidjeti(_Msg(), kb))
check(10, "/start: karta + salomlashuv izohda + tugma; rad/xatoda False (oddiy salomlashuvga)",
      s_ok and s_pl["caption"] == msg._greeting_text(premium=True)
      and s_pl["reply_markup"] == kb.model_dump(exclude_none=True)
      and s_rad is False and s_xato is False)
i_k = msk.find('if message.chat.type == "private" and await _start_vidjeti(message, kb):')
check(11, "/start kartasi faqat shaxsiy chatda, ban/admin/start=pro dan KEYIN, oddiy salomlashuvdan OLDIN",
      0 < msk.find('if start_payload == "pro" and message.chat.type == "private":') < i_k
      < msk.find("await message.answer(_greeting_text(premium=True), reply_markup=kb)"))

# ─────────────────────────────────────────────────────────────
# 12-15. /kunlik
# ─────────────────────────────────────────────────────────────
# get_full_user_profile shakli: plan_type, premium_until, digest_hours,
# digest_hour, digest_topics.
pro_prof = {"plan_type": "pro", "premium_until": _hozir + timedelta(days=9),
            "digest_hours": [20, 8], "digest_hour": None, "digest_topics": "Я" * 400}
bep_prof = {"plan_type": "free", "premium_until": None, "digest_hours": [8],
            "digest_hour": None, "digest_topics": "IT"}
kp, kb_ = dg.kunlik_holati(pro_prof), dg.kunlik_holati(bep_prof)
check(12, "holat: Pro — soatlar va mavzu (300 belgi, 1 KB ichida); bepul — qulf, soatsiz",
      kp["l"] == 0 and kp["h"] == [8, 20] and len(kp["m"]) == 300
      and len(v.kunlik_holati(kp).encode()) < 1024 and kb_ == {"l": 1, "h": [], "m": "", "t": kb_["t"]})

chaqiruvlar.clear()
dg._telegram_api_request = _api({"message_id": 1})
k_ok = asyncio.run(dg._kunlik_vidjeti(_Msg(), pro_prof))
k_pl = chaqiruvlar[-1][1]
check(13, "kunlik karta: so'rov yoqilgan, izoh QAT'IY (holat kartada), tugmalar — soat panjarasi",
      k_ok and k_pl["allow_queries"] is True and "Faol:" not in k_pl["caption"]
      and k_pl["reply_markup"] == dg._hours_keyboard([8, 20]).model_dump(exclude_none=True))
chaqiruvlar.clear()
k_guruh = asyncio.run(dg._kunlik_vidjeti(_Msg("group"), pro_prof))
guruhda_chaqiruv = len(chaqiruvlar)
dg._telegram_api_request = _api(None, msg.OUTCOME_REJECTED)
k_rad = asyncio.run(dg._kunlik_vidjeti(_Msg(), bep_prof))
check(14, "guruhda karta urinilmaydi; rad etilsa False (oddiy ekran)",
      k_guruh is False and guruhda_chaqiruv == 0 and k_rad is False
      and chaqiruvlar[-1][1]["caption"] == dg._PRO_ONLY)

asl_prof = pf.get_full_user_profile


async def _pf_profil(uid):
    return pro_prof if uid == 777 else None

pf.get_full_user_profile = _pf_profil
chaqiruvlar.clear()
msg._telegram_api_request = _api(True)
asyncio.run(pf.vidjet_sorovi({"id": "k1", "from": {"id": 777}, "data": "k"}))
asyncio.run(pf.vidjet_sorovi({"id": "k2", "from": {"id": 5}, "data": "k"}))
jk = {pl["widget_query_id"]: pl for _, pl in chaqiruvlar}
pf.get_full_user_profile = asl_prof
check(15, "\"k\" so'roviga SO'RAGAN odamning soatlari; profili yo'q — ma'lumotsiz (javob baribir)",
      json.loads(jk["k1"]["data"])["h"] == [8, 20] and "data" not in jk["k2"] and len(jk) == 2)

# ─────────────────────────────────────────────────────────────
# 16-20. /research
# ─────────────────────────────────────────────────────────────
ai._tadqiqot_qayd("internet_search", {"primary_query": "x"}, "https://a.uz/1")  # ContextVar yo'q
j = {"id": "j1", "b": "q", "q": [], "s": 0}
belgi = ai.TADQIQOT.set(j)
ai._tadqiqot_qayd("internet_search", {"primary_query": "elektromobil narxi"},
                  "Manba: https://a.uz/1 va https://b.uz/2).")
ai._tadqiqot_qayd("internet_search", {"url": "https://c.uz"}, "https://a.uz/1 https://c.uz/3")
ai._tadqiqot_qayd("internet_search", ["buzuq"], "https://d.uz/4")
q16 = list(j["q"]), j["s"]
ai._tadqiqot_qayd("run_python_sandbox", {}, "ok")
ai.TADQIQOT.reset(belgi)
check(16, "jarayon: qidiruv so'rovlari, NOYOB havolalar soni, PDF'dan keyin «xulosa»; buzuq args — e'tiborsiz",
      q16 == (["elektromobil narxi", "https://c.uz"], 3) and j["b"] == "x")

aik = kod(ILDIZ / "services" / "ai.py")
check(17, "jarayon yozuvi har asbob natijasidan keyin, PDF bosqichi sandbox'dan oldin",
      "_tadqiqot_qayd(call_item.name, args, tool_output)\n            messages.append({" in aik
      and aik.index('j["b"] = "p"') < aik.index("tool_output = await _run_file_task("))

chaqiruvlar.clear()
msg._telegram_api_request = _api({"message_id": 1})
msg._TADQIQOTLAR.clear()
jr = asyncio.run(msg._tadqiqot_ochiq(_Msg(), "<b>EV</b> bozori"))
t_pl = chaqiruvlar[-1][1]
jg = asyncio.run(msg._tadqiqot_ochiq(_Msg("group"), "x"))
check(18, "karta faqat shaxsiy chatda; izohda mavzu HTML-qochirilgan; holatda ichki `_u` yo'q",
      jr and jr["b"] == "q" and "&lt;b&gt;EV&lt;/b&gt;" in t_pl["caption"]
      and t_pl["allow_queries"] is True and jg is None and msg._TADQIQOTLAR[777] is jr)

jr["_u"] = {"https://a.uz"}
chaqiruvlar.clear()
msg._telegram_api_request = _api(True)
for uid, data in ((777, "r:" + jr["id"]), (5, "r:" + jr["id"]), (777, "r:boshqa")):
    asyncio.run(pf.vidjet_sorovi({"id": f"{uid}{data}", "from": {"id": uid}, "data": data}))
jt = {pl["widget_query_id"]: json.loads(pl["data"]) for _, pl in chaqiruvlar}
check(19, "\"r:<id>\": o'z jarayoni (ichki `_u`siz); begona odam yoki boshqa id — {x:1}",
      jt["777r:" + jr["id"]]["id"] == jr["id"] and "_u" not in jt["777r:" + jr["id"]]
      and jt["5r:" + jr["id"]] == {"x": 1} and jt["777r:boshqa"] == {"x": 1})

check(20, "handle_research: ContextVar finally'da tiklanadi, yakunda bosqich t/e va fayl soni",
      "TADQIQOT.reset(belgi)" in msk
      and 'jarayon.update(b="t" if tayyor else "e", d=int(time.time()), f=len(output_files))' in msk)

pro.database.get_full_user_profile, pro._obuna, pro._karta, pro.database.karta_faol_sorov = asl

# ─────────────────────────────────────────────────────────────
# 25-27. /profile — to'liq karta
# ─────────────────────────────────────────────────────────────
def _kabinet(plan="free", until=None, **kw):
    # get_full_user_profile() qaytaradigan kalitlar (db/database.py)
    p = {"user_id": 777, "username": "ali", "is_active": True, "is_banned": False,
         "plan_type": plan, "premium_until": until, "current_model": "GPT-5.6 Luna",
         "media_analysis_active": True, "daily_requests_used": 12, "daily_files_used": 1,
         "daily_images_used": 0, "daily_research_used": 0, "daily_biznes_used": 0,
         "digest_hour": None, "digest_hours": None, "digest_topics": None,
         "total_tokens_used": 0, "total_messages": 40,
         "created_at": datetime(2026, 3, 1, 20, 0, tzinfo=timezone.utc), "last_seen": None}
    p.update(kw)
    return p


f = pf.profil_holati(_kabinet(username="Mavjud emas"), "Ali")
kel = pf.profil_holati(_kabinet("pro", _hozir + timedelta(days=5, hours=1)))
m = pf.profil_holati(_kabinet("pro", None))
otgan = pf.profil_holati(_kabinet("pro", _hozir - timedelta(days=1)))
check(25, "holat: bepul / Pro (sana, kun) / muddatsiz / muddati o'tgan → bepul; a'zo sanasi Toshkentda",
      f["p"] == "f" and f["u"] == "" and f["n"] == "Ali" and f["i"] == 777 and f["m"] == 40
      and f["o"] == "02.03.2026" and f["x"][0] == MESSAGE_COST_TEXT and f["b"][0] == 12
      and kel["p"] == "p" and kel["k"] == 5 and kel["u"] == "ali" and "n" not in kel
      and m["p"] == "m" and otgan["p"] == "f" and {"r", "t"} <= set(kel)
      and len(v.karta_holati({**f, "n": "Я" * 64}).encode()) < 1024)

PROFILLAR = {777: _kabinet("pro", _hozir + timedelta(days=5))}


async def _gfp(uid):
    return PROFILLAR.get(uid)

asl_gfp = pf.get_full_user_profile
pf.get_full_user_profile = _gfp
chaqiruvlar.clear()
msg._telegram_api_request = _api({"message_id": 9})
mm = _Msg()
mm.from_user.first_name = "Ali"
asyncio.run(pf.handle_profile(mm, user_id=777))
m_, p_ = chaqiruvlar[-1]
hl = json.loads(p_["chat_data"])
check(26, "shaxsiy chat: to'liq holat kartada (ism ham), izoh ixcham — tarif va ball",
      m_ == "sendWidget" and p_["allow_queries"] is True and hl["n"] == "Ali" and hl["p"] == "p"
      and "SHAXSIY KABINET" in p_["caption"] and "Tarif:" in p_["caption"]
      and "Tanlangan Model" not in p_["caption"] and "Barcha xabarlar" not in p_["caption"])
chaqiruvlar.clear()
asyncio.run(pf.vidjet_sorovi({"id": "q7", "from": {"id": 777}, "data": "y"}))
m_, p_ = chaqiruvlar[-1]
check(27, "\"y\" javobi — o'sha to'liq holat (ismsiz: karta eski ismni saqlaydi)",
      m_ == "answerWidgetQuery" and json.loads(p_["data"])["p"] == "p" and "n" not in json.loads(p_["data"])
      and "if(D&&D.n&&!x.n)x.n=D.n" in v.karta_html())
pf.get_full_user_profile = asl_gfp

# ─────────────────────────────────────────────────────────────
print("─" * 55)
if failures:
    print(f"❌ {len(failures)} ta tekshiruv yiqildi:")
    for f in failures:
        print(f"   • {f}")
    sys.exit(1)
print("✅ Brend kartalari tekshiruvlari — hammasi o'tdi")
