# Telegram AI bot (@uzchatgptaibot)

aiogram 3.31 + OpenAI Responses API. Railway'da bitta jarayon —
`worker: python main.py` (`Procfile`): polling va web admin panel birga.
`git push meloress main` — deploy.

Qoidalar va arxitektura — **`CLAUDE.md`**; Telegram Business — **`BIZNES.md`**;
Bot API 10.3 va undan keyingilar — **`BOT_API_103.md`**.

## Papkalar tuzilishi

```
main.py                      kirish nuqtasi: handlerlar TARTIBI (xavfsizlik
                             sharti — CLAUDE.md), polling, web panel

core/                        umumiy infratuzilma
  config.py                  sozlamalar, prompt, limitlar (daily_limit),
                             yorliq lug'atlari (ACTIVITY_TYPES, AUDIT_ACTIONS …)
  loader.py                  bot, dispatcher, OpenAI mijozi, logger
  memory.py                  RAM holati (xabar buferi, qayta urinish, rasmlar)
  olchov.py                  Business o'lchov jurnali
  csv_fayl.py                CSV eksport (formula in'eksiyasidan himoya)

db/                          PostgreSQL / asyncpg
  database.py                foydalanuvchilar, kvota, eslatmalar, Business …
  history.py                 suhbat tarixi va xulosa (mavzular bo'yicha)

handlers/                    Telegram voqealari
  messages.py                matn, rasm/albom, hujjat, ovoz; status animatsiyasi
  guest.py                   guest mode (bot a'zo bo'lmagan chatlarda)
  callbacks.py               «Qayta so'rash»
  pro.py                     Pro, to'lov, sovg'a, promokod
  profile.py, capabilities.py, digest.py (/kunlik)
  biznes.py, biznes_uslub.py, biznes_media.py   Telegram Business
  helpers.py                 umumiy yordamchilar, eslatma va fon kuzatuvchilari
  admin/                     botda qolgan admin qismi: /xabar, /kod, report,
                             kunlik hisobot (qolgani web panelda)

services/
  ai.py                      OpenAI oqimi, tool-loop, qidiruv, rasm, STT/TTS
  sandbox.py                 model yozgan Python'ni izolyatsiyada bajarish
  sandbox_helpers/           sandbox ICHIGA nusxalanadi (docgen, deck, xledit)
  places.py                  yaqin atrofdagi joylar (Overpass)
  menu.py                    / buyruqlar menyusi va Mini App tugmasi
  file_task_quota.py         fayl sanog'i (bir marta yechish, qaytarish)

web/                         admin panel (aiohttp, bot jarayoni ichida)
tests/                       mustaqil assert-skriptlar (~100 ta)
assets/                      status emoji animatsiyalari (webm, ≤ 64 KB)
```

`services/sandbox_helpers/` `services/sandbox.py` yonida turishi **shart** —
sandbox uni `Path(__file__).parent` orqali topadi.

## Testlar

Freymvork yo'q — har fayl `assert` bilan yozilgan va mustaqil ishga tushadi:

```bash
PYTHONIOENCODING=utf-8 python tests/test_memory.py        # bitta test
node --check web/static/panel.js                          # panel JS sintaksisi
```

Hammasini ishga tushirish va qaysilari nimani qo'riqlashi — `CLAUDE.md`.

## Muhit o'zgaruvchilari

`.env`: `BOT_TOKEN`, `OPENAI_API_KEY`, `DATABASE_URL` (⚠️ mahalliy `.env`
jonli bazaga ulangan), ixtiyoriy `TEXT_EMOJI_PACK`, `WEB_APP_URL`.
