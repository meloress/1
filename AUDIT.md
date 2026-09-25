# AUDIT — Telegram Business yo'li (2026-09-25)

Faqat o'qish natijasi. Kodda **hech narsa optimallashtirilmagan**. Yagona o'zgarish — 2-bosqichdagi
o'lchov loglari (pastda, §9). Har bir taklif sizning tasdig'ingizdan keyin alohida kichik commit
va testi bilan kiritiladi.

Belgilar: **Ta'sir** — Y (yuqori) / O (o'rta) / P (past). **Xavf** — xulqni yoki natijani
o'zgartirish ehtimoli. ⚠️ **XAVFSIZLIK** — `owner_id` qoidasiga oid.

---

## 1. Bitta kiruvchi xabarning to'liq yo'li

### 1.1 Mijoz yozdi, rejim «Yordamchi» (asosiy yo'l)

| # | Qadam (funksiya) | DB so'rovlari | LLM |
|---|---|---|---|
| 1 | `biznes_xabar` → `_ulanish()` | 0 (RAM `_biznes_kesh`) | — |
| 2 | `biznes_kimdan()` | 0 | — |
| 3 | `database.pro_tarifmi(egasi)` | **1** (users + admins + superadmins) | — |
| 4 | `biznes_mijoz_korildi()` — kartoteka UPSERT | **1** | — |
| 5 | `_navbatga()` → debounce buferi, `TEXT_MERGE_WAIT` = **1,5 s** kutish | 0 | — |
| 6 | `_loyiha()` → chat qulfi `_loyiha_qulf[(chat, -egasi)]` | 0 | — |
| 7 | `get_maintenance_notice_for(egasi)` | **1** (bot_settings + admins) | — |
| 8 | `check_and_consume_quota()` — tranzaksiya, `FOR UPDATE` | **2–4** | — |
| 9 | `biznes_bilim_ol()` | **1** | — |
| 10 | `biznes_uslub.uslub_ol()` → `biznes_uslub_ol` — **ketma-ket 3 ta** SELECT | **3** | — |
| 11 | `get_openai_reply()` → xulosa + tarix (80 xabar) | 0 (RAM); jarayonda birinchi marta **2** | — |
| 12 | Responses API oqimi (`BIZNES_INSTRUCTIONS`, tool'siz) | — | **1** (odatda 1 raund) |
| 13 | `_log_token_usage` → `_token_saqla` (fon) | **1** (fon) | — |
| 14 | `safe_update_history(user)` → INSERT + `COUNT(*)` | **2** | — |
| 15 | `biznes_loyiha_yarat()` — tranzaksiya: UPDATE + INSERT + **global DELETE** | **3** | — |
| 16 | `_loyiha_korsat()` → `_dm_yubor()` → `biznes_mavzusi()` | 0 (RAM); birinchi marta **1–2** | — |
| 17 | `track_user_activity()` — save_user + log_user_activity (fon) | **2** (fon) | — |

**Jami:** ~**17–20 DB round-trip** (LLM'dan oldin kritik yo'lda **~9 ta ketma-ket**) + **1 LLM chaqiruvi**.
Kutish vaqtining asosiy qismi 1,5 s debounce va LLM; DB ~9 × (1–5 ms) — ikkinchi darajali.

Shartli, fon chaqiruvlari:
- tarix siqish: chatda 100+ qator bo'lsa, har 20 xabarda **+1 mini LLM**;
- mavzu nomlash business'da ishlamaydi (`thread_id < 0`).

**Embedding chaqiruvlari yo'q** — kodda embedding umuman ishlatilmaydi.

### 1.2 Boshqa tarmoqlar

| Holat | DB (taxm.) | LLM |
|---|---|---|
| Mijoz, «Kuzatuv» | 3 (pro, kartoteka) + 2 (tarix) | 0 |
| Mijoz, «Avtomat», matn | ~16 (1.1 + `biznes_chat_holati` + kunlik sanoq, `refund_daily` bo'lishi mumkin) | 1 |
| Mijoz, «Avtomat», ovoz | + fayl yuklash | + **1 STT** + 1 |
| Mijoz, «Avtomat», rasm | + fayl yuklash | 1 vision |
| Mijoz, stiker / matnsiz media | 3 | **0** (`if not matn: return`) ✅ |
| Egasi oddiy xabar | eskirt/pauza 1 + pro 1 + namuna 3 + tarix 2 = **~7** | 0; 10-, 40-, 70-… namunada **+1 mini** (uslub) |
| Egasi `.buyruq` | ta'til 1 + pro 1 + kvota 2–4 + (`.javob`: uslub 3) + tarix 2 | 1 |
| Bot o'z xabari qaytdi | 0 | 0 ✅ |
| Kunlik hisobot | har egaga ~6 | 1 mini |

---

## 2. Ketma-ket, lekin parallel bo'lishi mumkin

| # | Joy | Hozir | Taklif | Ta'sir | Yutuq | Xavf |
|---|---|---|---|---|---|---|
| 2.1 | `biznes_uslub_ol` | 3 SELECT bitta ulanishda ketma-ket | 1 so'rov (subselect'lar) yoki `gather` | O | −2 RTT har qoralamada | Past |
| 2.2 | `_loyiha`: bilim + uslub | ta'til → kvota → bilim → uslub | bilim ‖ uslub ‖ ta'til (o'qishlar); **kvota ta'tildan keyin qoladi** | O | −2…3 RTT | Past (kvota tartibi saqlanadi) |
| 2.3 | Egasi xabari: `namuna_saqla` → `organ()` | uslub o'rganish (**60 s gacha** LLM) **kutiladi**, egasining tarixi shundan keyin yoziladi | `organ()`ni fon vazifasiga olish | **Y** | Egasi javobi tarixga darhol tushadi | Past |
| 2.4 | `biznes_mijoz_korildi` | navbatdan oldin kutiladi | fon (xatosi baribir yutiladi) | P | −1 RTT (debounce ichida yashirin) | Past |
| 2.5 | Qoralamadan keyin: tarix INSERT ‖ `loyiha_yarat` | ketma-ket, qulf ichida | `gather` | P | −1…2 RTT | Past |

> 2.3 alohida muhim. 10-namunada egasining xabari o'rganish chaqiruvi tugaguncha tarixga
> yozilmaydi. Shu oraliqda mijoz yozsa, qoralama egasining oxirgi javobini ko'rmaydi.

---

## 3. Har xabarda qayta hisoblanadi, lekin keshlanishi mumkin

| # | Nima | Qanchalik tez-tez | Taklif | Ta'sir | Yutuq | Xavf |
|---|---|---|---|---|---|---|
| 3.1 | `pro_tarifmi(egasi)` | **har** business xabarda (egasi ham) | 60 s TTL RAM kesh | O | −1 RTT/xabar | Past: tarif tugashi ≤60 s kechikadi, haqiqiy darvoza — kvota |
| 3.2 | `biznes_uslub_ol` (3 so'rov) | har qoralama/avtojavob/`.javob` | egasi bo'yicha RAM, yozuvda bekor qilinadi (`namuna_qosh`, `uslub_yoz`, `egasi_yoz`, `namunalar_ochir`, tahrir) | O | −3 RTT | O'rta: bekor qilishni unutish = eski uslub |
| 3.3 | `biznes_bilim_ol` | har qoralama | RAM, `biznes_bilim_yoz`da yangilanadi (bitta jarayon — CLAUDE.md dagi naqsh) | P | −1 RTT | Past |
| 3.4 | `get_maintenance_notice_for` | har qoralama/buyruq | `bot_settings` RAM keshi | P | −1 RTT | Past |
| 3.5 | `biznes_mijoz_korildi` UPSERT | har mijoz xabari | ism o'zgarmagan bo'lsa ≤10 daqiqada o'tkazib yuborish | P | −1 yozuv/xabar | Past |
| 3.6 | `update_chat_history` → `COUNT(*)` | har tarix yozuvida | RAM'dagi son (kesh allaqachon ro'yxatni tutadi) | P | −1 RTT | Past; `test_topic_nom` shu songa tayanadi |

---

## 4. Keraksiz LLM chaqiruvlari

| # | Holat | Hozir | Taklif | Ta'sir | Yutuq | Xavf |
|---|---|---|---|---|---|---|
| 4.1 | Stiker, matnsiz media | LLM **yo'q** ✅ | — | — | — | — |
| 4.2 | "ok", "rahmat", "👍", "+" (Yordamchi) | to'liq qoralama: **~1,5–8k token** | qisqa minnatdorchilik/tasdiq uchun qoralama yozilmasin | O | tokenning ~10–20% i (o'lchanmagan — §9 dan keyin) | **O'rta — xulq o'zgaradi**: egasi bunday xabarga qoralama olmaydi. Sizning qaroringiz |
| 4.3 | Avtomatda "rahmat" | avtojavob | tegmaslik yoki qat'iy ro'yxat | P | — | Avtomatda javob kutiladi |
| 4.4 | Debounce oralig'idan (1,5 s) keyin ketma-ket xabarlar | har biriga yangi qoralama, oldingisi `eskirgan` → ikki marta to'lanadi | business uchun kattaroq oyna (3–5 s) | O | ketma-ket yozadigan mijozlarda ~30–50% | O'rta: qoralama 2–3 s kechroq |
| 4.5 | Egasi o'zi faol yozishayotgan chat | qoralama yoziladi va darhol `eskirgan` bo'ladi | egasi ≤N daqiqa oldin yozgan bo'lsa qoralama yozilmasin | O | `eskirgan` ulushicha (o'lchanadi) | **O'rta — xulq**. Qaror sizniki |

