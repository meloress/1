import asyncio
import json

from aiogram import types
from core.loader import logger
from services import namoz, obhavo, valyuta, vidjet
from datetime import datetime, timezone, timedelta
from db.database import get_full_user_profile, list_scheduled_tasks
from core.config import (
    MESSAGE_COST_TEXT, MESSAGE_COST_PHOTO, MESSAGE_COST_VOICE,
    MESSAGE_COST_DOCUMENT, plan_limits, daily_limit,
)

_FEATURE_COSTS = [
    ("✉️ <b>Matnli xabar</b>", MESSAGE_COST_TEXT),
    ("🖼 <b>Rasm tahlili</b>", MESSAGE_COST_PHOTO),
    ("🎤 <b>Ovozli xabar</b>", MESSAGE_COST_VOICE),
    ("📄 <b>Hujjat tahlili</b>", MESSAGE_COST_DOCUMENT),
]


def _beautify_date(date_val) -> str:
    """Bazada saqlangan har qanday vaqt formatini chiroyli ko'rinishga keltiradi."""
    if not date_val or date_val == "Noma'lum":
        return "Noma'lum"
    
    try:
        if isinstance(date_val, datetime):
            uzb_tz = timezone(timedelta(hours=5))
            dt = date_val.astimezone(uzb_tz)
            return dt.strftime("%d.%m.%Y | %H:%M")
            
        date_str = str(date_val)
        
        if "Asia/Tashkent" in date_str:
            clean_str = date_str.replace(" Asia/Tashkent", "").strip()
            dt_obj = datetime.strptime(clean_str, "%Y-%m-%d %H:%M:%S")
            return dt_obj.strftime("%d.%m.%Y | %H:%M")
            
        if "+" in date_str or "." in date_str:
            dt_obj = datetime.fromisoformat(date_str.replace(" ", "T"))
            uzb_tz = timezone(timedelta(hours=5))
            dt_tashkent = dt_obj.astimezone(uzb_tz)
            return dt_tashkent.strftime("%d.%m.%Y | %H:%M")
            
    except Exception:
        pass
        
    return str(date_val).split('.')[0]


def _plan_label(plan_type: str, premium_until) -> str:
    """Tarifni foydalanuvchi tilida, muddati bilan ko'rsatadi."""
    if plan_type == 'free':
        return "🆓 Free"
    if premium_until is None:
        return "💎 Cheksiz (muddatsiz)"
    days_left = max(0, (premium_until - datetime.now(timezone.utc)).days)
    name = "Pro" if plan_type == 'pro' else "Premium"
    return f"💎 {name} — {_beautify_date(premium_until)} gacha ({days_left} kun)"


def _progress_bar(used: int, limit: int, length: int = 10) -> str:
    """Kunlik kredit sarfini vizual chiziqcha (progress bar) ko'rinishida chizadi."""
    if limit <= 0:
        return "░" * length
    ratio = min(max(used / limit, 0.0), 1.0)
    filled = round(ratio * length)
    return "█" * filled + "░" * (length - filled)


