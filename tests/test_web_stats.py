"""Web paneldagi Boshqaruv va Statistika raqamlari uchun tekshiruv.
Ishga tushirish: python tests/test_web_stats.py

Tarmoq va baza kerak emas: `database` chaqiruvlari soxta ma'lumot
qaytaradi.

Eng muhimi — 8-tekshiruv: 3-bosqichning «tayyor» mezoni *raqamlar
Telegram paneli bilan bir xil* edi. Bu yerda ikkala ekran ham BITTA
soxta bazadan o'qiydi va natijalari solishtiriladi. Agar kimdir web
uchun alohida so'rov yozib qo'ysa, ikki raqam ajraladi va shu test
yiqiladi — yonma-yon qo'lda solishtirib o'tirmasdan.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["BOT_TOKEN"] = "123456:TEST-TOKEN-FOR-WEB-STATS"

import asyncio
import datetime
import pathlib
import re

from aiohttp.test_utils import TestClient, TestServer

import web
from web import api, auth
from core.config import TARIF_NOMI, TOKEN_KUNLIK_GRANT

ROOT = pathlib.Path(__file__).resolve().parent.parent
TASHKENT = datetime.timezone(datetime.timedelta(hours=5))

# ── Soxta baza ────────────────────────────────────────────────────
# Kunlar ATAYLAB tirqishli: 7 kunning faqat uchtasida amal bor.
BUGUN = datetime.datetime.now(TASHKENT).date()

SOXTA_ACTIVITY = {
    "total_users": 1204,
    "free_count": 1187,
    "pro_count": 14,
    "premium_count": 3,
    "ban_count": 0,
    "kunlar": 7,
    "most_active_30days": {"user_id": 641382905, "username": "dilshod_a", "activity_count": 312},
    "most_active_today": {"user_id": 641382905, "username": "dilshod_a", "activity_count": 42},
    "last_user": {"user_id": 5, "username": "yangi", "created_at": None},
    "daily_activity": [
        {"day": BUGUN - datetime.timedelta(days=4), "total": 100, "uniq_users": 10},
        {"day": BUGUN - datetime.timedelta(days=1), "total": 200, "uniq_users": 20},
        {"day": BUGUN, "total": 342, "uniq_users": 30},
    ],
    "type_breakdown": [
        ("text_message", 1842), ("photo_message", 214),
        ("guest_text_message", 400), ("voice_message", 143),
        ("guest_voice_message", 57), ("file_task", 96), ("research", 12),
    ],
}

SOXTA_KUNLIK = {
    "new_users": 9, "total_users": 1204, "active_users": 80, "actions": 342,
    "sales": 2, "stars": 1850, "errors": 11, "pro_users": 14,
    "prev_actions": 300, "active_7d": 103, "pro_expiring": 2,
    "top_types": [("text_message", 200), ("guest_text_message", 90), ("voice_message", 52)],
    # ⚠️ 24 soatlik TO'LIQ kesim. `actions` (342) shu ro'yxatning
    # yig'indisi — `daily_report_stats()` uni aynan shundan hisoblaydi.
    # `start` ro'yxatda ATAYLAB bor: u `ACTIVITY_TYPES` da yo'q va
    # panelda «Boshqa» qatoriga tushishi kerak.
    "types_24h": [("text_message", 200), ("guest_text_message", 90),
                  ("voice_message", 52)],
}

SOXTA_DAROMAD = {"stars_today": 1850, "stars_30d": 24300, "stars_total": 186700,
                 "sales_30d": 17, "refunds": 2, "by_plan": [(30, 12)]}


def soxta_bazani_qoy(modul, **ustidan):
    """Soxta bazani modulga qo'yadi (`web.api` uni shundan o'qiydi)."""
    async def activity_stats(kunlar=7):
        d = dict(SOXTA_ACTIVITY)
        d["kunlar"] = kunlar
        return d

    async def daily_report_stats():
        return dict(SOXTA_KUNLIK)

    async def revenue_stats():
        return dict(SOXTA_DAROMAD)

    # ⚠️ Token hisobi: bugun grantning 74% i yeyilgan, kecha OSHGAN.
    # Ikkala holat ham panelda boshqacha ko'rinishi kerak.
    async def token_stats(kunlar=30):
        import datetime as _dt
        from web.api import TIMEZONE as _TZ
        bugun = _dt.datetime.now(_TZ).date()
        return {"kunlik": [
            {"kun": bugun, "kirish": 1_600_000, "chiqish": 240_000,
             "keshdan": 976_000, "raund": 1180},
            {"kun": bugun - _dt.timedelta(days=1), "kirish": 2_400_000,
             "chiqish": 210_000, "keshdan": 1_200_000, "raund": 1610},
        ], "eng_qimmat": []}

    async def top_users(days, limit):
        return [
            {"user_id": 641382905, "username": "dilshod_a", "activity_count": 312},
            {"user_id": 512004119, "username": None, "activity_count": 241},
        ][:limit]

    async def recent_errors(limit=15, offset=0):
        return [{
            "id": 1, "kind": "timeout",
            # ⚠️ Begona matn: xato xabari foydalanuvchi yozganidan
            # kelib chiqishi mumkin, ya'ni u ishonchsiz.
            "message": "<script>alert(1)</script> javob kelmadi",
            "user_id": 641382905,
            "created_at": datetime.datetime(2026, 9, 15, 14, 12, tzinfo=datetime.timezone.utc),
        }][:limit]

    async def error_summary():
        return {"day": 11, "week": 40, "total": 100, "users_day": 5, "kinds": [("timeout", 6)]}

    async def get_maintenance():
        return {"active": False, "message": "..."}

    joy = modul.database_module
    for nom, fn in list(locals().items()):
        if nom in ("modul", "ustidan", "joy", "nom", "fn"):
            continue
        setattr(joy, nom, ustidan.get(nom, fn))


async def kir(client):
    """Darvozadan o'tish — endpointlar `@admin_only` bilan yopiq."""
    async def ha(user_id):
        return True
    web.huquq_bormi = ha
    auth.huquq_bormi = ha
    return {"Cookie": f"{auth.COOKIE_NAME}={auth.sessiya_yasa(1)}"}


