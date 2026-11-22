-- BALANSE database schema for Supabase (PostgreSQL).
-- Run this once: Supabase dashboard > SQL Editor > New query > paste > Run.
-- It is safe to run again; it does not delete data.

-- 0. Stores -----------------------------------------------------------------
-- Each store is a separate inventory: its own products, sales, stock records, alerts and settings.
create table if not exists stores (
    id          bigint generated always as identity primary key,
    name        text        not null,
    created_at  timestamptz not null default now()
);
create unique index if not exists stores_name_unique on stores (lower(name));
-- every project needs at least one store; existing data is moved into it below
insert into stores (name) select 'Main store' where not exists (select 1 from stores);

-- 1. Products ---------------------------------------------------------------
create table if not exists products (
    id              bigint generated always as identity primary key,
    store_id        bigint      references stores (id) on delete cascade,
    name            text        not null,
    category        text        not null,
    current_stock   numeric     not null check (current_stock >= 0),
    unit_cost       numeric     not null check (unit_cost >= 0),
    lead_time_days  integer     not null check (lead_time_days >= 0),
    is_demo         boolean     not null default false,   -- true for DEMONSTRATION DATA only
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);
-- Upgrading a project that was created before stores existed: add the column, move every product into the
-- first store, then require it. Safe to run again.
alter table products add column if not exists store_id bigint references stores (id) on delete cascade;
update products set store_id = (select min(id) from stores) where store_id is null;
alter table products alter column store_id set not null;
-- product names are unique inside a store, ignoring upper/lower case (the same name may exist in two stores)
drop index if exists products_name_unique;
create unique index if not exists products_store_name_unique on products (store_id, lower(name));

-- 2. Sales records ----------------------------------------------------------
create table if not exists sales_records (
    id             bigint generated always as identity primary key,
    product_id     bigint  not null references products (id) on delete cascade,
    sale_date      date    not null,
    quantity_sold  numeric not null check (quantity_sold > 0)
);
create index if not exists sales_product_date on sales_records (product_id, sale_date);

-- 3. Inventory (stock) records ----------------------------------------------
-- End-of-day stock for a product on a date. One record per product per day.
create table if not exists inventory_records (
    id              bigint generated always as identity primary key,
    product_id      bigint  not null references products (id) on delete cascade,
    record_date     date    not null,
    stock_quantity  numeric not null check (stock_quantity >= 0),
    unique (product_id, record_date)
);

-- 4. Settings, one row per store ---------------------------------------------
create table if not exists store_settings (
    store_id               bigint primary key references stores (id) on delete cascade,
    sales_period_days      integer not null check (sales_period_days >= 1),
    buffer_days            integer not null check (buffer_days >= 0),
    max_days_of_supply     integer not null check (max_days_of_supply >= 1),
    target_days_of_supply  integer not null check (target_days_of_supply >= 1),
    updated_at             timestamptz not null default now(),
    check (target_days_of_supply <= max_days_of_supply)
);
create table if not exists user_settings (
    id                     integer primary key check (id = 1),
    sales_period_days      integer not null check (sales_period_days >= 1),
    buffer_days            integer not null check (buffer_days >= 0),
    max_days_of_supply     integer not null check (max_days_of_supply >= 1),
    target_days_of_supply  integer not null check (target_days_of_supply >= 1),
    updated_at             timestamptz not null default now(),
    check (target_days_of_supply <= max_days_of_supply)
);
-- Older projects: copy the single settings row into the first store (only if it has none yet)
insert into store_settings (store_id, sales_period_days, buffer_days, max_days_of_supply, target_days_of_supply)
    select (select min(id) from stores), sales_period_days, buffer_days, max_days_of_supply, target_days_of_supply
    from user_settings where id = 1
    and not exists (select 1 from store_settings);
-- (the old one-row table is kept only so this copy can run; nothing reads it any more)


-- 5. Alerts (one active alert per product) ----------------------------------
create table if not exists alerts (
    id                bigint generated always as identity primary key,
    product_id        bigint not null unique references products (id) on delete cascade,
    classification    text   not null check (classification in
                        ('Stockout risk', 'Understock risk', 'Overstock risk', 'No recent sales')),
    explanation       text   not null,
    suggested_action  text   not null,
    reviewed          boolean not null default false,
    reviewed_at       timestamptz,
    created_at        timestamptz not null default now()
);

-- 6. Price records ----------------------------------------------------------
-- RESERVED for the future Price Market / Price Fluctuation module.
-- Proposed structure only. BALANSE does not read or write this table yet.
create table if not exists price_records (
    id                  bigint generated always as identity primary key,
    product_id          bigint references products (id) on delete cascade,
    market_or_supplier  text,
    recorded_price      numeric,
    price_unit          text,
    date_recorded       date,
    data_source         text
);

-- Security ------------------------------------------------------------------
-- Row Level Security is switched ON with no policies. That blocks the public
-- "anon" key completely. BALANSE runs on the server (Streamlit) and connects
-- with the service_role key, which is allowed through. Keep that key in .env
-- or in Streamlit Secrets. Never put it in code or share it.
alter table stores            enable row level security;
alter table store_settings    enable row level security;
alter table products          enable row level security;
alter table sales_records     enable row level security;
alter table inventory_records enable row level security;
alter table user_settings     enable row level security;
alter table alerts            enable row level security;
alter table price_records     enable row level security;
