"""Storage for BALANSE.

Two interchangeable back ends with the same methods and the same tables:

  SupabaseRepository   the database named in the research paper. Used when
                       SUPABASE_URL and SUPABASE_KEY are set.
  LocalRepository      a SQLite file on this computer (built into Python).
                       Used when no Supabase credentials are set, so the
                       prototype can be run, demonstrated and tested offline.

The rest of the app only talks to the Repository interface, so it does not
know or care which one is active. The SQL for Supabase is in sql/schema.sql.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime, timezone
from typing import Iterable, Optional

PAGE = 1000    # Supabase returns at most 1,000 rows per request
CHUNK = 500    # rows per insert request

SETTINGS_FIELDS = ("sales_period_days", "buffer_days", "max_days_of_supply", "target_days_of_supply")


class StorageError(Exception):
    """A database problem, worded so it can be shown to the user."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _to_date(value) -> Optional[date]:
    if value is None or isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value)[:10])


def _iso(value) -> Optional[str]:
    return value.isoformat() if isinstance(value, (date, datetime)) else value


def _chunks(rows: list, size: int = CHUNK):
    for start in range(0, len(rows), size):
        yield rows[start:start + size]


DEFAULT_STORE_NAME = "Main store"


class Repository:
    """Shared clean-up of rows, so both back ends return exactly the same shapes.

    Every inventory (products, sales, stock records, alerts, settings) belongs to one store.
    The repository works on one store at a time: store_id, changed with use_store().
    """
    backend = "none"
    store_id: Optional[int] = None

    @staticmethod
    def _clean_store_name(name: str) -> str:
        name = " ".join(str(name or "").split())
        if not name:
            raise StorageError("Give the store a name.")
        if len(name) > 60:
            raise StorageError("The store name can be at most 60 characters.")
        return name

    @staticmethod
    def _product(row: dict) -> dict:
        row = dict(row)
        row["current_stock"] = float(row["current_stock"])
        row["unit_cost"] = float(row["unit_cost"])
        row["lead_time_days"] = int(row["lead_time_days"])
        row["is_demo"] = bool(row.get("is_demo"))
        row["created_on"] = _to_date(row.get("created_at"))
        return row

    @staticmethod
    def _sale(row: dict) -> dict:
        row = dict(row)
        row["sale_date"] = _to_date(row["sale_date"])
        row["quantity_sold"] = float(row["quantity_sold"])
        return row

    @staticmethod
    def _record(row: dict) -> dict:
        row = dict(row)
        row["record_date"] = _to_date(row["record_date"])
        row["stock_quantity"] = float(row["stock_quantity"])
        return row

    @staticmethod
    def _alert(row: dict) -> dict:
        row = dict(row)
        row["reviewed"] = bool(row.get("reviewed"))
        return row


# ====================================================================== SQLite
PRODUCTS_TABLE = """
create table {name} (
    id integer primary key autoincrement,
    store_id integer not null references stores(id) on delete cascade,
    name text not null collate nocase,
    category text not null,
    current_stock real not null check (current_stock >= 0),
    unit_cost real not null check (unit_cost >= 0),
    lead_time_days integer not null check (lead_time_days >= 0),
    is_demo integer not null default 0,
    created_at text not null,
    updated_at text not null,
    unique (store_id, name)
);"""

