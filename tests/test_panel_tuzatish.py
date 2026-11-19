"""Admin panel auditi (2026-11-19) topgan xatolarning qo'riqchisi.
Ishga tushirish: PYTHONIOENCODING=utf-8 python tests/test_panel_tuzatish.py

Tarmoq, baza va Telegram kerak emas — hammasi almashtiriladi. SQL'i
lokal pgserver'da ham tekshirilgan (audit stendi).

Audit panelni haqiqiy brauzerda, haqiqiy kod va lokal Postgres bilan
bosib chiqdi va testlar ko'rmagan xatolarni topdi. Har bir tekshiruv
o'sha xatolardan biriga bog'langan — xato qaytsa, aynan shu raqam
yiqiladi:

  1-to'plam (jiddiy):
    [1]  profil API'si ismni (`tg_ism`) qaytaradi, «Mavjud emas» emas
    [2]  qidiruv ism bo'yicha ham, `%` / `_` oddiy belgi
    [3]  «Eng faol» bitta odamni bir necha qatorga bo'lmaydi
    [4]  ID diapazoni: 0, manfiy va BIGINT'dan katta son — 400, 500 emas
    [5]  admin faqat botga yozgan odamdan bo'ladi
    [6]  profil: username'siz odam — `username: null`, ism keladi
    [7]  ta'til matni HTML sifatida emas, oddiy matn bo'lib ketadi
    [8]  panel: avatar shaxsiy nomdan, admin tasdig'ida kimligi
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _manba import kod, js_kod

os.environ["BOT_TOKEN"] = "123456:TEST-TOKEN-FOR-PANEL-TUZATISH"

import asyncio
import pathlib
import re

from aiohttp.test_utils import TestClient, TestServer

import web
from web import api, auth
from db import database

ROOT = pathlib.Path(__file__).resolve().parent.parent
ADMIN = 641382901

CHAQIRUV = []        # soxta bazaga yozuvlar
PROFILLAR = {}       # uid -> get_full_user_profile javobi (haqiqiy shaklda)


def check(n, nom, shart, tafsilot=""):
    assert shart, f"[{n}] {nom} — YIQILDI {tafsilot}"
    print(f"[{n}] {nom} OK")


def funksiya(manba: str, nom: str) -> str:
    """`async def nom(` dan keyingi `def` gacha bo'lgan qism."""
    bosh = re.search(rf"\n(?:async )?def {nom}\(", manba)
    assert bosh, f"{nom} topilmadi"
    keyin = re.search(r"\n(?:@|async def |def )", manba[bosh.end():])
    return manba[bosh.start(): bosh.end() + (keyin.start() if keyin else len(manba))]


def soxta_baza():
    db = api.database_module

    async def is_admin(uid):
        return uid == 900000002

    async def is_superadmin(uid):
        return uid == ADMIN

    async def get_full_user_profile(uid):
        # ⚠️ Shakl HAQIQIY funksiyaniki: username yo'q bo'lsa None,
        # `tg_ism` kaliti bor (CLAUDE.md «A fake must return the keys…»).
        return PROFILLAR.get(uid)

    async def add_admin(uid, username=None):
        CHAQIRUV.append(("add_admin", uid, username))

    async def log_admin_action(admin_id, action, target=None, details=None):
        CHAQIRUV.append(("audit", action, target))

    async def get_user_payments(uid, limit=10):
        return []

    async def get_referral_progress(uid):
        return {"invited": 0, "qualified": 0, "rewarded": 0}

    for nom, fn in list(locals().items()):
        if callable(fn) and nom != "db":
            setattr(db, nom, fn)


