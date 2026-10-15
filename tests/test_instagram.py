# -*- coding: utf-8 -*-
"""Instagram Direct — Business'ning ikkinchi kanali (`handlers/instagram.py`).

Bu test ushlaydigan JIM nosozliklar:

  ⛔️ Imzosiz webhook qabul qilinsa — kimdir "mijoz" nomidan xabar uydirib,
     egasining tokeni hisobiga avtojavob yozdirardi.
  ⛔️ OAuth `state` soxtalashtirilsa — begona Instagram boshqa egaga ulanardi.
  ⛔️ Botning o'z javobi (echo) "egasi yozdi" deb o'qilsa — avtomat har
     javobdan keyin chatni pauzaga qo'yib, jim qolardi.
  ⛔️ Instagram mijozi Telegram chati bilan to'qnashsa yoki javob
     Telegram'ga ketsa (`_mijozga` yo'naltirishi).
  ⛔️ Kalit (access token) xato matniga — demak logga — tushsa.
  ⛔️ 1000 BAYTdan uzun matn bitta xabar bo'lib ketsa (Instagram rad etadi).

Tarmoqsiz va bazasiz (faqat 127.0.0.1 ga bitta rad etiladigan ulanish).

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_instagram.py
"""
import asyncio
import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

import handlers.biznes as b               # noqa: E402
import handlers.instagram as ig           # noqa: E402
from db import database                   # noqa: E402

EGASI, IGSID, HISOB = 7001, 1234567890123456, "17841400000000001"
CONN = f"ig:{HISOB}"


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


ig.IG_APP_ID, ig.IG_APP_SECRET, ig.IG_VERIFY_TOKEN = "app", "sir", "tasdiq"
ig.WEB_APP_URL = "https://bot.example"

# ── 1-3. OAuth state ─────────────────────────────────────────────────
s = ig.holat_yasa(EGASI)
check(1, "state: o'z imzosi bilan egasi qaytadi", ig.holat_tekshir(s) == EGASI)
uid, muddat, imzo = s.split(".")
check(2, "state: boshqa egaga almashtirilgan id rad etiladi",
      ig.holat_tekshir(f"9999.{muddat}.{imzo}") is None
      and ig.holat_tekshir("buzuq") is None and ig.holat_tekshir("") is None)
check(3, "state: muddati o'tgani rad etiladi",
      ig.holat_tekshir(ig.holat_yasa(EGASI, hozir=1000)) is None)
check(3.1, "ulash havolasi: state va qaytish manzili ichida",
      "state=" in ig.ulash_havolasi(EGASI)
      and "bot.example%2Fig%2Fulash" in ig.ulash_havolasi(EGASI))

# ── 4. Webhook imzosi ────────────────────────────────────────────────
tana = b'{"object":"instagram"}'
togri = "sha256=" + hmac.new(b"sir", tana, hashlib.sha256).hexdigest()
check(4, "imzo: to'g'ri — ha; boshqa tana, bo'sh, prefikssiz — yo'q",
      ig.imzo_togrimi(tana, togri) and not ig.imzo_togrimi(tana + b" ", togri)
      and not ig.imzo_togrimi(tana, None) and not ig.imzo_togrimi(tana, togri[7:]))

# ── 5. Matn bo'laklari ────────────────────────────────────────────────
uzun = " ".join(["Ассалому алайкум, нарх 150 000 сўм 🙂"] * 80)
bol = ig.matn_bolaklari(uzun)
check(5, f"1000 baytdan uzun matn {len(bol)} bo'lakka, har biri ≤1000 bayt, so'z butun",
      len(bol) > 1 and all(len(x.encode()) <= 1000 for x in bol)
      and " ".join(bol).split() == uzun.split())
check(5.1, "qisqa matn — bitta bo'lak", ig.matn_bolaklari("salom") == ["salom"])

