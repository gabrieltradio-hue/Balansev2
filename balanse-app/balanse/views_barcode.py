"""Barcode Scan page (added feature): scan a product's barcode label with the phone or laptop camera, check the
quantity, and save it as a sale or as added stock. A second tab makes printable barcode labels.

Saving goes through the existing services (record_sale, import_stock_records), so the rules for stock,
sales history and risk status are unchanged. The logic that needs no Streamlit is in barcode_logic.py.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from . import barcode_logic as bl
from . import ui
from .engine import fmt
from .repository import StorageError

# A small camera component made of one HTML file, so no extra Python package is needed for scanning.
_scanner = components.declare_component("balanse_barcode_scanner", path=str(Path(__file__).parent / "barcode_scanner_component"))

CART = "barcode_cart"          # product ids (as text) in the order they were scanned


def _qty_key(pid: str) -> str:
    return f"bc-qty-{pid}"


def _act_key(pid: str) -> str:
    return f"bc-act-{pid}"


def _forget(pid: str) -> None:
    cart = st.session_state.get(CART, [])
    if pid in cart:
        cart.remove(pid)
    st.session_state.pop(_qty_key(pid), None)
    st.session_state.pop(_act_key(pid), None)


def _add_product(product: dict, cart: list) -> tuple[str, str]:
    """Put a product on the scanned list, or add one to its quantity when it is already there."""
    pid = str(product["id"])
    if pid in cart:
        now = float(st.session_state.get(_qty_key(pid)) or 0) + 1
        st.session_state[_qty_key(pid)] = now
        return "info", f"Scanned '{product['name']}' again. Quantity is now {fmt(now)}. Change it below if that is not right."
    cart.append(pid)
    st.session_state[_qty_key(pid)] = 1.0
    st.session_state[_act_key(pid)] = bl.SALE
    return "success", f"Added '{product['name']}'. Check the quantity below."


def _add_code(text, products: list[dict], cart: list, *, by_hand: bool = False) -> tuple[str, str]:
    product_id = bl.parse_scan(text, allow_number=by_hand)
    if product_id is None:
        return "error", "That is not a Balanse product label, so nothing was added. Scan a label made on the Barcode labels tab."
    product = bl.find_product(products, product_id)
    if product is None:
        return "error", (f"{bl.product_code(product_id)} is not a product in this store, so nothing was added. "
                         "Check the store chosen in the sidebar.")
    return _add_product(product, cart)


def _save_cart() -> None:
    """Runs when Save is pressed, before the page redraws. Leaves the list alone if anything fails."""
    cart = st.session_state.get(CART, [])
    if not cart:
        return                                       # a second click on Save finds nothing left to save
    lines = [{"product_id": pid, "action": st.session_state.get(_act_key(pid)), "quantity": st.session_state.get(_qty_key(pid))}
             for pid in cart]
    try:
        saved, words, problems = bl.save_lines(ui.repo(), ui.load()["products"], lines,
                                               deduct_sales=st.session_state.get("bc-deduct", True))
    except StorageError as problem:
        saved, words, problems = [], [], [f"Nothing was saved. {problem}"]
    for pid in saved:
        _forget(pid)
    if saved:
        ui.changed()                                 # every screen recalculates
    st.session_state["barcode_result"] = (saved, words, problems)


def _scan_tab(data: dict) -> None:
    products = data["products"]
    cart: list = st.session_state.setdefault(CART, [])
    cart[:] = [pid for pid in cart if bl.find_product(products, pid)]      # e.g. after switching store

    saved, words, problems = st.session_state.pop("barcode_result", ([], [], []))
    notice = None

    st.caption("Press **Start camera** and hold a product's barcode flat in the wide box. Each scan adds the product to the list "
               "below. Scan the same label again to add one more unit.")
    event = _scanner(key="barcode-scanner", default=None)
    if isinstance(event, dict) and event.get("id") and event["id"] != st.session_state.get("barcode_last_event"):
        st.session_state["barcode_last_event"] = event["id"]     # each scan is handled once, not again on every redraw
        notice = _add_code(event.get("code"), products, cart)

    with st.expander("Camera not working? Add a product by hand"):
        with st.form("barcode-by-hand", clear_on_submit=True):
            typed = st.text_input("Product code", placeholder="e.g. BAL12 (printed under the barcode)")
            ids = [p["id"] for p in products]
            names = {p["id"]: p["name"] for p in products}
            picked = st.selectbox("…or choose the product", [None] + ids, format_func=lambda i: "Choose a product" if i is None else names[i])
            if st.form_submit_button("Add to list"):
                if typed.strip():
                    notice = _add_code(typed, products, cart, by_hand=True)
                elif picked is not None:
                    notice = _add_product(bl.find_product(products, picked), cart)
                else:
                    notice = ("error", "Type a product code or choose a product first.")

    # Messages go BELOW the camera box. One above it would shift the page and make the browser restart the camera.
    if saved:
        st.success("Saved: " + "; ".join(words) + ". Results recalculated.")
    for problem in problems:
        st.error(problem)
    if notice:
        getattr(st, notice[0])(notice[1])

    st.markdown("#### Scanned list")
    if not cart:
        st.info("Nothing scanned yet.")
        return
    head = st.columns([4, 2, 2, 1], vertical_alignment="center")
    for column, label in zip(head, ["Product", "Quantity", "Action", ""]):
        column.caption(label)
    by_id = {str(p["id"]): p for p in products}
    for pid in cart:
        product = by_id[pid]
        a, b, c, d = st.columns([4, 2, 2, 1], vertical_alignment="center")
        a.markdown(f"**{product['name']}**  \nIn stock now: {fmt(product['current_stock'])}")
        b.number_input("Quantity", min_value=0.0, step=1.0, format="%g", key=_qty_key(pid), label_visibility="collapsed")
        c.selectbox("Action", bl.ACTIONS, key=_act_key(pid), label_visibility="collapsed")
        d.button(":material/close:", key=f"bc-del-{pid}", on_click=_forget, args=(pid,), help="Remove from the list")
    st.checkbox("Subtract sales from current stock", value=True, key="bc-deduct",
                help="Untick if the current stock you entered already reflects these sales. Added stock is always added.")
    st.button(f"Save {len(cart)} item{'s' if len(cart) != 1 else ''}", type="primary", on_click=_save_cart)
    st.caption("Nothing is saved until you press Save. Sales go to Sales History with today's date.")


def _labels_tab(data: dict) -> None:
    products = data["products"]
    st.caption("Every product already has a barcode. It holds the product's number in the system (shown under the barcode as "
               "BAL12, for example), so there is nothing to type. Print the labels and stick them on the products or shelves.")
    ids = [p["id"] for p in products]
    names = {p["id"]: p["name"] for p in products}
    chosen = st.multiselect("Products", ids, default=ids, format_func=lambda i: names[i])
    if not chosen:
        st.info("Choose at least one product.")
        return
    selected = [p for p in products if p["id"] in chosen]
    sheet = bl.label_sheet_html(selected)
    st.download_button("Download printable label sheet", sheet.encode("utf-8"), file_name="balanse_barcode_labels.html",
                       mime="text/html", type="primary", help="Open the file in your browser and print it.")
    with st.expander("Download one barcode image"):
        one = st.selectbox("Product", ids, format_func=lambda i: names[i], key="bc-one")
        st.download_button("Download barcode image (PNG)", bl.barcode_png(bl.product_code(one)),
                           file_name=f"{bl.product_code(one)}.png", mime="image/png")
    components.html(sheet, height=520, scrolling=True)


def barcode_page() -> None:
    data = ui.page_header("Barcode Scan", "Scan a product's barcode label to record a sale or add stock.")
    if not data["products"]:
        ui.empty_state()
        return
    tabs = st.tabs(["Scan", "Barcode labels"])
    try:
        with tabs[0], ui.card("barcode-scan"):
            _scan_tab(data)
        with tabs[1], ui.card("barcode-labels"):
            _labels_tab(data)
    except StorageError as problem:
        st.error(f"Nothing was saved. {problem}")
