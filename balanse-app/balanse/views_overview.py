"""Dashboard, Inventory, Stock Alerts and Reorder Recommendations (screens 2 to 5 of the paper's Table 4)."""
from __future__ import annotations

from datetime import timedelta
from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from . import services, ui
from .engine import ALL_STATUSES, OPTIMAL, NO_SALES, OVERSTOCK, STOCKOUT, UNDERSTOCK, fmt

NEEDS_REVIEW_LIMIT = 5
ALERTS_PER_PAGE = 50
INVENTORY_ROWS = 300
BAR = "#0F1B2D"
BAR_SOFT = "#A9B6C9"
HERO_ITEMS = 4


# ====================================================================== Dashboard
def dashboard() -> None:
    data = ui.page_header("Dashboard")
    results, settings = data["results"], data["settings"]
    if not results:
        ui.empty_state()
        return
    st.markdown(f'<div class="bal-sub">{data["as_of"]:%b %d, %Y}</div>', unsafe_allow_html=True)
    ui.status_tiles(results)

    left, right = st.columns([2.2, 1], gap="large")
    with left:
        with st.container(key="card-sales"):
            ui.section("Units sold, 30 days", ("Open", "sales_history"))
            end = data["as_of"]
            totals: dict = {}
            for s in data["sales"]:
                if end - timedelta(days=29) <= s["sale_date"] <= end:
                    totals[s["sale_date"]] = totals.get(s["sale_date"], 0) + s["quantity_sold"]
            days = [end - timedelta(days=29 - i) for i in range(30)]
            colours = [BAR_SOFT] * 29 + [BAR]  # the latest day in navy, the rest as context
            figure = go.Figure(go.Bar(x=days, y=[totals.get(d, 0) for d in days], marker_color=colours, hovertemplate="%{x|%b %d}: %{y} units<extra></extra>"))
            figure.update_layout(height=430, margin=dict(l=0, r=0, t=8, b=4), bargap=.3, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                 yaxis=dict(gridcolor="#E8ECE9", zeroline=False, nticks=5), xaxis=dict(showgrid=False, tickformat="%b %d", nticks=8),
                                 font=dict(size=11, color="#68756D"))
            st.plotly_chart(figure, use_container_width=True, config={"displayModeBar": False})

    with right:
        # Stock alerts first (short), then the reorder summary, so the sales chart stays near the top of the screen.
        alerts = [r for r in results if r["status"] != OPTIMAL]
        seen = {a["product_id"] for a in data["alerts"] if a["reviewed"]}
        unreviewed = sum(1 for r in alerts if r["product_id"] not in seen)
        mix = ", ".join(f'{n} {s.lower()}' for s in (STOCKOUT, UNDERSTOCK, NO_SALES, OVERSTOCK)
                        if (n := sum(1 for r in alerts if r["status"] == s)))
        with st.container(key="card-excess"):
            st.markdown(f'<div class="card"><div class="l">Stock alerts</div><div class="v">{len(alerts)} alerts</div>'
                        f'<p>{escape(mix)}. {unreviewed} not yet reviewed.</p></div>', unsafe_allow_html=True)
            if st.button("Open stock alerts ›", key="alerts-open", type="tertiary", width="content"):
                ui.go("stock_alerts")

        to_order = [r for r in results if (r["suggested_reorder_units"] or 0) > 0]
        cost = sum(r["suggested_reorder_units"] * r["unit_cost"] for r in to_order)
        with st.container(key="hero-reorder"):
            st.markdown(f'<div class="hero"><div class="l">Reorder to review</div><div class="v">{len(to_order)} products</div>'
                        f'<p>About {ui.peso0(cost)} if every suggested quantity were ordered.</p></div>', unsafe_allow_html=True)
            if st.button("Open reorder list ›", key="hero-open", type="tertiary", width="content"):
                ui.go("reorder")

