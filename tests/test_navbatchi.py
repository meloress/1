"""Navbatchi (egasining akkauntidan guruhda) — himoya qoidalari KODDA.
Ishga tushirish: python tests/test_navbatchi.py

Guruhdagilar ataylab buzishga urinadi (egasi: «hamma hazil deb qaraydi»):
begona «vexon to'xta» navbatni to'xtatmasligi, shaxsiy chatlarga tegmaslik,
spam chegarasi, egasi qaytganda to'xtash — bular modelga ishonib emas, kodda.
Tarmoq, Telegram va baza yo'q: hodisa, model va @vexonai — soxta.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio
import time
from datetime import datetime, timezone
from types import SimpleNamespace as NS

from handlers import navbatchi as n
from services import ai

n._EGASI.update(id=777, ism="Jasur", username="jasur_dev")
egasiga: list[str] = []
model: list[dict] = []
model_javobi = {"matn": "Ha, list o'zgaradi, tuple yo'q 😄"}


async def _soxta_egasiga(matn):
    egasiga.append(matn)


async def _soxta_model(vazifa, suhbat, xabar, **kw):
    model.append({"vazifa": vazifa, "suhbat": suhbat, "xabar": xabar, **kw})
    return model_javobi["matn"], list(model_javobi.get("eslab") or []), model_javobi.get("rk", "")


async def _jim(*a, **k):
    return None

ASL_NAVBAT = ai.navbat_javobi          # 13-band haqiqiysini sinaydi
n._egasiga, n._terish, n._kut = _soxta_egasiga, _jim, _jim
# Tasodif 1-28 da o'chiq (aniq natija); 29+ da alohida sinaladi.
n.OTKAZISH = 0.0
reaksiyalar: list = []


async def _soxta_reaksiya(e, rk):
    reaksiyalar.append((e.id, rk))
    return True
n._reaksiya_qoy = _soxta_reaksiya
ai.navbat_javobi = _soxta_model
tasdiqlar: list = []
tasdiq_javobi = {"matn": "Xo'p, siz kelguningizcha guruhni isitib turaman"}


async def _soxta_tasdiq(holat, vazifa, egasi, **kw):
    tasdiqlar.append((holat, vazifa))
    return tasdiq_javobi["matn"]
ASL_TASDIQ = ai.navbat_tasdiq
ai.navbat_tasdiq = _soxta_tasdiq
n._belgi_html = lambda: "ᵃᵛᵗᵒʲᵃᵛᵒᵇ"

# ⛔️ Lokal .env — PRODUCTION baza: navbat yoqilganda uslub o'qiladi
# (`_uslub` → biznes_uslub.uslub_ol), xotira esa odam id bo'lsa — soxtalar.
from handlers import biznes_uslub as _bu


async def _uslub_bosh(egasi):
    return {}
_bu.uslub_ol = _uslub_bosh


class Hodisa:
    _id = 100

    def __init__(self, matn, *, out=False, chat=-1001, guruh=True, bot=False,
                 ism="Ali", mentioned=False, sana=None):
        Hodisa._id += 1
        self.id, self.chat_id, self.raw_text, self.out = Hodisa._id, chat, matn, out
        self.is_group = guruh
        self.message = NS(mentioned=mentioned,
                          date=sana or datetime.now(timezone.utc))
        self._odam = NS(first_name=ism, last_name=None, username=None, bot=bot)
        self.ochirildi, self.javob = False, None

    async def delete(self):
        self.ochirildi = True

    async def get_chat(self):
        return NS(title="Dasturchilar")

    async def get_sender(self):
        return self._odam

    async def reply(self, matn, **kw):
        self.javob = matn
        self.yuborilgan = getattr(self, "yuborilgan", []) + [("reply", matn)]
        return NS(id=self.id + 5000)

    async def respond(self, matn, **kw):
        self.javob = matn
        self.yuborilgan = getattr(self, "yuborilgan", []) + [("respond", matn)]
        return NS(id=self.id + 5000 + len(self.yuborilgan))


def yur(*hodisalar):
    for h in hodisalar:
        asyncio.run(n.xabar_keldi(h))


def tozala():
    n._NAVBAT.clear(); egasiga.clear(); model.clear(); n.BELGI_YOQIQ = True
    model_javobi["matn"] = "Ha, list o'zgaradi, tuple yo'q 😄"


# ── 1) Buyruq tahlili ────────────────────────────────────────────────
b = n.buyruq
assert b("vexon, men kelgunimcha dasturlash savollariga javob ber") == \
    ("boshla", "men kelgunimcha dasturlash savollariga javob ber")
for s in ("vexon to'xta", "Vexon TO‘XTA!", "vexon stop", "vexon, bas", "VEXON toxta."):
    assert b(s) == ("toxta", ""), s
assert b("vexon belgi o'chir") == ("belgi", "0") and b("vexon belgini yoq") == ("belgi", "1")
assert b("vexon zo'r") is None, "2 so'z — oddiy gap, navbat yoqilmasin"
assert b("vexonchi guruhda tur dedim") is None and b("salom vexon to'xta") is None
print("[1] buyruq tahlili: boshla / to'xta / belgi, oddiy gap buyruq emas OK")

# ── 2) Egasi yoqadi: buyruq guruhda qoladi, Vexon tabiiy javob beradi ─
tozala()
h = Hodisa("vexon guruhni qizitib tur, hazillash", out=True)
yur(h)
assert not h.ochirildi and -1001 in n._NAVBAT, "buyruq guruhda qolsin, navbat yoqilsin"
assert n._NAVBAT[-1001].vazifa == "guruhni qizitib tur, hazillash"
assert tasdiqlar[-1] == ("boshla", "guruhni qizitib tur, hazillash")
assert h.javob.startswith("Xo&#x27;p, siz kelguningizcha"), h.javob
assert h.yuborilgan[0][0] == "reply", "egasi: har doim reply (buyruqqa ham)"
assert (h.chat_id, h.id + 5000) in n._YOZILGAN, "tasdiq o'zimizniki deb belgilansin"
assert "Navbat yoqildi" in egasiga[-1] and "Dasturchilar" in egasiga[-1]
tasdiq_javobi["matn"] = None                    # model yo'q — zaxira gap
h2 = Hodisa("vexon guruhni qizitib tur, hazillash", out=True)
yur(h2)
assert h2.javob.startswith(n.html.escape(n._TASDIQ_ZAXIRA["boshla"])), h2.javob
tasdiq_javobi["matn"] = "Xo'p, siz kelguningizcha guruhni isitib turaman"
print("[2] egasi yoqdi: buyruq qoldi, uning profilidan tabiiy «xo'p» (zaxirasi bilan) OK")

# ── 3) ⛔️ Begona «vexon to'xta» — navbat TO'XTAMAYDI, suhbat bo'ladi ───
h = Hodisa("vexon to'xta", ism="Hazilkash")
yur(h)
assert -1001 in n._NAVBAT, "KRITIK: begona odam navbatni to'xtatdi"
assert not h.ochirildi, "begonaning xabari o'chirilmasin"
assert model and "vexon to'xta" in model[-1]["xabar"] and h.javob, \
    "begona buyruq model uchun oddiy suhbat — javob qaytadi"
print("[3] begona «vexon to'xta» navbatni to'xtatmadi, hazil javob oldi OK")

# ── 4) Tezlik: ORALIQ ichida ikkinchi xabarga model chaqirilmaydi ────
oldin = len(model)
yur(Hodisa("yana bir savol"))
assert len(model) == oldin, "20 s ichida ikkinchi javob — spam"
n._NAVBAT[-1001].oxirgi_javob = time.time() - n.ORALIQ - 1
yur(Hodisa("endi-chi?"))
assert len(model) == oldin + 1
print("[4] guruhda 20 s da bittadan ortiq javob yo'q OK")

# ── 5) Model «-» qaytarsa joy bo'shaydi (keyingi xabar kutib qolmaydi) ─
nav = n._NAVBAT[-1001]
nav.oxirgi_javob = 0.0
model_javobi["matn"] = None
yur(Hodisa("ertaga kim keladi"))
assert nav.oxirgi_javob == 0.0, "javobsiz xabar tezlik slotini yeb qo'ydi"
model_javobi["matn"] = "javob"
print("[5] javob bermagan xabar slotni band qilmadi OK")

# ── 6) Shaxsiy chat, bot, eski xabar, boshqa guruh — tegilmaydi ──────
oldin = len(model)
nav.oxirgi_javob = 0.0
eski = datetime.fromtimestamp(int(nav.boshlandi) - 60, timezone.utc)
yur(Hodisa("salom", guruh=False), Hodisa("salom", bot=True),
    Hodisa("salom", sana=eski), Hodisa("salom", chat=-1002),
    Hodisa("vexon to'xta", guruh=False, out=True))
assert len(model) == oldin and -1001 in n._NAVBAT, model[oldin:]
print("[6] shaxsiy chat, bot, navbatdan oldingi xabar, boshqa guruh — jim OK")

# ── 7) Belgi: yoniq — bor, o'chiq — yo'q ─────────────────────────────
nav.oxirgi_javob = 0.0
h = Hodisa("python nima")
yur(h)
assert h.javob.endswith("\nᵃᵛᵗᵒʲᵃᵛᵒᵇ"), h.javob
yur(Hodisa("vexon belgi o'chir", out=True))
assert n.BELGI_YOQIQ is False and -1001 in n._NAVBAT, "belgi buyrug'i navbatni to'xtatmasin"
nav.oxirgi_javob = 0.0
h = Hodisa("java nima")
yur(h)
assert h.javob == "javob", h.javob
print("[7] avtojavob belgisi o'chib-yoqiladi OK")

# ── 8) Egasiga reply / tilga olish — model buni biladi ───────────────
nav.oxirgi_javob = 0.0
yur(Hodisa("@jasur_dev qayerdasan"))
assert model[-1]["menga"] is True
nav.oxirgi_javob = 0.0
yur(Hodisa("rahmat", mentioned=True))
assert model[-1]["menga"] is True
nav.oxirgi_javob = 0.0
yur(Hodisa("ob-havo qanday"))
assert model[-1]["menga"] is False
assert model[-1]["oldingi"], "oldingi javoblar modelga berilsin (takrorlamasin)"
print("[8] egasiga reply va @username — «menga», oldingi javoblar uzatildi OK")

# ── 9) Bizning javobimiz egasining xabari deb navbatni to'xtatmaydi ──
sent_id = h.id + 5000
bizniki = Hodisa("javob", out=True)
bizniki.id = sent_id
yur(bizniki)
assert -1001 in n._NAVBAT, "o'zimiz yuborgan javob navbatni to'xtatib qo'ydi"
print("[9] o'zimiz yuborgan xabar «egasi qaytdi» deb o'qilmadi OK")

# ── 10) Egasi oddiy xabar yozsa — qaytdi, hisobot keladi ─────────────
yur(Hodisa("keldim, rahmat hammaga", out=True))
assert -1001 not in n._NAVBAT and "Navbat tugadi" in egasiga[-1]
assert "siz guruhga yozdingiz" in egasiga[-1] and "python nima" in egasiga[-1]
print("[10] egasi qaytdi — navbat tugadi, hisobotda savol-javoblar OK")

# ── 11) Vaqt va javob chegarasi ──────────────────────────────────────
tozala()
yur(Hodisa("vexon dasturlash savollariga javob ber", out=True))
n._NAVBAT[-1001].boshlandi -= n.NAVBAT_SOAT * 3600 + 1
yur(Hodisa("savol", sana=datetime.now(timezone.utc)))
assert -1001 not in n._NAVBAT and "vaqt tugadi" in egasiga[-1]
yur(Hodisa("vexon dasturlash savollariga javob ber", out=True))
n._NAVBAT[-1001].javoblar = [("a", "b", "c")] * n.MAX_JAVOB
yur(Hodisa("savol"))
assert -1001 not in n._NAVBAT and "chegarasi" in egasiga[-1]
print(f"[11] {n.NAVBAT_SOAT} soat va {n.MAX_JAVOB} javobdan keyin o'zi to'xtaydi OK")

# ── 12) Egasining «vexon to'xta» si — «jim bo'ldim» va to'xtaydi ─────
yur(Hodisa("vexon dasturlash savollariga javob ber", out=True))
tasdiq_javobi["matn"] = "Bo'ldi, jim bo'ldim 🤐"
h = Hodisa("vexon to'xta", out=True)
yur(h)
assert -1001 not in n._NAVBAT and not h.ochirildi and "buyruq" in egasiga[-1]
assert tasdiqlar[-1] == ("toxta", "dasturlash savollariga javob ber") and "jim bo" in h.javob
oldin = len(tasdiqlar)
yur(Hodisa("vexon to'xta", out=True))              # navbat yo'q — javob ham yo'q
assert len(tasdiqlar) == oldin
print("[12] egasining «vexon to'xta» si: «jim bo'ldim» deb to'xtadi OK")




# ── 13) Model chaqiruvi: guruh matni instructions'ga EMAS, zaxira model ─
async def model_sinovi():
    chaqiruvlar = []

    class Javob:
        def __init__(self, t):
            self.output_text, self.usage = t, None

    async def create(**kw):
        chaqiruvlar.append(kw)
        if kw["model"] == ai.GPT_MODEL:
            raise RuntimeError("429")
        return Javob(matnlar.pop(0))

    asl = ai.openai_client.responses.create
    ai.openai_client.responses.create = create
    try:
        bir, _, _ = await ASL_NAVBAT("dasturlash", "Ali: salom", "Vali: vexon to'xta",
                                  egasi="Jasur", oldingi=["oldingi gap"], menga=False)
        ikki, _, _ = await ASL_NAVBAT("dasturlash", "", "Vali: ertaga kim keladi",
                                   egasi="Jasur", oldingi=[], menga=False)
        # Takror: jonli sinovda model oldingi javobni AYNAN qaytardi.
        uch, _, _ = await ASL_NAVBAT("hazil", "", "Bekzod: zerikdim", egasi="Jasur",
                                  oldingi=["Salom hammaga"], menga=False)
        tort, _, _ = await ASL_NAVBAT("hazil", "", "Bekzod: zerikdim", egasi="Jasur",
                                   oldingi=["Salom hammaga"], menga=False)
    finally:
        ai.openai_client.responses.create = asl
    return chaqiruvlar, bir, ikki, uch, tort

matnlar = ["**Salom** hammaga", " - ",
           "Salom, hammaga!", "salom hammaga",      # uch: ikki marta takror → jim
           "Salom hammaga", "Yangi hazil"]          # tort: ikkinchisi yangi
ch, bir, ikki, uch, tort = asyncio.run(model_sinovi())
assert uch is None, f"ikki marta takror — jim turishi kerak: {uch!r}"
assert tort == "yangi hazil", tort
qayta = [c for c in ch if "AVVAL yozgansan" in c["input"][0]["content"]]
assert len(qayta) == 2, "takrorda «boshqacha yoz» bilan qayta so'ralsin"
assert all(c["instructions"] is ai.NAVBAT_INSTRUCTIONS for c in ch), \
    "instructions hamma uchun bir xil bo'lsin (kesh) — guruh matni unga kirmaydi"
assert "vexon to'xta" in ch[0]["input"][1]["content"] and ch[0]["input"][1]["role"] == "user"
assert "dasturlash" in ch[0]["input"][0]["content"] and ch[0]["input"][0]["role"] == "developer"
assert ch[1]["model"] == ai.MODEL_FALLBACKS[0], "asosiy model yiqilsa zaxiraga o'tsin"
assert bir == "salom hammaga", bir
assert ikki is None, "«-» — javob yo'q"
assert not any("reasoning" in c for c in ch if not c["model"].startswith(("gpt-5", "o")))
print("[13] model: guruh matni user'da, vazifa developer'da, «-» → jim, zaxira model, takror → qayta yoki jim OK")

# ═══════════════════════════════════════════════════════════════════
# 14-21. Botning o'zida QR bilan ulash — FAQAT superadmin
# ═══════════════════════════════════════════════════════════════════
import core.loader as yuklovchi
from db import database as db

baza = {"ulanish": None}
yozildi: list = []
SUPER = 777


async def _is_super(uid):
    return uid == SUPER


async def _ol():
    return baza["ulanish"]


async def _yoz(q):
    baza["ulanish"] = q
    yozildi.append(q)


class SoxtaBot:
    def __init__(self):
        self.yuborildi = []

    async def send_message(self, chat, matn, **kw):
        self.yuborildi.append(matn)

sbot = SoxtaBot()
db.is_superadmin, db.navbat_ulanish_ol, db.navbat_ulanish_yoz = _is_super, _ol, _yoz
yuklovchi.bot = sbot


class Xabar:
    def __init__(self, uid=SUPER, chat_turi="private", matn="/navbat_ulash"):
        self.from_user = NS(id=uid)
        self.chat = NS(id=uid, type=chat_turi)
        self.text, self.ochirildi, self.javoblar = matn, False, []

    async def delete(self):
        self.ochirildi = True

    async def answer(self, matn, **kw):
        self.javoblar.append(matn)


# ── 14) Begona va guruh — buyruq umuman yo'q ─────────────────────────
assert asyncio.run(n.egami(Xabar())) is True
assert asyncio.run(n.egami(Xabar(uid=555))) is False, "KRITIK: begona ulash buyrug'iga kirdi"
assert asyncio.run(n.egami(Xabar(chat_turi="supergroup"))) is False, "guruhda ham yo'q"


async def _yiqil(uid):
    raise RuntimeError("baza yo'q")
db.is_superadmin = _yiqil
assert asyncio.run(n.egami(Xabar())) is False, "baza xatosida — yopiq tomon"
db.is_superadmin = _is_super


class SoxtaDp:
    def __init__(self):
        self.message = self
        self.royxat = []

    def register(self, fn, *filtrlar):
        self.royxat.append((fn, filtrlar))

dp = SoxtaDp()
n.royxatdan_otkaz(dp)
for fn, filtrlar in dp.royxat:
    assert n.egami in filtrlar or n.parol_kutilmoqda in filtrlar, \
        f"KRITIK: {fn.__name__} superadmin filtrisiz ro'yxatdan o'tdi"
assert len(dp.royxat) == 5
print("[14] ulash buyruqlari faqat superadmin + shaxsiy chat; begonaga mavjud emas OK")

# ── 15) Shifr: bazada ochiq sessiya yo'q, boshqa token bilan ochilmaydi ─
shifr = n.shifrla({"sessiya": "MAXFIY_SESSIYA_1", "api_id": 1, "api_hash": "a" * 32})
assert "MAXFIY" not in shifr and n.ochir(shifr)["sessiya"] == "MAXFIY_SESSIYA_1"
import core.config as cfg
asl_token, cfg.BOT_TOKEN = cfg.BOT_TOKEN, "boshqa:token"
assert n.ochir(shifr) is None, "boshqa kalit bilan ochilmasin"
cfg.BOT_TOKEN = asl_token
assert n.ochir("buzuq") is None and n.ochir(None) is None
print("[15] sessiya bazada shifrlangan, kalitsiz ochilmaydi OK")

# ── 16) /navbat_api: xabar o'chadi, format tekshiriladi ──────────────
x = Xabar(matn="/navbat_api 123 xyz")
asyncio.run(n.navbat_api(x, NS(args="123 xyz")))
assert x.ochirildi and baza["ulanish"] is None and "Format" in x.javoblar[-1]
x = Xabar()
asyncio.run(n.navbat_api(x, NS(args="1234567 " + "ab" * 16)))
assert x.ochirildi and n.ochir(baza["ulanish"]) == {"api_id": 1234567, "api_hash": "ab" * 16}
print("[16] /navbat_api: api_hash chatda qolmaydi, noto'g'ri format saqlanmaydi OK")


# ── 17) Begona akkaunt skanerlasa — saqlanmaydi, chiqib ketiladi ─────
class SoxtaKlient:
    def __init__(self, me_id):
        self._me, self.chiqdi, self.uzildi = me_id, False, False
        self.session = NS(save=lambda: "YANGI_SESSIYA")
        self.api_id, self.api_hash = 1234567, "ab" * 16
        self.parollar = []

    async def get_me(self):
        return NS(id=self._me, first_name="Jasur", last_name=None, username="jasur_dev")

    async def log_out(self):
        self.chiqdi = True

    async def disconnect(self):
        self.uzildi = True

    async def sign_in(self, password):
        from telethon.errors import PasswordHashInvalidError
        self.parollar.append(password)
        if password != "togri":
            raise PasswordHashInvalidError(request=None)

qayta = []


async def _qayta():
    qayta.append(1)
asl_qayta, n.qayta_ulan = n.qayta_ulan, _qayta
k = SoxtaKlient(999)
asyncio.run(n._yakunla(k, SUPER, SUPER))
assert k.chiqdi and "sessiya" not in (n.ochir(baza["ulanish"]) or {}) and not qayta, \
    "KRITIK: boshqa odamning akkaunti egasi nomidan saqlandi"
k = SoxtaKlient(SUPER)
asyncio.run(n._yakunla(k, SUPER, SUPER))
assert n.ochir(baza["ulanish"])["sessiya"] == "YANGI_SESSIYA" and qayta == [1]
assert "Ulandi" in sbot.yuborildi[-1]
print("[17] faqat egasining o'z akkaunti saqlanadi, begonasi log_out OK")

# ── 18) Parol: o'chiriladi, 3 xatoda bekor, muddati o'tsa — yo'q ─────
k = SoxtaKlient(SUPER)
n._PAROL[SUPER] = {"client": k, "chat": SUPER, "urinish": 0, "t": time.time()}
assert n.parol_kutilmoqda(Xabar(matn="x")) and not n.parol_kutilmoqda(Xabar(uid=555, matn="x"))
for i in range(3):
    x = Xabar(matn=f"xato{i}")
    asyncio.run(n.parol_keldi(x))
    assert x.ochirildi, "parol chatda qolmasin"
assert SUPER not in n._PAROL and k.uzildi and "3 marta" in x.javoblar[-1]
k = SoxtaKlient(SUPER)
n._PAROL[SUPER] = {"client": k, "chat": SUPER, "urinish": 0, "t": time.time()}
qayta.clear()
x = Xabar(matn="togri")
asyncio.run(n.parol_keldi(x))
assert x.ochirildi and SUPER not in n._PAROL and qayta == [1] and k.parollar == ["togri"]


async def _muddat():
    n._PAROL[SUPER] = {"client": SoxtaKlient(SUPER), "chat": SUPER, "urinish": 0,
                       "t": time.time() - n.PAROL_MUDDAT - 1}
    natija = n.parol_kutilmoqda(Xabar(matn="x"))
    await asyncio.sleep(0)
    return natija
assert asyncio.run(_muddat()) is False and SUPER not in n._PAROL
print("[18] parol: darhol o'chadi, 3 xatoda va 5 daqiqada bekor, to'g'risida ulanadi OK")

# ── 19) QR serverda yasaladi (tashqi servis yo'q) ────────────────────
png = n._qr_png("tg://login?token=abc")
assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 300
print("[19] QR rasm serverda (segno), token tashqariga chiqmaydi OK")

# ── 20) /navbat_uzish: Telegram'da log_out, API qoladi ───────────────
k = SoxtaKlient(SUPER)
n._CLIENT = k
baza["ulanish"] = n.shifrla({"api_id": 1, "api_hash": "c" * 32, "sessiya": "S"})
x = Xabar(matn="/navbat_uzish")
asyncio.run(n.navbat_uzish(x))
assert k.chiqdi and n._CLIENT is None and n.ochir(baza["ulanish"]) == {"api_id": 1, "api_hash": "c" * 32}
print("[20] /navbat_uzish sessiyani Telegram'da ham tugatdi, API saqlandi OK")

# ── 21) Manba: Railway o'zgaruvchisi ustun, keyin baza ───────────────
baza["ulanish"] = n.shifrla({"api_id": 5, "api_hash": "d" * 32, "sessiya": "BAZA"})
assert asyncio.run(n._sozlama()) == ("BAZA", 5, "d" * 32)
os.environ.update(USERBOT_SESSION="ENV", USERBOT_API_ID="9", USERBOT_API_HASH="e" * 32)
assert asyncio.run(n._sozlama()) == ("ENV", 9, "e" * 32)
for k_ in ("USERBOT_SESSION", "USERBOT_API_ID", "USERBOT_API_HASH"):
    os.environ.pop(k_)
baza["ulanish"] = None
assert asyncio.run(n._sozlama()) is None
n.qayta_ulan = asl_qayta
print("[21] sessiya manbai: Railway → baza → yo'q (jim) OK")

# ── 22) QR jarayoni: yuborish, yangilash, parolga o'tish, QR o'chadi ──
import telethon
from telethon.errors import SessionPasswordNeededError


class QRBot(SoxtaBot):
    def __init__(self):
        super().__init__()
        self.rasmlar, self.tahrirlar, self.ochirildi = [], 0, []

    async def send_photo(self, chat, fayl, **kw):
        self.rasmlar.append(kw)
        return NS(message_id=55)

    async def edit_message_media(self, *a, **kw):
        self.tahrirlar += 1

    async def delete_message(self, chat, mid):
        self.ochirildi.append(mid)


def qr_klient(oqim):
    """oqim — har wait() da: "timeout" / "parol" / "ok"."""
    class QR:
        url = "tg://login?token=x"

        async def wait(self, timeout=None):
            q = oqim.pop(0)
            if q == "timeout":
                raise asyncio.TimeoutError
            if q == "parol":
                raise SessionPasswordNeededError(request=None)

        async def recreate(self):
            pass

    class K(SoxtaKlient):
        def __init__(self, *a, **k):
            super().__init__(SUPER)
            klientlar.append(self)

        async def connect(self):
            pass

        async def qr_login(self):
            return QR()
    return K

klientlar: list = []
asl_tc, qbot = telethon.TelegramClient, QRBot()
yuklovchi.bot = qbot
try:
    telethon.TelegramClient = qr_klient(["timeout", "parol"])
    asyncio.run(n._qr_jarayon(SUPER, SUPER, 1, "a" * 32))
    assert qbot.rasmlar[0].get("protect_content") is True, "QR forward qilinmasin"
    assert qbot.tahrirlar == 1, "token eskirganda QR yangilansin"
    assert qbot.ochirildi == [55], "QR rasmi oxirida o'chirilsin"
    assert SUPER in n._PAROL and not klientlar[-1].uzildi, "parol kutilganda ulanish tursin"
    assert "parolingizni" in qbot.yuborildi[-1] and SUPER not in n._ULASHMOQDA
    n._PAROL.clear()
    n.qayta_ulan = _qayta
    qayta.clear()
    telethon.TelegramClient = qr_klient(["ok"])
    asyncio.run(n._qr_jarayon(SUPER, SUPER, 1, "a" * 32))
    assert qayta == [1] and klientlar[-1].uzildi and "Ulandi" in qbot.yuborildi[-1]
finally:
    telethon.TelegramClient, n.qayta_ulan = asl_tc, asl_qayta
print("[22] QR: himoyalangan rasm, yangilanadi, parolga o'tadi, oxirida o'chadi OK")

# ── 23) Tasdiq modeli: instructions bir xil, holat developer'da ──────
async def tasdiq_sinovi():
    ch = []

    class J:
        output_text, usage = "**Xo'p**, turaman", None

    async def create(**kw):
        ch.append(kw)
        return J()
    asl = ai.openai_client.responses.create
    ai.openai_client.responses.create = create
    try:
        return ch, await ASL_TASDIQ("toxta", "hazillash", "Jasur")
    finally:
        ai.openai_client.responses.create = asl

ch, t = asyncio.run(tasdiq_sinovi())
assert t == "xo'p turaman" and ch[0]["instructions"] is ai.NAVBAT_TASDIQ_INSTRUCTIONS
assert "[HOLAT] toxta" in ch[0]["input"][0]["content"]
print("[23] tasdiq: bir xil instructions (kesh), holat developer'da, markdown tozalandi OK")

# ── 24) Xotira: avvalgi faktlar modelga, yangilari saqlanadi; uslub ──
biznes_uslub = _bu
xotira_ol, xotira_qosh = [], []


async def _odam_ol(egasi, odam):
    xotira_ol.append((egasi, odam))
    return ["Python o'rganyapti"]


async def _odam_qosh(egasi, odam, ism, faktlar):
    xotira_qosh.append((egasi, odam, ism, faktlar))
    return faktlar


async def _uslub_ol(egasi):
    return {"uslub": "kichik harf bilan, qisqa, «xullas» deydi"}

db.navbat_odam_ol, db.navbat_odam_qosh = _odam_ol, _odam_qosh
asl_uslub, biznes_uslub.uslub_ol = biznes_uslub.uslub_ol, _uslub_ol
try:
    tozala()
    yur(Hodisa("vexon dasturlash savollariga javob ber", out=True))
    nav = n._NAVBAT[-1001]
    assert nav.uslub == "", "⛔️ Biznes (mijoz) uslubi guruhga berilmaydi — hazilni bosib ketdi"
    model_javobi.update(matn="ha, tuple o'zgarmaydi", eslab=["frontend dasturchi"])
    h = Hodisa("men frontendchiman, list nima?")
    h._odam.id = 4242
    async def _yur_va_kut():
        await n.xabar_keldi(h)
        await asyncio.sleep(0.05)                  # fon vazifasi (eslab)
    asyncio.run(_yur_va_kut())
    assert xotira_ol[-1] == (777, 4242) and model[-1]["odam_haqida"] == ["Python o'rganyapti"]
    assert model[-1]["uslub"] == nav.uslub
    assert xotira_qosh[-1] == (777, 4242, "Ali", ["frontend dasturchi"]), xotira_qosh
    # Javob bermagan («-») xabardagi fakt ham eslab qolinadi.
    nav.oxirgi_javob = 0.0
    model_javobi.update(matn=None, eslab=["Samarqanddan"])
    h = Hodisa("men samarqandlikman")
    h._odam.id = 4243
    asyncio.run(_yur_va_kut())
    assert xotira_qosh[-1][1:] == (4243, "Ali", ["Samarqanddan"])
finally:
    biznes_uslub.uslub_ol = asl_uslub
    model_javobi.update(matn="javob", eslab=[])
print("[24] xotira: eski faktlar modelga, yangilari saqlanadi (jim bo'lsa ham); uslub yuklandi OK")

# ── 25) Fakt tekshiruvi: sezgir ma'lumot bazaga tushmaydi ────────────
cf = db.clean_navbat_fakt
for yaxshi in ("frontend dasturchi, React'ni yaxshi ko'radi", "Andijondan", "dinamo muxlisi",
               "Toshkentda yashaydi", "futbolni yaxshi ko'radi"):
    assert cf(yaxshi) == yaxshi, yaxshi
for yomon in ("telefoni 90 123 45 67", "karta raqami 8600123412341234", "kasal bo'lib qolgan",
              "pul kerak ekan", "uyi Chilonzor 9", "sevgilisi bor", "diniy odam", "@ali_dev",
              "parolini aytdi", "ab", "x" * 200):
    assert cf(yomon) is None, yomon
print("[25] faktlar: telefon, karta, salomatlik, pul, manzil, din, sevgi — saqlanmaydi OK")


# ── 26) Premium emoji: animatsiyali, rad etilsa oddiy bilan qayta ────
class RadPremium(Hodisa):
    async def reply(self, matn, **kw):
        if "<tg-emoji" in matn:
            raise RuntimeError("DOCUMENT_INVALID")
        self.javob = matn
        return NS(id=self.id + 5000)

n._NAVBAT[-1001].oxirgi_javob = 0.0
model_javobi.update(matn="salom 🤖")
h = Hodisa("bot bormi")
yur(h)
assert "<tg-emoji" in h.javob and "🤖" in h.javob, h.javob
n._NAVBAT[-1001].oxirgi_javob = 0.0
h = RadPremium("yana")
yur(h)
assert h.javob and "<tg-emoji" not in h.javob and "🤖" in h.javob, "premium rad etilsa oddiy emoji"
model_javobi.update(matn="javob")
print("[26] premium emoji: animatsiyali, rad etilsa oddiy emoji bilan yetdi OK")


# ── 27) /navbat_xotira: ro'yxat va tozalash ──────────────────────────
async def _royxat(egasi):
    return [("Ali", ["frontend dasturchi", "<b>Toshkent</b>"])]


async def _tozala(egasi):
    return 3

db.navbat_odamlar_royxat, db.navbat_odamlar_tozala = _royxat, _tozala
x = Xabar(matn="/navbat_xotira")
asyncio.run(n.navbat_xotira(x, NS(args=None)))
assert "Ali" in x.javoblar[-1] and "&lt;b&gt;Toshkent" in x.javoblar[-1], "HTML qochirilsin"
asyncio.run(n.navbat_xotira(x, NS(args="tozala")))
assert "3 kishi" in x.javoblar[-1]
print("[27] /navbat_xotira ko'rsatadi (HTML xavfsiz) va tozalaydi OK")


# ── 28) Model JSON: javob + eslab; JSON bo'lmasa — matn javob ────────
assert ai._navbat_ochish('{"javob": "ha", "eslab": ["a", "b", "c"], "reaksiya": "🤣"}') == \
    ("ha", ["a", "b"], "🤣")
assert ai._navbat_ochish('{"javob": "-", "eslab": [], "reaksiya": "🦄"}')[2] == "", \
    "ro'yxatda yo'q reaksiya — guruh rad etadi"
assert ai._navbat_ochish("oddiy matn") == ("oddiy matn", [], "")
assert ai.NAVBAT_SXEMA["schema"]["required"] == ["javob", "eslab", "reaksiya"]
assert ai._navbat_odamdek("zerikish — **zo'r**") == "zerikish zo'r", "uzun tire — AI belgisi"
assert ai._navbat_odamdek("o‘zgaradi, React’da") == "o'zgaradi React'da", "telefonda o' yoziladi"
assert ai._navbat_odamdek("ha bro \n \n  keyin") == "ha bro\n\nkeyin"
# Ko'cha tili: tinish belgisi va katta harf yo'q (egasi: «nuqta vergul bilan kim yozadi»).
od = ai._navbat_odamdek
assert od("Shu yerdaman, Sardor, yo'qolganim yo'q. Shunchaki: ishdaman!") == \
    "shu yerdaman Sardor yo'qolganim yo'q Shunchaki ishdaman"
assert od("«Zo'r» ekan; qachon kelasan?") == "zo'r ekan qachon kelasan?", "savol belgisi qoladi"
assert od("narxi 1,5 mln, 3.5 baravar...") == "narxi 1,5 mln 3.5 baravar...", "sonlar va … qoladi"
assert od("API ishlamayapti.") == "API ishlamayapti", "qisqartma kichik harfga tushmaydi"
assert od("Ha bro.\n\nKeyin, gaplashamiz.") == "ha bro\n\nkeyin gaplashamiz", "har xabar alohida"
# Baza funksiyasi soxta bo'lgani uchun: saqlash HAQIQATAN tekshiruvdan o'tkazadimi.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _manba import kod
_db = kod(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db", "database.py"))
_qosh = _db[_db.index("async def navbat_odam_qosh"):_db.index("async def navbat_odamlar_royxat")]
assert "clean_navbat_fakt(" in _qosh and "NAVBAT_FAKT_MAX" in _qosh and "NAVBAT_SAQLASH_KUN" in _qosh,     "KRITIK: navbat_odam_qosh faktni tekshiruvsiz saqlaydi"
print("[28] model chiqishi: JSON (javob, ≤2 fakt), uzun tire tozalandi, saqlash tekshiruvdan o'tadi OK")

# ── 29) Vaqt: o'qish kechikishi va telefonda terish tezligi ──────────
import random
random.seed(7)
# Egasi kutishni o'chirdi: o'qish 0, «yozmoqda» qisqa (≤ 6 s).
assert n.KUTISH_YOQIQ is False, "egasi so'radi: tez-tez javob bersin"
assert n.oqish_vaqti(True) == 0.0 and n.oqish_vaqti(False) == 0.0
assert n.terish_vaqti("ha") <= 2.0 and n.terish_vaqti("x" * 400) == 6.0
n.KUTISH_YOQIQ = True                              # qayta yoqilsa — odamdek oraliqlar
menga_v = [n.oqish_vaqti(True) for _ in range(2000)]
boshqa_v = [n.oqish_vaqti(False) for _ in range(2000)]
assert 3 <= min(menga_v) and max(menga_v) <= 18, "o'ziga qaratilganiga 3-18 s"
assert 6 <= min(boshqa_v) and max(boshqa_v) <= 100 and max(boshqa_v) > 45, \
    "boshqasiga 6-40 s, ba'zan 1-2 daqiqa"
assert len({round(v) for v in boshqa_v}) > 30, "kechikish har safar boshqacha"
assert 2.0 <= n.terish_vaqti("ha") <= 4.5 and n.terish_vaqti("x" * 400) == 25.0
assert n.terish_vaqti("x" * 60) > n.terish_vaqti("x" * 10)
n.KUTISH_YOQIQ = False
print("[29] vaqt: kutish o'chiq — darhol, «yozmoqda» ≤ 6 s; yoqilsa 3-100 s / 2-25 s OK")


# ── 30) Har xabarga yozmaydi: savol va o'ziga qaratilgani — o'tkazilmaydi ─
def yangi_navbat():
    tozala()
    yur(Hodisa("vexon guruhni qizitib tur, hazillash", out=True))
    return n._NAVBAT[-1001]

nav = yangi_navbat()
n.OTKAZISH = 1.0
oldin = len(model)
yur(Hodisa("zo'r ekan"))
assert len(model) == oldin and nav.oxirgi_javob == 0.0, "o'tkazilgan xabar slotni yemasin"
for s in ("nima gap", "ertaga kelasanmi", "qachon boshlanadi", "python yaxshimi?"):
    nav.oxirgi_javob = 0.0
    yur(Hodisa(s))
    assert len(model) == oldin + 1, s
    oldin += 1
nav.oxirgi_javob = 0.0
yur(Hodisa("zo'r ekan", mentioned=True))
assert len(model) == oldin + 1, "o'ziga qaratilgani o'tkazilmaydi"
n.OTKAZISH = 0.0
for s in ("zo'r ekan", "kuldim", "hammaga salom"):
    assert not n._SAVOL_RE.search(s), s
print("[30] odamdek: oddiy gapni ba'zan o'tkazadi, savol va reply — hech qachon OK")

# ── 31) Reply — DOIM (egasi so'radi): oxirgi xabarga ham, mavzuda ham ─
nav.oxirgi_javob = 0.0
h = Hodisa("nima gap")
yur(h)
assert [t for t, _ in h.yuborilgan] == ["reply"], "egasi: har doim reply"
oraliq = Hodisa("boshqa gap")


async def _orada_xabar(*a):
    await n.xabar_keldi(oraliq)                    # «o'qiyotganda» yangisi keldi
n._kut = _orada_xabar
nav.oxirgi_javob = 0.0
h = Hodisa("nima gap")
yur(h)
n._kut = _jim
assert h.yuborilgan[0][0] == "reply"
assert "boshqa gap" in model[-1]["suhbat"], "kutish paytida kelgani kontekstda"
print("[31] har doim reply (egasi so'radi); kutishda kelgani kontekstda OK")

# ── 32) U bilan gaplashayotganlar javobsiz QOLMAYDI: band bo'lsa — navbat ─
n.MENGA_ORALIQ = 0.0
nav.oxirgi_javob = 0.0
qaratilgan = Hodisa("jasur qayerdasan", mentioned=True, ism="Sardor")
begona_orada = Hodisa("bugun nima qildinglar", ism="Bekzod")   # menga emas — band, jim
vazifalar = []


async def _orada(*a):
    if not vazifalar:
        vazifalar.append(asyncio.create_task(n.xabar_keldi(qaratilgan)))
        await n.xabar_keldi(begona_orada)
        await asyncio.sleep(0.1)                   # qaratilgan navbatda turibdi


async def _ikkalasi():
    await n.xabar_keldi(Hodisa("bugun issiq ekan", ism="Vali"))
    await asyncio.gather(*vazifalar)
n._kut = _orada
oldin = len(model)
asyncio.run(_ikkalasi())
n._kut = _jim
assert len(model) == oldin + 2, "KRITIK: band paytida unga yozgan odam javobsiz qoldi"
assert model[-2]["xabar"] == "Vali: bugun issiq ekan"
assert model[-1]["xabar"] == "Sardor: jasur qayerdasan" and model[-1]["menga"] is True
assert qaratilgan.javob and begona_orada.javob is None, "band paytidagi oddiy gap — o'tkaziladi"
assert "jasur qayerdasan" not in model[-1]["suhbat"], "nishon kontekstda ikki marta bo'lmasin"
assert nav.nishon is None and nav.kutayotgan == 0
# Navbat cheklangan: to'lsa — jim (akkaunt spamga tushmasin).
nav.kutayotgan = n.MENGA_NAVBAT
oldin = len(model)
yur(Hodisa("jasur?", mentioned=True))
assert len(model) == oldin
nav.kutayotgan = 0
n.MENGA_ORALIQ = 3.0


# ORALIQ yuborilgan paytdan: 40 s «o'qigan» bo'lsa, 20 s darhol tugamasin.
async def _sekin(*a):
    await asyncio.sleep(0.2)
nav.oxirgi_javob = 0.0
n._kut = _sekin
t0 = time.time()
yur(Hodisa("nima gap"))
n._kut = _jim
assert nav.oxirgi_javob - t0 >= 0.15, "ORALIQ kutish boshidan sanaldi"
print("[32] unga yozganlar navbat bilan javob oladi, navbat cheklangan; ORALIQ yuborishdan OK")

# ── 33) Reaksiya: matnsiz ham javob; slot band qoladi ────────────────
nav.oxirgi_javob = 0.0
model_javobi.update(matn=None, rk="🤣")
h = Hodisa("kecha mashinam o'g'irlandi, keyin topildi - mahalla mollaxonasida ekan")
yur(h)
assert reaksiyalar[-1] == (h.id, "🤣") and h.javob is None and nav.reaksiyalar == 1
assert nav.oxirgi_javob > 0, "reaksiya ham faollik — ORALIQ ishlaydi"
nav.oxirgi_javob = 0.0
model_javobi.update(matn="ha bro", rk="👍")
h = Hodisa("ertaga ko'rishamizmi")
yur(h)
assert reaksiyalar[-1] == (h.id, "👍") and h.javob, "reaksiya + matn ikkalasi"
model_javobi.update(matn="javob", rk="")
assert "reaksiyalar: 1" not in n.hisobot(nav, "x") and "reaksiyalar: 2" in n.hisobot(nav, "x")
print("[33] reaksiya: matn o'rniga yoki u bilan, hisobotda sanaladi OK")

# ── 34) Ikki qisqa xabar: birinchisi reply, belgi — oxirgisida ────────
assert n.bolaklar("ha bro\n\nkeyin gaplashamiz") == ["ha bro", "keyin gaplashamiz"]
assert n.bolaklar("bir") == ["bir"]
uzun = "a" * 250 + "\n\nb"
assert n.bolaklar(uzun) == [uzun], "uzun qism (kod, tushuntirish) — bo'linmaydi"
assert len(n.bolaklar("a\n\nb\n\nc\n\nd")) == 1, "4 ta xabar — spam, bittada"
n.BELGI_YOQIQ = True
nav.oxirgi_javob = 0.0
model_javobi.update(matn="e qo'ysang-chi 😂\n\nkechqurun boramiz")
h = Hodisa("futbolga kim boradi")
yur(h)
assert [t for t, _ in h.yuborilgan] == ["reply", "reply"], h.yuborilgan
assert "ᵃᵛᵗᵒʲᵃᵛᵒᵇ" not in h.yuborilgan[0][1] and h.yuborilgan[1][1].endswith("ᵃᵛᵗᵒʲᵃᵛᵒᵇ")
assert nav.javoblar[-1][2] == "e qo'ysang-chi 😂\n\nkechqurun boramiz"
model_javobi.update(matn="javob")
print("[34] ikki xabar: ikkalasi ham reply, belgi oxirida OK")

# ── 35) Reaksiya: egasining xabariga — o'sha odamni belgilab, mos javob ─
from telethon.tl import types as tt


class ReaksiyaKlient:
    def __init__(self):
        self.xabarlar, self.odamlar = {}, {}

    async def get_messages(self, chat, ids):
        return self.xabarlar.get(ids)

    async def get_entity(self, uid):
        return self.odamlar[uid]


def reaksiya(msg_id, uid, emoji, *, my=False, sana=None, chat=1001):
    return tt.UpdateMessageReactions(
        peer=tt.PeerChat(chat_id=chat), msg_id=msg_id,
        reactions=tt.MessageReactions(results=[], recent_reactions=[tt.MessagePeerReaction(
            peer_id=tt.PeerUser(user_id=uid), date=sana or datetime.now(timezone.utc),
            reaction=tt.ReactionEmoji(emoticon=emoji), my=my)]))


nav = yangi_navbat()
rk = ReaksiyaKlient()
n._CLIENT = rk
bizniki = Hodisa("python savollariga men javob beraman", out=True)
begonaniki = Hodisa("salom", ism="Vali")
rk.xabarlar = {bizniki.id: bizniki, begonaniki.id: begonaniki}
rk.odamlar = {4242: NS(first_name="Sardor", last_name=None, username=None, bot=False),
              4243: NS(first_name="Malika", last_name=None, username=None, bot=False),
              4244: NS(first_name="Bot", last_name=None, username=None, bot=True),
              777: NS(first_name="Jasur", last_name=None, username=None, bot=False)}


def rkyur(u):
    asyncio.run(n.reaksiya_keldi(u))

model_javobi.update(matn="sardor oynaga qarab bosdingmi 😂")
oldin = len(model)
rkyur(reaksiya(bizniki.id, 4242, "🤡"))
assert len(model) == oldin + 1 and model[-1]["menga"] is True
assert model[-1]["xabar"].startswith("[REAKSIYA] Sardor") and "🤡" in model[-1]["xabar"]
assert "python savollariga" in model[-1]["xabar"], "qaysi xabarga bosgani modelga aytilsin"
tur, matn = bizniki.yuborilgan[-1]
assert tur == "reply" and '<a href="tg://user?id=4242">sardor</a> oynaga' in matn, matn
assert nav.javoblar[-1][:2] == ("Sardor", "[🤡 reaksiya]") and nav.nishon is None
# Javobdan keyin o'sha odam darhol yana bossa — 10 daqiqa jim.
nav.oxirgi_javob = 0.0
rkyur(reaksiya(bizniki.id, 4242, "😭"))
assert len(model) == oldin + 1, "KRITIK: javobdan keyin 10 daqiqalik chegara qo'yilmadi"
# Telegram o'sha ro'yxatni qayta yuborsa — ikkinchi javob yo'q.
nav.oxirgi_javob, nav.reaksiya_javob = 0.0, {}
rkyur(reaksiya(bizniki.id, 4242, "🤡"))
assert len(model) == oldin + 1, "bir reaksiyaga ikki marta javob"
# O'sha odam 10 daqiqa ichida yana bossa — jim (bosib-olib spam yozdirolmaydi).
nav.oxirgi_javob = 0.0
nav.reaksiya_javob[4242] = time.time()
rkyur(reaksiya(bizniki.id, 4242, "❤"))
assert len(model) == oldin + 1, "KRITIK: reaksiya orqali spam"
# Model ismni yozmasa — boshida belgilanadi.
nav.oxirgi_javob = 0.0
model_javobi.update(matn="rahmat, sizga ham 😊")
rkyur(reaksiya(bizniki.id, 4243, "❤"))
assert bizniki.yuborilgan[-1][1].startswith('<a href="tg://user?id=4243">Malika</a>, rahmat')
assert len(model) == oldin + 2
model_javobi.update(matn="javob")
print("[35] reaksiya: odam belgilanadi, mos javob; takror va 10 daqiqalik spam — yo'q OK")

# ── 36) Reaksiya: begona xabar, egasining o'zi, eski, bot, boshqa guruh — jim ─
nav.reaksiya_javob = {}
oldin = len(model)
eski = datetime.fromtimestamp(nav.boshlandi - 60, timezone.utc)
for u in (reaksiya(begonaniki.id, 4242, "👍"), reaksiya(bizniki.id, 4242, "🔥", my=True),
          reaksiya(bizniki.id, 777, "🔥"), reaksiya(bizniki.id, 4242, "😁", sana=eski),
          reaksiya(bizniki.id, 4244, "👍"), reaksiya(bizniki.id, 4242, "👀", chat=1002)):
    nav.oxirgi_javob = 0.0
    rkyur(u)
assert len(model) == oldin, model[oldin:]
nav.oxirgi_javob = 0.0
nav.nishon = ("band",)
rkyur(reaksiya(bizniki.id, 4242, "🙏"))
assert len(model) == oldin, "boshqa xabarga javob tayyorlanayotganda — ikkinchisi yo'q"
nav.nishon = None
assert n._belgila_html("salom", 1, "<b>X") == '<a href="tg://user?id=1">&lt;b&gt;X</a>, salom'
assert n._belgila_html("a &amp; amp", 2, "Amp") == 'a &amp; <a href="tg://user?id=2">amp</a>', \
    "HTML belgisi (&amp;) ichidagi so'z havola bo'lmasin"
n._CLIENT = None
print("[36] reaksiya: faqat egasining xabari, o'zi/eski/bot/boshqa guruh/band — jim OK")

# ── 37) Reply: qaysi xabarga javobligi modelga beriladi ──────────────
nav.oxirgi_javob = 0.0
h = Hodisa("yo'q, sen noto'g'ri aytding", mentioned=True)
h.is_reply = True


async def _asl_xabar():
    return NS(raw_text="python eng\n zo'r til", out=True)
h.get_reply_message = _asl_xabar
yur(h)
assert model[-1]["reply_qilingan"] == "sen: python eng zo'r til", model[-1].get("reply_qilingan")
nav.oxirgi_javob = 0.0
yur(Hodisa("oddiy gap", mentioned=True))
assert model[-1]["reply_qilingan"] == ""
print("[37] reply qilingan xabar (kimniki, matni) modelga beriladi OK")

print("\nnavbatchi: barcha tekshiruvlar o'tdi (37/37).")
