"""Flatten results/summary.json into spreadsheet-friendly CSVs.

results/summary.csv  one row per strategy x market x timeframe, 1 and 2 contracts
results/by_year.csv  net $ per calendar year (1 contract), same rows
"""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data import ROOT  # noqa: E402

OUT = os.path.join(ROOT, "results")


def main():
    r = json.load(open(os.path.join(OUT, "summary.json")))
    runs = r["runs"]
    years = sorted({y for s in runs for y in s.get("by_year", {})})
    with open(os.path.join(OUT, "summary.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["strategy", "name", "market", "contract", "timeframe", "trades",
                    "net_1ct", "net_2ct", "gross_1ct", "costs_1ct", "profit_factor", "win_pct",
                    "avg_trade_1ct", "max_dd_1ct", "max_dd_2ct", "net_to_dd", "sharpe",
                    "profitable_years", "first_trade", "last_trade"])
        for s in runs:
            if not s["trades"]:
                w.writerow([s["strategy"], s["name"], s["symbol"], s["contract"], s["tf"], 0])
                continue
            w.writerow([s["strategy"], s["name"], s["symbol"], s["contract"], s["tf"], s["trades"],
                        s["net"], round(2 * s["net"], 2), s["gross"], round(s["gross"] - s["net"], 2),
                        s["pf"], s["win_pct"], s["avg_trade"], s["max_dd"], round(2 * s["max_dd"], 2),
                        s["net_to_dd"], s["sharpe"], f"{s['years_profitable']}/{s['years']}",
                        s["first_trade"], s["last_trade"]])
    with open(os.path.join(OUT, "by_year.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["strategy", "market", "timeframe"] + years)
        for s in runs:
            by = s.get("by_year", {})
            w.writerow([s["strategy"], s["symbol"], s["tf"]] + [by.get(y, 0) for y in years])
    print("wrote summary.csv and by_year.csv")


if __name__ == "__main__":
    main()
