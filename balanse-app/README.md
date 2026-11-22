# BALANSE

A web-based inventory risk and decision-support prototype for small and medium suppliers.
It works out each product's average daily sales and days of supply, compares them with the
replenishment lead time and the user's limits, and shows a risk status, the reason for it and a
suggested action.

**BALANSE supports a decision. It never places orders or changes stock by itself.**

Built for the research paper *BALANSE: A Web-Based Inventory Risk and Decision-Support System for
Identifying Overstocking and Understocking Risks Among Small and Medium Suppliers*, with the stack
the paper names: Python, Streamlit, Supabase, Pandas and Plotly.

## Run it on your computer

You need Python 3.10 or newer.

```bash
pip install -r requirements.txt
```

```bash
streamlit run app.py
```

The app opens in your browser at http://localhost:8501. With no Supabase details set, data is
kept in a file called `balanse_local.db` in this folder, so you can try everything straight away.
Go to **Data Input → Demonstration data → Load demonstration data** to see a filled-in app.

## Connect Supabase

1. Create a free project at https://supabase.com.
2. Open **SQL Editor → New query**, paste everything from `sql/schema.sql`, and press **Run**.
3. Open **Project Settings → API**. Copy the **Project URL** and the **service_role** key.
4. Copy `.env.example` to `.env` and fill in:

   ```
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_KEY=your-service-role-key
   ```

5. Start the app again, add a product, and check that it appears in the `products` table in Supabase's **Table Editor**.

