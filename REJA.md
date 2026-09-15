# Web admin panel — to'liq reja

Oldingi reja (admin panelni tuzatish, to'ldirish va fayllarga bo'lish)
**to'liq bajarildi**: 12 tugmali klaviatura 4 taga yig'ildi, audit /
xatolar / daromad / limitlar ekranlari qo'shildi, `handlers/admin.py`
(2671 qator) paketga bo'lindi, kunlik hisobot ishga tushdi. Qoldiqlari
`CLAUDE.md` dagi «The admin panel is a package» bo'limida qoida bo'lib
yozilgan. Bu fayl endi **web panel** uchun.

**Qaror:** admin paneli Telegram klaviaturasidan Mini App'ga ko'chadi.
Tarqatma botda qoladi. Sabablari 1-bo'limda.

---

## 1. Nega

Uchta sabab, muhimlik bo'yicha:

1. **Mavzular (topic) rejimi klaviaturani buzdi.** Rejim yoqilganda chat
   mavzular ro'yxatiga aylanadi va admin har tugma bosganda Telegram
   yangi mavzu ochadi. Bu sozlama **bot bo'yicha global** — «foydalanuvchiga
   mavzu bo'lsin, adminga bo'lmasin» degan API yo'q. Panel Telegram
   klaviaturasida turar ekan, mavzular va admin paneli bir vaqtda
   ishlay olmaydi.
2. **Klaviatura ekranga sig'maydi.** 14 ta ekran 4 ta tugma + inline
   menyularga tiqilgan. Jadval, saralash, qidiruv, grafik — Telegram
   xabarida yo'q narsalar.
3. **Mantiq allaqachon ajratilgan.** `handlers/admin/` — 3724 qator,
   lekin deyarli hammasi `db/database.py` funksiyalarini chaqiradi. Xom
   SQL faqat ikki faylda: `stats.py` (11 ta) va `system.py` (4 ta).
   Ya'ni web panel yangi mantiq emas, yangi **ko'rinish** yozadi.

---

## 2. Nima botda qoladi

| Nima | Nega |
|---|---|
| 🎁 Promokod/referal **yuborish** (`/kod`) | Xuddi tarqatma kabi: `send_promo_gift()` tayyor tugmali xabar jo'natadi, `send_referral_invite()` esa har kimga o'zining shaxsiy havolasini yasaydi. Kod YARATISH esa panelda. |
| 📢 Tarqatma (`/xabar`) | `copy_message` bilan ishlaydi — admin botga nima yuborsa, odamlarga **aynan o'sha** yetadi (albom, formatlash, premium emoji). Webda qayta yig'ilgan xabar buni yo'qotadi. `/xabar` buyrug'i bilan boshlanadi. |
| 📨 «Adminga xabar» (report) | Foydalanuvchi botga yozadi, bot adminlarga yetkazadi. Javob ham botdan ketadi. |
| ⏰ Kunlik hisobot | Push — panelga kirmasdan keladi, o'z ma'nosi shunda. |
| 💳 To'lov handlerlari | `successful_payment` / `pre_checkout_query` — `main.py` dagi tartib qoidasi (routerdan oldin) tegilmaydi. |
| 👁 Kuzatuv nusxalari | Sozlama webda, uzatishning o'zi botda. |

Qolgan **hamma narsa** webga ko'chadi.

---

## 3. Arxitektura qarorlari

### 3.1 Panel bot jarayonining ICHIDA

Alohida Railway service emas. Sabablari:

- **RAM keshlari.** `config.apply_limit_overrides()` va
  `database.load_watch_cache()` — limit yoki kuzatuv o'zgarganda RAM
  keshi yangilanishi shart. Alohida jarayonda bu imkonsiz: web bazaga
  yozadi, bot esa eski qiymat bilan ishlashda davom etadi. Buni tuzatish
  uchun jarayonlararo signal kerak bo'lardi — ortiqcha murakkablik.
- **Bitta token, bitta `DATABASE_URL`.** Ikki servicega ko'chirish —
  sirni ikki joyda saqlash.
- **Trafik bitta odam.** Izolyatsiya uchun to'lanadigan narxning
  qaytimi yo'q.

`aiohttp` allaqachon `requirements.txt` da (aiogram uni ishlatadi), ya'ni
**yangi bog'liqlik 0 ta**. Server `main()` ichida `asyncio.create_task`
bilan ko'tariladi, polling bilan yonma-yon ishlaydi.

⚠️ Panel botni yiqitmasligi kerak: har route `@web.middleware` ichidagi
umumiy `try/except` bilan o'raladi, xato JSON bo'lib qaytadi va
`logger.exception` ga yoziladi.

### 3.2 Fayl tuzilmasi

```
web/
  __init__.py        — start_web_server(): aiohttp app, PORT, middleware
  auth.py            — initData tekshiruvi, cookie imzolash/o'qish, @admin_only
  api.py             — barcha JSON endpointlar (faqat db chaqiruvlari)
  static/
    panel.html       — bitta sahifa (artifactdagi maket asosida)
    panel.css
    panel.js
    logo.jpg         — BOT LOGOSI (pastga qarang)
services/menu.py     — sync_menu_button() qo'shiladi (mavjud fayl)
```

### 3.2.1 Logotip — bitta nusxa, bitta manzil

