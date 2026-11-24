"""Checks for everything a user can type or import.

Nothing invalid is ever saved silently. Every function returns the cleaned
values together with a list of plain-language problems; the caller saves only
when the list is empty (or, for CSV files, saves only the valid rows after
showing the user which rows were rejected and why).
"""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import Iterable, Mapping, Optional

import pandas as pd

from .engine import Settings

MAX_NAME_LENGTH = 120

# Accepted column names for each CSV file (lower-case, spaces/underscores ignored)
PRODUCT_COLUMNS = {
    "name": ["productname", "product", "name", "item", "itemname"],
    "category": ["category", "productcategory"],
    "current_stock": ["currentstock", "stock", "stockquantity", "quantity", "currentstockquantity", "onhand"],
    "unit_cost": ["unitcost", "cost", "costperunit"],
    "lead_time_days": ["leadtimedays", "leadtime", "replenishmentleadtime", "replenishmentleadtimedays"],
}
SALES_COLUMNS = {
    "name": PRODUCT_COLUMNS["name"],
    "sale_date": ["saledate", "salesdate", "date"],
    "quantity_sold": ["quantitysold", "quantity", "qty", "unitssold", "sold"],
}
STOCK_COLUMNS = {
    "name": PRODUCT_COLUMNS["name"],
    "record_date": ["recorddate", "date", "stockdate"],
    "stock_quantity": ["stockquantity", "stock", "quantity", "currentstock", "onhand"],
}


# ---------------------------------------------------------------- single values
def _is_blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return str(value).strip() == ""


def parse_number(value, label: str, *, minimum: Optional[float] = 0, allow_zero: bool = True,
                 whole: bool = False) -> tuple[Optional[float], Optional[str]]:
    """Return (number, None) or (None, problem)."""
    if _is_blank(value):
        return None, f"{label} is required."
    if isinstance(value, bool):
        return None, f"{label} must be a number."
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None, f"{label} must be a number (got '{value}')."
    if math.isnan(number) or math.isinf(number):
        return None, f"{label} must be a number (got '{value}')."
    if minimum is not None and number < minimum:
        return None, (f"{label} cannot be negative." if minimum == 0 else f"{label} cannot be less than {minimum:g}.")
    if not allow_zero and number == 0:
        return None, f"{label} must be more than 0."
    if whole and number != int(number):
        return None, f"{label} must be a whole number."
    return (int(number) if whole else number), None


def parse_date(value, label: str, *, today: Optional[date] = None) -> tuple[Optional[date], Optional[str]]:
    """Accepts a date, or text such as 2026-11-05 or 11/05/2026. Future dates are rejected."""
    if _is_blank(value):
        return None, f"{label} is required."
    if isinstance(value, datetime):
        result = value.date()
    elif isinstance(value, date):
        result = value
    else:
        text = str(value).strip()
        result = None
        for pattern in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%d-%b-%Y", "%b %d, %Y"):
            try:
                result = datetime.strptime(text, pattern).date()
                break
            except ValueError:
                continue
        if result is None:
            return None, f"{label} is not a valid date (got '{value}'). Use YYYY-MM-DD, for example 2026-11-05."
    if result > (today or date.today()):
        return None, f"{label} cannot be in the future ({result.isoformat()})."
    return result, None


# ---------------------------------------------------------------- settings
def validate_settings(values: Mapping, products: Iterable[Mapping] = ()) -> tuple[Optional[Settings], list[str], list[str]]:
    """Returns (settings, errors, warnings). Settings are saved only when errors is empty."""
    errors, warnings, clean = [], [], {}
    rules = [
        ("sales_period_days", "Sales period (days)", 1, 365),
        ("buffer_days", "Buffer days", 0, 365),
        ("max_days_of_supply", "Maximum days of supply", 1, 3650),
        ("target_days_of_supply", "Target days of supply", 1, 3650),
    ]
    for key, label, low, high in rules:
        number, problem = parse_number(values.get(key), label, minimum=0, whole=True)
        if problem:
            errors.append(problem)
        elif number < low:
            errors.append(f"{label} must be at least {low}.")
        elif number > high:
            errors.append(f"{label} cannot be more than {high}.")
        else:
            clean[key] = number
    if errors:
        return None, errors, warnings

    buffer_days, max_days, target = clean["buffer_days"], clean["max_days_of_supply"], clean["target_days_of_supply"]
    if target > max_days:
        errors.append(
            f"Target days of supply ({target}) cannot be more than maximum days of supply ({max_days}). "
            "Ordering up to the target would put products into Overstock risk.")
    # The Optimal range runs from lead time + buffer days up to the maximum days.
    # If the maximum is below lead time + buffer for a product, that product has no Optimal range.
    clashing = [p for p in products if int(p["lead_time_days"]) + buffer_days > max_days]
    if clashing:
        worst = max(clashing, key=lambda p: int(p["lead_time_days"]))
        errors.append(
            f"These limits overlap for {len(clashing)} product(s). For example, '{worst['name']}' has a lead time of "
            f"{int(worst['lead_time_days'])} days, so lead time plus buffer days is {int(worst['lead_time_days']) + buffer_days} days, "
            f"which is more than the maximum of {max_days} days. No amount of stock could be Optimal. "
            "Raise the maximum days of supply or lower the buffer days.")
    longest = max((int(p["lead_time_days"]) for p in products), default=None)
    if not errors and longest is not None and target < longest + buffer_days:
        warnings.append(
            f"Target days of supply ({target}) is less than the longest lead time plus buffer days ({longest + buffer_days}). "
            "For products with that lead time, ordering up to the target would still leave them below the Optimal range.")
    if errors:
        return None, errors, warnings
    return Settings(**clean), errors, warnings


