# ADMIN.md

The admin handlers that stayed in the bot (`handlers/admin/`), the database rules
(`db/database.py`, asyncpg, migrations) and the shared label dicts in `core/config.py`.
Moved out of `CLAUDE.md` on 2026-10-28; `CLAUDE.md` keeps one line per section. The web
panel itself is `WEB_PANEL.md`.

### What is left in the bot, and why each thing stayed

`handlers/admin/` is now five modules: `common.py` (guards + helpers used by more than
one *screen*, where "screen" includes the web panel — that is why
`_check_can_remove_admin()` lives there rather than in `system.py`), `broadcast.py`,
`promo.py` (sending only), `system.py` (report only), `daily.py` (the two background
watchers), and `__init__.py`, which does **nothing but register handlers**. It was one
2671-line file; then twelve screens; now **21 registrations**, down from 57.

Everything else moved to `web/`. What stayed did so for one reason each, and the reason
is always *"the bot can do this and a web form cannot"*:

- **`/xabar`** — broadcast. `copy_message` forwards the admin's own message verbatim:
  album, formatting, premium emoji. A message reassembled from a web form loses all of it.
- **`/kod`** — sending a promo code or a referral invite to named people.
  `send_promo_gift()` sends a ready button, `send_referral_invite()` builds each person's
  *own* link. Creating and revoking codes is in the panel; only the sending is here, so
  there is no second copy of anything.
- **report** (`report_callback` / `process_report_message`) — started by an ordinary
  user, who has no panel at all. These two are the **only** handlers here with no admin
  check, deliberately.
- **the daily report** (`daily.py`) — push; its whole point is arriving without opening
  anything.
- **payments** — in `main.py`, before every router; that ordering is untouchable.

Three things survived every refactor and must keep surviving:

1. **Registration order in `__init__.py` is functional.** FSM states go *after* the
   command handlers (otherwise an admin stuck in a state cannot invoke anything else),
   and `waiting_for_button` / `waiting_for_recipients` / `waiting_for_schedule` go
   *before* `waiting_for_content` (otherwise the button label an admin types is swallowed
   as "new broadcast content").
2. **The admin check lives inside each handler, not in a filter** — because
   `report_callback` and `process_report_message` are deliberately open to ordinary users.
3. **`bot` comes from `core.loader`**, not from a closure; no handler touches `dp`.

⛔️ **Entry points are commands, not reply-keyboard text.** The four-button reply keyboard
is gone (`core/keyboards.py` deleted). A handler bound to `F.text == '📢 Xabar yuborish'`
would now be **dead code that still registers**: the button no longer exists and nobody
types that string by hand. `tests/test_admin_registry.py` check 3 fails if `F.text ==`
reappears there.

⚠️ **Deleting the keyboard does not remove it from anyone's phone.** Telegram keeps a
`ReplyKeyboardMarkup` on screen until it is replaced or explicitly removed, so `/start`
sends `ReplyKeyboardRemove()`. Without it, admins would keep tapping four buttons that
answer nothing — which reads as "the bot broke", not as "this moved to the panel".

⚠️ **The keyboard was also the only *discoverable* entry point**, so removing it without
a replacement would leave `/xabar` findable only by memory. `services/menu.py::ADMIN_COMMANDS`
puts both commands in the `/` list, for admins only. Two traps came with that: the
`_shown` cache compared a single `is_pro` bool with `is`, so an admin-flag change would
never have been noticed (it is keyed on the `(is_pro, is_admin)` pair now); and the
`sync_commands(..., True, ...)` call has to sit **inside** the `if admin_flag` branch —
outside it, every ordinary user got `is_pro=True` and saw `/kunlik` and `/research` in
their menu. `tests/test_menu.py` check 3b guards the leak.

Anything written to `user_activity` must also appear in **`core/config.py::ACTIVITY_TYPES`**
— one dict of `type -> (emoji, label, points)` — or it silently vanishes from statistics.
That list is the SQL filter (`database.activity_stats()` and `daily_report_stats()` pass
it as `= ANY($1)`), the daily report's labels and the web panel's bar names — three
consumers now that the Telegram statistics screen is gone. It used to be three
hand-written copies. `tests/test_activity_tracking.py` guards it by **importing** the
dict rather than reading a file by path, so moving code no longer breaks it.

The admin path spends **zero AI tokens**: nothing under `handlers/admin/` calls
`services.ai`, and `non_admin_predicate` in `main.py` keeps admins out of the AI handlers
entirely.

