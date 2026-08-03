# TG Pool Framework

TG Pool is a Windows desktop application and local Python agent for managing
Telegram accounts, proxies, parsing, messaging, scheduled campaigns, account
conversion, and account activation. Central licensing, payments, administration,
and wallet signing are maintained as a separate administrator platform.

This repository is divided into two independently buildable sides:

```text
tg_pool_framework/
├── user/                         Customer-delivered product
│   ├── apps/desktop/             WPF desktop application
│   ├── apps/activator/           License activation console
│   ├── apps/website/             Public React website
│   ├── services/local-agent/     Python REST/WebSocket API and Telegram engine
│   ├── packages/desktop-common/  Shared customer-side .NET code
│   └── packaging/                Customer installer
├── admin/                        Central and privileged platform
│   ├── apps/admin-desktop/       Administrator WPF application
│   ├── services/license_server/  Licensing authority
│   ├── services/payment_server/  Payments, ledger, webhooks, and workers
│   ├── services/payment_signer/  Isolated TRON wallet signer
│   ├── contracts/                Generated OpenAPI contracts
│   └── packaging/                Administrator installer
└── ARCHITECTURE.md               Ownership and security boundaries
```

Customer and administrator source code do not import one another. Communication
between the two sides uses the versioned HTTP contracts in `admin/contracts`.

## Prerequisites

For the complete development environment, install:

- Windows 10 or 11
- Python 3.12
- .NET SDK 10
- Node.js 24 and pnpm 10 for the website
- PostgreSQL for production central services
- Inno Setup 6 only when building Windows installers

SQLite is sufficient for local development and automated tests. A running Redis
server is optional; features fall back to single-process behavior when
`REDIS_URL` is not configured.

Confirm the main tools:

```powershell
py -3.12 --version
dotnet --version
node --version
pnpm --version
```

All commands below assume PowerShell and start at the repository root.

## First-time setup

Use separate virtual environments so the customer and administrator sides can
be built and released independently.

### Install customer dependencies

```powershell
py -3.12 -m venv user\services\local-agent\.venv
user\services\local-agent\.venv\Scripts\python.exe -m pip install --upgrade pip
user\services\local-agent\.venv\Scripts\python.exe -m pip install -r user\services\local-agent\requirements.txt
```

The desktop application automatically discovers this virtual environment when
running from a development checkout.

### Install administrator dependencies

```powershell
py -3.12 -m venv admin\.venv
admin\.venv\Scripts\python.exe -m pip install --upgrade pip
admin\.venv\Scripts\python.exe -m pip install `
  -r admin\services\license_server\requirements.txt `
  -r admin\services\payment_server\requirements.txt `
  -r admin\services\payment_signer\requirements.txt
```

### Restore website dependencies

```powershell
Set-Location user\apps\website
pnpm install --frozen-lockfile
Set-Location ..\..\..
```

## Quick start: customer local agent only

This is the fastest way to verify the customer runtime. Licensing and central
payments are disabled when their URLs are unset.

```powershell
Set-Location user\services\local-agent
.\.venv\Scripts\python.exe -m uvicorn tg_pool.api.app:app `
  --host 127.0.0.1 `
  --port 8000
```

In another terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

The expected response contains `status: ok`. Stop the server with `Ctrl+C`.

To configure real accounts and optional integrations, copy and edit the supplied
template:

```powershell
Copy-Item user\services\local-agent\.env.example user\services\local-agent\.env
```

Do not use the example Telegram credentials. Configure either `ACCOUNTS_DIR`
with `.session`/`.json` account pairs or replace the sample `TG_API_ID_*`,
`TG_API_HASH_*`, and `TG_PHONE_*` values.

## Run the licensed customer desktop application

The desktop application starts the local agent automatically on a random
loopback port. It does not need a separately started local-agent process.

It does require:

1. A running public license API.
2. At least one issued license key.
3. A license signing private key whose public key matches
   `_PUBLIC_KEY_HEX` in
   `user/services/local-agent/tg_pool/licensing/signature.py`.

For a new deployment, generate the signing pair from `admin/services`:

```powershell
Set-Location admin\services
..\.venv\Scripts\python.exe -m license_server.generate_signing_key
Set-Location ..\..
```

Store the printed private value only in the public license service's secret
configuration. Put the printed public value into `_PUBLIC_KEY_HEX` before
building the customer release. Never commit or distribute the private value.

After starting the public license service and issuing a key as described below,
run the customer desktop application:

```powershell
$env:LICENSE_SERVER_URL = "http://127.0.0.1:8100"
$env:PAYMENT_SERVER_URL = "http://127.0.0.1:8200"
dotnet run --project user\apps\desktop\TgPoolLauncher.csproj
```

On first launch, `TgPoolActivator` requests the issued license key. Successful
activation is cached in the local `Data` directory and the desktop application
then starts its local Python agent.

## Run the administrator platform locally

Run administrator Python modules from `admin/services`, which is the package
root for `license_server`, `payment_server`, and `payment_signer`.

The examples below use SQLite. For production, replace the SQLite URLs with
PostgreSQL URLs and give every process a least-privilege database account.

### 1. License service

Create separate public and administrator environment files:

```powershell
Copy-Item admin\services\license_server\.env.public.example `
  admin\services\license_server\.env.public.dev
Copy-Item admin\services\license_server\.env.admin.example `
  admin\services\license_server\.env.admin.dev
