# -*- coding: utf-8 -*-
"""Telegram Business — tuzilgan qaror (`BIZNES_SXEMA`) va uning parseri.

Erkin matndagi `[tanlov:]` markerini model tarjima qildi ("[танлов:",
"[choice:") va shablonni ko'chirdi — `eval_biznes.py` 81% ko'rsatdi.
Sxema bilan 98-100%. Bu test ushlaydigan jim nosozliklar:

  ⛔️ uzilgan JSON (`{"qaror":"javob","matn":"Sal`) xom holda suhbatdoshga
     ketadi;
  ⛔️ "mana raqamim: ..." kabi shablonli variant egasiga tugma bo'ladi —
     bossa AYNAN shu ketadi;
  ⛔️ tarjima qilingan marker (zaxira yo'l) tanilmay suhbatdoshga ketadi;
  ⛔️ qoralama/avtojavob sxemasiz so'raladi (model qarorsiz erkin yozadi).

Tarmoqsiz va bazasiz ishlaydi.

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_biznes_qaror.py
"""
import asyncio
import json
import os
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import handlers.biznes as b              # noqa: E402
from db import database                  # noqa: E402
from services import ai                  # noqa: E402

EGASI, MIJOZ, DM = 7001, 9002, 7001
qa = ai.biznes_qaror_ajrat


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


def j(**k):
    d = {"qaror": "javob", "matn": "", "savol": "", "variantlar": []}
    d.update(k)
    return json.dumps(d, ensure_ascii=False)


# ── 1-6. Parser ──────────────────────────────────────────────────
check(1, "JSON javob: matn o'zi, savol bo'sh",
      qa(j(matn="Futbolka 80 000 so'm.")) == {"qaror": "javob", "matn": "Futbolka 80 000 so'm.",
                                              "savol": "—", "variantlar": []})
r = qa(j(qaror="tanlov", matn="keyinroq yozaman", savol="9 da borasizmi?",
         variantlar=["boraman", "  bugun   yo'q ", "", "3", "4"]))
check(2, "JSON tanlov: variantlar bo'sh joyi yig'iladi, bo'sh tashlanadi, 3 tadan oshmaydi",
      r["qaror"] == "tanlov" and r["variantlar"] == ["boraman", "bugun yo'q", "3"]
      and r["savol"] == "9 da borasizmi?")
check(3, "uzilgan/buzuq JSON — «egasiga», matn BO'SH (xom JSON hech qachon ketmaydi)",
      all(qa(x) == {"qaror": "egasiga", "matn": "", "savol": "model javobi buzildi",
                    "variantlar": []}
          for x in ('{"qaror":"javob","matn":"Sal', '{"qaror":"boshqa","matn":"x"}', "{}")))
check(4, "shablonli variant (…, ..., [..], <..>, ___) tashlanadi",
      qa(j(qaror="tanlov", variantlar=["mana raqamim: ...", "karta: [raqam]", "ism <ism>",
                                        "___", "…", "yo'q, bermayman"]))["variantlar"]
      == ["yo'q, bermayman"])
check(5, "zaxira: tarjima qilingan marker (танлов, choice) ham tanlov",
      qa("[танлов: savol | ha | yo'q] кейин")["qaror"] == "tanlov"
      and qa("[choice: ask | yes | no] later")["variantlar"] == ["yes", "no"]
      and qa("oddiy matn")["qaror"] == "javob")
check(6, "matn ichida qolgan marker tozalanadi; ```json``` o'rami ham",
      qa(j(matn="Salom [egasiga: x] qalay"))["matn"] == "Salom qalay"
      and qa(j(matn="Salom [tanlov: buzuq"))["matn"] == "Salom"
      and qa("```json\n" + j(matn="ok") + "\n```")["matn"] == "ok")

# ── Soxta dunyo ──────────────────────────────────────────────────
q = []
holat = {"model": j(matn="Salom!")}


class SoxtaBot:
    async def send_message(self, chat_id, text, business_connection_id=None, **kw):
        q.append(("send", chat_id, text, business_connection_id, kw.get("reply_markup")))
        return NS(chat=NS(id=chat_id), message_id=len(q) + 900)

    async def send_chat_action(self, *a, **k):
        pass

    async def read_business_message(self, *a, **k):
        pass


async def soxta_gpt(chat_id, prompt, **kw):
    q.append(("gpt", kw.get("javob_formati")))
    yield holat["model"]


async def hech(*a, **k):
    return None


async def rost(*a):
    return True


async def ruxsat(*a):
    return {"allowed": True, "unlimited": False}


