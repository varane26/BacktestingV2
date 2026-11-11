"""Standard report: full account stats + LucidPro 50K simulation + equity curves + report tables, for every
strategy x market x timeframe x sizing x period. This is the user's report format; use it for every test,
for every strategy (the BacktestEngine strategies here, VaultBreak through Vaultbreak/scripts/vb_lucid.py).

Sizings: fixed 1..N contracts (--sizes) and the standard schemes in sizing.py (--schemes).
Periods: the whole window from --from, plus 2016-2019, 2020-2023, 2024 onward and 2020 onward (clipped to --from).
Strategies warm up on data from 2016; a period counts the trades entered inside it.

Usage: python -I LucidSim/run_lucid.py --only S08 --symbols NQ --tfs 60,240,0
       [--from 2016-01-01] [--sizes 1,2,3,4] [--schemes all|none|"Trend 1/2,Vol target 1-4"]
       [--param key=value ...] [--commission 0.75] [--slip-ticks 1] [--limit-fill touch|through]
       [--out name or absolute path] [--procs 8]
Writes results/<--out>/:
  tables.md       the report tables to show the user, per run x period: A performance / risk,
                  B trades, C LucidPro 50K, one row per sizing (lucid_report.py)
  datasheet.html  everything in one page: settings, key results, by year, exit reasons, all equity
                  curves, every stats / Lucid field, and improve.json if the folder has one
  stats.csv       every account stat (net, CAGR, Sharpe, Sortino, Calmar, drawdowns, trade stats ...)
  lucid.csv       every LucidPro 50K field (pass rates, mean / median days to pass, payouts, breaches ...)
  by_year.csv     1-contract trades, win rate, net and PF per calendar year, whole window
  summary.json    settings, sizing descriptions, exit-reason counts and all records
  runs/           one JSON per run x period x sizing
  equity/         <run>_<period>_{sizes,balance_schemes,market_schemes}.svg, index.html
  daily/          end-of-day equity per sizing, whole window
  trades/         1-contract trades with MAE / MFE and exit reason, whole window
"""
import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import date
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "BacktestEngine"))

import engine  # noqa: E402
import sizing  # noqa: E402
from charts import equity_multi_svg, gallery_html  # noqa: E402
from data import load, eth_session, ROOT  # noqa: E402
from lucid_report import build  # noqa: E402
from metrics import analyze  # noqa: E402
from propsim import simulate, RULES  # noqa: E402
from run_all import START, COMMISSION, SLIP_TICKS, SPECS, PARAMS, fmt_ct  # noqa: E402
from strategies import STRATEGIES  # noqa: E402

ACCOUNT = RULES["account_size"]
STD_PERIODS = [("2016-2019", "2016-01-01", "2020-01-01"), ("2020-2023", "2020-01-01", "2024-01-01"),
               ("2024-2026", "2024-01-01", "2100-01-01"), ("2019-2026", "2019-01-01", "2100-01-01")]   # user 2026-11-08: 2019-2026 replaces 2020-2026
CHART_GROUPS = [("sizes", ("fixed",)), ("balance_schemes", ("balance",)), ("market_schemes", ("market",))]


def tf_label(tf):
    return "daily" if tf == 0 else (f"{tf // 60}h" if tf >= 60 and tf % 60 == 0 else f"{tf}m")


def periods_from(start):
    out = [(f"{start[:4]}-2026", start, "2100-01-01")]
    for lab, lo, hi in STD_PERIODS:
        if hi > start:
            out.append((lab if lo >= start else f"{start[:4]}-{lab[5:]}", max(lo, start), hi))
    return out


def slug(s):
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")


def run_id(meta):
    return f"{meta['strategy']}_{meta['market']}_{meta['timeframe']}"