---

## 5. Prompt tuzilishi va prompt caching

Mijoz yo'lida modelga ketadigan tartib (`get_openai_reply`, `biznes_yoriqnoma` bilan):

```
instructions : BIZNES_INSTRUCTIONS            — statik, 293 token       ✅ hamma uchun bir xil
input[0]     : developer "Hozir: YYYY-MM-DD HH:MM" — HAR DAQIQA o'zgaradi ❌
input[1]     : developer xulosa (bo'lsa)
input[2..]   : tarix — 80 tagacha xabar            (append-only)
input[n-1]   : developer yo'riqnoma: qoidalar + bilim + uslub  — egasiga xos, ~0,5–2,7k
input[n]     : user xabar
```

| # | Muammo | Ta'sir | Taklif | Yutuq | Xavf |
|---|---|---|---|---|---|
| 5.1 | Statik qism 293 token — OpenAI keshining **1 024 token** minimumidan kichik. Undan keyingi birinchi element daqiqa aniqligidagi vaqt, shuning uchun keshlanadigan prefiks **amalda 0** (jonli logda: `keshdan 0 = 0%`) | **Y** (pul va TTFT) | Tartib: instructions → **egasi yo'riqnomasi** → xulosa → tarix → **vaqt + user** | Egasining barcha mijozlari uchun ~0,5–3k prefiks keshdan; bitta chat ichida tarix ham | **O'rta**: qoidalar tarixdan oldinga o'tadi, "yaqinlik" og'irligi kamayadi. `tahrirsiz` ulushi bilan A/B o'lchash shart |
| 5.2 | `prompt_cache_key` = `…-pro`: business so'rovlari oddiy Pro DM trafigi bilan bitta kalitda, prefikslari esa boshqa | O | `…-biznes-<egasi>` | kesh urilishi barqarorroq | Past |
| 5.3 | Tarix oynasi: `is_pro=True` → **80 xabar** (`CONTEXT_WINDOW_PRO`) | **Y** (token) | business uchun alohida kichikroq oyna (masalan 30) | uzun chatlarda −50%+ kirish tokeni | **O'rta — natija o'zgaradi** (kontekst qisqaradi). Qaror sizniki |