async def bosh(*a, **k):
    return {}


async def bilim(_):
    return ""


async def chat_holati(*a):
    return {"ochirilgan": False, "pauza": False}


async def yarat(owner, conn, chat, matn, loyiha, variantlar=None):
    q.append(("yarat", loyiha, variantlar))
    return 1


async def birinchi(*a, **k):
    return True

b.bot = SoxtaBot()
b.get_gpt_reply = soxta_gpt
b.safe_update_history = hech
b.track_user_activity = lambda *a: None
b.send_error_with_retry = hech
b.BIZNES_MERGE_WAIT = 0.01
b._birinchi_marta = birinchi
for nom, f in dict(pro_tarifmi=rost, get_maintenance_notice_for=hech,
                   biznes_mijoz_korildi=hech, check_and_consume_quota=ruxsat,
                   check_and_consume_daily=ruxsat, refund_daily=hech, refund_quota=hech,
                   biznes_bilim_ol=bilim, biznes_uslub_ol=bosh, biznes_namuna_qosh=bosh,
                   biznes_chat_holati=chat_holati, biznes_pauza=hech,
                   biznes_loyiha_eskirt=hech, biznes_kutayotgan_tanlov=hech, biznes_loyiha_yarat=yarat,
                   biznes_mavzu_ol=hech).items():
    setattr(database, nom, f)

UL = {"owner_id": EGASI, "owner_chat": DM, "yoqilgan": True, "rejim": "avtomat",
      "ish_vaqti": None, "avto_belgi": False,
      "huquqlar": {"can_reply": True, "can_read_messages": True}}
database._biznes_kesh["c1"] = UL


async def ulanish_bor(conn_id):
    return database.biznes_ulanish_ol(conn_id)

b._ulanish = ulanish_bor
mid = [1]


def ishga(matn):
    q.clear()
    b._aytilgan.clear()
    mid[0] += 1
    x = NS(business_connection_id="c1", text=matn, caption=None, sender_business_bot=None,
           voice=None, photo=None, from_user=NS(id=MIJOZ, username="a", full_name="Ali"),
           chat=NS(id=MIJOZ), message_id=mid[0], reply_to_message=None)

    async def run():
        await b.biznes_xabar(x)
        await asyncio.sleep(0.05)
    asyncio.run(run())


def mijozga():
    return [x[2] for x in q if x[0] == "send" and x[3]]


def egasiga():
    return [x for x in q if x[0] == "send" and not x[3]]


# ── 7-9. Avtomat: sxema bilan so'raydi, qarorga amal qiladi ──────
ishga("salom")
check(7, "avtomat modeldan BIZNES_SXEMA bilan so'raydi; javob suhbatdoshga",
      ("gpt", ai.BIZNES_SXEMA) in q and mijozga() == ["Salom!"])

holat["model"] = '{"qaror":"javob","matn":"Futbolka 80'
ishga("futbolka qancha")
check(8, "avtomat: uzilgan JSON — suhbatdoshga neytral gap, xom JSON YO'Q, egasiga xabar",
      mijozga() == [b.neytral_gap(None)] and egasiga() and "qaror" not in str(mijozga()))

holat["model"] = j(qaror="tanlov", matn="keyinroq yozaman", savol="kelasanmi?",
                   variantlar=["kelaman", "bugun yo'q"])
ishga("ertaga kelasanmi")
check(9, "avtomat: JSON tanlov — neytral gap suhbatdoshga, variant tugmalari egasiga",
      mijozga() == ["keyinroq yozaman"] and ("yarat", "kelaman", ["kelaman", "bugun yo'q"]) in q
      and "bz:yv:1:0" in str(egasiga()[0][4]))

# ── 10-11. Yordamchi ─────────────────────────────────────────────
UL["rejim"] = "yordamchi"
holat["model"] = j(matn="Salom, qalaysiz?")
ishga("salom")
check(10, "yordamchi: sxema bilan so'raydi; javob qoralama bo'ladi, suhbatdoshga hech narsa",
      ("gpt", ai.BIZNES_SXEMA) in q and ("yarat", "Salom, qalaysiz?", None) in q
      and mijozga() == [])

holat["model"] = j(qaror="egasiga", matn="aniqlashtiraman", savol="chegirma so'radi")
ishga("chegirma bormi")
check(11, "yordamchi: «egasiga» — tanlov ko'rinishida (variantsiz), qoralama emas",
      ("yarat", "", []) in q and "faqat siz bilasiz" in egasiga()[0][2])

print("\nHammasi o'tdi: 11/11")
