"""BALANSE calculation engine.

Pure functions only: no Streamlit, no database, no file access. Everything the
research paper defines as a formula or a classification rule lives here, so it
can be tested on its own against a hand-worked answer key.

Source: "BALANSE: A Web-Based Inventory Risk and Decision-Support System ..."
  Feature 2   Average daily sales = units sold in the period / days the product was in stock
              Days of supply      = current stock / average daily sales
  Table 5     The five statuses and their rules
  Feature 6   Target stock = average daily sales x target days of supply
              Suggested reorder quantity = target stock - current stock (never below 0;
              does not count units already on order)
  Feature 9   Excess units = current stock - (maximum days x average daily sales)
              Estimated excess value = excess units x unit cost
  Feature 10  Estimated days until stockout = current stock / average daily sales

Comparisons are done with exact fractions, so a value that sits exactly on a
limit (for example days of supply equal to the lead time) is always classified
the same way and never flips because of floating-point rounding.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from fractions import Fraction
from typing import Iterable, Mapping, Optional, Sequence

# ---------------------------------------------------------------- statuses
STOCKOUT = "Stockout risk"
UNDERSTOCK = "Understock risk"
OPTIMAL = "Optimal"
OVERSTOCK = "Overstock risk"
NO_SALES = "No recent sales"

ALL_STATUSES = [STOCKOUT, UNDERSTOCK, NO_SALES, OPTIMAL, OVERSTOCK]

#: Order used for "most urgent first" lists. Lower number = more urgent.
URGENCY = {STOCKOUT: 0, UNDERSTOCK: 1, NO_SALES: 2, OVERSTOCK: 3, OPTIMAL: 4}

SUGGESTED_ACTIONS = {
    STOCKOUT: "Review the purchase order and consider replenishment.",
    UNDERSTOCK: "Consider increasing the next replenishment quantity.",
    OPTIMAL: "Continue monitoring current inventory.",
    OVERSTOCK: "Consider delaying or reviewing the next purchase.",
    NO_SALES: "Review the product's sales history and stock movement.",
}


# ---------------------------------------------------------------- settings
@dataclass(frozen=True)
class Settings:
    """Limits chosen by the user (Table 4, Data Input screen).

    The default numbers are PROVISIONAL. The paper says the defaults will be
    set after the key informant interviews (N4 to N7), which have not fixed
    them yet. Users can change all four on the Settings page.
    """
    sales_period_days: int = 30
    buffer_days: int = 3
    max_days_of_supply: int = 30
    target_days_of_supply: int = 14

    def as_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- helpers
def to_fraction(value) -> Fraction:
    """Exact fraction for an int, float, Decimal or numeric string."""
    if isinstance(value, Fraction):
        return value
    if isinstance(value, bool):
        raise TypeError("a true/false value is not a number")
    if isinstance(value, int):
        return Fraction(value)
    return Fraction(str(value))


def fmt(value, places: int = 1) -> str:
    """Readable number: 20 -> '20', 2.25 -> '2.3' (1 place), 2.0 -> '2'."""
    if value is None:
        return "n/a"
    number = round(float(value), places)
    if number == int(number):
        return f"{int(number):,}"
    return f"{number:,.{places}f}"


def plural(value, word: str) -> str:
    return f"{fmt(value)} {word}" + ("" if float(value) == 1 else "s")


def period_window(as_of: date, sales_period_days: int) -> tuple[date, date]:
    """First and last day of the sales period. The period ends on `as_of` and is counted inclusively."""
    if sales_period_days < 1:
        raise ValueError("The sales period must be at least 1 day.")
    return as_of - timedelta(days=sales_period_days - 1), as_of


# ---------------------------------------------------------------- in-stock days
@dataclass(frozen=True)
class DayCount:
    days_in_period: int        # days of the period that are on or after the product's first record
    days_in_stock: int         # days counted as "in stock" (the divisor of average daily sales)
    out_of_stock_days: tuple   # the days left out


def count_in_stock_days(
    period_start: date,
    period_end: date,
    sales_by_day: Mapping[date, float],
    stock_records: Iterable[tuple[date, float]],
    tracking_start: Optional[date] = None,
) -> DayCount:
    """Count the days in the period on which the product was available for sale.

    The paper says to divide by "the number of days the product was in stock"
    but does not say how to tell. BALANSE uses this rule (see docs/FORMULAS.md):

      * A day counts as OUT of stock when the latest stock record on or before
        that day shows 0 units AND nothing was sold that day.
      * A day with a sale always counts as in stock (something was on the shelf).
      * A day with no stock record before it counts as in stock.
      * Days before the product's first record (`tracking_start`) are not counted
        at all, so a product added last week is not averaged over a whole month.
    """
    first = period_start
    if tracking_start is not None and tracking_start > first:
        first = tracking_start
    if first > period_end:
        return DayCount(0, 0, ())

    records = sorted((d, float(q)) for d, q in stock_records)
    index, last_qty = 0, None
    in_stock, out_days = 0, []
    day = first
    while day <= period_end:
        while index < len(records) and records[index][0] <= day:
            last_qty = records[index][1]
            index += 1
        sold_today = float(sales_by_day.get(day, 0) or 0) > 0
        if last_qty is not None and last_qty <= 0 and not sold_today:
            out_days.append(day)
        else:
            in_stock += 1
        day += timedelta(days=1)
    return DayCount((period_end - first).days + 1, in_stock, tuple(out_days))


# ---------------------------------------------------------------- core formulas
def average_daily_sales(total_units_sold, days_in_stock) -> Optional[Fraction]:
    """Average daily sales = total units sold / days the product was in stock.

    Returns None when the product was not in stock on any day of the period,
    because the average cannot be worked out (never divides by zero).
    """
    if days_in_stock is None or days_in_stock <= 0:
        return None
    return to_fraction(total_units_sold) / to_fraction(days_in_stock)


def days_of_supply(current_stock, avg_daily_sales) -> Optional[Fraction]:
    """Days of supply = current stock / average daily sales.

    Returns None when there are no sales to divide by ("No recent sales").
    """
    if avg_daily_sales is None or avg_daily_sales <= 0:
        return None
    return to_fraction(current_stock) / to_fraction(avg_daily_sales)


def classify(current_stock, days_supply, lead_time_days, buffer_days, max_days_of_supply) -> str:
    """Apply Table 5, in this order of precedence:

      1. Stockout risk    current stock is 0, or days of supply < lead time
      2. No recent sales  stock remains but days of supply cannot be calculated
      3. Understock risk  lead time <= days of supply < lead time + buffer days
      4. Optimal          lead time + buffer days <= days of supply <= maximum days
      5. Overstock risk   days of supply > maximum days
    """
    stock = to_fraction(current_stock)
    if stock <= 0:
        return STOCKOUT
    if days_supply is None:
        return NO_SALES
    dos = to_fraction(days_supply)
    lead = to_fraction(lead_time_days)
    if dos < lead:
        return STOCKOUT
    if dos < lead + to_fraction(buffer_days):
        return UNDERSTOCK
    if dos <= to_fraction(max_days_of_supply):
        return OPTIMAL
    return OVERSTOCK


def target_stock(avg_daily_sales, target_days_of_supply) -> Optional[Fraction]:
    """Target stock = average daily sales x target days of supply."""
    if avg_daily_sales is None:
        return None
    return to_fraction(avg_daily_sales) * to_fraction(target_days_of_supply)


def suggested_reorder_quantity(current_stock, avg_daily_sales, target_days_of_supply) -> Optional[Fraction]:
    """Suggested reorder quantity = target stock - current stock, never below 0.

    Units already on order are NOT counted (the paper says the formula does
    not yet count them). This is a quantity for the user to review, not an order.
    """
    target = target_stock(avg_daily_sales, target_days_of_supply)
    if target is None:
        return None
    return max(Fraction(0), target - to_fraction(current_stock))


def excess_units(current_stock, avg_daily_sales, max_days_of_supply) -> Optional[Fraction]:
    """Excess units = current stock - (maximum days x average daily sales), never below 0.

    Returns None when there are no recent sales: with no sales rate the formula
    would call ALL stock "excess", which the paper does not claim. For those
    products BALANSE shows the current stock and lets the user judge (Table 5).
    """
    if avg_daily_sales is None or avg_daily_sales <= 0:
        return None
    return max(Fraction(0), to_fraction(current_stock) - to_fraction(max_days_of_supply) * to_fraction(avg_daily_sales))


def estimated_excess_value(excess, unit_cost) -> Optional[Fraction]:
    """Estimated money tied up in excess stock = excess units x unit cost (an estimate)."""
    if excess is None:
        return None
    return to_fraction(excess) * to_fraction(unit_cost)


# ---------------------------------------------------------------- explanation
def explain(status: str, *, stock, ads, dos, lead, buffer_days, max_days, period_days,
            days_in_stock, total_sold, excess) -> tuple[str, str]:
    """Plain-language reason for a status, with the numbers used, and the rule that was met."""
    lead_txt = plural(lead, "day")
    if status == STOCKOUT and to_fraction(stock) <= 0:
        reason = (f"This product is out of stock (current stock is 0). Your supplier needs {lead_txt} to deliver, "
                  "so no stock is available until the next replenishment arrives.")
        if ads is not None and ads > 0:
            reason += f" It was selling about {fmt(ads)} units per day."
        return reason, "Rule met: current stock is 0."
    if status == STOCKOUT:
        gap = to_fraction(lead) - dos
        reason = ("Your current stock may run out before your next replenishment arrives. "
                  f"Your stock of {fmt(stock)} units is estimated to last {plural(dos, 'day')} at about {fmt(ads)} units per day, "
                  f"while your supplier needs {lead_txt} to deliver. That is about {plural(gap, 'day')} short.")
        return reason, f"Rule met: days of supply ({fmt(dos)}) are less than the replenishment lead time ({fmt(lead)})."
    if status == UNDERSTOCK:
        limit = to_fraction(lead) + to_fraction(buffer_days)
        reason = ("Your stock covers the replenishment lead time, but it does not meet your buffer days. "
                  f"Your stock of {fmt(stock)} units is estimated to last {plural(dos, 'day')} at about {fmt(ads)} units per day. "
                  f"Lead time ({lead_txt}) plus buffer ({plural(buffer_days, 'day')}) is {plural(limit, 'day')}.")
        return reason, (f"Rule met: days of supply ({fmt(dos)}) cover the lead time ({fmt(lead)}) "
                        f"but are less than lead time plus buffer days ({fmt(limit)}).")
    if status == OPTIMAL:
        limit = to_fraction(lead) + to_fraction(buffer_days)
        reason = ("Your current inventory is within your stock coverage limits. "
                  f"Your stock of {fmt(stock)} units is estimated to last {plural(dos, 'day')} at about {fmt(ads)} units per day, "
                  f"which is between lead time plus buffer ({plural(limit, 'day')}) and your maximum ({plural(max_days, 'day')}).")
        return reason, (f"Rule met: days of supply ({fmt(dos)}) are from lead time plus buffer days ({fmt(limit)}) "
                        f"up to the maximum days ({fmt(max_days)}).")
    if status == OVERSTOCK:
        reason = ("Your inventory exceeds your maximum days of supply. "
                  f"Your stock of {fmt(stock)} units is estimated to last {plural(dos, 'day')} at about {fmt(ads)} units per day, "
                  f"while your maximum is {plural(max_days, 'day')}. About {fmt(excess)} units are above that limit. "
                  "Consider reviewing your next purchasing decision.")
        return reason, f"Rule met: days of supply ({fmt(dos)}) are more than the maximum days ({fmt(max_days)})."
    # No recent sales
    if days_in_stock == 0:
        reason = (f"The product was not in stock on any day of the last {plural(period_days, 'day')}, so there are no sales to measure. "
                  f"{fmt(stock)} units are in stock now. Days of supply cannot currently be calculated.")
    else:
        reason = (f"No sales were recorded during the last {plural(period_days, 'day')} while {fmt(stock)} units remain in stock. "
                  "Days of supply cannot currently be calculated. Check the current stock to judge whether it is too much.")
    return reason, "Rule met: no units were sold in the chosen period while stock remains."


# ---------------------------------------------------------------- one product
def analyze_product(
    product: Mapping,
    sales: Iterable[tuple[date, float]],
    stock_records: Iterable[tuple[date, float]],
    settings: Settings,
    as_of: date,
) -> dict:
    """Every number, the status, its reason and the suggested action for one product.

    product needs: id, name, category, current_stock, unit_cost, lead_time_days,
    and optionally created_on (a date).
    """
    stock = to_fraction(product["current_stock"])
    lead = int(product["lead_time_days"])
    unit_cost = to_fraction(product.get("unit_cost") or 0)
    start, end = period_window(as_of, settings.sales_period_days)

    sales = [(d, float(q)) for d, q in sales]
    records = [(d, float(q)) for d, q in stock_records]
    # Today's stock is known from the product itself, so it always counts as the record for today.
    records = [(d, q) for d, q in records if d != as_of] + [(as_of, float(stock))]

    sales_by_day: dict[date, float] = {}
    for day, qty in sales:
        if start <= day <= end:
            sales_by_day[day] = sales_by_day.get(day, 0.0) + qty
    total_sold = to_fraction(sum(to_fraction(q) for q in sales_by_day.values()))

    known_dates = [d for d, _ in sales] + [d for d, _ in records if d != as_of]
    created = product.get("created_on")
    if created:
        known_dates.append(created)
    tracking_start = min(known_dates) if known_dates else as_of

    count = count_in_stock_days(start, end, sales_by_day, records, tracking_start)
    ads = average_daily_sales(total_sold, count.days_in_stock)
    dos = days_of_supply(stock, ads)
    status = classify(stock, dos, lead, settings.buffer_days, settings.max_days_of_supply)

    excess = excess_units(stock, ads, settings.max_days_of_supply)
    excess_value = estimated_excess_value(excess, unit_cost)
    target = target_stock(ads, settings.target_days_of_supply)
    reorder = suggested_reorder_quantity(stock, ads, settings.target_days_of_supply)

    reason, rule = explain(
        status, stock=stock, ads=ads, dos=dos, lead=lead, buffer_days=settings.buffer_days,
        max_days=settings.max_days_of_supply, period_days=settings.sales_period_days,
        days_in_stock=count.days_in_stock, total_sold=total_sold, excess=excess)

    # Feature 10: simple projection (an estimate, not a prediction)
    runout_date = as_of + timedelta(days=math.floor(dos)) if dos is not None and stock > 0 else None
    gap_vs_lead = (dos - lead) if dos is not None else None

    def num(x):
        return None if x is None else float(x)

    return {
        "product_id": product.get("id"),
        "name": product.get("name"),
        "category": product.get("category"),
        "current_stock": num(stock),
        "unit_cost": num(unit_cost),
        "lead_time_days": lead,
        "period_start": start,
        "period_end": end,
        "days_in_period": count.days_in_period,
        "days_in_stock": count.days_in_stock,
        "out_of_stock_days": len(count.out_of_stock_days),
        "total_units_sold": num(total_sold),
        "avg_daily_sales": num(ads),
        "days_of_supply": num(dos),
        "status": status,
        "urgency": URGENCY[status],
        "explanation": reason,
        "rule": rule,
        "suggested_action": SUGGESTED_ACTIONS[status],
        "target_stock": num(target),
        "suggested_reorder_qty": num(reorder),
        # whole units to review: a part of a unit cannot be ordered, so it is rounded up
        "suggested_reorder_units": None if reorder is None else int(math.ceil(reorder)),
        "excess_units": num(excess),
        "estimated_excess_value": num(excess_value),
        "stock_value_at_cost": num(stock * unit_cost),
        "estimated_days_until_stockout": num(dos) if stock > 0 else (0.0 if stock <= 0 else None),
        "estimated_runout_date": runout_date,
        "gap_vs_lead_time_days": num(gap_vs_lead),
    }


def sort_key(result: Mapping):
    """Most urgent first: by status, then by fewest days of supply, then by name."""
    dos = result.get("days_of_supply")
    if result["status"] == OVERSTOCK:
        secondary = -(dos or 0)          # the most overstocked first
    else:
        secondary = dos if dos is not None else 0
    return (result["urgency"], secondary, str(result.get("name") or "").lower())


def analyze_all(
    products: Sequence[Mapping],
    sales: Iterable[Mapping],
    stock_records: Iterable[Mapping],
    settings: Settings,
    as_of: date,
) -> list[dict]:
    """Analyze every product. `sales` rows need product_id, sale_date, quantity_sold;
    `stock_records` rows need product_id, record_date, stock_quantity. Result is sorted most urgent first."""
    sales_by_product: dict = {}
    for row in sales:
        sales_by_product.setdefault(row["product_id"], []).append((row["sale_date"], row["quantity_sold"]))
    records_by_product: dict = {}
    for row in stock_records:
        records_by_product.setdefault(row["product_id"], []).append((row["record_date"], row["stock_quantity"]))
    results = [
        analyze_product(p, sales_by_product.get(p["id"], []), records_by_product.get(p["id"], []), settings, as_of)
        for p in products
    ]
    results.sort(key=sort_key)
    return results
