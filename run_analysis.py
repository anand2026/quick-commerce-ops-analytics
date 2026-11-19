"""Load CSVs into DuckDB, run sql/analysis.sql, save each result to outputs/ (for Tableau / Google Sheets)."""
import duckdb, os, re

os.makedirs("outputs", exist_ok=True)
con = duckdb.connect("quickcommerce.duckdb")
for t in ["stores", "products", "order_items", "inventory_daily"]:
    con.execute(f"CREATE OR REPLACE TABLE {t} AS SELECT * FROM read_csv_auto('data/{t}.csv')")
con.execute("CREATE OR REPLACE TABLE orders_raw AS SELECT * FROM read_csv_auto('data/orders.csv')")

sql = open("sql/analysis.sql").read()
for name, q in re.findall(r"-- name: (\w+)\n(.*?)(?=\n-- name:|\Z)", sql, re.S):
    if q.strip().upper().startswith("CREATE"):
        con.execute(q); continue
    df = con.execute(q).df()
    df.to_csv(f"outputs/{name}.csv", index=False)
    print(f"\n== {name} ==\n{df.to_string(index=False, max_rows=30)}")
