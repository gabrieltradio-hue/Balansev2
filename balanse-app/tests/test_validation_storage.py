"""Input checks, CSV imports, both storage back ends, alerts and demonstration data."""
import io
from datetime import date, timedelta

import pandas as pd
import pytest

from balanse import demo_data, services, validation
from balanse.engine import OPTIMAL, STOCKOUT, UNDERSTOCK, Settings
from balanse.repository import LocalRepository, StorageError, SupabaseRepository, get_repository

from .cases import TODAY
from .fake_supabase import BrokenSupabase, FakeSupabase

GOOD = {"name": "Demo Tea", "category": "Beverages", "current_stock": "40", "unit_cost": "12.5", "lead_time_days": "5"}


@pytest.fixture(params=["local", "supabase"])
def repo(request, tmp_path):
    """Every storage test runs twice: on the local file and on the Supabase code path (with a stand-in client)."""
    if request.param == "local":
        return LocalRepository(str(tmp_path / "test.db"))
    return SupabaseRepository(FakeSupabase())


def frame(text: str) -> pd.DataFrame:
    data, problem = validation.read_csv(io.StringIO(text))
    assert problem is None, problem
    return data


# ------------------------------------------------------------------ products
def test_valid_product():
    clean, errors = validation.validate_product(GOOD, settings=Settings())
    assert errors == []
    assert clean == {"name": "Demo Tea", "category": "Beverages", "current_stock": 40.0, "unit_cost": 12.5, "lead_time_days": 5,
                     "on_order_units": 0}


@pytest.mark.parametrize("change,expected", [
    ({"current_stock": "-5"}, "Current stock cannot be negative."),                 # scenario 7
    ({"name": ""}, "Product name is required."),                                     # scenario 8
    ({"category": "  "}, "Product category is required."),
    ({"current_stock": ""}, "Current stock is required."),
    ({"unit_cost": None}, "Unit cost is required."),
    ({"unit_cost": "abc"}, "Unit cost must be a number"),
    ({"unit_cost": "-1"}, "Unit cost cannot be negative."),
    ({"lead_time_days": "-2"}, "Replenishment lead time (days) cannot be negative."),
    ({"lead_time_days": "2.5"}, "Replenishment lead time (days) must be a whole number."),
    ({"lead_time_days": "x"}, "Replenishment lead time (days) must be a number"),
    ({"lead_time_days": "400"}, "cannot be more than 365 days"),
    ({"current_stock": "nan"}, "Current stock must be a number"),
    ({"current_stock": "inf"}, "Current stock must be a number"),
])
def test_invalid_product(change, expected):
    _, errors = validation.validate_product(dict(GOOD, **change), settings=Settings())
    assert any(expected in e for e in errors), errors


def test_duplicate_product_name_is_rejected_but_editing_itself_is_fine():
    _, errors = validation.validate_product(GOOD, existing_names=["demo tea"])
    assert any("already exists" in e for e in errors)
    _, errors = validation.validate_product(GOOD, existing_names=["Demo Tea"], own_name="Demo Tea")
    assert errors == []


def test_zero_lead_time_and_zero_stock_are_allowed():
    _, errors = validation.validate_product(dict(GOOD, lead_time_days="0", current_stock="0"), settings=Settings())
    assert errors == []


def test_lead_time_that_leaves_no_optimal_range_is_rejected():
    _, errors = validation.validate_product(dict(GOOD, lead_time_days="29"), settings=Settings())   # 29 + 3 > 30
    assert any("No amount of stock could be Optimal" in e for e in errors)


# ------------------------------------------------------------------ settings (scenario 14)
def test_valid_settings():
    settings, errors, _ = validation.validate_settings(Settings().as_dict())
    assert errors == [] and settings == Settings()


