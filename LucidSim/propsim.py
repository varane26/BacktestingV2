"""Monte Carlo of a LucidPro 50K account (daily loss limit OFF): evaluation, then funded payouts.

Rules, from Lucid's help center (checked 2026-10-29):
- Evaluation: profit target $3,000; max loss limit (MLL) $2,000, end-of-day trailing from the
  highest closing balance, locked at $50,100 once a close exceeds $52,100; no consistency rule;
  no DLL (purchase option off); up to 40 micros.
- Funded: same MLL; 90% of payouts to the trader; each payout cycle needs >= $500 profit and
  a largest day <= 40% of the cycle's profit; balance above the $52,100 buffer is withdrawable;
  minimum request $500; maximum $2,000 for payout 1 and $2,500 after; no day-count rule.

Modelling choices:
- The MLL level only moves at the end of a day, but a breach is checked intraday on every
  1-minute bar's worst price.
- The target counts as reached when the closed balance hits $53,000 after a trade; the funded
  account starts on the next trading day.
- Payout requests (checked against Lucid's help center "LucidPro Payouts", 2026-11-08): cycle profit >= $500, largest
  day <= 40% of the cycle profit, payout only from balance above the $52,100 buffer, $500 minimum, $2,000 maximum for
  payout 1 and $2,500 for payouts 2+; every condition resets after a payout. PAYOUT_MODE "full" (default from
  2026-11-08, the user's rule): request only the full $2,000 / $2,500, i.e. once the balance is >= $54,100 / $54,600
  with the cycle rules met. "first" (before 2026-11-08): take the largest allowed amount on the first eligible day,
  often only $500-1,500, which made "days to first payout" look shorter.
- Sizing: `days` are the 1-contract paths; `sizing` = a callable balance -> contracts, or
  (base_qty, scaled_qty, balance), which trades
  base_qty until the start-of-day balance reaches `balance`, then scaled_qty (e.g. (1, 2, 52500):
  1 MNQ until $52,500, then 2 MNQ), in the evaluation and again in the funded account.
- Paths: 20-trading-day blocks drawn at random from the strategy's own day-by-day history
  (block bootstrap). 1,000 paths, fixed seed. An evaluation that has neither passed nor failed
  after 504 trading days (2 years) counts as unresolved. A funded account runs for up to
  252 trading days (1 year) after the pass.
"""
import random
import statistics

RULES = {
    "provider": "LucidPro",
    "account_size": 50000,
    "profit_target": 3000,
    "max_loss": 2000,
    "trail_lock_trigger": 52100,
    "trail_lock_level": 50100,
    "split": 0.90,
    "cycle_min_profit": 500,
    "consistency": 0.40,
    "buffer": 52100,
    "min_payout": 500,
    "payout_caps": (2000, 2500),
}
# LucidPro 100K (tradetanto.com rules summary, checked 2026-11-01): $6,000 target, $3,000 EOD trailing MLL
# locking at $100,100, payout cycle >= $750, caps $2,500 then $3,000, up to 60 micros.
RULES_100K = {**RULES, "account_size": 100000, "profit_target": 6000, "max_loss": 3000,
              "trail_lock_trigger": 103100, "trail_lock_level": 100100, "cycle_min_profit": 750,
              "buffer": 103100, "payout_caps": (2500, 3000)}
N_SIMS = 1000
BLOCK = 20
EVAL_MAX_DAYS = 504
FUNDED_DAYS = 252
SEED = int(__import__("os").environ.get("LUCID_SEED", 20261029))   # LUCID_SEED env: noise checks
PAYOUT_MODE = "full"


def _path(pool, rng, length):
    n = len(pool)
    out = []
    while len(out) < length:
        s = rng.randrange(n)
        out.extend(pool[(s + j) % n] for j in range(BLOCK))
    return out[:length]


def _mll(peak, r):
    return min(peak - r["max_loss"], r["trail_lock_level"])


def _qty(bal, sizing):
    """sizing: None (1, or paths already scaled), a callable bal -> contracts, or
    (base_qty, scaled_qty, balance)."""
    if sizing is None:
        return 1
    if callable(sizing):
        return sizing(bal)
    return sizing[1] if bal >= sizing[2] else sizing[0]


def _label(sizing):
    if sizing is None:
        return "fixed"
    if callable(sizing):
        return getattr(sizing, "label", "custom")
    return f"{sizing[0]} then {sizing[1]} from ${sizing[2]:,}"


def _evaluation(path, r, sizing=None):
    """Returns ('pass' | 'fail' | 'open', trading days used)."""
    bal = peak = float(r["account_size"])
    target = r["account_size"] + r["profit_target"]
    mll = _mll(peak, r)
    for d, (events, min_rest, eod) in enumerate(path, 1):
        q = _qty(bal, sizing)
        min_rest *= q
        eod *= q
        for min_rel, real_rel in events:
            min_rel *= q
            real_rel *= q
            if bal + min_rel <= mll:
                return "fail", d
            if bal + real_rel >= target:
                return "pass", d
        if bal + min_rest <= mll:
            return "fail", d
        bal += eod
        if bal > peak:
            peak = bal
            mll = max(mll, _mll(peak, r))
    return "open", len(path)


