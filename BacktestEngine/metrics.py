"""Account-level statistics from a strategy's trades, on a 1-minute mark-to-market equity curve.

analyze() returns the user's report fields (initial_cash ... average_holding_bars), the
per-trading-day paths that propsim.py replays, and per-trade rows with MAE / MFE (worst and
best open P&L in $ while the trade was on, from 1-minute highs and lows). A trading day is the CME session that ends
at 16:00 CT (bars after 16:00 belong to the next day). Costs are booked at the exit.
"""
import math
import statistics
from datetime import date

from engine import MKT, STOP, LIMIT


def analyze(b, trades, i_from, pv, tick, comm, slip_ticks, qty, initial, i_to=None):
    """qty: contracts per trade, or a callable (entry bar index, closed balance) -> contracts that
    is asked when each trade opens (0 = skip the trade). i_to: stop at this bar (trades still open
    there are followed to their exit)."""
    O, H, L, C, T, D = b.o, b.h, b.l, b.c, b.hhmm, b.day
    slip = slip_ticks * tick * pv
    tl = []
    for ei, xi, side, epx, xpx, ek, xk, el, xl in trades:
        cost = 2 * comm + (slip if ek != LIMIT else 0) + (slip if xk != LIMIT else 0)
        tl.append((ei, xi, side, epx, xpx, xk, side * (xpx - epx) * pv - cost))
    sized = callable(qty)
    done = []                  # trades taken: (ei, xi, side, epx, xpx, xk, net, unit)

    def start(t, bal):
        q = qty(t[0], bal) if sized else qty
        if q <= 0:
            return None
        tr = t[:6] + (t[6] * q, pv * q)
        done.append(tr)
        return tr

    realized = float(initial)
    eq = float(initial)
    peak = float(initial)
    peak_i = i_from
    max_dd = max_dd_pct = 0.0
    max_dd_dur = 0
    max_dd_days = 0
    peak_day = 0
    wiped = False
    days = []                  # (session_day, sod_equity, events, min_rest_rel, eod_rel)
    eod_eq = []
    cur_day = None
    sod = float(initial)
    events = []
    min_since = 0.0
    k = 0
    cur = None
    mae = mfe = 0.0
    excursions = {}

    def exit_worst(tr, i, o, h, l):
        """Equity at the worst price the open trade saw on its exit bar, before it closed."""
        side, epx, xpx, xk = tr[2], tr[3], tr[4], tr[5]
        if xk == MKT:
            px = o
        elif xk == STOP:
            px = xpx
        else:
            high_first = h - o <= o - l
            if side == 1:
                px = o if high_first else l
            else:
                px = h if high_first else o
        return side * (px - epx) * tr[7]

    end = b.n
    if i_to is not None:
        end = min(b.n, max([i_to] + [t[1] + 1 for t in tl if t[0] < i_to]))
    for i in range(i_from, end):
        t = T[i]
        sday = D[i] + 1 if t > 1600 else D[i]
        if sday != cur_day:
            if cur_day is not None:
                days.append((cur_day, sod, events, min_since, eq - sod))
                eod_eq.append(eq)
            cur_day = sday
            sod = eq
            events = []
            min_since = 0.0
        o, h, l, c = O[i], H[i], L[i], C[i]
        worst = None
        if cur is not None and cur[1] == i:
            w = realized + exit_worst(cur, i, o, h, l)
            worst = w
            mae = min(mae, w - realized)
            mfe = max(mfe, cur[2] * (cur[4] - cur[3]) * cur[7])
            excursions[cur[0]] = (mae, mfe)
            realized += cur[6]
            min_since = min(min_since, w - sod, realized - sod)
            events.append((min_since, realized - sod))
            min_since = 0.0
            cur = None
        while k < len(tl) and tl[k][0] < i:
            k += 1
        if cur is None and k < len(tl) and tl[k][0] == i:
            cur = start(tl[k], realized)
            k += 1
        if cur is not None and cur[0] == i:
            mae = mfe = 0.0
            if cur[1] == i:
                w = realized + exit_worst(cur, i, o, h, l)
                worst = w if worst is None else min(worst, w)
                mae = min(mae, w - realized)
                mfe = max(mfe, cur[2] * (cur[4] - cur[3]) * cur[7])
                excursions[cur[0]] = (mae, mfe)
                realized += cur[6]
                min_since = min(min_since, w - sod, realized - sod)
                events.append((min_since, realized - sod))
                min_since = 0.0
                cur = None
        if cur is not None:
            side, epx = cur[2], cur[3]
            adverse = l if side == 1 else h
            w = realized + side * (adverse - epx) * cur[7]
            eq = realized + side * (c - epx) * cur[7]
            mae = min(mae, w - realized)
            mfe = max(mfe, side * ((h if side == 1 else l) - epx) * cur[7])
            min_since = min(min_since, w - sod, eq - sod)
        else:
            eq = realized
            min_since = min(min_since, eq - sod)
        if eq >= peak:
            peak = eq
            peak_i = i
            peak_day = len(days)
        else:
            dd = peak - eq
            if dd > max_dd:
                max_dd = dd
            if peak > 0 and dd / peak > max_dd_pct:
                max_dd_pct = dd / peak
            if i - peak_i > max_dd_dur:
                max_dd_dur = i - peak_i
                max_dd_days = len(days) - peak_day + 1
            if eq <= 0:
                wiped = True
    if cur_day is not None:
        days.append((cur_day, sod, events, min_since, eq - sod))
        eod_eq.append(eq)

    nets = [x[6] for x in done]
    final = eq
    years = (days[-1][0] - days[0][0]) / 365.25 if len(days) > 1 else 0
    rets = []
    prev = float(initial)
    for e in eod_eq:
        rets.append(e / prev - 1 if prev > 0 else 0.0)
        prev = e
    mean_r = statistics.fmean(rets) if rets else 0.0
    sd_r = statistics.stdev(rets) if len(rets) > 1 else 0.0
    down = math.sqrt(sum(min(r, 0.0) ** 2 for r in rets) / len(rets)) if rets else 0.0
    cagr = ((final / initial) ** (1 / years) - 1) if years > 0 and final > 0 else None
    if wiped:                  # equity hit $0: return-based ratios are meaningless
        cagr = None
        sd_r = down = 0.0
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x <= 0]
    gp, gl = sum(wins), -sum(losses)
    streak_w = streak_l = best_w = best_l = 0
    for x in nets:
        if x > 0:
            streak_w += 1
            streak_l = 0
        else:
            streak_l += 1
            streak_w = 0
        best_w = max(best_w, streak_w)
        best_l = max(best_l, streak_l)
    avg_w = gp / len(wins) if wins else 0.0
    avg_l = -gl / len(losses) if losses else 0.0
    n = len(nets)
    stats = {
        "initial_cash": initial,
        "final_equity": final,
        "net_profit": final - initial,
        "total_return_pct": 100 * (final / initial - 1),
        "cagr_pct": 100 * cagr if cagr is not None else None,
        "annualized_volatility_pct": None if wiped else 100 * sd_r * math.sqrt(252),
        "sharpe_ratio": mean_r / sd_r * math.sqrt(252) if sd_r > 0 else None,
        "sortino_ratio": mean_r / down * math.sqrt(252) if down > 0 else None,
        "account_wiped_out": wiped,
        "max_drawdown": -max_dd if max_dd else 0.0,
        "max_drawdown_pct": -100 * max_dd_pct,
        "max_drawdown_duration_bars": max_dd_dur,
        "max_drawdown_duration_trading_days": max_dd_days,
        "calmar_ratio": (100 * cagr) / (100 * max_dd_pct) if cagr is not None and max_dd_pct > 0 else None,
        "trade_count": n,
        "win_rate_pct": 100 * len(wins) / n if n else None,
        "profit_factor": gp / gl if gl > 0 else None,
        "average_winner": avg_w,
        "average_loser": avg_l,
        "payoff_ratio": avg_w / -avg_l if avg_l < 0 else None,
        "recovery_factor": (final - initial) / max_dd if max_dd > 0 else None,
        "max_consecutive_wins": best_w,
        "max_consecutive_losses": best_l,
        "expectancy_per_trade": sum(nets) / n if n else None,
        "average_trade": sum(nets) / n if n else None,
        "median_trade": statistics.median(nets) if n else None,
        "gross_profit": gp,
        "gross_loss": gl,
        "best_trade": max(nets) if n else None,
        "worst_trade": min(nets) if n else None,
        "average_holding_bars": statistics.fmean(x[1] - x[0] for x in done) if n else None,
        "trading_days": len(days),
        "first_day": date.fromordinal(days[0][0]).isoformat() if days else None,
        "last_day": date.fromordinal(days[-1][0]).isoformat() if days else None,
    }
    rows = [{"entry_i": x[0], "exit_i": x[1], "side": "long" if x[2] == 1 else "short",
             "entry_px": x[3], "exit_px": x[4], "net_usd": round(x[6], 2),
             "mae_usd": round(excursions.get(x[0], (0.0, 0.0))[0], 2),
             "mfe_usd": round(excursions.get(x[0], (0.0, 0.0))[1], 2),
             "bars_held": x[1] - x[0], "contracts": round(x[7] / pv)} for x in done]
    return stats, days, rows
