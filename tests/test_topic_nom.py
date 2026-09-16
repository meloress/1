# -*- coding: utf-8 -*-
"""Mavzuga (topic) avtomatik nom qo'yish.

⚠️ BU TESTNING ASOSIY SABABI: bot mavzuning HOZIRGI nomini o'qiy
olmaydi — Bot API'da `getForumTopic` yo'q. Ya'ni `editForumTopic` har
safar chaqirilsa, foydalanuvchi qo'ygan nom ustidan yozilaverardi.
Shuning uchun nom FAQAT suhbat boshida qo'yiladi, va 3-tekshiruv aynan
shuni — bitta suhbatda ikkinchi marta chaqirilmasligini — qo'riqlaydi.

Offline: baza ham, tarmoq ham, Telegram ham soxta.
"""
import ast
import asyncio
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import services.ai as ai
import db.history as h

_xato = 0


def check(n, nom, shart):
    global _xato
    if shart:
        print(f"[{n}] {nom} OK")
    else:
        _xato += 1
        print(f"[{n}] {nom} XATO")


# --------------------------------------------------
# 1. Qachon nomlanadi
# --------------------------------------------------
K = ai.nomlash_kerakmi
check(1, "birinchi javobdan keyin nomlanadi", K(111, 55, "assistant", 2))
check(2, "mavzusiz chatda hech qachon nomlanmaydi",
      not K(111, 0, "assistant", 2))
check(3, "savolga (user) nom qo'yilmaydi", not K(111, 55, "user", 1))
check(4, "suhbat davomida qayta nomlanmaydi",
      not K(111, 55, "assistant", 4) and not K(111, 55, "assistant", 80))
check(5, "guruhda (manfiy chat_id) nomlanmaydi",
      not K(-100123, 55, "assistant", 2))
# Debouncer ulgurmay ikkita savol kelsa bot javobi 3-qator bo'ladi.
check(6, "ikkita savol birdan kelsa ham nomlanadi", K(111, 55, "assistant", 3))


# --------------------------------------------------
# 2. Model javobini tozalash
# --------------------------------------------------
T = ai._nom_tozala
check(7, "tirnoq olib tashlanadi", T('"Python ro\'yxatlari"') == "Python ro'yxatlari")
check(8, "faqat birinchi satr olinadi",
      T("Toshkent ob-havosi\nQo'shimcha izoh") == "Toshkent ob-havosi")
check(9, "«Mavzu:» muqaddimasi kesiladi", T("Mavzu: Kitob tavsiyasi") == "Kitob tavsiyasi")
check(10, "uzun nom kesiladi",
      len(T("a" * 200)) == ai._MAVZU_NOM_MAX)
check(11, "bo'sh javob bo'sh nom", T("") == "" and T("   \n  ") == "")


# --------------------------------------------------
# 3. To'liq yo'l: safe_update_history -> editForumTopic
# --------------------------------------------------
class SoxtaJavob:
    def __init__(self, matn):
        self.output_text = matn


class SoxtaResponses:
    def __init__(self, matn):
        self.matn = matn
        self.chaqiruvlar = []

    async def create(self, **kw):
        self.chaqiruvlar.append(kw)
        return SoxtaJavob(self.matn)


class SoxtaOpenAI:
    def __init__(self, matn):
        self.responses = SoxtaResponses(matn)


class SoxtaBot:
    def __init__(self, xato=None):
        self.chaqiruvlar = []
        self.xato = xato

    async def edit_forum_topic(self, **kw):
        self.chaqiruvlar.append(kw)
        if self.xato:
            raise self.xato


async def yur(matn="Python ro'yxatlari", bot_xato=None, tarix=None):
    """Bitta savol-javobni o'tkazadi va Telegramga ketgan chaqiruvni qaytaradi."""
    qatorlar = {"n": 0}

    async def soxta_update(chat_id, content, role="user", thread_id=0):
        qatorlar["n"] += 1
        return qatorlar["n"]

    async def soxta_tarix(chat_id, limit=30, thread_id=0):
        return tarix if tarix is not None else [
            {"role": "user", "content": "python ro'yxati nima?"},
            {"role": "assistant", "content": "Ro'yxat — bu ..."},
        ]

    asl = (ai.update_chat_history, ai.get_chat_history, ai.openai_client, ai.bot)
    ai.update_chat_history = soxta_update
    ai.get_chat_history = soxta_tarix
    ai.openai_client = SoxtaOpenAI(matn)
    ai.bot = SoxtaBot(bot_xato)
    try:
        await ai.safe_update_history(111, "python ro'yxati nima?", role="user",
                                     thread_id=55)
        await ai.safe_update_history(111, "Ro'yxat — bu ...", role="assistant",
                                     thread_id=55)
        # Nomlash fon vazifasi — tugashini kutamiz.
        for _ in range(20):
            await asyncio.sleep(0.01)
            if ai.bot.chaqiruvlar:
                break
        # Ikkinchi savol-javob: qayta nomlanmasligi kerak.
        await ai.safe_update_history(111, "yana bir savol", role="user",
                                     thread_id=55)
        await ai.safe_update_history(111, "yana bir javob", role="assistant",
                                     thread_id=55)
        await asyncio.sleep(0.05)
        return list(ai.bot.chaqiruvlar), list(ai.openai_client.responses.chaqiruvlar)
    finally:
        (ai.update_chat_history, ai.get_chat_history,
         ai.openai_client, ai.bot) = asl


tg, model = asyncio.run(yur())
check(12, "Telegramga editForumTopic ketdi", len(tg) == 1)
check(13, "nom va mavzu to'g'ri uzatildi",
      tg and tg[0].get("chat_id") == 111 and tg[0].get("message_thread_id") == 55
      and tg[0].get("name") == "Python ro'yxatlari")
check(14, "modelga BIR MARTA murojaat", len(model) == 1)
check(15, "nom mini modeldan so'raladi — katta kvotadan emas",
      model and model[0].get("model") == ai.HISTORY_SUMMARY_MODEL)
check(16, "modelga foydalanuvchining SAVOLI beriladi",
      model and "python ro'yxati nima?" in str(model[0].get("input")))

# Telegram rad etsa (huquq yo'q, mavzu o'chirilgan) — javob yo'li buzilmasin.
tg2, _ = asyncio.run(yur(bot_xato=RuntimeError("TOPIC_NOT_FOUND")))
check(17, "Telegram rad etsa ham xato yuqoriga chiqmaydi", len(tg2) == 1)

# Model bo'sh qaytarsa — Telegramga umuman tegilmaydi.
tg3, _ = asyncio.run(yur(matn="   "))
check(18, "bo'sh nom bilan mavzuga tegilmaydi", tg3 == [])


# --------------------------------------------------
# 4. `update_chat_history` sonni HAR YO'LDA qaytaradi
# --------------------------------------------------
# Chegaradan oshgan holatda erta `return` bor — o'sha ham son qaytarishi
# shart, aks holda `None <= 3` TypeError beradi.
fn = next(n for n in ast.walk(ast.parse(inspect.getsource(h)))
          if isinstance(n, ast.AsyncFunctionDef)
          and n.name == "update_chat_history")
qaytish = [n for n in ast.walk(fn) if isinstance(n, ast.Return)]
check(19, "har bir return `jami` ni qaytaradi",
      len(qaytish) >= 2 and all(isinstance(r.value, ast.Name)
                                and r.value.id == "jami" for r in qaytish))

print()
print("XATO YO'Q" if not _xato else f"{_xato} TA XATO")
sys.exit(1 if _xato else 0)
