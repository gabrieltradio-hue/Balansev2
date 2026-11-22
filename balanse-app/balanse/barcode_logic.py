"""Barcode scanning and barcode labels: the parts that need no Streamlit, so they can be tested without a browser.

This module is an ADDITION. It reuses the existing validation and services (record_sale and
import_stock_records), so stock and sales are saved exactly the way the rest of the app saves them.

A label holds the product's own number in the system as a Code 128 barcode, written BAL<id> (for example BAL12).
No new column or table is needed, and no product has to be re-entered to get a label.
The Code 128 encoder is written here (about 30 lines), so no extra package is needed to make labels.
"""
from __future__ import annotations

import io
import re
from datetime import date
from html import escape
from typing import Optional

from . import services, validation
from .repository import Repository, StorageError

PREFIX = "BAL"
SALE, STOCK = "Sale", "Add stock"
ACTIONS = (SALE, STOCK)

# Older labels (BALANSE-12) and labels typed with a dash (BAL-12) are read too.
_CODE = re.compile(r"^\s*(?:BALANSE-|BAL-?)(\d{1,12})\s*$", re.IGNORECASE)
_NUMBER = re.compile(r"^\s*(\d{1,12})\s*$")


# ---------------------------------------------------------------- codes
def product_code(product_id) -> str:
    return f"{PREFIX}{int(product_id)}"


def parse_scan(text, *, allow_number: bool = False) -> Optional[int]:
    """The product id inside scanned or typed text, or None when it is not a Balanse label.

    Accepts BAL12 (any letter case, a dash and spaces are fine). With allow_number, a bare number such as 12
    is accepted too (used for typing by hand)."""
    if text is None:
        return None
    raw = str(text).strip()
    found = _CODE.match(raw) or (_NUMBER.match(raw) if allow_number else None)
    return int(found.group(1)) if found else None


def find_product(products: list[dict], product_id) -> Optional[dict]:
    wanted = str(product_id)
    return next((p for p in products if str(p["id"]) == wanted), None)


# ---------------------------------------------------------------- Code 128 (character set B: letters, digits, punctuation)
# Bar and space widths for each symbol value 0-106 (the last one is the stop symbol), starting with a bar.
_PATTERNS = (
    "212222", "222122", "222221", "121223", "121322", "131222", "122213", "122312",
    "132212", "221213", "221312", "231212", "112232", "122132", "122231", "113222",
    "123122", "123221", "223211", "221132", "221231", "213212", "223112", "312131",
    "311222", "321122", "321221", "312212", "322112", "322211", "212123", "212321",
    "232121", "111323", "131123", "131321", "112313", "132113", "132311", "211313",
    "231113", "231311", "112133", "112331", "132131", "113123", "113321", "133121",
    "313121", "211331", "231131", "213113", "213311", "213131", "311123", "311321",
    "331121", "312113", "312311", "332111", "314111", "221411", "431111", "111224",
    "111422", "121124", "121421", "141122", "141221", "112214", "112412", "122114",
    "122411", "142112", "142211", "241211", "221114", "413111", "241112", "134111",
    "111242", "121142", "121241", "114212", "124112", "124211", "411212", "421112",
    "421211", "212141", "214121", "412121", "111143", "111341", "131141", "114113",
    "114311", "411113", "411311", "113141", "114131", "311141", "411131", "211412",
    "211214", "211232", "2331112",
)
_START_B = 104


def _expand(widths: str) -> str:
    out, dark = [], True
    for width in widths:
        out.append(("1" if dark else "0") * int(width))
        dark = not dark
    return "".join(out)


def code128_modules(text: str) -> str:
    """The barcode as a string of 1 (bar) and 0 (space) modules, without the empty margins."""
    if not text or any(not 32 <= ord(ch) <= 126 for ch in text):
        raise ValueError("Code 128 text must be 1 or more printable ASCII characters.")
    values = [ord(ch) - 32 for ch in text]
    check = (_START_B + sum(i * v for i, v in enumerate(values, start=1))) % 103
    return "".join(_expand(_PATTERNS[v]) for v in [_START_B, *values, check, 106])


# ---------------------------------------------------------------- barcode pictures and printable labels
_QUIET = 10          # empty modules left and right of the bars (the standard asks for at least 10)


def barcode_svg(text: str) -> str:
    """A barcode as an SVG picture. It stretches to the width it is given, so the page sets the size."""
    bits = code128_modules(text)
    rects, i = [], 0
    while i < len(bits):
        if bits[i] == "1":
            j = i
            while j < len(bits) and bits[j] == "1":
                j += 1
            rects.append(f'<rect x="{_QUIET + i}" y="0" width="{j - i}" height="30"/>')
            i = j
        else:
            i += 1
    total = len(bits) + 2 * _QUIET
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total} 30" preserveAspectRatio="none" '
            f'shape-rendering="crispEdges" role="img" aria-label="Barcode {escape(text)}">'
            f'<rect width="{total}" height="30" fill="#fff"/><g fill="#000">{"".join(rects)}</g></svg>')