def _build_credit_section(daily_used: int, limit: int | None) -> str:
    """
    Kunlik AI Credit holatini aniq va chiroyli ko'rinishda shakllantiradi:
    progress-bar, foiz, ishlatilgan/qolgan ball va qolgan ball bilan yana
    qaysi feature'lardan necha marta foydalanish mumkinligi (dinamik).

    `limit` — tarifga qarab core.config.plan_limits() dan keladi; None
    faqat haqiqatan cheksiz tarif ('premium') uchun. ILGARI bu yerda
    `plan_type != 'free'` tekshirilardi va Pro foydalanuvchiga "cheksiz" deb
    YOLG'ON ko'rsatilardi.
    """
    if limit is None:
        return (
            "🔋 <b>Bugungi AI Creditlar</b>\n"
            "🔓 <b>Cheksiz</b> — kunlik limit qo'llanilmaydi"
        )

    used = min(daily_used, limit)
    remaining = max(0, limit - used)
    percent = min(100, int(round((used / limit) * 100))) if limit > 0 else 0
    bar = _progress_bar(used, limit)

    lines = [
        "🔋 <b>Bugungi AI Creditlar</b>",
        f"<code>{bar}</code>  {percent}%",
        f"<b>Ishlatilgan:</b> <code>{used} / {limit}</code> ball\n<b>Qolgan:</b> <code>{remaining}</code> ball",
    ]

    if remaining <= 0:
        lines.append("\n⏳ Bugungi limit tugadi.")
    else:
        affordable = [
            (label, remaining // cost)
            for label, cost in _FEATURE_COSTS
            if remaining // cost > 0
        ]
        if affordable:
            lines.append(f"\n<b>Qolgan <code>{remaining}</code> ball bilan yana:</b>")
            lines.extend(f"• {label}: <b>{count}</b> ta" for label, count in affordable)
        else:
            lines.append(f"\n⚠️ Qolgan <code>{remaining}</code> ball birorta amal uchun ham yetmaydi❗️")

    lines.append("\n🕛 Yangilanish: ertaga soat <b>00:00</b> da")

    return "\n".join(lines)


def _build_file_section(files_used: int, limit: int | None, plan_type: str) -> str:
    """Fayl yaratish sanog'i — ball byudjetidan ALOHIDA ko'rsatiladi.

    Ikkovini bitta bo'limga qo'shib yuborsak foydalanuvchi nima nimani
    yeyayotganini tushunmay qoladi; alohida turgani "fayl tugadi, lekin
    suhbat ishlaydi" degan asosiy g'oyani ham ko'rsatib turadi.
    """
    if limit is None:
        return (
            "📄 <b>Fayl yaratish va tahrirlash</b>\n"
            "🔓 <b>Cheksiz</b> — kunlik chegara qo'llanilmaydi"
        )

    used = min(files_used, limit)
    remaining = max(0, limit - used)
    bar = _progress_bar(used, limit)

    lines = [
        "📄 <b>Fayl yaratish va tahrirlash</b>",
        f"<code>{bar}</code>  <code>{used} / {limit}</code>",
    ]
    if remaining <= 0:
        lines.append(
            "\n⏳ Bugungi fayl limiti tugadi — ertaga soat <b>00:00</b> da yangilanadi."
            "\n💬 Oddiy savollar hozir ham ishlaydi."
        )
        if plan_type == 'free':
            lines.append(f"💎 <b>Pro</b>'da kuniga {daily_limit('pro', 'files')} ta — /pro")
    else:
        lines.append(f"\n✅ Bugun yana <b>{remaining} ta</b> fayl yaratishingiz mumkin"
                     "\n<i>(PPTX, PDF, Word, Excel, format o'girish)</i>")
    return "\n".join(lines)


def _build_pro_counters(profile: dict, plan_type: str) -> str:
    """Pro imkoniyatlari sanog'i — FAQAT tarifda mavjud bo'lsa chiziladi.

    Bepul foydalanuvchi profili ATAYLAB o'zgarmaydi: "0 / 0" turgan sanoq
    faqat chalkashtiradi, reklama esa allaqachon limit xabarlarida bor.
    """
    rows = []
    for label, key, used_col in (
        ("🖼 Rasm chizish", "images", "daily_images_used"),
        ("🔎 Chuqur tadqiqot", "research", "daily_research_used"),
    ):
        limit = daily_limit(plan_type, key)
        if limit is None:
            rows.append(f"{label} — 🔓 <b>cheksiz</b>")
        elif limit > 0:
            used = min(profile.get(used_col, 0) or 0, limit)
            rows.append(f"{label} — <code>{used} / {limit}</code>")
    if not rows:
        return ""
    return "💎 <b>PRO IMKONIYATLARI</b>\n" + "\n".join(rows)


def _amaldagi_tarif(profile: dict) -> str:
    """Muddati o'tgan, lekin watcher hali free'ga tushirmagan Pro — bot uni
    allaqachon bepul deb hisoblaydi (check_and_consume_quota); ekran ham shunday."""
    plan_type = profile.get('plan_type') or 'free'
    tugash = profile.get('premium_until')
    if plan_type != 'free' and tugash is not None and tugash < datetime.now(timezone.utc):
        return 'free'
    return plan_type


def karta_raqamlari(profile: dict) -> dict:
    """Jonli kartaning raqamlari (services/vidjet.py: kalitlar). Matnli
    profil bilan BIR XIL manba va bir xil qoida: bepulda yo'q imkoniyat
    (chegara 0) chizilmaydi, None — cheksiz."""
    plan_type = _amaldagi_tarif(profile)
    out = {}
    for kalit, limit_nomi, ustun in (
            ("b", "points", "daily_requests_used"), ("f", "files", "daily_files_used"),
            ("r", "images", "daily_images_used"), ("t", "research", "daily_research_used")):
        limit = daily_limit(plan_type, limit_nomi)
        if limit is None or limit > 0:
            used = profile.get(ustun, 0) or 0
            out[kalit] = [min(used, limit) if limit is not None else used, limit]
    return out


def profil_holati(profile: dict, ism: str | None = None) -> dict:
    """Profil kartasining to'liq holati (services/vidjet.py: kalitlar) —
    raqamlar `karta_raqamlari()` dan, tarif `_amaldagi_tarif()` qoidasi bilan
    (muddati o'tgan Pro — bepul), sanalar Toshkent vaqtida."""
    plan_type = _amaldagi_tarif(profile)
    tugash = profile.get('premium_until')
    d = karta_raqamlari(profile)
    if plan_type == 'free':
        d["p"] = "f"
    elif tugash is None:
        d["p"] = "m"
    else:
        d.update(p="p", e=_beautify_date(tugash).split(" | ")[0],
                 k=max(0, (tugash - datetime.now(timezone.utc)).days))
    u = profile.get('username')
    a = _beautify_date(profile.get('created_at')).split(" | ")[0]
    d.update(i=profile['user_id'], u=u if u and u != "Mavjud emas" else "",
             m=profile.get('total_messages') or 0, o="—" if a == "Noma'lum" else a,
             g=profile.get('current_model') or "", x=[c for _, c in _FEATURE_COSTS])
    if ism:
        d["n"] = ism[:64]
    return d


class _KartaTugmasi:
    """Karta ichidagi tugma — `CallbackQuery` o'rnida (handler faqat shu
    maydonlarni o'qiydi). `answer` matni kartaga qaytadi (karta o'zi ko'rsatadi)."""
    def __init__(self, data: str, user, message):
        self.id, self.data, self.from_user, self.message = "vidjet", data, user, message
        self.javob: list[str] = []

    async def answer(self, text: str | None = None, show_alert: bool = False, **_):
        if text:
            self.javob.append(text)


# Karta tugmasi faqat SHU handlerlarga boradi — xabar ostidagi tugmalarning
# o'zi. Boshqa prefiks (admin, biznes) kartadan chaqirilmaydi.
_AMAL_PREFIKS = ("pro:", "dg:")


async def vidjet_amali(sorov: dict, callback: str) -> dict:
    """Karta ichidagi tugma (`TelegramWidget.request("c:<callback>")`) — xabar
    ostidagi tugma bosilgandek: o'sha handler, o'sha tekshiruvlar.

    ⚠️ `callback` mijozdan keladi — oddiy callback_data bilan BIR XIL ishonch:
    handlerlar kun, oluvchi, superadmin, banni o'zi tekshiradi. `from` ni
    Telegram tasdiqlaydi; faqat bot bilan shaxsiy chatdagi asl xabar (forward
    va guruh — yo'q). Handler 10 s da tugamasa ham javob beriladi (15 s
    chegarasi), ish esa fonda davom etadi."""
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey
    from aiogram.types import Message, User
    from core.loader import bot, dp
    from handlers import digest, pro
    chat, uid = sorov.get("chat") or {}, (sorov.get("from") or {}).get("id")
    if (not callback.startswith(_AMAL_PREFIKS) or len(callback) > 60 or not uid
            or chat.get("type") != "private" or chat.get("id") != uid
            or not sorov.get("message_id")):
        return {"x": 1}
    message = Message.model_validate({
        "message_id": sorov["message_id"], "date": int(datetime.now().timestamp()),
        "chat": {"id": chat["id"], "type": "private"},
        "from": {"id": bot.id, "is_bot": True, "first_name": "Vexon AI"},
        # `vidjet_xabari()` uchun: bu xabar — karta (chat_data qo'lda yo'q).
        "widget": {"html": ""}}, context={"bot": bot})
    q = _KartaTugmasi(callback, User.model_validate(sorov["from"]), message)
    state = FSMContext(storage=dp.storage,
                       key=StorageKey(bot_id=bot.id, chat_id=chat["id"], user_id=uid))
    handler = pro.handle_pro_callback if callback.startswith("pro:") else digest.handle_digest_callback
    vazifa = asyncio.ensure_future(handler(q, state))
    await asyncio.wait({vazifa}, timeout=10)
    if vazifa.done() and vazifa.exception():
        logger.warning(f"[Vidjet] karta tugmasi {callback!r} yiqildi: {vazifa.exception()!r}")
        return {"ok": 0, "t": "⚠️ Bajarilmadi — pastdagi tugmadan urinib ko'ring"}
    return {"ok": 1, **({"t": q.javob[0][:150]} if q.javob else {})}


async def vidjet_sorovi(sorov: dict) -> None:
    """Karta vidjetining "y" so'roviga yangi raqamlar (`widget_query`).

    `from` ni Telegram o'zi tasdiqlaydi (soxtalashtirib bo'lmaydi) — shuning
    uchun javob har doim SO'RAGAN odamning raqamlari. Har so'rovga javob
    beriladi, xatoda ham: javobsiz so'rov vidjetda TIMEOUT bo'ladi."""
    from handlers.messages import _telegram_api_request  # ⚠️ og'ir modul
    javob = {"widget_query_id": sorov.get("id")}
    uid = (sorov.get("from") or {}).get("id")
    data = sorov.get("data") or ""
    if data.startswith(vidjet.AMAL_SOROVI):
        # Karta ichidagi tugma — "c:<callback_data>" (`vidjet_amali`).
        try:
            javob["data"] = json.dumps(await vidjet_amali(sorov, data[len(vidjet.AMAL_SOROVI):]),
                                       ensure_ascii=False)
        except Exception as e:
            logger.warning(f"[Vidjet] karta tugmasi bajarilmadi ({data!r}): {e}")
    elif data.startswith(vidjet.OBHAVO_SOROVI):
        # Ob-havo kartasi — "w:lat,lon". `data` foydalanuvchi qurilmasidan
        # keladi (callback_data kabi): faqat ikki son, diapazoni tekshirilgan.
        try:
            lat, lon = (float(x) for x in data[len(vidjet.OBHAVO_SOROVI):].split(","))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                javob["data"] = vidjet.obhavo_holati(await obhavo.prognoz(lat, lon))
        except Exception as e:
            logger.info(f"[Vidjet] ob-havo yangilanmadi ({data!r}): {e}")
    elif data.startswith(vidjet.VALYUTA_SOROVI):
        # Valyuta kartasi — "v:USD,EUR". Kodlar ham qurilmadan: toza_kodlar
        # faqat 3 harfli lotin kodni o'tkazadi, Markaziy bankda yo'qi tushadi.
        try:
            kodlar = valyuta.toza_kodlar(data[len(vidjet.VALYUTA_SOROVI):])
            k = await valyuta.kurslar()
            holat = valyuta.holat(k, kodlar)
            if holat["r"]:
                javob["data"] = vidjet.valyuta_holati(holat)
        except Exception as e:
            logger.info(f"[Vidjet] valyuta yangilanmadi ({data!r}): {e}")
    elif data.startswith(vidjet.NAMOZ_SOROVI):
        # Namoz kartasi kun almashganda — "n:r:39" / "n:a:lat,lon,tz".
        # Qurilmadan keladi: `sorov_oqi` diapazon va mintaqa nomini tekshiradi.
        try:
            joy = namoz.sorov_oqi(data[len(vidjet.NAMOZ_SOROVI):])
            if joy and (d := await namoz.holat(joy, "")):
                javob["data"] = vidjet.namoz_holati(d)
        except Exception as e:
            logger.info(f"[Vidjet] namoz yangilanmadi ({data!r}): {e}")
    elif data.startswith(vidjet.ESLATMA_SOROVI) and uid:
        # Eslatma kartasi — "e:<id>". Ro'yxat SO'RAGAN odamniki (`from` ni
        # Telegram tasdiqlaydi), ya'ni begona id shunchaki "yo'q" bo'ladi.
        try:
            tid = int(data[len(vidjet.ESLATMA_SOROVI):])
            r = next((r for r in await list_scheduled_tasks(uid) if r["id"] == tid), None)
            javob["data"] = vidjet.eslatma_holati({"at": int(r["run_at"].timestamp())} if r
                                                  else {"x": 1})
        except Exception as e:
            logger.info(f"[Vidjet] eslatma holati o'qilmadi ({data!r}): {e}")
    elif data == vidjet.KUNLIK_SOROVI and uid:
        # /kunlik kartasi — so'ragan odamning soatlari va mavzulari.
        try:
            from handlers.digest import kunlik_holati   # ⚠️ tsiklik import
            profil = await get_full_user_profile(uid)
            if profil:
                javob["data"] = vidjet.kunlik_holati(kunlik_holati(profil))
        except Exception as e:
            logger.warning(f"[Vidjet] kunlik holati o'qilmadi (user={uid}): {e}")
    elif data.startswith(vidjet.TADQIQOT_SOROVI) and uid:
        # /research kartasi — "r:<id>"; begona yoki RAM'da yo'q id — {x:1}.
        from handlers.messages import tadqiqot_ol   # ⚠️ og'ir modul
        j = tadqiqot_ol(uid, data[len(vidjet.TADQIQOT_SOROVI):])
        javob["data"] = vidjet.tadqiqot_holati(j if j else {"x": 1})
    elif data.startswith(vidjet.TOLOV_SOROVI) and uid:
        # Karta to'lovi kartasi — "t:<id>". `tolov_holati` SO'RAGAN odamning
        # o'z to'lovini o'qiydi (user_id bilan); begona id — {"h": "x"}.
        try:
            from handlers.pro import tolov_holati   # ⚠️ tsiklik import
            lid = int(data[len(vidjet.TOLOV_SOROVI):])
            javob["data"] = vidjet.tolov_holati(await tolov_holati(uid, lid))
        except Exception as e:
            logger.info(f"[Vidjet] to'lov holati o'qilmadi ({data!r}): {e}")
    elif data == vidjet.KARTA_SOROVI and uid:
        try:
            profil = await get_full_user_profile(uid)
            if profil:
                javob["data"] = vidjet.karta_holati(profil_holati(profil))
        except Exception as e:
            logger.warning(f"[Vidjet] karta raqamlari o'qilmadi (user={uid}): {e}")
    await _telegram_api_request("answerWidgetQuery", javob)


async def vidjet_mw(handler, event, data):
    """`dp.update` outer middleware — vidjet so'rovini zanjirdan oldin oladi.

    aiogram 3.31 `widget_query` ni BILMAYDI: maydon `model_extra` ga
    tushadi, `update.event_type` esa "unknown update type" deb yiqiladi.
    Outer middleware o'sha joydan (ichki `_listen_update`) OLDIN ishlaydi.
    aiogram 10.4'ni o'rgangach maydon haqiqiy bo'ladi — ikkalasi o'qiladi."""
    sorov = (getattr(event, "widget_query", None)
             or (event.model_extra or {}).get("widget_query"))
    if sorov is None:
        return await handler(event, data)
    if not isinstance(sorov, dict):
        sorov = sorov.model_dump(by_alias=True, exclude_none=True)
    await vidjet_sorovi(sorov)


async def _karta_yubor(message: types.Message, profile: dict, tarif: str, kb,
                       ism: str | None = None) -> bool:
    """Shaxsiy chatda profil — to'liq karta vidjeti, izohi ixcham (hammasi
    kartada). Qaytadi: yetib bordimi (yoki timeout — takror yuborilmaydi)."""
    from handlers.messages import (OUTCOME_UNKNOWN, _telegram_api_request,
                                   _thread_key)
    holat = profil_holati(profile, ism)
    b = holat.get("b")
    # Vidjetni qo'llamaydigan ilova FAQAT izohni ko'radi — tarif va ball o'sha yerda ham tursin.
    izoh = f"🪪 <b>SHAXSIY KABINET</b>\n📦 <b>Tarif:</b> {tarif}"
    if b:
        izoh += ("\n🔋 <b>AI Creditlar:</b> "
                 + ("cheksiz" if b[1] is None else f"<code>{b[0]} / {b[1]}</code>"))
    payload = {"chat_id": message.chat.id, "html": vidjet.karta_html(),
               "chat_data": vidjet.karta_holati(holat), "allow_queries": True,
               "caption": izoh[:vidjet.CAPTION_MAX], "parse_mode": "HTML",
               "reply_markup": kb.model_dump(exclude_none=True)}
    if tid := _thread_key(message):
        payload["message_thread_id"] = tid
    outcome: list = []
    if await _telegram_api_request("sendWidget", payload, outcome=outcome) is not None:
        return True
    return OUTCOME_UNKNOWN in outcome


async def handle_profile(message: types.Message, user_id: int | None = None):
    """Foydalanuvchi profilini shakllantirish va yuborish.

    user_id ATAYLAB alohida parametr: callback tugmasidan chaqirilganda
    `message` botning O'Z xabari bo'ladi va message.from_user — bot, ya'ni
    u yerdan foydalanuvchini olsak, botning profilini ko'rsatib qo'yardik.
    """
    user_id = user_id if user_id is not None else message.from_user.id
    profile_data = await get_full_user_profile(user_id)
    
    if not profile_data:
        await message.answer("⚠️ Profilingiz topilmadi. Iltimos, /start buyrug'ini bering.")
        return
    
    if profile_data.get('username') and profile_data['username'] != "Mavjud emas":
        username = f"@{profile_data['username']}"
    else:
        username = "Mavjud emas"
    status_text = "🟢 Faol" if profile_data['is_active'] else "🔴 Bloklangan"
    plan_type = _amaldagi_tarif(profile_data)
    plan_label = _plan_label(plan_type, profile_data.get('premium_until'))
    media_status = "Faol" if profile_data['media_analysis_active'] else "O'chirilgan"
    daily_used = profile_data['daily_requests_used']
    created_at = _beautify_date(profile_data.get('created_at', ''))
    last_seen = _beautify_date(profile_data.get('last_seen', ''))

    point_limit, file_limit = plan_limits(plan_type)
    credit_section = _build_credit_section(daily_used, point_limit)
    file_section = _build_file_section(
        profile_data.get('daily_files_used', 0), file_limit, plan_type)
    pro_section = _build_pro_counters(profile_data, plan_type)

    sarlavha = (
        f"🪪 <b>SHAXSIY KABINET</b>\n\n"
        f"👤 <b>Profil:</b> {username}\n"
        f"🆔 <b>ID:</b> <code>{profile_data['user_id']}</code>\n"
        f"💳 <b>Status:</b> {status_text}\n"
        f"📦 <b>Tarif:</b> {plan_label}\n\n"
        
        f"⚙️ <b>TIZIM SOZLAMALARI</b>\n"
        f"🧠 <b>Tanlangan Model:</b> <code>{profile_data['current_model']}</code>\n\n"
        
        f"📊 <b>FOYDALANISH STATISTIKASI</b>\n"
        f"├ ✉️ <b>Barcha xabarlar:</b> <code>{profile_data['total_messages']}</code>"
    )
    text = (
        f"{sarlavha}\n\n"
        f"{credit_section}\n\n"

        f"{file_section}\n\n"

        f"{pro_section + chr(10) + chr(10) if pro_section else ''}"
    )
    
    # Klaviatura quruvchisi pro.py'da yashaydi (pro.py profile.py'ni
    # import qilmaydi — sikl bo'lmasligi uchun shu yo'nalish).
    from handlers.pro import pro_keyboard_for
    kb = pro_keyboard_for(plan_type)
    # Bot API 10.4: shaxsiy chatda raqamlar — jonli karta. Rad etilsa
    # (eski server, buzuq tugma) — oldingi matnli profil, o'zgarishsiz.
    if message.chat.type == "private":
        try:
            # Ism bazada yo'q — faqat xabar egasi SHU foydalanuvchi bo'lsa
            # (tugmadan chaqirilganda `from_user` — botning o'zi).
            fu = getattr(message, "from_user", None)
            ism = getattr(fu, "first_name", None) if getattr(fu, "id", None) == user_id else None
            if await _karta_yubor(message, profile_data, plan_label, kb, ism):
                return
        except Exception as e:
            logger.warning(f"[Vidjet] karta yuborilmadi (user={user_id}): {e}")
    await message.answer(text, parse_mode="HTML", reply_markup=kb)
