"""Screens 1 and 6 of the paper's Table 4 (Data Input, Product Details) and the Sales History page."""
from __future__ import annotations

from datetime import timedelta
from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from . import demo_data, services, ui, validation
from .engine import NO_SALES, OVERSTOCK, fmt
from .repository import StorageError

def _pick_product(data: dict, key: str, label: str = "Product"):
    products = data["products"]
    ids = [p["id"] for p in products]
    names = {p["id"]: p["name"] for p in products}
    current = st.session_state.get("product_id")
    index = ids.index(current) if current in ids else 0
    chosen = st.selectbox(label, ids, index=index, format_func=lambda i: names[i], key=key)
    st.session_state["product_id"] = chosen
    return next(p for p in products if p["id"] == chosen)


def _history_chart(data: dict, product: dict, result: dict, days_back: int) -> go.Figure:
    end = data["as_of"]
    start = end - timedelta(days=days_back - 1)
    sales = services.daily_sales_series(data["sales"], product["id"], start, end)
    records = sorted((r["record_date"], r["stock_quantity"]) for r in data["records"]
                     if r["product_id"] == product["id"] and start <= r["record_date"] <= end)
    figure = make_subplots(specs=[[{"secondary_y": True}]])
    figure.add_bar(x=[d for d, _ in sales], y=[q for _, q in sales], name="Units sold", marker_color=ui.BAR_SOFT,
                   hovertemplate="%{x|%b %d}: %{y} sold<extra></extra>")
    figure.add_scatter(x=[d for d, _ in records], y=[q for _, q in records], name="Stock on hand", mode="lines+markers",
                       line=dict(color="#0F1B2D", width=2), marker=dict(size=5), secondary_y=True,
                       hovertemplate="%{x|%b %d}: %{y} in stock<extra></extra>")
    period_start = result["period_start"]
    if period_start > start:
        figure.add_vline(x=period_start, line_dash="dot", line_color="#687089")
        figure.add_annotation(x=period_start, y=1.06, yref="paper", text="sales period starts", showarrow=False,
                              font=dict(size=11, color="#687089"), xanchor="left")
    ui.chart_style(figure, 300, margin=dict(l=0, r=0, t=30, b=0), legend=dict(orientation="h", y=-0.18), hovermode="x unified")
    figure.update_yaxes(title_text="Units sold per day", secondary_y=False, rangemode="tozero")
    figure.update_yaxes(title_text="Stock on hand", secondary_y=True, rangemode="tozero", showgrid=False)
    return figure