# ---------------------------------------------------------------- products
def validate_product(data: Mapping, *, existing_names: Iterable[str] = (), settings: Optional[Settings] = None,
                     own_name: Optional[str] = None) -> tuple[dict, list[str]]:
    """Check one product. `existing_names` are names already saved; `own_name` is the product's
    current name when editing (so it does not clash with itself)."""
    errors, clean = [], {}
    name = "" if _is_blank(data.get("name")) else " ".join(str(data.get("name")).split())
    if not name:
        errors.append("Product name is required.")
    elif len(name) > MAX_NAME_LENGTH:
        errors.append(f"Product name is too long (maximum {MAX_NAME_LENGTH} characters).")
    else:
        taken = {str(n).strip().lower() for n in existing_names}
        if own_name:
            taken.discard(own_name.strip().lower())
        if name.lower() in taken:
            errors.append(f"A product named '{name}' already exists. Product names must be unique.")
    clean["name"] = name

    category = "" if _is_blank(data.get("category")) else " ".join(str(data.get("category")).split())
    if not category:
        errors.append("Product category is required.")
    clean["category"] = category

    stock, problem = parse_number(data.get("current_stock"), "Current stock")
    errors.append(problem) if problem else clean.__setitem__("current_stock", stock)
    cost, problem = parse_number(data.get("unit_cost"), "Unit cost")
    errors.append(problem) if problem else clean.__setitem__("unit_cost", cost)
    # Optional: units already ordered from the supplier but not yet received. Blank means none.
    if _is_blank(data.get("on_order_units")):
        clean["on_order_units"] = 0
    else:
        on_order, problem = parse_number(data.get("on_order_units"), "Units on order", whole=True)
        errors.append(problem) if problem else clean.__setitem__("on_order_units", on_order)
    lead, problem = parse_number(data.get("lead_time_days"), "Replenishment lead time (days)", whole=True)
    if problem:
        errors.append(problem)
    else:
        clean["lead_time_days"] = lead
        if lead > 365:
            errors.append("Replenishment lead time cannot be more than 365 days.")
        elif settings is not None and lead + settings.buffer_days > settings.max_days_of_supply:
            errors.append(
                f"A lead time of {lead} days plus your buffer of {settings.buffer_days} days is {lead + settings.buffer_days} days, "
                f"which is more than your maximum days of supply ({settings.max_days_of_supply}). No amount of stock could be Optimal. "
                "Raise the maximum days of supply in Settings first, or check the lead time.")
    return clean, errors


def validate_sale(data: Mapping, *, today: Optional[date] = None) -> tuple[dict, list[str]]:
    errors, clean = [], {}
    if _is_blank(data.get("product_id")):
        errors.append("Choose a product.")
    else:
        clean["product_id"] = data.get("product_id")
    sale_date, problem = parse_date(data.get("sale_date"), "Sale date", today=today)
    errors.append(problem) if problem else clean.__setitem__("sale_date", sale_date)
    qty, problem = parse_number(data.get("quantity_sold"), "Quantity sold", allow_zero=False)
    errors.append(problem) if problem else clean.__setitem__("quantity_sold", qty)
    return clean, errors


# ---------------------------------------------------------------- CSV files
def _normalise(text) -> str:
    return "".join(ch for ch in str(text).lower() if ch.isalnum())


def map_columns(frame: pd.DataFrame, wanted: Mapping[str, list[str]]) -> tuple[dict, list[str]]:
    """Match the file's column headings to the fields we need. Returns (field -> column, problems)."""
    found, problems = {}, []
    lookup = {}
    for column in frame.columns:
        lookup.setdefault(_normalise(column), column)
    for field, aliases in wanted.items():
        match = next((lookup[a] for a in aliases if a in lookup and lookup[a] not in found.values()), None)
        if match is None:
            problems.append(f"Missing column for {field.replace('_', ' ')}. Accepted headings: {', '.join(sorted(set(aliases)))}.")
        else:
            found[field] = match
    return found, problems


