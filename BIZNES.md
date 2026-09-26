# Telegram Business — egasi nomidan yozuvchi bot

Bu fayl — Telegram Business funksiyasining TO'LIQ qoidalari va keyingi ishlar
rejasi. `CLAUDE.md` da faqat qisqa ko'rsatkich bor; bu sohada ishlashdan
oldin shu faylni o'qing. Bosqichlar rejasi va asl qarorlar — `REJA.md`.

## Kod xaritasi

| Fayl | Nima |
|---|---|
| `handlers/biznes.py` | ulanish, `biznes_kimdan` (tsikl himoyasi), nuqtali buyruqlar, Yordamchi/Avtomat, `/biznes` ekrani, hisobot, javobsiz chatlar, `/mijozlar`, profil/story |
| `handlers/biznes_uslub.py` | egasining USLUBI: namuna yig'ish, o'rganish, uslub bloki, «Uslubim» ekrani |
| `services/ai.py` | `BIZNES_INSTRUCTIONS` (mijoz yo'lining o'z prompti), `biznes_yoriqnoma=` parametri, `egasiga_ajrat`, `biznes_kun_xulosasi`, `BIZNES_MANBA` |
| `db/database.py` | `biznes_*` jadvallar va funksiyalar (SQL faqat shu yerda) |
| `core/config.py` | `BIZNES_*` konstantalar |
| `core/csv_fayl.py` | CSV formula-injection himoyasi (panel bilan umumiy) |
| `tests/test_biznes*.py` | har bosqichga bitta test, hammasi oflayn |
| `tests/eval_biznes.py` | ANIQLIK — jonli model, qo'lda (prompt o'zgarsa oldin/keyin) |

Sinov davri: `/biznes` va `/mijozlar` ATAYLAB menyuda yo'q
(`services/menu.py`), yozib ishlatilsa ishlaydi. Hamma uchun ochilganda
`PRO_COMMANDS` ga qo'shiladi. Avtomat rejim ochiq (`BIZNES_AVTOMAT_OCHIQ = True`, egasi 2026-09-26 da o'lchovsiz ochdi).

## Egasining bot DM'i: bitta «💼 Biznes» mavzusi

