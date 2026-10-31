# -*- coding: utf-8 -*-
"""Karta orqali Pro to'lovi (2026-10-30) — chek, superadmin tasdig'i.

  ⛔️ chek rasmi o'zi Pro BERMAYDI — faqat superadmin tugmasi (soxta skrinshot);
  ⛔️ superadmin bo'lmagan odam «✅ Tasdiqlash» callback'ini yasab yubora olmaydi;
  ⛔️ chek GPT'ga «rasm tahlili» bo'lib ketmaydi (handler AI'dan OLDIN);
  ⛔️ eskirgan chek holatida yuborilgan rasm YUTILMAYDI — AI'ga o'tadi;
  ⛔️ karta narxlari Stars nisbatida — chegirma yorliqlari yolg'on emas;
  ⛔️ Stars tugmalari karta bilan birga TURADI (Telegram qoidasi).

Tarmoqsiz va bazasiz (`database.*` hammasi soxta).

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_karta_tolov.py
"""
import asyncio
import os
import sys
import time
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram.dispatcher.event.bases import SkipHandler  # noqa: E402

import core.config as c                  # noqa: E402
import handlers.pro as p                 # noqa: E402
from db import database                  # noqa: E402
from tests._manba import kod             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


# ── 1. Narxlar: Stars nisbati, yorliqlar haqiqiy ──────────────────
def chegirma(narx: dict, kun: int) -> int:
    return round((1 - (narx[kun] / kun) / (narx[30] / 30)) * 100)


yorliq = {d: b for d, _, _, b in c.PRO_PLANS}
check(1, "karta narxlari: 1 oy 25 000; har tarif yorlig'i so'mdagi kunlik narxdan chiqadi",
      c.KARTA_NARX[30] == 25_000 and set(c.KARTA_NARX) == set(c.PRO_PLANS_BY_DAYS)
      and all((f"−{chegirma(c.KARTA_NARX, d)}%" if yorliq[d] else "") == yorliq[d]
              for d in c.KARTA_NARX))

# ── 2-3. Matnlar ──────────────────────────────────────────────────
m = p.karta_sorov_matni(30, 25_047, "8600123412341234", "ALI <VALIYEV>")
check(2, "so'rov matni: karta 4 talab, egasi (escape), aniq summa, qo'shimcha, 24 soat",
      "8600 1234 1234 1234" in m and "ALI &lt;VALIYEV&gt;" in m and "25 047" in m
      and "Oxiridagi 47 so'm" in m and "24 soat" in m)
kb = p._karta_sorov_kb(7, 25_047, "8600123412341234")
nusxa = [t.copy_text.text for q in kb.inline_keyboard for t in q if t.copy_text]
check(3, "so'rov tugmalari: karta va summa NUSXALANADI (bo'shliqsiz), chek, bekor",
      nusxa == ["8600123412341234", "25047"]
      and [t.callback_data for q in kb.inline_keyboard for t in q if t.callback_data]
      == ["pro:chek:7", "pro:kb:7"])

# ── 4. Pro ekrani: karta Stars bilan BIRGA ────────────────────────
async def profil(uid):
    return {"plan_type": "free", "premium_until": None}
database.get_full_user_profile = profil


def tugmalar(kb):
    return [t.callback_data for q in kb.inline_keyboard for t in q]


ADMIN_URL = f"https://t.me/{c.ADMIN_USERNAME}"


def adminli(kb):
    return kb is not None and any(t.url == ADMIN_URL for q in kb.inline_keyboard for t in q)


KARTA = {"v": None}


async def karta_ol():
    if KARTA["v"] == "xato":
        raise RuntimeError("baza yo'q")
    return KARTA["v"]
database.karta_ol = karta_ol

