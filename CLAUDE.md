# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Language

**All code comments, docstrings, commit messages and user-facing strings are in Uzbek (Latin script).** Match that — a comment or bot reply in English reads as foreign here. Comments explain *why*, especially the non-obvious constraints listed below; several of them are load-bearing and were paid for with real bugs.

## Commands

```bash
python main.py                      # botni ishga tushirish (polling)
python tests/test_memory.py         # bitta testni ishga tushirish
python services/sandbox.py          # sandbox izolyatsiyasini tekshirish
python services/sandbox_helpers/deck.py   # PPTX maketlarini tekshirish
python tests/test_tts_lang.py --live  # jonli TTS sintezi bilan
```

No test framework, no linter, no build step. Each `tests/test_*.py` is a standalone `assert`-based script with numbered `print("[N] ... OK")` lines and a final summary. New tests follow that shape. On Windows, prefix with `PYTHONIOENCODING=utf-8` — some tests print emoji and the console codepage will otherwise raise `UnicodeEncodeError` (a false failure, not a real one).

Run the whole suite by looping over `tests/test_*.py`; `test_pro_security.py` is the slow one.

Some are structural guards rather than feature tests, and they earn their keep on refactors:

- `test_admin_registry.py` — every admin handler still registered, in order.
- `test_activity_tracking.py` — reads handler source **by file path**, so moving code breaks it.
- `test_prompt_rules.py` — 60 individual prompt rules still present in the assembled `instructions`. Run it **before and after** any prompt edit; identical results are what make a prompt change safe to ship.
- `test_nearby.py` — the untrusted-boundary guard on `find_nearby`: a model-written category must never reach the Overpass query intact, and "the source failed" must never be reported as "nothing nearby". Runs offline.
- `test_image_edit.py` — `edit_image`'s three silent failure modes: the dispatch branch sitting above the bare `else`, the source bytes staying out of the tool schema, and the two API arguments (`size="auto"`, `input_fidelity="high"`) that only degrade the picture rather than raising. Runs offline.
- `test_file_intent.py` / `test_emoji_pack.py` / `test_image_pick.py` — the three places where a config number silently changes behaviour (which tool schema is attached, which emoji map is live, how many photos come back). `test_image_pick.py` also pins the picker model to a tile-based one; a patch-based model there costs 23x per image.
- `test_admin_extras.py` checks 19-20 — every admin callback handler still starts with `require_admin_or_deny_query`, and the two user counts in `handle_users_command` still filter the same set. Both were written after the corresponding bug, and check 19 was verified by deleting the guard and watching it fail.

Exact token counts need `tiktoken` (`pip install tiktoken`, encoding `o200k_base`). It is **not** in `requirements.txt` — the bot never counts tokens itself, it is a local measuring tool. Do not estimate from character counts; that was 11% off on this prompt.

## Deploy

**`git push meloress main` deploys.** The Railway service is connected to GitHub, so a push to `git@github.com:meloress/1.git` (remote `meloress`) triggers the build by itself — no API call, no token. `origin` still points at `afiffamily/1`, where this account has **no write access** (403), so never push there.

Both the account and the remote moved on 2026-09-08; the GraphQL path below is history, kept only in case the GitHub connection is removed again.

- Without a GitHub connection, `git push` does *not* deploy and a plain deploy call rebuilds the snapshot taken when the service was created, i.e. old code. Deploys then have to name the commit explicitly:
  `serviceInstanceDeployV2(serviceId, environmentId, commitSha)` against `https://backboard.railway.com/graphql/v2` with a team token (`Authorization: Bearer`, and a real `User-Agent` — Cloudflare answers `403 error code: 1010` to the default urllib one). Railway fetches the commit from the repo, so **the service must point at the repo that actually has that commit, and it must be public**. The `up` endpoint (local tarball upload) fails on this account.
- Never ask for a token in chat. Have the user put it in `RAILWAY_TOKEN` and read it from the environment without echoing it.

### Reading production logs

The user is logged into the Railway CLI on this machine (`~/.railway/config.json`), so
logs are readable directly — no token, no copy-paste:

```bash
railway status
timeout 45 railway logs      # streams, never exits on its own — the timeout is required
timeout 60 railway logs -b   # build logs
```

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
- service **`1`** (this bot, `@uzchatgptaibot`) `d644a705-d075-440b-a68d-9fd21dcbd44b`
- the same project also runs `Melores-Bot`, `Hisobotchi-bot`, `Trello-bot`, `Web-panel`
  and several Postgres instances — ours is the one named `1`

**Which commit is live** comes from `deployments(input: {projectId, environmentId,
serviceId})` → `node.meta.commitHash` / `commitMessage` / `createdAt` (UTC; Tashkent is
UTC+5). Use it before concluding anything from a screenshot — a table complaint was
nearly misdiagnosed because it was unclear whether the fix had deployed yet.

The logs are the best source of work. Both of the largest problems found on 2026-09-10
came from reading them, not from guessing: the image picker burning 47 843 tokens on one
request, and a silent `asyncio.TimeoutError` (whose `str()` is empty) making the picker
fall back to unseen candidates.

### Token budget

The bot runs on a free daily grant (2.5M tokens/day for `gpt-5.6-luna`). Before the September 2026 work the OpenAI usage dashboard showed **20.307M input tokens over 8 days — 2.54M/day, i.e. 101% of the grant on an average day and 248% on the busiest one**, so the model was silently falling through `MODEL_FALLBACKS` and the excess was billable.

⚠️ **Caching does not reduce that count.** OpenAI support confirmed (2026-09-09) the complimentary allowance is a *token quota*, not a discounted rate: cached and uncached input count the same. Caching only changes money, which matters once you exceed the grant. So the only lever is fewer tokens per round.

Nearly all of it is fixed overhead, not user text. Measured with `tiktoken` (`o200k_base`) — never estimate from character counts, that was 11% off:

| | tokens |
|---|---|
| `instructions` (prompt + concise + image note) | 5 521 |
| tool schemas (Pro, all three doors closed) | 2 253 |
| capability manifest | 319 |
| **fixed total per round** | **8 093** |
| history | 0 → ~8 200 |
| median user message | ~10 |
| median reply | ~70 |

Those first three are what a round costs before the user has said anything. The Railway
log confirms it: sampled `[TOKEN]` lines run 7 697 (a free user, no `generate_image` or
`open_reminder`) to 16 304, and the whole spread is history — 3 of 10 sampled requests
carried ~8 000 tokens of it. **There is no hidden waste left.** History is the full reply
text, i.e. real context; trimming it is a quality decision, not a cleanup. Round 1
usually shows `keshdan 0 = 0%` and round 2 shows 90%+, which changes latency and money
but not the quota.

The input:output ratio is about 100:1, so `max_tokens` and stop sequences save nothing — output is already tiny. And a searched request runs **~1.7 rounds**, each re-sending the whole prefix, so every token removed from the prefix is saved that many times over.

`_log_token_usage()` in `services/ai.py` prints `[TOKEN] … kirish=… (keshdan … = NN%)` for every round; the cached share is visible in the Railway log even though it does not reduce the quota.

Measure before optimising. The bot's own Postgres answers most questions — how many requests a day, how long replies are, how often a tool actually fires. Two guesses were wrong that way: model routing looked like a big win until `pick_reasoning_effort` turned out to classify only 3-4% of real messages as trivial (and length is a terrible proxy: "Manga Toshkent … kontrakt narxlarini ber" is 66 characters and needs a full web search), and trimming fetched page text looked worth 10% until a live search measured 1 877 tokens, not 4 000.

