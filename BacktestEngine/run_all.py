"""Run every strategy x market x signal timeframe and write results/.

Usage: python -I BacktestEngine/run_all.py [--only S01,S04] [--symbols NQ,ES] [--tfs 1,5,15,60]
"""
import argparse
import csv
import json
import math
import os
import sys
import time
from datetime import date
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data import load, eth_session, ROOT  # noqa: E402
from engine import LIMIT  # noqa: E402
from strategies import STRATEGIES  # noqa: E402

START = date(2016, 1, 1)          # ES/NQ day sessions are incomplete before 2016
COMMISSION = 0.75                 # $ per contract per side (micro)
SLIP_TICKS = 1                    # ticks per side on market and stop fills; none on limits
SPECS = {                         # micro contract traded on each market's data
    "NQ": {"contract": "MNQ", "pv": 2.0, "tick": 0.25},
    "ES": {"contract": "MES", "pv": 5.0, "tick": 0.25},
    "GC": {"contract": "MGC", "pv": 10.0, "tick": 0.10},
    "BTC": {"contract": "MBT", "pv": 0.10, "tick": 5.0},
}
PARAMS = {
    "NQ": {"gap_min": 0.5, "tick": 0.25, "mom_pct": 0.10,
           "long_stop": 80, "long_tgt": 40, "short_stop": 80, "short_tgt": 50},
    # strategy 04's point stops/targets are NQ-sized; ES uses a quarter of them
    "ES": {"gap_min": 0.5, "tick": 0.25, "mom_pct": 0.10,
           "long_stop": 20, "long_tgt": 10, "short_stop": 20, "short_tgt": 12.5},
    # GC / BTC: no point stops/targets set for strategy 04 yet (it raises KeyError there)
    "GC": {"gap_min": 0.5, "tick": 0.10, "mom_pct": 0.10},
    "BTC": {"gap_min": 5.0, "tick": 5.0, "mom_pct": 0.10},
}
OUT = os.path.join(ROOT, "results")


def fmt_ct(cabs):
    d, m = divmod(cabs, 1440)
    return f"{date.fromordinal(d).isoformat()} {m // 60:02d}:{m % 60:02d}"


def summarize(eng, cabs, pv, tick):
    slip = SLIP_TICKS * tick * pv
    nets, rows = [], []
    for ei, xi, side, epx, xpx, ek, xk, el, xl in eng.trades:
        gross = side * (xpx - epx) * pv
        cost = 2 * COMMISSION + (slip if ek != LIMIT else 0) + (slip if xk != LIMIT else 0)
        net = gross - cost
        nets.append(net)
        rows.append((fmt_ct(cabs[ei]), fmt_ct(cabs[xi]), "long" if side == 1 else "short",
                     epx, xpx, el, xl, round(gross, 2), round(net, 2), cabs[xi] // 1440))
    n = len(nets)
    s = {"trades": n}
    if n == 0:
        return s, rows
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x <= 0]
    eq = peak = dd = 0.0
    for x in nets:
        eq += x
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    by_year, by_day = {}, {}
    for r, x in zip(rows, nets):
        y = date.fromordinal(r[9]).year
        by_year[y] = by_year.get(y, 0.0) + x
        by_day[r[9]] = by_day.get(r[9], 0.0) + x
    # Sharpe on daily P&L over every weekday in the test window (flat days count as 0)
    d0, d1 = rows[0][9], rows[-1][9]
    days = [by_day.get(d, 0.0) for d in range(d0, d1 + 1) if date.fromordinal(d).weekday() < 5]
    mean = sum(days) / len(days)
    var = sum((x - mean) ** 2 for x in days) / max(1, len(days) - 1)
    gross_loss = -sum(losses)
    s.update({
        "net": round(sum(nets), 2),
        "gross": round(sum(r[7] for r in rows), 2),
        "win_pct": round(100.0 * len(wins) / n, 1),
        "pf": round(sum(wins) / gross_loss, 2) if gross_loss > 0 else None,
        "avg_trade": round(sum(nets) / n, 2),
        "max_dd": round(dd, 2),
        "net_to_dd": round(sum(nets) / dd, 2) if dd > 0 else None,
        "sharpe": round(mean / math.sqrt(var) * math.sqrt(252), 2) if var > 0 else None,
        "years_profitable": sum(1 for v in by_year.values() if v > 0),
        "years": len(by_year),
        "by_year": {str(k): round(v, 2) for k, v in sorted(by_year.items())},
        "first_trade": rows[0][0],
        "last_trade": rows[-1][1],
    })
    return s, rows


def job(args):
    key, sym, tf = args
    name, fn, _ = STRATEGIES[key]
    b = eth_session(load(sym))
    i0 = next(i for i in range(b.n) if b.day[i] >= START.toordinal())
    t0 = time.time()
    eng = fn(b, tf, i0, b.n, PARAMS[sym])
    spec = SPECS[sym]
    s, rows = summarize(eng, b.cabs, spec["pv"], spec["tick"])
    os.makedirs(os.path.join(OUT, "trades"), exist_ok=True)
    tf_lab = f"{tf}m" if tf else "daily"
    with open(os.path.join(OUT, "trades", f"{key}_{sym}_{tf_lab}.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["entry_bar_ct", "exit_bar_ct", "side", "entry_px", "exit_px",
                    "entry_order", "exit_order", "gross_usd_1ct", "net_usd_1ct"])
        for r in rows:
            w.writerow(r[:9])
    s.update({"strategy": key, "name": name, "symbol": sym, "contract": spec["contract"],
              "tf": tf_lab, "secs": round(time.time() - t0, 1)})
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=",".join(STRATEGIES))
    ap.add_argument("--symbols", default="NQ,ES")
    ap.add_argument("--tfs", default="1,5,15,60")
    ap.add_argument("--procs", type=int, default=8)
    a = ap.parse_args()
    tfs = [int(x) for x in a.tfs.split(",")]
    jobs = []
    for key in a.only.split(","):
        tf_dependent = STRATEGIES[key][2]
        for sym in a.symbols.split(","):
            for tf in (tfs if tf_dependent else [0]):
                jobs.append((key, sym, tf))
    jobs.sort(key=lambda j: (j[2] != 1, j))       # slowest (1-minute) first
    t0 = time.time()
    results = []
    with Pool(min(a.procs, len(jobs))) as pool:
        for s in pool.imap_unordered(job, jobs):
            results.append(s)
            print(f"{s['strategy']} {s['symbol']} {s['tf']:>5}: trades {s['trades']:>6}  "
                  f"net ${s.get('net', 0):>11,.2f}  pf {s.get('pf')}  dd ${s.get('max_dd', 0):,.0f}"
                  f"  ({s['secs']}s)", flush=True)
    results.sort(key=lambda s: (s["strategy"], s["symbol"] != "NQ", s["tf"]))
    os.makedirs(OUT, exist_ok=True)
    tag = "" if a.only == ",".join(STRATEGIES) else "_" + a.only.replace(",", "_")
    with open(os.path.join(OUT, f"summary{tag}.json"), "w") as fh:
        json.dump({"start": START.isoformat(), "commission_per_side": COMMISSION,
                   "slippage_ticks_per_side": SLIP_TICKS, "specs": SPECS, "runs": results}, fh, indent=1)
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
