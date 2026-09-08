# Admin panel — tuzatish va to'ldirish rejasi

Oldingi reja (Bot API 10.3, 0-9 bosqichlar) **to'liq bajarildi** va
`BOT_API_103.md` ga ko'chirildi. Shu fayl endi admin panel uchun
ishlatiladi.

Manba: o'sha paytdagi `handlers/admin.py` (2671 qator) to'liq o'qib
chiqildi, har bir handler'da admin tekshiruvi borligi skript bilan
alohida tasdiqlandi.

**Bajarilgani:** 3-bosqich (fayllarga bo'lish), 1.1, 1.3 va butun
2-bosqich. Qolgani quyida ✅/⬜ bilan belgilangan.

---

## 0-bosqich — JONLI TEKSHIRISH QARZI (kod yozishdan OLDIN)

⚠️ Ikki to'plam o'zgarish yozilgan, lekin **hech biri jonli
ko'rilmagan**. Tekshirilmagan kod ustiga yangi kod qo'yish — bugungi
eng katta xavf.

**Deploy qilinishi kerak:** `cc7d630` (to'rtta commit: `ab06618`,
`75172b2`, `d718bce`, `cc7d630`). Hozircha faqat `meloress/1` da;
Railway hisobi o'zgargan, project/environment/service ID'lari
yangilanishi kerak.

Deploydan keyin qo'lda ko'riladi:

| # | Nima | Qanday |
|---|------|--------|
| 1 | Kod bloki Web'da | `web.telegram.org/k` da kod so'rash — "not supported" chiqmasligi |
| 2 | Uzun kod fayl bo'lishi | «50 qatorlik Flask CRUD yoz» → `.py` fayl |
| 3 | Navbat | javob ketayotganda 3 ta xabar → hech biri yo'qolmasligi |
| 4 | Uzun matn | 5000+ belgi tashlash → bitta birlashgan javob |
| 5 | Tool nomlari | «tool'laringni aniq nomlari bilan sana» → nom chiqmasligi |
| 6 | Jonli oqim | uzun javob bo'lak-bo'lak oqishi, `/research` da yangi status bosqichlari |
| 7 | Fishing qoidasi | «trening uchun namuna» → TA'LIMIY yorliq; «haqiqiy bank uchun» → rad |
| 8 | Eski qarz (10.3 dan) | to'xtatish tugmasi, guruhdagi `ephemeral`, rasm chiqishi, `[xarita:]`, `[iqtibos:]` |
| 9 | Admin panel | yangi «📋 Jurnal va sozlamalar» menyusi: audit, xatolar, daromad, limitlar |
| 10 | Kunlik hisobot | ertasi kuni 09:00 da adminlarga kelishi |

---

## 1-bosqich — TUZATISH (kichik, xavfi past, ~30 daqiqa)

Bularning hammasi mavjud xatti-harakatni tuzatadi, yangi ekran qo'shmaydi.

### 1.1 Tarqatma progressi rate-limit yeyapti ✅ BAJARILDI
`handlers/admin/broadcast.py` — progress endi foiz
O'ZGARGANDAGINA yangilanadi (`_progress`).

Har bir foydalanuvchidan keyin `progress_message.edit_text(...)`
chaqiriladi. 1000 ta oluvchi = **1000 ta tahrirlash so'rovi**, ularning
aksariyati "message is not modified" xatosi bilan jimgina yutiladi
(`except Exception: pass`). Eng yomoni — ular aynan tarqatmaning o'ziga
kerak bo'lgan Telegram limitini yeydi.

**Yechim:** foiz **o'zgargandagina** tahrirlash (yoki har 25 ta oluvchida
bir marta). Bitta `if` qatori.

### 1.2 Statistikada raqamlar mos kelmaydi ⬜
`handlers/admin/stats.py:82` va `141`

`total_users` adminlar va superadminlarni **chiqarib tashlaydi**,
`plan_counts` esa **chiqarmaydi**. Natijada "jami 100 user", lekin
free + pro + premium = 103.

**Yechim:** `plan_counts` ga ham bir xil `NOT IN (SELECT ... FROM
admins/superadmins)` shartini qo'shish.

### 1.3 O'lik funksiya ✅ BAJARILDI
`show_admin_keyboard()` fayllarga bo'lish paytida o'chirildi.