The cached prefix is **instructions + the tool schemas**, and OpenAI documents *changing the tools available mid-conversation* as a cache-miss cause. Two consequences. `prompt_cache_key` is set in `build_request_params()` per **plan**, never per user — the prefix is identical for everyone on a plan, and a per-user key would have ten active users each warming a private cache. And the tool loop rebuilds `active_tools` every round, dropping tools whose budget is spent, so rounds 2 and 3 of a searched request send a different prefix and start cold. Making the array stable would fix that, but the drop is also what forces the model to stop calling a spent tool, and one wasted round re-sends the whole context (~12k tokens) while the cache would only save part of it — so measure the `keshdan` percentage on multi-round requests before touching it.

`PROMPT_CACHE_RETENTION = "24h"` exists in `core/config.py` and is deliberately off: it fits a day-precision prefix perfectly, but cache **writes** cost more and OpenAI does not document how the complimentary daily grant counts them.

## Architecture

`BOT_API_103.md` is the long-form companion to this file: everything added with Bot API 10.3 and after, explained in full — including the decisions that were **tried and reverted** (the interim "preparing your file" message, the sources slide). Read it before re-attempting anything in that area; this file only carries the rules.

### Handler registration order is a safety constraint

`main.py` registers handlers in a deliberate order and each position is justified in a comment. The critical ones:

1. `successful_payment` / `pre_checkout_query` go on `dp.message` **directly**, before any router. `handlers/messages.py` has a `GeneratingState.generating` spam-guard with no content filter; if a payment lands while a reply is streaming, that guard would swallow it — money taken, Pro not granted.
2. FSM states (gift, promo, digest, broadcast) come before the AI handlers so a user's answer to "kimga sovg'a qilay?" is not sent to GPT as a question.
3. `maintenance_gate` sits before the AI handlers but after `/start` and `/profile`; `/pro`, `/promo`, `/gift` sit *after* it — selling a subscription for a disabled bot is a refund source.
4. `generating_state_router` is included before `general_router` so a message arriving mid-reply does not start a second parallel request.

Do not reorder these without reading the comments.

### The stop button needs two things aiogram won't do for you

`sendRichMessageDraft(can_stop=True)` makes Telegram send a `stopped_message_generation` update. aiogram 3.31.0 knows that type, so `main.py` registers a plain `@dp.stopped_message_generation()` observer that maps `event.draft_id` → `handlers.messages.request_stop()`. Registration order does not matter — the observer does not touch the `dp.message` chain.

`allowed_updates` therefore needs no manual patching: `dp.resolve_used_update_types()` finds the type from that handler. Both workarounds this used to need (an `outer_middleware` catching the update before `event_type` resolved it, and appending the type by hand) were removed with the 3.29 → 3.31 upgrade; `tests/test_bot_api_103.py` check 39 guards that the resolver really lists it.

⚠️ 3.31 turned the 10.3 fields `InlineKeyboardButton.disabled` and `InlineKeyboardMarkup.force_reply` into **real model fields** — they used to live in `model_extra`. Anything reading them must check both, `pro._downgrade_kb()` included: reading only `model_extra` there dropped `disabled` from the fallback keyboard, producing a typeless button that gets the whole message rejected.

Drafts are private-chat-only (API limit); `sendRichMessage` is not. `process_stream_draft` keeps those two as separate flags (`using_rich_draft` vs `can_send_rich`) — merging them again would strip tables, collapsed sources and images from every group answer.

### The tool loop (`services/ai.py`)

`get_openai_reply()` streams from the Responses API and runs a tool loop with **per-tool round budgets** (`MAX_SEARCH_ROUNDS`, `MAX_FILE_ROUNDS`, `MAX_IMAGE_ROUNDS`, `MAX_MEMORY_ROUNDS`, `MAX_REMINDER_ROUNDS`, `MAX_NEARBY_ROUNDS`, plus `MAX_TOTAL_ROUNDS`). When a budget is spent the tool is dropped from `active_tools`, forcing the model to answer.

Tools: `internet_search`, `run_python_sandbox`, `generate_image`, `edit_image`, `update_memory`, `manage_reminder`, `find_nearby`. Three of them are reached through a cheap door (`start_file_task`, `open_memory`, `open_reminder`) — see below.

**Three tools are attached in two steps, and that is a token decision.** A cheap
"door" is always attached; the expensive real schema arrives only on the round after the
model opens it. `start_file_task` 212 → `run_python_sandbox` 5 578; `open_memory` 248 →
`update_memory` 764; `open_reminder` 212 → `manage_reminder` 772. Measured with
`tiktoken`. The door costs one extra round on the small fraction of requests that use the
tool, and saves the difference on every round of every other request — memory was used in
13 of 1 210 measured requests and the reminder tool in **none**, while `update_memory`
was attached to every DM request and `manage_reminder` to every Pro one. Opening a door
does **not** consume that tool's round budget (`memory_rounds` increments only on the
real call), or opening it would eat the budget the actual write needs. Each door needs
its own `elif` above the bare `else`, and `_capability_manifest()` must name the *door*,
never the tool behind it.

**The file tool's own numbers.** `run_python_sandbox`'s description is the whole layout manual — **5 578 tokens** measured with `tiktoken` — and the model writes the code *inside* the call, so the manual cannot move out of the schema. But `file_task_enabled` is `output_files is not None`, i.e. every DM request, while the tool is actually called in 1.4% of them (17 of 1 210 measured). So a **212-token** `start_file_task` door is attached instead; when the model calls it, `file_mode` turns on and the full tool arrives on the next round. That saves **5 366 tokens per round** — and a round is re-sent in full each loop iteration, so the real saving is that times the round count. The cost is one extra round on the 1.4%. `file_mode` stays on for the rest of the request because the file loop retries up to four times. Two things must hold: `start_file_task` needs its own `elif` above the bare `else` (otherwise "make me a presentation" becomes a DuckDuckGo query), and `_capability_manifest()` must name the tool that is *actually attached* — naming `run_python_sandbox` there would have the model call a tool it does not have.

**Dispatch order matters**: the `else` branch routes any unknown tool name to web search, so every named tool must be an `elif` *above* it — otherwise "menga rasm chiz" silently becomes a DuckDuckGo query.

**A tool that quietly returns nothing is how the context explodes.** Images are searched once per request — re-running would shift catalogue numbers under a `[rasm:2]` the model has already written — but the repeat call still re-emits the same catalogue. Returning silence taught the model "no images found", so it searched again, and again; each round appends full page text, and by round three the request hit OpenAI's 200k TPM ceiling and the whole answer was lost after 50 seconds of work. Any budget that drops a tool must say so in the tool output.

`RateLimitError` arrives **mid-stream**, not when the stream opens: the SDK sends the request on the first iteration, so `_open_response_stream()`'s fallback ladder never sees a 429 and the answer died outright. The round is retried once after `RATE_LIMIT_RETRY_DELAY` — but only if no text has been yielded yet, otherwise the user would see the start of the answer twice.

**Pro gating is done by omission**: `image_enabled = ... and is_pro`, `reminder_enabled = is_pro and user_id is not None`. Free users never see the schema, so no tokens are spent advertising a tool they cannot use. Flipping a feature to free-with-upsell means removing `is_pro` from that condition; the task functions already validate independently.

`get_vision_reply()` is a **separate, single-round** path — the memory tool call is harvested after the stream and its result is not fed back. Adding a full loop there means porting the `pending_calls` block.

`[CLEAR_TEXT]` travels through the same chunk stream as content and is emitted **after every** tool round, throwing away the model's pre-tool chatter so it doesn't stick to the final answer. The condition used to exclude repeat searches, and the leftover text then glued itself to the next round's — users saw two "…tayyorlayapman" sentences in one message. Reaching that point already means a tool ran (`if not got_function_call: return` above it), so no condition is needed.

