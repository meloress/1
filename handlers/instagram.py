"""Instagram Direct — xabar qabul, yuborish va ulash matnlari.

NEGA ALOHIDA MODUL — `handlers/biznes.py` Telegram update
(`business_message`, `business_connection_id`) bilan ishlaydi. IG event
esa Meta webhook JSON. Qaror mantiqi (Bilim/Uslub/`BIZNES_SXEMA`) BIR XIL —
farq faqat shu qatlamda: eventni ajratish, Graph API'ga yuborish.

UI (`/biznes` → Sozlamalar → Instagram) `handlers/biznes.py` da yashaydi:
alohida buyruq yo'q (ega qarori). Bu modulda faqat sof quruvchilar va
tarmoq qatlami.

SQL YO'Q — hamma saqlash `db/database.py::instagram_*` orqali.
`core.loader` (bot) faqat funksiya ICHIDA import qilinadi — modul importi
token'siz muhitda ham ishlasin (testlar).
"""

import logging
from html import escape

logger = logging.getLogger(__name__)

# Yordamchi kutayotganlar: (owner_id, ig_sid) to'plami — mijoz yozdi,
# egasi hali javob bermadi. RAM'da — deploy'da yo'qolsa, tarix
# (`instagram_xabar`) qoladi va keyingi xabarda yangi karta keladi.
_kutilayotgan: set = set()


def hodisadan_xabarlar(hodisa: dict) -> list:
    """Meta webhook JSON → [{sender, matn, mid}]. Sof funksiya.

    Faqat `instagram` object, faqat matnli `message` lar. Echo (botning
    o'zi yuborgani), postback bo'lmagan reaction, bo'sh matn — tashlanadi.
    """
    natija = []
    if not isinstance(hodisa, dict):
        return natija
    for entry in hodisa.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        for msg in entry.get("messaging") or []:
            if not isinstance(msg, dict):
                continue
            xabar = msg.get("message") or {}
            if not isinstance(xabar, dict):
                continue
            # Botning o'z aksi (loop himoyasi — `biznes_kimdan` dagi `bot`
            # shoxining IG analogi) va matnsizlar o'tmaydi.
            if xabar.get("is_echo"):
                continue
            matn = xabar.get("text")
            if not isinstance(matn, str) or not matn.strip():
                continue
            yuboruvchi = (msg.get("sender") or {}).get("id", "")
            if not yuboruvchi:
                continue
            natija.append({
                "sender": str(yuboruvchi),
                "matn": matn.strip(),
                "mid": xabar.get("mid", ""),
            })
    return natija


def matn_tozala(matn: str, chegara: int = 1000) -> str:
    """IG plain kanaliga moslash: bir qator oralig'i, chegara bilan kesish.

    IG'da rich markup yo'q — kesilgani haqida hech narsa qo'shilmaydi,
    chunki bu mijoz ko'radigan matn emas, modelga kiradigan xom matn.
    """
    try:
        from core import config as cfg
        chegara = int(getattr(cfg, "IG_MATN_MAX", chegara) or chegara)
    except Exception:
        pass
    matn = " ".join(str(matn or "").split())
    return matn[:chegara]


async def yubor(sahifa_token: str, ig_sid: str, matn: str,
                _post=None) -> tuple:
    """Graph API'ga yuborish → (ok, sabab). Sof bo'lmagan yagona joy.

    `_post` — test uchun injeksiya (`async (url, payload, headers) → dict`).
    Token xatoga qo'shilmaydi (logga ham).
    """
    if not sahifa_token or not ig_sid or not matn:
        return False, "bo'sh"
    try:
        from core import config as cfg
        bazaviy = str(getattr(cfg, "IG_GRAPH_API", "") or
                      "https://graph.facebook.com/v21.0")
    except Exception:
        bazaviy = "https://graph.facebook.com/v21.0"
    url = f"{bazaviy}/me/messages"
    yuk = {"recipient": {"id": ig_sid},
           "message": {"text": matn[:1000]}}
    sar = {"Authorization": "Bearer ***"}
    try:
        if _post is not None:
            javob = await _post(url, yuk, sar)
        else:
            import aiohttp
            async with aiohttp.ClientSession() as sess:
                async with sess.post(
                        url, json={
                            "recipient": {"id": ig_sid},
                            "message": {"text": matn[:1000]},
                            "messaging_type": "RESPONSE"},
                        headers={"Authorization": f"Bearer {sahifa_token}"},
                        timeout=15) as r:
                    try:
                        javob = await r.json()
                    except Exception:
                        javob = {"status": r.status}
                    if r.status != 200:
                        return False, str(javob)[:200]
        if isinstance(javob, dict) and javob.get("error"):
            return False, str(javob.get("error"))[:200]
        return True, ""
    except Exception as exc:
        logger.warning("[instagram] yuborilmadi: %s", type(exc).__name__)
        return False, type(exc).__name__