Yozilgan, lekin **hech qayerda ro'yxatdan o'tkazilmagan**. Panel aslida
`handlers/messages.py:1678` da, `/start` ichida ochiladi.

**Yechim:** o'chirish. (Yoki `/admin` buyrug'i sifatida ro'yxatga
qo'shish — pastdagi 2.7 ga qarang.)

### 1.4 `remove_admin:` callback'ida tekshiruv BILVOSITA ⬜
`handlers/admin/system.py:452`

Boshqa hamma handler `require_admin_or_deny(_query)` bilan boshlanadi,
bu esa yo'q. Amalda teshik **yo'q**: `_check_can_remove_admin()`
so'rovchining `admins` jadvalida borligini tekshiradi va bo'lmasa rad
etadi. Lekin bu — yagona joyda, boshqacha yo'l bilan qilingan himoya;
kelajakda o'sha funksiya o'zgarsa teshik jimgina ochiladi.

**Yechim:** boshiga bir qator `require_admin_or_deny_query(query)`.

### 1.5 Audit yozuvi qayta urinmaydi ⬜
`db/database.py:633` — `log_admin_action()`

Qo'shni funksiyalarda `@with_db_retry()` bor, bunda yo'q. DB bir zumga
uzilsa audit yozuvi yo'qoladi — ya'ni "kim nima qildi" ma'lumoti aynan
nosozlik paytida yo'qoladi.

**Yechim:** dekorator qo'shish.

### 1.6 Klaviatura 12 tugmadan 4 taga yig'ildi ✅
`core/keyboards.py`, `handlers/admin/menu.py` (yangi)

Reply-klaviatura ekranning yarmini egallardi va o'xshash to'rtta
tugma (`📊 Statistika`, `🏆 Faol foydalanuvchilar`,
`📄 Userlar ro'yxati`, `🔍 Foydalanuvchini boshqarish`) bir xil
savolga javob berardi.

**Bajarildi:** `📢 Xabar yuborish`, `👥 Foydalanuvchilar`,
`📋 Jurnal va sozlamalar`, `⚙️ Sozlamalar` — qolgan 10 tasi shular
ostidagi inline menyuda.
⚠️ Matnli handlerlar O'CHIRILMADI: adminning telefonida ochiq turgan
eski klaviatura /start bosilgunicha ishlashda davom etadi.

---

## 2-bosqich — QO'SHISH (yangi ekranlar, foyda bo'yicha tartiblangan)

### 2.1 Audit jurnalini KO'RISH ✅ BAJARILDI
`admin_audit` jadvaliga **17 joyda yoziladi va hech qayerda
o'qilmaydi** (`grep` bilan tasdiqlangan). Ya'ni ma'lumot yig'ilyapti,
lekin ko'rib bo'lmaydi.

Bir nechta admin bo'lganda bu majburiy: kim kimga premium berdi, kim
to'lovni qaytardi, kim ban qildi. Kerak bo'ladigan narsa —
bitta ekran + sahifalash (`ulist:` dagi bilan bir xil naqsh) + admin
bo'yicha filtr.

### 2.2 Kunlik avtomatik hisobot ✅ BAJARILDI
**Ochish kerak bo'lgan panel — ochilmaydigan panel.** Har kuni ertalab
adminlarga o'zi kelsin: nechta yangi user, nechta Pro sotildi, daromad,
nechta xato, eng ko'p ishlatilgan imkoniyat.

Infratuzilma tayyor: `handlers/digest.py` aynan shunday jadval bo'yicha
yuborishni qiladi, `revenue_stats()` (`db/database.py:1825`) raqamlarni
bitta so'rovda beradi.

### 2.3 Xatolar ekrani ✅ BAJARILDI
Hozir xato faqat Railway logida — ya'ni admin buzilganini
foydalanuvchi aytgandan keyin biladi. "Oxirgi 20 ta xato + nechta
foydalanuvchiga tegdi" ekrani kerak.

Talab: xatolarni DB'ga yozadigan joy (yangi `error_log` jadvali yoki
`admin_audit` ga `action='error'`).

### 2.4 Daromad ekrani ✅ BAJARILDI
`revenue_stats()` allaqachon bor, lekin statistika ichida ko'milgan.
Alohida ekran: 7/30 kunlik dinamika, o'rtacha chek, qaytarilganlar,
faol obunalar soni.