⚠️ **A test that fails after a deletion is telling you where its rule moved.** Four did,
and none of them wanted its assertion deleted: a label nothing writes any more
(`referral_campaign`) had to leave `AUDIT_ACTIONS`; a "both screens call one validator"
check became "the limits must not migrate into `web/api.py`"; two checks that read a
deleted file now check the *source* of the keys instead (does `broadcast.py` really write
this segment; is this limit key really in `PLAN_LIMITS`); and "two screens, same numbers"
became "no raw SQL in `web/api.py` or `daily.py`". Ask what the check was protecting
before you change it — it is almost never the screen.

### asyncpg type rules no offline test can see

⚠️ **Two asyncpg type rules broke this panel live, and no offline test could
see either.** Both endpoints came back 500 while every test passed, because the
fake database has no types at all.

- `NOW() - ($N || ' days')::interval` makes asyncpg infer `$N` as **text**, so an
  `int` raises `DataError`. Everything else in `db/database.py` already passed
  `str(...)` (`str(within_days)`, `str(int(days))`); the two new journal filters
  did not, and took the audit screen, the error screen **and** `alert_watcher()`
  down with them — the watcher retried every 15 minutes, forever.
- `SUM()` over a **BIGINT** column returns `NUMERIC`, which asyncpg gives back as
  `Decimal`, which `json_response` cannot serialise. `user_history`'s columns are
  BIGINT, so every token query needs `::bigint`. This one did not appear on
  deploy: the table was still empty, `SUM` returned `NULL`, and the screen only
  died once the first real request had been logged.

`test_web_stats.py` check 9e and `test_web_journal.py` check 17 read the **source
text** for both rules — the same approach as `test_panel_raqamlar.py`, and the only
one available without a database.
- `TIMESTAMPTZ` comes back from asyncpg **in UTC**. Anything shown to a person or to the
  model goes through `astimezone(TASHKENT_TZ)` first — the reminder list sat five hours
  behind for a while and nobody noticed.

### Migrations run before the bot starts, so they must be cheap

`create_users_table()` / `create_history_table()` are awaited in `main()` ahead of
polling and the web server. Everything in them blocks startup.

⛔️ **`CREATE INDEX CONCURRENTLY` is therefore NOT in them** — it is in
`indekslarni_qur()`, which `main.py` fires with `asyncio.create_task()`. `CONCURRENTLY`
scans the whole table and takes seconds on a large one; awaited, both the bot and the
panel would sit dark for that long, for something that only affects *speed*. An
unindexed bot works, just slower; a bot still waiting works not at all. The result goes
to the log only (`[indeks] … tayyor` / `… qurilmadi: …`).

Two traps come with `CONCURRENTLY`, and `test_panel_raqamlar.py` check 12 pins both.
asyncpg sends `conn.execute(sql)` over the simple query protocol and opens no
transaction — but **only when no parameters are passed**; add one and it switches to a
prepared statement and Postgres answers "cannot run inside a transaction block". And a
failed `CONCURRENTLY` leaves an **invalid** index that `IF NOT EXISTS` then happily skips
forever, so `_indeks_yarat()` checks `pg_index.indisvalid` and drops it (also
`CONCURRENTLY`) before rebuilding. Its error is logged as a warning rather than swallowed:
the existing index block ends in `except: pass`, which is why these calls sit outside it.

### `make_interval`, not string concatenation

Every day-interval in the codebase is `make_interval(days => $N::int)`. The old
`($N || ' days')::interval` made asyncpg infer `$N` as **text**, so passing an `int`
raised `DataError` — that single line killed the audit screen, the error screen and
`alert_watcher()`, which then retried every 15 minutes forever. Wrapping the arguments
in `str()` fixed the symptom and left the trap in place for the next writer.
`test_web_journal.py` check 17 walks the tree (comments stripped) and fails if the old
spelling returns. `_YOZ_MUDDAT_SQL` still contains `NOW() +` and still has no `GREATEST`,
so `test_pro_grant.py` check 4 — the frozen overwrite behaviour — is untouched by this.
### Five label maps that all rotted the same way

`core/config.py` holds five dicts — `ACTIVITY_TYPES`, `AUDIT_ACTIONS`, `LIMIT_NOMI`,
`SEGMENT_NOMI`, `TARIF_NOMI` — for one reason: the same list kept being hand-written in each new
screen, and **every single copy drifted**. Found one per phase, always the same way:

- activity type labels were written twice in `handlers/admin/stats.py` and a third time
  in `handlers/admin/daily.py` as `ACTIVITY_LABELS`, which was already missing
  `location_message` — the daily report printed the raw type name;