```

Set both files to the same development database:

```env
LICENSE_DATABASE_URL=sqlite+aiosqlite:///./license-dev.db
```

In `.env.public.dev`, set the signing private key and release information:

```env
LICENSE_SIGNING_PRIVATE_KEY=<32-byte-private-seed-in-hex>
LATEST_LAUNCHER_VERSION=1.0.0
LATEST_LAUNCHER_NOTES=Local development
```

In `.env.admin.dev`, set a long random administrator key:

```env
LICENSE_ADMIN_API_KEY=<random-administrator-secret>
```

Apply migrations from `admin/services`:

```powershell
Set-Location admin\services
$env:LICENSE_DATABASE_URL = "sqlite+aiosqlite:///./license-dev.db"
..\.venv\Scripts\python.exe -m alembic `
  -c license_server\alembic.ini upgrade head
Set-Location ..\..
```

Start the public API in one terminal:

```powershell
Set-Location admin\services
$env:LICENSE_ENV_FILE = (Resolve-Path license_server\.env.public.dev).Path
..\.venv\Scripts\python.exe -m uvicorn license_server.public_app:app `
  --host 127.0.0.1 --port 8100
```

Start the private administrator API in another terminal:

```powershell
Set-Location admin\services
$env:LICENSE_ENV_FILE = (Resolve-Path license_server\.env.admin.dev).Path
..\.venv\Scripts\python.exe -m uvicorn license_server.admin_app:app `
  --host 127.0.0.1 --port 8110
```

Check both processes:

```powershell
Invoke-RestMethod http://127.0.0.1:8100/health
Invoke-RestMethod http://127.0.0.1:8110/health
```

Issue a development license from `admin/services`:

```powershell
..\.venv\Scripts\python.exe -m license_server.generate_keys `
  --tier month `
  --count 1 `
  --note "local development" `
  --url http://127.0.0.1:8110 `
  --admin-key "<same-administrator-secret>"
```

Keep the printed license key for the customer activator.

### 2. Payment APIs

Create one environment file per security surface:

```powershell
Copy-Item admin\services\payment_server\.env.public.example `
  admin\services\payment_server\.env.public.dev
Copy-Item admin\services\payment_server\.env.admin.example `
  admin\services\payment_server\.env.admin.dev
Copy-Item admin\services\payment_server\.env.webhook.example `
  admin\services\payment_server\.env.webhook.dev
```

Set the following database URL in all three files:

```env
PAYMENT_DATABASE_URL=sqlite+aiosqlite:///./payments-dev.db
```

Then configure only the secrets required by each surface:

- Public: `DATAMOLL_PROVIDER_KEY` and `DATAMOLL_PROVIDER_SECRET` for catalog
  and purchasing operations.
- Administrator: `PAYMENT_ADMIN_API_KEY`, `PAYMENT_SIGNER_URL`, and
  `PAYMENT_SIGNER_API_KEY`.
- Webhook: `PAYMENT_WEBHOOK_KEY` and optionally
  `PAYMENT_TELEGRAM_BOT_TOKEN`.

Apply migrations from `admin/services`:

```powershell
Set-Location admin\services
$env:PAYMENT_DATABASE_URL = "sqlite+aiosqlite:///./payments-dev.db"
..\.venv\Scripts\python.exe -m alembic `
  -c payment_server\alembic.ini upgrade head
Set-Location ..\..
```

Start each API in a separate terminal:

```powershell
# Public customer payment API
Set-Location admin\services
$env:PAYMENT_ENV_FILE = (Resolve-Path payment_server\.env.public.dev).Path
..\.venv\Scripts\python.exe -m uvicorn payment_server.public_app:app `
  --host 127.0.0.1 --port 8200
```

```powershell
# Private administrator payment API
Set-Location admin\services
$env:PAYMENT_ENV_FILE = (Resolve-Path payment_server\.env.admin.dev).Path
..\.venv\Scripts\python.exe -m uvicorn payment_server.admin_app:app `
  --host 127.0.0.1 --port 8210
