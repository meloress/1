"""Paneldagi RAQAMLAR bir-biriga mos kelishini tekshiradi.

Bu fayl jonli shikoyatdan tug'ildi. Telefondan olingan bitta ekranda
quyidagilar bir vaqtda turardi:

    «Pro obunachilar 2»          (yuqoridagi KPI)
    «Pro 1 · Premium 1 · Bepul 228»  (tarif doirasi)
    «230 ta · 2 tasi Pro»        (Foydalanuvchilar sarlavhasi)
    «24 soatdagi so'rovlar 150»  (KPI)
    «121+11+5+4+1 = 142»         (So'rov turlari ustunlari)

Hech biri ochiqdan-ochiq «xato» emasdi — har bir raqam o'z so'rovida
to'g'ri edi. Muammo ta'riflarning uchta boshqa-boshqa bo'lganida:
adminni sanaydimi, bloklanganni sanaydimi, qaysi turlarni sanaydi.
Admin bunday farqni ko'rsa butun paneldagi raqamga ishonmay qoladi.

Shuning uchun bu yerdagi tekshiruvlar SQL ning MATNINI o'qiydi: baza
ham, tarmoq ham kerak emas, lekin ta'rif ikkinchi marta yozilsa darhol
yiqiladi. Qolgan tekshiruvlar — sof funksiyalar (muddat chegarasi,
foiz, yig'indi).

Ishga tushirish:  PYTHONIOENCODING=utf-8 python tests/test_panel_raqamlar.py
"""

import datetime
import os
import pathlib
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("BOT_TOKEN", "123456:TEST-TOKEN-FOR-PANEL-NUMBERS")

from core.config import (LIMIT_IZOHI, LIMIT_NOMI, PLAN_LIMITS,  # noqa: E402
                         TARIF_NOMI, TARIF_RANGI)
from db import database as db  # noqa: E402
from web import api  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
TASHKENT = datetime.timezone(datetime.timedelta(hours=5))
UTC = datetime.timezone.utc


def _funksiya(manba: str, nom: str) -> str:
    """Faylning shu funksiyasi tanasi — keyingi `async def` gacha."""
    bosh = manba.index(f"async def {nom}(")
    keyingi = manba.find("\nasync def ", bosh + 1)
    return manba[bosh:keyingi if keyingi > 0 else len(manba)]


