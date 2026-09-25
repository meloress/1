"""Web paneldagi foydalanuvchi amallari uchun tekshiruv.
Ishga tushirish: python tests/test_web_users.py

Tarmoq, baza va Telegram kerak emas — hammasi almashtiriladi.

Bu fayl PUL va HUQUQ yo'lini qo'riqlaydi, ya'ni xatosi eng qimmat
turadigan joyni:

  * refund TARTIBI — avval Telegram, keyin baza. Teskari bo'lsa
    Telegram rad etganda foydalanuvchidan tarif olib qo'yilib, puli
    qaytmasdan qolardi;
  * har bir YOZUV amali audit jurnaliga tushishi;
  * har bir endpoint `@admin_only` bilan yopilgani.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _manba import kod

os.environ["BOT_TOKEN"] = "123456:TEST-TOKEN-FOR-WEB-USERS"

import ast
import asyncio
import json
import datetime
import pathlib

from aiohttp.test_utils import TestClient, TestServer

import web
from web import api, auth
from core.config import TARIF_NOMI
from core.config import DAILY_COUNTERS, LIMIT_NOMI

ROOT = pathlib.Path(__file__).resolve().parent.parent
UTC = datetime.timezone.utc

# ── Yozib boradigan soxta olam ────────────────────────────────────
AUDIT = []       # log_admin_action chaqiruvlari
XABARLAR = []    # botdan ketgan xabarlar
TELEGRAM = []    # refund_star_payment chaqiruvlari
BAZA = []        # mark_payment_refunded chaqiruvlari

PROFIL = {
    "user_id": 641382905, "username": "dilshod_a", "is_banned": False,
    "plan_type": "premium", "premium_until": datetime.datetime(2026, 10, 8, tzinfo=UTC),
    "created_at": datetime.datetime(2026, 3, 12, tzinfo=UTC),
    "last_seen": datetime.datetime(2026, 9, 15, tzinfo=UTC),
    "daily_requests_used": 84, "total_messages": 1847,
    "daily_files_used": 2, "daily_images_used": 5, "daily_research_used": 0,
}

TOLOV = {
    "id": 4812, "payer_id": 641382905, "beneficiary_id": 641382905,
    "charge_id": "CHG_TEST_1", "stars": 1500, "days": 30,
    "created_at": datetime.datetime(2026, 9, 12, tzinfo=UTC), "refunded_at": None,
}


class SoxtaBot:
    """`core.loader.bot` o'rniga. Telegram rad etishini ham o'ynay oladi."""
    rad_etsinmi = False

    async def send_message(self, chat_id, text, parse_mode=None):
        XABARLAR.append((chat_id, text))

    async def refund_star_payment(self, user_id, telegram_payment_charge_id):
        TELEGRAM.append((user_id, telegram_payment_charge_id))
        if SoxtaBot.rad_etsinmi:
            from aiogram.exceptions import TelegramBadRequest
            raise TelegramBadRequest(method=None, message="CHARGE_ALREADY_REFUNDED")


def soxta_baza(tolov=None):
    db = api.database_module

    async def list_users(q=None, tarif="all", limit=20, offset=0,
                         tartib="faollik"):
        rows = [dict(PROFIL)] if offset == 0 else []
        return {"rows": rows, "jami": 45,
                "sanoq": {"all": 45, "pro": 2, "free": 40, "ban": 3,
                          "nofaol": 7}}

    async def get_full_user_profile(uid):
        return dict(PROFIL) if uid == PROFIL["user_id"] else None

    async def get_user_payments(uid, limit=10):
        return [dict(tolov or TOLOV)]

    async def get_referral_progress(uid):
        return {"invited": 3, "qualified": 2, "rewarded": 1}

    async def log_admin_action(admin_id, action, target=None, details=None):
        AUDIT.append({"admin": admin_id, "amal": action, "kimga": target, "tafsilot": details})

    async def set_user_premium(uid, days, **kw):
        AUDIT.append({"amal": "_db_premium", "kimga": uid, "tafsilot": days})

    async def set_user_premium_checked(uid, days, *, plan="pro",
                                       kutilgan_tarif, kutilgan_muddat):
        """Haqiqiysidagi kabi: mos kelmasa HECH NARSA yozmaydi."""
        hozir = {"tarif": PROFIL["plan_type"], "muddat": PROFIL["premium_until"]}
        if (hozir["tarif"] != kutilgan_tarif
                or hozir["muddat"] != kutilgan_muddat):
            return {"ok": False, "hozir": hozir}
        AUDIT.append({"amal": "_db_premium", "kimga": uid, "tafsilot": days})
        return {"ok": True, "oldin": hozir}

    async def set_user_plan(uid, plan):
        AUDIT.append({"amal": "_db_plan", "kimga": uid, "tafsilot": plan})

    async def reset_user_quota(uid):
        AUDIT.append({"amal": "_db_quota", "kimga": uid, "tafsilot": None})

    async def ban_user(uid):
        AUDIT.append({"amal": "_db_ban", "kimga": uid, "tafsilot": None})

    async def unban_user(uid):
        AUDIT.append({"amal": "_db_unban", "kimga": uid, "tafsilot": None})

    async def get_payment_by_id(pid):
        t = dict(tolov or TOLOV)
        return t if pid == t["id"] else None

    async def mark_payment_refunded(charge_id, admin_id):
        BAZA.append((charge_id, admin_id))
        return True

    for nom, fn in list(locals().items()):
        if nom in ("db", "tolov", "nom", "fn"):
            continue
        setattr(db, nom, fn)


def amallar_faqat(turi):
    """Audit yozuvlari (soxta DB chaqiruvlari `_db_` bilan boshlanadi)."""
    return [a for a in AUDIT if a["amal"] == turi]


async def main():
    import core.loader
    core.loader.bot = SoxtaBot()
    soxta_baza()

    async def ha(uid):
        return True
    web.huquq_bormi = ha
    auth.huquq_bormi = ha
    h = {"Cookie": f"{auth.COOKIE_NAME}={auth.sessiya_yasa(1)}"}
    UID = PROFIL["user_id"]

    async with TestClient(TestServer(web.build_app())) as c:
        # 1) HAMMA yangi endpoint cookie'siz yopiq.
        yollar = [
            ("GET", f"/api/users"), ("GET", f"/api/users/{UID}"),
            ("POST", f"/api/users/{UID}/premium"), ("POST", f"/api/users/{UID}/plan"),
            ("POST", f"/api/users/{UID}/quota"), ("POST", f"/api/users/{UID}/ban"),
            ("POST", f"/api/users/{UID}/message"), ("POST", "/api/payments/4812/refund"),
        ]
        for metod, yol in yollar:
            r = await c.request(metod, yol, json={})
            assert r.status == 401, f"{metod} {yol} cookie'siz ochiq: {r.status}"
        print(f"[1] {len(yollar)} ta endpoint cookie'siz 401 qaytaradi OK")

        # 2) Manba bo'yicha: har bir route handleri `@admin_only` bilan.
        #    Jonli tekshiruv bitta unutilgan dekoratorni ushlaydi, lekin
        #    faqat men sinab ko'rgan yo'lni. Bu esa HAMMASINI ko'radi.
        src = kod(ROOT / "web" / "api.py")
        daraxt = ast.parse(src)
        dekorator = {
            f.name: any(getattr(d, "id", "") == "admin_only" for d in f.decorator_list)
            for f in ast.walk(daraxt) if isinstance(f, ast.AsyncFunctionDef)
        }
        marshrutlar = set()
        for n in ast.walk(daraxt):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr in ("add_get", "add_post")):
                marshrutlar.add(n.args[1].id)
        assert marshrutlar, "register() dagi marshrutlar topilmadi"
        qo_riqsiz = [m for m in marshrutlar if not dekorator.get(m)]
        assert not qo_riqsiz, f"@admin_only yo'q: {qo_riqsiz}"
        print(f"[2] {len(marshrutlar)} ta marshrutning hammasi @admin_only bilan OK")

        # 3) Ro'yxat: sahifalash va chip sanoqlari.
        d = await (await c.get("/api/users?page=0", headers=h)).json()
        assert d["sahifalar"] == 3 and d["sahifa"] == 0, d      # 45 / 20 -> 3
        assert d["sanoq"]["all"] == 45
        # ⚠️ `premium` — ESKI, cheksiz limitli tarif. Ilgari u jadvalda
        # «pro» ga yopishtirilardi, Boshqaruv ekranidagi doirada esa
        # alohida segment bo'lib turardi: bitta odam ikki ekranda ikki
        # xil tarifda. Kalit endi `TARIF_NOMI` niki.
        assert d["rows"][0]["tarif"] == "premium", d["rows"][0]
        assert d["rows"][0]["tarif"] in TARIF_NOMI, "kalit yagona ro'yxatda yo'q"
        # Noto'g'ri filtr va sahifa so'rovni YIQITMASLIGI kerak.
        for yomon in ("?filter=hech-narsa", "?page=-5", "?page=abc", "?q=' OR 1=1 --"):
            assert (await c.get("/api/users" + yomon, headers=h)).status == 200, yomon
        print("[3] ro'yxat sahifalanadi, noto'g'ri parametr yiqitmaydi OK")

        # 4) Kartochka: limitlar `daily_limit()` dan, yo'q odam — 404.
        p = await (await c.get(f"/api/users/{UID}", headers=h)).json()
        assert p["tarif"] == "premium" and p["jami_sorov"] == 1847
        # ⚠️ Nomlar QO'LDA yozilmaydi. Ilgari shu yerda uchta satr
        # qotirilgandi va u nusxa edi: 6-bosqichda ro'yxat
        # `core/config.py::LIMIT_NOMI` ga ko'chganda test o'zi yiqildi,
        # ya'ni u nomlarni emas, o'z nusxasini qo'riqlayotgan ekan.
        # Endi manba bilan solishtiriladi — sanoq tartibi ham tekshiriladi.
        nomlar = [s["nom"] for s in p["sanoqlar"]]
        assert nomlar == [LIMIT_NOMI[k] for k in DAILY_COUNTERS], nomlar
        assert p["ballar"]["ishlatilgan"] == 84
        assert (await c.get("/api/users/777/", headers=h)).status in (404, 405)
        assert (await c.get("/api/users/777", headers=h)).status == 404
        assert (await c.get("/api/users/xyz", headers=h)).status == 400
        print("[4] kartochka to'liq, yo'q foydalanuvchi 404, buzuq ID 400 OK")

        # 5) Pro berish: bazaga yozadi, auditga tushadi, ODAMGA XABAR
        #    yuboradi (REJA 10-bo'lim, 5-tekshiruv).
        AUDIT.clear(); XABARLAR.clear()
        # ⚠️ `holat` — kartochkada KO'RILGAN qiymat, server uni joriy
        # qiymat bilan solishtiradi.
        HOLAT = {"tarif": PROFIL["plan_type"],
                 "muddat": PROFIL["premium_until"].astimezone(
                     api.TIMEZONE).isoformat(timespec="seconds")}
        r = await c.post(f"/api/users/{UID}/premium", headers=h,
                         json={"kun": 30, "holat": HOLAT})
        assert r.status == 200, await r.text()
        assert amallar_faqat("_db_premium"), "bazaga yozilmadi"
        yozuv = amallar_faqat("set_premium")
        assert yozuv and yozuv[0]["kimga"] == UID, AUDIT
        # ⭐ Audit yozuvi TUZILGAN: oldingi holat keyin TIKLASH uchun
        # yaroqli bo'lishi kerak. Ilgari bu yerda faqat «30» turardi va
        # xato bosilgan muddatni qaytarishning iloji yo'q edi.
        d = json.loads(yozuv[0]["tafsilot"])
        assert isinstance(d, dict), (
            "audit yozuvi TUZILGAN emas — oldingi holat yo'qoladi va "
            "xato bosilgan muddatni tiklashning iloji qolmaydi")
        assert d["kun"] == 30, d
        assert d["oldin"]["tarif"] == PROFIL["plan_type"], d
        assert d["oldin"]["muddat"] == HOLAT["muddat"], d
        assert isinstance(d["oldin"]["qolgan"], int), d
        # Jurnal ekranida esa u O'QILADIGAN ko'rinishda chiqadi.
        assert api._tafsilot("set_premium", yozuv[0]["tafsilot"]).startswith("30 kun (oldin:")
        assert XABARLAR and str(UID) == str(XABARLAR[0][0]), XABARLAR
        assert "Pro" in XABARLAR[0][1]
        print("[5] Pro berildi: baza + audit + foydalanuvchiga xabar OK")

        # 6) Muddat ishonchsiz kirish: faqat ruxsat etilgani o'tadi.
        for yomon in ({"kun": 5}, {"kun": 99999}, {"kun": "o'ttiz"}, {"kun": -30}):
            r = await c.post(f"/api/users/{UID}/premium", headers=h,
                             json={**yomon, "holat": HOLAT})
            assert r.status == 400, f"{yomon} qabul qilindi"
        # ⛔️ `holat` MAJBURIY. Uni ixtiyoriy qilish butun himoyani bekor
        # qilardi: chetlab o'tish uchun maydonni yubormaslik kifoya edi.
        r = await c.post(f"/api/users/{UID}/premium", headers=h, json={"kun": 30})
        assert r.status == 400, "holatsiz so'rov o'tkazib yuborildi"
        r = await c.post(f"/api/users/{UID}/premium", headers=h,
                         json={"kun": 30, "holat": {"tarif": "pro",
                                                    "muddat": "shanba kuni"}})
        assert r.status == 400, "buzuq sana qabul qilindi"

        r = await c.post(f"/api/users/{UID}/premium", headers=h,
                         json={"kun": None, "holat": HOLAT})
        assert r.status == 200, await r.text()
        assert json.loads(amallar_faqat("set_premium")[-1]["tafsilot"])["kun"] == "inf"
        print("[6] faqat ruxsat etilgan muddatlar; holatsiz so'rov rad etiladi OK")

        # 7) Bloklash / ochish va kvota — hammasi auditda.
        AUDIT.clear(); XABARLAR.clear()
        await c.post(f"/api/users/{UID}/ban", headers=h, json={"ban": True})
        await c.post(f"/api/users/{UID}/ban", headers=h, json={"ban": False})
        await c.post(f"/api/users/{UID}/quota", headers=h, json={})
        await c.post(f"/api/users/{UID}/plan", headers=h, json={"tarif": "free"})
        for amal in ("ban_user", "unban_user", "reset_quota", "set_plan"):
            assert amallar_faqat(amal), f"{amal} auditga tushmadi"
        # Bloklashda xabar YUBORILMAYDI (bot keyingi xabarda o'zi aytadi),
        # blok ochilganda va tarif tushirilganda — yuboriladi.
        assert len(XABARLAR) == 2, [x[1][:40] for x in XABARLAR]
        r = await c.post(f"/api/users/{UID}/plan", headers=h, json={"tarif": "pro"})
        assert r.status == 400, "tarifni 'pro' ga qo'yish shu yo'ldan o'tmasin"
        print("[7] blok/kvota/tarif amallari auditda, xabarlar o'rinli OK")

        # 8) Xabar yozish: bo'sh rad etiladi, HTML ekranlanadi.
        AUDIT.clear(); XABARLAR.clear()
        assert (await c.post(f"/api/users/{UID}/message", headers=h,
                             json={"matn": "   "})).status == 400
        assert (await c.post(f"/api/users/{UID}/message", headers=h,
                             json={"matn": "x" * 4000})).status == 400
        r = await c.post(f"/api/users/{UID}/message", headers=h,
                         json={"matn": "<b>ochiq teg"})
        assert r.status == 200, await r.text()
        assert "&lt;b&gt;" in XABARLAR[0][1], XABARLAR[0][1]
        assert amallar_faqat("send_message"), "xabar auditga tushmadi"
        print("[8] xabar: bo'sh/uzun rad etiladi, HTML ekranlanadi, auditda OK")

        # 9) ⭐ REFUND TARTIBI — eng qimmat xato shu yerda bo'lardi.
        AUDIT.clear(); XABARLAR.clear(); TELEGRAM.clear(); BAZA.clear()
        SoxtaBot.rad_etsinmi = True
        r = await c.post("/api/payments/4812/refund", headers=h, json={})
        assert r.status == 400, await r.text()
        assert TELEGRAM, "Telegram'ga umuman murojaat qilinmadi"
        assert not BAZA, "TELEGRAM RAD ETDI, LEKIN BAZA O'ZGARTIRILDI"
        assert not amallar_faqat("refund_stars"), "rad etilgan refund auditga tushdi"
        assert not XABARLAR, "rad etilgan refund uchun xabar yuborildi"
        print("[9] Telegram rad etsa baza TEGILMAYDI, audit yozilmaydi OK")

        # 10) Muvaffaqiyatli refund: Telegram → baza → audit → xabar.
        SoxtaBot.rad_etsinmi = False
        TELEGRAM.clear(); BAZA.clear(); AUDIT.clear(); XABARLAR.clear()
        r = await c.post("/api/payments/4812/refund", headers=h, json={})
        assert r.status == 200, await r.text()
        assert TELEGRAM == [(TOLOV["payer_id"], TOLOV["charge_id"])], TELEGRAM
        assert BAZA == [(TOLOV["charge_id"], 1)], BAZA
        assert amallar_faqat("refund_stars"), "refund auditga tushmadi"
        assert XABARLAR and "qaytarildi" in XABARLAR[0][1]
        print("[10] refund: Telegram → baza → audit → xabar, shu tartibda OK")

        # 11) Qayta-refund va yo'q to'lov: Telegram'ga UMUMAN borilmaydi.
        TELEGRAM.clear()
        soxta_baza({**TOLOV, "refunded_at": datetime.datetime.now(UTC)})
        r = await c.post("/api/payments/4812/refund", headers=h, json={})
        assert r.status == 409, r.status
        soxta_baza()
        assert (await c.post("/api/payments/999/refund", headers=h, json={})).status == 404
        assert not TELEGRAM, "qaytarilgan to'lov uchun Telegram chaqirildi"
        print("[11] qaytarilgan/yo'q to'lovda Telegram'ga borilmaydi OK")

        # 12) Xabar yetmasa amal BEKOR QILINMAYDI: Pro berildi — berildi.
        AUDIT.clear()

        async def yetmaydi(chat_id, text, parse_mode=None):
            raise RuntimeError("bot bloklangan")
        core.loader.bot.send_message = yetmaydi
        r = await c.post(f"/api/users/{UID}/premium", headers=h,
                         json={"kun": 7, "holat": HOLAT})
        assert r.status == 200, await r.text()
        assert (await r.json())["xabar_yetdi"] is False
        assert amallar_faqat("set_premium"), "xabar yetmagani uchun amal bekor bo'ldi"
        print("[12] xabar yetmasa ham amal bajariladi va auditda qoladi OK")

        # ── 13) ⭐ SO'ROVLAR ORASIDA TO'LOV BO'LGAN HOLAT ──────────
        # Admin kartani ochdi va «20 kun» ni ko'rdi. U tugmani bosguncha
        # odam Stars bilan 30 kun sotib oldi. Tekshiruvsiz admin O'ZI
        # KO'RMAGAN 30 kunni o'chirgan bo'lardi — pul to'langan kunlarni.
        AUDIT.clear(); XABARLAR.clear()
        # ⚠️ Idempotentlik keshini tozalaymiz: 5-bandda AYNAN shu tana
        # yuborilgan edi va `@bir_marta` o'sha javobni qaytarib berardi.
        # Bu yerda biz ikki bosishni emas, KEYINROQ qilingan amalni
        # o'ynayapmiz — ya'ni kesh bu sinovga tegishli emas.
        auth._natijalar.clear()
        PROFIL["premium_until"] = datetime.datetime(2026, 11, 8, tzinfo=UTC)
        r = await c.post(f"/api/users/{UID}/premium", headers=h,
                         json={"kun": 30, "holat": HOLAT})   # ESKI holat
        assert r.status == 409, await r.text()
        d = await r.json()
        assert "o'zgargan" in d["error"], d
        # ⚠️ HECH NARSA yozilmasin: na baza, na audit, na xabar.
        assert not amallar_faqat("_db_premium"), "409 ga qaramay bazaga yozildi"
        assert not amallar_faqat("set_premium"), "409 ga qaramay auditga yozildi"
        assert not XABARLAR, "409 ga qaramay foydalanuvchiga xabar ketdi"
        # Panel yangi holatni oladi va qayta ko'rsatadi.
        assert d["hozir"]["muddat"].startswith("2026-11-08"), d

        # Yangi holat bilan qayta urinish O'TADI.
        YANGI = {"tarif": PROFIL["plan_type"],
                 "muddat": PROFIL["premium_until"].astimezone(
                     api.TIMEZONE).isoformat(timespec="seconds")}
        r = await c.post(f"/api/users/{UID}/premium", headers=h,
                         json={"kun": 30, "holat": YANGI})
        assert r.status == 200, await r.text()
        print("[13] so'rovlar orasida to'lov bo'lsa 409, hech narsa yozilmaydi OK")

    print("\nweb users: barcha tekshiruvlar o'tdi (13/13).")


if __name__ == "__main__":
    asyncio.run(main())
