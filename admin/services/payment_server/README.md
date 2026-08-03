# Payment server

The payment server is the central authority for customer API keys, balances,
deposits, and Datamoll purchases. Customer installations only receive a TG
Pool API key; Datamoll provider credentials remain on this server.

## Configuration and process boundaries

Do not give every process one combined environment. Start from
`.env.public.example`, `.env.admin.example`, or `.env.webhook.example` and set
`PAYMENT_ENV_FILE` to the selected file. The public process receives provider
credentials but no administrator or webhook key. The administrator process
receives signer access but no provider credentials. The webhook process receives
only its callback key and notification settings.

Across the isolated processes, the platform uses:

```env
PAYMENT_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/tg_pool_payments
PAYMENT_ADMIN_API_KEY=replace-with-a-long-random-secret
PAYMENT_WEBHOOK_KEY=replace-with-a-different-long-random-secret
PAYMENT_AUTO_CREATE_WALLETS=1
DATAMOLL_PROVIDER_KEY=provider-key
DATAMOLL_PROVIDER_SECRET=provider-secret
PAYMENT_SIGNER_URL=http://private-signer:8300
PAYMENT_SIGNER_API_KEY=shared-internal-secret
PAYMENT_CHAIN_NETWORK=mainnet
PAYMENT_TRC20_CONTRACT=TConfiguredTokenContract
PAYMENT_TRON_HTTP_ENDPOINT=https://api.trongrid.io
# Retail unit price = wholesale * 1.20 + 0.25 in this example.
PAYMENT_RETAIL_MARKUP_PERCENT=20
PAYMENT_RETAIL_MARKUP_FIXED=0.25
```

With automatic creation enabled, `POST /admin/users` asks the isolated signer
to generate a wallet. The payment service stores only its public address; the
private key remains encrypted in the signer vault. `deposit_address` may still
be supplied explicitly for migration or emergency administration.

`PAYMENT_RETAIL_MARKUP_PERCENT` and `PAYMENT_RETAIL_MARKUP_FIXED` define the
customer-facing Datamoll price. The percentage is applied first, then the fixed
amount is added per account. Wholesale prices remain unchanged in the product
cache. Catalog responses, wallet debits, order responses, and sales statistics
all use the retail price. Both settings default to `0` for backward-compatible
pass-through pricing.

Run the migration, then start each API as a separate deployment from the
`admin/services` directory:

```powershell
alembic -c payment_server/alembic.ini upgrade head
uvicorn payment_server.public_app:app --host 0.0.0.0 --port 8200
uvicorn payment_server.admin_app:app --host 127.0.0.1 --port 8210
uvicorn payment_server.webhook_app:app --host 127.0.0.1 --port 8220
```

`payment_server.app:app` is a compatibility test surface and must not be
deployed.

Point each customer backend at the public HTTPS endpoint:

```env
PAYMENT_SERVER_URL=https://payments.example.com
```

For Telegram onboarding, also configure `PAYMENT_TELEGRAM_BOT_TOKEN` and
`PAYMENT_PUBLIC_URL`, then run:

```powershell
python -m payment_server.telegram_bot
```

Run the TRC20 deposit watcher as a separate process:

```powershell
python -m payment_server.deposit_watcher
```

The watcher loads wallet addresses from `payment_wallets` on every poll,
verifies the configured `PAYMENT_TRC20_CONTRACT`, and calls
`POST /webhooks/tron/deposits` with `X-Webhook-Key`. A deposit is credited once
`PAYMENT_REQUIRED_CONFIRMATIONS` is reached. Repeated events and confirmation
updates are idempotent. Configure polling with:

```env
PAYMENT_DEPOSIT_POLL_INTERVAL_SECONDS=10
PAYMENT_DEPOSIT_LOOKBACK_SECONDS=604800
PAYMENT_DEPOSIT_MAX_PAGES=10
PAYMENT_DEPOSIT_MAX_CONCURRENCY=50
PAYMENT_DEPOSIT_RETRY_ATTEMPTS=3
PAYMENT_DEPOSIT_RETRY_BASE_DELAY_SECONDS=0.5
TRONGRID_API_KEY=
```

Address scans, transaction confirmation lookups, and webhook deliveries run in
bounded concurrent batches. The watcher fetches the current block height once
per poll, retries transient HTTP and rate-limit failures with exponential
backoff, and isolates individual address or transaction failures so the rest of
the batch continues. Keep `PAYMENT_DEPOSIT_MAX_CONCURRENCY` within the limits of
your TRON provider and payment API; `50` is the default tested with a burst of
1,000 deposits.

The lookback defaults to seven days so a restarted watcher catches recent
transfers. The API sends a best-effort Telegram message when a deposit is
credited for the first time and the user has a Telegram ID. Set
`PAYMENT_TELEGRAM_TRUST_ENV=0` to bypass broken system HTTP proxy settings, or
leave it at `1` when Telegram must use the host proxy.

The configured stablecoin is credited at one ledger currency unit per token
(the default is `1 USDT = 1 USD`). Use a conversion service instead of this
fixed mapping if you configure a non-stable asset.

## Administrator withdrawals

The signer must be deployed separately according to
`payment_signer/README.md`. To inspect a user's live chain balance and
database purchasing balance:

```http
GET /admin/users/{user_id}/wallet
X-Admin-Key: ...
```

To withdraw a specific amount, or omit `amount` to sweep the full current
on-chain token balance:

```http
POST /admin/users/{user_id}/withdrawals
X-Admin-Key: ...
X-Admin-Actor: operator-name
Idempotency-Key: unique-operation-id

{"amount": "25.00"}
```

The destination always comes from the isolated signer's administrator-wallet
setting; withdrawal callers cannot supply a destination. A sweep is an on-chain
asset movement and never creates a customer ledger debit. Refresh submitted
withdrawals with `POST /admin/withdrawals/{withdrawal_id}/refresh`.

The administrator desktop app can read and change that destination through
`GET /admin/treasury-wallet` and `PUT /admin/treasury-wallet`. The isolated
signer validates and persists the new address in its state database; the
configured environment address remains the initial default for a fresh signer.
Both responses include the wallet's live `on_chain_balance` and `asset`.

The same operation is available from the administrator CLI:

```powershell
python -m payment_server.withdraw --user-id 42 --amount 25
python -m payment_server.withdraw --user-id 42
```

The second command sweeps the full current token balance. Set
`PAYMENT_ADMIN_URL`, `PAYMENT_ADMIN_API_KEY`, and optionally
`PAYMENT_ADMIN_ACTOR` in the administrator environment.
