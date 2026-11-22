"""DEMONSTRATION DATA: NOT REAL BUSINESS RECORDS.

A small, completely made-up data set for showing and testing BALANSE. The
products, quantities, costs and sales are invented. Nothing here comes from a
real company or from the key informant interviews.

All products belong to ONE category, as the paper requires. The category name
can be changed (DEMO_CATEGORY in .env) because the paper says the final
category will be chosen from the interviews; the made-up product names below
are drinks and should be replaced when that category is decided.

Every date is counted back from "today", so the demo always looks current.
The data set includes a product for every status and the special cases the
paper lists for the dry run: zero sales, zero stock, a long lead time, stock
exactly at a limit, stock-out days in the history and a changing sales rate.

EXPECTED_STATUS is the hand-worked answer key for the DEFAULT settings
(sales period 30 days, buffer 3 days, maximum 30 days, target 14 days).
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Optional

from .engine import OPTIMAL, NO_SALES, OVERSTOCK, STOCKOUT, UNDERSTOCK

LABEL = "DEMONSTRATION DATA"
DEFAULT_CATEGORY = "Beverages"
HISTORY_DAYS = 60

# name, stock, unit cost, lead time, pattern, expected status with default settings, hand working
PRODUCTS = [
    ("Demo Cola 1.5 L (case of 12)", 18, 420.00, 5, ("daily", 8), STOCKOUT,
     "8 a day; 18 / 8 = 2.25 days, less than the 5-day lead time (the paper's Product A)"),
    ("Demo Bottled Water 500 mL (case of 24)", 0, 180.00, 3, ("sold_out_today", 10), STOCKOUT,
     "current stock is 0"),
    ("Demo Orange Juice 1 L (case of 12)", 30, 660.00, 5, ("daily", 6), UNDERSTOCK,
     "6 a day; 30 / 6 = 5 days = lead time exactly, below lead + buffer (8)"),
    ("Demo Iced Tea 500 mL (case of 24)", 35, 480.00, 5, ("daily", 5), UNDERSTOCK,
     "5 a day; 35 / 5 = 7 days, covers lead time (5) but below 8"),
    ("Demo Soda Water 330 mL (case of 24)", 32, 390.00, 5, ("daily", 4), OPTIMAL,
     "4 a day; 32 / 4 = 8 days = lead + buffer exactly"),
    ("Demo Energy Drink 250 mL (case of 24)", 150, 960.00, 4, ("daily", 10), OPTIMAL,
     "10 a day; 150 / 10 = 15 days, between 7 and 30"),
    ("Demo Chocolate Milk 1 L (case of 12)", 150, 780.00, 7, ("daily", 5), OPTIMAL,
     "5 a day; 150 / 5 = 30 days = maximum exactly"),
    ("Demo Lemon Soda 1.5 L (case of 12)", 180, 400.00, 5, ("daily", 3), OVERSTOCK,
     "3 a day; 180 / 3 = 60 days, above 30; excess = 180 - 30 x 3 = 90 units"),
    ("Demo Sparkling Grape Juice 750 mL (case of 6)", 500, 540.00, 7, ("weekly", 15), OVERSTOCK,
     "15 once a week (batch orders); 5 sale days in 30 days = 75 units; 75 / 30 = 2.5 a day; 500 / 2.5 = 200 days"),
    ("Demo Soy Milk 1 L (case of 12)", 40, 720.00, 6, ("none", 0), NO_SALES,
     "no sales in the period while 40 units remain"),
    ("Demo Coconut Water 330 mL (case of 24)", 60, 840.00, 5, ("outage", 6), OPTIMAL,
     "out of stock for 10 of the 30 days; 120 units / 20 in-stock days = 6 a day; 60 / 6 = 10 days"),
    ("Demo Sports Drink 500 mL (case of 24)", 96, 600.00, 6, ("rising", 4, 12), OPTIMAL,
     "4 a day, then 12 a day for the last 15 days; 240 / 30 = 8 a day; 96 / 8 = 12 days (a 14-day period gives Understock)"),
    ("Demo Mineral Water 5 gal (refill)", 44, 35.00, 20, ("daily", 2), UNDERSTOCK,
     "long lead time; 2 a day; 44 / 2 = 22 days, covers 20 but below 23"),
    ("Demo Ginger Ale 330 mL (case of 24)", 100, 450.00, 5, ("new", 4), OPTIMAL,
     "added 5 days ago; 20 units / 5 days = 4 a day; 100 / 4 = 25 days"),
]

EXPECTED_STATUS = {row[0]: row[5] for row in PRODUCTS}
HAND_WORKING = {row[0]: row[6] for row in PRODUCTS}


def _sales_for(pattern: tuple, as_of: date) -> dict[date, float]:
    """Made-up units sold per day for one product."""
    kind = pattern[0]
    out: dict[date, float] = {}
    for back in range(HISTORY_DAYS):
        day = as_of - timedelta(days=back)
        if kind == "daily":
            out[day] = pattern[1]
        elif kind == "sold_out_today":       # sold every day until it ran out; nothing today
            if back >= 1:
                out[day] = pattern[1]
        elif kind == "weekly":               # one batch order a week
            if back % 7 == 1:
                out[day] = pattern[1]
        elif kind == "outage":               # out of stock from 20 to 11 days ago
            if not 11 <= back <= 20:
                out[day] = pattern[1]
        elif kind == "rising":               # slower before, faster in the last 15 days
            out[day] = pattern[2] if back < 15 else pattern[1]
        elif kind == "new":                  # only 5 days of history
            if back < 5:
                out[day] = pattern[1]
    return out


def _stock_history(current: float, sales: dict[date, float], pattern: tuple, as_of: date, first_day: date) -> dict[date, float]:
    """Made-up end-of-day stock, worked backwards from today's stock, with deliveries now and then."""
    typical = max(sales.values(), default=0)
    ceiling = max(current * 1.5, typical * 25, 40)
    delivery = round(ceiling * 0.6)
    records = {as_of: float(current)}
    level, day = float(current), as_of
    while day > first_day:
        level += sales.get(day, 0)           # yesterday's closing stock = today's + what was sold today
        if level > ceiling:
            level -= delivery                # a delivery arrived today
        day -= timedelta(days=1)
        records[day] = max(level, 1.0)
    if pattern[0] == "outage":
        for back in range(11, 21):
            records[as_of - timedelta(days=back)] = 0.0
    return records


def build(as_of: Optional[date] = None, category: Optional[str] = None) -> dict:
    """Return {"products": [...], "sales": [...], "stock_records": [...]} keyed by product name."""
    as_of = as_of or date.today()
    category = (category or os.environ.get("DEMO_CATEGORY") or DEFAULT_CATEGORY).strip() or DEFAULT_CATEGORY
    products, sales_rows, stock_rows = [], [], []
    for name, stock, cost, lead, pattern, _status, _working in PRODUCTS:
        history = 5 if pattern[0] == "new" else HISTORY_DAYS
        first_day = as_of - timedelta(days=history - 1)
        products.append({"name": name, "category": category, "current_stock": float(stock), "unit_cost": float(cost),
                         "lead_time_days": lead, "created_at": first_day.isoformat() + "T00:00:00+00:00"})
        sales = _sales_for(pattern, as_of)
        for day in sorted(sales):
            sales_rows.append({"name": name, "sale_date": day, "quantity_sold": float(sales[day])})
        for day, qty in sorted(_stock_history(stock, sales, pattern, as_of, first_day).items()):
            stock_rows.append({"name": name, "record_date": day, "stock_quantity": float(qty)})
    return {"products": products, "sales": sales_rows, "stock_records": stock_rows}
