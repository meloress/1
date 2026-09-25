/* Panelning YAGONA lug'ati.
 *
 * ⚠️ Nega alohida fayl: matnlar `panel.js` ning o'n xil joyiga sochilib
 * ketgan edi va shuning uchun bir xil narsa ikki xil atalardi — pastki
 * navigatsiyada «Userlar», sahifa sarlavhasida «Foydalanuvchilar»;
 * ustunlarda «Matn · guest», izohda «mehmon rejimi». Bitta faylda
 * turgani bunday farqni KO'RINADIGAN qiladi: ikki qator yonma-yon
 * yozilsa, mos kelmagani darhol ko'zga tashlanadi.
 *
 * ⚠️ BU YERDA RO'YXAT YO'Q. Tarif nomlari, limit nomlari, qamrov
 * nomlari va audit amallari serverdan keladi (`/api/meta`,
 * `core/config.py`) — chunki ularni bot ham ishlatadi va ikki nusxa
 * bo'lishi mumkin emas. Bu fayl faqat PANELNING O'Z matnlari uchun.
 */
window.SOZ = {
  /* ── Ekranlar ──────────────────────────────────────────────── */
  ekran: {
    dash:      ["Boshqaruv", null],
    users:     ["Foydalanuvchilar", "yuklanmoqda…"],
    stats:     ["Statistika", "oxirgi 7 kun"],
    promo:     ["Promo va sovg'a", "kodlar, bepul Pro, referal"],
    journal:   ["Jurnal", "audit, xatolar, daromad"],
    system:    ["Sozlamalar", "limitlar, ta'til, kuzatish, adminlar"],
    broadcast: ["Tarqatma", "Telegramda boshqariladi"],
    profil:    ["Foydalanuvchi", null]
  },

  /* ── Umumiy holatlar ───────────────────────────────────────── */
  yoq: "—",
  yuklanmoqda: "Yuklanmoqda…",
  bajarilmoqda: "Bajarilmoqda…",
  yangilandi: "Yangilandi",
  qaytaUrinish: "Qayta urinish",
  yuklanmadi: "Ma'lumot yuklanmadi.",
  /* 409 \u2014 kartadagi ma'lumot eskirgan, panel profilni qayta yuklaydi. */
  eskirdi: "Profil yangilandi \u2014 raqamlarni tekshirib qayta urinib ko'ring.",
  saqlandi: "Saqlandi",
  bekorQilish: "Bekor qilish",
  bekorQilindi: "Bekor qilindi",
  nusxa: "Nusxalandi",

  /* Bo'sh holatlar — har biri «nega bo'sh» ni ham aytadi. */
  bosh: {
    token:     "Hali token sarfi yozilmagan.",
    xato:      "Bugun xato qayd etilmagan.",
    amal:      "Bu davrda amal qayd etilmagan.",
    audit:     "Hali admin amali yo'q.",
    promo:     "Hali promokod yaratilmagan.",
    kuzatuv:   "Kuzatuvda hech kim yo'q.",
    tolov:     "To'lov yo'q.",
    tarqatma:  "Rejalashtirilgan tarqatma yo'q.",
    user:      "Bu toifada foydalanuvchi yo'q.",
    qidiruv:   "Bunday foydalanuvchi topilmadi. Boshqa ID yoki @username bilan qidiring.",
    top:       "So'nggi 7 kunda faollik qayd etilmagan."
  },

  /* ── Sana ──────────────────────────────────────────────────── */
  oylar: ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul",
          "avgust", "sentabr", "oktabr", "noyabr", "dekabr"],
  hafta: ["Dush", "Sesh", "Chor", "Pay", "Jum", "Shan", "Yak"],
  bugun: "Bugun",
  kecha: "Kecha",
  hozirgina: "hozirgina",
  daqiqaOldin: " daqiqa oldin",
  soatOldin: " soat oldin",
  kunOldin: " kun oldin",

  /* ── Holat belgilari ───────────────────────────────────────── */
  holat: {
    ishlayapti: "Bot ishlayapti",
    tatil:      "Texnik ta'til",
    bazaYoq:    "Baza uzilgan"
  },
  tatilYoq: "O'chiq",
  tatilBor: "Yoqilgan",

  /* Kuzatuv guruhi banneri — Boshqaruv ekranining tepasida.
     Matn ANIQ bo'lsin: «nimadir ishlamayapti» emas, nima ishlamayapti
     va nima qilish kerak. Sabab serverdan keladi va shu yerda emas. */
  kuzatuvBanner: {
    yoq:         "Kuzatuv guruhi sozlanmagan",
    yoqIzoh:     "Ogohlantirishlar hech qayerga bormaydi. " +
                 "Sozlamalar → Kuzatuv bo'limidan guruhni ulang.",
    yetmayapti:  "Kuzatuv guruhiga xabar yetmayapti"
  },

  /* ── Foydalanuvchilar ──────────────────────────────────────── */
  user: {
    nomsiz:    "Foydalanuvchi",
    chip:      { all: "Hammasi", pro: "Pro", free: "Bepul",
                 ban: "Bloklangan", nofaol: "Botni bloklaganlar" },
    tartib:    { faollik: "Oxirgi faollik", yangi: "Ro'yxatdan o'tgan" },
    oxirgi:    "oxirgi faollik",
    royxatdan: "ro'yxatdan",
    cheksiz:   "cheksiz",
    gacha:     " gacha",
    yana:      "Yana yuklash",
    hammasi:   "Hammasi ko'rsatildi"
  },

  /* ── Promokodlar ───────────────────────────────────────────── */
  kod: {
    faol:     "Faol",
    tugagan:  "Limit tugagan",
    muddat:   "Muddati o'tgan",
    bekor:    "Bekor qilingan",
    muddatsiz: "muddatsiz",
    nusxa:    "Nusxalash",
    toxtat:   "To'xtatish",
    toxtatSavol: " kodi to'xtatilsinmi? Ishlatilganlar saqlanib qoladi, yangi odam ishlata olmaydi."
  },

  /* ── Limitlar ──────────────────────────────────────────────── */
  limit: {
    ozgargan:  "o'zgartirilgan",
    aslQaytar: "Asl qiymatga qaytarish",
    aslSavol:  "Asl qiymatga qaytarilsinmi? Ikkala tarif ham config'dagi songa qaytadi.",
    ozgarishYoq: "O'zgarish yo'q.",
    kuchga:    "O'zgarish darhol kuchga kiradi — bot shu zahoti yangi qiymat bilan ishlaydi.",
    manfiy:    "Limit manfiy bo'lishi mumkin emas.",
    bosh:      "Limit bo'sh qolmasin — asl qiymat uchun ↺ tugmasini bosing.",
    katta:     "Limit juda katta. Cheksizlik uchun alohida tarif bor."
  },

  /* ── Tasdiq savollari ──────────────────────────────────────── */
  savol: {
    ban:     "Foydalanuvchi bloklansinmi? U botga yoza olmay qoladi.",
    unban:   "Blok olib tashlansinmi?",
    free:    "Tarif bepulga tushirilsinmi? Qolgan kunlar bekor bo'ladi.",
    refund:  "To'lov qaytarilsinmi? Pul Telegram orqali qaytariladi va tarif olib tashlanadi.",
    adminQosh: "Bu odamga to'liq admin huquqi berilsinmi?",
    adminOl: "Admin huquqi olib tashlansinmi?",
    kuzatuvOl: "Kuzatuvdan olib tashlansinmi?",
    tatil:   "Texnik ta'til yoqilsinmi? Adminlardan boshqa hamma javob o'rniga ogohlantirish oladi.",
    sovga:   "Bepul Pro berilsinmi? Har biriga botdan xabar boradi.",
    tarqatma: "Rejalashtirilgan tarqatma bekor qilinsinmi?",

    /* ⚠️ TASDIQ MATNI AMALNI AYTSIN, "Ishonchingiz komilmi?" emas.
       Tasdiq odamni to'xtatish uchun emas — U NIMA QILAYOTGANINI
       KO'RSATISH uchun. "Ishonchingiz komilmi?" hech qanday yangi
       ma'lumot bermaydi, ya'ni o'qilmay bosiladi va tasdiq bo'lishdan
       to'xtaydi. Shuning uchun bu uchtasi funksiya: ular KIMGA,
       QANCHA va NIMA yuborilishini aytadi. */
    /* ⚠️ MATN HOZIRGI HOLATNI AYTSIN. Bu amal muddatni ALMASHTIRADI,
       ya'ni kartadagi «20 kun» ni o'chiradi \u2014 va admin buni tasdiq
       oynasida KO'RMASA, yo'qotganini ham bilmaydi. */
    proFree: function (kim, kun) {
      return kim + " ga " + kun + " kunlik Pro berilsinmi? Hozir bepul tarifda.";
    },
    proMuddat: function (kim, kun, qolgan, sana) {
      return kim + ": hozir " + qolgan + " kuni bor (" + sana +
             " gacha) \u2014 u o'chadi, muddat bugundan boshlab " + kun +
             " kun bo'ladi.";
    },
    /* ⛔️ ENG QATTIQ HOLAT: cheksiz tarif muddatliga almashadi va eski
       qiymat auditdan boshqa hech qayerda qolmaydi. */
    proCheksizdan: function (kim, kun) {
      return kim + " da hozir CHEKSIZ Pro bor. U O'CHADI va o'rniga " +
             kun + " kunlik muddat qo'yiladi. Cheksiz tarif qaytarilmaydi.";
    },
    /* Cheksiz — alohida matn: u boshqa chiplar bilan yonma-yon turadi
       va bitta bosishda MUDDATSIZ tarif beradi. */
    proCheksizga: function (kim) {
      return kim + " ga CHEKSIZ Pro berilsinmi?" +
             " Bu muddatsiz: avtomatik tugamaydi va faqat qo'lda" +
             " bekor qilinadi.";
    },
    eksport: function (nima, max) {
      return nima + " CSV fayli tayyorlansinmi? Eng ko'pi bilan " + max +
             " qator. Fayl Telegram chatingizga hujjat bo'lib keladi" +
             " \u2014 undan forward qilish mumkin.";
    },
    xabar: function (kim, parcha) {
      return kim + " ga botdan xabar yuborilsinmi?\n\n\u00ab" + parcha + "\u00bb";
    }
  },

  /* Eksport turlarining ko'rinadigan nomlari. Bu PANELNING o'z matni
     (bot uni ishlatmaydi), shuning uchun shu yerda. Chegara soni esa
     serverdan keladi (`/api/meta`) — u `api.py` dagi `EKSPORT_MAX`. */
  eksportNomi: {
    users:    "Foydalanuvchilar",
    audit:    "Admin amallari jurnali",
    payments: "To'lovlar"
  },

  /* ── Amal natijalari ───────────────────────────────────────── */
  natija: {
    pro:       "Pro berildi.",
    free:      "Bepul tarifga o'tkazildi.",
    kvota:     "Kunlik sanoqlar tiklandi.",
    ban:       "Bloklandi.",
    unban:     "Blok olib tashlandi.",
    xabar:     "Xabar yuborildi.",
    refund:    "Pul qaytarildi.",
    xabarYetmadi: " — lekin xabar yetmadi (botni bloklagan bo'lishi mumkin)",
    adminQosh: "Admin qo'shildi — «Panel» tugmasi unda darhol paydo bo'ladi.",
    adminOl:   "Admin o'chirildi.",
    kuzatuvQosh: "Kuzatuvga qo'shildi.",
    kuzatuvOl: "Kuzatuvdan olindi.",
    guruh:     "Kuzatuv guruhi yangilandi.",
    tatilYoq:  "Texnik ta'til o'chirildi.",
    tatilBor:  "Texnik ta'til YOQILDI.",
    matn:      "Matn saqlandi.",
    bajarilmadi: "Bajarilmadi"
  },

  /* ── Kirish ekrani ─────────────────────────────────────────── */
  kirish: {
    ruxsatYoq:  ["Ruxsat yo'q",
                 "Bu panel faqat adminlar uchun. Agar bu xato deb hisoblasangiz, superadminga murojaat qiling."],
    ulanmadi:   ["Ulanmadi",
                 "Server javob bermadi. Internetni tekshirib, qayta urinib ko'ring."],
    kop:        ["Juda ko'p urinish", "Bir daqiqadan so'ng qayta urinib ko'ring."],
    rad:        ["Kirish rad etildi", "Panelni Telegram ichidagi «Panel» tugmasi orqali oching."],
    yopildi:    ["Sessiya yopildi", "Panelni qayta ochish uchun Telegramdagi «Panel» tugmasini bosing."]
  }
};
