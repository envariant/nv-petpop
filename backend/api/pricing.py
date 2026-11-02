"""What an order costs (decision 126): line items, so options and extras can each carry a price later. Today there is
one line, the figurine at PETPOP_PRICE_SGD (a placeholder until Nishant sets prices). A future rule reads the
composition (Contract 2: its parts, layers, shells and stamps) and adds lines; the payment asks for the total."""
from __future__ import annotations

import os
from decimal import Decimal
from typing import Any

from . import models as m

CURRENCY = "SGD"


def base_price() -> Decimal:
    return Decimal(os.environ.get("PETPOP_PRICE_SGD", "39.00")).quantize(Decimal("0.01"))


def quote(composition: dict[str, Any]) -> m.Quote:
    items = [("Figurine", base_price())]
    # Options and extras are priced here when they have prices: e.g. ("Collar", Decimal("4.00")) for a shell part.
    total = sum((a for _, a in items), Decimal("0.00"))
    return m.Quote(items=[m.QuoteItem(label=label, amount=f"{a:.2f}") for label, a in items],
                   total=m.Price(amount=f"{total:.2f}", currency=CURRENCY))
