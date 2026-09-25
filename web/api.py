"""Web panelning JSON endpointlari.

⚠️ Bu yerda MANTIQ YO'Q — faqat `db/database.py` chaqiruvlari va ularni
panel kutgan shaklga o'tkazish. Sabab REJA 3.2 da: Telegram ekrani va
web bir xil raqamni ko'rsatishi shart, ya'ni hisob-kitob ikkalasidan
ham YUQORIDA, bitta joyda turishi kerak. Bu faylga SQL yozilsa, o'sha
kun raqamlar ajralib ketadi.

Har endpoint `@admin_only` bilan boshlanadi (REJA 4.3 — huquq HAR
so'rovda qayta tekshiriladi).
"""

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from aiohttp import web

from core import config as config_module
from core.config import (ACTIVITY_TYPES, AUDIT_ACTIONS, DAILY_COUNTERS,
                         GPT_MODEL_DISPLAY_NAME, LIMIT_IZOHI, LIMIT_NOMI,
                         PLAN_LIMITS, PRO_PLANS, SEGMENT_NOMI, TARIF_NOMI,
                         TOKEN_KUNLIK_GRANT,
                         TARIF_RANGI, TIMEZONE, audit_nomi, daily_limit,
                         guruh_xato_sababi)
from db import database as database_module
from web.auth import admin_only, bir_marta

logger = logging.getLogger(__name__)

# Grafikdagi kun yorliqlari. `date.weekday()`: 0 = dushanba.
HAFTA = ["Dush", "Sesh", "Chor", "Pay", "Jum", "Shan", "Yak"]

# So'rov turlaridan nechtasi alohida ustun bo'ladi; qolgani «Boshqa».
TUR_KORSAT = 6

# Grafikda tanlanadigan oynalar. Boshqa qiymat 7 ga tushadi — panel
# tugmasi ham shu ro'yxatdan chiziladi, ya'ni ikki joyda ikki xil
# variant bo'lishi mumkin emas.
GRAFIK_KUNLARI = (7, 30, 90)


def _foiz(qism: float, butun: float, kasr: int = 0) -> Optional[float]:
    """Ulush foizda. Bo'luvchi nol bo'lsa `None` — nol EMAS.

    ⚠️ Farqi muhim: «0%» va «hali ma'lumot yo'q» bir narsa emas, va
    panel ularni boshqacha ko'rsatadi («0%» va «—»).
    """
    if not butun:
        return None
    return round(qism / butun * 100, kasr) if kasr else round(qism / butun * 100)


def _turlar(kesim: List[tuple], eng_kop: int = TUR_KORSAT) -> List[Dict[str, Any]]:
    """`[(tur, soni)]` → paneldagi ustunlar. Yig'indi ALBATTA jamiga teng.

    Nom `ACTIVITY_TYPES` dan olinadi — kunlik hisobot ham o'shandan
    o'qiydi, ya'ni ikki joyda bitta tur ikki xil atalmaydi.

    ⚠️ HECH NARSA TASHLAB KETILMAYDI. Ilgari ro'yxatda yo'q tur
    (`start`) jimgina tushib qolardi va beshtadan keyingisi umuman
    so'ralmasdi — natijada ekranda «24 soatda 150 so'rov» yozilib,
    ustunlar qo'shilganda 142 chiqardi. Admin buni ko'radi va butun
    paneldagi raqamlarga ishonmay qoladi, to'g'ri qiladi ham.
    Nomsiz va ortib qolgan turlar endi «Boshqa» qatoriga yig'iladi.
    Log'dagi ogohlantirish qoladi: yangi tur `ACTIVITY_TYPES` ga
    qo'shilmasa, u «Boshqa» ichida oylab ko'rinmay yurishi mumkin.
    """
    nomli: List[Dict[str, Any]] = []
    boshqa = 0
    for tur, soni in kesim:
        qiymat = ACTIVITY_TYPES.get(tur)
        if qiymat is None:
            logger.warning(
                f"[web] '{tur}' ACTIVITY_TYPES da yo'q — «Boshqa» ga qo'shildi. "
                "core/config.py ga qo'shing.")
            boshqa += soni
            continue
        nomli.append({"nom": qiymat[1], "soni": soni})

    nomli.sort(key=lambda t: t["soni"], reverse=True)
    if len(nomli) > eng_kop:
        boshqa += sum(t["soni"] for t in nomli[eng_kop:])
        nomli = nomli[:eng_kop]
    if boshqa:
        nomli.append({"nom": "Boshqa", "soni": boshqa, "boshqa": True})
    return nomli


def _tarif(st: Dict[str, Any]) -> Dict[str, Any]:
    """Tarif taqsimoti: nom, son, foiz — YAGONA ro'yxatdan (`TARIF_NOMI`).

    ⚠️ Segmentlar qo'shilganda `jami` ga TENG bo'ladi: `activity_stats()`
    to'rt sanoqni kesishmaydigan qilib qaytaradi. Panel ularni bitta
    doiraga chizadi, ya'ni yig'indi mos kelmasa doira yolg'on ko'rsatadi.

    ⚠️ `premium` — eski, cheksiz limitli tarif; yangi hech narsa uni
    bermaydi. Bazada qatori bo'lsa ko'rsatiladi, bo'lmasa ro'yxatda ham
    turmaydi — bo'sh segment adminni «bu nima?» degan savolga soladi.
    """
    jami = st.get("total_users", 0) or 0
    xom = {
        "pro":     st.get("pro_count", 0) or 0,
        "premium": st.get("premium_count", 0) or 0,
        "free":    st.get("free_count", 0) or 0,
        "ban":     st.get("ban_count", 0) or 0,
    }
    # Pro va Bepul doim ko'rinadi (nol bo'lsa ham — «Pro 0» ma'noli
    # javob), qolgani faqat qatori bo'lsa.
    korinadi = [k for k in ("pro", "premium", "free", "ban")
                if xom[k] or k in ("pro", "free")]
    return {
        "jami": jami,
        "qismlar": [{
            "kalit": k,
            "nom": TARIF_NOMI.get(k, "Bloklangan"),
            "soni": xom[k],
            "rang": TARIF_RANGI.get(k, "#3A3556"),
            "foiz": _foiz(xom[k], jami, 1),
        } for k in korinadi],
    }


def _biznes_kpi(d: Dict[str, Any]) -> Dict[str, Any]:
    """Telegram Business kartasi (REJA.md 4.5).

    ⚠️ Ulush bugungi JAMI token ichida — grantga nisbatan emas: savol
    «grantning qanchasini biznes yeyapti», va u `_token_kpi` dagi
    raqam bilan bir kunlik kesimda solishtiriladi. Token bo'lmasa None:
    «0%» yolg'on bo'lardi (o'lchanmagan ≠ nol).
    """
    jami = d.get("token_jami") or 0
    token = d.get("token") or 0
    return {
        "ulanishlar": d.get("ulanishlar") or 0,
        "sorovlar": d.get("sorovlar") or 0,
        "token": token,
        "ulush": round(token / jami * 100) if jami else None,
    }


def _token_kpi(d: Dict[str, Any]) -> Dict[str, Any]:
    """Bugungi token sarfi — kunlik grantga nisbatan.

    ⚠️ Grant CHEKLOV EMAS, o'lchov: undan oshgan token baribir ishlaydi,
    faqat pulli bo'ladi. Shuning uchun panel «bloklandi» demaydi,
    «oshgan» deydi.

    ⚠️ «Keshdan» ulushi kvotani KAMAYTIRMAYDI (OpenAI tasdiqlagan,
    2026-09-09) — u faqat so'rov boshi kun bo'yi bir xil qolayotganini
    ko'rsatadi. Tushib ketsa, prefiks har xabarda o'zgarib turibdi.
    """
    qatorlar = d.get("kunlik") or []
    bugun = datetime.now(TIMEZONE).date()
    xarita = {r["kun"]: r for r in qatorlar}
    b = xarita.get(bugun) or {}
    k = xarita.get(bugun - timedelta(days=1)) or {}

    jami = (b.get("kirish") or 0) + (b.get("chiqish") or 0)
    kecha = (k.get("kirish") or 0) + (k.get("chiqish") or 0)
    kirish = b.get("kirish") or 0
    return {
        "bugun": jami,
        "kecha": kecha,
        "grant": TOKEN_KUNLIK_GRANT,
        "foiz": round(jami / TOKEN_KUNLIK_GRANT * 100) if TOKEN_KUNLIK_GRANT else 0,
        "oshgan": jami > TOKEN_KUNLIK_GRANT,
        "kecha_oshgan": kecha > TOKEN_KUNLIK_GRANT,
        "keshdan": round((b.get("keshdan") or 0) / kirish * 100) if kirish else None,
        "raund": b.get("raund") or 0,
    }


@admin_only
async def overview(request: web.Request):
    """Boshqaruv ekrani (REJA 6.1)."""
    try:
        kun_oynasi = int(request.query.get("kun", 7))
    except ValueError:
        kun_oynasi = 7
    if kun_oynasi not in GRAFIK_KUNLARI:
        kun_oynasi = 7

    # ⚠️ PARALLEL, ketma-ket EMAS. Oltitasi bir-biriga bog'liq emas va
    # bittasi ham yozmaydi, ya'ni tartibning ma'nosi yo'q edi — lekin
    # ketma-ket yozilgani uchun ekran olti marta bazaga borib kelardi.
    # Bu eng ko'p ochiladigan ekran, shuning uchun farq sezilarli.
    #
    # ⛔️ Bu naqshni YOZADIGAN endpointga ko'chirmang: `refund` da
    # Telegram baribir bazadan OLDIN turishi shart, `watch_set` da esa
    # kesh yangilanishi yozuvdan keyin bo'lishi kerak.
    (kunlik, daromad, xatolar, xato_jami,
     tatil, st, token, kuzatuv, biznes) = await asyncio.gather(
        database_module.daily_report_stats(),
        database_module.revenue_stats(),
        database_module.recent_errors(limit=4),
        database_module.error_summary(),
        database_module.get_maintenance(),
        database_module.activity_stats(kun_oynasi),
        database_module.token_stats(2),
        database_module.get_watch_health(),
        database_module.biznes_panel_stats(),
    )

    kunlar = _kun_qatori(st["daily_activity"], kun_oynasi,
                         kalit="day", soni="total", kishi="uniq_users")

    amallar = kunlik.get("actions") or 0
    oldingi = kunlik.get("prev_actions") or 0
    return web.json_response({
        "kpi": {
            "sorovlar": {
                "qiymat": amallar,
                # Kecha umuman amal bo'lmagan bo'lsa «+100%» deyish
                # yolg'on bo'lardi — o'zgarish ko'rsatilmaydi.
                "ozgarish": _foiz(amallar - oldingi, oldingi, 1) if oldingi else None,
            },
            "token": _token_kpi(token),
            "faol": {
                "qiymat": kunlik.get("active_7d") or 0,
                "jami": st["total_users"],
                "yangi": kunlik.get("new_users") or 0,
            },
            "pro": {
                "qiymat": kunlik.get("pro_users") or 0,
                "tugaydi": kunlik.get("pro_expiring") or 0,
            },
            "daromad": {
                "bugun": daromad.get("stars_today") or 0,
                "oy": daromad.get("stars_30d") or 0,
            },
        },
        "kunlar": kunlar,
        "kun_oynasi": kun_oynasi,
        "kun_variantlari": list(GRAFIK_KUNLARI),
        # 24 soatlik kesim — `actions` KPI si AYNAN shu ro'yxatdan
        # hisoblanadi (`daily_report_stats`), ya'ni ustunlar yig'indisi
        # yuqoridagi songa teng bo'lishi ta'rifan kafolatlangan.
        "turlar": _turlar(kunlik.get("types_24h") or []),
        "tarif": _tarif(st),
        "xatolar": [{
            "vaqt": _sana(x.get("created_at")),
            "tur": x.get("kind") or "?",
            "matn": (x.get("message") or "")[:120],
            "user": x.get("user_id"),
        } for x in xatolar],
        "xato_soni": xato_jami.get("day") or 0,
        # ⚠️ Kuzatuv guruhi — panelning YAGONA chiqish kanali. U yiqilsa
        # ogohlantirishlar hech qayerga bormaydi va buni ilgari faqat
        # Railway logi bilardi. Matnlar `soz.js` da; bu yerdan faqat
        # holat ketadi.
        "kuzatuv": {
            "guruh": bool(kuzatuv.get("guruh")),
            "sabab": kuzatuv.get("sabab"),
            "vaqt": _sana(kuzatuv.get("vaqt")),
        },
        "tatil": bool(tatil.get("active")),
        "biznes": _biznes_kpi(biznes),
        # ⚠️ «Bot ishlayapti» BELGISI QOTIRILGAN MATN EMAS. Panel bot
        # jarayonining ICHIDA ishlaydi, ya'ni bu javobning kelishi
        # jarayon tirikligining o'zi; qolgan ikkitasi esa haqiqatan
        # buzilishi mumkin bo'lgan narsa: baza ulanishi va texnik
        # ta'til. Uchalasidan panel bitta holat chiqaradi.
        "baza": database_module.pool is not None,
    })


