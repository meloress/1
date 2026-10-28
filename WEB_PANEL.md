# WEB_PANEL.md

The web admin panel (`web/`), moved out of `CLAUDE.md` when that file passed 180 KB.
The plan behind it is `git show 3ba4744:REJA.md`. The panel's tests are listed in
`TESTLAR.md`; the asyncpg type rules are in `ADMIN.md` because they apply to every
query, not only the panel's.

### The web admin panel runs inside the bot process

`web/` is an aiohttp server started from `main()` — not a separate Railway service.
The reason is RAM caches: `config.apply_limit_overrides()` and
`database.load_watch_cache()` hold settings in memory, so a second process could write
a new limit to the database while the bot kept using the old value. One process, one
`DATABASE_URL`, one token. `aiohttp` is already a dependency (aiogram uses it), so the
panel added **no** new package.

It must never take the bot down: every route is wrapped by one `@web.middleware`
`try/except` that turns an unhandled exception into JSON plus a logged traceback, and
`main()` starts the server inside its own `try/except` so a failure to bind leaves the
bot running without a panel.

**Three independent auth layers** (`web/auth.py`), and only the last two are gates:

1. The blue menu button is set per chat (`services/menu.py::sync_menu_button()`) so it
   appears only for admins. This is **decoration** — the URL can be opened by hand.
2. `POST /api/session` verifies Telegram's `initData` HMAC with
   `aiogram.utils.web_app.safe_parse_webapp_init_data`, **plus an age check aiogram does
   not do** (5 minutes) — without it a stolen `initData` would work forever. Success sets
   a signed `HttpOnly; Secure` cookie holding only `user_id`, an expiry and an HMAC; no
   session table.
3. `@admin_only` on every `/api/*` handler re-runs `is_admin()` **on every request**,
   never cached, so a demoted admin is locked out on their next request rather than at
   the end of the 12-hour session.

⚠️ **The panel also sends `initData` on every request**, in `X-Telegram-Init-Data`, and
`admin_only` verifies that signature with the bot token **before** it looks at the cookie.
The header is the stronger proof — only Telegram can produce it — while the cookie is our
own signature and would stand for 12 hours if stolen. Its age limit is **24 hours**, not
the 5 minutes `/api/session` uses, and the difference is not laxness: `initData` is issued
once when the Mini App opens and never refreshes, so a 5-minute rule there would kill the
panel five minutes in. The cookie stays as the second path because a panel opened in a
plain browser has no `initData` at all.

The cookie key is a *derivative* of `BOT_TOKEN` (`sha256("webpanel:" + token)`), not the
token, so a leaked cookie signature cannot be turned back into the bot token.

⚠️ **`web/api.py` contains no SQL.** Every number it returns comes from a `db/database.py`
function — that is why `activity_stats()` and `top_users()` were moved there out of
`handlers/admin/stats.py` before that file was deleted. The second consumer is still
real: `daily.py` builds the daily report from the same functions, so a query written in
`api.py` means the panel and the report disagree from the day one of them is edited.
`tests/test_web_stats.py` check 8 fails on `SELECT`/`INSERT`/`UPDATE`/`DELETE`/`pool.acquire`
in either file.

⚠️ **Decoration must not depend on the database.** `_kim()` reads the admin's name and
role for the sidebar card, and both queries sit inside a `try/except`: authorisation
already happened above, so a one-second database hiccup must not turn a successful login
into a 500 and lock the admin out of the panel. `tests/test_web_auth.py` check 7 forces
those calls to raise and still expects `200`.

⚠️ **Refund order is Telegram first, then the database.** The order was copied from
`handlers/admin/users.py`, which has since been deleted — so `web/api.py::refund` is now
the only implementation and nothing else encodes the rule. Telegram can refuse a refund
(window expired, already refunded); the other order takes the plan away from a user whose
money never came back. `tests/test_web_users.py` check 9 is what holds the order in place.
If Telegram succeeds and the database write then fails, that is logged as its own loud
line — the plan is still live on the account.