def _dashboard_group(key: str, title: str, rows: list) -> None:
    """A group of dashboard rows behind one coloured edge, with the status mix in the heading."""
    mix: dict = {}
    for r in rows:
        mix[r["status"]] = mix.get(r["status"], 0) + 1
    summary = " · ".join(f'{n} {ui.STATUS_STYLE[s]["short"].lower()}' for s, n in mix.items())
    with st.container(key=key):
        st.markdown(f'<div class="bal-grp">{escape(title)}<span>{escape(summary)}</span></div>', unsafe_allow_html=True)
        for r in rows:
            _dashboard_row(r, f"dash-{r['product_id']}")


def _dashboard_row(r: dict, key: str) -> None:
    """Dashboard row, kept short on purpose: status, name, days of supply and Details.
    The reason and suggested action stay on Product Details. Display only."""
    dos = r["days_of_supply"]
    with st.container(horizontal=True, vertical_alignment="center", gap="small", key=f"drow-{key}"):
        st.markdown(f'<div class="bal-row">{ui.status_html(r["status"], True)}<span class="nm">{escape(r["name"])}</span>'
                    f'<span class="d">{"No sales rate" if dos is None else fmt(dos) + " days"}</span></div>', unsafe_allow_html=True, width="stretch")
        if st.button("Details ›", key=key, type="tertiary", width="content"):
            ui.go("product_details", r["product_id"])


# ====================================================================== Inventory
SORTS = {
    "Most urgent first": None,
    "Product name (A to Z)": ("name", True),
    "Days of supply (fewest first)": ("days_of_supply", True),
    "Days of supply (most first)": ("days_of_supply", False),
    "Current stock (lowest first)": ("current_stock", True),
    "Current stock (highest first)": ("current_stock", False),
    "Average daily sales (highest first)": ("avg_daily_sales", False),
}


def _inventory_table(rows: list, settings, grouped: bool) -> str:
    def line(r: dict) -> str:
        days = "n/a" if r["days_of_supply"] is None else f"{fmt(r['days_of_supply'])} d"
        last = "" if grouped else f'<td>{ui.status_html(r["status"], True)}<small>{escape(r["suggested_action"])}</small></td>'
        return (f'<tr><td>{escape(r["name"])}<small>{escape(r["category"])}</small></td><td class="r">{fmt(r["current_stock"])}</td>'
                f'<td class="r">{fmt(r["avg_daily_sales"]) if r["avg_daily_sales"] else "0"}</td>'
                f'<td><div class="dos"><span class="bal-mono">{days}</span>{ui.result_gauge(r, settings)}</div></td>'
                f'<td class="r">{r["lead_time_days"]} d</td>{last}</tr>')
    head = ('<tr><th>Product</th><th class="r">Stock</th><th class="r">Sells / day</th><th>Days of supply</th><th class="r">Lead time</th>'
            + ("" if grouped else "<th>Status and suggested action</th>") + "</tr>")
    body = ""
    if grouped:
        for status in [STOCKOUT, UNDERSTOCK, NO_SALES, OVERSTOCK, OPTIMAL]:
            group = [r for r in rows if r["status"] == status]
            if group:
                body += (f'<tr class="grp"><td colspan="5">{ui.status_html(status)}<span class="c">{len(group)}</span>'
                         f'<span class="m">{escape(ui.STATUS_MEANING[status])}</span>'
                         f'<span class="a">Suggested: {escape(group[0]["suggested_action"])}</span></td></tr>')
                body += "".join(line(r) for r in group)
    else:
        body = "".join(line(r) for r in rows)
    return f'<div class="bal-tablewrap"><table class="bal bal-grid bal-compact"><thead>{head}</thead><tbody>{body}</tbody></table></div>'