LOCAL_SCHEMA = """
create table if not exists stores (
    id integer primary key autoincrement,
    name text not null unique collate nocase,
    created_at text not null
);
create table if not exists app_meta (key text primary key, value text);
create table if not exists store_settings (
    store_id integer primary key references stores(id) on delete cascade,
    sales_period_days integer not null check (sales_period_days >= 1),
    buffer_days integer not null check (buffer_days >= 0),
    max_days_of_supply integer not null check (max_days_of_supply >= 1),
    target_days_of_supply integer not null check (target_days_of_supply >= 1),
    updated_at text not null
);
create table if not exists sales_records (
    id integer primary key autoincrement,
    product_id integer not null references products(id) on delete cascade,
    sale_date text not null,
    quantity_sold real not null check (quantity_sold > 0)
);
create index if not exists sales_product_date on sales_records(product_id, sale_date);
create table if not exists inventory_records (
    id integer primary key autoincrement,
    product_id integer not null references products(id) on delete cascade,
    record_date text not null,
    stock_quantity real not null check (stock_quantity >= 0),
    unique (product_id, record_date)
);
create table if not exists user_settings (
    id integer primary key check (id = 1),
    sales_period_days integer not null check (sales_period_days >= 1),
    buffer_days integer not null check (buffer_days >= 0),
    max_days_of_supply integer not null check (max_days_of_supply >= 1),
    target_days_of_supply integer not null check (target_days_of_supply >= 1),
    updated_at text not null
);
create table if not exists alerts (
    id integer primary key autoincrement,
    product_id integer not null unique references products(id) on delete cascade,
    classification text not null,
    explanation text not null,
    suggested_action text not null,
    reviewed integer not null default 0,
    reviewed_at text,
    created_at text not null
);
-- Reserved for the future Price Market module. Nothing reads or writes it yet.
create table if not exists price_records (
    id integer primary key autoincrement,
    product_id integer references products(id) on delete cascade,
    market_or_supplier text,
    recorded_price real,
    price_unit text,
    date_recorded text,
    data_source text
);
"""