def main() -> None:
    dbs = (ROOT / "db" / "database.py").read_text(encoding="utf-8")

    # ── 1) Tarif ta'rifi BITTA JOYDA ────────────────────────────
    # Uchta so'rov «Pro nima?» degan savolga javob beradi:
    # foydalanuvchilar jadvalidagi chip, tarif doirasi va KPI. Ilgari
    # uchtasi uch xil edi va aynan shu «2 / 1+1 / 2» ni bergan.
    assert '_PRO_SHART = ' in dbs and '_FREE_SHART = ' in dbs and '_BAN_SHART = ' in dbs, \
        "tarif shartlari yagona nom sifatida ajratilmagan"
    for nom in ("list_users", "activity_stats", "daily_report_stats"):
        tana = _funksiya(dbs, nom)
        assert "_PRO_SHART" in tana or "_FREE_SHART" in tana or "_TARIF_SHARTI" in tana, \
            f"{nom} tarifni O'ZI ta'riflayapti — ikkinchi nusxa"
    # Qo'lda yozilgan nusxa qaytib kelmasin.
    nusxa = re.findall(r"COALESCE\(plan_type,'free'\)\s*<>\s*'free'", dbs)
    assert len(nusxa) == 1, (
        f"«pro» ta'rifi {len(nusxa)} marta yozilgan — bittasi bo'lishi kerak "
        "(_PRO_SHART)")
    print("[1] tarif ta'rifi bitta joyda, uchala so'rov ham o'shandan OK")

    # ── 2) ADMIN HECH QAYERDA SANALMAYDI ────────────────────────
    # ⚠️ `daily_report_stats()` ilgari adminlarni sanardi,
    # `activity_stats()` esa sanamasdi — ya'ni bitta ekranning
    # yuqorisi va pasti bir-biriga mos kelmasdi va farq aynan
    # admin edi.
    tana = _funksiya(dbs, "daily_report_stats")
    sanoqlar = re.findall(r"\)\s+AS\s+(\w+)", tana)
    kutilgan = {"new_users", "total_users", "active_users", "pro_users",
                "prev_actions", "active_7d", "pro_expiring"}
    assert kutilgan <= set(sanoqlar), f"sanoq nomlari o'zgargan: {sanoqlar}"
    # Har bir odam sanog'i `_ODDIY_USER` bilan yopilgan bo'lsin.
    # (`sales`, `stars`, `errors` — to'lov va xato jadvallari, odam
    # sanog'i emas, shuning uchun ro'yxatda yo'q.)
    for nom in kutilgan:
        joy = tana.index(f"AS {nom}")
        parcha = tana[:joy].rsplit("(SELECT", 1)[-1]
        assert "_ODDIY_USER" in parcha, (
            f"«{nom}» sanog'i adminlarni ham qo'shib sanayapti:\n{parcha[:200]}")
    print("[2] daily_report_stats ning har bir odam sanog'i adminlarsiz OK")

    # ── 3) «FAOL» va «JAMI» — IKKI BOSHQA SAVOL ─────────────────
    # 230 — ro'yxatdagi hamma odam; 49 — oxirgi 7 kunda yozganlar.
    # Panelda ikkalasi ham bor va ikkalasi ham «faol» deb atalardi.
    html = (ROOT / "web" / "static" / "panel.html").read_text(encoding="utf-8")
    korinadigan = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    assert "Faol foydalanuvchilar. Adminlar sanoqqa kirmaydi." not in korinadigan, (
        "tarif doirasidagi son «faol» deb atalgan — u JAMI foydalanuvchi")
    assert "Faol (7 kun)" in korinadigan, "«faol» ta'rifi ekrandan yo'qolgan"
    assert "_ODDIY_USER" in _funksiya(dbs, "activity_stats"), \
        "jami sanog'i adminlarni qo'shib sanayapti"
    print("[3] «jami» va «faol (7 kun)» ekranda ajratilgan OK")

    # ── 4) YIG'INDI = UMUMIY SON ────────────────────────────────
    # `actions` KPI si tur kesimining O'ZIDAN hisoblanadi, ya'ni
    # ular ta'rifan mos keladi — ikki alohida so'rov emas.
    assert "out['actions'] = sum(" in tana, (
        "«24 soatdagi so'rovlar» hali ham alohida so'rovdan hisoblanyapti")
    # ⚠️ Faqat SO'ROV MATNI tekshiriladi, izohlar emas: shu funksiyaning
    # ustida «na `LIMIT 5`, na tur filtri» degan izoh turibdi va u
    # o'z o'rnida. Izohni ushlab testni yiqitish — bu loyihada
    # to'rt marta takrorlangan xato.
    kesim_sorovi = tana.split("turlar = await conn.fetch(", 1)[1].split("''')", 1)[0]
    assert "LIMIT" not in kesim_sorovi, "tur kesimi hali ham kesilgan"
    assert "= ANY(" not in kesim_sorovi, "tur kesimi hali ham filtrlangan"
    kesim = [("text_message", 121), ("guest_text_message", 11),
             ("voice_message", 5), ("photo_message", 4),
             ("file_task", 1), ("start", 8)]
    ustunlar = api._turlar(kesim)
    assert sum(u["soni"] for u in ustunlar) == 150, ustunlar
    assert ustunlar[-1] == {"nom": "Boshqa", "soni": 8, "boshqa": True}, ustunlar
    print("[4] tur ustunlari yig'indisi umumiy songa teng OK")

    # ── 5) «-10.7%» — bir xil uzunlikdagi ikki oraliq ────────────
    # ⚠️ Ikkalasi ham AYLANMA oyna (24 soat va undan oldingi 24
    # soat), ya'ni mintaqa vaqti bu hisobga umuman ta'sir qilmaydi.
    assert "INTERVAL '48 hours'" in tana and "INTERVAL '24 hours'" in tana
    assert api._foiz(150 - 168, 168, 1) == -10.7
    assert api._foiz(168 - 150, 150, 1) == 12.0
    # Kecha nol bo'lsa «+100%» — yolg'on. O'zgarish ko'rsatilmaydi.
    assert api._foiz(5, 0, 1) is None
    # «0%» va «ma'lumot yo'q» aralashmasin.
    assert api._foiz(0, 10, 1) == 0.0
    print("[5] o'zgarish foizi teng uzunlikdagi ikki oraliqdan hisoblanadi OK")

    # ── 6) ⭐ PROMOKOD MUDDATI — TOSHKENT KUNINING OXIRI ─────────
    # ⚠️ Ilgari sana UTC yarim tuniga tushardi, ya'ni panel uni
    # «21.09.2026 05:00» deb ko'rsatardi va kod tanlangan kunning
    # deyarli hammasida ALLAQACHON o'lik bo'lardi. Bu faqat
    # ko'rinish emas edi: `redeem_promo()` ham o'sha lahzani
    # tekshiradi.
    kelasi = (datetime.datetime.now(TASHKENT) + datetime.timedelta(days=30)).date()
    spec, xato = db.clean_promo_spec("TEST", 7, 5, kelasi.isoformat())
    assert not xato, xato
    muddat = spec[3].astimezone(TASHKENT)
    assert (muddat.date(), muddat.hour, muddat.minute, muddat.second) == \
        (kelasi, 23, 59, 59), muddat
    # Tanlangan kunning 23:59:59 da kod HALI ISHLAYDI…
    oxiri = datetime.datetime.combine(kelasi, datetime.time(23, 59, 59),
                                      tzinfo=TASHKENT)
    assert spec[3] >= oxiri, "kod tanlangan kun tugamasdan o'lik bo'lib qoladi"
    # …ertasi kuni 00:00:00 da esa yo'q.
    ertasi = datetime.datetime.combine(kelasi + datetime.timedelta(days=1),
                                       datetime.time(0, 0, 0), tzinfo=TASHKENT)
    assert spec[3] < ertasi, "kod ertangi kunga o'tib ketdi"
    # O'tgan sana — darhol o'lik kod, rad etiladi.
    _s, x = db.clean_promo_spec("TEST", 7, 5, "2020-01-01")
    assert x, "o'tgan sanali kod qabul qilindi"
    print("[6] promokod Toshkent vaqti bilan kun oxirida tugaydi OK")

    # ── 7) MUDDATSIZ PRO «tugaydiganlar» ga tushmaydi ───────────
    # `premium_until IS NULL` — muddati yo'q, ya'ni tugamaydi ham.
    assert "premium_until IS NOT NULL" in tana, (
        "muddatsiz Pro «7 kunda tugaydi» sanog'iga tushib ketishi mumkin")
    print("[7] muddatsiz Pro «7 kunda tugaydi» sanog'iga kirmaydi OK")

    # ── 8) PANEL «Pro» DEGANDA `pro` YOZADI ─────────────────────
    # ⚠️ Eng qimmat topilma: `set_user_premium()` ning standart tarifi
    # `'premium'` edi — CHEKSIZ limitli alohida tarif. Ya'ni
    # paneldagi «Pro berish · 7 kun» tugmasi odamga cheksiz limit
    # berardi, Limitlar ekrani esa uni umuman boshqara olmasdi.
    imzo = re.search(r"async def set_user_premium\(.*?\) -> None:", dbs, re.S).group(0)
    assert "plan: str = 'pro'" in imzo, f"standart tarif hali 'pro' emas: {imzo}"
    assert set(TARIF_NOMI) == set(PLAN_LIMITS), (
        f"tarif nomlari va limitlar ro'yxati ajralib ketgan: "
        f"{set(TARIF_NOMI) ^ set(PLAN_LIMITS)}")
    assert set(TARIF_RANGI) == set(TARIF_NOMI) | {"ban"}
    print("[8] «Pro berish» endi `pro` yozadi, tariflar yagona ro'yxatda OK")

    # ── 9) Limit izohlari ro'yxat bilan bir xil kalitda ─────────
    assert set(LIMIT_IZOHI) == set(LIMIT_NOMI), (
        f"izohsiz limit bor: {set(LIMIT_NOMI) - set(LIMIT_IZOHI)}")
    assert set(LIMIT_NOMI) <= set(PLAN_LIMITS["free"]), "limit kaliti PLAN_LIMITS da yo'q"
    print("[9] har limitning nomi ham, izohi ham bor OK")

    # ── 10) Audit tafsiloti odam tilida, lekin XOM QIYMAT YO'QOLMAYDI ──
    holatlar = [
        ("set_premium", "inf", "Muddatsiz"),
        ("set_premium", "30", "30 kun"),
        ("set_premium", "sovga 30 kun", "Sovg'a · 30 kun"),
        ("set_plan", "free", "Bepul"),
        ("limit_change", "free.points = 500", "Bepul · Kunlik ballar → 500"),
        ("limit_change", "pro.files = asl", "Pro · Fayl yaratish → asl qiymat"),
        ("create_promo", "BEHRUZ 7d x1", "BEHRUZ · 7 kun · 1 marta"),
        ("send_promo", "BEHRUZ -> 1 ta", "BEHRUZ · 1 kishiga yuborildi"),
        ("send_referral", "3 ta", "3 kishiga yuborildi"),
        ("referral_config", "3 ta -> 7 kun", "3 do'st → 7 kun Pro"),
        ("broadcast", "segment=all yuborildi=5 xato=0", "Hammaga · 5 kishiga yetdi"),
        ("maintenance", "yoqildi + matn", "Yoqildi · matn yangilandi"),
        ("cancel_broadcast", "#3", "Tarqatma #3"),
    ]
    for amal, xom, kutilgan_matn in holatlar:
        chiqdi = api._tafsilot(amal, xom)
        assert chiqdi == kutilgan_matn, f"{amal}: {chiqdi!r} != {kutilgan_matn!r}"
    # ⚠️ Qoidaga tushmagan qiymat XOM holda chiqadi — jimgina
    # yo'qolib ketishi auditda eng yomon xatti-harakat.
    assert api._tafsilot("set_premium", "kutilmagan") == "kutilmagan"
    assert api._tafsilot("bilib_bolmaydigan", "x=1") == "x=1"
    assert api._tafsilot("set_plan", None) is None
    print("[10] audit tafsiloti odam tilida, notanish qiymat yo'qolmaydi OK")

    # ── 11) Sana — ISO, formatlash panelda ──────────────────────
    # Bitta sana uch joyda uch xil uzunlikda ko'rsatiladi («bugun»,
    # «2 soat oldin», «14.09, 21:34»), ya'ni serverdan tayyor satr
    # kelsa panel uni qaytadan ajratishga majbur bo'lardi.
    iso = api._sana(datetime.datetime(2026, 9, 14, 16, 34, tzinfo=UTC))
    assert iso == "2026-09-14T21:34:00+05:00", iso
    assert api._sana(None) is None and api._sana("2026") is None
    print("[11] sanalar Toshkent siljishi bilan ISO bo'lib keladi OK")

    print("\npanel raqamlari: barcha tekshiruvlar o'tdi (11/11).")


if __name__ == "__main__":
    main()