@admin_only
async def stats(request: web.Request):
    """Statistika ekrani (REJA 6.3)."""
    st, top, kunlik, token = await asyncio.gather(   # parallel — overview'dagi izohga qarang
        database_module.activity_stats(),
        database_module.top_users(7, 10),
        database_module.daily_report_stats(),
        database_module.token_stats(7),
    )

    kesim = st["type_breakdown"]
    jami_amal = sum(soni for _t, soni in kesim) or 0
    guest = sum(soni for t, soni in kesim if t.startswith("guest_"))
    ovoz = sum(soni for t, soni in kesim if t.endswith("voice_message"))
    fayl = sum(soni for t, soni in kesim if t == "file_task")
    tadqiqot = sum(soni for t, soni in kesim if t == "research")

    # 7 kunlik jami — «kunlik o'rtacha» shundan chiqadi.
    hafta_jami = sum(r["total"] for r in st["daily_activity"])
    eng_kop = max((u["activity_count"] for u in top), default=0)

    return web.json_response({
        "kpi": {
            "jami": st["total_users"],
            "yangi": kunlik.get("new_users") or 0,
            "kunlik_ortacha": round(hafta_jami / st["kunlar"]) if hafta_jami else 0,
            # ⚠️ Maketda bu joyda «o'rtacha javob vaqti» turardi — bot
            # javob vaqtini HECH QAYERGA yozmaydi, shuning uchun uning
            # o'rnida haqiqiy raqam: guruhdagi (guest) so'rovlar ulushi.
            "mehmon_ulush": _foiz(guest, jami_amal),
            "konversiya": _foiz(st["pro_count"] + st["premium_count"],
                                st["total_users"], 2),
        },
        "top": [{
            "user_id": u["user_id"],
            "username": u.get("username"),
            "soni": u["activity_count"],
            "ulush": _foiz(u["activity_count"], eng_kop) or 0,
        } for u in top],
        "tarif": _tarif(st),
        # 30 kunlik kesim — Telegram ekranidagi «Turlar bo'yicha» bilan
        # bir xil so'rovdan.
        "turlar": _turlar(kesim),
        "ulushlar": [
            {"nom": "Guruhdagi so'rovlar", "izoh": "mehmon rejimi", "foiz": _foiz(guest, jami_amal)},
            {"nom": "Ovozli savollar", "izoh": "STT → javob → TTS", "foiz": _foiz(ovoz, jami_amal)},
            {"nom": "Fayl yaratilgan", "izoh": "PPTX, PDF, XLSX", "foiz": _foiz(fayl, jami_amal, 1)},
            {"nom": "Chuqur tadqiqot", "izoh": "/research", "foiz": _foiz(tadqiqot, jami_amal, 1)},
        ],
        # Kim qancha token yeyayotgani. `user_history` ni tanlashning
        # BONUSI shu: kunlik yig'indi jadvalida bu ma'lumot bo'lmasdi.
        #
        # ⚠️ Username YO'Q: bu ro'yxat «kim aybdor» degani emas, «qayerga
        # ketyapti» degani — ID yetarli, va profilga o'tish uchun ham
        # ID kerak.
        "eng_qimmat": [{
            "user_id": r["user_id"],
            "token": r["jami"],
            "raund": r["raund"],
        } for r in (token.get("eng_qimmat") or [])],
    })


# ═══════════════════════════════════════════════════════════════════
#  FOYDALANUVCHILAR (REJA 6.2)
# ═══════════════════════════════════════════════════════════════════

# Filtr kalitlari. `nofaol` — botni BLOKLAGANLAR; u ilgari Jurnal
# ekranida alohida jadval edi va shu sababli bir xil odamlar ikki
# ekranda ikki xil ustun bilan ko'rsatilardi. Endi bitta ro'yxat,
# to'rt filtr o'rniga besh.
TARIFLAR = ("all", "pro", "free", "ban", "nofaol")
# Jurnal filtri uchun ruxsat etilgan oynalar. Ro'yxatdan tashqari
# qiymat «hammasi» ga tushadi — admin kiritishi ham tekshiriladi.
JURNAL_KUNLARI = (1, 7, 30, 90)


def _jurnal_filtr(request: web.Request) -> tuple:
    """(q, kun) — jurnal ekranlari uchun umumiy o'qish."""
    q = (request.query.get("q") or "").strip()[:64] or None
    try:
        kun = int(request.query.get("kun", 0))
    except ValueError:
        kun = 0
    return q, (kun if kun in JURNAL_KUNLARI else None)


TARTIBLAR = ("faollik", "yangi")
SAHIFA = 20
# Admin bera oladigan muddatlar. Telegram ekranidagi tugmalar bilan
# AYNAN bir xil (`_premium_duration_keyboard`) — ikki joyda ikki xil
# variant bo'lsa, «90 kun» qayerdadir yo'qolib qolardi.
PREMIUM_KUNLARI = (7, 30, 90, None)   # None = cheksiz
XABAR_MAX = 3500                      # Telegram chegarasi 4096, zaxira bilan

# Kunlik sanoqlarning ko'rinadigan nomi. `DAILY_COUNTERS` ning o'zida
# nom yo'q — u yerdagi uchinchi element limit KALITI.
# ⚠️ Yangi sanoq qo'shilsa bu yerga nom qo'shilmasa ham panel ishlaydi:
# kalitning o'zi ko'rinadi (`.get(kalit, kalit)`), ya'ni sanoq
# YO'QOLMAYDI — faqat inglizcha atalib turadi. CLAUDE.md dagi «yangi
# sanoq = bitta qator + ikki ustun» qoidasi shu tufayli buzilmaydi.
#
# ⚠️ 6-bosqichda bu ro'yxat SHU YERDAN ketdi: Sozlamalar ekrani ham aynan
# shu limitlarni nomlaydi va u yerda ular boshqacha atalgandi («Fayllar»
# emas, «Fayl»). To'rtinchi eskirgan ro'yxat bo'lishiga yo'l qo'ymay
# `core/config.py::LIMIT_NOMI` ga ko'chirildi.
SANOQ_NOMI = LIMIT_NOMI


def _target(request: web.Request) -> int:
    """URL dagi foydalanuvchi ID si. Noto'g'ri bo'lsa — 400."""
    try:
        return int(request.match_info["user_id"])
    except (KeyError, ValueError):
        raise web.HTTPBadRequest(text='{"error": "ID noto\'g\'ri"}',
                                 content_type="application/json")


async def _tana(request: web.Request) -> Dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


async def _yoz(request: web.Request, amal: str, kimga: Optional[int],
               tafsilot: Optional[str] = None) -> None:
    """Audit jurnaliga yozuv.

    ⚠️ HAR yozuv amalidan keyin chaqiriladi (REJA 4.3). Xatosi
    yutiladi — amal allaqachon bajarilgan, jurnal yozilmagani uchun
    adminni «bajarilmadi» deb aldash noto'g'ri bo'lardi. Lekin log'da
    iz qoladi.
    """
    try:
        await database_module.log_admin_action(
            request["user_id"], amal, kimga, tafsilot)
    except Exception:
        logger.exception(f"[web] audit yozilmadi: {amal} -> {kimga}")


async def _xabar(user_id: int, matn: str) -> bool:
    """Foydalanuvchiga botdan xabar. Yetmasa — `False`, xato emas.

    Odam botni bloklagan yoki o'chirib yuborgan bo'lishi mumkin; bu
    amalni bekor qilish uchun sabab emas (Pro berildi — berildi).
    Panel buni «xabar yetmadi» deb ko'rsatadi.
    """
    from core.loader import bot          # sikl importni oldini olish uchun shu yerda
    try:
        await bot.send_message(user_id, matn, parse_mode="HTML")
        return True
    except Exception as exc:
        logger.info(f"[web] {user_id} ga xabar yetmadi: {exc}")
        return False


def _tarif_kaliti(u: Dict[str, Any]) -> str:
    """Odamning KO'RINADIGAN tarifi: `ban` | `free` | `pro` | `premium`.

    ⚠️ Ilgari bu yerda `free` dan boshqa hamma narsa «pro» ga
    yopishtirilardi, ya'ni cheksiz limitli `premium` odam jadvalda
    «Pro» bo'lib ko'rinardi — lekin Boshqaruv ekranidagi doirada
    ALOHIDA «Premium» segmenti bo'lib turardi. Bitta odam ikki ekranda
    ikki xil tarifda. Kalit endi `TARIF_NOMI` niki, nomni panel o'sha
    ro'yxatdan oladi.
    """
    if u.get("is_banned"):
        return "ban"
    tarif = u.get("plan_type") or "free"
    return tarif if tarif in TARIF_NOMI else "free"


def _qator(u: Dict[str, Any]) -> Dict[str, Any]:
    """Jadval qatori."""
    return {
        "user_id": u["user_id"],
        "username": u.get("username"),
        "tarif": _tarif_kaliti(u),
        "plan_type": u.get("plan_type") or "free",
        "premium_until": _sana(u.get("premium_until")),
        "created_at": _sana(u.get("created_at")),
        "last_seen": _sana(u.get("last_seen")),
    }


