"""Forecast-to-Fill (S08) on NQ traded as MNQ: three tests, every timeframe, sizes 1-4 MNQ and sizing
schemes, LucidPro 50K simulation, each period separately.

  A  lucid      original code, flat 15:40 CT and back in at 17:00 (LucidPro rules, no DLL)
  B  overnight  original code as written, positions held overnight (Lucid sim ignores that rule)
  C  improved   flat like A, plus entry/exit thresholds 0.6/0.4 and ATR-normalised slope
  C-overnight   C's signal held overnight; ablations on 1h, 4h and daily isolate each change.

Writes results/s08_three_tests/: stats.csv (full account stats, fixed sizes), schemes.csv,
lucid.csv, summary.json, trades/, daily/, equity/*.svg + index.html.
Usage: python -I BacktestEngine/s08_tests.py
"""
import csv
import json
import math
import os
import statistics
import sys
from datetime import date
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "LucidSim"))

import propsim  # noqa: E402
from charts import gallery_html  # noqa: E402
from data import load, eth_session, ROOT  # noqa: E402
from metrics import analyze  # noqa: E402
from run_all import START, COMMISSION, SLIP_TICKS, SPECS, PARAMS, fmt_ct  # noqa: E402
from strategies import STRATEGIES  # noqa: E402

OUT = os.path.join(ROOT, "results", "s08_three_tests")
ACCOUNT = 50000.0
TFS = [1, 5, 15, 60, 240, 0]                      # 0 = session daily bars (17:00-16:00 CT)
PERIODS = [("2016-2026", "2016-01-01", "2100-01-01"), ("2016-2019", "2016-01-01", "2020-01-01"),
           ("2020-2023", "2020-01-01", "2024-01-01"), ("2024-2026", "2024-01-01", "2100-01-01")]
IMPROVED = {"entry_thr": 0.6, "exit_thr": 0.4, "slope_norm": "atr"}
TESTS = {   # name: (params, timeframes, full sizing grid)
    "A_lucid": ({"lucid_flat": True}, TFS, True),
    "B_overnight": ({}, TFS, True),
    "C_improved": ({"lucid_flat": True, **IMPROVED}, TFS, True),
    "C_improved_overnight": (dict(IMPROVED), TFS, True),
    "C1_thresholds_only": ({"lucid_flat": True, "entry_thr": 0.6, "exit_thr": 0.4}, [60, 240, 0], False),
    "C2_atr_slope_only": ({"lucid_flat": True, "slope_norm": "atr"}, [60, 240, 0], False),
    "C3_rth_entries_only": ({"lucid_flat": True, "rth_only": True}, [60, 240], False),
    "C4_improved_plus_rth": ({"lucid_flat": True, **IMPROVED, "rth_only": True}, [60, 240], False),
}


def tf_lab(tf):
    return "daily" if tf == 0 else (f"{tf // 60}h" if tf >= 60 else f"{tf}m")


# ---- sizing schemes: q(day index, start-of-day balance, ctx); size is fixed when a trade starts ----
def fixed(n):
    return lambda k, bal, ctx: n


