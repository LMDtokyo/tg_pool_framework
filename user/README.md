# TG Pool user product

This tree is the complete customer-delivered product. It contains no
administrator application, central service implementation, or wallet signer.

## Components

- `apps/desktop` — Windows customer UI.
- `apps/activator` — license activation helper.
- `apps/website` — public customer website.
- `services/local-agent` — loopback-only Python control API and Telegram engine.
- `packages/desktop-common` — code shared only by customer desktop applications.
- `packaging/windows-installer` — customer release packaging.

## Development

Run Python tests from `services/local-agent`:

```powershell
python -m pytest
```

Build the desktop projects from this directory:

```powershell
dotnet build TgPool.User.slnx
```

Build the website from `apps/website` with `pnpm build`.
