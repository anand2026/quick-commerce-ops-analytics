"""Generate a SIMULATED quick-commerce (10-minute delivery) dataset.
All data is synthetic. Output: data/*.csv
"""
import numpy as np, pandas as pd, os

rng = np.random.default_rng(42)
os.makedirs("data", exist_ok=True)

# Dark stores
zones = ["Gurgaon", "South Delhi", "Noida", "West Delhi", "Faridabad"]
stores = pd.DataFrame({"store_id": [f"DS{i:02d}" for i in range(1, 26)],
                       "zone": np.repeat(zones, 5)})
short_staffed = {"DS07", "DS13", "DS19"}          # rider shortage at evening peak

# Products
cats = ["Dairy & Breakfast", "Fruits & Veg", "Snacks", "Beverages", "Staples",
        "Personal Care", "Household", "Frozen"]
n_prod = 320
products = pd.DataFrame({"product_id": [f"P{i:04d}" for i in range(n_prod)],
                         "category": rng.choice(cats, n_prod),
                         "price": rng.integers(20, 600, n_prod)})
products["unit_cost"] = (products.price * rng.uniform(0.7, 0.85, n_prod)).round(1)

# Orders
dates = pd.date_range("2025-05-01", "2025-10-31", freq="D")
n = 220_000
day = rng.integers(0, len(dates), n)
hour_p = np.array([1,0,0,0,0,0,1,3,5,6,5,5,6,5,4,4,5,7,10,11,9,6,3,2], float)
hour = rng.choice(24, n, p=hour_p / hour_p.sum())
ts = dates[day] + pd.to_timedelta(hour, "h") + pd.to_timedelta(rng.integers(0, 60, n), "m")
store = rng.choice(stores.store_id, n)
dist = rng.gamma(2.2, 0.75, n).clip(0.3, 5)
peak = (hour >= 18) & (hour <= 21)
rain = np.isin(dates[day].strftime("%Y-%m-%d"),
               pd.date_range("2025-07-14", "2025-07-20").strftime("%Y-%m-%d"))  # monsoon week
ss = np.isin(store, list(short_staffed))

# Promo pilot: 20% off Dairy & Breakfast in 6 stores, 2025-09-01..09-14
pilot_stores = ["DS02", "DS05", "DS09", "DS14", "DS18", "DS23"]
in_pilot = np.isin(store, pilot_stores) & (dates[day] >= "2025-09-01") & (dates[day] <= "2025-09-14")

mins = (6 + 1.6 * dist + 2.2 * peak + 3.8 * (peak & ss) + 3 * rain
        + rng.normal(0, 1.8, n)).clip(4, 60).round(1)
cancel = rng.random(n) < (0.015 + 0.03 * rain + 0.02 * (peak & ss))
defect_p = 0.025 + 0.004 * (mins - 10).clip(0)
r = rng.random(n)
defect = np.where(r < defect_p * 0.5, "missing_item",
         np.where(r < defect_p * 0.8, "damaged",
         np.where(r < defect_p, "wrong_item", None)))
cust = rng.integers(1, 38_000, n)

orders = pd.DataFrame({"order_id": np.arange(1, n + 1), "customer_id": cust,
                       "store_id": store, "order_ts": ts, "distance_km": dist.round(2),
                       "status": np.where(cancel, "cancelled", "delivered"),
                       "delivery_minutes": np.where(cancel, np.nan, mins),
                       "defect_type": np.where(cancel, None, defect)})

# Order items (pilot boosts Dairy share + basket size)
k = rng.integers(1, 7, n) + in_pilot * rng.integers(0, 2, n)
oid = np.repeat(orders.order_id.values, k)
pil = np.repeat(in_pilot, k)
dairy = products.index[products.category == "Dairy & Breakfast"].values
pid = np.where(pil & (rng.random(len(oid)) < 0.07), rng.choice(dairy, len(oid)),
               rng.integers(0, n_prod, len(oid)))
items = pd.DataFrame({"order_id": oid, "product_id": products.product_id.values[pid],
                      "qty": rng.integers(1, 4, len(oid))})
items["unit_price"] = products.price.values[pid] * np.where(
    pil & (products.category.values[pid] == "Dairy & Breakfast"), 0.8, 1.0)

# Daily inventory snapshot per store x category
inv = pd.MultiIndex.from_product([dates, stores.store_id, cats],
                                 names=["date", "store_id", "category"]).to_frame(index=False)
base = {"Fruits & Veg": 45000, "Dairy & Breakfast": 55000, "Frozen": 200000}
inv["inventory_value"] = (inv.category.map(base).fillna(170000)
                          * rng.uniform(0.8, 1.2, len(inv))).round(0)
inv["stockout_skus"] = rng.poisson(1.2, len(inv)) + 4 * (
    inv.store_id.isin(short_staffed) & (inv.category == "Fruits & Veg"))

# A few deliberate data-quality issues to clean
dup = orders.sample(150, random_state=1)
orders = pd.concat([orders, dup])
orders.loc[orders.sample(40, random_state=2).index, "delivery_minutes"] = -1

for name, df in [("stores", stores), ("products", products), ("orders", orders),
                 ("order_items", items), ("inventory_daily", inv)]:
    df.to_csv(f"data/{name}.csv", index=False)
    print(name, len(df))
