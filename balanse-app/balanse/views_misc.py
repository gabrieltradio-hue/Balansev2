"""Settings, and the placeholder page for the future Price Market module."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from . import price_market as pm
from . import services, ui
from .repository import StorageError
from html import escape

from .engine import OPTIMAL, NO_SALES, OVERSTOCK, STOCKOUT, UNDERSTOCK


# ====================================================================== Settings
def settings_page() -> None:
    data = ui.page_header("Settings")
    current = data["settings"]

    with st.form("settings"):
        a, b = st.columns(2)
        period = a.number_input("Sales period (days)", min_value=1, max_value=365, step=1, value=current.sales_period_days,
                                help="How many days of sales are used for average daily sales, ending today. "
                                     "A longer period smooths out single large orders; a shorter one reacts faster to change.")
        buffer_days = b.number_input("Buffer days", min_value=0, max_value=365, step=1, value=current.buffer_days,
                                     help="Extra days of stock you want on top of the lead time, as a simple safety margin. "
                                          "Below lead time + buffer days, a product is Understock risk.")
        maximum = a.number_input("Maximum days of supply", min_value=1, max_value=3650, step=1, value=current.max_days_of_supply,
                                 help="The most days of stock you want to hold. Above this, a product is Overstock risk.")
        target = b.number_input("Target days of supply", min_value=1, max_value=3650, step=1, value=current.target_days_of_supply,
                                help="How many days of sales you want stock to cover after reordering. Used for the suggested reorder quantity.")
        submitted = st.form_submit_button("Save settings", type="primary")
    if submitted:
        saved, errors, warnings = services.save_settings(ui.repo(), {
            "sales_period_days": period, "buffer_days": buffer_days,
            "max_days_of_supply": maximum, "target_days_of_supply": target})
        if errors:
            st.error("The settings were not saved:")
            for problem in errors:
                st.error(problem)
        else:
            ui.changed()
            for warning in warnings:
                ui.flash(warning, "warning")
            ui.flash("Settings saved. Every product has been recalculated.")
            st.rerun()

    _stores_card()


def _stores_card() -> None:
    """Rename or delete the stores. Adding a store is done from the sidebar."""
    all_stores = ui.stores()
    here = ui.current_store()
    with ui.card("stores", "Stores"):
        for store in all_stores:
            sid = store["id"]
            cols = st.columns([4, 1.2, 1.2] if len(all_stores) > 1 else [4, 1.2], vertical_alignment="center", gap="small")
            new_name = cols[0].text_input("Store name", value=store["name"], key=f"store-name-{sid}", label_visibility="collapsed", max_chars=60)
            if cols[1].button("Rename", key=f"store-rename-{sid}", disabled=new_name.strip() == store["name"], use_container_width=True):
                try:
                    ui.repo().rename_store(sid, new_name)
                except StorageError as problem:
                    st.error(str(problem))
                else:
                    ui.stores_changed()
                    ui.flash(f"Store renamed to '{' '.join(new_name.split())}'.")
                    st.rerun()
            if len(all_stores) > 1:
                with cols[2].popover("Delete", use_container_width=True):
                    st.write(f"Delete **{store['name']}** with all its products, sales records, stock records and alerts? This cannot be undone.")
                    sure = st.checkbox("Yes, delete it", key=f"store-delete-sure-{sid}")
                    if st.button("Delete store", disabled=not sure, key=f"store-delete-go-{sid}", type="primary"):
                        try:
                            ui.repo().delete_store(sid)
                        except StorageError as problem:
                            st.error(str(problem))
                        else:
                            ui.stores_changed()
                            if sid == here["id"]:
                                st.session_state.pop("store_id", None)
                                st.session_state.pop("store_pick", None)
                                ui.changed()
                            ui.flash(f"Store '{store['name']}' deleted.")
                            st.rerun()


# ====================================================================== Price Market (placeholder)
def price_market() -> None:
    st.markdown(ui.CSS, unsafe_allow_html=True)
    st.title("Price Market / Price Fluctuation")
    st.markdown('<span class="st ring" style="--c:#68756D"><span class="dot"></span>Coming soon</span>', unsafe_allow_html=True)
    st.write("It is planned to bring market and supplier price information into BALANSE. "
             "Its method and any recommendations will be based on a future consultation with a specialist or economist.")
