"""The answer key: test scenarios with expected results worked out by hand.

Used by tests/test_engine.py and by scripts/make_test_log.py (which writes
docs/TEST_LOG.md). Settings unless stated: sales period 30 days, buffer 3 days,
maximum 30 days, target 14 days. "Today" is 2026-11-10.

Each case: id, title, product, sales pattern, stock records, settings overrides,
expected values.
Sales patterns:  ("daily", units, days)        the same units on each of the last `days` days, including today
                 ("list", [(days_ago, units)]) explicit sales
"""
from datetime import date, timedelta

from balanse.engine import OPTIMAL, NO_SALES, OVERSTOCK, STOCKOUT, UNDERSTOCK

TODAY = date(2026, 11, 10)


def ago(days: int) -> date:
    return TODAY - timedelta(days=days)


def expand_sales(pattern):
    if pattern is None:
        return []
    if pattern[0] == "daily":
        return [(ago(i), pattern[1]) for i in range(pattern[2])]
    return [(ago(d), q) for d, q in pattern[1]]


def product(stock, lead, cost=10.0, created_days_ago=90):
    return {"id": 1, "name": "Test product", "category": "Test", "current_stock": stock, "unit_cost": cost,
            "lead_time_days": lead, "created_on": ago(created_days_ago)}


