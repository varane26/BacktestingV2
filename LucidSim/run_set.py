"""Standard report for a hand-picked set of strategy x market x timeframe runs, in one folder, with every
period evaluated in its own process (faster than run_lucid.py's one process per run).

Usage: python -I LucidSim/run_set.py --runs S11:NQ:5,S12:ES:5,S13:NQ:15 --out <absolute path>
       A run may add a label and its own params: S15:GC:5:half:asian_stop_frac=0.5;asian_max_rng=1
       (run id S15half_GC_5m); --param values apply to every run.
       [--from 2016-01-01] [--sizes 1,2,3,4] [--schemes all] [--param key=value ...]
       [--commission 0.75] [--slip-ticks 1] [--procs 8] [--title text]
Writes the same files as run_lucid.py (tables.md, datasheet.html, stats.csv, lucid.csv, ...).
"""
import argparse
import os
import sys
import time
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "BacktestEngine"))

import sizing  # noqa: E402
from data import load, eth_session, ROOT  # noqa: E402
from run_all import START, COMMISSION, SLIP_TICKS, SPECS, PARAMS  # noqa: E402
from run_lucid import evaluate, write_outputs, periods_from, tf_label  # noqa: E402
from strategies import STRATEGIES  # noqa: E402

_BARS = {}


def _bars(sym):
    if sym not in _BARS:
        b = eth_session(load(sym))
        _BARS[sym] = (b, sizing.market_flags(b))
    return _BARS[sym]


def job(args):
    key, lab, rp, sym, tf, period, whole, out, comm, slip, over, sizes, schemes = args
    name, fn, _ = STRATEGIES[key]
    b, flags = _bars(sym)
    i0 = next(i for i in range(b.n) if b.day[i] >= START.toordinal())
    p = dict(PARAMS[sym])
    p.update(over)
    p.update(rp)
    eng = fn(b, tf, i0, b.n, p)
    spec = SPECS[sym]
    meta = {"strategy": key + lab, "name": name + (f" [{lab}]" if lab else ""), "market": sym, "contract": spec["contract"],
            "timeframe": tf_label(tf), "settings": p}
    return evaluate(b, eng.trades, meta, spec, [period], whole, out, comm, slip, sizes, schemes, flags)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", required=True)
    ap.add_argument("--from", dest="start", default="2016-01-01")
    ap.add_argument("--sizes", default="1,2,3,4")
    ap.add_argument("--schemes", default="all")
    ap.add_argument("--commission", type=float, default=COMMISSION)
    ap.add_argument("--slip-ticks", type=float, default=SLIP_TICKS)
    ap.add_argument("--param", action="append", default=[])
    ap.add_argument("--out", required=True)
    ap.add_argument("--procs", type=int, default=8)
    ap.add_argument("--title", default="Lucid report")
    a = ap.parse_args()
    out = a.out if os.path.isabs(a.out) else os.path.join(ROOT, "results", a.out)
    for sub in ("runs", "equity", "daily", "trades"):
        os.makedirs(os.path.join(out, sub), exist_ok=True)
    sizes = [int(x) for x in a.sizes.split(",") if x]
    schemes = None if a.schemes == "all" else ([] if a.schemes == "none" else a.schemes.split(","))
    over = {}
    for k, v in (x.split("=", 1) for x in a.param):
        try:
            over[k] = float(v)
        except ValueError:
            over[k] = v
    runs = []
    for r in a.runs.split(","):
        k, s, t, *rest = r.split(":")
        lab = rest[0] if rest else ""
        rp = {}
        for kv in (rest[1].split(";") if len(rest) > 1 else []):
            x, v = kv.split("=", 1)
            try:
                rp[x] = float(v)
            except ValueError:
                rp[x] = v
        runs.append((k, lab, rp, s, int(t)))
    periods = periods_from(a.start)
    jobs = [(k, lab, rp, s, t, per, periods[0][0], out, a.commission, a.slip_ticks, over, sizes, schemes)
            for k, lab, rp, s, t in runs for per in periods]
    # the whole-window jobs are the slowest: start them first
    jobs.sort(key=lambda j: j[5][0] != periods[0][0])
    t0 = time.time()
    recs, charts, by_year, exits = [], [], [], {}
    with Pool(min(a.procs, len(jobs))) as pool:
        for rs, cs, by, ex in pool.imap_unordered(job, jobs):
            r1 = rs[0]
            print(f"{r1['strategy']} {r1['market']} {r1['timeframe']} {r1['period']}: 1 ct net "
                  f"${r1['stats']['net_profit']:,.0f}, PF {r1['stats']['profit_factor'] or 0:.2f}, Lucid pass "
                  f"{r1['lucidpro_50k']['evaluation_pass_rate_pct']:.1f}%  ({time.time() - t0:.0f}s)", flush=True)
            recs.extend(rs)
            charts.extend(cs)
            by_year.extend(by)
            exits.update(ex)
    rorder = {(k + lab, s, tf_label(t)): n for n, (k, lab, _, s, t) in enumerate(runs)}
    porder = {p[0]: n for n, p in enumerate(periods)}
    order = {lab: n for n, (lab, *_) in enumerate(sizing.sizings(sizes, schemes))}
    recs.sort(key=lambda r: (rorder[(r["strategy"], r["market"], r["timeframe"])], porder[r["period"]], order[r["sizing"]]))
    rid = {f"{k}{lab}_{s}_{tf_label(t)}": n for n, (k, lab, _, s, t) in enumerate(runs)}
    by_year.sort(key=lambda r: (rid[r["run"]], r["year"]))
    info = {"from": a.start, "periods": periods, "commission_per_side": a.commission,
            "slippage_ticks_per_side": a.slip_ticks, "limit_fill": "touch",
            "params": {**over, **{k + lab: rp for k, lab, rp, _, _ in runs if rp}}}
    write_outputs(out, recs, sorted(charts, key=lambda c: next(n for r, n in rid.items() if c.startswith(r + "_"))),
                  by_year, exits, info, sizes, schemes, a.title)
    print(f"done in {time.time() - t0:.0f}s -> {out}")


if __name__ == "__main__":
    main()