def _funded(path, r, sizing=None):
    """Returns (payout amounts, day of first payout or None, breached, days survived)."""
    bal = peak = float(r["account_size"])
    mll = _mll(peak, r)
    cycle_start = bal
    best_day = 0.0
    payouts = []
    first = None
    for d, (events, min_rest, eod) in enumerate(path, 1):
        q = _qty(bal, sizing)
        min_rest *= q
        eod *= q
        for min_rel, _ in events:
            if bal + min_rel * q <= mll:
                return payouts, first, True, d
        if bal + min_rest <= mll:
            return payouts, first, True, d
        bal += eod
        if bal > peak:
            peak = bal
            mll = max(mll, _mll(peak, r))
        best_day = max(best_day, eod)
        profit = bal - cycle_start
        room = bal - r["buffer"]
        cap = r["payout_caps"][0 if not payouts else 1]
        if PAYOUT_MODE == "full":
            need = cap
        elif PAYOUT_MODE == "half":                    # request 50% of the cap ($1,000, then $1,250)
            need = 0.5 * cap
        else:                                          # "first" (largest allowed) and "min" (always $500)
            need = r["min_payout"]
        if (profit >= r["cycle_min_profit"] and best_day <= r["consistency"] * profit
                and room >= need):
            amt = need if PAYOUT_MODE in ("half", "min") else min(cap, room)
            bal -= amt
            payouts.append(amt)
            if first is None:
                first = d
            cycle_start = bal
            best_day = 0.0
    return payouts, first, False, len(path)


def simulate(days, r=RULES, sizing=None, n_sims=N_SIMS, funded_sizing="same"):
    """sizing: None (paths as given), a callable balance -> contracts, or (base_qty, scaled_qty,
    balance); see module doc.
    funded_sizing: "same" = use `sizing` in the funded account too, or its own None / tuple
    (e.g. pass the evaluation with (3, 3, 0) and trade the funded account with (1, 1, 0))."""
    fsz = sizing if funded_sizing == "same" else funded_sizing
    pool = [(ev, mr, eod) for _, _, ev, mr, eod in days]
    rng = random.Random(SEED)
    passed, failed, open_ = [], 0, 0
    funded = []
    for _ in range(n_sims):
        path = _path(pool, rng, EVAL_MAX_DAYS + FUNDED_DAYS)
        res, d = _evaluation(path[:EVAL_MAX_DAYS], r, sizing)
        if res == "fail":
            failed += 1
            continue
        if res == "open":
            open_ += 1
            continue
        passed.append(d)
        funded.append((d,) + _funded(path[d:d + FUNDED_DAYS], r, fsz))
    n_pass = len(passed)
    paid = [f for f in funded if f[1]]
    trader = [r["split"] * sum(f[1]) for f in funded]
    trader_paid = [r["split"] * sum(f[1]) for f in paid]

    def mean(xs):
        return statistics.fmean(xs) if xs else None

    return {
        "provider": r["provider"],
        "account_size": r["account_size"],
        "daily_loss_limit_assumption": "off",
        "drawdown_model": "end-of-day trailing max loss $2,000, locking at starting balance + $100 "
                          "once a close exceeds $52,100; breach checked intraday on 1-minute bars",
        "evaluation_profit_target": r["profit_target"],
        "evaluation_max_loss_limit": r["max_loss"],
        "evaluation_consistency_limit_pct": None,
        "sizing": _label(sizing),
        "funded_sizing": "same" if funded_sizing == "same" else _label(fsz),
        "simulations": n_sims,
        "evaluation_pass_rate_pct": 100.0 * n_pass / n_sims,
        "pass_within_10_days_pct": 100.0 * sum(1 for x in passed if x <= 10) / n_sims,
        "pass_within_15_days_pct": 100.0 * sum(1 for x in passed if x <= 15) / n_sims,
        "pass_within_20_days_pct": 100.0 * sum(1 for x in passed if x <= 20) / n_sims,
        "pass_within_30_days_pct": 100.0 * sum(1 for x in passed if x <= 30) / n_sims,
        "pass_within_45_days_pct": 100.0 * sum(1 for x in passed if x <= 45) / n_sims,
        "pass_within_60_days_pct": 100.0 * sum(1 for x in passed if x <= 60) / n_sims,
        "evaluation_passed_simulations": n_pass,
        "evaluation_failed_simulations": failed,
        "evaluation_unresolved_simulations": open_,
        "mean_days_to_pass": mean(passed),
        "median_days_to_pass": statistics.median(passed) if passed else None,
        "payout_rate_pct_of_evaluations": 100.0 * len(paid) / n_sims,
        "payout_rate_pct_of_passed_evaluations": 100.0 * len(paid) / n_pass if n_pass else None,
        "mean_payouts_per_passed_evaluation": mean([len(f[1]) for f in funded]),
        "mean_trader_payout_per_passed_evaluation": mean(trader),
        "mean_trader_payout_when_eligible": mean(trader_paid),
        "mean_days_to_first_payout_when_eligible": mean([f[0] + f[2] for f in paid]),
        "mean_funded_days_to_first_payout": mean([f[2] for f in paid]),
        "funded_breach_rate_pct_of_passed": 100.0 * sum(1 for f in funded if f[3]) / n_pass if n_pass else None,
        "mean_funded_days_survived": mean([f[4] for f in funded]),
        "expected_trader_payout_per_evaluation": (n_pass / n_sims) * (mean(trader) or 0.0),
        "payout_split_pct_to_trader": 100 * r["split"],
        "payout_request_mode": PAYOUT_MODE,
        "profitable_days_required_per_payout": 0,
        "funded_consistency_limit_pct": 100 * r["consistency"],
        "payout_cycle_min_profit": r["cycle_min_profit"],
        "payout_min_request": r["min_payout"],
        "payout_caps": list(r["payout_caps"]),
        "funded_horizon_trading_days": FUNDED_DAYS,
        "evaluation_max_trading_days": EVAL_MAX_DAYS,
        "bootstrap_block_days": BLOCK,
    }
