# Administrator/user separation

## Boundary

The customer installation is built exclusively from `user`. Central and
privileged deployments are built exclusively from `admin`. Neither side may
reference the other side's source code or build output.

Allowed communication crosses an authenticated, versioned HTTP interface:

```text
Customer desktop -> loopback local agent -> public central APIs
Admin desktop -> private admin APIs -> domain services -> private signer
Chain watcher -> dedicated webhook API
```

## Data ownership

Customer machines own Telegram sessions, accounts, proxies, campaigns, exports,
local logs, preferences, and cached signed license responses. Central services
own license records, customer identities, API-key hashes, ledgers, pricing,
orders, deposits, withdrawals, wallet addresses, and audit records. Only the
wallet signer owns private wallet keys.

## Network exposure

- `license_server.public_app` and `payment_server.public_app` may be internet-facing.
- `license_server.admin_app` and `payment_server.admin_app` are private operations APIs.
- `payment_server.webhook_app` accepts only authenticated machine callbacks.
- `payment_signer.app` is private and may be reached only by the payment service.
- The user local agent binds to loopback and requires its per-launch token.

The legacy combined service applications remain temporarily available for
compatibility tests. Deployment documentation permits only the isolated entry
points above.
