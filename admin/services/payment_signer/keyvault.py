from __future__ import annotations

import argparse
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Mapping

from cryptography.fernet import Fernet, InvalidToken


class KeyVaultError(RuntimeError):
    pass


class KeyVault:
    def __init__(
        self,
        keys: Mapping[str, str],
        *,
        wallet_requests: Mapping[str, str] | None = None,
        path: str | None = None,
        encryption_key: str | None = None,
    ) -> None:
        self._keys = {address.strip(): key.strip() for address, key in keys.items()}
        self._wallet_requests = {
            request_id.strip(): address.strip()
            for request_id, address in (wallet_requests or {}).items()
        }
        self._path = Path(path) if path else None
        self._encryption_key = encryption_key
        self._lock = threading.Lock()

    @classmethod
    def load(cls, path: str, encryption_key: str) -> "KeyVault":
        try:
            encrypted = Path(path).read_bytes()
            plaintext = Fernet(encryption_key.encode("ascii")).decrypt(encrypted)
            payload = json.loads(plaintext)
        except (OSError, ValueError, InvalidToken, json.JSONDecodeError) as exc:
            raise KeyVaultError("Unable to decrypt the signer key vault") from exc
        if not isinstance(payload, dict):
            raise KeyVaultError("Signer key vault must contain a JSON object")
        if "keys" in payload or "wallet_requests" in payload:
            keys = payload.get("keys", {})
            wallet_requests = payload.get("wallet_requests", {})
        else:
            keys = payload
            wallet_requests = {}
        if not isinstance(keys, dict) or not isinstance(wallet_requests, dict):
            raise KeyVaultError("Signer key vault contains invalid entries")
        if not all(
            isinstance(address, str) and isinstance(key, str)
            for address, key in keys.items()
        ):
            raise KeyVaultError("Signer key vault contains invalid keys")
        if not all(
            isinstance(request_id, str) and isinstance(address, str)
            for request_id, address in wallet_requests.items()
        ):
            raise KeyVaultError("Signer key vault contains invalid wallet requests")
        if any(address not in keys for address in wallet_requests.values()):
            raise KeyVaultError("Signer wallet request references an unknown key")
        return cls(
            keys,
            wallet_requests=wallet_requests,
            path=path,
            encryption_key=encryption_key,
        )

    def private_key_hex(self, address: str) -> str:
        with self._lock:
            value = self._keys.get(address.strip())
            if not value:
                raise KeyVaultError("No signing key is configured for this wallet")
            return value

    def addresses(self) -> list[str]:
        with self._lock:
            return list(self._keys)

    def create_wallet(self, request_id: str) -> str:
        from tronpy.keys import PrivateKey

        normalized = request_id.strip()
        if not normalized or len(normalized) > 200:
            raise KeyVaultError("Wallet request ID must contain 1 to 200 characters")
        if self._path is None or not self._encryption_key:
            raise KeyVaultError("Signer key vault is not writable")
        with self._lock:
            existing = self._wallet_requests.get(normalized)
            if existing:
                return existing
            private_key = PrivateKey.random()
            address = private_key.public_key.to_base58check_address()
            updated_keys = dict(self._keys)
            updated_requests = dict(self._wallet_requests)
            updated_keys[address] = private_key.hex()
            updated_requests[normalized] = address
            _write_encrypted_payload(
                self._path,
                {
                    "version": 2,
                    "keys": updated_keys,
                    "wallet_requests": updated_requests,
                },
                self._encryption_key,
            )
            self._keys = updated_keys
            self._wallet_requests = updated_requests
            return address


def _write_encrypted_payload(
    output_path: str | Path, payload: Mapping[str, Any], encryption_key: str
) -> None:
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    encrypted = Fernet(encryption_key.encode("ascii")).encrypt(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    )
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=destination.parent, delete=False
        ) as temporary:
            temporary.write(encrypted)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = temporary.name
        os.replace(temporary_path, destination)
    except OSError as exc:
        raise KeyVaultError("Unable to persist the encrypted signer key vault") from exc
    finally:
        if temporary_path:
            try:
                Path(temporary_path).unlink(missing_ok=True)
            except OSError:
                pass


def _encrypt(input_path: str, output_path: str, encryption_key: str) -> None:
    source = Path(input_path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not payload:
        raise SystemExit("Input must be a non-empty JSON address-to-private-key object")
    _write_encrypted_payload(output_path, payload, encryption_key)


def _initialize(output_path: str, encryption_key: str) -> None:
    if Path(output_path).exists():
        raise SystemExit("Refusing to overwrite an existing signer key vault")
    _write_encrypted_payload(
        output_path,
        {"version": 2, "keys": {}, "wallet_requests": {}},
        encryption_key,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an encrypted payment signer vault")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("generate-key", help="Generate a Fernet vault encryption key")
    initialize = subparsers.add_parser("init", help="Create an empty encrypted vault")
    initialize.add_argument("--output", required=True)
    encrypt = subparsers.add_parser("encrypt", help="Encrypt an address/private-key JSON file")
    encrypt.add_argument("--input", required=True)
    encrypt.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "generate-key":
        print(Fernet.generate_key().decode("ascii"))
    else:
        encryption_key = os.getenv("SIGNER_VAULT_KEY", "").strip()
        if not encryption_key:
            raise SystemExit("SIGNER_VAULT_KEY must be set")
        if args.command == "init":
            _initialize(args.output, encryption_key)
        else:
            _encrypt(args.input, args.output, encryption_key)


if __name__ == "__main__":
    main()
