import json

from cryptography.fernet import Fernet

from payment_signer.keyvault import KeyVault, _encrypt, _initialize


def test_key_vault_round_trip(tmp_path):
    source = tmp_path / "keys.json"
    encrypted = tmp_path / "keys.enc"
    key = Fernet.generate_key().decode("ascii")
    source.write_text(
        json.dumps({"TTestAddress111111111111111111111111": "ab" * 32}),
        encoding="utf-8",
    )

    _encrypt(str(source), str(encrypted), key)
    vault = KeyVault.load(str(encrypted), key)

    assert vault.addresses() == ["TTestAddress111111111111111111111111"]
    assert vault.private_key_hex(vault.addresses()[0]) == "ab" * 32


def test_wallet_creation_is_encrypted_and_idempotent(tmp_path):
    encrypted = tmp_path / "keys.enc"
    key = Fernet.generate_key().decode("ascii")
    _initialize(str(encrypted), key)

    vault = KeyVault.load(str(encrypted), key)
    address = vault.create_wallet("telegram:123")
    assert vault.create_wallet("telegram:123") == address

    reloaded = KeyVault.load(str(encrypted), key)
    assert reloaded.create_wallet("telegram:123") == address
    assert len(reloaded.private_key_hex(address)) == 64
    assert address.encode("ascii") not in encrypted.read_bytes()