# ── 6. Hodisalar ─────────────────────────────────────────────────────
d = {"object": "instagram", "entry": [{"id": HISOB, "messaging": [
    {"sender": {"id": str(IGSID)}, "recipient": {"id": HISOB}, "message": {"mid": "m1", "text": "salom"}},
    {"sender": {"id": str(IGSID)}, "recipient": {"id": HISOB}, "read": {"mid": "m0"}},
    {"sender": {"id": str(IGSID)}, "recipient": {"id": HISOB}, "reaction": {"emoji": "❤"}},
]}]}
check(6, "faqat xabar hodisasi olinadi (o'qildi/reaksiya emas); begona object — hech narsa",
      len(ig.hodisalar(d)) == 1 and ig.hodisalar({"object": "page", "entry": d["entry"]}) == []
      and ig.hodisalar(None) == [])
check(6.1, "matnsiz rasm — modelga belgi",
      "rasm" in ig.ilova_matni([{"type": "image", "payload": {"url": "x"}}])
      and ig.ilova_matni([]) == "")

# ── Soxta baza va Instagram ───────────────────────────────────────────
database._biznes_kesh.clear()
database._biznes_kesh.update({
    "tg-1": {"owner_id": EGASI, "owner_chat": EGASI, "yoqilgan": True,
             "huquqlar": {"can_reply": True}, "rejim": "avtomat"},
    CONN: {"owner_id": EGASI, "owner_chat": EGASI, "yoqilgan": True,
           "huquqlar": dict(ig.HUQUQ), "rejim": "avtomat", "avto_belgi": True},
})


async def ig_ol(owner, conn):
    assert owner == EGASI and conn == CONN
    return {"username": "dokon", "token": "MAXFIY-KALIT",
            "token_vaqt": datetime.now(timezone.utc)}


database.biznes_ig_ol = ig_ol
sorovlar = []


async def sorov(usul, url, *, token=None, params=None, data=None, json_=None):
    sorovlar.append((usul, url, token, params, json_))
    if url.endswith("/me/messages"):
        return {"recipient_id": str(IGSID), "message_id": f"mid-{len(sorovlar)}"}
    return {"name": "Ali Valiyev", "username": "ali_v"}


ASL_SOROV = ig._sorov
ig._sorov = sorov

# ── 7-8. Ulanish tanlovi va chat id ──────────────────────────────────
check(7, "egasining ulanishi: Telegram afzal, instagram=True — faqat Instagram",
      database.biznes_egasi_ulanishi(EGASI)[0] == "tg-1"
      and database.biznes_egasi_ulanishi(EGASI, instagram=True)[0] == CONN
      and database.biznes_egasi_ulanishi(EGASI, instagram=False)[0] == "tg-1")
check(8, "Instagram chati manfiy — Telegram mijozi (musbat) bilan to'qnashmaydi",
      ig.chatmi(-IGSID) and not ig.chatmi(IGSID) and not ig.chatmi(True)
      and b._havola({"chat_id": -IGSID, "username": "ali_v"}) == "https://ig.me/m/ali_v"
      and b._havola({"chat_id": 5, "username": "ali"}) == "https://t.me/ali")


