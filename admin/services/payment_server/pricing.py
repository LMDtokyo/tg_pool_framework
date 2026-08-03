from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from payment_server.db.repository import money


@dataclass(frozen=True)
class RetailPricing:
    markup_percent: Decimal = Decimal("0")
    markup_fixed: Decimal = Decimal("0")

    @classmethod
    def from_values(
        cls,
        markup_percent: Decimal | str,
        markup_fixed: Decimal | str,
    ) -> "RetailPricing":
        try:
            percent = Decimal(str(markup_percent).strip() or "0")
            fixed = Decimal(str(markup_fixed).strip() or "0")
        except InvalidOperation as exc:
            raise RuntimeError("Retail markup values must be valid numbers") from exc
        if not percent.is_finite() or not fixed.is_finite():
            raise RuntimeError("Retail markup values must be finite")
        if percent < 0 or fixed < 0:
            raise RuntimeError("Retail markup values cannot be negative")
        return cls(markup_percent=money(percent), markup_fixed=money(fixed))

    @classmethod
    def from_env(cls) -> "RetailPricing":
        return cls.from_values(
            os.getenv("PAYMENT_RETAIL_MARKUP_PERCENT", "0"),
            os.getenv("PAYMENT_RETAIL_MARKUP_FIXED", "0"),
        )

    def price(self, wholesale_price: Decimal | str) -> Decimal:
        wholesale = money(wholesale_price)
        if wholesale < 0:
            raise ValueError("Wholesale price cannot be negative")
        multiplier = Decimal("1") + (self.markup_percent / Decimal("100"))
        return money((wholesale * multiplier) + self.markup_fixed)