@pytest.mark.parametrize("change,expected", [
    ({"sales_period_days": 0}, "Sales period (days) must be at least 1."),
    ({"buffer_days": -1}, "Buffer days cannot be negative."),
    ({"max_days_of_supply": 0}, "Maximum days of supply must be at least 1."),
    ({"target_days_of_supply": 0}, "Target days of supply must be at least 1."),
    ({"target_days_of_supply": "many"}, "Target days of supply must be a number"),
    ({"target_days_of_supply": 45}, "cannot be more than maximum days of supply"),
    ({"sales_period_days": 7.5}, "Sales period (days) must be a whole number."),
])
def test_invalid_settings(change, expected):
    settings, errors, _ = validation.validate_settings(dict(Settings().as_dict(), **change))
    assert settings is None and any(expected in e for e in errors), errors


def test_overlapping_limits_are_rejected():
    products = [{"name": "Slow supplier item", "lead_time_days": 20}]
    settings, errors, _ = validation.validate_settings(dict(Settings().as_dict(), max_days_of_supply=20, target_days_of_supply=14), products)
    assert settings is None and any("overlap" in e for e in errors)


def test_low_target_gives_a_warning_not_an_error():
    products = [{"name": "Slow supplier item", "lead_time_days": 20}]
    settings, errors, warnings = validation.validate_settings(Settings().as_dict(), products)
    assert settings is not None and errors == [] and warnings


# ------------------------------------------------------------------ CSV (scenario 13)
def test_products_csv_accepts_good_rows_and_explains_bad_ones():
    text = ("Product Name,Category,Current Stock,Unit Cost,Lead Time (days)\n"
            "Demo A,Beverages,10,5,3\n"
            "Demo B,Beverages,-4,5,3\n"
            ",Beverages,4,5,3\n"
            "Demo C,Beverages,ten,5,3\n"
            "Demo A,Beverages,10,5,3\n"
            "Demo D,Beverages,10,5,3\n"
            "Demo D,Beverages,99,5,3\n")
    valid, rejected, problems = validation.check_products_csv(frame(text), settings=Settings())
    assert problems == []
    assert [v["name"] for v in valid] == ["Demo A", "Demo D"]
    reasons = {r["row"]: r["problem"] for r in rejected}
    assert "cannot be negative" in reasons[3]
    assert "Product name is required" in reasons[4]
    assert "must be a number" in reasons[5]
    assert "Duplicate of row 2" in reasons[6]
    assert "Conflicts with row 7" in reasons[8]


def test_products_csv_with_missing_column():
    valid, rejected, problems = validation.check_products_csv(frame("Product Name,Category,Stock\nA,B,1\n"))
    assert valid == [] and len(problems) == 2 and "unit cost" in problems[0]


def test_products_csv_rejects_names_already_saved():
    text = "name,category,stock,unit cost,lead time\nDemo A,Beverages,10,5,3\n"
    valid, rejected, _ = validation.check_products_csv(frame(text), existing_names=["demo a"])
    assert valid == [] and "already exists" in rejected[0]["problem"]


@pytest.mark.parametrize("text,expected", [
    ("", "empty"),
    ("just one column\nvalue\n", "does not look like a CSV"),
    ("a,b,c\n", "no rows"),
])
def test_unreadable_csv_files(text, expected):
    data, problem = validation.read_csv(io.StringIO(text))
    assert data is None and expected in problem


def test_sales_csv():
    products = {"demo a": {"id": 7, "name": "Demo A"}}
    text = ("product,date,quantity sold\n"
            "Demo A,2026-11-05,4\n"
            "demo a,11/06/2026,2.5\n"
            "Demo A,2026-13-45,4\n"
            "Demo A,2026-11-07,0\n"
            "Demo A,2026-11-07,-3\n"
            "Unknown,2026-11-07,3\n"
            "Demo A,2027-01-01,3\n"
            "Demo A,2026-11-01,9\n")
    valid, rejected, problems = validation.check_sales_csv(
        frame(text), products_by_name=products, existing_sales=[(7, date(2026, 11, 1), 9.0)], today=TODAY)
    assert problems == []
    assert [(v["sale_date"], v["quantity_sold"]) for v in valid] == [(date(2026, 11, 5), 4.0), (date(2026, 11, 6), 2.5)]
    reasons = {r["row"]: r["problem"] for r in rejected}
    assert "not a valid date" in reasons[4]
    assert "must be more than 0" in reasons[5]
    assert "cannot be negative" in reasons[6]
    assert "not in your product list" in reasons[7]
    assert "cannot be in the future" in reasons[8]
    assert "already saved" in reasons[9]


