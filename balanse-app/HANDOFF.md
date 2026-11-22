# BALANSE: handoff

BALANSE is a Python + Streamlit inventory risk and decision-support prototype for small and medium suppliers. It shows each product's status, why, and a suggested action. It never places orders or changes stock. There is no AI: everything is rule-based arithmetic.

## Run it from source

1. Install Python 3.10 or newer.
2. In this folder, run `pip install -r requirements.txt`.
3. Run `streamlit run app.py`, then open http://localhost:8501.

The database file (`balanse_local.db`) is created on first run and starts empty. Use **Data Input → Demonstration data** to load the sample set. Without Supabase credentials the app uses that local file.

The desktop-window launcher `run_balanse.py` needs the `pywebview` package, which is not in `requirements.txt`. The plain `streamlit run app.py` route does not need it.

## Files

- `app.py`: entry point, navigation, optional password.
- `balanse/engine.py`: all formulas and status rules. No Streamlit, no database.
- `balanse/validation.py`: checks for forms, settings and CSV imports.
- `balanse/repository.py`: storage. Supabase if credentials are set, otherwise local SQLite (`BALANSE_LOCAL_DB` env var, default `balanse_local.db`).
- `balanse/services.py`: load and analyse, save, import, alerts, delete product (cascades to its sales, stock records and alerts).
- `balanse/views_overview.py`: Dashboard, Inventory, Stock Alerts, Reorder.
- `balanse/views_products.py`: Product Details, Sales History, Data Input (CSV import, demonstration tab).
- `balanse/views_misc.py`: Settings (including stores), Price Market (placeholder).
- `balanse/ui.py`: all CSS and shared components.
- `balanse/demo_data.py`: 14 generated "Demo" products plus a hand-worked answer key.
- `docs/FORMULAS.md`: formulas and status precedence.
- `tests/`: automated tests. Run `python -m pytest tests`.
- `run_balanse.py`, `build_installer.bat`, `installer.iss`: packaging into a Windows desktop app and setup file.

## The calculations

- Average daily sales: units sold in the sales period (default 30 days) ÷ days counted as in stock.
- Days of supply = current stock ÷ average daily sales. Undefined when there are no sales.
- Status, in order:
  - Stockout: stock is 0, or days of supply is below the lead time.
  - Understock: covers the lead time but not lead time + buffer days.
  - Optimal: between lead time + buffer days and the maximum.
  - Overstock: above the maximum.
  - No recent sales: nothing sold in the period but stock remains.
- Defaults: maximum 30 days, target 14 days, buffer 3 days, sales period 30 days. These are settings chosen by the user, not calculated.
- Target stock = average daily sales × target days.
- Suggested reorder quantity = target stock − current stock, never below 0, rounded up to whole units. Units already on order are not counted.
- Excess units = stock − maximum × average daily sales. Excess value = excess units × unit cost.
- Projection: the run-out day is days of supply counted from today.
- Validation: target days must not exceed maximum days, and must be at least the longest lead time + buffer days.

## Design decisions already made

- One font everywhere: DM Sans, with tabular numbers for figures.
- Sidebar: dark navy (#0F1B2D), light grey page names, blue (#2F6FE0) highlight for the current page, white section headings, fixed width 260px.
- Primary buttons are navy with white text.
- Status colours: Stockout rust, Understock dark navy, No sales grey, Optimal light green (#7DBF9A, dark text on it), Overstock blue. Coverage bars use the same colours as their legend.
- Status strip order: Stockout, Understock, No sales, Optimal, Overstock.
- Dashboard rows are short: status, name, days, Details. Reason and suggestion appear on Product Details.
- Tables are plain horizontal rules by default. Only the Reorder table uses the full grid (class `bal-grid`).
- Coverage bar markers are solid black, with no white outline.
- Several explanatory notes and cards were removed on request. Ask before adding text back.

## Open items

- Sidebar: resize handle, the cursor change at the sidebar edge, and the collapse button's visibility were changed but not confirmed in a browser.
- Dashboard alignment (status tiles and right-hand cards matching the chart) was changed but not confirmed.
- Stock Alerts excludes Optimal products by design. Not yet decided whether to show them.
- Deleting several sample products at once: a bulk-delete option was proposed but not built. Products are currently deleted one at a time from Product Details.
- Supabase has not been tested against a real project.
- Price Market is a placeholder on purpose, waiting for a specialist consultation.
- Packaging: the `.exe` was built and its server confirmed to start. The setup file needs Inno Setup, which was not installed when this was written.
