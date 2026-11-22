# Barcode scanning and barcode labels (added feature)

Nothing that already existed was changed, except three lines in `app.py` that add the **Barcode Scan** page to the menu
(System group). `requirements.txt` is unchanged: no new package is needed.

## What was added
- `balanse/barcode_logic.py`: reads codes, makes Code 128 barcodes, makes the label sheet, saves the scanned list (no Streamlit inside).
- `balanse/views_barcode.py`: the **Barcode Scan** page with two tabs, **Scan** and **Barcode labels**.
- `balanse/barcode_scanner_component/index.html`: the camera reader (one HTML file).
- `tests/test_barcode.py`: 49 tests. `docs/BARCODE_SCANNING.md`: this file.

Every product already has a barcode. It is a Code 128 barcode holding the product's own number in the system, printed under
it as `BAL12`. No new column, no new table, and nobody has to re-enter products.

## Use the scanner
1. Open **Barcode Scan → Scan** on a phone (Android Chrome) or a laptop with a camera. Press **Start camera**, allow access.
2. Hold a product's barcode flat inside the wide box, about 15 to 25 cm away, in good light. Each scan adds the product to the **Scanned list**
   (quantity 1, action Sale).
3. Scan the same label again to add one more unit. Holding the same label in view counts once.
4. Change the **Quantity** and choose **Sale** or **Add stock** for each line. Press the X to remove a line.
5. Press **Save**. Sales go to Sales History with today's date and reduce stock (untick the box to keep stock unchanged).
   Added stock raises current stock. Dashboard, statuses and alerts recalculate with the existing rules.
Nothing is saved until Save is pressed. If any line is wrong (for example more sold than in stock), nothing is saved.

Camera not working? Open **Camera not working? Add a product by hand**: type the code under the barcode, or pick the product.

## Make and print labels
1. **Barcode Scan → Barcode labels**. Choose the products (all are selected).
2. **Download printable label sheet**, open the file in a browser, press **Print labels** at 100% size. Each barcode is about 6 cm wide.
   Keep labels flat and clean (no folds or shiny glare). **Download one barcode image** gives a single PNG.

## Deployment notes
- Phone cameras only work on **https** pages (or `localhost`). Use the Streamlit Community Cloud link; the plain `http://192.168...` address will not work.
- Android Chrome has a built-in barcode reader and uses it. Other browsers (most laptops) load the small ZXing library from jsDelivr, so they need internet once.
- The Windows installer build (`Balanse.spec`) already copies the whole `balanse` folder, so the scanner file is included.
- Labels from one store are not accepted in another store (the app says so).
- Older QR labels are gone: this version makes and reads barcodes only. The text `BALANSE-12` typed by hand is still understood.

## Test results (what was run)
- All 149 existing tests still pass. 49 new tests pass (reading codes, the barcode encoder, sales, added stock, bad quantities, not enough stock,
  nothing saved when one line is wrong, storage failure, status recalculation) on both the local file and the Supabase code path.
- The barcode encoder was checked against reportlab's Code 128 (table and symbols match exactly). A printed PNG was read back along its middle row and gives the same bars.
- The camera file was run in Chromium with a pretend camera and a pretend barcode reader: it starts, sends one event per scan, does not repeat
  while the label stays in view, scans again after it leaves, stops, and shows clear messages for blocked, missing and unloadable readers.

## Not tested here (please check once on your phone)
- Real camera decoding of a printed barcode on a real phone, and the ZXing fallback used on laptops (no internet access in the build environment).
- The Streamlit page itself (Streamlit could not be installed here). The page code was syntax-checked only. Run the app once, open Barcode Scan, and try one scan end to end.

## Limits
- A person still scans, checks the quantity and presses Save.
- One-dimensional barcodes need a flat label held level in the wide box. Curved or tiny labels scan badly.
- Real store barcodes (EAN or UPC printed on products) are not linked to products. That needs a new product field, which was left out on purpose.
- If one line fails to save halfway (internet drops), the lines already saved leave the list and the rest stay for a retry.
- Sales are dated today. Past sales still come from Data Input or CSV import.