def test_stock_csv():
    products = {"demo a": {"id": 7, "name": "Demo A"}}
    text = ("product name,record date,stock quantity\n"
            "Demo A,2026-11-01,50\nDemo A,2026-11-02,-1\nDemo A,2026-11-01,60\nDemo A,bad,5\n")
    valid, rejected, _ = validation.check_stock_csv(frame(text), products_by_name=products, today=TODAY)
    assert len(valid) == 1 and valid[0]["stock_quantity"] == 50
    reasons = {r["row"]: r["problem"] for r in rejected}
    assert "cannot be negative" in reasons[3] and "Conflicts with row 2" in reasons[4] and "not a valid date" in reasons[5]


def test_sample_csv_files_import_cleanly(repo):
    products, rejected, problems = validation.check_products_csv(pd.read_csv("sample_data/products.csv", dtype=str, keep_default_na=False), settings=Settings())
    assert problems == [] and rejected == [] and len(products) >= 5
    saved = services.add_products(repo, products, TODAY)
    by_name = {p["name"].lower(): p for p in saved}
    sales, rejected, problems = validation.check_sales_csv(pd.read_csv("sample_data/sales.csv", dtype=str, keep_default_na=False), products_by_name=by_name, today=date(2030, 1, 1))
    assert problems == [] and rejected == [] and sales
    stock, rejected, problems = validation.check_stock_csv(pd.read_csv("sample_data/stock_records.csv", dtype=str, keep_default_na=False), products_by_name=by_name, today=date(2030, 1, 1))
    assert problems == [] and rejected == [] and stock
    bad, rejected, problems = validation.check_products_csv(pd.read_csv("sample_data/products_with_errors.csv", dtype=str, keep_default_na=False), settings=Settings())
    assert problems == [] and len(rejected) >= 4


# ------------------------------------------------------------------ storage
def test_save_and_read_back(repo):
    clean, _ = validation.validate_product(GOOD)
    saved = services.add_products(repo, [clean], TODAY)
    assert len(saved) == 1 and saved[0]["id"]
    products = repo.list_products()
    assert products[0]["name"] == "Demo Tea" and products[0]["current_stock"] == 40.0 and products[0]["is_demo"] is False
    assert repo.list_inventory_records()[0]["record_date"] == TODAY           # stock history starts on the day it was added
    repo.insert_sales([{"product_id": saved[0]["id"], "sale_date": TODAY, "quantity_sold": 3}])
    assert repo.list_sales()[0]["sale_date"] == TODAY and repo.list_sales(saved[0]["id"])[0]["quantity_sold"] == 3.0


def test_database_refuses_a_duplicate_name(repo):
    clean, _ = validation.validate_product(GOOD)
    services.add_products(repo, [clean], TODAY)
    with pytest.raises(StorageError):
        repo.insert_products([clean])
    assert len(repo.list_products()) == 1


def test_database_refuses_negative_stock(repo):
    with pytest.raises(StorageError):
        repo.insert_products([dict(GOOD, current_stock=-1, unit_cost=1, lead_time_days=1)])


def test_settings_are_saved_and_default_when_missing(repo):
    assert services.get_settings(repo) == Settings()
    settings, errors, _ = services.save_settings(repo, dict(Settings().as_dict(), sales_period_days=14, buffer_days=2))
    assert errors == [] and services.get_settings(repo).sales_period_days == 14
    _, errors, _ = services.save_settings(repo, dict(Settings().as_dict(), target_days_of_supply=99))
    assert errors and services.get_settings(repo).sales_period_days == 14     # the bad settings were not saved