⛔️ Mavzular yoqilgan shaxsiy chatda `message_thread_id` SIZ yuborilgan xabar HAR SAFAR
yangi mavzu ochadi (jonli ko'rilgan, 2026-09-25) — har qoralama alohida mavzu edi. Shuning
uchun egasiga ketadigan hamma Business xabari `handlers/biznes.py::_dm_yubor()` dan o'tadi:
`biznes_mavzusi()` mavzuni bir marta ochadi (`createForumTopic`, per-dm qulf — ikkita
ochilmasin), id `biznes_profil.dm_mavzu` da. Egasi mavzuni o'chirsa Telegram "thread not
found" deydi — yangisi ochilib xabar bir marta qayta yuboriladi. Mavzu ochilmasa (mavzular
o'chiq) — mavzusiz, qayta urinish soatiga bir. Mijozga ketadigan xabarlar bunga TEGMAYDI
(ular `business_connection_id` bilan). `nomla_mavzu()` bu mavzuni `biznes_mavzumi()` bilan
o'tkazib yuboradi — qoralamalar tarixga yozilmagani uchun egasining u yerdagi birinchi
savoli "yangi mavzu" bo'lib ko'rinib, nom ustidan yozilardi. `test_biznes_mavzu.py`.

Callback'dan keladigan javoblar (`query.message.answer`) o'zi shu mavzuga tushadi — aiogram
mavzuni xabardan oladi.

## Faqat egasi biladigan savol — `[tanlov:]`, va «🤖 avtojavob» belgisi

Jonli sinov (2026-09-25): bot egasi nomidan "menda ham sigaret qolmagan" (egasi chekmaydi) va
"boramiz, 9:00 da" (egasining vaqtini bilmay) deb yozdi. Model rolni o'ynab bo'shliqni to'qiydi.

⛔️ **Qoida `BIZNES_INSTRUCTIONS` da (statik, keshlanadi):** egasining shaxsiy hayoti haqida fakt
to'qima, uning nomidan va'da berma — o'rniga `[tanlov: savol | variant | variant]`. Prompt kafolat
emas, shuning uchun markerni **kod** ushlaydi (`services.ai.tanlov_ajrat`, `egasiga_ajrat` naqshi;
buzilgani ham tanlov — variantsiz):
- **Yordamchi:** soxta qoralama o'rniga egasiga "buni faqat siz bilasiz" + variant tugmalari
  (`bz:yv:<lid>:<n>`), «O'zim yozaman», «Bekor». «Yuborish» tugmasi YO'Q — bir bosishda yolg'on
  ketmasin. Variantlar `biznes_loyiha.variantlar` (JSONB) da; `n` ro'yxat chegarasida tekshiriladi
  (`isinstance(bool)`). Tanlangan variant — modelning matni: `yuborildi`, namuna EMAS.
- **Avtomat:** suhbatdoshga marker ortidagi neytral gap (yoki `NEYTRAL_JAVOB`), chat pauzada,
  egasiga o'sha tugmalar. Egasi chatga o'zi yozsa kutayotgan tanlov eskiradi (avtomatda ham).
- **`.javob`:** marker chatga ketmaydi (egasi mazmunni o'zi aytgan — qaror uniki).

**Biznes ham, shaxsiy ham:** rejim yo'q — bot faqat Bilimda (`[EGASI HAQIDA]`) yozilganga tayanadi;
biznes yozilmagan bo'lsa narx/mahsulot haqida gapirmaydi. Suhbatdosh "mijoz" deb emas,
"suhbatdosh" (do'st, oila ham) deb ataladi.

**«🤖 avtojavob» belgisi.** Telegram'ning "ChatGPT AI" yozuvi faqat EGASIGA ko'rinadi. Bot o'zi
(egasi ko'rmasdan) yuborgan AVTOMAT javob oxiriga kursiv belgi qo'shiladi (`avto_matn`,
`biznes_ulanish.avto_belgi`, standart yoqilgan, `/biznes` → «🤖 belgisi»). Yordamchida yo'q —
egasi bosgan matn uning so'zi. ⚠️ Tarixga BELGISIZ matn yoziladi, aks holda model belgini o'z
uslubi deb takrorlaydi.

Narx (`tiktoken`): `BIZNES_INSTRUCTIONS` 293 → **601**, yo'riqnoma +28 (yordamchi) / +50 (avtomat) —
har qoralama ~**+340 token**. `test_biznes_tanlov.py`.

## Aniqlik: tuzilgan qaror va baholash to'plami (2026-09-26)

⛔️ **Prompt yoki model o'zgarsa — `tests/eval_biznes.py` OLDIN va KEYIN.** Jonli model, 40 ta
qiyin xabar (shaxsiy fakt, va'da, biznes, xarid, injeksiya, "botmisan", haqorat), har biri
uchun kutilgan qaror va taqiqlar. `test_*.py` emas (token sarflaydi, natija tasodifiy):
`--takror 3` bilan o'lchang — bir ishga tushirish 89% va 97% ni berdi, prompt o'zgarmasdan.
`--qoralama` — Yordamchi rejimi. Natija `tests/.eval_biznes_oxirgi.json` (gitignore).

| | avtomat | qoralama |
|---|---|---|
| erkin matn + `[tanlov:]` markeri | 81% (haqiqatda 76%: `’` regexdan qochdi) | — |
| `BIZNES_SXEMA` + prompt tuzatishlari | **98-99%** (×3) | **100%** (×2) |

**Nega sxema.** Model markerni tarjima qildi (`[танлов:`, `[choice:`) va shablonni ko'chirdi.
Endi `text.format` = `BIZNES_SXEMA`: `qaror` (javob | tanlov | egasiga), `matn`, `savol`,
`variantlar` — har javobda qaror majburiy. `biznes_qaror_ajrat()` (sof, `test_biznes_qaror.py`):
- `{` bilan boshlanib ajratilmaydi (uzilgan JSON) → **egasiga**, matn bo'sh — xom JSON hech
  qachon ketmaydi;
- `...`, `…`, `[..]`, `<..>`, `___` li variant tashlanadi (egasi bossa aynan shu ketardi);
- JSON bo'lmasa — eski markerlar zaxira (tarjimalari bilan).
Qoralamada `egasiga` → variantsiz tanlov. Rasm yo'li ham sxema bilan (jonli tekshirilgan).

**Prompt qoidalari eval'dan chiqdi:** odat haqida "ha" ham, "yo'q" ham fakt; faqat umumiy
odob (salom, qalaysan, rahmat) istisno — "ovqatlandingmi" odob emas; bilimda yo'q mahsulotga
"yo'q" dema (ro'yxat to'liq emas); Telegram/SMS kodi → tanlov; "botmisan?" — inkor qilma;
haqoratni qaytarma; xarid/shikoyat/chegirma → har doim egasiga (narxni bilsa ham); oddiy narx
savoli → javob; neytral gap birinchi shaxsda, savolsiz, egasining ismisiz. Narx: instructions
848, avtomat yo'riqnomasi 763, qoralama 440 token (`tiktoken`) — eski yordamchi promptidan
(5 521) baribir ancha arzon.

## Ishonchlilik va pauza (2026-09-26)

- **Dublikat update** (`biznes_korilgan`, RAM + baza): avtomat ikki marta javob bermaydi.
  Testlarda `b._birinchi_marta` soxtalanadi — aks holda `.env` dagi haqiqiy bazaga boradi.
- **Poyga:** model yozayotganda egasi o'zi yozsa, qoralama/avtojavob chiqmaydi. Soat emas,
  TARTIB RAQAMI (`time.monotonic()` Windows'da ~16 ms qadamli — test shunda yiqildi).
- **429:** `_qayta_429` — ≤30 s kutib bir marta. **Qoralama yozilmasa** — egasiga soatiga bir.
- **Pauza faqat egasi o'zi yozganda** ('egasi', 3 soat). Uzatish pauzasi OLIB TASHLANDI —
  pastdagi «Uzatishdan keyin jim qolmaslik» bo'limi.
- **Alifbo:** suhbatdosh lotinda yozsa, javob/qoralama/variantlardagi kirill `uz_lotinga()`
  bilan o'giriladi (kirillda yozganga tegilmaydi).
- **Tezlik:** bilim/uslub RAM keshi (har yozuvchi bekor qiladi — `test_biznes_kesh.py`
  7-tekshiruv), Pro keshi 60 s, parallel o'qish, business indeks.
- **`/biznes`:** bosh ekranda rejim + Bilim/Uslubim/Sozlamalar + bugungi statistika; qolgani
  `_sozlama_kb`.

## Tejash (AUDIT oxirgi bandlari, 2026-09-26)

- **Debounce 3 s** (`BIZNES_MERGE_WAIT`, DM'niki 1,5 s): "salom" / "narxi?" / "futbolka"
  bitta so'rov. Testlar `b.BIZNES_MERGE_WAIT` ni kichraytiradi (`TEXT_MERGE_WAIT` emas).
- **Model muddati 60 s** (`BIZNES_MODEL_TIMEOUT`): osilgan model chat qulfini 180 s
  ushlardi. Muddat — oddiy xato: ball qaytadi, egasiga "javob kechikdi".
- **"rahmat" / 👍 — Yordamchida qoralama yo'q** (`faqat_rahmatmi`). ⛔️ "ha", "ok", "mayli"
  qo'shilmasin: ular egasining savoliga javob, keyingi qadamni qoralama aytadi.
- **Vaqt xabari tarixdan keyin** (`services/ai.py`, `biznes_vaqt`): oldin turgan daqiqali
  vaqt keshni 0 ga tushirardi. Eval o'zgarmadi.
- **Kartoteka fonda**, ism o'zgarmasa 10 daqiqada bir.
- ATAYLAB qilinmadi: tarix oynasini qisqartirish (5.3) va "egasi faol — qoralama yo'q"
  (4.5) — ikkalasi ham aniqlikni tokenga almashtiradi. `AUDIT.md` jadvali.

## Uzatishdan keyin jim qolmaslik (2026-09-26)

Egasi jonli sinovda: bot so'rashi kerak narsani so'radi, keyin suhbatdosh yana yozsa javob
bermadi. Avval 3 soatlik 'uzatish' pauzasi + bir marta "Hozir bandman" + egasiga eslatma edi —
egasi buni ham "javob bermayapti" deb ko'rdi. Endi:

- Uzatishda (tanlov / egasiga) suhbatdoshga `neytral_gap(ism)` — **"Og'abek online bo'lganda
  o'zi javob beradi."** (suhbatdosh tilida). Ism — `bot.get_chat(owner_chat).first_name`,
  RAM'da (`_egasi_ismi`). Prompt shu gapni aynan so'raydi; `matn` bo'sh bo'lsa kod qo'yadi.
- ⛔️ **Pauza qo'yilmaydi** — suhbatdosh yana yozsa bot odatdagidek javob beradi (yangi shaxsiy
  savol bo'lsa — yana tanlov). Bazada qolgan eski 'uzatish' pauzalari `_toxtash_sababi`da
  e'tiborsiz. Egasi O'ZI chatga yozsa — 'egasi' pauzasi qoladi (suhbat uning qo'lida).
- `egasi_variantlari()` — variantdan neytral gap va egasining ismi olib tashlanadi: model uni
  variant qilib ham qo'ydi, egasi bossa o'zi haqida uchinchi shaxsda yozgan bo'lardi.
- `BAND_JAVOB`, `_pauza_paytida`, `biznes_band_ol`, `BIZNES_ESLATMA_DAQIQA`, «▶️ Botni qayta
  yoqish» o'chirildi (`band_yuborildi` ustuni bazada qoldi — ishlatilmaydi).
- **Belgi:** `AVTO_BELGI = "ᵃᵛᵗᵒʲᵃᵛᵒᵇ"` — javob OSTIDA, bo'sh qatorsiz, HTML'siz ("🤖 avtojavob"
  bo'sh qatordan keyin kursivda edi — egasi: "juda xunuk").
- Eval: avtomat 88/88, qoralama 44/44. `test_biznes_pauza.py`.

## «💾 Eslab qol» (2026-09-26)

**Muammo:** bot "chekasanmi?" ni har safar egasiga uzatadi — egasi bir marta javob bergan
bo'lsa ham. Bot egasini o'rganmasdi.

- Egasi tanlovga javob beradi — tugma (`bz:yv`), «O'zim yozaman» (`process_tahrir`) yoki
  **chatning o'zida** (`_egasi_tanlovga_javob`: egasining shu chatdagi birinchi xabari —
  javob, tanlov `tahrirlandi`). Uchala yo'lda ham «💾 Eslab qol» tugmasi (`_fakt_kb`).
  Faqat TANLOVga (`variantlar IS NOT NULL`): oddiy qoralama bilimdan kelgan — aylanma.
- Bosilsa (`bz:fk`, `_fakt_saqla`) Bilim oxiriga `FAKT_SARLAVHA` ostida
  `- «savol» → javob` (`bilimga_fakt`: bitta qator, takrorsiz, `clean_biznes_bilim` —
  chegara va karta tekshiruvi). ⛔️ Alohida jadval EMAS: Bilimni egasi ko'radi va
  tahrirlaydi; ikkinchi, ko'rinmaydigan "xotira" — egasi o'chira olmaydigan fakt.
- `_FAKT_QOIDASI` yo'riqnomaga faqat sarlavha bor bilimda qo'shiladi (qolganlarga 0 token):
  doimiy fakt → o'zi javob; vaqtga bog'liq ("hozir qayerdasan → uydaman") → baribir tanlov.
  Eval: `fakt_*` holatlari 12/12.
- `test_biznes_fakt.py`.

## Keyingi ishlar (rejalashtirilgan, 2026-09-25)

Maqsad: egasi hech narsa sozlamasin — odatdagidek ishlasin, bot o'zi o'rgansin.

1. **Tahrirlash tugmasisiz o'rganish.** Egasi qoralamani e'tiborsiz qoldirib
   mijozga o'zi yozsa, hozir qoralama shunchaki `eskirgan` bo'ladi
   (`biznes_loyiha_eskirt`). O'rniga juftlik (qoralama → egasi aslida
   yozgani) tuzatish sifatida saqlansin — eng kuchli signal, egasiga nol ish.
2. **Bilim o'zi yig'ilsin.** Ertalabki hisobotdagi bitta mini chaqiruv egasi
   javoblaridagi faktlarni (narx, manzil, muddat) ajratib Bilimga qo'shsin;
   egasiga "qo'shildi: …" + o'chirish tugmasi.
3. **Ulanganda o'zi sozlansin.** Ulanish → avtomatik Yordamchi + bitta
   tushuntirish xabari; rejim/bilim/qoidalar ixtiyoriy.
4. **`/biznes` soddalashsin.** Asosiy ekranda holat (necha xabardan
   o'rganildi, bugun nechta taklif, nechtasi tahrirsiz), qolgani
   «Sozlamalar» ichida; «Hozir o'rganish» kerak bo'lmay qoladi.

Jonli tasdiqlanmagan (REJA.md 0.2): egasining o'z xabarlari `business_message`
bo'lib keladimi (namuna yig'ish shunga bog'liq — Railway logida
`[BIZNES] uslub o'rganildi` yoki namuna sanog'i bilan tekshiring).

## Qoidalar

### Telegram Business: the owner's dot-commands (phase 1)

`handlers/biznes.py`. The owner connects the bot to their own account (Settings → Telegram
Business → Chatbots) and types `.en Salom`, `.javob …`, `.xulosa` in any private chat; the
command is deleted and the result appears in its place (or in the owner's bot DM). In this
phase the bot **never writes to a customer on its own**. Plan and later phases: `REJA.md`.

⛔️ **`biznes_kimdan()` is the single loop guard.** `sender_business_bot` is checked
*first*: when the bot sends on the owner's behalf, `from_user` is the **owner**, so the
other order would read the bot's own result as the owner's next command. Every handler goes
through this function and nowhere else re-states the condition. `test_biznes.py` checks 3-4
fail if the order is swapped (verified by mutation).

⚠️ **History is keyed `(customer_chat_id, -owner_id)`.** In a business chat `chat.id` is the
*customer's* id, so the customer's own DM with the bot (`thread_id = 0`) would otherwise merge
with it. Topic ids are positive, so a negative one collides with nothing and `db/history.py`
needed no change — but `nomlash_kerakmi()` had to become `thread_id > 0`: `bool(-7001)` is
`True`, and `editForumTopic` would have been called in a customer chat. Customer messages are
stored as `user`, the owner's (and what the bot sent for them) as `assistant`, only with
`can_read_messages` and only for a Pro owner — the summary model costs tokens.

⚠️ **The connection cache is written before the database.** `biznes_ulanish_yoz()` updates
`_biznes_kesh` first, so a failed write cannot leave a disconnected account "enabled" in RAM
(the bot would keep acting and nothing would raise). A connection missing from the cache —
made before the table existed — is fetched with `getBusinessConnection` and stored.

Order inside `_bajar()` is the quota contract: maintenance → Pro → right → argument → points
→ delete the command → model → send. A free owner, a missing right or an empty argument costs
**nothing**; an empty model answer refunds. A rejected send to the chat (e.g. the 24-hour rule)
sends the text to the owner instead of pretending it went. The "no preamble" rule
(`BUYRUQ_QOIDASI`) lives in the command prompt, **not** in `instructions` — it would be paid on
every round of every request; `test_prompt_rules.py` guards both facts. `_toza()` strips a
leftover "Mana tarjima:" line as a second layer.

⚠️ Still unverified live (`REJA.md` 0.2): whether the owner's own messages arrive as
`business_message`, whether the bot's messages come back, which right `deleteBusinessMessages`
needs for the owner's message (a failure is logged and the result is sent anyway), and the
exact 24-hour error text. Test on a **second bot** before enabling Business Mode on the live
one — the inline-mode lesson applies.

### Telegram Business: knowledge and the "Yordamchi" mode (phase 2)

`/biznes` (Pro) picks the mode — `buyruq` / `yordamchi` / `kuzatuv`
(`BIZNES_REJIMLAR`) — and takes the owner's free-text **knowledge** (`biznes_profil`,
`BIZNES_BILIM_MAX` 4 000 chars). In `yordamchi` a customer message is debounced, the model
writes a reply **draft**, and the draft goes to the owner's bot DM with Yuborish / Tahrirlash /
Bekor. Nothing reaches the customer that the owner did not tap. `kuzatuv` only writes history.

⛔️ **The customer path is `biznes_yoriqnoma=`, and that one argument does three things.**
It appends knowledge + rules as a `developer` message (never `instructions` — per-owner text
there poisons the cache for everyone), it **forces `tools_enabled=False`** inside
`get_openai_reply` (a customer must not draw images or search on the owner's quota, whatever
the caller passes), and it **skips `_memory_context`** — the owner's personal memory would
otherwise leak into text written to a stranger. `test_biznes_yordamchi.py` checks 1-3 pass
`tools_enabled=True` on purpose; check 2 fails if the forcing line is deleted (verified).

Measured with `tiktoken`: the rules block is **238 tokens**, a full 4 000-char knowledge text
**~1 726** (Uzbek; the plan's "≈1 000" estimate was low). Both are paid on every draft, on top
of the usual prefix and the chat history — a draft is a normal-sized request, charged to the
owner's points.

⚠️ **The debounce reuses `text_merge_buffers` keyed `(customer_chat, -owner)`**, so the DM
queue's wake-up in `_process_merged_text` must skip negative keys (`k[1] >= 0`): the customer's
own DM has the same `chat_id`, and without the guard it would pick up the business buffer and
answer the customer's business message **in their DM**. Check 24 pins it. The customer's text
is written to history *after* the model call — written before, the model sees it twice.

⛔️ **Sending is an atomic claim, never select-then-send.** `biznes_loyiha_band()` is one
`UPDATE … WHERE holat = 'kutmoqda' AND owner_id … AND age < 24h RETURNING`; the loser of a
double tap gets `None` and sends nothing (check 13 fires two taps with `asyncio.gather`, and
fails against a check-then-act variant). A rejected send puts the row back to `kutmoqda` and
tells the owner the reason — it is never reported as sent. The owner writing to the customer
themselves marks pending drafts `eskirgan`, and a new draft stales the previous one.
`callback_data` carries only the row id (64-byte limit), so drafts live in Postgres, not RAM.

Knowledge is **rejected, not truncated**, when too long (a truncated price list loses its tail
silently) or when it holds a card or passport number. The card rule is deliberately narrower
than `_SECRET_RE`: a shop phone number must pass, and so must a price list like
"50 000 80 000 120 000" — 16 digits with separators, which a "13+ digits" rule rejected.

**Measuring phase 2 → 3:** the gate is the share of drafts sent unedited. Rows end as
`yuborildi` (unchanged) or `tahrirlandi` (owner's text), and every send logs
`[BIZNES] yuborildi … tahrirsiz=True|False`. Below ~60% the plan says: no automatic mode.

### Telegram Business: the "Avtomat" mode (phase 3)

The bot answers the customer **itself**. ⛔️ **It shipped switched off** and the owner opened it
deliberately on 2026-09-26, before the measurement, once `[tanlov:]` and the 🤖 label existed.
`BIZNES_AVTOMAT_OCHIQ = False` hides the button *and* stops processing — the original reason: `REJA.md`
allows this mode only after phase 2 shows ≥60% of drafts sent unedited — and nothing has
been measured yet. Flip that one constant after the measurement; `test_biznes_avtomat.py`
check 31 pins the default so the flip has to be deliberate.

Every reply costs one unit of the new **`biznes` daily counter** (`DAILY_COUNTERS` row, two
`users` columns, `PLAN_LIMITS` free 0 / Pro 50 / premium ∞, `LIMIT_NOMI`), not points. 50 is
a guess sized against the grant (one reply ≈ 8-10k tokens → ~450k/day for one busy owner);
the phase-3 measurement exists to correct it, and it is editable in the panel.

⛔️ **Nothing technical ever reaches the customer.** Four paths, each tested: an exhausted
counter sends the customer nothing and the owner **one** message a day; a model error or a
rejected send refunds the counter and goes to the owner through `send_error_with_retry(...,
kind="biznes", retry=False)` — at most once an hour, or an OpenAI outage would become one owner
message per customer message. `retry=False` exists for this: the retry button would re-run the
customer's text as the *owner's* DM question. Check 28 collects every customer-bound text in the
whole run and fails on any error, marker or limit wording.

⛔️ **`[egasiga: sabab]` is caught by code, not trusted to the model.** `egasiga_ajrat()` (next
to `strip_rich_tokens()`) removes well-formed markers and also a *broken* one up to the end of
the line — raw `[egasiga: narx` would show the customer the bot's internal instruction. A marker
means: the customer gets the neutral sentence the model wrote after it (or `NEYTRAL_JAVOB`),
the owner gets the reason and the message, and the chat pauses for `BIZNES_PAUZA_SOAT` (3). An
empty answer is treated as a handover too — silence is worse. The avtomat instructions are
**363 tokens** (`tiktoken`), 125 more than the draft ones, on top of knowledge and history.

⚠️ **Pause and per-chat opt-out live in Postgres (`biznes_chat`), not RAM** — a deploy must not
make the bot walk back into a conversation the owner took over. The owner writing in the chat
sets the pause (the natural "take over"); the pause is compared with `NOW()` in SQL so the two
clocks cannot disagree. Working hours (`ish_vaqti`, Tashkent) are the window the bot **is**
active; `ish_vaqtimi()` handles the midnight crossing and treats the end as exclusive.

⚠️ **`biznes_kimdan()` also recognises the bot's own sends by `(chat_id, message_id)`**
(`_yuborilgan`, last 2 000). Whether a bot message comes back with `sender_business_bot` is still
unverified (`REJA.md` 0.2.3); without this second layer an echoed auto-reply would read as the
owner writing, and every reply would pause its own chat. Check 24 fails if it is removed.

Voice (STT → the normal debounced flow) and photos (`get_vision_reply(..., biznes_yoriqnoma=)`,
single round: no memory tool, no `edit_image`) are handled **only in avtomat** — in the other
modes the transcription would cost money and give the owner nothing. One reply per chat at a
time: the same per-chat lock as the drafts (`GeneratingState` is keyed by a user, and here there
is no user to key it by).

### Telegram Business: report, unanswered chats, customer file, profile (phase 4)

**Morning report (4.1).** `biznes_hisobot_watcher()` checks every 10 minutes and sends after
`BIZNES_HISOBOT_SOAT` (9, Tashkent) — deliberately *not* "sleep until 9": a deploy at 9:05
would lose that day's report. Once-per-day is `biznes_hisobot_band()`, an atomic
`UPDATE … WHERE hisobot_sana < today RETURNING` taken **before** any work, so a restart
neither repeats the message nor pays the model twice. An empty day sends nothing.

One **mini-model** call per owner per day (`biznes_kun_xulosasi`, `HISTORY_SUMMARY_MODEL`,
**175-token** prompt) writes the summary *and* extracts the customer-file fields — one call
per chat would cost N times as much. Its failure leaves the report with numbers only.

⛔️ **The model's customer-file output is untrusted twice over.** It names chats by `n`, never
by `chat_id`, and `n` is bounds-checked against the list it was shown (`isinstance(bool)`
first — `True` is an `int`); the fields go through `clean_mijoz_maydon()` (phone must be 9-15
digits after a regex, else `None`; other fields one line, length-cut). An empty field never
overwrites a known one (`COALESCE`). Check 6 feeds a bool, a string and an out-of-range `n`.

**Unanswered chat (4.2).** Every 5 minutes, chats whose **last** row is the customer's and is
60-180 min old (`biznes_javobsizlar`, partial index `… WHERE thread_id < 0` built in the
background). The upper bound is what keeps a deploy — which empties the RAM flag — from
re-alerting old chats. `_ogoh_holat` pattern: the flag is set **from the send result** (an alert
that did not arrive is not "said"), and dropped when the chat leaves the list, i.e. was answered.
Silent 22:00-08:00; what happened at night is in the morning report.

**Customer file (4.3).** Telegram's own name/username are stored on every customer message
(one upsert, errors swallowed — bookkeeping is not the reply path). `/mijozlar` lists, and the
CSV export uses **`core/csv_fayl.py`** — the formula-injection escape moved there out of
`web/api.py` (which re-imports it under the old names), because a second copy is how one of
them would lose the escape.

⛔️ **Profile and story (4.4) change nothing without a tap.** `/biznes` → Bio / Ism / Rasm /
Story: the owner describes it, the bot prepares text (points) or an image (the existing
`generate_image` path — Pro and the `images` counter, refunded if nothing was drawn), shows it,
and **only `_tasdiqla()`** writes to Telegram. The pending item lives in RAM for an hour (a deploy
means asking again); a stranger's tap is refused without deleting the owner's item, and it is
single-use, so a double tap writes once. Telegram wants a **JPG** profile photo and a **1080x1920**
story, so `_jpeg()` re-encodes/crops. ⚠️ `InputStoryContentPhoto.photo` is typed `str` in aiogram,
so the story is built with `model_construct`; the session still turns the nested `InputFile`
into `attach://` (verified by preparing the request offline).

**Panel card (4.5).** Active connections, today's business requests, and business tokens as a
share of **today's total** tokens — `None`, not 0%, when nothing was measured. Tokens are
attributed through `services.ai.BIZNES_MANBA`, a `ContextVar` set by `_biznes_hisobida()`
around every business model call and written to `user_history.manba`. A ContextVar and not a
parameter: the call is three functions deep, and `asyncio.create_task` in `_log_token_usage`
copies the context, so the background write still sees it. SQL stays in `db/database.py`
(`biznes_panel_stats`, `::bigint` on both sums).

### Telegram Business: writing like the owner (phase 5)

All of it lives in **`handlers/biznes_uslub.py`** (SQL in `db/database.py`, `BIZNES_INSTRUCTIONS` in `services/ai.py` because it is the reply path). That module must not import `handlers.biznes` — `test_biznes_uslub.py` check 22.

⛔️ **The customer path does not use the assistant prompt.** With `biznes_yoriqnoma` set,
`get_openai_reply` / `get_vision_reply` send `services.ai.BIZNES_INSTRUCTIONS` (**293
tokens**) instead of `build_system_prompt()` (5 521): drafts written with the ChatGPT prompt
read like an assistant ("Qanday yordam bera olaman?", markdown) and nothing like the owner.
The role instruction and the "always use internet_search" time line are skipped there too.
`BIZNES_INSTRUCTIONS` is identical for every owner, so it stays cacheable; everything
per-owner is in the `developer` message. `test_biznes_uslub.py` checks 1-4.

**Where the style comes from.** `biznes_namuna` holds what the owner typed **themselves** in
business chats (plus the text they replaced a draft with). `chat_messages` cannot be used
for this: there `assistant` is the owner *and* what the bot sent for them, so the bot would
learn from itself. Commands, the bot's own echoes and customer text never become samples
(check 11); a sample with a card/passport number is dropped (`clean_biznes_namuna`), because
samples go into prompts for **other** customers. `biznes_uslub.uslub_bloki()` sends the owner's own rules
(`uslub_egasi`, from «Uslubim») > the learned description (`uslub`) > the last
`BIZNES_NAMUNA_KORSAT` samples > the last `BIZNES_TAHRIR_KORSAT` edit pairs from
`biznes_loyiha` (`tahrirlandi`) — at most **~760 tokens**, so a draft is still ~4 400 tokens
cheaper than before. `.javob` uses the same path; `.en`/`.tarjima`/`.xulosa` do not.

The description is one mini-model call (`biznes_uslub.model_organ`) after
`BIZNES_USLUB_ORGAN[0]` (10) samples, then every `[1]` (30), counted by
`biznes_profil.namuna_jami`, which only grows (the sample table is trimmed). ⚠️ A failed call
still advances `uslub_jami` and keeps the old text, or every owner message during an OpenAI
outage would start a new call (check 14). `_organmoqda` makes two concurrent triggers one call.
Style lookup is decoration: `uslub_ol()` swallows DB errors, so a draft is written without style
rather than not at all.