def _sana(dt: Any) -> Optional[str]:
    """Sana — ISO-8601, Toshkent siljishi bilan (`…T21:34:00+05:00`).

    ⚠️ FORMATLASH BU YERDA EMAS, PANELDA. Ilgari bu funksiya tayyor
    `«14.09.2026 21:34»` satrini qaytarardi va telefonda u ikki qatorga
    bo'linib, jadval qatorini ikki barobar baland qilardi. Undan ham
    yomoni: «2 soat oldin» yoki «Bugun / Kecha» kabi guruhlash ham
    mumkin emasdi — tayyor satrdan sanani qaytadan ajratib olish
    kerak bo'lardi. ISO satr esa bir xil ma'lumotni SAQLAYDI va panel
    uni joyiga qarab uzun, qisqa yoki nisbiy qilib chizadi.

    Siljish ATAYLAB Toshkentniki: panel istalgan mintaqada ochilishi
    mumkin, sanalar esa botning vaqti bilan aytilishi kerak.
    """
    if not isinstance(dt, datetime):
        return None
    try:
        return dt.astimezone(TIMEZONE).isoformat(timespec="seconds")
    except Exception:
        return None


@admin_only
async def users(request: web.Request):
    """Ro'yxat: qidiruv, filtr, sahifalash."""
    q = (request.query.get("q") or "").strip()[:64] or None
    tarif = request.query.get("filter") or "all"
    if tarif not in TARIFLAR:
        tarif = "all"
    try:
        sahifa = max(0, int(request.query.get("page", 0)))
    except ValueError:
        sahifa = 0

    tartib = request.query.get("tartib") or "faollik"
    if tartib not in TARTIBLAR:
        tartib = "faollik"

    d = await database_module.list_users(
        q=q, tarif=tarif, limit=SAHIFA, offset=sahifa * SAHIFA, tartib=tartib)
    return web.json_response({
        "rows": [_qator(u) for u in d["rows"]],
        "jami": d["jami"],
        "sanoq": d["sanoq"],
        "sahifa": sahifa,
        "sahifalar": max(1, -(-d["jami"] // SAHIFA)),
        "tartib": tartib,
    })


@admin_only
async def user(request: web.Request):
    """Bitta foydalanuvchi kartochkasi: profil, sanoqlar, to'lovlar."""
    uid = _target(request)
    profil = await database_module.get_full_user_profile(uid)
    if not profil:
        return web.json_response({"error": "topilmadi"}, status=404)

    # Profil yuqorida ALOHIDA olinadi: topilmasa qolgan ikkitasi
    # umuman keraksiz. Qolgan ikkitasi esa parallel.
    tolovlar, ref = await asyncio.gather(
        database_module.get_user_payments(uid, limit=10),
        database_module.get_referral_progress(uid),
    )
    tarif_nomi = profil.get("plan_type") or "free"

    # Limitlar `daily_limit()` dan — u limitning YAGONA o'qish nuqtasi,
    # ya'ni admin panelidan o'zgartirilgan qiymat shu zahoti ko'rinadi.
    # `PLAN_LIMITS` ni to'g'ridan o'qisak, o'zgartirilgan limit
    # e'tiborga olinmasdi (CLAUDE.md, «Quotas» bo'limi).
    sanoqlar = []
    for kalit, (used_col, _date_col, limit_kaliti) in DAILY_COUNTERS.items():
        sanoqlar.append({
            "kalit": kalit,
            "nom": SANOQ_NOMI.get(kalit, kalit),
            "ishlatilgan": profil.get(used_col, 0) or 0,
            "limit": daily_limit(tarif_nomi, limit_kaliti),
        })

    return web.json_response({
        "user_id": uid,
        "username": profil.get("username"),
        "tarif": _tarif_kaliti(profil),
        "plan_type": tarif_nomi,
        "bloklangan": bool(profil.get("is_banned")),
        "premium_until": _sana(profil.get("premium_until")),
        "created_at": _sana(profil.get("created_at")),
        "last_seen": _sana(profil.get("last_seen")),
        "ballar": {
            "ishlatilgan": profil.get("daily_requests_used", 0) or 0,
            "limit": daily_limit(tarif_nomi, "points"),
        },
        "sanoqlar": sanoqlar,
        "jami_sorov": profil.get("total_messages", 0) or 0,
        "referal": ref,
        "tolovlar": [{
            "id": t.get("id"),
            "stars": t.get("stars"),
            "days": t.get("days"),
            "sana": _sana(t.get("created_at")),
            "qaytarilgan": bool(t.get("refunded_at")),
            "charge_id": t.get("charge_id"),
        } for t in tolovlar],
    })


def _holat_javobi(h: Dict[str, Any]) -> Dict[str, Any]:
    """Tarif holati — panel yuboradigan shakl bilan AYNAN bir xil."""
    return {"tarif": h.get("tarif"), "muddat": _sana(h.get("muddat"))}


def _qolgan_kun(muddat) -> Optional[int]:
    """Bugundan muddatgacha necha kun. O'tib ketgan bo'lsa 0."""
    if not isinstance(muddat, datetime):
        return None
    return max(0, (muddat - datetime.now(muddat.tzinfo)).days)


def _set_premium_tafsiloti(kun, oldin: Dict[str, Any]) -> str:
    """Audit yozuvi — TUZILGAN, ya'ni keyin TIKLASH uchun yaroqli.

    ⚠️ Ilgari bu yerda faqat `"30"` turardi. Amal esa muddatni
    ALMASHTIRADI: admin xato bosgan bo'lsa, eski qiymat hech qayerda
    qolmasdi va uni tiklashning iloji yo'q edi. Endi oldingi tarif va
    ANIQ sana yoziladi.

    `qolgan` — o'sha paytdagi kun soni. U sanadan qayta hisoblanmaydi,
    chunki vaqt o'tgan sari javob o'zgaradi; jurnal esa O'SHA ondagi
    holatni ko'rsatishi kerak.
    """
    return json.dumps({
        "kun": "inf" if kun is None else kun,
        "oldin": {
            "tarif": oldin.get("tarif"),
            "muddat": _sana(oldin.get("muddat")),
            "qolgan": _qolgan_kun(oldin.get("muddat")),
        },
    }, ensure_ascii=False)


@admin_only
@bir_marta
async def premium(request: web.Request):
    """Muddatni BELGILAYDI (qo'shmaydi). `kun: null` — cheksiz.

    ⚠️ Bu amal muddatni USTIDAN yozadi — u tuzatish amali. Qo'shish
    kerak bo'lsa `giveaway_set` (Promo → Sovg'a) ishlatiladi. Farqi
    ekranda ham ko'rinadi: bu yerda «Muddatni belgilash», u yerda
    «qo'shiladi».
    """
    uid = _target(request)
    tana = await _tana(request)
    kun = tana.get("kun", 30)
    # ⚠️ Buzuq qiymatni `None` ga aylantirish MUMKIN EMAS: bu yerda
    # `None` — «cheksiz» degani, ya'ni `{"kun": "o'ttiz"}` yozgan
    # so'rov eng katta sovg'ani olardi. Tushunib bo'lmadi = rad etiladi.
    if kun is not None:
        try:
            kun = int(kun)
        except (TypeError, ValueError):
            kun = "?"
    if kun not in PREMIUM_KUNLARI:
        return web.json_response(
            {"error": f"muddat {PREMIUM_KUNLARI} dan biri bo'lsin"}, status=400)

    # ⭐ OPTIMISTIK TEKSHIRUV. Panel kartochkada KO'RGAN holatni qaytarib
    # yuboradi; server uni tranzaksiya ichida joriy holat bilan
    # solishtiradi. Bu amal muddatni ALMASHTIRADI, ya'ni ekrandagi
    # «20 kun» ni o'chiradi — agar o'sha 20 kun ekran ochilgandan keyin
    # o'zgargan bo'lsa (to'lov, promokod, referal mukofoti), admin
    # O'ZI KO'RMAGAN narsani o'chirgan bo'lardi.
    #
    # ⛔️ MAYDON MAJBURIY, yo'q bo'lsa 400. «Yo'q bo'lsa eskicha ishlasin»
    # degan yo'l butun himoyani BEKOR qiladi: uni chetlab o'tish uchun
    # maydonni yubormaslik kifoya bo'lardi. Panel — bu endpointning
    # YAGONA mijozi va u server bilan bitta jarayonda deploy bo'ladi,
    # ya'ni «eski mijoz» — deploy paytida ochiq qolgan varaq, xolos;
    # u yangilansa (`?v=` hash'i shuni kafolatlaydi) maydon paydo
    # bo'ladi. Eski varaqdagi admin baribir ESKI holatni ko'rsatib
    # turadi, ya'ni uni o'tkazib yuborish xavfning o'zi.
    holat = tana.get("holat")
    if not isinstance(holat, dict) or not holat.get("tarif"):
        return web.json_response(
            {"error": "Profil holati yuborilmadi — panelni yangilang."},
            status=400)
    xom_muddat = holat.get("muddat")
    try:
        kutilgan_muddat = (datetime.fromisoformat(xom_muddat)
                           if xom_muddat else None)
    except (TypeError, ValueError):
        return web.json_response({"error": "muddat formati noto'g'ri"}, status=400)

    natija = await database_module.set_user_premium_checked(
        uid, kun,
        kutilgan_tarif=str(holat["tarif"]),
        kutilgan_muddat=kutilgan_muddat)
    if natija is None:
        return web.json_response({"error": "topilmadi"}, status=404)
    if not natija["ok"]:
        # 409 — panel buni «profilni qayta yukla» deb tushunadi.
        return web.json_response({
            "error": "Foydalanuvchi holati o'zgargan — profilni yangilang.",
            "hozir": _holat_javobi(natija["hozir"]),
        }, status=409)

    await _yoz(request, "set_premium", uid, _set_premium_tafsiloti(
        kun, natija["oldin"]))
    yetdi = await _xabar(uid, (
        "🎉 <b>Sizga Pro tarif berildi!</b>\n\n"
        + ("Muddati: <b>cheksiz</b>." if kun is None else f"Muddati: <b>{kun} kun</b>.")
        + "\n\nBarcha imkoniyatlar ochildi — /profile orqali tekshirib ko'ring."
    ))
    return web.json_response({"ok": True, "xabar_yetdi": yetdi})


@admin_only
@bir_marta
async def plan(request: web.Request):
    """Tarifni o'zgartirish. Hozircha faqat `free` ga tushirish."""
    uid = _target(request)
    tarif = (await _tana(request)).get("tarif", "free")
    if tarif != "free":
        return web.json_response(
            {"error": "Pro berish uchun /premium ishlatiladi"}, status=400)

    await database_module.set_user_plan(uid, "free")
    await _yoz(request, "set_plan", uid, "free")
    # Odam nimadir YO'QOTDI — buni bilishi kerak, aks holda imkoniyat
    # yo'qolganini «bot buzildi» deb tushunadi.
    yetdi = await _xabar(uid, (
        "ℹ️ <b>Tarifingiz Bepul tarifga o'tkazildi.</b>\n\n"
        "Kunlik limitlar bepul tarif bo'yicha hisoblanadi. "
        "Savolingiz bo'lsa — /pro."
    ))
    return web.json_response({"ok": True, "xabar_yetdi": yetdi})


@admin_only
async def quota(request: web.Request):
    """Kunlik sanoqlarni nolga tushirish."""
    uid = _target(request)
    await database_module.reset_user_quota(uid)
    await _yoz(request, "reset_quota", uid)
    # Xabar ATAYLAB yuborilmaydi: kvota tiklash ko'pincha texnik amal,
    # va har safar xabar yuborish odamni bekorga bezovta qilardi.
    return web.json_response({"ok": True})


@admin_only
@bir_marta
async def ban(request: web.Request):
    """Bloklash / ochish."""
    uid = _target(request)
    bloklansinmi = bool((await _tana(request)).get("ban", True))
    if bloklansinmi:
        await database_module.ban_user(uid)
        await _yoz(request, "ban_user", uid)
        # Bloklanganini bot o'zi keyingi xabarda aytadi — ikki marta
        # aytish shart emas.
        return web.json_response({"ok": True, "bloklangan": True})

    await database_module.unban_user(uid)
    await _yoz(request, "unban_user", uid)
    yetdi = await _xabar(uid, (
        "✅ <b>Blok olib tashlandi.</b>\n\n"
        "Botdan yana foydalanishingiz mumkin."
    ))
    return web.json_response({"ok": True, "bloklangan": False, "xabar_yetdi": yetdi})


@admin_only
@bir_marta
async def message(request: web.Request):
    """Adminning foydalanuvchiga yozgan xabari."""
    uid = _target(request)
    matn = str((await _tana(request)).get("matn") or "").strip()
    if not matn:
        return web.json_response({"error": "matn bo'sh"}, status=400)
    if len(matn) > XABAR_MAX:
        return web.json_response(
            {"error": f"matn {XABAR_MAX} belgidan uzun"}, status=400)

    # ⚠️ Admin yozgan matn Telegram'ga HTML bo'lib ketadi. Yopilmagan
    # `<b>` butun xabarni rad ettiradi, shuning uchun ekranlanadi —
    # admin formatlash kerak bo'lsa botning o'zidan yozadi.
    from html import escape
    yetdi = await _xabar(uid, "📨 <b>Admin xabari</b>\n\n" + escape(matn))
    await _yoz(request, "send_message", uid, matn[:200])
    if not yetdi:
        return web.json_response(
            {"error": "xabar yetmadi — foydalanuvchi botni bloklagan bo'lishi mumkin"},
            status=502)
    return web.json_response({"ok": True})


@admin_only
# ⛔️ `@bir_marta` ATAYLAB YO'Q. Bu endpointda takrorlanishdan
# himoya 10 soniyalik keshdan KUCHLIROQ va DOIMIY: `refunded_at`
# ustuni (atomik yozuv, `db/database.py`), undan oldingi 409
# tekshiruvi va Telegram'ning o'z rad javobi. Kesh bularning ustiga
# hech narsa qo'shmaydi, buning o'rniga 409 («allaqachon qaytarilgan»)
# javobini 200 bilan YASHIRARDI — pul yo'lida bu noto'g'ri savdo.
async def refund(request: web.Request):
    """To'lovni qaytarish.

    ⚠️ TARTIB: AVVAL Telegram, KEYIN baza — `handlers/admin/users.py`
    dagi bilan AYNAN bir xil. Telegram refund'ni rad etishi mumkin
    (muddat o'tgan, allaqachon qaytarilgan); teskari tartibda tarif
    olib qo'yilib, pul qaytmasdan qolardi.
    """
    from aiogram.exceptions import TelegramBadRequest
    from core.loader import bot

    try:
        payment_id = int(request.match_info["payment_id"])
    except (KeyError, ValueError):
        return web.json_response({"error": "ID noto'g'ri"}, status=400)

    tolov = await database_module.get_payment_by_id(payment_id)
    if tolov is None:
        return web.json_response({"error": "to'lov topilmadi"}, status=404)
    if tolov.get("refunded_at"):
        return web.json_response({"error": "allaqachon qaytarilgan"}, status=409)

    try:
        await bot.refund_star_payment(
            user_id=tolov["payer_id"],            # PULNI TO'LAGAN odam
            telegram_payment_charge_id=tolov["charge_id"],
        )
    except TelegramBadRequest as e:
        # Telegram'ning o'z sababi — «Xatolik» degan umumiy matn
        # admin uchun foydasiz.
        return web.json_response({"error": f"Telegram rad etdi: {e.message}"}, status=400)
    except Exception:
        logger.exception("[web] refund_star_payment error")
        return web.json_response({"error": "Telegram bilan bog'lanib bo'lmadi"}, status=502)

    try:
        # ⭐ NATIJA TEKSHIRILADI. Bazadagi yozuv atomik:
        # `… WHERE charge_id = $1 AND refunded_at IS NULL RETURNING`
        # (db/database.py). Ya'ni poygada faqat BITTASI yutadi va
        # qolgani `False` oladi. Ilgari natija e'tiborsiz qolardi —
        # natijada yutqazgan so'rov ham auditga yozib, foydalanuvchiga
        # IKKINCHI «pulingiz qaytarildi» xabarini yuborardi.
        belgilandi = await database_module.mark_payment_refunded(
            tolov["charge_id"], request["user_id"])
    except Exception:
        # Pul QAYTARILDI, lekin baza yozilmadi. Bu holat log'da ANIQ
        # qolishi shart: tarif hali ham foydalanuvchida turadi.
        logger.exception(
            f"[web] REFUND QILINDI, LEKIN BAZAGA YOZILMADI: charge={tolov['charge_id']}")
        return web.json_response(
            {"error": "Pul qaytarildi, lekin bazada belgilanmadi. Log'ni tekshiring."},
            status=500)

    if not belgilandi:
        # Boshqa so'rov ulgurdi. Pul bir marta qaytgan, ya'ni bu xato
        # emas — lekin audit va xabar TAKRORLANMAYDI.
        return web.json_response({"ok": True, "takror": True})

    await _yoz(request, "refund_stars", tolov.get("beneficiary_id"), tolov["charge_id"])
    await _xabar(tolov["payer_id"], (
        "↩️ <b>To'lovingiz qaytarildi</b>\n\n"
        f"💰 {tolov['stars']} ⭐ hisobingizga qaytarildi.\n"
        f"🧾 Chek: <code>{tolov['charge_id']}</code>"
    ))
    return web.json_response({"ok": True})


# ═══════════════════════════════════════════════════════════════════
#  JURNAL (REJA 6.5)
# ═══════════════════════════════════════════════════════════════════

JURNAL_SAHIFA = 20


def _kim(user_id: Optional[int], username: Optional[str]) -> Optional[str]:
    """Odamning KO'RINADIGAN nomi — panelda YAGONA formatter.

    Tartib: `@username` → `ID:123`. Yo'q bo'lsa `None`.

    ⚠️ Bitta odam bitta joyda bitta nom bilan atalishi kerak. Ilgari
    jurnalning filtr chiplari `ID:2001717965`, o'sha adminning jadvaldagi
    qatori esa `@jumayeevou` deb yozilardi — bir ekranda ikki nom, va
    admin ular boshqa-boshqa odam deb o'ylashi mumkin edi. Sabab oddiy
    edi: chiplar ro'yxati faqat `admin_id` dan yig'ilardi, username
    umuman so'ralmasdi.
    """
    if username:
        return "@" + username
    return f"ID:{user_id}" if user_id else None


# Audit tafsilotini odam tiliga o'giradigan qoidalar.
#
# ⚠️ Nega o'girish EKRANDA, yozuvda emas: `admin_audit` da ikki yillik
# qator yotibdi va ular allaqachon `«inf»`, `«7d x1»`, `«free»` bo'lib
# yozilgan. Yozuvni o'zgartirish faqat YANGI qatorlarga ta'sir qilardi,
# ya'ni jurnal yarmi odamcha, yarmi texnik bo'lib qolardi — eng yomon
# variant. O'girish shu yerda bo'lsa, eski qator ham odamcha ko'rinadi.
#
# ⚠️ Xom qiymat HECH QACHON YO'QOLMAYDI: qoida mos kelmasa xom satr
# o'zi chiqadi. Jimgina bo'sh qoldirish — auditda eng yomon xatti-harakat.
#
# Bu ro'yxat `core/config.py` da EMAS, chunki uni o'qiydigan ikkinchi
# ekran yo'q (Telegram jurnali 7-bosqichda o'chdi). Ikkinchi iste'molchi
# paydo bo'lsa — `AUDIT_ACTIONS` yoniga ko'chiriladi.
_LIMIT_ASL = "asl qiymat"


def _premium_tafsiloti(xom: str) -> str:
    """`{"kun":30,"oldin":{...}}` → `«30 kun (oldin: 20 kun)»`.

    ⚠️ Buzuq JSON JIM YUTILMAYDI — xom satr o'zi qaytadi. Auditda
    bo'sh katak ko'rsatish qatorni umuman yo'q qilib qo'yardi.
    """
    try:
        d = json.loads(xom)
        kun = d["kun"]
        o = d.get("oldin") or {}
    except (ValueError, KeyError, TypeError):
        return xom

    yangi = "Muddatsiz" if kun == "inf" else f"{kun} kun"
    tarif = o.get("tarif")
    if not tarif or tarif == "free":
        oldingi = TARIF_NOMI.get("free", "Bepul")
    elif o.get("muddat") is None:
        oldingi = "Muddatsiz"
    else:
        qolgan = o.get("qolgan")
        oldingi = f"{qolgan} kun" if isinstance(qolgan, int) else "muddatli"
    return f"{yangi} (oldin: {oldingi})"


def _tafsilot(amal: str, xom: Optional[str]) -> Optional[str]:
    """`«free.points = 500»` → `«Bepul · Kunlik ballar → 500»`."""
    if not xom:
        return None
    t = xom.strip()

    if amal == "set_premium":
        # TUZILGAN yozuv (yangi qatorlar). Eskilari quyidagi
        # qoidalardan o'tadi — ikkalasi yonma-yon yashaydi.
        if t.startswith("{"):
            return _premium_tafsiloti(t)
        if t == "inf":
            return "Muddatsiz"
        m = re.fullmatch(r"sovga (\d+) kun", t)
        if m:
            return f"Sovg'a · {m.group(1)} kun"
        if t.isdigit():
            return f"{t} kun"

    elif amal == "set_plan":
        return TARIF_NOMI.get(t, t)

    elif amal == "limit_change":
        m = re.fullmatch(r"(\w+)\.(\w+) = (.+)", t)
        if m:
            tarif, kalit, qiymat = m.groups()
            return (f"{TARIF_NOMI.get(tarif, tarif)} · "
                    f"{LIMIT_NOMI.get(kalit, kalit)} → "
                    f"{_LIMIT_ASL if qiymat == 'asl' else qiymat}")

    elif amal == "create_promo":
        m = re.fullmatch(r"(\S+) (\d+)d x(\d+)", t)
        if m:
            return f"{m.group(1)} · {m.group(2)} kun · {m.group(3)} marta"

    elif amal == "send_promo":
        m = re.fullmatch(r"(\S+) -> (\d+) ta", t)
        if m:
            return f"{m.group(1)} · {m.group(2)} kishiga yuborildi"

    elif amal == "send_referral":
        m = re.fullmatch(r"(\d+) ta", t)
        if m:
            return f"{m.group(1)} kishiga yuborildi"

    elif amal == "referral_config":
        m = re.fullmatch(r"(\d+) ta -> (\d+) kun", t)
        if m:
            return f"{m.group(1)} do'st → {m.group(2)} kun Pro"

    elif amal == "broadcast":
        m = re.fullmatch(r"segment=(\S+) yuborildi=(\d+) xato=(\d+)", t)
        if m:
            qamrov = SEGMENT_NOMI.get(m.group(1), m.group(1))
            xato = f" · {m.group(3)} ta yetmadi" if m.group(3) != "0" else ""
            return f"{qamrov} · {m.group(2)} kishiga yetdi{xato}"
        m = re.fullmatch(r"rejalashtirildi #(\d+) segment=(\S+)", t)
        if m:
            return (f"Rejalashtirildi #{m.group(1)} · "
                    f"{SEGMENT_NOMI.get(m.group(2), m.group(2))}")

    elif amal == "maintenance":
        holat = "Yoqildi" if t.startswith("yoqildi") else (
            "O'chirildi" if t.startswith("o'chirildi") else None)
        if holat:
            return holat + (" · matn yangilandi" if "matn" in t else "")

    elif amal == "cancel_broadcast":
        m = re.fullmatch(r"#(\d+)", t)
        if m:
            return f"Tarqatma #{m.group(1)}"

    elif amal == "watch_group":
        return f"Guruh {t}"

    elif amal == "user_report":
        # Foydalanuvchi xabari JSON bo'lib yoziladi — jurnalda uning
        # xom shakli chiqmasin, lekin yo'qolmasin ham.
        return t[:120]

    return t


@admin_only
async def journal_audit(request: web.Request):
    """Admin amallari. `?admin=` bilan bitta admin bo'yicha filtr.

    Har qator UCHTA savolga javob beradi: KIM (admin), NIMA (amal +
    tafsilot), KIMGA (foydalanuvchi). Uchinchisi bo'lmasligi mumkin va
    bu normal — limit o'zgartirish yoki texnik ta'til hech kimga
    tegishli emas; panel unday qatorda «—» ko'rsatadi.
    """
    try:
        sahifa = max(0, int(request.query.get("page", 0)))
    except ValueError:
        sahifa = 0
    admin_id = request.query.get("admin")
    try:
        admin_id = int(admin_id) if admin_id else None
    except ValueError:
        admin_id = None

    q, kun = _jurnal_filtr(request)
    rows, jami = await asyncio.gather(
        database_module.get_admin_audit(
            limit=JURNAL_SAHIFA, offset=sahifa * JURNAL_SAHIFA,
            admin_id=admin_id, q=q, kun=kun),
        database_module.count_admin_audit(admin_id, q=q, kun=kun),
    )

    tayyor = []
    adminlar: Dict[int, str] = {}
    for r in rows:
        amal = r.get("action") or ""
        nom, ikonka = audit_nomi(amal)
        aid = r.get("admin_id")
        if aid:
            # Filtr chiplari uchun: nom bilan, quruq ID bilan emas.
            adminlar.setdefault(aid, _kim(aid, r.get("admin_username")) or f"ID:{aid}")
        tayyor.append({
            "id": r.get("id"),
            "vaqt": _sana(r.get("action_time")),
            "admin": _kim(aid, r.get("admin_username")) or "tizim",
            "admin_id": aid,
            "amal": nom,
            "ikonka": ikonka,
            "kimga": _kim(r.get("target_user_id"), r.get("target_username")),
            "kimga_id": r.get("target_user_id"),
            "tafsilot": _tafsilot(amal, (r.get("details") or "")[:200]),
        })

    return web.json_response({
        "rows": tayyor,
        "jami": jami,
        "sahifa": sahifa,
        "sahifalar": max(1, -(-jami // JURNAL_SAHIFA)),
        "adminlar": [{"id": i, "nom": n} for i, n in sorted(adminlar.items())],
    })


@admin_only
async def journal_errors(request: web.Request):
    try:
        sahifa = max(0, int(request.query.get("page", 0)))
    except ValueError:
        sahifa = 0
    q, kun = _jurnal_filtr(request)
    rows, xulosa, jami = await asyncio.gather(
        database_module.recent_errors(
            limit=JURNAL_SAHIFA, offset=sahifa * JURNAL_SAHIFA, q=q, kun=kun),
        database_module.error_summary(),
        # ⚠️ Sanoq FILTR bilan. `xulosa["total"]` butun jadvalning soni,
        # ya'ni qidiruv yoqilganda sahifalar soni yolg'on chiqardi va
        # admin bo'sh sahifalarni varaqlardi.
        database_module.count_errors(q=q, kun=kun),
    )
    return web.json_response({
        "rows": [{
            "id": r.get("id"),
            "vaqt": _sana(r.get("created_at")),
            "tur": r.get("kind") or "?",
            "matn": (r.get("message") or "")[:400],
            "user": r.get("user_id"),
        } for r in rows],
        "xulosa": {
            "kun": xulosa.get("day") or 0,
            "hafta": xulosa.get("week") or 0,
            "jami": xulosa.get("total") or 0,
            "odamlar": xulosa.get("users_day") or 0,
            "turlar": [{"nom": k, "soni": n} for k, n in (xulosa.get("kinds") or [])],
        },
        # Filtrga tushgan son — `xulosa.jami` butun jadvalniki.
        "jami": jami,
        "sahifa": sahifa,
        "sahifalar": max(1, -(-jami // JURNAL_SAHIFA)),
    })


# ═══════════════════════════════════════════════════════════════════
#  CSV EKSPORT
# ═══════════════════════════════════════════════════════════════════
EKSPORT_MAX = 5000          # bitta faylga sig'adigan qator soni

# Nima eksport qilinadi: kalit -> (fayl nomi, sarlavhalar).
# ⚠️ RO'YXAT QATTIQ: `?tur=` dan kelgan qiymat FAQAT shu kalitlardan
# biri bo'lishi mumkin. Aks holda admin kiritgan matn fayl nomiga
# tushib, `Content-Disposition` sarlavhasini buzardi.
EKSPORT_TURLARI = {
    "users": ("foydalanuvchilar",
              ("user_id", "username", "tarif", "muddat", "bloklangan",
               "ro'yxatdan", "oxirgi_faollik")),
    "payments": ("tolovlar",
                 ("id", "sana", "tolovchi", "oluvchi", "yulduz", "kun",
                  "qaytarilgan")),
    "audit": ("audit",
              ("id", "vaqt", "admin_id", "admin", "amal", "kimga_id",
               "kimga", "tafsilot")),
}


# ⚠️ CSV yordamchilari `core/csv_fayl.py` ga KO'CHDI (REJA.md 4.3):
# Telegram Business kartotekasi ham xuddi shu formula himoyasi bilan
# eksport qiladi, ikkinchi nusxa esa bu himoyani biri yo'qotib qo'yadigan
# yo'l bo'lardi. Nomlar shu yerda qoldi — chaqiruvchilar o'zgarmadi.
from core.csv_fayl import csv_katak as _csv_katak, csv_matn as _csv  # noqa: E402


@admin_only
@bir_marta
async def eksport(request: web.Request):
    """CSV yuklab olish: foydalanuvchilar, to'lovlar yoki audit.

    ⚠️ Har eksport AUDITGA yoziladi. Bu ma'lumotni panel ichida
    ko'rishdan boshqacha: fayl chiqib ketadi va qayerda tugashini
    biz boshqarmaymiz, shuning uchun kim qachon nimani olganini
    bilish shart.
    """
    tur = request.query.get("tur") or "users"
    if tur not in EKSPORT_TURLARI:
        return web.json_response({"error": "noma'lum tur"}, status=400)
    nom, sarlavhalar = EKSPORT_TURLARI[tur]

    if tur == "users":
        d = await database_module.list_users(limit=EKSPORT_MAX, offset=0)
        qatorlar = [(
            u.get("user_id"),
            f"@{u['username']}" if u.get("username") else "",
            TARIF_NOMI.get(u.get("plan_type") or "free", u.get("plan_type")),
            _sana(u.get("premium_until")),
            "ha" if u.get("is_banned") else "",
            _sana(u.get("created_at")),
            _sana(u.get("last_seen")),
        ) for u in d["rows"]]
    elif tur == "payments":
        rows = await database_module.all_payments(limit=EKSPORT_MAX)
        qatorlar = [(
            r.get("id"), _sana(r.get("created_at")),
            r.get("payer_id"), r.get("beneficiary_id"),
            r.get("stars"), r.get("days"),
            _sana(r.get("refunded_at")),
        ) for r in rows]
    else:
        rows = await database_module.get_admin_audit(limit=EKSPORT_MAX, offset=0)
        qatorlar = []
        for r in rows:
            amal = r.get("action") or ""
            qatorlar.append((
                r.get("id"), _sana(r.get("action_time")),
                r.get("admin_id"),
                _kim(r.get("admin_id"), r.get("admin_username")) or "tizim",
                audit_nomi(amal)[0],
                r.get("target_user_id"),
                _kim(r.get("target_user_id"), r.get("target_username")) or "",
                _tafsilot(amal, (r.get("details") or "")[:200]),
            ))

    sana = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    fayl = f"{nom}-{sana}.csv"
    baytlar = _csv(sarlavhalar, qatorlar).encode("utf-8")

    # ⚠️ FAYL BRAUZERGA EMAS, TELEGRAMGA. Panel — Mini App, ya'ni
    # Telegram webview'i: `blob:` havolasi bilan yuklab olish u yerda
    # jim yiqiladi (Android'da ayniqsa) va admin hech narsa ko'rmaydi.
    # Hujjat sifatida yuborilgan fayl esa har doim keladi, chatda
    # qoladi va uni boshqa joyga uzatish ham oson.
    yetdi = await _hujjat(request["user_id"], baytlar, fayl,
                          f"📊 <b>{nom}</b> · {len(qatorlar)} qator")
    await _yoz(request, "export", None, f"{tur} · {len(qatorlar)} qator")
    if not yetdi:
        return web.json_response(
            {"error": "fayl yuborilmadi — botni bloklagan bo'lishingiz mumkin"},
            status=502)
    return web.json_response({"ok": True, "qator": len(qatorlar), "fayl": fayl})


async def _hujjat(uid: int, baytlar: bytes, nom: str, izoh: str) -> bool:
    """Faylni Telegram hujjati qilib yuboradi. Xato = False, hech qachon
    istisno tashlamaydi — eksport yiqilsa ham panel ishlayveradi."""
    try:
        from aiogram.types import BufferedInputFile
        from core.loader import bot
        await bot.send_document(
            uid, BufferedInputFile(baytlar, filename=nom),
            caption=izoh, parse_mode="HTML")
        return True
    except Exception as e:
        logger.warning(f"[Panel] eksport yuborilmadi uid={uid}: {e}")
        return False


def _kun_qatori(rows: List[Dict[str, Any]], kunlar: int,
                *, kalit: str = "kun", soni: str = "soni",
                kishi: str = "kishi") -> List[Dict[str, Any]]:
    """Bo'sh kunlarni 0 bilan to'ldirilgan kunlik qator.

    ⚠️ Bu ikkita grafik uchun UMUMIY. Ikkinchi nusxa yozilsa, biri
    bo'sh kunni tashlab ketadigan bo'lib qolar va o'sha grafik
    tushishni ko'rsatmay, tekis chiziq chizardi.
    """
    bor = {r[kalit]: r for r in rows}
    bugun = datetime.now(TIMEZONE).date()
    out = []
    for orqaga in range(kunlar - 1, -1, -1):
        kun = bugun - timedelta(days=orqaga)
        r = bor.get(kun) or {}
        out.append({
            "kun": kun.isoformat(),
            "nom": HAFTA[kun.weekday()],
            "soni": r.get(soni, 0) or 0,
            "kishi": r.get(kishi, 0) or 0,
        })
    return out


@admin_only
async def journal_revenue(request: web.Request):
    d = await database_module.revenue_stats()
    sotuv = d.get("sales_30d") or 0
    stars_30d = d.get("stars_30d") or 0
    # Tariflar nomi `PRO_PLANS` dan — narx ro'yxati o'zgarsa jurnal
    # o'zidan to'g'rilanadi.
    nomlar = {kun: nom for kun, _s, nom, _b in PRO_PLANS}
    return web.json_response({
        "bugun": d.get("stars_today") or 0,
        "oy": stars_30d,
        "jami": d.get("stars_total") or 0,
        "sotuv_30d": sotuv,
        "qaytarilgan": d.get("refunds") or 0,
        # «O'rtacha chek» — 30 kunlik summa / 30 kunlik sotuv. Sotuv
        # bo'lmasa `None`: nolga bo'lish o'rniga «—».
        "ortacha": round(stars_30d / sotuv) if sotuv else None,
        "tariflar": [{
            "kun": kun,
            "nom": nomlar.get(kun, f"{kun} kun"),
            "soni": soni,
        } for kun, soni in (d.get("by_plan") or [])],
        # Kunlik grafik. Bazada FAQAT sotuv bo'lgan kun bor, ya'ni jim
        # kun qatorda umuman yo'q — uni tashlab ketsak grafik «yaxshi»
        # ko'rinadi, chunki tushish ko'rinmaydi. Shuning uchun 30 kunning
        # hammasi to'ldiriladi, sotuvsiz kun = 0. Bu `overview` dagi
        # so'rovlar grafigi bilan AYNAN bir xil qoida.
        "kunlik": _kun_qatori(d.get("daily") or [], 30,
                              soni="stars", kishi="soni"),
    })


# ═══════════════════════════════════════════════════════════════════
#  SOZLAMALAR (REJA 6.6)
# ═══════════════════════════════════════════════════════════════════

# `premium` ataylab yo'q: u cheksiz tarif, o'zgartiradigan limiti yo'q.
LIMIT_TARIFLARI = ("free", "pro")
# Admin ham xato yozadi. Cheksizlik uchun ALOHIDA tarif bor, shuning
# uchun bu yerda «juda katta son = cheksiz» yo'li ataylab yopilgan.
LIMIT_MAX = 100000

# Panel ishga tushgan payt. Modul bot bilan bitta jarayonda, ish
# boshlanishida import qilinadi — ya'ni bu amalda jarayonning vaqti.
BOSHLANGAN = time.time()


@admin_only
async def limits(request: web.Request):
    """Kunlik limitlar jadvali. Nomlar `LIMIT_NOMI` dan (yagona ro'yxat)."""
    ozgargan = await database_module.get_limit_overrides()
    return web.json_response({
        "rows": [{
            "kalit": kalit,
            "nom": nom,
            # Izoh `LIMIT_IZOHI` dan — ball narxlari `MESSAGE_COST_*`
            # dan yig'iladi, ya'ni narx o'zgarsa matn o'zi to'g'rilanadi.
            "izoh": LIMIT_IZOHI.get(kalit, ""),
            "tariflar": {
                tarif: {
                    # ⚠️ Qiymat `daily_limit()` dan EMAS, o'zgartirish va
                    # `PLAN_LIMITS` dan alohida olinadi: panel «bu qiymat
                    # qayerdan keldi»ni ko'rsatishi kerak, `daily_limit()`
                    # esa ikkalasini birlashtirib, farqni yo'qotib beradi.
                    "qiymat": (ozgargan.get(tarif) or {}).get(
                        kalit, PLAN_LIMITS[tarif].get(kalit)),
                    "ozgargan": kalit in (ozgargan.get(tarif) or {}),
                    "asl": PLAN_LIMITS[tarif].get(kalit),
                } for tarif in LIMIT_TARIFLARI
            },
        } for kalit, nom in LIMIT_NOMI.items()],
        "tariflar": list(LIMIT_TARIFLARI),
    })


@admin_only
async def limit_set(request: web.Request):
    """Bitta limitni o'zgartiradi.

    ⚠️ ENG MUHIM QATOR — `apply_limit_overrides()`. Usiz bazada yangi
    qiymat turadi, bot esa ESKISI bilan ishlaydi: panel «o'zgardi» deb
    ko'rsatadi, foydalanuvchi eski limitga uriladi va buni hech narsa
    aytmaydi. REJA 3.1 dagi «panel bot jarayonining ichida» qarorining
    butun sababi shu bitta chaqiruv.
    """
    tana = await _tana(request)
    tarif, kalit, qiymat = tana.get("tarif"), tana.get("kalit"), tana.get("qiymat")

    if tarif not in LIMIT_TARIFLARI:
        return web.json_response({"error": "tarif noto'g'ri"}, status=400)
    if kalit not in LIMIT_NOMI:
        return web.json_response({"error": "limit nomi noto'g'ri"}, status=400)

    # `None` — «o'zgartirishni olib tashla», ya'ni config qiymatiga
    # qaytish. Bu CHEKSIZLIK EMAS. Shuning uchun buzuq qiymatni `None` ga
    # aylantirib yuborish mumkin emas: `{"qiymat": "o'ttiz"}` limitni
    # jimgina tiklab yuborardi va admin o'zgartirdim deb o'ylab turardi.
    if qiymat is not None:
        # ⚠️ `True` — Python'da `int`. Tekshirilmasa `{"qiymat": true}`
        # butun tarifning limitini 1 ga tushirardi.
        if isinstance(qiymat, bool):
            return web.json_response({"error": "qiymat butun son bo'lsin"}, status=400)
        try:
            qiymat = int(qiymat)
        except (TypeError, ValueError):
            return web.json_response({"error": "qiymat butun son bo'lsin"}, status=400)
        if not 0 <= qiymat <= LIMIT_MAX:
            return web.json_response(
                {"error": f"qiymat 0 dan {LIMIT_MAX} gacha bo'lsin"}, status=400)

    yangi = await database_module.set_limit_override(tarif, kalit, qiymat)
    config_module.apply_limit_overrides(yangi)
    await _yoz(request, "limit_change", None,
               f"{tarif}.{kalit} = {'asl' if qiymat is None else qiymat}")
    return web.json_response({
        "ok": True,
        # Panel qayta so'rov yubormasin: yangi qiymat darhol qaytadi va u
        # `daily_limit()` dan olinadi — ya'ni bot AYNAN shu raqam bilan
        # ishlayotgani tasdiqlanadi, panel o'zi hisoblab qo'ymaydi.
        "qiymat": daily_limit(tarif, kalit),
        "ozgargan": qiymat is not None,
    })


@admin_only
async def maintenance(request: web.Request):
    """Texnik ta'til holati + tizim kartochkasi."""
    t = await database_module.get_maintenance()
    from handlers import messages as messages_module    # sikl importni oldini olish
    ish = int(time.time() - BOSHLANGAN)
    return web.json_response({
        "active": t["active"],
        "matn": t["message"],
        "holat": {
            # Maketda «Oxirgi deploy 44003a8 · 21:12» qotirilgandi. Bu
            # ma'lumot Railway muhit o'zgaruvchisida bor, LEKIN mahalliy
            # ishga tushirishda yo'q — shunda `null` qaytadi va qator
            # umuman chiqmaydi. Soxta commit ko'rsatilmaydi.
            "commit": (os.getenv("RAILWAY_GIT_COMMIT_SHA") or "")[:7] or None,
            "ishlash": f"{ish // 86400}k {ish % 86400 // 3600}s {ish % 3600 // 60}d",
            "mavzu": bool(getattr(messages_module, "TOPICS_ENABLED", False)),
            "baza": database_module.pool is not None,
            "model": GPT_MODEL_DISPLAY_NAME,
        },
    })


@admin_only
async def maintenance_set(request: web.Request):
    """Rejimni yoqish/o'chirish va matnni tahrirlash."""
    tana = await _tana(request)
    matn = tana.get("matn")
    if matn is not None:
        matn = str(matn).strip()
        if not matn:
            return web.json_response({"error": "matn bo'sh"}, status=400)
        if len(matn) > XABAR_MAX:
            return web.json_response(
                {"error": f"matn {XABAR_MAX} belgidan uzun"}, status=400)

    # `active` yuborilmasa hozirgi holat saqlanadi — «faqat matnni
    # tahrirladim» degan so'rov rejimni tasodifan yoqib yubormasin.
    if "active" in tana:
        faol = bool(tana["active"])
    else:
        faol = (await database_module.get_maintenance())["active"]

    await database_module.set_maintenance(faol, matn)
    await _yoz(request, "maintenance", None,
               ("yoqildi" if faol else "o'chirildi") + (" + matn" if matn else ""))
    yangi = await database_module.get_maintenance()
    return web.json_response({"ok": True, "active": yangi["active"],
                              "matn": yangi["message"]})


@admin_only
async def watch(request: web.Request):
    """Kuzatuv guruhi va ro'yxati."""
    guruh, ruyxat = await asyncio.gather(
        database_module.get_watch_group_id(),
        database_module.get_watchlist(),
    )
    return web.json_response({
        "guruh": guruh,
        "rows": [{
            "user_id": r.get("user_id"),
            "username": r.get("username"),
            "added_at": _sana(r.get("added_at")),
        } for r in ruyxat],
    })


# Telegram xatosini ADMIN TUSHUNADIGAN sababga o'giradi. Telegram'ning
# o'z matni inglizcha va texnik («Bad Request: chat not found»), admin
# esa undan nima qilishni bilmaydi.
#
# ⚠️ Kalit — Telegram javobining MATNI. Bu mo'rt, lekin boshqa yo'l
# yo'q: Bot API bu holatlar uchun alohida kod bermaydi. Shuning uchun
# mos kelmagani JIM YUTILMAYDI — oxirgi qator Telegram matnini o'zini
# ko'rsatadi, ya'ni yangi holat paydo bo'lsa admin baribir sabab ko'radi.
# ⚠️ Ro'yxat `core/config.py::GURUH_XATOSI` da — bu yerda nusxasi YO'Q.
# Uni ogohlantirish yuboruvchi va kuzatuv nusxalovchi ham o'qiydi;
# uchta nusxa bo'lsa panel bir sababni, banner boshqasini aytardi.


async def _guruh_sinovi(guruh: int, admin_id: int) -> Optional[str]:
    """Guruhga sinov xabari. Qaytadi: xato sababi yoki `None`."""
    from aiogram.exceptions import TelegramAPIError
    from core.loader import bot
    from html import escape          # `_xabar` dagi bilan bir xil naqsh

    # Kim ulagani — xabarda ko'rinsin. Nomni o'qish BEZAK: u yiqilsa
    # ham sinov o'tishi kerak, aks holda bazadagi bir soniyalik uzilish
    # butun amalni to'xtatardi.
    kim = f"ID {admin_id}"
    try:
        meta = await database_module.get_admin_meta(admin_id) or {}
        nom = meta.get("username")
        if nom:
            kim = f"@{nom} (ID {admin_id})"
    except Exception:
        logger.warning(f"[web] {admin_id} nomi o'qilmadi — ID ishlatiladi")

    try:
        await bot.send_message(
            guruh,
            "✅ <b>Kuzatuv guruhi ulandi</b>\n\n"
            f"Ulagan: {escape(kim)}\n"
            "Bundan buyon ogohlantirishlar va kuzatuv xabarlari shu yerga keladi.",
            parse_mode="HTML")
    except TelegramAPIError as e:
        sabab = guruh_xato_sababi(str(getattr(e, "message", "") or e))
        if sabab:
            return sabab
        return f"Telegram rad etdi: {getattr(e, 'message', None) or e}"
    # ⚠️ Yiqilgan sinovda HOLAT YOZILMAYDI: bu hali saqlanmagan NOMZOD
    # guruh, ya'ni uning xatosi hozirgi ishlayotgan guruh haqida hech
    # narsa demaydi. Faqat muvaffaqiyat yoziladi — va u `set_watch_group_id`
    # bilan birga eski bannerni o'chiradi.
    except Exception:
        logger.exception("[web] guruh sinovi yiqildi")
        return "Telegram bilan bog'lanib bo'lmadi — keyinroq urinib ko'ring."
    return None


@admin_only
@bir_marta
async def watch_set(request: web.Request):
    """Kuzatuvga qo'shish / olib tashlash / guruhni o'zgartirish.

    ⚠️ Har uchalasidan keyin `load_watch_cache()`. Kuzatuv tekshiruvi
    (`get_watch_target()`) HAR xabarda, sinxron, bazaga bormasdan
    ishlaydi — ya'ni u faqat RAM keshini biladi. Kesh yangilanmasa panel
    «qo'shildi» deb ko'rsatadi, xabarlar esa guruhga tushmaydi va buni
    hech narsa aytmaydi.

    `add_watch` / `remove_watch` keshni o'zi ham yangilaydi; bu chaqiruv
    — kafolat: kelajakda yangi mutatsiya qo'shilib kesh qatori unutilsa,
    teshik shu yerda yopiladi. Admin amali, issiq yo'l emas.
    """
    tana = await _tana(request)
    amal = tana.get("amal")

    if amal == "group":
        xom = str(tana.get("guruh") or "").strip()
        try:
            guruh = int(xom)
        except (TypeError, ValueError):
            return web.json_response(
                {"error": "Guruh ID butun son bo'lsin (masalan -1002481…)"}, status=400)

        # ⭐ AVVAL SINOV XABARI, KEYIN SAQLASH. Ilgari bu yerda faqat
        # `int()` tekshirilardi: noto'g'ri ID kiritilsa panel «Saqlandi»
        # deb yozardi va ogohlantirishlar jimgina HECH QAYERGA
        # bormasdi — aynan o'sha paytda ular kerak bo'ladi.
        #
        # ⚠️ Tartib `refund` dagi bilan bir xil sababdan: Telegram
        # avval, baza keyin. Aks holda baza yangi guruhni ko'rsatib
        # turardi-yu, u yerga hech narsa yetmasdi.
        xato = await _guruh_sinovi(guruh, request["user_id"])
        if xato:
            return web.json_response({"error": xato}, status=400)

        await database_module.set_watch_group_id(guruh)
        await database_module.load_watch_cache()
        await _yoz(request, "watch_group", None, str(guruh))
        return web.json_response({"ok": True, "guruh": guruh})

    if amal not in ("add", "remove"):
        return web.json_response({"error": "amal noma'lum"}, status=400)

    kim = str(tana.get("kim") or "").strip()
    if not kim:
        return web.json_response({"error": "ID yoki @username yozing"}, status=400)
    uid = await database_module.get_user_by_identifier(kim)
    if not uid:
        return web.json_response(
            {"error": "Bunday foydalanuvchi topilmadi — u botga /start bermagan."},
            status=404)

    if amal == "add":
        await database_module.add_watch(uid, request["user_id"])
        await database_module.load_watch_cache()
        await _yoz(request, "watch_add", uid)
        return web.json_response({"ok": True, "user_id": uid})

    await database_module.remove_watch(uid)
    await database_module.load_watch_cache()
    await _yoz(request, "watch_remove", uid)
    return web.json_response({"ok": True, "user_id": uid})


@admin_only
async def admins(request: web.Request):
    """Panelga kira oladigan HAMMA odam.

    ⚠️ Manba `get_admins()` EMAS, `get_panel_admins()`. Farqi jonli
    bazada ko'rindi: `admins` jadvali bo'sh, superadmin esa bor — ya'ni
    `get_admins()` ga tayangan ekran «hech kim kira olmaydi» deb turgan
    bo'lardi, holbuki bitta odam kira oladi. Huquq tekshiruvi ikkala
    jadvalni ham ko'radi, ro'yxat ham ko'rishi shart.

    Funksiya `is_super` ni bitta so'rovda qaytaradi — har qator uchun
    alohida `is_superadmin()` chaqirish N+1 bo'lardi.
    """
    return web.json_response({"rows": [{
        "user_id": a["user_id"],
        "username": a.get("username"),
        "nom": a.get("display_name"),
        "created_at": a.get("created_at"),
        "super": a.get("is_super", False),
        # Panel o'z qatorida «O'chirish» tugmasini ko'rsatmasligi uchun.
        # Haqiqiy himoya server tomonda — `_check_can_remove_admin()`.
        "ozim": a["user_id"] == request["user_id"],
    } for a in await database_module.get_panel_admins()]})


@admin_only
async def admins_set(request: web.Request):
    """Admin qo'shish / o'chirish.

    ⚠️ O'CHIRISH QOIDASI QAYTA YOZILMAYDI. `_check_can_remove_admin()` —
    Telegram ekrani ishlatadigan AYNAN o'sha darvoza (o'zini o'chirmaslik,
    superadminni o'chirmaslik, yangi admin uch kun kutishi, oxirgi admin
    qolmasligi). Bu yerda «soddaroq» tekshiruv yozilsa panel botdan
    ZAIFROQ eshik bo'lib qolardi va buni hech narsa ushlamasdi.
    """
    from handlers.admin.common import _check_can_remove_admin
    from services import menu as menu_module

    tana = await _tana(request)
    amal = tana.get("amal")
    try:
        uid = int(str(tana.get("kim") or "").strip())
    except (TypeError, ValueError):
        # ⚠️ Telegram ekrani ham FAQAT sonli ID qabul qiladi, va bu
        # ataylab: @username egasi uni o'zgartirsa nom boshqa odamga
        # o'tib ketadi — admin huquqini bunday manzilga bog'lab bo'lmaydi.
        return web.json_response(
            {"error": "Faqat sonli ID. @username o'zgarib, boshqa odamga o'tishi mumkin."},
            status=400)

    if amal == "add":
        if await database_module.is_admin(uid):
            return web.json_response({"error": "Bu odam allaqachon admin."}, status=400)
        # Username bazadan olinadi (bo'lmasa `None`) — ro'yxatda odam
        # quruq raqam emas, nomi bilan ko'rinishi uchun.
        try:
            prof = await database_module.get_full_user_profile(uid)
        except Exception:
            prof = None
        nom = (prof or {}).get("username")
        await database_module.add_admin(
            uid, username=(nom if nom and nom != "Mavjud emas" else None))
        await _yoz(request, "add_admin", uid)
        # Ko'k «Panel» tugmasi darhol paydo bo'lsin — aks holda yangi
        # admin panelga faqat keyingi `/start` dan keyin kira olardi.
        try:
            await menu_module.sync_menu_button(uid, True)
        except Exception:
            logger.exception(f"[web] {uid} uchun panel tugmasi qo'yilmadi")
        return web.json_response({"ok": True})

    if amal != "remove":
        return web.json_response({"error": "amal noma'lum"}, status=400)

    xato = await _check_can_remove_admin(request["user_id"], uid)
    if xato:
        return web.json_response({"error": xato}, status=403)
    await database_module.remove_admin(uid)
    await _yoz(request, "remove_admin", uid)
    try:
        await menu_module.sync_menu_button(uid, False)
    except Exception:
        logger.exception(f"[web] {uid} uchun panel tugmasi olinmadi")
    return web.json_response({"ok": True})

# ═══════════════════════════════════════════════════════════════════
#  PROMO VA SOVG'A (REJA 6.4)
# ═══════════════════════════════════════════════════════════════════

PROMO_RO_YXAT = 30       # ro'yxatda ko'rinadigan kodlar soni
SOVGA_MAX = 20           # bir martada nechta odamga


def _kod_holati(c: Dict[str, Any]) -> str:
    """Kodning ko'rinadigan holati: `faol` / `tugagan` / `bekor`.

    ⚠️ Uchta sabab, uchta boshqa holat emas: admin uchun «nega
    ishlamayapti» savoliga javob shu. «Tugagan» — limiti to'lgan YOKI
    muddati o'tgan; ikkalasi ham «endi ishlamaydi» degani.
    """
    if c.get("revoked"):
        return "bekor"
    muddat = c.get("expires_at")
    if isinstance(muddat, datetime) and muddat <= datetime.now(muddat.tzinfo):
        return "tugagan"
    if (c.get("used_count") or 0) >= (c.get("max_uses") or 0):
        return "tugagan"
    return "faol"


@admin_only
async def promo(request: web.Request):
    """Promokodlar ro'yxati."""
    kodlar = await database_module.list_promo_codes(limit=PROMO_RO_YXAT)
    return web.json_response({
        "rows": [{
            "kod": c.get("code"),
            "kun": c.get("days"),
            "ishlatilgan": c.get("used_count") or 0,
            "max": c.get("max_uses"),
            "muddat": _sana(c.get("expires_at")),
            "holat": _kod_holati(c),
        } for c in kodlar],
    })


@admin_only
async def promo_set(request: web.Request):
    """Kod yaratish yoki bekor qilish.

    ⚠️ Tekshiruv bu yerda YO'Q: `database.clean_promo_spec()` — Telegram
    ekrani ishlatadigan aynan o'sha sof funksiya. Qoidani ikkinchi marta
    yozish `ACTION_LABELS` bilan bo'lgan xatoning aynan o'zi bo'lardi.
    """
    tana = await _tana(request)
    amal = tana.get("amal")

    if amal == "revoke":
        kod = str(tana.get("kod") or "").strip()
        if not kod:
            return web.json_response({"error": "kod bo'sh"}, status=400)
        if not await database_module.revoke_promo_code(kod):
            return web.json_response({"error": "Bunday kod yo'q."}, status=404)
        await _yoz(request, "revoke_promo", None, kod.upper())
        return web.json_response({"ok": True})

    if amal != "create":
        return web.json_response({"error": "amal noma'lum"}, status=400)

    spec, xato = database_module.clean_promo_spec(
        tana.get("kod"), tana.get("kun"), tana.get("max"), tana.get("muddat"))
    if xato:
        return web.json_response({"error": xato}, status=400)
    kod, kun, soni, muddat = spec

    if not await database_module.create_promo_code(
            kod, kun, soni, muddat, request["user_id"]):
        return web.json_response({"error": f"{kod} kodi allaqachon mavjud."}, status=409)
    await _yoz(request, "create_promo", None, f"{kod} {kun}d x{soni}")
    return web.json_response({"ok": True, "kod": kod})


@admin_only
async def giveaway(request: web.Request):
    """Bepul berilgan Pro ko'rsatkichlari.

    ⚠️ Maketda bu yerda «Sovg'alar tarixi» kartochkasi bor edi —
    `@malika_r · promokod · 30 kun` kabi qatorlar bilan. Bunday jadval
    bazada YO'Q: `promo_redemptions` kim ishlatganini biladi, referal
    mukofoti `referrals` da, admin sovg'asi esa `admin_audit` da —
    uchalasini birlashtirgan ko'rinish hech qayerda yozilmaydi. Uni
    yasash uchun yangi SQL kerak bo'lardi, bu esa shu faylning qoidasini
    buzadi (REJA 3.2). Shuning uchun kartochka `giveaway_stats()` ning
    HAQIQIY raqamlariga almashtirildi: nechta kod faol, nechta marta
    ishlatilgan, qancha kun bepul berilgan, referal nechtasi mukofotga
    yetgan. Bu savolga («bepul Pro bizga qancha turyapti») to'g'ridan
    javob beradi, soxta tarixdan farqli.
    """
    d = await database_module.giveaway_stats()
    promo_kun = d.get("promo_days") or 0
    return web.json_response({
        "kodlar": {
            "faol": d.get("active_codes") or 0,
            "jami": d.get("total_codes") or 0,
            "ishlatilgan": d.get("redemptions") or 0,
            "kun": promo_kun,
        },
        "referal": {
            "taklif": d.get("invited") or 0,
            "yetgan": d.get("qualified") or 0,
            "mukofot": d.get("rewarded") or 0,
        },
    })


@admin_only
@bir_marta
async def giveaway_set(request: web.Request):
    """Bir yoki bir nechta odamga bepul Pro.

    ⚠️ `extend=True`: 20 kuni qolgan odamga 30 kun sovg'a qilinsa u 50
    kun oladi, 30 emas. Kartochkadagi «Pro berish» esa ataylab USTIDAN
    yozadi (`set_user_premium` ning asl xatti-harakati) — u tuzatish
    amali, bu esa sovg'a. Ikkisi boshqa narsa.
    """
    tana = await _tana(request)
    kun = tana.get("kun")
    if isinstance(kun, bool):
        return web.json_response({"error": "kun butun son bo'lsin"}, status=400)
    try:
        kun = int(kun)
    except (TypeError, ValueError):
        return web.json_response({"error": "kun butun son bo'lsin"}, status=400)
    # Cheksiz sovg'a bu yerda YO'Q: «cheksiz» — kartochkadagi bitta
    # odamga qo'lda beriladigan amal, ro'yxatga emas.
    if not 0 < kun <= database_module.PROMO_KUN_MAX:
        return web.json_response(
            {"error": f"kun 1 dan {database_module.PROMO_KUN_MAX} gacha bo'lsin"},
            status=400)

    xom = str(tana.get("kimlar") or "")
    tokenlar = [t for t in re.split(r"[\s,]+", xom) if t][:SOVGA_MAX]
    if not tokenlar:
        return web.json_response({"error": "Kimga? ID yoki @username yozing."}, status=400)

    berildi, topilmadi, yetmadi = [], [], []
    korilgan = set()
    for token in tokenlar:
        uid = await database_module.get_user_by_identifier(token)
        if not uid:
            topilmadi.append(token)
            continue
        if uid in korilgan:
            continue
        korilgan.add(uid)
        await database_module.set_user_premium(uid, kun, extend=True)
        await _yoz(request, "set_premium", uid, f"sovga {kun} kun")
        if await _xabar(uid, (
                "🎁 <b>Sizga sovg'a — Pro tarif!</b>\n\n"
                f"Muddati: <b>{kun} kun</b> qo'shildi.\n\n"
                "Barcha imkoniyatlar ochildi — /profile orqali ko'ring.")):
            berildi.append(uid)
        else:
            # ⚠️ Xabar yetmasa ham Pro BERILGAN. Ro'yxatda alohida
            # ko'rsatiladi: admin «berilmadi» deb ikkinchi marta
            # yubormasligi kerak.
            yetmadi.append(uid)
    return web.json_response({
        "ok": bool(berildi or yetmadi),
        "berildi": berildi, "yetmadi": yetmadi, "topilmadi": topilmadi,
    })


@admin_only
async def referral(request: web.Request):
    """Umumiy referal sharti (shaxsiy emas — `user_id=None`)."""
    d = await database_module.get_referral_config()
    return web.json_response({
        "required": d["required"],
        "reward_days": d["reward_days"],
        # ⚠️ `max_rewards` ATAYLAB o'zgartirilmaydi — u abuse tavani.
        # Panel uni faqat KO'RSATADI, tugmasi yo'q (`database.py` izohi).
        "max_rewards": d["max_rewards"],
        "chegara": {"required": database_module.REFERRAL_REQUIRED_MAX,
                    "reward_days": database_module.REFERRAL_REWARD_DAYS_MAX},
    })


@admin_only
async def referral_set(request: web.Request):
    """Referal shartini o'zgartirish.

    ⚠️ Tekshiruv `database.clean_referral_config()` da — Telegram ekrani
    ham o'shani chaqiradi. «3 do'st → 300 kun» kabi yozuv bitta odamga
    bir yilda Pro yig'ib berardi, va chegara ekranga emas, funksiyaga
    qo'yilgan.
    """
    tana = await _tana(request)
    req, days, xato = database_module.clean_referral_config(
        tana.get("required"), tana.get("reward_days"))
    if xato:
        return web.json_response({"error": xato}, status=400)
    await database_module.set_referral_config(req, days)
    await _yoz(request, "referral_config", None, f"{req} ta -> {days} kun")
    return web.json_response({"ok": True, "required": req, "reward_days": days})


# ═══════════════════════════════════════════════════════════════════
#  TARQATMA — FAQAT KO'RISH (REJA 6.7)
# ═══════════════════════════════════════════════════════════════════

@admin_only
async def broadcasts(request: web.Request):
    """Rejalashtirilgan tarqatmalar.

    ⚠️ Yangi tarqatma bu yerdan YUBORILMAYDI va bu ataylab (REJA 2):
    bot xabarni `copy_message` bilan uzatadi, ya'ni adminning botga
    yuborgan xabari odamlarga AYNAN o'sha holida yetadi — albom,
    formatlash, premium emoji bilan. Webda qayta yig'ilgan xabar buni
    yo'qotardi.

    Maketda bu yerda yana «Oxirgi tarqatma» kartochkasi bor edi
    (yuborilgan/yetmagan/bloklagan/davomiyligi). Bunday yozuv bazada
    yo'q — `scheduled_broadcasts` faqat REJALASHTIRILGANNI biladi,
    yuborilgani esa `sent_at` bilan belgilanadi va natijasi hech qayerda
    saqlanmaydi. Kartochka olib tashlandi: soxta raqam ko'rsatishdan
    ko'ra yo'qligini aytgan yaxshi.
    """
    rows = await database_module.list_scheduled_broadcasts()
    return web.json_response({
        "rows": [{
            "id": r.get("id"),
            "segment": SEGMENT_NOMI.get(r.get("segment"), r.get("segment")),
            "vaqt": _sana(r.get("run_at")),
        } for r in rows],
    })


@admin_only
async def broadcast_cancel(request: web.Request):
    """Rejalashtirilgan tarqatmani bekor qilish."""
    try:
        bid = int(request.match_info["broadcast_id"])
    except (KeyError, ValueError):
        return web.json_response({"error": "ID noto'g'ri"}, status=400)
    if not await database_module.cancel_scheduled_broadcast(bid):
        # Yuborilgan yoki allaqachon o'chirilgan — ikkalasi ham «endi
        # bekor qilib bo'lmaydi», va ikkinchi urinish xato emas.
        return web.json_response(
            {"error": "Bu tarqatma yo'q yoki allaqachon yuborilgan."}, status=404)
    await _yoz(request, "cancel_broadcast", None, f"#{bid}")
    return web.json_response({"ok": True})


@admin_only
async def meta(request: web.Request):
    """Panel bir marta o'qiydigan ro'yxatlar — YAGONA MANBADAN.

    ⚠️ Bularning hammasi ilgari `panel.js` ichida QO'LDA yozilgan edi
    (`PLAN = {pro: "Pro", free: "Bepul"}`) va o'sha nusxada `premium`
    umuman yo'q edi — ya'ni cheksiz tarifdagi odam jadvalda «Pro» bo'lib
    ko'rinardi. Bu loyihada bir xil xato beshinchi marta takrorlangan
    joy (`CLAUDE.md`, «Four label maps»), shuning uchun panel endi
    ro'yxatni O'YLAB TOPMAYDI — shu yerdan oladi.

    Javob o'zgarmas: sessiya boshida bir marta so'raladi.
    """
    return web.json_response({
        "tariflar": TARIF_NOMI,
        "ranglar": TARIF_RANGI,
        "limitlar": LIMIT_NOMI,
        "limit_izohi": LIMIT_IZOHI,
        "qamrovlar": SEGMENT_NOMI,
        "grafik_kunlari": list(GRAFIK_KUNLARI),
        # Tasdiq oynasida «eng ko'pi bilan N qator» deyiladi. Panel bu
        # sonni O'YLAB TOPMASLIGI kerak — u shu faylda, bitta joyda.
        "eksport_max": EKSPORT_MAX,
    })


def register(app: web.Application) -> None:
    app.router.add_get("/api/meta", meta)
    app.router.add_get("/api/overview", overview)
    app.router.add_get("/api/stats", stats)
    app.router.add_get("/api/users", users)
    app.router.add_get("/api/users/{user_id}", user)
    app.router.add_post("/api/users/{user_id}/premium", premium)
    app.router.add_post("/api/users/{user_id}/plan", plan)
    app.router.add_post("/api/users/{user_id}/quota", quota)
    app.router.add_post("/api/users/{user_id}/ban", ban)
    app.router.add_post("/api/users/{user_id}/message", message)
    app.router.add_post("/api/payments/{payment_id}/refund", refund)
    app.router.add_get("/api/journal/audit", journal_audit)
    app.router.add_get("/api/journal/errors", journal_errors)
    app.router.add_get("/api/journal/revenue", journal_revenue)
    app.router.add_post("/api/export", eksport)
    app.router.add_get("/api/limits", limits)
    app.router.add_post("/api/limits", limit_set)
    app.router.add_get("/api/maintenance", maintenance)
    app.router.add_post("/api/maintenance", maintenance_set)
    app.router.add_get("/api/watch", watch)
    app.router.add_post("/api/watch", watch_set)
    app.router.add_get("/api/admins", admins)
    app.router.add_post("/api/admins", admins_set)
    app.router.add_get("/api/promo", promo)
    app.router.add_post("/api/promo", promo_set)
    app.router.add_get("/api/giveaway", giveaway)
    app.router.add_post("/api/giveaway", giveaway_set)
    app.router.add_get("/api/referral", referral)
    app.router.add_post("/api/referral", referral_set)
    app.router.add_get("/api/broadcasts", broadcasts)
    app.router.add_delete("/api/broadcasts/{broadcast_id}", broadcast_cancel)