CASES = [
    # --- the 14 scenarios named in the project brief ---
    dict(id="S01", title="Sufficient inventory",
         product=product(150, 4), sales=("daily", 10, 30),
         working="ADS 300/30 = 10; DoS 150/10 = 15; 4+3 = 7 <= 15 <= 30",
         expect=dict(status=OPTIMAL, avg_daily_sales=10, days_of_supply=15, suggested_reorder_qty=0, excess_units=0)),
    dict(id="S02", title="May run out before delivery (paper's Product A)",
         product=product(18, 5), sales=("daily", 8, 30),
         working="ADS 240/30 = 8; DoS 18/8 = 2.25 < lead 5; short by 2.75 days; reorder 8x14 - 18 = 94",
         expect=dict(status=STOCKOUT, avg_daily_sales=8, days_of_supply=2.25, gap_vs_lead_time_days=-2.75,
                     target_stock=112, suggested_reorder_qty=94)),
    dict(id="S03", title="Insufficient buffer stock",
         product=product(35, 5), sales=("daily", 5, 30),
         working="ADS 5; DoS 7; lead 5 <= 7 < 5+3 = 8; reorder 5x14 - 35 = 35",
         expect=dict(status=UNDERSTOCK, avg_daily_sales=5, days_of_supply=7, suggested_reorder_qty=35)),
    dict(id="S04", title="Excessive stock (brief's example: 500 units, 10 a day, max 30)",
         product=product(500, 5, cost=20.0), sales=("daily", 10, 30),
         working="ADS 10; DoS 50 > 30; excess 500 - 30x10 = 200 units; value 200 x 20 = 4,000",
         expect=dict(status=OVERSTOCK, avg_daily_sales=10, days_of_supply=50, excess_units=200,
                     estimated_excess_value=4000, suggested_reorder_qty=0)),
    dict(id="S05", title="Zero sales while stock remains",
         product=product(40, 6), sales=None,
         working="no units sold in the period, stock 40 > 0; DoS cannot be calculated",
         expect=dict(status=NO_SALES, avg_daily_sales=0, days_of_supply=None, excess_units=None, suggested_reorder_qty=0)),
    dict(id="S06", title="Zero current stock",
         product=product(0, 3), sales=("list", [(i, 10) for i in range(1, 30)]),
         working="current stock is 0 -> Stockout risk whatever the sales are; today is not an in-stock day: 290/29 = 10",
         expect=dict(status=STOCKOUT, avg_daily_sales=10, days_in_stock=29, suggested_reorder_qty=140)),
    dict(id="S06b", title="Zero current stock and zero sales",
         product=product(0, 3), sales=None,
         working="current stock is 0 -> Stockout risk takes precedence over No recent sales",
         expect=dict(status=STOCKOUT, days_of_supply=None)),
    dict(id="S09", title="Zero replenishment lead time",
         product=product(10, 0), sales=("daily", 5, 30),
         working="ADS 5; DoS 2; lead 0 <= 2 < 0+3 -> Understock risk",
         expect=dict(status=UNDERSTOCK, days_of_supply=2)),
    dict(id="S09b", title="Zero lead time and zero buffer days",
         product=product(10, 0), sales=("daily", 5, 30), settings=dict(buffer_days=0),
         working="DoS 2; lead 0 + buffer 0 = 0 <= 2 <= 30 -> Optimal",
         expect=dict(status=OPTIMAL, days_of_supply=2)),
    dict(id="S10a", title="Sales over different periods: 30-day period",
         product=product(96, 6), sales=("list", [(i, 12) for i in range(15)] + [(i, 4) for i in range(15, 30)]),
         working="15x12 + 15x4 = 240; 240/30 = 8; DoS 96/8 = 12; 9 <= 12 <= 30",
         expect=dict(status=OPTIMAL, total_units_sold=240, avg_daily_sales=8, days_of_supply=12)),
    dict(id="S10b", title="Sales over different periods: 14-day period (same product)",
         product=product(96, 6), sales=("list", [(i, 12) for i in range(15)] + [(i, 4) for i in range(15, 30)]),
         settings=dict(sales_period_days=14),
         working="last 14 days: 14x12 = 168; 168/14 = 12; DoS 96/12 = 8; lead 6 <= 8 < 9",
         expect=dict(status=UNDERSTOCK, total_units_sold=168, avg_daily_sales=12, days_of_supply=8)),
    dict(id="S10c", title="Sales outside the period are ignored",
         product=product(40, 5), sales=("list", [(45, 100), (60, 100)]),
         working="both sales are older than 30 days -> 0 units in the period",
         expect=dict(status=NO_SALES, total_units_sold=0)),
    dict(id="S11", title="Stock-out days in the sales history",
         product=product(60, 5), sales=("list", [(i, 6) for i in range(30) if not 11 <= i <= 20]),
         records=[(ago(i), 0) for i in range(11, 21)] + [(ago(10), 50)],
         working="10 days at 0 stock with no sales are left out: 120 units / 20 in-stock days = 6 (not 120/30 = 4); DoS 60/6 = 10",
         expect=dict(status=OPTIMAL, days_in_stock=20, out_of_stock_days=10, avg_daily_sales=6, days_of_supply=10)),
    dict(id="S11b", title="A sale on a zero-stock day still counts as an in-stock day",
         product=product(60, 5), sales=("list", [(i, 6) for i in range(30) if i != 5] + [(5, 3)]),
         records=[(ago(5), 0), (ago(4), 40)],
         working="day 5 ends at 0 stock but 3 units were sold, so it is counted: 29x6 + 3 = 177; 177/30 = 5.9",
         expect=dict(days_in_stock=30, total_units_sold=177, avg_daily_sales=5.9)),
    dict(id="S12", title="Changing sales rate (recent sales faster)",
         product=product(100, 5), sales=("list", [(i, 20) for i in range(10)] + [(i, 5) for i in range(10, 30)]),
         working="10x20 + 20x5 = 300; 300/30 = 10; DoS 10; 8 <= 10 <= 30",
         expect=dict(status=OPTIMAL, avg_daily_sales=10, days_of_supply=10)),
    dict(id="S15", title="New product: only days since it was added are counted",
         product=product(100, 5, created_days_ago=4), sales=("daily", 4, 5),
         working="added 5 days ago (today included): 20 units / 5 days = 4 (not 20/30); DoS 25",
         expect=dict(status=OPTIMAL, days_in_period=5, days_in_stock=5, avg_daily_sales=4, days_of_supply=25)),
    dict(id="S16", title="Batch orders once a week (paper's Product B pattern)",
         product=product(500, 7), sales=("list", [(1, 15), (8, 15), (15, 15), (22, 15), (29, 15)]),
         working="75 units / 30 days = 2.5; DoS 500/2.5 = 200 > 30; excess 500 - 75 = 425",
         expect=dict(status=OVERSTOCK, avg_daily_sales=2.5, days_of_supply=200, excess_units=425)),
    # --- boundary values (Table 5) ---
    dict(id="B01", title="Days of supply exactly equal to lead time",
         product=product(30, 5), sales=("daily", 6, 30),
         working="DoS 5 = lead 5 -> covers lead time, below 8 -> Understock risk",
         expect=dict(status=UNDERSTOCK, days_of_supply=5)),
    dict(id="B02", title="Days of supply just below lead time",
         product=product(29, 5), sales=("daily", 6, 30),
         working="DoS 29/6 = 4.83 < 5 -> Stockout risk",
         expect=dict(status=STOCKOUT)),
    dict(id="B03", title="Days of supply exactly lead time plus buffer days",
         product=product(32, 5), sales=("daily", 4, 30),
         working="DoS 8 = 5 + 3 -> Optimal",
         expect=dict(status=OPTIMAL, days_of_supply=8)),
    dict(id="B04", title="Days of supply just below lead time plus buffer days",
         product=product(31, 5), sales=("daily", 4, 30),
         working="DoS 7.75 < 8 -> Understock risk",
         expect=dict(status=UNDERSTOCK, days_of_supply=7.75)),
    dict(id="B05", title="Days of supply exactly the maximum days",
         product=product(150, 7), sales=("daily", 5, 30),
         working="DoS 30 = maximum 30 -> Optimal; excess 0",
         expect=dict(status=OPTIMAL, days_of_supply=30, excess_units=0)),
    dict(id="B06", title="Days of supply just above the maximum days",
         product=product(151, 7), sales=("daily", 5, 30),
         working="DoS 30.2 > 30 -> Overstock risk; excess 151 - 150 = 1",
         expect=dict(status=OVERSTOCK, days_of_supply=30.2, excess_units=1)),
    dict(id="B07", title="Boundary with a non-terminating sales rate (1 unit every 3 days)",
         product=product(5, 5), sales=("list", [(i, 1) for i in range(0, 30, 3)]),
         working="10 units / 30 days = 1/3 a day; DoS 5 / (1/3) = 15 exactly; 8 <= 15 <= 30 -> Optimal",
         expect=dict(status=OPTIMAL, days_of_supply=15)),
    dict(id="B08", title="Very long lead time",
         product=product(44, 20), sales=("daily", 2, 30),
         working="DoS 22; lead 20 <= 22 < 23 -> Understock risk",
         expect=dict(status=UNDERSTOCK, days_of_supply=22)),
    dict(id="B09", title="Reorder quantity is never negative",
         product=product(500, 5), sales=("daily", 3, 30),
         working="target 3x14 = 42; 42 - 500 is negative -> 0",
         expect=dict(target_stock=42, suggested_reorder_qty=0, suggested_reorder_units=0)),
    dict(id="B10", title="Reorder quantity rounds up to whole units for review",
         product=product(10, 5), sales=("list", [(i, 1) for i in range(0, 30, 3)]),
         working="ADS 1/3; target 14/3 = 4.67; 4.67 - 10 is negative -> 0",
         expect=dict(suggested_reorder_qty=0)),
    dict(id="B11", title="Fractional reorder quantity",
         product=product(1, 2), sales=("list", [(i, 1) for i in range(0, 30, 3)]),
         working="ADS 1/3; target 4.67; 4.67 - 1 = 3.67 -> 4 whole units to review",
         expect=dict(suggested_reorder_units=4)),
]