def inventory() -> None:
    data = ui.page_header("Inventory")
    results, settings = data["results"], data["settings"]
    if not results:
        ui.empty_state()
        return
    ui.status_tiles(results)

    a, b, c, d, e = st.columns([2, 1.8, 1.5, 1.5, 1.7])
    chosen_products = a.multiselect("Product", sorted({r["name"] for r in results}), placeholder="All products", label_visibility="collapsed")
    ui.status_option_css(list(ALL_STATUSES), "Status")
    statuses = b.multiselect("Status", ALL_STATUSES, format_func=ui.status_text, placeholder="All statuses", label_visibility="collapsed",
                             key="inv-status")
    categories = sorted({r["category"] for r in results})
    chosen_categories = c.multiselect("Category", categories, placeholder="All categories", label_visibility="collapsed")
    layout = d.selectbox("Layout", ["Grouped by status", "One list"], label_visibility="collapsed")
    sort = e.selectbox("Sort by", list(SORTS), label_visibility="collapsed")

    rows = [r for r in results
            if (not chosen_products or r["name"] in chosen_products)
            and (not statuses or r["status"] in statuses)
            and (not chosen_categories or r["category"] in chosen_categories)]
    if SORTS[sort]:
        field, ascending = SORTS[sort]
        missing = [r for r in rows if r[field] is None]
        present = sorted((r for r in rows if r[field] is not None),
                         key=lambda r: r[field].lower() if isinstance(r[field], str) else r[field], reverse=not ascending)
        rows = present + missing

    st.markdown(f'<div class="bal-sub">{len(rows)} of {len(results)} products</div>', unsafe_allow_html=True)
    if not rows:
        st.info("No products match. Change the search or filters.")
        return
    shown = rows
    with ui.card("inventory-table"):
        if len(rows) > INVENTORY_ROWS and not st.checkbox(f"Show all {len(rows)} products (showing the first {INVENTORY_ROWS})"):
            shown = rows[:INVENTORY_ROWS]
        st.markdown(_inventory_table(shown, settings, layout == "Grouped by status"), unsafe_allow_html=True)
        st.markdown(ui.zone_legend(), unsafe_allow_html=True)

    with ui.card("inventory-open", "Open a product"):
        left, right = st.columns([4, 1])
        names = {r["product_id"]: r["name"] for r in rows}
        chosen = left.selectbox("Product", list(names), format_func=lambda i: names[i], label_visibility="collapsed")
        if right.button("Open details", type="primary", use_container_width=True):
            ui.go("product_details", chosen)

    with st.expander("Delete several products"):
        st.write("Choose the products to remove. Each one is deleted with its sales records, stock records and alert. This cannot be undone.")
        match = st.text_input("Name contains", placeholder="e.g. Sample, to list only matching products", key="bulk-match")
        pool = {r["product_id"]: r["name"] for r in results if match.strip().lower() in r["name"].lower()}
        all_matching = st.checkbox(f"Select all {len(pool)} matching products", key=f"bulk-all-{match}") if match.strip() and pool else False
        picked = st.multiselect("Products to delete", list(pool), default=list(pool) if all_matching else [], format_func=lambda i: pool[i],
                                placeholder="Choose products", key=f"bulk-pick-{match}-{all_matching}")
        sure = st.checkbox(f"Yes, permanently delete {len(picked)} product{'s' if len(picked) != 1 else ''}", key=f"bulk-sure-{len(picked)}", disabled=not picked)
        if st.button("Delete selected products", disabled=not (picked and sure)):
            for pid in picked:
                services.delete_product(ui.repo(), pid)
            st.session_state.pop("product_id", None)
            ui.changed()
            ui.flash(f"{len(picked)} product{'s' if len(picked) != 1 else ''} deleted.")
            st.rerun()

    table = pd.DataFrame({"Product": [r["name"] for r in rows], "Category": [r["category"] for r in rows],
                          "Current stock": [r["current_stock"] for r in rows], "Average daily sales": [r["avg_daily_sales"] for r in rows],
                          "Days of supply": [r["days_of_supply"] for r in rows], "Lead time (days)": [r["lead_time_days"] for r in rows],
                          "Status": [r["status"] for r in rows], "Suggested action (for review)": [r["suggested_action"] for r in rows]})
    st.download_button("Download this table (CSV)", table.to_csv(index=False).encode("utf-8"), file_name="balanse_inventory.csv", mime="text/csv")