⚠️ **Model-style input discipline applies to admin input too.** `/api/users?q=` goes to
Postgres as a parameter, never string-interpolated. The premium endpoint accepts only
`7 / 30 / 90 / null`; the first version turned an unparseable value into `None`, and
`None` means *unlimited* there — so `{"kun": "o'ttiz"}` granted lifetime Pro. Anything
the panel renders through `innerHTML` (error text, usernames) goes through `xavfsiz()`
in `panel.js` first.

⚠️ **A write endpoint that changes a cached setting must refresh the cache in the same
request.** Two do: `POST /api/limits` calls `config.apply_limit_overrides()` and
`POST /api/watch` calls `database.load_watch_cache()`. Both caches exist because they are
read on the hot path — `daily_limit()` runs on every message and `get_watch_target()` is
synchronous with no I/O at all — so without the refresh the database holds the new value
while the bot keeps using the old one, the panel says "saved", and **nothing raises**.
This is the concrete reason the panel runs in the bot's process; a second process could
not fix it at all. `tests/test_web_settings.py` checks 2 and 8 are the guard, and check 2
is the phase's whole acceptance criterion.

⚠️ **"Admin" is two tables, and a screen that reads one of them lies.** `admins` and
`superadmins` are separate, and `huquq_bormi()` checks both — so any list answering "who
can open this panel" has to check both too. `get_admins()` reads only the first, and on
the live database (2026-09-15) that table is **empty** while one superadmin exists: the
panel would have shown nobody while that person was logged into it. `database.get_panel_admins()`
is the union (`FULL OUTER JOIN`, one query, `is_super` flag included — which also removed
a per-row `is_superadmin()` call). Fake data never shows this; reading production does,
which is why every phase of this panel was checked against the live Postgres read-only.

⚠️ **`None` means two different things in the limits API and they must not be confused.**
On `POST /api/limits`, `qiymat: null` means *remove the override*, i.e. fall back to
`PLAN_LIMITS` — it is **not** unlimited (unlimited is what the `premium` plan is for, and
that plan is deliberately absent from the editable table). So an unparseable value cannot
be coerced to `None` here, for the same reason it could not be on the premium endpoint.
`0` is also not unlimited: it means "this plan does not have the feature".

`web/static/panel.js` splits its startup into `qism()`-wrapped blocks. One missing
element inside a single IIFE used to kill everything after it — navigation included —
with one line in the console and no visible cause. Buttons inside a list that is redrawn
after every write (`data-wdel`, `data-addel`, `data-pdel`, `data-pcopy`, `data-bdel`, `data-uid`) are
bound once on the **container** via `delegat()`, never on the row: rebinding after each
redraw stacks listeners and fires one click twice, which on a refund or a gift means
doing it twice.

The panel's logo is `/static/logo.jpg` **everywhere** it appears (`REJA.md` 3.2.1);
`tests/test_web_panel.py` check 4 fails on any other image source.

⚠️ **The panel has no tables and no second screen layout.** Every list is one
`.rows > .row` structure: on a wide screen a `--ust` grid variable turns it into aligned
columns, on a phone that variable is off and the row wraps into a card. The tables it
replaced were wrapped in `overflow-x:auto`, so on a phone the last column — "last seen",
and the action buttons — was simply off-screen, and nothing said so. If you add a list,
add it as `.rows`; a `<table>` there is the bug coming back.

