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
    ochirildi = []

    async def ig_ochir(egasi, conn):
        ochirildi.append((egasi, conn))
    asl, asl2 = database.biznes_ulanish_yoz, database.biznes_ig_ochir
    database.biznes_ulanish_yoz, database.biznes_ig_ochir = ulanish_yoz, ig_ochir
    try:
        await ig.uz(EGASI)
    finally:
        database.biznes_ulanish_yoz, database.biznes_ig_ochir = asl, asl2
    check(23, "«Uzish» — faqat shu egasining Instagram ulanishi o'chadi va kaliti "
              "o'chiriladi (maxfiylik sahifasidagi va'da), Telegram'niki tegilmaydi",
          yozildi == [(CONN, EGASI, False)] and ochirildi == [(EGASI, CONN)])

asyncio.run(ekran())

# ── 19. web marshrutlari ro'yxatda ────────────────────────────────────
import web as w  # noqa: E402
yollar = {(r.method, r.resource.canonical) for r in w.build_app().router.routes()
          if r.resource is not None}
check(19, "panel serverida /ig/webhook (GET+POST) va /ig/ulash bor",
      {("GET", "/ig/webhook"), ("POST", "/ig/webhook"), ("GET", "/ig/ulash")} <= yollar)


# ══ 2-versiya: ishonchlilik, media, izohlar, tez savollar, HUMAN_AGENT ══
import handlers.biznes_media as bm  # noqa: E402


