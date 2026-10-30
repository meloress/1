# DEPLOY.md

Railway in detail: the account and service ids, reading production logs, the GraphQL
queries, and which bot runs on which token. Moved out of `CLAUDE.md` on 2026-10-28; the
push command and the rules that bite on every deploy stayed there.

## Deploy details

The public domain (Settings → Networking → Generate Domain) is what `WEB_APP_URL` and the
blue Mini App button are derived from.
⚠️ Since phase 7 this is no longer cosmetic. "Empty means no menu button; the bot is
unaffected" was true while every admin screen still existed in Telegram — it does not any
more. With no domain, an admin has **only** `/xabar` and `/kod`: no statistics, no user
management, no limits, no journal. Deploying without the domain is not a degraded panel,
it is no panel.

Both the account and the remote moved on 2026-09-08; the GraphQL path below is history, kept only in case the GitHub connection is removed again.

- Without a GitHub connection, `git push` does *not* deploy and a plain deploy call rebuilds the snapshot taken when the service was created, i.e. old code. Deploys then have to name the commit explicitly:
  `serviceInstanceDeployV2(serviceId, environmentId, commitSha)` against `https://backboard.railway.com/graphql/v2` with a team token (`Authorization: Bearer`, and a real `User-Agent` — Cloudflare answers `403 error code: 1010` to the default urllib one). Railway fetches the commit from the repo, so **the service must point at the repo that actually has that commit, and it must be public**. The `up` endpoint (local tarball upload) fails on this account.
### Karta payment: the card lives in the panel, not in Railway (2026-10-30)

There is **no** Railway variable for it. The card number and holder name are in
`bot_settings` (`karta_raqam`, `karta_egasi`), set from panel → Sozlamalar → **Karta** by
the superadmin, live on the next `/pro` without a deploy. Empty hides the «💳 Karta orqali»
button entirely, so the feature ships dark. Every request stores which card it was shown,
so a receipt for the previous card still shows that card's last four digits. Receipts go
to the **superadmin only** (`get_superadmin_id()`), and only `is_superadmin()` can press
approve/reject. Never ask the owner for the card number in chat — they type it in the panel.

### Reading production logs

The user is logged into the Railway CLI on this machine (`~/.railway/config.json`), so
logs are readable directly — no token, no copy-paste:

```bash
railway status
timeout 45 railway logs      # streams, never exits on its own — the timeout is required
timeout 60 railway logs -b   # build logs
```

⚠️ **The login expires.** Run `railway whoami` first: "Unauthorized. Please login with
`railway login`" means every command above prints nothing, and `railway logs | grep …`
returning empty then reads as "no errors" when it is "no access". Only the user can log in
again (browser flow); say so instead of concluding anything from the empty output.

Older logs (past the stream) come from the GraphQL API: `deployments(input: {projectId,
environmentId, serviceId}, first: N)` for the ids, then
`deploymentLogs(deploymentId: $id, limit: 500) { message timestamp }` per deployment —
that is how three weeks of CSP reports were searched across 60 deployments.

⚠️ **`railway link` and `railway list` are broken on this account (CLI 4.6.3).** `list`
prints an empty list and `link -p <id>` answers *"not found in Melores's Projects team"*
for a project that is demonstrably there. The CLI asks for the deprecated `me { projects }`
field, which always returns empty — the same wrong query cost an hour here. The working
query is `me { workspaces { projects { edges { node { … } } } } }`, and the link has to be
written into `~/.railway/config.json` by hand, keyed by directory path. That file holds
`user.token`; never print it.

- workspace `Melores's Projects` `e4ee0499-8975-4fdb-a58d-3070e58dd692`
- project `truthful-prosperity` `ca061dfe-9a94-41a1-a135-9312e8fbfbc5`
- environment `production` `598aeb0b-1ff2-4a49-b055-44b39b9d764a`
- service **`1`** (this bot — `@vexonai` since 2026-10-25, `@uzchatgptaibot` before; the
  old one runs in the same service as a redirect, see "The bot moved to @vexonai") `d644a705-d075-440b-a68d-9fd21dcbd44b`
- the same project also runs `Melores-Bot`, `Hisobotchi-bot`, `Trello-bot`, `Web-panel`
  and several Postgres instances — ours is the one named `1`

**Which commit is live** comes from `deployments(input: {projectId, environmentId,
serviceId})` → `node.meta.commitHash` / `commitMessage` / `createdAt` (UTC; Tashkent is
UTC+5). Use it before concluding anything from a screenshot — a table complaint was
nearly misdiagnosed because it was unclear whether the fix had deployed yet.

⚠️ **Poll that query with `first: 1` and wait for `SUCCESS <the hash you pushed>`.**
`railway status` right after a push can still report the *previous* deployment's
`SUCCESS`, which reads as "deployed" when the build has not started.

- One `TelegramConflictError` right after a deploy is normal: the old container keeps
  polling for a few seconds while the new one starts. Only a repeating one is a problem.
