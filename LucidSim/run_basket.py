"""Standard report for a multi-leg, multi-market basket run as ONE strategy (e.g. Triple Open).

Each leg is a BacktestEngine strategy run on its own market. The legs are merged onto the NQ minute
timeline as one synthetic instrument whose price is the basket's dollar equity (1 unit = 1 micro per
leg, costs included): closed P&L plus the open legs marked to market at every minute close. One
basket trade = one session (first leg entry to last leg exit). Sizes and schemes scale the whole
basket. Then run_lucid.evaluate / write_outputs build the usual tables, charts and data sheet.

Usage: python -I LucidSim/run_basket.py --basket triple_v2 --out <abs path> [--no-lucid]
"""
import argparse
import os
import sys
from array import array

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(os.path.dirname(HERE), "BacktestEngine")]

import engine  # noqa: E402
import sizing  # noqa: E402
from data import load, eth_session, Bars, FIELDS  # noqa: E402
from run_all import START, COMMISSION, SLIP_TICKS, SPECS, PARAMS  # noqa: E402
from strategies import STRATEGIES  # noqa: E402
from run_lucid import evaluate, write_outputs, periods_from  # noqa: E402

V2 = dict(ml_chase=0.16, ml_skip_lastmon=1, ml_tp_atr=0.75, ml_lock_t=900, ml_lock_atr=0.1)
BASKETS = {
    "triple_v2": ("Triple Open V2 basket", [
        ("L656ES", "S16", "ES", 5, dict(V2, ml_adx_lt=30)),
        ("L644ES", "S12", "ES", 5, dict(V2, ml_adx_lt=30)),
        ("L644NQ", "S11", "NQ", 5, dict(V2)),
        ("L656NQ", "S16", "NQ", 5, dict(V2, ml_wk_min=-0.43))]),
    **{f"tv2_{tag}": (f"Triple Open V2 {tag}", [
        ("L656ES", "S16", "ES", 5, {**V2, "ml_adx_lt": 30, **ch}),
        ("L644ES", "S12", "ES", 5, {**V2, "ml_adx_lt": 30, **ch}),
        ("L644NQ", "S11", "NQ", 5, {**V2, **ch}),
        ("L656NQ", "S16", "NQ", 5, {**V2, "ml_wk_min": -0.43, **ch})]) for tag, ch in (
            ("keep_lastmon", dict(ml_skip_lastmon=0)),
            ("no_chase_filter", dict(ml_chase=0)),
            ("both_off", dict(ml_skip_lastmon=0, ml_chase=0)),
            ("es_adx_off", dict(ml_adx_lt=0)),
            ("only_exits", dict(ml_skip_lastmon=0, ml_chase=0, ml_adx_lt=0)))},
    "triple_paper": ("Triple Open paper basket", [
        ("L656ES", "S16", "ES", 5, {}),
        ("L644ES", "S12", "ES", 5, {}),
        ("L644NQ", "S11", "NQ", 5, {})]),
}


def leg_trades(bars, key, sym, tf, over):
    b = bars[sym]
    i0 = next(i for i in range(b.n) if b.day[i] >= START.toordinal())
    p = dict(PARAMS[sym]); p.update(over)
    return STRATEGIES[key][1](b, tf, i0, b.n, p).trades