**Panelda logo kerak bo'lgan HAR JOYDA `/static/logo.jpg` ishlatiladi.**
Asl fayl loyiha ildizida (`logo.jpg`), web nusxasi
`web/static/logo.jpg` — aynan shu nusxa serverdan beriladi. Boshqa
rasm, boshqa yo'l yoki tashqi havola qo'shilmaydi: keyingi bosqichlarda
(sarlavha, yuklanish ekrani, bo'sh holat kartochkalari) hammasi shu
bitta manzilga murojaat qiladi.

Logo o'zgarsa: ildizdagi `logo.jpg` almashtiriladi va
`web/static/logo.jpg` ga qayta ko'chiriladi — koddagi hech narsa
o'zgarmaydi.

Handler mantiqi `web/api.py` ga **ko'chirilmaydi** — u `db/database.py`
funksiyalarini to'g'ridan-to'g'ri chaqiradi. `stats.py` dagi 11 ta xom
SQL esa `db/database.py` ga ikkita yangi funksiya bo'lib ko'chadi
(`activity_stats()`, `top_users()`) — shunda Telegram ekrani ham, web
ham bitta manbadan o'qiydi.

### 3.3 Railway

Service `1` ga domen biriktiriladi (Settings → Networking → Generate
Domain). Railway `PORT` ni env orqali beradi; server aynan shundan
o'qiydi, qotirilgan port yo'q. Domen `https://` bo'ladi — Mini App
uchun shart.

---

## 4. Xavfsizlik modeli

Uch qatlam. Har biri mustaqil; biri buzilsa qolganlari ushlab turadi.

### 4.1 Ko'rinish — ko'k tugma faqat adminda

`setChatMenuButton` **`chat_id` qabul qiladi**, ya'ni tugma har chatga
alohida qo'yiladi (aiogram 3.31 da tekshirilgan). Bu naqsh loyihada
allaqachon bor: `services/menu.py` Pro buyruqlarini `BotCommandScopeChat`
bilan aynan shunday qo'yadi.

- adminda → `MenuButtonWebApp(text="Panel", web_app=WebAppInfo(url=...))`
- qolganlarda → `MenuButtonDefault()` (hozirgi «/» ro'yxati)

Qachon qo'yiladi: `/start` da, admin qo'shilganda, bot ishga tushganda.
Qachon olinadi: admin ro'yxatdan chiqarilganda — **o'sha zahoti**.

⚠️ Bu qatlam — **bezak, darvoza emas**. `services/menu.py` boshidagi
ogohlantirish shu yerda ham amal qiladi: havolani qo'lda ochish mumkin,
shuning uchun haqiqiy tekshiruv pastda.

### 4.2 Imzo — `initData`

Mini App ochilganda Telegram `initData` beradi: foydalanuvchi ma'lumoti
+ `auth_date` + bot tokeni bilan qilingan HMAC-SHA256. Soxtalashtirib
bo'lmaydi.

aiogram'da tayyor: `aiogram.utils.web_app.safe_parse_webapp_init_data`.
Yangi kutubxona kerak emas.

```
POST /api/session   { init_data }
  → safe_parse_webapp_init_data(BOT_TOKEN, init_data)   # imzo
  → auth_date 5 daqiqadan eski bo'lsa rad               # qayta ishlatishga qarshi
  → is_admin(user.id)                                   # huquq
  → Set-Cookie: sid=<imzolangan>; HttpOnly; Secure; SameSite=Lax; Max-Age=12h
```

Cookie ichida faqat `user_id` + muddat + HMAC imzosi (kalit —
`BOT_TOKEN` dan olingan hosila). Sessiya jadvali kerak emas.

### 4.3 Huquq — HAR so'rovda

`@admin_only` dekoratori har bir `/api/*` so'rovda cookie'ni ochadi va
**`is_admin()` ni qaytadan chaqiradi** (keshlanmaydi). Adminlikdan
chiqarilgan odam keyingi so'rovidayoq yopiladi — 12 soatlik sessiya
kutilmaydi.

Qo'shimcha qoidalar:

- Admin qo'shish/o'chirish — faqat superadmin (`is_superadmin`,
  `_check_can_remove_admin` mantiqi saqlanadi).
- Har **yozuv** amali `log_admin_action()` ga tushadi: kim, nima, kimga.
- `POST /api/session` ga soddagina chastota chegarasi (IP bo'yicha
  daqiqada 10 ta) — imzoni brute-force qilishga urinish uchun.
- Token faqat HMAC uchun ishlatiladi; web hech qachon Telegram API'ga
  murojaat qilmaydi (yuborish kerak bo'lsa — botning o'z funksiyasi
  chaqiriladi, bitta jarayon).

---

## 5. Endpointlar

Hammasi JSON. Har biri `@admin_only`.

### Umumiy

| Metod | Yo'l | Nimadan o'qiydi |
|---|---|---|
| POST | `/api/session` | `safe_parse_webapp_init_data`, `is_admin` |
| GET | `/api/overview` | `daily_report_stats`, `revenue_stats`, `error_summary`, `get_maintenance` |

### Foydalanuvchilar

| Metod | Yo'l | Funksiya |
|---|---|---|
| GET | `/api/users?q=&filter=&page=` | `search_users` / `get_all_users`, `get_users_count` |
| GET | `/api/users/{id}` | `get_full_user_profile`, `get_user_payments`, `get_referral_progress` |
| POST | `/api/users/{id}/premium` | `set_user_premium` |
| POST | `/api/users/{id}/plan` | `set_user_plan` |
| POST | `/api/users/{id}/quota` | `reset_user_quota` |
| POST | `/api/users/{id}/ban` | `ban_user` / `unban_user` |
| POST | `/api/payments/{id}/refund` | `get_payment_by_id` + `mark_payment_refunded` |

### Statistika

| Metod | Yo'l | Funksiya |
|---|---|---|
| GET | `/api/stats` | **yangi** `activity_stats()`, `top_users()` (hozir `stats.py` dagi xom SQL) |

### Jurnal

| Metod | Yo'l | Funksiya |
|---|---|---|
| GET | `/api/journal/audit?page=` | `get_admin_audit`, `count_admin_audit` |
| GET | `/api/journal/errors` | `recent_errors`, `error_summary` |
| GET | `/api/journal/revenue` | `revenue_stats` |
| GET | `/api/journal/inactive` | `inactive_users`, `count_inactive_users` |

### Sozlamalar

| Metod | Yo'l | Funksiya |
|---|---|---|
| GET/POST | `/api/limits` | `get_limit_overrides`, `set_limit_override` **+ `config.apply_limit_overrides()`** |
| GET/POST | `/api/maintenance` | `get_maintenance`, `set_maintenance` |
| GET | `/api/watch` | `get_watchlist`, `get_watch_group_id` |
| POST | `/api/watch` | `add_watch`, `remove_watch`, `set_watch_group_id` **+ `load_watch_cache()`** |
| GET | `/api/admins` | `get_admins`, `get_admin_meta`, `is_superadmin` |
| POST | `/api/admins` | `add_admin`, `remove_admin` **+ menyu tugmasini sinxronlash** |

⚠️ Qalin qilib belgilangan uch joy — **RAM keshini yangilash**. Unutilsa
panel «o'zgardi» deb ko'rsatadi, bot esa eski qiymat bilan ishlaydi. Bu
3.1 dagi «bir jarayon» qarorining sababi.

### Promo va sovg'a

| Metod | Yo'l | Funksiya |
|---|---|---|
| GET | `/api/promo` | `list_promo_codes` |
| POST | `/api/promo` | `create_promo_code`, `revoke_promo_code` |
| GET | `/api/giveaway` | `giveaway_stats` |
| POST | `/api/giveaway` | `set_user_premium` + botdan xabar yuborish |
| GET/POST | `/api/referral` | `get_referral_config`, `set_referral_config`, `clear_referral_config` |

### Tarqatma (faqat ko'rish)

| Metod | Yo'l | Funksiya |
|---|---|---|
| GET | `/api/broadcasts` | `list_scheduled_broadcasts` |
| DELETE | `/api/broadcasts/{id}` | `cancel_scheduled_broadcast` |

---

## 6. Ekranlar

Maket tasdiqlangan (artifact). Har ekran — bitta `section`, ichida
sub-tablar.

### 6.1 Boshqaruv
KPI: bugungi so'rovlar, faol (7 kun), Pro obunachilar, bugungi daromad.
7 kunlik so'rovlar grafigi (hover bilan). Bugungi token sarfi grantga
nisbatan. So'rov turlari bo'yicha ustunlar. Oxirgi 4 ta xato.

### 6.2 Foydalanuvchilar
Qidiruv (ism, @username, ID), filtr (hammasi / Pro / bepul /
bloklangan), sahifalangan jadval. Qator bosilganda kartochka:

- Ballar, kunlik sanoqlar (fayl, rasm, tadqiqot), ro'yxatdan o'tgan
  sana, jami so'rov, referal holati
- Amallar: Pro berish (7/30/365 kun), tarifni o'zgartirish, kvotani
  tiklash, bloklash/ochish, xabar yozish
- To'lovlar jadvali + qaytarish

### 6.3 Statistika
Faol foydalanuvchilar (top 10), tarif taqsimoti, so'rov turlari,
xulosa ko'rsatkichlar (kunlik o'rtacha, konversiya).

### 6.4 Promo va sovg'a
Sub-tablar: **Promokodlar** (ro'yxat, yaratish, bekor qilish) ·
**Bepul Pro** (kimga, necha kun, tarix) · **Referal sharti** (nechta
do'st, necha kun, kimlarga).

### 6.5 Jurnal
Sub-tablar: **Audit** (sahifalangan, admin bo'yicha filtr) ·
**Xatolar** (tur, tafsilot, foydalanuvchi) · **Daromad** (oylik, o'rtacha
chek, qaytarilganlar, oxirgi to'lovlar) · **Nofaol userlar**.

### 6.6 Sozlamalar
Sub-tablar: **Limitlar** (bepul/Pro bo'yicha jadval, tahrirlash) ·
**Texnik ta'til** (kalitcha + matn + tizim holati) · **Kuzatish** (guruh
ID, ro'yxat) · **Adminlar** (ro'yxat, qo'shish, o'chirish).

### 6.7 Tarqatma
Nega botda qolgani tushuntiriladi + rejalashtirilganlar ro'yxati (bekor
qilish mumkin) + oxirgi tarqatma hisoboti.

---

## 7. Bosqichlar

Har bosqich alohida commit va deploy. «Tayyor» mezoni yozilgan.

### ✅ 1-bosqich — Skelet va darvoza  (BAJARILDI)
- `web/__init__.py`, `web/auth.py`, `main.py` ga ulash, Railway domeni
- `POST /api/session`, `@admin_only`, cookie
- `services/menu.py::sync_menu_button()` + `/start` va admin
  qo'shish/o'chirishga ulash
- Bo'sh panel: «Salom, Melores» + chiqish tugmasi

**Tayyor:** ko'k tugma faqat adminda chiqadi, bosilganda panel
ochiladi; admin bo'lmagan hisob havolani qo'lda ochsa `403`.

Nima qilindi:

- `web/auth.py` — `initData` imzosi (`safe_parse_webapp_init_data`) +
  **yosh tekshiruvi** (5 daqiqa; aiogram yoshni tekshirmaydi, ya'ni
  o'g'irlangan `initData` abadiy amal qilardi), cookie imzolash
  (`user_id.muddat.HMAC`, kalit — BOT_TOKEN dan **hosila**, tokenning
  o'zi emas), `@admin_only`, IP bo'yicha daqiqada 10 ta urinish.
- `web/__init__.py` — `build_app()` + `start_web_server()`, umumiy
  `try/except` middleware (paneldagi xato JSON bo'lib qaytadi va botga
  tegmaydi), `POST /api/session`, `GET /api/me`, `POST /api/logout`,
  `GET /` va `/static/`.
- `web/static/panel.{html,css,js}` — skelet (logo, «Salom, <ism>»,
  «Yopish»). Maket ranglari CSS o'zgaruvchilarida, 2-bosqich shular
  ustiga quriladi.
- `services/menu.py::sync_menu_button()` — `MenuButtonWebApp` /
  `MenuButtonDefault`, `sync_commands()` bilan bir xil kesh naqshi.
  Ulangan joylar: `/start` (**hamma uchun** — bot o'chiq turganda
  adminlikdan chiqarilgan odamning tugmasi shunda o'zi yo'qoladi),
  `process_add_admin`, `remove_admin_callback`, `process_remove_admin`.
- `core/config.py::WEB_APP_URL` — `WEB_APP_URL` env, bo'lmasa
  `https://$RAILWAY_PUBLIC_DOMAIN`. **Bo'sh bo'lsa tugma umuman
  qo'yilmaydi** va bot xatosiz ishlashda davom etadi.
- `main.py` — `await start_web_server()` fon vazifalaridan keyin,
  `try/except` ichida: panel ko'tarilmasa bot panelsiz davom etadi.
- `tests/test_web_auth.py` — 6 ta tekshiruv, tarmoqsiz va bazasiz
  (`huquq_bormi` almashtiriladi, `aiohttp.test_utils` ishlatiladi).

⚠️ **Railway'da qolgan qo'l ishi:** Settings → Networking → Generate
Domain. Domensiz `RAILWAY_PUBLIC_DOMAIN` bo'sh bo'ladi va ko'k tugma
chiqmaydi (panelning o'zi baribir ishlaydi, faqat havola orqali).

### ✅ 2-bosqich — Dizayn asosi  (BAJARILDI)
- `panel.html/css/js` maketdan ko'chiriladi
- `Telegram.WebApp` ga ulanish: `ready()`, `expand()`, `themeParams`,
  `BackButton`, `HapticFeedback`
- Telefon va kompyuter ko'rinishi

**Tayyor:** panel Telegram ichida to'liq balandlikda ochiladi, pastki
tab-panel ishlaydi.

Nima qilindi:

- Maket (artifact `UzChatGPT Panel`) uch faylga bo'lindi:
  `panel.html` (7 ta ekran, 11 ta sub-panel), `panel.css` (token
  tizimi o'zgaruvchilarda), `panel.js`. Logotip — `/static/logo.jpg`
  (maketdagi SVG tugun o'rniga; 3.2.1 ga qarang), favicon ham o'sha.
- **Telegram ulanishi:** `ready()`, `expand()`, `BackButton` (bosh
  ekranda yashiriladi — u yerda «orqaga» yopish ma'nosini beradi va
  chalg'itadi), `HapticFeedback` har bosilishda, `disableVerticalSwipes()`
  (jadvalni aylantirayotgan odam panelni tasodifan yopib yubormasin),
  `viewportStableHeight` → CSS `--vh` (`100vh` Telegram ichida noto'g'ri).
- **`themeParams` ATAYLAB o'qilmaydi.** Maket to'liq bo'yalgan qora —
  host rangini meros olsa ikki xil dastur ko'rinishini berardi. Buning
  o'rniga teskarisi: `setHeaderColor` / `setBackgroundColor` /
  `setBottomBarColor` Telegram chetlarini panel rangiga bo'yaydi.
- **Darvoza ekranlari:** `#yuklash` (logo + aylanma), `#xato` (403, 429,
  ulanmadi — har biriga o'z matni + «Qayta urinish»), `#shell`. Panel
  va tab-panel `hidden` turadi, ya'ni admin bo'lmagan odam **bironta
  raqam ham ko'rmaydi**.
- ⚠️ **Maketdan bitta ataylab chekinish.** Pastki tab-panelda 5 ta joy
  bor, ekran esa 7 ta — telefonda **Statistika va Tarqatmaga umuman
  yo'l qolmasdi** (chap menyu faqat kompyuterda). Bosh ekranga «Boshqa
  bo'limlar» kartochkasi qo'shildi, u faqat tor ekranda ko'rinadi
  (`.faqat-tel`). Tab-panelni 7 taga cho'zish emas: 360px da «Boshqaruv»
  yorlig'i qirqilardi.
- ⚠️ **panel.js `qism()` bo'laklariga ajratilgan.** Bitta IIFE ichida
  bitta yo'q element (`getElementById(...)` → null) undan keyingi
  HAMMA narsani o'ldirardi: ekranlar almashmay qoladi, tab-panel jim
  bo'ladi, konsolda esa bitta qator. Endi har bo'lak o'z `try/catch`
  ichida — buzilgan vidjet navigatsiyani olib ketmaydi.
- Sanani qotirib qo'yish o'rniga `Asia/Tashkent` bo'yicha hisoblanadi
  (oy nomlari qo'lda — `uz-UZ` hamma mijozda yo'q).
- ⚠️ **Ism va rol — BEZAK, shuning uchun bazaga bog'liq emas.**
  `_kim()` chap kartochkadagi matnni beradi; huquq undan oldin
  `huquq_bormi()` da tekshirilgan. Bu ikki DB so'rovi `try/except`
  ichida: aks holda bazadagi bir soniyalik uzilish MUVAFFAQIYATLI
  kirishni `500` ga aylantirib, adminni panelga umuman kiritmay
  qo'yardi. `tests/test_web_auth.py` 7-tekshiruvi shuni qadaydi —
  chaqiruvlar ataylab xato qaytaradi, kirish esa baribir `200`.
  (O'sha chaqiruvlar qo'shilganda test jimgina mahalliy `.env` dagi
  jonli bazaga bog'lanib qolgan edi va «tarmoqsiz» va'dasini
  buzgan edi — shu yerdayoq ushlandi.)
- `tests/test_web_panel.py` — 8 ta tekshiruv, brauzersiz va tarmoqsiz.
  Hammasi bitta turdagi nosozlikni qo'riqlaydi: **jim o'lgan tugma**
  (`data-go` → yo'q ekran, sub-tab → yo'q panel, `panel.js` → yo'q ID),
  ustiga telefondagi qamrov va logo qoidasi.

Ma'lumotlar hozircha **namuna** — sarlavhadagi «Namuna ma'lumotlar»
yorlig'i (`#namuna`) shuni aytib turadi va 3-bosqichda olib tashlanadi.

⚠️ **Jonli tekshirish hali qilinmadi** — 10-bo'limdagi ro'yxat
telefonda, Railway domeni ulangandan keyin bajariladi.

### ✅ 3-bosqich — Boshqaruv + Statistika  (BAJARILDI)
- `GET /api/overview`, `GET /api/stats`
- `activity_stats()` va `top_users()` ni `db/database.py` ga ko'chirish
  (`stats.py` ham o'shandan o'qiydigan bo'ladi)

**Tayyor:** raqamlar Telegram paneli bilan **bir xil** (yonma-yon
solishtiriladi).

Nima qilindi:

- **`handlers/admin/stats.py` da endi bironta xom SQL yo'q** (259 → 159
  qator). 11 ta so'rov `db/database.py` ga ikkita funksiya bo'lib
  ko'chdi: `activity_stats()` (jami/tarif sanoqlari, eng faollar,
  oxirgi foydalanuvchi, 7 kunlik faollik, 30 kunlik turlar kesimi) va
  `top_users(days, limit)`. Telegram ekrani ham, web ham AYNAN shulardan
  o'qiydi.
- `_ODDIY_USER` — adminlarni sanoqdan chiqaruvchi shart endi bitta
  o'zgaruvchida. Ilgari u so'rovlarning bir qismida bor, bir qismida
  yo'q edi va ekranda «jami 100, free+pro+premium = 103» chiqardi.
- **`core/config.py::ACTIVITY_TYPES`** — faollik turlarining yagona
  ro'yxati (`tur → (emoji, nom, ball)`). U bir vaqtda SQL filtri
  (`= ANY($1)`), Telegram ekranidagi nomlar va webdagi ustun nomlari.
  Ilgari SQL filtri va `type_labels` `stats.py` da qo'lda ikki marta
  yozilgan edi — web uchinchi nusxa bo'lardi.
  `tests/test_activity_tracking.py` endi dict'ni **import qiladi**,
  faylni matn sifatida o'qimaydi.
- `daily_report_stats()` ga uchta kalit qo'shildi (`prev_actions`,
  `active_7d`, `pro_expiring`) — KPI kartochkalari uchun. Alohida
  so'rov qilinmadi: ikki so'rov — ikki lahza, raqamlar bir-biriga
  mos kelmasligi mumkin.
- `web/api.py` — `/api/overview` va `/api/stats`. **Bu faylda SQL
  yo'q**, faqat `database` chaqiruvlari va shaklga o'tkazish.
- Panel: KPI, grafik, ustunlar, xatolar, top-10, tarif taqsimoti va
  ulushlar — hammasi haqiqiy ma'lumotda. Ekran birinchi ochilganda
  yuklanadi (`ekranYukla`), xato bo'lsa qayta urinish mumkin.

Maketdan ikki chekinish, ikkalasi ham **ma'lumot yo'qligi** sababli:

| Maketda | Nega bo'lmadi | O'rniga |
|---|---|---|
| «Bugungi tokenlar» kartochkasi | Bot token sarfini **hech qayerga yozmaydi** — u faqat Railway logidagi `[TOKEN]` qatorlarida. `users.total_tokens_used` bor, lekin u `user_history` jadvalidan o'qiydi, unga esa hech narsa yozilmaydi — ya'ni raqam doim 0. | «Tarif taqsimoti» (haqiqiy) |
| «O'rtacha javob 4.8s» | Bot javob vaqtini o'lchamaydi ham, yozmaydi ham. | «Guruh ulushi» (haqiqiy) |

⚠️ **Token hisobi kerak bo'lsa** — bu alohida qaror: yangi jadval +
`services/ai.py::_log_token_usage()` ga yozuv qo'shish kerak, ya'ni
o'zgarish botning ISSIQ yo'liga tegadi. 3-bosqich doirasidan tashqarida
qoldirildi.

Boshqa tuzatishlar (ikkalasi ham maketda ko'rinmasdi):

- **Grafik shkalasi endi ma'lumotga qarab tanlanadi.** Maketda yuqori
  chegara 400 qilib qotirilgan edi — kuniga 12 ta so'rovi bor bot
  grafigi tekis chiziqqa aylanardi va hech qanday o'zgarish
  ko'rinmasdi.
- **Jim kunlar nol bilan to'ldiriladi.** Bazada faqat amal bo'lgan kun
  qatori bor; ularni borligicha chizsak grafik «yaxshi» ko'rinardi, chunki
  tushish ko'rinmasdi.
- **Bazadan kelgan matn panelda ekranlanadi** (`xavfsiz()`): xato
  xabari va username foydalanuvchi yozganidan kelib chiqishi mumkin.
- «0%» va «ma'lumot yo'q» ajratildi: server bo'luvchi nol bo'lganda
  `null` yuboradi, panel «—» ko'rsatadi.
- Texnik ta'til yoqilgan bo'lsa sarlavhadagi «Bot ishlayapti» yorlig'i
  «Texnik ta'til» ga o'zgaradi — aks holda u yolg'on bo'lardi.

Jonli ma'lumot yana ikki nuqsonni ochdi (ikkalasi ham maketda ham,
soxta ma'lumotda ham ko'rinmasdi):

- **`daily_report_stats()` ning `top_types` so'rovida filtr yo'q edi** —
  «eng ko'p ishlatilgani» ro'yxatiga `start` ham tushardi. U so'rov emas,
  buyruq, va top-5 ning bir o'rnini bekorga egallardi. Filtr endi
  `LIMIT` dan OLDIN (keyin filtrlansa top-5 goh 4 ta bo'lib qolardi).
- **`handlers/admin/daily.py` da `ACTIVITY_LABELS` degan UCHINCHI qo'lda
  yozilgan nusxa bor ekan va unda `location_message` YO'Q edi** — ya'ni
  kunlik hisobot joylashuv so'rovini `location_message` degan xom satr
  qilib ko'rsatib yurgan. O'chirildi, u ham `ACTIVITY_TYPES` dan
  o'qiydi. Aynan shu narsa ro'yxatni bitta joyga yig'ish kerakligini
  tasdiqladi.

`web/api.py::_turlar()` ro'yxatda yo'q turni tashlab ketadi, lekin
**jimgina emas** — `logger.warning` bilan: panelga xom satr chiqqandan
ko'ra tashlagan yaxshi, ammo izsiz qolsa yangi tur oylab ko'rinmay
yurishi mumkin.

`tests/test_web_stats.py` — 8 ta tekshiruv. 8-tekshiruv 3-bosqichning
«tayyor» mezonini avtomatlashtiradi: Telegram ekrani va web BITTA soxta
bazadan o'qiydi va natijalari solishtiriladi, ya'ni kimdir web uchun
alohida so'rov yozib qo'ysa test yiqiladi.

Ko'chirilgan SQL **jonli bazada** ham sinaldi (faqat `SELECT`):
`activity_stats()`, uchala `top_users()` chaqiruvi va yangi kalitlar —
hammasi ishladi, `free+pro+premium` `total_users` ga to'g'ri keldi.

### ✅ 4-bosqich — Foydalanuvchilar  (BAJARILDI — jonli tekshiruvdan tashqari)
- Ro'yxat, qidiruv, filtr, sahifalash
- Kartochka va barcha amallar, to'lovlar, refund

**Tayyor:** sinov hisobiga Pro berib, bekor qilib ko'riladi; audit
jurnalida ikkala amal ham ko'rinadi.

Nima qilindi:

- **`database.list_users(q, tarif, limit, offset)`** — qidiruv, filtr va
  sahifalash SQL darajasida. Mavjudlari yaramadi: `get_all_users()` da
  na chegara, na filtr bor (HAMMA qatorni tortadi), `search_users()`
  esa faqat username bo'yicha qidiradi va sahifalamaydi. Qidiruv matni
  — PARAMETR, satrga yopishtirilmaydi (jonli bazada `' OR 1=1 --` bilan
  sinaldi: 0 ta natija).
- **Chip sanoqlari kesishmaydi**: `pro + free + ban = jami`. Bloklangan
  odam «bepul» da ham tursa, chiplar yig'indisi jamidan oshib ketardi —
  bu xato loyihada bir marta bo'lgan (`_ODDIY_USER` izohi).
- Ro'yxatda adminlar yo'q — panelning boshqa hamma sanog'i ham ularsiz,
  ikki xil «jami» ko'rsatib bo'lmaydi. Adminlar 6-bosqichdagi
  Sozlamalar → Adminlar ekranida boshqariladi.
- **8 ta endpoint**: ro'yxat, kartochka, Pro berish, tarifni tushirish,
  kvota tiklash, blok/ochish, xabar yozish, refund. Har biri
  `@admin_only`, har **yozuv** amali `log_admin_action()` ga tushadi.
- **Refund `handlers/admin/users.py` dagi tartibni AYNAN takrorlaydi:**
  avval Telegram, keyin baza. Teskari bo'lsa Telegram rad etganda
  (muddat o'tgan, allaqachon qaytarilgan) foydalanuvchidan tarif olib
  qo'yilib, puli qaytmasdan qolardi. Pul qaytib, baza yozilmagan holat
  log'da ALOHIDA belgilanadi — tarif hali odamda turadi.
- **Foydalanuvchiga xabar**: Pro berilganda, tarif bepulga tushirilganda
  va blok ochilganda yuboriladi. Bloklashda YUBORILMAYDI (bot keyingi
  xabarda o'zi aytadi), kvota tiklashda ham (ko'pincha texnik amal,
  har safar bezovta qilish ortiqcha). Xabar yetmasa amal BEKOR
  QILINMAYDI — Pro berildi, berildi; panel «xabar yetmadi» deb yozadi.
- Panel: qidiruv 300ms kutadi (har harfga so'rov emas), sahifalash,
  kartochka qator bosilganda ochiladi, `tg.showConfirm` bilan tasdiq
  (blok, refund, tarif tushirish), muddat tanlash bitta qatorda.

⚠️ **Jonli tekshiruv bajarilmadi va bu ataylab.** «Sinov hisobiga Pro
berib, bekor qilish» — bu ishlab turgan bazaga YOZISH va haqiqiy odamga
Telegram xabari yuborish demak. Buni panel orqali o'zingiz qilasiz
(10-bo'lim, 5-tekshiruv). Mantiqning o'zi soxta baza va soxta Telegram
bilan to'liq sinalgan.

Test yo'lda **jiddiy xatoni** ushladi: `{"kun": "o'ttiz"}` yuborilganda
`int()` yiqilib, `kun = None` bo'lardi — `None` esa bu yerda «cheksiz»
degani, ya'ni **buzuq kirish eng katta sovg'ani olardi**. Endi
tushunib bo'lmagan qiymat rad etiladi.

Kichikroq tuzatish: maketdagi qidiruv «ID, username yoki ism» deb
va'da qilardi — bazada ism ustuni YO'Q, faqat `username` va `user_id`.
Matn to'g'rilandi.

`tests/test_web_users.py` — 12 ta tekshiruv, ular ichida:
2-si **manba bo'yicha** har bir marshrut `@admin_only` bilan yopilganini
(jonli tekshiruv faqat men sinagan yo'lni ko'radi, bu esa hammasini),
9-si Telegram rad etganda bazaning TEGILMAGANINI, 10-si muvaffaqiyatli
refundning tartibini.

### ✅ 5-bosqich — Jurnal  (BAJARILDI)
Audit, xatolar, daromad, nofaol userlar.

**Tayyor:** 4 ta sub-tab ham ma'lumot ko'rsatadi, sahifalash ishlaydi.

Nima qilindi:

- To'rtta endpoint: `/api/journal/audit` (sahifalash + admin filtri),
  `/api/journal/errors` (sahifalash + xulosa + turlar kesimi),
  `/api/journal/revenue`, `/api/journal/inactive`. Yangi SQL yozilmadi —
  hammasi mavjud `database` funksiyalaridan.
- Panel: to'rttasi ham bir vaqtda yuklanadi (sub-tab almashishi bir
  zumda bo'lishi kerak, so'rovlar esa yengil), audit va xatolarda
  sahifalash, auditda admin bo'yicha chip filtri.

⚠️ **Yana bir eskirgan ro'yxat topildi va u eng yomoni edi.**
`handlers/admin/journal.py` dagi `ACTION_LABELS` — audit yozuvining
texnik nomini odam o'qiydigan nomga aylantiradigan ro'yxat — kod
yozadigan nomlar bilan **mos emasdi**:

| Ro'yxatda | Kod yozadi | Natija |
|---|---|---|
| `ban` | `ban_user` | xom nom |
| `unban` | `unban_user` | xom nom |
| `set_free` | `set_plan` | xom nom |
| `refund` | `refund_stars` | xom nom |
| `promo_create` | `create_promo` | xom nom |
| — | `revoke_promo`, `send_promo`, `send_referral`, `referral_campaign` | xom nom |

Ya'ni **16 ta amaldan 9 tasi** audit jurnalida `refund_stars` degan
texnik satr bo'lib chiqib turgan, yana 6 ta yorliq esa hech qachon
yozilmaydigan kalitga osilgan edi. Ro'yxat
`core/config.py::AUDIT_ACTIONS` ga ko'chdi (17 ta amal, `send_message`
ham qo'shildi) — Telegram jurnali ham, web ham shundan o'qiydi.
Jonli bazada tekshirildi: audit endi «💎 Pro berildi», «🎟 Promokod
yuborildi», «🤝 Referal kampaniyasi» deb ko'rsatadi.

Maketdagi yana bir noto'g'ri va'da tuzatildi: «Nofaol foydalanuvchilar»
kartochkasi «14 kundan beri yozmaganlar» deb tushuntirilgandi va
«Eslatma yuborish» tugmasi bor edi. `inactive_users()` esa BOSHQA
narsani qaytaradi — `is_active = FALSE`, ya'ni tarqatma paytida xabar
YETMAGAN odamlar: botni bloklagan yoki o'chirib yuborganlar. Ularga
eslatma yuborib bo'lmaydi, shuning uchun tugma olib tashlandi va matn
to'g'rilandi. («14 kun yozmaganlar» — bu `notify_inactive_users()` fon
vazifasi, u o'zi ishlaydi va panelga chiqmaydi.)

Yana uchta qotirilgan namuna raqam olib tashlandi: yon menyudagi
«Foydalanuvchilar 1 204» va «Jurnal 4», hamda sarlavha ostidagi
«1 204 ta yozuv · 14 tasi Pro». Grafik ustidagi «24 soat / 7 kun /
30 kun» chiplari ham olib tashlandi — ular bosilganda hech narsa
qilmasdi (grafik doim 7 kunlik), o'zgarmaydigan tugma esa buzilgan
panel taassurotini beradi.

`tests/test_web_journal.py` — 9 ta tekshiruv. 1-tekshiruv kod
yozadigan amallarni `AUDIT_ACTIONS` bilan solishtiradi (`log_admin_action`
va web'ning `_yoz` chaqiruvlarini manbadan o'qib), 2-tekshiruv esa
teskarisini: hech qachon yozilmaydigan «o'lik» yorliq qolmasin.

### ✅ 6-bosqich — Sozlamalar va promo  (BAJARILDI — jonli tekshiruvdan tashqari)
Limitlar, texnik ta'til, kuzatish, adminlar, promokodlar, bepul Pro,
referal, hamda tarqatmaning «faqat ko'rish» ekrani.

**Tayyor:** limitni webdan o'zgartirib, botga savol yuborilganda
**yangi** limit ishlaydi (RAM keshi yangilanganini shu tasdiqlaydi).

Nima qilindi:

- **O'n oltita endpoint.** Sozlamalar: `/api/limits` (GET/POST),
  `/api/maintenance` (GET/POST), `/api/watch` (GET/POST), `/api/admins`
  (GET/POST). Promo: `/api/promo` (GET/POST), `/api/giveaway`
  (GET/POST), `/api/referral` (GET/POST). Tarqatma: `/api/broadcasts`
  (GET) va `DELETE /api/broadcasts/{id}`. Yangi SQL yozilmadi — hammasi
  mavjud `database` funksiyalaridan.
- Paneldagi oxirgi qotirilgan namuna raqamlar ketdi, shuning uchun
  sarlavhadagi «Promo va sozlama — namuna» yorlig'i ham olib tashlandi:
  endi yettala ekran ham haqiqiy ma'lumotda.

⚠️ **RAM keshi — bu bosqichning butun mohiyati.** Ikki joyda:

| Endpoint | Chaqiriladi | Unutilsa nima bo'ladi |
|---|---|---|
| `POST /api/limits` | `config.apply_limit_overrides()` | Bazada yangi limit, bot esa eskisi bilan ishlaydi. Panel «o'zgardi» deydi, foydalanuvchi eski chegaraga uriladi, hech narsa xato bermaydi. |
| `POST /api/watch` | `database.load_watch_cache()` | `get_watch_target()` har xabarda, sinxron, bazasiz ishlaydi — ya'ni faqat keshni biladi. Panel «qo'shildi» deydi, xabarlar guruhga tushmaydi. |

Bu 3.1 dagi «panel bot jarayonining ICHIDA» qarorining amaldagi sababi:
ikkinchi jarayon bo'lganda bu ikki chaqiruv umuman yordam bermasdi.
`tests/test_web_settings.py` ning 2- va 8-tekshiruvi aynan shuni
qo'riqlaydi.

⚠️ **Yana ikkita eskirgan ro'yxat topildi** — ACTIVITY_LABELS va
ACTION_LABELS bilan aynan bir xil naqsh:

| Qayerda | Nima bo'lgandi |
|---|---|
| `handlers/admin/journal.py::LIMIT_KEYS` va `web/api.py::SANOQ_NOMI` | Bir xil to'rt limit ikki joyda, ikki xil nom bilan: «Fayl» va «Fayllar», «Tadqiqot» va «Chuqur tadqiqot». Admin ularni boshqa-boshqa sozlama deb o'ylashi mumkin edi. |
| `handlers/admin/journal.py` dagi `segment_nom` | Tarqatma qamrovining nomlari. Web uchun yozilgan BIRINCHI nusxada `"pro"` va `"active"` degan **mavjud bo'lmagan** kalitlar bor edi — ya'ni panel `premium` segmentini xom nomi bilan ko'rsatgan bo'lardi. Manbaga (`_filter_users_by_segment`) qaralgach tuzatildi. |

Ikkalasi ham `core/config.py` ga ko'chdi: **`LIMIT_NOMI`** (4 ta) va
**`SEGMENT_NOMI`** (4 ta). Bu `ACTIVITY_TYPES` va `AUDIT_ACTIONS` dan
keyingi uchinchi va to'rtinchi yagona ro'yxat.

⚠️ **Qoidalar ham ikki joyda yozilmadi.** Uchta tekshiruv Telegram
ekrani bilan **bitta** funksiyadan o'tadi:

- `database.clean_promo_spec()` — promokod qoidalari (kod shakli, 1–3650
  kun, 1–100000 marta, muddat kelajakda). Ilgari `handlers/admin/promo.py`
  ning handler tanasida edi.
- `database.clean_referral_config()` — allaqachon shunday edi, web ham
  o'shani chaqiradi («3 do'st → 300 kun» rad etiladi).
- `handlers/admin/common.py::_check_can_remove_admin()` — admin
  o'chirish qoidasi. `handlers/admin/system.py` dan **`common.py`** ga
  ko'chirildi, chunki u endi ikki ekranning qo'riqchisi. Web uni qayta
  yozganda panel botdan **zaifroq eshik** bo'lib qolardi (o'zini
  o'chirish, superadminni o'chirish, uch kunlik kutish, oxirgi admin) va
  buni hech narsa ushlamasdi.

⚠️ **Oltita yangi audit amali.** `maintenance`, `watch_add`,
`watch_remove`, `watch_group`, `referral_config`, `cancel_broadcast` —
ularni **faqat web yozadi**. Telegram ekranlari bu amallarni umuman
auditga yozmasdi, ya'ni texnik ta'tilni kim yoqqani va kim kuzatuvga
qo'shilgani hech qayerda qolmasdi.

**Maketdan chetga chiqishlar va sabablari:**

| Maketda | Nima qilindi | Nega |
|---|---|---|
| Limitlar jadvalida «Kontekst (xabar) 30 / 80» qatori | Olib tashlandi | Kontekst oynasi `CONTEXT_WINDOW_*` konstantasi, `PLAN_LIMITS` da yo'q va `set_limit_override()` uni o'zgartira olmaydi. Bosilganda hech narsa qilmaydigan tugma — buzilgan panel taassuroti. |
| «Holat» kartochkasida `44003a8 · 21:12`, `4s 12m`, `gpt-5.6-luna` | Haqiqiy qiymatlar | Commit `RAILWAY_GIT_COMMIT_SHA` dan; mahalliy ishga tushirishda u yo'q va **qator umuman chizilmaydi** — soxta commit ko'rsatilmaydi. |
| «Sovg'alar tarixi» ro'yxati (`@malika_r · promokod · 30 kun`) | `giveaway_stats()` raqamlariga almashtirildi | Bunday birlashtirilgan jadval bazada **yo'q**: kim ishlatgani `promo_redemptions` da, referal mukofoti `referrals` da, admin sovg'asi `admin_audit` da. Uni yasash yangi SQL talab qilardi — bu 3.2 qoidasini buzadi. Yangi kartochka «bepul Pro bizga qancha turyapti» degan savolga to'g'ridan javob beradi. |
| Referalda «Kimlarga tegishli — hamma / yangi kelganlar» | Olib tashlandi | Kodda bunday ajratish yo'q: umumiy shart hammaga, shaxsiy shart bitta odamga (botdan beriladi). O'rniga haqiqiy chegaralar yozildi. |
| «Oxirgi tarqatma»: yuborilgan / yetmagan / bloklagan / davomiyligi | Kartochka olib tashlandi | `scheduled_broadcasts` faqat rejalashtirilganni biladi; yuborilganidan keyin `sent_at` dan boshqa hech narsa qolmaydi. Natija hech qayerda saqlanmaydi. |
| Kuzatuv guruhi `-1002481…` deb ko'rsatilgan | Haqiqiy qiymat yoki «qo'yilmagan» | Guruh qo'yilmagan bo'lsa kuzatuv **umuman ishlamaydi** (`get_watch_target()` `None` qaytaradi) — ro'yxatdagilar «Faol» emas, «guruh yo'q» deb belgilanadi. |
| Adminlar ro'yxati uchta qatordan iborat | `get_panel_admins()` | ⬇️ Pastdagi izohga qarang. |

⚠️ **Jonli bazada bitta jiddiy nuqson topildi** (3-bosqichdagi `start`
xatosi kabi — soxta ma'lumot buni ko'rsatmasdi). Adminlar ro'yxati
avval `get_admins()` dan olinardi, u esa faqat `admins` jadvalini
o'qiydi. Jonli bazada `admins` **bo'sh**, superadmin esa bor
(`@jumayeevou`) — ya'ni ekran «panelga hech kim kira olmaydi» deb
turgan bo'lardi, holbuki o'sha odam kira oladi va hozir ham kirib
turibdi. Huquq tekshiruvi (`web.huquq_bormi`) ikkala jadvalni ham
ko'radi, ro'yxat esa bittasini — «kim kira oladi» degan savolga
yolg'on javob.

Yangi `database.get_panel_admins()` ikkala jadvalni bitta so'rovda
(`FULL OUTER JOIN`) birlashtiradi va `is_super` bayrog'ini o'zi
qaytaradi — bu yo'l-yo'lakay har qator uchun alohida `is_superadmin()`
chaqiruvini ham (N+1) yo'q qildi. `tests/test_web_settings.py`
12-tekshiruvi `admins` jadvalini bo'shatib, superadmin baribir
ro'yxatda qolishini tekshiradi.

**Boshqa qarorlar:**

- Sovg'a `set_user_premium(..., extend=True)` bilan beriladi —
  qolgan muddat **ustiga** qo'shiladi. Kartochkadagi «Pro berish» esa
  ataylab ustidan yozadi: u tuzatish amali, bu esa sovg'a.
- Sovg'ada `kun: null` (cheksiz) **qabul qilinmaydi**: cheksiz Pro —
  bitta odamga kartochkadan beriladigan amal, ro'yxatga tarqatiladigan
  narsa emas.
- «Xabar yetmadi» alohida ko'rsatiladi: Pro **berilgan**, faqat xabar
  bormagan. Admin buni «bajarilmadi» deb tushunib ikkinchi marta bersa,
  odam ikki barobar kun olardi.
- Admin qo'shishda faqat **sonli ID** qabul qilinadi (Telegram ekrani
  ham shunday): `@username` egasi uni o'zgartirsa nom boshqa odamga
  o'tib ketadi, admin huquqi esa qoladi.
- Admin qo'shilganda/o'chirilganda `sync_menu_button()` darhol
  chaqiriladi — ko'k «Panel» tugmasi keyingi `/start` ni kutmaydi.
- Panel qatorlaridagi tugmalar **delegatsiya** bilan bog'lanadi
  (`delegat()`): ro'yxat har yuklashda qayta chiziladi, tinglovchini
  qatorga qo'yish esa bitta bosishni ikki marta bajaradigan yo'l.

`tests/test_web_settings.py` — 13 ta tekshiruv (2- va 8-tekshiruv RAM
keshi, 11-tekshiruv admin o'chirish darvozasi, 12-tekshiruv yuqoridagi
jonli nuqson).
`tests/test_web_promo.py` — 12 ta tekshiruv (3- va 6-tekshiruv eng
qimmati: qoidaning yagonaligi va `extend=True`).

### ✅ 7-bosqich — Telegram ekranlarini o'chirish  (BAJARILDI)
Ko'chib bo'lgan ekranlar o'chirildi, reply-klaviatura olib tashlandi.

**Tayyor:** `register_admin_handlers()` da **21 ta** registratsiya
qoldi (57 tadan), test yashil.

> Rejada «~10 ta» deb yozilgandi — noto'g'ri baho edi. Faqat
> tarqatmaning o'zi 15 ta registratsiya talab qiladi (konstruktor,
> tugmalar, rang, ko'rib chiqish, segment, tasdiq, bekor, keyinroq),
> report ikkita, promokod yuborish to'rttasi. 21 — bu haqiqiy pol.

**O'chirilgan fayllar:**

| Fayl | Qayerga ko'chgan |
|---|---|
| `handlers/admin/menu.py` | Yo'q — inline menyular reply-klaviatura bilan birga ketdi |
| `handlers/admin/stats.py` | `/api/stats`, `/api/overview` |
| `handlers/admin/journal.py` | `/api/journal/*`, `/api/limits` |
| `handlers/admin/users.py` | `/api/users*`, `/api/payments/{id}/refund` |
| `core/keyboards.py` | Yo'q — reply-klaviaturaning o'zi |
| `tests/test_admin_menu.py` | Yo'q — u klaviatura va menyuni sinardi |

`system.py` 590 → 166 qator (faqat report), `promo.py` 700 → 263 qator
(faqat yuborish).

**Nima BOTDA qoldi va nega** (REJA 2 ning amaliy tasdig'i):

- **`/xabar`** — tarqatma. `copy_message` adminning xabarini aynan
  uzatadi.
- **`/kod`** — promokod va referal taklifini odamga yuborish.
- **Report** — foydalanuvchi boshlaydi, ya'ni panelga umuman kirmaydi.
- **Kunlik hisobot** (`daily.py`) — push, fon vazifasi.
- **To'lov handlerlari** — `main.py` da, tartibiga tegilmadi.

⚠️ **`/kod` — rejadagi bo'shliq.** REJA 2 «qolgan hamma narsa webga
ko'chadi» deydi, lekin promokodni ANIQ odamlarga yuborish oqimi web
spetsifikatsiyasida (5- va 6-bo'lim) umuman yo'q — ya'ni u ko'chmagan
ham. Ikki yo'l bor edi: o'chirish (o'rinbosarsiz imkoniyat yo'qoladi)
yoki saqlash. Saqlandi, sababi tarqatmanikiga aynan o'xshash:
`send_promo_gift()` tayyor tugmali xabar jo'natadi,
`send_referral_invite()` esa har kimga o'zining shaxsiy havolasini
yasaydi — webda qayta yig'ilgan xabar ikkalasini ham yo'qotardi. Kod
YARATISH esa panelda qoldi, ya'ni ikki nusxa yo'q.

⚠️ **Kirish nuqtasi — BUYRUQ, matnli tugma emas.** Klaviatura yo'q
bo'lgach `F.text == '📢 Xabar yuborish'` ga bog'langan handler jimgina
**o'lik** bo'lib qolardi: ro'yxatda turadi, lekin hech qachon ishga
tushmaydi (tugma yo'q, admin esa matnni qo'lda yozmaydi). Shuning
uchun `Command("xabar")` va `Command("kod")`.
`tests/test_admin_registry.py` 3-tekshiruvi `F.text ==` qaytib
kelmasligini qo'riqlaydi.

⚠️ **Eski klaviatura o'zi yo'qolmaydi.** Telegram `ReplyKeyboardMarkup`
ni almashtirilgunicha yoki OCHIQ o'chirilgunicha ko'rsataveradi —
faylni o'chirish adminning telefonidagi tugmalarni olib tashlamaydi.
Tozalanmasa admin ishlamaydigan to'rtta tugmani bosib, hech qanday
javob olmasdi va buni «bot buzildi» deb tushunardi. `/start` endi
`ReplyKeyboardRemove()` yuboradi.

⚠️ **Klaviatura — adminning yagona KO'RINADIGAN kirish nuqtasi edi.**
Uni olib tashlab, o'rniga hech narsa qo'ymaslik — `/xabar` ni faqat
eslab qolgan odam topa oladi degani (`/start` bir marta aytadi, keyin
yo'qoladi). Shuning uchun `services/menu.py` ga **`ADMIN_COMMANDS`**
qo'shildi va u «/» ro'yxatiga faqat adminda chiqadi.

Bu yo'l-yo'lakay ikkita nozik joyni ochdi:

1. `sync_commands` keshi `is_pro` bo'yicha `is` bilan solishtirardi.
   Admin bayrog'i qo'shilgach o'sha tekshiruv adminlikdagi o'zgarishni
   umuman ko'rmay qolardi — odam admin bo'ladi, buyruqlar esa eski
   ro'yxatda qolib ketardi. Kesh endi **juftlik** bo'yicha.
2. Chaqiruv birinchi urinishda `if admin_flag` dan TASHQARIDA turgandi
   va har bir foydalanuvchiga `is_pro=True` berardi — bepul odam
   menyusida `/kunlik` bilan `/research` ni ko'rardi. `if` ichiga
   ko'chirildi; `tests/test_menu.py` 3b-tekshiruvi sizishni qo'riqlaydi.

**Testlar:**

- `tests/test_admin_registry.py` — 2 dan **5 ta** tekshiruvga kengaydi.
  Yangi 2-tekshiruv webga ko'chgan **31 ta** ekran nomini biladi va
  ularning biri botga qaytarilsa, xato xabarida «bu ekran o'chirilgan
  emas — KO'CHGAN» deb sababini aytadi. 3- va 4-tekshiruv buyruq
  kirishi va klaviatura tozalanishini qo'riqlaydi.
- `tests/test_admin_extras.py` — 20 dan **13 ta**ga qisqardi: jurnal
  ekranlarining tekshiruvlari `test_web_journal.py` va
  `test_web_settings.py` ga o'tgan, ikki joyda takrorlash qo'riqchi
  emas, yuk.
- `tests/test_web_stats.py` 8-tekshiruvi **shaklini o'zgartirdi**.
  Ilgari u Telegram ekrani bilan webning raqamlarini solishtirardi;
  ekran endi bitta. Qoidaning o'zi esa qoldi va u muhimroq:
  `web/api.py` da xom SQL bo'lmasin (`SELECT`/`INSERT`/`UPDATE`/
  `DELETE`/`pool.acquire`), `daily.py` da ham — ya'ni panel bilan
  kunlik hisobot bir kuni ikki xil raqam ko'rsata olmaydi.
- `tests/test_activity_tracking.py` — iste'molchilar ro'yxatidan
  `stats.py` chiqdi, uchtasi qoldi.
- `tests/test_menu.py` — yangi 3b-tekshiruv.
- `tests/test_admin_menu.py` — **o'chirildi** (klaviatura va menyuni
  sinardi, ikkalasi ham yo'q).
- `tests/test_admin_kod.py` — **yangi**, 6 ta tekshiruv. `/kod` endi web
  testlari qoplamaydigan yagona admin oqimi: menyuda faqat yuborish
  amallari, tanlash ro'yxatida faqat ishlatsa bo'ladigan kodlar
  (limiti to'lgan yoki bekor qilingani odamga ishlamaydigan sovg'a
  bo'lardi), kod yo'qda panelga yo'naltirish, eski callback yiqitmasligi.

---

## 8. Testlar

Yangi (mavjud uslub: raqamlangan `assert`, tarmoqsiz, bazasiz):

- `tests/test_web_auth.py`
  1. soxta imzoli `initData` rad etiladi
  2. `auth_date` 5 daqiqadan eski bo'lsa rad etiladi
  3. imzosi to'g'ri, lekin admin bo'lmagan foydalanuvchi rad etiladi
  4. cookie imzosi buzilsa rad etiladi
- `tests/test_web_routes.py`
  5. **har** `/api/*` handler `@admin_only` bilan boshlanadi (manba
     bo'yicha — `test_admin_extras.py` dagi 19-tekshiruv naqshi)
  6. yozuv amallari `log_admin_action` chaqiradi
  7. limit va kuzatuv endpointlari RAM keshini yangilaydi
     (`apply_limit_overrides` / `load_watch_cache` manbada bor)

- `tests/test_web_panel.py` (2-bosqichda yozildi, 8 ta tekshiruv)
  8. har `data-go` haqiqiy ekranga olib boradi, bosh ekran aniq bitta
  9. **har ekran telefonda ham ochiladi** — tab-panel + bosh ekran
     tugmalari birgalikda 7 tasini ham qamraydi
  10. sub-tab tugmasi ↔ panel juftligi va ochiq panel aniq bitta
  11. logo faqat `/static/logo.jpg` dan olinadi (3.2.1 qoidasi)
  12. `panel.js` chaqirgan har ID `panel.html` da bor
  13. css/js/Telegram kutubxonasi ulangan
  14. `expand`, `BackButton`, `HapticFeedback`, `--vh` joyida
  15. panel va tab-panel kirishdan oldin `hidden`

- `tests/test_web_stats.py` (3-bosqichda yozildi, 8 ta tekshiruv)
  16. `/api/overview` va `/api/stats` cookie'siz `401`
  17. grafik doim 7 kun, jim kun `0` bilan to'ldiriladi
  18. kecha ma'lumot bo'lmasa o'zgarish foizi ko'rsatilmaydi
  19. nolga bo'lish «—», haqiqiy nol «0%»
  20. begona matn (xato xabari, username) panelda ekranlanadi
  21. turlar xom emas, ko'rinadigan nom bilan qaytadi
  22. ulushlar va konversiya to'g'ri hisoblanadi
  23. **Telegram ekrani va web bir manbadan — raqamlar bir xil**

- `tests/test_web_users.py` (4-bosqichda yozildi, 12 ta tekshiruv)
  24. 8 ta yangi endpoint cookie'siz `401`
  25. **manba bo'yicha** har bir marshrut `@admin_only` bilan
  26. ro'yxat sahifalanadi, noto'g'ri parametr yiqitmaydi
  27. kartochka to'liq; yo'q foydalanuvchi `404`, buzuq ID `400`
  28. Pro berish: baza + audit + foydalanuvchiga xabar
  29. faqat ruxsat etilgan muddatlar qabul qilinadi
  30. blok/kvota/tarif amallari auditda, xabarlar o'rinli
  31. xabar: bo'sh va uzun rad etiladi, HTML ekranlanadi
  32. **Telegram refundni rad etsa baza tegilmaydi**
  33. muvaffaqiyatli refund: Telegram → baza → audit → xabar
  34. qaytarilgan/yo'q to'lovda Telegram'ga umuman borilmaydi
  35. xabar yetmasa ham amal bajariladi va auditda qoladi

- `tests/test_web_journal.py` (5-bosqichda yozildi, 9 ta tekshiruv)
  36. **kod yozadigan har bir audit amalining nomi bor**
  37. o'lik yorliq yo'q, ro'yxatning ikkinchi nusxasi yo'q
  38. jurnalning 4 ta endpointi ham cookie'siz `401`
  39. noma'lum amal YASHIRILMAYDI — xom nomi bilan ko'rinadi
  40. audit filtri va sahifalashi, buzuq parametr yiqitmaydi
  41. xatolar: xulosa, turlar, sahifalash, matn ekranlanadi
  42. daromad: o'rtacha chek va tarif nomlari
  43. sotuv yo'qda o'rtacha chek «—», nolga bo'linmaydi
  44. nofaol ro'yxati to'g'ri tushuntirilgan

- `tests/test_web_settings.py` (6-bosqichda yozildi, 13 ta tekshiruv)
  45. sozlamalarning 8 ta endpointi cookie'siz `401`
  46. ⭐ **webdan o'zgartirilgan limit BOT xotirasida ham darhol kuchga
      kiradi** — bosqichning «tayyor» mezoni
  47. tiklash asl qiymatni qaytaradi, CHEKSIZLIK bermaydi
  48. buzuq qiymat (`true` ham!), cheksiz tarif va begona kalit rad etiladi
  49. limit nomlari yagona ro'yxatdan, ikkala ekranda nusxa yo'q
  50. ta'til: matn tahriri rejimni o'zgartirmaydi, hammasi auditda
  51. holat kartochkasi haqiqiy, qotirilgan namuna qolmagan
  52. kuzatuvning uchala amali ham RAM keshini yangilaydi
  53. topilmagan odam va buzuq guruh ID rad etiladi
  54. admin qo'shilganda «Panel» tugmasi darhol; `@username` rad etiladi
  55. ⭐ **admin o'chirish qoidasi Telegram bilan BITTA darvozadan o'tadi**
  56. ⭐ **superadmin `admins` jadvalida bo'lmasa ham ro'yxatda ko'rinadi**
      (jonli bazada topilgan nuqson)
  57. 30 ta marshrutning hammasi `@admin_only` bilan

- `tests/test_web_promo.py` (6-bosqichda yozildi, 12 ta tekshiruv)
  58. promo va tarqatmaning 8 ta endpointi cookie'siz `401`
  59. limit to'lgan, muddati o'tgan va bekor qilingan kod farqlanadi
  60. ⭐ **promokod qoidalari bitta sof funksiyada** (`clean_promo_spec`)
  61. kod yaratiladi, katta harfga o'giriladi, takrori `409`
  62. kod bekor qilinadi (o'chirilmaydi), yo'q kod `404`
  63. ⭐ **sovg'a qolgan muddat USTIGA qo'shiladi** (`extend=True`)
  64. berildi / xabar yetmadi / topilmadi — uchtasi alohida
  65. buzuq muddat va bo'sh ro'yxat Pro bermaydi (cheksiz yo'li yopiq)
  66. referal: «3 do'st → 300 kun» rad etiladi, o'zgarish auditda
  67. segment nomlari yagona ro'yxatdan, noma'lumi yashirilmaydi
  68. tarqatma bekor qilinadi; yuborilgani `404`, buzuq ID `400`
  69. yangi tarqatma faqat botda, sababi ekranda yozilgan

Mavjudlaridan yangilandi: `test_activity_tracking.py` (3-bosqichda —
endi `ACTIVITY_TYPES` ni import qiladi; 7-bosqichda `stats.py`
iste'molchilar ro'yxatidan chiqdi), `test_web_users.py` (6-bosqichda —
sanoq nomlarini qo'lda emas, `LIMIT_NOMI` dan o'qiydi; eski nusxa o'zi
yiqilib, testning nomlarni emas, O'Z NUSXASINI qo'riqlayotganini
ko'rsatdi).

**7-bosqichda** `test_admin_registry.py` 2 dan 5 ta tekshiruvga
kengaydi (webga ko'chgan 31 ta ekran qaytmasligi, buyruq kirishi,
klaviatura tozalanishi), `test_admin_extras.py` 20 dan 13 taga
qisqardi, `test_menu.py` ga 3b qo'shildi, `test_admin_menu.py`
o'chirildi.

⚠️ **To'rtta test o'chirishdan keyin O'ZI yiqildi va bu qimmatli
signal edi** — har biri qoidasi endi boshqa joyda ekanini ko'rsatdi:

| Test | Nima aytdi | Nima qilindi |
|---|---|---|
| `test_web_journal` 2 | `referral_campaign` endi hech kim yozmaydi | Yorliq `AUDIT_ACTIONS` dan olib tashlandi. Jonli bazadagi 2 ta eski yozuv xom nom bilan ko'rinadi — o'sha bazada `stats_view`, `users_export` kabi yana **12 ta** eski amal allaqachon shunday, ya'ni bu mavjud xatti-harakat. |
| `test_web_promo` 3 | «Ikkala ekran ham `clean_promo_spec` chaqiradimi» — chaqiruvchi bitta qoldi | Savol o'zgardi: chegaralar `web/api.py` ga KO'CHMASIN, `database.py` dagi sof funksiyada qolsin. |
| `test_web_promo` 10 / `test_web_settings` 5 | O'chgan `journal.py` dan nusxa qidirardi | Endi kalitlarning MANBASI tekshiriladi: har bir segment `broadcast.py` da yoziladimi, har bir limit kaliti `PLAN_LIMITS` da bormi. |
| `test_web_stats` 8 | Solishtiradigan ikkinchi ekran yo'q | Qoida saqlandi, shakli o'zgardi: `web/api.py` va `daily.py` da xom SQL bo'lmasin. |

Har safar test «nimani qo'riqlayapman» degan savolni qaytadan
bergan — va javob har safar «ekranni emas, QOIDANI» bo'lib chiqqan.

---

## 9. Xavflar va chegaralar

| Xavf | Nima qilinadi |
|---|---|
| Paneldagi xato botni yiqitadi | Umumiy middleware `try/except`, panel xatosi faqat JSON qaytaradi |
| Panel internetda ochiq | 4-bo'limdagi uch qatlam; har so'rovda `is_admin` |
| Ikki panel = ikki barobar qarov | 7-bosqich majburiy, keyinga qoldirilmaydi |
| Telefonda ishlamay qolishi | Har bosqich telefonda tekshiriladi, kompyuterda emas |
| Token ikki joyda | Yo'q — bitta jarayon, bitta env |

**Webda bo'lmaydi (ataylab):** tarqatma kontenti, report javoblari,
kunlik hisobot, to'lov qabul qilish.

---

## 10. Jonli tekshirish ro'yxati

Har bosqichdan keyin **telefonda**, Telegram ichida:

| # | Nima | Kutilgan |
|---|---|---|
| 1 | Oddiy foydalanuvchi chati | Ko'k tugma yo'q, «/» ro'yxati o'zgarmagan |
| 2 | Admin chati | Ko'k tugma «Panel», bosilganda ochiladi |
| 3 | Havolani boshqa hisobdan ochish | `403`, hech qanday ma'lumot ko'rinmaydi |
| 4 | Adminlikdan chiqarish | Keyingi so'rovda panel yopiladi, tugma yo'qoladi |
| 5 | Pro berish | Foydalanuvchi botdan xabar oladi, audit jurnalida yozuv bor |
| 6 | Limitni o'zgartirish | Bot yangi limit bilan ishlaydi (deploysiz) |
| 7 | Texnik ta'til | Yoqilganda oddiy foydalanuvchi ogohlantirish oladi |
| 8 | Refund | To'lov «qaytarilgan» bo'ladi, Pro olinadi |
| 9 | Panelni yopib qayta ochish | Sessiya saqlanadi (12 soat) |
| 10 | Bot javoblari | Panel ishlayotganda javob tezligi o'zgarmagan |
| 11 | Kuzatuvga odam qo'shish | Uning keyingi xabari kuzatuv guruhiga tushadi (deploysiz) |
| 12 | Promokod yaratish | Bot `/promo` da o'sha kod qabul qilinadi |
| 13 | Bepul Pro (2 kishiga) | Ikkalasi ham xabar oladi, auditda ikkita yozuv |
| 14 | Admin qo'shish | Yangi adminda ko'k «Panel» tugmasi `/start` siz paydo bo'ladi |
| 15 | Admin `/start` bosadi | **Eski reply-klaviatura yo'qoladi**, «/» ro'yxatida `/xabar` va `/kod` paydo bo'ladi |
| 16 | `/xabar` | Tarqatma konstruktori ochiladi (ilgari «📢 Xabar yuborish» tugmasi qilardi) |
| 17 | `/kod` | Ikkita yuborish amali chiqadi; kod tanlab odamga yuboriladi, u bir bosishda faollashtiradi |
| 18 | Oddiy foydalanuvchining «/» ro'yxati | `/xabar` va `/kod` **KO'RINMAYDI** |
| 19 | Adminning eski xabaridagi tugmani bosish | Hech narsa bo'lmaydi (handler o'chgan) — bu kutilgan, panel yangi joy |

⚠️ 15-band eng muhimi: klaviatura faylini o'chirish uni telefondan
olib tashlamaydi. `/start` bosilmaguncha admin eski to'rt tugmani
ko'rib turadi va ular endi hech narsa qilmaydi.

---

## Tartib

```
✅ 1-bosqich — skelet va darvoza
✅ 2-bosqich — dizayn asosi
✅ 3-bosqich — boshqaruv + statistika
✅ 4-bosqich — foydalanuvchilar
✅ 5-bosqich — jurnal
✅ 6-bosqich — sozlamalar va promo
✅ 7-bosqich — Telegram ekranlarini o'chirish

Reja to'liq bajarildi. Qolgani — jonli tekshirish (10-bo'lim).
```

Maket: artifact (tasdiqlangan) — binafsha→moviy gradient, qora fon,
Sora + IBM Plex Sans + IBM Plex Mono. Logo — `/static/logo.jpg`
(3.2.1 ga qarang).
