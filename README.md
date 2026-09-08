# Telegram AI bot

aiogram 3.29 + OpenAI Responses API. Railway'da `worker: python main.py`
sifatida ishlaydi (`Procfile`).

## Papkalar tuzilishi

```
main.py                      kirish nuqtasi: handlerlarni ro'yxatdan
                             o'tkazadi va polling'ni boshlaydi

core/                        umumiy infratuzilma
  config.py                  sozlamalar, system prompt, limit/narxlar
  loader.py                  bot, dispatcher, OpenAI mijozi, logger
  keyboards.py               klaviaturalar
  memory.py                  jarayon ichidagi vaqtinchalik holat
                             (xabar buferi, qayta urinish keshi)

db/                          ma'lumotlar bazasi (PostgreSQL / asyncpg)
  database.py                foydalanuvchilar, kvotalar, admin, ban
  history.py                 suhbat tarixi

handlers/                    Telegram voqealariga javob beruvchi qatlam
  messages.py                matn, rasm, hujjat, ovoz
  callbacks.py               tugma bosishlari (qayta urinish)
  guest.py                   guest mode (bot a'zo bo'lmagan chatlarda)
  admin/                     admin panel (paket)
    __init__.py              FAQAT handlerlarni ro'yxatdan o'tkazish
    common.py                qo'riqchilar va umumiy yordamchilar
    broadcast.py             ommaviy xabar
    promo.py                 promokod, referal, "Bepul Pro"
    users.py                 ro'yxat, kartochka, ban/premium, to'lov
    stats.py                 statistika va faol foydalanuvchilar
    system.py                texnik ta'til, kuzatish, adminlar, report
    journal.py               audit, xatolar, daromad, limitlar
    menu.py                  klaviatura ostidagi inline menyular
    daily.py                 kunlik hisobot, rejali tarqatma (fonda)
  profile.py                 /profile
  helpers.py                 handlerlar uchun yordamchilar
                             (xatolik xabari, kuzatuv, kunlik pin)

services/                    tashqi servislar va og'ir ishlar
  ai.py                      OpenAI oqimi, tool-loop, qidiruv, STT/TTS,
                             hujjatdan matn ajratish
  sandbox.py                 GPT yozgan Python kodini izolyatsiyada
                             bajarish
  file_task_quota.py         fayl yaratish sanog'i (bir marta yechish,
                             fayl chiqmasa qaytarish)
  sandbox_helpers/           sandbox ICHIGA nusxalanadigan modullar
    docgen.py                PDF/PPTX joylashuvini o'lchab chizish
    xledit.py                Excel'ni formatni buzmasdan tahrirlash

tests/                       qo'lda ishga tushiriladigan tekshiruvlar
docs/                        spetsifikatsiya va rejalar
```

`services/sandbox_helpers/` `services/sandbox.py` yonida turishi **shart** —
sandbox uni `Path(__file__).parent / "sandbox_helpers"` orqali topadi va
har bir ishga tushirishda vaqtinchalik ish papkasiga nusxalaydi.

## Testlar

Test freymvorki ishlatilmaydi — har bir fayl `assert` bilan yozilgan va
mustaqil ishga tushadi:

```bash
python tests/test_extract.py            # hujjatdan matn ajratish
python tests/test_file_task_loop.py     # tool-loop, kvota, bosqich byudjeti
python tests/test_file_task_quota.py    # fayl sanog'i
python tests/test_pending_file.py       # fayl + alohida ko'rsatma
python tests/test_refund_quota.py       # kvota qaytarish
python tests/test_tts_lang.py           # TTS til aniqlash (--live bilan sintez)
python tests/test_activity_tracking.py  # statistikada hamma faollik ko'rinishi

python services/sandbox.py                    # sandbox izolyatsiyasi
python services/sandbox_helpers/docgen.py     # hujjat chizish
python services/sandbox_helpers/xledit.py     # Excel tahriri
```

## Faollik turlari

Admin statistikasi `user_activity` jadvaliga tayanadi. Kod yozadigan
har bir tur `handlers/admin/stats.py` dagi SQL filtri va `type_labels` da
bo'lishi shart — aks holda u statistikada ko'rinmay qoladi.
`tests/test_activity_tracking.py` shuni qo'riqlaydi.

| Tur | Qayerda yoziladi |
|---|---|
| `text_message`, `photo_message`, `document_message`, `voice_message` | `handlers/messages.py` |
| `guest_*_message` | `handlers/guest.py` (kvota ruxsat bergan holatda) |
| `file_task` | `handlers/messages.py` (fayl haqiqatan chiqqanda) |
| `start` | statistikaga kirmaydi — AI chaqiruvi emas |

## Muhit o'zgaruvchilari

`.env` faylida: `BOT_TOKEN`, `OPENAI_API_KEY`, `DATABASE_URL`.
