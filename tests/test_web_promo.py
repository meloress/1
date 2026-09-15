"""Web paneldagi Promo, Bepul Pro, Referal va Tarqatma tekshiruvi.
Ishga tushirish: python tests/test_web_promo.py

Tarmoq, baza va Telegram kerak emas.

Bu ekranlar BEPUL Pro tarqatadi — ya'ni xatosi to'g'ridan-to'g'ri pul.
Shuning uchun tekshiruvlarning ko'pi chegaralar haqida:

  * promokod va referal shartining qoidalari IKKI joyda yozilmasin
    (`clean_promo_spec` / `clean_referral_config` — Telegram ekrani ham
    aynan shularni chaqiradi);
  * sovg'a `extend=True` bilan berilsin — 20 kuni qolgan odam 30 kunlik
    sovg'adan keyin 50 kun olishi kerak, 30 emas;
  * xabar yetmagani «berilmadi» degani EMAS — admin ikkinchi marta
    bermasligi uchun bu ikkisi alohida ko'rsatiladi.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["BOT_TOKEN"] = "123456:TEST-TOKEN-FOR-WEB-PROMO"

import asyncio
import datetime
import pathlib

from aiohttp.test_utils import TestClient, TestServer

import web
from web import api, auth
from core.config import SEGMENT_NOMI

ROOT = pathlib.Path(__file__).resolve().parent.parent
UTC = datetime.timezone.utc
ADMIN = 641382901

AUDIT = []
XABARLAR = []
PREMIUM = []               # set_user_premium chaqiruvlari
KODLAR = {}
BEKOR = []                 # cancel_scheduled_broadcast

KELAJAK = datetime.datetime.now(UTC) + datetime.timedelta(days=30)
OTGAN = datetime.datetime.now(UTC) - datetime.timedelta(days=1)


class SoxtaBot:
    yetmasinmi = set()

    async def send_message(self, chat_id, text, parse_mode=None):
        if chat_id in SoxtaBot.yetmasinmi:
            raise RuntimeError("bot bloklangan")
        XABARLAR.append((chat_id, text))


def soxta_baza():
    db = api.database_module
    KODLAR.clear()
    KODLAR.update({
        "SENTABR30": {"code": "SENTABR30", "days": 30, "used_count": 41,
                      "max_uses": 100, "expires_at": KELAJAK, "revoked": False},
        "TUGAGAN": {"code": "TUGAGAN", "days": 14, "used_count": 88,
                    "max_uses": 88, "expires_at": None, "revoked": False},
        "MUDDATI": {"code": "MUDDATI", "days": 7, "used_count": 1,
                    "max_uses": 50, "expires_at": OTGAN, "revoked": False},
        "BEKOR": {"code": "BEKOR", "days": 7, "used_count": 0,
                  "max_uses": 50, "expires_at": None, "revoked": True},
    })

    async def list_promo_codes(limit=30):
        return [dict(v) for v in KODLAR.values()]

    async def create_promo_code(code, days, max_uses, expires_at, created_by):
        if code in KODLAR:
            return False
        KODLAR[code] = {"code": code, "days": days, "used_count": 0,
                        "max_uses": max_uses, "expires_at": expires_at, "revoked": False}
        return True

    async def revoke_promo_code(code):
        k = KODLAR.get(code.upper())
        if not k:
            return False
        k["revoked"] = True
        return True

    async def giveaway_stats():
        return {"active_codes": 2, "total_codes": 4, "redemptions": 130,
                "promo_days": 3900, "invited": 19, "qualified": 6, "rewarded": 4}

    async def get_user_by_identifier(token):
        t = token.lstrip("@")
        return {"nodira_x": 511204873, "511204873": 511204873,
                "jasurt": 778120334, "778120334": 778120334}.get(t)

    async def set_user_premium(uid, days, **kw):
        PREMIUM.append({"uid": uid, "kun": days, "kw": kw})

    async def get_referral_config(user_id=None):
        return {"required": 3, "reward_days": 7, "max_rewards": 5, "claimed": False}

    async def set_referral_config(required, reward_days, user_id=None):
        AUDIT.append({"amal": "_db_referral", "tafsilot": f"{required}/{reward_days}"})
        return True

    async def list_scheduled_broadcasts():
        return [
            {"id": 7, "admin_id": ADMIN, "segment": "premium",
             "run_at": datetime.datetime(2026, 9, 18, 19, 0, tzinfo=UTC)},
            {"id": 8, "admin_id": ADMIN, "segment": "bilib_bolmaydigan",
             "run_at": datetime.datetime(2026, 9, 19, 10, 0, tzinfo=UTC)},
        ]

    async def cancel_scheduled_broadcast(bid):
        BEKOR.append(bid)
        return bid == 7

    async def log_admin_action(admin_id, action, target=None, details=None):
        AUDIT.append({"amal": action, "kimga": target, "tafsilot": details})

    for nom, fn in list(locals().items()):
        if nom in ("db", "nom", "fn"):
            continue
        setattr(db, nom, fn)


def amal(turi):
    return [a for a in AUDIT if a["amal"] == turi]


async def main():
    import core.loader
    core.loader.bot = SoxtaBot()
    soxta_baza()

    async def ha(uid):
        return True
    web.huquq_bormi = ha
    auth.huquq_bormi = ha
    h = {"Cookie": f"{auth.COOKIE_NAME}={auth.sessiya_yasa(ADMIN)}"}

    async with TestClient(TestServer(web.build_app())) as c:
        # 1) Yettala endpoint ham cookie'siz yopiq.
        yollar = [("GET", "/api/promo"), ("POST", "/api/promo"),
                  ("GET", "/api/giveaway"), ("POST", "/api/giveaway"),
                  ("GET", "/api/referral"), ("POST", "/api/referral"),
                  ("GET", "/api/broadcasts"), ("DELETE", "/api/broadcasts/7")]
        for metod, yol in yollar:
            r = await c.request(metod, yol, json={})
            assert r.status == 401, f"{metod} {yol} cookie'siz ochiq: {r.status}"
        print(f"[1] promo va tarqatmaning {len(yollar)} ta endpointi cookie'siz 401 OK")

        # 2) Kod holati: uchta boshqa sabab, uchta to'g'ri javob.
        #    ⚠️ «Tugagan» ni «Faol» deb ko'rsatish eng chalg'ituvchi xato
        #    bo'lardi: admin ishlamayotgan kodni tarqatishda davom etardi.
        d = await (await c.get("/api/promo", headers=h)).json()
        holat = {r["kod"]: r["holat"] for r in d["rows"]}
        assert holat == {"SENTABR30": "faol", "TUGAGAN": "tugagan",
                         "MUDDATI": "tugagan", "BEKOR": "bekor"}, holat
        assert [r for r in d["rows"] if r["kod"] == "SENTABR30"][0]["muddat"], "muddat yo'q"
        assert [r for r in d["rows"] if r["kod"] == "TUGAGAN"][0]["muddat"] is None
        print("[2] limit to'lgan, muddati o'tgan va bekor qilingan kod farqlanadi OK")

        # 3) ⭐ Kod qoidalari YAGONA joyda — `clean_promo_spec`.
        AUDIT.clear()
        for yomon in ({"amal": "create", "kod": "yomon kod!", "kun": 30, "max": 10},
                      {"amal": "create", "kod": "X" * 40, "kun": 30, "max": 10},
                      {"amal": "create", "kod": "YAXSHI", "kun": "o'ttiz", "max": 10},
                      {"amal": "create", "kod": "YAXSHI", "kun": 0, "max": 10},
                      {"amal": "create", "kod": "YAXSHI", "kun": 9999, "max": 10},
                      {"amal": "create", "kod": "YAXSHI", "kun": 30, "max": 0},
                      {"amal": "create", "kod": "YAXSHI", "kun": True, "max": 10},
                      {"amal": "create", "kod": "YAXSHI", "kun": 30, "max": 10,
                       "muddat": "2020-01-01"},
                      {"amal": "create", "kod": "YAXSHI", "kun": 30, "max": 10,
                       "muddat": "kecha"}):
            r = await c.post("/api/promo", headers=h, json=yomon)
            assert r.status == 400, f"{yomon} qabul qilindi"
        assert not amal("create_promo"), "rad etilgan kod auditga tushdi"
        assert "YAXSHI" not in KODLAR, "rad etilgan kod bazaga yozildi"
        # Manba bo'yicha: web o'z tekshiruvini QAYTA yozmagan.
        #
        # ⚠️ 7-bosqichda bu tekshiruv shaklini o'zgartirdi. Ilgari u
        # «ikkala ekran ham bitta funksiyani chaqiradimi» degan savolga
        # javob berardi; kod yaratish ekrani botdan o'chirildi, ya'ni
        # chaqiruvchi bitta qoldi. Qoidaning o'zi esa muhimroq va
        # qoladi: chegaralar `web/api.py` da EMAS, `database.py` dagi
        # sof funksiyada bo'lsin — u yerda ular testda tekshiriladi va
        # keyingi chaqiruvchi (masalan qaytib keladigan bot ekrani)
        # ularni qayta yozishga majbur bo'lmaydi.
        src = (ROOT / "web" / "api.py").read_text(encoding="utf-8")
        assert "clean_promo_spec" in src, "web promokod qoidasini qayta yozgan"
        # ⚠️ Faqat `promo_set` TANASI qaraladi. Butun fayl bo'yicha
        # qidirish soxta ogohlantirish berardi: `100000` fayl ichida bor,
        # lekin u `LIMIT_MAX` — kunlik limitning tavani, promokodga
        # aloqasi yo'q.
        gavda = src.split("async def promo_set")[1].split("\nasync def ")[0]
        for chegara in ("3650", "100000", "isalnum", "strptime"):
            assert chegara not in gavda, (
                f"promokod chegarasi ({chegara}) web/api.py ga ko'chib kelgan — "
                "u `database.clean_promo_spec()` da turishi kerak")
        d = (ROOT / "db" / "database.py").read_text(encoding="utf-8")
        assert "def clean_promo_spec" in d and "PROMO_KUN_MAX" in d
        print("[3] ⭐ promokod qoidalari bitta sof funksiyada, panelda nusxa yo'q OK")

        # 4) To'g'ri kod yaratiladi; takrori 409.
        r = await c.post("/api/promo", headers=h,
                         json={"amal": "create", "kod": "yangi_kod", "kun": 30,
                               "max": 100, "muddat": ""})
        assert r.status == 200, await r.text()
        # Kod HAR DOIM katta harfda saqlanadi — foydalanuvchi kichik
        # yozsa ham topilishi kerak (`create_promo_code` UPPER qiladi).
        assert (await r.json())["kod"] == "YANGI_KOD"
        assert amal("create_promo")[0]["tafsilot"] == "YANGI_KOD 30d x100"
        r = await c.post("/api/promo", headers=h,
                         json={"amal": "create", "kod": "YANGI_KOD", "kun": 7, "max": 5})
        assert r.status == 409, await r.text()
        print("[4] kod yaratiladi, katta harfga o'giriladi, takrori 409 OK")

        # 5) Bekor qilish: yo'q kod 404, bor kod auditda.
        assert (await c.post("/api/promo", headers=h,
                             json={"amal": "revoke", "kod": "YOQ"})).status == 404
        r = await c.post("/api/promo", headers=h,
                         json={"amal": "revoke", "kod": "sentabr30"})
        assert r.status == 200, await r.text()
        assert KODLAR["SENTABR30"]["revoked"] is True
        assert amal("revoke_promo"), "bekor qilish auditga tushmadi"
        assert (await c.post("/api/promo", headers=h, json={"amal": "hech"})).status == 400
        print("[5] kod bekor qilinadi (o'chirilmaydi), yo'q kod 404 OK")

        # 6) ⭐ Sovg'a USTIGA qo'shiladi, ustidan yozilmaydi.
        #    Kartochkadagi «Pro berish» — tuzatish amali, u ustidan
        #    yozadi. Sovg'a esa qolgan muddatni yo'q qilmasligi kerak.
        AUDIT.clear(); PREMIUM.clear(); XABARLAR.clear()
        r = await c.post("/api/giveaway", headers=h,
                         json={"kimlar": "@nodira_x, 778120334", "kun": 30})
        assert r.status == 200, await r.text()
        assert len(PREMIUM) == 2, PREMIUM
        assert all(p["kw"].get("extend") is True for p in PREMIUM), (
            "sovg'a muddatni USTIDAN yozdi — qolgan kunlar yo'qoldi")
        assert all(p["kun"] == 30 for p in PREMIUM), PREMIUM
        assert len(XABARLAR) == 2 and len(amal("set_premium")) == 2
        assert amal("set_premium")[0]["tafsilot"] == "sovga 30 kun"
        print("[6] ⭐ sovg'a qolgan muddat USTIGA qo'shiladi, ikkalasi ham auditda OK")

        # 7) Topilmagan va xabar yetmagan — UCH XIL natija.
        #    ⚠️ «Yetmadi» — Pro BERILGAN, faqat xabar bormagan. Admin
        #    buni «bajarilmadi» deb tushunib ikkinchi marta bersa, odam
        #    ikki barobar kun olardi.
        AUDIT.clear(); PREMIUM.clear(); XABARLAR.clear()
        SoxtaBot.yetmasinmi = {778120334}
        r = await c.post("/api/giveaway", headers=h,
                         json={"kimlar": "@nodira_x 778120334 @yoq_odam", "kun": 7})
        d = await r.json()
        assert d["berildi"] == [511204873], d
        assert d["yetmadi"] == [778120334], d
        assert d["topilmadi"] == ["@yoq_odam"], d
        assert len(PREMIUM) == 2, "xabar yetmagan odamga Pro berilmadi"
        assert len(amal("set_premium")) == 2, "xabar yetmagani audit yozuvini yo'qotdi"
        SoxtaBot.yetmasinmi = set()
        print("[7] berildi / xabar yetmadi / topilmadi — uchtasi alohida OK")

        # 8) Sovg'a muddati: buzuq qiymat Pro bermasin.
        #    ⚠️ `null` bu yerda QABUL QILINMAYDI: kartochkada `null`
        #    «cheksiz» degani, va ro'yxatga cheksiz Pro tarqatish yo'li
        #    ochiq qolmasligi kerak.
        PREMIUM.clear()
        for yomon in ({"kimlar": "@nodira_x", "kun": None},
                      {"kimlar": "@nodira_x", "kun": "o'ttiz"},
                      {"kimlar": "@nodira_x", "kun": True},
                      {"kimlar": "@nodira_x", "kun": 0},
                      {"kimlar": "@nodira_x", "kun": -5},
                      {"kimlar": "@nodira_x", "kun": 99999},
                      {"kimlar": "   ", "kun": 30}):
            r = await c.post("/api/giveaway", headers=h, json=yomon)
            assert r.status == 400, f"{yomon} qabul qilindi"
        assert not PREMIUM, "buzuq so'rov Pro berdi"
        print("[8] buzuq muddat va bo'sh ro'yxat Pro bermaydi (cheksiz yo'li yopiq) OK")

        # 9) Referal: qoidalar `clean_referral_config` da.
        AUDIT.clear()
        d = await (await c.get("/api/referral", headers=h)).json()
        assert d["required"] == 3 and d["reward_days"] == 7
        # `max_rewards` KO'RSATILADI, lekin O'ZGARTIRILMAYDI — u abuse
        # tavani (`db/database.py` izohi: admin uni tasodifan ko'tarib
        # qo'ysa cheksiz kun yig'ish yo'li ochilardi). Ya'ni panelda unga
        # tegadigan MAYDON bo'lmasligi kerak; POST esa uni umuman
        # o'qimaydi.
        assert d["max_rewards"] == 5, d
        html = (ROOT / "web" / "static" / "panel.html").read_text(encoding="utf-8")
        assert 'id="r-max' not in html, "max_rewards uchun kiritish maydoni paydo bo'lgan"
        assert "max_rewards" not in src.split("async def referral_set")[1], (
            "referral_set max_rewards ni o'qiyapti — u sozlanmasligi kerak")
        for yomon in ({"required": 3, "reward_days": 300},
                      {"required": 0, "reward_days": 7},
                      {"required": 1000, "reward_days": 7},
                      {"required": "uch", "reward_days": 7}):
            r = await c.post("/api/referral", headers=h, json=yomon)
            assert r.status == 400, f"{yomon} qabul qilindi"
        assert not amal("_db_referral"), "rad etilgan shart bazaga yozildi"
        r = await c.post("/api/referral", headers=h, json={"required": 5, "reward_days": 14})
        assert r.status == 200, await r.text()
        assert amal("referral_config")[0]["tafsilot"] == "5 ta -> 14 kun"
        print("[9] referal sharti: «3 do'st → 300 kun» rad etiladi, o'zgarish auditda OK")

        # 10) Tarqatma: segment nomi yagona ro'yxatdan, noma'lumi XOM
        #     ko'rinadi — yashirilsa qator umuman yo'qday bo'lardi.
        d = await (await c.get("/api/broadcasts", headers=h)).json()
        assert d["rows"][0]["segment"] == SEGMENT_NOMI["premium"], d["rows"][0]
        assert d["rows"][1]["segment"] == "bilib_bolmaydigan", "noma'lum segment yashirildi"
        # ⚠️ Nusxa `handlers/admin/journal.py` da tug'ilgandi; fayl
        # 7-bosqichda o'chdi. Endi qo'riqlanadigan joy — kalitlarning
        # MANBASI: segmentni haqiqatda `broadcast.py` yozadi, ya'ni
        # ro'yxat o'shanikiga mos bo'lishi shart. Aynan shu mos
        # kelmaslik birinchi urinishda yuz bergan edi — panel uchun
        # `"pro"` va `"active"` degan mavjud bo'lmagan kalitlar yozilgan.
        b = (ROOT / "handlers" / "admin" / "broadcast.py").read_text(encoding="utf-8")
        for kalit in SEGMENT_NOMI:
            assert f'"{kalit}"' in b, (
                f"SEGMENT_NOMI da «{kalit}» bor, broadcast.py esa uni yozmaydi")
        assert "SEGMENT_NOMI" in (ROOT / "web" / "api.py").read_text(encoding="utf-8")
        print("[10] segment nomlari yagona ro'yxatdan, noma'lumi yashirilmaydi OK")

        # 11) Bekor qilish: yuborilgan tarqatma 404, buzuq ID 400.
        AUDIT.clear(); BEKOR.clear()
        assert (await c.delete("/api/broadcasts/xyz", headers=h)).status == 400
        assert not BEKOR, "buzuq ID bilan bazaga borildi"
        assert (await c.delete("/api/broadcasts/8", headers=h)).status == 404
        assert not amal("cancel_broadcast"), "bekor qilinmagan tarqatma auditga tushdi"
        assert (await c.delete("/api/broadcasts/7", headers=h)).status == 200
        assert amal("cancel_broadcast")[0]["tafsilot"] == "#7"
        print("[11] tarqatma bekor qilinadi; yuborilgani 404, buzuq ID 400 OK")

        # 12) Yangi tarqatma web'dan YUBORILMAYDI — bu ataylab (REJA 2).
        #     `copy_message` adminning xabarini aynan uzatadi; webda
        #     qayta yig'ilgan xabar albom, formatlash va premium emojini
        #     yo'qotardi.
        assert "add_post(\"/api/broadcasts" not in src, (
            "web'dan tarqatma yuborish yo'li ochilgan — REJA 2 ga zid")
        html = (ROOT / "web" / "static" / "panel.html").read_text(encoding="utf-8")
        assert "copy_message" in html and "/xabar" in html, (
            "tarqatma nega botda qolgani tushuntirilmagan")
        print("[12] yangi tarqatma faqat botda; sababi ekranda yozilgan OK")

    print("\nweb promo: barcha tekshiruvlar o'tdi (12/12).")


if __name__ == "__main__":
    asyncio.run(main())
