tg_pool_framework — project status

What this is

A framework for running a pool of Telegram accounts through Telethon:
mass messaging, user extraction/parsing, proxy checking, tdata<->session
conversion, account health checks. Two parts: a Python backend (runs
either as a CLI tool or as a REST API) and a WPF desktop launcher that
spawns the backend locally and talks to it over http+websocket.

Below is what's actually done, based on the code and tests, not on
comments or file names.


BACKEND (Python)

Accounts (src/accounts)

Loads accounts from a folder, from tdata, from .session+.json pairs, or
from env vars (up to 49 TG_API_ID_i/... slots). Round-robin proxy
assignment across N accounts. In-memory account registry with
filtering/sorting (status, premium, 2fa, country, role, folder, free
text), with optional DB persistence. Health check: login, get_me, 2FA
check, ban/floodwait detection, and — when deep_check is on — pinging
@SpamBot and parsing the restriction-lift date out of its reply (RU/EN).
A warmup policy for fresh accounts (gradual ramp-up by day). Session
file encryption via Fernet. Two background schedulers — one rechecks
accounts once their cooldown expires, the other periodically rechecks
the whole pool.

Fully done, every file has tests.

API (src/api)

FastAPI app. Endpoints: /health, /accounts (+role/folder/recheck/
rescan), /campaign (start/stop/status), /parsing (start/stop/status),
/proxy_check (start/status), /tdata_convert (start/status),
/session_convert (start/status), /ws/events (websocket streaming
account/message/metric events). Campaign and parsing share the same
account pool through a PoolAccessGuard — one can't start while the
other is running.

Fully done, 44 tests covering every endpoint and edge case (409 busy,
400 invalid input, etc).

Messaging campaigns — in detail (src/messaging + orchestrator.py + api/campaign.py)

This is where most of the recent work went. Implemented and tested:

- spintax {option1|option2} in message text, nesting works
- media: single file or a list (random pick per recipient), video_note
  and voice modes
- reposting an existing message via a link (t.me/name/id and private
  t.me/c/id/id) or through a bot relay (username + list of post ids,
  random pick)
- account-folder targeting — a campaign only runs on accounts tagged
  with a given folder
- per-account send-count range (messages_per_account_min/max) — each
  worker gets a random quota within the range, only successful sends
  count against it
- exact total send count (exact_total_target) — the campaign cycles,
  excluding already-messaged recipients each round, until it hits the
  target or the source runs out of people
- scheduled sending (schedule_at) — messages go out through Telegram's
  own scheduler, success means "accepted for scheduling," not
  "delivered"
- pin after send (pin_after_send) — a pin failure doesn't undo a
  successful send
- staggered worker start (worker_batch_size/delay) instead of the whole
  pool starting at once
- repeating the whole campaign every N hours (repeat_every_hours)

Plus smaller things: inline buttons ([Label|url]), {first_name}/
{username} personalization, adaptive backoff on flood waits, a circuit
breaker per worker (an account gets temporarily excluded after a run of
failures and the worker fails over to a spare), campaign history saved
to the DB.

Three things were deliberately left out (a separate call I made earlier
in the project) — auto-stop based on ban count, deleting dialogs to
hide that messages were sent, and reposting through a disposable
per-account private chat. That's an intentional exclusion, not
something forgotten.

Parsing / data extraction (src/extraction + orchestrator.py)