⚠️ **Muhim eslatma (CLAUDE.md, OpenAI javobi, 2026-09-09):** kesh **bepul kunlik grantni
kamaytirmaydi** — keshlangan token ham to'liq hisoblanadi. 5.1–5.2 faqat grantdan oshgan qismning
pulini va kechikishni kamaytiradi. Grantni faqat **kamroq token** (5.3, 4.x) tejaydi.

---

## 6. DB: indekslar, N+1, `owner_id` filtri

### 6.1 ⚠️ XAVFSIZLIK — `owner_id` filtri yo'q so'rovlar

| # | Funksiya | So'rov | Hozirgi himoya | Baho | Taklif |
|---|---|---|---|---|---|
| **S1** | `biznes_loyiha_yakun(loyiha_id, holat, yakuniy)` | `UPDATE biznes_loyiha … WHERE id = $1` — **egasi tekshirilmaydi** | Chaqiruvchilar id'ni faqat egasi tekshirilgan `biznes_loyiha_band()` natijasidan oladi | **Qoida buzilishi.** Hozir ekspluatatsiya qilib bo'lmaydi, lekin keyingi chaqiruvchi xom id uzatsa, begona loyiha yoziladi | `AND owner_id = $N` qo'shish, chaqiruvchilar `egasi` uzatadi |
| **S2** | `biznes_loyiha_yarat` ichidagi tozalash | `DELETE FROM biznes_loyiha WHERE yaratilgan < NOW() - 30 kun` — **barcha egalar** | Ataylab saqlash muddati, foydalanuvchi kiritmasi yo'q | Xavfsizlik emas, lekin egasi so'rovi ichida **global** yozuv; indeks yo'q → har qoralamada to'liq skan | Kunlik watcher'ga ko'chirish |
| S3 | `db/history.py::clear_user_history(chat_id)` → `thread_id=None` | mijoz `chat_id` si bo'yicha **barcha** mavzular, jumladan **hamma egalarning** business tarixi (`thread_id<0`) | Hozir **hech qayerda chaqirilmaydi** | Yashirin mina | `thread_id >= 0` sharti yoki funksiyani olib tashlash |
| S4 | `chat_messages` / `chat_summaries` business qatorlari | `WHERE chat_id = $1 AND thread_id = $2`, bunda `thread_id = -owner_id` | Egasi kalitning **ichida** | Qoida bajarilgan, lekin **bilvosita** | Hujjatlashtirish (BIZNES.md); alohida `owner_id` ustuni shart emas |

