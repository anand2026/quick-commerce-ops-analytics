"""Build reports/ops_dashboard.xlsx (Excel/Sheets KPI dashboard) and reports/summary_deck.pdf from outputs/."""
import os, pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from openpyxl import Workbook
from openpyxl.chart import LineChart, BarChart, Reference
from openpyxl.formatting.rule import ColorScaleRule, CellIsRule
from openpyxl.styles import Font, PatternFill
from openpyxl.utils.dataframe import dataframe_to_rows

os.makedirs("reports", exist_ok=True)
o = lambda n: pd.read_csv(f"outputs/{n}.csv")
kpi, wk, st, inv, dfx, promo = (o("overall_kpis"), o("weekly_kpis_anomalies"), o("store_peak_ranking"),
                                o("inventory_turns"), o("defects_by_delivery_time"), o("promo_pilot_did"))
wk = wk.iloc[1:-1].reset_index(drop=True)  # drop partial first/last weeks

# ---------- Excel dashboard ----------
wb = Workbook(); bold = Font(bold=True); hdr = PatternFill("solid", fgColor="F8CB46")
def sheet(name, df):
    ws = wb.create_sheet(name)
    for r in dataframe_to_rows(df, index=False, header=True): ws.append(r)
    for c in ws[1]: c.font, c.fill = bold, hdr
    for col in ws.columns: ws.column_dimensions[col[0].column_letter].width = 16
    return ws

d = wb.active; d.title = "Dashboard"
d["A1"] = "Quick-Commerce Ops Dashboard (simulated data, May-Oct 2025)"; d["A1"].font = Font(bold=True, size=14)
labels = ["Orders", "Avg delivery (min)", "P90 delivery (min)", "On-time % (<=15 min)", "Defect %", "Cancel %"]
for i, (lab, v) in enumerate(zip(labels, kpi.iloc[0].tolist())):
    d.cell(3, 1 + i, lab).font = bold; d.cell(3, 1 + i).fill = hdr; d.cell(4, 1 + i, v).font = Font(size=16, bold=True)
    d.column_dimensions[d.cell(3, 1 + i).column_letter].width = 20
d["A6"] = "Anomaly weeks"; d["B6"] = "=COUNTIF(Weekly!E:E,TRUE)"
d["A7"] = "Worst store (peak late %)"; d["B7"] = "=INDEX(Stores!B:B,MATCH(MAX(Stores!D:D),Stores!D:D,0))"
d["A8"] = "Its peak late %"; d["B8"] = "=MAX(Stores!D:D)"
d["A9"] = "Avg peak late %, other stores"; d["B9"] = "=AVERAGEIF(Stores!D:D,\"<20\")"
for c in ("A6", "A7", "A8", "A9"): d[c].font = bold

w = sheet("Weekly", wk)
w.conditional_formatting.add(f"C2:C{w.max_row}", CellIsRule(operator="greaterThan", formula=["10"], fill=PatternFill("solid", fgColor="F4B6B6")))
s = sheet("Stores", st)
s.conditional_formatting.add(f"D2:D{s.max_row}", ColorScaleRule(start_type="min", start_color="FFFFFF", end_type="max", end_color="E06666"))
iv = sheet("Inventory", inv); df_ = sheet("Defects", dfx); sheet("Promo_Pilot", promo)

lc = LineChart(); lc.title = "Weekly late-delivery %"; lc.height, lc.width = 7, 16
lc.add_data(Reference(w, min_col=3, max_col=4, min_row=1, max_row=w.max_row), titles_from_data=True)
lc.set_categories(Reference(w, min_col=1, min_row=2, max_row=w.max_row)); d.add_chart(lc, "A11")
bc = BarChart(); bc.title = "Annual inventory turns"; bc.height, bc.width = 7, 12
bc.add_data(Reference(iv, min_col=2, min_row=1, max_row=iv.max_row), titles_from_data=True)
bc.set_categories(Reference(iv, min_col=1, min_row=2, max_row=iv.max_row)); d.add_chart(bc, "J11")
bd = BarChart(); bd.title = "Defect % by delivery time"; bd.height, bd.width = 7, 12
bd.add_data(Reference(df_, min_col=3, min_row=1, max_row=df_.max_row), titles_from_data=True)
bd.set_categories(Reference(df_, min_col=1, min_row=2, max_row=df_.max_row)); d.add_chart(bd, "J26")
wb.save("reports/ops_dashboard.xlsx")