_, bez = asyncio.run(p._render_pro_screen(1))
KARTA["v"] = "xato"
_, yiqildi = asyncio.run(p._render_pro_screen(1))
KARTA["v"] = ("8600123412341234", "ALI VALIYEV")
matn, bilan = asyncio.run(p._render_pro_screen(1))
check(4, "karta sozlanmagan (yoki baza xatosi — /pro yiqilmaydi) — Stars muddatlari darrov; "
         "sozlangan — avval usul: «Stars orqali» | «Karta orqali»",
      "pro:kartalar" not in tugmalar(bez) and "pro:kartalar" not in tugmalar(yiqildi)
      and all(f"pro:buy:{d}" in tugmalar(bez) for d in c.PRO_PLANS_BY_DAYS)
      and tugmalar(bilan)[:2] == ["pro:stars", "pro:kartalar"]
      and not any(t.startswith("pro:buy:") for t in tugmalar(bilan))
      and "karta orqali" in matn)


class Bos:
    """Usul tugmasi bosildi — Pro matni qoladi, faqat tugmalar almashadi."""
    def __init__(self, data):
        self.data, self.from_user, self.kb = data, NS(id=1), None
        self.message = NS(edit_reply_markup=self._erm)

    async def _erm(self, reply_markup=None):
        self.kb = reply_markup

    async def answer(self, *a, **k):
        pass


stars, kartalar = Bos("pro:stars"), Bos("pro:kartalar")
asyncio.run(p.handle_pro_callback(stars, None))
asyncio.run(p._karta_callback(kartalar, None, ["pro", "kartalar"]))
orqaga = Bos("pro:usul")
asyncio.run(p.handle_pro_callback(orqaga, None))
check("4a", "Stars → muddatlar + Orqaga; Karta → so'mli muddatlar + Orqaga; Orqaga → yana usul",
      all(f"pro:buy:{d}" in tugmalar(stars.kb) for d in c.PRO_PLANS_BY_DAYS)
      and all(f"pro:karta:{d}" in tugmalar(kartalar.kb) for d in c.PRO_PLANS_BY_DAYS)
      and tugmalar(stars.kb)[-1] == tugmalar(kartalar.kb)[-1] == "pro:usul"
      and tugmalar(orqaga.kb)[:2] == ["pro:stars", "pro:kartalar"])

# ── 5-7. Chek qabul qilish ────────────────────────────────────────
q = []


class Holat:
    def __init__(self, data=None, h="KartaStates:chek"):
        self.data, self.h = dict(data or {}), h

    async def get_data(self):
        return self.data

    async def get_state(self):
        return self.h

    async def set_state(self, h):
        self.h = getattr(h, "state", h)

    async def update_data(self, **k):
        self.data.update(k)

    async def clear(self):
        self.h, self.data = None, {}


class Xabar:
    def __init__(self, uid=55, photo=True):
        self.from_user = NS(id=uid, full_name="Ali", username="ali")
        self.photo = [NS(file_id="kichik", file_unique_id="u0"),
                      NS(file_id="katta", file_unique_id="u1")] if photo else None
        self.document = None if photo else NS(file_id="pdf", file_unique_id="u2")

    async def answer(self, matn, **k):
        q.append(("javob", matn))


async def chek_yoz(lid, uid, file_id, turi, unique):
    q.append(("chek_yoz", lid, uid, file_id, turi, unique))
    return {"id": lid, "user_id": uid, "days": 30, "summa": 25_047, "karta": "8600123412341234",
            "chek_file": file_id, "chek_turi": turi, "takror": 3}


async def superadmin():
    return 900


class Bot:
    async def send_photo(self, chat, fayl, caption=None, parse_mode=None, reply_markup=None):
        q.append(("admin_rasm", chat, fayl, caption, tugmalar(reply_markup)))

    async def send_document(self, chat, fayl, caption=None, parse_mode=None, reply_markup=None):
        q.append(("admin_fayl", chat, fayl))

    async def send_message(self, chat, matn, parse_mode=None, reply_markup=None):
        q.append(("send", chat, matn, reply_markup))


