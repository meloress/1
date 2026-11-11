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
           "tadqiqot": v.tadqiqot_html(), "profil": v.karta_html(), "tolov": v.tolov_html(),
           "tabrik": v.tabrik_html()}
check(1, "brend kartalarining hammasi 4 KB (siqilgan) ga sig'adi va hammasida Vexon logosi bor",
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
      all('class="vk">VEXON' in HTMLLAR[n] for n in ("kunlik", "tadqiqot", "profil", "tolov"))
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
        iz = asyncio.run(pro._render_pro_screen(777, ixcham=True))[0]
        izohlar.append(pro._korinadigan(iz))
        # Jonli (iPhone, 2026-11-11): izoh karta ekrani almashganda ham qoladi —
        # «👇 … tanlang» eskirib qolardi, chiziq esa uzun to'siq bo'lib turardi.
        if "━" in iz or "👇" in iz:
            izohlar.append(10 ** 6)
OBUNA.clear()
check(7, f"har holatda izoh 1024 belgidan qisqa (eng uzuni {max(izohlar)}), chiziqsiz va «👇»siz",
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
# 28-40. Tugmalar ortidagi ekranlar — kartalar
# ─────────────────────────────────────────────────────────────
from core.config import PRO_PLANS, KARTA_NARX, OBUNA_NARX, MESSAGE_EFFECTS  # noqa: E402
from db import database  # noqa: E402

asl2 = {k: getattr(database, k, None) for k in (
    "get_full_user_profile", "karta_sorov_yarat", "is_banned", "karta_sorov_ol", "karta_bekor",
    "get_user_by_identifier", "set_digest")}
asl_pro = (pro._obuna, pro._karta, pro.send_rich, pro.bot)
# ⚠️ `pro._karta` ham soxta: aks holda `database.karta_ol()` lokal .env dagi
# PRODUCTION bazasiga boradi (2026-11-11 shu bo'limda shunday bo'lgan edi).
database.get_full_user_profile, pro._obuna, pro._karta = _profil, _obuna, _karta_yoq


class _VMsg(_Msg):
    """Karta xabari: aiogram 3.31 `widget` ni `model_extra` ga qo'yadi."""
    def __init__(self, holat=None, t="private", karta=True):
        super().__init__(t)
        self.message_id = 9
        self.model_extra = ({"widget": {"html": "<b>", "chat_data": json.dumps(holat or {})}}
                            if karta else {})
        self.tugmalar, self.javoblar = [], []

    async def edit_reply_markup(self, reply_markup=None):
        self.tugmalar.append(reply_markup)

    async def edit_text(self, *a, **k):
        self.javoblar.append(("edit_text", a))

    async def answer(self, text, **k):
        self.javoblar.append((text, k.get("reply_markup")))


class _Bos:
    def __init__(self, data, message, uid=777):
        self.data, self.message = data, message
        self.from_user = type("U", (), {"id": uid, "username": "u"})()
        self.alert = []

    async def answer(self, *a, **k):
        self.alert.append(a)


class _Holat:
    def __init__(self):
        self.h, self.data = None, {}

    async def set_state(self, s):
        self.h = getattr(s, "state", s)

    async def update_data(self, **k):
        self.data.update(k)

    async def get_state(self):
        return self.h

    async def get_data(self):
        return self.data

    async def clear(self):
        self.h = None


def _yozuvlar():
    return [json.loads(pl["chat_data"]) for m, pl in chaqiruvlar if m == "editMessageWidgetData"]


def _yuborilgan():
    return [pl for m, pl in chaqiruvlar if m == "sendWidget"]


s_, k_ = pro.tarif_plitkalari("s"), pro.tarif_plitkalari("k")
eng = min(PRO_PLANS, key=lambda x: x[1] / x[0])[0]
check(41, "«Eng foydali» belgisi plitka ICHIDA (absolute bilan tepada — iPhone'da chiziq bo'lib chiqdi)",
      'n.appendChild(el("em",0,"Eng foydali"))' in v.pro_html() and "top:-9px" not in v.pro_html())
check(28, "tarif plitkalari: nom/narx/chegirma PRO_PLANS va KARTA_NARX dan, eng foydalisi bitta "
          "(kun boshiga eng arzon — tugmalardagi qoida), 1 oyda «oyiga» yo'q",
      [x[0] for x in s_] == [x[2] for x in PRO_PLANS] and [x[3] for x in s_] == [x[3] for x in PRO_PLANS]
      and [x[1] for x in s_] == [f"{pro.som(x[1])} ⭐" for x in PRO_PLANS]
      and [x[1] for x in k_] == [f"{pro.som(KARTA_NARX[x[0]])} so'm" for x in PRO_PLANS]
      and [x[4] for x in s_] == [1 if x[0] == eng else 0 for x in PRO_PLANS] == [x[4] for x in k_]
      and "oyiga" not in s_[0][2] and "oyiga" in s_[-1][2]
      and f"oyiga ≈ {pro.som(round(KARTA_NARX[365] * 30 / 365))} so'm" in k_[-1][2].replace(" ", " ")
      and " so'm" not in k_[-1][2].split("·")[1])     # raqam ichida uzilmaydi (bo'linmas bo'shliq)

PROFIL.update(plan_type="free", premium_until=None)
OBUNA.clear()
es = asyncio.run(pro.pro_kartasi(777, "s"))
OBUNA["v"] = {"holat": "faol", "keyingi": _hozir, "narx": OBUNA_NARX}
PROFIL.update(plan_type="pro", premium_until=datetime(2026, 12, 11, 20, 0, tzinfo=timezone.utc))
es_ob = asyncio.run(pro.pro_kartasi(777, "s"))
OBUNA.clear()
ek = asyncio.run(pro.pro_kartasi(777, "k"))
asos = asyncio.run(pro.pro_kartasi(777))
check(29, "ekran holati: Stars — obuna qatori faqat obuna yo'q bo'lsa (tugmalar sharti); karta; "
          "karta sozlanmagan — «kb» yo'q; hammasi 1 KB ichida, tariflarda jadval yo'q",
      es["e"] == "s" and es["h"] == "f" and es["ob"] == OBUNA_NARX and es["t"] == s_
      and "ob" not in es_ob and es_ob["h"] == "p" and ek["e"] == "k" and ek["t"] == k_
      and "r" not in es and "kb" not in es and "kb" not in asos and "r" in asos
      and all(len(v.pro_holati(x).encode()) < 1024 for x in (es, es_ob, ek, asos)))


async def _karta_bor():
    return ("8600123412341234", "ALI VALIYEV")

pro._karta = _karta_bor
msg._telegram_api_request = _api(True)
PROFIL.update(plan_type="free", premium_until=None)
ekranlar = []
for data in ("pro:stars", "pro:kartalar", "pro:usul"):
    chaqiruvlar.clear()
    vm = _VMsg()
    asyncio.run(pro.handle_pro_callback(_Bos(data, vm), _Holat()))
    ekranlar.append((_yozuvlar(), vm.tugmalar))
chaqiruvlar.clear()
vob = _VMsg()
asyncio.run(pro.handle_pro_callback(_Bos("pro:obuna_bekor", vob), _Holat()))
obuna_yozuv = _yozuvlar()
chaqiruvlar.clear()
oddiy = _VMsg(karta=False)
asyncio.run(pro.handle_pro_callback(_Bos("pro:stars", oddiy), _Holat()))
check(30, "Stars / Karta / Orqaga — tugmalar almashadi VA karta o'sha xabarda o'sha ekranga o'tadi "
          "(karta bor — «kb»); obunani o'chirish — faqat tugmalar (tasdiq), karta joyida; "
          "matnli (eski) xabarda karta yozuvi yo'q",
      [x[0][0].get("e", "") for x in ekranlar] == ["s", "k", ""]
      and all(len(x[0]) == 1 and len(x[1]) == 1 for x in ekranlar)
      and "r" in ekranlar[2][0][0] and ekranlar[1][0][0]["t"] == k_
      and all(x[0][0].get("kb") == 1 for x in ekranlar)
      and len(vob.tugmalar) == 1 and not obuna_yozuv
      and oddiy.tugmalar and not _yozuvlar())

KS = {}


async def _yarat(uid, kun, narx, karta, oluvchi=None):
    return {"id": 42, "summa": narx + 47}


async def _ban_yoq(uid):
    return False

database.karta_sorov_yarat, database.is_banned = _yarat, _ban_yoq
# «Bitta jonli ekran» (2026-11-11): o'chirish `msg.bot` orqali — soxta, tarmoqsiz.
OCHDI, XQ = [], []


class _OchirBot:
    def __init__(self, asl):
        self.asl = asl

    def __getattr__(self, nom):
        return getattr(self.asl, nom)

    async def delete_message(self, chat_id, message_id):
        OCHDI.append((chat_id, message_id))


async def _xq(lid, mid):
    XQ.append((lid, mid))

async def _faol_yoq(uid, oyna):
    return None

for k_nom in ("karta_xabar_qosh", "karta_faol_sorov"):
    asl2[k_nom] = getattr(database, k_nom, None)
# ⚠️ `karta_faol_sorov` — Pro ekranidagi «to'lovim qayerda?» bloki; soxtasiz
# lokal .env dagi PRODUCTION bazasiga borardi.
database.karta_xabar_qosh, database.karta_faol_sorov = _xq, _faol_yoq
asl_msg_bot = msg.bot
msg.bot = _OchirBot(asl_msg_bot)
msg._EKRAN.clear()
msg._EKRAN[555] = (8, "")          # chatdagi joriy ekran (masalan, eski Pro)
chaqiruvlar.clear()
msg._telegram_api_request = _api({"message_id": 10})
h1, vm = _Holat(), _VMsg()
asyncio.run(pro.handle_pro_callback(_Bos("pro:karta:30", vm), h1))
check(54, "to'lov kartasi chiqqach: muddatlar kartasi (bosilgani) va chatdagi ekran o'chadi; "
          "kartaning id'si to'lovga yoziladi (natijada o'chadi)",
      OCHDI == [(555, 9), (555, 8)] and XQ == [(42, 10)] and 555 not in msg._EKRAN)
yw = _yuborilgan()
kb_kutilgan = pro._karta_sorov_kb(42, 25_047, "8600123412341234").model_dump(exclude_none=True)
hk = json.loads(yw[0]["chat_data"]) if yw else {}
check(31, "karta to'lovi — shaxsiy chatda karta: raqam, summa, tanish so'mlar, 3 soatlik oyna, "
          "so'rovlar yoqilgan; izohda karta va summa; tugmalar O'SHA; chek kutish yoqilgan",
      len(yw) == 1 and yw[0]["html"] == v.tolov_html() and yw[0]["allow_queries"] is True
      and hk["n"] == "8600123412341234" and hk["nf"] == "8600 1234 1234 1234" and hk["s"] == 25_047
      and hk["sf"] == "25 047" and hk["w"] == 47 and hk["h"] == "k" and hk["id"] == 42
      and abs(hk["x"] - (datetime.now().timestamp() + pro.KARTA_CHEK_OYNA)) < 60
      and "8600 1234 1234 1234" in yw[0]["caption"] and "25 047" in yw[0]["caption"]
      and yw[0]["reply_markup"] == kb_kutilgan and not vm.javoblar
      and h1.h == "KartaStates:chek" and h1.data["karta_id"] == 42
      and len(v.tolov_holati(hk).encode()) < 1024)

msg._telegram_api_request = _api(None, msg.OUTCOME_REJECTED)
h2, vm2 = _Holat(), _VMsg()
asyncio.run(pro.handle_pro_callback(_Bos("pro:karta:30", vm2), h2))
check(32, "karta rad etilsa — oldingi matn (karta_sorov_matni), o'sha tugmalar, chek kutish baribir",
      len(vm2.javoblar) == 1 and vm2.javoblar[0][0] == pro.karta_sorov_matni(
          30, 25_047, "8600123412341234", "ALI VALIYEV", 42)
      and vm2.javoblar[0][1].model_dump(exclude_none=True) == kb_kutilgan and h2.h == "KartaStates:chek")

TOLOV = {}


async def _sorov_ol(lid, uid):
    return TOLOV.get((lid, uid))

database.karta_sorov_ol = _sorov_ol
PROFIL.update(plan_type="pro", premium_until=datetime(2026, 12, 11, 20, 0, tzinfo=timezone.utc))
javoblar = []
msg._telegram_api_request = _api(True)
for holati in ("kutmoqda", "tekshirilmoqda", "rad", "tasdiqlandi", "eskirdi"):
    TOLOV[(42, 777)] = {"holat": holati, "sabab": "summa mos emas"}
    chaqiruvlar.clear()
    asyncio.run(pf.vidjet_sorovi({"id": "q", "from": {"id": 777}, "data": "t:42"}))
    javoblar.append(json.loads(chaqiruvlar[-1][1]["data"]))
chaqiruvlar.clear()
asyncio.run(pf.vidjet_sorovi({"id": "q", "from": {"id": 5}, "data": "t:42"}))
begona = json.loads(chaqiruvlar[-1][1]["data"])
asyncio.run(pf.vidjet_sorovi({"id": "q2", "from": {"id": 777}, "data": "t:abc"}))
buzuq = chaqiruvlar[-1]
check(33, "\"t:<id>\": o'z to'lovi holati (rad — sabab, tasdiq — tugash sanasi); begona — x; "
          "buzuq id — baribir javob (TIMEOUT emas)",
      [x["h"] for x in javoblar] == ["k", "t", "r", "a", "e"] and javoblar[2]["z"] == "summa mos emas"
      and javoblar[3]["g"] == "12.12.2026" and begona == {"h": "x"}
      and buzuq == ("answerWidgetQuery", {"widget_query_id": "q2"}))


async def _bekor(lid, uid):
    return True

database.karta_bekor = _bekor
# Bazadagi qator (haqiqiy `SELECT *` kalitlari): holat undan qayta yig'iladi —
# karta ichidagi tugmadan kelganda xabarning chat_data si qo'lda bo'lmaydi.
yaratildi = datetime.now(timezone.utc) - timedelta(minutes=20)
TOLOV[(42, 777)] = {"id": 42, "user_id": 777, "days": 30, "summa": 25_047,
                    "karta": "8600123412341234", "holat": "bekor", "oluvchi": None,
                    "yaratilgan": yaratildi, "sabab": None, "xabarlar": [10, 11]}
chaqiruvlar.clear()
OCHDI.clear()
msg._EKRAN.clear()
msg._telegram_api_request = _api({"message_id": 12})
vm3 = _VMsg(holat={})
b3 = _Bos("pro:kb:42", vm3)
asyncio.run(pro.handle_pro_callback(b3, _Holat()))
yw = _yuborilgan()
check(34, "«✖️ Bekor qilish» — to'lov xabarlari (karta, chek, eslatma) va bosilgan xabar o'chadi; "
          "karta muddatlari YANGI ekran bo'lib (eski kartaga holat yozilmaydi)",
      OCHDI == [(777, 10), (777, 11), (555, 9)] and len(yw) == 1
      and yw[0]["html"] == v.pro_html() and json.loads(yw[0]["chat_data"])["e"] == "k"
      and yw[0]["reply_markup"] == pro._karta_tariflar_kb().model_dump(exclude_none=True)
      and not _yozuvlar() and msg._EKRAN.get(555) == (12, "") and "Bekor" in b3.alert[0][0])

TOLOV[(44, 777)] = {"id": 44, "user_id": 777, "days": 30, "summa": 25_047, "karta": "8600123412341234",
                    "holat": "eskirdi", "oluvchi": 888, "yaratilgan": yaratildi, "sabab": None,
                    "xabarlar": [20]}
chaqiruvlar.clear()
OCHDI.clear()
msg._telegram_api_request = _api({"message_id": 13})
asyncio.run(pro.handle_pro_callback(_Bos("pro:qayta:44", _VMsg(holat={})), _Holat()))
yw = _yuborilgan()
yoq = _Bos("pro:qayta:99", _VMsg(holat={}))
asyncio.run(pro.handle_pro_callback(yoq, _Holat()))
check(55, "vaqti tugagan sovg'a kartasidagi «Qaytadan» (pro:qayta) — eski xabarlar va bosilgan karta "
          "o'chadi, O'SHA oluvchiga karta muddatlari yangi ekranda (oldingi ekran ham o'chadi); "
          "to'lov topilmasa — hech narsa o'chmaydi",
      OCHDI == [(777, 20), (555, 9), (555, 12)] and len(yw) == 1 and yw[0]["html"] == v.sovga_html()
      and json.loads(yw[0]["chat_data"])["e"] == "k" and json.loads(yw[0]["chat_data"])["rid"] == 888
      and "pro:karta:30:888" in json.dumps(yw[0]["reply_markup"]) and msg._EKRAN.get(555) == (13, "")
      and yoq.message.javoblar and "topilmadi" in yoq.message.javoblar[0][0])

OCHDI.clear()
msg._EKRAN.clear()
asyncio.run(msg.ekran_almashtir(5, {"message_id": 100}))
asyncio.run(msg.ekran_almashtir(5, 101))
asyncio.run(msg.ekran_almashtir(-7, 300))
birinchi = (list(OCHDI), dict(msg._EKRAN))
asyncio.run(msg.ekran_almashtir(5, True))
asyncio.run(msg.ekran_almashtir(5, 102))
asyncio.run(msg.ekranni_ochir(5, 999))
asyncio.run(msg.ekranni_ochir(-7, 300))
ikkinchi = (list(OCHDI), dict(msg._EKRAN))
asyncio.run(msg.ekranni_ochir(5))
check(56, "bitta jonli ekran: yangisi chiqqach eskisi o'chadi; guruhda hech narsa; timeout (id yo'q) — "
          "eskisi o'chadi, yangisi eslanmaydi; boshqa xabarni o'chirish joriy ekranga tegmaydi",
      birinchi == ([(5, 100)], {5: (101, "")})
      and ikkinchi == ([(5, 100), (5, 101), (5, 999)], {5: (102, "")})
      and OCHDI[-1] == (5, 102) and msg._EKRAN == {} and msg.xabar_id(True) is None
      and msg.xabar_id(None) is None and msg.xabar_id(type("M", (), {"message_id": 7})()) == 7)

tp = pro.tabrik_kartasi("p", title="1 oy", days=30, gacha="12.12.2026")
tg = pro.tabrik_kartasi("g", title="3 oy", kim="@" + "a" * 60)
ty = pro.tabrik_kartasi("y", title="1 oy", days=30, kim="12345", eslatma="⚠️ yetmadi")
check(35, "bayram kartasi: matnlar turiga qarab, imkoniyatlar PLAN_LIMITS dan, 1 KB ichida",
      tp["a"] == "Pro faollashdi!" and tp["b"] == "1 oy (30 kun) · 12.12.2026 gacha"
      and tg["b"].startswith("@aaa") and "3 oy" in tg["b"] and ty["u"] == "⚠️ yetmadi"
      and pro._son(daily_limit('pro', 'points')) in tp["l"][0][1]
      and pro.tabrik_kartasi("k", gacha="")["b"] == "Pro faollashdi"
      and all(len(v.tabrik_holati(x).encode()) < 1024 for x in (tp, tg, ty)))

yuborildi.clear()
pro.send_rich = _rich
chaqiruvlar.clear()
msg._telegram_api_request = _api({"message_id": 11})
asyncio.run(pro._notify_purchase(_Msg(), 777, 777, 30, "CHEK-1"))
yw = _yuborilgan()
yaxshi = (len(yw) == 1 and yw[0]["html"] == v.tabrik_html() and "CHEK-1" in yw[0]["caption"]
          and yw[0]["message_effect_id"] == MESSAGE_EFFECTS["🎉"] and not yuborildi
          and "pro:profile" in json.dumps(yw[0]["reply_markup"])
          and json.loads(yw[0]["chat_data"])["b"] == "1 oy (30 kun) · 12.12.2026 gacha")
msg._telegram_api_request = _api(None, msg.OUTCOME_REJECTED)
asyncio.run(pro._notify_purchase(_Msg(), 777, 777, 30, "CHEK-1"))
check(36, "xarid: bayram kartasi (chek izohda, effekt, o'sha tugmalar); rad etilsa — oldingi matn",
      yaxshi and len(yuborildi) == 1 and "PRO TARIF FAOLLASHTIRILDI" in yuborildi[0])


class _Bot:
    def __init__(self):
        self.yuborildi = []

    async def send_message(self, uid, matn, **k):
        self.yuborildi.append(uid)
        raise RuntimeError("bloklagan")

pro.bot = _Bot()


def _rad_888(natija):
    async def f(method, payload, *, outcome=None, timeout=None):
        chaqiruvlar.append((method, payload))
        if payload.get("chat_id") == 888:
            outcome.append(msg.OUTCOME_REJECTED)
            return None
        return natija
    return f

yuborildi.clear()
chaqiruvlar.clear()
PROFIL.update(username="dost")
msg._telegram_api_request = _api({"message_id": 12})
asyncio.run(pro._notify_purchase(_Msg(), 777, 888, 90, "CHEK-2"))
ikki = [(x["chat_id"], json.loads(x["chat_data"])["a"]) for x in _yuborilgan()]
chaqiruvlar.clear()
msg._telegram_api_request = _rad_888({"message_id": 13})
asyncio.run(pro._notify_purchase(_Msg(), 777, 888, 90, "CHEK-2"))
yw = _yuborilgan()
check(37, "sovg'a: oluvchiga «Sizga sovg'a», beruvchiga «yuborildi» kartasi; oluvchiga yetmasa "
          "(karta ham, matn ham) — beruvchi kartasi va izohida ogohlantirish",
      ikki == [(888, "Sizga sovg'a! 🎁"), (555, "Sovg'a yuborildi! 🎁")]
      and set(pro.bot.yuborildi) == {888} and yw[-1]["chat_id"] == 555
      and "yetmadi" in json.loads(yw[-1]["chat_data"])["u"] and "yetkazib bo'lmadi" in yw[-1]["caption"]
      and "@dost" in json.loads(yw[-1]["chat_data"])["b"] and not yuborildi)
PROFIL.pop("username", None)

chaqiruvlar.clear()
msg._telegram_api_request = _api({"message_id": 14})
hg = _Holat()
asyncio.run(pro._start_gift(_Msg(), hg))
yw = _yuborilgan()
yuborildi.clear()
asyncio.run(pro._start_gift(_Msg("supergroup"), _Holat()))
check(38, "sovg'a so'rovi: shaxsiy chatda karta (qadamlar), javob maydoni (force_reply) o'sha; "
          "holat yoqilgan; guruhda — oldingi matn",
      len(yw) == 1 and json.loads(yw[0]["chat_data"]) == {"e": "g"}
      and yw[0]["reply_markup"].get("force_reply") is True and hg.h == "GiftStates:waiting_for_recipient"
      and len(yuborildi) == 1 and "SOVG'A QILISH" in yuborildi[0])


class _Yozdi(_VMsg):
    def __init__(self, matn):
        super().__init__(karta=False)
        self.text, self.forward_origin = matn, None
        self.ochdi = False

    async def delete(self):
        self.ochdi = True


async def _topdi(x):
    return 888

database.get_user_by_identifier = _topdi
PROFIL.update(plan_type="free", premium_until=None, username="dost")
chaqiruvlar.clear()
OCHDI.clear()
msg._EKRAN[555] = (14, "")          # 38 dagi «Kimga?» so'rovi
msg._telegram_api_request = _api({"message_id": 15})
yozdi = _Yozdi("@dost")
asyncio.run(pro.process_gift_recipient(yozdi, _Holat()))
yw = _yuborilgan()
hs = json.loads(yw[0]["chat_data"]) if yw else {}
check(57, "oluvchi yozildi — «Kimga?» so'rovi tariflar bilan almashadi, javob (@username) ham o'chadi",
      OCHDI == [(555, 14)] and msg._EKRAN.get(555) == (15, "") and yozdi.ochdi)
check(39, "sovg'a oluvchisi topildi — tariflar kartasi (oluvchi nomi, obunasiz), tugmalar sovg'a "
          "narxlari (pro:buy:<kun>:888)",
      len(yw) == 1 and hs == {"e": "s", "gf": "@dost", "t": s_, "rid": 888, "kb": 1}
      and "pro:kartalar:888" in json.dumps(yw[0]["reply_markup"])
      and all(f"pro:buy:{x[0]}:888" in json.dumps(yw[0]["reply_markup"]) for x in PRO_PLANS)
      and "pro:obuna" not in json.dumps(yw[0]["reply_markup"]))
PROFIL.pop("username", None)


async def _saqla(uid, hours, topics=None, thread_id=None):
    pass

database.set_digest = _saqla
PROFIL.update(plan_type="pro", premium_until=_hozir + timedelta(days=9),
              digest_hours=[20], digest_hour=None, digest_topics="sport")
chaqiruvlar.clear()
vk = _VMsg(holat={"h": [20]})
asyncio.run(dg.handle_digest_callback(_Bos("dg:h:8", vk), _Holat()))
yz = _yozuvlar()
chaqiruvlar.clear()
asyncio.run(dg.handle_digest_callback(_Bos("dg:h:9", _VMsg(karta=False)), _Holat()))
check(40, "/kunlik: soat bosilganda karta darhol yangi soatlar bilan; matnli xabarda — yozuv yo'q; "
          "shablonlar `chatDataChanged` ni tinglaydi",
      len(yz) == 1 and yz[0]["h"] == [8, 20] and yz[0]["m"] == "sport" and not _yozuvlar()
      and all('onEvent("chatDataChanged"' in h for h in (v.pro_html(), v.tolov_html(), v.kunlik_html())))
for k_nom in ("digest_hours", "digest_hour", "digest_topics"):
    PROFIL.pop(k_nom, None)

# ─────────────────────────────────────────────────────────────
# 42-53. Kartadagi tugmalar (`vidjet_amali`) va karta orqali sovg'a
# ─────────────────────────────────────────────────────────────
import core.loader as yuklovchi  # noqa: E402
from aiogram.fsm.context import FSMContext  # noqa: E402
from aiogram.fsm.storage.base import StorageKey  # noqa: E402


class _TgBot:
    """aiogram usullari (`message.edit_reply_markup` …) shu yerga keladi — tarmoqsiz."""
    id = 4242

    def __init__(self):
        self.usullar = []

    async def __call__(self, method, request_timeout=None):
        self.usullar.append((type(method).__name__, method))
        return True

    async def send_invoice(self, chat_id, **k):
        self.usullar.append(("send_invoice", (chat_id, k.get("payload"), k.get("reply_markup"))))
        return type("M", (), {"message_id": 77})()

    async def send_message(self, chat_id, matn, **k):
        self.usullar.append(("send_message", (chat_id, matn)))


tgbot = _TgBot()
asl_bot = yuklovchi.bot
yuklovchi.bot, pro.bot = tgbot, tgbot
pro._karta = _karta_bor
msg._telegram_api_request = _api(True)
PROFIL.update(plan_type="free", premium_until=None, username="dost")


def _sorov(data, chat_turi="private", chat_id=777, uid=777, mid=9):
    return {"id": "w1", "from": {"id": uid, "is_bot": False, "first_name": "Ali"},
            "chat": {"id": chat_id, "type": chat_turi}, "message_id": mid, "data": data}


rad_etildi = [asyncio.run(pf.vidjet_amali(_sorov("x"), cb)) for cb in ("bz:ok", "admin:x", "pro:" + "1" * 70)]
rad_etildi += [asyncio.run(pf.vidjet_amali(_sorov("x", chat_turi="supergroup", chat_id=-5), "pro:stars")),
               asyncio.run(pf.vidjet_amali(_sorov("x", chat_id=999), "pro:stars")),
               asyncio.run(pf.vidjet_amali({**_sorov("x"), "message_id": None}, "pro:stars"))]
check(42, "karta tugmasi: faqat pro:/dg: callback, faqat bot bilan shaxsiy chatdagi asl xabar — "
          "qolgani {x:1}, handler chaqirilmaydi",
      all(x == {"x": 1} for x in rad_etildi) and not tgbot.usullar)

chaqiruvlar.clear()
tgbot.usullar.clear()
asyncio.run(pf.vidjet_sorovi(_sorov("c:pro:stars")))
javob = [pl for m, pl in chaqiruvlar if m == "answerWidgetQuery"]
tug = [m for n, m in tgbot.usullar if n == "EditMessageReplyMarkup"]
check(43, "\"c:pro:stars\" — xabar ostidagi tugma bosilgandek: o'sha xabarning tugmalari almashadi, "
          "karta Stars ekraniga o'tadi, javob ok",
      javob and json.loads(javob[-1]["data"]) == {"ok": 1}
      and tug and tug[0].chat_id == 777 and tug[0].message_id == 9
      and any(f"pro:buy:{x[0]}" in json.dumps(tug[0].reply_markup.model_dump()) for x in PRO_PLANS)
      and _yozuvlar() and _yozuvlar()[-1]["e"] == "s")

chaqiruvlar.clear()
tgbot.usullar.clear()
natija = asyncio.run(pf.vidjet_amali(_sorov("x"), "pro:karta:30"))
holati = asyncio.run(FSMContext(storage=yuklovchi.dp.storage,
                                key=StorageKey(bot_id=tgbot.id, chat_id=777, user_id=777)).get_state())
check(44, "kartadan karta to'lovi: to'lov kartasi yuboriladi va chek kutish holati (FSM) O'SHA "
          "saqlagichda yoqiladi — keyingi rasm chek bo'lib tushadi",
      natija.get("ok") == 1 and holati == "KartaStates:chek"
      and any(pl["html"] == v.tolov_html() for pl in _yuborilgan()))

tgbot.usullar.clear()
OCHDI.clear()
msg._EKRAN.clear()
natija = asyncio.run(pf.vidjet_amali(_sorov("x"), "pro:buy:30"))
inv = [m for n, m in tgbot.usullar if n == "send_invoice"]
inv_kb = inv[0][2].inline_keyboard if inv else []
check(45, "kartadagi plitka — Stars to'lov oynasi (invoice) o'sha chatga, o'ziga; to'lov tugmasi "
          "BIRINCHI, keyin «⬅️ Orqaga»; muddatlar kartasi o'chadi, invoice — joriy ekran",
      natija.get("ok") == 1 and inv and inv[0][0] == 777 and ":30:777" in inv[0][1]
      and inv_kb[0][0].pay is True and inv_kb[1][0].callback_data == "pro:orqa"
      and OCHDI == [(777, 9)] and msg._EKRAN.get(777) == (77, "invoice"))

chaqiruvlar.clear()
OCHDI.clear()
msg._telegram_api_request = _api({"message_id": 78})
natija = asyncio.run(pf.vidjet_amali(_sorov("x", mid=77), "pro:orqa"))
yw = _yuborilgan()
msg._telegram_api_request = _api(True)
check(58, "invoice'dagi «⬅️ Orqaga» — invoice o'chadi, Stars muddatlari yangi Pro kartasida",
      natija.get("ok") == 1 and OCHDI == [(777, 77)] and len(yw) == 1
      and json.loads(yw[0]["chat_data"])["e"] == "s"
      and "pro:buy:30" in json.dumps(yw[0]["reply_markup"]) and msg._EKRAN.get(777) == (78, ""))

natija = asyncio.run(pf.vidjet_amali(_sorov("x"), "dg:h:8"))
check(46, "handler aytgan xabar (answer) kartaga qaytadi — bepulda soat: «Pro imkoniyati»",
      natija.get("ok") == 1 and "Pro" in natija.get("t", ""))

# ── Karta orqali sovg'a ───────────────────────────────────────
YARATILDI = []


async def _yarat_s(uid, kun, narx, karta, oluvchi=None):
    YARATILDI.append((uid, kun, narx, oluvchi))
    return {"id": 43, "summa": narx + 47}

database.karta_sorov_yarat = _yarat_s
chaqiruvlar.clear()
vk2 = _VMsg()
asyncio.run(pro.handle_pro_callback(_Bos("pro:kartalar:888", vk2), _Holat()))
kb_k = json.dumps(vk2.tugmalar[-1].model_dump()) if vk2.tugmalar else ""
yz = _yozuvlar()
check(47, "sovg'a — «💳 Karta orqali»: muddatlar oluvchi bilan (pro:karta:<kun>:888), «Orqaga» — "
          "sovg'aning Stars ekrani; karta: oluvchi nomi, rid",
      all(f"pro:karta:{x[0]}:888" in kb_k for x in PRO_PLANS) and "pro:stars:888" in kb_k
      and yz and yz[-1]["e"] == "k" and yz[-1]["gf"] == "@dost" and yz[-1]["rid"] == 888)

chaqiruvlar.clear()
hs2 = _Holat()
asyncio.run(pro.handle_pro_callback(_Bos("pro:karta:90:888", _VMsg()), hs2))
yw = [pl for pl in _yuborilgan() if pl["html"] == v.tolov_html()]
o_zi = _Bos("pro:karta:30:777", _VMsg())
asyncio.run(pro.handle_pro_callback(o_zi, _Holat()))
check(48, "sovg'a karta to'lovi: so'rov OLUVCHI bilan yoziladi, kartada va izohda kimga; chek kutish "
          "to'lovchida; o'ziga «sovg'a» — rad, so'rov ochilmaydi",
      YARATILDI == [(777, 90, KARTA_NARX[90], 888)] and yw
      and json.loads(yw[0]["chat_data"])["gf"] == "@dost" and "Sovg'a: @dost" in yw[0]["caption"]
      and hs2.h == "KartaStates:chek" and o_zi.alert and "O'zingizga" in o_zi.alert[0][0])

chaqiruvlar.clear()
vs2 = _VMsg()
asyncio.run(pro.handle_pro_callback(_Bos("pro:stars:888", vs2), _Holat()))
kb_s = json.dumps(vs2.tugmalar[-1].model_dump()) if vs2.tugmalar else ""
yz = _yozuvlar()
check(49, "sovg'aning Stars ekrani: narxlar oluvchi bilan, obunasiz, «💳 Karta orqali» (sovg'a), bekor",
      all(f"pro:buy:{x[0]}:888" in kb_s for x in PRO_PLANS) and "pro:kartalar:888" in kb_s
      and "pro:obuna" not in kb_s and "pro:close" in kb_s
      and yz and yz[-1] == {"e": "s", "gf": "@dost", "t": s_, "rid": 888, "kb": 1})


class _AdminXabar(_VMsg):
    html_text = "💳 <b>Karta to'lovi #43</b>"

    async def edit_caption(self, **k):
        self.javoblar.append(("caption", k.get("caption")))


async def _super(uid):
    return uid == 900


async def _tasdiq(lid, uid):
    return {"user_id": 777, "days": 90, "summa": 75_047, "oluvchi": 888}


async def _audit(*a):
    pass


menyu = []


async def _menyu(uid, pro_bormi):
    menyu.append(uid)

database.is_superadmin, database.karta_tasdiqla = _super, _tasdiq
asl_audit, asl_menyu = database.log_admin_action, pro.menu_module.sync_commands
database.log_admin_action, pro.menu_module.sync_commands = _audit, _menyu
chaqiruvlar.clear()
tgbot.usullar.clear()
admin = _Bos("pro:kt:43", _AdminXabar(karta=False), uid=900)
asyncio.run(pro.handle_pro_callback(admin, _Holat()))
kartalar_ = [(pl["chat_id"], json.loads(pl["chat_data"])["a"]) for pl in _yuborilgan()]
check(50, "sovg'a tasdiqlandi: menyu OLUVCHIGA, oluvchiga «Sizga sovg'a», to'lovchiga «yuborildi» — "
          "to'lovchiga «Pro faollashdi» YO'Q; admin chekida belgi",
      menyu == [888] and kartalar_ == [(888, "Sizga sovg'a! 🎁"), (777, "Sovg'a yuborildi! 🎁")]
      and not any(n == "send_message" for n, _ in tgbot.usullar)
      and any(x[0] == "caption" and "TASDIQLANDI" in x[1] for x in admin.message.javoblar))
database.log_admin_action, pro.menu_module.sync_commands = asl_audit, asl_menyu

TOLOV[(43, 777)] = {"holat": "tasdiqlandi", "oluvchi": 888, "sabab": None}
PROFIL.update(premium_until=datetime(2027, 1, 9, 20, 0, tzinfo=timezone.utc))
oluvchi_sana = asyncio.run(pro.tolov_holati(777, 43))
db = kod(ILDIZ / "db" / "database.py")
check(51, "sovg'a: admin matnida oluvchi; «t:» tasdiqda OLUVCHINING sanasi; SQL — ustun, INSERT va "
          "Pro tranzaksiyada oluvchiga",
      "Pro shu odamga: <code>888</code>" in pro.karta_admin_matni(
          {"id": 43, "days": 90, "summa": 75_047, "karta": "8600123412341234", "user_id": 777,
           "oluvchi": 888}, "Ali", "ali")
      and "Pro shu odamga" not in pro.karta_admin_matni(
          {"id": 43, "days": 90, "summa": 75_047, "karta": "8600123412341234", "user_id": 777}, "Ali", None)
      and oluvchi_sana == {"h": "a", "g": "10.01.2027"}
      and "ADD COLUMN IF NOT EXISTS oluvchi BIGINT" in db
      and "INSERT INTO karta_tolov (user_id, days, summa, karta, oluvchi)" in db
      and "_EXTEND_PLAN_SQL, r['oluvchi'] or r['user_id']" in db
      and "RETURNING user_id, days, summa, oluvchi" in db)

htmllar = {"pro": v.pro_html(), "sovga": v.sovga_html(), "tolov": v.tolov_html(),
           "tabrik": v.tabrik_html(), "kunlik": v.kunlik_html(), "profil": v.karta_html()}
chaqirilgan = set()
for h in htmllar.values():
    chaqirilgan |= set(re.findall(r'"((?:pro|dg):[a-z_]+)', h))
ps = kod(ILDIZ / "handlers" / "pro.py")
check(52, "kartadagi har tugma callback'i — mavjud handler amali (pro:/dg:), so'rov tap ichida "
          "(`W.request(\"c:\"+c)` faqat `A` da); Pro va bayram kartasida so'rovlar yoqilgan",
      chaqirilgan and all(c.split(":")[0] in ("pro", "dg") for c in chaqirilgan)
      and all(f'action == "{c.split(":")[1]}"' in ps or f'"{c.split(":")[1]}"' in ps
              or c.startswith("dg:") for c in chaqirilgan)
      and all(h.count('W.request("c:"+c)') == 1 for h in htmllar.values())
      and '"html": vidjet.pro_html(), "allow_queries": True' in ps
      and "izoh, kb, sorov=True,\n" in ps)

htm = v.kunlik_html()
check(53, "/kunlik iPhone uchun: SVG atributida var() yo'q, gradient zaxira rang bilan; soat bosiladi",
      not re.search(r'(fill|stroke):"var\(', htm) and 'stroke:"url(#kg)"' not in htm
      and '"url(#kg) #6b72ff"' in htm and 'A("dg:h:"+i)' in htm)

yuklovchi.bot = asl_bot
msg.bot = asl_msg_bot
msg._EKRAN.clear()
PROFIL.pop("username", None)
for k_nom, qiymat in asl2.items():
    if qiymat is not None:
        setattr(database, k_nom, qiymat)
pro._obuna, pro._karta, pro.send_rich, pro.bot = asl_pro

# ─────────────────────────────────────────────────────────────
print("─" * 55)
if failures:
    print(f"❌ {len(failures)} ta tekshiruv yiqildi:")
    for f in failures:
        print(f"   • {f}")
    sys.exit(1)
print("✅ Brend kartalari tekshiruvlari — hammasi o'tdi")