def evaluate(b, all_trades, meta, spec, periods, whole, out, comm, slip, sizes, schemes, flags, lucid=True):
    """The standard report for one strategy run (its trades on bars b) over `periods`; any strategy
    engine can call it. meta: strategy, name, market, contract, timeframe, settings. whole: label of
    the whole-window period (trades / daily / by-year files are written for it).
    Returns (records, chart files, by-year rows, exit-reason counts). lucid=False skips the LucidPro sim."""
    run = run_id(meta)
    sim = simulate if lucid else (lambda *a, **k: {})
    sday = lambda i: b.day[i] + (1 if b.hhmm[i] > 1600 else 0)
    plan = sizing.sizings(sizes, schemes)
    recs, charts, by_year, exits = [], [], [], {}
    for plab, lo, hi in periods:
        lo_o, hi_o = date.fromisoformat(lo).toordinal(), date.fromisoformat(hi).toordinal()
        i_from = next(i for i in range(b.n) if sday(i) >= lo_o)
        i_to = next((i for i in range(i_from, b.n) if sday(i) >= hi_o), b.n)
        trades = [t for t in all_trades if i_from <= t[0] < i_to]
        a = (b, trades, i_from, spec["pv"], spec["tick"], comm, slip)
        st1, days1, rows1 = analyze(*a, 1, ACCOUNT, i_to)
        ctx = sizing.context(flags, days1)
        curves = {}
        for lab, kind, rule, _ in plan:
            if kind == "fixed":
                n = rule(None, None, ctx)
                st, days, rows = (st1, days1, rows1) if n == 1 else analyze(*a, n, ACCOUNT, i_to)
                rule_bal = lambda bal, n=n: n
                rule_bal.label = lab
                lp = sim(days1, sizing=rule_bal)
            else:
                qty = lambda ei, bal, rule=rule: rule(sday(ei), bal, ctx)
                st, days, rows = analyze(*a, qty, ACCOUNT, i_to)
                if kind == "balance":
                    rule_bal = lambda bal, rule=rule: rule(None, bal, ctx)
                    rule_bal.label = lab
                    lp = sim(days1, sizing=rule_bal)
                else:
                    lp = sim(days)
                    if lp:
                        lp["sizing"] = lp["funded_sizing"] = f"{lab} (day paths at the sizes traded)"
            sized = [r["contracts"] for r in rows]
            st["average_contracts_per_trade"] = sum(sized) / len(sized) if sized else None
            rec = {**{k: meta[k] for k in ("strategy", "name", "market", "contract", "timeframe")},
                   "settings": meta.get("settings", {}), "period": plab, "sizing": lab, "stats": st,
                   "lucidpro_50k": lp}
            with open(os.path.join(out, "runs", f"{run}_{plab}_{slug(lab)}.json"), "w") as fh:
                json.dump(rec, fh, indent=1, default=str)
            recs.append(rec)
            curves[lab] = [d[1] + d[4] for d in days]
        day_list = [d[0] for d in days1]
        n = min(len(c) for c in curves.values())
        sub = (f"{meta['contract']} | {plab} | ${comm}/side + {slip:g} tick | 1 ct: PF {st1['profit_factor'] or 0:.2f}, "
               f"Sharpe {st1['sharpe_ratio'] or 0:.2f}"
               + (f", Lucid pass {recs[-len(plan)]['lucidpro_50k']['evaluation_pass_rate_pct']:.0f}%" if lucid else ""))
        for part, kinds in CHART_GROUPS:
            labs = ([] if part == "sizes" or "1 ct" not in curves else ["1 ct"]) + \
                [lab for lab, kind, _, _ in plan if kind in kinds]
            if labs and (part == "sizes" or labs != ["1 ct"]):
                fn = f"{run}_{plab}_{part}.svg"
                equity_multi_svg(day_list[:n], {lab: curves[lab][:n] for lab in labs},
                                 f"{meta['strategy']} {meta['name']}, {meta['market']} {meta['timeframe']}: "
                                 f"{part.replace('_', ' ')}", sub, os.path.join(out, "equity", fn), ACCOUNT)
                charts.append(fn)
        if plab != whole:
            continue
        lab_of = {t[0]: t[8] for t in trades}
        for t in trades:
            exits[t[8]] = exits.get(t[8], 0) + 1
        with open(os.path.join(out, "trades", f"{run}.csv"), "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["entry_bar_ct", "exit_bar_ct", "side", "entry_px", "exit_px",
                        "net_usd", "mae_usd", "mfe_usd", "bars_held", "exit_reason"])
            for r in rows1:
                w.writerow([fmt_ct(b.cabs[r["entry_i"]]), fmt_ct(b.cabs[r["exit_i"]]), r["side"],
                            r["entry_px"], r["exit_px"], r["net_usd"], r["mae_usd"], r["mfe_usd"],
                            r["bars_held"], lab_of.get(r["entry_i"], "")])
        with open(os.path.join(out, "daily", f"{run}.csv"), "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["date"] + [f"equity {lab}" for lab in curves])
            for i in range(n):
                w.writerow([date.fromordinal(day_list[i]).isoformat()] + [round(c[i], 2) for c in curves.values()])
        years = {}
        for r in rows1:
            s = years.setdefault(date.fromordinal(sday(r["exit_i"])).year, [0, 0, 0.0, 0.0])
            s[0] += 1
            s[1] += r["net_usd"] > 0
            s[2 if r["net_usd"] > 0 else 3] += r["net_usd"]
        by_year = [{"run": run, "year": y, "trades": s[0], "win_rate_pct": round(100 * s[1] / s[0], 2),
                    "net_1ct": round(s[2] + s[3], 2), "profit_factor": round(s[2] / -s[3], 3) if s[3] else None}
                   for y, s in sorted(years.items())]
    return recs, charts, by_year, {run: exits} if exits else {}


def write_table(path, recs, part):
    keys = []
    for r in recs:
        for k in r[part]:
            if k not in keys:
                keys.append(k)
    ids = ["strategy", "name", "market", "contract", "timeframe", "period", "sizing"]
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(ids + keys)
        for r in recs:
            w.writerow([r[k] for k in ids] + [r[part].get(k) for k in keys])


def write_outputs(out, recs, charts, by_year, exits, info, sizes, schemes, title):
    """Everything after the runs: CSVs, summary.json, chart gallery, tables.md and datasheet.html.
    recs must already be in report order (run, period, sizing)."""
    plan = sizing.sizings(sizes, schemes)
    write_table(os.path.join(out, "stats.csv"), recs, "stats")
    write_table(os.path.join(out, "lucid.csv"), recs, "lucidpro_50k")
    with open(os.path.join(out, "by_year.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["run", "year", "trades", "win_rate_pct", "net_1ct", "profit_factor"])
        w.writeheader()
        w.writerows(by_year)
    with open(os.path.join(out, "summary.json"), "w") as fh:
        json.dump({**info, "title": title, "sizings": {lab: desc for lab, _, _, desc in plan},
                   "exit_counts": exits, "charts": charts, "runs": recs}, fh, indent=1, default=str)
    gallery_html(os.path.join(out, "equity"), [(c, c[:-4].replace("_", " ")) for c in charts], title)
    build(out)


def job(args):
    key, sym, tf, start, out, comm, slip, through, over, sizes, schemes, lucid, periods = args
    engine.LIMIT_THROUGH = through
    name, fn, _ = STRATEGIES[key]
    b = eth_session(load(sym))
    i0 = next(i for i in range(b.n) if b.day[i] >= START.toordinal())
    p = dict(PARAMS[sym])
    p.update(over)
    eng = fn(b, tf, i0, b.n, p)
    spec = SPECS[sym]
    # user 2026-11-08: runs are labelled by the strategy name, never by S-codes
    meta = {"strategy": slug(name), "name": name, "market": sym, "contract": spec["contract"],
            "timeframe": tf_label(tf), "settings": p}
    return evaluate(b, eng.trades, meta, spec, periods, periods[0][0], out, comm, slip, sizes, schemes,
                    sizing.market_flags(b), lucid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default="2016-01-01")
    ap.add_argument("--only", default=",".join(STRATEGIES))
    ap.add_argument("--symbols", default="NQ")
    ap.add_argument("--tfs", default="1,5,15,60")
    ap.add_argument("--sizes", default="1,2,3,4")
    ap.add_argument("--schemes", default="all")
    ap.add_argument("--commission", type=float, default=COMMISSION)
    ap.add_argument("--slip-ticks", type=float, default=SLIP_TICKS)
    ap.add_argument("--limit-fill", choices=["touch", "through"], default="touch")
    ap.add_argument("--out", default=None)
    ap.add_argument("--param", action="append", default=[])
    ap.add_argument("--procs", type=int, default=8)
    ap.add_argument("--no-lucid", action="store_true", help="skip the LucidPro 50K sim (tables A and B only)")
    ap.add_argument("--periods", default=None,
                    help="brief test: only these period labels, comma-separated (e.g. 2019-2026,2024-2026)")
    a = ap.parse_args()
    periods = periods_from(a.start)
    if a.periods:
        want = a.periods.split(",")
        periods = [next(p for p in periods if p[0] == w) for w in want]
    out = os.path.join(ROOT, "results", a.out or f"lucidpro50k_{a.start[:4]}")
    for sub in ("runs", "equity", "daily", "trades"):
        os.makedirs(os.path.join(out, sub), exist_ok=True)
    sizes = [int(x) for x in a.sizes.split(",") if x]
    schemes = None if a.schemes == "all" else ([] if a.schemes == "none" else a.schemes.split(";" if ";" in a.schemes else ","))
    over = {}
    for k, v in (x.split("=", 1) for x in a.param):
        try:
            over[k] = float(v)
        except ValueError:
            over[k] = v
    jobs = []
    for key in a.only.split(","):
        for sym in a.symbols.split(","):
            for tf in ([int(x) for x in a.tfs.split(",")] if STRATEGIES[key][2] else [0]):
                jobs.append((key, sym, tf, a.start, out, a.commission, a.slip_ticks,
                             a.limit_fill == "through", over, sizes, schemes, not a.no_lucid, periods))
    jobs.sort(key=lambda j: (j[2] != 1, j[:3]))
    t0 = time.time()
    recs, charts, by_year, exits = [], [], [], {}
    with Pool(min(a.procs, len(jobs))) as pool:
        for rs, cs, by, ex in pool.imap_unordered(job, jobs):
            r1 = next(r for r in rs if r["sizing"] == "1 ct")
            print(f"{r1['strategy']} {r1['market']} {r1['timeframe']:>5}: 1 ct net ${r1['stats']['net_profit']:,.0f}, "
                  f"Sharpe {r1['stats']['sharpe_ratio'] or 0:.2f}"
                  + (f", Lucid pass {r1['lucidpro_50k']['evaluation_pass_rate_pct']:.1f}%" if r1['lucidpro_50k'] else ""),
                  flush=True)
            recs.extend(rs)
            charts.extend(cs)
            by_year.extend(by)
            exits.update(ex)
    order = {lab: k for k, (lab, *_) in enumerate(sizing.sizings(sizes, schemes))}
    porder = {p[0]: k for k, p in enumerate(periods)}
    recs.sort(key=lambda r: (r["strategy"], r["market"], r["timeframe"], porder[r["period"]], order[r["sizing"]]))
    by_year.sort(key=lambda r: (r["run"], r["year"]))
    info = {"from": a.start, "periods": periods, "commission_per_side": a.commission,
            "slippage_ticks_per_side": a.slip_ticks, "limit_fill": a.limit_fill, "params": over,
            "lucid": not a.no_lucid}
    write_outputs(out, recs, sorted(charts), by_year, exits, info, sizes, schemes, f"{'Lucid' if not a.no_lucid else 'Backtest'} report from {a.start}")
    print(f"done in {time.time() - t0:.0f}s -> {out}")


if __name__ == "__main__":
    main()