⚠️ **The theme comes from Telegram, not from the panel.** `panel.js::tema()` copies
`tg.colorScheme` onto `data-tema` and subscribes to `themeChanged`; every colour is a
token defined on bare `:root` and re-defined under `[data-tema="light"]` *and* under
`prefers-color-scheme: light`, so the browser and the Mini App both get a complete
palette. This reverses the earlier decision (the panel used to be dark-only and painted
Telegram's header to match it) — that was fine until someone on a light client opened a
black page inside a white app. Do not re-introduce a hard-coded colour: the CSS rule is
that only the brand gradient and the SVG `<defs>` carry literal hex.

⚠️ **Panel strings live in `web/static/soz.js`, lists come from `/api/meta`.** The split
matters: a string only the panel shows belongs in the dictionary, a list the *bot* also
uses (tariff, limit, segment names) must come from `core/config.py` over `/api/meta`, or
it becomes the sixth hand-written copy.

⚠️ **Saving the limits is Telegram's MainButton, not a button per row.** The per-row
"Saqlash" was cut off at the right edge on a phone and gave that card a horizontal
scrollbar. The main button appears only when a field actually differs from what was
loaded, and after a successful save the toast offers **Bekor qilish** for 5 seconds,
which re-sends the previous values.

### The panel's second pass: speed, filters, export, alerts

⚠️ **Read endpoints run their queries in parallel, write endpoints must not.**
`overview` made **six** sequential round trips to Postgres on the most-opened screen;
`stats`, `user`, `journal_errors` and `watch` were the same shape. They are
`asyncio.gather` now. ⛔️ Do not copy the pattern into a write endpoint: `refund` needs
Telegram **before** the database, `watch_set` needs the cache refresh **after** the write,
and `user` still fetches the profile first because a missing profile makes the other two
queries pointless.

⚠️ **`_kun_qatori()` fills the empty days, and both charts go through it.** The database
only holds days where something happened, so a silent day is simply absent — and a chart
that skips it looks *better* than reality, because the dip never appears. The requests
chart and the revenue chart share the one helper (field names are parameters); a second
copy is how one of them would quietly start drawing a flat line. `panel.js::chizuvchi(prefix)`
is the same decision on the front end: the chart used to be bolted to fixed element ids
(`line`, `dots`, `tip`), so a second chart meant copying the whole function. Ids are
prefixed now (`chart-…`, `dchart-…`) and the code is one factory.

⚠️ **A filtered list and its count must be built from one filter.** `_jurnal_filtri()` /
`_audit_filtri()` return `(where, args)` and both the page query and the `COUNT(*)` use
it. Written twice, the panel says "found 41" over a filtered list, draws five pages, and
shows an empty screen from page two on — with nothing raising. The audit count also has
to carry the same `LEFT JOIN`s, because the search touches `u.username` and `t.username`.
`test_web_journal.py` checks 10-12 pin all of it, including that a malformed `kun` is
ignored rather than trusted — admin input is an untrusted boundary too.

⛔️ **CSV export escapes formulas, and that is a security control, not formatting.**
Excel executes a cell that starts with `=`, `+`, `-` or `@`, so a user who names
themselves `=HYPERLINK(…)` would be running code on the admin's machine the moment the
export is opened. `_csv_katak()` prefixes an apostrophe. The file also carries a BOM or
Excel reads it as ANSI and mangles every `o'` and `g'`. `test_web_journal.py` check 14 is
the guard.

⚠️ **The export arrives as a Telegram document, not a browser download.** The panel is a
Mini App, i.e. a Telegram webview, and a `blob:` download fails silently there — the admin
taps the button and nothing happens. `_hujjat()` sends the bytes to the **requesting
admin** (`request["user_id"]`, never a `_target`), which also means the file lands in a
chat where it can be forwarded. Every export writes an `export` row to the audit log:
data leaving the system is different from data looked at inside it.

⚠️ **Alerts exist because the panel is pull-only.** Nothing tells an admin anything until
they open it, and the daily report arrives in the morning — so a bot that died in the
evening was discovered the next day. `admin_daily.alert_watcher()` closes that window with
**exactly two** conditions: an error surge, and silence. Adding a third needs a good
reason; an alert that fires often is an alert nobody reads, and then the real one is
missed too.

Three details are load-bearing. The repeat flag lives in RAM (`_ogoh_holat`) and clears
when the condition does, so one outage is one message and a recovery re-arms it. Silence
between 02:00 and 08:00 Tashkent is **not** reported, or every night would produce a false
alarm. And `last_activity_at()` returning `None` (an empty table, a fresh bot) is not
"silent forever" — it is ignored. `tests/test_ogohlantirish.py` checks 2, 4 and 8 hold
those three.

⚠️ **Token spend is written to the database now, not only to the log.** The bot runs on
a free daily grant and the panel could not say how much of it was gone — `[TOKEN]` lines
existed only in the Railway log, which is a stream, not an answer to "how much today".
`_log_token_usage()` still logs, and additionally fires `_token_saqla()` as a background
task: the reply never waits on it and a database failure is swallowed, because accounting
is not more important than the answer.

The rows go into **`user_history`**, a table that already existed and that **nothing had
ever written to** — so no new table, and the per-user column comes free, which is what
makes "who is burning the grant" answerable at all. `token_stats()` cuts days by
**Tashkent**, not UTC (`created_at` is a naive UTC timestamp), or "today" would roll over
at 05:00 and the morning number would be yesterday's. `TOKEN_SAQLASH_KUN` (90) is trimmed
once a day inside `daily_report_watcher` — a table nothing trimmed would grow forever at
~2 400 rows a day.

⚠️ **The grant is a measurement, not a limit**, and the panel says so: tokens past it
still work, they are simply billable. So the card reads "grantdan oshdi", never
"blocked". And the cached share is displayed **beside** the total, never subtracted from
it — OpenAI confirmed (2026-09-09) that cached input counts against the quota exactly the
same. What that percentage actually tells you is whether the request prefix is still
stable through the day; if it falls, something per-user has leaked into the cached prefix.
`tests/test_web_stats.py` checks 9-9d pin the arithmetic, the empty-database case, and
that the write stays off the reply path.

### The panel's third pass: the phone, the double tap, the stale card

Four complaints, and every one of them was invisible to the test suite because the
suite has no browser, no Telegram and no types.

⛔️ **`touch-action: manipulation` goes on `html, body`, not on the buttons.** The
complaint was double-tap zoom on *text and empty space*, so closing only the tappable
elements would have fixed the part nobody was tapping. ⚠️ Do not "also" add
`user-scalable=no` to the viewport: iOS has ignored it since iOS 10, and where it is
honoured it kills pinch-zoom for someone who needs it. Pinch still works; only the
accidental double tap stopped zooming.

⚠️ **Every input is `max(16px, …)` and 16px is an iOS constant, not a taste.** Below
it, WKWebView force-zooms the whole page on focus and never zooms back. Three
selectors carry it (`input,textarea,select`, `.field input`, `.kiritish`) — the bare
element rule matters because `font: inherit` was pulling 15px from `body`. The
`transform: scale()` trick was deliberately not used: it moves the focus ring and the
hit area with it.

⚠️ **`:hover` lives in one `@media (hover:hover) and (pointer:fine)` block.** On a
phone the hover state sticks after the finger leaves and the row reads as "selected".
Moving the rules earlier in the file was the risky part, not the media query — four of
them compete with `[aria-current]` or `.btn.danger` at *equal* specificity, so the
relative order had to be preserved. Check that before moving any of them again.

⚠️ **`tg.expand()` does nothing on desktop.** It sets the height on phones; the narrow
window on Telegram Desktop needs `requestFullscreen()` (Bot API 8.0), guarded by
`typeof`, `isVersionAtLeast("8.0")` and `try/catch`. ⛔️ **There is no platform value
`"web"`** — Telegram Web is `weba` and `webk`. Writing `"web"` makes the condition
never fire and the bug stays silent, which is why `test_panel_korinish.py` check 12
asserts the set of four exactly.

⚠️ **`sahifa()` no longer returns a `FileResponse`.** It reads `panel.html` once and
rewrites every `/static/*.css|js` link to `?v=<that file's own sha256 prefix>`, so an
admin cannot be left on yesterday's JavaScript after a deploy while an unchanged file
stays cached. Per-file hashes, not one global version. ⚠️ The version is never written
by hand: a hand-written number is forgotten exactly once, and then cache-busting
*looks* present while doing nothing — worse than not having it. `logo.jpg` is
deliberately untouched (`REJA.md` 3.2.1 fixes its URL). One consequence for local work:
the rendered page is cached in a module global, so editing CSS during development needs
a restart.

⚠️ **The error row goes to the top of the `<section>`, not into its first `.card`.**
On six of the eight screens the first `.card` sits *after* the KPI row — 1277 characters
into `dash` — so on a phone the "could not load" message was below the fold while five
`—` placeholders sat on screen saying nothing. A static `—` does not distinguish "not
loaded yet" from "the request failed", which is why the KPI values now show a skeleton
first. This was a live incident, not a hypothetical: a 500 from `/api/overview` looked
exactly like an idle panel.

### Two clicks, and why the disabled button is not the fix

`so_rov(yol, tana, usul, tugma)` disables the button for the duration of the request,
synchronously, before the first `await`. That stops the double tap **on screen**. It is
not a guarantee: a slow network, a page reload or a second app window still sends two
requests, and `set_user_premium(..., extend=True)` *adds* days, so the second one
silently turned 30 into 60.

`@bir_marta` (`web/auth.py`) is the server half. Three things decide whether it works:

- ⭐ **The key is derived from the content, never random.** A `crypto.randomUUID()` per
  call cannot stop a double tap — two taps produce two UUIDs and both look new. The key
  is `sha256(user_id + path_qs + body)` with a 10-second window; an explicit
  `Idempotency-Key` header overrides it when a deliberate repeat is wanted. ⚠️ `path_qs`,
  not `path`: `/api/export?tur=users` and `?tur=payments` share a path and an empty body.
- ⭐ **A per-key `asyncio.Lock`.** The second request arrives while the first is still
  running, so caching the result afterwards buys nothing on its own. The second waits and
  returns the first's response.
- **Only 2xx is cached.** A cached 4xx would show the admin a stale error after they had
  already fixed the cause, and a failed request performed nothing, so repeating it is
  free.

Which endpoints carry it is **computed, not listed**: those whose repeat has an external
effect (they send through `_xabar` / `_hujjat` / `_guruh_sinovi`, or pass `extend=True`).
The other eight rewrite the same state and are naturally idempotent. ⛔️ `refund` is
deliberately excluded: `refunded_at` is an atomic, *permanent* guard, and a 10-second
cache would only hide the 409 behind a 200 — the wrong trade on a money path. Its bug
was different and is fixed: `mark_payment_refunded()` already returned `False` for the
loser of a race, and the caller ignored it, so the loser still wrote an audit row and
sent the user a **second** "your money was refunded" message.

### The alert channel could fail silently, and nothing said so

The panel is pull-only, so `alert_watcher()` is the one thing that reaches an admin
without being asked. It writes to the watch group — and that send could fail with
nothing but a `logger.warning`, i.e. the "the bot is down" message failing was visible
only in the log you read when the bot is down.

⭐ **`_ogoh_holat` is set from the send's return value, never before it.** That flag
means "this has already been reported". Setting it for a message that never arrived
marks an unsaid thing as said, and since the flag only clears when the *condition*
clears, the alert was then lost completely. `_ogoh_yubor()` returns a bool for exactly
this. The retry interval is the existing 15-minute check with no backoff and no new
constant: a send that fails reaches nobody, so retrying cannot spam anyone — the only
cost is 96 failed Telegram calls a day, and it stops the moment one lands.

⛔️ **Only a group-level failure lights the banner.** `config.guruh_xato_sababi()` is
the single classifier (the list is `GURUH_XATOSI`, and `test_web_settings.py` check 15
fails if any of the three consumers copies it). "Message is too long", "can't parse
entities", a rejected media type — those fix themselves on the next message, and putting
them on the banner would leave it permanently lit, which is a banner nobody reads.
`_send_watch_copy()` therefore records **once, at the end**: the fallback rung succeeding
means the group is healthy, so writing on each `except` would flash "broken → fixed" for
a message that was actually delivered.

The state lives in three `watch_settings` columns and the banner condition compares two
timestamps, so a successful send clears it by itself — there is no "dismiss" button and
no clearing step that can be forgotten. `database.watch_holat_yoz()` only writes when the
state *changes*, because `_send_watch_copy()` runs on every message of a watched user.


### The panel's own security rules

⛔️ **The client IP is the *rightmost* `X-Forwarded-For` entry, never the first.** The
client writes the leftmost one, so the old code let anyone defeat the rate limit by
sending a different value each request — and leave a permanent key behind each time, a
memory-exhaustion path of its own. `ISHONCHLI_PROKSI` counts hops from the right, and
`XFF_TEKSHIR=1` exists to log the raw header once on Railway so that number can be
confirmed; turn it off afterwards, it prints IP addresses.

⚠️ **The rate limiter is bounded now** (`CHASTOTA_OYNA`, `CHASTOTA_MAX`) and it counts
writes per **admin**, not per IP — the caller already passed the signature and the
permission check, and a phone changes IP every few minutes. `YOZUV_RATE_LIMIT` is 120/min
and that number is aimed at a runaway script, not at a fast human: a limit set near real
usage fires on legitimate bursts, the admin learns to ignore it, and then the real one is
missed too. The measurement behind it is that the heaviest test file makes 31 writes in a
few seconds.

⛔️ **`X-Frame-Options` must never be added.** The Mini App is loaded in an iframe by
Telegram Web, so `DENY` and `SAMEORIGIN` both kill the panel outright. Framing is
controlled by `frame-ancestors` (`telegram.org` plus `*.telegram.org`, which covers
`web.`, `webk.`, `webz.`, `weba.`); desktop and mobile use an embedded webview, where the
directive does not apply at all.

⚠️ **CSP is enforcing since 2026-09-29** — it shipped as `Content-Security-Policy-Report-Only`
first, and three weeks of logs (all 60 deployments, searched through the GraphQL
`deploymentLogs` API) held no real violation. `frame-ancestors` is **ignored** in
Report-Only, so it was checked by hand instead (Web is `web.telegram.org`, covered by
`*.telegram.org`). If the panel ever goes blank in one client, this header is the first
suspect; `report-uri` is still on. The original reasoning: two unknowns can
only be settled live: the inline `style=` attributes in `panel.html` (hence
`'unsafe-inline'` on `style-src`) and how Telegram Desktop's webview answers
`frame-ancestors`. `POST /csp-report` logs violations to Railway, because Report-Only
tells you nothing on a phone where the console cannot be opened. That endpoint is
deliberately **not** under `/api/` and deliberately has no `@admin_only` — the browser
sends the report without our header or cookie — so the "every `/api/*` is guarded" rule
stays intact. Flip to enforcing only after the log stays quiet through every screen on
iOS, Android, Desktop and Web; `test_web_xavfsizlik.py` check 6b now pins the enforcing
state.

`del_cookie()` in aiohttp 3.9.5 takes only `domain`/`path`, so logout sets the cookie to
`""` with `max_age=0` and the **same** `Secure`/`SameSite`/`HttpOnly` attributes instead.

### Setting a plan is not adding to one, and the screen has to say so

Five grant sites exist. Four go through `_EXTEND_PLAN_SQL` and **add** (Stars payment,
promo code, referral reward, and the panel's gift via `extend=True`); that SQL
carries the three guards `test_pro_grant.py` freezes — `GREATEST(..., NOW())` so a lapsed
subscription's days are not added to a past date, unlimited stays unlimited, and the tier
never drops. There is no recurring-subscription path at all, so no renewal can lose days.

The fifth is the profile card, and it **overwrites** — deliberately, because it is the
correction tool: without it an admin who mistyped 3650 days could never shorten it. That
is frozen by `test_pro_grant.py` check 4 and must stay. The defect was never the
behaviour, it was that nothing said so:

- the button now reads **"Muddatni belgilash"**, against "qo'shish" on the gift screen —
  the verbs differ, so the two actions differ before any dialog opens;
- the confirmation states the **current** state in one of four wordings (free, dated,
  from-unlimited, to-unlimited) — "Ishonchingiz komilmi?" is not a confirmation, it is a
  button with extra steps, and `test_panel_korinish.py` check 14 rejects that phrasing;
- ⭐ the panel sends the `premium_until` **it displayed**, and
  `set_user_premium_checked()` compares it against the live row inside one transaction
  with `FOR UPDATE`, answering **409** on a mismatch. Without it, a payment landing
  between opening the card and tapping the chip would be erased by an admin who never saw
  it. A separate `SELECT` then `UPDATE` would leave exactly that window open, so the
  comparison has to be inside the transaction.
- ⛔️ the `holat` field is **required**; accepting its absence would leave the bypass as
  "just omit the field". The panel is this endpoint's only client and deploys in the same
  process, so an "old client" is a tab left open across a deploy — and that tab is showing
  stale numbers anyway, which is the hazard itself.

The audit row is JSON now (`{"kun":30,"oldin":{"tarif","muddat","qolgan"}}`) so the
previous expiry can actually be restored; `_premium_tafsiloti()` renders it as
`30 kun (oldin: 20 kun)` on the journal screen and falls through to the raw string for the
older rows, which are still plain `"30"` and `"sovga 45 kun"`.
