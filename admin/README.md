# TG Pool administrator platform

This tree owns all central authority and privileged operations. It must never be
included in the customer installer.

## Applications and services

- `apps/admin-desktop` — private operator UI.
- `services/license_server` — public activation and private key management APIs.
- `services/payment_server` — customer payments, private administration, and webhooks.
- `services/payment_signer` — isolated TRON key vault and signing API.
- `contracts` — versioned HTTP contracts consumed by released clients.

## Isolated entry points

Run commands from `admin/services` so each service package is importable:

```powershell
uvicorn license_server.public_app:app --host 0.0.0.0 --port 8100
uvicorn license_server.admin_app:app --host 127.0.0.1 --port 8110
uvicorn payment_server.public_app:app --host 0.0.0.0 --port 8200
uvicorn payment_server.admin_app:app --host 127.0.0.1 --port 8210
uvicorn payment_server.webhook_app:app --host 127.0.0.1 --port 8220
uvicorn payment_signer.app:app --host 127.0.0.1 --port 8300
```

Public, administrator, webhook, and signer processes must use distinct
environment files and service identities. Never deploy the compatibility
`license_server.app:app` or `payment_server.app:app` entry points publicly.
