"""Write the sample CSV files in sample_data/.

SAMPLE DATA — MADE UP, NOT REAL BUSINESS RECORDS. The files show the column
layout BALANSE imports. Dates are counted back from the day this script is run,
so run it again to get sample sales that fall inside the current sales period:

    python scripts/make_sample_csv.py
"""
import csv
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from balanse import demo_data  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "sample_data"
KEEP = 8          # products to include
SALES_DAYS = 35   # days of sales to include


def main(as_of: date | None = None) -> None:
    as_of = as_of or date.today()
    data = demo_data.build(as_of, "Beverages")
    names = [p["name"] for p in data["products"][:KEEP]]

    def sample(name: str) -> str:
        return name.replace("Demo ", "Sample ", 1)

    OUT.mkdir(exist_ok=True)
    with open(OUT / "products.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["product_name", "category", "current_stock", "unit_cost", "lead_time_days"])
        for p in data["products"][:KEEP]:
            writer.writerow([sample(p["name"]), p["category"], f"{p['current_stock']:g}", f"{p['unit_cost']:.2f}", p["lead_time_days"]])

    with open(OUT / "sales.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["product_name", "sale_date", "quantity_sold"])
        for s in data["sales"]:
            if s["name"] in names and (as_of - s["sale_date"]).days < SALES_DAYS:
                writer.writerow([sample(s["name"]), s["sale_date"].isoformat(), f"{s['quantity_sold']:g}"])

    with open(OUT / "stock_records.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["product_name", "record_date", "stock_quantity"])
        for r in data["stock_records"]:
            if r["name"] in names and 0 < (as_of - r["record_date"]).days < SALES_DAYS and (as_of - r["record_date"]).days % 7 == 0:
                writer.writerow([sample(r["name"]), r["record_date"].isoformat(), f"{r['stock_quantity']:g}"])

    # A file with deliberate mistakes, for showing the error messages
    with open(OUT / "products_with_errors.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["product_name", "category", "current_stock", "unit_cost", "lead_time_days"])
        writer.writerow(["Sample Good Row 1 L", "Beverages", "24", "300.00", "4"])
        writer.writerow(["Sample Negative Stock 1 L", "Beverages", "-12", "300.00", "4"])
        writer.writerow(["", "Beverages", "24", "300.00", "4"])
        writer.writerow(["Sample Text In Cost 1 L", "Beverages", "24", "three hundred", "4"])
        writer.writerow(["Sample Missing Lead Time 1 L", "Beverages", "24", "300.00", ""])
        writer.writerow(["Sample Good Row 1 L", "Beverages", "99", "300.00", "4"])
    print(f"Sample CSV files written to {OUT} (dates end on {as_of.isoformat()}).")


if __name__ == "__main__":
    main()
