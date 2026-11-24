# BALANSE formulas and classification rules

Everything here is implemented in `balanse/engine.py` and checked by `tests/test_engine.py`.
The source is the research paper (Features 2 to 10 and Table 5). Where the paper leaves a
detail open, the choice made in the prototype is listed under "Decisions the paper leaves open"
so the research team can confirm or change it.

## Settings (chosen by the user)

| Setting | Meaning | Starting value |
|---|---|---|
| Sales period (days) | How many days of sales are used, ending today and counting today | 30 |
| Buffer days | Extra days of stock wanted on top of the lead time | 3 |
| Maximum days of supply | The most days of stock the user wants to hold | 30 |
| Target days of supply | Days of sales the stock should cover after reordering | 14 |

The starting values are **provisional**. The paper says the defaults will be set after the key
informant interviews (N4 to N7). The interviews in Appendix B do not give numbers for them.

## Formulas

| Measure | Formula | Paper |
|---|---|---|
| Average daily sales | Units sold in the sales period ÷ number of days the product was in stock | Feature 2 |
| Days of supply | Current stock ÷ average daily sales | Feature 2, Table 5 note |
| Target stock | Average daily sales × target days of supply | Feature 6 |
| Suggested reorder quantity | Target stock − (current stock + units on order), never below 0 | Feature 6 |
| Excess units | Current stock − (maximum days × average daily sales), never below 0 | Feature 9 |
| Estimated excess stock value | Excess units × unit cost | Feature 9 |
| Estimated days until stockout | Current stock ÷ average daily sales | Feature 10 |

Worked example: stock 100, 50 units sold, 10 days in stock → 50 ÷ 10 = 5 a day → 100 ÷ 5 = 20 days of supply.

The suggested reorder quantity counts units already on order as stock on its way. The paper did not include this yet; the app adds it as an extension.
It is a quantity for the user to review. BALANSE never places an order.

## Classification rules (Table 5)

Checked in this order; the first rule that fits gives the status.

| Order | Status | Rule |
|---|---|---|
| 1 | Stockout risk | Current stock is 0, **or** days of supply < replenishment lead time |
| 2 | No recent sales | Stock remains but no units were sold in the sales period, so days of supply cannot be calculated |
| 3 | Understock risk | Lead time ≤ days of supply < lead time + buffer days |
| 4 | Optimal | Lead time + buffer days ≤ days of supply ≤ maximum days |
| 5 | Overstock risk | Days of supply > maximum days |

Values exactly on a limit:

| Days of supply | Status |
|---|---|
| Equal to the lead time | Understock risk (Optimal if buffer days is 0) |
| Equal to lead time + buffer days | Optimal |
| Equal to the maximum days | Optimal |
| Above the maximum days | Overstock risk |

Comparisons use exact fractions, not rounded decimals, so a value on a limit is always
classified the same way.

## Suggested actions

| Status | Suggested action (for the user to review) |
|---|---|
| Stockout risk | Review the purchase order and consider replenishment. |
| Understock risk | Consider increasing the next replenishment quantity. |
| Optimal | Continue monitoring current inventory. |
| Overstock risk | Consider delaying or reviewing the next purchase. |
| No recent sales | Review the product's sales history and stock movement. |

## Decisions the paper leaves open

These are the prototype's choices. Please confirm each one or tell us what to change.

1. **How "days the product was in stock" is counted.** The paper gives the idea but not the method.
   - A day is counted as **out of stock** when the latest stock record on or before that day shows 0 units **and** nothing was sold that day.
   - A day with a sale always counts as in stock.
   - A day with no earlier stock record counts as in stock.
   - Days before the product's first record (the day it was added, or its first sale or stock record) are not counted, so a product added last week is not averaged over a whole month.
   - Today's stock is taken from the product's current stock.
2. **The sales period** ends today and includes today.
3. **Rounding of the suggested quantity.** The formula can give part of a unit. The quantity shown for review is rounded **up** to a whole unit. The exact value is kept in the calculation.
4. **Excess for "No recent sales".** With no sales rate the formula would call all stock "excess". The prototype shows "cannot be estimated" and the stock's value at unit cost, in line with Table 5 ("its current stock will be shown so that the user can judge").
5. **A product that was out of stock for the whole period but has stock now** has no sales to measure, so it is shown as No recent sales with its own explanation.
6. **Settings that overlap are refused.**
   - Target days above maximum days is an error (ordering to the target would cause Overstock risk).
   - Maximum days below lead time + buffer days for any product is an error (that product could never be Optimal). The same check runs when a product is added.
   - Target days below the longest lead time + buffer days gives a warning only.
7. **Recording a sale by hand** can subtract the quantity from current stock (ticked by default). **Imported sales** are treated as history and do not change current stock.
8. **Alerts.** Each product that is not Optimal has one alert. "Mark as reviewed" only records that the user has seen it. If the product's status changes, the alert is replaced and needs review again. It is removed when the product becomes Optimal.
9. **Reorder suggestions are shown for every product below its target stock**, including Optimal ones. The paper mentions products "at risk of understocking"; the Reorder screen in Table 4 lists a table of products. Use the Status column to focus on the at-risk ones.

## Not part of the calculations

The Price Market / Price Fluctuation page is a placeholder. No price information is used
anywhere in the formulas above. See `balanse/price_market.py`.