database.karta_chek_yoz = chek_yoz
database.get_superadmin_id = superadmin
p.bot = Bot()

h = Holat({"karta_id": 7, "karta_t": time.time()})
asyncio.run(p.process_karta_chek(Xabar(), h))
rasm = next(x for x in q if x[0] == "admin_rasm")
check(5, "chek: eng katta rasm yoziladi, holat tugaydi, egasiga «qabul qilindi» (Pro EMAS), "
         "superadminga rasm + summa + takror ogohlantirishi + 4 qaror tugmasi",
      ("chek_yoz", 7, 55, "katta", "photo", "u1") in q and h.h is None
      and any(x[0] == "javob" and "Chek qabul qilindi" in x[1] for x in q)
      and rasm[1] == 900 and "25 047" in rasm[3] and "#3" in rasm[3]
      and rasm[4] == ["pro:kt:7", "pro:kr:7:kelmadi", "pro:kr:7:summa", "pro:kr:7:chek"])

q.clear()
eski = Holat({"karta_id": 7, "karta_t": time.time() - p.KARTA_CHEK_OYNA - 1})
try:
    asyncio.run(p.process_karta_chek(Xabar(), eski))
    otdi = False
except SkipHandler:
    otdi = True
check(6, "eskirgan holat: rasm YUTILMAYDI (SkipHandler → AI), holat tozalanadi, bazaga tegilmaydi",
      otdi and eski.h is None and not q)

q.clear()
asyncio.run(p.process_karta_chek(Xabar(photo=False), Holat({"karta_id": 8, "karta_t": time.time()})))
check(7, "PDF chek — hujjat sifatida superadminga", any(x[0] == "admin_fayl" for x in q))


# ── 8-11. Superadmin qarori ───────────────────────────────────────
class So:
    def __init__(self, data, uid=900):
        self.data, self.from_user = data, NS(id=uid)
        self.message = NS(html_text="💳 <b>Karta to'lovi #7</b>",
                          edit_caption=self._ec, edit_reply_markup=self._erm,
                          answer=self._a, edit_text=self._et)
        self.alert = None

    async def _ec(self, caption=None, parse_mode=None, reply_markup=None):
        q.append(("caption", caption))

    async def _erm(self, reply_markup=None):
        pass

    async def _a(self, *a, **k):
        q.append(("msg", a))

    async def _et(self, *a, **k):
        q.append(("et", a))

    async def answer(self, *a, **k):
        self.alert = a


holat = {"tasdiq": [{"user_id": 55, "days": 30, "summa": 25_047}]}


async def is_super(uid):
    return uid == 900


async def tasdiqla(lid, uid):
    q.append(("tasdiqla", lid, uid))
    return holat["tasdiq"].pop() if holat["tasdiq"] else None


async def rad(lid, uid, sabab):
    q.append(("rad", lid, sabab))
    return {"user_id": 55, "days": 30, "summa": 25_047}


async def audit(admin, amal, target, izoh):
    q.append(("audit", amal, target, izoh))


async def sync(uid, is_pro):
    q.append(("menyu", uid, is_pro))


database.is_superadmin = is_super
database.karta_tasdiqla = tasdiqla
database.karta_rad = rad
database.log_admin_action = audit
p.menu_module.sync_commands = sync

q.clear()
begona = So("pro:kt:7", uid=55)
asyncio.run(p.handle_pro_callback(begona, Holat()))
check(8, "superadmin EMAS — yasalgan «pro:kt» rad, bazaga tegilmaydi",
      not any(x[0] in ("tasdiqla", "rad") for x in q) and "bosh admin" in begona.alert[0])