While a file is being built the screen shows **only the status animation** — nothing the model wrote before the tool call reaches the user. Sending that preamble as an interim message was tried and reverted: it left a half-drawn draft bubble next to the real one, and the abandoned draft killed the spinner for the whole 1-2 minute wait. If you try it again, the draft must be overwritten or closed before a real message is sent, not simply replaced with a new `draft_id`.

### Photos: two separate pipelines that must not be confused

A photo in a **chat reply** and a photo **inside a document** share nothing but the search call, and mixing them up is the failure mode users actually hit.

- **In chat**: `internet_search(want_images=true)` searches, validates each URL is live, and stores the hits in `images_out`. `images_only=true` is the same path with the web search skipped entirely — it exists because a picture used to be possible only when the model happened to search, so any answer written from the model's own knowledge arrived with no image at all. It still spends a `search_rounds` slot (otherwise the model can ask for pictures forever), it implies `want_images` in code because the model forgets one of the two, and it never injects `_SYNTHESIS_SYSTEM` — that prompt demands a sources list, and an images-only call has no sources. The URL is deliberately **never shown to the model** — it costs 30-60 tokens each and the model rewrites them into dead links. The model only sees `[rasm:1]` / `[rasmlar]` tokens (~25 tokens total); `embed_images()` swaps them for real media blocks just before sending — one image as a bare block, 2 to `SEARCH_IMAGE_COLLAGE_MAX` (4) as a `<tg-collage>` (all on one screen), 5 to `SEARCH_IMAGE_MAX` (10) as a `<tg-slideshow>` — how many are fetched comes from the model's `image_count`, so "10 ta rasm topib ber" works and the slideshow branch is finally reachable. A collage carries a single caption, so its inner blocks are built without one and every source goes into one `<figcaption>`: the photo is someone else's and the credit is not optional, and `strip_image_tokens()` scrubs them from every fallback path and from the streaming draft. Telegram fetches the URL itself — nothing is downloaded.
- **In a document**: see the Sandbox section. Bytes, not URLs.

The routing between them is prompt-level and fragile: adding the word "rasm" to the file tool's description was enough to make *every* request ("olma haqida ma'lumot ber") turn into a file task. Both tool descriptions now carry an explicit ⛔️ pointing at the other one, and `IMAGE_CAPABILITY_NOTE` in the system prompt exists because the model would otherwise answer "I can't send pictures" without calling any tool at all. That note is added **only** in `get_openai_reply` — `get_vision_reply` has no search tool, so promising it there would be a lie.

**The model picks the photos by looking at them.** `search_images()` gathers ~20 candidates, checks they are live, and then hands the thumbnails to `SEARCH_IMAGE_PICK_MODEL` (`gpt-4.1`, `detail: "low"` = 82 tokens each) in **one** call together with the user's actual request; the picker returns the indices it wants plus a short Uzbek description of each. That description is what makes "what colour is the car in the first photo" answerable, and it is deliberately written from the image, not from the request. The picker runs on a **different model from the main answer**; if it fails for any reason the first N candidates are used, i.e. the old behaviour, so a picture is never lost. An empty pick is a valid answer — an unrelated photo is worse than none.

⛔️ **The picker model must be tile-based, and that is a 23x decision.** `detail: "low"`
is honoured only by tile-based models (gpt-4o, gpt-4.1, gpt-5, gpt-5.1), where it means
~85 tokens regardless of image size. Patch-based models (gpt-4.1-mini, -nano, o4-mini)
**ignore `detail` entirely** and bill 32×32 patches times a multiplier. This was live:
with `gpt-4.1-mini` a single image request logged **47 843 input tokens** (22 candidates,
~2 175 each) and a 34-candidate request blew through `SEARCH_IMAGE_PICK_TIMEOUT` and fell
back to the unseen first-N. Measured on one live URL at `detail: "low"` (2026-09-10):

| model | tokens/image |
|---|---|
| gpt-4.1 | **82** |
| gpt-5-mini / gpt-5.4-mini | 1 390 |
| gpt-4.1-mini | 1 878 |
| gpt-4o-mini | 2 830 |

`tests/test_image_pick.py` checks 31-33 guard the model choice, its presence in the free
list, and the candidate count times the per-image cost. Note also that
`asyncio.TimeoutError` has an **empty** `str()`, so the failure log used to end in a
colon and say nothing; it now falls back to the exception class name and prints the
candidate count.

**Commons and `ddgs` are both queried and merged**, Commons first. It used to be Commons with `ddgs` as a fallback, and that is what produced the worst live bug: Commons is a free-licence encyclopedia archive with no tuning photos, so "BMW 540i tuning body kit" returned nothing, `_images_sync()` shortened the query until Commons *did* answer, and the user got the plain "BMW 540i" shots back — the same four, every time, however they refined the request. The fallback never ran because Commons always answered something. On the server DuckDuckGo's image endpoint answers `403` (datacenter IP) and `ddgs` silently switches to Bing, whose results can be unrelated ("Hongqi H5 Classic" once returned Roblox avatars) — that is now the picker's job to reject, not a filter's.

Query shortening is the **last resort**, not the first: only when *both* sources come back empty does `_images_sync()` walk the query down to 3 words, then to 2. Both steps are needed — "Hongqi H5 new model" trimmed to 3 is still "Hongqi H5 new", which also returns nothing. `_title_stem()` collapses "BMW 540i (G30) China", "… (2)", "… (3)" into one candidate: they are frames of a single shoot with different URLs, so URL dedupe alone handed the user one picture four times. URLs already sent in this chat (`core/memory.py::recent_sent_images`, cleared by `/new`) are dropped too — a repeat request must return something new or say so honestly. And `upload.wikimedia.org` is in `_TRUSTED_IMAGE_HOSTS`, so its URLs skip the liveness probe entirely: the API already guarantees they exist, while ten parallel probes earn a `429` that made live images look dead (10 candidates collapsed to 1).

The query itself is separated too. A web query is written for articles (`site:`, long phrases, figures) and is useless against an image index, so `internet_search` takes an optional short English `image_query`, and `image_query()` strips operators and bare numbers from the fallback — but **not four-digit years**: "Hongqi H5 2025" and "Hongqi H5" are different cars, and dropping the year is how a request for the new model kept returning the same old photo. `_image_relevant()` then requires one meaningful query word in the title/URL/source — when nothing matches, **no image is sent at all**, because an unrelated photo on a slide is worse than an empty one.

`[rasm:N]` is valid **only inside the reply that produced the catalogue**, so `safe_update_history()` rewrites it through `image_tokens_to_history()` before anything reaches `chat_messages` — the token becomes `[yuborilgan rasm: <description>]`. A raw token left in history reads to the model as still-live: on "rasm yubor" it would re-emit `[rasm:1]` instead of calling the tool, `embed_images()` would silently drop it, and the user got an empty answer. Deleting it outright was the other extreme — the model then had no idea what it had sent. Keeping the description costs ~15 tokens per image and is what lets it answer questions about a photo it already sent. Both the catalogue text and `IMAGE_CAPABILITY_NOTE` say outright that a link never substitutes for a picture and that every repeat request needs its own search.

Image search runs with `safesearch="on"` (`SEARCH_IMAGE_SAFESEARCH`); the library default `moderate` was not enough for a bot with no age gate.

### A failed send is not the same as a rejected send

`_telegram_api_request` reports *why* a call failed through an `outcome` out-param: `OUTCOME_REJECTED` (Telegram answered `ok:false`) versus `OUTCOME_UNKNOWN` (timeout, connection reset). The rich-message fallback ladder retries in a plainer form **only** on REJECTED. On UNKNOWN it gives up silently, because the message may well have arrived.

