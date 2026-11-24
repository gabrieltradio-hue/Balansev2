# BALANSE code walkthrough: questions a teacher may ask

A study guide for explaining the system. Every answer below is true of the code as it stands; file names point to where to show it.

## The big picture (30-second answer)

BALANSE is a web app for small and medium businesses. It reads their products, sales and stock records, works out for each product **how many days the stock will last**, compares that with the **supplier lead time**, and flags the product as one of five statuses. It also suggests a quantity to reorder and estimates money tied up in excess stock. It supports decisions; it never places orders or changes stock by itself.

Three layers, each in its own place:

| Layer | Files | Job |
|---|---|---|
| Calculation | `balanse/engine.py` | The formulas and the status rules. No screen, no database. |
| Rules and data handling | `balanse/validation.py`, `balanse/services.py`, `balanse/repository.py` | Check inputs, import CSVs, keep alerts in step, save and load. |
| Screens | `app.py`, `balanse/views_*.py`, `balanse/ui.py` | Streamlit pages, styling, navigation, the store switcher. |

Keeping the maths in a layer that knows nothing about screens or databases is deliberate: it can be tested alone against hand-worked answers.

---

## Q1. What algorithm do you use to decide a product's status?

A rule-based classifier (a decision list) in `classify()`, `engine.py`. It is evaluated top to bottom and the first rule that matches wins:

1. Stock is 0, or days of supply is less than the lead time: **Stockout risk**
2. Stock remains but days of supply cannot be worked out (no sales): **No recent sales**
3. Days of supply is at least the lead time but below lead time plus buffer days: **Understock risk**
4. Days of supply is between lead time plus buffer and the maximum days: **Optimal**
5. Above the maximum days: **Overstock risk**

It is not machine learning. That is a design choice: the owner of a small shop can see exactly why a product was flagged, and each product gets a plain-language explanation with the numbers (`explain()`).

## Q2. How is days of supply calculated?

Two formulas (`average_daily_sales`, `days_of_supply`):

- Average daily sales = units sold in the period divided by the days the product was in stock
- Days of supply = current stock divided by average daily sales

The default period is the last 30 days. The settings are changeable: sales period, buffer days (default 3), maximum days of supply (default 30), target days of supply (default 14).

## Q3. How do you decide how many days a product "was in stock"?

This is the least obvious part, so be ready for it. The research paper says to divide by the days in stock but not how to tell. `count_in_stock_days()` walks through the period one day at a time:

- A day counts as **out of stock** only if the latest stock record on or before that day shows 0 **and** nothing was sold that day.
- A day with a sale always counts as in stock.
- Days before the product's first record are not counted, so a product added last week is not averaged over a month.

Reason: if a product was empty for ten days, dividing by 30 would understate how fast it really sells, and the product would look safer than it is.

The records are sorted once and read with a moving pointer, so the loop is linear: O(days + records).

## Q4. Why do you use `Fraction` instead of normal decimal numbers?

Floating-point arithmetic rounds. A product whose days of supply land exactly on a limit (for example exactly equal to the lead time) could be classified differently depending on rounding error. Python's `fractions.Fraction` is exact, so the same input always gives the same status. Numbers are converted to ordinary floats only at the end, for display (`analyze_product`).

## Q5. How is the suggested reorder quantity worked out?

`suggested_reorder_quantity()`:

- Target stock = average daily sales times target days of supply
- Suggested quantity = target stock minus (current stock + units on order), never below 0, then rounded **up** to a whole unit (you cannot order part of a unit)

Limits we state openly: it does not count units already on order, and it is a quantity to *review*, not an order.

## Q6. How is excess stock estimated?

`excess_units()`: current stock minus (maximum days times average daily sales), never below 0. Estimated excess value is excess units times unit cost. For products with no sales the formula would call all the stock excess, which is not a fair claim, so it returns "not calculable" and the app shows the stock for the user to judge.

## Q7. What is the time complexity of analysing everything?

`analyze_all()` groups sales and stock records by product with dictionaries in one pass (linear in the number of rows), then analyses each product, which costs a short loop over the period, then sorts by urgency, which is O(P log P) for P products. In practice it is linear in the data plus the sort, which is fast for the size of a small or medium business.

## Q8. How are products ordered on screen?

`sort_key()`: first by status urgency (Stockout, Understock, No sales, Overstock, Optimal), then by fewest days of supply, then by name. For Overstock the most overstocked comes first, because "fewest days" would be backwards there.

## Q9. How do alerts work?

`sync_alerts()` in `services.py` keeps one alert per product that is not Optimal:

- A new warning creates an unreviewed alert.
- If the status changes, the alert is replaced and becomes unreviewed again.
- If the status stays the same, the reviewed mark is kept.
- If the product becomes Optimal, its alert is deleted.

Marking an alert reviewed never changes stock or status; it only records that someone saw it.

## Q10. How is the data stored?

`repository.py` defines one interface with two back ends that behave the same: a local SQLite file (works offline, used for the demonstration) and Supabase (PostgreSQL online, schema in `sql/schema.sql`). The rest of the app never knows which is in use. Tables: stores, products, sales records, stock (inventory) records, settings, alerts, and a reserved table for the future price module.

## Q11. How do multiple stores work?

Each store is a separate inventory. Products carry a `store_id`; sales, stock records and alerts belong to products, so they follow automatically. Settings are kept per store. The repository works on one active store at a time and filters every read and write by it. Opening an older database file moves its data into a store called "Main store" without loss (`LocalRepository._upgrade`). There are no user logins; that was a deliberate scope decision.

## Q12. How do you stop bad data getting in?

`validation.py` checks every input before it is saved: names must be present and not duplicates, numbers cannot be negative, dates cannot be in the future, and a sale cannot exceed the stock on hand. CSV imports are checked row by row: valid rows are shown, rejected rows are listed with the row number and the reason, and a file with problems is not saved silently. Column names are matched flexibly (for example "stock" or "on hand").

## Q13. How did you test it?

`tests/` has 149 automated tests (pytest). The engine tests compare against hand-worked answers in `tests/cases.py`, including edge cases on the exact limits. Storage tests run twice, once on SQLite and once on the Supabase code path using an in-memory stand-in (`tests/fake_supabase.py`). Store tests check that stores do not leak into each other, that an old database file is upgraded safely, and that the last store cannot be deleted. Honest limit: the Supabase path has not been run against a real Supabase project.

## Q14. Why Streamlit?

It lets the whole system be written in Python, the same language as the calculation engine, so there is no separate front end to keep in step. Pages are registered in `app.py` and the look is set by one stylesheet in `ui.py`. The trade-off is that Streamlit redraws a page on each click, which limits some animation.

## Q15. What are the limitations?

- Default limits (30 days, 3 buffer days, 14 target days) are provisional until the key informant interviews fix them.
- Units already on order (entered per product) are counted in the reorder suggestion, so ordered-but-not-received stock is not ordered twice.
- The price market module is a placeholder.
- No logins; anyone who opens the app sees all stores.
- It supports decisions only: it does not place orders or change stock by itself.

---

## If you are asked who wrote it

Answer truthfully and follow your course's rules on AI use. A good answer is one you can back with understanding: you should be able to walk through Q1 to Q6 above without notes, and show the matching function in `engine.py` for each.