def barcode_png(text: str, module_px: int = 4, height_px: int = 140) -> bytes:
    """A barcode as PNG bytes (Pillow is installed together with Streamlit)."""
    from PIL import Image, ImageDraw
    bits = code128_modules(text)
    image = Image.new("L", ((len(bits) + 2 * _QUIET) * module_px, height_px), 255)
    draw = ImageDraw.Draw(image)
    for i, bit in enumerate(bits):
        if bit == "1":
            x = (_QUIET + i) * module_px
            draw.rectangle([x, 0, x + module_px - 1, height_px], fill=0)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


_SHEET_CSS = (
    "body{font-family:Arial,Helvetica,sans-serif;margin:12px;color:#111}"
    ".bar{margin-bottom:12px;font-size:13px}.bar button{padding:6px 14px;font-size:13px;cursor:pointer}"
    ".sheet{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}"
    ".label{border:1px dashed #888;padding:8px;text-align:center;break-inside:avoid;page-break-inside:avoid}"
    ".label svg{display:block;margin:0 auto;width:100%;max-width:62mm;height:16mm}"
    ".name{font-size:12px;font-weight:bold;margin-top:4px;word-break:break-word}"
    ".code{font-size:12px;color:#333;font-family:monospace;letter-spacing:1px}"
    "@page{margin:10mm}@media print{.bar{display:none}body{margin:0}}"
)


def label_sheet_html(products: list[dict]) -> str:
    """One printable page of labels (barcode, product name, code). Opens anywhere; the Print button hides itself on paper."""
    cells = []
    for product in products:
        code = product_code(product["id"])
        cells.append(f'<div class="label">{barcode_svg(code)}<div class="name">{escape(str(product["name"]))}</div>'
                     f'<div class="code">{code}</div></div>')
    return ('<!doctype html><html><head><meta charset="utf-8"><title>Balanse barcode labels</title>'
            f"<style>{_SHEET_CSS}</style></head><body>"
            '<div class="bar"><button onclick="window.print()">Print labels</button> '
            "Print at 100% size. Each barcode is about 6 cm wide. Cut along the dashed lines. Keep the barcode flat and not folded.</div>"
            f'<div class="sheet">{"".join(cells)}</div></body></html>')


# ---------------------------------------------------------------- saving the scanned list
def save_lines(repo: Repository, products: list[dict], lines: list[dict], *, deduct_sales: bool = True,
               today: Optional[date] = None) -> tuple[list[str], list[str], list[str]]:
    """Save the scanned list. Each line is {"product_id", "action": SALE or STOCK, "quantity"}.

    Everything is checked first, and nothing is saved if any line is wrong. Sales go through
    services.record_sale and added stock through services.import_stock_records.
    Returns (ids saved, what was saved in words, problems)."""
    today = today or date.today()
    plan, problems, seen = [], [], set()
    for line in lines:
        product = find_product(products, line.get("product_id"))
        if product is None:
            problems.append("A scanned product is not in this store any more. Remove it from the list.")
            continue
        name = product["name"]
        if str(product["id"]) in seen:
            problems.append(f"'{name}' is in the list twice. Keep one line for it.")
            continue
        seen.add(str(product["id"]))
        action = line.get("action")
        if action not in ACTIONS:
            problems.append(f"Choose Sale or Add stock for '{name}'.")
            continue
        qty, problem = validation.parse_number(line.get("quantity"), f"Quantity for '{name}'", allow_zero=False)
        if problem:
            problems.append(problem)
            continue
        if action == SALE and deduct_sales and qty > float(product["current_stock"]):
            problems.append(f"Not enough stock for '{name}'. Only {float(product['current_stock']):g} units are in stock, "
                            f"so {qty:g} cannot be sold. Correct the quantity, or untick 'Subtract sales from current stock'.")
            continue
        plan.append((product, action, qty))
    if problems or not plan:
        return [], [], problems or ["There is nothing to save yet. Scan a product first."]

    saved_ids, saved_words = [], []
    for product, action, qty in plan:
        try:
            if action == SALE:
                errors = services.record_sale(
                    repo, product, {"product_id": product["id"], "sale_date": today, "quantity_sold": qty},
                    deduct_from_stock=deduct_sales, as_of=today)
                if errors:
                    problems.extend(errors)
                    break
                saved_words.append(f"sold {qty:g} × {product['name']}")
            else:
                services.import_stock_records(
                    repo, [{"product_id": product["id"], "record_date": today,
                            "stock_quantity": float(product["current_stock"]) + qty}], as_of=today)
                saved_words.append(f"added {qty:g} × {product['name']} to stock")
            saved_ids.append(str(product["id"]))
        except StorageError as problem:
            problems.append(f"'{product['name']}' was not saved. {problem}")
            break
    return saved_ids, saved_words, problems