# ====================================================================== Stock Alerts
def _alert_row(alert: dict, settings) -> None:
    r = alert["result"]
    columns = st.columns([1.5, 3.3, 1.6, 2.9], vertical_alignment="center", gap="small")
    columns[0].markdown(ui.status_html(r["status"], True), unsafe_allow_html=True)
    columns[1].markdown(f'<div class="bal-nm">{escape(r["name"])}</div><div class="bal-why">{escape(ui.why_text(r, settings))}</div>'
                        f'<div class="bal-act">Suggested: {escape(r["suggested_action"])}</div>', unsafe_allow_html=True)
    columns[2].markdown(ui.result_gauge(r, settings), unsafe_allow_html=True)
    inner = columns[3].columns([1, 1.9], vertical_alignment="center")
    if inner[0].button("Details ›", key=f"alert-open-{alert['product_id']}", type="tertiary", use_container_width=True):
        ui.go("product_details", alert["product_id"])
    if alert["reviewed"]:
        if inner[1].button("Undo", key=f"unreview-{alert['product_id']}", help="Mark as not reviewed", use_container_width=True):
            ui.repo().set_alert_reviewed(alert["product_id"], False)
            ui.changed()
            st.rerun()
    elif inner[1].button("Mark as reviewed", key=f"review-{alert['product_id']}", type="primary", use_container_width=True):
        ui.repo().set_alert_reviewed(alert["product_id"], True)
        ui.changed()
        ui.flash(f"'{r['name']}' marked as reviewed. Its status and stock are unchanged.")
        st.rerun()
    st.markdown('<div class="bal-hr"></div>', unsafe_allow_html=True)


def _alert_list(alerts: list, key: str, settings) -> None:
    """Most urgent first. Long lists are shown 50 at a time so the page stays quick."""
    if not alerts:
        return
    limit = ALERTS_PER_PAGE
    with ui.card(f"alerts-{key}"):
        if len(alerts) > limit and st.checkbox(f"Show all {len(alerts)}", key=f"all-{key}"):
            limit = len(alerts)
        for alert in alerts[:limit]:
            _alert_row(alert, settings)
        if len(alerts) > limit:
            st.caption(f"Showing the {limit} most urgent of {len(alerts)}.")


def stock_alerts() -> None:
    data = ui.page_header("Stock Alerts")
    alerts, settings = data["alerts"], data["settings"]
    if not data["results"]:
        ui.empty_state()
        return
    if not alerts:
        st.success("No active warnings. Every product is within its stock coverage limits.")
        return
    pending = [a for a in alerts if not a["reviewed"]]
    done = [a for a in alerts if a["reviewed"]]
    ui.status_option_css([s for s in ALL_STATUSES if s != OPTIMAL], "Show")
    statuses = st.multiselect("Show", [s for s in ALL_STATUSES if s != OPTIMAL], format_func=ui.status_text, placeholder="All warnings",
                              label_visibility="collapsed", key="alerts-show")
    keep = lambda a: not statuses or a["classification"] in statuses   # noqa: E731
    tab_pending, tab_done = st.tabs([f"To review ({len(pending)})", f"Reviewed ({len(done)})"])
    with tab_pending:
        shown = [a for a in pending if keep(a)]
        if not shown:
            st.success("Nothing left to review here.")
        _alert_list(shown, "pending", settings)
    with tab_done:
        shown = [a for a in done if keep(a)]
        if not shown:
            st.write("No reviewed alerts.")
        _alert_list(shown, "done", settings)
    st.markdown(ui.zone_legend(), unsafe_allow_html=True)

