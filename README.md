# Quick-Commerce Operations Analytics

SQL analysis of a **simulated** 10-minute grocery delivery business: 220K orders, 25 dark stores, 320 SKUs, 6 months (May–Oct 2025).
The data is synthetic (`generate_data.py`), with realistic operational patterns built in. The goal is to show how an analyst detects and explains them.

**Stack:** Python (pandas, NumPy) · SQL (DuckDB: CTEs, joins, window functions) · Tableau / Google Sheets on `outputs/`

## Run
```bash
python3 -m venv .venv && .venv/bin/pip install duckdb pandas numpy
.venv/bin/python generate_data.py && .venv/bin/python run_analysis.py
```

## Key findings
| Area | Finding |
|---|---|
| Data quality | Removed 150 duplicate orders and 40 invalid (negative) delivery times |
| Overall KPIs | Avg delivery 9.7 min, P90 13.6 min, on-time (≤15 min) 95.3%, defect 2.9%, cancellation 1.7% |
| Anomaly | Week of 14 Jul: late rate 19.1% vs 4.2% rolling 8-week baseline (monsoon week) |
| Root cause | 3 stores (DS07, DS13, DS19) are ~42% late at evening peak vs ~6% elsewhere. They account for 4.4% of orders but 38.7% of late deliveries, which points to a peak-hour rider shortage |
| Defects | Defect rate rises from 2.5% (≤10 min) to 9.7% (20+ min) |
| Inventory | Turns range from 73/yr (Fruits & Veg) to 11/yr (Frozen); Fruits & Veg has the most stockouts |
| Promo pilot | 20% off Dairy in 6 stores for 2 weeks: +40 pct-pt lift in dairy revenue per store-day vs control (difference-in-differences) |

**Recommendation:** add evening-peak riders at the 3 flagged stores, and add a weather-triggered staffing buffer.

## Files
- `sql/analysis.sql`: all queries (data quality, KPIs, anomalies, store ranking, defects, inventory turns, promo DiD)
- `outputs/*.csv`: query results, ready for Tableau / Google Sheets
- `reports/ops_dashboard.xlsx`: Excel KPI dashboard (KPI tiles, lookup formulas, conditional formatting, charts); opens in Google Sheets too
- `reports/summary_deck.pdf`: 5-slide stakeholder summary (findings and recommendations)
- `build_reports.py`: rebuilds both reports from `outputs/`