async def asosiy():
    # ── 9. _mijozga — ig: ulanishda Instagram'ga, belgi bilan ──────────
    sorovlar.clear()
    x = await b._mijozga(-IGSID, CONN, "Narxi 150 ming", belgi=True)
    usul, url, token, _, jsn = sorovlar[-1]
    check(9, "javob Instagram API'ga ketdi: IGSID ga, egasining kaliti, avto belgi bilan",
          url.endswith("/me/messages") and token == "MAXFIY-KALIT"
          and jsn["recipient"]["id"] == str(IGSID)
          and jsn["message"]["text"] == f"Narxi 150 ming\n{b.AVTO_BELGI}"
          and x.chat.id == -IGSID)

    # ── 10-12. Kiruvchi: mijoz / botning echo'si / egasining o'zi ──────
    kelgan = []

    async def ushla(xabar):
        kelgan.append((xabar, b.biznes_kimdan(xabar, database._biznes_kesh[CONN])))
    asl = b.biznes_xabar
    b.biznes_xabar = ushla
    try:
        await ig.xabar_keldi({"sender": {"id": str(IGSID)}, "recipient": {"id": HISOB},
                              "message": {"mid": "m1", "text": "Narxi qancha?"}})
        xabar, kim = kelgan[-1]
        check(10, "mijoz xabari: kim=mijoz, chat=-IGSID, ig: ulanish, ism Instagram'dan",
              kim == "mijoz" and xabar.chat.id == -IGSID
              and xabar.business_connection_id == CONN
              and xabar.from_user.full_name == "Ali Valiyev (Instagram)"
              and xabar.from_user.username == "ali_v" and xabar.text == "Narxi qancha?"
              and isinstance(xabar.message_id, int) and xabar.message_id > 0)

        await ig.xabar_keldi({"sender": {"id": HISOB}, "recipient": {"id": str(IGSID)},
                              "message": {"mid": "mid-e", "is_echo": True,
                                          "text": f"Narxi 150 ming\n{b.AVTO_BELGI}"}})
        check(11, "botning o'z javobi qaytib keldi (echo) — kim=bot, pauza yo'q",
              kelgan[-1][1] == "bot")

        await ig.xabar_keldi({"sender": {"id": HISOB}, "recipient": {"id": str(IGSID)},
                              "message": {"mid": "mid-o", "is_echo": True,
                                          "text": "Ertaga keling"}})
        check(12, "egasi Instagram ilovasidan o'zi yozdi — kim=egasi",
              kelgan[-1][1] == "egasi" and kelgan[-1][0].chat.id == -IGSID)

        n = len(kelgan)
        await ig.xabar_keldi({"sender": {"id": str(IGSID)}, "recipient": {"id": "999"},
                              "message": {"mid": "m2", "text": "salom"}})
        check(13, "ulanmagan Instagram hisobiga kelgan xabar — e'tiborsiz", len(kelgan) == n)
    finally:
        b.biznes_xabar = asl

    # ── 14. Kalit xato matniga tushmaydi ─────────────────────────────
    ig._sorov = ASL_SOROV
    try:
        await ig._sorov("GET", "http://127.0.0.1:9/x", params={"access_token": "MAXFIY"},
                        token="MAXFIY")
        tushdi = None
    except ig.IgXato as e:
        tushdi = e
    check(14, "ulanish xatosi: IgXato, matnida kalit yo'q, asl xato (URL bilan) zanjirda yo'q",
          tushdi is not None and "MAXFIY" not in str(tushdi)
          and tushdi.__cause__ is None and tushdi.__suppress_context__)

    # ── 15-17. Webhook endpointi ──────────────────────────────────────
    from aiohttp import web
    app = web.Application()
    ig.register(app)
    fonda = []
    asl_fonda = ig._fonda
    ig._fonda = lambda k: (fonda.append(k), k.close())
    try:
        async with TestClient(TestServer(app)) as c:
            r = await c.get("/ig/webhook", params={"hub.mode": "subscribe",
                                                   "hub.verify_token": "tasdiq",
                                                   "hub.challenge": "42"})
            r2 = await c.get("/ig/webhook", params={"hub.mode": "subscribe",
                                                    "hub.verify_token": "xato",
                                                    "hub.challenge": "42"})
            check(15, "obuna tasdig'i: to'g'ri token — challenge, noto'g'ri — 403",
                  r.status == 200 and await r.text() == "42" and r2.status == 403)
            tana = json.dumps(d).encode()
            r = await c.post("/ig/webhook", data=tana,
                             headers={"X-Hub-Signature-256": "sha256=" + "0" * 64})
            check(16, "imzosi noto'g'ri webhook — 403 va hech narsa ishlanmaydi",
                  r.status == 403 and not fonda)
            imzo = "sha256=" + hmac.new(b"sir", tana, hashlib.sha256).hexdigest()
            r = await c.post("/ig/webhook", data=tana, headers={"X-Hub-Signature-256": imzo})
            check(17, "imzoli webhook — 200 darhol, xabar fonda",
                  r.status == 200 and len(fonda) == 1)
            r = await c.get("/ig/ulash", params={"state": "buzuq", "code": "x"})
            check(18, "OAuth qaytishi: soxta state — 400, kod almashtirilmaydi",
                  r.status == 400 and not any("oauth" in s[1] for s in sorovlar))
            # Haqiqiy state, lekin Meta rad etdi — egasi Telegram'da SABABINI oladi.
            egasiga = []

            async def egasiga_yoz(chat, matn, **kw):
                egasiga.append((chat, matn))
                return True

            async def rad(usul, url, **kw):
                raise ig.IgXato("Instagram rad etdi: Insufficient developer role")
            asl_eg, asl_sr = b._egasiga, ig._sorov
            b._egasiga, ig._sorov = egasiga_yoz, rad
            try:
                r = await c.get("/ig/ulash", params={"state": ig.holat_yasa(EGASI), "code": "k"})
                sahifa = await r.text()
            finally:
                b._egasiga, ig._sorov = asl_eg, asl_sr
            check(18.1, "Meta rad etsa: sahifa 502 + Telegram'ga qaytish havolasi, egasiga "
                        "tushunarli sabab (texnik matn emas)",
                  r.status == 502 and "t.me/uzbot" in sahifa and len(egasiga) == 1
                  and egasiga[0][0] == EGASI and "Meta tekshiruvida" in egasiga[0][1])
    finally:
        ig._fonda = asl_fonda