# ── Ulash ekrani matnlari (Sozlamalar ichida ko'rsatiladi) ────────────
# Tugmalar `bz:ig*` — `handlers/biznes.py::handle_biznes_callback` ushlaydi.


def _raqam_mi(qiymat: str) -> bool:
    """IG/Page ID — faqat raqam, 5-25 belgi. Sof."""
    q = (qiymat or "").strip()
    return q.isdigit() and 5 <= len(q) <= 25


def ekran_matni(ul: dict | None) -> str:
    """Sof — testda tekshiriladi. Sozlamalar ichidagi Instagram bo'limi."""
    qator = ["📸 <b>Instagram Direct</b>\n"]
    if not ul or not ul.get("yoqilgan"):
        qator.append("❌ Ulanmagan.")
        qator.append("\n<b>Ulash (3 qadam, 5 daqiqa):</b>\n"
                     "1. Instagram'ni <b>Professional</b> akkauntga o'tkazing.\n"
                     "2. Uni <b>Facebook Page</b>'ga bog'lang.\n"
                     "3. Pastdagi «🔌 Ulash» ni bosing — men ketma-ket so'rayman:\n"
                     "IG ID → Page ID → Page token.\n\n"
                     "Javoblar Telegram'dagi Bilim/Uslub/Rejim bilan — "
                     "Yordamchida qoralama sizga keladi, Avtomatda o'zi yuboradi.")
        return "\n".join(qator)
    qator.append(f"✅ Ulangan (IG ID: <code>{escape(str(ul.get('ig_id', '')))}</code>).")
    qator.append("Javoblar Telegram'dagi Bilim/Uslub/Rejim bilan ishlaydi.")
    return "\n".join(qator)


def qoralama_matni(ig_sid: str, matn: str) -> str:
    """Sof — Biznes mavzusiga chiqadigan IG kartasi.

    Bu QORALAMA emas, xabarnoma: javobni egasi yozadi («✏️ Javob yozish»).
    Model yozgan qoralama matni — keyingi qadam.
    """
    return ("📸 <b>Instagram</b> — mijoz yozdi:\n\n"
            f"{escape(matn[:1000])}\n\n"
            f"<i>«✏️ Javob yozish» ni bosing — yozganingiz IG'ga ketadi.</i>")


async def javob_yubor(uid: int, ig_sid: str, matn: str) -> tuple:
    """Egasi yozgan javob → IG'ga yuborish. (ok, xabar).

    Token/qaror shu yerda: ulanish o'chirilgan bo'lsa hech narsa ketmaydi
    va "yuborildi" deyimaydi (Telegram'dagi 24-soat qoidasi naqshi).
    """
    from db import database as db
    matn = matn_tozala(matn)
    if not matn:
        return False, "Bo'sh javob yuborilmaydi."
    try:
        ul = await db.instagram_ulanish_ol(uid)
    except Exception:
        ul = None
    if not ul or not ul.get("yoqilgan"):
        return False, "Instagram uzilgan."
    ok, sabab = await yubor(ul["sahifa_token"], ig_sid, matn)
    if not ok:
        return False, f"Yuborilmadi: {sabab[:100]}"
    _kutilayotgan.discard((uid, ig_sid[:20]))
    try:
        await db.instagram_xabar_yoz(uid, ig_sid, "assistent", matn)
    except Exception:
        pass
    return True, "IG'ga yuborildi"


def qoralama_bekor(uid: int, ig_sid: str) -> None:
    """Egasi «✖️ Bekor» ni bosdi — kutayotgan karta o'chadi."""
    _kutilayotgan.discard((uid, ig_sid[:20]))


async def mijoz_qoralamasi(egasi: int, egasi_chat: int, ig_sid: str, matn: str) -> bool:
    """Yordamchi: IG mijoz xabari → egasining «💼 Biznes» mavzusiga karta.

    Qaytadi: karta yetdimi. Xato yutiladi — webhook (Meta'ga 200) to'xtamasin.
    """
    _kutilayotgan.add((egasi, ig_sid[:20]))
    try:
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        from core.loader import bot
        from handlers import biznes as bz
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✏️ Javob yozish",
                                 callback_data=f"bz:igj:{ig_sid[:20]}"),
            InlineKeyboardButton(text="✖️ Bekor",
                                 callback_data=f"bz:igx:{ig_sid[:20]}"),
        ]])
        tid = await bz.biznes_mavzusi(egasi_chat)
        await bot.send_message(egasi_chat, qoralama_matni(ig_sid, matn),
                               parse_mode="HTML", reply_markup=kb,
                               message_thread_id=tid if tid else None)
        return True
    except Exception as exc:
        logger.warning("[instagram] qoralama yetmadi: %s", type(exc).__name__)
        return False
