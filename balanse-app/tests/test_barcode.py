"""Barcode scanning: reading codes, the Code 128 encoder, saving the scanned list, and the label pictures."""
from datetime import date

import pytest

from balanse import barcode_logic, services
from balanse.repository import LocalRepository, StorageError, SupabaseRepository

from .fake_supabase import FakeSupabase

TODAY = date(2026, 11, 22)


@pytest.fixture(params=["local", "supabase"])
def repo(request, tmp_path):
    return LocalRepository(str(tmp_path / "bc.db")) if request.param == "local" else SupabaseRepository(FakeSupabase())


def make(repo, name, stock):
    return services.add_products(repo, [{"name": name, "category": "Test", "current_stock": stock, "unit_cost": 10.0, "lead_time_days": 3}])[0]


def line(product, action, qty):
    return {"product_id": product["id"], "action": action, "quantity": qty}


# ---------------------------------------------------------------- reading codes
@pytest.mark.parametrize("text,expected", [
    ("BAL12", 12), ("  bal-7 ", 7), ("BALANSE-31", 31), ("balanse-5", 5), ("BAL0", 0),
    ("BAL", None), ("BAL12abc", None), ("hello", None), ("12", None), ("", None), (None, None),
    ("BALANSE12", None), ("BAL--3", None), ("5901234123457", None), ("https://x.y/?code=BAL1", None),
])
def test_parse_scan(text, expected):
    assert barcode_logic.parse_scan(text) == expected


def test_parse_by_hand_accepts_a_bare_number():
    assert barcode_logic.parse_scan("12", allow_number=True) == 12
    assert barcode_logic.parse_scan("abc", allow_number=True) is None


def test_product_code_reads_back():
    assert barcode_logic.product_code(5) == "BAL5"
    assert barcode_logic.parse_scan(barcode_logic.product_code(123456)) == 123456


def test_find_product_matches_int_and_text_ids():
    products = [{"id": 4, "name": "A"}]
    assert barcode_logic.find_product(products, "4")["name"] == "A"
    assert barcode_logic.find_product(products, 5) is None


# ---------------------------------------------------------------- Code 128 encoder
def test_pattern_table_is_well_formed():
    table = barcode_logic._PATTERNS
    assert len(table) == 107 and len(set(table)) == 107
    assert all(sum(map(int, t)) == 11 for t in table[:106]) and table[106] == "2331112"
    assert all(sum(int(w) for w in t[0::2]) % 2 == 0 for t in table[:106])      # every symbol has an even bar total


def test_encoder_rejects_bad_text():
    for bad in ["", "é", "a\nb"]:
        with pytest.raises(ValueError):
            barcode_logic.code128_modules(bad)


def test_encoder_matches_reportlab():
    """reportlab is only a test reference (the app does not need it): its Code 128 table and symbols must match ours."""
    code128 = pytest.importorskip("reportlab.graphics.barcode.code128")
    widths = lambda letters: "".join(str(ord(ch.upper()) - 64) for ch in letters)
    assert barcode_logic._PATTERNS == tuple(widths(code128._patterns[i]) for i in range(107))
    texts = ["BAL1", "BAL12", "BALANSE-12", "Hello World", "a1b2c3d4e5f6g7h8i9j0",
             "".join(chr(i) for i in range(32, 127) if not chr(i).isdigit())]
    for text in texts:
        ref = code128.Code128(text, barWidth=1, quiet=0)
        ref.validate()
        ref.encode()
        symbols = list(ref.encoded)
        assert symbols[0] == 104 and all(v < 96 for v in symbols[1:-2]), text      # plain character set B throughout
        assert barcode_logic.code128_modules(text) == "".join(barcode_logic._expand(barcode_logic._PATTERNS[v]) for v in symbols)


# ---------------------------------------------------------------- saving
def current(repo, product):
    return next(p for p in repo.list_products() if p["id"] == product["id"])["current_stock"]


def test_sale_reduces_stock_and_lands_in_sales_history(repo):
    tea = make(repo, "Tea", 20)
    saved, words, problems = barcode_logic.save_lines(repo, repo.list_products(), [line(tea, barcode_logic.SALE, 3)], today=TODAY)
    assert problems == [] and saved == [str(tea["id"])]
    assert current(repo, tea) == 17
    sales = repo.list_sales(tea["id"])
    assert [(s["sale_date"], s["quantity_sold"]) for s in sales] == [(TODAY, 3.0)]


def test_add_stock_raises_stock_without_a_sale(repo):
    tea = make(repo, "Tea", 20)
    saved, _, problems = barcode_logic.save_lines(repo, repo.list_products(), [line(tea, barcode_logic.STOCK, 10)], today=TODAY)
    assert problems == [] and current(repo, tea) == 30
    assert repo.list_sales(tea["id"]) == []