async def v2():
    from aiohttp import web

    # ── 24. Meta xato kodi IgXato'da qoladi (190 / 24 soat) ─────────────
    async def xato_qaytar(request):
        return web.json_response({"error": {"message": "Error validating access token",
                                            "code": 190, "error_subcode": 460}}, status=400)
    app = web.Application()
    app.router.add_get("/x", xato_qaytar)
    async with TestServer(app) as srv:
        try:
            await ASL_SOROV("GET", str(srv.make_url("/x")), token="MAXFIY")
            e = None
        except ig.IgXato as x:
            e = x
    check(24, "Meta xatosi: IgXato.kod=190, subkod=460, matnida kalit yo'q",
          e is not None and e.kod == 190 and e.subkod == 460 and "MAXFIY" not in str(e))

    # Umumiy soxta Instagram: har chaqiruv yoziladi, `javob` funksiyasi qaror qiladi.
    chaqiruv = []
    javob = {"f": None}

    async def soxta(usul, url, *, token=None, params=None, data=None, json_=None):
        chaqiruv.append((usul, url, params, json_))
        if javob["f"]:
            return await javob["f"](usul, url, params, json_)
        return {"message_id": f"mid-{len(chaqiruv)}"}
    ig._sorov = soxta

    yozildi, ochirildi, egasiga = [], [], []

    async def ulanish_yoz(conn, egasi, chat, yoqilgan, huquq):
        yozildi.append((conn, egasi, yoqilgan))
        database._biznes_kesh[conn]["yoqilgan"] = yoqilgan

    async def ig_ochir(egasi, conn):
        ochirildi.append((egasi, conn))

    async def egasiga_yoz(chat, matn, **kw):
        egasiga.append((chat, matn))
        return True
    asl = (database.biznes_ulanish_yoz, database.biznes_ig_ochir, b._egasiga)
    database.biznes_ulanish_yoz, database.biznes_ig_ochir, b._egasiga = (
        ulanish_yoz, ig_ochir, egasiga_yoz)
    try:
        # ── 25. O'lik kalit → ulanish o'chadi, kalit o'chadi, egasi BIR MARTA biladi
        async def olik(usul, url, params, jsn):
            raise ig.IgXato("Instagram rad etdi: Error validating access token", 190)
        javob["f"] = olik
        for _ in range(2):
            try:
                await ig.yubor(CONN, -IGSID, "salom")
            except ig.IgXato:
                pass
        check(25, "kalit o'lgan (190): ulanish o'chdi, kalit o'chirildi, egasiga bitta "
                  "«uzildi» xabari, keyingi yuborish APIga chiqmaydi",
              yozildi == [(CONN, EGASI, False)] and ochirildi == [(EGASI, CONN)]
              and len(egasiga) == 1 and "uzildi" in egasiga[0][1] and len(chaqiruv) == 1)
        database._biznes_kesh[CONN]["yoqilgan"] = True

        # ── 26. 24 soat: inson=True — HUMAN_AGENT bilan qayta; avtojavob — yo'q
        async def deraza(usul, url, params, jsn):
            if jsn and jsn.get("tag") == "HUMAN_AGENT":
                return {"message_id": "mid-tag"}
            raise ig.IgXato("Instagram rad etdi: outside of allowed window", 10, 2534022)
        javob["f"] = deraza
        chaqiruv.clear()
        x = await ig.yubor(CONN, -IGSID, "Buyurtmangiz tayyor", inson=True)
        tegli = [j for _, _, _, j in chaqiruv if j and j.get("tag") == "HUMAN_AGENT"]
        chaqiruv.clear()
        try:
            await ig.yubor(CONN, -IGSID, "Avtojavob")
            rad = False
        except ig.IgXato:
            rad = True
        check(26, "24 soat o'tgan: egasining matni HUMAN_AGENT bilan qayta ketadi; "
                  "avtojavob belgisiz rad etiladi (Meta qoidasi)",
              x is not None and len(tegli) == 1
              and tegli[0]["messaging_type"] == "MESSAGE_TAG"
              and rad and not any(j and j.get("tag") for _, _, _, j in chaqiruv))
        javob["f"] = None

        # ── 27-29. Postga izoh → Direct'ga yopiq javob ───────────────────
        izoh_d = {"object": "instagram", "entry": [{"id": HISOB, "changes": [
            {"field": "comments", "value": {"id": "c-1", "text": "narxi qancha?",
                                            "from": {"id": str(IGSID), "username": "ali_v"},
                                            "media": {"id": "post-1"}}}]}]}
        check(27, "izohlar(): comments maydoni olinadi; savol — ha, «🔥»/«zo'r» — yo'q, "
                  "«+» — ha (Instagram'da «narxini yozing»)",
              ig.izohlar(izoh_d) == [(HISOB, izoh_d["entry"][0]["changes"][0]["value"])]
              and ig.hodisalar(izoh_d) == []
              and ig.izoh_savolmi("narxi qancha?") and ig.izoh_savolmi("+")
              and ig.izoh_savolmi("Сколько стоит") and not ig.izoh_savolmi("🔥🔥")
              and not ig.izoh_savolmi("zo'r ekan"))

        kelgan = []

        async def ushla(xabar):
            kelgan.append((xabar, b.biznes_kimdan(xabar, database._biznes_kesh[CONN])))
        asl_bx = b.biznes_xabar
        b.biznes_xabar = ushla

        async def post(usul, url, params, jsn):
            if url.endswith("/post-1"):
                return {"caption": "Qizil ko'ylak, 42-48 razmer"}
            return {"message_id": f"mid-{len(chaqiruv)}"}
        javob["f"] = post
        try:
            await ig.izoh_keldi(HISOB, izoh_d["entry"][0]["changes"][0]["value"])
            n = len(kelgan)
            await ig.izoh_keldi(HISOB, {"id": "c-2", "text": "narxi?",
                                        "from": {"id": HISOB}, "media": {"id": "post-1"}})
            await ig.izoh_keldi(HISOB, {"id": "c-3", "text": "🔥",
                                        "from": {"id": "555"}, "media": {"id": "post-1"}})
            xabar, kim = kelgan[0]
            check(28, "savol-izoh mijoz xabari bo'lib keladi (post tavsifi bilan); egasining "
                      "o'z izohi va «🔥» — e'tiborsiz",
                  n == 1 and len(kelgan) == 1 and kim == "mijoz" and xabar.chat.id == -IGSID
                  and "postingizga izoh" in xabar.text and "Qizil ko'ylak" in xabar.text
                  and xabar.text.endswith("narxi qancha?"))

            chaqiruv.clear()
            await ig.yubor(CONN, -IGSID, "Narxi 150 ming")
            msg = [j for u, url, _, j in chaqiruv if url.endswith("/me/messages")]
            ochiq = [(url, p) for u, url, p, _ in chaqiruv if url.endswith("/c-1/replies")]
            chaqiruv.clear()
            await ig.yubor(CONN, -IGSID, "Yana savol bormi?")
            keyin = [j for u, url, _, j in chaqiruv if url.endswith("/me/messages")]
            check(29, "birinchi javob izoh orqali (comment_id) + ochiq «Direct'ga yozdik»; "
                      "keyingisi oddiy (recipient id)",
                  msg and msg[0]["recipient"] == {"comment_id": "c-1"}
                  and ochiq and ochiq[0][1]["message"] == ig.IZOH_JAVOBI
                  and keyin and keyin[0]["recipient"] == {"id": str(IGSID)})

            # ── 30. Yopiq javob echo'si boshqa id bilan qaytsa ham — bot ──
            ig._yuborilgan.append((None, "Yopiq javob"))
            await ig.xabar_keldi({"sender": {"id": HISOB}, "recipient": {"id": "424242"},
                                  "message": {"mid": "e2", "is_echo": True,
                                              "text": "Yopiq javob"}})
            check(30, "izoh javobining echo'si (boshqa id) — kim=bot, chat pauzaga tushmaydi",
                  kelgan[-1][1] == "bot")

            # ── 31. Tez savol tugmasi (postback) — oddiy xabar ────────────
            pb = {"object": "instagram", "entry": [{"id": HISOB, "messaging": [
                {"sender": {"id": str(IGSID)}, "recipient": {"id": HISOB},
                 "postback": {"mid": "pb-1", "title": "Narxlar qancha?", "payload": "tez:0"}}]}]}
            h = ig.hodisalar(pb)
            await ig.xabar_keldi(h[0])
            check(31, "«tez savol» bosilishi (postback) — matni shu savol bo'lgan mijoz xabari",
                  len(h) == 1 and kelgan[-1][1] == "mijoz"
                  and kelgan[-1][0].text == "Narxlar qancha?")

            # ── 32. Rasm, ovoz, reels, storis — ig_media bilan keladi ──────
            for m in ({"mid": "r1", "attachments": [{"type": "image", "payload": {"url": "https://cdn/r.jpg"}}]},
                      {"mid": "r2", "attachments": [{"type": "audio", "payload": {"url": "https://cdn/a.mp4"}}]},
                      {"mid": "r3", "attachments": [{"type": "ig_reel", "payload": {"url": "https://cdn/v"}}]},
                      {"mid": "r4", "text": "narxi?", "reply_to": {"story": {"url": "https://cdn/s.jpg", "id": "s1"}}}):
                await ig.xabar_keldi({"sender": {"id": str(IGSID)}, "recipient": {"id": HISOB},
                                      "message": m})
            rasm, ovoz, reels, storis = [x for x, _ in kelgan[-4:]]
        finally:
            b.biznes_xabar = asl_bx
            javob["f"] = None
        check(32, "rasm/ovoz/reels/storis: ig_media bilan, matnsizlarida text=None; "
                  "media_bormi — ha",
              rasm.text is None and rasm.ig_media["ilova"]["type"] == "image"
              and storis.text == "narxi?" and storis.ig_media["storis"]["id"] == "s1"
              and all(bm.media_bormi(x) for x in (rasm, ovoz, reels, storis)))

        yuklangan = []

        async def url_yukla(url, tur):
            yuklangan.append(url)
            return (b"\xff\xd8rasm", "image/jpeg") if tur == "image/" else (b"ovoz", "audio/mp4")

        async def tavsif(baytlar, mime="image/jpeg"):
            return "qizil ko'ylak, narx yorlig'i 150 000"

        async def stt(yol, is_pro=False):
            return "ertaga olib kelasizmi"
        asl_m = (bm._url_yukla, bm.rasm_tavsifi, bm.speech_to_text_smart)
        bm._url_yukla, bm.rasm_tavsifi, bm.speech_to_text_smart = url_yukla, tavsif, stt
        bm._sanoq.clear()
        try:
            t_rasm = await bm.media_matn(rasm, EGASI, True)
            t_ovoz = await bm.media_matn(ovoz, EGASI, True)
            t_reels = await bm.media_matn(reels, EGASI, True)
            t_storis = await bm.media_matn(storis, EGASI, True)
            n = len(yuklangan)
            t_kuzat = await bm.media_matn(rasm, EGASI, False)
            t_egasi = await bm.media_matn(rasm, EGASI, True, mijoz=False)
        finally:
            bm._url_yukla, bm.rasm_tavsifi, bm.speech_to_text_smart = asl_m
        check(33, "rasm → tavsif, ovoz → matn, reels → belgi, storisga javob → storis "
                  "tavsifi + savol; Kuzatuv va egasining rasmi — yuklanmaydi, faqat belgi",
              t_rasm == "[rasm: qizil ko'ylak, narx yorlig'i 150 000]"
              and t_ovoz == "[ovozli xabar] ertaga olib kelasizmi"
              and "reels" in t_reels and "ko'ra olmaysan" in t_reels
              and t_storis.startswith("[storisingizga javob — storisda: qizil ko'ylak")
              and t_storis.endswith("\nnarxi?")
              and n == 3 and t_kuzat == "[rasm]" and t_egasi == "[rasm]"
              and len(yuklangan) == 3)

        # ── 34. «yozmoqda» / «ko'rildi» ─────────────────────────────────
        chaqiruv.clear()
        await ig.harakat(CONN, -IGSID, "typing_on")
        ig._izohlar[-555] = ("c-9", __import__("time").time())
        await ig.harakat(CONN, -555, "typing_on")
        ig._izohlar.pop(-555, None)
        check(34, "typing_on — sender_action; izoh orqali kelgan chatda yuborilmaydi "
                  "(u hali Direct'da yozmagan)",
              len(chaqiruv) == 1 and chaqiruv[0][3] == {"recipient": {"id": str(IGSID)},
                                                         "sender_action": "typing_on"})

        # ── 35. Soatlik kalit/obuna ────────────────────────────────────
        async def egalar():
            return [(EGASI, True)]
        asl_eg = database.biznes_egalar
        database.biznes_egalar = egalar
        ig._obuna.clear()
        chaqiruv.clear()
        try:
            await ig.kalitlarni_yangila()
            await ig.kalitlarni_yangila()
        finally:
            database.biznes_egalar = asl_eg
        obuna = [p for u, url, p, _ in chaqiruv if url.endswith("/subscribed_apps")]
        check(35, "soatlik: eski ulanish yangi maydonlarga (izoh, postback) BIR MARTA "
                  "qayta obuna bo'ladi",
              len(obuna) == 1 and obuna[0]["subscribed_fields"] == ig.OBUNA
              and "comments" in ig.OBUNA and "messaging_postbacks" in ig.OBUNA)

        # ── 36. Tez savollar ──────────────────────────────────────────
        async def bilim(egasi):
            return ""
        asl_b = database.biznes_bilim_ol
        database.biznes_bilim_ol = bilim
        chaqiruv.clear()
        try:
            savollar = await ig.tez_savollar_qoy(EGASI)
        finally:
            database.biznes_bilim_ol = asl_b
        tana = chaqiruv[-1][3]
        cta = tana["ice_breakers"][0]["call_to_actions"]
        check(36, "Bilim bo'sh — standart savollar; Instagram'ga ≤4 ta, har biri ≤80 belgi",
              savollar == ig.STANDART_SAVOLLAR and chaqiruv[-1][1].endswith("/messenger_profile")
              and tana["platform"] == "instagram" and 1 <= len(cta) <= 4
              and all(len(c["question"]) <= 80 for c in cta))
    finally:
        database.biznes_ulanish_yoz, database.biznes_ig_ochir, b._egasiga = asl
        ig._sorov = ASL_SOROV

asyncio.run(v2())

check(37, "OAuth so'rovi izohlar ruxsatini ham oladi",
      "instagram_business_manage_comments" in ig.ulash_havolasi(EGASI))


# ── 38. Kirish logida query-satr yo'q (OAuth kodi) ─────────────────────
class _Log:
    def __init__(self):
        self.yozuv = []

    def info(self, fmt, *a):
        self.yozuv.append(fmt % a)


_l = _Log()
_so = type("S", (), {"remote": "1.2.3.4", "method": "GET", "path": "/ig/ulash",
                     "path_qs": "/ig/ulash?code=SIRLI&state=x"})()
w.KirishLogi(_l, "").log(_so, type("R", (), {"status": 200})(), 0.01)
check(38, "kirish logi: yo'l bor, ?code=… yo'q",
      "/ig/ulash" in _l.yozuv[0] and "SIRLI" not in _l.yozuv[0])

print("\ninstagram: barcha tekshiruvlar o'tdi.")