Qolgan hamma `biznes_*` so'rovlari `owner_id` bo'yicha filtrlangan. Tekshirilganlar:
`bilim_*`, `uslub_*`, `namuna_*`, `mavzu_*`, `loyiha_band/eskirt`, `chat_*`, `mijoz_*`, `hisobot_band`,
`kun_hisobi` (thread orqali), `javobsizlar` (JOIN `owner_id = -thread_id`).

Callback'lar ham `query.from_user.id` bo'yicha tekshirilgan:
- `bz:y/b/t` → `band(lid, uid)`;
- `bz:o/a`, `_tasdiqla` va CSV — `uid` bo'yicha.

Global o'qishlar faqat admin panel (`biznes_panel_stats`) va ishga tushishdagi kesh yuklashda — ataylab.

### 6.2 Indekslar

| # | So'rov | Muammo | Taklif | Ta'sir | Xavf |
|---|---|---|---|---|---|
| 6.2.1 | `biznes_chatlar` (`/biznes` → Chatlar), `biznes_kun_hisobi` (hisobot) | `WHERE thread_id = $1` — mavjud indeks `(chat_id, thread_id, id)` thread bo'yicha boshlanmaydi. Qisman indeks `(created_at) WHERE thread_id < 0` esa `$1` parametr bo'lgani uchun kafolatli ishlatilmaydi (generic plan `$1 < 0` ni isbotlay olmaydi; `EXPLAIN` bilan tasdiqlanmagan — prod'ga faqat o'qish uchun ham kirmadim) | `(thread_id, id) WHERE thread_id < 0` (CONCURRENTLY, `indekslarni_qur`); `kun_hisobi`da sana oralig'i | **Y** (`chat_messages` hamma foydalanuvchilarning DM tarixini saqlaydi, ya'ni skan jadval bilan o'sadi) | Past |
| 6.2.2 | `biznes_loyiha`: `(owner_id, chat_id, holat)`, `(owner_id, holat, id)`, `yaratilgan` | PK'dan boshqa indeks yo'q | `(owner_id, chat_id) WHERE holat='kutmoqda'`, `(owner_id, id)` | O (30 kunlik jadval, hozir kichik) | Past |
| 6.2.3 | `biznes_namuna` | `(owner_id, id DESC)` bor ✅ | — | — | — |

### 6.3 N+1

| # | Joy | Tafsilot | Taklif | Ta'sir |
|---|---|---|---|---|
| 6.3.1 | `javobsiz_tekshir()` | 50 tagacha qator, har biriga `pro_tarifmi()` | egalar bo'yicha bitta so'rov yoki 3.1 keshi | P (har 5 daqiqada) |
| 6.3.2 | `biznes_hisobot_watcher` | har egaga ketma-ket ~6 so'rov + LLM | egalar ko'payganda — cheklangan `gather` | P (kuniga bir marta) |
| 6.3.3 | `biznes_chatlar` | 10 chatning har biriga korrelyatsiyali subselect | LATERAL yoki 6.2.1 indeksi | P |

