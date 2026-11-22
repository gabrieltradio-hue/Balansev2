"""What the screens ask for: load and analyze the data, save products and sales,
import files, keep the alerts list in step, and load or clear demonstration data.

No Streamlit here, so every function can be tested without a browser.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from . import demo_data
from .engine import OPTIMAL, Settings, analyze_all
from .repository import Repository
from .validation import validate_settings


# ---------------------------------------------------------------- settings
def get_settings(repo: Repository) -> Settings:
    saved = repo.get_settings()
    return Settings(**saved) if saved else Settings()


def save_settings(repo: Repository, values: dict) -> tuple[Optional[Settings], list[str], list[str]]:
    settings, errors, warnings = validate_settings(values, repo.list_products())
    if settings is not None:
        repo.save_settings(settings.as_dict())
    return settings, errors, warnings


# ---------------------------------------------------------------- analysis
def load_everything(repo: Repository, as_of: Optional[date] = None) -> dict:
    """Read all saved data, run the analysis, and bring the alerts list up to date."""
    as_of = as_of or date.today()
    settings = get_settings(repo)
    products = repo.list_products()
    sales = repo.list_sales()
    records = repo.list_inventory_records()
    results = analyze_all(products, sales, records, settings, as_of)
    alerts = sync_alerts(repo, results)
    return {"as_of": as_of, "settings": settings, "products": products, "sales": sales,
            "records": records, "results": results, "alerts": alerts}


def sync_alerts(repo: Repository, results: list[dict]) -> list[dict]:
    """One alert for every product that is not Optimal.

    * A new alert starts as not reviewed.
    * If the product's status changes, the alert is replaced and is not reviewed again.
    * If the status stays the same, the "reviewed" mark is kept (only the wording is refreshed).
    * When a product becomes Optimal, its alert is removed.
    Marking an alert as reviewed never changes a status or a stock quantity.
    """
    existing = {a["product_id"]: a for a in repo.list_alerts()}
    wanted = {r["product_id"]: r for r in results if r["status"] != OPTIMAL}
    for product_id, alert in existing.items():
        if product_id not in wanted:
            repo.delete_alert(product_id)
    for product_id, result in wanted.items():
        old = existing.get(product_id)
        new = {"product_id": product_id, "classification": result["status"],
               "explanation": result["explanation"], "suggested_action": result["suggested_action"]}
        if old is None or old["classification"] != result["status"]:
            repo.upsert_alert(dict(new, reviewed=False, reviewed_at=None))
        elif old["explanation"] != result["explanation"] or old["suggested_action"] != result["suggested_action"]:
            repo.upsert_alert(dict(new, reviewed=old["reviewed"], reviewed_at=old.get("reviewed_at"),
                                   created_at=old.get("created_at")))
    by_product = {a["product_id"]: a for a in repo.list_alerts()}
    return [dict(by_product[r["product_id"]], **{"result": r}) for r in results if r["product_id"] in by_product]


# ---------------------------------------------------------------- products
def has_demo_data(products: list[dict]) -> bool:
    return any(p["is_demo"] for p in products)


def add_products(repo: Repository, clean_rows: list[dict], as_of: Optional[date] = None, is_demo: bool = False) -> list[dict]:
    """Save new products and write today's stock quantity into the stock history."""
    as_of = as_of or date.today()
    saved = repo.insert_products(clean_rows, is_demo=is_demo)
    repo.upsert_inventory_records(
        [{"product_id": p["id"], "record_date": as_of, "stock_quantity": p["current_stock"]} for p in saved])
    return saved


def update_product(repo: Repository, product: dict, clean: dict, as_of: Optional[date] = None) -> None:
    as_of = as_of or date.today()
    repo.update_product(product["id"], clean)
    if float(clean["current_stock"]) != float(product["current_stock"]):
        repo.upsert_inventory_records(
            [{"product_id": product["id"], "record_date": as_of, "stock_quantity": clean["current_stock"]}])


def delete_product(repo: Repository, product_id) -> None:
    repo.delete_product(product_id)     # its sales, stock records and alert go with it


# ---------------------------------------------------------------- sales
def record_sale(repo: Repository, product: dict, clean: dict, *, deduct_from_stock: bool,
                as_of: Optional[date] = None) -> list[str]:
    """Save one sale. When `deduct_from_stock` is on, current stock goes down by the
    quantity (and is refused if there is not enough stock). Returns problems, empty when saved."""
    as_of = as_of or date.today()
    qty = float(clean["quantity_sold"])
    if deduct_from_stock and qty > float(product["current_stock"]):
        return [f"Not enough stock. Only {product['current_stock']:g} units of '{product['name']}' are in stock. "
                "Correct the quantity, or untick 'Subtract from current stock' if the stock count already reflects this sale."]
    repo.insert_sales([{"product_id": product["id"], "sale_date": clean["sale_date"], "quantity_sold": qty}])
    if deduct_from_stock:
        new_stock = float(product["current_stock"]) - qty
        repo.update_product(product["id"], {"current_stock": new_stock})
        repo.upsert_inventory_records([{"product_id": product["id"], "record_date": as_of, "stock_quantity": new_stock}])
    return []


def import_sales(repo: Repository, valid_rows: list[dict]) -> int:
    """Imported sales are history. They do not change the current stock quantity."""
    return repo.insert_sales(valid_rows)


def import_stock_records(repo: Repository, valid_rows: list[dict], as_of: Optional[date] = None) -> int:
    """Save stock records. A record dated today also becomes the product's current stock."""
    as_of = as_of or date.today()
    count = repo.upsert_inventory_records(valid_rows)
    for row in valid_rows:
        if row["record_date"] == as_of:
            repo.update_product(row["product_id"], {"current_stock": row["stock_quantity"]})
    return count


# ---------------------------------------------------------------- demonstration data
def load_demo_data(repo: Repository, as_of: Optional[date] = None, category: Optional[str] = None) -> list[str]:
    """Load the fictional data set. Refused when real products exist, so the two are never mixed."""
    as_of = as_of or date.today()
    products = repo.list_products()
    if any(not p["is_demo"] for p in products):
        return ["You already have your own products saved. Demonstration data is not mixed with real records. "
                "Delete your own products first if you want to load the demonstration data."]
    if products:
        return ["Demonstration data is already loaded."]
    data = demo_data.build(as_of, category)
    saved = repo.insert_products(data["products"], is_demo=True)
    ids = {p["name"]: p["id"] for p in saved}
    repo.insert_sales([dict(s, product_id=ids[s["name"]]) for s in data["sales"]])
    repo.upsert_inventory_records([dict(r, product_id=ids[r["name"]]) for r in data["stock_records"]])
    return []


def clear_demo_data(repo: Repository) -> int:
    return repo.delete_demo_products()


def daily_sales_series(sales: list[dict], product_id, start: date, end: date) -> list[tuple[date, float]]:
    """Units sold per day for one product, with 0 for days without a sale (for charts)."""
    totals: dict[date, float] = {}
    for s in sales:
        if s["product_id"] == product_id and start <= s["sale_date"] <= end:
            totals[s["sale_date"]] = totals.get(s["sale_date"], 0.0) + s["quantity_sold"]
    days = (end - start).days + 1
    return [(start + timedelta(days=i), totals.get(start + timedelta(days=i), 0.0)) for i in range(days)]
