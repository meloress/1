/* Web admin panel — brauzer tomoni.
 *
 * Tuzilishi: avval Telegram bilan ulanish, keyin darvoza (`/api/session`),
 * undan keyingina ekranlar chiziladi. Yettala ekran ham haqiqiy
 * ma'lumotda ishlaydi; qotirilgan namuna raqam qolmagan.
 *
 * ⚠️ Har bo'lak `qism()` ichida chaqiriladi: bitta vidjetdagi xato
 * (masalan 3-bosqichda o'chirilgan element) butun navigatsiyani
 * o'ldirmasligi kerak. Bitta IIFE ichida `getElementById(...).onclick`
 * null qaytarsa, undan KEYINGI hamma narsa ishga tushmay qolardi —
 * ekranlar almashmaydi, tab-panel jim bo'ladi va sababi ko'rinmaydi.
 */
(function () {
  "use strict";

  var tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;

  function qism(nom, fn) {
    try { fn(); } catch (e) { console.error("[panel] " + nom + ":", e); }
  }
  function $(id) { return document.getElementById(id); }

  /* ── Telegram bilan ulanish ───────────────────────────────────
     Panel ataylab to'liq bo'yalgan: `themeParams` dan rang OLINMAYDI,
     aksincha Telegram sarlavhasi va pastki chizig'i panelning o'z
     rangiga bo'yaladi — aks holda qora panel ustida oq sarlavha
     turib, ikki xil dastur ko'rinishini berardi.                 */
  var VOID = "#07060C", DEEP = "#0B0A14";

  function telegram() {
    if (!tg) return;
    tg.ready();
    tg.expand();                       // to'liq balandlik (REJA 2-bosqich)
    try { tg.setHeaderColor(DEEP); } catch (e) {}
    try { tg.setBackgroundColor(VOID); } catch (e) {}
    try { tg.setBottomBarColor(DEEP); } catch (e) {}
    // Pastga tortish oynani yopib yuboradi — jadvalni aylantirayotgan
    // odam buni tasodifan qiladi. Eski mijozlarda metod yo'q.
    if (typeof tg.disableVerticalSwipes === "function") tg.disableVerticalSwipes();
    olcham();
    tg.onEvent("viewportChanged", olcham);
  }

  function olcham() {
    // `viewportStableHeight` — klaviatura ochilganda o'zgarmaydigan
    // balandlik; 100vh Telegram ichida noto'g'ri qiymat beradi.
    var h = tg && tg.viewportStableHeight;
    if (h) document.documentElement.style.setProperty("--vh", h + "px");
  }

  function titroq(turi) {
    if (!tg || !tg.HapticFeedback) return;
    try { tg.HapticFeedback.impactOccurred(turi || "light"); } catch (e) {}
  }

  /* ── Darvoza ──────────────────────────────────────────────────
     Ketma-ketlik: yangi imzo → (eskirgan bo'lsa) cookie → xato.
     Panel FAQAT muvaffaqiyatdan keyin ko'rsatiladi, ya'ni admin
     bo'lmagan odam bironta raqam ham ko'rmaydi.                  */
  function korsat(kim) {
    ["yuklash", "xato", "shell"].forEach(function (id) {
      var el = $(id);
      if (el) el.hidden = id !== kim;
    });
    var tb = $("tabbar");
    if (tb) tb.hidden = kim !== "shell";
  }

  function xatoKorsat(sarlavha, matn) {
    var a = $("xato-sarlavha"), b = $("xato-matn");
    if (a && sarlavha) a.textContent = sarlavha;
    if (b && matn) b.textContent = matn;
    korsat("xato");
  }

  function bosh(ism) {
    // Ism o'rnidagi harflar — avatar. Emoji va tinish belgilari tashlanadi.
    var s = String(ism || "").replace(/^@/, "");
    var w = s.replace(/[^A-Za-zЀ-ӿ' ]/g, " ").trim().split(/\s+/);
    var t = ((w[0] || "?")[0] || "?") + ((w[1] || "")[0] || "");
    return t.toUpperCase();
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
      return xatoKorsat("Ulanmadi", "Server javob bermadi. Internetni tekshirib, qayta urinib ko'ring.");
    }

    if (!r.ok) {
      // Imzo eskirgan bo'lishi mumkin (panel uzoq ochiq turib qayta
      // yuklangan) — 12 soatlik cookie aynan shuning uchun bor.
      var c = null;
      try { c = await fetch("/api/me"); } catch (e) {}
      if (c && c.ok) return ichkariga(await c.json());

      if (r.status === 403)
        return xatoKorsat("Ruxsat yo'q", "Bu panel faqat adminlar uchun. Agar bu xato deb hisoblasangiz, superadminga murojaat qiling.");
      if (r.status === 429)
        return xatoKorsat("Juda ko'p urinish", "Bir daqiqadan so'ng qayta urinib ko'ring.");
      return xatoKorsat("Kirish rad etildi", "Panelni Telegram ichidagi «Panel» tugmasi orqali oching.");
    }
    ichkariga(await r.json());
  }

  function ichkariga(ma) {
    var ism = (ma && ma.ism) || "Admin";
    var n = $("who-ism"), a = $("who-av"), r = $("who-rol");
    if (n) n.textContent = ism;
    if (a) a.textContent = bosh(ism);
    if (r && ma && ma.rol) r.textContent = ma.rol;
    korsat("shell");
    olcham();
    // ⚠️ Ma'lumot FAQAT shu yerdan boshlab so'raladi. `navigatsiya()`
    // kirishdan OLDIN ishga tushadi va `go()` ichida `ekranYukla()`
    // bor — `kirdi` bayrog'isiz panel hali yopiq turib
    // `/api/overview` ga so'rov yuborardi va 401 olib, ekranga
    // «ma'lumot yuklanmadi» yozib qo'yardi.
    kirdi = true;
    ekranYukla(hozir);
  }

  /* ── Ekranlar ─────────────────────────────────────────────── */
  var TITLES = {
    dash: ["Boshqaruv", null],
    // ⚠️ Bu yerda maketdagi «1 204 ta yozuv» qotirilgan edi va
    // haqiqiy son bilan mos kelmasdi. Endi jadval yuklanganda
    // `jadvalYukla()` yangilaydi.
    users: ["Foydalanuvchilar", "yuklanmoqda…"],
    stats: ["Statistika", "oxirgi 7 kun"],
    promo: ["Promo va sovg'a", "kodlar, bepul Pro, referal"],
    journal: ["Jurnal", "audit, xatolar, daromad"],
    system: ["Sozlamalar", "limitlar, ta'til, kuzatish, adminlar"],
    broadcast: ["Tarqatma", "Telegramda boshqariladi"]
  };
  var BOSH_EKRAN = "dash";
  var hozir = BOSH_EKRAN;

  var OYLAR = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul",
               "avgust", "sentabr", "oktabr", "noyabr", "dekabr"];

  function bugun() {
    // Server Toshkent vaqtida ishlaydi, panel esa istalgan mintaqada
    // ochilishi mumkin — shuning uchun vaqt ATAYLAB Asia/Tashkent'ga
    // o'giriladi. Oy nomlari qo'lda: `uz-UZ` hamma mijozda yo'q.
    try {
      var p = {};
      new Intl.DateTimeFormat("en-GB", {
        timeZone: "Asia/Tashkent", day: "numeric", month: "numeric",
        hour: "2-digit", minute: "2-digit", hour12: false
      }).formatToParts(new Date()).forEach(function (x) { p[x.type] = x.value; });
      return "bugun · " + p.day + "-" + OYLAR[+p.month - 1] + ", " +
             p.hour + ":" + p.minute + " (UTC+5)";
    } catch (e) {
      return "bugun";
    }
  }

  function go(name, pane) {
    document.querySelectorAll("section[data-screen]").forEach(function (s) {
      s.classList.toggle("on", s.dataset.screen === name);
    });
    document.querySelectorAll("#nav button, #tabbar button").forEach(function (b) {
      if (b.dataset.go) b.setAttribute("aria-current", b.dataset.go === name ? "true" : "false");
    });
    var t = TITLES[name] || ["", ""];
    var ttl = $("title"), crumb = $("crumb");
    if (ttl) ttl.textContent = t[0];
    if (crumb) crumb.textContent = t[1] === null ? bugun() : t[1];
    if (pane) showPane(name, pane);
    hozir = name;
    orqaTugma();
    ekranYukla(name);
    window.scrollTo({ top: 0, behavior: "instant" });
  }

  /* Telegram'ning o'z «orqaga» tugmasi. Bosh ekranda kerak emas —
     u yerda tugma yopish ma'nosini beradi va chalg'itadi. */
  function orqaTugma() {
    if (!tg || !tg.BackButton) return;
    try {
      if (hozir === BOSH_EKRAN) tg.BackButton.hide();
      else tg.BackButton.show();
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
      tg.BackButton.onClick(function () { titroq("light"); go(BOSH_EKRAN); });
    }
    go(BOSH_EKRAN);
  }

  /* ── Server bilan gaplashish ──────────────────────────────── */
  function son(n) {
    return Number(n || 0).toLocaleString("ru-RU").replace(/,/g, " ");
  }
  function foiz(v, kasr) {
    // `null` = ma'lumot yo'q (bo'luvchi nol edi). «0%» bilan aralashib
    // ketmasligi kerak — server ataylab shu farqni yuboradi.
    return v === null || v === undefined ? "—" : v.toFixed(kasr || 0) + "%";
  }
  function xavfsiz(s) {
    // Xato matni va username bazadan keladi, ya'ni ular BEGONA matn.
    // `innerHTML` ga to'g'ridan-to'g'ri qo'yilsa panelga skript
    // kiritilishi mumkin edi.
    return String(s === null || s === undefined ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function ol(yol) {
    var r = await fetch(yol);
    if (!r.ok) throw new Error(yol + " → " + r.status);
    return r.json();
  }

  function ustunlarChiz(joy, royxat) {
    var el = $(joy);
    if (!el) return;
    if (!royxat.length) {
      el.innerHTML = '<p class="hint">Bu davrda amal qayd etilmagan.</p>';
      return;
    }
    var eng = Math.max.apply(null, royxat.map(function (t) { return t.soni; })) || 1;
    el.innerHTML = royxat.map(function (t, i) {
      return '<div class="bar"><span>' + xavfsiz(t.nom) + "</span>" +
             '<div class="track"><div class="fill' + (i === 0 ? " top" : "") + '" style="width:' +
             Math.max(3, t.soni / eng * 100).toFixed(1) + '%"></div></div>' +
             '<b class="n num">' + son(t.soni) + "</b></div>";
    }).join("");
  }

  function tarifChiz(ratioId, legendId, t) {
    var jami = t.jami || 1;
    var qismlar = [
      { nom: "Pro", soni: t.pro, rang: "linear-gradient(90deg,#C724FF,#7B5CFF)", nuqta: "#9A44FF" },
      { nom: "Premium", soni: t.premium, rang: "#2BB3FF", nuqta: "#2BB3FF" },
      { nom: "Bepul", soni: t.free, rang: "#2E2A44", nuqta: "#2E2A44" }
    ];
    var ratio = $(ratioId), legend = $(legendId);
    if (ratio) ratio.innerHTML = qismlar.map(function (q) {
      // Nol kenglikdagi bo'lak chizilmaydi — aks holda 2px lik
      // oraliqlar qatorni chipor qilib yuboradi.
      return q.soni ? '<i style="width:' + (q.soni / jami * 100).toFixed(2) +
                      '%;background:' + q.rang + '"></i>' : "";
    }).join("");
    if (legend) legend.innerHTML = qismlar.map(function (q) {
      return '<span><i style="background:' + q.nuqta + '"></i>' +
             q.nom + " " + son(q.soni) + "</span>";
    }).join("");
  }

  /* ── Chiziqli grafik: 7 kunlik so'rovlar ──────────────────── */
  var DAYS = [];
  var W = 640, PAD_L = 42, PAD_R = 12, MAX = 100;
  function x(i) {
    var n = DAYS.length > 1 ? DAYS.length - 1 : 1;
    return PAD_L + i * (W - PAD_L - PAD_R) / n;
  }
  function y(v) { return 20 + (1 - v / MAX) * 135; }

  function grafik(kunlar) {
    DAYS = kunlar;
    // ⚠️ Shkala ma'lumotga qarab tanlanadi. Maketda 400 qotirilgan edi
    // — kuniga 12 ta so'rovi bor bot grafigi tekis chiziqqa aylanardi
    // va hech qanday o'zgarish ko'rinmasdi.
    var eng = Math.max.apply(null, DAYS.map(function (p) { return p.soni; }));
    MAX = pogona(eng);

    var line = "", dots = "", labels = "", ylab = "";
    DAYS.forEach(function (p, i) {
      line += (i ? " L" : "M") + x(i).toFixed(1) + " " + y(p.soni).toFixed(1);
      dots += '<circle cx="' + x(i).toFixed(1) + '" cy="' + y(p.soni).toFixed(1) + '" r="' +
              (i === DAYS.length - 1 ? 4.5 : 3) + '" fill="' +
              (i === DAYS.length - 1 ? "#2BB3FF" : "#0B0A14") + '" stroke="#7B5CFF" stroke-width="2"/>';
      labels += '<text x="' + x(i).toFixed(1) + '" y="172" text-anchor="middle">' + xavfsiz(p.nom) + "</text>";
    });
    [1, 0.75, 0.5, 0.25].forEach(function (ulush, n) {
      ylab += '<text x="0" y="' + (14 + n * 45) + '">' + Math.round(MAX * ulush) + "</text>";
    });
    var area = line + " L" + x(DAYS.length - 1).toFixed(1) + " 158 L" + x(0).toFixed(1) + " 158 Z";
    $("line").setAttribute("d", line);
    $("area").setAttribute("d", area);
    $("dots").innerHTML = dots;
    $("xlab").innerHTML = labels;
    $("ylab").innerHTML = ylab;
    $("chart-svg").setAttribute("aria-label",
      "Oxirgi 7 kundagi so'rovlar: " + DAYS.map(function (p) { return p.nom + " " + p.soni; }).join(", "));
  }

  /* Yuqori chegara — 4 ga bo'linadigan "chiroyli" son, eng kamida 4.
     Nolga bo'lish va tekis nol grafik shu yerda to'xtaydi. */
  function pogona(eng) {
    if (!eng) return 4;
    var p = Math.pow(10, Math.floor(Math.log10(eng)));
    var q = Math.ceil(eng / p * 4) / 4 * p;
    return Math.max(4, Math.ceil(q / 4) * 4);
  }

  function grafikHodisalari() {
    var hit = $("hit"), tip = $("tip"), cross = $("cross"), box = $("chart");
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
      tip.innerHTML = xavfsiz(DAYS[i].nom) + " · <b>" + DAYS[i].soni + "</b> so'rov · " +
                      DAYS[i].kishi + " kishi";
    }
    function leave() { tip.style.opacity = "0"; cross.setAttribute("opacity", "0"); }
    hit.addEventListener("mousemove", move);
    hit.addEventListener("mouseleave", leave);
    hit.addEventListener("touchmove", move, { passive: true });
    hit.addEventListener("touchend", leave);
  }

  /* ── Boshqaruv ekrani ─────────────────────────────────────── */
  async function boshqaruv() {
    var d = await ol("/api/overview");
    var k = d.kpi;

    $("k-sorov").textContent = son(k.sorovlar.qiymat);
    $("k-sorov-d").innerHTML = k.sorovlar.ozgarish === null
      ? "kecha taqqoslash uchun ma'lumot yo'q"
      : '<b class="' + (k.sorovlar.ozgarish >= 0 ? "up" : "down") + '">' +
        (k.sorovlar.ozgarish >= 0 ? "+" : "") + k.sorovlar.ozgarish + "%</b> kechagiga nisbatan";

    $("k-faol").textContent = son(k.faol.qiymat);
    $("k-faol-d").innerHTML = son(k.faol.jami) + ' dan · <b class="up">+' +
                              son(k.faol.yangi) + "</b> yangi";

    $("k-pro").textContent = son(k.pro.qiymat);
    $("k-pro-d").textContent = k.pro.tugaydi
      ? k.pro.tugaydi + " tasi 7 kunda tugaydi"
      : "7 kun ichida tugaydigani yo'q";

    $("k-pul").textContent = son(k.daromad.bugun) + " ⭐";
    $("k-pul-d").textContent = "30 kunda " + son(k.daromad.oy) + " ⭐";

    grafik(d.kunlar);
    ustunlarChiz("typebars", d.turlar);
    tarifChiz("t-ratio", "t-legend", d.tarif);
    $("t-jami").textContent = son(d.tarif.jami);
    $("t-yangi").textContent = son(k.faol.yangi);
    $("t-tatil").textContent = d.tatil ? "YOQILGAN" : "o'chiq";

    $("xato-soni").innerHTML = "<i></i>bugun " + son(d.xato_soni) + " ta";
    // Yon menyudagi sonlar — maketda qotirilgan edi ("1 204", "4").
    $("n-users").textContent = son(d.tarif.jami);
    $("n-xato").textContent = son(d.xato_soni);
    $("xatolar").innerHTML = d.xatolar.length
      ? d.xatolar.map(function (x) {
          return '<div class="row"><span class="tag ' + (x.tur === "timeout" ? "warn" : "ban") +
                 '">' + xavfsiz(x.tur) + '</span><div class="t"><b>' + xavfsiz(x.matn) +
                 "</b><span>" + (x.user ? "user " + xavfsiz(x.user) + " · " : "") +
                 xavfsiz(x.vaqt) + "</span></div></div>";
        }).join("")
      : '<p class="hint">Bugun xato qayd etilmagan.</p>';

    // Texnik ta'til yoqilgan bo'lsa «Bot ishlayapti» yolg'on bo'lardi.
    var h = $("holat");
    h.className = d.tatil ? "pill" : "pill live";
    h.innerHTML = "<i></i>" + (d.tatil ? "Texnik ta'til" : "Bot ishlayapti");
  }

  /* ── Statistika ekrani ────────────────────────────────────── */
  async function statistika() {
    var d = await ol("/api/stats");
    $("s-jami").textContent = son(d.kpi.jami);
    $("s-jami-d").innerHTML = '<b class="up">+' + son(d.kpi.yangi) + "</b> so'nggi 24 soatda";
    $("s-ortacha").textContent = son(d.kpi.kunlik_ortacha);
    $("s-guest").textContent = foiz(d.kpi.guest_ulush);
    $("s-konv").textContent = foiz(d.kpi.konversiya, 2);

    $("s-top").innerHTML = d.top.length
      ? d.top.map(function (u, i) {
          var nom = u.username ? "@" + u.username : "ID:" + u.user_id;
          return '<tr><td class="num">' + (i + 1) + '</td><td><div class="person"><div class="av">' +
            bosh(nom) + "</div><div><b>" + xavfsiz(nom) + "</b><span>" + xavfsiz(u.user_id) +
            '</span></div></div></td><td class="num">' + son(u.soni) +
            '</td><td><div class="bar" style="grid-template-columns:1fr"><div class="track"><div class="fill' +
            (i === 0 ? " top" : "") + '" style="width:' + u.ulush + '%"></div></div></div></td></tr>';
        }).join("")
      : '<tr><td colspan="4" style="padding:26px 18px;color:var(--ink-3)">' +
        "So'nggi 7 kunda faollik qayd etilmagan.</td></tr>";

    tarifChiz("s-ratio", "s-legend", d.tarif);
    $("s-ulushlar").innerHTML = d.ulushlar.map(function (u) {
      return '<div class="row"><div class="t"><b>' + xavfsiz(u.nom) + "</b><span>" +
             xavfsiz(u.izoh) + '</span></div><b class="num">' +
             foiz(u.foiz, u.foiz !== null && u.foiz % 1 ? 1 : 0) + "</b></div>";
    }).join("");
    ustunlarChiz("s-turlar", d.turlar);
  }

  /* ── Jurnal (4 ta sub-tab) ────────────────────────────────── */
  var jSahifa = { audit: 0, errors: 0 }, jSahifalar = { audit: 1, errors: 1 };
  var jAdmin = null;   // audit filtri: bitta admin yoki hammasi

  async function jurnalAudit() {
    var d = await ol("/api/journal/audit?page=" + jSahifa.audit +
                     (jAdmin ? "&admin=" + jAdmin : ""));
    jSahifalar.audit = d.sahifalar;
    $("j-audit-soni").textContent = "jami " + son(d.jami) + " ta";
    $("j-audit").innerHTML = d.rows.length
      ? d.rows.map(function (r) {
          return '<tr><td class="num">' + xavfsiz(r.vaqt || "—") + "</td>" +
            "<td>" + xavfsiz(r.admin) + "</td>" +
            "<td>" + xavfsiz(r.amal) +
            (r.tafsilot ? ' <span class="code">' + xavfsiz(r.tafsilot) + "</span>" : "") +
            '</td><td class="uid">' + xavfsiz(r.kimga || "—") + "</td></tr>";
        }).join("")
      : '<tr><td colspan="4" style="padding:26px 18px;color:var(--ink-3)">Yozuv yo\'q.</td></tr>';
    $("j-audit-holat").textContent = "sahifa " + (jSahifa.audit + 1) + "/" + d.sahifalar;

    // Filtr chiplari — jurnalda uchragan adminlardan yig'iladi.
    var chips = $("j-adminlar");
    if (!chips.dataset.tayyor && d.adminlar.length) {
      chips.dataset.tayyor = "1";
      chips.innerHTML = '<button class="chip" aria-pressed="true" data-admin="">Hammasi</button>' +
        d.adminlar.map(function (a) {
          return '<button class="chip" aria-pressed="false" data-admin="' + a + '">ID:' + a + "</button>";
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
    var d = await ol("/api/journal/errors?page=" + jSahifa.errors);
    jSahifalar.errors = d.sahifalar;
    var x = d.xulosa;
    $("j-xato-soni").innerHTML = "<i></i>bugun " + son(x.kun) + " · hafta " + son(x.hafta);
    ustunlarChiz("j-xato-turlar", x.turlar);
    $("j-xatolar").innerHTML = d.rows.length
      ? d.rows.map(function (r) {
          return '<tr><td class="num">' + xavfsiz(r.vaqt || "—") + "</td>" +
            '<td><span class="tag ' + (r.tur === "timeout" ? "warn" : "ban") + '">' +
            xavfsiz(r.tur) + "</span></td>" +
            "<td>" + xavfsiz(r.matn) + "</td>" +
            '<td class="uid">' + xavfsiz(r.user || "—") + "</td></tr>";
        }).join("")
      : '<tr><td colspan="4" style="padding:26px 18px;color:var(--ink-3)">Xato qayd etilmagan.</td></tr>';
    $("j-xato-holat").textContent = "jami " + son(x.jami) +
      " · sahifa " + (jSahifa.errors + 1) + "/" + d.sahifalar;
  }

  async function jurnalDaromad() {
    var d = await ol("/api/journal/revenue");
    $("j-oy").textContent = son(d.oy) + " ⭐";
    $("j-oy-d").textContent = son(d.sotuv_30d) + " ta sotuv · " +
                              son(d.qaytarilgan) + " ta qaytarilgan";
    $("j-bugun").textContent = son(d.bugun) + " ⭐";
    // Sotuv bo'lmasa o'rtacha chek YO'Q — «0 ⭐» yolg'on bo'lardi.
    $("j-ortacha").textContent = d.ortacha === null ? "—" : son(d.ortacha) + " ⭐";
    $("j-jami").textContent = son(d.jami) + " ⭐";
    ustunlarChiz("j-tariflar", d.tariflar.map(function (t) {
      return { nom: t.nom, soni: t.soni };
    }));
  }

  async function jurnalNofaol() {
    var d = await ol("/api/journal/inactive");
    $("j-nofaol-soni").textContent = "jami " + son(d.jami) + " ta";
    $("j-nofaol").innerHTML = d.rows.length
      ? d.rows.map(function (u) {
          return "<tr><td>" + xavfsiz(u.username ? "@" + u.username : "—") + "</td>" +
            '<td class="uid">' + xavfsiz(u.user_id) + "</td>" +
            '<td class="num">' + xavfsiz(u.last_seen || "—") + "</td>" +
            "<td>" + (u.tarif === "free" ? PLAN.free : PLAN.pro) + "</td></tr>";
        }).join("")
      : '<tr><td colspan="4" style="padding:26px 18px;color:var(--ink-3)">Bunday foydalanuvchi yo\'q.</td></tr>';
  }

  function jurnalQayta(qaysi) {
    var fn = { audit: jurnalAudit, errors: jurnalXatolar }[qaysi];
    if (fn) fn().catch(function (e) { console.error("[panel] jurnal " + qaysi + ":", e); });
  }

  async function jurnal() {
    // To'rttasi ham birdan yuklanadi: sub-tab almashishi bir zumda
    // bo'lishi kerak, so'rovlar esa yengil.
    await Promise.all([jurnalAudit(), jurnalXatolar(), jurnalDaromad(), jurnalNofaol()]);
  }

  function jurnalNav() {
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

  /* Ekran ma'lumoti bir marta yuklanadi; qayta ochilganda eskisi
     qoladi. Yangilash — «Qayta yuklash» tugmasi yoki panelni qayta
     ochish. Har o'tishda so'rov yuborish bitta odam uchun ortiqcha. */
  var yuklangan = {};
  var kirdi = false;   // kirishdan oldin bironta so'rov yuborilmaydi
  function ekranYukla(nom) {
    var fn = { dash: boshqaruv, stats: statistika, users: jadvalYukla,
               journal: jurnal, promo: promoEkran, system: sozlamalar,
               broadcast: tarqatmalar }[nom];
    if (!kirdi || !fn || yuklangan[nom]) return;
    yuklangan[nom] = true;
    fn().catch(function (e) {
      yuklangan[nom] = false;   // xatodan keyin qayta urinish mumkin
      console.error("[panel] " + nom + " yuklanmadi:", e);
      xatoQatori(nom);
    });
  }

  function xatoQatori(nom) {
    var joy = document.querySelector('section[data-screen="' + nom + '"] .card');
    if (joy && !joy.querySelector(".yuklanmadi")) {
      var p = document.createElement("p");
      p.className = "hint yuklanmadi";
      p.textContent = "Ma'lumot yuklanmadi. Panelni qayta oching.";
      joy.appendChild(p);
    }
  }

  /* ── Foydalanuvchilar ─────────────────────────────────────── */
  var PLAN = {
    pro: '<span class="tag pro">Pro</span>',
    free: '<span class="tag">Bepul</span>',
    ban: '<span class="tag ban">Bloklangan</span>'
  };
  var uFiltr = "all", uQuery = "", uSahifa = 0, uSahifalar = 1, uOchiq = null;

  function nomi(u) {
    return u.username ? "@" + u.username : "ID:" + u.user_id;
  }

  async function jadvalYukla() {
    var yol = "/api/users?page=" + uSahifa + "&filter=" + encodeURIComponent(uFiltr) +
              (uQuery ? "&q=" + encodeURIComponent(uQuery) : "");
    var d = await ol(yol);
    uSahifalar = d.sahifalar;

    ["all", "pro", "free", "ban"].forEach(function (k) {
      var el = $("c-" + k);
      if (el) el.textContent = son(d.sanoq[k]);
    });

    var body = $("urows");
    body.innerHTML = d.rows.length
      ? d.rows.map(function (u) {
          return '<tr class="clickable" data-uid="' + u.user_id + '"><td><div class="person"><div class="av' +
            (u.tarif === "pro" ? " pro" : "") + '">' + bosh(nomi(u)) +
            "</div><div><b>" + xavfsiz(nomi(u)) + "</b><span>" + xavfsiz(u.user_id) + "</span></div></div></td>" +
            "<td>" + PLAN[u.tarif] + "</td>" +
            '<td class="num">' + xavfsiz(u.created_at || "—") + "</td>" +
            '<td style="color:var(--ink-2)">' + xavfsiz(u.last_seen || "—") + "</td>" +
            '<td><button class="btn sm">Ochish</button></td></tr>';
        }).join("")
      : '<tr><td colspan="5" style="padding:26px 18px;color:var(--ink-3)">' +
        (uQuery ? "Bunday foydalanuvchi topilmadi. Boshqa ID yoki @username bilan qidiring."
                : "Bu toifada foydalanuvchi yo'q.") + "</td></tr>";

    body.querySelectorAll("tr[data-uid]").forEach(function (tr) {
      tr.addEventListener("click", function () {
        titroq("light");
        kartochka(Number(tr.dataset.uid));
      });
    });

    $("u-holat").textContent = d.jami
      ? "Jami " + son(d.jami) + " ta · sahifa " + (uSahifa + 1) + "/" + uSahifalar
      : "Natija yo'q";
    TITLES.users[1] = son(d.sanoq.all) + " ta · " + son(d.sanoq.pro) + " tasi Pro";
    if (hozir === "users") $("crumb").textContent = TITLES.users[1];
    $("u-orqaga").disabled = uSahifa <= 0;
    $("u-oldinga").disabled = uSahifa >= uSahifalar - 1;
  }

  function jadvalQayta() {
    jadvalYukla().catch(function (e) {
      console.error("[panel] jadval:", e);
      $("u-holat").textContent = "Ro'yxat yuklanmadi.";
    });
  }

  /* ── Bitta foydalanuvchi kartochkasi ──────────────────────── */
  async function kartochka(uid) {
    var d = await ol("/api/users/" + uid);
    uOchiq = d;
    var nom = d.username ? "@" + d.username : "ID:" + d.user_id;

    $("u-av").textContent = bosh(nom);
    $("u-ism").textContent = nom;
    $("u-meta").textContent = "ID: " + d.user_id +
      (d.last_seen ? " · oxirgi faollik " + d.last_seen : "");

    var tag = $("u-tag");
    if (d.bloklangan) {
      tag.className = "tag ban"; tag.textContent = "Bloklangan";
    } else if (d.tarif === "pro") {
      tag.className = "tag pro";
      tag.textContent = "Pro" + (d.premium_until ? " · " + d.premium_until + " gacha" : " · cheksiz");
    } else {
      tag.className = "tag"; tag.textContent = "Bepul";
    }

    // `limit === null` — cheksiz, `0` — bu tarifda imkoniyat yo'q.
    // Ikkalasini «0 / 0» qilib ko'rsatish yolg'on bo'lardi.
    function chegara(v) { return v === null ? "∞" : v; }
    var facts = [
      { k: "Ballar", v: son(d.ballar.ishlatilgan) + " / " + chegara(d.ballar.limit) }
    ];
    d.sanoqlar.forEach(function (s) {
      facts.push({ k: s.nom, v: son(s.ishlatilgan) + " / " + chegara(s.limit) });
    });
    facts.push({ k: "Ro'yxatdan", v: (d.created_at || "—").split(" ")[0] });
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
          return '<div class="row"><div class="t"><b>' + son(t.days) + " kun</b><span>" +
            xavfsiz(t.sana || "—") + " · <span class=\"uid\">#" + xavfsiz(t.id) +
            '</span></span></div><b class="num">' + son(t.stars) + " ⭐</b>" + oxiri + "</div>";
        }).join("")
      : '<p class="hint">To\'lov yo\'q.</p>';
    $("u-tolovlar").querySelectorAll("[data-refund]").forEach(function (b) {
      b.addEventListener("click", function () { qaytarish(Number(b.dataset.refund)); });
    });

    $("a-ban").textContent = d.bloklangan ? "Blokni ochish" : "Bloklash";
    $("a-kunlar").hidden = true;
    $("a-xabar").hidden = true;
    natija("");
    $("ucard").hidden = false;
    $("ucard").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function natija(matn, yomonmi) {
    var el = $("a-natija");
    el.innerHTML = matn ? xavfsiz(matn) : "&nbsp;";
    el.style.color = yomonmi ? "var(--bad)" : "var(--ok)";
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

  async function amal(yol, tana, muvaffaqiyat) {
    var r = await fetch(yol, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(tana || {})
    });
    var d = {};
    try { d = await r.json(); } catch (e) {}
    if (!r.ok) {
      titroq("heavy");
      natija(d.error || ("Bajarilmadi (" + r.status + ")"), true);
      return false;
    }
    titroq("medium");
    natija(muvaffaqiyat + (d.xabar_yetdi === false
      ? " — lekin xabar yetmadi (botni bloklagan bo'lishi mumkin)" : ""));
    return true;
  }

  async function qayta() {
    // Amaldan keyin kartochka ham, ro'yxat ham yangilanadi: tarif
    // o'zgargan bo'lsa jadvaldagi yorliq eskiligicha qolib ketardi.
    var matn = $("a-natija").innerHTML;
    if (uOchiq) await kartochka(uOchiq.user_id);
    $("a-natija").innerHTML = matn;
    jadvalQayta();
  }

  async function qaytarish(payment_id) {
    if (!await tasdiq("To'lov qaytarilsinmi? Pul Telegram orqali qaytariladi va tarif olib tashlanadi.")) return;
    if (await amal("/api/payments/" + payment_id + "/refund", null, "Pul qaytarildi.")) await qayta();
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
      if (await amal("/api/users/" + uOchiq.user_id + "/premium", { kun: kun },
                     "Pro berildi.")) await qayta();
    });

    $("a-free").addEventListener("click", async function () {
      if (!uOchiq) return;
      if (!await tasdiq("Tarif bepulga tushirilsinmi?")) return;
      if (await amal("/api/users/" + uOchiq.user_id + "/plan", { tarif: "free" },
                     "Bepul tarifga o'tkazildi.")) await qayta();
    });

    $("a-quota").addEventListener("click", async function () {
      if (!uOchiq) return;
      if (await amal("/api/users/" + uOchiq.user_id + "/quota", null,
                     "Kunlik sanoqlar tiklandi.")) await qayta();
    });

    $("a-ban").addEventListener("click", async function () {
      if (!uOchiq) return;
      var bloklansinmi = !uOchiq.bloklangan;
      if (bloklansinmi && !await tasdiq("Foydalanuvchi bloklansinmi?")) return;
      if (await amal("/api/users/" + uOchiq.user_id + "/ban", { ban: bloklansinmi },
                     bloklansinmi ? "Bloklandi." : "Blok olib tashlandi.")) await qayta();
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
      if (await amal("/api/users/" + uOchiq.user_id + "/message", { matn: matn },
                     "Xabar yuborildi.")) {
        $("a-matn").value = "";
        $("a-xabar").hidden = true;
      }
    });

    $("u-yop").addEventListener("click", function () {
      $("ucard").hidden = true;
      uOchiq = null;
    });
  }

  function jadval() {
    document.querySelectorAll("[data-filter]").forEach(function (c) {
      c.addEventListener("click", function () {
        uFiltr = c.dataset.filter;
        uSahifa = 0;
        document.querySelectorAll("[data-filter]").forEach(function (o) {
          o.setAttribute("aria-pressed", o === c ? "true" : "false");
        });
        titroq("light");
        jadvalQayta();
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

  /* ── Chiplar ──────────────────────────────────────────────── */
  function chiplar() {
    document.querySelectorAll(".chips .chip:not([data-filter])").forEach(function (c) {
      c.addEventListener("click", function () {
        c.parentNode.querySelectorAll(".chip").forEach(function (o) {
          o.setAttribute("aria-pressed", o === c ? "true" : "false");
        });
        titroq("light");
      });
    });
  }

  /* ══ SOZLAMALAR, PROMO VA TARQATMA (6-bosqich) ═══════════════════

     ⚠️ Bu ekranlar YOZADI, qolganlari faqat o'qiydi. Shuning uchun
     uchta qoida hamma joyda bir xil:
       1. Orqaga qaytmaydigan amal `tasdiq()` dan o'tadi;
       2. Natija SHU kartochkada ko'rinadi (`.natija`), umumiy joyda
          emas — admin qaysi amal bajarilganini ko'rib turishi kerak;
       3. Serverdan qaytgan qiymat ishonchli manba: panel o'zi hisoblab
          qo'ymaydi, javobdagi raqamni ko'rsatadi.                   */

  function natijaChiz(id, matn, yomonmi) {
    var el = $(id);
    if (!el) return;
    el.innerHTML = matn ? xavfsiz(matn) : "&nbsp;";
    el.className = "natija" + (yomonmi ? " yomon" : "");
  }

  /* Yozuv so'rovi. `amal()` dan farqi: natijani O'ZI chizmaydi —
     har ekranning o'z `.natija` qatori bor. */
  async function so_rov(yol, tana, usul) {
    var cfg = { method: usul || "POST", headers: { "Content-Type": "application/json" } };
    if (cfg.method !== "DELETE") cfg.body = JSON.stringify(tana || {});
    var r = await fetch(yol, cfg);
    var d = {};
    try { d = await r.json(); } catch (e) {}
    titroq(r.ok ? "medium" : "heavy");
    return { ok: r.ok, d: d, xato: d.error || ("Bajarilmadi (" + r.status + ")") };
  }

  /* ── Limitlar ─────────────────────────────────────────────── */
  var LIMITLAR = null;

  function limitQiymat(tarif, kalit) {
    var el = document.querySelector('[data-lim="' + tarif + ":" + kalit + '"]');
    return el ? el.value.trim() : "";
  }

  async function limitlar() {
    var d = await ol("/api/limits");
    LIMITLAR = d;
    $("l-rows").innerHTML = d.rows.map(function (r) {
      return "<tr><td>" + xavfsiz(r.nom) + "</td>" +
        d.tariflar.map(function (t) {
          var v = r.tariflar[t];
          return '<td class="num"><input class="kiritish tor" type="number" min="0" ' +
            'max="100000" data-lim="' + t + ":" + r.kalit + '" value="' +
            (v.qiymat === null ? "" : xavfsiz(v.qiymat)) + '">' +
            (v.ozgargan ? ' <span title="o\'zgartirilgan">⭐</span>' : "") + "</td>";
        }).join("") +
        '<td><button class="btn sm" data-lsave="' + r.kalit + '">Saqlash</button> ' +
        '<button class="btn sm" data-lreset="' + r.kalit + '" ' +
        'title="asl qiymatga qaytarish" aria-label="Asl qiymatga qaytarish">↺</button></td></tr>';
    }).join("");
  }

  async function limitSaqla(kalit) {
    var qator = null;
    LIMITLAR.rows.forEach(function (r) { if (r.kalit === kalit) qator = r; });
    if (!qator) return;
    var yuborildi = 0;
    for (var i = 0; i < LIMITLAR.tariflar.length; i++) {
      var tarif = LIMITLAR.tariflar[i];
      var xom = limitQiymat(tarif, kalit);
      if (xom === "") continue;                       // bo'sh — tegilmaydi
      var son = Number(xom);
      // O'zgarmagan qiymatni qayta yubormaymiz: har yozuv auditga
      // tushadi va jurnal ma'nosiz qatorlar bilan to'lib ketardi.
      if (son === qator.tariflar[tarif].qiymat) continue;
      var j = await so_rov("/api/limits", { tarif: tarif, kalit: kalit, qiymat: son });
      if (!j.ok) return natijaChiz("l-natija", j.xato, true);
      yuborildi++;
    }
    if (!yuborildi) return natijaChiz("l-natija", "O'zgarish yo'q.");
    natijaChiz("l-natija", qator.nom + " yangilandi — bot darhol shu qiymat bilan ishlaydi.");
    await limitlar();
  }

  async function limitTikla(kalit) {
    if (!await tasdiq("Asl qiymatga qaytarilsinmi? Ikkala tarif ham config'dagi songa qaytadi.")) return;
    for (var i = 0; i < LIMITLAR.tariflar.length; i++) {
      var j = await so_rov("/api/limits",
        { tarif: LIMITLAR.tariflar[i], kalit: kalit, qiymat: null });
      if (!j.ok) return natijaChiz("l-natija", j.xato, true);
    }
    natijaChiz("l-natija", "Asl qiymat tiklandi.");
    await limitlar();
  }

  /* ── Texnik ta'til ────────────────────────────────────────── */
  async function tatil() {
    var d = await ol("/api/maintenance");
    $("maintSw").setAttribute("aria-pressed", d.active ? "true" : "false");
    $("m-matn").textContent = d.matn;
    $("m-textarea").value = d.matn;
    var h = d.holat, q = [];
    // Commit faqat Railway'da bor — mahalliyda qator umuman chiqmaydi.
    if (h.commit) q.push(["Oxirgi deploy", xavfsiz(h.commit), ""]);
    q.push(["Ishlash muddati", xavfsiz(h.ishlash), ""]);
    q.push(["Mavzu rejimi", h.mavzu ? "yoqiq" : "o'chiq", ""]);
    q.push(["Baza", h.baza ? "ulangan" : "ulanmagan", h.baza ? "up" : ""]);
    q.push(["Model", xavfsiz(h.model), ""]);
    $("m-holat").innerHTML = q.map(function (r) {
      return '<div class="kv"><span>' + r[0] + '</span><b class="' + r[2] + '">' +
             r[1] + "</b></div>";
    }).join("");
  }

  /* ── Kuzatish ─────────────────────────────────────────────── */
  async function kuzatuv() {
    var d = await ol("/api/watch");
    // Guruh qo'yilmagan bo'lsa kuzatuv UMUMAN ishlamaydi
    // (`get_watch_target()` `None` qaytaradi) — buni aytib turish kerak,
    // aks holda admin odam qo'shib, xabar kelmasligiga hayron bo'ladi.
    $("w-guruh").textContent = d.guruh === null ? "qo'yilmagan" : d.guruh;
    $("w-rows").innerHTML = d.rows.length
      ? d.rows.map(function (u) {
          var nom = u.username ? "@" + u.username : "ID:" + u.user_id;
          return '<div class="row"><div class="t"><b>' + xavfsiz(nom) +
            "</b><span>qo'shilgan " + xavfsiz(u.added_at || "—") + "</span></div>" +
            (d.guruh === null ? '<span class="tag">guruh yo\'q</span>'
                              : '<span class="tag ok">Faol</span>') +
            '<button class="btn sm danger" data-wdel="' + u.user_id + '">O\'chirish</button></div>';
        }).join("")
      : '<p class="hint">Kuzatuvda hech kim yo\'q.</p>';
  }

  /* ── Adminlar ─────────────────────────────────────────────── */
  async function adminlar() {
    var d = await ol("/api/admins");
    $("ad-rows").innerHTML = d.rows.map(function (a) {
      var nom = a.nom || ("ID:" + a.user_id);
      // Superadminni va o'zini o'chirish tugmasi KO'RSATILMAYDI. Bu
      // qulaylik, himoya emas — himoya serverda (`_check_can_remove_admin`).
      var tugma = (a.super || a.ozim) ? ""
        : '<button class="btn sm danger" data-addel="' + a.user_id + '">O\'chirish</button>';
      return '<div class="row"><div class="person"><div class="av' +
        (a.super ? " pro" : "") + '">' + bosh(nom) + "</div><div><b>" +
        xavfsiz(nom) + "</b><span>" + xavfsiz(a.user_id) + "</span></div></div>" +
        '<div class="spacer"></div><span class="tag' + (a.super ? " pro" : "") + '">' +
        (a.super ? "Superadmin" : "Admin") + "</span>" +
        (a.ozim ? '<span class="tag">siz</span>' : "") + tugma + "</div>";
    }).join("");
  }

  async function sozlamalar() {
    // To'rttasi birdan: sub-tab almashishi bir zumda bo'lsin (jurnal
    // ekranidagi bilan bir xil qaror).
    await Promise.all([limitlar(), tatil(), kuzatuv(), adminlar()]);
  }

  /* ── Promokodlar ──────────────────────────────────────────── */
  var KOD_HOLATI = {
    faol: '<span class="tag ok">Faol</span>',
    tugagan: '<span class="tag">Tugagan</span>',
    bekor: '<span class="tag ban">Bekor qilingan</span>'
  };

  async function promokodlar() {
    var d = await ol("/api/promo");
    $("p-rows").innerHTML = d.rows.length
      ? d.rows.map(function (c) {
          return '<tr><td><span class="code">' + xavfsiz(c.kod) + "</span></td>" +
            "<td>Pro · " + son(c.kun) + " kun</td>" +
            '<td class="num">' + son(c.ishlatilgan) + " / " + son(c.max) + "</td>" +
            '<td class="num">' + xavfsiz(c.muddat || "muddatsiz") + "</td>" +
            "<td>" + (KOD_HOLATI[c.holat] || xavfsiz(c.holat)) + "</td>" +
            "<td>" + (c.holat === "faol"
              ? '<button class="btn sm danger" data-pdel="' + xavfsiz(c.kod) + '">Bekor</button>'
              : "") + "</td></tr>";
        }).join("")
      : '<tr><td colspan="6" style="padding:26px 18px;color:var(--ink-3)">Promokod yaratilmagan.</td></tr>';
  }

  /* ── Bepul Pro ────────────────────────────────────────────── */
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

  /* ── Referal sharti ───────────────────────────────────────── */
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
    await Promise.all([promokodlar(), sovga(), referal()]);
  }

  /* ── Tarqatma (faqat ko'rish) ─────────────────────────────── */
  async function tarqatmalar() {
    var d = await ol("/api/broadcasts");
    $("b-rows").innerHTML = d.rows.length
      ? d.rows.map(function (b) {
          return '<div class="row"><div class="t"><b>' + xavfsiz(b.segment) +
            "</b><span>#" + xavfsiz(b.id) + "</span></div>" +
            '<span class="num">' + xavfsiz(b.vaqt || "—") + "</span>" +
            '<button class="btn sm danger" data-bdel="' + b.id + '">Bekor</button></div>';
        }).join("")
      : '<p class="hint">Rejalashtirilgan tarqatma yo\'q. Botda <span class="code">/xabar</span> → «Keyinroq yuborish».</p>';
  }

  /* ── Hodisalar ────────────────────────────────────────────── */

  /* Ro'yxat ichidagi tugmalar HAR yuklashda qayta chiziladi, shuning
     uchun tinglovchi qatorga emas, ro'yxatga qo'yiladi (delegatsiya).
     Har chizishdan keyin qayta bog'lash — eskisi ustiga yangisini
     qo'yib, bitta bosishni ikki marta bajaradigan yo'l. */
  function delegat(joyId, atribut, fn) {
    var joy = $(joyId);
    if (!joy) return;
    joy.addEventListener("click", function (e) {
      var b = e.target.closest("[" + atribut + "]");
      if (b && joy.contains(b)) fn(b.getAttribute(atribut), b);
    });
  }

  function sozlamaHodisalari() {
    delegat("l-rows", "data-lsave", function (k) {
      limitSaqla(k).catch(function (e) { natijaChiz("l-natija", String(e), true); });
    });
    delegat("l-rows", "data-lreset", function (k) {
      limitTikla(k).catch(function (e) { natijaChiz("l-natija", String(e), true); });
    });

    $("maintSw").addEventListener("click", async function () {
      var sw = $("maintSw");
      var yoq = sw.getAttribute("aria-pressed") !== "true";
      if (yoq && !await tasdiq("Texnik ta'til yoqilsinmi? Adminlardan boshqa hamma javob o'rniga ogohlantirish oladi.")) return;
      var j = await so_rov("/api/maintenance", { active: yoq });
      if (!j.ok) return natijaChiz("m-natija", j.xato, true);
      // Kalitchani javobdan keyin qo'yamiz: so'rov yiqilsa ekranda
      // «yoqilgan» turib, aslida o'chiq qolib ketardi.
      sw.setAttribute("aria-pressed", j.d.active ? "true" : "false");
      natijaChiz("m-natija", j.d.active ? "Texnik ta'til YOQILDI." : "Texnik ta'til o'chirildi.");
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
      var j = await so_rov("/api/maintenance", { matn: matn });
      if (!j.ok) return natijaChiz("m-natija", j.xato, true);
      $("m-matn").textContent = j.d.matn;
      $("m-forma").hidden = true;
      natijaChiz("m-natija", "Matn saqlandi.");
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
      var j = await so_rov("/api/watch", { amal: "group", guruh: $("w-guruh-input").value.trim() });
      if (!j.ok) return natijaChiz("w-natija", j.xato, true);
      $("w-guruh-forma").hidden = true;
      $("w-guruh-input").value = "";
      natijaChiz("w-natija", "Kuzatuv guruhi yangilandi.");
      await kuzatuv();
    });

    $("w-qosh").addEventListener("click", async function () {
      var kim = $("w-kim").value.trim();
      if (!kim) return natijaChiz("w-natija", "ID yoki @username yozing.", true);
      var j = await so_rov("/api/watch", { amal: "add", kim: kim });
      if (!j.ok) return natijaChiz("w-natija", j.xato, true);
      $("w-kim").value = "";
      natijaChiz("w-natija", "Kuzatuvga qo'shildi.");
      await kuzatuv();
    });
    delegat("w-rows", "data-wdel", async function (uid) {
      if (!await tasdiq("Kuzatuvdan olib tashlansinmi?")) return;
      var j = await so_rov("/api/watch", { amal: "remove", kim: uid });
      if (!j.ok) return natijaChiz("w-natija", j.xato, true);
      natijaChiz("w-natija", "Kuzatuvdan olindi.");
      await kuzatuv();
    });

    $("ad-qosh").addEventListener("click", async function () {
      var kim = $("ad-kim").value.trim();
      if (!kim) return natijaChiz("ad-natija", "Sonli ID yozing.", true);
      if (!await tasdiq("Bu odamga to'liq admin huquqi berilsinmi?")) return;
      var j = await so_rov("/api/admins", { amal: "add", kim: kim });
      if (!j.ok) return natijaChiz("ad-natija", j.xato, true);
      $("ad-kim").value = "";
      natijaChiz("ad-natija", "Admin qo'shildi — «Panel» tugmasi unda darhol paydo bo'ladi.");
      await adminlar();
    });
    delegat("ad-rows", "data-addel", async function (uid) {
      if (!await tasdiq("Admin huquqi olib tashlansinmi?")) return;
      var j = await so_rov("/api/admins", { amal: "remove", kim: uid });
      if (!j.ok) return natijaChiz("ad-natija", j.xato, true);
      natijaChiz("ad-natija", "Admin o'chirildi.");
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
      });
      if (!j.ok) return natijaChiz("p-natija", j.xato, true);
      ["p-kod", "p-kun", "p-max", "p-muddat"].forEach(function (id) { $(id).value = ""; });
      $("p-forma").hidden = true;
      natijaChiz("p-natija", j.d.kod + " yaratildi. Odamlarga yuborish uchun botda /kod.");
      await promokodlar();
    });
    delegat("p-rows", "data-pdel", async function (kod) {
      if (!await tasdiq(kod + " bekor qilinsinmi? Ishlatilganlar saqlanib qoladi.")) return;
      var j = await so_rov("/api/promo", { amal: "revoke", kod: kod });
      if (!j.ok) return natijaChiz("p-natija", j.xato, true);
      natijaChiz("p-natija", kod + " bekor qilindi.");
      await promokodlar();
    });

    $("g-yubor").addEventListener("click", async function () {
      var kimlar = $("g-kimlar").value.trim();
      if (!kimlar) return natijaChiz("g-natija", "Kimga? ID yoki @username yozing.", true);
      if (!await tasdiq("Bepul Pro berilsinmi? Har biriga botdan xabar boradi.")) return;
      var j = await so_rov("/api/giveaway", { kimlar: kimlar, kun: $("g-kun").value.trim() });
      if (!j.ok) return natijaChiz("g-natija", j.xato, true);
      var d = j.d, q = [];
      if (d.berildi.length) q.push(d.berildi.length + " tasiga berildi");
      // ⚠️ «Yetmadi» — Pro BERILGAN, faqat xabar bormagan. Admin buni
      // «bajarilmadi» deb tushunib, ikkinchi marta bermasligi kerak.
      if (d.yetmadi.length) q.push(d.yetmadi.length + " tasiga berildi, lekin xabar yetmadi");
      if (d.topilmadi.length) q.push("topilmadi: " + d.topilmadi.join(", "));
      natijaChiz("g-natija", q.join(" · "), !d.berildi.length && !d.yetmadi.length);
      if (d.berildi.length || d.yetmadi.length) $("g-kimlar").value = "";
      await sovga();
    });

    $("r-saqla").addEventListener("click", async function () {
      var j = await so_rov("/api/referral", {
        required: $("r-required").value.trim(),
        reward_days: $("r-days").value.trim()
      });
      if (!j.ok) return natijaChiz("r-natija", j.xato, true);
      natijaChiz("r-natija", j.d.required + " ta do'st → " + j.d.reward_days + " kun Pro.");
      await referal();
    });
  }

  function tarqatmaHodisalari() {
    delegat("b-rows", "data-bdel", async function (bid) {
      if (!await tasdiq("Rejalashtirilgan tarqatma bekor qilinsinmi?")) return;
      var j = await so_rov("/api/broadcasts/" + bid, null, "DELETE");
      if (!j.ok) return natijaChiz("b-natija", j.xato, true);
      natijaChiz("b-natija", "Bekor qilindi.");
      await tarqatmalar();
    });
  }

  /* ── Chiqish ──────────────────────────────────────────────── */
  function chiqish() {
    $("chiqish").addEventListener("click", async function () {
      titroq("medium");
      try { await fetch("/api/logout", { method: "POST" }); } catch (e) {}
      if (tg) tg.close();
      else xatoKorsat("Sessiya yopildi", "Panelni qayta ochish uchun Telegramdagi «Panel» tugmasini bosing.");
    });
    var q = $("qayta");
    if (q) q.addEventListener("click", function () { korsat("yuklash"); kir(); });
  }

  /* ── Ishga tushirish ──────────────────────────────────────── */
  qism("telegram", telegram);
  qism("navigatsiya", navigatsiya);
  qism("grafik", grafikHodisalari);
  qism("jadval", jadval);
  qism("jurnal", jurnalNav);
  qism("sozlama", sozlamaHodisalari);
  qism("promo", promoHodisalari);
  qism("tarqatma", tarqatmaHodisalari);
  qism("chiplar", chiplar);
  qism("chiqish", chiqish);
  kir();
})();