This exists because the shared aiohttp session caps every call at 10s — right for the 0.6s draft pings it was tuned for, wrong for a rich message carrying image URLs, since Telegram fetches each image from the source site before it creates the message. The client timed out, the ladder concluded "rejected", re-sent without images, and Telegram delivered both: users saw the same answer twice, once with photos and once without. Media sends now get `RICH_MEDIA_TIMEOUT` instead.

### Splitting a long answer must not cut a construct in half

`_split_for_telegram()` breaks answers at a limit that depends on the send path — `MAX_RICH_CHARS` (30000, rich messages cap at 32768) or `MAX_PLAIN_CHARS` (4000, `sendMessage` caps at 4096) — and the cut point lands wherever the last newline or space happens to be. Three constructs cannot survive that cut and are handled explicitly: an open code fence is closed and reopened with its language on the next part, and `_safe_cut()` moves the boundary *before* a markdown link and *before* a footnote pair. Splitting `[OLX Uzbekistan](https://…)` in the middle leaves both halves as literal text — that is how a sources list once reached a user as `• [OLX` followed by `Uzbekistan](https://…)`. A footnote is the same shape with its halves far apart — `[^1]` sits in the text, `[^1]: …` at the very end — so `_safe_cut()` takes the whole remaining text, not `rest[:limit]`, or the definition beyond the limit would be invisible to it. Anything else added to answers with paired syntax needs the same treatment. `==marked==`, `<sub>`/`<sup>` and `- [ ]` need no code at all: Telegram renders them and `build_rich_markdown()` passes them through untouched — they are prompt rules only.

A collapsible section is the one construct the model does not write itself: it writes `[batafsil: Title] … [/batafsil]` and `build_rich_markdown()` turns the pair into `<details>`, inside `_protect_spans()` so a marker in a code block stays text. Same reason as `[rasm:N]` — a malformed marker is dropped, malformed HTML gets the whole message rejected. An unpaired marker is therefore discarded, and a nested one is flattened. A pull quote works the same way: `[iqtibos: the words | who said them]` becomes `<aside>…<cite>…</cite></aside>`, the author half optional. Markdown is not parsed inside `<aside>` (only `<details>`, `<tg-collage>` and `<tg-slideshow>` parse it), so both halves are html-escaped there — unlike a `<details>` body, which stays markdown. The draft and the plain fallback are not rich, so `strip_rich_tokens()` renders both markers as plain text there (bold heading, «quoted» line); it sits beside `strip_image_tokens()` at the same two call sites.

A part cut to the rich size cannot be handed to the plain fallback as-is: when a rich message is rejected, the part is re-split with `MAX_PLAIN_CHARS` before `_answer_plain()`. Skipping that loses the whole answer — worse than the small limit it replaced. `push_update()` likewise trims the draft (rich) and the plain waiting message to different limits, since the draft can degrade to the latter mid-stream.

### A code fence in the `markdown` field breaks Telegram Web