---

## 7. Dublikat update, Telegram 429, LLM timeout

| # | Holat | Hozir nima bo'ladi | Ta'sir | Taklif | Xavf |
|---|---|---|---|---|---|
| 7.1 | **Dublikat update** (deploy paytida eski jarayon update'ni olgan, offsetni tasdiqlamay o'lgan) | **Himoya yo'q.** Avtomatda mijozga **ikki javob** ketishi mumkin. `.javob` ikki marta yuboriladi va ikki marta to'lanadi. Namuna va tarix ikki marta yoziladi | **O** | `(conn_id, chat_id, message_id)` bo'yicha dedup — RAM (TTL) + avtomat uchun bazada atomik belgi (qayta ishga tushishdan omon qoladi) | Past |
| 7.2 | **429 (`TelegramRetryAfter`)** egasiga yuborishda | Qayta urinilmaydi. `_egasiga` → `False`, qoralama bazada `kutmoqda`, lekin egasi uni **hech qachon ko'rmaydi**, ball qaytarilmaydi | O | `retry_after` ni bir marta kutib qayta yuborish (egasi DM'i) | Past |
| 7.3 | 429 mijozga (avtomat) | Ball qaytariladi, egasiga soatiga bitta xato ✅ | — | `retry_after` ≤ 5 s bo'lsa bir marta qayta urinish | Past |
| 7.4 | **LLM timeout / xato** (Yordamchi) | Fallback modellar, 429 uchun bitta qayta urinish, 180 s idle timeout (`get_openai_reply`). Xatoda ball qaytariladi, lekin egasiga **hech narsa aytilmaydi** | O | egasiga bitta "qoralama yozilmadi" xabari (soatiga bir) | Past (yangi xabar) |
| 7.5 | Uzoq LLM + chat qulfi | Qulf model tugaguncha ushlanadi, keyingi mijoz xabarlari 180 s+ gacha kutadi | P | qoralama uchun umumiy timeout (masalan 60 s) | O'rta |
| 7.6 | 🐞 **Poyga: egasi qoralama yozilayotganda javob berdi** | `eskirt` hali mavjud bo'lmagan qoralamaga ishlaydi, keyin yangi qoralama `kutmoqda` bo'lib keladi — egasi **eskirgan javobni yuborishi mumkin**. Bundan tashqari mijoz xabari tarixga modeldan KEYIN yozilgani uchun tarixda savol egasining javobidan keyin tushadi | **O** (to'g'rilik) | `loyiha_yarat`dan oldin: "egasi shu chatga model boshlangandan keyin yozdimi?" → qoralamani darhol `eskirgan` qilish | Past |

Xotira (RAM) o'sishi: `_loyiha_qulf`, `_mavzu_qulf`, `text_merge_locks`, `_aytilgan`, `db/history._cache` —
hech biri kesilmaydi. Hozirgi hajmda sezilmaydi (**P**). Egalar va mijozlar ko'paysa — LRU.

---

## 8. Ustuvor ro'yxat (tavsiya etilgan tartib)

