"""Standard sizing rules for the LucidPro reports.

A rule is rule(session_day, balance, ctx) -> contracts (0 = skip the trade). It is asked when a trade
opens, so a position keeps its size until it exits.
- "fixed":   N contracts.
- "balance": depends on the balance only. Account stats use the account's closed balance; the Lucid
             sim applies the same rule to the evaluation / funded balance.
- "market":  depends on what was known at that session's open (NQ trend / range, the strategy's own
             1-contract equity). The Lucid sim replays the day paths at the sizes actually traded.
"""

ACCOUNT = 50000.0


def _fixed(n):
    return lambda sday, bal, ctx: n


SCHEMES = [
    # name, kind, rule, description
    ("1->2 at +$2.5k", "balance", lambda s, bal, ctx: 2 if bal >= ACCOUNT + 2500 else 1,
     "1 contract, 2 once the balance is $2,500 up"),
    ("1->4, +1 per +$1k", "balance", lambda s, bal, ctx: max(1, min(4, 1 + int((bal - ACCOUNT) // 1000))),
     "one more contract per $1,000 of profit, 1 to 4"),
    ("2, 1 below start", "balance", lambda s, bal, ctx: 2 if bal >= ACCOUNT else 1,
     "2 contracts, 1 while the balance is below its start"),
    ("Trend 1/2", "market", lambda s, bal, ctx: 2 if ctx["uptrend"].get(s, False) else 1,
     "2 when the market closed above its 50-session average the session before"),
    ("Calm vol 1/2", "market", lambda s, bal, ctx: 2 if ctx["calm"].get(s, False) else 1,
     "2 when the 20-session average range is below its 1-year median"),
    ("Vol target 1-4", "market", lambda s, bal, ctx: ctx["voltarget"].get(s, 1),
     "round(2 x 1-year median range / 20-session range), 1 to 4 (volatility targeting in points)"),
    ("Equity curve 1/2", "market", lambda s, bal, ctx: 2 if ctx["eq_up"].get(s, False) else 1,
     "2 when the strategy's 1-contract equity is above its 20-session average"),
    ("Bench 0/1", "market", lambda s, bal, ctx: 1 if ctx["eq_up"].get(s, False) else 0,
     "1 contract only while the 1-contract equity is above its 20-session average, else no trades"),
]


def sizings(sizes, scheme_names):
    """[(label, kind, rule, description)] for the fixed sizes and the chosen schemes."""
    out = [(f"{n} ct", "fixed", _fixed(n), f"{n} contract{'s' if n > 1 else ''} on every trade") for n in sizes]
    out += [s for s in SCHEMES if scheme_names is None or s[0] in scheme_names]
    return out


def market_flags(b):
    """Per session day (17:00-16:00 CT), known at that session's open: uptrend, calm, voltarget.
    Ranges are in points, so the back-adjusted prices do not distort them."""
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
    up, calm, vt = {}, {}, {}
    for j, k in enumerate(keys):
        if j >= 50:
            up[k] = closes[j - 1] > sum(closes[j - 50:j]) / 50
        if j >= 270:
            a20 = sum(rng[j - 20:j]) / 20
            med = sorted(sum(rng[m - 20:m]) / 20 for m in range(j - 250, j))[125]
            calm[k] = a20 < med
            vt[k] = max(1, min(4, round(2 * med / a20))) if a20 > 0 else 1
    return {"uptrend": up, "calm": calm, "voltarget": vt}


def context(flags, days1):
    """flags + eq_up from the 1-contract day records (session_day, sod, events, min_rest, eod)."""
    eq, cum = [], 0.0
    for d in days1:
        eq.append(cum)
        cum += d[4]
    eq_up = {d[0]: k >= 20 and eq[k] > sum(eq[k - 20:k]) / 20 for k, d in enumerate(days1)}
    return {**flags, "eq_up": eq_up}