def test_sale_without_subtracting_keeps_stock(repo):
    tea = make(repo, "Tea", 20)
    barcode_logic.save_lines(repo, repo.list_products(), [line(tea, barcode_logic.SALE, 3)], deduct_sales=False, today=TODAY)
    assert current(repo, tea) == 20 and len(repo.list_sales(tea["id"])) == 1


def test_mixed_list_saves_each_line(repo):
    tea, jam = make(repo, "Tea", 20), make(repo, "Jam", 5)
    saved, words, problems = barcode_logic.save_lines(
        repo, repo.list_products(), [line(tea, barcode_logic.SALE, 2), line(jam, barcode_logic.STOCK, 4)], today=TODAY)
    assert problems == [] and len(saved) == 2 and len(words) == 2
    assert (current(repo, tea), current(repo, jam)) == (18, 9)


@pytest.mark.parametrize("qty", [0, -1, None, "", "abc"])
def test_bad_quantity_is_refused(repo, qty):
    tea = make(repo, "Tea", 20)
    saved, _, problems = barcode_logic.save_lines(repo, repo.list_products(), [line(tea, barcode_logic.SALE, qty)], today=TODAY)
    assert saved == [] and problems and current(repo, tea) == 20


def test_not_enough_stock_saves_nothing_at_all(repo):
    tea, jam = make(repo, "Tea", 20), make(repo, "Jam", 2)
    saved, _, problems = barcode_logic.save_lines(
        repo, repo.list_products(), [line(tea, barcode_logic.SALE, 5), line(jam, barcode_logic.SALE, 9)], today=TODAY)
    assert saved == [] and "Not enough stock" in problems[0]
    assert (current(repo, tea), current(repo, jam)) == (20, 2) and repo.list_sales() == []


def test_unknown_product_duplicate_line_and_empty_list(repo):
    tea = make(repo, "Tea", 20)
    products = repo.list_products()
    assert barcode_logic.save_lines(repo, products, [{"product_id": 9999, "action": barcode_logic.SALE, "quantity": 1}], today=TODAY)[2]
    twice = [line(tea, barcode_logic.SALE, 1), line(tea, barcode_logic.SALE, 1)]
    assert "twice" in barcode_logic.save_lines(repo, products, twice, today=TODAY)[2][0]
    assert barcode_logic.save_lines(repo, products, [], today=TODAY)[2]
    assert barcode_logic.save_lines(repo, products, [line(tea, "Other", 1)], today=TODAY)[2]
    assert current(repo, tea) == 20 and repo.list_sales() == []


def test_storage_failure_reports_which_lines_were_saved(repo, monkeypatch):
    tea, jam = make(repo, "Tea", 20), make(repo, "Jam", 20)
    real, calls = repo.insert_sales, []

    def flaky(rows):
        calls.append(1)
        if len(calls) == 2:
            raise StorageError("connection lost")
        return real(rows)

    monkeypatch.setattr(repo, "insert_sales", flaky)
    saved, _, problems = barcode_logic.save_lines(
        repo, repo.list_products(), [line(tea, barcode_logic.SALE, 1), line(jam, barcode_logic.SALE, 1)], today=TODAY)
    assert saved == [str(tea["id"])] and "Jam" in problems[0]        # the screen keeps Jam on the list for a retry


def test_status_recalculates_after_a_scanned_sale(repo):
    """The existing engine reads what the scan saved: selling most of the stock changes the product's status."""
    tea = make(repo, "Tea", 30)
    before = services.load_everything(repo, TODAY)["results"][0]["status"]
    barcode_logic.save_lines(repo, repo.list_products(), [line(tea, barcode_logic.SALE, 30)], today=TODAY)
    after = services.load_everything(repo, TODAY)["results"][0]
    assert after["current_stock"] == 0 and after["status"] != before


# ---------------------------------------------------------------- pictures
def runs_to_modules(png_bytes, module_px):
    """Read a barcode PNG back along its middle row, as a person's scanner would, into 1/0 modules."""
    import io
    from PIL import Image
    image = Image.open(io.BytesIO(png_bytes)).convert("L")
    row = [image.getpixel((x, image.height // 2)) < 128 for x in range(image.width)]
    modules = [row[x] for x in range(0, image.width, module_px)]
    return "".join("1" if m else "0" for m in modules)


def test_png_reads_back_to_the_same_modules():
    pytest.importorskip("PIL")
    text = barcode_logic.product_code(42)
    modules = runs_to_modules(barcode_logic.barcode_png(text, module_px=4), 4)
    bits = barcode_logic.code128_modules(text)
    assert modules == "0" * 10 + bits + "0" * 10                        # bars with the empty margins either side


def test_svg_and_label_sheet():
    svg = barcode_logic.barcode_svg("BAL1")
    assert svg.startswith("<svg") and "<rect" in svg
    html = barcode_logic.label_sheet_html([{"id": 1, "name": "Tea <b>"}, {"id": 22, "name": "Jam"}])
    assert "BAL1<" in html and "BAL22<" in html and "Tea &lt;b&gt;" in html and html.count("<svg") == 2