async def main():
    soxta_bazani_qoy(api)
    async with TestClient(TestServer(web.build_app())) as client:
        # 1) Darvoza: cookie'siz bironta raqam chiqmasin.
        for yol in ("/api/overview", "/api/stats"):
            r = await client.get(yol)
            assert r.status == 401, f"{yol} cookie'siz ochiq: {r.status}"
        print("[1] /api/overview va /api/stats cookie'siz 401 qaytaradi OK")

        h = await kir(client)
        ov = await (await client.get("/api/overview", headers=h)).json()
        st = await (await client.get("/api/stats", headers=h)).json()

        # 2) Grafik HAR DOIM 7 kun. Bazada faqat amal bo'lgan kunlar
        #    bor — tirqishlarni tashlab ketsak grafik "yaxshi"
        #    ko'rinardi, chunki tushish ko'rinmasdi.
        assert len(ov["kunlar"]) == 7, ov["kunlar"]
        sonlar = [k["soni"] for k in ov["kunlar"]]
        assert sonlar.count(0) == 4, f"bo'sh kunlar nol bilan to'ldirilmagan: {sonlar}"
        assert sonlar[-1] == 342, "oxirgi kun bugungi bo'lishi kerak"
        kunlar = [k["kun"] for k in ov["kunlar"]]
        assert kunlar == sorted(kunlar), "kunlar tartibda emas"
        print("[2] grafik 7 kunni to'liq beradi, jim kun 0 bo'ladi OK")

        # 3) O'zgarish foizi: kecha nol bo'lsa «+100%» YOLG'ON bo'lardi.
        assert ov["kpi"]["sorovlar"]["ozgarish"] == 14.0, ov["kpi"]["sorovlar"]
        soxta_bazani_qoy(api, daily_report_stats=_nol_kecha)
        ov2 = await (await client.get("/api/overview", headers=h)).json()
        assert ov2["kpi"]["sorovlar"]["ozgarish"] is None, \
            "kecha ma'lumot yo'qda o'zgarish ko'rsatilyapti"
        soxta_bazani_qoy(api)
        print("[3] kecha ma'lumot bo'lmasa o'zgarish foizi ko'rsatilmaydi OK")

        # 4) Nolga bo'lish: «0%» va «ma'lumot yo'q» ajratilgan.
        assert api._foiz(5, 0) is None and api._foiz(0, 10) == 0
        print("[4] nolga bo'lish «—» beradi, haqiqiy nol «0%» bo'lib qoladi OK")

        # 5) Xato matni XOM holda uzatiladi (kesilgan), panel uni
        #    `xavfsiz()` bilan ekranlaydi — ikkalasi ham tekshiriladi.
        x = ov["xatolar"][0]
        # Vaqt ISO-8601 bo'lib, TOSHKENT siljishi bilan keladi;
        # formatlash panelda (`sana()` / `nisbiy()`), chunki bitta sana
        # uch xil joyda uch xil uzunlikda ko'rsatiladi.
        assert x["tur"] == "timeout" and x["vaqt"] == "2026-09-15T19:12:00+05:00", x
        js = (ROOT / "web" / "static" / "panel.js").read_text(encoding="utf-8")
        assert "function xavfsiz(" in js, "panel.js da ekranlash funksiyasi yo'q"
        # `username` `nom` o'zgaruvchisi orqali o'tadi, shuning uchun
        # ro'yxatda o'sha turibdi.
        for maydon in ("x.matn", "x.tur", "x.user", "nom", "t.nom", "u.izoh"):
            assert f"xavfsiz({maydon})" in js, f"{maydon} ekranlanmagan — panelga skript kiritilishi mumkin"

        # ⚠️ Qoida so'zma-so'z satr bo'yicha emas, MAZMUNAN tekshiriladi:
        # `username` HTML yasayotgan qatorga (ya'ni ichida `<` bor
        # qatorga) `xavfsiz()` siz tushmasligi kerak. Ilgari bu yerda
        # aniq bir ifoda qidirilardi va `nomi()` yordamchisi qo'shilishi
        # bilanoq test yolg'ondan yiqildi — kod esa to'g'ri edi.
        for n, qator in enumerate(js.splitlines(), 1):
            if ".username" in qator and "<" in qator and "xavfsiz(" not in qator:
                raise AssertionError(
                    f"panel.js:{n} — username HTML ga ekranlanmasdan qo'yilgan: {qator.strip()}")
        print("[5] vaqt Toshkentga o'girilgan, begona matn panelda ekranlanadi OK")

        # 6) ⭐ USTUNLAR YIG'INDISI = UMUMIY SON.
        #
        # ⚠️ Bu tekshiruv aynan jonli shikoyatdan tug'ildi: ekranda
        # «24 soatdagi so'rovlar 150» yozilib turardi, pastdagi «So'rov
        # turlari» ustunlari esa qo'shilganda 142 berardi. Ikki sabab
        # bor edi va ikkalasi ham jimgina ishlardi — `ACTIVITY_TYPES` da
        # yo'q tur (`start`) tashlab ketilardi, va so'rov `LIMIT 5` edi.
        # Admin bunday farqni ko'rsa butun paneldagi raqamga ishonmay
        # qoladi, va haq bo'ladi.
        nomlar = [t["nom"] for t in ov["turlar"]]
        assert "Matn" in nomlar and "Matn · mehmon" in nomlar, nomlar
        assert not any("_message" in n for n in nomlar), f"xom tur nomi: {nomlar}"
        assert sum(t["soni"] for t in ov["turlar"]) == ov["kpi"]["sorovlar"]["qiymat"], (
            f"ustunlar yig'indisi umumiy songa teng emas: {ov['turlar']}")

        # Ro'yxatda yo'q tur YO'QOLMAYDI — «Boshqa» ga qo'shiladi.
        b = api._turlar([("start", 6), ("text_message", 1)])
        assert b == [{"nom": "Matn", "soni": 1},
                     {"nom": "Boshqa", "soni": 6, "boshqa": True}], b
        # Ortib qolgani ham «Boshqa» ga: ro'yxat cheksiz uzaymaydi,
        # lekin yig'indi baribir saqlanadi.
        kop = [(t, 10) for t in ("text_message", "photo_message", "voice_message",
                                 "document_message", "location_message",
                                 "file_task", "research")]
        c = api._turlar(kop)
        assert len(c) == api.TUR_KORSAT + 1 and c[-1]["nom"] == "Boshqa", c
        assert sum(t["soni"] for t in c) == 70, c
        print("[6] turlar yig'indisi umumiy songa teng, notanishi «Boshqa» ga tushadi OK")

        # 7) Statistika ekrani: ulushlar va konversiya.
        jami_amal = sum(c for _t, c in SOXTA_ACTIVITY["type_breakdown"])
        guest = 400 + 57
        assert st["kpi"]["mehmon_ulush"] == round(guest / jami_amal * 100)
        assert st["kpi"]["konversiya"] == round(17 / 1204 * 100, 2)
        assert st["kpi"]["kunlik_ortacha"] == round((100 + 200 + 342) / 7)
        assert st["top"][0]["ulush"] == 100, "eng faol 100% bo'lishi kerak"
        assert st["top"][1]["username"] is None, "username yo'q foydalanuvchi tushib qolmasin"
        print("[7] statistika ulushlari va konversiya to'g'ri hisoblanadi OK")

        # 8) ⭐ ASOSIY MEZON: panelda XOM SQL yo'q.
        #
        # ⚠️ Bu tekshiruv 7-bosqichda SHAKLINI O'ZGARTIRDI. Ilgari u
        # Telegram statistika ekrani bilan webning raqamlarini
        # solishtirardi — «ikki ekran, bitta manba» qoidasi. Ekran endi
        # BITTA (`handlers/admin/stats.py` o'chirildi), ya'ni
        # solishtiradigan narsa yo'q.
        #
        # Lekin qoidaning O'ZI qolyapti va u muhimroq: `web/api.py` da
        # SQL yozilmasin. Sabab shu faylning sarlavhasida — hisob-kitob
        # `db/database.py` da, ikkala tomondan ham YUQORIDA turishi
        # kerak. Web o'ziga SQL yozgan kunidan boshlab kunlik hisobot
        # (`daily.py`) va panel bir-biriga mos kelmay qoladi, va buni
        # hech narsa aytmaydi.
        src = (ROOT / "web" / "api.py").read_text(encoding="utf-8")
        for taqiq in ("pool.acquire", "SELECT ", "INSERT ", "UPDATE ", "DELETE "):
            assert taqiq not in src, f"web/api.py ga xom SQL kirib qolgan: {taqiq}"
        assert "activity_stats()" in src, "web statistikani yagona manbadan olmaydi"
        # Kunlik hisobot ham AYNAN o'sha funksiyalardan o'qiydi — ya'ni
        # panel va hisobot bir kuni ikki xil raqam ko'rsata olmaydi.
        d = (ROOT / "handlers" / "admin" / "daily.py").read_text(encoding="utf-8")
        assert "pool.acquire" not in d, "daily.py ga xom SQL qaytib kelgan"
        assert "daily_report_stats" in d
        assert st["kpi"]["jami"] == SOXTA_ACTIVITY["total_users"]
        # ⚠️ Tarif doirasi: segmentlar QO'SHILGANDA jamiga teng. Ilgari
        # bloklangan odam ham `free_count` ichida turardi, ya'ni doira
        # jamidan oshib ketishi mumkin edi.
        q = {x["kalit"]: x["soni"] for x in st["tarif"]["qismlar"]}
        assert q["free"] == SOXTA_ACTIVITY["free_count"]
        assert q["premium"] == SOXTA_ACTIVITY["premium_count"]
        assert sum(q.values()) == st["tarif"]["jami"], st["tarif"]
        assert q["pro"] == SOXTA_ACTIVITY["pro_count"]
        # Nom YAGONA ro'yxatdan (`TARIF_NOMI`) keladi — panel o'zi
        # yozib qo'ymaydi, chunki aynan shu nusxa `premium` ni
        # tushirib qoldirgan edi.
        nomlari = {x["kalit"]: x["nom"] for x in st["tarif"]["qismlar"]}
        assert nomlari == {k: TARIF_NOMI[k] for k in nomlari}, nomlari
        print("[8] panelda xom SQL yo'q, raqamlar yagona manbadan OK")

        # ═══════════════════════════════════════════════════════════════
        # 9) TOKEN SARFI — ENG QIMMAT XAVF ENDI KO'RINADI
        # ═══════════════════════════════════════════════════════════════
        # NEGA BOR: bot kunlik BEPUL grant ustida ishlaydi va uning qanchasi
        # yeyilgani faqat Railway logida bor edi. Ya'ni pul ketayotganini
        # hech kim ko'rmasdi.
        t = ov["kpi"]["token"]
        assert t["bugun"] == 1_840_000, t          # kirish + chiqish
        assert t["grant"] == TOKEN_KUNLIK_GRANT, t
        assert t["foiz"] == 74, t
        assert t["oshgan"] is False, t
        # ⚠️ Keshlangan ulush KVOTANI KAMAYTIRMAYDI (OpenAI, 2026-09-09) —
        # u faqat so'rov boshi kun bo'yi bir xil qolayotganini ko'rsatadi.
        # Shuning uchun u `bugun` dan CHIQARILMAYDI.
        assert t["keshdan"] == 61, t
        print(f"[9] token kartasi: {t['foiz']}% · keshdan {t['keshdan']}% OK")

        # ── 9b) Kecha grantdan oshgani alohida aytiladi ────────────────
        # Oshgan token baribir ISHLAYDI, faqat pulli bo'ladi — shuning
        # uchun bu «bloklandi» emas, ogohlantirish.
        assert t["kecha"] == 2_610_000 and t["kecha_oshgan"] is True, t
        js_matn = (ROOT / "web" / "static" / "panel.js").read_text(encoding="utf-8")
        assert "kecha oshgan" in js_matn, "panel kechagi oshishni aytmaydi"
        assert "grantdan oshdi" in js_matn, "panel bugungi oshishni aytmaydi"
        print("[9b] grantdan oshish panelda aytiladi OK")

        # ── 9c) Hisob BO'SH bazada ham yiqilmaydi ──────────────────────
        # Yangi bot: hali bironta qator yo'q. Nolga bo'linish yoki KeyError
        # butun Boshqaruv ekranini o'ldirardi.
        bosh = api._token_kpi({"kunlik": [], "eng_qimmat": []})
        assert bosh["bugun"] == 0 and bosh["foiz"] == 0, bosh
        assert bosh["keshdan"] is None, "kirish 0 da keshdan ulushi bo'lmaydi"
        assert bosh["oshgan"] is False, bosh
        print("[9c] bo'sh bazada token kartasi yiqilmaydi OK")

        # ── 9d) Yozish javobni KUTTIRMAYDI va yiqilmaydi ───────────────
        # ⚠️ Hisob javobdan muhimroq emas: baza yiqilsa ham foydalanuvchi
        # javobini olishi kerak.
        ai_matn = (ROOT / "services" / "ai.py").read_text(encoding="utf-8")
        assert "asyncio.create_task(_token_saqla(" in ai_matn, (
            "token yozuvi javob yo'lida kutilyapti")
        i = ai_matn.index("async def _token_saqla")
        tana = ai_matn[i:i + 600]
        assert "except Exception" in tana, "token yozuvi xatosi yutilmaydi"
        print("[9d] token yozuvi fon vazifasida va xatosi yutiladi OK")

        # ── 9e) ⭐ SUM() BIGINT ustida — natija ::bigint ga
        # o'tkazilishi SHART. Postgres SUM(BIGINT) dan NUMERIC
        # qaytaradi, asyncpg uni `Decimal` qiladi, `Decimal` esa JSON
        # ga serializatsiya QILINMAYDI — butun Boshqaruv ekrani 500
        # bo'lib yiqiladi.
        #
        # Bu JONLI xato edi va testlar uni KO'RMAGAN: bu yerda baza
        # soxta va int qaytaradi. Shuning uchun tekshiruv SQL MATNINI
        # o'qiydi — `test_panel_raqamlar.py` dagi qoida bilan bir xil.
        db_matn = (ROOT / "db" / "database.py").read_text(encoding="utf-8")
        i = db_matn.index("async def token_stats")
        tana = db_matn[i:db_matn.index("\n@with_db_retry", i)]
        tana = tana[tana.index("pool.acquire"):]        # izohlar emas, SQL
        xom = [q.strip() for q in tana.split("\n")
               if "SUM(" in q and "::bigint" not in q]
        assert not xom, f"token_stats da ::bigint siz SUM(): {xom}"
        print("[9e] token_stats: hamma SUM() ::bigint ga o'tkazilgan OK")

    print("\nweb stats: barcha tekshiruvlar o'tdi (13/13).")


async def _nol_kecha():
    d = dict(SOXTA_KUNLIK)
    d["prev_actions"] = 0
    return d


if __name__ == "__main__":
    asyncio.run(main())
