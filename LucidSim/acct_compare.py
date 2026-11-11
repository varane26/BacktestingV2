"""LucidPro 50K vs 100K on the same 1-contract day paths (whole window from 2016). Run only when the
user asks for a 100K benchmark; the standard report stays on 50K.

Usage: python -I LucidSim/acct_compare.py S08 60 [--symbol NQ] [key=value ...]
Prints a markdown table: pass rate, pass within 45 days, median days to pass, payout rate,
funded breach rate and expected trader payout per evaluation, at 1-4 contracts (50K) and 1-4, 6 (100K).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "BacktestEngine"))

from data import load, eth_session  # noqa: E402
from metrics import analyze  # noqa: E402
from propsim import simulate, RULES, RULES_100K  # noqa: E402
from run_all import PARAMS, START, SPECS, COMMISSION, SLIP_TICKS  # noqa: E402
from strategies import STRATEGIES  # noqa: E402


def main():
    args = sys.argv[1:]
    key, tf = args[0], int(args[1])
    sym = "NQ"
    over = {}
    rest = args[2:]
    while rest:
        a = rest.pop(0)
        if a == "--symbol":
            sym = rest.pop(0)
        else:
            k, v = a.split("=", 1)
            try:
                over[k] = float(v)
            except ValueError:
                over[k] = v
    b = eth_session(load(sym))
    i0 = next(i for i in range(b.n) if b.day[i] >= START.toordinal())
    p = dict(PARAMS[sym])
    p.update(over)
    eng = STRATEGIES[key][1](b, tf, i0, b.n, p)
    spec = SPECS[sym]
    st, days, _ = analyze(b, eng.trades, i0, spec["pv"], spec["tick"], COMMISSION, SLIP_TICKS, 1, 50000, b.n)
    print(f"{key} {sym} {tf}m {over}: 1 {spec['contract']} PF {st['profit_factor']:.2f}, net ${st['net_profit']:,.0f}")
    print("| Account | Contracts | Pass % | <=45d % | Median days | Payout % of evals | Funded breach % | Exp $/eval |")
    print("|---|---|---|---|---|---|---|---|")
    for name, r, sizes in (("50K", RULES, (1, 2, 3, 4)), ("100K", RULES_100K, (1, 2, 3, 4, 6))):
        for n in sizes:
            f = lambda bal, n=n: n
            f.label = f"{n} ct"
            lp = simulate(days, r=r, sizing=f)
            md = lp["median_days_to_pass"]
            print(f"| {name} | {n} | {lp['evaluation_pass_rate_pct']:.1f} | {lp['pass_within_45_days_pct']:.1f} | "
                  f"{'-' if md is None else round(md)} | {lp['payout_rate_pct_of_evaluations']:.1f} | "
                  f"{lp['funded_breach_rate_pct_of_passed'] or 0:.0f} | ${lp['expected_trader_payout_per_evaluation']:,.0f} |")


if __name__ == "__main__":
    main()
