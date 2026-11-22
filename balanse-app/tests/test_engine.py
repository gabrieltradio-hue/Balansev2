"""Calculations and classification rules, checked against the hand-worked answer key."""
from datetime import date, timedelta

import pytest

from balanse import demo_data, engine
from balanse.engine import OPTIMAL, NO_SALES, OVERSTOCK, STOCKOUT, UNDERSTOCK, Settings, analyze_product

from .cases import CASES, TODAY, expand_sales


def run_case(case):
    settings = Settings(**case.get("settings", {}))
    return analyze_product(case["product"], expand_sales(case["sales"]), case.get("records", []), settings, TODAY)


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_answer_key(case):
    result = run_case(case)
    for field, expected in case["expect"].items():
        actual = result[field]
        if expected is None or isinstance(expected, str):
            assert actual == expected, f"{case['id']} {field}: expected {expected!r}, got {actual!r}"
        else:
            assert actual == pytest.approx(expected, abs=1e-9), f"{case['id']} {field}: expected {expected}, got {actual}"


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_same_input_gives_same_result(case):
    """Reliability: repeated runs with identical inputs give identical results."""
    first = run_case(case)
    for _ in range(5):
        assert run_case(case) == first


def test_brief_worked_example():
    """Brief: stock 100, 50 units sold, 10 days in stock -> 5 a day, 20 days of supply."""
    ads = engine.average_daily_sales(50, 10)
    assert ads == 5
    assert engine.days_of_supply(100, ads) == 20


def test_never_divides_by_zero():
    assert engine.average_daily_sales(50, 0) is None
    assert engine.days_of_supply(100, 0) is None
    assert engine.days_of_supply(100, None) is None
    assert engine.excess_units(100, 0, 30) is None
    assert engine.suggested_reorder_quantity(100, None, 14) is None


@pytest.mark.parametrize("stock,dos,lead,buffer_days,max_days,expected", [
    (0, None, 5, 3, 30, STOCKOUT),          # zero stock, no sales
    (0, 0, 5, 3, 30, STOCKOUT),             # zero stock with sales
    (10, None, 5, 3, 30, NO_SALES),
    (10, 4.999, 5, 3, 30, STOCKOUT),
    (10, 5, 5, 3, 30, UNDERSTOCK),          # equal to lead time
    (10, 7.999, 5, 3, 30, UNDERSTOCK),
    (10, 8, 5, 3, 30, OPTIMAL),             # equal to lead time + buffer
    (10, 30, 5, 3, 30, OPTIMAL),            # equal to maximum
    (10, 30.001, 5, 3, 30, OVERSTOCK),
    (10, 5, 5, 0, 30, OPTIMAL),             # no buffer: equal to lead time is Optimal
    (10, 1, 0, 0, 30, OPTIMAL),             # zero lead time, zero buffer
])
def test_classification_rules(stock, dos, lead, buffer_days, max_days, expected):
    assert engine.classify(stock, dos, lead, buffer_days, max_days) == expected


def test_every_status_has_an_explanation_with_numbers_and_an_action():
    for case in CASES:
        result = run_case(case)
        assert result["explanation"].strip() and result["rule"].startswith("Rule met:")
        assert result["suggested_action"] == engine.SUGGESTED_ACTIONS[result["status"]]
        if result["status"] in (UNDERSTOCK, OPTIMAL, OVERSTOCK):
            assert engine.fmt(result["days_of_supply"]) in result["explanation"]
            assert engine.fmt(result["current_stock"]) in result["explanation"]


def test_stockout_explanation_matches_the_paper_example():
    result = run_case(next(c for c in CASES if c["id"] == "S02"))
    assert "may run out before your next replenishment arrives" in result["explanation"]
    assert "2.8 days short" in result["explanation"]          # 2.75 shown to one decimal place
    assert "5 days to deliver" in result["explanation"]