# ====================================================================== Product Details
def product_details() -> None:
    data = ui.page_header(None)
    if not data["products"]:
        st.title("Product Details")
        ui.empty_state()
        return
    if st.button("‹ Inventory", type="tertiary"):
        ui.go("inventory")
    product = _pick_product(data, "details-product", "Switch product")
    result = next(r for r in data["results"] if r["product_id"] == product["id"])
    settings = data["settings"]
    lead, buffer_days, max_days = result["lead_time_days"], settings.buffer_days, settings.max_days_of_supply

    st.title(product["name"])
    st.markdown(f'<div class="bal-sub">{escape(product["category"])} · unit cost {ui.money(product["unit_cost"])} · replenishment lead time {lead} days'
                + (" · demonstration product" if product["is_demo"] else "") + "</div>", unsafe_allow_html=True)
    st.markdown(ui.figs([
        ("Status", ui.status_html(result["status"]), ""),
        ("Current stock", ui.units(result["current_stock"]), ""),
        ("Sells per day", "No sales" if not result["avg_daily_sales"] else fmt(result["avg_daily_sales"]), "Units sold ÷ days in stock"),
        ("Days of supply", "n/a" if result["days_of_supply"] is None else fmt(result["days_of_supply"]), f"{lead}-day delivery"),
    ]), unsafe_allow_html=True)

    with ui.card("coverage", "Coverage"):
        st.markdown(f'<div style="padding-top:14px">{ui.result_gauge(result, settings, big=True)}{ui.ticks_html(lead, buffer_days, max_days)}{ui.zone_legend()}</div>',
                    unsafe_allow_html=True)

    left, right = st.columns([3, 2], gap="large")
    with left:
        with ui.card("why", "Why this status"):
            st.write(result["explanation"])
            st.caption(result["rule"])
            in_stock = f"{result['days_in_stock']} of {result['days_in_period']}" + (
                f" ({result['out_of_stock_days']} out-of-stock day{'' if result['out_of_stock_days'] == 1 else 's'} left out)" if result["out_of_stock_days"] else "")
            rows = [("Current stock", ui.units(result["current_stock"])), (f"Units sold in the last {settings.sales_period_days} days", ui.units(result["total_units_sold"])),
                    ("Days counted as in stock", in_stock),
                    ("Average daily sales", "0 (no recent sales)" if not result["avg_daily_sales"] else f"{fmt(result['avg_daily_sales'], 2)} per day"),
                    ("Days of supply", ui.days(result["days_of_supply"])), ("Replenishment lead time", f"{lead} days"),
                    ("Lead time + buffer days", f"{lead + buffer_days} days"), ("Maximum days of supply", f"{max_days} days")]
            st.markdown('<div class="kv">' + "".join(f"<span>{escape(k)}</span><span>{escape(v)}</span>" for k, v in rows) + "</div>", unsafe_allow_html=True)

        with ui.card("history", "Stock and sales history"):
            span = st.radio("Show", [30, 60, 90], format_func=lambda n: f"Last {n} days", horizontal=True, index=0, label_visibility="collapsed")
            st.plotly_chart(_history_chart(data, product, result, span), use_container_width=True, config={"displayModeBar": False})
    with right:
        with ui.card("action", "Suggested action"):
            body = f'<p style="color:var(--text);font-size:14px;margin:0">{escape(result["suggested_action"])}</p>'
            if result["suggested_reorder_units"] is None:
                body += "<p>A suggested quantity cannot be calculated without a sales rate.</p>"
            elif result["suggested_reorder_units"] > 0:
                body += (f'<p>Suggested quantity to review: <strong class="bal-mono" style="color:var(--text)">{result["suggested_reorder_units"]:,} units</strong> '
                         f'(target stock {fmt(result["target_stock"])} minus current stock {fmt(result["current_stock"])} '
                         f'and units on order {fmt(result["on_order_units"])}). '
                         f'Target = {fmt(result["avg_daily_sales"], 2)} per day × {settings.target_days_of_supply} target days.</p>')
            else:
                body += "<p>Current stock is at or above the target stock, so no quantity is suggested.</p>"
            st.markdown(f'<div class="stat">{body}</div>', unsafe_allow_html=True)

        with ui.card("projection", "Projection (an estimate)"):
            if result["current_stock"] <= 0:
                text = "The product is out of stock now."
            elif result["estimated_days_until_stockout"] is None:
                text = "No recent sales, so a run-out date cannot be estimated."
            else:
                gap = result["gap_vs_lead_time_days"]
                text = (f"If sales continue at about {fmt(result['avg_daily_sales'])} units per day and nothing is restocked, stock may run out in about "
                        f"<strong class='bal-mono' style='color:var(--text)'>{fmt(result['estimated_days_until_stockout'])} days</strong> (around {result['estimated_runout_date']:%b %d, %Y}). "
                        f"That is {fmt(abs(gap))} days {'after' if gap >= 0 else 'before'} a delivery ordered today could arrive ({lead}-day lead time). "
                        "An estimate from the current sales rate, not a guaranteed result.")
            st.markdown(f'<div class="stat"><p>{text}</p></div>', unsafe_allow_html=True)

        with ui.card("excess", "Excess stock (an estimate)"):
            if result["status"] == NO_SALES:
                text = f"Cannot be estimated without a sales rate. Current stock is worth {ui.money(result['stock_value_at_cost'])} at unit cost."
            elif result["excess_units"]:
                text = (f"About <strong class='bal-mono' style='color:var(--text)'>{fmt(result['excess_units'])} units</strong> are above the {max_days}-day maximum, "
                        f"about {ui.money(result['estimated_excess_value'])} at unit cost. An estimate based on the numbers you entered. Balanse does not claim any saving.")
            else:
                text = "No excess: stock is within the maximum days of supply."
            st.markdown(f'<div class="stat"><p>{text}</p></div>', unsafe_allow_html=True)

    with st.expander("Edit this product"):
        with st.form("edit-product"):
            name = st.text_input("Product name", product["name"])
            category = st.text_input("Product category", product["category"])
            e1, e2, e3, e4 = st.columns(4)
            stock = e1.number_input("Current stock quantity", value=float(product["current_stock"]), step=1.0, format="%g")
            cost = e2.number_input(f"Unit cost ({ui.currency()})", value=float(product["unit_cost"]), step=1.0, format="%.2f")
            lead_in = e3.number_input("Replenishment lead time (days)", value=int(product["lead_time_days"]), step=1)
            on_order_in = e4.number_input("Units on order", value=int(product.get("on_order_units") or 0), step=1, min_value=0,
                                          help="Ordered from your supplier but not yet received. Reduces the suggested reorder quantity.")
            if st.form_submit_button("Save changes", type="primary"):
                clean, errors = validation.validate_product(
                    {"name": name, "category": category, "current_stock": stock, "unit_cost": cost, "lead_time_days": lead_in,
                     "on_order_units": on_order_in},
                    existing_names=[p["name"] for p in data["products"]], settings=settings, own_name=product["name"])
                if errors:
                    for problem in errors:
                        st.error(problem)
                else:
                    services.update_product(ui.repo(), product, clean)
                    ui.changed()
                    ui.flash(f"'{clean['name']}' saved. Results recalculated.")
                    st.rerun()
    with st.expander("Delete this product"):
        st.write("This removes the product with its sales records, stock records and alert. It cannot be undone.")
        sure = st.checkbox(f"Yes, delete '{product['name']}'", key=f"sure-{product['id']}")
        if st.button("Delete product", disabled=not sure):
            services.delete_product(ui.repo(), product["id"])
            st.session_state.pop("product_id", None)
            ui.changed()
            ui.flash(f"'{product['name']}' deleted.")
            st.rerun()