- A build stuck in BUILDING / DEPLOYING for 15+ minutes is usually Railway itself — check
  status.railway.com before debugging the code (2026-09-29: "API degradation causing slow
  or stuck deployments", every region).

The logs are the best source of work. Both of the largest problems found on 2026-09-10
came from reading them, not from guessing: the image picker burning 47 843 tokens on one
request, and a silent `asyncio.TimeoutError` (whose `str()` is empty) making the picker
fall back to unseen candidates.

### The bot moved to @vexonai; the old one only redirects

On 2026-10-25 the bot moved from `@uzchatgptaibot` to **`@vexonai`** (brand **Vexon AI**).
`BOT_TOKEN` is the new bot; the old token sits in **`ESKI_BOT_TOKEN`** and
`handlers/eski_bot.py` polls it **inside the same process** with its own `Dispatcher`.
Whatever anyone does there — text, photo, a stale button, `@mention` in a group — gets one
fixed message (logo + "@vexonai, your Pro and history are kept there"). Same database, same
user ids, so the claim is true. `tests/test_eski_bot.py` pins the rules below.

- ⛔️ **A Business customer of the old bot gets nothing.** They think they are talking to
  the owner; "this bot has stopped" would land in the owner's name. Only the owner is told,
  once, to connect `@vexonai` (check 2).
- `pre_checkout_query` is **rejected**, so nobody pays the dead bot (check 3).
- `ESKI_BOT_TOKEN == BOT_TOKEN` is refused in `main.py`: two pollers on one token raise
  `TelegramConflictError` and the **main** bot starts losing updates (check 7).
- The module touches no database (check 8) and never raises into `main()`.
- The bot's own name is read from `getMe` (`pro.BOT_USERNAME`) in every user-facing text,
  with `'vexonai'` as the fallback — the old name hard-coded in the Business setup steps
  would have sent every new owner to the dead bot.

⛔️ **A new Business connection inherits the owner's settings** (live complaint, the same
day: "I connected @vexonai and it does not answer"). Reconnecting to another bot brings a
**new `conn_id`**, settings were keyed by the old one, so the new row opened in `buyruq`
mode — commands only, customers get silence — while the dead old row stayed `yoqilgan`
(its disconnect update went to the old bot) and `/biznes` could pick it. Telegram allows one
bot per account, so `_saqla()` → `database.biznes_telegram_almashdi()` copies the settings
from the owner's other enabled Telegram connection, disables it and moves `kutmoqda`
drafts, in one transaction; `ig:` is never touched. `biznes_almashuvni_tuzat()` runs once at
startup for owners who connected before the fix. SQL verified on a local Postgres;
`tests/test_biznes_almashuv.py`.

**The panel's «Ko'chish» card is temporary.** `database.kochish_stats()` counts who moved
by `users.last_seen >= KOCHISH_VAQTI` — only the new bot writes to the database, so that is
exact — and owners by the `yangilangan` of their enabled Telegram connection. "Not moved"
cannot separate "wrote to the old bot and stayed" from "silent"; the old bot writes nothing.
`/api/overview` returns `kochish` only while `ESKI_BOT_TOKEN` is set, so removing the token
hides the card with no cleanup step (`test_web_stats.py` 15). Delete the card,
`kochish_stats()` and `KOCHISH_VAQTI` together once the old bot is switched off.

**`/eski_xabar` (admin, 2026-10-28) — one announcement from the old bot to everyone who has
not moved.** The new bot cannot write to someone who never pressed its `/start`; the old
one can. Recipients come from `database.eski_tarqatma_oluvchilar()` — the **same**
definition as the card's «qolgan», plus owners whose Business is still on the old bot even
if they already write to the new one (their customers get silence). The text is fixed
(`eski_bot._elon()`, owner variant adds the reconnect path) and sent as a logo caption,
so it must stay under 1 024 visible characters (`test_eski_bot.py` 9). The command first
sends both variants to the admin **through the old bot**, then asks for confirmation; the
send is ~20/s, honours 429 and counts blocked users without stopping (checks 10-11). The
module still touches no database — the list is passed in. Delete the command, its callback,
the menu row and the `eski_tarqatma` audit label (→ `AUDIT_ESKI`) with the card.

What did **not** move, because Telegram ties it to the bot: Business connections (each
owner reconnects), Stars from old payments (refunds only work from the old bot — the panel's
refund fails safely, Telegram first), private-chat topics, and the right to message a user
who has not pressed /start on the new bot. The logo emoji set is per bot
(`holat4_by_vexonai` is created on first start); `web/static/logo.jpg` and
`assets/vexon_logo.jpg` are the new logo.

**The 16 status animations are generated, not hand-made:** `python assets/status_yasash.py
[tur…]` draws each from `assets/vexon_v.png` (the «V» cut out of the logo) and fits it under
64 KB by raising `crf`. The previous scripts lived in a scratchpad and were lost, which is
why the logo change meant redrawing everything — edit this file instead. Every type's
`_LOGO_BELGI` emoji changed on 2026-10-25 so the startup `replaceStickerInSet` swaps all 16;
change a type's emoji again whenever its animation changes, and pick emoji that need no
U+FE0F.