q.clear()
asyncio.run(p.handle_pro_callback(So("pro:kt:7"), Holat()))
send = [x for x in q if x[0] == "send"]
check(9, "tasdiq: Pro bazada, menyu, audit «karta_tasdiq», egasiga «faollashdi», chekda belgi",
      ("tasdiqla", 7, 900) in q and ("menyu", 55, True) in q
      and any(x[0] == "audit" and x[1] == "karta_tasdiq" and x[2] == 55 for x in q)
      and send and send[0][1] == 55 and "Pro faollashdi" in send[0][2]
      and any(x[0] == "caption" and "TASDIQLANDI" in x[1] for x in q))

q.clear()
ikkinchi = So("pro:kt:7")
asyncio.run(p.handle_pro_callback(ikkinchi, Holat()))
check(10, "ikkinchi bosish (yoki ikkinchi qurilma) — «allaqachon hal qilingan», egasiga hech narsa",
      "allaqachon" in ikkinchi.alert[0] and not any(x[0] in ("send", "menyu", "audit") for x in q))

q.clear()
asyncio.run(p.handle_pro_callback(So("pro:kr:7:summa"), Holat()))
send = [x for x in q if x[0] == "send"]
check(11, "rad: sabab egasiga, «qayta yuborish» + «Admin bilan bog'lanish», audit «karta_rad», "
          "Pro/menyu YO'Q",
      ("rad", 7, p._RAD_SABAB["summa"]) in q and not any(x[0] == "menyu" for x in q)
      and any(x[0] == "audit" and x[1] == "karta_rad" for x in q)
      and send and p._RAD_SABAB["summa"] in send[0][2]
      and tugmalar(send[0][3]) == ["pro:chek:7", None] and adminli(send[0][3]))

q.clear()
asyncio.run(p.handle_pro_callback(So("pro:kr:7:pul_ber"), Holat()))
check(12, "noma'lum rad sababi (yasalgan callback) — bazaga tegilmaydi", not any(x[0] == "rad" for x in q))


# ── 13. «Karta» callback: narx serverdan, mijozdan emas ───────────
async def yarat(uid, kun, narx, karta):
    q.append(("yarat", uid, kun, narx, karta))
    return {"id": 9, "summa": narx + 47}


async def ban_yoq(uid):
    return False

database.karta_sorov_yarat = yarat
database.is_banned = ban_yoq
q.clear()
h = Holat(h=None)
asyncio.run(p.handle_pro_callback(So("pro:karta:180", uid=55), h))
yomon = So("pro:karta:7", uid=55)
asyncio.run(p.handle_pro_callback(yomon, Holat(h=None)))
check(13, "karta so'rovi: narx KARTA_NARX dan, chek kutish holati yoqiladi; katalogda yo'q kun — rad",
      ("yarat", 55, 180, 125_000, "8600123412341234") in q and h.h == "KartaStates:chek"
      and h.data["karta_id"] == 9 and sum(1 for x in q if x[0] == "yarat") == 1
      and "mavjud emas" in yomon.alert[0])

# ── 14. Ro'yxatga olish tartibi va audit yorliqlari ───────────────
main = kod(os.path.join(ROOT, "main.py"))
i = main.index("pro_module.process_karta_chek")
check(14, "chek handleri AI handlerlaridan va ta'til darvozasidan OLDIN, faqat rasm/fayl; "
          "audit amallari AUDIT_ACTIONS da",
      i < main.index("register(handle_photo") and i < main.index("register(handle_document")
      and i < main.index("handle_maintenance_notice, F.text")
      and "F.photo | F.document" in main[i:i + 200]
      and {"karta_tasdiq", "karta_rad"} <= set(c.AUDIT_ACTIONS))


