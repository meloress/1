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

  2-to'plam (o'rta):
    [9]  sovg'a: 20 tadan ko'p — rad (jimgina kesilmaydi), tasdiqda soni va kuni
    [10] brauzer: `tg` faqat `initData` bo'lsa — zaxira Saqlash va chiqish ishlaydi
    [11] karta: tasdiqda yangi raqam to'liq, uzun ism — to'g'ri xato, maydonlar ustma-ust
    [12] bugungi daromad — ikkala tomon Toshkent sanasi (UTC sessiyada 05:00 emas)
    [13] grafik: kenglik haqiqiy, ResizeObserver, tooltip kartada qisiladi
    [14] navigatsiya: 5 bo'lim, ichma-ich kartochka yo'q, faol tab ko'rinadi
    [15] kuzatuv guruhi faqat manfiy ID; ulkan ID — 400; banner Kuzatuv tabida ham
    [16] CSV: botni bloklaganlar ham, ism ustuni ham (formula himoyasi bilan)
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

    async def get_user_by_identifier(token):
        CHAQIRUV.append(("topish", token))
        return 5000000002 if token == "5000000002" else None

    async def set_user_premium(uid, days, **kw):
        CHAQIRUV.append(("premium", uid, days))

    async def list_users(**kw):
        CHAQIRUV.append(("list_users", kw))
        return {"rows": [
            {"user_id": 1, "username": "faol", "tg_ism": '=HYPERLINK("http://x","bos")',
             "plan_type": "free", "is_banned": False, "is_active": True},
            {"user_id": 2, "username": None, "tg_ism": "Ketgan", "plan_type": "free",
             "is_banned": False, "is_active": False},
        ], "jami": 2, "sanoq": {}}

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

        # 9) Sovg'a: 21 kishi — HECH KIMGA berilmaydi va sababi aytiladi.
        #    Ilgari `[:SOVGA_MAX]` 21-chisini jimgina tashlab, «20 tasiga
        #    berildi» derdi.
        CHAQIRUV.clear()
        kimlar = " ".join(str(5000000000 + i) for i in range(api.SOVGA_MAX + 1))
        r = await c.post("/api/giveaway", headers=h, json={"kimlar": kimlar, "kun": 30})
        xato = (await r.json()).get("error") or ""
        assert r.status == 400 and str(api.SOVGA_MAX + 1) in xato, (r.status, xato)
        assert not CHAQIRUV, f"rad etilgan sovg'a bazaga tegdi: {CHAQIRUV}"
        check(9, "sovg'a: 20 tadan ko'p — 400, hech kimga berilmaydi", True)

        # 15) Kuzatuv guruhi: musbat ID — shaxsiy chat (hamma kuzatilgan
        #     yozishma o'sha odamga ketardi); ulkan son — 400, 500 emas.
        #     Ikkalasi ham sinov xabaridan OLDIN rad etiladi.
        for guruh in ["12345", "-1001234567890123456789", "0"]:
            r = await c.post("/api/watch", headers=h, json={"amal": "group", "guruh": guruh})
            assert r.status == 400, (guruh, r.status)
        db_m = kod(ROOT / "db" / "database.py")
        gi = funksiya(db_m, "get_user_by_identifier")
        check(15, "kuzatuv guruhi faqat manfiy; get_user_by_identifier BIGINT'ni tekshiradi",
              "2 ** 63" in gi and "except ValueError" in gi)

        # 16) CSV: botni bloklaganlar ham (`nofaollar_ham=True`), ism
        #     ustuni bor va u ham formula himoyasidan o'tadi.
        ketgan = {}

        async def soxta_hujjat(uid, baytlar, nom, izoh):
            ketgan["matn"] = baytlar.decode("utf-8")
            return True
        api._hujjat = soxta_hujjat
        CHAQIRUV.clear()
        r = await c.post("/api/export?tur=users", headers=h)
        assert r.status == 200, await r.text()
        lu_kw = [x[1] for x in CHAQIRUV if x[0] == "list_users"]
        satrlar = ketgan["matn"].lstrip("﻿").splitlines()
        sarlavha = satrlar[0].split(";")
        assert lu_kw and lu_kw[0].get("nofaollar_ham") is True, lu_kw
        assert "ism" in sarlavha and "botni_bloklagan" in sarlavha, sarlavha
        assert "'=HYPERLINK" in satrlar[1], satrlar[1]
        assert satrlar[2].split(";")[sarlavha.index("botni_bloklagan")] == "ha", satrlar[2]
        check(16, "CSV: bloklaganlar ham, ism ustuni, formula zararsiz", True)

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

    soz = js_kod((ROOT / "web" / "static" / "soz.js").read_text(encoding="utf-8"))
    html = (ROOT / "web" / "static" / "panel.html").read_text(encoding="utf-8")
    css = (ROOT / "web" / "static" / "panel.css").read_text(encoding="utf-8")

    # 10) `tg` — faqat Telegram ichida. Skript brauzerda ham WebApp'ni
    #     yaratadi: `if (tg)` u yerda rost bo'lib, limitlarni saqlab
    #     bo'lmasdi va «Chiqish» ma'lumotni ekranda qoldirardi.
    check(10, "tg faqat initData bo'lsa",
          re.search(r"var tg = WA && WA\.initData \? WA : null;", js) is not None)

    # 11) Karta: tasdiqda yangi raqam TO'LIQ; uzun ism — o'z xabari.
    xato = database.clean_karta("8600123412341234", "A" * 300)[2]
    gift = js[js.index('$("g-yubor")'): js.index('$("g-yubor")') + 1500]
    check(11, "karta tasdig'ida raqam, uzun ism xabari, maydonlar ustma-ust; sovg'a tasdig'ida soni/kuni",
          "S.savol.karta(raqamlar" in js and "50 belgi" in xato
          and 'class="forma ustma" id="k-forma"' in html
          and "S.savol.sovga(soni, kun)" in gift
          and gift.index("META.sovga_max") < gift.index("tasdiq("))

    # 12) Bugungi daromad: `timestamptz >= date` sessiya zonasida
    #     o'giriladi (server UTC) va chegara 05:00 bo'lib qolardi.
    rs = funksiya(db_manba, "revenue_stats")
    check(12, "bugungi daromad ikkala tomonda Toshkent sanasi",
          re.search(r"created_at >= \(NOW\(\) AT TIME ZONE 'Asia/Tashkent'\)::date", rs) is None
          and re.search(r"\(created_at AT TIME ZONE 'Asia/Tashkent'\)::date\s*=\s*"
                        r"\(NOW\(\) AT TIME ZONE 'Asia/Tashkent'\)::date", rs) is not None)

    # 13) Grafik: kenglik qotirilmagan — telefonda yozuv 6-7px bo'lardi.
    ch = js[js.index("function chizuvchi("): js.index("function chizuvchi(") + 6000]
    check(13, "grafik: haqiqiy kenglik, ResizeObserver, tooltip qisiladi",
          "var W = 640, PAD_L" not in js and 'setAttribute("viewBox"' in ch
          and "ResizeObserver" in ch and "Math.max(yarim" in ch)

    # 14) Navigatsiya: «Boshqa bo'limlar» zaxirasi yo'q (test_web_panel 2
    #     beshala bo'limni tekshiradi), Faollik panelidagi kartochkalar
    #     ICHMA-ICH emas, faol ichki tab ko'rinishga aylantiriladi.
    faollik = html[html.index('<div class="pane on" data-pane="activity">'):
                   html.index('<div class="pane" data-pane="audit">')]
    # Har bir kartochka qaysi CHUQURLIKDA ochiladi — hammasi bir xil
    # bo'lishi shart (grid2 ning bolalari). Ilgari birinchisi yopilmagan
    # edi va ikkinchisi bir daraja ichkarida ochilardi.
    chuqurlik, kartalar = 0, []
    for t in re.finditer(r'<(/?)div\b([^>]*)>', faollik):
        if t.group(1):
            chuqurlik -= 1
        else:
            if 'class="card"' in t.group(2):
                kartalar.append(chuqurlik)
            chuqurlik += 1
    ichma_ich = len(set(kartalar)) != 1 or len(kartalar) != 4
    check(14, "5 bo'lim, ichma-ich kartochka yo'q, faol tab scrollIntoView",
          "faqat-tel" not in html and "faqat-tel" not in css and not ichma_ich
          and "scrollIntoView" in js[js.index("function showPane("): js.index("function navigatsiya(")]
          and "report:" in soz and "journal:" not in soz)

    print("\npanel tuzatish: barcha tekshiruvlar o'tdi (16/16).")


if __name__ == "__main__":
    asyncio.run(main())