def test_projection_fields():
    result = run_case(next(c for c in CASES if c["id"] == "S01"))
    assert result["estimated_days_until_stockout"] == 15
    assert result["estimated_runout_date"] == TODAY + timedelta(days=15)
    assert result["gap_vs_lead_time_days"] == 11
    none = run_case(next(c for c in CASES if c["id"] == "S05"))
    assert none["estimated_runout_date"] is None and none["estimated_days_until_stockout"] is None


def test_in_stock_days_rules():
    start, end = date(2026, 11, 1), date(2026, 11, 10)
    # no stock records at all: every day counts
    assert engine.count_in_stock_days(start, end, {}, []).days_in_stock == 10
    # zero stock from the 4th, restocked on the 7th: the 4th, 5th and 6th are out
    count = engine.count_in_stock_days(start, end, {}, [(date(2026, 11, 4), 0), (date(2026, 11, 7), 20)])
    assert count.days_in_stock == 7 and len(count.out_of_stock_days) == 3
    # a zero record from before the period carries forward
    assert engine.count_in_stock_days(start, end, {}, [(date(2026, 10, 20), 0)]).days_in_stock == 0
    # days before the product's first record are not counted
    assert engine.count_in_stock_days(start, end, {}, [], tracking_start=date(2026, 11, 6)).days_in_period == 5
    # the period is counted inclusively
    assert engine.period_window(end, 30) == (date(2026, 10, 12), end)


def test_out_of_stock_for_the_whole_period_but_stock_now():
    product = {"id": 1, "name": "x", "category": "c", "current_stock": 25, "unit_cost": 1, "lead_time_days": 3,
               "created_on": TODAY - timedelta(days=90)}
    records = [(TODAY - timedelta(days=60), 0)]
    result = analyze_product(product, [], records, Settings(), TODAY)
    # today's stock is 25, so only today counts as in stock; nothing sold -> No recent sales, never a division by zero
    assert result["status"] == NO_SALES and result["days_of_supply"] is None


def test_sorting_most_urgent_first():
    results = engine.analyze_all(
        [dict(c["product"], id=i, name=c["id"]) for i, c in enumerate(CASES)],
        [{"product_id": i, "sale_date": d, "quantity_sold": q} for i, c in enumerate(CASES) for d, q in expand_sales(c["sales"])],
        [{"product_id": i, "record_date": d, "stock_quantity": q} for i, c in enumerate(CASES) for d, q in c.get("records", [])],
        Settings(), TODAY)
    order = [engine.URGENCY[r["status"]] for r in results]
    assert order == sorted(order)
    assert results[0]["status"] == STOCKOUT


def test_demo_data_matches_its_answer_key():
    data = demo_data.build(TODAY)
    ids = {p["name"]: i for i, p in enumerate(data["products"])}
    products = [dict(p, id=ids[p["name"]], created_on=date.fromisoformat(p["created_at"][:10])) for p in data["products"]]
    results = engine.analyze_all(
        products,
        [dict(s, product_id=ids[s["name"]]) for s in data["sales"]],
        [dict(r, product_id=ids[r["name"]]) for r in data["stock_records"]],
        Settings(), TODAY)
    assert {r["name"]: r["status"] for r in results} == demo_data.EXPECTED_STATUS
    assert {r["status"] for r in results} == set(engine.ALL_STATUSES)        # every status is shown
    assert len({p["category"] for p in data["products"]}) == 1               # one category only


def test_large_data_set_is_fast():
    """Response time: 1,000 made-up products with 30 days of sales must analyze well inside 10 seconds."""
    import time
    products = [{"id": i, "name": f"P{i}", "category": "c", "current_stock": 50 + i % 200, "unit_cost": 10,
                 "lead_time_days": 3 + i % 10, "created_on": TODAY - timedelta(days=90)} for i in range(1000)]
    sales = [{"product_id": i, "sale_date": TODAY - timedelta(days=d), "quantity_sold": 1 + (i + d) % 9}
             for i in range(1000) for d in range(30)]
    started = time.perf_counter()
    results = engine.analyze_all(products, sales, [], Settings(), TODAY)
    elapsed = time.perf_counter() - started
    assert len(results) == 1000
    assert elapsed < 10, f"took {elapsed:.1f} seconds"