async def main():
    db_manba = kod(ROOT / "db" / "database.py")
    api_manba = kod(ROOT / "web" / "api.py")

    # 1) get_full_user_profile — lug'at QO'LDA yig'iladi, ya'ni yangi
    #    ustun o'z-o'zidan kelmaydi. Audit: panel profilida ism hech
    #    chiqmasdi; username'siz odam esa «@Mavjud emas» bo'lib chizilardi.
    f = funksiya(db_manba, "get_full_user_profile")
    check(1, "profil lug'atida tg_ism bor, «Mavjud emas» yo'q",
          "'tg_ism'" in f and "Mavjud emas" not in f)

    # 2) Qidiruv: ism bo'yicha ham, LIKE joker belgilari ekranlangan.
    assert database.like_ekranla(None) is None
    assert database.like_ekranla("dilshod_a") == "dilshod\\_a"
    assert database.like_ekranla("100%") == "100\\%"
    assert database.like_ekranla("a\\b") == "a\\\\b"
    lu = funksiya(db_manba, "list_users")
    check(2, "qidiruv tg_ism bo'yicha, % _ \\ ekranlangan",
          re.search(r"tg_ism\s+ILIKE", lu) and lu.count("ESCAPE") >= 2
          and "like_ekranla(frag)" in lu)

    # 3) «Eng faol»: guruh FAQAT user_id bo'yicha. `user_activity.username`
    #    yozilgan paytdagi qiymat — u bo'yicha guruhlansa bitta odam 2-3
    #    qatorga bo'linardi (audit: 17 so'rovli odam 3-, 4-, 6-o'rinda).
    tu = funksiya(db_manba, "top_users")
    guruhlar = re.findall(r"GROUP BY ([^\n]+)", tu)
    check(3, "top_users faqat user_id bo'yicha guruhlaydi, adminlarsiz, nom users'dan",
          guruhlar == ["user_id"] and "_ODDIY_USER" in tu and "JOIN users" in tu
          and "most_active" not in funksiya(db_manba, "activity_stats"),
          guruhlar)

    # 4) ID diapazoni — `int()` yetmaydi: 21 xonali son Postgres'ga
    #    sig'maydi va 500 «server xatosi» berardi.
    yaroqsiz = ["0", "-5", "abc", "", None, str(api.BIGINT_MAX + 1),
                "999999999999999999999"]
    assert all(api._user_id(v) is None for v in yaroqsiz), \
        [v for v in yaroqsiz if api._user_id(v) is not None]
    assert api._user_id("123") == 123 and api._user_id(api.BIGINT_MAX) == api.BIGINT_MAX
    check(4, "_user_id: 0, manfiy, son emas va BIGINT'dan katta — None", True)

    soxta_baza()

    async def ha(uid):
        return True
    web.huquq_bormi = ha
    auth.huquq_bormi = ha
    from services import menu as menu_module

    async def soxta_menyu(uid, is_admin):
        CHAQIRUV.append(("menyu", uid, is_admin))
    menu_module.sync_menu_button = soxta_menyu

    h = {"Cookie": f"{auth.COOKIE_NAME}={auth.sessiya_yasa(ADMIN)}"}
    PROFILLAR[5000000002] = {"user_id": 5000000002, "username": None, "tg_ism": "Ali",
                             "plan_type": "free", "premium_until": None,
                             "is_banned": False, "total_messages": 3}

    async with TestClient(TestServer(web.build_app())) as c:
        async def qosh(kim):
            CHAQIRUV.clear()
            r = await c.post("/api/admins", headers=h, json={"amal": "add", "kim": kim})
            return r.status, (await r.json()).get("error"), list(CHAQIRUV)

        # 5) Admin qo'shish: faqat botga yozgan, musbat ID.
        natija = {k: await qosh(k) for k in
                  ["0", "-5", "99999999999999999999", "123456789", "@ali",
                   str(ADMIN), "5000000002"]}
        for k in ["0", "-5", "99999999999999999999"]:
            assert natija[k][0] == 400 and not natija[k][2], (k, natija[k])
        assert natija["123456789"][0] == 404 and not natija["123456789"][2], natija["123456789"]
        assert natija["@ali"][0] == 400 and not natija["@ali"][2]
        assert natija[str(ADMIN)][0] == 400, "superadmin qayta admin qilindi"
        assert natija["5000000002"][0] == 200, natija["5000000002"]
        assert ("add_admin", 5000000002, None) in natija["5000000002"][2], natija["5000000002"]
        check(5, "admin: 0/manfiy/ulkan — 400, botda yo'q — 404, superadmin — 400, bor — qo'shildi", True)

        # 6) Profil va URL'dagi ID.
        r = await c.get("/api/users/5000000002", headers=h)
        d = await r.json()
        assert r.status == 200 and d["username"] is None and d["tg_ism"] == "Ali", d
        for yomon in ["0", "-5", "99999999999999999999"]:
            r = await c.get(f"/api/users/{yomon}", headers=h)
            assert r.status == 400, (yomon, r.status)
        check(6, "profil: username null + ism; yaroqsiz ID — 400 (500 emas)", True)

    # 7) Ta'til matni — admin yozgan oddiy matn. Bot standart HTML
    #    rejimida: «Bot < 1 soat» kabi matn rad etilib, ta'til paytida
    #    hech kim javob olmasdi.
    main_manba = kod(ROOT / "main.py")
    gate = funksiya(main_manba.replace("\n    async def", "\nasync def"),
                    "handle_maintenance_notice")
    biz = kod(ROOT / "handlers" / "biznes.py")
    check(7, "ta'til matni parse_mode=None / html=False bilan yuboriladi",
          "parse_mode=None" in gate and "_egasiga(dm, notice, html=False)" in biz)

    # 8) Panel: avatar SHAXSIY nomdan (nomsizga «F» emas, odam belgisi);
    #    admin tasdig'ida kimligi — avval /api/users/<id> so'raladi.
    js = js_kod((ROOT / "web" / "static" / "panel.js").read_text(encoding="utf-8"))
    shaxs = re.search(r"function shaxs\(u\) \{([^}]*)\}", js)
    adm = js[js.index('$("ad-qosh")'): js.index('$("ad-qosh")') + 1600]
    # `bosh()` — HAR QANDAY yozuvdagi harf (\p{L}); faqat lotin/kirill
    # bo'lsa emoji yoki arabcha ism avatari «?» bo'lib chiqardi.
    bosh = js[js.index("function bosh("): js.index("function bosh(") + 700]
    check(8, "panel: avatar shaxs() dan, bosh() Unicode harf, admin tasdig'idan oldin odam topiladi",
          shaxs and '"ID:"' in shaxs.group(1)
          and "avatar(shaxs(u)" in js and "bosh(shaxs(d))" in js
          and "avatar(nomi(" not in js
          and "\\p{L}" in bosh and '"?"' not in bosh
          and adm.index('"/api/users/"') < adm.index("tasdiq("))

    print("\npanel tuzatish: barcha tekshiruvlar o'tdi (8/8).")


if __name__ == "__main__":
    asyncio.run(main())