class LocalRepository(Repository):
    backend = "Local file (SQLite)"

    def __init__(self, path: str = "balanse_local.db"):
        self.path = path
        try:
            self._db = sqlite3.connect(path, check_same_thread=False)
            self._db.row_factory = sqlite3.Row
            self._db.execute("pragma foreign_keys = on")
            self._db.executescript(LOCAL_SCHEMA)
            self._db.commit()
            self._upgrade()
        except sqlite3.Error as exc:
            raise StorageError(f"The local data file could not be opened ({exc}).") from exc
        last = self._meta("last_store")
        known = {s["id"] for s in self.list_stores()}
        self.store_id = int(last) if last and int(last) in known else min(known)

    def _upgrade(self) -> None:
        """Make sure a first store exists and that products belong to a store. Older files get all their
        data moved into 'Main store'; nothing is lost."""
        db = self._db
        if not db.execute("select 1 from stores limit 1").fetchone():
            db.execute("insert into stores (name, created_at) values (?, ?)", (DEFAULT_STORE_NAME, _now()))
            db.commit()
        main = db.execute("select min(id) from stores").fetchone()[0]
        columns = [r["name"] for r in db.execute("pragma table_info(products)").fetchall()]
        if not columns:                                            # a brand new file
            db.executescript(PRODUCTS_TABLE.format(name="products"))
        elif "store_id" not in columns:                            # a file from before stores existed
            db.executescript("pragma foreign_keys = off;")
            db.executescript("begin;" + PRODUCTS_TABLE.format(name="products_new") + f"""
                insert into products_new (id, store_id, name, category, current_stock, unit_cost, lead_time_days, is_demo, created_at, updated_at)
                    select id, {int(main)}, name, category, current_stock, unit_cost, lead_time_days, is_demo, created_at, updated_at from products;
                drop table products;
                alter table products_new rename to products;
                commit;""")
            db.executescript("pragma foreign_keys = on;")
        db.execute("create index if not exists products_store on products(store_id)")
        old = db.execute("select * from user_settings where id = 1").fetchone()
        if old and not db.execute("select 1 from store_settings limit 1").fetchone():
            db.execute("insert into store_settings (store_id, sales_period_days, buffer_days, max_days_of_supply, "
                       "target_days_of_supply, updated_at) values (?,?,?,?,?,?)",
                       (main, old["sales_period_days"], old["buffer_days"], old["max_days_of_supply"],
                        old["target_days_of_supply"], old["updated_at"]))
        db.commit()

    # -- stores
    def _meta(self, key: str) -> Optional[str]:
        rows = self._rows("select value from app_meta where key = ?", [key])
        return rows[0]["value"] if rows else None

    def list_stores(self) -> list[dict]:
        return self._rows("select id, name, created_at from stores order by id")

    def use_store(self, store_id: int) -> None:
        self.store_id = int(store_id)
        self._run("insert into app_meta (key, value) values ('last_store', ?) on conflict (key) do update set value = excluded.value",
                  [str(self.store_id)])

    def create_store(self, name: str) -> dict:
        name = self._clean_store_name(name)
        if any(s["name"].lower() == name.lower() for s in self.list_stores()):
            raise StorageError(f"There is already a store called '{name}'.")
        cursor = self._run("insert into stores (name, created_at) values (?, ?)", [name, _now()])
        return {"id": cursor.lastrowid, "name": name}

    def rename_store(self, store_id: int, name: str) -> None:
        name = self._clean_store_name(name)
        if any(s["name"].lower() == name.lower() and s["id"] != store_id for s in self.list_stores()):
            raise StorageError(f"There is already a store called '{name}'.")
        self._run("update stores set name = ? where id = ?", [name, store_id])

    def delete_store(self, store_id: int) -> None:
        """Removes the store with its products, sales, stock records, alerts and settings."""
        if len(self.list_stores()) <= 1:
            raise StorageError("The last store cannot be deleted.")
        self._run("delete from stores where id = ?", [store_id])
        if self.store_id == store_id:
            self.use_store(self.list_stores()[0]["id"])

    # -- helpers
    def _run(self, sql: str, params: Iterable = ()):
        try:
            cursor = self._db.execute(sql, tuple(params))
            self._db.commit()
            return cursor
        except sqlite3.IntegrityError as exc:
            self._db.rollback()
            raise StorageError(f"The record was rejected by the database ({exc}).") from exc
        except sqlite3.Error as exc:
            self._db.rollback()
            raise StorageError(f"The database could not complete the request ({exc}).") from exc

    def _many(self, sql: str, rows: list):
        try:
            self._db.executemany(sql, rows)
            self._db.commit()
        except sqlite3.IntegrityError as exc:
            self._db.rollback()
            raise StorageError(f"Some records were rejected by the database ({exc}). Nothing was saved.") from exc
        except sqlite3.Error as exc:
            self._db.rollback()
            raise StorageError(f"The database could not complete the request ({exc}).") from exc

    def _rows(self, sql: str, params: Iterable = ()) -> list[dict]:
        try:
            return [dict(r) for r in self._db.execute(sql, tuple(params)).fetchall()]
        except sqlite3.Error as exc:
            raise StorageError(f"The database could not be read ({exc}).") from exc

    # -- products
    def list_products(self) -> list[dict]:
        return [self._product(r) for r in self._rows("select * from products where store_id = ? order by name collate nocase", [self.store_id])]

    def insert_products(self, products: list[dict], is_demo: bool = False) -> list[dict]:
        now, ids = _now(), []
        try:
            for p in products:
                cursor = self._db.execute(
                    "insert into products (store_id, name, category, current_stock, unit_cost, lead_time_days, is_demo, created_at, updated_at) "
                    "values (?,?,?,?,?,?,?,?,?)",
                    (self.store_id, p["name"], p["category"], p["current_stock"], p["unit_cost"], p["lead_time_days"], int(is_demo),
                     p.get("created_at") or now, now))
                ids.append(cursor.lastrowid)
            self._db.commit()
        except sqlite3.IntegrityError as exc:
            self._db.rollback()
            raise StorageError(f"A product was rejected by the database ({exc}). Nothing was saved.") from exc
        except sqlite3.Error as exc:
            self._db.rollback()
            raise StorageError(f"The products could not be saved ({exc}).") from exc
        if not ids:
            return []
        marks = ",".join("?" * len(ids))
        found = {r["id"]: self._product(r) for r in self._rows(f"select * from products where id in ({marks})", ids)}
        return [found[i] for i in ids]

    def update_product(self, product_id, fields: dict) -> None:
        allowed = {k: v for k, v in fields.items() if k in ("name", "category", "current_stock", "unit_cost", "lead_time_days")}
        if not allowed:
            return
        sets = ", ".join(f"{k} = ?" for k in allowed) + ", updated_at = ?"
        self._run(f"update products set {sets} where id = ?", [*allowed.values(), _now(), product_id])

    def delete_product(self, product_id) -> None:
        self._run("delete from products where id = ?", [product_id])

    def delete_demo_products(self) -> int:
        return self._run("delete from products where is_demo = 1 and store_id = ?", [self.store_id]).rowcount

    # -- sales
    def list_sales(self, product_id=None) -> list[dict]:
        if product_id is None:
            rows = self._rows("select s.* from sales_records s join products p on p.id = s.product_id "
                              "where p.store_id = ? order by s.sale_date, s.id", [self.store_id])
        else:
            rows = self._rows("select * from sales_records where product_id = ? order by sale_date, id", [product_id])
        return [self._sale(r) for r in rows]

    def insert_sales(self, sales: list[dict]) -> int:
        self._many("insert into sales_records (product_id, sale_date, quantity_sold) values (?,?,?)",
                   [(s["product_id"], _iso(s["sale_date"]), s["quantity_sold"]) for s in sales])
        return len(sales)

    def delete_sale(self, sale_id) -> None:
        self._run("delete from sales_records where id = ?", [sale_id])

    # -- stock records
    def list_inventory_records(self, product_id=None) -> list[dict]:
        if product_id is None:
            rows = self._rows("select r.* from inventory_records r join products p on p.id = r.product_id "
                              "where p.store_id = ? order by r.record_date, r.id", [self.store_id])
        else:
            rows = self._rows("select * from inventory_records where product_id = ? order by record_date, id", [product_id])
        return [self._record(r) for r in rows]

    def upsert_inventory_records(self, records: list[dict]) -> int:
        self._many(
            "insert into inventory_records (product_id, record_date, stock_quantity) values (?,?,?) "
            "on conflict (product_id, record_date) do update set stock_quantity = excluded.stock_quantity",
            [(r["product_id"], _iso(r["record_date"]), r["stock_quantity"]) for r in records])
        return len(records)

    # -- settings
    def get_settings(self) -> Optional[dict]:
        rows = self._rows("select * from store_settings where store_id = ?", [self.store_id])
        return {k: int(rows[0][k]) for k in SETTINGS_FIELDS} if rows else None

    def save_settings(self, values: dict) -> None:
        self._run(
            "insert into store_settings (store_id, sales_period_days, buffer_days, max_days_of_supply, target_days_of_supply, updated_at) "
            "values (?,?,?,?,?,?) on conflict (store_id) do update set sales_period_days = excluded.sales_period_days, "
            "buffer_days = excluded.buffer_days, max_days_of_supply = excluded.max_days_of_supply, "
            "target_days_of_supply = excluded.target_days_of_supply, updated_at = excluded.updated_at",
            [self.store_id, *(int(values[k]) for k in SETTINGS_FIELDS), _now()])

    # -- alerts
    def list_alerts(self) -> list[dict]:
        return [self._alert(r) for r in self._rows("select a.* from alerts a join products p on p.id = a.product_id "
                                                    "where p.store_id = ? order by a.id", [self.store_id])]

    def upsert_alert(self, alert: dict) -> None:
        """One alert per product. Keeps the reviewed mark unless told to reset it."""
        self._run(
            "insert into alerts (product_id, classification, explanation, suggested_action, reviewed, reviewed_at, created_at) "
            "values (?,?,?,?,?,?,?) on conflict (product_id) do update set classification = excluded.classification, "
            "explanation = excluded.explanation, suggested_action = excluded.suggested_action, "
            "reviewed = excluded.reviewed, reviewed_at = excluded.reviewed_at, created_at = excluded.created_at",
            [alert["product_id"], alert["classification"], alert["explanation"], alert["suggested_action"],
             int(bool(alert.get("reviewed"))), alert.get("reviewed_at"), alert.get("created_at") or _now()])

    def delete_alert(self, product_id) -> None:
        self._run("delete from alerts where product_id = ?", [product_id])

    def set_alert_reviewed(self, product_id, reviewed: bool) -> None:
        self._run("update alerts set reviewed = ?, reviewed_at = ? where product_id = ?",
                  [int(reviewed), _now() if reviewed else None, product_id])


