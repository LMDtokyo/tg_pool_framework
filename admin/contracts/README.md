# API contracts

The JSON documents in this directory are generated from the isolated FastAPI
entry points and are the only supported source-level exchange between central
services and released clients.

From `admin/services`, run:

```powershell
python ..\contracts\export_openapi.py
```

Contract files are versioned. Breaking changes require a new public API version;
released user clients remain pinned to the version they were generated against.