def build(name, legs):
    bars = {s: eth_session(load(s)) for s in sorted({l[2] for l in legs})}
    base = bars["NQ"]
    pos_of = {c: i for i, c in enumerate(base.cabs)}            # NQ minute -> index
    n = base.n
    delta = [0.0] * (n + 1)                                     # closed P&L steps (difference array)
    mtm = [0.0] * n                                             # open-leg MTM at each NQ minute
    spans = []                                                  # (entry NQ idx, exit NQ idx, label)
    for lab, key, sym, tf, over in legs:
        b, pv, tick = bars[sym], SPECS[sym]["pv"], SPECS[sym]["tick"]
        for ei, xi, side, ep, xp, ek, xk, _el, xl in leg_trades(bars, key, sym, tf, over):
            cost = 2 * COMMISSION + SLIP_TICKS * tick * pv * ((ek != engine.LIMIT) + (xk != engine.LIMIT))
            entry_cost = COMMISSION + (SLIP_TICKS * tick * pv if ek != engine.LIMIT else 0)
            net = (xp - ep) * side * pv - cost
            # walk the leg's own bars, carry its last close onto every NQ minute in the span
            j0 = pos_of.get(b.cabs[ei]); j1 = pos_of.get(b.cabs[xi])
            if j0 is None:
                j0 = next(k for k in range(n) if base.cabs[k] >= b.cabs[ei])
            if j1 is None:
                j1 = next(k for k in range(j0, n) if base.cabs[k] >= b.cabs[xi])
            k = ei
            last = b.c[ei]
            for j in range(j0, j1):
                while k < xi and b.cabs[k] <= base.cabs[j]:
                    last = b.c[k]; k += 1
                mtm[j] += (last - ep) * side * pv - entry_cost
            delta[j1] += net
            spans.append((j0, j1, lab, xl))
    # synthetic price: closed cumulative + open MTM (o = h = l = c at minute closes)
    px = array("f")
    cum = 0.0
    for j in range(n):
        cum += delta[j]
        px.append(cum + mtm[j])
    cols = {name_: getattr(base, name_) for name_, _ in FIELDS}
    cols.update(o=px, h=px, l=px, c=px)
    syn = Bars("BASKET", cols)
    # one basket trade per session: merge overlapping leg spans
    spans.sort()
    trades, cur = [], None
    for j0, j1, lab, xl in spans:
        if cur and j0 <= cur[1]:
            cur[1] = max(cur[1], j1); cur[2].add(lab)
        else:
            if cur: trades.append(cur)
            cur = [j0, j1, {lab}]
    if cur: trades.append(cur)
    # entry one bar before the first leg's entry minute so the entry MTM falls inside the trade
    out = [(max(0, j0 - 1), j1, 1, syn.c[max(0, j0 - 1)], syn.c[j1], engine.LIMIT, engine.LIMIT,
            "Basket", f"{len(labs)} legs") for j0, j1, labs in trades]
    return syn, out, sizing.market_flags(base)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--basket", default="triple_v2")
    ap.add_argument("--from", dest="start", default="2016-01-01")
    ap.add_argument("--sizes", default="1,2,3,4")
    ap.add_argument("--schemes", default="all")
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-lucid", action="store_true")
    a = ap.parse_args()
    out = a.out
    for d in ("runs", "equity", "trades", "daily"):
        os.makedirs(os.path.join(out, d), exist_ok=True)
    sizes = [int(x) for x in a.sizes.split(",")]
    schemes = None if a.schemes == "all" else ([] if a.schemes == "none" else a.schemes.split(","))
    recs, charts, by_year, exits = [], [], [], {}
    for bk in a.basket.split(","):
        name, legs = BASKETS[bk]
        syn, trades, flags = build(name, legs)
        meta = {"strategy": {"triple_v2": "TOV2", "triple_paper": "TOPAPER"}.get(bk, bk.upper()), "name": name, "market": "ES+NQ", "contract": "1 micro per leg",
                "timeframe": "5m", "settings": {l[0]: l[4] for l in legs}}
        spec = {"pv": 1.0, "tick": 0.01}
        periods = periods_from(a.start)
        r, c, y, e = evaluate(syn, trades, meta, spec, periods, periods[0][0], out, 0.0, 0.0, sizes, schemes,
                              flags, not a.no_lucid)
        recs += r; charts += c; by_year += y; exits.update(e)
        print(name, "done:", len(trades), "basket trades")
    write_outputs(out, recs, charts, by_year, exits,
                  {"costs": f"${COMMISSION}/side + {SLIP_TICKS} tick per leg, inside the basket price", "from": a.start,
                   "periods": periods_from(a.start), "commission_per_side": COMMISSION, "slippage_ticks_per_side": SLIP_TICKS,
                   "limit_fill": "touch", "params": {}, "lucid": not a.no_lucid}, sizes, schemes, "Triple Open basket report from " + a.start)


if __name__ == "__main__":
    main()
