"""Price Market / Price Fluctuation — RESERVED FOR FUTURE DEVELOPMENT.

This module is deliberately a placeholder. The research team has not yet held
its specialist/economist consultation, so there is NO methodology here:
no formulas, no thresholds, no classification rules, no forecasts and no
price-based recommendations. Nothing in this file is used by the inventory
risk calculations in engine.py, and it must stay that way until the team
approves a method based on the specialist's actual statements.

What exists, so the feature can be added later without restructuring the app:
  * its own page in the navigation (views_misc.price_market)
  * an empty `price_records` table in the database (see sql/schema.sql)
  * the proposed record layout below

When the interview transcript and the team's decisions are available:
  1. read them first;
  2. implement only what they support, in this module;
  3. add repository methods for price_records;
  4. keep the results out of engine.py unless the team decides otherwise.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

STATUS = "Coming soon"

#: Proposed structural placeholders only. They are NOT finalized research requirements.
PROPOSED_FIELDS = [
    ("Product", "Which product the price is for"),
    ("Market or supplier", "Where the price was observed"),
    ("Recorded price", "The price that was seen"),
    ("Price unit", "What the price is per (piece, case, kilogram)"),
    ("Date recorded", "When the price was seen"),
    ("Data source", "Who or what reported the price"),
]


@dataclass
class PriceRecord:
    """Proposed shape of one saved price. Not used anywhere yet."""
    product_id: Optional[int] = None
    market_or_supplier: Optional[str] = None
    recorded_price: Optional[float] = None
    price_unit: Optional[str] = None
    date_recorded: Optional[date] = None
    data_source: Optional[str] = None


def analyze(*_args, **_kwargs):
    """Not implemented on purpose. See the module note above."""
    raise NotImplementedError(
        "Price analysis is not implemented. Its method will be based on a future specialist/economist consultation.")
