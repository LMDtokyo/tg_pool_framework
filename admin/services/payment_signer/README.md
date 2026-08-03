# Isolated TRON signer

The signer is a private internal service that holds encrypted wallet keys and
is the only component allowed to sign TRC20 transfers. Do not expose it to the
public internet and do not run it with the payment API's environment file.

## Create the encrypted vault

Generate an encryption key:

```powershell
python -m payment_signer.keyvault generate-key
```

Set that value as `SIGNER_VAULT_KEY`, then initialize an empty encrypted vault:

```powershell
$env:SIGNER_VAULT_KEY="generated-fernet-key"
python -m payment_signer.keyvault init --output wallet-keys.enc
```

For migration, an existing address/private-key JSON mapping can be imported:

```json
{
  "TDepositAddress1": "64-character-private-key-hex",
  "TDepositAddress2": "64-character-private-key-hex"
}
```

Encrypt it instead of running `init`:

```powershell
$env:SIGNER_VAULT_KEY="generated-fernet-key"
python -m payment_signer.keyvault encrypt --input wallet-keys.json --output wallet-keys.enc
```

Securely erase any plaintext JSON after independently verifying the encrypted
vault. Keep `SIGNER_VAULT_KEY` in the signer host's secret manager, separate
from `wallet-keys.enc`. Back up the changing encrypted vault continuously;
losing either the vault or its encryption key makes wallet funds inaccessible.

## Signer configuration

Create `payment_signer/.env` on the signer host (see `.env.example`):

```env
PAYMENT_SIGNER_API_KEY=long-random-internal-secret
SIGNER_VAULT_FILE=/secure/path/wallet-keys.enc
SIGNER_VAULT_KEY=generated-fernet-key
SIGNER_AUTO_CREATE_WALLETS=1
SIGNER_STATE_DATABASE=/secure/path/signer-sweeps.db
SIGNER_TREASURY_ADDRESS=TAdminTreasuryAddress
SIGNER_TRC20_CONTRACT=TConfiguredTokenContract
SIGNER_TRON_NETWORK=nile
SIGNER_ASSET=USDT
SIGNER_FEE_LIMIT_SUN=100000000
SIGNER_TRON_HTTP_ENDPOINT=https://nile.trongrid.io
TRONGRID_API_KEY=
```

`SIGNER_TREASURY_ADDRESS` seeds a new signer state database. An authenticated
administrator-wallet change is stored in that database and takes precedence on
later restarts.

Relative `SIGNER_VAULT_FILE` / `SIGNER_STATE_DATABASE` paths resolve from the
`payment_signer` package directory. Override the env file with `SIGNER_ENV_FILE`
if needed. For Nile or Shasta with a TronGrid credential, set
`SIGNER_TRON_HTTP_ENDPOINT` explicitly to that testnet's endpoint.

Run one signer instance on a private network:

```powershell
uvicorn payment_signer.app:app --host 127.0.0.1 --port 8300
```

`POST /v1/wallets` is signer-authenticated and idempotent by request ID. It
generates a TRON key pair, atomically persists the private key in the encrypted
vault, and returns only the public address. Repeating the same Telegram `/start`
flow therefore cannot create another wallet for that player.

`SIGNER_STATE_DATABASE` is a local idempotency record. Back it up and run only
one signer process against that file. It contains transaction metadata, not
private keys.

Each source account needs enough delegated Energy/Bandwidth or TRX to execute
the TRC20 transfer. `SIGNER_FEE_LIMIT_SUN` is a transaction fee ceiling, not
the expected fee.