# ---------- Summary deck ----------
Y = "#F8CB46"
def slide(pdf, title, bullets=None, draw=None):
    fig = plt.figure(figsize=(11, 6.2)); fig.patch.set_facecolor("white")
    fig.text(0.05, 0.9, title, fontsize=22, weight="bold")
    fig.add_artist(plt.Line2D([0.05, 0.95], [0.87, 0.87], color=Y, lw=4))
    if bullets:
        for i, b in enumerate(bullets): fig.text(0.06, 0.76 - i * 0.09, "•  " + b, fontsize=14, wrap=True)
    if draw: draw(fig.add_axes([0.08, 0.1, 0.85, 0.65] if not bullets else [0.62, 0.14, 0.34, 0.6]))
    pdf.savefig(fig); plt.close(fig)

k = kpi.iloc[0]; p = promo.iloc[0]; top3 = st.head(3)
with PdfPages("reports/summary_deck.pdf") as pdf:
    slide(pdf, "Quick-Commerce Ops Review: May-Oct 2025", [
        f"{int(k.orders):,} orders, 25 dark stores (simulated data)",
        f"Avg delivery {k.avg_mins} min, P90 {k.p90_mins} min, on-time {k.on_time_pct}%",
        f"Defect rate {k.defect_pct}%, cancellations {k.cancel_pct}%",
        "Problem: evening-peak delays and one bad week are pulling on-time % down"])
    def wkplot(ax):
        ax.plot(pd.to_datetime(wk.week), wk.late_pct, color="#333", marker="o", ms=3, label="Late %")
        ax.plot(pd.to_datetime(wk.week), wk.rolling_8w_pct, color=Y, lw=2, label="Rolling 8-wk avg")
        a = wk[wk.is_anomaly == True]; ax.scatter(pd.to_datetime(a.week), a.late_pct, color="red", s=80, zorder=3, label="Anomaly")
        ax.legend(); ax.set_ylabel("% orders > 15 min")
    slide(pdf, "Finding 1: monsoon week late rate jumped to 19% (vs ~4%)", draw=wkplot)
    def stplot(ax):
        c = ["#E06666" if i < 3 else "#BBBBBB" for i in range(len(st))]
        ax.bar(st.store_id, st.peak_late_pct, color=c); ax.set_ylabel("Peak-hour late %"); ax.tick_params(axis="x", rotation=90)
    slide(pdf, "Finding 2: 3 stores cause 39% of late orders", [
        f"{', '.join(top3.store_id)}: ~{top3.peak_late_pct.mean():.0f}% late, 6-10 PM",
        "Other stores: ~6%; off-peak, all are fine", "Root cause: peak-hour rider shortage",
        "Slow orders: more defects (2.5% to 9.7%)"], stplot)
    slide(pdf, "Finding 3: Dairy promo pilot worked", [
        f"20% off Dairy in 6 stores for 2 weeks vs 19 control stores",
        f"Pilot: Rs {p.pilot_before:,.0f} to Rs {p.pilot_during:,.0f} dairy revenue per store-day",
        f"Control stayed flat (Rs {p.control_before:,.0f} to Rs {p.control_during:,.0f})",
        f"Difference-in-differences lift: +{p.did_lift_pct_pts} pct-pts"])
    slide(pdf, "Recommendations", [
        "Add evening-peak riders at DS07, DS13, DS19 (target: <10% late)",
        "Weather-triggered staffing buffer for rain days",
        "Scale the Dairy promo; re-check margin after discount",
        "Track weekly late % with automatic anomaly alerts (dashboard)"])
print("built reports/ops_dashboard.xlsx, reports/summary_deck.pdf")