def test_recording_a_sale_updates_stock_only_when_asked(repo):
    product = services.add_products(repo, [validation.validate_product(GOOD)[0]], TODAY)[0]
    sale = {"sale_date": TODAY, "quantity_sold": 4}
    assert services.record_sale(repo, product, sale, deduct_from_stock=True, as_of=TODAY) == []
    assert repo.list_products()[0]["current_stock"] == 36
    product = repo.list_products()[0]
    assert services.record_sale(repo, product, sale, deduct_from_stock=False, as_of=TODAY) == []
    assert repo.list_products()[0]["current_stock"] == 36
    problems = services.record_sale(repo, product, {"sale_date": TODAY, "quantity_sold": 999}, deduct_from_stock=True, as_of=TODAY)
    assert problems and "Not enough stock" in problems[0] and len(repo.list_sales()) == 2


def test_results_recalculate_when_data_changes(repo):
    product = services.add_products(repo, [validation.validate_product(dict(GOOD, current_stock="18"))[0]], TODAY)[0]
    repo.insert_sales([{"product_id": product["id"], "sale_date": TODAY - timedelta(days=i), "quantity_sold": 8} for i in range(30)])
    repo.update_product(product["id"], {"current_stock": 18})
    assert services.load_everything(repo, TODAY)["results"][0]["status"] == STOCKOUT
    services.update_product(repo, repo.list_products()[0], dict(validation.validate_product(dict(GOOD, current_stock="120"))[0]), TODAY)
    assert services.load_everything(repo, TODAY)["results"][0]["status"] == OPTIMAL
    services.save_settings(repo, dict(Settings().as_dict(), buffer_days=11))      # 5 + 11 = 16 > 15 days of supply
    assert services.load_everything(repo, TODAY)["results"][0]["status"] == UNDERSTOCK


def test_alerts_and_mark_as_reviewed(repo):
    assert services.load_demo_data(repo, TODAY) == []
    data = services.load_everything(repo, TODAY)
    alerts = data["alerts"]
    assert len(alerts) == sum(1 for r in data["results"] if r["status"] != OPTIMAL) == 8
    assert all(not a["reviewed"] for a in alerts)
    assert alerts[0]["classification"] == STOCKOUT                                  # most urgent first
    target = alerts[0]["product_id"]
    stock_before = {p["id"]: p["current_stock"] for p in repo.list_products()}
    repo.set_alert_reviewed(target, True)
    again = services.load_everything(repo, TODAY)
    reviewed = next(a for a in again["alerts"] if a["product_id"] == target)
    assert reviewed["reviewed"] is True
    assert reviewed["classification"] == STOCKOUT                                   # reviewing does not change the status
    assert {p["id"]: p["current_stock"] for p in repo.list_products()} == stock_before   # or the stock
    assert [r["status"] for r in again["results"]] == [r["status"] for r in data["results"]]
    # the status changes -> the alert is replaced and needs review again
    product = next(p for p in repo.list_products() if p["id"] == target)
    repo.update_product(target, {"current_stock": product["current_stock"] + 35})
    changed = next((a for a in services.load_everything(repo, TODAY)["alerts"] if a["product_id"] == target), None)
    assert changed is None or changed["reviewed"] is False


def test_alert_is_removed_when_a_product_becomes_optimal(repo):
    services.load_demo_data(repo, TODAY)
    cola = next(p for p in repo.list_products() if p["name"].startswith("Demo Cola"))
    repo.update_product(cola["id"], {"current_stock": 120})                          # 120 / 8 = 15 days -> Optimal
    alerts = services.load_everything(repo, TODAY)["alerts"]
    assert cola["id"] not in {a["product_id"] for a in alerts}


def test_demo_data_is_labelled_separate_and_removable(repo):
    assert services.load_demo_data(repo, TODAY) == []
    products = repo.list_products()
    assert len(products) == len(demo_data.PRODUCTS) and all(p["is_demo"] for p in products)
    assert "already loaded" in services.load_demo_data(repo, TODAY)[0]
    assert services.clear_demo_data(repo) == len(demo_data.PRODUCTS)
    assert repo.list_products() == [] and repo.list_sales() == [] and repo.list_inventory_records() == [] and repo.list_alerts() == []
    services.add_products(repo, [validation.validate_product(GOOD)[0]], TODAY)       # a real product
    problems = services.load_demo_data(repo, TODAY)
    assert problems and "not mixed" in problems[0] and len(repo.list_products()) == 1