# ====================================================================== Supabase
class SupabaseRepository(Repository):
    backend = "Supabase"

    def __init__(self, client):
        self._client = client
        self.store_id = None

    # -- stores
    def list_stores(self) -> list[dict]:
        rows = self._all("stores", "id")
        if not rows:                                   # first run: create the first store
            rows = self._do(lambda: self._client.table("stores").insert(
                {"name": DEFAULT_STORE_NAME, "created_at": _now()}).execute(), "create the first store")
        return [{"id": r["id"], "name": r["name"], "created_at": r.get("created_at")} for r in rows]

    def _sid(self) -> int:
        if self.store_id is None:
            self.store_id = self.list_stores()[0]["id"]
        return self.store_id

    def use_store(self, store_id: int) -> None:
        self.store_id = int(store_id)

    def create_store(self, name: str) -> dict:
        name = self._clean_store_name(name)
        if any(s["name"].lower() == name.lower() for s in self.list_stores()):
            raise StorageError(f"There is already a store called '{name}'.")
        row = self._do(lambda: self._client.table("stores").insert({"name": name, "created_at": _now()}).execute(),
                       "create the store")[0]
        return {"id": row["id"], "name": row["name"]}

    def rename_store(self, store_id: int, name: str) -> None:
        name = self._clean_store_name(name)
        if any(s["name"].lower() == name.lower() and s["id"] != store_id for s in self.list_stores()):
            raise StorageError(f"There is already a store called '{name}'.")
        self._do(lambda: self._client.table("stores").update({"name": name}).eq("id", store_id).execute(), "rename the store")

    def delete_store(self, store_id: int) -> None:
        """Removes the store with its products, sales, stock records, alerts and settings."""
        if len(self.list_stores()) <= 1:
            raise StorageError("The last store cannot be deleted.")
        self._do(lambda: self._client.table("stores").delete().eq("id", store_id).execute(), "delete the store")
        if self.store_id == store_id:
            self.store_id = None
            self._sid()

    def _store_product_ids(self) -> set:
        return {p["id"] for p in self.list_products()}

    # -- helpers
    def _do(self, action, what: str):
        try:
            return action().data or []
        except Exception as exc:   # network, permissions, constraint violations
            message = getattr(exc, "message", None) or str(exc)
            raise StorageError(f"Supabase could not {what} ({message}).") from exc

    def _all(self, table: str, order: str, filters: Optional[dict] = None) -> list[dict]:
        rows, start = [], 0
        while True:
            def action(start=start):
                query = self._client.table(table).select("*")
                for column, value in (filters or {}).items():
                    query = query.eq(column, value)
                return query.order(order).order("id").range(start, start + PAGE - 1).execute()
            page = self._do(action, f"read {table.replace('_', ' ')}")
            rows += page
            if len(page) < PAGE:
                return rows
            start += PAGE

    # -- products
    def list_products(self) -> list[dict]:
        rows = [self._product(r) for r in self._all("products", "name", {"store_id": self._sid()})]
        return sorted(rows, key=lambda r: r["name"].lower())

    def insert_products(self, products: list[dict], is_demo: bool = False) -> list[dict]:
        now, saved = _now(), []
        sid = self._sid()
        payload = [{"store_id": sid, "name": p["name"], "category": p["category"], "current_stock": p["current_stock"],
                    "unit_cost": p["unit_cost"], "lead_time_days": p["lead_time_days"], "is_demo": is_demo,
                    "created_at": p.get("created_at") or now, "updated_at": now} for p in products]
        for part in _chunks(payload):
            saved += self._do(lambda part=part: self._client.table("products").insert(part).execute(), "save the products")
        by_name = {r["name"].lower(): self._product(r) for r in saved}
        return [by_name[p["name"].lower()] for p in products if p["name"].lower() in by_name]

    def update_product(self, product_id, fields: dict) -> None:
        allowed = {k: v for k, v in fields.items() if k in ("name", "category", "current_stock", "unit_cost", "lead_time_days")}
        if not allowed:
            return
        allowed["updated_at"] = _now()
        self._do(lambda: self._client.table("products").update(allowed).eq("id", product_id).execute(), "update the product")

    def delete_product(self, product_id) -> None:
        self._do(lambda: self._client.table("products").delete().eq("id", product_id).execute(), "delete the product")

    def delete_demo_products(self) -> int:
        return len(self._do(lambda: self._client.table("products").delete().eq("is_demo", True).eq("store_id", self._sid()).execute(),
                            "clear the demonstration data"))

    # -- sales
    def list_sales(self, product_id=None) -> list[dict]:
        if product_id is None:
            ids = self._store_product_ids()
            return [self._sale(r) for r in self._all("sales_records", "sale_date") if r["product_id"] in ids]
        return [self._sale(r) for r in self._all("sales_records", "sale_date", {"product_id": product_id})]

    def insert_sales(self, sales: list[dict]) -> int:
        payload = [{"product_id": s["product_id"], "sale_date": _iso(s["sale_date"]), "quantity_sold": s["quantity_sold"]} for s in sales]
        for part in _chunks(payload):
            self._do(lambda part=part: self._client.table("sales_records").insert(part).execute(), "save the sales records")
        return len(payload)

    def delete_sale(self, sale_id) -> None:
        self._do(lambda: self._client.table("sales_records").delete().eq("id", sale_id).execute(), "delete the sale")

    # -- stock records
    def list_inventory_records(self, product_id=None) -> list[dict]:
        if product_id is None:
            ids = self._store_product_ids()
            return [self._record(r) for r in self._all("inventory_records", "record_date") if r["product_id"] in ids]
        return [self._record(r) for r in self._all("inventory_records", "record_date", {"product_id": product_id})]

    def upsert_inventory_records(self, records: list[dict]) -> int:
        payload = [{"product_id": r["product_id"], "record_date": _iso(r["record_date"]), "stock_quantity": r["stock_quantity"]}
                   for r in records]
        for part in _chunks(payload):
            self._do(lambda part=part: self._client.table("inventory_records")
                     .upsert(part, on_conflict="product_id,record_date").execute(), "save the stock records")
        return len(payload)

    # -- settings
    def get_settings(self) -> Optional[dict]:
        rows = self._do(lambda: self._client.table("store_settings").select("*").eq("store_id", self._sid()).execute(), "read the settings")
        return {k: int(rows[0][k]) for k in SETTINGS_FIELDS} if rows else None

    def save_settings(self, values: dict) -> None:
        payload = {"store_id": self._sid(), **{k: int(values[k]) for k in SETTINGS_FIELDS}, "updated_at": _now()}
        self._do(lambda: self._client.table("store_settings").upsert(payload, on_conflict="store_id").execute(), "save the settings")

    # -- alerts
    def list_alerts(self) -> list[dict]:
        ids = self._store_product_ids()
        return [self._alert(r) for r in self._all("alerts", "id") if r["product_id"] in ids]

    def upsert_alert(self, alert: dict) -> None:
        payload = {"product_id": alert["product_id"], "classification": alert["classification"],
                   "explanation": alert["explanation"], "suggested_action": alert["suggested_action"],
                   "reviewed": bool(alert.get("reviewed")), "reviewed_at": alert.get("reviewed_at"),
                   "created_at": alert.get("created_at") or _now()}
        self._do(lambda: self._client.table("alerts").upsert(payload, on_conflict="product_id").execute(), "save the alert")

    def delete_alert(self, product_id) -> None:
        self._do(lambda: self._client.table("alerts").delete().eq("product_id", product_id).execute(), "remove the alert")

    def set_alert_reviewed(self, product_id, reviewed: bool) -> None:
        payload = {"reviewed": bool(reviewed), "reviewed_at": _now() if reviewed else None}
        self._do(lambda: self._client.table("alerts").update(payload).eq("product_id", product_id).execute(), "update the alert")


# ====================================================================== choose one
def get_repository(env: Optional[dict] = None) -> Repository:
    """Supabase when SUPABASE_URL and SUPABASE_KEY are set, otherwise the local file."""
    env = os.environ if env is None else env
    url, key = (env.get("SUPABASE_URL") or "").strip(), (env.get("SUPABASE_KEY") or "").strip()
    if url and key:
        try:
            from supabase import create_client
            return SupabaseRepository(create_client(url, key))
        except Exception as exc:
            raise StorageError(f"Could not connect to Supabase. Check SUPABASE_URL and SUPABASE_KEY ({exc}).") from exc
    return LocalRepository((env.get("BALANSE_LOCAL_DB") or "balanse_local.db").strip())