Telegram turns ` ``` ` in a rich message's `markdown` field into the new **copyable code block** content type, which Web-K reports as `messageMediaUnsupported` — the reader sees "This message is not supported on Telegram Web" *instead of the whole answer*. Mobile and desktop render it fine, so this only shows up on the web client. `code_fences_to_html()` (`services/ai.py`) rewrites every fence to `<pre><code class="language-…">`, which is plain text plus `MessageEntityPre` and renders everywhere. It is called from `_protect_spans()` (so the later table/date/emoji passes never see the code), from the streaming draft, and from the two guest rich payloads — but **not** on the plain `text` fallback, which goes out with `parse_mode="Markdown"` and needs the fence intact.

Code longer than `LONG_CODE_LINES` (30) leaves the message entirely: `_extract_long_code()` pulls it out, `_send_output_files()` sends it as `kod_1.py`, and the text keeps a one-line note. The **original** text with the code still goes to history (`history_text`), otherwise "now change that code" would have nothing to work with.

### One request per user, and messages queue instead of vanishing

Telegram splits a message over 4096 chars into several updates, so every incoming text goes through the debounce buffer in `core/memory.py` (`text_merge_buffers`, per-chat `asyncio.Lock`) and is merged after `TEXT_MERGE_WAIT` (1.5s) — joined with `"\n"`, since the parts may equally be separate messages. The old "short first message goes through instantly" shortcut was removed: it turned three quick messages into three independent requests, the first of which then locked out the other two.

While a reply is generating, `busy_handler` (`GeneratingState.generating`) **appends to that same buffer** and `_process_merged_text`'s `finally` block starts it once the state is cleared — order matters, or the queued message re-enters the busy state and loops. Commands and media keep the old "please wait" behaviour: a queued `/pro` would be sent to GPT as a question. `TEXT_MERGE_BUFFER_TTL` is 600s because the buffer now has to survive a whole generation, not just a 1.5s timer.

`_next_or_stop()` enforces `STREAM_IDLE_TIMEOUT` (180s) — an **idle** limit, not a total one. A file task or a deep research legitimately goes minutes without emitting a chunk, and a total budget would kill exactly the work that needs it. On timeout a partial answer is still delivered (with a note); with nothing at all it raises, and the caller's existing `except` gives the user a clean error plus the retry button and refunds the points.

### Live streaming: what a rejected draft means

`push_update()` writes the accumulating answer to a `sendRichMessageDraft`, throttled to `PUSH_INTERVAL` (1.0s) **and** `PUSH_MIN_CHARS` (100) — with the first chunk forced through, because the wait is felt at the start. Editing per chunk earns a 429 and freezes the stream.

A failed draft ping is **not** proof the draft is unusable. `rich_draft_ok` records whether any draft (animation frame or content push) ever succeeded: if one has, a rejection is treated as a temporary flood-wait and retried (`RICH_DRAFT_FAILURE_LIMIT`); if none ever has, the path is abandoned immediately so the user gets the plain waiting message without delay. `_edit_message_fallback()` handles `TelegramRetryAfter` itself instead of swallowing it with every other exception.

The status animation is **restarted** when a `[STATUS]` chunk arrives after text has already streamed — the model often writes "let me search…" first, which stops the animator, and the screen then sat frozen on stale text for the 20-60s the tool ran. `/research` has its own eight-stage status list; `[STATUS]search` from inside it must not overwrite it.

### The model must not name its own tools

The system prompt has a `CONFIDENTIAL` section, but a prompt rule is not a guarantee — in a live test the bot correctly refused to print the system prompt and then listed `internet_search`, `run_python_sandbox`, … anyway. `strip_internal_names()` (`services/ai.py`) is the second layer: it replaces the real names from `INTERNAL_TOOL_NAMES` (`core/config.py`, the single list) with neutral Uzbek descriptions, on the final text, on the streaming draft, and in the guest path. It deliberately scrubs code blocks too — "list your tools as a python list" is exactly the way around it. `tests/test_no_tool_leak.py` asserts the list matches the actual tool schemas, so a new tool fails the test until it is added.

The prompt also carries a phishing/social-engineering section that fixes the *shape* of the answer (fake placeholders, a visible simulation label, red flags instead of a ready-to-send message) while explicitly forbidding over-refusal of ordinary security questions. `tests/test_safety_prompt.py` only guards that the section still exists — the wording is not asserted.

### The prompt is sent whole on every round, so duplication is expensive

The free daily grant counts tokens, not requests, and caching does not reduce that count (OpenAI support, 2026-09-09) — so anything in `instructions` is paid for on **every round of every request**, and a searched request runs ~1.7 rounds. Measured with `tiktoken` (`o200k_base`), not estimated: instructions 5 521 tokens, tool schemas 2 253, capability manifest 319.

`STRICT_MATH_RULES` used to be appended after the whole prompt and was a near-verbatim copy of the template's own `MATH, PHYSICS & CHEMISTRY` section — nine rules stated twice, side by side in one string, 274 tokens per round. It is gone; the two phrases that were unique to it ("This is a hard requirement", "There are no other acceptable delimiters") were folded into the section that remains. `CONCISE_INSTRUCTION` likewise lost the three sentences that repeated `OUTPUT CONTRACT` rule 4.

`tests/test_prompt_rules.py` is the guard: it asserts 60 individual rules are still present in the assembled `instructions`, whichever section they live in. Run it before and after any prompt edit — it was written *before* the deduplication and passed identically after, which is what made the change safe to ship. A mechanical cross-block similarity scan found no other duplication above 60%, so there is no more fat of this kind; further shrinking means rewriting prose, which is a quality decision, not a cleanup.

⚠️ The scan cannot see across languages: the tool descriptions are Uzbek and the prompt is English, so `IMAGE_CAPABILITY_NOTE` overlaps `internet_search`'s `want_images` / `images_only` descriptions without any lexical match. That overlap is deliberate and bug-paid (the model used to answer "I can't send pictures" without calling anything) — do not "deduplicate" it.

### Prompt caching constrains where text goes

`build_system_prompt()` is written to day precision so the prefix is identical all day and prompt caching works. Anything per-user (long-term memory, the user's name) goes into `messages` as a `developer` message, **never** into `instructions`. Putting user-specific text in the system prompt silently destroys the cache for everyone.

### Model list is a billing guard

`INTERNAL_TOOL_NAMES` (`core/config.py`) must list **every** tool name, doors included —
`strip_internal_names()` scrubs exactly those strings, so a name missing from it leaks.
`tests/test_no_tool_leak.py` used to compare against a hand-written tuple of schemas and
silently rotted: `start_file_task`, `find_nearby`, `open_memory` and `open_reminder` were
all missing from the list and the test still passed. It now walks the `services.ai`
module for every `{"type": "function"}` dict, so a new tool fails it until it is added.

`GPT_MODEL` and `MODEL_FALLBACKS` must stay inside OpenAI's free data-sharing list. A model outside it bills at full price and nothing warns you — the bill arrives at month end. `tests/test_free_models.py` guards this.

### Quotas: two independent systems

- **Points** (`check_and_consume_quota`) — the daily budget; cost varies by message kind and reasoning effort (`message_cost()`).
- **Daily counters** (`DAILY_COUNTERS` → `check_and_consume_daily`) — separate counts for `files`, `images`, `research`. These are the expensive operations; billing them to the points budget meant three files exhausted a user's whole day and read as "the bot broke".

`services/file_task_quota.py::DailyQuota` charges **once** per user request no matter how many times the model calls the tool, and refunds if nothing was produced.

`unlimited=True` means "nothing was deducted, do not refund" (admin/premium). Returning it for Pro would break every refund guard — `tests/test_plan_limits.py` asserts this.

Adding a new counter = one row in `DAILY_COUNTERS` + two DB columns. Nothing else.

`daily_limit()` in `core/config.py` is the **single read point** for every limit — quota code, the file/image/research counters and the admin screen all go through it. That is why the admin-editable limits sit there as an in-memory `_LIMIT_OVERRIDES` dict rather than a DB read: `daily_limit()` runs on every message. `bot_settings.limit_overrides` (JSONB) is loaded once at startup via `apply_limit_overrides()` and refreshed when an admin changes a value; `NULL`/missing means "use `PLAN_LIMITS`", so an unconfigured bot behaves exactly as before and needs no migration. Anything that reads `PLAN_LIMITS` directly bypasses the override and will silently disagree with the panel.

### Model output is an untrusted boundary

Whatever the model writes into a tool call reaches the database. Validation lives in `db/database.py`, never in the tool `description` — an instruction is not a guarantee:

- `clean_memory()` strips newlines (a multi-line memory renders as fake instructions in the developer message) and rejects card/passport/account number patterns.
- `parse_run_at()` rejects past times, unparseable strings and dates beyond `REMINDER_MAX_AHEAD_DAYS`.
- Every `UPDATE`/`DELETE` driven by a model-supplied index carries `AND user_id = $N`; the index is bounds-checked against the list actually shown to the model *before* touching the DB (note `isinstance(idx, bool)` — `True` is an `int` in Python).

### Two kinds of memory

- **Conversation history** (`db/history.py`, `chat_messages` table + RAM cache) — context. Stored to `CONTEXT_WINDOW_PRO` for everyone; the tariff only changes how many are *read* (free 30, Pro 80 — they were 50/150 and were cut for token cost), so switching plans needs no migration. `/new` clears this.
- **Long-term memory** (`user_memories`) — facts the model chose to keep, category-prefixed (`ism:`, `kasb:`, …). Survives `/new`. Available on every tariff.

History used to live in SQLite; Railway wipes the container filesystem on every deploy, so each deploy reset every user's context. It is Postgres now — do not move it back to a file.

### Inline mode must stay OFF — it breaks guest mode

⛔️ Do not enable `/setinline` in @BotFather, and do not "helpfully" suggest it.
A live test (2026-09-10) settled this: with inline on, Telegram treats
`@bot savol` in a chat as an **inline query**, the send button disappears, the
client spins and ends with an "x", and the message never arrives as
`guest_message` at all. Guest mode simply stops working.

`handle_inline_share` used to carry the opposite claim — that the two update
types "live side by side and neither replaces the other" — and its trick of
answering a non-empty query with an empty result list does **not** rescue it:
no results means the text cannot be sent as an ordinary message either. The
handler stays registered, but only for a future in which this changes.

So the choice is a prettier share button *or* guest mode, and guest mode wins by
a wide margin. With inline off, `_share_button()` falls back to a
`t.me/share/url` link — the message goes as flat text without a button, which is
a cosmetic loss, not a broken feature. The startup check is now inverted: it
warns when inline is **enabled**, since that is the broken state.

### Guest mode

⚠️ **The final answer goes through `build_rich_markdown()`, the status animation does
not.** `_edit_guest_inline_message(..., rich=True)` is the switch. It used to call only
`code_fences_to_html()`, so a group answer lost tables, `<details>`, pull quotes, maps,
buttons, collapsed sources and premium emoji — and, worse, the markers the model writes
anyway (`[batafsil: …]`, `[xarita:…]`) reached the reader as raw text. The plain-`text`
fallback rung takes `strip_rich_tokens()` for the same reason: the marker disappears, the
information stays. Status frames stay on the cheap path — they are re-sent every 4s and
every extra decoration only raises the chance of a rejection that would cost the
animation.

Guest also uses `speech_to_text_smart` / `text_to_speech_smart`, so a Pro user gets the
natural voice in a group instead of the free edge-tts one.

**Photos work in guest too.** `images_out` used to be `None` there, and that was not a
missing feature but a silent bug: `IMAGE_CAPABILITY_NOTE` is added unconditionally in
`get_openai_reply`, so the prompt promised pictures, the model called
`internet_search(want_images=true)`, and the tool answered with **silence** — which the
model reads as "no images found" and retries, the exact context-explosion path described
above. `handle_guest_message` now owns one `images: list` and passes it to all three
`get_gpt_reply` calls (not to `get_vision_reply` — single round, no search tool).

⚠️ **A media send needs its own timeout, and a timeout is not a rejection.** The shared
guest session is capped at 10s, tuned for 0.6s draft pings, while Telegram fetches every
image URL from the source site *before* it creates the message. `_edit_guest_inline_message`
therefore passes `RICH_MEDIA_TIMEOUT` on the image-bearing payload only, and `_attempt`
now returns a third value, `noaniq` — on a timeout or connection reset the ladder stops
instead of falling through to the plain payload, because the message may already have
arrived. Without that, the user sees the same answer twice, once with photos and once
without: the identical bug the DM path already paid for (`OUTCOME_UNKNOWN`).

`safe_update_history(..., images=images)` matters here as much as in the DM path — a raw
`[rasm:1]` left in history makes the model re-emit the token instead of searching, and
the user gets an empty answer.

Still missing in guest, deliberately: files (`output_files=None`) — the group has nowhere
to put one, and the caller's DM is only reachable if they have started the bot.

`handlers/guest.py` handles chats outside DMs via `guest_message`. It passes `caller_user_id` as **both** `chat_id` and `user_id`, so a person has one identity and one memory whether they write in a group or in the DM. Quota is charged to that user. Reminders are delivered to the DM regardless of where they were created.

### The admin panel is a package, and its registration order is the contract

`handlers/admin/` — `common.py` (guards + helpers used by more than one screen), `broadcast.py`, `promo.py`, `users.py`, `stats.py`, `system.py`, `journal.py` (audit / errors / revenue / limits / scheduled broadcasts / inactive users), `menu.py` (the inline menus behind the reply keyboard), `daily.py` (the two background watchers), and `__init__.py`, which does **nothing but register handlers**. It was one 2671-line file with a 2200-line function inside it.

The reply keyboard is four buttons; the other ten screens live in inline menus under `👥 Foydalanuvchilar` and `⚙️ Sozlamalar`. Their **text handlers are still registered** — an admin's phone keeps the old keyboard until the next `/start`. A screen takes `Message` and reads the admin's id from `message.from_user`, but in a callback `query.message` is the *bot's* message, so `menu.py` dispatches through `query.message.model_copy(update={"from_user": query.from_user})`; without that swap every button answers "faqat admin uchun". Whether a screen also gets `state` is read from its signature, not a hand-kept list.

Three things survived the split and must keep surviving:

1. **Registration order in `__init__.py` is functional.** FSM states go *after* the button handlers (otherwise an admin stuck in the promo state cannot press anything else), and `waiting_for_button` / `waiting_for_recipients` / `waiting_for_schedule` go *before* `waiting_for_content` (otherwise the button label an admin types is swallowed as "new broadcast content").
2. **The admin check lives inside each handler, not in a filter** — because `report_callback` and `process_report_message` are deliberately open to ordinary users.
3. **`bot` comes from `core.loader`**, not from a closure; no handler touches `dp`.

`tests/test_admin_registry.py` pins the full list — name, kind and order — of every registered handler. It is the safety net for any further reshuffling: it caught all five new registrations the moment they were added. Update the expected list deliberately, never to "make it pass".

Anything written to `user_activity` must also appear in the SQL filter and `type_labels` in `handlers/admin/stats.py`, or it silently vanishes from admin statistics. `tests/test_activity_tracking.py` guards this — and note it reads that file **by path**, so moving the code means updating the test.

The panel spends **zero AI tokens**: no module under `handlers/admin/` calls `services.ai`, and `non_admin_predicate` in `main.py` keeps admins out of the AI handlers entirely.

### Errors reach the admin through one funnel

`send_error_with_retry()` (`handlers/helpers.py`) is the only path a user-visible failure takes, so that is where `db.log_error()` writes to the `error_log` table — the "⚠️ Xatolar" screen reads it. Adding a second logging site elsewhere splits the picture; pass a `kind` instead (`"timeout"`, `"matn"`, …). The table trims itself on write (`ERROR_LOG_KEEP`).

### Premium emoji in the answer text

`build_rich_markdown()`'s last step swaps the emoji the model wrote for their animated form, `![ ](tg://emoji?id=…)`. The map is **loaded from an emoji pack at startup** (`TEXT_EMOJI_PACK`, currently `RestrictedEmoji` — 995 animated standard emoji) by `load_text_emoji_pack()`, because every sticker in a pack states which plain emoji it stands for, so Telegram builds the mapping. The previous hand-written `TEXT_CUSTOM_EMOJI` list was wrong in five of six entries — 🤖 pointed at a 🌟 from an unrelated pack, 🧠 at 🙂, 📄 at 📝, ⏰ at 📆, 🧹 at 🗑 — so the reader saw a different emoji than the model wrote. That list survives only as the fallback when the pack cannot be fetched. `apply_emoji_pack()` rebuilds three globals together (lookup, reverse lookup, regex); rebuilding only some would leave raw `![ ](tg://emoji?id=…)` on screen after a rejected send. This is post-processing on the bot side: **it costs no model tokens**, and the pack is fetched once at startup, never per message. ⚠️ It does change the failure profile: with 995 emoji mapped nearly every answer now carries custom emoji, so if the owner's Premium lapses the whole-message rejection stops being rare and hits every reply — the downgrade rung below is what keeps answers alive. The hand-placed `CUSTOM_EMOJI` ids used in buttons and system messages are untouched by any of this. The space in the alt text is required — `![](…)` can be read as a media block. It runs last because it must see the HTML the earlier steps produced: markdown is not parsed inside a table cell or an `<aside>`, so `_MD_DEAD_ZONE_RE` skips those regions and the plain emoji stays there (code blocks are already out via `_protect_spans()`). `TEXT_CUSTOM_EMOJI_MAX` caps the count. It was 12 and that was visible: an emoji-heavy reply (a "fun facts about octopuses" answer carries 30+) had its first twelve animated and the rest flat, so the *same* emoji appeared animated near the top and static further down — which reads as a bug. It is 50 now, one above the largest count in the whole stored history, so in practice the cap never fires; each swap costs ~36 characters against the 30000 rich limit, so 50 is ~1 800 characters. Note that emoji inside a table cell, an `<aside>` or a code block are deliberately left plain (`_outside_dead_zones`) — markdown is not parsed there, and `<tg-emoji>` is only valid in the `html` field, which this send path does not use. That mixed appearance is a platform limit, not the cap.

Custom emoji in text requires the bot owner to hold Telegram Premium, and a lapsed subscription makes Telegram reject the **whole message**. So the downgrade rung strips them: `plain_md` now goes through `strip_custom_emoji()` as well as `strip_image_tokens()`, and the flag deciding whether to retry is `bezakli` ("has media *or* premium emoji"), not `has_media`.

### A map is drawn from a marker the model writes

`[xarita:41.3111,69.2797,13]` becomes `<tg-map lat=… long=… zoom=…/>`. Coordinates come from the model — no geocoding, which would add a network call, a rate limit and a failure point. The code validates only the *ranges* (lat −90…90, long −180…180, zoom 1…20) and drops the marker when they fail; it cannot validate the *place*, since 41.9/12.5 is Rome and 41.3/69.3 is Tashkent and both look fine, so accuracy is the prompt's job. `<tg-map/>` is self-closing — written as `<tg-map></tg-map>` it gets the whole message rejected, which is exactly why the tag is emitted by code and not by the model. Like premium emoji, it is skipped inside table cells and `<aside>` via `_outside_dead_zones()`.

### Editing a photo the user already sent

`edit_image` is the same `_run_image_task()` as `generate_image` with a `source`
argument — one function, because the quota, the error text, the output-list contract and
the instruction handed back to the model are identical; only the endpoint differs. It
shares the `images` daily counter and the `MAX_IMAGE_ROUNDS` budget: to the user a drawing
and an edit are both "one picture", and a separate budget would just hand the model a
second attempt.

**The source bytes are never a tool parameter**, the same discipline as the map marker and
the location coordinate. The schema carries `prompt` and nothing else; the bytes come from
the chat through the existing `input_file_bytes` plumbing, which already carried the last
file. `handle_photo` now calls `_remember_file()` — before that the bot forgot a photo the
moment it had described it, so "now change the background" had no source at all.
`_is_image_bytes()` checks the **magic bytes, not the extension**: a PDF named `rasm.png`
would otherwise reach OpenAI and come back as an unreadable error. The schema is **386
tokens** (`tiktoken`, `o200k_base`) and is attached only while a picture is actually in the
chat, so ordinary traffic pays nothing for it — the same rule as `find_nearby`.

Two API arguments are load-bearing and neither one fails loudly if removed — the picture
just comes back wrong. `size="auto"` takes the output shape from the input, or a vertical
selfie is cropped square. `input_fidelity="high"` is what keeps the person's face, a logo
or text recognisably *the same*; below it the model redraws something similar, which
defeats the whole feature. `tests/test_image_edit.py` checks 18-19 pin both.

There are **two entry paths and both are needed.** A photo with a caption
("fonini o'zgartir") lands in `get_vision_reply`, which is single-round; the tool call is
harvested after the stream exactly as `update_memory` already was, and the result is not
fed back — so when the edit fails, *the code* appends the apology, because the model has
already written "here you go" above a message with no picture. A photo followed by a
separate message goes the ordinary `get_openai_reply` route with the full loop. Skipping
the vision path would have broken the most natural gesture there is: sending a picture and
saying what to do with it in one message.

⚠️ `pending_file_note()` needed a picture branch. The generic note says "use
run_python_sandbox to edit this file", and for a photo that sends "change the background"
into Python. Both routes are real — the sandbox still converts and resizes — so the note
names both, with `edit_image` first for anything that changes how the picture *looks*, and
says outright that a question about the photo's content needs no tool at all.

Still missing: groups. `edit_image` inherits `image_enabled`, which requires
`output_files is not None`, and `handlers/guest.py` passes `None` — so neither drawing nor
editing works outside a DM even for a Pro user.

### Finding real places near the user

A location message is stored (`core/memory.py::remember_location`, 30 min TTL) and the
`find_nearby` tool is attached **only while that record exists**. Same discipline as the
file tool: the schema is 548 tokens, and outside this flow it is never sent, so the
feature costs nothing on ordinary traffic. The short TTL is deliberate — someone driving
is somewhere else half an hour later, and answering "nearest fuel" from a stale
coordinate is a confident wrong answer.

**The model supplies the OSM tag, the code builds the query.** `categories` arrives as
`amenity=fuel`, `shop=supermarket` and is validated by `_TURKUM_RE` before it goes
anywhere near Overpass — model output is an untrusted boundary, and a category pasted
straight into the query string could restructure it. That split is also why there is no
hardcoded category list: the model knows OSM tagging, so "shinamontaj" and "bolalar
maydonchasi" work with no extra code. The coordinate is *never* a tool parameter — it
comes from the chat. A model-written coordinate would be invented, exactly like the map
marker problem.

**Mirror order is measured, not guessed** (`services/places.py`, 2026-09-10). The three
well-known Overpass instances answered in 22-40s or failed outright — 4 of 11 test
queries succeeded. `maps.mail.ru` answered the same queries in 1.6-4.9s, and holds full
planet data: verified in Tashkent, Samarkand (14 fuel stations), Namangan (nearest
pharmacy 247 m) and Nukus. It is first, the others are backup, and all are raced in
parallel.

⚠️ **An empty answer does not win that race.** `overpass.osm.ch` replies in 0.8s with
zero results because it only holds a Switzerland extract — first-success-wins would have
let it beat the slow-but-correct mirrors and the bot would say "nothing nearby" in a city
full of pharmacies. It is deliberately not in the list, and an empty result is now only
accepted once every mirror has answered. Test any new mirror on an *Uzbek* coordinate.

**The route link is built in code, never by the model.** `format_places()` appends a
ready `https://yandex.uz/maps/?rtext=~lat,lon&rtt=auto` to the nearest `ROUTE_LINKS_FOR`
(3) places and the tool description tells the model to copy it verbatim into
`[tugma: Yo'nalish | …]`. Same lesson as image URLs: a URL handed to the model comes back
rewritten and dead. Only the top three get one — a link is ~25 tokens and the model only
ever buttons the nearest.

**"Nothing found" and "the source did not answer" are different answers.** `find_nearby`
raises `PlacesUnavailable` rather than returning `[]`, and `_run_nearby_task` turns that
into an explicit instruction to tell the user it is a technical fault — because
"there is nothing near you" would be an unverified claim presented as fact.

**A location enters the conversation as a message, not as a canned card.** The first
version answered a location with a fixed "what should I find nearby?" card and no AI
call — cheap, and broken. That card never reaches `chat_messages`, so the model could not
see it: on screen the user sent a location and typed "Zapravka", while the model saw only
its own earlier "send me your location" followed by "Zapravka", and asked for the
location again. A loop the user cannot escape. `handle_location` now stores the
coordinate and pushes `_LOCATION_NOTE` through `_queue_for_ai()` — the same debounce
buffer `handle_text` uses, so quota, the busy queue, streaming and history all behave
identically. The 1.5s merge window is a bonus: a location followed immediately by
"zapravka" becomes one request and one round. The note carries **no coordinate** — a
coordinate written into history would still be there tomorrow, and "nearest" would be
answered from a stale position; the real one lives only in the 30-minute RAM record.

`handle_location` must stay registered **before** `capabilities.handle_unsupported`,
which still matches the other unhandled types; `F.location` was removed from that list.
And `location_message` had to be added to the SQL filter and `type_labels` in
`handlers/admin/stats.py`; `tests/test_activity_tracking.py` caught that omission
immediately.

### What the model may claim it can do

The model's capability list is not prose in the system prompt — it is built per
request from the **actual tool schemas** (`_capability_manifest()` in
`services/ai.py`) and sent as a `developer` message. Tool schemas alone were not
enough: they say what exists and nothing about what does not, so the model filled
the gap by guessing — promising drawn images to a free user (`generate_image` is
Pro-only) and PPTX in a group (`output_files=None` there, so the file tool is
never attached). The manifest names the attached tools, the missing ones *with
the reason*, and the things that are never possible (video, YouTube, music,
mini apps, choosing to answer by voice — TTS runs only on the voice-in path).
Because the names come from the schema dicts, renaming a tool moves the text
with it; a hand-written list would rot silently. It is skipped when
`tools_enabled=False` (internal calls) and must stay out of `instructions` —
its content depends on the user's plan, so caching it would poison the prefix
for everyone. `tests/test_capability_manifest.py` guards all of that.

### The model can draw a real button, not describe one

`[tugma: Label | https://…]` becomes `<tg-button type="url">` inside a
`<tg-button-row>`. Before this the only path to a Telegram button was code, so
"show me what it looks like" could only ever be answered with words. Same
discipline as the other markers: only `http(s)`, a malformed marker is dropped,
code blocks are untouched, and `strip_rich_tokens()` degrades it to `Label: url`
for the draft and the plain fallback. `callback_data` is deliberately not
offered — a model-invented callback has no handler and would be a dead button.

⚠️ `_RICH_PROTECT_RE` matches `https?://[^\s\]]+`, not `\S+`: the old pattern
swallowed the `]` that closes the marker, so the button never formed. A literal
`]` does not occur in a real URL (it is `%5D`).

Tables are **allowed** and the prompt says so. `_compact_tables()` turns GFM
into a real `<table compact>` (2-20 columns, separator row required). The prompt
used to forbid tables outright, which is what produced space-aligned
pseudo-tables that look fine on screen and lose all structure when copied.

⚠️ **`compact` is not a layout control** — aiogram's own field doc for
`is_compact` reads *"True, if table cells have smaller indents"*, nothing more.
It does not wrap, scroll or size columns, so reach for the prompt, not this
attribute, when a table reads badly. A live complaint ("compare two cars")
produced a tall unreadable strip because the model wrote whole sentences into
cells and the old rule said only "2 to 20 columns" — which reads as permission
for 20. The prompt now caps it at 2-4 for a phone and states that a cell is a
value, not a sentence.

A second live test ("tabulate 5 BMW models") exposed three more things the first
pass got wrong or missed. **Orientation is not fixed**: "one row per property,
one column per item" was shipped and is wrong whenever there are many items —
5 cars x 3 specs is 5 rows and 4 columns, and the rule as written asked for 6.
The rule is now "whichever side has FEWER members goes on the columns".
**Units belong in the header**, not repeated in every cell: "290 km/soat" wrapped
onto three lines where "290" under a "Tezlik (km/h)" header would not.
**Headers must be 1-2 short words** — "Maksimal tezlik" was broken *mid-word* into
"Maksi/mal/tezlik" on a phone. Total cost of the table rules: +186 tokens per
round, measured, against the ~1M/day the door tools saved the same day. `is_bordered`,
`is_striped` and `caption` also exist on the API type and are **unused**; the
HTML attribute spellings are not documented (`_EXPANDABLE_ATTR` is the standing
warning that field name ≠ attribute name), so adding them needs a live send
test before shipping — a wrong attribute gets the whole message rejected.

### Inline button styles

Telegram accepts only `primary` / `success` / `danger` on a real `InlineKeyboardButton`. Any other value is rejected and **the whole message fails to send**. Use `pro_module.btn()` and the `BTN_*` constants. Where delivery matters, build a plain fallback keyboard too — `pro.send_rich()` degrades progressively, and the broadcast sender switches the entire run to plain on the first rejection.

`BTN_LINK` ("link") is the exception: it exists only for `<tg-button>` **inside a rich message** and only on callback buttons. `btn()` deliberately does not accept it.

`btn(disabled=True)` (Bot API 10.3) renders a visible but dead button. `disabled` **is** the button's type field, so `callback_data`/`url` must not be sent with it — and `_downgrade_kb()` has to carry it through, otherwise the fallback keyboard produces a typeless button and the whole message is rejected.

Buttons can also live inside the message body via `pro_module.rich_button()` / `rich_button_row()` (`<tg-button-row>`, 1-8 per row). These are HTML in the `markdown` field, so their text must be escaped — the builders do it. Escaping quotes is not enough: `html.escape()` leaves newlines alone, and a raw newline inside an attribute makes Telegram's parser cut the tag off there and print the rest as literal text. `_attr_value()` turns them into `&#10;`, which the client resolves back to a real newline when the value is used — that is what makes "copy" work on a multi-line snippet.

### The command menu is decoration, not a gate

`services/menu.py` sets the `/` list per chat (`BotCommandScopeChat`), so Pro
commands appear on purchase and vanish when the plan lapses. The free list is
set once at startup for all private chats; the per-chat scope overrides it,
which is why `/start` needs no extra DB read.

The menu can always be stale — a user can type `/kunlik` without opening it, and
expiry is only detected on the user's next message. The real check stays in the
handler. Adding a Pro command = one row in `PRO_COMMANDS`; `tests/test_menu.py`
asserts every listed command is actually registered.

### Telegram limits worth knowing here

- Bot API cannot download files larger than 20 MB — that is why `DOCUMENT_MAX_SIZE_PRO` is 20 MB and not higher.
- `XTR` invoice amounts are the star count directly, **not** multiplied by 100. `tests/test_pro_payload.py` locks this.

### Sandbox

`services/sandbox.py` runs model-written Python with a scrubbed environment (no `BOT_TOKEN`, `OPENAI_API_KEY`, `DATABASE_URL`), a fresh temp cwd, a 60s timeout and RLIMITs on Linux. **Network is not blocked** — Railway offers no container isolation; the mitigation is that there are no secrets to steal and the timeout caps abuse.

`services/sandbox_helpers/` must stay next to `sandbox.py`; it is located via `Path(__file__).parent` and copied into each run.

**Two limits in `_apply_limits()`/`_build_child_env()` are load-bearing and only bite on Linux** (`_HAS_RESOURCE` is `False` on Windows, so local runs never see either). Memory is capped with `RLIMIT_DATA`, never `RLIMIT_AS`: `AS` counts *reserved address space*, and numpy/pandas/matplotlib/pptx reserve gigabytes they never touch — a 2 GB `AS` cap made `import pandas` itself raise `MemoryError`, and a different library failed each run. Separately, `OPENBLAS_NUM_THREADS=1` (with the `OMP_`/`MKL_`/`NUMEXPR_` twins) is required because `nproc` inside a container reports *host* cores; OpenBLAS then sizes a buffer per thread and dies with "Memory allocation still failed". These are not `PYTHON*` vars, so `-E` leaves them alone. `sandbox.check_libraries()` runs at startup and logs any library that will not import — without it, a broken import is invisible: the model just falls back to PDF and the user silently gets the wrong format.

Both helpers there exist for the same reason: the model composes documents by hardcoding coordinates and never measures what it placed. `docgen` owns text metrics for PDF; `deck` owns slide geometry for PPTX (safe margins, aspect-preserving image fit, a reserved footer band, a reserved caption line for image credit). Before `deck`, the three failures were always the same — picture over text, credit over picture, page number over picture. The tool description makes `deck` mandatory for PPTX and explicitly scopes the older manual-layout rules to PDF/DOCX/XLSX, because two sets of layout instructions produce worse output than one. `tests/test_deck_layout.py` asserts no two content shapes intersect — it already caught a 0.1" clash between the section number and its heading.

`deck` also owns image *placement*, not just geometry: `Deck(images=[...])` is a pool and every layout's `image` defaults to the `AUTO` sentinel, so photos spread across the whole deck. This exists because the model reads "put a picture on the first slide" literally and leaves every other slide bare. `image=None` is the explicit opt-out — that is why `AUTO` cannot simply be `None`. Side-by-side layouts put text and picture in frames of identical size and top, the picture cover-cropped to fill its frame exactly, so image scale never wanders between slides. `image_slide` is the opposite case — cropping a map or a chart destroys it — so there the picture is fitted whole and the card is then shrunk to hug it with fixed padding; the box it is given is only a bound, never the drawn frame. Caption and credit are positioned off the returned rect, not off that bound.

The tool description promises the model there is **no internet** inside the sandbox, and that promise is what makes generated code deterministic — a model asked to fetch a photo invents a URL, and invented URLs are dead. So photos for documents arrive the other way round: the model lists what it needs in `image_queries`, `_run_file_task` downloads and converts them **before** the run, and `run_in_sandbox(extra_files=...)` drops them in the work dir as `rasm1.jpg`, `rasm2.jpg` — positional, one per query, a missing one still burns its number so the rest don't shift. They are cached per user request, because the file loop reruns up to 4 times and a second download would hand the model *different* photos than the caption it already wrote. Everything is re-encoded to JPEG via Pillow: most DuckDuckGo image results are WEBP and python-pptx rejects WEBP.

## Other agent configs

A Codex config exists at `~/.codex/config.toml`. Reply `/import` to scan and list what is importable (MCP servers, slash commands, subagents, skills, instructions), then `/import --yes=<digest>` — the scan output names the digest — to apply the user-level items.