```

```powershell
# Dedicated payment webhook API
Set-Location admin\services
$env:PAYMENT_ENV_FILE = (Resolve-Path payment_server\.env.webhook.dev).Path
..\.venv\Scripts\python.exe -m uvicorn payment_server.webhook_app:app `
  --host 127.0.0.1 --port 8220
```

Check the APIs:

```powershell
Invoke-RestMethod http://127.0.0.1:8200/health
Invoke-RestMethod http://127.0.0.1:8210/health
Invoke-RestMethod http://127.0.0.1:8220/health
```

The health endpoints work without Datamoll or TRON access. Catalog, purchasing,
wallet, deposit, and withdrawal operations require their corresponding external
credentials and services.

### 3. Isolated payment signer

The signer is optional for UI and non-wallet development. It is required for
automatic wallet creation, balance inspection, and TRC20 withdrawals.

Create its configuration:

```powershell
Copy-Item admin\services\payment_signer\.env.example `
  admin\services\payment_signer\.env.dev
Set-Location admin\services
..\.venv\Scripts\python.exe -m payment_signer.keyvault generate-key
```

Put the generated Fernet key in `SIGNER_VAULT_KEY` inside `.env.dev`, then
initialize the encrypted vault:

```powershell
$env:SIGNER_VAULT_KEY = "<generated-fernet-key>"
..\.venv\Scripts\python.exe -m payment_signer.keyvault init `
  --output payment_signer\local\wallet-keys.enc
```

Complete `.env.dev` with:

- A unique `PAYMENT_SIGNER_API_KEY` matching the payment administrator process.
- The same `SIGNER_VAULT_KEY` used to initialize the vault.
- A valid treasury address and TRC20 contract for the configured network.
- A Nile or Shasta endpoint for development, or the mainnet endpoint for
  production.

Start the signer:

```powershell
$env:SIGNER_ENV_FILE = (Resolve-Path payment_signer\.env.dev).Path
..\.venv\Scripts\python.exe -m uvicorn payment_signer.app:app `
  --host 127.0.0.1 --port 8300
```

Signer startup contacts the configured TRON endpoint to validate the token
contract. It will not start with placeholder addresses or without network
access. Never expose port 8300 publicly.

### 4. Administrator desktop

With the private payment API running, open a terminal at the repository root:

```powershell
$env:PAYMENT_ADMIN_URL = "http://127.0.0.1:8210"
dotnet run --project admin\apps\admin-desktop\TgPoolAdmin.csproj
```

Enter the same `PAYMENT_ADMIN_API_KEY` in the administrator application when
prompted.

### 5. Optional workers

Run the Telegram onboarding bot from `admin/services` after setting
`PAYMENT_TELEGRAM_BOT_TOKEN`, `PAYMENT_ADMIN_API_KEY`, and
`PAYMENT_PUBLIC_URL`:

```powershell
..\.venv\Scripts\python.exe -m payment_server.telegram_bot
```

Run the TRC20 deposit watcher only after configuring the chain endpoint,
contract, wallet addresses, webhook URL, and webhook key:

```powershell
..\.venv\Scripts\python.exe -m payment_server.deposit_watcher
```

For local split deployment, set the watcher's `PAYMENT_PUBLIC_URL` to the
dedicated webhook address, such as `http://127.0.0.1:8220`.

## API surfaces

| Process | Default local port | Exposure | Purpose |
|---|---:|---|---|
| Customer local agent | Random from desktop; `8000` standalone | Loopback only | Desktop control API |
| Public license API | `8100` | Public HTTPS | Activation, version, profile names |
| Admin license API | `8110` | Private | Issue, list, revoke, and reset keys |
| Public payment API | `8200` | Public HTTPS | Customer identity, balance, catalog, orders |
| Admin payment API | `8210` | Private | Users, pricing, statistics, withdrawals |
| Payment webhook API | `8220` | Restricted machine access | Confirmed deposit callbacks |
| Wallet signer | `8300` | Private service network | Wallet vault and TRC20 signing |

Never publicly deploy the compatibility entry points
`license_server.app:app` or `payment_server.app:app`; they intentionally contain
both public and privileged routes for backward-compatible tests.

## Website

Start the Vite development server:

```powershell
Set-Location user\apps\website
pnpm dev
```

Production checks are:

```powershell
pnpm lint
pnpm build
```

The current checkout references content modules under `src/data` that are not
present in the repository. Supply the project content files (`nav`, `footer`,
`capabilities`, `faq`, `modules`, `steps`, `pricing`, and `manual`) before the
website TypeScript build can succeed. This does not affect the desktop or API
applications.

## Database migrations

Run migrations before production deployment and whenever a new migration is
added:

