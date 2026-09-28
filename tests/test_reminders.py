"""Eslatmalar uchun qo'lda ishga tushiriladigan tekshiruv.
Ishga tushirish: python tests/test_reminders.py

Uchta narsa qo'riqlanadi, uchalasi ham ISHONCH CHEGARASI:
  1) parse_run_at — vaqtni MODEL yozadi, ya'ni ishonchsiz manba. O'tmish
     yoki axlat qiymat jimgina qabul qilinsa, eslatma hech qachon (yoki
     darhol) ishga tushib, foydalanuvchi buni "bot aldadi" deb biladi;
  2) next_run_at — bot bir necha kun o'chib tursa, takrorlanuvchi eslatma
     kelajakka CHIQIB OLISHI kerak, aks holda watcher bitta eslatmani
     ketma-ket o'nlab marta yuboradi;
  3) _run_reminder_task indeks mantiqi — model bergan raqam noto'g'ri
     bo'lsa DB'ga umuman tegilmasligi kerak (xotira asbobidagi bilan bir xil).
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import asyncio
from datetime import datetime, timedelta

from db.database import (
    clean_reminder_text, parse_run_at, next_run_at, _add_months, TASHKENT_TZ,
)
from core.config import REMINDER_MAX_LEN, REMINDER_MAX_AHEAD_DAYS
from services import ai

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=TASHKENT_TZ)


def test_clean_text():
    # Yangi qatorlar bir qatorga siqiladi — eslatma HTML blockquote ichida
    # ko'rsatiladi, ko'p qatorli matn u yerda ko'rinishni buzadi.
    assert clean_reminder_text("Karimga\nqo'ng'iroq   qilish") == "Karimga qo'ng'iroq qilish"
    assert len(clean_reminder_text("x" * (REMINDER_MAX_LEN + 300))) == REMINDER_MAX_LEN
    for bosh in ("", "   ", None, "\n\n"):
        assert clean_reminder_text(bosh) == ""
    print("[1] matn tozalanadi, bo'shi rad etiladi OK")


def test_parse_run_at():
    assert parse_run_at("2026-08-08 09:00", NOW) == \
        datetime(2026, 8, 8, 9, 0, tzinfo=TASHKENT_TZ)
    # ISO "T" ajratgichi va soniyali format ham qabul qilinadi.
    assert parse_run_at("2026-08-08T09:00", NOW) is not None
    assert parse_run_at("2026-08-08 09:00:00", NOW) is not None
    print("[2] to'g'ri formatlar o'tadi OK")

    # O'TMISH rad etiladi — aks holda eslatma yaratilgan zahoti "kechikkan"
    # bo'lib darhol yuborilardi.
    assert parse_run_at("2026-08-06 09:00", NOW) is None
    assert parse_run_at("2026-08-07 11:00", NOW) is None
    # Bir necha soniyalik orqada qolish esa normal (model "hozir" deb yozadi).
    assert parse_run_at("2026-08-07 11:59", NOW) is not None
    print("[3] o'tmish rad etiladi, kichik og'ish kechiriladi OK")

    # Juda uzoq kelajak — model xato hisoblab 2190-yilga yozib qo'ymasin.
    uzoq = (NOW + timedelta(days=REMINDER_MAX_AHEAD_DAYS + 10)).strftime("%Y-%m-%d %H:%M")
    assert parse_run_at(uzoq, NOW) is None
    print("[4] juda uzoq kelajak rad etiladi OK")

    for axlat in ("ertaga soat 9 da", "08/08/2026", "2026-13-45 99:99",
                  "", None, "tez orada", "2026-08-08"):
        assert parse_run_at(axlat, NOW) is None, f"o'tib ketdi: {axlat!r}"
    print("[5] axlat qiymatlar rad etiladi OK")


def test_next_run_at():
    base = datetime(2026, 8, 7, 9, 0, tzinfo=TASHKENT_TZ)

    assert next_run_at(base, "once", NOW) is None
    assert next_run_at(base, "qwerty", NOW) is None
    print("[6] takrorlanmaydigan eslatma o'chiriladi OK")

    assert next_run_at(base, "daily", NOW) == \
        datetime(2026, 8, 8, 9, 0, tzinfo=TASHKENT_TZ)
    assert next_run_at(base, "weekly", NOW) == \
        datetime(2026, 8, 14, 9, 0, tzinfo=TASHKENT_TZ)
    assert next_run_at(base, "monthly", NOW) == \
        datetime(2026, 9, 7, 9, 0, tzinfo=TASHKENT_TZ)
    print("[7] daily/weekly/monthly to'g'ri suriladi OK")

    # ENG MUHIMI: bot 10 kun o'chib turgan bo'lsa ham natija KELAJAKDA
    # bo'lishi kerak — aks holda watcher bitta eslatmani 10 marta yuboradi.
    eski = datetime(2026, 7, 28, 9, 0, tzinfo=TASHKENT_TZ)
    nxt = next_run_at(eski, "daily", NOW)
    assert nxt > NOW, f"kelajakda bo'lishi kerak edi, keldi {nxt}"
    assert nxt == datetime(2026, 8, 8, 9, 0, tzinfo=TASHKENT_TZ)
    print("[8] uzoq to'xtashdan keyin kelajakka chiqadi OK")

    # Oy oxiri qirqiladi: 31-yanvar + 1 oy = 28-fevral (2026 kabisa emas).
    assert _add_months(datetime(2026, 1, 31, 9, 0, tzinfo=TASHKENT_TZ), 1) == \
        datetime(2026, 2, 28, 9, 0, tzinfo=TASHKENT_TZ)
    # Kabisa yilda 29-fevral.
    assert _add_months(datetime(2028, 1, 31, 9, 0, tzinfo=TASHKENT_TZ), 1) == \
        datetime(2028, 2, 29, 9, 0, tzinfo=TASHKENT_TZ)
    # Yil chegarasidan o'tish.
    assert _add_months(datetime(2026, 12, 15, 9, 0, tzinfo=TASHKENT_TZ), 1) == \
        datetime(2027, 1, 15, 9, 0, tzinfo=TASHKENT_TZ)
    print("[9] oy oxiri va yil chegarasi to'g'ri OK")


async def test_index_bounds():
    """Model bergan `index` noto'g'ri bo'lsa DB'ga TEGILMASLIGI kerak."""
    rows = [{"id": 501, "text": "a", "run_at": NOW, "repeat": "once"},
            {"id": 502, "text": "b", "run_at": NOW, "repeat": "daily"}]
    tegilgan = []

    async def fake_list(user_id):
        return rows

    async def fake_cancel(user_id, task_id):
        tegilgan.append(task_id)
        return "bekor qilindi"

    real_list, real_cancel = ai.list_scheduled_tasks, ai.cancel_scheduled_task
    ai.list_scheduled_tasks, ai.cancel_scheduled_task = fake_list, fake_cancel
    try:
        # True — Python'da int, indeks sifatida o'tib ketmasligi kerak.
        for yomon in (0, 3, -1, None, "2", 2.0, True):
            out = await ai._run_reminder_task(
                7, {"action": "cancel", "index": yomon})
            assert "eslatma yo'q" in out, f"{yomon!r} uchun xato kutilgan, keldi: {out}"
        assert tegilgan == [], f"noto'g'ri indeks bilan DB'ga tegildi: {tegilgan}"
        print("[10] noto'g'ri indeks DB'ga yetib bormaydi OK")

        assert await ai._run_reminder_task(
            7, {"action": "cancel", "index": 2}) == "bekor qilindi"
        assert tegilgan == [502], f"noto'g'ri id bekor qilindi: {tegilgan}"
        print("[11] pozitsiya -> haqiqiy id to'g'ri moslanadi OK")

        out = await ai._run_reminder_task(7, {"action": "list"})
        assert "501" not in out, "ichki id modelga ko'rsatilmasligi kerak"
        assert out.startswith("1. "), f"raqamlangan ro'yxat kutilgan, keldi: {out}"
        print("[12] list raqamlangan va ichki id sizib chiqmaydi OK")
    finally:
        ai.list_scheduled_tasks, ai.cancel_scheduled_task = real_list, real_cancel

    # Guest rejim (user_id=None) — asbob biriktirilmaydi, lekin himoya
    # ikkinchi qavatda ham turadi.
    assert await ai._run_reminder_task(None, {"action": "create"}) == "eslatma mavjud emas"
    assert "noma'lum amal" in await ai._run_reminder_task(7, {"action": "qwerty"})
    print("[13] guest va noma'lum amal himoyasi OK")


async def test_cleanup_and_limits():
    """Bazada eski eslatma qolmasin va muddat bir oydan oshmasin."""
    import inspect
    from db import database as db

    # Bir martalik eslatma yuborilgach qator O'CHIRILADI, bayroq
    # qo'yilmaydi — aks holda jadval abadiy o'sardi.
    adv = inspect.getsource(db.advance_scheduled_task)
    assert "DELETE FROM scheduled_tasks WHERE id = $1" in adv
    assert "active = FALSE" not in adv, "eski bayroq usuli qolib ketgan"
    # Bekor qilinganda ham o'chiriladi, lekin BEGONA eslatmaga tegmasin.
    can = inspect.getsource(db.cancel_scheduled_task)
    assert "DELETE FROM scheduled_tasks" in can and "user_id = $2" in can
    print("[14] ishlatilgan eslatma bazadan o'chiriladi OK")

    # Bir oydan uzoq eslatma qabul qilinmaydi.
    assert REMINDER_MAX_AHEAD_DAYS <= 31, "chegara bir oydan oshib ketgan"
    uzoq = (NOW + timedelta(days=32)).strftime("%Y-%m-%d %H:%M")
    assert parse_run_at(uzoq, NOW) is None
    yaqin = (NOW + timedelta(days=25)).strftime("%Y-%m-%d %H:%M")
    assert parse_run_at(yaqin, NOW) is not None
    print("[15] eng uzog'i bir oy OK")


async def test_ai_body():
    """Eslatma matnini MODEL yozadi, yiqilsa shablon ketadi."""
    from handlers import helpers

    chaqiruv = {}

    async def fake_reply(chat_id, prompt, **kw):
        chaqiruv["chat_id"] = chat_id
        chaqiruv["kw"] = kw
        for c in ("⏰ Ishga ketish vaqti!\n\n", "Omad!"):
            yield c

    import services.ai as ai_mod
    real = ai_mod.get_gpt_reply
    ai_mod.get_gpt_reply = fake_reply
    try:
        body = await helpers._reminder_body("Ishga ketish")
    finally:
        ai_mod.get_gpt_reply = real
    assert body.startswith("⏰ Ishga ketish vaqti!"), body
    # Ichki chaqiruv: tarixga tegmasin va internetga chiqmasin.
    assert chaqiruv["chat_id"] == 0
    assert chaqiruv["kw"].get("tools_enabled") is False, \
        "model qidiruvga chiqib ketadi — sekin va qimmat"
    print("[16] eslatma matnini model yozadi OK")

    # Model yiqilsa — eslatma BARIBIR yetib borishi kerak.
    yuborilgan = {}

    async def fail_reply(*a, **k):
        raise RuntimeError("model yiqildi")
        yield ""

    async def fake_dm(user_id, text, kb=None):
        yuborilgan["text"] = text

    real_dm = helpers._dm_or_deactivate
    ai_mod.get_gpt_reply = fail_reply
    helpers._dm_or_deactivate = fake_dm
    try:
        await helpers._send_reminder(7, "Ishga ketish")
    finally:
        ai_mod.get_gpt_reply = real
        helpers._dm_or_deactivate = real_dm
    assert "Ishga ketish" in yuborilgan["text"], "zaxira eslatma ketmadi"
    print("[17] model yiqilsa ham eslatma yetib boradi OK")


async def test_vazifa():
    """Rejalashtirilgan VAZIFA: vaqti kelganda bot ishni o'zi bajaradi.

    ⛔️ vazifa oddiy eslatma bo'lib ketadi (faqat matn qaytadi);
    ⛔️ oddiy eslatma qimmat qidiruvli so'rovga aylanadi;
    ⛔️ Pro tugagan odamga har kuni qidiruvli so'rov (pul) ketaveradi;
    ⛔️ yiqilganda odam HECH NARSA olmaydi;
    ⛔️ natija tarixga yozilmaydi — «batafsil ayt» ishlamaydi.
    """
    from handlers import helpers
    import handlers.messages as msg
    import services.ai as ai_mod

    # 18) Model `task` ni faqat aniq True bo'lganda vazifa qiladi.
    q = []

    async def fake_create(user_id, text, when, repeat="once", vazifa=False):
        q.append(vazifa)
        return "qo'yildi"

    real_create = ai_mod.create_scheduled_task
    ai_mod.create_scheduled_task = fake_create
    try:
        for t in (True, "true", None):
            await ai_mod._run_reminder_task(5, {"action": "create", "text": "x",
                                                "when": "2099-01-01 09:00", "task": t})
    finally:
        ai_mod.create_scheduled_task = real_create
    sxema = ai_mod._REMINDER_TOOL["parameters"]["properties"]
    assert q == [True, False, False] and sxema["task"]["type"] == "boolean", q
    print("[18] `task` maydoni: faqat true — vazifa OK")

    # 19-21) Bajaruvchi.
    j = {"pro": True, "chaqiruv": None, "yuborildi": [], "tarix": [], "eslatma": []}

    async def pro(uid):
        return j["pro"]

    async def reply(chat_id, prompt, **kw):
        j["chaqiruv"] = (chat_id, prompt, kw)
        yield "[STATUS]search"
        yield "qidiryapman…"
        yield "[CLEAR_TEXT]⏰ Dollar kursi\n\n1 USD = 12 000 so'm"

    async def rich(chat_id, **kw):
        j["yuborildi"].append((chat_id, kw.get("markdown", "")))
        return object()

    async def tarix(chat_id, content, role="user", **kw):
        j["tarix"].append((chat_id, role, content))

    async def eslat(user_id, text):
        j["eslatma"].append(text)

    asl = (helpers.database.pro_tarifmi, ai_mod.get_gpt_reply, msg._send_rich_message,
           ai_mod.safe_update_history, helpers._send_reminder)
    helpers.database.pro_tarifmi, ai_mod.get_gpt_reply = pro, reply
    msg._send_rich_message, ai_mod.safe_update_history = rich, tarix
    helpers._send_reminder = eslat
    try:
        await helpers._vazifani_bajar(7, "Bugungi USD/UZS kursi")
        chat, prompt, kw = j["chaqiruv"]
        assert chat == 0 and "user_id" not in kw and isinstance(kw.get("images_out"), list), kw
        assert "Bugungi USD/UZS kursi" in prompt and kw.get("tools_enabled", True) is True
        assert j["yuborildi"] and j["yuborildi"][0][0] == 7
        assert "qidiryapman" not in j["yuborildi"][0][1] and "12 000" in j["yuborildi"][0][1]
        assert [(c, r) for c, r, _ in j["tarix"]] == [(7, "user"), (7, "assistant")], j["tarix"]
        assert not j["eslatma"]
        print("[19] vazifa: qidiruvli halqa, natija odamga va uning tarixiga OK")

        j["pro"], j["chaqiruv"] = False, None
        await helpers._vazifani_bajar(7, "Bugungi USD/UZS kursi")
        assert j["chaqiruv"] is None and j["eslatma"] == ["Bugungi USD/UZS kursi"]
        print("[20] Pro tugagan — model chaqirilmaydi, oddiy eslatma OK")

        async def yiqil(*a, **k):
            raise RuntimeError("model yiqildi")
            yield ""
        j["pro"], j["eslatma"] = True, []
        ai_mod.get_gpt_reply = yiqil
        await helpers._vazifani_bajar(7, "Bugungi USD/UZS kursi")
        assert j["eslatma"] == ["Bugungi USD/UZS kursi"], "yiqilganda odam hech narsa olmadi"
        print("[21] yiqilsa — oddiy eslatma baribir yetib boradi OK")
    finally:
        (helpers.database.pro_tarifmi, ai_mod.get_gpt_reply, msg._send_rich_message,
         ai_mod.safe_update_history, helpers._send_reminder) = asl

    # 22) Kuzatuvchi: vazifa — bajaruvchiga, eslatma — eslatmaga.
    from _manba import kod
    w = kod(os.path.join(ROOT, "handlers", "helpers.py"))
    w = w[w.index("async def reminder_watcher("):w.index("async def premium_expiry_watcher(")]
    assert 'if row.get("vazifa"):' in w and "_vazifani_bajar(" in w and "_send_reminder(" in w
    print("[22] kuzatuvchi vazifani bajaruvchiga, eslatmani eslatmaga yuboradi OK")


async def main():
    test_clean_text()
    test_parse_run_at()
    test_next_run_at()
    await test_index_bounds()
    await test_cleanup_and_limits()
    await test_ai_body()
    await test_vazifa()
    print("\neslatmalar: barcha tekshiruvlar o'tdi (22/22).")


if __name__ == "__main__":
    asyncio.run(main())