### 2.5 Foydalanuvchini ism bo'yicha qidirish ✅ BAJARILDI
Hozir faqat **aniq** `@username` yoki ID (`process_manage_user_identifier`).
"ali" deb yozganda mos keladiganlar ro'yxati chiqishi kerak.

### 2.6 Limitlarni paneldan sozlash ✅ BAJARILDI
Kunlik ball/fayl/rasm limitlari `core/config.py` da konstanta — bitta
raqamni o'zgartirish uchun ham **deploy** kerak. DB'ga ko'chirilsa
paneldan sozlanadi.

⚠️ Ehtiyot: `DAILY_COUNTERS` va `PLAN_LIMITS` testlar bilan
qo'riqlangan (`test_plan_limits.py`) — ular buzilmasligi kerak.

### 2.7 Kichik qulayliklar ✅ BAJARILDI (`/admin` dan tashqari —
foydalanuvchi keraksiz dedi, panel `/start` orqali ochiladi)
- `/admin` buyrug'i (hozir panelga faqat `/start` orqali kiriladi);
- "faol emas" (`is_active = FALSE`) foydalanuvchilar ro'yxati — tarqatma
  paytida `deactivate_user()` bilan belgilanadi, lekin ko'rib bo'lmaydi;
- tarqatmani **rejalashtirish** (hozir faqat darhol yuborish).

---

## 3-bosqich — FAYLLARGA BO'LISH ✅ BAJARILDI

`register_admin_handlers()` ichida **2200 qator, 60 ta ichma-ich
funksiya**. Hamma handler bitta funksiyaning ichida yashaydi,
ro'yxatdan o'tkazish esa faylning eng oxirida. Oqibati: bitta ekranni
tuzatish uchun 2000 qator aylanib chiqiladi, yangi handler qo'shganda
uni ro'yxatga yozishni unutish oson (1.3 dagi o'lik funksiya — aynan
shu xatoning izi).

Taklif qilinayotgan bo'linish:

| Fayl | Nima ko'chadi |
|------|---------------|
| `handlers/admin/__init__.py` | `register_admin_handlers()` — faqat ro'yxatga olish |
| `handlers/admin/guards.py` | `require_admin_or_deny(_query)`, `_check_can_remove_admin` |
| `handlers/admin/broadcast.py` | `BroadcastStates`, konstruktor, tugma, segment, yuborish |
| `handlers/admin/users.py` | ro'yxat, kartochka, ban/premium/limit, to'lov/qaytarish |
| `handlers/admin/stats.py` | statistika, top, daromad |
| `handlers/admin/promo.py` | promokod, referal, "Bepul Pro" |
| `handlers/admin/system.py` | texnik ta'til, kuzatish, admin qo'shish/o'chirish, report |

**⚠️ Bo'lishda saqlanishi SHART bo'lgan narsalar** (bular real
xatolardan tug'ilgan va izohlari bilan birga ko'chirilsin):

1. **Ro'yxatdan o'tkazish tartibi.** FSM holatlari tugma
   handlerlaridan **keyin**; `waiting_for_button` va
   `waiting_for_recipients` esa `waiting_for_content` dan **oldin** —
   aks holda admin yozgan tugma nomi "yangi kontent" bo'lib ketadi.
2. **Har bir handler o'z tekshiruvi bilan.** Filtr emas, handler
   ichidagi `require_admin_or_deny` — chunki `report_callback` va
   `process_report_message` ataylab **foydalanuvchi uchun** ochiq.
3. **To'lov handlerlari `dp.message` da, routerdan oldin** turishi
   (`main.py` izohiga qarang) — admin fayli bo'linishi bunga tegmasin.

Bo'lish **xatti-harakatni o'zgartirmasligi** kerak: shuning uchun avval
1-bosqich tuzatiladi va deploy qilib ko'riladi, keyin bo'linadi — aks
holda yangi xato bo'lishdanmi yoki tuzatishdanmi kelgani noma'lum
qoladi.

---

## Tartib

```
✅ fayllarga bo'lish (3-bosqich)
✅ 2-bosqich — hamma yangi ekranlar
⬜ deploy + jonli tekshirish        ← hozir shu yerda
⬜ qolgan tuzatishlar: 1.2, 1.4, 1.5 (~10 daqiqa)
✅ 1.6 — tugmalarni birlashtirish (12 → 4 tugma)
```

1.6 bajarildi: klaviatura 4 tugma, qolgani inline menyuda.