```powershell
# Customer/local-agent database
Set-Location user\services\local-agent
$env:DATABASE_URL = "postgresql+asyncpg://user:pass@localhost:5432/tg_pool"
.\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head

# Central databases; run from admin/services
Set-Location ..\..\..\admin\services
$env:LICENSE_DATABASE_URL = "postgresql+asyncpg://user:pass@localhost:5432/tg_pool_licenses"
..\.venv\Scripts\python.exe -m alembic -c license_server\alembic.ini upgrade head
$env:PAYMENT_DATABASE_URL = "postgresql+asyncpg://user:pass@localhost:5432/tg_pool_payments"
..\.venv\Scripts\python.exe -m alembic -c payment_server\alembic.ini upgrade head
```

The desktop development path normally uses its managed local SQLite databases,
so manually running local-agent migrations is mainly needed for server-style
deployments using `DATABASE_URL`.

## Build and test

### Customer side

```powershell
dotnet build user\TgPool.User.slnx

Set-Location user\services\local-agent
.\.venv\Scripts\python.exe -m pytest
Set-Location ..\..\..
```

### Administrator side

```powershell
dotnet build admin\TgPool.Admin.slnx

Set-Location admin\services\license_server
..\..\.venv\Scripts\python.exe -m pytest

Set-Location ..\payment_server
..\..\.venv\Scripts\python.exe -m pytest

Set-Location ..\payment_signer
..\..\.venv\Scripts\python.exe -m pytest

Set-Location ..\..\..
```

### Regenerate API contracts

After changing a central API route or schema:

```powershell
Set-Location admin\services
..\.venv\Scripts\python.exe ..\contracts\export_openapi.py
Set-Location ..\..
```

Review and commit all five generated JSON files. Public contract breaking
changes require a new API version or a coordinated customer release.

## Publish Windows applications

Publish the self-contained customer desktop application:

```powershell
dotnet publish user\apps\desktop\TgPoolLauncher.csproj `
  -c Release -p:PublishProfile=win-x64
```

Publish the administrator desktop application:

```powershell
dotnet publish admin\apps\admin-desktop\TgPoolAdmin.csproj `
  -c Release -p:PublishProfile=win-x64
```

Compile the corresponding Inno Setup files afterward:

```text
user/packaging/windows-installer/TgPoolLauncher.iss
admin/packaging/windows-installer/TgPoolAdmin.iss
```

## Production rules

- Put public APIs behind HTTPS and a reverse proxy.
- Bind administrator APIs to a private network or VPN.
- Permit signer traffic only from authorized payment-service identities.
- Use different secrets and environment files for every surface.
- Use PostgreSQL rather than SQLite for central production services.
- Store signing keys, API keys, provider credentials, and vault keys in a
  secret manager—not committed `.env` files.
- Back up the payment database, license database, signer state database,
  encrypted vault, and vault encryption key independently.
- Never place wallet private keys in the payment database.
- Preserve idempotency keys for withdrawals and external purchases.

See `ARCHITECTURE.md` for the complete ownership and network model.

## Troubleshooting

### `python` is not recognized

Use `py -3.12` during setup. After creating the virtual environments, use the
explicit `.venv\Scripts\python.exe` paths shown above.

### Desktop reports that the backend did not start

Confirm that `user/services/local-agent/.venv` exists and dependencies are
installed. Then run the local agent manually to see its startup error:

```powershell
Set-Location user\services\local-agent
.\.venv\Scripts\python.exe -m uvicorn tg_pool.api.app:app `
  --host 127.0.0.1 --port 8000
```

Desktop logs are stored under its managed `Data\Logs` directory.

### License activation succeeds but the local agent rejects the response

The public key compiled into `tg_pool/licensing/signature.py` does not match
the private key used by the public license service. Correct the keypair and
rebuild the customer release; never disable signature validation in production.

### An admin endpoint returns 404 on a public port

This is intentional. Use ports 8110 and 8210 for administrator operations.
Public processes do not contain administrator routes.

### Payment catalog or order calls fail

Configure valid `DATAMOLL_PROVIDER_KEY` and `DATAMOLL_PROVIDER_SECRET` values
for the public payment process. Customer installations receive only their TG
Pool API key, never the provider credentials.

### Signer fails during startup

Verify the vault file, Fernet key, signer state path, treasury address, token
contract, network, and TRON endpoint. The signer validates the on-chain token
contract at startup and therefore requires network access.

### Tests cannot create temporary databases

Run the terminal with permission to write to the system temporary directory,
or configure `TEMP` and `TMP` to point to a writable development directory.

## Additional documentation

- `ARCHITECTURE.md` — security and ownership boundaries
- `user/README.md` — customer-side component summary
- `admin/README.md` — administrator service summary
- `admin/contracts/README.md` — API contract workflow
- `admin/services/payment_server/README.md` — payment and withdrawal details
- `admin/services/payment_signer/README.md` — signer vault operations