def test_demo_category_can_be_changed():
    assert {p["category"] for p in demo_data.build(TODAY, "Canned goods")["products"]} == {"Canned goods"}


def test_deleting_a_product_removes_its_records(repo):
    services.load_demo_data(repo, TODAY)
    cola = next(p for p in repo.list_products() if p["name"].startswith("Demo Cola"))
    services.delete_product(repo, cola["id"])
    assert repo.list_sales(cola["id"]) == [] and repo.list_inventory_records(cola["id"]) == []


def test_supabase_paging_reads_more_than_1000_rows():
    repo = SupabaseRepository(FakeSupabase())
    product = repo.insert_products([validation.validate_product(GOOD)[0]])[0]
    repo.insert_sales([{"product_id": product["id"], "sale_date": TODAY - timedelta(days=i % 30), "quantity_sold": 1} for i in range(2350)])
    assert len(repo.list_sales()) == 2350


def test_database_failure_becomes_a_readable_error():
    repo = SupabaseRepository(BrokenSupabase())
    with pytest.raises(StorageError) as caught:
        repo.list_products()
    assert "Supabase could not read" in str(caught.value)


def test_back_end_is_chosen_from_the_environment(tmp_path):
    local = get_repository({"BALANSE_LOCAL_DB": str(tmp_path / "x.db")})
    assert isinstance(local, LocalRepository)
    with pytest.raises(StorageError):
        get_repository({"SUPABASE_URL": "not-a-url", "SUPABASE_KEY": "x"})


# ------------------------------------------------------------------ stores
def _add(repo, name="Tea"):
    return repo.insert_products([validation.validate_product(dict(GOOD, name=name))[0]])[0]


def test_a_first_store_exists_and_new_stores_start_empty(repo):
    assert [s["name"] for s in repo.list_stores()] == ["Main store"]
    _add(repo)
    other = repo.create_store("Branch 2")
    repo.use_store(other["id"])
    assert repo.list_products() == [] and repo.list_sales() == [] and repo.list_alerts() == [] and repo.get_settings() is None


def test_stores_keep_their_data_apart(repo):
    main = repo.list_stores()[0]["id"]
    tea = _add(repo)
    repo.insert_sales([{"product_id": tea["id"], "sale_date": TODAY, "quantity_sold": 2}])
    repo.save_settings({"sales_period_days": 30, "buffer_days": 3, "max_days_of_supply": 30, "target_days_of_supply": 14})
    other = repo.create_store("Branch 2")
    repo.use_store(other["id"])
    again = _add(repo)                                     # the same product name is fine in another store
    assert again["id"] != tea["id"] and len(repo.list_products()) == 1 and repo.list_sales() == []
    repo.save_settings({"sales_period_days": 14, "buffer_days": 1, "max_days_of_supply": 20, "target_days_of_supply": 10})
    repo.use_store(main)
    assert len(repo.list_sales()) == 1 and repo.get_settings()["buffer_days"] == 3
    assert [p["id"] for p in repo.list_products()] == [tea["id"]]


def test_store_names_are_checked(repo):
    repo.create_store("Branch 2")
    for bad in ("", "   ", "branch 2", "x" * 61):
        with pytest.raises(StorageError):
            repo.create_store(bad)
    with pytest.raises(StorageError):
        repo.rename_store(repo.list_stores()[0]["id"], "BRANCH 2")


def test_deleting_a_store_removes_only_its_data_and_the_last_store_stays(repo):
    main = repo.list_stores()[0]["id"]
    _add(repo)
    other = repo.create_store("Branch 2")
    repo.use_store(other["id"])
    _add(repo, "Coffee")
    repo.delete_store(other["id"])
    assert [s["name"] for s in repo.list_stores()] == ["Main store"] and repo.store_id == main
    assert [p["name"] for p in repo.list_products()] == ["Tea"]
    with pytest.raises(StorageError):
        repo.delete_store(main)