| Tartib | Band | Nima | Ta'sir | Xavf | Xulqni o'zgartiradimi |
|---|---|---|---|---|---|
| 1 | **S1** | `biznes_loyiha_yakun` ga `owner_id` | Xavfsizlik | Past | Yo'q |
| 2 | 7.6 | Egasi yozgan bo'lsa yangi qoralama darhol eskiradi | Y (to'g'rilik) | Past | Faqat bugni tuzatadi |
| 3 | 2.3 | Uslub o'rganish — fon vazifasi | Y | Past | Yo'q |
| 4 | 6.2.1 | business tarixi uchun qisman indeks | Y (o'sish) | Past | Yo'q |
| 5 | 7.1 | Dublikat update himoyasi | O | Past | Yo'q |
| 6 | 2.1–2.2, 3.1–3.4 | Parallel o'qishlar + RAM keshlar | O | Past–O'rta | Yo'q |
| 7 | 7.2, 7.4 | 429 qayta urinish, egasiga "yozilmadi" xabari | O | Past | Kichik (yangi xabar) |
| 8 | S2, S3, 6.2.2 | Tozalash watcher'ga, `clear_user_history`, `biznes_loyiha` indekslari | P–O | Past | Yo'q |
| 9 | 5.1–5.2 | Prompt tartibi + business cache key | Y (pul/TTFT) | O'rta | Ehtimol — A/B kerak |
| 10 | 4.2, 4.4, 4.5, 5.3 | "ok/rahmat", debounce, faol chat, tarix oynasi | Y (token) | O'rta | **Ha** — alohida qaror |

1–8-bandlar "natijani emas, tezlik va narxni" o'zgartiradi (7.6 — bug tuzatish).
9–10-bandlar natijaga ta'sir qilishi mumkin — ularni §9 dagi o'lchovlardan keyin va sizning
qaroringiz bilan qilish kerak.

---

## 9. 2-bosqich: o'lchov (kiritildi)

`core/olchov.py` — har bir Business oqimi oxirida **bitta** strukturali JSON qator:

```
OLCHOV {"oqim":"loyiha","id":"1bb3f6a9","jami_ms":2140,
        "bosqichlar":{"qulf":0,"tatil":3,"kvota":9,"bilim_uslub":6,"model":2080,
                      "tarix":5,"loyiha_yarat":7,"egasiga":30},
        "llm":1,"kirish":3120,"keshdan":0,"chiqish":42,"model":"gpt-5.6-luna",
        "ttft_ms":830,"kutish_ms":1520,"qismlar":2,"chat":9002,"egasi":7001,"natija":"tugadi"}
```

| Oqim | Qayerda | Bosqichlar |
|---|---|---|
| `xabar` | `biznes_xabar` (har business update) | ulanish, egasi_holati, pro, namuna, kartoteka, tarix; `kim`, `rejim`, `turi`, `belgi_soni`, `natija` |
| `loyiha` | `_loyiha` (qoralama) | qulf, tatil, kvota, bilim_uslub, model, tarix, loyiha_yarat, egasiga; `kutish_ms` (debounce + navbat), `ttft_ms` |
| `avtojavob` | `_avtojavob` | qulf, toxtash, sanoq, bilim_uslub, model, yuborish, tarix |
| `ovoz` | `_avto_ovoz` | (STT; ichida `avtojavob` alohida qator) |
| `buyruq` | `_bajar` | tekshiruv, kvota, ochirish, model, yuborish |
| `yuborish` | `loyihani_yubor` (egasi tugmani bosdi) | jami |
| `uslub_organ` | `biznes_uslub.organ` | jami + mini-LLM tokenlari |
| `hisobot` | `_hisobot` | hisob, model |

- **`id`** — korrelyatsiya: `xabar` va u keltirib chiqargan `loyiha`/`avtojavob` bir xil `id` oladi.
- **Tokenlar** `services.ai._log_token_usage` dan joriy oqimga qo'shiladi. Ichma-ich oqim o'zinikini oladi.
- **Narx** logga yozilmaydi: model narxlari kodda yo'q (bepul grant + ortig'i billing). Pulni
  tokenlardan tashqarida hisoblash to'g'riroq.

**Logga tushmaydi (qat'iy):**
- xabar matni, model javobi, bilim, uslub, API kalit;
- `yoz()` satrni faqat ≤32 belgi va bir qatorli bo'lsa o'tkazadi, qolganini `null` qiladi;
- `tests/test_olchov.py` 9-tekshiruvi `olchov.qosh/yoz` ga matn o'zgaruvchisi (`matn`, `javob`,
  `bilim`, …) berilsa yiqiladi — mutatsiya bilan tekshirilgan.

**Xulqqa ta'sir yo'q:**
- dekorator istisnoni o'zgarishsiz qayta ko'taradi (test 1–3);
- oqimdan tashqarida (oddiy DM trafigi) hamma chaqiruv jim (test 6);
- o'ralgan `biznes_xabar` imzosi aiogram uchun o'zgarmagan (test 8);
- `_loyiha`/`_avtojavob` da `bilim`/`uslub` o'qishlari o'lchov uchun alohida qatorlarga
  ajratildi — tartib (bilim → uslub → model) va `try` chegarasi aynan o'sha.

**O'qish:**
```bash
timeout 60 railway logs | grep -o 'OLCHOV .*' | sed 's/^OLCHOV //' > olchov.jsonl
# masalan: qoralama bosqichlari o'rtachasi, TTFT, token
```
