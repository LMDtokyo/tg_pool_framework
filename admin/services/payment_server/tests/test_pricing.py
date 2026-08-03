from decimal import Decimal

import pytest

from payment_server.pricing import RetailPricing


def test_retail_price_applies_percentage_and_fixed_markup():
    pricing = RetailPricing(
        markup_percent=Decimal("12.5"),
        markup_fixed=Decimal("0.20"),
    )

    assert pricing.price("4.00") == Decimal("4.70000000")


def test_retail_pricing_loads_from_environment(monkeypatch):
    monkeypatch.setenv("PAYMENT_RETAIL_MARKUP_PERCENT", "15")
    monkeypatch.setenv("PAYMENT_RETAIL_MARKUP_FIXED", "0.10")

    pricing = RetailPricing.from_env()

    assert pricing.price("2") == Decimal("2.40000000")


def test_retail_pricing_from_values():
    pricing = RetailPricing.from_values("10", "0.50")
    assert pricing.markup_percent == Decimal("10.00000000")
    assert pricing.markup_fixed == Decimal("0.50000000")
    assert pricing.price("3.50") == Decimal("4.35000000")


@pytest.mark.parametrize(
    ("percent", "fixed"),
    [
        ("not-a-number", "0"),
        ("0", "NaN"),
        ("-1", "0"),
        ("0", "-0.01"),
    ],
)
def test_retail_pricing_rejects_invalid_configuration(monkeypatch, percent, fixed):
    monkeypatch.setenv("PAYMENT_RETAIL_MARKUP_PERCENT", percent)
    monkeypatch.setenv("PAYMENT_RETAIL_MARKUP_FIXED", fixed)

    with pytest.raises(RuntimeError):
        RetailPricing.from_env()

    with pytest.raises(RuntimeError):
        RetailPricing.from_values(percent, fixed)