The service_role key is a secret. It stays on the server (Streamlit runs your Python on the server,
not in the visitor's browser). Do not put it in code, do not commit `.env`, and do not share it.
The schema switches on Row Level Security with no policies, which blocks the public key.

Free Supabase projects pause after a period without use. Open the Supabase dashboard and restore
the project if the app reports that it cannot read the data.

## Put it online with Streamlit Community Cloud

1. Put this folder in a GitHub repository. `.gitignore` already keeps `.env` and the local data file out.
2. Go to https://share.streamlit.io, sign in with GitHub, and choose **Create app**.
3. Pick the repository and branch, and set **Main file path** to `app.py`.
4. Open **Advanced settings → Secrets** and paste (see `.streamlit/secrets.toml.example`):

   ```toml
   SUPABASE_URL = "https://your-project.supabase.co"
   SUPABASE_KEY = "your-service-role-key"
   APP_PASSWORD = "choose-a-password"
   ```

5. Press **Deploy**.

Things to know:

- **Use Supabase online.** Without it the app saves to a local file, and Streamlit Cloud wipes that file whenever the app restarts.
- **Free apps are public.** Set `APP_PASSWORD` so only people with the password can open it. As the paper says, use demonstration data only, not real business records.
- To change a secret later: the app's **⋮ menu → Settings → Secrets**.

## Design (version 2)

Light theme with green and charcoal. Three ideas run through every page:

- **One status language.** Each status is a small coloured dot (a ring for No recent sales) plus its name. The strip at the top of the Dashboard and Inventory is the legend.
- **Coverage bar.** A thin bar with four zones (before delivery arrives, inside buffer days, optimal range, above maximum) and a marker for the product's days of supply. It shows why a product has its status.
- **Hairlines, not boxes.** Sections are separated by thin rules and small-caps headings.

The colours and layout live in `balanse/ui.py` (the CSS and the shared pieces) and `.streamlit/config.toml`. The calculations are not touched by the design.
Streamlit's own widgets and page frame are restyled, so a few details (such as link buttons beside section headings) will not match a hand-built website exactly.
Product Details has no menu entry: open it by clicking Details on any product.

## The screens

| Page | What it does |
|---|---|
| Dashboard | Number of products in each status, a Needs review list with reasons and suggested actions, products needing immediate attention, estimated money tied up in excess stock |
| Inventory | Every product in one table. Search, filter by status and category, sort, open a product |
| Stock Alerts | One card per warning, most urgent first, with the numbers behind it and a Mark as reviewed button |
| Reorder Recommendations | Target days setting, target stock and a suggested quantity to review, with the formula |
| Sales History | Saved sales by day, by product and date range, with a chart |
| Product Details | Why this status, the numbers used, suggested action, simple projection, excess estimate, stock and sales history chart, edit and delete |
| Data Input | Add a product, record a sale, import CSV files with a preview, load or clear demonstration data |
| Price Market | Placeholder only. See below |
| Settings | Sales period, buffer days, maximum and target days of supply |

## CSV files

Sample files are in `sample_data/`. Column headings can use spaces or underscores, in any letter case.

| File | Columns |
|---|---|
| Products | `product_name, category, current_stock, unit_cost, lead_time_days` |
| Sales records | `product_name, sale_date, quantity_sold` |
| Stock records | `product_name, record_date, stock_quantity` |

Dates are `YYYY-MM-DD`. Import products first, then sales and stock records. The preview shows the
valid rows and lists every rejected row with its reason; only valid rows are saved.
`products_with_errors.csv` has deliberate mistakes for showing the error messages.

The sample sales are dated up to the day the files were made. To get sample sales that fall inside
today's sales period, make them again:

```bash
python scripts/make_sample_csv.py
```

## Demonstration data

**DEMONSTRATION DATA — NOT REAL BUSINESS RECORDS.** Fourteen made-up products in one category,
with 60 days of invented sales and stock records. It includes every status and the special cases
the paper lists for the dry run. The hand-worked answer key is in `balanse/demo_data.py` and on the
Data Input page.

- The category name is set by `DEMO_CATEGORY` in `.env`. The made-up product names are drinks and should be replaced once the research team chooses the category.
- Demonstration data and your own records are never mixed. Clear the demonstration data before entering real products.

## Formulas and rules

See `docs/FORMULAS.md`. It lists every formula, the five statuses with their order of precedence,
the boundary cases, and the nine places where the paper leaves a detail open and the prototype
had to choose.

## Tests

```bash
python -m pytest tests
```

138 automated tests: the calculations and classification against a hand-worked answer key,
boundary values, input checks, CSV imports, both storage back ends, alerts and demonstration data.

```bash
python scripts/make_test_log.py
```

Writes `docs/TEST_LOG.md`: test case, input, expected result, actual result, pass or fail.

`tests/browser_check.js` drives the running app in a real browser (it needs Node.js and
Playwright, and a fresh, empty database). It is optional.

## Project layout

```
app.py                      start here: navigation, optional password
balanse/engine.py           all formulas and classification rules (no Streamlit, no database)
balanse/validation.py       checks for forms, settings and CSV files
balanse/repository.py       storage: Supabase, or a local SQLite file when no credentials are set
balanse/services.py         load and analyze, save, import, alerts, demonstration data
balanse/demo_data.py        the made-up demonstration data set and its answer key
balanse/ui.py               shared screen pieces (status labels, formats, styles)
balanse/views_overview.py   Dashboard, Inventory, Stock Alerts, Reorder Recommendations
balanse/views_products.py   Product Details, Sales History, Data Input
balanse/views_misc.py       Settings, Price Market placeholder
balanse/price_market.py     reserved module for the future price feature (no logic yet)
sql/schema.sql              database tables for Supabase
sample_data/                sample CSV files
scripts/                    make_sample_csv.py, make_test_log.py
tests/                      automated tests and the answer key (cases.py)
docs/                       FORMULAS.md, TEST_LOG.md
```

## Implemented

- Feature 1: product form, sale form, CSV import for products, sales and stock records, with a preview and checks for missing, negative, non-numeric, duplicate and conflicting values, bad dates and badly formed files
- Feature 2: average daily sales over in-stock days and days of supply, with an adjustable sales period and no division by zero
- Features 3 and 4: Stockout, Understock and Overstock detection by the Table 5 rules
- Feature 5: a plain-language reason for every status, with the numbers used and the rule that was met
- Feature 6: a suggested action for every status and a suggested reorder quantity to review
- Feature 7: dashboard, inventory table with search, sort and filters, Stock Alerts with Mark as reviewed
- Feature 8 (optional): stock and sales history chart per product
- Feature 9 (optional): estimated money tied up in excess stock
- Feature 10 (optional): simple projection of the run-out day against the lead time
- Supabase storage with a local fallback, optional password, demonstration data, sample CSV files, automated tests and a test log

## Not complete, and why

- **Supabase has not been tested against a real project.** No credentials were available. The Supabase code runs in the automated tests against a small stand-in that copies the calls it makes, which is not the same as the real service. Test it once with your project before a demonstration.
- **Streamlit Community Cloud deployment has not been tried.** The steps above follow Streamlit's process, but the app was only run locally.
- **Default limits are provisional.** The paper sets them after the interviews, and the interview answers in Appendix B give no numbers.
- **The product category is not final.** The paper chooses it from the interviews. The demonstration data uses "Beverages" as a stand-in.
- **Usability, ease of understanding and usefulness (Table 8)** need real users and the SUS questionnaire. They cannot be tested by code.
- **Price Market / Price Fluctuation** is a placeholder on purpose, waiting for the specialist consultation.
- **Sign-in is one shared password**, not separate user accounts.
- **Phones:** the layout was checked at phone width in a desktop browser only, not on a real phone.

## Future improvements

- Price Market module, built only from the specialist's actual statements and the team's decisions
- Count units already on order in the suggested quantity (the paper notes the formula does not yet)
- Separate accounts and separate data per business
- Set the default limits and the category from the interview findings
- Export the alerts and suggestions as a printable report
- Per-product limits (for example a different maximum for slow sellers), if the interviews support it

## The earlier JavaScript prototype

An earlier browser-only version of Balanse (HTML, CSS and JavaScript, data in the browser) exists
separately. It is not part of this project and was not changed. This Python/Streamlit version
follows the research paper's stack and rules; the two use different formulas in places (the
earlier one used reorder points and safety stock, which the paper does not).
