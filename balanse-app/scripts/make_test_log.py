"""Run the answer-key scenarios and write docs/TEST_LOG.md.

    python scripts/make_test_log.py

For every case it records the input, the expected result worked out by hand,
the actual result from the engine, and pass or fail. Each case is run three
times to confirm the result is the same on every repeat.
"""
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from balanse.engine import Settings, analyze_product, fmt  # noqa: E402
from balanse import validation  # noqa: E402
from tests.cases import CASES, TODAY, expand_sales  # noqa: E402


def show(value):
    if value is None:
        return "cannot be calculated"
    if isinstance(value, str):
        return value
    return fmt(value, 2)


def describe_input(case) -> str:
    p = case["product"]
    settings = Settings(**case.get("settings", {}))
    sales = expand_sales(case["sales"])
    in_period = [q for d, q in sales if (TODAY - d).days < settings.sales_period_days]
    parts = [f"stock {p['current_stock']:g}", f"lead time {p['lead_time_days']} d", f"unit cost {p['unit_cost']:g}",
             f"{sum(in_period):g} units sold on {len(in_period)} day(s) of the period"]
    if case.get("records"):
        zero = sum(1 for _, q in case["records"] if q == 0)
        parts.append(f"{zero} stock record(s) at 0")
    if case.get("settings"):
        parts.append("settings: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in case["settings"].items()))
    return "; ".join(parts)


def main() -> int:
    lines, failed = [], 0
    for case in CASES:
        settings = Settings(**case.get("settings", {}))
        runs = [analyze_product(case["product"], expand_sales(case["sales"]), case.get("records", []), settings, TODAY) for _ in range(3)]
        result = runs[0]
        repeatable = all(r == result for r in runs)
        checks = []
        for field, expected in case["expect"].items():
            actual = result[field]
            same = (actual == expected) if (expected is None or isinstance(expected, str)) else (
                actual is not None and abs(actual - expected) < 1e-9)
            checks.append((field.replace("_", " "), show(expected), show(actual), same))
        passed = repeatable and all(c[3] for c in checks)
        failed += not passed
        expected_text = "; ".join(f"{name}: {exp}" for name, exp, _, _ in checks)
        actual_text = "; ".join(f"{name}: {act}" for name, _, act, _ in checks)
        lines.append(f"| {case['id']} | {case['title']} | {describe_input(case)} | {case['working']} | {expected_text} | "
                     f"{actual_text} | {'same on 3 runs' if repeatable else 'DIFFERENT'} | {'PASS' if passed else 'FAIL'} |")

    # input-validation cases (invalid data must be refused with a message, never crash)
    good = {"name": "Test product", "category": "Test", "current_stock": "40", "unit_cost": "12.5", "lead_time_days": "5"}
    invalid = [
        ("V01", "Negative stock (scenario 7)", dict(good, current_stock="-5"), "Current stock cannot be negative."),
        ("V02", "Missing product name (scenario 8)", dict(good, name=""), "Product name is required."),
        ("V03", "Missing stock (scenario 8)", dict(good, current_stock=""), "Current stock is required."),
        ("V04", "Text instead of a number", dict(good, unit_cost="abc"), "Unit cost must be a number"),
        ("V05", "Negative lead time", dict(good, lead_time_days="-1"), "Replenishment lead time (days) cannot be negative."),
        ("V06", "Lead time that leaves no Optimal range", dict(good, lead_time_days="29"), "No amount of stock could be Optimal"),
    ]
    vlines = []
    for code, title, data, expected in invalid:
        _, errors = validation.validate_product(data, settings=Settings())
        passed = any(expected in e for e in errors)
        failed += not passed
        changed = next(f"{k} = '{v}'" for k, v in data.items() if good[k] != v)
        vlines.append(f"| {code} | {title} | {changed} | Refused: \"{expected}\" | {'Refused: \"' + errors[0] + '\"' if errors else 'ACCEPTED'} | {'PASS' if passed else 'FAIL'} |")
    settings_cases = [
        ("V07", "Target days above maximum days (scenario 14)", dict(Settings().as_dict(), target_days_of_supply=45), [], "cannot be more than maximum days of supply"),
        ("V08", "Target days of 0 (scenario 14)", dict(Settings().as_dict(), target_days_of_supply=0), [], "Target days of supply must be at least 1."),
        ("V09", "Limits overlap for a product", dict(Settings().as_dict(), max_days_of_supply=20), [{"name": "Long lead item", "lead_time_days": 20}], "These limits overlap"),
    ]
    for code, title, values, products, expected in settings_cases:
        saved, errors, _ = validation.validate_settings(values, products)
        passed = saved is None and any(expected in e for e in errors)
        failed += not passed
        changed = ", ".join(f"{k.replace('_', ' ')} = {v}" for k, v in values.items() if Settings().as_dict()[k] != v)
        vlines.append(f"| {code} | {title} | {changed} | Not saved: \"{expected}\" | {'Not saved: \"' + errors[0][:90] + '\"' if errors else 'SAVED'} | {'PASS' if passed else 'FAIL'} |")

    total = len(CASES) + len(vlines)
    out = [
        "# BALANSE test log",
        "",
        f"Generated {datetime.now():%Y-%m-%d %H:%M} by `python scripts/make_test_log.py`. "
        "Expected results were worked out by hand before the run (see `tests/cases.py`).",
        "",
        f"**Result: {total - failed} of {total} cases passed.**",
        "",
        "Settings unless stated: sales period 30 days, buffer 3 days, maximum 30 days, target 14 days. "
        f"\"Today\" in these cases is {TODAY.isoformat()}. ADS = average daily sales, DoS = days of supply.",
        "",
        "## Calculations and classification",
        "",
        "| Case | Scenario | Input | Hand working | Expected | Actual | Repeat | Result |",
        "|---|---|---|---|---|---|---|---|",
        *lines,
        "",
        "## Invalid input",
        "",
        "| Case | Scenario | Input | Expected | Actual | Result |",
        "|---|---|---|---|---|---|",
        *vlines,
        "",
        "The full automated suite (`python -m pytest tests`) and the browser check (`node tests/browser_check.js`) "
        "cover more than this log: CSV imports, both storage back ends, alerts, demonstration data and every screen.",
        "",
    ]
    (ROOT / "docs" / "TEST_LOG.md").write_text("\n".join(out), encoding="utf-8")
    print(f"{total - failed} of {total} cases passed. Written to docs/TEST_LOG.md")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
