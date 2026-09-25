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
 * serverdan `/api/meta` orqali keladi. Sabab `CLAUDE.md` da: shu
 * loyihada qo'lda ko'chirilgan ro'yxat BESH marta eskirgan.
 */
(function () {
  "use strict";

  var tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
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
    }
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

  function titroq(turi) {
    if (!tg || !tg.HapticFeedback) return;
    try {
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

  /* ══ DARVOZA ════════════════════════════════════════════════════ */
  function korsat(kim) {
    ["yuklash", "xato", "shell"].forEach(function (id) {
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
    var w = s.replace(/[^A-Za-zЀ-ӿ' ]/g, " ").trim().split(/\s+/);
    var t = ((w[0] || "?")[0] || "?") + ((w[1] || "")[0] || "");
    return t.toUpperCase();
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
    var ism = (ma && ma.ism) || "Admin";
    var n = $("who-ism"), a = $("who-av"), r = $("who-rol");
    if (n) n.textContent = ism;
    if (a) a.innerHTML = bosh(ism) === null ? ODAM_SVG : xavfsiz(bosh(ism));
    if (r && ma && ma.rol) r.textContent = ma.rol;
    korsat("shell");
    olcham();

    // ⚠️ Lug'at ekranlardan OLDIN. Tarif nomlari undan olinadi va
    // ular bo'lmasa jadval «undefined» bilan chiziladi.
    try { META = await ol("/api/meta"); } catch (e) { META = null; }
    if (!META) META = { tariflar: {}, ranglar: {}, limitlar: {}, limit_izohi: {},
                        // `EKSPORT_MAX` ning zaxirasi: lug'at kelmasa
                        // tasdiq matni «0 qator» deb yolg'on gapirmasin.
                        eksport_max: 5000,
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

  function go(name, pane) {
    document.querySelectorAll("section[data-screen]").forEach(function (s) {
      s.classList.toggle("on", s.dataset.screen === name);
    });
    // ⚠️ Profil — ICHKI sahifa, ya'ni u ochilganda pastdagi tab
    // «Foydalanuvchilar» bo'lib yonib turishi kerak: odam o'sha
    // bo'limning ichida.
    var faol = name === "profil" ? "users" : name;
    document.querySelectorAll("#nav button, #tabbar button").forEach(function (b) {
      if (b.dataset.go) b.setAttribute("aria-current", b.dataset.go === faol ? "true" : "false");
    });
    var t = S.ekran[name] || ["", ""];
    var ttl = $("title"), crumb = $("crumb");
    if (ttl) ttl.textContent = t[0];
    if (crumb) crumb.textContent = t[1] === null ? bugunMatn() : t[1];
    if (pane) showPane(name, pane);
    if (name !== "profil") oxirgiRoyxat = name;
    hozir = name;
    orqaTugma();
    limitTugmasi();
    ekranYukla(name);
    window.scrollTo({ top: 0, behavior: "instant" });
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
      b.setAttribute("aria-current", b.dataset.pane === pane ? "true" : "false");
    });
    sec.querySelectorAll(".pane").forEach(function (p) {
      p.classList.toggle("on", p.dataset.pane === pane);
    });
    limitTugmasi();
  }

  function navigatsiya() {
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
        titroq("light");
        showPane(bar.dataset.tabs, b.dataset.pane);
      });
    });
    if (tg && tg.BackButton) {
      tg.BackButton.onClick(function () { titroq("light"); go(oxirgiRoyxat); });
    }
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

  function son(n) {
    return Number(n || 0).toLocaleString("ru-RU").replace(/,/g, " ").replace(/ /g, " ");
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

  async function ol(yol) {
    var r = await fetch(yol, { headers: imzo() });
    if (!r.ok) throw new Error(yol + " → " + r.status);
    return r.json();
  }

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
    var crumb = $("crumb");
    if (!crumb) return;
    var t = S.ekran[hozir] || ["", ""];
    var asos = t[1] === null ? bugunMatn() : (t[1] || "");
    crumb.textContent = asos + (asos ? " · " : "") +
      S.yangilandi.toLowerCase() + " " + soat(new Date().toISOString());
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

    var qism = [t.foiz + "% · " + million(t.grant) + " dan"];
    if (t.keshdan !== null && t.keshdan !== undefined) {
      qism.push("keshdan " + t.keshdan + "%");
    }
    // Kecha grantdan oshgan bo'lsa buni AYTAMIZ: oshgan qismi pulli.
    if (t.kecha_oshgan) qism.push("kecha oshgan");
    $("k-token-d").innerHTML = t.oshgan
      ? '<b class="down">grantdan oshdi</b> · ' + xavfsiz(qism.join(" · "))
      : xavfsiz(qism.join(" · "));
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
  var W = 640, PAD_L = 44, PAD_R = 12, TOP = 18, BASE = 158;

  /* Yuqori chegara — 4 ga bo'linadigan "chiroyli" son, eng kamida 4.
     Nolga bo'lish va tekis nol grafik shu yerda to'xtaydi. */
  function pogona(eng) {
    if (!eng) return 4;
    var p = Math.pow(10, Math.floor(Math.log10(eng)));
    var q = Math.ceil(eng / p * 4) / 4 * p;
    return Math.max(4, Math.ceil(q / 4) * 4);
  }

  function chizuvchi(prefiks, sarlavha, izoh) {
    var DAYS = [], MAX = 100;
    function el(nom) { return $(prefiks + nom); }

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
          dots += '<circle cx="' + x(i).toFixed(1) + '" cy="' + y(p.soni).toFixed(1) + '" r="' +
                  (i === DAYS.length - 1 ? 4.5 : 3) + '" fill="' +
                  (i === DAYS.length - 1 ? "#2BB3FF" : "var(--panel)") + '" stroke="#7B5CFF" stroke-width="2"/>';
        }
        if (i % kop === 0 || i === DAYS.length - 1) {
          // ⚠️ 7 kunlik oynada hafta kuni («Dush») ma'noli, 30 yoki 90
          // kunlikda esa u to'rt marta takrorlanadi va o'qni o'qib
          // bo'lmay qoladi — u yerda sana yoziladi.
          var yorliq = DAYS.length <= 7 ? p.nom
            : (p.kun || "").slice(8, 10) + "." + (p.kun || "").slice(5, 7);
          labels += '<text x="' + x(i).toFixed(1) + '" y="176" text-anchor="middle">' +
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
      function move(e) {
        if (!DAYS.length) return;
        var cx = e.touches ? e.touches[0].clientX : e.clientX;
        var i = nearest(cx), r = box.getBoundingClientRect();
        cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("opacity", ".55");
        tip.style.opacity = "1";
        tip.style.left = (x(i) / W * r.width) + "px";
        tip.style.top = (y(DAYS[i].soni) / 210 * r.height) + "px";
        tip.innerHTML = xavfsiz(kunNomi(DAYS[i].kun + "T12:00:00+05:00")) +
                        " · " + izoh(DAYS[i]);
      }
      function leave() { tip.style.opacity = "0"; cross.setAttribute("opacity", "0"); }
      hit.addEventListener("mousemove", move);
      hit.addEventListener("mouseleave", leave);
      hit.addEventListener("touchstart", move, { passive: true });
      hit.addEventListener("touchmove", move, { passive: true });
      hit.addEventListener("touchend", leave);
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
      : '<b class="' + (k.sorovlar.ozgarish >= 0 ? "up" : "down") + '">' +
        (k.sorovlar.ozgarish >= 0 ? "+" : "") + k.sorovlar.ozgarish + "%</b> oldingi 24 soatga nisbatan";

    $("k-faol").textContent = son(k.faol.qiymat);
    $("k-faol-d").innerHTML = son(k.faol.jami) + ' dan · <b class="up">+' +
                              son(k.faol.yangi) + "</b> bugun yangi";

    $("k-pro").textContent = son(k.pro.qiymat);
    // ⚠️ Muddatsiz Pro bu sanoqqa kirmaydi (`premium_until IS NULL`),
    // ya'ni «tugaydi» faqat haqiqatan tugaydiganlar haqida.
    $("k-pro-d").textContent = k.pro.tugaydi
      ? k.pro.tugaydi + " tasi 7 kunda tugaydi"
      : "7 kun ichida tugaydigani yo'q";

    $("k-pul").textContent = son(k.daromad.bugun) + " ⭐";
    $("k-pul-d").textContent = "30 kunda " + son(k.daromad.oy) + " ⭐";

    tokenChiz(k.token);

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
          return '<div class="row"><span class="tag ' + (x.tur === "timeout" ? "warn" : "ban") +
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
  function kuzatuvBanner(k) {
    var joy = document.querySelector('section[data-screen="dash"]');
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
      titroq("light");
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
          var nom = u.username ? "@" + u.username : "ID:" + u.user_id;
          return '<div class="row"><div class="person">' + avatar(nom, i === 0) +
            "<div><b>" + xavfsiz(nom) + "</b><span>" + xavfsiz(u.user_id) +
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
          return '<div class="row" data-uid="' + xavfsiz(u.user_id) + '">' +
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
    titroq("light");
    jurnalQayta(qaysi);
  }

  async function jurnalAudit() {
    var d = await ol("/api/journal/audit?page=" + jSahifa.audit +
                     (jAdmin ? "&admin=" + jAdmin : "") + jFiltrQator("audit"));
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
          '<span class="tag">' + xavfsiz(r.tafsilot) + "</span>"
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
        titroq("light");
        jurnalQayta("audit");
      });
    }
  }

  async function jurnalXatolar() {
    var d = await ol("/api/journal/errors?page=" + jSahifa.errors +
                     jFiltrQator("errors"));
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
      h += '<div class="row"><span class="tag ' + (r.tur === "timeout" ? "warn" : "ban") + '">' +
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

  function ekranYukla(nom) {
    var fn = { dash: boshqaruv, stats: statistika, users: jadvalYukla,
               journal: jurnal, promo: promoEkran, system: sozlamalar,
               broadcast: tarqatmalar }[nom];
    if (!kirdi || !fn || yuklangan[nom]) return;
    yuklangan[nom] = true;
    fn().catch(function (e) {
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
    // marta (§4). Endi username bo'lmasa nom «Foydalanuvchi»,
    // raqam esa faqat pastki satrda.
    return u.username ? "@" + u.username : S.user.nomsiz;
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
        titroq("light");
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
        titroq("light");
        jadvalQayta();
      });
    }
  }

  async function jadvalYukla() {
    var yol = "/api/users?page=" + uSahifa + "&filter=" + encodeURIComponent(uFiltr) +
              "&tartib=" + encodeURIComponent(uTartib) +
              (uQuery ? "&q=" + encodeURIComponent(uQuery) : "");
    var d = await ol(yol);
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
          return '<div class="row bosiladi" data-uid="' + u.user_id + '">' +
            '<div class="person">' +
            avatar(u.username ? "@" + u.username : "ID:" + u.user_id,
                   u.tarif === "pro" || u.tarif === "premium") +
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
    var nom = d.username ? "@" + d.username : S.user.nomsiz;

    var shaxs = d.username ? "@" + d.username : "ID:" + d.user_id;
    $("u-av").innerHTML = bosh(shaxs) === null ? ODAM_SVG : xavfsiz(bosh(shaxs));
    $("u-ism").textContent = nom;
    $("u-meta").textContent = "ID " + d.user_id +
      (d.last_seen ? " · " + S.user.oxirgi + " " + nisbiy(d.last_seen) : "");

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
    if (!await tasdiq(S.savol.refund)) return;
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
    delegat("s-token", "data-uid", function (uid) {
      kartochka(Number(uid)).then(function () { go("profil"); })
        .catch(function (e) { console.error("[panel] profil:", e); });
    });
    delegat("urows", "data-uid", function (uid) {
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
    $("m-matn").textContent = d.matn;
    $("m-textarea").value = d.matn;
    var h = d.holat, q = [];
    if (h.commit) q.push(["Oxirgi deploy", h.commit, ""]);
    q.push(["Ishlash muddati", h.ishlash, ""]);
    q.push(["Mavzu rejimi", h.mavzu ? "yoqiq" : "o'chiq", ""]);
    q.push(["Baza", h.baza ? "ulangan" : "ulanmagan", h.baza ? "up" : "down"]);
    q.push(["Model", h.model, ""]);
    $("m-holat").innerHTML = q.map(function (r) {
      return '<div class="kv"><span>' + xavfsiz(r[0]) + '</span><b class="' + r[2] + '">' +
             xavfsiz(r[1]) + "</b></div>";
    }).join("");
  }

  /* ══ KUZATISH ═══════════════════════════════════════════════════ */
  async function kuzatuv() {
    var d = await ol("/api/watch");
    // Guruh qo'yilmagan bo'lsa kuzatuv UMUMAN ishlamaydi.
    $("w-guruh").textContent = d.guruh === null ? "qo'yilmagan" : d.guruh;
    $("w-rows").innerHTML = d.rows.length
      ? d.rows.map(function (u) {
          var nom = u.username ? "@" + u.username : "ID:" + u.user_id;
          return '<div class="row"><div class="t"><b>' + xavfsiz(nom) +
            "</b><span>qo'shilgan " + xavfsiz(qisqa(u.added_at)) + "</span></div>" +
            (d.guruh === null ? '<span class="tag">guruh yo\'q</span>'
                              : '<span class="tag ok">Faol</span>') +
            '<button class="btn sm danger" data-wdel="' + u.user_id + '">O\'chirish</button></div>';
        }).join("")
      : boshHolat(S.bosh.kuzatuv);
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
    await Promise.all([limitlar(), tatil(), kuzatuv(), adminlar()]);
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
    await Promise.all([promokodlar(), sovga(), referal()]);
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
      if (!await tasdiq(S.savol.kuzatuvOl)) return;
      var j = await so_rov("/api/watch", { amal: "remove", kim: uid }, null, b);
      if (!j.ok) return natijaChiz("w-natija", j.xato, true);
      natijaChiz("w-natija", S.natija.kuzatuvOl);
      await kuzatuv();
    });

    $("ad-qosh").addEventListener("click", async function () {
      var kim = $("ad-kim").value.trim();
      if (!kim) return natijaChiz("ad-natija", "Sonli ID yozing.", true);
      if (!await tasdiq(S.savol.adminQosh)) return;
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
      if (!await tasdiq(S.savol.adminOl)) return;
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
      if (!await tasdiq(S.savol.sovga)) return;
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
  qism("chiqish", chiqish);
  kir();
})();