# ── 15. aiogram: SkipHandler haqiqatan keyingi routerga o'tkazadimi ──
async def jonli():
    from aiogram import Bot as ABot, Dispatcher, F, Router
    from aiogram.types import Update
    dp, r, tushdi = Dispatcher(), Router(), []

    async def birinchi(m):
        raise SkipHandler()

    async def ai(m):
        tushdi.append("ai")
    dp.message.register(birinchi, F.photo)
    r.message.register(ai, F.photo)
    dp.include_router(r)
    u = Update.model_validate({"update_id": 1, "message": {
        "message_id": 1, "date": 0, "chat": {"id": 5, "type": "private"},
        "from": {"id": 5, "is_bot": False, "first_name": "A"},
        "photo": [{"file_id": "x", "file_unique_id": "y", "width": 1, "height": 1}]}})
    await dp.feed_update(ABot("1:" + "a" * 35), u)
    return tushdi

check(15, "aiogram: dp.message dagi SkipHandler rasmni ichki routerga (AI) o'tkazadi",
      asyncio.run(jonli()) == ["ai"])

# ── 16. Panel kiritgan karta — ishonchsiz kirish ──────────────────
ck = database.clean_karta
check(16, "clean_karta: bo'shliq/tire bilan 16 raqam o'tadi; qisqa, harfli, ismsiz — rad; "
          "ikkalasi bo'sh — o'chirish",
      ck("8600 1234-5678 9012", " ali  valiyev ") == ("8600123456789012", "ali valiyev", "")
      and ck("", "") == (None, None, "")
      and all(ck(r, e)[2] for r, e in [("1234", "Ali"), ("8600 1234 5678 901x", "Ali"),
                                       ("8600123456789012", ""), ("8600123456789012", "12345"),
                                       ("", "Ali")]))


# ── 17-19. Panel: faqat superadmin yozadi, xabar va audit ─────────
async def panel():
    from aiohttp.test_utils import TestClient, TestServer
    import web
    from web import api, auth
    import core.loader
    SUPER, ADMIN = 641382901, 778120334
    yozildi, audit_q, tg = [], [], []

    class TgBot:
        async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None):
            tg.append((chat_id, text))
    core.loader.bot = TgBot()
    db = api.database_module

    async def is_superadmin(uid):
        return uid == SUPER

    async def karta_yoz(r, e):
        yozildi.append((r, e))
        KARTA["v"] = (r, e) if r else None

    async def log_admin_action(admin_id, action, target=None, details=None):
        audit_q.append((admin_id, action, details))

    async def ha(uid):
        return True
    db.is_superadmin, db.karta_yoz, db.log_admin_action = is_superadmin, karta_yoz, log_admin_action
    web.huquq_bormi = auth.huquq_bormi = ha
    kuki = {u: {"Cookie": f"{auth.COOKIE_NAME}={auth.sessiya_yasa(u)}"} for u in (SUPER, ADMIN)}
    natija = {}
    async with TestClient(TestServer(web.build_app())) as cl:
        natija["kukisiz"] = (await cl.get("/api/karta")).status, (await cl.post("/api/karta", json={})).status
        KARTA["v"] = ("8600123412341234", "ALI VALIYEV")
        natija["admin_get"] = await (await cl.get("/api/karta", headers=kuki[ADMIN])).json()
        r = await cl.post("/api/karta", headers=kuki[ADMIN],
                          json={"raqam": "9860 0000 0000 0001", "egasi": "BEGONA"})
        natija["admin_post"] = r.status, list(yozildi)
        r = await cl.post("/api/karta", headers=kuki[SUPER], json={"raqam": "12", "egasi": "Ali"})
        natija["yomon"] = r.status, list(yozildi)
        r = await cl.post("/api/karta", headers=kuki[SUPER],
                          json={"raqam": "9860 1111 2222 3333", "egasi": "Ali Valiyev"})
        natija["super_post"] = r.status, list(yozildi), list(audit_q), list(tg)
        natija["super_get"] = await (await cl.get("/api/karta", headers=kuki[SUPER])).json()
        r = await cl.post("/api/karta", headers=kuki[SUPER], json={"raqam": "", "egasi": ""})
        natija["ochir"] = r.status, yozildi[-1], KARTA["v"]
    return natija, SUPER