def read_csv(uploaded) -> tuple[Optional[pd.DataFrame], Optional[str]]:
    """Read an uploaded CSV as text (nothing is converted yet). Returns (frame, problem)."""
    try:
        frame = pd.read_csv(uploaded, dtype=str, keep_default_na=False, skip_blank_lines=True)
    except pd.errors.EmptyDataError:
        return None, "The file is empty."
    except UnicodeDecodeError:
        return None, "The file is not a readable text CSV. Save it as 'CSV UTF-8' and try again."
    except Exception as exc:  # malformed CSV
        return None, f"The file could not be read as a CSV ({exc})."
    if frame.shape[1] < 2:
        return None, "The file does not look like a CSV with comma-separated columns."
    if frame.empty:
        return None, "The file has column headings but no rows."
    return frame, None


def check_products_csv(frame: pd.DataFrame, *, existing_names: Iterable[str] = (),
                       settings: Optional[Settings] = None) -> tuple[list[dict], list[dict], list[str]]:
    """Returns (valid rows, rejected rows with reasons, file-level problems)."""
    columns, problems = map_columns(frame, PRODUCT_COLUMNS)
    if problems:
        return [], [], problems
    valid, rejected, seen = [], [], {}
    existing = list(existing_names)
    for position, row in enumerate(frame.to_dict("records"), start=2):   # row 1 is the heading
        data = {field: row[column] for field, column in columns.items()}
        clean, errors = validate_product(data, existing_names=existing, settings=settings)
        key = clean.get("name", "").lower()
        if key and not errors:
            if key in seen:
                same = all(seen[key][k] == clean[k] for k in clean)
                errors.append(f"Duplicate of row {seen[key]['_row']}." if same
                              else f"Conflicts with row {seen[key]['_row']}: the same product has different values.")
            else:
                seen[key] = dict(clean, _row=position)
        if errors:
            rejected.append({"row": position, "product": data.get("name", ""), "problem": " ".join(errors)})
        else:
            valid.append(clean)
    return valid, rejected, []


def check_sales_csv(frame: pd.DataFrame, *, products_by_name: Mapping[str, Mapping],
                    existing_sales: Iterable[tuple] = (), today: Optional[date] = None
                    ) -> tuple[list[dict], list[dict], list[str]]:
    """`products_by_name` maps lower-case product name -> product. `existing_sales` holds
    (product_id, sale_date, quantity) tuples already saved, used to catch a file imported twice."""
    columns, problems = map_columns(frame, SALES_COLUMNS)
    if problems:
        return [], [], problems
    already = {(pid, d, float(q)) for pid, d, q in existing_sales}
    valid, rejected = [], []
    for position, row in enumerate(frame.to_dict("records"), start=2):
        errors = []
        name = " ".join(str(row[columns["name"]]).split())
        product = products_by_name.get(name.lower())
        if not name:
            errors.append("Product name is required.")
        elif product is None:
            errors.append(f"Product '{name}' is not in your product list. Add or import the product first.")
        clean, more = validate_sale({"product_id": product["id"] if product else "-",
                                     "sale_date": row[columns["sale_date"]],
                                     "quantity_sold": row[columns["quantity_sold"]]}, today=today)
        errors += more
        if not errors and (clean["product_id"], clean["sale_date"], float(clean["quantity_sold"])) in already:
            errors.append("This exact sale (same product, date and quantity) is already saved. Skipped to avoid counting it twice.")
        if errors:
            rejected.append({"row": position, "product": name, "problem": " ".join(errors)})
        else:
            valid.append(dict(clean, name=product["name"]))
    return valid, rejected, []


def check_stock_csv(frame: pd.DataFrame, *, products_by_name: Mapping[str, Mapping],
                    today: Optional[date] = None) -> tuple[list[dict], list[dict], list[str]]:
    columns, problems = map_columns(frame, STOCK_COLUMNS)
    if problems:
        return [], [], problems
    valid, rejected, seen = [], [], {}
    for position, row in enumerate(frame.to_dict("records"), start=2):
        errors = []
        name = " ".join(str(row[columns["name"]]).split())
        product = products_by_name.get(name.lower())
        if not name:
            errors.append("Product name is required.")
        elif product is None:
            errors.append(f"Product '{name}' is not in your product list. Add or import the product first.")
        record_date, problem = parse_date(row[columns["record_date"]], "Record date", today=today)
        if problem:
            errors.append(problem)
        qty, problem = parse_number(row[columns["stock_quantity"]], "Stock quantity")
        if problem:
            errors.append(problem)
        if not errors:
            key = (product["id"], record_date)
            if key in seen:
                errors.append(f"Duplicate of row {seen[key]}." if seen.get((key, "qty")) == qty
                              else f"Conflicts with row {seen[key]}: two stock quantities for the same product and date.")
            else:
                seen[key] = position
                seen[(key, "qty")] = qty
        if errors:
            rejected.append({"row": position, "product": name, "problem": " ".join(errors)})
        else:
            valid.append({"product_id": product["id"], "name": product["name"], "record_date": record_date, "stock_quantity": qty})
    return valid, rejected, []