class _SoxtaBot:
    async def me(self):
        from types import SimpleNamespace
        return SimpleNamespace(username="uzbot")


import core.loader as _loader  # noqa: E402
_loader.bot = _SoxtaBot()      # `_sahifa` bot nomini o'qiydi — tarmoqqa chiqmasin

asyncio.run(asosiy())

# ── 20-23. «📸 Instagram» ekrani (oddiy foydalanuvchi uchun) ──────────
yoz = ig.yoriqnoma(None, False)
check(20, "yo'riqnoma: Professional, xabarlarga ruxsat, kirish, Ruxsat — token/ID so'ramaydi",
      all(k in yoz for k in ("Professional", "Allow access to messages", "Ruxsat berish",
                              "xabar beraman"))
      and not any(k in yoz.lower() for k in ("token", "app id", "kalit")))
check(21, "Meta xatolari tushunarli sababga aylanadi",
      "Meta tekshiruvida" in ig.sabab("Insufficient Developer Role")
      and "Professional" in ig.sabab("The user is not an Instagram Business account professional")
      and "eskirgan" in ig.sabab("This authorization code has been used")
      and ig.sabab("boshqa") .startswith("Instagram rad etdi"))


async def ekran():
    database._biznes_kesh[CONN]["yoqilgan"] = False
    m1, kb1 = await b.instagram_ekrani(EGASI)
    database._biznes_kesh[CONN]["yoqilgan"] = True
    m2, kb2 = await b.instagram_ekrani(EGASI)
    t1 = [t for q in kb1.inline_keyboard for t in q]
    t2 = [t for q in kb2.inline_keyboard for t in q]
    check(22, "ulanmagan: yo'riqnoma + imzoli kirish havolasi, uzish YO'Q; ulangan: @nom + uzish",
          "Oldin tekshiring" in m1 and any(t.url and "state=" in t.url for t in t1)
          and not any(t.callback_data == "bz:igx" for t in t1)
          and "@dokon" in m2 and any(t.callback_data == "bz:igx" for t in t2))
    yozildi = []

    async def ulanish_yoz(conn, egasi, chat, yoqilgan, huquq):
        yozildi.append((conn, egasi, yoqilgan))
    asl = database.biznes_ulanish_yoz
    database.biznes_ulanish_yoz = ulanish_yoz
    try:
        await ig.uz(EGASI)
    finally:
        database.biznes_ulanish_yoz = asl
    check(23, "«Uzish» — faqat shu egasining Instagram ulanishi o'chadi (Telegram'niki emas)",
          yozildi == [(CONN, EGASI, False)])

asyncio.run(ekran())

# ── 19. web marshrutlari ro'yxatda ────────────────────────────────────
import web as w  # noqa: E402
yollar = {(r.method, r.resource.canonical) for r in w.build_app().router.routes()
          if r.resource is not None}
check(19, "panel serverida /ig/webhook (GET+POST) va /ig/ulash bor",
      {("GET", "/ig/webhook"), ("POST", "/ig/webhook"), ("GET", "/ig/ulash")} <= yollar)

print("\ninstagram: barcha tekshiruvlar o'tdi.")