n, SUPER = asyncio.run(panel())
check(17, "panel: cookie'siz 401; oddiy admin karta KO'RADI, lekin yozolmaydi (403, bazaga tegilmaydi)",
      n["kukisiz"] == (401, 401) and n["admin_get"]["raqam"] == "8600123412341234"
      and n["admin_get"]["ozgartira_oladi"] is False and len(n["admin_get"]["narx"]) == 4
      and n["admin_post"] == (403, []))
st, yoz, aud, tg = n["super_post"]
check(18, "superadmin: noto'g'ri raqam — 400, yozilmaydi; to'g'risi — tozalab yoziladi, auditda "
          "faqat oxirgi 4 raqam, superadminga Telegram'da xabar (sessiya o'g'irlansa ham biladi)",
      n["yomon"] == (400, []) and st == 200 and yoz == [("9860111122223333", "Ali Valiyev")]
      and aud == [(SUPER, "karta_sozlama", "···· 3333")]
      and "9860111122223333" not in str(aud)
      and len(tg) == 1 and tg[0][0] == SUPER and "3333" in tg[0][1]
      and n["super_get"]["ozgartira_oladi"] is True)
check(19, "bo'sh raqam va ism — karta to'lovi o'chadi (bazada NULL, /pro da tugma yo'qoladi)",
      n["ochir"] == (200, (None, None), None))

# ── 20. «Admin bilan bog'lanish» — to'lov muammosi joylarida ─────
yuborildi = []


class Javob:
    async def answer(self, matn, parse_mode=None, reply_markup=None):
        yuborildi.append((matn, reply_markup))


asyncio.run(p._safe_send(Javob(), "✅ To'lovingiz qabul qilindi."))
check(20, "admin tugmasi t.me/<ADMIN_USERNAME>: to'lov muammosi xabari, karta so'rovi, blok matni",
      adminli(yuborildi[0][1]) and "adminga yozing" in yuborildi[0][0]
      and adminli(p._karta_sorov_kb(7, 25_047, "8600123412341234"))
      and adminli(p.admin_kb()) and "adminga yozing" in p.BAN_MATNI)

# ── 21. Deploy FSM'ni o'chirdi — chek bazadagi so'rovdan tanilsin ──
p.bot = Bot()
kutilmoqda = {"v": 7}


async def kutilmoqda_ol(uid, oyna):
    q.append(("kutilmoqda", uid, oyna))
    if kutilmoqda["v"] == "xato":
        raise RuntimeError("baza yo'q")
    return kutilmoqda["v"]
database.karta_chek_kutilmoqda = kutilmoqda_ol


def bazadan(holat):
    try:
        asyncio.run(p.process_karta_chek_bazadan(Xabar(), holat))
        return False
    except SkipHandler:
        return True


q.clear()
bosh = Holat(h=None)
otkazdi = bazadan(bosh)
tanildi = (("chek_yoz", 7, 55, "katta", "photo", "u1") in q
           and any(x[0] == "admin_rasm" for x in q) and bosh.h is None and not otkazdi)
q.clear()
kutilmoqda["v"] = None
yoq = bazadan(Holat(h=None)) and not any(x[0] == "chek_yoz" for x in q)
kutilmoqda["v"] = "xato"
xato = bazadan(Holat(h=None))
j = main.index("pro_module.process_karta_chek_bazadan")
check(21, "FSM yo'q, bazada kutayotgan so'rov — chek superadminga; so'rov yo'q yoki baza xatosi — "
          "rasm AI'ga (SkipHandler); handler FSM'li chekdan keyin, AI'dan oldin, faqat shaxsiy chat",
      tanildi and yoq and xato
      and i < j < main.index("register(handle_photo") and j < main.index("register(handle_document")
      and j < main.index("handle_maintenance_notice, F.text")
      and 'F.chat.type == "private"' in main[j:j + 200])

print("\nHammasi o'tdi: 21/21")
