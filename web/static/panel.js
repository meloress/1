/* Web admin panel — brauzer tomoni.
 *
 * Tuzilishi: avval Telegram bilan ulanish, keyin darvoza
 * (`/api/session`), undan keyin lug'at (`/api/meta`), so'ngra ekranlar.
 *
 * ⚠️ Har bo'lak `qism()` ichida chaqiriladi: bitta vidjetdagi xato
 * butun navigatsiyani o'ldirmasligi kerak. Bitta IIFE ichida
 * `getElementById(...).onclick` null qaytarsa, undan KEYINGI hamma
 * narsa ishga tushmay qolardi — ekranlar almashmaydi, tab-panel jim
 * bo'ladi va sababi ko'rinmaydi.
 *
 * ⚠️ MATN BU YERDA YOZILMAYDI. Panelning o'z matnlari `soz.js` da,
 * botniki bilan umumiy ro'yxatlar (tarif, limit, qamrov nomlari)
 * serverdan `/api/meta` orqali keladi. Sabab `ADMIN.md` «Five label maps» da: shu
 * loyihada qo'lda ko'chirilgan ro'yxat BESH marta eskirgan.
 */
(function () {
  "use strict";

  /* ⚠️ `tg` — FAQAT HAQIQATAN Telegram ichida. Telegram skripti oddiy
     brauzerda ham `Telegram.WebApp` ni yaratadi (platform "unknown"),
     ya'ni `if (tg)` u yerda ham rost bo'lardi: limitlarning zaxira
     «Saqlash» tugmasi yashirin qolib, brauzerdan limit saqlab bo'lmasdi,
     «Chiqish» esa ko'rinmas `tg.close()` ni chaqirib, ma'lumotni ekranda
     qoldirardi. Telegram ichida `initData` doim bor, tashqarida — bo'sh. */
  var WA = window.Telegram && window.Telegram.WebApp;
  var tg = WA && WA.initData ? WA : null;
  var S = window.SOZ;
  var META = null;            // /api/meta — tarif va limit nomlari

  function qism(nom, fn) {
    try { fn(); } catch (e) { console.error("[panel] " + nom + ":", e); }
  }
  function $(id) { return document.getElementById(id); }

  /* ══ TELEGRAM ═══════════════════════════════════════════════════ */

  /* ⚠️ TEMA TELEGRAMDAN MEROS OLINADI. Ilgari panel qat'iy qora edi va
     Telegram sarlavhasini O'Z rangiga bo'yardi. Yorug' temadagi
     mijozda esa butun Telegram oq, panel qop-qora bo'lib chiqardi —
     bu «bitta dastur» emas, «ilova buzilgan» taassuroti.

     Endi teskarisi: panel Telegramning temasiga moslashadi va
     sarlavhani o'z FONI bilan bo'yaydi, ya'ni ikkalasi ham bir xil
     yorug'likda turadi. */
  function tema() {
    var t = (tg && tg.colorScheme) || null;
    if (t === "light" || t === "dark") document.documentElement.setAttribute("data-tema", t);
    // Ranglar CSS o'zgaruvchilarida — Telegram tugmalarini O'SHA
    // hisoblangan qiymatlar bilan bo'yaymiz, qotirilgan HEX bilan emas.
    var st = getComputedStyle(document.documentElement);
    var deep = st.getPropertyValue("--deep").trim();
    var void_ = st.getPropertyValue("--void").trim();
    if (!tg) return;
    try { tg.setHeaderColor(deep); } catch (e) {}
    try { tg.setBackgroundColor(void_); } catch (e) {}
    try { tg.setBottomBarColor(deep); } catch (e) {}
  }

  function telegram() {
    if (!tg) { tema(); return; }
    tg.ready();
    tg.expand();
    kengaytir();
    tema();
    tg.onEvent("themeChanged", tema);
    // Pastga tortish oynani yopib yuboradi — ro'yxatni aylantirayotgan
    // odam buni tasodifan qiladi. Eski mijozlarda metod yo'q.
    if (typeof tg.disableVerticalSwipes === "function") tg.disableVerticalSwipes();
    olcham();
    tg.onEvent("viewportChanged", olcham);
    if (typeof tg.onEvent === "function") {
      try { tg.onEvent("safeAreaChanged", olcham); } catch (e) {}
      try { tg.onEvent("contentSafeAreaChanged", olcham); } catch (e) {}
      // Face ID qulfi: Mini App yig'ilib qayta ochilganda (Bot API 8.0).
      try { tg.onEvent("deactivated", qulfChetda); } catch (e) {}
      try { tg.onEvent("activated", qulfQaytdi); } catch (e) {}
    }
    // Eski mijozda yuqoridagi hodisalar yo'q — ilovadan chiqish ham shu.
    // ⚠️ Bu tinglovchi `navigatsiya()` dagisidan OLDIN: qaytganda avval
    // qulf yopiladi, keyin ekran yuklash (qulf ostida) hech narsa qilmaydi.
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "hidden") qulfChetda();
      else qulfQaytdi();
    });
  }

  /* ══ KOMPYUTERDA TO'LIQ EKRAN ═══════════════════════════
     ⚠️ `expand()` faqat TELEFONDA ishlaydi — u Mini App'ni oynaning
     to'liq balandligiga yoyadi. Desktop va brauzerda esa Telegram
     panelni tor oynada ochadi va `expand()` unga umuman ta'sir
     qilmaydi, shuning uchun 1240px gacha moslashadigan maket telefon
     ko'rinishida qolib ketardi.

     ⚠️ «web» DEGAN PLATFORMA QIYMATI YO'Q. Telegram Web ikkita:
     `weba` (Web A) va `webk` (Web K). «web» deb yozilsa shart hech
     qachon bajarilmaydi va bag jimgina qoladi.

     Uchta himoya: metod bor-yo'qligi, mijoz versiyasi (Bot API 8.0)
     va try/catch. Eski mijozda uchinchisi ham kerak — `isVersionAtLeast`
     ba'zi qurilishlarda metod bo'lmasa ham `true` qaytaradi. */
  var KENG_EKRAN = ["tdesktop", "macos", "weba", "webk"];

  function kengaytir() {
    if (KENG_EKRAN.indexOf(tg.platform) < 0) return;
    if (typeof tg.requestFullscreen !== "function") return;
    if (typeof tg.isVersionAtLeast !== "function" || !tg.isVersionAtLeast("8.0")) return;
    try { tg.requestFullscreen(); } catch (e) {}
  }

  /* Oyna balandligi va XAVFSIZ CHEKKALAR.
     `safeAreaInset` — qurilmaning o'zi (jag'a, uy tugmasi chizig'i),
     `contentSafeAreaInset` — Telegramning o'z sarlavhasi. Ikkalasi
     qo'shiladi: sarlavha qurilmaning jag'asi tagida turishi mumkin. */
  function olcham() {
    var d = document.documentElement.style;
    var h = tg && tg.viewportStableHeight;
    if (h) d.setProperty("--vh", h + "px");
    var a = (tg && tg.safeAreaInset) || {};
    var b = (tg && tg.contentSafeAreaInset) || {};
    var tepa = (a.top || 0) + (b.top || 0);
    var past = (a.bottom || 0) + (b.bottom || 0);
    if (tepa) d.setProperty("--tepa", tepa + "px");
    if (past) d.setProperty("--past", past + "px");
  }

  /* Tebranish. «tanlov» — iOS'dagi vaqt g'ildiragi «chiq»i (selectionChanged):
     tab, filtr chipi, grafik bo'ylab barmoq. Tugma bosilishi — «light». */
  function titroq(turi) {
    if (!tg || !tg.HapticFeedback) return;
    try {
      if (turi === "tanlov") return tg.HapticFeedback.selectionChanged();
      if (turi === "ok") return tg.HapticFeedback.notificationOccurred("success");
      if (turi === "xato") return tg.HapticFeedback.notificationOccurred("error");
      tg.HapticFeedback.impactOccurred(turi || "light");
    } catch (e) {}
  }

  /* ── Pastdagi asosiy tugma (§3.4) ─────────────────────────────
     ⚠️ Ilgari Limitlar jadvalining HAR QATORIDA alohida «Saqlash»
     tugmasi turardi. Telefonda ular o'ng chetda kesilib qolardi va
     qatorga gorizontal siljish qo'shardi (§2.3). Endi saqlash bitta
     joyda — Telegramning o'z pastki tugmasida, va u faqat
     O'ZGARISH BO'LSA ko'rinadi. */
  var mbBosildi = null;

  function asosiyTugma(matn, fn) {
    if (!tg || !tg.MainButton) return;
    try {
      if (mbBosildi) tg.MainButton.offClick(mbBosildi);
      mbBosildi = null;
      if (!fn) return tg.MainButton.hide();
      mbBosildi = function () { titroq("medium"); fn(); };
      tg.MainButton.setText(matn);
      tg.MainButton.onClick(mbBosildi);
      tg.MainButton.show();
    } catch (e) {}
  }

  /* ══ TOAST ══════════════════════════════════════════════════════ */
  var toastTimer = null, bekorFn = null;

  function toast(matn, bekor) {
    var el = $("toast"), m = $("toast-matn"), b = $("toast-bekor");
    if (!el) return;
    m.textContent = matn;
    bekorFn = bekor || null;
    b.hidden = !bekor;
    b.textContent = S.bekorQilish;
    el.classList.add("on");
    clearTimeout(toastTimer);
    // 5 soniya — «Bekor qilish» uchun yetarli, lekin ekranni
    // to'sib turmaydigan muddat.
    toastTimer = setTimeout(function () { el.classList.remove("on"); }, 5000);
  }

  function toastYop() {
    clearTimeout(toastTimer);
    var el = $("toast");
    if (el) el.classList.remove("on");
    bekorFn = null;
  }

  /* ══ FACE ID QULFI ══════════════════════════════════════════════
     ⚠️ BU TELEFONDAGI QULF, SERVER DARVOZASI EMAS. Kirish huquqini hamon
     `initData` imzosi va `@admin_only` hal qiladi (WEB_PANEL.md). Qulf
     bitta xavfni yopadi: ochiq telefon BOSHQA ODAMNING qo'lida — Telegram
     ochiq, «Panel» tugmasi bir bosishda. Server buni ajrata olmaydi (imzo
     o'sha akkauntniki), shuning uchun tekshiruv telefonda, Telegram'ning
     BiometricManager'i orqali.

       • Faqat `ios` / `android` va Bot API 7.2+. Kompyuterda va brauzerda
         biometriya yo'q — u yerda qulf ham yo'q.
       • Holat Telegram CloudStorage'ida: `faceid` = "1" (yoqilgan), "0"
         (admin o'zi o'chirgan), yo'q — hali o'rnatilmagan, birinchi
         ochilishda so'raladi. ⚠️ localStorage EMAS: uni WebView bilan
         birga tozalab yuborish mumkin, CloudStorage esa Telegram serverida
         va unga faqat shu bot'ning Mini App kodi yoza oladi.
       • ⛔️ "1" bo'lsa-yu biometriya endi ishlamasa (telefon sozlamasida
         o'chirilgan) — panel OCHILMAYDI. Aks holda qulfni chetlab o'tish
         yo'li «Sozlamalar → Telegram → Face ID: o'chiq» bo'lardi.
       • Panel 1 daqiqadan ko'p chetda tursa — qaytganda yana qulflanadi.
       • Ma'lumot qulf ochilgandan KEYIN yuklanadi (`ichkariga`). */
  var TELEFON = ["ios", "android"];
  var QULF_KALIT = "faceid";
  var QULF_MUDDAT = 60000;
  var BM = null;              // tg.BiometricManager, init qilingan bo'lsa
  var qulfHolati = null;      // CloudStorage: "1" / "0" / null
  var qulfFaol = false;       // shu sessiyada qulf ishlayaptimi
  var qulfYopiq = false;      // hozir qulf ekrani turibdimi
  var qulfKutuvchi = null;    // qulf ochilganda chaqiriladi
  var chetdaVaqt = 0;         // panel qachon fonga ketgan

  function bmTayyor() {
    return new Promise(function (hal) {
      if (!tg || TELEFON.indexOf(tg.platform) < 0) return hal(null);
      if (typeof tg.isVersionAtLeast !== "function" || !tg.isVersionAtLeast("7.2")) return hal(null);
      var bm = tg.BiometricManager;
      if (!bm || typeof bm.init !== "function") return hal(null);
      // Javob kelmasa (eski yoki buzuq mijoz) — biometriyasiz telefon
      // bilan bir xil holat: qulf yo'q.
      var t = setTimeout(function () { hal(null); }, 4000);
      try {
        bm.init(function () { clearTimeout(t); hal(bm.isInited ? bm : null); });
      } catch (e) { clearTimeout(t); hal(null); }
    });
  }

  /* CloudStorage: `ol` → satr ("" — kalit yo'q) yoki null (o'qilmadi),
     `yoz` → true/false (xatoda null). ⚠️ "" va null FARQLI: "" — qulf hech
     qachon o'rnatilmagan, null — tarmoq xatosi (o'shanda ehtiyotkor yo'l). */
  function bulut(amal, kalit, qiymat) {
    return new Promise(function (hal) {
      var cs = tg && tg.CloudStorage;
      if (!cs || typeof tg.isVersionAtLeast !== "function" || !tg.isVersionAtLeast("6.9")) return hal(null);
      var t = setTimeout(function () { hal(null); }, 4000);
      function tamom(xato, javob) {
        clearTimeout(t);
        hal(xato ? null : (amal === "ol" ? (javob || "") : !!javob));
      }
      try {
        if (amal === "ol") cs.getItem(kalit, tamom);
        else cs.setItem(kalit, qiymat, tamom);
      } catch (e) { clearTimeout(t); hal(null); }
    });
  }

  function bioNomi() {
    var tur = BM && BM.biometricType;
    var ios = tg && tg.platform === "ios";
    if (tur === "face") return ios ? "Face ID" : "Yuz";
    if (tur === "finger") return ios ? "Touch ID" : "Barmoq izi";
    return "Biometriya";
  }

  function qulfKorsat(holat) {
    var nom = bioNomi(), t = S.qulf[holat](nom);
    $("qulf-sarlavha").textContent = t[0];
    $("qulf-matn").textContent = t[1];
    var och = $("qulf-och");
    och.textContent = (holat === "ruxsat" || holat === "yoq") ? S.qulf.qayta : S.qulf.och(nom);
    och.disabled = holat === "kut";
    // Telegram'ning shu bot uchun biometriya sozlamasi — faqat ruxsat
    // berilmaganda foydali; telefonning o'z sozlamasini u ochmaydi.
    $("qulf-sozlama").hidden = holat !== "ruxsat";
    korsat("qulf");
  }

  function bmSora() {
    return new Promise(function (hal) {
      try { BM.requestAccess({ reason: S.qulf.sabab }, function (ok) { hal(!!ok); }); }
      catch (e) { hal(false); }
    });
  }

  function bmTasdiqla() {
    return new Promise(function (hal) {
      try { BM.authenticate({ reason: S.qulf.sabab }, function (ok) { hal(!!ok); }); }
      catch (e) { hal(false); }
    });
  }

  async function qulfUrin() {
    if (!BM.isBiometricAvailable) return qulfKorsat("yoq");
    if (!BM.isAccessGranted) {
      // Bir marta rad etilgan ruxsatni Telegram qayta so'ramaydi —
      // faqat sozlamadan yoqiladi.
      var rad = BM.isAccessRequested;
      if (!rad) { qulfKorsat("kut"); rad = !await bmSora(); }
      if (rad) {
        // ⚠️ Qulf HECH QACHON o'rnatilmagan ("") — bu admin «kerak emas»
        // degani: panel ochiladi va "0" yoziladi (Sozlamalardan yoqiladi).
        // Aks holda birinchi ochilishdagi bitta «Ruxsat bermayman» panelni
        // telefonda butunlay yopib qo'yardi, o'chirish yo'li ham yo'q edi.
        // O'rnatilgan ("1") qulfda esa rad etish — chetlab o'tish urinishi.
        if (qulfHolati === "") return qulfVoz();
        return qulfKorsat("ruxsat");
      }
    }
    qulfKorsat("kut");
    // Tizim oynasi javobsiz qolsa tugma abadiy o'chiq turmasin.
    var t = setTimeout(function () { $("qulf-och").disabled = false; }, 15000);
    var ok = await bmTasdiqla();
    clearTimeout(t);
    if (!ok) return qulfKorsat("rad");
    titroq("ok");
    // Birinchi muvaffaqiyat — qulf «o'rnatildi»: endi biometriya o'chsa
    // ham panel ochilmaydi (yuqoridagi ⛔️).
    if (qulfHolati !== "1") { qulfHolati = "1"; bulut("yoz", QULF_KALIT, "1"); }
    qulfFaol = true;
    qulfOchildi();
  }

  var qulfVozKechildi = false;
  function qulfVoz() {
    qulfHolati = "0";
    qulfFaol = false;
    qulfVozKechildi = true;
    bulut("yoz", QULF_KALIT, "0");
    qulfOchildi();
  }

  function qulfOchildi() {
    qulfYopiq = false;
    var h = qulfKutuvchi;
    qulfKutuvchi = null;
    if (h) h();
  }

  /* Qulf ochilganda tugaydigan va'da. Kutilmagan xatoda — qulf yopiq
     qoladi (qayta urinish tugmasi bilan), o'zidan ochilib ketmaydi. */
  function qulfKut(ishgaTushir) {
    return new Promise(function (hal) {
      qulfKutuvchi = hal;
      qulfYopiq = true;
      Promise.resolve().then(ishgaTushir).catch(function (e) {
        console.error("[panel] qulf:", e);
        if (BM) qulfKorsat("rad");
        else qulfOchildi();
      });
    });
  }

  async function qulfBoshla() {
    BM = await bmTayyor();
    if (!BM) return qulfOchildi();
    qulfHolati = await bulut("ol", QULF_KALIT);
    if (qulfHolati === "0") return qulfOchildi();
    if (!BM.isBiometricAvailable && qulfHolati !== "1") return qulfOchildi();
    qulfFaol = true;
    await qulfUrin();
  }

  function qulfChetda() {
    if (qulfFaol && !qulfYopiq) chetdaVaqt = Date.now();
  }

  function qulfQaytdi() {
    if (!qulfFaol || qulfYopiq || !chetdaVaqt) return;
    var uzoq = Date.now() - chetdaVaqt > QULF_MUDDAT;
    chetdaVaqt = 0;
    if (!uzoq) return;
    // Qulf ostida Telegram tugmalari bosilmasin.
    asosiyTugma(null);
    if (tg && tg.BackButton) { try { tg.BackButton.hide(); } catch (e) {} }
    qulfKut(qulfUrin).then(function () {
      korsat("shell");
      sarlavhaHolati();
      orqaTugma();
      limitTugmasi();
      ekranYukla(hozir);
    });
  }

  /* Sozlamalar → Adminlar → «Shu telefon». Biometriya bor telefonda
     (yoki qulf allaqachon o'rnatilgan bo'lsa) ko'rinadi. */
  function qurilmaKartasi() {
    var k = $("qurilma");
    if (!k) return;
    k.hidden = !(BM && (BM.isBiometricAvailable || qulfHolati === "1"));
    if (k.hidden) return;
    var nom = bioNomi();
    $("face-nom").textContent = S.qulf.nomi(nom);
    $("faceSw").setAttribute("aria-label", S.qulf.nomi(nom));
    $("faceSw").setAttribute("aria-pressed", qulfFaol ? "true" : "false");
  }

  function qulfHodisalari() {
    $("qulf-och").addEventListener("click", function () {
      titroq("light");
      qulfUrin().catch(function (e) { console.error("[panel] qulf:", e); qulfKorsat("rad"); });
    });
    $("qulf-sozlama").addEventListener("click", function () {
      try { BM.openSettings(); } catch (e) {}
    });
    $("q-sozlama").addEventListener("click", function () {
      try { BM.openSettings(); } catch (e) {}
    });
    $("faceSw").addEventListener("click", async function () {
      if (!BM) return;
      var sw = this, nom = bioNomi();
      var yoqilsin = sw.getAttribute("aria-pressed") !== "true";
      $("q-sozlama").hidden = true;
      if (!yoqilsin && !await tasdiq(S.qulf.ochirSavol(nom))) return;
      if (!BM.isBiometricAvailable) return natijaChiz("q-natija", S.qulf.yoq(nom)[1], true);
      if (!BM.isAccessGranted) {
        if (BM.isAccessRequested || !await bmSora()) {
          $("q-sozlama").hidden = false;
          return natijaChiz("q-natija", S.qulf.ruxsat(nom)[1], true);
        }
      }
      // IKKALA yo'nalishda ham avval biometriya: o'chirishni faqat egasi
      // qila olsin, yoqishda esa u haqiqatan ishlashini ko'raylik.
      sw.disabled = true;
      var ok = await bmTasdiqla();
      sw.disabled = false;
      if (!ok) return natijaChiz("q-natija", S.qulf.rad(nom)[1], true);
      var yozildi = await bulut("yoz", QULF_KALIT, yoqilsin ? "1" : "0");
      if (!yozildi) return natijaChiz("q-natija", S.qulf.yozilmadi, true);
      qulfHolati = yoqilsin ? "1" : "0";
      qulfFaol = yoqilsin;
      sw.setAttribute("aria-pressed", yoqilsin ? "true" : "false");
      natijaChiz("q-natija", yoqilsin ? S.qulf.yoqildi(nom) : S.qulf.ochirildi(nom));
      toast(S.saqlandi);
    });
  }

  /* ══ DARVOZA ════════════════════════════════════════════════════ */
  function korsat(kim) {
    ["yuklash", "xato", "qulf", "shell"].forEach(function (id) {
      var el = $(id);
      if (el) el.hidden = id !== kim;
    });
    var tb = $("tabbar");
    if (tb) tb.hidden = kim !== "shell";
  }

  function xatoKorsat(juft) {
    var a = $("xato-sarlavha"), b = $("xato-matn");
    if (a) a.textContent = juft[0];
    if (b) b.textContent = juft[1];
    korsat("xato");
  }

  /* Avatar harflari. `ID:123` uchun harf yo'q — u yerda odam belgisi
     chiziladi (§4: ilgari bunday qatorda avatarda «I» turardi, ya'ni
     «ID» so'zining birinchi harfi, va bu hech narsani bildirmasdi). */
  function bosh(ism) {
    var s = String(ism || "").replace(/^@/, "");
    if (/^ID:/.test(s) || /^\d+$/.test(s)) return null;
    // Har qanday yozuvdagi HARF (`\p{L}`): ism endi Telegram'dan keladi —
    // arabcha, emoji, xitoycha ham bo'ladi. Ilgari faqat lotin/kirill
    // tanilardi va «🌸🌸🌸» yoki «محمد» avatari «?» bo'lib chiqardi.
    // Harf umuman bo'lmasa — `null`, ya'ni odam belgisi.
    var w = s.split(/[^\p{L}']+/u).map(function (x) {
      var m = x.match(/\p{L}/u);
      return m ? m[0] : "";
    }).filter(Boolean);
    if (!w.length) return null;
    return (w[0] + (w[1] || "")).toUpperCase();
  }

  var ODAM_SVG = '<svg class="ikon" viewBox="0 0 24 24" aria-hidden="true">' +
                 '<circle cx="12" cy="8" r="3.4"/><path d="M5 19a7 7 0 0 1 14 0"/></svg>';

  /* ⚠️ Avatarga KO'RINADIGAN nom emas, SHAXSIY nom beriladi. Farqi
     muhim: username yo'q odamning ekrandagi yozuvi «Foydalanuvchi»,
     va undan harf olinsa ro'yxatdagi HAMMA nomsiz odam bir xil «F»
     bo'lib chiqardi — ya'ni avatar hech narsani ajratmasdi. Bunday
     holda harf emas, odam belgisi chiziladi. */
  function avatar(shaxs, pro) {
    var h = bosh(shaxs);
    return '<div class="av' + (pro ? " pro" : "") + '">' +
           (h === null ? ODAM_SVG : xavfsiz(h)) + "</div>";
  }

  async function kir() {
    var r;
    try {
      r = await fetch("/api/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ init_data: (tg && tg.initData) || "" })
      });
    } catch (e) {
      return xatoKorsat(S.kirish.ulanmadi);
    }

    if (!r.ok) {
      // Imzo eskirgan bo'lishi mumkin (panel uzoq ochiq turib qayta
      // yuklangan) — 12 soatlik cookie aynan shuning uchun bor.
      var c = null;
      try { c = await fetch("/api/me", { headers: imzo() }); } catch (e) {}
      if (c && c.ok) return ichkariga(await c.json());
      if (r.status === 403) return xatoKorsat(S.kirish.ruxsatYoq);
      if (r.status === 429) return xatoKorsat(S.kirish.kop);
      return xatoKorsat(S.kirish.rad);
    }
    ichkariga(await r.json());
  }

  async function ichkariga(ma) {
    // ⛔️ Face ID — HAMMA NARSADAN OLDIN: na ism, na raqam qulfdan oldin
    // chizilmaydi. Sessiya (cookie) esa allaqachon ochilgan — `initData`
    // 5 daqiqada eskiradi, qulf ekranida ko'proq turilsa kirish yo'qolardi.
    await qulfKut(qulfBoshla);
    qism("qurilma", qurilmaKartasi);
    var ism = (ma && ma.ism) || "Admin";
    var n = $("who-ism"), a = $("who-av"), r = $("who-rol");
    if (n) n.textContent = ism;
    if (a) a.innerHTML = bosh(ism) === null ? ODAM_SVG : xavfsiz(bosh(ism));
    if (r && ma && ma.rol) r.textContent = ma.rol;
    korsat("shell");
    olcham();
    sarlavhaHolati();          // panel endi ko'rinadi — o'lchamlar haqiqiy
    if (qulfVozKechildi) toast(S.qulf.vozKechildi(bioNomi()));

    // ⚠️ Lug'at ekranlardan OLDIN. Tarif nomlari undan olinadi va
    // ular bo'lmasa jadval «undefined» bilan chiziladi.
    try { META = await ol("/api/meta"); } catch (e) { META = null; }
    if (!META) META = { tariflar: {}, ranglar: {}, limitlar: {}, limit_izohi: {},
                        // `EKSPORT_MAX` ning zaxirasi: lug'at kelmasa
                        // tasdiq matni «0 qator» deb yolg'on gapirmasin.
                        eksport_max: 5000, sovga_max: 20, kun_max: 3650,
                        grafik_kunlari: [7, 30, 90] };

    qism("chiplar", chiplarniChiz);
    kirdi = true;
    ekranYukla(hozir);
  }

  function tarifNomi(kalit) {
    if (kalit === "ban") return S.user.chip.ban;
    return (META.tariflar && META.tariflar[kalit]) || kalit;
  }
  function tarifRangi(kalit) {
    return (META.ranglar && META.ranglar[kalit]) || "var(--ink-3)";
  }
  function yorliq(kalit) {
    var sinf = kalit === "ban" ? "tag ban" : (kalit === "free" ? "tag" : "tag pro");
    return '<span class="' + sinf + '">' + xavfsiz(tarifNomi(kalit)) + "</span>";
  }

  /* ══ EKRANLAR ═══════════════════════════════════════════════════ */
  var BOSH_EKRAN = "dash";
  var hozir = BOSH_EKRAN;
  var oxirgiRoyxat = "users";   // profildan qaytadigan joy

  function bugunMatn() {
    // Server Toshkent vaqtida ishlaydi, panel esa istalgan mintaqada
    // ochilishi mumkin — shuning uchun vaqt ATAYLAB Asia/Tashkent'ga
    // o'giriladi. Oy nomlari qo'lda: `uz-UZ` hamma mijozda yo'q.
    var p = qismlar(new Date());
    if (!p) return S.bugun.toLowerCase();
    return "bugun · " + (+p.day) + "-" + S.oylar[+p.month - 1] + ", " +
           p.hour + ":" + p.minute;
  }

  function qismlar(d) {
    try {
      var p = {};
      new Intl.DateTimeFormat("en-GB", {
        timeZone: "Asia/Tashkent", year: "numeric", day: "numeric",
        month: "numeric", hour: "2-digit", minute: "2-digit", hour12: false
      }).formatToParts(d).forEach(function (x) { p[x.type] = x.value; });
      return p;
    } catch (e) { return null; }
  }

  /* Sarlavha ikki joyda: tepadagi kichik (`#title`) va telefondagi katta
     (`#katta-…`). Bitta funksiya — ikkalasi hech qachon farq qilmasin. */
  function sarlavhaYoz(sarlavha, izoh) {
    [["title", "katta-sarlavha", sarlavha], ["crumb", "katta-crumb", izoh]].forEach(function (q) {
      if (q[2] === undefined) return;
      [q[0], q[1]].forEach(function (id) { var el = $(id); if (el) el.textContent = q[2]; });
    });
  }

  function telefonmi() {
    return !!(window.matchMedia && window.matchMedia("(max-width:900px)").matches);
  }

  /* Bo'limni almashtirish — View Transitions bor joyda silliq. Brauzer
     eskisini suratga oladi, `fn` DOM'ni o'zgartiradi, keyin ikkalasi
     orasida o'tadi. Yo'q joyda (yoki «kamroq harakat» tanlanganda) —
     darhol, hozirgidek. */
  function otish(fn) {
    var kam = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    // Kirishdan oldin panel yashirin — suratga olinadigan narsa yo'q.
    if (!document.startViewTransition || kam || !kirdi) return fn();
    var vt;
    try { vt = document.startViewTransition(fn); } catch (e) { return fn(); }
    // Tez ketma-ket bosishda brauzer oldingi o'tishni BEKOR qiladi (`fn`
    // baribir bajariladi) va uning va'dalari rad etiladi — ushlanmasa
    // konsolda «Transition was skipped» istisnosi qoladi.
    ["ready", "finished", "updateCallbackDone"].forEach(function (k) {
      if (vt && vt[k] && vt[k].catch) vt[k].catch(function () {});
    });
  }

  /* ══ PROFIL VARAG'I (telefon) ══════════════════════════════════
     ⚠️ Telefonda profil ALOHIDA EKRAN EMAS, ro'yxat USTIDAN chiqadigan
     varaq: ro'yxat orqada turadi va o'sha joyida qoladi. Ilgari profil
     butun ekranni almashtirardi va «Orqaga» ro'yxatni TEPASIGA qaytarardi
     — 3-sahifaning o'rtasidagi odamni ko'rib qaytgan admin joyini
     yo'qotardi. Kompyuterda profil avvalgidek ichki sahifa (§3.1). */
  var varaq = false;

  function pardaKorsat(yengil) {
    var p = $("parda");
    if (!p) return;
    p.classList.toggle("yengil", !!yengil);
    p.style.opacity = "";
    p.hidden = false;
  }

  function varaqYop(keyin) {
    var sec = document.querySelector('section[data-screen="profil"]');
    var p = $("parda");
    var tugadi = false;
    function tamom() {
      if (tugadi) return;
      tugadi = true;
      varaq = false;
      sec.classList.remove("on");
      sec.style.transition = sec.style.transform = "";
      if (p) { p.hidden = true; p.style.transition = p.style.opacity = ""; }
      document.documentElement.classList.remove("varaqli");
      keyin();
    }
    // Barmoq qoldirgan joydan (yoki 0 dan) pastga — iOS varag'idek.
    sec.style.transition = "transform .28s cubic-bezier(.32,.72,0,1)";
    sec.style.transform = "translateY(100%)";
    if (p) { p.style.transition = "opacity .28s"; p.style.opacity = "0"; }
    var kam = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (kam) return tamom();
    sec.addEventListener("transitionend", tamom, { once: true });
    setTimeout(tamom, 360);          // transitionend kelmasa ham
  }

  function go(name, pane) {
    // Varaq ochiq — avval u pastga tushadi, keyin haqiqiy o'tish.
    if (varaq && name !== "profil") {
      return varaqYop(function () { goIchki(name, pane, true); });
    }
    goIchki(name, pane, false);
  }

  function goIchki(name, pane, varaqdan) {
    // ⚠️ Profil — ICHKI sahifa, ya'ni u ochilganda pastdagi tab
    // «Foydalanuvchilar» bo'lib yonib turishi kerak: odam o'sha
    // bo'limning ichida.
    var faol = name === "profil" ? "users" : name;
    var varaqqa = name === "profil" && telefonmi();
    var qayta = varaqqa && varaq;               // varaq allaqachon ochiq
    var orqa = oxirgiRoyxat;
    if (name !== "profil") oxirgiRoyxat = name;
    hozir = name;

    function chiz() {
      document.querySelectorAll("section[data-screen]").forEach(function (s) {
        // Varaq ostida o'zi ochilgan ro'yxat ko'rinib turadi.
        s.classList.toggle("on", s.dataset.screen === name ||
                                 (varaqqa && s.dataset.screen === orqa));
      });
      document.querySelectorAll("#nav button, #tabbar button").forEach(function (b) {
        if (b.dataset.go) b.setAttribute("aria-current", b.dataset.go === faol ? "true" : "false");
      });
      // Varaqda sarlavha O'ZGARMAYDI — orqadagi bo'lim nomi qoladi.
      if (!varaqqa) {
        var t = S.ekran[name] || ["", ""];
        sarlavhaYoz(t[0], t[1] === null ? bugunMatn() : t[1]);
      }
      if (pane) showPane(name, pane);
      // Varaqni ochish/yopish ro'yxatni TEPAGA qaytarmaydi — joyi saqlanadi.
      if (!varaqqa && !varaqdan) window.scrollTo({ top: 0, behavior: "instant" });
      if (varaqqa && !qayta) {
        var sec = document.querySelector('section[data-screen="profil"]');
        sec.scrollTop = 0;
        varaq = true;
        pardaKorsat(false);
        document.documentElement.classList.add("varaqli");
      }
      sarlavhaHolati();
    }
    // Varaq o'zining animatsiyasi bilan chiqadi — View Transition faqat
    // bo'limdan bo'limga (va kompyuterdagi profilga).
    if (varaqqa || varaqdan) chiz();
    else otish(chiz);
    orqaTugma();
    limitTugmasi();
    ekranYukla(name);
  }

  /* ⚠️ «Orqaga» FAQAT ICHKI SAHIFADA (§3.1). Ilgari u bosh ekrandan
     boshqa HAMMA joyda ko'rinardi — ya'ni Promo, Jurnal va Sozlamalar
     go'yo Boshqaruvning ichida joylashgandek tuyulardi, holbuki ular
     pastdagi tablar, ya'ni teng darajadagi bo'limlar. Endi u faqat
     foydalanuvchi profili ochilganda chiqadi. */
  function orqaTugma() {
    if (!tg || !tg.BackButton) return;
    try {
      if (hozir === "profil") tg.BackButton.show();
      else tg.BackButton.hide();
    } catch (e) {}
  }

  function showPane(screen, pane) {
    var sec = document.querySelector('section[data-screen="' + screen + '"]');
    if (!sec) return;
    sec.querySelectorAll(".subtabs button").forEach(function (b) {
      var faol = b.dataset.pane === pane;
      b.setAttribute("aria-current", faol ? "true" : "false");
      // Tab qatori tor ekranda aylanadi — faol tab KO'RINIB tursin.
      // Ilgari 360px'da «Adminlar» bosilsa ham u ekrandan tashqarida
      // qolib, faqat ostki chizig'ining bir bo'lagi ko'rinardi.
      if (faol && b.scrollIntoView) {
        try { b.scrollIntoView({ block: "nearest", inline: "nearest" }); } catch (e) {}
      }
    });
    sec.querySelectorAll(".pane").forEach(function (p) {
      p.classList.toggle("on", p.dataset.pane === pane);
    });
    limitTugmasi();
  }

  function navigatsiya() {
    /* ⚠️ ESKI NATIJA QOLMASIN. Kartochkadagi har bir tugma bosilganda
       o'sha kartochkaning natija qatori AVVAL tozalanadi (capture bosqichi —
       tugmaning o'z ishlovchisidan oldin), keyin ishlovchi yangisini
       yozadi. Ilgari bloklash yoki qaytarish bekor qilinsa ham ostida
       oldingi amalning «Kunlik sanoqlar tiklandi.» xabari turaverardi —
       admin uni yangi amalning natijasi deb o'qirdi. Har ishlovchida
       alohida tozalash — o'n beshta joy, bittasi albatta unutiladi. */
    document.addEventListener("click", function (e) {
      var b = e.target && e.target.closest && e.target.closest("button");
      var karta = b && b.closest(".card");
      if (!karta) return;
      karta.querySelectorAll(".natija").forEach(function (n) {
        n.innerHTML = "&nbsp;";
        n.className = "natija";
      });
    }, true);

    document.querySelectorAll("[data-go]").forEach(function (b) {
      b.addEventListener("click", function () {
        titroq("light");
        go(b.dataset.go, b.dataset.pane);
      });
    });
    document.querySelectorAll(".subtabs").forEach(function (bar) {
      bar.addEventListener("click", function (e) {
        var b = e.target.closest("button");
        if (!b) return;
        titroq("tanlov");
        showPane(bar.dataset.tabs, b.dataset.pane);
      });
    });
    if (tg && tg.BackButton) {
      tg.BackButton.onClick(function () { titroq("light"); go(oxirgiRoyxat); });
    }
    // Telegram'dan / boshqa ilovadan panelga qaytdi — eskirgan bo'lsa yangilansin.
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "visible") ekranYukla(hozir);
    });
    go(BOSH_EKRAN);
  }

  /* ══ SERVER ═════════════════════════════════════════════════════ */

  /* ⚠️ HAR SO'ROVGA TELEGRAM IMZOSI (§3.5). Cookie o'z-o'zicha yetarli
     edi, lekin u BIZNING imzomiz; `initData` esa Telegramniki va uni
     server bot tokeni bilan har safar qayta hisoblaydi. Ya'ni cookie
     o'g'irlangan taqdirda ham so'rov imzosiz o'tmaydi. */
  function imzo(qoshimcha) {
    var h = qoshimcha || {};
    if (tg && tg.initData) h["X-Telegram-Init-Data"] = tg.initData;
    return h;
  }

  /* ⚠️ Minglik ajratgich — BO'LINMAYDIGAN bo'shliq (U+00A0). Ilgari u
     oddiy bo'shliqqa almashtirilardi va son satr oxirida bo'linib
     ketardi: «75 / 000 so'm», «408 / 846». Tor ajratgich (U+202F) ham
     shunga keltiriladi — u ba'zi shriftlarda ko'rinmaydi. */
  function son(n) {
    return Number(n || 0).toLocaleString("ru-RU").replace(/[,\u202f ]/g, "\u00a0");
  }
  function foiz(v, kasr) {
    // `null` = ma'lumot yo'q (bo'luvchi nol edi). «0%» bilan aralashib
    // ketmasligi kerak — server ataylab shu farqni yuboradi.
    return v === null || v === undefined ? S.yoq : v.toFixed(kasr || 0) + "%";
  }
  function xavfsiz(s) {
    // Xato matni va username bazadan keladi, ya'ni ular BEGONA matn.
    return String(s === null || s === undefined ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /* Tasdiq oynasi uchun matnning boshi. Uzun xabar butunlay
     ko'rsatilsa tasdiq o'qilmaydigan devorga aylanadi. */
  function parcha(matn, uzunlik) {
    var t = String(matn || "").replace(/\s+/g, " ").trim();
    var n = uzunlik || 80;
    return t.length > n ? t.slice(0, n) + "\u2026" : t;
  }

  /* ⚠️ 401 = cookie (12 soat) tugagan. Jimgina qayta kirib bo'lmaydi:
     `/api/session` 5 daqiqadan eski initData'ni qabul qilmaydi (qayta
     ishlatishga qarshi). Ilgari har ekranda «Yuklanmadi · Qayta urinish»
     chiqardi va urinish HECH QACHON ishlamasdi — endi to'g'ri gap. */
  function sessiyaTugadimi(r) {
    if (r.status === 401 && kirdi) { kirdi = false; xatoKorsat(S.kirish.tugadi); }
  }

  async function ol(yol) {
    var r = await fetch(yol, { headers: imzo() });
    sessiyaTugadimi(r);
    if (!r.ok) throw new Error(yol + " → " + r.status);
    return r.json();
  }

  /* Qidiruv poygasi: sekin tarmoqda «ali» javobi «alisher» dan KEYIN
     kelib, ekranni eski natija bilan yozib qo'yardi. Har so'rovga
     raqam; javob kelganda u eng oxirgisi bo'lmasa — tashlanadi. */
  var navbat = {};
  function navbatOl(kalit) { return (navbat[kalit] = (navbat[kalit] || 0) + 1); }
  function eskirganmi(kalit, n) { return n !== navbat[kalit]; }

  /* ══ SANA ═══════════════════════════════════════════════════════
     Server ISO-8601 (Toshkent siljishi bilan) yuboradi, formatlash
     shu yerda. §2.7: telefonda «14.09.2026 21:34» ikki qatorga
     bo'linib, qatorni ikki barobar baland qilardi. Endi uch shakl:
       nisbiy  — «2 soat oldin» (yaqin sana uchun eng o'qiluvchan)
       qisqa   — «14.09, 21:34»
       kun     — «14-sentabr» (guruh sarlavhasi)                     */

  function pars(iso) {
    if (!iso) return null;
    var d = new Date(iso);
    return isNaN(d.getTime()) ? null : d;
  }

  function nisbiy(iso) {
    var d = pars(iso);
    if (!d) return S.yoq;
    var s = (Date.now() - d.getTime()) / 1000;
    if (s < 0) return qisqa(iso);
    if (s < 60) return S.hozirgina;
    if (s < 3600) return Math.floor(s / 60) + S.daqiqaOldin;
    if (s < 86400) return Math.floor(s / 3600) + S.soatOldin;
    if (s < 86400 * 7) return Math.floor(s / 86400) + S.kunOldin;
    return qisqa(iso);
  }

  function qisqa(iso) {
    var d = pars(iso), p = d && qismlar(d);
    if (!p) return S.yoq;
    return ikki(p.day) + "." + ikki(p.month) + ", " + p.hour + ":" + p.minute;
  }

  function soat(iso) {
    var d = pars(iso), p = d && qismlar(d);
    return p ? p.hour + ":" + p.minute : S.yoq;
  }

  function faqatKun(iso) {
    var d = pars(iso), p = d && qismlar(d);
    return p ? p.year + "-" + ikki(p.month) + "-" + ikki(p.day) : "";
  }

  /* «Bugun» / «Kecha» / «14-sentabr» — jurnal guruhi sarlavhasi. */
  function kunNomi(iso) {
    var p = qismlar(pars(iso) || new Date());
    if (!p) return S.yoq;
    var bugun = qismlar(new Date());
    var kecha = qismlar(new Date(Date.now() - 86400000));
    var k = faqatKun(iso);
    if (bugun && k === bugun.year + "-" + ikki(bugun.month) + "-" + ikki(bugun.day)) return S.bugun;
    if (kecha && k === kecha.year + "-" + ikki(kecha.month) + "-" + ikki(kecha.day)) return S.kecha;
    return (+p.day) + "-" + S.oylar[+p.month - 1];
  }

  function ikki(v) { return String(v).length < 2 ? "0" + v : String(v); }

  /* ══ HOLAT KO'RINISHLARI (§5) ═══════════════════════════════════ */
  function skelet(joy, qator) {
    var el = typeof joy === "string" ? $(joy) : joy;
    if (!el) return;
    var s = "";
    for (var i = 0; i < (qator || 3); i++) s += "<i></i>";
    el.innerHTML = '<div class="skelet">' + s + "</div>";
  }

  /* KPI raqamlarini yuklanish holatiga qo'yadi.
     ⚠️ JONLI BAG: `/api/overview` 500 qaytarganda ekranda beshta
     statik «—» qolardi va hech narsa «yuklanmadi» demasdi — admin
     panel ishlayapti deb o'ylab, sababni faqat serverdan topgan edi. */
  function kpiSkelet(idlar) {
    idlar.forEach(function (id) {
      var el = $(id);
      if (el) el.innerHTML = '<span class="skelet-kpi"></span>';
    });
  }

  function boshHolat(matn) {
    return '<div class="holat-bosh"><span>' + xavfsiz(matn) + "</span></div>";
  }

  function xatoHolat(qaytaFn) {
    var el = document.createElement("div");
    el.className = "holat-bosh";
    el.innerHTML = "<span>" + xavfsiz(S.yuklanmadi) + "</span>";
    var b = document.createElement("button");
    b.className = "btn sm";
    b.textContent = S.qaytaUrinish;
    b.addEventListener("click", qaytaFn);
    el.appendChild(b);
    return el;
  }

  /* «Yangilandi: HH:MM» — §5. Ekran ma'lumoti bir marta yuklanadi,
     ya'ni admin ko'rayotgan raqam qachonlik ekanini bilishi kerak. */
  function yangilandiBelgisi() {
    // Profil varag'i ochiq bo'lsa sarlavha orqadagi bo'limniki — tegilmaydi.
    if (hozir === "profil" && varaq) return;
    var t = S.ekran[hozir] || ["", ""];
    var asos = t[1] === null ? bugunMatn() : (t[1] || "");
    sarlavhaYoz(undefined, asos + (asos ? " · " : "") +
      S.yangilandi.toLowerCase() + " " + soat(new Date().toISOString()));
  }

  /* ══ KATTA SARLAVHA (telefon) ══════════════════════════════════
     iOS'dagidek: ekran tepasida katta nom; pastga aylantirilib u
     tepadagi panel ostiga kirganda — panelda kichik nom paydo bo'ladi. */
  function sarlavhaHolati() {
    var tb = $("topbar"), k = $("katta");
    if (!tb || !k) return;
    // ⚠️ Panel hali yashirin (kirishdan oldin) yoki kompyuter maketi —
    // katta sarlavhaning o'lchami 0, ya'ni «ekrandan chiqib ketgan»
    // ko'rinadi. Ilgari aynan shu holatda ochilishda ikkala sarlavha
    // birga ko'rinardi.
    var ixcham = telefonmi() && k.offsetHeight > 0 &&
      k.getBoundingClientRect().bottom <= tb.getBoundingClientRect().bottom + 2;
    tb.classList.toggle("ixcham", ixcham);
  }

  function kattaSarlavha() {
    var kutuv = false;
    window.addEventListener("scroll", function () {
      if (kutuv) return;
      kutuv = true;
      requestAnimationFrame(function () { kutuv = false; sarlavhaHolati(); });
    }, { passive: true });
    window.addEventListener("resize", sarlavhaHolati);
  }

  function ustunlarChiz(joy, royxat) {
    var el = $(joy);
    if (!el) return;
    if (!royxat.length) { el.innerHTML = boshHolat(S.bosh.amal); return; }
    var eng = Math.max.apply(null, royxat.map(function (t) { return t.soni; })) || 1;
    el.innerHTML = royxat.map(function (t, i) {
      // «Boshqa» — nomlanmagan turlar yig'indisi; u yetakchi bo'lib
      // ko'rinmasligi kerak, shuning uchun kulrang.
      var sinf = t.boshqa ? " kul" : (i === 0 ? " top" : "");
      return '<div class="bar"><span>' + xavfsiz(t.nom) + "</span>" +
             '<div class="track"><div class="fill' + sinf + '" style="width:' +
             Math.max(3, t.soni / eng * 100).toFixed(1) + '%"></div></div>' +
             '<b class="n">' + son(t.soni) + "</b></div>";
    }).join("");
  }

  /* Tarif doirasi + FOIZLI ro'yxat.
     ⚠️ Doiraning o'zi yetarli emas: 230 tadan 1 ta segment yarim
     piksel kenglikda chiqadi va umuman ko'rinmaydi. Shuning uchun
     yonida raqam va foiz yoziladi (§4). */
  function tarifChiz(ratioId, ulushId, t) {
    var jami = t.jami || 1;
    var ratio = $(ratioId), ulush = $(ulushId);
    if (ratio) ratio.innerHTML = t.qismlar.map(function (q) {
      return q.soni ? '<i style="width:' + (q.soni / jami * 100).toFixed(2) +
                      '%;background:' + xavfsiz(q.rang) + '"></i>' : "";
    }).join("");
    if (ulush) ulush.innerHTML = t.qismlar.map(function (q) {
      return '<div class="u"><i style="background:' + xavfsiz(q.rang) + '"></i>' +
             xavfsiz(q.nom) + '<b>' + son(q.soni) + "</b>" +
             '<span class="p">' + foiz(q.foiz, 1) + "</span></div>";
    }).join("");
  }

  /* Token sarfi: bugungi raqam va kunlik grantga nisbatan chiziq.
     ⚠️ Grant CHEKLOV EMAS — undan oshgan token baribir ishlaydi,
     faqat pulli bo'ladi. Shuning uchun matn «bloklandi» demaydi. */
  function tokenChiz(t) {
    if (!t || !$("k-token")) return;
    $("k-token").textContent = million(t.bugun);
    var bar = $("k-token-bar");
    bar.style.width = Math.min(100, t.foiz) + "%";
    bar.className = t.oshgan ? "over" : (t.foiz >= 80 ? "warn" : "");

    // Grant kuni UTC — Toshkentda 05:00 da yangilanadi (platforma bilan bir xil).
    var qism = [t.foiz + "% · " + million(t.grant) + " dan", "05:00 da yangilanadi"];
    if (t.keshdan !== null && t.keshdan !== undefined) {
      qism.push("keshdan " + t.keshdan + "%");
    }
    // Kecha grantdan oshgan bo'lsa buni AYTAMIZ: oshgan qismi pulli.
    if (t.kecha_oshgan) qism.push("kecha oshgan");
    $("k-token-d").innerHTML = t.oshgan
      ? '<b class="down">grantdan oshdi</b> · ' + xavfsiz(qism.join(" · "))
      : xavfsiz(qism.join(" · "));
  }

  /* Telegram Business kartasi (REJA.md 4.5). Token yo'q kunda ulush
     «—»: o'lchanmagan narsa 0% emas. */
  function biznesChiz(b) {
    if (!b || !$("b-ulanish")) return;
    $("b-ulanish").textContent = son(b.ulanishlar);
    $("b-sorov").textContent = son(b.sorovlar);
    $("b-token").textContent = b.ulush === null || b.ulush === undefined
      ? "—" : million(b.token) + " · " + b.ulush + "%";
  }

  /* VAQTINCHALIK «Ko'chish» kartasi. `k` null — eski bot o'chirilgan,
     karta yashirin qoladi. Foiz faqat «o'tganlar» yonida: bitta ulush
     yetadi, ikkinchisi undan kelib chiqadi. */
  function kochishChiz(k) {
    var karta = $("kochish");
    if (!karta) return;
    karta.hidden = !k;
    if (!k) return;
    var jami = (k.otgan || 0) + (k.qolgan || 0);
    $("ko-otgan").textContent = son(k.otgan) +
      (jami ? " · " + Math.round(k.otgan / jami * 100) + "%" : "");
    $("ko-qolgan").textContent = son(k.qolgan);
    $("ko-ulagan").textContent = son(k.ega_ulagan);
    $("ko-ulamagan").textContent = son(k.ega_ulamagan);
  }

  /* «▲ 12%» / «▼ 5%» — o'zgarish yorlig'i. Nol — neytral, strelkasiz:
     «▲ 0%» o'sish bo'lmagan joyda o'sish deydi. */
  function trend(foizi) {
    var v = Number(foizi) || 0;
    var sinf = v > 0 ? "up" : (v < 0 ? "down" : "teng");
    var belgi = v > 0 ? "▲ " : (v < 0 ? "▼ " : "");
    return '<b class="trend ' + sinf + '">' + belgi + Math.abs(v) + "%</b>";
  }

  /* ══ MINI-GRAFIK (KPI kartasi) ══════════════════════════════════
     7 kunlik ingichka chiziq — raqamning YO'NALISHINI ko'rsatadi, katta
     grafik o'rnini bosmaydi (shuning uchun o'qsiz va yorliqsiz).
     ⚠️ OXIRGI BO'LAK UZUQ: oxirgi nuqta — BUGUN, u hali tugamagan. Ertalab
     ochilgan panelda u har doim pastda turadi va bir xil chiziq «qulash»
     bo'lib ko'rinardi. Uzuq chiziq «bu hali sanalyapti» deydi.
     ⚠️ Chiziq gradiyenti `userSpaceOnUse` (`sparkLine`): `objectBoundingBox`
     bilan tekis chiziq (hamma kun 0) balandligi nol bo'lib, CHIZILMASDI. */
  function mini(id, qiymatlar, izoh) {
    var el = $(id);
    if (!el) return;
    var n = qiymatlar.length;
    if (n < 2) { el.innerHTML = ""; return; }
    var eng = Math.max.apply(null, qiymatlar) || 1;
    var p = qiymatlar.map(function (v, i) {
      // 3px tepada va pastda bo'sh joy — chiziq qalinligi kesilmasin.
      return [i / (n - 1) * 100, 27 - (Number(v) || 0) / eng * 24];
    });
    function yol(a) {
      return a.map(function (q, i) {
        return (i ? "L" : "M") + q[0].toFixed(2) + " " + q[1].toFixed(2);
      }).join(" ");
    }
    el.innerHTML =
      '<path class="m-maydon" d="' + yol(p) + ' L100 30 L0 30 Z"/>' +
      '<path class="m-chiziq" d="' + yol(p.slice(0, n - 1)) + '"/>' +
      '<path class="m-chiziq m-bugun" d="' + yol(p.slice(n - 2)) + '"/>';
    el.setAttribute("aria-label", izoh + ": " + qiymatlar.map(son).join(", "));
  }

  /* 1 840 000 -> «1.84M». Uzun raqam telefonda kartochkadan chiqib
     ketardi va uni bir qarashda o'qib ham bo'lmasdi. */
  function million(n) {
    n = Number(n) || 0;
    if (n >= 1e6) return (n / 1e6).toFixed(2) + "M";
    if (n >= 1e3) return Math.round(n / 1e3) + "K";
    return son(n);
  }

  /* ══ GRAFIK ═════════════════════════════════════════════════════
     ⚠️ FABRIKA, bitta nusxa EMAS. Ilgari grafik qattiq id'larga
     ("line", "dots", "tip"…) bog'langan edi, ya'ni ikkinchi grafik
     uchun butun funksiyani nusxalash kerak bo'lardi — va o'sha nusxa
     albatta eskirardi (bu loyihada besh marta ro'y bergan).
     `chizuvchi(prefiks)` har bir grafikka o'z holatini beradi, kod esa
     bitta joyda qoladi. HTML tomonda id'lar prefiks bilan: "d-line",
     "d-dots" va hokazo. */
  /* ⚠️ Kenglik (`W`) QOTIRILMAGAN — har grafikda o'zi, konteynerning
     haqiqiy piksel kengligi. Ilgari `viewBox="0 0 640 210"` edi va SVG
     telefonda butunicha kichrayardi: 11px yozuvlar 360px ekranda 6.4px,
     390px'da 7.2px bo'lib o'qib bo'lmasdi (audit, 2026-11-19). Endi
     1 birlik = 1 CSS piksel, ya'ni yozuv hamma joyda 11px. */
  // BALAND — x yorliqlari (y=176) va ularning pastki qismi sig'adigan
  // eng kichik balandlik; 210 da ostida bo'sh joy qolardi.
  var PAD_L = 44, PAD_R = 16, TOP = 18, BASE = 158, BALAND = 186;

  /* Yuqori chegara — 4 ga bo'linadigan "chiroyli" son, eng kamida 4.
     Nolga bo'lish va tekis nol grafik shu yerda to'xtaydi. */
  function pogona(eng) {
    if (!eng) return 4;
    var p = Math.pow(10, Math.floor(Math.log10(eng)));
    var q = Math.ceil(eng / p * 4) / 4 * p;
    return Math.max(4, Math.ceil(q / 4) * 4);
  }

  function chizuvchi(prefiks, sarlavha, izoh) {
    var DAYS = [], MAX = 100, W = 640, oxirgi = null;
    function el(nom) { return $(prefiks + nom); }

    /* Konteyner kengligi. Yashirin tabda (masalan Daromad ochilmagan)
       u 0 — unda eski qiymat qoladi, tab ochilganda ResizeObserver
       qayta chizadi. */
    function olcha() {
      var box = el("box"), w = box ? Math.round(box.clientWidth) : 0;
      if (w > 0) W = w;
      el("svg").setAttribute("viewBox", "0 0 " + W + " " + BALAND);
      el("hit").setAttribute("width", W);
    }

    function x(i) {
      var n = DAYS.length > 1 ? DAYS.length - 1 : 1;
      return PAD_L + i * (W - PAD_L - PAD_R) / n;
    }
    /* ⚠️ Y O'QI NOLDAN. Ilgari shkala eng kichik qiymatdan boshlanardi
       (ekranda 44 dan) va shuning uchun 176→132 kabi oddiy tebranish
       chuqur qulashdek ko'rinardi (§4). Noldan boshlangan shkala
       nisbatni to'g'ri ko'rsatadi. */
    function y(v) { return BASE - (v / MAX) * (BASE - TOP); }

    function chiz(kunlar) {
      oxirgi = kunlar;
      olcha();
      DAYS = kunlar || [];
      var eng = DAYS.length
        ? Math.max.apply(null, DAYS.map(function (p) { return p.soni; })) : 0;
      MAX = pogona(eng);

      var line = "", dots = "", labels = "", ylab = "", setka = "";
      var kop = DAYS.length > 14 ? Math.ceil(DAYS.length / 7) : 1;
      DAYS.forEach(function (p, i) {
        line += (i ? " L" : "M") + x(i).toFixed(1) + " " + y(p.soni).toFixed(1);
        // Uzun oynada har bir nuqtaga doira chizilsa chiziq ko'rinmay
        // qoladi — faqat oxirgisi belgilanadi.
        if (DAYS.length <= 14 || i === DAYS.length - 1) {
          dots += '<circle class="nuqta' + (i === DAYS.length - 1 ? " oxirgi" : "") +
                  '" cx="' + x(i).toFixed(1) + '" cy="' + y(p.soni).toFixed(1) + '" r="' +
                  (i === DAYS.length - 1 ? 4.5 : 3) + '" fill="' +
                  (i === DAYS.length - 1 ? "#2BB3FF" : "var(--panel)") + '" stroke="#7B5CFF" stroke-width="2"/>';
        }
        if (i % kop === 0 || i === DAYS.length - 1) {
          // ⚠️ 7 kunlik oynada hafta kuni («Dush») ma'noli, 30 yoki 90
          // kunlikda esa u to'rt marta takrorlanadi va o'qni o'qib
          // bo'lmay qoladi — u yerda sana yoziladi.
          var yorliq = DAYS.length <= 7 ? p.nom
            : (p.kun || "").slice(8, 10) + "." + (p.kun || "").slice(5, 7);
          // Oxirgi yorliq o'ng chetga TEKISLANADI — markazlansa uning
          // yarmi kartadan tashqarida qolardi.
          var langar = i === DAYS.length - 1 && DAYS.length > 1 ? "end" : "middle";
          labels += '<text x="' + x(i).toFixed(1) + '" y="176" text-anchor="' + langar + '">' +
                    xavfsiz(yorliq) + "</text>";
        }
      });
      [1, 0.75, 0.5, 0.25, 0].forEach(function (ulush) {
        var yy = y(MAX * ulush);
        setka += '<line class="setka" x1="' + PAD_L + '" y1="' + yy.toFixed(1) +
                 '" x2="' + W + '" y2="' + yy.toFixed(1) + '"/>';
        ylab += '<text x="0" y="' + (yy + 4).toFixed(1) + '">' + son(Math.round(MAX * ulush)) + "</text>";
      });
      var area = line + " L" + x(Math.max(0, DAYS.length - 1)).toFixed(1) + " " + BASE +
                 " L" + x(0).toFixed(1) + " " + BASE + " Z";
      el("line").setAttribute("d", line);
      el("area").setAttribute("d", area);
      el("dots").innerHTML = dots;
      el("xlab").innerHTML = labels;
      el("ylab").innerHTML = ylab;
      el("setka").innerHTML = setka;
      el("svg").setAttribute("aria-label",
        sarlavha + ": " + DAYS.map(function (p) { return p.nom + " " + p.soni; }).join(", "));
    }

    function hodisalar() {
      var hit = el("hit"), tip = el("tip"), cross = el("cross"), box = el("box");
      if (!hit || !box) return;
      function nearest(clientX) {
        var r = box.getBoundingClientRect();
        var vx = (clientX - r.left) / r.width * W;
        var best = 0, bd = 1e9;
        DAYS.forEach(function (p, i) { var d = Math.abs(x(i) - vx); if (d < bd) { bd = d; best = i; } });
        return best;
      }
      var oldingi = -1;
      function move(e) {
        if (!DAYS.length) return;
        var cx = e.touches ? e.touches[0].clientX : e.clientX;
        var i = nearest(cx), r = box.getBoundingClientRect();
        // Barmoq yangi kunga o'tdi — iOS g'ildiragidek bitta «chiq».
        if (e.touches && i !== oldingi) titroq("tanlov");
        oldingi = i;
        cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("opacity", ".55");
        tip.innerHTML = xavfsiz(kunNomi(DAYS[i].kun + "T12:00:00+05:00")) +
                        " · " + izoh(DAYS[i]);
        tip.style.opacity = "1";
        // ⚠️ KARTA ICHIDA QISILADI. Markazi nuqtada turgani uchun
        // chetdagi nuqtada yarmi tashqariga chiqardi: kompyuterda qo'shni
        // kartani yopardi, telefonda ekrandan chiqib ketardi.
        var yarim = tip.offsetWidth / 2;
        var chap = x(i) / W * r.width;
        tip.style.left = Math.max(yarim, Math.min(r.width - yarim, chap)) + "px";
        tip.style.top = (y(DAYS[i].soni) / BALAND * r.height) + "px";
      }
      function leave() { oldingi = -1; tip.style.opacity = "0"; cross.setAttribute("opacity", "0"); }
      hit.addEventListener("mousemove", move);
      hit.addEventListener("mouseleave", leave);
      hit.addEventListener("touchstart", move, { passive: true });
      hit.addEventListener("touchmove", move, { passive: true });
      hit.addEventListener("touchend", leave);
      // Kenglik o'zgardi (telefon burildi, oyna kattalashdi, yashirin
      // tab ochildi) — shu kenglikda qayta chiziladi. Faqat KENGLIK
      // o'zgarganda: balandlik o'zgarishiga qayta chizish halqa bo'lardi.
      if (window.ResizeObserver) {
        new ResizeObserver(function () {
          var w = Math.round(box.clientWidth);
          if (oxirgi && w > 0 && w !== W) chiz(oxirgi);
        }).observe(box);
      }
    }

    return { chiz: chiz, hodisalar: hodisalar };
  }

  var kunOynasi = 7;
  var sorovGrafigi = chizuvchi("chart-", "So'rovlar oqimi", function (p) {
    return "<b>" + son(p.soni) + "</b> so'rov · " + son(p.kishi) + " kishi";
  });
  var daromadGrafigi = chizuvchi("dchart-", "Daromad oqimi", function (p) {
    return "<b>" + son(p.soni) + "</b> ⭐ · " + son(p.kishi) + " sotuv";
  });
  function grafik(kunlar) { sorovGrafigi.chiz(kunlar); }
  function grafikHodisalari() {
    sorovGrafigi.hodisalar();
    daromadGrafigi.hodisalar();
  }

  /* ══ BOSHQARUV ══════════════════════════════════════════════════ */
  async function boshqaruv() {
    kpiSkelet(["k-sorov", "k-faol", "k-pro", "k-pul", "k-token"]);
    var d = await ol("/api/overview?kun=" + kunOynasi);
    var k = d.kpi;

    $("k-sorov").textContent = son(k.sorovlar.qiymat);
    $("k-sorov-d").innerHTML = k.sorovlar.ozgarish === null
      ? "kecha taqqoslash uchun ma'lumot yo'q"
      : trend(k.sorovlar.ozgarish) + " oldingi 24 soatga nisbatan";
    // Grafik oynasi 7/30/90 kun — mini-grafik doim OXIRGI 7 kun.
    var hafta = (d.kunlar || []).slice(-7);
    mini("k-sorov-sp", hafta.map(function (p) { return p.soni; }), S.mini.sorov);

    $("k-faol").textContent = son(k.faol.qiymat);
    $("k-faol-d").innerHTML = son(k.faol.jami) + ' dan · <b class="up">+' +
                              son(k.faol.yangi) + "</b> bugun yangi";
    mini("k-faol-sp", hafta.map(function (p) { return p.kishi; }), S.mini.faol);

    $("k-pro").textContent = son(k.pro.qiymat);
    // ⚠️ Muddatsiz Pro bu sanoqqa kirmaydi (`premium_until IS NULL`),
    // ya'ni «tugaydi» faqat haqiqatan tugaydiganlar haqida.
    $("k-pro-d").textContent = k.pro.tugaydi
      ? k.pro.tugaydi + " tasi 7 kunda tugaydi"
      : "7 kun ichida tugaydigani yo'q";

    $("k-pul").textContent = son(k.daromad.bugun) + " ⭐";
    // Kecha — FOIZ EMAS, summa: bugun tugamagan kun (api.py izohi).
    // ` ⭐` — yulduz raqamdan ajralib yolg'iz qatorga tushmasin.
    $("k-pul-d").textContent = "kecha " + son(k.daromad.kecha) + " ⭐ · 30 kunda " +
                               son(k.daromad.oy) + " ⭐";
    mini("k-pul-sp", (k.daromad.kunlar || []).map(function (p) { return p.soni; }), S.mini.pul);

    tokenChiz(k.token);
    biznesChiz(d.biznes);
    kochishChiz(d.kochish);

    kunChiplari(d.kun_variantlari, d.kun_oynasi);
    grafik(d.kunlar);
    ustunlarChiz("typebars", d.turlar);
    $("typebars-jami").textContent = "jami " + son(k.sorovlar.qiymat);
    tarifChiz("t-ratio", "t-ulush", d.tarif);
    $("t-jami").textContent = son(d.tarif.jami);

    // Texnik ta'til — rangli yorliq, oddiy matn emas (§4).
    var tt = $("t-tatil");
    tt.className = d.tatil ? "tag warn" : "tag ok";
    tt.textContent = d.tatil ? S.tatilBor : S.tatilYoq;

    $("xato-soni").textContent = "bugun " + son(d.xato_soni) + " ta";
    $("n-users").textContent = son(d.tarif.jami);
    $("n-xato").textContent = son(d.xato_soni);
    $("xatolar").innerHTML = d.xatolar.length
      ? d.xatolar.map(function (x) {
          return '<div class="row' + (x.user ? ' bosiladi" data-uid="' + xavfsiz(x.user) : "") +
                 '"><span class="tag ' + (x.tur === "timeout" ? "warn" : "ban") +
                 '">' + xavfsiz(x.tur) + '</span><div class="t"><b>' + xavfsiz(x.matn) +
                 "</b><span>" + (x.user ? "ID " + xavfsiz(x.user) + " · " : "") +
                 xavfsiz(nisbiy(x.vaqt)) + "</span></div></div>";
        }).join("")
      : boshHolat(S.bosh.xato);

    kuzatuvBanner(d.kuzatuv);
    holatBelgisi(d);
    yangilandiBelgisi();
  }

  /* ⭐ Kuzatuv guruhi — panelning YAGONA chiqish kanali: ogohlantirishlar
     shu yerga boradi. U yiqilsa, ilgari buni faqat Railway logi bilardi,
     ya'ni «bot jim» xabari yetmagani botning o'zi jim qolganida
     ko'rinardi. Banner ekranning ENG TEPASIDA — `xatoQatori` bilan bir
     xil sabab: telefonda birinchi `.card` KPI qatoridan keyin turadi.

     ⚠️ O'CHIRISH TUGMASI YO'Q. Banner muvaffaqiyatli yuborishdan keyin
     o'zi yo'qoladi (server ikkita vaqtni solishtiradi), ya'ni qo'lda
     o'chirilgan banner muammo qolgan holda yo'qolib ketmaydi. */
  function kuzatuvBanner(k, joy) {
    // Ikki joyda: Boshqaruvning tepasi va Odamlar › Kuzatuv — guruhni
    // TUZATADIGAN joy (ilgari banner faqat Boshqaruvda edi).
    joy = joy || document.querySelector('section[data-screen="dash"]');
    if (!joy) return;
    var eski = joy.querySelector(".banner");
    if (eski) eski.remove();
    if (!k) return;

    var bosh, izoh;
    if (!k.guruh) { bosh = S.kuzatuvBanner.yoq; izoh = S.kuzatuvBanner.yoqIzoh; }
    else if (k.sabab) {
      bosh = S.kuzatuvBanner.yetmayapti;
      izoh = k.sabab + (k.vaqt ? " · " + nisbiy(k.vaqt) : "");
    } else return;

    var el = document.createElement("div");
    el.className = "banner";
    el.setAttribute("role", "status");
    el.innerHTML = ikonka("kuzatuv_ol") + "<div><b>" + xavfsiz(bosh) +
                   "</b><span>" + xavfsiz(izoh) + "</span></div>";
    joy.insertBefore(el, joy.firstChild);
  }

  /* Sarlavhadagi kichik holat nuqtasi. Uchta haqiqiy holat: baza
     uzilgan (qizil), texnik ta'til (sariq), ishlayapti (yashil).
     ⚠️ «Bot ishlayapti» QOTIRILGAN MATN EMAS — javobning kelishi
     jarayon tirikligini bildiradi, qolgan ikkisi esa serverdan. */
  function holatBelgisi(d) {
    var h = $("holat");
    if (!h) return;
    var sinf = "holat", matn = S.holat.ishlayapti;
    if (d.baza === false) { sinf += " yomon"; matn = S.holat.bazaYoq; }
    else if (d.tatil) { sinf += " ogoh"; matn = S.holat.tatil; }
    h.className = sinf;
    h.title = matn;
    h.innerHTML = '<i></i><span class="matn">' + xavfsiz(matn) + "</span>";
  }

  function kunChiplari(variantlar, tanlangan) {
    var el = $("chart-kunlar");
    if (!el || el.dataset.tayyor) {
      if (el) el.querySelectorAll("[data-kun]").forEach(function (b) {
        b.setAttribute("aria-pressed", Number(b.dataset.kun) === tanlangan ? "true" : "false");
      });
      return;
    }
    el.dataset.tayyor = "1";
    el.innerHTML = (variantlar || [7, 30, 90]).map(function (n) {
      return '<button class="chip" data-kun="' + n + '" aria-pressed="' +
             (n === tanlangan) + '">' + n + " kun</button>";
    }).join("");
    el.addEventListener("click", function (e) {
      var b = e.target.closest("[data-kun]");
      if (!b) return;
      kunOynasi = Number(b.dataset.kun);
      titroq("tanlov");
      yuklangan.dash = false;
      ekranYukla("dash");
    });
  }

  /* ══ STATISTIKA ═════════════════════════════════════════════════ */
  async function statistika() {
    kpiSkelet(["s-jami", "s-ortacha", "s-mehmon", "s-konv"]);
    var d = await ol("/api/stats");
    $("s-jami").textContent = son(d.kpi.jami);
    $("s-jami-d").innerHTML = '<b class="up">+' + son(d.kpi.yangi) + "</b> so'nggi 24 soatda";
    $("s-ortacha").textContent = son(d.kpi.kunlik_ortacha);
    $("s-mehmon").textContent = foiz(d.kpi.mehmon_ulush);
    $("s-konv").textContent = foiz(d.kpi.konversiya, 2);

    var eng = 1;
    d.top.forEach(function (u) { if (u.ulush > eng) eng = u.ulush; });
    $("s-top").innerHTML = d.top.length
      ? '<div class="rbosh"><span>Foydalanuvchi</span><span class="ong">So\'rov</span><span>Ulush</span></div>' +
        d.top.map(function (u, i) {
          // Ism ro'yxatdagidek: «ID:123» + ostida yana «123» — bitta ID
          // ikki marta (§4) — endi yo'q; avatar shaxsiy nomdan.
          return '<div class="row bosiladi" data-uid="' + xavfsiz(u.user_id) + '" data-un="' +
            xavfsiz(u.username || "") + '"><div class="person">' +
            avatar(shaxs(u), i === 0) +
            "<div><b>" + xavfsiz(nomi(u)) + "</b><span>" + xavfsiz(u.user_id) +
            '</span></div></div><b class="num ong">' + son(u.soni) + "</b>" +
            '<div class="track" style="height:9px;border-radius:999px;background:var(--panel-2);overflow:hidden">' +
            '<div class="fill' + (i === 0 ? " top" : "") + '" style="height:100%;border-radius:999px;' +
            'background:linear-gradient(90deg,var(--violet),var(--azure));width:' + u.ulush + '%"></div></div></div>';
        }).join("")
      : boshHolat(S.bosh.top);

    tarifChiz("s-ratio", "s-ulush", d.tarif);
    $("s-ulushlar").innerHTML = d.ulushlar.map(function (u) {
      return '<div class="row"><div class="t"><b>' + xavfsiz(u.nom) + "</b><span>" +
             xavfsiz(u.izoh) + '</span></div><b class="num">' +
             foiz(u.foiz, u.foiz !== null && u.foiz % 1 ? 1 : 0) + "</b></div>";
    }).join("");
    // «Kim aybdor» emas, «qayerga ketyapti» — shuning uchun ID, va
    // bosilganda o'sha odamning profiliga o'tadi.
    $("s-token").innerHTML = (d.eng_qimmat || []).length
      ? d.eng_qimmat.map(function (u) {
          return '<div class="row bosiladi" data-uid="' + xavfsiz(u.user_id) + '">' +
            '<div class="t"><b>ID ' + xavfsiz(u.user_id) + "</b></div>" +
            '<span class="num">' + million(u.token) + "</span>" +
            '<span class="num hint">' + son(u.raund) + " raund</span></div>";
        }).join("")
      : boshHolat(S.bosh.token || "Hali token sarfi yozilmagan");

    ustunlarChiz("s-turlar", d.turlar);
    yangilandiBelgisi();
  }

  /* ══ JURNAL ═════════════════════════════════════════════════════ */

  /* Audit amali ikonkalari — pastki navigatsiya bilan BIR USLUBDA
     (chiziqli SVG), emoji emas (§4). Kalit serverdan keladi
     (`core/config.py::AUDIT_ACTIONS`), ya'ni yangi amal qo'shilsa u
     shu yerda kalit bilan so'raladi; topilmasa nuqta chiziladi va
     qator baribir ko'rinadi. */
  var IKONKA = {
    ban:            '<path d="M5.6 5.6l12.8 12.8"/><circle cx="12" cy="12" r="9"/>',
    unban:          '<path d="M20 6 9 17l-5-5"/>',
    pro:            '<path d="M12 3l2.6 5.6 6.1.8-4.5 4.2 1.2 6.1L12 16.8 6.6 19.7l1.2-6.1L3.3 9.4l6.1-.8z"/>',
    plan:           '<path d="M3 12h18M12 3v18"/>',
    reset:          '<path d="M3 12a9 9 0 1 0 3-6.7M3 4v5h5"/>',
    pul:            '<path d="M9 7h6a3 3 0 0 1 0 6H9m0-6v10m0-4h6"/><circle cx="12" cy="12" r="9"/>',
    xabar:          '<path d="M4 5h16v12H8l-4 3z"/>',
    admin_qosh:     '<circle cx="10" cy="8" r="3.2"/><path d="M4 19a6 6 0 0 1 12 0M18 8v6M15 11h6"/>',
    admin_ol:       '<circle cx="10" cy="8" r="3.2"/><path d="M4 19a6 6 0 0 1 12 0M15 11h6"/>',
    tarqatma:       '<path d="M3 11v2a1 1 0 0 0 1 1h3l5 4V6L7 10H4a1 1 0 0 0-1 1zM17 8.5a5 5 0 0 1 0 7"/>',
    tarqatma_bekor: '<path d="M3 11v2a1 1 0 0 0 1 1h3l5 4V6L7 10H4a1 1 0 0 0-1 1zM16 9l5 5M21 9l-5 5"/>',
    limit:          '<path d="M4 8h16M4 16h16"/><circle cx="9" cy="8" r="2.2"/><circle cx="15" cy="16" r="2.2"/>',
    promo:          '<path d="M20 12v8H4v-8M2 7h20v5H2zM12 22V7"/>',
    promo_bekor:    '<path d="M2 7h20v5H2zM4 12v8h8M16 16l5 5M21 16l-5 5"/>',
    referal:        '<circle cx="9" cy="8" r="3.2"/><path d="M3.5 19a5.5 5.5 0 0 1 11 0M17 11a2.6 2.6 0 1 0-1.6-4.6M20.5 19a4.4 4.4 0 0 0-3.4-4.3"/>',
    tatil:          '<path d="M14.7 6.3a4 4 0 0 0 5 5L14 17l-3-3z"/><path d="M11 14 4 21"/>',
    kuzatuv:        '<path d="M2 12s3.6-6 10-6 10 6 10 6-3.6 6-10 6-10-6-10-6z"/><circle cx="12" cy="12" r="2.6"/>',
    kuzatuv_ol:     '<path d="M4 4l16 16M10.6 10.6A2.6 2.6 0 0 0 12 14.6M6.5 7.6C3.9 9.2 2 12 2 12s3.6 6 10 6c1.7 0 3.2-.4 4.5-1"/>',
    statistika:     '<path d="M3 20h18M7 20V10M12 20V4M17 20v-7"/>',
    eksport:        '<path d="M12 3v12M8 11l4 4 4-4M4 19h16"/>',
    jurnal:         '<path d="M5 3h11l4 4v14H5zM9 12h6M9 16h6"/>'
  };

  function ikonka(kalit) {
    var d = IKONKA[kalit] || '<circle cx="12" cy="12" r="3"/>';
    return '<svg class="ikon" viewBox="0 0 24 24" aria-hidden="true">' + d + "</svg>";
  }

  var jSahifa = { audit: 0, errors: 0 }, jSahifalar = { audit: 1, errors: 1 };
  var jAdmin = null;

  /* ══ JURNAL FILTRI ══════════════════════════════════════════════
     Ikkala jurnal (audit va xatolar) bir xil ishlaydi, shuning uchun
     holat ham, chiplar ham bitta joyda. Ikkinchi nusxa yozilsa, biri
     sahifani nolga qaytarishni unutar va admin qidiruvdan keyin bo'sh
     sahifada qolardi. */
  var jFiltr = { audit: { q: "", kun: 0 }, errors: { q: "", kun: 0 } };
  var JURNAL_KUNLAR = [
    { kun: 0, nom: "Hammasi" }, { kun: 1, nom: "Bugun" },
    { kun: 7, nom: "7 kun" }, { kun: 30, nom: "30 kun" },
    { kun: 90, nom: "90 kun" }
  ];

  /* So'rov qatoriga filtrni qo'shadi. Bo'sh qiymat UMUMAN yuborilmaydi —
     server tomonda "kun=0" baribir tashlanardi, lekin bo'sh parametr
     URL'ni o'qishni qiyinlashtiradi. */
  function jFiltrQator(qaysi) {
    var f = jFiltr[qaysi], s = "";
    if (f.q) s += "&q=" + encodeURIComponent(f.q);
    if (f.kun) s += "&kun=" + f.kun;
    return s;
  }

  function jKunChiplari(qaysi, idKonteyner) {
    var box = $(idKonteyner);
    if (!box) return;
    box.innerHTML = JURNAL_KUNLAR.map(function (v) {
      return '<button class="chip' + (jFiltr[qaysi].kun === v.kun ? " on" : "") +
             '" data-jkun="' + qaysi + ":" + v.kun + '">' + v.nom + "</button>";
    }).join("");
  }

  /* Qidiruv har bosilgan harfda so'rov yubormaydi: 300 ms kutadi.
     Usiz «@nodira» yozish sakkizta so'rov degani edi. */
  function jQidiruvUlash(qaysi, idInput, idKonteyner, qayta) {
    var inp = $(idInput);
    if (!inp) return;
    var t = null;
    inp.addEventListener("input", function () {
      clearTimeout(t);
      t = setTimeout(function () {
        jFiltr[qaysi].q = inp.value.trim();
        jSahifa[qaysi] = 0;          // ⚠️ yangi filtr — birinchi sahifadan
        qayta();
      }, 300);
    });
    jKunChiplari(qaysi, idKonteyner);
  }

  function jKunTanlandi(qiymat) {
    var p = String(qiymat).split(":");
    var qaysi = p[0], kun = Number(p[1]);
    jFiltr[qaysi].kun = kun;
    jSahifa[qaysi] = 0;              // ⚠️ yangi filtr — birinchi sahifadan
    jKunChiplari(qaysi, qaysi === "audit" ? "j-audit-kun" : "j-xato-kun");
    titroq("tanlov");
    jurnalQayta(qaysi);
  }

  async function jurnalAudit() {
    var n = navbatOl("audit");
    var d = await ol("/api/journal/audit?page=" + jSahifa.audit +
                     (jAdmin ? "&admin=" + jAdmin : "") + jFiltrQator("audit"));
    if (eskirganmi("audit", n)) return;
    jSahifalar.audit = d.sahifalar;
    var fa = jFiltr.audit;
    $("j-audit-soni").textContent =
      ((fa.q || fa.kun) ? "topildi " : "jami ") + son(d.jami) + " ta";

    // ⚠️ SANA BO'YICHA GURUHLASH (§4). Ilgari har qatorda to'liq sana
    // turardi («14.09.2026 21:34») va telefonda u ikki qatorga
    // bo'linib ketardi. Endi kun sarlavhada bir marta, qatorda esa
    // faqat soat.
    var h = "", oxirgiKun = null;
    d.rows.forEach(function (r) {
      var k = faqatKun(r.vaqt);
      if (k !== oxirgiKun) {
        oxirgiKun = k;
        h += '<div class="kun-bosh">' + xavfsiz(kunNomi(r.vaqt)) + "</div>";
      }
      // Har qator uchta savolga javob beradi: KIM → NIMA → KIMGA.
      h += '<div class="row">' + ikonka(r.ikonka) +
        '<div class="t"><b>' + xavfsiz(r.amal) +
        (r.kimga ? ' <span style="color:var(--ink-3)">→</span> ' + xavfsiz(r.kimga) : "") +
        "</b><span>" + xavfsiz(r.admin) + " · " + xavfsiz(soat(r.vaqt)) +
        (r.tafsilot ? "</span></div>" +
          '<span class="tag tafsilot">' + xavfsiz(r.tafsilot) + "</span>"
                    : "</span></div>") + "</div>";
    });
    $("j-audit").innerHTML = d.rows.length ? h : boshHolat(S.bosh.audit);
    $("j-audit-holat").textContent = "sahifa " + (jSahifa.audit + 1) + "/" + d.sahifalar;

    var chips = $("j-adminlar");
    if (!chips.dataset.tayyor && d.adminlar.length) {
      chips.dataset.tayyor = "1";
      // ⚠️ Chipda NOM turadi, quruq ID emas — jadvalda ham o'sha nom
      // ko'rinadi va ikkalasi bitta odam ekani ko'rinib turadi.
      chips.innerHTML = '<button class="chip" aria-pressed="true" data-admin="">' +
        S.user.chip.all + "</button>" +
        d.adminlar.map(function (a) {
          return '<button class="chip" aria-pressed="false" data-admin="' + a.id + '">' +
                 xavfsiz(a.nom) + "</button>";
        }).join("");
      chips.addEventListener("click", function (e) {
        var b = e.target.closest("[data-admin]");
        if (!b) return;
        jAdmin = b.dataset.admin || null;
        jSahifa.audit = 0;
        chips.querySelectorAll(".chip").forEach(function (o) {
          o.setAttribute("aria-pressed", o === b ? "true" : "false");
        });
        titroq("tanlov");
        jurnalQayta("audit");
      });
    }
  }

  async function jurnalXatolar() {
    var n = navbatOl("errors");
    var d = await ol("/api/journal/errors?page=" + jSahifa.errors +
                     jFiltrQator("errors"));
    if (eskirganmi("errors", n)) return;
    jSahifalar.errors = d.sahifalar;
    var x = d.xulosa;
    $("j-xato-soni").textContent = "bugun " + son(x.kun) + " · hafta " + son(x.hafta);
    ustunlarChiz("j-xato-turlar", x.turlar);
    var h = "", oxirgiKun = null;
    d.rows.forEach(function (r) {
      var k = faqatKun(r.vaqt);
      if (k !== oxirgiKun) {
        oxirgiKun = k;
        h += '<div class="kun-bosh">' + xavfsiz(kunNomi(r.vaqt)) + "</div>";
      }
      h += '<div class="row' + (r.user ? ' bosiladi" data-uid="' + xavfsiz(r.user) : "") +
        '"><span class="tag ' + (r.tur === "timeout" ? "warn" : "ban") + '">' +
        xavfsiz(r.tur) + '</span><div class="t"><b>' + xavfsiz(r.matn) + "</b><span>" +
        xavfsiz(soat(r.vaqt)) + (r.user ? " · ID " + xavfsiz(r.user) : "") +
        "</span></div></div>";
    });
    $("j-xatolar").innerHTML = d.rows.length ? h : boshHolat(S.bosh.xato);
    // Filtr yoqilganda «jami» — topilgan son, butun jadvalniki emas.
    var f = jFiltr.errors, filtrli = !!(f.q || f.kun);
    $("j-xato-holat").textContent =
      (filtrli ? "topildi " + son(d.jami) + " ta" : "jami " + son(x.jami)) +
      " · sahifa " + (jSahifa.errors + 1) + "/" + d.sahifalar;
  }

  async function jurnalDaromad() {
    var d = await ol("/api/journal/revenue");
    $("j-oy").textContent = son(d.oy) + " ⭐";
    $("j-oy-d").textContent = son(d.sotuv_30d) + " ta sotuv · " +
                              son(d.qaytarilgan) + " ta qaytarilgan";
    $("j-bugun").textContent = son(d.bugun) + " ⭐";
    // Sotuv bo'lmasa o'rtacha chek YO'Q — «0 ⭐» yolg'on bo'lardi.
    $("j-ortacha").textContent = d.ortacha === null ? S.yoq : son(d.ortacha) + " ⭐";
    $("j-jami").textContent = son(d.jami) + " ⭐";
    daromadGrafigi.chiz(d.kunlik || []);
    ustunlarChiz("j-tariflar", d.tariflar.map(function (t) {
      return { nom: t.nom, soni: t.soni };
    }));
  }

  function jurnalQayta(qaysi) {
    var fn = { audit: jurnalAudit, errors: jurnalXatolar }[qaysi];
    if (fn) fn().catch(function (e) { console.error("[panel] jurnal " + qaysi + ":", e); });
  }

  async function jurnal() {
    skelet("j-audit", 5);
    await Promise.all([jurnalAudit(), jurnalXatolar(), jurnalDaromad()]);
    yangilandiBelgisi();
  }

  /* ══ CSV EKSPORT ════════════════════════════════════════════════
     Fayl brauzerga emas, TELEGRAM CHATIGA keladi — sabab api.py da:
     Mini App webview'ida `blob:` yuklab olish jim yiqiladi. */
  async function eksport(tur, tugma) {
    // Tugmani o'chirish/tiklash endi `so_rov()` ning ishi — bu yerda
    // alohida nusxa turgan edi va qolgan 12 ta yozish amali undan
    // foydalanmasdi.
    // Eksport ma'lumotni TIZIMDAN CHIQARADI: fayl Telegram chatiga
    // tushadi va u yerdan forward qilinadi. Shuning uchun tasdiq
    // nimani, qanchasini va QAYERGA ketishini aytadi.
    var nima = (S.eksportNomi && S.eksportNomi[tur]) || tur;
    if (!await tasdiq(S.savol.eksport(nima, son(META.eksport_max)))) return;
    var j = await so_rov("/api/export?tur=" + encodeURIComponent(tur),
                         {}, null, tugma);
    toast(j.ok ? son(j.d.qator) + " qator — fayl Telegramga yuborildi" : j.xato);
  }

  function jurnalNav() {
    // Qidiruv va sana chiplari. Chiplar har chizishda qayta yasaladi,
    // shuning uchun tinglovchi KONTEYNERDA — qatorda emas (aks holda
    // bitta bosish ikki marta ishlardi).
    document.querySelectorAll("[data-eksport]").forEach(function (b) {
      b.addEventListener("click", function () {
        eksport(b.dataset.eksport, b);
      });
    });

    jQidiruvUlash("audit", "j-audit-q", "j-audit-kun", jurnalAudit);
    jQidiruvUlash("errors", "j-xato-q", "j-xato-kun", jurnalXatolar);
    delegat("j-audit-kun", "data-jkun", jKunTanlandi);
    delegat("j-xato-kun", "data-jkun", jKunTanlandi);

    document.querySelectorAll("[data-jnav]").forEach(function (b) {
      b.addEventListener("click", function () {
        var q = b.dataset.jnav.split(":");
        var qaysi = q[0], yon = Number(q[1]);
        var yangi = jSahifa[qaysi] + yon;
        if (yangi < 0 || yangi >= jSahifalar[qaysi]) return;
        jSahifa[qaysi] = yangi;
        titroq("light");
        jurnalQayta(qaysi);
      });
    });
  }

  /* ══ EKRAN YUKLASH ══════════════════════════════════════════════ */
  var yuklangan = {};
  var kirdi = false;
  /* ⚠️ Ilgari ekran BIR MARTA yuklanardi: panel ochiq turganda (yoki
     profilda Pro berib qaytganda) raqamlar ochilgan paytdagicha qolardi.
     Endi faqat o'qiladigan ekranlar 60 soniyadan eski bo'lsa qayta
     yuklanadi — ekranga qaytganda yoki Telegram'dan panelga qaytganda.
     Sozlamalar va Promo YO'Q: ular qayta chizilsa yozilayotgan, hali
     saqlanmagan qiymatlar (limitlar, promo formasi) o'chib ketardi. */
  var YANGILANADI = { dash: 1, users: 1, report: 1 };
  var ESKIRISH_MS = 60000;

  /* Besh bo'lim (2026-11-19): har biri o'z ichki tablarining hammasini
     BIR yuklashda oladi — sozlamalar() va jurnal() oldindan shunday edi. */
  function odamlarEkran() { return Promise.all([jadvalYukla(), kuzatuv()]); }
  function hisobotEkran() { return Promise.all([statistika(), jurnal()]); }

  function ekranYukla(nom) {
    var fn = { dash: boshqaruv, users: odamlarEkran, report: hisobotEkran,
               promo: promoEkran, system: sozlamalar }[nom];
    // Qulf ostida hech narsa yuklanmaydi — ochilgach `qulfQaytdi` chaqiradi.
    // Va'da qaytadi — «pastga tortib yangilash» belgisi tugashini kutadi.
    if (!kirdi || !fn || qulfYopiq) return Promise.resolve();
    var t = yuklangan[nom];
    if (t && !(YANGILANADI[nom] && Date.now() - t > ESKIRISH_MS)) return Promise.resolve();
    yuklangan[nom] = Date.now();
    return fn().catch(function (e) {
      yuklangan[nom] = false;
      console.error("[panel] " + nom + " yuklanmadi:", e);
      xatoQatori(nom);
    });
  }

  /* §5: xato holati + «Qayta urinish» tugmasi. Ilgari bu yerda
     faqat «Panelni qayta oching» degan matn qolardi — ya'ni admin
     butun Mini App'ni yopib ochishga majbur bo'lardi. */
  function xatoQatori(nom) {
    // ⭐ EKRANNING ENG TEPASIGA, birinchi `.card` ichiga EMAS.
    // Oltita ekranda birinchi `.card` KPI qatoridan keyin turadi
    // (`dash` da 1277 belgi keyin), ya'ni telefonda xato xabari
    // ekrandan pastda qolardi. `users` va `profil` da `.card` allaqachon
    // birinchi element edi — ular uchun hech narsa o'zgarmaydi.
    var joy = document.querySelector('section[data-screen="' + nom + '"]');
    if (!joy || joy.querySelector(".yuklanmadi")) return;
    var el = xatoHolat(function () {
      el.remove();
      ekranYukla(nom);
    });
    el.classList.add("yuklanmadi", "card");
    joy.insertBefore(el, joy.firstChild);
  }

  /* ══ FOYDALANUVCHILAR ═══════════════════════════════════════════ */
  var uFiltr = "all", uQuery = "", uSahifa = 0, uSahifalar = 1, uTartib = "faollik";
  var uOchiq = null;

  function nomi(u) {
    // ⚠️ Ilgari bu yerda «ID:6739642698» qaytardi va qatorning
    // ikkinchi satrida YANA o'sha raqam turardi — bitta ID ikki
    // marta (§4). Endi Telegram ismi (tg_ism) birinchi, bo'lmasa
    // @username, u ham bo'lmasa «Foydalanuvchi»; raqam faqat pastki
    // satrda. Ko'pchilikning username'i yo'q — ism esa deyarli doim bor.
    return u.tg_ism || (u.username ? "@" + u.username : S.user.nomsiz);
  }

  /* Avatar uchun SHAXSIY nom (`avatar()` izohiga qarang): ism yoki
     @username, ikkalasi ham bo'lmasa «ID:…» — `bosh()` undan harf olmaydi
     va odam belgisini chizadi. ⚠️ `nomi()` bu yerga YARAMAYDI: u nomsiz
     odamga «Foydalanuvchi» qaytaradi va hamma nomsiz odam bir xil «F»
     bo'lib qolardi (2026-11-19 regressiyasi). */
  function shaxs(u) {
    return u.tg_ism || (u.username ? "@" + u.username : "ID:" + u.user_id);
  }

  function chiplarniChiz() {
    var f = $("u-chiplar");
    if (f && !f.dataset.tayyor) {
      f.dataset.tayyor = "1";
      f.innerHTML = ["all", "pro", "free", "ban", "nofaol"].map(function (k) {
        return '<button class="chip" data-filter="' + k + '" aria-pressed="' +
          (k === "all") + '">' + xavfsiz(S.user.chip[k]) +
          ' <span class="n" id="c-' + k + '">—</span></button>';
      }).join("");
      f.addEventListener("click", function (e) {
        var b = e.target.closest("[data-filter]");
        if (!b) return;
        uFiltr = b.dataset.filter;
        uSahifa = 0;
        f.querySelectorAll(".chip").forEach(function (o) {
          o.setAttribute("aria-pressed", o === b ? "true" : "false");
        });
        titroq("tanlov");
        jadvalQayta();
      });
    }
    var t = $("u-tartib");
    if (t && !t.dataset.tayyor) {
      t.dataset.tayyor = "1";
      t.innerHTML = Object.keys(S.user.tartib).map(function (k) {
        return '<button class="chip" data-tartib="' + k + '" aria-pressed="' +
          (k === "faollik") + '">' + xavfsiz(S.user.tartib[k]) + "</button>";
      }).join("");
      t.addEventListener("click", function (e) {
        var b = e.target.closest("[data-tartib]");
        if (!b) return;
        uTartib = b.dataset.tartib;
        uSahifa = 0;
        t.querySelectorAll(".chip").forEach(function (o) {
          o.setAttribute("aria-pressed", o === b ? "true" : "false");
        });
        titroq("tanlov");
        jadvalQayta();
      });
    }
  }

  async function jadvalYukla() {
    var yol = "/api/users?page=" + uSahifa + "&filter=" + encodeURIComponent(uFiltr) +
              "&tartib=" + encodeURIComponent(uTartib) +
              (uQuery ? "&q=" + encodeURIComponent(uQuery) : "");
    var n = navbatOl("users");
    var d = await ol(yol);
    if (eskirganmi("users", n)) return;
    uSahifalar = d.sahifalar;

    ["all", "pro", "free", "ban", "nofaol"].forEach(function (k) {
      var el = $("c-" + k);
      if (el) el.textContent = son(d.sanoq[k]);
    });

    var body = $("urows");
    body.innerHTML = d.rows.length
      ? '<div class="rbosh"><span>Foydalanuvchi</span><span>Tarif</span><span>' +
        xavfsiz(S.user.tartib[uTartib]) + "</span></div>" +
        d.rows.map(function (u) {
          var vaqt = uTartib === "yangi" ? u.created_at : u.last_seen;
          // `data-un` — bosib turish menyusidagi «Telegram'da ochish» uchun.
          return '<div class="row bosiladi" data-uid="' + u.user_id + '" data-un="' +
            xavfsiz(u.username || "") + '">' +
            '<div class="person">' +
            avatar(shaxs(u), u.tarif === "pro" || u.tarif === "premium") +
            "<div><b>" + xavfsiz(nomi(u)) + '</b><span>' + xavfsiz(u.user_id) +
            "</span></div></div>" + yorliq(u.tarif) +
            '<span class="hint num">' + xavfsiz(vaqt ? nisbiy(vaqt) : S.yoq) + "</span></div>";
        }).join("")
      : boshHolat(uQuery ? S.bosh.qidiruv : S.bosh.user);

    $("u-holat").textContent = d.jami
      ? "Jami " + son(d.jami) + " ta · sahifa " + (uSahifa + 1) + "/" + uSahifalar
      : "Natija yo'q";
    S.ekran.users[1] = son(d.sanoq.all) + " ta · " + son(d.sanoq.pro) + " tasi Pro";
    $("u-orqaga").disabled = uSahifa <= 0;
    $("u-oldinga").disabled = uSahifa >= uSahifalar - 1;
    if (hozir === "users") yangilandiBelgisi();
  }

  function jadvalQayta() {
    jadvalYukla().catch(function (e) {
      console.error("[panel] jadval:", e);
      $("u-holat").textContent = S.yuklanmadi;
    });
  }

  /* ══ BITTA FOYDALANUVCHI ════════════════════════════════════════ */
  async function kartochka(uid) {
    var d = await ol("/api/users/" + uid);
    uOchiq = d;
    // Sarlavha — Telegram ismi (tg_ism), bo'lmasa @username, u ham
    // bo'lmasa «Foydalanuvchi». @username va ID esa pastki metada:
    // ism ko'rinadigan bo'lgach, ular alohida ko'rsatiladi.
    var nom = nomi(d);

    $("u-av").innerHTML = bosh(shaxs(d)) === null ? ODAM_SVG : xavfsiz(bosh(shaxs(d)));
    $("u-ism").textContent = nom;
    $("u-meta").textContent = (d.username ? "@" + d.username + " · " : "") +
      "ID " + d.user_id +
      (d.last_seen ? " · " + S.user.oxirgi + " " + nisbiy(d.last_seen) : "");
    // Username — t.me (hamma joyda ochiladi). Usernamesiz odam uchun
    // havola yo'q: bot sizga mention yuboradi (`/api/users/<id>/tglink`).
    var tgl = $("u-tg");
    tgl.href = d.username ? "https://t.me/" + encodeURIComponent(d.username) : "#";
    tgl.textContent = d.username ? "Telegram'da ochish ↗" : "Telegram'da ochish (botga yuboriladi) ↗";

    var tag = $("u-tag");
    tag.className = "tag" + (d.tarif === "ban" ? " ban" : (d.tarif === "free" ? "" : " pro"));
    tag.textContent = tarifNomi(d.tarif) +
      (d.tarif !== "free" && d.tarif !== "ban"
        ? (d.premium_until ? " · " + qisqa(d.premium_until) + S.user.gacha
                           : " · " + S.user.cheksiz)
        : "");

    // `limit === null` — cheksiz, `0` — bu tarifda imkoniyat yo'q.
    function chegara(v) { return v === null ? "∞" : son(v); }
    var facts = [
      { k: (META.limitlar && META.limitlar.points) || "Ballar",
        v: son(d.ballar.ishlatilgan) + " / " + chegara(d.ballar.limit) }
    ];
    d.sanoqlar.forEach(function (s) {
      facts.push({ k: s.nom, v: son(s.ishlatilgan) + " / " + chegara(s.limit) });
    });
    facts.push({ k: S.user.royxatdan, v: d.created_at ? qisqa(d.created_at) : S.yoq });
    facts.push({ k: "Jami so'rov", v: son(d.jami_sorov) });
    facts.push({ k: "Referal", v: d.referal.invited + " / " + d.referal.rewarded });
    $("u-facts").innerHTML = facts.map(function (f) {
      return '<div class="fact"><p class="k">' + xavfsiz(f.k) + '</p><p class="v">' +
             xavfsiz(f.v) + "</p></div>";
    }).join("");

    $("u-tolovlar").innerHTML = d.tolovlar.length
      ? d.tolovlar.map(function (t) {
          var oxiri = t.qaytarilgan
            ? '<span class="tag">Qaytarilgan</span>'
            : '<button class="btn sm danger" data-refund="' + t.id + '">Qaytarish</button>';
          return '<div class="row"><div class="t"><b>' + son(t.days) + " kun · " +
            son(t.stars) + " ⭐</b><span>" + xavfsiz(qisqa(t.sana)) + " · #" +
            xavfsiz(t.id) + "</span></div>" + oxiri + "</div>";
        }).join("")
      : boshHolat(S.bosh.tolov);

    $("a-ban").textContent = d.tarif === "ban" ? "Blokni ochish" : "Bloklash";
    $("a-kunlar").hidden = true;
    $("a-xabar").hidden = true;
    natija("");
    S.ekran.profil[1] = "ID " + d.user_id;
    go("profil");
  }

  function natija(matn, yomonmi) {
    var el = $("a-natija");
    el.innerHTML = matn ? xavfsiz(matn) : "&nbsp;";
    el.className = "natija" + (yomonmi ? " yomon" : "");
  }

  /* Telegram'ning o'z tasdiq oynasi; brauzerda oddiy `confirm`.
     ⚠️ Orqaga qaytarib bo'lmaydigan amal tasdiqsiz bajarilmaydi. */
  function tasdiq(savol) {
    return new Promise(function (hal) {
      if (tg && typeof tg.showConfirm === "function") {
        try { return tg.showConfirm(savol, function (ha) { hal(!!ha); }); }
        catch (e) { /* eski mijoz — pastdagi yo'l */ }
      }
      hal(window.confirm(savol));
    });
  }

  /* Telegram klaviaturasini yopadi. Saqlangandan keyin u ochiq qolsa
     natija xabari ham, o'zgargan ro'yxat ham klaviatura tagida
     ko'rinmaydi — odam nima bo'lganini bilmaydi.
     Eski mijozda metod yo'q, shuning uchun `typeof`. */
  function klaviaturaYop() {
    if (!tg || typeof tg.hideKeyboard !== "function") return;
    try { tg.hideKeyboard(); } catch (e) {}
  }

  /* Enter — formaning asosiy amali.
     ⚠️ `textarea` DA EMAS: u yerda Enter yangi qator, va uni o'g'irlash
     ko'p qatorli xabar yozishni buzardi.
     ⚠️ TUGMA O'CHIQ BO'LSA ISHLAMAYDI — `so_rov()` so'rov boshlanishida
     tugmani darhol o'chiradi, ya'ni Enter'ni bosib turish ikkinchi
     so'rov yubormaydi.
     ⚠️ `isComposing` — IME (masalan xitoycha klaviatura) so'z terish
     paytida ham Enter yuboradi; o'sha Enter forma uchun emas. */
  function enterBosilsa(idlar, tugmaId) {
    idlar.forEach(function (id) {
      var el = $(id);
      if (!el || el.tagName === "TEXTAREA") return;
      el.addEventListener("keydown", function (e) {
        if (e.key !== "Enter" || e.isComposing) return;
        e.preventDefault();
        var t = $(tugmaId);
        if (t && !t.disabled) t.click();
      });
    });
  }

  async function amal(yol, tana, muvaffaqiyat, tugma) {
    var j = await so_rov(yol, tana, null, tugma);
    if (!j.ok) {
      natija(j.xato, true);
      // ⚠️ 409 = kartadagi ma'lumot ESKIRGAN. Uni yangilamasdan
      // qoldirsak, admin o'sha eski raqamga qarab qayta bosardi va
      // yana 409 olardi — chiqib bo'lmaydigan halqa.
      if (j.status === 409 && uOchiq) {
        toast(S.eskirdi);
        qayta().catch(function (e) { console.error("[panel] 409:", e); });
      }
      return false;
    }
    natija(muvaffaqiyat + (j.d.xabar_yetdi === false ? S.natija.xabarYetmadi : ""));
    toast(muvaffaqiyat);
    return true;
  }

  async function qayta() {
    var matn = $("a-natija").innerHTML;
    if (uOchiq) {
      var uid = uOchiq.user_id;
      await kartochka(uid);
    }
    $("a-natija").innerHTML = matn;
    jadvalQayta();
  }

  async function qaytarish(payment_id, tugma) {
    // Pul yo'li: tasdiq QANCHA va NIMA bo'lishini aytsin. Server qaytarilgan
    // to'lovning kunlarini muddatdan AYIRADI (mark_payment_refunded) —
    // «tarif olib tashlanadi» deyish noto'g'ri edi: 200 kuni bor odamda
    // 90 kunlik to'lov qaytarilsa Pro qoladi.
    var t = ((uOchiq && uOchiq.tolovlar) || []).filter(function (x) { return x.id === payment_id; })[0];
    if (!await tasdiq(S.savol.refund(t ? son(t.stars) : "?", t ? t.days : "?"))) return;
    if (await amal("/api/payments/" + payment_id + "/refund", null,
                   S.natija.refund, tugma)) await qayta();
  }

  /* Kartochkada ko'rilgan tarif holati — server shuni tekshiradi.
     ⚠️ `plan_type`, `tarif` EMAS: `tarif` bloklangan odamni «ban» deb
     ko'rsatadi, bazadagi `plan_type` esa o'sha payt «pro» bo'lishi
     mumkin — ikkisi hech qachon solishtirilmasligi kerak. */
  function proHolati(d) {
    return { tarif: d.plan_type || "free", muddat: d.premium_until || null };
  }

  /* Muddatgacha necha kun qolgani. Server ham shu qoidadan foydalanadi
     (`_qolgan_kun`), ya'ni tasdiqdagi son auditdagisi bilan bir xil. */
  function qolganKun(iso) {
    var d = pars(iso);
    if (!d) return null;
    return Math.max(0, Math.floor((d.getTime() - Date.now()) / 86400000));
  }

  /* Tasdiq matni — TO'RT holat. Har biri boshqa narsani aytadi, chunki
     admin uchun ular boshqa-boshqa oqibat. */
  function proSavoli(d, kun) {
    var kim = nomi(d);
    var cheksizmi = d.plan_type !== "free" && !d.premium_until;
    if (kun === null) return S.savol.proCheksizga(kim);
    if (cheksizmi) return S.savol.proCheksizdan(kim, kun);
    if (d.plan_type !== "free" && d.premium_until) {
      return S.savol.proMuddat(kim, kun, qolganKun(d.premium_until),
                               qisqa(d.premium_until));
    }
    return S.savol.proFree(kim, kun);
  }

  function amallar() {
    $("a-pro").addEventListener("click", function () {
      titroq("light");
      $("a-xabar").hidden = true;
      $("a-kunlar").hidden = !$("a-kunlar").hidden;
    });
    $("a-kunlar").addEventListener("click", async function (e) {
      var b = e.target.closest("[data-kun]");
      if (!b || !uOchiq) return;
      var kun = b.dataset.kun === "inf" ? null : Number(b.dataset.kun);
      $("a-kunlar").hidden = true;
      if (!await tasdiq(proSavoli(uOchiq, kun))) return;
      // ⭐ `holat` — kartochkada KO'RILGAN qiymat. Server uni joriy
      // qiymat bilan tranzaksiya ichida solishtiradi va farq qilsa
      // HECH NARSA yozmaydi (409). Usiz ekran ochilgandan keyin kelgan
      // to'lov yoki promokod jimgina o'chib ketardi.
      if (await amal("/api/users/" + uOchiq.user_id + "/premium",
                     { kun: kun, holat: proHolati(uOchiq) },
                     S.natija.pro, b)) await qayta();
    });

    $("a-free").addEventListener("click", async function () {
      if (!uOchiq) return;
      if (!await tasdiq(S.savol.free)) return;
      if (await amal("/api/users/" + uOchiq.user_id + "/plan", { tarif: "free" },
                     S.natija.free, this)) await qayta();
    });

    $("a-quota").addEventListener("click", async function () {
      if (!uOchiq) return;
      // Tasdiq bilan: telefonda tasodifiy bosish odamga bugungi limitni
      // qaytadan berib yuborardi.
      if (!await tasdiq(S.savol.kvota)) return;
      if (await amal("/api/users/" + uOchiq.user_id + "/quota", null,
                     S.natija.kvota, this)) await qayta();
    });

    $("a-ban").addEventListener("click", async function () {
      if (!uOchiq) return;
      var bloklansinmi = uOchiq.tarif !== "ban";
      if (!await tasdiq(bloklansinmi ? S.savol.ban : S.savol.unban)) return;
      if (await amal("/api/users/" + uOchiq.user_id + "/ban", { ban: bloklansinmi },
                     bloklansinmi ? S.natija.ban : S.natija.unban, this)) await qayta();
    });

    // Kuzatuvga shu yerdan — ilgari ID'ni ko'chirib, Sozlamalarga o'tib,
    // qayta yozish kerak edi.
    $("a-kuzat").addEventListener("click", async function () {
      if (!uOchiq) return;
      if (!await tasdiq(S.savol.kuzat(nomi(uOchiq)))) return;
      if (await amal("/api/watch", { amal: "add", kim: String(uOchiq.user_id) },
                     S.natija.kuzat, this)) yuklangan.users = false;
    });

    $("a-msg").addEventListener("click", function () {
      titroq("light");
      $("a-kunlar").hidden = true;
      $("a-xabar").hidden = !$("a-xabar").hidden;
      if (!$("a-xabar").hidden) $("a-matn").focus();
    });
    $("a-bekor").addEventListener("click", function () { $("a-xabar").hidden = true; });
    $("a-yubor").addEventListener("click", async function () {
      if (!uOchiq) return;
      var matn = $("a-matn").value.trim();
      if (!matn) return natija("Matn bo'sh.", true);
      // Yuborilgan xabar qaytarilmaydi — tasdiqda kimga va matnning
      // boshi ko'rsatiladi, ya'ni noto'g'ri odamga yozish shu yerda
      // to'xtaydi.
      if (!await tasdiq(S.savol.xabar(nomi(uOchiq), parcha(matn)))) return;
      if (await amal("/api/users/" + uOchiq.user_id + "/message", { matn: matn },
                     S.natija.xabar, this)) {
        $("a-matn").value = "";
        $("a-xabar").hidden = true;
        klaviaturaYop();
      }
    });
    delegat("u-tolovlar", "data-refund", function (id, b) { qaytarish(Number(id), b); });
  }

  function jadval() {
    // Odam ko'rinadigan har ro'yxatdan — profilga (`kartochka` o'zi `go("profil")`).
    ["s-token", "s-top", "xatolar", "j-xatolar"].forEach(function (id) {
      delegat(id, "data-uid", function (uid) {
        if (Date.now() - menyuVaqt < 700) return;      // `urows` dagi izoh
        titroq("light");
        kartochka(Number(uid)).catch(function (e) {
          console.error("[panel] profil:", e);
          toast(S.yuklanmadi);
        });
      });
    });
    // Mini App ichida oddiy <a> Telegram'ni ochmaydi (WebView ichida
    // t.me sahifasi ochiladi) — Telegram'ning o'z usuli. Brauzerda
    // username bor bo'lsa — oddiy <a> o'zi ochadi.
    $("u-tg").addEventListener("click", function (e) {
      if (!uOchiq || (uOchiq.username && !tg)) return;
      e.preventDefault();
      telegramdaOch(uOchiq.user_id, uOchiq.username);
    });
    delegat("urows", "data-uid", function (uid) {
      // Bosib turish menyusi hozirgina ochilgan — barmoq uzilishidagi
      // «click» profilni ham ochib yubormasin.
      if (Date.now() - menyuVaqt < 700) return;
      titroq("light");
      kartochka(Number(uid)).catch(function (e) {
        console.error("[panel] kartochka:", e);
        toast(S.yuklanmadi);
      });
    });

    // Qidiruvda har harfga so'rov yubormaymiz — 300ms jim turadi.
    var kutish = null;
    $("q").addEventListener("input", function (e) {
      uQuery = e.target.value.trim();
      uSahifa = 0;
      clearTimeout(kutish);
      kutish = setTimeout(jadvalQayta, 300);
    });

    $("u-orqaga").addEventListener("click", function () {
      if (uSahifa > 0) { uSahifa--; titroq("light"); jadvalQayta(); }
    });
    $("u-oldinga").addEventListener("click", function () {
      if (uSahifa < uSahifalar - 1) { uSahifa++; titroq("light"); jadvalQayta(); }
    });

    amallar();
  }

  /* ══ YOZUV SO'ROVLARI ═══════════════════════════════════════════ */
  /* Tasdiq uchun: ro'yxat qatoridagi nom (ekranda ko'ringanining o'zi)
     va ID — «kimni o'chiryapman» tasdiq oynasida ko'rinsin. */
  function qatorNomi(tugma, uid) {
    var b = tugma && tugma.closest(".row") && tugma.closest(".row").querySelector("b");
    var nom = b ? b.textContent.trim() : "";
    return (nom && nom.indexOf(String(uid)) < 0 ? nom + " · " : "") + "ID " + uid;
  }

  function natijaChiz(id, matn, yomonmi) {
    var el = $(id);
    if (!el) return;
    el.innerHTML = matn ? xavfsiz(matn) : "&nbsp;";
    el.className = "natija" + (yomonmi ? " yomon" : "");
  }

  /* `tugma` — ixtiyoriy. Berilsa so'rov davomida O'CHIRILADI va
     `finally` da tiklanadi.

     ⚠️ Bu YAGONA himoya emas. Server tomonida ham `@bir_marta`
     turadi (`web/auth.py`): sekin tarmoqda yoki ikkinchi ilova
     oynasida tugma baribir ikki marta bosiladi, va o'shanda
     `set_user_premium(..., extend=True)` kunlarni IKKI MARTA
     qo'shardi. Ekran himoyasi buni ko'rinmas qiladi, server himoyasi
     esa bo'lmasligini kafolatlaydi — ikkalasi ham kerak.

     ⚠️ Matn faqat MATNLI tugmada almashadi: kalitcha (`.switch`)
     va ikonka tugmasida matn yo'q, u yerda «Bajarilmoqda…» maketni
     buzardi. */
  async function so_rov(yol, tana, usul, tugma) {
    var eski = null;
    if (tugma) {
      eski = tugma.innerHTML;
      tugma.disabled = true;
      if (tugma.textContent.trim()) tugma.textContent = S.bajarilmoqda;
    }
    var cfg = {
      method: usul || "POST",
      headers: imzo({ "Content-Type": "application/json" })
    };
    if (cfg.method !== "DELETE") cfg.body = JSON.stringify(tana || {});
    try {
      var r;
      try {
        r = await fetch(yol, cfg);
        sessiyaTugadimi(r);
      } catch (e) {
        titroq("xato");
        return { ok: false, d: {}, status: 0, xato: S.kirish.ulanmadi[1] };
      }
      var d = {};
      try { d = await r.json(); } catch (e) {}
      titroq(r.ok ? "ok" : "xato");
      return { ok: r.ok, d: d, status: r.status,
               xato: d.error || (S.natija.bajarilmadi + " (" + r.status + ")") };
    } finally {
      if (tugma) { tugma.disabled = false; tugma.innerHTML = eski; }
    }
  }

  /* ══ LIMITLAR ═══════════════════════════════════════════════════ */
  var LIMITLAR = null;
  var limitEski = null;      // «Bekor qilish» uchun oldingi qiymatlar

  function limitInput(tarif, kalit) {
    return document.querySelector('[data-lim="' + tarif + ":" + kalit + '"]');
  }

  async function limitlar() {
    var d = await ol("/api/limits");
    LIMITLAR = d;
    // ⚠️ Har limit — ALOHIDA kartochka, jadval qatori emas. Jadvalda
    // «Saqlash» va «↺» tugmalari o'ng chetda kesilib qolardi va
    // qator gorizontal siljish hosil qilardi (§2.3).
    $("l-rows").innerHTML = d.rows.map(function (r) {
      var maydonlar = d.tariflar.map(function (t) {
        var v = r.tariflar[t];
        return '<label style="display:flex;align-items:center;gap:var(--s-2);flex:1 1 130px;min-width:0">' +
          '<span class="hint" style="flex:1">' + xavfsiz(tarifNomi(t)) + "</span>" +
          '<input class="kiritish tor" type="number" inputmode="numeric" min="0" max="100000" ' +
          'step="1" data-lim="' + t + ":" + r.kalit + '" value="' +
          (v.qiymat === null ? "" : xavfsiz(v.qiymat)) + '" ' +
          'aria-label="' + xavfsiz(r.nom + " — " + tarifNomi(t)) + '">' +
          (v.ozgargan ? '<span class="tag warn">' + xavfsiz(S.limit.ozgargan) + "</span>" : "") +
          "</label>";
      }).join("");
      return '<div class="row" style="align-items:flex-start;flex-direction:column;gap:var(--s-2)">' +
        '<div style="display:flex;align-items:center;gap:var(--s-2);width:100%">' +
        "<div class=\"t\"><b>" + xavfsiz(r.nom) + "</b><span>" + xavfsiz(r.izoh) + "</span></div>" +
        '<button class="btn sm faqat-ikon" data-lreset="' + r.kalit + '" ' +
        'title="' + xavfsiz(S.limit.aslQaytar) + '" aria-label="' + xavfsiz(S.limit.aslQaytar) + '">↺</button>' +
        "</div>" +
        '<div style="display:flex;gap:var(--s-3);flex-wrap:wrap;width:100%">' + maydonlar + "</div>" +
        "</div>";
    }).join("");
    limitEski = joriyLimitlar();
    limitTugmasi();
  }

  /* Hozirgi holat — «Bekor qilish» uchun.
     ⚠️ Qiymatning O'ZI yetarli emas, `ozgargan` bayrog'i ham kerak.
     Sabab: o'zgartirilmagan limit ekranda config'dagi son bilan
     turadi (masalan 1000). Faqat sonni qaytarsak, bekor qilish o'sha
     1000 ni o'zgartirish sifatida YOZARDI — limit bir xil qolgan
     holda qatorda «o'zgartirilgan» yorlig'i paydo bo'lardi, ya'ni
     bekor qilish o'zidan keyin iz qoldirardi. */
  function joriyLimitlar() {
    var out = {};
    if (!LIMITLAR) return out;
    LIMITLAR.rows.forEach(function (r) {
      LIMITLAR.tariflar.forEach(function (t) {
        var el = limitInput(t, r.kalit);
        out[t + ":" + r.kalit] = {
          xom: el ? el.value.trim() : "",
          ozgargan: !!r.tariflar[t].ozgargan
        };
      });
    });
    return out;
  }

  /* O'zgargan maydonlar ro'yxati — MainButton shunga qarab chiqadi. */
  function limitOzgarishlari() {
    var out = [];
    if (!LIMITLAR) return out;
    LIMITLAR.rows.forEach(function (r) {
      LIMITLAR.tariflar.forEach(function (t) {
        var el = limitInput(t, r.kalit);
        if (!el) return;
        var xom = el.value.trim();
        var asl = r.tariflar[t].qiymat;
        if (xom === "" ? asl === null : Number(xom) === asl) return;
        out.push({ tarif: t, kalit: r.kalit, xom: xom, nom: r.nom });
      });
    });
    return out;
  }

  function limitTugmasi() {
    var ochiq = hozir === "system" &&
      document.querySelector('section[data-screen="system"] .pane[data-pane="limits"].on');
    var o = ochiq ? limitOzgarishlari() : [];
    asosiyTugma("Saqlash", o.length ? limitSaqla : null);
    // Telegramdan tashqarida MainButton yo'q — zaxira tugma.
    var b = $("l-saqla");
    if (b) b.hidden = !(o.length && !(tg && tg.MainButton));
  }

  /* Kiritilgan qiymatni tekshiradi. Xato bo'lsa sabab qaytadi (§4). */
  function limitXatosi(xom) {
    if (xom === "") return S.limit.bosh;
    if (!/^\d+$/.test(xom)) return S.limit.manfiy;
    if (Number(xom) > 100000) return S.limit.katta;
    return null;
  }

  async function limitSaqla() {
    var o = limitOzgarishlari();
    if (!o.length) return natijaChiz("l-natija", S.limit.ozgarishYoq);

    for (var i = 0; i < o.length; i++) {
      var x = limitXatosi(o[i].xom);
      if (x) {
        var el = limitInput(o[i].tarif, o[i].kalit);
        if (el) { el.classList.add("xato"); el.focus(); }
        return natijaChiz("l-natija", o[i].nom + ": " + x, true);
      }
    }
    document.querySelectorAll("[data-lim]").forEach(function (e) { e.classList.remove("xato"); });

    var oldingi = limitEski;
    for (var j = 0; j < o.length; j++) {
      var r = await so_rov("/api/limits",
        { tarif: o[j].tarif, kalit: o[j].kalit, qiymat: Number(o[j].xom) });
      if (!r.ok) return natijaChiz("l-natija", r.xato, true);
    }
    natijaChiz("l-natija", S.limit.kuchga);
    await limitlar();
    // 5 soniyalik «Bekor qilish»: oldingi qiymatlarni qaytaradi.
    toast(S.saqlandi, function () { limitQaytar(oldingi); });
  }

  async function limitQaytar(eski) {
    toastYop();
    if (!eski || !LIMITLAR) return;
    for (var kalit in eski) {
      if (!Object.prototype.hasOwnProperty.call(eski, kalit)) continue;
      var q = kalit.split(":");
      var h = eski[kalit];
      var el = limitInput(q[0], q[1]);
      if (el && el.value.trim() === h.xom && !hozirOzgargan(q[0], q[1])) continue;
      // `null` — «o'zgartirishni olib tashla», ya'ni config qiymatiga
      // qaytish. Bu CHEKSIZLIK EMAS (`web/api.py::limit_set` izohi).
      await so_rov("/api/limits", {
        tarif: q[0], kalit: q[1],
        qiymat: (h.ozgargan && h.xom !== "") ? Number(h.xom) : null
      });
    }
    await limitlar();
    natijaChiz("l-natija", S.bekorQilindi);
  }

  function hozirOzgargan(tarif, kalit) {
    var bor = false;
    if (!LIMITLAR) return false;
    LIMITLAR.rows.forEach(function (r) {
      if (r.kalit === kalit && r.tariflar[tarif].ozgargan) bor = true;
    });
    return bor;
  }

  async function limitTikla(kalit) {
    if (!await tasdiq(S.limit.aslSavol)) return;
    var oldingi = joriyLimitlar();
    for (var i = 0; i < LIMITLAR.tariflar.length; i++) {
      var j = await so_rov("/api/limits",
        { tarif: LIMITLAR.tariflar[i], kalit: kalit, qiymat: null });
      if (!j.ok) return natijaChiz("l-natija", j.xato, true);
    }
    await limitlar();
    natijaChiz("l-natija", S.limit.kuchga);
    toast(S.saqlandi, function () { limitQaytar(oldingi); });
  }

  /* ══ TEXNIK TA'TIL ══════════════════════════════════════════════ */
  async function tatil() {
    var d = await ol("/api/maintenance");
    $("maintSw").setAttribute("aria-pressed", d.active ? "true" : "false");
    $("avtoSw").setAttribute("aria-pressed", d.avtomat ? "true" : "false");
    $("m-matn").textContent = d.matn;
    $("m-textarea").value = d.matn;
    var h = d.holat, q = [];
    // Bot o'zi yoqqan ta'til — tuzalgach o'zi o'chadi (services/avto_tatil.py).
    if (d.avto) q.push(["Avtomatik yoqilgan", d.avto, "down"]);
    if (h.commit) q.push(["Oxirgi deploy", h.commit, ""]);
    q.push(["Ishlash muddati", h.ishlash, ""]);
    q.push(["Mavzu rejimi", h.mavzu ? "yoqiq" : "o'chiq", ""]);
    q.push(["Baza", h.baza ? "ulangan" : "ulanmagan", h.baza ? "up" : "down"]);
    q.push(["Model", h.model, ""]);
    // Javob tezligi, 24 soat: median (yarmi shundan tez) va 90% (o'ndan
    // to'qqiztasi shundan tez). «1-so'z» — foydalanuvchi birinchi so'zni
    // ko'rgan payt; matnda 1.5 s birlashtirish kutishi kirmaydi.
    var s = function (ms) { return ms == null ? "—" : (ms / 1000).toFixed(1) + " s"; };
    var tz = d.tezlik || [];
    if (!tz.length) q.push(["Javob tezligi", "24 soatda ma'lumot yo'q", ""]);
    tz.forEach(function (r) {
      q.push(["Tezlik · " + r.nom,
              "1-so'z " + s(r.ttft50) + " · to'liq " + s(r.jami50) +
              " (90%: " + s(r.ttft90) + " / " + s(r.jami90) + ") · " + r.soni + " ta", ""]);
    });
    $("m-holat").innerHTML = q.map(function (r) {
      return '<div class="kv"><span>' + xavfsiz(r[0]) + '</span><b class="' + r[2] + '">' +
             xavfsiz(r[1]) + "</b></div>";
    }).join("");
  }

  /* ══ KUZATISH ═══════════════════════════════════════════════════ */
  async function kuzatuv() {
    var d = await ol("/api/watch");
    kuzatuvBanner(d.holat, document.querySelector('.pane[data-pane="watch"]'));
    // Guruh qo'yilmagan bo'lsa kuzatuv UMUMAN ishlamaydi.
    $("w-guruh").textContent = d.guruh === null ? "qo'yilmagan" : d.guruh;
    $("w-rows").innerHTML = d.rows.length
      ? d.rows.map(function (u) {
          return '<div class="row"><div class="t"><b>' +
            xavfsiz(nomi(u)) + "</b><span>ID " + xavfsiz(u.user_id) + " · qo'shilgan " +
            xavfsiz(qisqa(u.added_at)) + "</span></div>" +
            (d.guruh === null ? '<span class="tag">guruh yo\'q</span>'
                              : '<span class="tag ok">Faol</span>') +
            '<button class="btn sm danger" data-wdel="' + u.user_id + '">O\'chirish</button></div>';
        }).join("")
      : boshHolat(S.bosh.kuzatuv);
  }

  /* ══ KARTA TO'LOVI ══════════════════════════════════════════════ */
  async function kartaSozlama() {
    var d = await ol("/api/karta");
    $("k-raqam").textContent = d.raqam ? d.raqam.replace(/(\d{4})(?=\d)/g, "$1 ") : S.karta.yoq;
    $("k-egasi").textContent = d.egasi || "—";
    // Forma — faqat superadmin; qolganlar ko'radi, yozolmaydi (server ham 403).
    $("k-forma").hidden = !d.ozgartira_oladi;
    $("k-ochir").hidden = !d.raqam;
    $("k-izoh").innerHTML =
      (d.ozgartira_oladi ? "" : "<b>" + xavfsiz(S.karta.faqatSuper) + "</b> ") +
      xavfsiz(S.karta.narx) + " " + d.narx.map(function (n) {
        return xavfsiz(n.nom) + " — <b>" + son(n.som) + " so'm</b>";
      }).join(", ") + ".";
  }

  /* ══ ADMINLAR ═══════════════════════════════════════════════════ */
  async function adminlar() {
    var d = await ol("/api/admins");
    $("ad-rows").innerHTML = d.rows.map(function (a) {
      var nom = a.nom || (a.username ? "@" + a.username : S.user.nomsiz);
      // Superadminni va o'zini o'chirish tugmasi KO'RSATILMAYDI. Bu
      // qulaylik, himoya emas — himoya serverda (`_check_can_remove_admin`).
      var tugma = (a.super || a.ozim) ? ""
        : '<button class="btn sm danger" data-addel="' + a.user_id + '">O\'chirish</button>';
      return '<div class="row"><div class="person">' +
        avatar(a.username ? "@" + a.username : (a.nom || "ID:" + a.user_id), a.super) +
        "<div><b>" + xavfsiz(nom) + "</b><span>" + xavfsiz(a.user_id) + "</span></div></div>" +
        '<span class="tag' + (a.super ? " pro" : "") + '">' +
        (a.super ? "Superadmin" : "Admin") + "</span>" +
        (a.ozim ? '<span class="tag">siz</span>' : "") + tugma + "</div>";
    }).join("");
  }

  async function sozlamalar() {
    skelet("l-rows", 4);
    await Promise.all([limitlar(), tatil(), kartaSozlama(), adminlar()]);
    yangilandiBelgisi();
  }

  /* ══ PROMOKODLAR ════════════════════════════════════════════════ */
  var KOD_HOLATI = {
    faol:    ["tag ok", "faol"],
    tugagan: ["tag", "tugagan"],
    bekor:   ["tag ban", "bekor"]
  };

  async function promokodlar() {
    var d = await ol("/api/promo");
    $("p-rows").innerHTML = d.rows.length
      ? '<div class="rbosh"><span>Kod</span><span>Beradi</span><span>Ishlatilgan</span><span>Amal qiladi</span><span></span></div>' +
        d.rows.map(function (c) {
          var h = KOD_HOLATI[c.holat] || ["tag", c.holat];
          var nomi = c.holat === "faol" ? S.kod.faol
                   : (c.holat === "bekor" ? S.kod.bekor
                   : (c.muddat && new Date(c.muddat) <= new Date() ? S.kod.muddat : S.kod.tugagan));
          // ⚠️ Ishlamaydigan kod XIRA turadi. Ilgari «1/1 ishlatilgan»
          // va «muddati o'tgan» kodlar faolidan hech qanday farq
          // qilmasdi — admin ularni hali ham yuborsa bo'ladi deb
          // o'ylardi (§4).
          return '<div class="row' + (c.holat === "faol" ? "" : " xira") + '">' +
            '<div class="t"><b><span class="code">' + xavfsiz(c.kod) + "</span> " +
            '<span class="' + h[0] + '">' + xavfsiz(nomi) + "</span></b>" +
            '</div>' +
            "<span>Pro · " + son(c.kun) + " kun</span>" +
            '<span class="num">' + son(c.ishlatilgan) + " / " + son(c.max) + "</span>" +
            '<span class="hint num">' + xavfsiz(c.muddat ? qisqa(c.muddat) : S.kod.muddatsiz) + "</span>" +
            '<span style="display:flex;gap:6px;justify-content:flex-end">' +
            '<button class="btn sm" data-pcopy="' + xavfsiz(c.kod) + '">' + S.kod.nusxa + "</button>" +
            (c.holat === "faol"
              ? '<button class="btn sm danger" data-pdel="' + xavfsiz(c.kod) + '">' + S.kod.toxtat + "</button>"
              : "") + "</span></div>";
        }).join("")
      : boshHolat(S.bosh.promo);
  }

  async function sovga() {
    var d = await ol("/api/giveaway");
    $("g-stats").innerHTML =
      '<div class="kv"><span>Faol kodlar</span><b>' + son(d.kodlar.faol) + " / " +
        son(d.kodlar.jami) + "</b></div>" +
      '<div class="kv"><span>Kod ishlatilgan</span><b>' + son(d.kodlar.ishlatilgan) + "</b></div>" +
      '<div class="kv"><span>Kod bilan berilgan</span><b>' + son(d.kodlar.kun) + " kun</b></div>" +
      '<div class="kv"><span>Referal takliflari</span><b>' + son(d.referal.taklif) + "</b></div>" +
      '<div class="kv"><span>Shartga yetgan</span><b>' + son(d.referal.yetgan) + "</b></div>" +
      '<div class="kv"><span>Mukofot olgan</span><b>' + son(d.referal.mukofot) + "</b></div>";
  }

  async function referal() {
    var d = await ol("/api/referral");
    $("r-required").value = d.required;
    $("r-required").max = d.chegara.required;
    $("r-days").value = d.reward_days;
    $("r-days").max = d.chegara.reward_days;
    $("r-izoh").innerHTML =
      "Bir odam eng ko'pi bilan <b>" + son(d.max_rewards) +
      " marta</b> mukofot oladi — bu chegara ataylab sozlanmaydi. " +
      "Chegaralar: do'stlar soni 1–" + son(d.chegara.required) +
      ", mukofot 1–" + son(d.chegara.reward_days) + " kun.";
  }

  async function promoEkran() {
    skelet("p-rows", 4);
    await Promise.all([promokodlar(), sovga(), referal(), tarqatmalar()]);
    yangilandiBelgisi();
  }

  /* ══ TARQATMA ═══════════════════════════════════════════════════ */
  async function tarqatmalar() {
    var d = await ol("/api/broadcasts");
    $("b-rows").innerHTML = d.rows.length
      ? d.rows.map(function (b) {
          return '<div class="row"><div class="t"><b>' + xavfsiz(b.segment) +
            "</b><span>#" + xavfsiz(b.id) + " · " + xavfsiz(qisqa(b.vaqt)) + "</span></div>" +
            '<button class="btn sm danger" data-bdel="' + b.id + '">Bekor</button></div>';
        }).join("")
      : boshHolat(S.bosh.tarqatma);
    yangilandiBelgisi();
  }

  /* ══ HODISALAR ══════════════════════════════════════════════════
     Ro'yxat ichidagi tugmalar HAR yuklashda qayta chiziladi, shuning
     uchun tinglovchi qatorga emas, ro'yxatga qo'yiladi (delegatsiya).
     Har chizishdan keyin qayta bog'lash — eskisi ustiga yangisini
     qo'yib, bitta bosishni ikki marta bajaradigan yo'l.            */
  function delegat(joyId, atribut, fn) {
    var joy = $(joyId);
    if (!joy) return;
    joy.addEventListener("click", function (e) {
      var b = e.target.closest("[" + atribut + "]");
      if (b && joy.contains(b)) fn(b.getAttribute(atribut), b);
    });
  }

  function sozlamaHodisalari() {
    delegat("l-rows", "data-lreset", function (k) {
      limitTikla(k).catch(function (e) { natijaChiz("l-natija", String(e), true); });
    });
    // Har o'zgarishda pastdagi «Saqlash» tugmasi qayta hisoblanadi.
    var ls = $("l-saqla");
    if (ls) ls.addEventListener("click", function () {
      limitSaqla().catch(function (e) { natijaChiz("l-natija", String(e), true); });
    });
    $("l-rows").addEventListener("input", function (e) {
      if (e.target.matches("[data-lim]")) {
        e.target.classList.remove("xato");
        limitTugmasi();
      }
    });

    $("maintSw").addEventListener("click", async function () {
      var sw = $("maintSw");
      var yoq = sw.getAttribute("aria-pressed") !== "true";
      if (yoq && !await tasdiq(S.savol.tatil)) return;
      var j = await so_rov("/api/maintenance", { active: yoq }, null, sw);
      if (!j.ok) return natijaChiz("m-natija", j.xato, true);
      // Kalitchani javobdan keyin qo'yamiz: so'rov yiqilsa ekranda
      // «yoqilgan» turib, aslida o'chiq qolib ketardi.
      sw.setAttribute("aria-pressed", j.d.active ? "true" : "false");
      natijaChiz("m-natija", j.d.active ? S.natija.tatilBor : S.natija.tatilYoq);
      toast(S.saqlandi);
      yuklangan.dash = false;      // sarlavhadagi holat yangilansin
    });

    $("avtoSw").addEventListener("click", async function () {
      var sw = $("avtoSw");
      var ochiq = sw.getAttribute("aria-pressed") !== "true";
      if (!ochiq && !await tasdiq(S.savol.avtomat)) return;
      var j = await so_rov("/api/maintenance", { avtomat: ochiq }, null, sw);
      if (!j.ok) return natijaChiz("m-natija", j.xato, true);
      // Javobdan keyin — so'rov yiqilsa ekran yolg'on gapirmasin.
      sw.setAttribute("aria-pressed", j.d.avtomat ? "true" : "false");
      natijaChiz("m-natija", j.d.avtomat ? S.natija.avtoOchiq : S.natija.avtoYopiq);
      toast(S.saqlandi);
    });

    $("m-tahrir").addEventListener("click", function () {
      titroq("light");
      $("m-forma").hidden = !$("m-forma").hidden;
      if (!$("m-forma").hidden) $("m-textarea").focus();
    });
    $("m-bekor").addEventListener("click", function () { $("m-forma").hidden = true; });
    $("m-saqla").addEventListener("click", async function () {
      var matn = $("m-textarea").value.trim();
      if (!matn) return natijaChiz("m-natija", "Matn bo'sh.", true);
      var j = await so_rov("/api/maintenance", { matn: matn }, null, this);
      if (!j.ok) return natijaChiz("m-natija", j.xato, true);
      $("m-matn").textContent = j.d.matn;
      $("m-forma").hidden = true;
      klaviaturaYop();
      natijaChiz("m-natija", S.natija.matn);
      toast(S.saqlandi);
    });

    $("w-guruh-tahrir").addEventListener("click", function () {
      titroq("light");
      $("w-guruh-forma").hidden = !$("w-guruh-forma").hidden;
      if (!$("w-guruh-forma").hidden) $("w-guruh-input").focus();
    });
    $("w-guruh-bekor").addEventListener("click", function () {
      $("w-guruh-forma").hidden = true;
    });
    $("w-guruh-saqla").addEventListener("click", async function () {
      var j = await so_rov("/api/watch",
                           { amal: "group", guruh: $("w-guruh-input").value.trim() },
                           null, this);
      if (!j.ok) return natijaChiz("w-natija", j.xato, true);
      $("w-guruh-forma").hidden = true;
      $("w-guruh-input").value = "";
      klaviaturaYop();
      natijaChiz("w-natija", S.natija.guruh);
      toast(S.saqlandi);
      await kuzatuv();
    });

    $("w-qosh").addEventListener("click", async function () {
      var kim = $("w-kim").value.trim();
      if (!kim) return natijaChiz("w-natija", "ID yoki @username yozing.", true);
      var j = await so_rov("/api/watch", { amal: "add", kim: kim }, null, this);
      if (!j.ok) return natijaChiz("w-natija", j.xato, true);
      $("w-kim").value = "";
      klaviaturaYop();
      natijaChiz("w-natija", S.natija.kuzatuvQosh);
      await kuzatuv();
    });
    delegat("w-rows", "data-wdel", async function (uid, b) {
      if (!await tasdiq(S.savol.kuzatuvOl(qatorNomi(b, uid)))) return;
      var j = await so_rov("/api/watch", { amal: "remove", kim: uid }, null, b);
      if (!j.ok) return natijaChiz("w-natija", j.xato, true);
      natijaChiz("w-natija", S.natija.kuzatuvOl);
      await kuzatuv();
    });

    async function kartaSaqla(tugma, raqam, egasi) {
      var j = await so_rov("/api/karta", { raqam: raqam, egasi: egasi }, null, tugma);
      if (!j.ok) return natijaChiz("k-natija", j.xato, true);
      $("k-raqam-input").value = "";
      $("k-egasi-input").value = "";
      klaviaturaYop();
      natijaChiz("k-natija", j.d.raqam ? S.natija.karta : S.natija.kartaOchiq);
      toast(S.saqlandi);
      await kartaSozlama();
    }
    $("k-saqla").addEventListener("click", async function () {
      var raqam = $("k-raqam-input").value.trim(), egasi = $("k-egasi-input").value.trim();
      if (!raqam || !egasi) return natijaChiz("k-natija", S.karta.ikkalasi, true);
      var raqamlar = raqam.replace(/[\s-]/g, "");
      if (!/^\d{16,19}$/.test(raqamlar)) return natijaChiz("k-natija", S.karta.raqam, true);
      if (!await tasdiq(S.savol.karta(raqamlar.replace(/(\d{4})(?=\d)/g, "$1 "), egasi))) return;
      await kartaSaqla(this, raqam, egasi);
    });
    $("k-ochir").addEventListener("click", async function () {
      if (!await tasdiq(S.savol.kartaOchir)) return;
      await kartaSaqla(this, "", "");
    });
    enterBosilsa(["k-raqam-input", "k-egasi-input"], "k-saqla");

    $("ad-qosh").addEventListener("click", async function () {
      var kim = $("ad-kim").value.trim();
      if (!/^\d{1,19}$/.test(kim)) return natijaChiz("ad-natija", "Sonli ID yozing.", true);
      // ⛔️ Tasdiqda KIM ekanligi. Avval odam topiladi: bot uni bilmasa —
      // umuman so'ralmaydi (server ham rad etadi, bu faqat aniqroq xabar).
      var r;
      try { r = await fetch("/api/users/" + kim, { headers: imzo() }); }
      catch (e) { return natijaChiz("ad-natija", S.kirish.ulanmadi[1], true); }
      sessiyaTugadimi(r);
      if (r.status === 404 || r.status === 400) return natijaChiz("ad-natija", S.savol.adminTopilmadi, true);
      if (!r.ok) return natijaChiz("ad-natija", S.yuklanmadi, true);
      var odam = await r.json();
      var kimligi = nomi(odam) + (odam.tg_ism && odam.username ? " (@" + odam.username + ")" : "") +
                    " · ID " + odam.user_id;
      if (!await tasdiq(S.savol.adminQosh + "\n\n" + kimligi)) return;
      var j = await so_rov("/api/admins", { amal: "add", kim: kim }, null, this);
      if (!j.ok) return natijaChiz("ad-natija", j.xato, true);
      $("ad-kim").value = "";
      klaviaturaYop();
      natijaChiz("ad-natija", S.natija.adminQosh);
      await adminlar();
    });
    // Enter — formaning asosiy amali. Sozlamalardagi uchala forma ham
    // BIR QATORLI input bilan, ya'ni Enter uchun to'sqinlik yo'q.
    enterBosilsa(["w-guruh-input"], "w-guruh-saqla");
    enterBosilsa(["w-kim"], "w-qosh");
    enterBosilsa(["ad-kim"], "ad-qosh");

    delegat("ad-rows", "data-addel", async function (uid, b) {
      if (!await tasdiq(S.savol.adminOl(qatorNomi(b, uid)))) return;
      var j = await so_rov("/api/admins", { amal: "remove", kim: uid }, null, b);
      if (!j.ok) return natijaChiz("ad-natija", j.xato, true);
      natijaChiz("ad-natija", S.natija.adminOl);
      await adminlar();
    });
  }

  function promoHodisalari() {
    $("p-yangi").addEventListener("click", function () {
      titroq("light");
      $("p-forma").hidden = !$("p-forma").hidden;
      if (!$("p-forma").hidden) $("p-kod").focus();
    });
    $("p-bekor").addEventListener("click", function () { $("p-forma").hidden = true; });
    $("p-yarat").addEventListener("click", async function () {
      var j = await so_rov("/api/promo", {
        amal: "create",
        kod: $("p-kod").value.trim(),
        kun: $("p-kun").value.trim(),
        max: $("p-max").value.trim(),
        muddat: $("p-muddat").value.trim()
      }, null, this);
      if (!j.ok) return natijaChiz("p-natija", j.xato, true);
      ["p-kod", "p-kun", "p-max", "p-muddat"].forEach(function (id) { $(id).value = ""; });
      $("p-forma").hidden = true;
      klaviaturaYop();
      natijaChiz("p-natija", j.d.kod + " yaratildi. Odamlarga yuborish uchun botda /kod.");
      toast(S.saqlandi);
      await promokodlar();
    });

    // Promo va referal formalari: hamma maydon bir qatorli.
    // ⛔️ `g-kimlar` — `textarea`, u ataylab YO'Q: u yerda Enter yangi
    // qator va ro'yxat bir necha qatorga yoziladi.
    enterBosilsa(["p-kod", "p-kun", "p-max", "p-muddat"], "p-yarat");
    enterBosilsa(["r-required", "r-days"], "r-saqla");

    delegat("p-rows", "data-pcopy", function (kod) {
      // ⚠️ `navigator.clipboard` faqat xavfsiz ulanishda ishlaydi;
      // Telegram Mini App har doim HTTPS, lekin rad etilishi ham
      // mumkin — o'shanda kod ekranda ko'rinib turadi, ya'ni admin
      // uni qo'lda ko'chira oladi.
      try {
        navigator.clipboard.writeText(kod).then(function () {
          titroq("light"); toast(S.nusxa);
        }, function () { toast(kod); });
      } catch (e) { toast(kod); }
    });

    delegat("p-rows", "data-pdel", async function (kod, b) {
      if (!await tasdiq(kod + S.kod.toxtatSavol)) return;
      var j = await so_rov("/api/promo", { amal: "revoke", kod: kod }, null, b);
      if (!j.ok) return natijaChiz("p-natija2", j.xato, true);
      natijaChiz("p-natija2", kod + " to'xtatildi.");
      toast(S.saqlandi);
      await promokodlar();
    });

    $("g-yubor").addEventListener("click", async function () {
      var kimlar = $("g-kimlar").value.trim();
      if (!kimlar) return natijaChiz("g-natija", "Kimga? ID yoki @username yozing.", true);
      // ⚠️ Tasdiqdan OLDIN: necha kishi va necha kun. Ilgari «Bepul Pro
      // berilsinmi?» deyilardi — 0 yoki 99 999 kun uchun ham, 21 kishi
      // uchun ham (21-chisi esa serverda jimgina tushib qolardi).
      var soni = kimlar.split(/[\s,]+/).filter(Boolean).length;
      var kunMatn = $("g-kun").value.trim(), kun = Number(kunMatn);
      if (soni > META.sovga_max) {
        return natijaChiz("g-natija", S.sovgaKop(META.sovga_max, soni), true);
      }
      if (!/^\d+$/.test(kunMatn) || kun < 1 || kun > META.kun_max) {
        return natijaChiz("g-natija", S.sovgaKun(META.kun_max), true);
      }
      if (!await tasdiq(S.savol.sovga(soni, kun))) return;
      var j = await so_rov("/api/giveaway",
                           { kimlar: kimlar, kun: $("g-kun").value.trim() },
                           null, this);
      if (!j.ok) return natijaChiz("g-natija", j.xato, true);
      var d = j.d, q = [];
      if (d.berildi.length) q.push(d.berildi.length + " tasiga berildi");
      // ⚠️ «Yetmadi» — Pro BERILGAN, faqat xabar bormagan. Admin buni
      // «bajarilmadi» deb tushunib, ikkinchi marta bermasligi kerak.
      if (d.yetmadi.length) q.push(d.yetmadi.length + " tasiga berildi, lekin xabar yetmadi");
      if (d.topilmadi.length) q.push("topilmadi: " + d.topilmadi.join(", "));
      natijaChiz("g-natija", q.join(" · "), !d.berildi.length && !d.yetmadi.length);
      if (d.berildi.length || d.yetmadi.length) $("g-kimlar").value = "";
      klaviaturaYop();
      await sovga();
    });

    $("r-saqla").addEventListener("click", async function () {
      var j = await so_rov("/api/referral", {
        required: $("r-required").value.trim(),
        reward_days: $("r-days").value.trim()
      }, null, this);
      if (!j.ok) return natijaChiz("r-natija", j.xato, true);
      klaviaturaYop();
      natijaChiz("r-natija", j.d.required + " ta do'st → " + j.d.reward_days + " kun Pro.");
      toast(S.saqlandi);
      await referal();
    });
  }

  function tarqatmaHodisalari() {
    delegat("b-rows", "data-bdel", async function (bid, b) {
      if (!await tasdiq(S.savol.tarqatma)) return;
      var j = await so_rov("/api/broadcasts/" + bid, null, "DELETE", b);
      if (!j.ok) return natijaChiz("b-natija", j.xato, true);
      natijaChiz("b-natija", S.bekorQilindi);
      await tarqatmalar();
    });
  }

  function toastHodisalari() {
    var b = $("toast-bekor");
    if (b) b.addEventListener("click", function () {
      if (bekorFn) bekorFn();
      else toastYop();
    });
  }

  function chiqish() {
    $("chiqish").addEventListener("click", async function () {
      titroq("medium");
      try { await fetch("/api/logout", { method: "POST", headers: imzo() }); } catch (e) {}
      if (tg) tg.close();
      else xatoKorsat(S.kirish.yopildi);
    });
    var q = $("qayta");
    if (q) q.addEventListener("click", function () { korsat("yuklash"); kir(); });
  }

  /* ══ TELEGRAM'DA OCHISH / NUSXALASH — profil va menyu uchun bitta ══ */
  async function telegramdaOch(uid, un) {
    // Username'siz odamning ochiq havolasi yo'q — bot adminga mention
    // yuboradi (`/api/users/<id>/tglink`, WEB_PANEL.md).
    if (!un) {
      var j = await so_rov("/api/users/" + uid + "/tglink");
      toast(j.ok ? S.menyu.tglinkKetdi : j.xato);
      return;
    }
    var url = "https://t.me/" + encodeURIComponent(un);
    if (tg && tg.openTelegramLink) { try { return tg.openTelegramLink(url); } catch (e) {} }
    window.open(url, "_blank", "noopener");
  }

  function nusxala(matn) {
    // ⚠️ `navigator.clipboard` rad etilishi mumkin — o'shanda matn
    // toast'da ko'rinadi, ya'ni qo'lda ko'chirsa bo'ladi.
    try {
      navigator.clipboard.writeText(matn).then(function () {
        titroq("light"); toast(S.nusxa + " · " + matn);
      }, function () { toast(matn); });
    } catch (e) { toast(matn); }
  }

  /* ══ VARAQNI TORTIB YOPISH ═════════════════════════════════════
     iOS varag'idek: varaq TEPADA turganda pastga tortilsa barmoqqa
     ergashadi; yetarlicha (130px) yoki tez tortilsa yopiladi, aks holda
     joyiga qaytadi. Varaq ichida aylantirilgan bo'lsa — bu oddiy
     aylantirish, yopish emas. Kiritish maydoni ustida — ham. */
  function varaqSurish() {
    var sec = document.querySelector('section[data-screen="profil"]');
    var p = $("parda");
    if (!sec) return;
    var y0 = null, dy = 0, t0 = 0, sur = false;
    sec.addEventListener("touchstart", function (e) {
      y0 = null;
      if (!varaq || e.touches.length !== 1 || sec.scrollTop > 0) return;
      if (e.target.closest && e.target.closest("input, textarea, select")) return;
      y0 = e.touches[0].clientY; t0 = Date.now(); dy = 0; sur = false;
    }, { passive: true });
    sec.addEventListener("touchmove", function (e) {
      if (y0 === null) return;
      dy = e.touches[0].clientY - y0;
      if (!sur) {
        if (dy < -4) { y0 = null; return; }     // yuqoriga — aylantirish
        if (dy < 8) return;
        sur = true;
        sec.style.transition = "none";
        if (p) p.style.transition = "none";
      }
      e.preventDefault();
      var d = dy - 8;
      sec.style.transform = "translateY(" + Math.max(0, d) + "px)";
      if (p) p.style.opacity = String(Math.max(0, 1 - d / (sec.offsetHeight || 600)));
    }, { passive: false });
    function tugat() {
      if (y0 === null) return;
      y0 = null;
      if (!sur) return;
      sur = false;
      var tezlik = dy / Math.max(1, Date.now() - t0);          // px/ms
      if (dy > 130 || (dy > 40 && tezlik > 0.5)) {
        titroq("light");
        go(oxirgiRoyxat);
        return;
      }
      sec.style.transition = "transform .25s cubic-bezier(.32,.72,0,1)";
      sec.style.transform = "";
      if (p) { p.style.transition = "opacity .25s"; p.style.opacity = ""; }
    }
    sec.addEventListener("touchend", tugat);
    sec.addEventListener("touchcancel", tugat);
  }

  /* Telefon burildi (iPhone yonboshida 932px — kompyuter maketi) yoki
     oyna o'zgardi: varaq va ichki sahifa bir-biriga almashadi. Aks holda
     kompyuter maketida ikkita bo'lim ustma-ust chizilardi. */
  function maketAlmashdi() {
    menyuYop();
    sarlavhaHolati();
    if (hozir !== "profil") return;
    var sec = document.querySelector('section[data-screen="profil"]');
    var tel = telefonmi(), t;
    if (!tel && varaq) {
      varaq = false;
      $("parda").hidden = true;
      document.documentElement.classList.remove("varaqli");
      document.querySelectorAll("section[data-screen]").forEach(function (s) {
        s.classList.toggle("on", s === sec);
      });
      t = S.ekran.profil;
    } else if (tel && !varaq) {
      varaq = true;
      document.querySelectorAll("section[data-screen]").forEach(function (s) {
        s.classList.toggle("on", s === sec || s.dataset.screen === oxirgiRoyxat);
      });
      pardaKorsat(false);
      document.documentElement.classList.add("varaqli");
      t = S.ekran[oxirgiRoyxat] || ["", ""];
    } else return;
    sarlavhaYoz(t[0], t[1] === null ? bugunMatn() : t[1]);
    sarlavhaHolati();
  }

  /* ══ PASTGA TORTIB YANGILASH (telefon) ═════════════════════════
     Faqat O'QILADIGAN bo'limlarda (`YANGILANADI`: Boshqaruv, Odamlar,
     Hisobot). ⛔️ Sozlamalar va O'sish'da YO'Q — xuddi avtomatik
     yangilanishdagi sabab: qayta chizish yozilgan, hali saqlanmagan
     limit va promo qiymatlarini o'chirib yuborardi.
     Telegram'ning o'z «pastga tortib yopish»i o'chirilgan
     (`disableVerticalSwipes`), ya'ni bu harakat bilan to'qnashmaydi. */
  function tortibYangilash() {
    var wrap = $("wrap"), ptr = $("ptr");
    if (!wrap || !ptr) return;
    var CHEGARA = 64, y0 = null, d = 0, faol = false, oshdi = false, band = false;
    function joyiga() {
      wrap.style.transition = ptr.style.transition =
        "transform .3s cubic-bezier(.32,.72,0,1), opacity .3s";
      wrap.style.transform = "";
      ptr.style.transform = "";
      ptr.style.opacity = "0";
      ptr.classList.remove("aylanadi");
      // ⚠️ `transform` .wrap'da QOLMASIN: u ichidagi `position:fixed`
      // (profil varag'i) uchun yangi asos bo'lib, varaqni sindirardi.
      setTimeout(function () { wrap.style.transition = ptr.style.transition = ""; }, 320);
    }
    document.addEventListener("touchstart", function (e) {
      y0 = null;
      if (band || varaq || menyuOchiq || qulfYopiq || !telefonmi() || !YANGILANADI[hozir]) return;
      if (e.touches.length !== 1 || window.scrollY > 0 || !e.target.closest) return;
      if (!e.target.closest("#wrap") ||
          e.target.closest(".chart, .xarita, input, textarea, .subtabs, .chips")) return;
      y0 = e.touches[0].clientY; d = 0; faol = false; oshdi = false;
    }, { passive: true });
    document.addEventListener("touchmove", function (e) {
      if (y0 === null) return;
      var dy = e.touches[0].clientY - y0;
      if (!faol) {
        if (dy < -4 || window.scrollY > 0) { y0 = null; return; }
        if (dy < 10) return;
        faol = true;
        wrap.style.transition = ptr.style.transition = "none";
      }
      e.preventDefault();
      d = Math.min(120, (dy - 10) * 0.5);          // qarshilik: barmoqning yarmi
      wrap.style.transform = "translateY(" + d + "px)";
      ptr.style.opacity = String(Math.min(1, d / CHEGARA));
      ptr.style.transform = "translateY(" + (d - 44) + "px) rotate(" + Math.round(d * 5) + "deg)";
      var endi = d >= CHEGARA;
      if (endi !== oshdi) { oshdi = endi; if (endi) titroq("light"); }
    }, { passive: false });
    function tugat() {
      if (y0 === null) return;
      y0 = null;
      if (!faol) return;
      faol = false;
      if (!oshdi) return joyiga();
      band = true;
      wrap.style.transition = ptr.style.transition = "transform .2s cubic-bezier(.32,.72,0,1)";
      wrap.style.transform = "translateY(" + (CHEGARA - 8) + "px)";
      ptr.style.transform = "translateY(" + (CHEGARA - 52) + "px)";
      ptr.classList.add("aylanadi");
      yuklangan[hozir] = false;
      // Kamida yarim soniya — aks holda tez tarmoqda belgi «miltillab» o'tadi.
      Promise.all([ekranYukla(hozir), new Promise(function (r) { setTimeout(r, 500); })])
        .then(function () { band = false; joyiga(); titroq("tanlov"); });
    }
    document.addEventListener("touchend", tugat);
    document.addEventListener("touchcancel", tugat);
  }

  /* ══ BOSIB TURISH MENYUSI ══════════════════════════════════════
     Odam qatorini ~0,5 s bosib turish (kompyuterda — o'ng tugma):
     profilni ochmasdan tez amallar. ⚠️ Faqat QAYTARILADIGAN yoki tasdiq
     so'raydigan amallar — bloklash, Pro berish bu yerda YO'Q: bitta
     noto'g'ri barmoq harakati odamni bloklab qo'ymasin. */
  var menyuOchiq = false, menyuQator = null, menyuVaqt = 0;
  var MENYU_IKON = {
    och:   '<path d="M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    id:    '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/>',
    tg:    '<path d="M21.5 4.5 2.5 11l6 2.2L18 7l-7 8.3V21l3-4 4.5 2z"/>',
    kuzat: '<path d="M2 12s3.6-6 10-6 10 6 10 6-3.6 6-10 6-10-6-10-6z"/><circle cx="12" cy="12" r="2.6"/>'
  };

  function menyuOch(row, x, y) {
    var m = $("menyu");
    if (!m || !row) return;
    menyuYop();
    var uid = row.getAttribute("data-uid");
    var nomEl = row.querySelector("b");
    var nom = nomEl ? nomEl.textContent.trim() : "ID " + uid;
    m.dataset.uid = uid;
    m.dataset.un = row.getAttribute("data-un") || "";
    m.dataset.nom = nom;
    m.innerHTML = "<b>" + xavfsiz(nom) + "</b>" +
      [["och", S.menyu.och], ["id", S.menyu.id(uid)], ["tg", S.menyu.tg], ["kuzat", S.menyu.kuzat]]
        .map(function (q) {
          return '<button role="menuitem" data-m="' + q[0] + '"><svg viewBox="0 0 24 24" aria-hidden="true">' +
                 MENYU_IKON[q[0]] + "</svg>" + xavfsiz(q[1]) + "</button>";
        }).join("");
    menyuQator = row;
    row.classList.add("menyuda");
    pardaKorsat(true);
    m.hidden = false;
    menyuOchiq = true;
    menyuVaqt = Date.now();

    // Joylash: qator ostida; joy bo'lmasa — ustida. Ekrandan chiqmasin
    // (telefonda pastki tab-panel ham hisobga olinadi).
    var r = row.getBoundingClientRect();
    var vw = document.documentElement.clientWidth, vh = window.innerHeight;
    var past = telefonmi() && $("tabbar") ? $("tabbar").offsetHeight : 0;
    var mw = m.offsetWidth, mh = m.offsetHeight;
    var chap = Math.max(12, Math.min(vw - mw - 12, x !== undefined ? x : r.left + 8));
    var tepa = y !== undefined ? y : r.bottom + 8;
    var ustida = tepa + mh > vh - past - 12;
    if (ustida) tepa = (y !== undefined ? y : r.top - 8) - mh;
    m.classList.toggle("tepada", ustida);
    m.style.left = chap + "px";
    m.style.top = Math.max(12, tepa) + "px";
  }

  function menyuYop() {
    if (!menyuOchiq) return;
    menyuOchiq = false;
    $("menyu").hidden = true;
    if (menyuQator) menyuQator.classList.remove("menyuda");
    menyuQator = null;
    if (!varaq) $("parda").hidden = true;
  }

  async function menyuAmal(amal) {
    var m = $("menyu");
    var uid = Number(m.dataset.uid), un = m.dataset.un, nom = m.dataset.nom;
    menyuYop();
    if (amal === "och") {
      titroq("light");
      return kartochka(uid).catch(function (e) {
        console.error("[panel] menyu → profil:", e);
        toast(S.yuklanmadi);
      });
    }
    if (amal === "id") return nusxala(String(uid));
    if (amal === "tg") return telegramdaOch(uid, un);
    if (amal === "kuzat") {
      // Profildagi tugma bilan AYNAN bir xil tasdiq va so'rov.
      if (!await tasdiq(S.savol.kuzat(nom))) return;
      var j = await so_rov("/api/watch", { amal: "add", kim: String(uid) });
      toast(j.ok ? S.natija.kuzatuvQosh : j.xato);
      if (j.ok) yuklangan.users = false;
    }
  }

  function bosibTurish() {
    var vaqtlagich = null, x0 = 0, y0 = 0, uzoq = false;
    ["urows", "s-top"].forEach(function (id) {
      var joy = $(id);
      if (!joy) return;
      joy.addEventListener("touchstart", function (e) {
        var row = e.target.closest && e.target.closest("[data-uid]");
        uzoq = false;
        clearTimeout(vaqtlagich);
        if (!row || e.touches.length !== 1) return;
        x0 = e.touches[0].clientX; y0 = e.touches[0].clientY;
        vaqtlagich = setTimeout(function () {
          vaqtlagich = null;
          uzoq = true;
          titroq("medium");
          menyuOch(row);
        }, 480);
      }, { passive: true });
      joy.addEventListener("touchmove", function (e) {
        if (!vaqtlagich) return;
        var t = e.touches[0];
        // Barmoq siljidi — bu aylantirish, bosib turish emas.
        if (Math.abs(t.clientX - x0) > 8 || Math.abs(t.clientY - y0) > 8) {
          clearTimeout(vaqtlagich); vaqtlagich = null;
        }
      }, { passive: true });
      joy.addEventListener("touchend", function (e) {
        clearTimeout(vaqtlagich); vaqtlagich = null;
        // Menyu ochildi — barmoq uzilishidagi «click» profilni ochmasin.
        if (uzoq && e.cancelable) e.preventDefault();
      }, { passive: false });
      joy.addEventListener("touchcancel", function () { clearTimeout(vaqtlagich); vaqtlagich = null; });
      // Kompyuterda o'ng tugma; Android bosib turishda ham shuni yuboradi —
      // menyu allaqachon ochiq bo'lsa ikkinchi marta ochilmaydi.
      joy.addEventListener("contextmenu", function (e) {
        var row = e.target.closest && e.target.closest("[data-uid]");
        if (!row) return;
        e.preventDefault();
        if (menyuOchiq && menyuQator === row) return;
        menyuOch(row, e.touches ? undefined : e.clientX, e.touches ? undefined : e.clientY);
      });
    });
    delegat("menyu", "data-m", function (amal) { menyuAmal(amal); });
    $("parda").addEventListener("click", function () {
      if (menyuOchiq) return menyuYop();
      if (varaq) { titroq("light"); go(oxirgiRoyxat); }
    });
    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      if (menyuOchiq) menyuYop();
      else if (varaq) go(oxirgiRoyxat);
    });
    // Sahifa siljisa menyu yopiladi (qatoridan ajralib qolmasin). Ochilgandan
    // keyingi 300 ms hisobga olinmaydi — iOS inersiyasi uni darhol yopardi.
    window.addEventListener("scroll", function () {
      if (Date.now() - menyuVaqt > 300) menyuYop();
    }, { passive: true });
    window.addEventListener("resize", maketAlmashdi);
    // Maket chegarasi (900px) kesib o'tilganda — ba'zi WebView'larda
    // burilishda `resize` kechikadi, media-so'rov hodisasi esa aniq.
    var mq = window.matchMedia && window.matchMedia("(max-width:900px)");
    if (mq && mq.addEventListener) mq.addEventListener("change", maketAlmashdi);
    else if (mq && mq.addListener) mq.addListener(maketAlmashdi);
  }

  /* ══ ISHGA TUSHIRISH ════════════════════════════════════════════ */
  qism("telegram", telegram);
  qism("navigatsiya", navigatsiya);
  qism("grafik", grafikHodisalari);
  qism("jadval", jadval);
  qism("jurnal", jurnalNav);
  qism("sozlama", sozlamaHodisalari);
  qism("promo", promoHodisalari);
  qism("tarqatma", tarqatmaHodisalari);
  qism("toast", toastHodisalari);
  qism("qulf", qulfHodisalari);
  qism("katta-sarlavha", kattaSarlavha);
  qism("varaq", varaqSurish);
  qism("tortib-yangilash", tortibYangilash);
  qism("bosib-turish", bosibTurish);
  qism("chiqish", chiqish);
  kir();
})();
