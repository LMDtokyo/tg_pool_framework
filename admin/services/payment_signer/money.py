from __future__ import annotations

from decimal import Decimal
from typing import Any


TOKEN_QUANTUM = Decimal("0.00000001")


def token_amount(value: Any) -> Decimal:
    result = Decimal(str(value)).quantize(TOKEN_QUANTUM)
    if not result.is_finite():
        raise ValueError("Amount must be finite")
    return result