# ====================================================================== Sales History
def sales_history() -> None:
    data = ui.page_header("Sales History")
    if not data["products"]:
        ui.empty_state()
        return
    names = {p["id"]: p["name"] for p in data["products"]}
    a, b, c = st.columns([3, 2, 2])
    options = [None] + list(names)
    chosen = a.selectbox("Product", options, format_func=lambda i: "All products" if i is None else names[i])
    start = b.date_input("From", data["as_of"] - timedelta(days=data["settings"].sales_period_days - 1), max_value=data["as_of"])
    end = c.date_input("To", data["as_of"], max_value=data["as_of"])
    if start > end:
        st.error("'From' must be on or before 'To'.")
        return

    rows = [s for s in data["sales"] if start <= s["sale_date"] <= end and (chosen is None or s["product_id"] == chosen)]
    total = sum(s["quantity_sold"] for s in rows)
    day_count = (end - start).days + 1
    st.markdown(ui.figs([
        ("Units sold", fmt(total), ""),
        ("Sales records", f"{len(rows):,}", ""),
        ("Average per calendar day", fmt(total / day_count, 2), "Units sold ÷ every day in the range. The status uses in-stock days, so the two can differ."),
    ]), unsafe_allow_html=True)
    if not rows:
        st.info("No sales records for this choice.")
    else:
        per_day: dict = {}
        for s in rows:
            per_day[s["sale_date"]] = per_day.get(s["sale_date"], 0) + s["quantity_sold"]
        days = [start + timedelta(days=i) for i in range(day_count)]
        with ui.card("sales-chart", "Units sold per day"):
            figure = go.Figure(go.Bar(x=days, y=[per_day.get(d, 0) for d in days], marker_color=ui.soft_bars(len(days)),
                                      hovertemplate="%{x|%b %d, %Y}: %{y} units<extra></extra>"))
            ui.chart_style(figure, 280, margin=dict(l=0, r=0, t=8, b=4))
            st.plotly_chart(figure, use_container_width=True, config={"displayModeBar": False})

        with ui.card("sales-records", "Sales records"):
            table = pd.DataFrame({"Date": [s["sale_date"] for s in rows], "Product": [names.get(s["product_id"], "?") for s in rows],
                                  "Quantity sold": [s["quantity_sold"] for s in rows], "Record": [s["id"] for s in rows]})
            table = table.sort_values(["Date", "Product"], ascending=[False, True])
            st.dataframe(table, hide_index=True, use_container_width=True, height=320,
                         column_config={"Quantity sold": st.column_config.NumberColumn(format="%.1f"),
                                        "Record": st.column_config.NumberColumn(help="Record number, used to remove a wrong entry below")})
            st.download_button("Download these records (CSV)", table.to_csv(index=False).encode("utf-8"),
                               file_name="balanse_sales_history.csv", mime="text/csv")
        with st.expander("Remove a wrong sales record"):
            st.caption("Removes the record from the history. It does not change the current stock quantity.")
            by_id = {s["id"]: s for s in rows}
            record = st.selectbox("Record", list(by_id), format_func=lambda i: (
                f"#{i} · {by_id[i]['sale_date']:%b %d, %Y} · {names.get(by_id[i]['product_id'], '?')} · {fmt(by_id[i]['quantity_sold'])} units"))
            if st.button("Remove this record"):
                ui.repo().delete_sale(record)
                ui.changed()
                ui.flash("Sales record removed. Results recalculated.")
                st.rerun()


