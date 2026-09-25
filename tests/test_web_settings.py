"""Web paneldagi Sozlamalar ekrani uchun tekshiruv.
Ishga tushirish: python tests/test_web_settings.py

Tarmoq, baza va Telegram kerak emas — hammasi almashtiriladi.

Bu fayl 6-bosqichning «TAYYOR» mezonini qo'riqlaydi:

  ⭐ 2-tekshiruv — webdan o'zgartirilgan limit BOT ishlatadigan qiymatga
  aylanadimi. `config.apply_limit_overrides()` chaqiruvi unutilsa bazada
  yangi son turadi, bot esa eskisi bilan ishlaydi: panel «o'zgardi» deb
  ko'rsatadi, foydalanuvchi eski limitga uriladi va buni HECH NARSA
  aytmaydi. REJA 3.1 dagi «panel bot jarayonining ichida» qarorining
  butun sababi shu bitta chaqiruv, va uni faqat shu test tekshiradi.

  Qolganlari — ishonchsiz kirish (admin ham xato yozadi) va himoya
  darvozasining ikki ekranda BIR XIL ekani.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _manba import kod

os.environ["BOT_TOKEN"] = "123456:TEST-TOKEN-FOR-WEB-SETTINGS"

import ast
import asyncio
import re
import datetime
import pathlib

from aiohttp.test_utils import TestClient, TestServer

import web
from web import api, auth
from core import config
from core.config import LIMIT_NOMI, PLAN_LIMITS

ROOT = pathlib.Path(__file__).resolve().parent.parent
UTC = datetime.timezone.utc

ADMIN = 641382901          # sessiyadagi admin
BOSHQA = 778120334         # oddiy admin
SUPER = 641382901          # superadmin — ADMIN ning o'zi

AUDIT = []
KESH = []                  # load_watch_cache chaqiruvlari
GURUHGA = []               # kuzatuv guruhiga ketgan sinov xabarlari


class SoxtaBot:
    """`core.loader.bot` o'rniga. Telegram rad etishini ham o'ynaydi."""
    xato = None            # None | Telegram javobining matni

    async def send_message(self, chat_id, text, parse_mode=None):
        if SoxtaBot.xato:
            from aiogram.exceptions import TelegramBadRequest
            raise TelegramBadRequest(method=None, message=SoxtaBot.xato)
        GURUHGA.append((chat_id, text))
MENYU = []                 # sync_menu_button chaqiruvlari
HOLAT = {"overrides": {}, "maintenance": {"active": False, "message": "Eski matn"},
         "guruh": -1002481000, "watch": {511204873}, "adminlar": {ADMIN, BOSHQA}}


def soxta_baza():
    db = api.database_module

    async def get_limit_overrides():
        return {k: dict(v) for k, v in HOLAT["overrides"].items()}

    async def set_limit_override(plan, key, value):
        bolim = dict(HOLAT["overrides"].get(plan) or {})
        if value is None:
            bolim.pop(key, None)
        else:
            bolim[key] = int(value)
        if bolim:
            HOLAT["overrides"][plan] = bolim
        else:
            HOLAT["overrides"].pop(plan, None)
        return {k: dict(v) for k, v in HOLAT["overrides"].items()}

    async def get_maintenance():
        return dict(HOLAT["maintenance"])

    async def set_maintenance(active, message=None):
        HOLAT["maintenance"]["active"] = active
        if message is not None:            # COALESCE: None matnni o'zgartirmaydi
            HOLAT["maintenance"]["message"] = message

    async def get_watch_group_id():
        return HOLAT["guruh"]

    async def set_watch_group_id(gid):
        HOLAT["guruh"] = gid

    async def get_watchlist():
        return [{"user_id": u, "username": "akmal",
                 "added_at": datetime.datetime(2026, 9, 9, tzinfo=UTC)}
                for u in sorted(HOLAT["watch"])]

    async def add_watch(uid, added_by):
        HOLAT["watch"].add(uid)

    async def remove_watch(uid):
        HOLAT["watch"].discard(uid)

    async def load_watch_cache():
        KESH.append(True)

    async def get_user_by_identifier(token):
        t = token.lstrip("@")
        return 511204873 if t in ("akmal", "511204873") else None

    async def get_full_user_profile(uid):
        return {"user_id": uid, "username": "yangi_admin"}

    async def get_admins():
        return [{"user_id": u, "username": "melores" if u == SUPER else "aziz",
                 "display_name": "@melores" if u == SUPER else "@aziz",
                 "created_at": "2026-03-01 10:00"} for u in sorted(HOLAT["adminlar"])]

    async def get_panel_admins():
        # ⚠️ Superadmin `admins` jadvalida BO'LMASLIGI mumkin (jonli
        # bazada aynan shunday) — shuning uchun u bu yerda ro'yxatga
        # alohida qo'shiladi, xuddi haqiqiy FULL OUTER JOIN kabi.
        kimlar = sorted(HOLAT["adminlar"] | {SUPER})
        return [{"user_id": u, "username": "melores" if u == SUPER else "aziz",
                 "display_name": "@melores" if u == SUPER else "@aziz",
                 "created_at": "2026-03-01 10:00",
                 "is_super": u == SUPER} for u in kimlar]

    async def is_superadmin(uid):
        return uid == SUPER

    async def is_admin(uid):
        return uid in HOLAT["adminlar"]

    async def add_admin(uid, username=None):
        HOLAT["adminlar"].add(uid)

    async def remove_admin(uid):
        HOLAT["adminlar"].discard(uid)

    async def get_superadmin_id():
        return SUPER

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

    # `_check_can_remove_admin` bazaning pool'iga to'g'ridan-to'g'ri
    # boradi (so'rovchining `created_at` ini o'qish uchun) — testda pool
    # yo'q, shuning uchun funksiya o'sha joyda xatoni yutadi va
    # `requester_created_at = None` bo'lib qoladi. Superadmin uchun bu
    # muhim emas: qoidaning qolgan qismi baribir ishlaydi.
    from services import menu as menu_module

    async def soxta_menyu(uid, is_admin):
        MENYU.append((uid, is_admin))
    menu_module.sync_menu_button = soxta_menyu

    async def ha(uid):
        return True
    web.huquq_bormi = ha
    auth.huquq_bormi = ha
    h = {"Cookie": f"{auth.COOKIE_NAME}={auth.sessiya_yasa(ADMIN)}"}

    async with TestClient(TestServer(web.build_app())) as c:
        # 1) Sakkizta endpoint ham cookie'siz yopiq.
        yollar = [("GET", "/api/limits"), ("POST", "/api/limits"),
                  ("GET", "/api/maintenance"), ("POST", "/api/maintenance"),
                  ("GET", "/api/watch"), ("POST", "/api/watch"),
                  ("GET", "/api/admins"), ("POST", "/api/admins")]
        for metod, yol in yollar:
            r = await c.request(metod, yol, json={})
            assert r.status == 401, f"{metod} {yol} cookie'siz ochiq: {r.status}"
        print(f"[1] sozlamalarning {len(yollar)} ta endpointi cookie'siz 401 OK")

        # 2) ⭐ 6-BOSQICHNING TAYYOR MEZONI: webdan o'zgartirilgan limit
        #    BOT ishlatadigan qiymatga aylanadimi.
        config.apply_limit_overrides({})
        asl = config.daily_limit("free", "points")
        r = await c.post("/api/limits", headers=h,
                         json={"tarif": "free", "kalit": "points", "qiymat": 77})
        assert r.status == 200, await r.text()
        assert config.daily_limit("free", "points") == 77, (
            "BAZAGA YOZILDI, LEKIN BOT ESKI LIMIT BILAN ISHLAYAPTI — "
            "`config.apply_limit_overrides()` chaqirilmagan")
        assert (await r.json())["qiymat"] == 77, "javobdagi qiymat `daily_limit()` dan emas"
        assert amal("limit_change"), "limit o'zgarishi auditga tushmadi"
        # Boshqa tarif va boshqa sanoq TEGILMASIN.
        assert config.daily_limit("pro", "points") == PLAN_LIMITS["pro"]["points"]
        assert config.daily_limit("free", "files") == PLAN_LIMITS["free"]["files"]
        print("[2] ⭐ webdan o'zgartirilgan limit BOT xotirasida ham darhol kuchga kiradi OK")

        # 3) Tiklash asl qiymatga qaytaradi — CHEKSIZLIK EMAS.
        #    `None` bu yerda «o'zgartirishni olib tashla» degani; agar u
        #    cheksizlik bo'lib ketsa, bepul tarif cheksiz bo'lib qolardi.
        r = await c.post("/api/limits", headers=h,
                         json={"tarif": "free", "kalit": "points", "qiymat": None})
        assert r.status == 200, await r.text()
        assert config.daily_limit("free", "points") == asl, "asl qiymat qaytmadi"
        assert config.daily_limit("free", "points") is not None, "tiklash cheksizlik berdi"
        print("[3] tiklash asl qiymatni qaytaradi, cheksizlik bermaydi OK")

        # 4) Ishonchsiz kirish: admin ham xato yozadi.
        #    ⚠️ `true` — Python'da `int(True) == 1`: tekshirilmasa butun
        #    tarifning kunlik limiti 1 ga tushib qolardi.
        for yomon in ({"tarif": "free", "kalit": "points", "qiymat": True},
                      {"tarif": "free", "kalit": "points", "qiymat": "o'ttiz"},
                      {"tarif": "free", "kalit": "points", "qiymat": -1},
                      {"tarif": "free", "kalit": "points", "qiymat": 10 ** 9},
                      {"tarif": "premium", "kalit": "points", "qiymat": 5},
                      {"tarif": "free", "kalit": "kontekst", "qiymat": 5}):
            r = await c.post("/api/limits", headers=h, json=yomon)
            assert r.status == 400, f"{yomon} qabul qilindi"
        assert config.daily_limit("free", "points") == asl, "buzuq so'rov limitni o'zgartirdi"
        print("[4] buzuq qiymat, cheksiz tarif va begona kalit rad etiladi OK")

        # 5) Nomlar YAGONA ro'yxatdan; nusxa qaytib kelmasin.
        d = await (await c.get("/api/limits", headers=h)).json()
        assert [r["nom"] for r in d["rows"]] == list(LIMIT_NOMI.values()), d["rows"]
        assert [r["kalit"] for r in d["rows"]] == list(LIMIT_NOMI), d["rows"]
        assert "premium" not in d["tariflar"], "cheksiz tarif o'zgartirish jadvalida"
        # ⚠️ Ikkinchi nusxa `handlers/admin/journal.py::LIMIT_KEYS` da
        # edi; fayl 7-bosqichda o'chdi (ekran webga ko'chdi). Endi
        # qo'riqlanadigan joy — kalitlarning MANBASI: jadvaldagi har bir
        # kalit `PLAN_LIMITS` da bo'lishi shart, aks holda panel
        # o'zgartira olmaydigan qatorni ko'rsatib turardi (maketdagi
        # «Kontekst (xabar)» aynan shunday edi).
        for kalit in LIMIT_NOMI:
            assert kalit in PLAN_LIMITS["free"], (
                f"«{kalit}» LIMIT_NOMI da bor, PLAN_LIMITS da yo'q — "
                "o'zgartirib bo'lmaydigan qator")
        a = kod(ROOT / "web" / "api.py")
        assert '"files": "Fayllar"' not in a, "web/api.py da nomlarning nusxasi qaytib kelgan"
        assert "LIMIT_NOMI" in a, "web yagona ro'yxatdan o'qimaydi"
        print(f"[5] {len(LIMIT_NOMI)} ta limit nomi yagona ro'yxatdan, nusxa yo'q OK")

        # 6) Texnik ta'til: matnni tahrirlash rejimni YOQMASIN.
        #    Bu oson yo'l qo'yiladigan xato: `active` yuborilmasa
        #    `bool(None) == False` bo'lib, yoqilgan ta'til jimgina
        #    o'chib ketardi (yoki teskarisi).
        AUDIT.clear()
        r = await c.post("/api/maintenance", headers=h, json={"active": True})
        assert r.status == 200 and (await r.json())["active"] is True
        r = await c.post("/api/maintenance", headers=h, json={"matn": "Yangi matn"})
        assert r.status == 200, await r.text()
        d = await r.json()
        assert d["active"] is True, "faqat matn o'zgartirilganda rejim o'chib qoldi"
        assert d["matn"] == "Yangi matn"
        assert (await c.post("/api/maintenance", headers=h, json={"matn": "  "})).status == 400
        await c.post("/api/maintenance", headers=h, json={"active": False})
        assert len(amal("maintenance")) == 3, AUDIT
        print("[6] ta'til: matn tahriri rejimni o'zgartirmaydi, hammasi auditda OK")

        # 7) Holat kartochkasi SOXTA raqam ko'rsatmaydi.
        d = await (await c.get("/api/maintenance", headers=h)).json()
        assert set(d["holat"]) == {"commit", "ishlash", "mavzu", "baza", "model"}, d["holat"]
        # Mahalliyda Railway o'zgaruvchisi yo'q — commit `null`, ya'ni
        # panel qatorni umuman chizmaydi. Maketdagi «44003a8» qotirilgan edi.
        assert d["holat"]["commit"] is None or len(d["holat"]["commit"]) == 7
        # ⚠️ Faqat KO'RINADIGAN matn tekshiriladi: izohlarda «maketda
        # shunday qotirilgandi» deb yozilgan va u to'g'ri joyda turibdi.
        html = re.sub(r"<!--.*?-->", "",
                      (ROOT / "web" / "static" / "panel.html").read_text(encoding="utf-8"),
                      flags=re.S)
        for namuna in ("44003a8", "4s 12m", "gpt-5.6-luna", "-1002481…", "1 154"):
            assert namuna not in html, f"maketdagi qotirilgan «{namuna}» qolib ketgan"
        print("[7] holat kartochkasi haqiqiy; qotirilgan namuna qolmagan OK")

        # 8) Kuzatish: uchala amal ham RAM keshini yangilaydi.
        #    `get_watch_target()` har xabarda, bazaga bormasdan ishlaydi —
        #    kesh yangilanmasa panel «qo'shildi» deydi, xabarlar esa
        #    guruhga tushmaydi va buni hech narsa aytmaydi.
        AUDIT.clear(); KESH.clear(); GURUHGA.clear()
        SoxtaBot.xato = None
        assert (await c.post("/api/watch", headers=h,
                             json={"amal": "add", "kim": "@akmal"})).status == 200
        assert (await c.post("/api/watch", headers=h,
                             json={"amal": "remove", "kim": "511204873"})).status == 200
        assert (await c.post("/api/watch", headers=h,
                             json={"amal": "group", "guruh": "-100999"})).status == 200
        assert len(KESH) == 3, f"load_watch_cache() {len(KESH)} marta chaqirildi"
        for nom in ("watch_add", "watch_remove", "watch_group"):
            assert amal(nom), f"{nom} auditga tushmadi"
        # ⭐ Guruhga SINOV XABARI ketdi. Usiz noto'g'ri ID saqlanib,
        # ogohlantirishlar jimgina hech qayerga bormasdi.
        assert len(GURUHGA) == 1 and GURUHGA[0][0] == -100999, GURUHGA
        assert "Kuzatuv guruhi ulandi" in GURUHGA[0][1], GURUHGA[0][1]
        print("[8] kuzatuv: kesh yangilanadi, auditda, guruhga sinov xabari OK")

        # 9) Yo'q odam kuzatuvga qo'shilmaydi va guruh ID matn bo'lmaydi.
        KESH.clear()
        r = await c.post("/api/watch", headers=h, json={"amal": "add", "kim": "@yoq_odam"})
        assert r.status == 404, await r.text()
        assert not KESH, "topilmagan odamdan keyin ham kesh yangilandi"
        for yomon in ({"amal": "group", "guruh": "guruh"}, {"amal": "group", "guruh": ""},
                      {"amal": "add", "kim": ""}, {"amal": "hech_narsa"}):
            assert (await c.post("/api/watch", headers=h, json=yomon)).status in (400, 404), yomon
        print("[9] topilmagan odam va buzuq guruh ID rad etiladi OK")

        # 10) Admin qo'shish: menyu tugmasi DARHOL qo'yiladi.
        AUDIT.clear(); MENYU.clear()
        r = await c.post("/api/admins", headers=h, json={"amal": "add", "kim": "503992187"})
        assert r.status == 200, await r.text()
        assert MENYU == [(503992187, True)], MENYU
        assert amal("add_admin"), "add_admin auditga tushmadi"
        assert (await c.post("/api/admins", headers=h,
                             json={"amal": "add", "kim": "503992187"})).status == 400
        # ⚠️ @username QABUL QILINMAYDI: username egasi uni o'zgartirsa
        # nom boshqa odamga o'tib ketadi, admin huquqi esa qoladi.
        assert (await c.post("/api/admins", headers=h,
                             json={"amal": "add", "kim": "@aziz"})).status == 400
        print("[10] admin qo'shildi, «Panel» tugmasi darhol; @username rad etiladi OK")

        # 11) ⭐ O'CHIRISH QOIDASI — panel botdan ZAIFROQ eshik bo'lmasin.
        #     Qoida `_check_can_remove_admin()` da, va u AYNAN Telegram
        #     ekrani ishlatadigan funksiya. Web uni QAYTA YOZSA, ikkisi
        #     bir kuni ajralib ketardi.
        MENYU.clear()
        r = await c.post("/api/admins", headers=h, json={"amal": "remove", "kim": str(ADMIN)})
        assert r.status == 403, "admin o'zini o'chira oldi"
        assert not MENYU, "rad etilgan o'chirishda menyu tugmasi olindi"
        r = await c.post("/api/admins", headers=h, json={"amal": "remove", "kim": str(SUPER)})
        assert r.status == 403, "superadmin panel orqali o'chirildi"
        r = await c.post("/api/admins", headers=h, json={"amal": "remove", "kim": "999"})
        assert r.status == 403, "admin bo'lmagan odam «o'chirildi»"
        r = await c.post("/api/admins", headers=h, json={"amal": "remove", "kim": str(BOSHQA)})
        assert r.status == 200, await r.text()
        assert MENYU == [(BOSHQA, False)], "o'chirilgan adminda «Panel» tugmasi qoldi"
        assert amal("remove_admin"), "remove_admin auditga tushmadi"
        # Manba bo'yicha: web O'Z tekshiruvini yozmaganiga ishonch.
        src = kod(ROOT / "web" / "api.py")
        assert "_check_can_remove_admin" in src, (
            "web o'chirish qoidasini QAYTA YOZGAN — bitta darvoza bo'lishi kerak")
        print("[11] ⭐ o'chirish qoidasi Telegram bilan BITTA darvozadan o'tadi OK")

        # 12) ⚠️ Superadmin `admins` jadvalida BO'LMASA ham ro'yxatda
        #     ko'rinsin. Jonli bazada (2026-09-15) aynan shunday: jadval
        #     bo'sh, superadmin esa bor — `get_admins()` ga tayangan
        #     ekran «panelga hech kim kira olmaydi» deb turardi, holbuki
        #     bitta odam kira oladi. Ro'yxat huquq tekshiruvi bilan
        #     BIR XIL to'plamni ko'rsatishi shart.
        HOLAT["adminlar"] = set()
        d = await (await c.get("/api/admins", headers=h)).json()
        assert [r["user_id"] for r in d["rows"]] == [SUPER], d
        assert d["rows"][0]["super"] is True and d["rows"][0]["ozim"] is True
        src2 = kod(ROOT / "web" / "api.py")
        gavda = src2.split("async def admins(")[1].split("async def ")[0]
        assert "get_panel_admins" in gavda, (
            "ro'yxat `get_admins()` dan olinyapti — superadmin ko'rinmaydi")
        print("[12] superadmin `admins` jadvalida bo'lmasa ham ro'yxatda ko'rinadi OK")

        # 13) Manba bo'yicha: har bir yangi marshrut `@admin_only` bilan.
        daraxt = ast.parse(src)
        dekorator = {
            f.name: any(getattr(d, "id", "") == "admin_only" for d in f.decorator_list)
            for f in ast.walk(daraxt) if isinstance(f, ast.AsyncFunctionDef)
        }
        marshrutlar = set()
        for n in ast.walk(daraxt):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr in ("add_get", "add_post", "add_delete")):
                marshrutlar.add(n.args[1].id)
        qoriqsiz = sorted(m for m in marshrutlar if not dekorator.get(m))
        assert not qoriqsiz, f"@admin_only yo'q: {qoriqsiz}"
        assert len(marshrutlar) == 31, f"marshrutlar soni kutilgandan boshqa ({len(marshrutlar)} ta)"
        print(f"[13] {len(marshrutlar)} ta marshrutning hammasi @admin_only bilan OK")

        # ── 14) ⭐ TELEGRAM RAD ETSA GURUH SAQLANMAYDI ──────────────
        # `refund` bilan bir xil qoida: Telegram avval, baza keyin.
        # Aks holda bazada yangi guruh turardi-yu, u yerga hech narsa
        # yetmasdi — va buni HECH NARSA aytmasdi.
        for xato, kutilgan in (
                ("Bad Request: chat not found", "topilmadi"),
                ("Forbidden: bot is not a member of the group chat", "guruhda emas"),
                ("Bad Request: have no rights to send a message", "huquqi yo'q")):
            AUDIT.clear(); KESH.clear(); GURUHGA.clear()
            SoxtaBot.xato = xato
            r = await c.post("/api/watch", headers=h,
                             json={"amal": "group", "guruh": "-100777"})
            assert r.status == 400, await r.text()
            d = await r.json()
            assert kutilgan in d["error"], (xato, d)
            assert not KESH, "Telegram rad etdi, kesh esa yangilandi"
            assert not amal("watch_group"), "rad etilgan guruh auditga tushdi"
        # Noma'lum xato ham JIM YUTILMAYDI — Telegram matnini ko'rsatadi.
        SoxtaBot.xato = "Bad Request: something brand new"
        d = await (await c.post("/api/watch", headers=h,
                                json={"amal": "group", "guruh": "-100777"})).json()
        assert "something brand new" in d["error"], d
        SoxtaBot.xato = None
        print("[14] Telegram rad etsa guruh saqlanmaydi, sabab tushunarli OK")

        # ── 15) ⭐ GURUH XATOSI RO'YXATI BITTA JOYDA ───────────────
        # Uchta iste'molchi: panel sinovi, ogohlantirish yuboruvchi va
        # kuzatuv nusxalovchi. Ro'yxat ularning biriga ham nusxalanmasin
        # — bu faylda beshta yorliq xaritasi aynan shunday nusxalanib,
        # HAR BIRI bir-biridan farq qilib ketgan edi (`ban` va
        # `ban_user`, «Fayl» va «Fayllar»).
        # ⚠️ IZOHLAR TASHLANADI (`tests/_manba.py`). Ro'yxat kodda emas,
        # uni TUSHUNTIRAYOTGAN izohda ham uchraydi — izohlarni qoldirsak
        # test o'z hujjatimizni nusxa deb o'qirdi. Shu tekshiruvning
        # birinchi ishga tushishida AYNAN shunday bo'ldi.
        import pathlib
        ildiz = pathlib.Path(__file__).resolve().parent.parent
        for nisbiy in ("web/api.py", "handlers/admin/daily.py",
                       "handlers/helpers.py"):
            matn = kod(ildiz / nisbiy)
            assert "chat not found" not in matn, (
                nisbiy + ": guruh xatolari ro'yxati nusxalangan — "
                "`core/config.py::GURUH_XATOSI` dan o'qilsin")

        # ⛔️ Ajratish ma'noli: guruh darajasidagi xato adminni chaqiradi,
        # xabarga xos xato esa keyingi xabarda o'zi tuzaladi.
        assert config.guruh_xato_sababi(
            "Forbidden: bot was kicked from the group chat")
        assert config.guruh_xato_sababi("Bad Request: message is too long") is None
        assert config.guruh_xato_sababi("") is None
        print("[15] guruh xatolari ro'yxati bitta joyda, ajratish to'g'ri OK")

    config.apply_limit_overrides({})
    print("\nweb settings: barcha tekshiruvlar o'tdi (15/15).")


if __name__ == "__main__":
    asyncio.run(main())