SCHEMES = [
    ("1 MNQ", fixed(1)), ("2 MNQ", fixed(2)), ("3 MNQ", fixed(3)), ("4 MNQ", fixed(4)),
    ("1->2 at +$2.5k", lambda k, bal, ctx: 2 if bal >= ACCOUNT + 2500 else 1),
    ("1->4, +1 per +$1k", lambda k, bal, ctx: max(1, min(4, 1 + int((bal - ACCOUNT) // 1000)))),
    ("2, 1 below start", lambda k, bal, ctx: 2 if bal >= ACCOUNT else 1),
    ("Trend 1/2", lambda k, bal, ctx: 2 if ctx["uptrend"][k] else 1),
    ("Calm vol 1/2", lambda k, bal, ctx: 2 if ctx["calm"][k] else 1),
    ("Vol target 1-4", lambda k, bal, ctx: ctx["voltarget"][k]),
    ("Equity curve 1/2", lambda k, bal, ctx: 2 if ctx["eq_up"][k] else 1),
    ("Bench 0/1 (equity filter)", lambda k, bal, ctx: 1 if ctx["eq_up"][k] else 0),
]
BALANCE_SCHEMES = {"1->2 at +$2.5k", "1->4, +1 per +$1k", "2, 1 below start"}
SCHEME_NOTES = {
    "Trend 1/2": "2 MNQ when NQ closed above its 50-day average the session before",
    "Calm vol 1/2": "2 MNQ when the 20-day average session range is below its 1-year median",
    "Vol target 1-4": "round(2 x 1-year median range / 20-day range), 1 to 4 MNQ (volatility targeting in points)",
    "Equity curve 1/2": "2 MNQ when the 1-MNQ equity is above its 20-day average",
    "Bench 0/1 (equity filter)": "1 MNQ only while the 1-MNQ equity is above its 20-day average, else no trades",
}


def market_flags(b):
    sess = {}
    for i in range(b.n):
        sd = b.day[i] + (1 if b.hhmm[i] > 1600 else 0)
        h, l, c = b.h[i], b.l[i], b.c[i]
        if sd in sess:
            s = sess[sd]
            s[0], s[1], s[2] = max(s[0], h), min(s[1], l), c
        else:
            sess[sd] = [h, l, c]
    keys = sorted(sess)
    closes = [sess[k][2] for k in keys]
    rng = [sess[k][0] - sess[k][1] for k in keys]
    up, cm, vt = {}, {}, {}
    for j, k in enumerate(keys):
        if j >= 50:
            up[k] = closes[j - 1] > sum(closes[j - 50:j]) / 50
        if j >= 270:
            a20 = sum(rng[j - 20:j]) / 20
            med = sorted(sum(rng[m - 20:m]) / 20 for m in range(j - 250, j))[125]
            cm[k] = a20 < med
            vt[k] = max(1, min(4, round(2 * med / a20))) if a20 > 0 else 1
    return up, cm, vt


def context(flags, days):
    up, cm, vt = flags
    eq, cum = [], 0.0
    for d in days:
        eq.append(cum)
        cum += d[4]
    return {"uptrend": [up.get(d[0], False) for d in days], "calm": [cm.get(d[0], False) for d in days],
            "voltarget": [vt.get(d[0], 1) for d in days],
            "eq_up": [k >= 20 and eq[k] > sum(eq[k - 20:k]) / 20 for k in range(len(days))]}


def scheme_run(days, rows_by_day, qf, ctx):
    bal = ACCOUNT
    eqs, qs, rets, nets = [], [], [], []
    peak, mdd, mdd_intra, worst = ACCOUNT, 0.0, 0.0, 0.0
    q = 0
    for k, (sday, _, events, min_rest, eod) in enumerate(days):
        if not ctx["carry"][k]:
            q = qf(k, bal, ctx)
        qs.append(q)
        mdd_intra = max(mdd_intra, peak - (bal + q * min([m for m, _ in events] + [min_rest, 0.0])))
        if q > 0:
            nets.extend(q * x for x in rows_by_day.get(k, ()))
        new = bal + q * eod
        rets.append(new / bal - 1 if bal > 0 else 0.0)
        worst = min(worst, q * eod)
        bal = new
        peak = max(peak, bal)
        mdd = max(mdd, peak - bal)
        eqs.append(bal)
    wins = [x for x in nets if x > 0]
    gl = -sum(x for x in nets if x <= 0)
    sd = statistics.stdev(rets) if len(rets) > 1 else 0.0
    traded = [q for q, d in zip(qs, days) if d[2]]
    return {"net_profit": bal - ACCOUNT, "trades": len(nets),
            "win_rate_pct": 100 * len(wins) / len(nets) if nets else None,
            "profit_factor": sum(wins) / gl if gl > 0 else None,
            "average_trade": (bal - ACCOUNT) / len(nets) if nets else None,
            "max_drawdown_eod": -mdd, "max_drawdown_intraday": -mdd_intra, "worst_day": worst,
            "sharpe_ratio": statistics.fmean(rets) / sd * math.sqrt(252) if sd > 0 and min(eqs) > 0 else None,
            "account_wiped_out": min(eqs) <= 0,
            "avg_contracts_on_trade_days": statistics.fmean(traded) if traded else None}, eqs, qs


def lucid(days, name, qf, qs, ctx):
    if name in BALANCE_SCHEMES:
        orig = propsim._qty
        propsim._qty = lambda bal, sizing: qf(0, bal, ctx)
        try:
            return propsim.simulate(days, sizing=(0, 0, 0))
        finally:
            propsim._qty = orig
    scaled = [(sd_, sod, [(m * q, r * q) for m, r in ev], mr * q, eod * q)
              for (sd_, sod, ev, mr, eod), q in zip(days, qs)]
    return propsim.simulate(scaled)


def job(args):
    test, tf = args
    params, _, full_grid = TESTS[test]
    b = eth_session(load("NQ"))
    i0 = next(i for i in range(b.n) if b.day[i] >= START.toordinal())
    p = dict(PARAMS["NQ"])
    p.update(params)
    eng = STRATEGIES["S08"][1](b, tf, i0, b.n, p)
    spec = SPECS["NQ"]
    flags = market_flags(b)
    sd = lambda i: b.day[i] + (1 if b.hhmm[i] > 1600 else 0)
    schemes = SCHEMES if full_grid else SCHEMES[:2]
    out = {"test": test, "tf": tf_lab(tf), "stats": [], "schemes": [], "lucid": [], "curves": {}, "days": None,
           "trades": None}
    for label, lo, hi in PERIODS:
        lo_o, hi_o = date.fromisoformat(lo).toordinal(), date.fromisoformat(hi).toordinal()
        i_from = next(i for i in range(b.n) if sd(i) >= lo_o)
        trades = [t for t in eng.trades if lo_o <= sd(t[0]) < hi_o]
        sizes = (1, 2, 3, 4) if full_grid else (1,)
        for q in sizes:
            st, days_q, rows_q = analyze(b, trades, i_from, spec["pv"], spec["tick"], COMMISSION, SLIP_TICKS, q, ACCOUNT)
            if q == 1:
                days, rows = days_q, rows_q
            if st["last_day"] and hi_o < date.fromisoformat(st["last_day"]).toordinal():
                st["note"] = "account stats run to the end of the data; trades are those entered in the period"
            out["stats"].append({"test": test, "timeframe": tf_lab(tf), "period": label, "contracts": q, **st})
        days = [d for d in days if d[0] < hi_o]
        idx = {d[0]: k for k, d in enumerate(days)}
        rows_by_day = {}
        for r in rows:
            k = idx.get(sd(r["exit_i"]))
            if k is not None:
                rows_by_day.setdefault(k, []).append(r["net_usd"])
        ctx = context(flags, days)
        carry = [False] * len(days)
        for t in trades:
            for d in range(sd(t[0]) + 1, sd(t[1]) + 1):
                if d in idx:
                    carry[idx[d]] = True
        ctx["carry"] = carry
        for name, qf in schemes:
            st, eqs, qs = scheme_run(days, rows_by_day, qf, ctx)
            out["schemes"].append({"test": test, "timeframe": tf_lab(tf), "period": label, "scheme": name, **st})
            lr = lucid(days, name, qf, qs, ctx)
            out["lucid"].append({"test": test, "timeframe": tf_lab(tf), "period": label, "scheme": name, **lr})
            if label == "2016-2026":
                out["curves"][name] = eqs
        if label == "2016-2026":
            out["days"] = [d[0] for d in days]
            out["trades"] = [[fmt_ct(b.cabs[r["entry_i"]]), fmt_ct(b.cabs[r["exit_i"]]), r["side"], r["entry_px"],
                              r["exit_px"], r["net_usd"], r["mae_usd"], r["mfe_usd"], r["bars_held"]] for r in rows]
    return out


COLORS = ["#2563eb", "#d97706", "#059669", "#db2777", "#7c3aed", "#0891b2", "#65a30d", "#dc2626"]


def svg(days, series, title, sub, path):
    W, L, R, TOP, MID, BOT = 1000, 80, 20, 60, 360, 500
    H = 560
    allv = [v for s in series.values() for v in s] + [ACCOUNT]
    lo, hi = min(allv), max(allv)
    pad = (hi - lo) * 0.05 or 1
    lo, hi = lo - pad, hi + pad
    dds = {}
    for lab, s in series.items():
        pk, dd = s[0], []
        for v in s:
            pk = max(pk, v)
            dd.append(v - pk)
        dds[lab] = dd
    dlo = min(min(d) for d in dds.values()) or -1
    d0, span = days[0], (days[-1] - days[0]) or 1
    x = lambda d: L + (d - d0) / span * (W - L - R)
    y = lambda v: MID - (v - lo) / (hi - lo) * (MID - TOP)
    yd = lambda v: MID + 25 + v / dlo * (BOT - MID - 25)
    money = lambda v: f"-${abs(v):,.0f}" if v < 0 else f"${v:,.0f}"
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
         f'font-family="Segoe UI, Arial, sans-serif" font-size="12"><rect width="{W}" height="{H}" fill="#fff"/>',
         f'<text x="{L}" y="22" font-size="16" font-weight="600">{title}</text>',
         f'<text x="{L}" y="40" fill="#555">{sub}</text>']
    for j in range(7):
        v = lo + (hi - lo) * j / 6
        o.append(f'<line x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="#eee"/>'
                 f'<text x="{L - 6}" y="{y(v) + 4:.1f}" text-anchor="end" fill="#555">{money(v)}</text>')
    o.append(f'<line x1="{L}" x2="{W - R}" y1="{y(ACCOUNT):.1f}" y2="{y(ACCOUNT):.1f}" stroke="#999" stroke-dasharray="4 4"/>')
    for j in range(3):
        v = dlo * j / 2
        o.append(f'<text x="{L - 6}" y="{yd(v) + 4:.1f}" text-anchor="end" fill="#555">{money(v)}</text>')
    o.append(f'<text x="{L}" y="{MID + 18}" fill="#555">Drawdown from peak</text>')
    for yr in range(date.fromordinal(d0).year, date.fromordinal(days[-1]).year + 1):
        d = date(yr, 1, 1).toordinal()
        if d0 <= d <= days[-1]:
            o.append(f'<line x1="{x(d):.1f}" x2="{x(d):.1f}" y1="{TOP}" y2="{BOT}" stroke="#f3f4f6"/>'
                     f'<text x="{x(d):.1f}" y="{BOT + 18}" text-anchor="middle" fill="#555">{yr}</text>')
    n = len(days)
    st = max(1, n // 1500)
    for k, (lab, s) in enumerate(series.items()):
        c = COLORS[k % len(COLORS)]
        pts = " ".join(f"{x(days[i]):.1f},{y(s[i]):.1f}" for i in range(0, n, st))
        o.append(f'<polyline points="{pts}" fill="none" stroke="{c}" stroke-width="1.4"/>')
        dp = " ".join(f"{x(days[i]):.1f},{yd(dds[lab][i]):.1f}" for i in range(0, n, st))
        o.append(f'<polyline points="{dp}" fill="none" stroke="{c}" stroke-width="1"/>')
        lx, ly = L + 10 + (k % 3) * 300, TOP + 14 + (k // 3) * 16
        o.append(f'<rect x="{lx}" y="{ly - 8}" width="12" height="3" fill="{c}"/>'
                 f'<text x="{lx + 16}" y="{ly - 3}">{lab}: {money(s[-1] - ACCOUNT)}</text>')
    o.append("</svg>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(o))


def write_csv(path, rows):
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


TITLES = {"A_lucid": "A: original, LucidPro rules (flat 15:40 CT, back in 17:00)",
          "B_overnight": "B: original, held overnight (overnight rule ignored)",
          "C_improved": "C: improved (0.6/0.4 thresholds, ATR slope), LucidPro rules",
          "C_improved_overnight": "C': improved, held overnight"}

if __name__ == "__main__":
    for sub in ("equity", "trades", "daily"):
        os.makedirs(os.path.join(OUT, sub), exist_ok=True)
    jobs = [(t, tf) for t, (_, tfs, _) in TESTS.items() for tf in tfs]
    with Pool(8) as pool:
        results = pool.map(job, jobs)
    stats = [r for res in results for r in res["stats"]]
    schemes = [r for res in results for r in res["schemes"]]
    lucids = [r for res in results for r in res["lucid"]]
    write_csv(os.path.join(OUT, "stats.csv"), stats)
    write_csv(os.path.join(OUT, "schemes.csv"), schemes)
    write_csv(os.path.join(OUT, "lucid.csv"), lucids)
    gallery = []
    keep = ["1 MNQ", "2 MNQ", "3 MNQ", "4 MNQ", "Vol target 1-4", "Equity curve 1/2"]
    for res in results:
        run = f"{res['test']}_{res['tf']}"
        with open(os.path.join(OUT, "trades", f"{run}.csv"), "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["entry_bar_ct", "exit_bar_ct", "side", "entry_px", "exit_px", "net_usd_1mnq",
                        "mae_usd", "mfe_usd", "bars_held"])
            w.writerows(res["trades"])
        cur = {k: v for k, v in res["curves"].items()}
        with open(os.path.join(OUT, "daily", f"{run}.csv"), "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["date"] + list(cur))
            for i, d in enumerate(res["days"]):
                w.writerow([date.fromordinal(d).isoformat()] + [round(v[i], 2) for v in cur.values()])
        if res["test"] in TITLES:
            s1 = next(s for s in res["schemes"] if s["period"] == "2016-2026" and s["scheme"] == "1 MNQ")
            l1 = next(s for s in res["lucid"] if s["period"] == "2016-2026" and s["scheme"] == "1 MNQ")
            sub = (f"NQ as MNQ ($2/pt), 2016-01 to 2026-09, $0.75/side + 1 tick | 1 MNQ: PF {s1['profit_factor'] or 0:.2f}, "
                   f"Lucid pass {l1['evaluation_pass_rate_pct']:.0f}%")
            svg(res["days"], {k: cur[k] for k in keep}, f"S08 {res['tf']}, {TITLES[res['test']]}", sub,
                os.path.join(OUT, "equity", f"{run}.svg"))
            gallery.append((f"{run}.svg", f"{TITLES[res['test']]}, {res['tf']}"))
    for tf in ("1h", "4h", "daily"):
        series, days = {}, None
        for res in results:
            if res["tf"] == tf and res["test"] != "B_overnight" and res["test"] != "C_improved_overnight":
                series[res["test"]] = res["curves"]["1 MNQ"]
                days = days or res["days"]
        svg(days, series, f"S08 {tf}, 1 MNQ, LucidPro rules: each improvement on its own",
            "A = original; C1 thresholds 0.6/0.4; C2 ATR slope; C3 RTH entries; C = C1+C2; C4 = C+C3",
            os.path.join(OUT, "equity", f"ablation_{tf}.svg"))
        gallery.append((f"ablation_{tf}.svg", f"Improvements one at a time, {tf}"))
    gallery_html(os.path.join(OUT, "equity"), gallery, "S08 Forecast-to-Fill: three tests")
    with open(os.path.join(OUT, "summary.json"), "w") as fh:
        json.dump({"tests": {k: {"params": v[0], "timeframes": [tf_lab(t) for t in v[1]]} for k, v in TESTS.items()},
                   "commission_per_side": COMMISSION, "slippage_ticks_per_side": SLIP_TICKS,
                   "contract": "MNQ on NQ data ($2/pt, tick 0.25 = $0.50; 1 MNQ = 0.1 NQ)",
                   "scheme_notes": SCHEME_NOTES, "periods": PERIODS}, fh, indent=1)
    print("done ->", OUT)