# ====================================================================== Data Input
def _demo_blocks_real_entries(data: dict) -> bool:
    if services.has_demo_data(data["products"]):
        st.warning("Demonstration data is loaded in this store. To enter your own products, either switch to another store "
                   "or add a new one from the switcher at the top of the sidebar, or clear the demonstration data (last tab).")
        return True
    return False


def _tab_add_product(data: dict) -> None:
    blocked = _demo_blocks_real_entries(data)
    categories = sorted({p["category"] for p in data["products"]})
    n = st.session_state.get("add_form_n", 0)      # changes after each save, which gives a fresh, empty form
    with st.form(f"add-product-{n}", clear_on_submit=False):
        name = st.text_input("Product name", placeholder="e.g. Cola 1.5 L (case of 12)", key=f"add-name-{n}")
        category = st.text_input("Product category", value=categories[0] if len(categories) == 1 else "",
                                 placeholder="e.g. Beverages", key=f"add-category-{n}")
        a, b, c, d = st.columns(4)
        stock = a.number_input("Current stock quantity", value=None, step=1.0, format="%g", placeholder="units on hand", key=f"add-stock-{n}")
        cost = b.number_input(f"Unit cost ({ui.currency()})", value=None, step=1.0, format="%.2f", placeholder="cost per unit", key=f"add-cost-{n}")
        lead = c.number_input("Replenishment lead time (days)", value=None, step=1, placeholder="days to deliver", key=f"add-lead-{n}",
                              help="How many days your own supplier takes to deliver after you order.")
        on_order = d.number_input("Units on order", value=None, step=1, min_value=0, placeholder="0 if none", key=f"add-on-order-{n}",
                                  help="Ordered from your supplier but not yet received. Leave blank if none.")
        if st.form_submit_button("Save product", type="primary", disabled=blocked):
            clean, errors = validation.validate_product(
                {"name": name, "category": category, "current_stock": stock, "unit_cost": cost, "lead_time_days": lead,
                 "on_order_units": on_order},
                existing_names=[p["name"] for p in data["products"]], settings=data["settings"])
            if errors:
                for problem in errors:
                    st.error(problem)
            else:
                saved = services.add_products(ui.repo(), [clean])
                ui.changed()
                st.session_state["product_id"] = saved[0]["id"]
                st.session_state["add_form_n"] = n + 1
                ui.flash(f"'{clean['name']}' saved. Add its sales records next, so its days of supply can be calculated.")
                st.rerun()


def _tab_record_sale(data: dict) -> None:
    if not data["products"]:
        st.info("Add a product first.")
        return
    product = _pick_product(data, "sale-product")
    st.caption(f"Current stock: {fmt(product['current_stock'])} units")
    with st.form("record-sale", clear_on_submit=True):
        a, b = st.columns(2)
        sale_date = a.date_input("Sale date", data["as_of"], max_value=data["as_of"])
        qty = b.number_input("Quantity sold", value=None, step=1.0, format="%g", placeholder="units")
        deduct = st.checkbox("Subtract from current stock", value=True,
                             help="Untick if the current stock you entered already reflects this sale.")
        if st.form_submit_button("Save sale", type="primary"):
            clean, errors = validation.validate_sale({"product_id": product["id"], "sale_date": sale_date, "quantity_sold": qty})
            if not errors:
                errors = services.record_sale(ui.repo(), product, clean, deduct_from_stock=deduct)
            if errors:
                for problem in errors:
                    st.error(problem)
            else:
                ui.changed()
                ui.flash(f"Sale saved: {fmt(clean['quantity_sold'])} units of '{product['name']}' on {clean['sale_date']:%b %d, %Y}."
                         + (" Current stock reduced." if deduct else " Current stock unchanged."))
                st.rerun()


IMPORTS = {
    "Products": {"columns": "product_name, category, current_stock, unit_cost, lead_time_days", "sample": "products.csv"},
    "Sales records": {"columns": "product_name, sale_date, quantity_sold", "sample": "sales.csv"},
    "Stock records": {"columns": "product_name, record_date, stock_quantity", "sample": "stock_records.csv"},
}


