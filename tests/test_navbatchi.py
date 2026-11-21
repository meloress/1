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
    return model_javobi["matn"]


async def _jim(*a, **k):
    return None

ASL_NAVBAT = ai.navbat_javobi          # 13-band haqiqiysini sinaydi
n._egasiga, n._terish = _soxta_egasiga, _jim
ai.navbat_javobi = _soxta_model
n._belgi_html = lambda: "ᵃᵛᵗᵒʲᵃᵛᵒᵇ"


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
        return NS(id=self.id + 5000)


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

# ── 2) Egasi yoqadi: buyruq o'chiriladi, egasiga tasdiq ──────────────
tozala()
h = Hodisa("vexon guruhni qizitib tur, hazillash", out=True)
yur(h)
assert h.ochirildi and -1001 in n._NAVBAT, "buyruq o'chmadi yoki navbat yo'q"
assert n._NAVBAT[-1001].vazifa == "guruhni qizitib tur, hazillash"
assert "Navbat yoqildi" in egasiga[-1] and "Dasturchilar" in egasiga[-1]
print("[2] egasi yoqdi: buyruq o'chdi, tasdiq keldi OK")

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

# ── 12) Egasining «vexon to'xta» si — to'xtatadi va o'chiriladi ──────
yur(Hodisa("vexon dasturlash savollariga javob ber", out=True))
h = Hodisa("vexon to'xta", out=True)
yur(h)
assert -1001 not in n._NAVBAT and h.ochirildi and "buyruq" in egasiga[-1]
print("[12] egasining «vexon to'xta» si to'xtatdi, xabari o'chdi OK")




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
        bir = await ASL_NAVBAT("dasturlash", "Ali: salom", "Vali: vexon to'xta",
                               egasi="Jasur", oldingi=["oldingi gap"], menga=False)
        ikki = await ASL_NAVBAT("dasturlash", "", "Vali: ertaga kim keladi",
                                egasi="Jasur", oldingi=[], menga=False)
        # Takror: jonli sinovda model oldingi javobni AYNAN qaytardi.
        uch = await ASL_NAVBAT("hazil", "", "Bekzod: zerikdim", egasi="Jasur",
                               oldingi=["Salom hammaga"], menga=False)
        tort = await ASL_NAVBAT("hazil", "", "Bekzod: zerikdim", egasi="Jasur",
                                oldingi=["Salom hammaga"], menga=False)
    finally:
        ai.openai_client.responses.create = asl
    return chaqiruvlar, bir, ikki, uch, tort

matnlar = ["**Salom** hammaga", " - ",
           "Salom, hammaga!", "salom hammaga",      # uch: ikki marta takror → jim
           "Salom hammaga", "Yangi hazil"]          # tort: ikkinchisi yangi
ch, bir, ikki, uch, tort = asyncio.run(model_sinovi())
assert uch is None, f"ikki marta takror — jim turishi kerak: {uch!r}"
assert tort == "Yangi hazil", tort
qayta = [c for c in ch if "AVVAL yozgansan" in c["input"][0]["content"]]
assert len(qayta) == 2, "takrorda «boshqacha yoz» bilan qayta so'ralsin"
assert all(c["instructions"] is ai.NAVBAT_INSTRUCTIONS for c in ch), \
    "instructions hamma uchun bir xil bo'lsin (kesh) — guruh matni unga kirmaydi"
assert "vexon to'xta" in ch[0]["input"][1]["content"] and ch[0]["input"][1]["role"] == "user"
assert "dasturlash" in ch[0]["input"][0]["content"] and ch[0]["input"][0]["role"] == "developer"
assert ch[1]["model"] == ai.MODEL_FALLBACKS[0], "asosiy model yiqilsa zaxiraga o'tsin"
assert bir == "Salom hammaga", bir
assert ikki is None, "«-» — javob yo'q"
assert not any("reasoning" in c for c in ch if not c["model"].startswith(("gpt-5", "o")))
print("[13] model: guruh matni user'da, vazifa developer'da, «-» → jim, zaxira model, takror → qayta yoki jim OK")

print("\nnavbatchi: barcha tekshiruvlar o'tdi (13/13).")