def test_demo_data_clear_only_touches_the_open_store(repo):
    services.load_demo_data(repo, TODAY)
    other = repo.create_store("Branch 2")
    repo.use_store(other["id"])
    services.load_demo_data(repo, TODAY)
    repo.delete_demo_products()
    assert repo.list_products() == []
    repo.use_store(repo.list_stores()[0]["id"])
    assert len(repo.list_products()) > 0


def test_an_older_local_file_is_moved_into_main_store(tmp_path):
    import sqlite3
    path = str(tmp_path / "old.db")
    db = sqlite3.connect(path)
    db.executescript("""
        create table products (id integer primary key autoincrement, name text not null unique collate nocase, category text not null,
            current_stock real not null, unit_cost real not null, lead_time_days integer not null, is_demo integer not null default 0,
            created_at text not null, updated_at text not null);
        create table sales_records (id integer primary key autoincrement, product_id integer not null references products(id) on delete cascade,
            sale_date text not null, quantity_sold real not null);
        create table user_settings (id integer primary key check (id = 1), sales_period_days integer not null, buffer_days integer not null,
            max_days_of_supply integer not null, target_days_of_supply integer not null, updated_at text not null);
        insert into products values (1, 'Tea', 'Drinks', 10, 5, 3, 0, '2026-01-01', '2026-01-01');
        insert into sales_records values (1, 1, '2026-01-02', 4);
        insert into user_settings values (1, 30, 2, 40, 20, '2026-01-01');
    """)
    db.commit()
    db.close()
    repo = LocalRepository(path)
    assert [s["name"] for s in repo.list_stores()] == ["Main store"]
    assert [p["name"] for p in repo.list_products()] == ["Tea"] and len(repo.list_sales()) == 1
    assert repo.get_settings() == {"sales_period_days": 30, "buffer_days": 2, "max_days_of_supply": 40, "target_days_of_supply": 20}
    assert LocalRepository(path).list_products()[0]["name"] == "Tea"        # opening it again changes nothing


def test_units_on_order_are_optional_and_checked():
    clean, errors = validation.validate_product({**GOOD})
    assert not errors and clean["on_order_units"] == 0           # blank means none
    clean, errors = validation.validate_product({**GOOD, "on_order_units": "30"})
    assert not errors and clean["on_order_units"] == 30
    _, errors = validation.validate_product({**GOOD, "on_order_units": "-4"})
    assert any("Units on order" in e for e in errors)
    _, errors = validation.validate_product({**GOOD, "on_order_units": "2.5"})
    assert any("whole number" in e for e in errors)


def test_units_on_order_are_saved_and_read_back(repo):
    saved = services.add_products(repo, [{**validation.validate_product({**GOOD, "on_order_units": "30"})[0]}])
    assert saved[0]["on_order_units"] == 30
    repo.update_product(saved[0]["id"], {"on_order_units": 12})
    assert repo.list_products()[0]["on_order_units"] == 12


def test_old_database_file_gains_the_on_order_column(tmp_path):
    """A file created before this column existed must open and read as 0 on order."""
    import sqlite3
    from balanse.repository import LOCAL_SCHEMA, PRODUCTS_TABLE
    path = tmp_path / "old.db"
    db = sqlite3.connect(path)
    db.executescript(LOCAL_SCHEMA)
    db.execute("insert into stores (name, created_at) values ('Main', '2026-01-01')")
    old_table = PRODUCTS_TABLE.format(name="products").replace("    on_order_units real not null default 0 check (on_order_units >= 0),\n", "")
    db.executescript(old_table)
    db.execute("insert into products (store_id, name, category, current_stock, unit_cost, lead_time_days, is_demo, created_at, updated_at) "
               "values (1, 'Cola', 'Drinks', 5, 10, 3, 0, '2026-01-01', '2026-01-01')")
    db.commit()
    db.close()
    repo = LocalRepository(str(path))
    assert repo.list_products()[0]["on_order_units"] == 0