Collection strategies: group members, channel comments, group messages,
reactions, polls, system messages, topic messages — all real
implementations (actual Telethon calls, pagination, FloodWait
handling). Sources are split across workers by weight, not round-robin
(LPT — estimate each source's size via GetFullChannelRequest, then
greedily assign to whichever worker is currently least loaded).
Cross-run dedup via Redis (SADD + TTL). Per-source anti-flood via a
Redis rate limiter — but that's only wired into the pure-parsing
pipeline (orchestrate_extraction_only), not into the messaging one
(orchestrate_multi_source). Per-source strategy selection via a Lua
script (when there's more than one source and no strategy is pinned).
Excel export (summary/by-source/full), with a hook for custom columns
via Lua.

Fully done, tested.

Proxies (src/proxy)

Proxy checking is written from scratch, no external proxy library:
real SOCKS5 handshake (with auth), SOCKS4, HTTP CONNECT — each one
actually connects to a Telegram data center and measures latency. Proxy
geo lookup uses an offline database (geoip2fast), no outside calls.
tdata<->session conversion via opentele, in batches, with jitter between
accounts, with 2FA handling.

Done, tested.

Resilience and scripting (src/resilience, src/scripting)

CircuitBreaker — standard CLOSED/OPEN/HALF_OPEN. LuaEngine — a sandbox
built on lupa (os/io/require/load stripped out, memory cap, execution
time cap via an instruction-count hook, hot-reload by file mtime). Used
for the auto-responder, parsing strategy selection, custom export
columns, and user filters.

Done, tested.

Database (src/db)

Async SQLAlchemy, upsert via ON CONFLICT (postgres and sqlite both
supported). Three linear alembic migrations: accounts -> campaigns +
results -> geo/2fa/role/folder. All of this is optional — without
DATABASE_URL set, everything still works, it just doesn't keep history.

Done.

CLI modes (src/features + main.py)

main.py picks a mode from the MODE env var (or asks interactively if
run from a terminal): send, parse, check_accounts, check_proxies,
convert_tdata, convert_session. This is the console equivalent of the
same functionality exposed through the API — the code is nearly
mirrored between the two.

Done.


LAUNCHER (WPF)

Tabs: Dashboard, Accounts, Campaign, ProxyCheck, RotationCheck, Tdata,
Parsing, Session->Tdata. Three languages (ru/en/zh), switches instantly
without a restart.

Fully working end to end:
- Dashboard — connection status, live campaign stats, account table fed
  by websocket events
- Accounts — table, filters, rescanning the account folder for new
  accounts, pool recheck
- ProxyCheck — paste a list, run the check, results table
- Tdata and Session->Tdata — conversion both ways, with folder-browse
  dialogs
- Parsing — sources, strategy, filters, export, start/stop, progress

Campaign is where the real gap is. The UI only sends 5 fields out of
roughly 21 the backend supports: target, message, media_path,
buttons_raw, parse_mode. Everything else is drawn on screen (toggles,
fields) but wired to nothing — no DTO field, no BackendClient call. The
code itself even comments these as temporary placeholders. Not wired:
media_paths (multiple files), media_kind (there's a video_note toggle,
it does nothing), spintax (not exposed at all), silent, link_preview,
forward_link and bot_relay (repost), account_folder (folder targeting),
messages_per_account_min/max (fields exist, disabled, hardcoded to
1/40), exact_total_target, schedule_at, pin_after_send,
worker_batch_size/delay, repeat_every_hours.

RotationCheck is a stub end to end. It doesn't even have a backend
endpoint to call — proxy_checker.py currently only measures whether a
proxy is reachable and how slow it is, it never actually sends a
request through it to see what IP comes out the other end. The Run
button is disabled with a tooltip explaining why.

Smaller loose ends in Accounts — the 5 action icons in the row (folder/
username/2FA/info/monitor) are drawn but not bound to any command.
AssignRoleAsync/AssignFolderAsync exist and work on the BackendClient
side, nothing in the UI calls them yet.

No auto-updater anywhere in the launcher — no version check, no update
mechanism.


INSTALLER (installer/)

Inno Setup. Installs portably (Program Files or a per-user folder — can
run without admin rights), ships the self-contained launcher exe plus
the backend source (no bundled Python — the user needs Python installed
separately). Creates the Data\ folder tree (accounts, proxies, exports,
logs, crashes) with the right permissions. Checks for Python on PATH —
if found, installs requirements.txt automatically; if not, shows a
message asking the user to install Python by hand. No updater here
either.


WHAT'S LEFT

1. Wire the Campaign UI up to what the backend already supports — this
   is the biggest chunk of remaining work: spintax, multi-media/
   video_note/voice, repost, folder targeting, per-account send-count
   range, exact total count, scheduled send, pin after send, worker
   batching, repeat cycle. The backend can do all of this right now;
   it's purely a C#-side job (DTO + ViewModel + the actual controls).
2. RotationCheck — either add a backend endpoint that actually sends a
   request through the proxy and reads back the outbound IP, or drop
   the tab if the feature isn't needed after all.
3. Accounts — hook the 5 action icons up to the existing
   AssignRoleAsync/AssignFolderAsync (the methods are there, just
   unused).
4. Parsing anti-flood (the Redis rate limiter per source) currently
   only runs in plain parsing, not when a campaign extracts recipients
   from a source — if that's wanted too, thread antiflood_redis_client
   into orchestrate_multi_source the same way it's already done in
   orchestrate_extraction_only.
5. Launcher auto-update — decide if it's needed at all; there's
   currently nothing in the project for it.