# ====================================================================== Reorder Recommendations
def reorder_recommendations() -> None:
    data = ui.page_header("Reorder Recommendations")
    results, settings = data["results"], data["settings"]
    if not results:
        ui.empty_state()
        return

    with ui.card("reorder-target", "Target days of supply"):
        with st.form("target-form", border=False):
            left, right = st.columns([1, 3], vertical_alignment="bottom")
            target = left.number_input("Target days of supply", min_value=1, max_value=3650, step=1, value=settings.target_days_of_supply,
                                       help="How many days of sales you want your stock to cover after reordering.")
            if right.form_submit_button("Save target and recalculate"):
                saved, errors, warnings = services.save_settings(ui.repo(), dict(settings.as_dict(), target_days_of_supply=target))
                if errors:
                    for problem in errors:
                        st.error(problem)
                else:
                    ui.changed()
                    for warning in warnings:
                        ui.flash(warning, "warning")
                    ui.flash(f"Target days of supply saved: {saved.target_days_of_supply} days.")
                    st.rerun()

        st.markdown(f'<div class="bal-mono" style="font-size:13px;line-height:1.7;color:var(--text2)">target stock = sells per day × {settings.target_days_of_supply} target days<br>'
                    'suggested quantity = target stock − (current stock + units on order), never below 0 (rounded up to whole units)</div>', unsafe_allow_html=True)
    only_needed = st.toggle("Only products with a quantity to review", value=True)
    rows = [r for r in results if not only_needed or (r["suggested_reorder_units"] or 0) > 0]
    if not rows:
        st.success("No product is below its target stock. Nothing to reorder at the moment.")
        return
    with ui.card("reorder-table", "Suggested quantities"):
        def cell(value, digits: str = "") -> str:
            return "–" if value is None else (fmt(value) if not digits else f"{value:{digits}}")
        body = "".join(
            f'<tr><td>{escape(r["name"])}</td><td>{ui.status_html(r["status"], True)}</td>'
            f'<td class="r">{cell(r["current_stock"])}</td><td class="r">{cell(r["avg_daily_sales"])}</td><td class="r">{cell(r["target_stock"])}</td>'
            f'<td class="r">{cell(r["suggested_reorder_units"], ",")}</td>'
            f'<td class="r">{"–" if r["suggested_reorder_units"] is None else ui.money(r["suggested_reorder_units"] * r["unit_cost"])}</td>'
            f'<td class="r">{r["lead_time_days"]} d</td><td>{escape(r["suggested_action"])}</td></tr>' for r in rows)
        head = ('<tr><th>Product</th><th>Status</th><th class="r">Current stock</th><th class="r">Sells / day</th><th class="r">Target stock</th>'
                '<th class="r">Suggested quantity</th><th class="r">Estimated cost</th><th class="r">Lead time</th><th>Suggested action (for review)</th></tr>')
        st.markdown(f'<div class="bal-tablewrap"><table class="bal bal-grid"><thead>{head}</thead><tbody>{body}</tbody></table></div>', unsafe_allow_html=True)
        table = pd.DataFrame({
            "Product": [r["name"] for r in rows],
            "Status": [r["status"] for r in rows],
            "Current stock": [r["current_stock"] for r in rows],
            "Average daily sales": [r["avg_daily_sales"] for r in rows],
            "Target stock": [r["target_stock"] for r in rows],
            "Suggested quantity to review": [r["suggested_reorder_units"] for r in rows],
            "Estimated cost": [None if r["suggested_reorder_units"] is None else r["suggested_reorder_units"] * r["unit_cost"] for r in rows],
            "Lead time (days)": [r["lead_time_days"] for r in rows],
            "Suggested action (for review)": [r["suggested_action"] for r in rows],
        })
        total = sum((r["suggested_reorder_units"] or 0) * r["unit_cost"] for r in rows)
        st.download_button("Download this list (CSV)", table.to_csv(index=False).encode("utf-8"), file_name="balanse_reorder_suggestions.csv", mime="text/csv")