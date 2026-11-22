"""A tiny in-memory stand-in for the Supabase client.

It copies only the calls SupabaseRepository makes (select / eq / order / range,
insert, update, delete, upsert) and the constraints in sql/schema.sql that the
app relies on (unique product name, one alert per product, one stock record per
product and date, delete cascades). It lets the Supabase code path be tested
without a real project. It is NOT a substitute for testing against Supabase.
"""
from types import SimpleNamespace

UNIQUE = {"products": ["store_id", "name"], "stores": ["name"], "store_settings": ["store_id"], "alerts": ["product_id"], "inventory_records": ["product_id", "record_date"],
          "user_settings": ["id"]}
CHILDREN = ["sales_records", "inventory_records", "alerts"]


class FakeError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class Query:
    def __init__(self, db, table):
        self.db, self.table = db, table
        self.action, self.payload, self.filters, self.orders, self.window, self.conflict = "select", None, [], [], None, None

    def select(self, _columns="*"):
        self.action = "select"
        return self

    def insert(self, payload):
        self.action, self.payload = "insert", payload
        return self

    def update(self, payload):
        self.action, self.payload = "update", payload
        return self

    def delete(self):
        self.action = "delete"
        return self

    def upsert(self, payload, on_conflict=None):
        self.action, self.payload, self.conflict = "upsert", payload, on_conflict
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def order(self, column):
        self.orders.append(column)
        return self

    def range(self, start, end):
        self.window = (start, end)
        return self

    def _match(self, row):
        return all(row.get(c) == v for c, v in self.filters)

    def _key(self, row, columns):
        return tuple(str(row.get(c)).lower() if c == "name" else row.get(c) for c in columns)

    def execute(self):
        rows = self.db.tables.setdefault(self.table, [])
        if self.action == "select":
            found = [dict(r) for r in rows if self._match(r)]
            for column in reversed(self.orders):
                found.sort(key=lambda r: (r.get(column) is None, r.get(column)))
            if self.window:
                found = found[self.window[0]:self.window[1] + 1]
            return SimpleNamespace(data=found)
        if self.action in ("insert", "upsert"):
            payload = self.payload if isinstance(self.payload, list) else [self.payload]
            out = []
            for item in payload:
                item = dict(item)
                columns = self.conflict.split(",") if self.conflict else UNIQUE.get(self.table)
                clash = next((r for r in rows if columns and self._key(r, columns) == self._key(item, columns)), None)
                if clash is not None and self.action == "insert":
                    raise FakeError(f"duplicate key value violates unique constraint on {self.table}")
                if self.table == "products" and (item.get("current_stock", 0) < 0 or item.get("lead_time_days", 0) < 0):
                    raise FakeError("new row violates check constraint")
                if clash is not None:
                    clash.update(item)
                    out.append(dict(clash))
                else:
                    if "id" not in item:
                        self.db.next_id += 1
                        item["id"] = self.db.next_id
                    rows.append(item)
                    out.append(dict(item))
            return SimpleNamespace(data=out)
        if self.action == "update":
            changed = [r for r in rows if self._match(r)]
            for r in changed:
                r.update(self.payload)
            return SimpleNamespace(data=[dict(r) for r in changed])
        if self.action == "delete":
            gone = [r for r in rows if self._match(r)]
            self.db.tables[self.table] = [r for r in rows if not self._match(r)]
            if self.table == "stores":
                store_ids = {r["id"] for r in gone}
                dropped = [r for r in self.db.tables.get("products", []) if r.get("store_id") in store_ids]
                self.db.tables["products"] = [r for r in self.db.tables.get("products", []) if r.get("store_id") not in store_ids]
                self.db.tables["store_settings"] = [r for r in self.db.tables.get("store_settings", []) if r.get("store_id") not in store_ids]
                ids = {r["id"] for r in dropped}
                for child in CHILDREN:
                    self.db.tables[child] = [r for r in self.db.tables.get(child, []) if r["product_id"] not in ids]
            if self.table == "products":
                ids = {r["id"] for r in gone}
                for child in CHILDREN:
                    self.db.tables[child] = [r for r in self.db.tables.get(child, []) if r["product_id"] not in ids]
            return SimpleNamespace(data=[dict(r) for r in gone])
        raise FakeError("unsupported")


class FakeSupabase:
    def __init__(self):
        self.tables, self.next_id = {}, 0

    def table(self, name):
        return Query(self, name)


class BrokenSupabase:
    """Every call fails, like a dropped connection."""
    def table(self, name):
        raise FakeError("connection refused")
