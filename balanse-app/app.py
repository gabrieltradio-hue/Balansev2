"""BALANSE: start here:  streamlit run app.py

Inventory risk and decision-support prototype for small and medium suppliers.
This file only wires things together: settings from .env, the optional
password, the navigation and the pages. Calculations are in balanse/engine.py.
"""
from __future__ import annotations

import hmac
import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()                      # reads .env when running on your own computer

st.set_page_config(page_title="BALANSE", page_icon=":material/inventory_2:", layout="wide")

# On Streamlit Community Cloud, credentials come from the app's Secrets box instead of .env
try:
    for _key in ("SUPABASE_URL", "SUPABASE_KEY", "APP_PASSWORD", "DEMO_CATEGORY", "CURRENCY_SYMBOL"):
        if _key in st.secrets and not os.environ.get(_key):
            os.environ[_key] = str(st.secrets[_key])
except Exception:                  # no secrets file: nothing to copy
    pass

from balanse import ui, views_misc, views_overview, views_products, views_barcode  # noqa: E402
from balanse.repository import StorageError  # noqa: E402


def password_gate() -> bool:
    """Optional shared password (APP_PASSWORD). Free Streamlit Cloud apps are public, so set one before sharing the link."""
    expected = os.environ.get("APP_PASSWORD", "")
    if not expected or st.session_state.get("signed_in"):
        return True
    st.title("BALANSE")
    st.caption("Inventory risk and decision support")
    with st.form("sign-in"):
        entered = st.text_input("Password", type="password")
        if st.form_submit_button("Sign in", type="primary"):
            if hmac.compare_digest(entered, expected):
                st.session_state["signed_in"] = True
                st.rerun()
            st.error("That password is not correct.")
    return False


def main() -> None:
    if not password_gate():
        return

    pages = {
        "dashboard": st.Page(views_overview.dashboard, title="Dashboard", icon=":material/dashboard:", default=True),
        "inventory": st.Page(views_overview.inventory, title="Inventory", icon=":material/inventory_2:", url_path="inventory"),
        "stock_alerts": st.Page(views_overview.stock_alerts, title="Stock Alerts", icon=":material/notification_important:", url_path="stock-alerts"),
        "reorder": st.Page(views_overview.reorder_recommendations, title="Reorder", icon=":material/shopping_cart:", url_path="reorder"),
        "sales_history": st.Page(views_products.sales_history, title="Sales History", icon=":material/receipt_long:", url_path="sales-history"),
        "product_details": st.Page(views_products.product_details, title="Product Details", icon=":material/search:", url_path="product"),
        "data_input": st.Page(views_products.data_input, title="Data Input", icon=":material/upload_file:", url_path="data-input"),
        "barcode_scan": st.Page(views_barcode.barcode_page, title="Barcode Scan", icon=":material/barcode_scanner:", url_path="barcode-scan"),
        "price_market": st.Page(views_misc.price_market, title="Price Market", icon=":material/schedule:", url_path="price-market"),
        "settings": st.Page(views_misc.settings_page, title="Settings", icon=":material/settings:", url_path="settings"),
    }
    st.session_state["_pages"] = pages
    navigation = st.navigation({
        # Product Details is opened from a product, so CSS hides its menu link
        "Monitor": [pages["dashboard"], pages["inventory"], pages["stock_alerts"], pages["reorder"], pages["sales_history"], pages["product_details"]],
        "System": [pages["data_input"], pages["barcode_scan"], pages["price_market"], pages["settings"]],
    })

    try:
        ui.sidebar()
        navigation.run()
    except StorageError as problem:
        st.error(f"The data could not be read or saved. {problem}")
        st.caption("Check your internet connection and the Supabase settings in .env, then use the button below.")
        if st.button("Try again"):
            ui.changed()
            ui.repo.clear()
            st.rerun()


main()
