from decimal import Decimal

from tronpy.keys import PrivateKey

from payment_signer.chain import TronSweepService
from payment_signer.keyvault import KeyVault


PRIVATE_KEY = "01".zfill(64)
SOURCE_ADDRESS = PrivateKey.fromhex(PRIVATE_KEY).public_key.to_base58check_address()


class FakeBroadcast:
    txid = "tron-tx-1"


class FakeTransaction:
    txid = "tron-tx-1"

    def sign(self, key):
        assert key.public_key.to_base58check_address() == SOURCE_ADDRESS
        return self

    def broadcast(self):
        return FakeBroadcast()


class FakeBuilder:
    def __init__(self, calls):
        self.calls = calls

    def with_owner(self, address):
        self.calls.append(("owner", address))
        return self

    def fee_limit(self, amount):
        self.calls.append(("fee_limit", amount))
        return self

    def build(self):
        return FakeTransaction()


class FakeFunctions:
    def __init__(self, calls):
        self.calls = calls

    def decimals(self):
        return 6

    def balanceOf(self, address):
        self.calls.append(("balance", address))
        return 12_500_000

    def transfer(self, destination, amount):
        self.calls.append(("transfer", destination, amount))
        return FakeBuilder(self.calls)


class FakeContract:
    def __init__(self, calls):
        self.functions = FakeFunctions(calls)


class FakeClient:
    def __init__(self):
        self.calls = []

    def is_address(self, address):
        return address.startswith("T")

    def get_contract(self, address):
        self.calls.append(("contract", address))
        return FakeContract(self.calls)

    def get_account_balance(self, address):
        self.calls.append(("trx_balance", address))
        return Decimal("987.455")


def test_sweep_signs_exact_amount_to_allowlisted_treasury(monkeypatch):
    treasury = "TTreasuryAddress111111111111111111111"
    contract = "TTokenContract11111111111111111111111"
    fake_client = FakeClient()
    monkeypatch.setenv("SIGNER_TREASURY_ADDRESS", treasury)
    monkeypatch.setenv("SIGNER_TRC20_CONTRACT", contract)
    monkeypatch.setenv("SIGNER_FEE_LIMIT_SUN", "100000000")
    monkeypatch.setattr(
        TronSweepService,
        "_build_client",
        lambda self: fake_client,
    )

    service = TronSweepService(KeyVault({SOURCE_ADDRESS: PRIVATE_KEY}))
    result = service.sweep(SOURCE_ADDRESS, Decimal("4.25"))

    assert result.transaction_hash == "tron-tx-1"
    assert result.balance_before == Decimal("12.50000000")
    assert ("transfer", treasury, 4_250_000) in fake_client.calls
    assert ("owner", SOURCE_ADDRESS) in fake_client.calls
    assert ("fee_limit", 100_000_000) in fake_client.calls


def test_treasury_address_can_be_changed_after_validation(monkeypatch):
    monkeypatch.setenv("SIGNER_TREASURY_ADDRESS", "TInitialTreasury111111111111111111111")
    monkeypatch.setenv("SIGNER_TRC20_CONTRACT", "TTokenContract11111111111111111111111")
    monkeypatch.setattr(TronSweepService, "_build_client", lambda self: FakeClient())

    service = TronSweepService(KeyVault({SOURCE_ADDRESS: PRIVATE_KEY}))
    updated = "TUpdatedTreasury111111111111111111111"

    assert service.set_treasury_address(updated) == updated
    assert service.treasury_address == updated


def test_balance_reads_public_trc20_balance_without_vault_key(monkeypatch):
    treasury = "TTreasuryAddress111111111111111111111"
    fake_client = FakeClient()
    monkeypatch.setenv("SIGNER_TREASURY_ADDRESS", treasury)
    monkeypatch.setenv("SIGNER_TRC20_CONTRACT", "TTokenContract11111111111111111111111")
    monkeypatch.setattr(TronSweepService, "_build_client", lambda self: fake_client)

    service = TronSweepService(KeyVault({SOURCE_ADDRESS: PRIVATE_KEY}))

    assert service.balance(treasury) == Decimal("12.50000000")
    assert ("balance", treasury) in fake_client.calls


def test_trx_balance_reads_native_account_balance_without_vault_key(monkeypatch):
    treasury = "TTreasuryAddress111111111111111111111"
    fake_client = FakeClient()
    monkeypatch.setenv("SIGNER_TREASURY_ADDRESS", treasury)
    monkeypatch.setenv("SIGNER_TRC20_CONTRACT", "TTokenContract11111111111111111111111")
    monkeypatch.setattr(TronSweepService, "_build_client", lambda self: fake_client)

    service = TronSweepService(KeyVault({SOURCE_ADDRESS: PRIVATE_KEY}))

    assert service.trx_balance(treasury) == Decimal("987.45500000")
    assert ("trx_balance", treasury) in fake_client.calls