- audit action labels lived in `handlers/admin/journal.py` as `ACTION_LABELS` and **9 of
  16 keys did not match what the code writes** (`ban` vs `ban_user`, `refund` vs
  `refund_stars`), so most of the audit screen showed technical strings;
- the four daily limits were named in `handlers/admin/journal.py::LIMIT_KEYS` *and* in
  `web/api.py::SANOQ_NOMI`, differently — "Fayl" vs "Fayllar", "Tadqiqot" vs "Chuqur
  tadqiqot". Two screens naming one setting two ways reads as two settings;
- the **tariff names** lived in `panel.js` as `PLAN = {pro: "Pro", free: "Bepul"}` and that
  copy had no `premium` at all — so a user on the unlimited `premium` plan showed as "Pro"
  in the table while the dashboard's distribution ring gave them their own segment. One
  person, two screens, two tariffs. `TARIF_NOMI` is now the list and the panel reads it
  from `/api/meta`; its keys are asserted equal to `PLAN_LIMITS`'s;
- broadcast segment labels sat inline in `handlers/admin/journal.py` as `segment_nom`.
  The first web copy of it invented `"pro"` and `"active"`, **neither of which exists**
  (`_filter_users_by_segment` writes `all` / `free` / `premium` / `pick`), so the panel
  would have shown `premium` raw. Caught by reading the source that writes the value —
  not by testing the screen.

All five are now one dict each, read by every consumer. If you add a screen that names
one of these things, read the dict — do not retype the list. And when you do write a new
copy anyway, the guard is always the same: walk the source for the calls that *write* the
values and compare both directions, as `tests/test_web_journal.py` checks 1-2 do.

The same discipline applies to **rules**, not just labels. Three validators are shared by
the Telegram screen and the panel, and neither may re-implement them:
`database.clean_promo_spec()` (promo code shape, 1-3650 days, 1-100000 uses, expiry in
the future — it used to live in the body of `process_promo_create`),
`database.clean_referral_config()`, and `handlers/admin/common.py::_check_can_remove_admin()`.
That last one moved out of `system.py` when the panel needed it: written twice, the panel
would have become a **weaker door than the bot** (removing yourself, removing a
superadmin, the three-day wait for a new admin, the last-admin guard) and nothing would
have caught it.

### Errors reach the admin through one funnel

Every admin action name written to `admin_audit` must appear in **`core/config.py::AUDIT_ACTIONS`** (`action -> (label, icon)`), which the panel's journal screen reads through `audit_nomi()`. The label carries **no emoji** — the icon is a key the panel resolves against its own line-SVG set (`panel.js::IKONKA`), so the journal matches the rest of the UI instead of being the one screen made of emoji; an unknown key draws a dot, so a new action is never invisible.

An action the code no longer writes must be **removed** from `AUDIT_ACTIONS` — `referral_campaign` was, when its flow moved to the panel — and moved to **`AUDIT_ESKI`**, the second dict, which exists only for action names that are in the live database and not in the code. Two dicts, two questions: "what does the code write" and "what is lying in the table". `audit_nomi()` falls through `AUDIT_ACTIONS` → `AUDIT_ESKI` → the raw string, and the raw string is still shown rather than hidden (`test_web_journal.py` check 4): a hidden row reads as no row at all. ⚠️ `AUDIT_ESKI` was written from the names this repo is known to have used; it could **not** be checked against the live table (production reads are blocked in this environment), so an action nobody remembers will still appear raw — which is the safe direction. It used to be a hand-written `ACTION_LABELS` in `handlers/admin/journal.py` and it had rotted badly: 9 of 16 action names did not match what the code writes (`ban` vs `ban_user`, `refund` vs `refund_stars`, `set_free` vs `set_plan`, `promo_create` vs `create_promo`), so most of the audit screen showed raw technical strings, while 6 labels hung on keys nothing ever writes. `tests/test_web_journal.py` walks the source for `log_admin_action(...)` and web's `_yoz(...)` calls and asserts both directions: every written action has a label, and every label is actually written.

`send_error_with_retry()` (`handlers/helpers.py`) is the only path a user-visible failure takes, so that is where `db.log_error()` writes to the `error_log` table — the "⚠️ Xatolar" screen reads it. Adding a second logging site elsewhere splits the picture; pass a `kind` instead (`"timeout"`, `"matn"`, …). The table trims itself on write (`ERROR_LOG_KEEP`).