def _tab_import(data: dict) -> None:
    kind = st.radio("What does the file contain?", list(IMPORTS), horizontal=True)
    st.caption(f"Columns needed: `{IMPORTS[kind]['columns']}`. Dates as YYYY-MM-DD. "
               f"A sample file is in the project's `sample_data/{IMPORTS[kind]['sample']}`.")
    blocked = kind == "Products" and _demo_blocks_real_entries(data)
    uploaded = st.file_uploader("CSV file", type=["csv"], key=f"upload-{kind}")
    if uploaded is None:
        return
    frame, problem = validation.read_csv(uploaded)
    if problem:
        st.error(problem)
        return
    by_name = {p["name"].lower(): p for p in data["products"]}
    if kind == "Products":
        valid, rejected, problems = validation.check_products_csv(
            frame, existing_names=[p["name"] for p in data["products"]], settings=data["settings"])
    elif kind == "Sales records":
        valid, rejected, problems = validation.check_sales_csv(
            frame, products_by_name=by_name,
            existing_sales=[(s["product_id"], s["sale_date"], s["quantity_sold"]) for s in data["sales"]])
    else:
        valid, rejected, problems = validation.check_stock_csv(frame, products_by_name=by_name)
    if problems:
        st.error("The file cannot be imported:")
        for item in problems:
            st.error(item)
        return

    st.markdown(f"**Preview** · {len(valid)} valid row(s), {len(rejected)} rejected row(s) of {len(frame)}")
    if rejected:
        st.error(f"{len(rejected)} row(s) have problems and will NOT be saved. Row numbers match the file (row 1 is the heading).")
        problems_table = pd.DataFrame(rejected).rename(columns={"row": "Row", "product": "Product", "problem": "Problem"})
        if len(rejected) <= 30:
            st.table(problems_table.set_index("Row"))        # a plain table, so each reason can be read in full
        else:
            st.dataframe(problems_table, hide_index=True, use_container_width=True, height=300)
    if valid:
        preview = pd.DataFrame(valid).drop(columns=["product_id"], errors="ignore")
        st.dataframe(preview.head(200), hide_index=True, use_container_width=True, height=260)
        if len(valid) > 200:
            st.caption(f"Showing the first 200 of {len(valid)} valid rows.")
        if kind == "Sales records":
            st.caption("Imported sales are history. They do not change the current stock quantity.")
        if kind == "Stock records":
            st.caption("A stock record dated today also becomes the product's current stock.")
        if st.button(f"Save {len(valid)} valid row(s)", type="primary", disabled=blocked):
            if kind == "Products":
                services.add_products(ui.repo(), valid)
            elif kind == "Sales records":
                services.import_sales(ui.repo(), valid)
            else:
                services.import_stock_records(ui.repo(), valid)
            ui.changed()
            ui.flash(f"{len(valid)} {kind.lower()} row(s) saved." + (f" {len(rejected)} row(s) were rejected and not saved." if rejected else ""))
            st.rerun()
    else:
        st.warning("No valid rows to save.")


def _tab_demo(data: dict) -> None:
    st.markdown(f"**{demo_data.LABEL}**")
    if services.has_demo_data(data["products"]):
        st.success("Demonstration data is loaded.")
        if st.button("Clear demonstration data"):
            removed = services.clear_demo_data(ui.repo())
            st.session_state.pop("product_id", None)
            ui.changed()
            ui.flash(f"Demonstration data cleared ({removed} products with their records). You can now enter your own records.")
            st.rerun()
    else:
        if data["products"]:
            st.info("You have your own products saved, so demonstration data cannot be loaded. The two are never mixed.")
        elif st.button("Load demonstration data", type="primary"):
            problems = services.load_demo_data(ui.repo())
            ui.changed()
            for problem in problems:
                ui.flash(problem, "error")
            if not problems:
                ui.flash("Demonstration data loaded. Open the Dashboard to see it.")
            st.rerun()
    with st.expander("Answer key for the demonstration data (default settings)"):
        st.caption("Worked out by hand for: sales period 30 days, buffer 3 days, maximum 30 days, target 14 days.")
        st.dataframe(pd.DataFrame({"Product": list(demo_data.EXPECTED_STATUS), "Expected status": list(demo_data.EXPECTED_STATUS.values()),
                                   "Hand working": [demo_data.HAND_WORKING[n] for n in demo_data.EXPECTED_STATUS]}),
                     hide_index=True, use_container_width=True)


def data_input() -> None:
    data = ui.page_header("Data Input")
    tabs = st.tabs(["Add a product", "Record a sale", "Import CSV", "Demonstration data"])
    try:
        with tabs[0], ui.card("input-add"):
            _tab_add_product(data)
        with tabs[1], ui.card("input-sale"):
            _tab_record_sale(data)
        with tabs[2], ui.card("input-import"):
            _tab_import(data)
        with tabs[3], ui.card("input-demo"):
            _tab_demo(data)
    except StorageError as problem:
        st.error(f"Nothing was saved. {problem}")
