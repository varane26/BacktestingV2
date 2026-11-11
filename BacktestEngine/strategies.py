"""The seven strategies from strategies/strategy_0N.pl, ported to the engine.

All logic runs on 1-minute bars in CT (data1). `tf` is the signal-bar size in
minutes, standing in for the strategy's own signal timeframe (data2 or the
in-code bars). Size is one contract; dollar results scale linearly with size.
Each function runs bars[i0:i1] and returns the engine.
"""
import math
from datetime import date
from engine import Engine, TFBars, hhmm, MKT, STOP, LIMIT, BUY, SHORT, XLONG, XSHORT


def s01_orb_ema_gap(b, tf, i0, i1, p):
    """Opening range 08:30-08:45 CT, long on a signal-bar close above the range high and
    EMA200 on a gap-up day; stop at the range low, target 1.5R; flat 15:40, re-enter 17:00."""
    O, H, L, C, V, T, D, CA = b.o, b.h, b.l, b.c, b.v, b.hhmm, b.day, b.cabs
    eng = Engine(CA, p["tick"])
    tfb = TFBars(tf)
    alpha = 2.0 / 201
    ema = None
    rng_hi = rng_lo = 0.0
    rng_date = None
    rth_date = None
    rth_open = last_rth_c = prev_rth_c = 0.0
    gap = 0.0
    c2 = 0.0
    ent_wait = re_wait = False
    sd_entry = stop_px = tgt_px = 0.0
    re_dir = 0
    re_stop = re_tgt = 0.0
    for i in range(i0, i1):
        o, h, l, c = O[i], H[i], L[i], C[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        t = T[i]
        d = D[i]
        if 830 < t <= 1500:
            if d != rth_date:
                prev_rth_c = last_rth_c
                rth_open = o
                rth_date = d
            last_rth_c = c
        gap_ok = rth_date == d and prev_rth_c > 0
        if gap_ok:
            gap = rth_open - prev_rth_c
        # opening range from the 1-minute bars 08:30-08:45 (same range for every tf)
        if 830 < t <= 845:
            if d != rng_date:
                rng_hi, rng_lo, rng_date = h, l, d
            else:
                if h > rng_hi:
                    rng_hi = h
                if l < rng_lo:
                    rng_lo = l
        sig = False
        closed = tfb.update(CA[i], o, h, l, c, V[i])
        if closed:
            for end, bo, bh, bl, bc, bv in closed:
                ema = bc if ema is None else ema + alpha * (bc - ema)
                c2 = bc
                t2 = hhmm(end)
                sig = (end // 1440 == rng_date and t2 > 845 and t2 <= 1535
                       and bc > rng_hi and bc > ema and gap_ok and gap >= p["gap_min"])
        lucid = 1540 <= t < 1700
        pos = eng.pos
        if ent_wait:
            if pos != 0:
                stop_px = eng.entry_px - sd_entry
                tgt_px = eng.entry_px + 1.5 * sd_entry
            ent_wait = False
        if re_wait:
            if pos != 0:
                stop_px, tgt_px = re_stop, re_tgt
            re_wait = False
        if pos != 0:
            if lucid:
                re_dir, re_stop, re_tgt = pos, stop_px, tgt_px
                eng.order(MKT, XLONG, None, "Flat")
            else:
                eng.order(STOP, XLONG, stop_px, "SL")
                eng.order(LIMIT, XLONG, tgt_px, "TP")
        if re_dir != 0 and pos == 0 and (t == 1600 or 1701 <= t < 1800):
            eng.order(MKT, BUY, None, "LR")
            eng.order(STOP, XLONG, re_stop, "LR_SL")
            eng.order(LIMIT, XLONG, re_tgt, "LR_TP")
            re_dir = 0
            re_wait = True
        if pos == 0 and re_dir == 0 and not re_wait and not lucid and sig:
            sd = c2 - rng_lo
            if sd > 0:
                sd_entry = sd
                stop_px = c2 - sd
                tgt_px = c2 + 1.5 * sd
                eng.order(MKT, BUY, None, "L")
                eng.order(STOP, XLONG, stop_px, "SL0")
                eng.order(LIMIT, XLONG, tgt_px, "TP0")
                ent_wait = True
    return eng


def s02_sma_ema_pullback(b, tf, i0, i1, p):
    """Two-leg long pullback system on signal bars (SMA414/EMA16 and SMA882/EMA1293/EMA6);
    flat 15:40, unconditional re-open at 17:00 (LucidMode 1)."""
    O, H, L, C, V, T, CA = b.o, b.h, b.l, b.c, b.v, b.hhmm, b.cabs
    eng = Engine(CA, p["tick"])
    tfb = TFBars(tf)
    n1, n2 = 414, 882
    a1, a2f, a3 = 2.0 / 17, 2.0 / 7, 2.0 / 1294
    warm = 1293
    closes = []
    sum1 = sum2 = 0.0
    nb = 0
    e1 = e2f = m3 = 0.0
    prev_low = 0.0
    leg = 0
    re_dir = 0
    for i in range(i0, i1):
        o, h, l, c = O[i], H[i], L[i], C[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        t = T[i]
        ent_ev = exit_ev = False
        closed = tfb.update(CA[i], o, h, l, c, V[i])
        if closed:
            for end, bo, bh, bl, bc, bv in closed:
                nb += 1
                closes.append(bc)
                sum1 += bc
                sum2 += bc
                if nb > n1:
                    sum1 -= closes[nb - 1 - n1]
                if nb > n2:
                    sum2 -= closes[nb - 1 - n2]
                if nb == 1:
                    e1 = e2f = m3 = bc
                else:
                    e1 += a1 * (bc - e1)
                    e2f += a2f * (bc - e2f)
                    m3 += a3 * (bc - m3)
                lower_c = nb > 1 and bc < prev_low
                b1 = nb >= n1 and bc > sum1 / n1 and bc < e1 and nb > warm
                x1 = bc > e1 and lower_c
                b2 = nb >= n2 and bc < sum2 / n2 and bc > m3 and bc < e2f and nb > warm
                x2 = bc > e2f and lower_c
                prev_leg = leg
                if leg == 1 and x1:
                    leg = 0
                elif leg == 2 and x2:
                    leg = 0
                elif leg == 0:
                    leg = 1 if b1 else (2 if b2 else 0)
                ent_ev = leg > 0 and prev_leg == 0
                exit_ev = leg == 0 and prev_leg > 0
                prev_low = bl
        pos = eng.pos
        if pos != 0 and (t < 1540 or t >= 1700):
            re_dir = 0
        if pos == 1 and closed and exit_ev:
            eng.order(MKT, XLONG, None, "LX")
        if pos == 0 and re_dir == 0 and closed and not (1540 <= t < 1600) and ent_ev:
            eng.order(MKT, BUY, None, "L")
        if pos == 1 and 1540 <= t < 1700:
            re_dir = 1
            eng.order(MKT, XLONG, None, "Flat")
        if re_dir == 1 and pos == 0 and 1600 <= t < 1759:
            eng.order(MKT, BUY, None, "Re")
    return eng


def _daily_rth_strategy(b, i0, i1, rule, stop_mult, tick):
    """Shared shell of strategies 03 and 07: RTH daily bars (08:30-15:00 CT) built on
    data1, rules evaluated on the 15:00 bar, exit at C > H[1], optional fixed stop,
    flat 15:40 and re-open at 17:00 with the same stop. `rule(state)` returns
    True for a long entry on the day just completed."""
    O, H, L, C, T, D, DW = b.o, b.h, b.l, b.c, b.hhmm, b.day, b.dow
    eng = Engine(b.cabs, tick)
    day_open = False
    rdate = rdow = None
    rh = rl = rc = 0.0
    st = {"h": [], "l": [], "c": [], "dow": [], "atr": 0.0, "n": 0}
    stop_dist = stop_px = 0.0
    re_dir = 0
    re_stop = 0.0
    re_sent = False
    prev_mp = 0
    for i in range(i0, i1):
        o, h, l, c = O[i], H[i], L[i], C[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        t = T[i]
        d = D[i]
        just_re = False
        if re_sent:
            just_re = True
            re_sent = False
            re_dir = 0
        mp = eng.pos
        if mp != 0 and prev_mp == 0:
            if just_re:
                stop_px = re_stop
            elif stop_dist > 0:
                stop_px = eng.entry_px - mp * stop_dist
            else:
                stop_px = 0.0
        is_rth = 830 < t <= 1500
        fin = None
        if day_open and (not is_rth or d != rdate):
            fin = (rdow, rh, rl, rc)
            day_open = False
        if is_rth:
            if not day_open:
                day_open = True
                rdate, rdow, rh, rl = d, DW[i], h, l
            else:
                if h > rh:
                    rh = h
                if l < rl:
                    rl = l
            rc = c
            if t == 1500 and fin is None:
                fin = (rdow, rh, rl, rc)
                day_open = False
        if fin is not None:
            fdow, fh, fl, fc = fin
            st["h"].append(fh)
            st["l"].append(fl)
            st["c"].append(fc)
            st["dow"].append(fdow)
            st["n"] += 1
            n = st["n"]
            if n == 1:
                st["atr"] = fh - fl
            else:
                pc = st["c"][-2]
                tr = max(fh - fl, abs(fh - pc), abs(fl - pc))
                st["atr"] += (tr - st["atr"]) / 14
            ent_l = rule(st)
            ex_l = n >= 2 and fc > st["h"][-2]
            stop_dist = stop_mult * st["atr"] if stop_mult > 0 else 0.0
            no_entry = 1540 <= t < 1700
            mp = eng.pos
            if mp == 1:
                if ex_l:
                    eng.order(MKT, XLONG, None, "LX")
            elif mp == 0 and re_dir == 0 and not re_sent and not no_entry and ent_l:
                eng.order(MKT, BUY, None, "L")
                if stop_dist > 0:
                    eng.order(STOP, XLONG, fc - stop_dist, "SL1")
        mp = eng.pos
        if mp == 1 and stop_px > 0:
            eng.order(STOP, XLONG, stop_px, "SL")
        if mp != 0 and 1540 <= t < 1700:
            if re_dir == 0:
                re_dir = mp
                re_stop = stop_px
            eng.order(MKT, XLONG, None, "Flat")
        if re_dir != 0 and mp == 0 and not re_sent and (t == 1600 or 1700 < t < 1800):
            eng.order(MKT, BUY, None, "Re")
            if re_stop > 0:
                eng.order(STOP, XLONG, re_stop, "ReSL")
            re_sent = True
        prev_mp = eng.pos
    return eng


def s03_monday_down(b, tf, i0, i1, p):
    """Long at Monday's RTH close after a down Monday; exit C > H[1]; stop 4 x ATR14."""
    def rule(st):
        c = st["c"]
        return st["n"] >= 2 and c[-1] < c[-2] and st["dow"][-1] == 1
    return _daily_rth_strategy(b, i0, i1, rule, 4.0, p["tick"])


def s07_macd_ibs(b, tf, i0, i1, p):
    """Long at the RTH close when (MACD hist fell 3 days and < 0 and IBS < 0.2) or IBS < 0.1;
    exit C > H[1]; no stop."""
    m = {"e12": 0.0, "e26": 0.0, "sig": 0.0, "hist": []}

    def rule(st):
        n = st["n"]
        fc, fh, fl = st["c"][-1], st["h"][-1], st["l"][-1]
        if n == 1:
            m["e12"] = m["e26"] = fc
            macd = 0.0
            m["sig"] = macd
        else:
            m["e12"] += (2.0 / 13) * (fc - m["e12"])
            m["e26"] += (2.0 / 27) * (fc - m["e26"])
            macd = m["e12"] - m["e26"]
            m["sig"] += (2.0 / 10) * (macd - m["sig"])
        hist = m["hist"]
        hist.append(macd - m["sig"])
        ibs = (fc - fl) / (fh - fl) if fh - fl > 0 else 0.5
        mo = n >= 4 and hist[-1] < 0 and hist[-4] > hist[-3] > hist[-2] > hist[-1]
        return (mo and ibs < 0.2) or ibs < 0.1
    return _daily_rth_strategy(b, i0, i1, rule, 0.0, p["tick"])


def s04_vwap_continuation(b, tf, i0, i1, p):
    """VWAP-trend pullback entries 09:30-14:30 CT on signal bars, fixed point stop/target,
    flat 14:55 CT, max 4 trades and 2 losers a day. Works in NY minutes like the original."""
    O, H, L, C, V, CA = b.o, b.h, b.l, b.c, b.v, b.cabs
    eng = Engine(CA, p["tick"])
    tfb = TFBars(tf)
    slope_bars = max(1, round(15 / tf))
    mom_bars = max(1, round(60 / tf))
    need = max(slope_bars, mom_bars)
    mom_min = p["mom_pct"] / 100.0
    l_sl, l_tp, s_sl, s_tp = p["long_stop"], p["long_tgt"], p["short_stop"], p["short_tgt"]
    cl_r = []
    vw_r = []
    n5 = 0
    cur_day = None
    cum_pv = cum_v = 0.0
    wait = 0
    trades_today = losses_today = 0
    prev_tt = 0
    sl = tp = 0.0
    for i in range(i0, i1):
        o, h, l, c = O[i], H[i], L[i], C[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        ca = CA[i]
        if len(eng.trades) != prev_tt:
            tr = eng.trades[-1]
            trades_today += 1
            if tr[2] * (tr[4] - tr[3]) < 0:
                losses_today += 1
            prev_tt = len(eng.trades)
        ny = (ca + 60) % 1440
        day_ny = (ca + 60) // 1440
        if eng.pos == 1 and 955 <= ny < 1080:
            eng.order(MKT, XLONG, None, "EOD")
        elif eng.pos == -1 and 955 <= ny < 1080:
            eng.order(MKT, XSHORT, None, "EOD")
        go = 0
        closed = tfb.update(ca, o, h, l, c, V[i])
        if closed:
            for end, bo, bh, bl, bc, bv in closed:
                c5 = (end + 60) % 1440
                if day_ny != cur_day:
                    cur_day = day_ny
                    cum_pv = cum_v = 0.0
                    trades_today = losses_today = 0
                    wait = 0
                if 570 <= c5 <= 960:
                    cum_pv += (bh + bl + bc) / 3.0 * bv
                    cum_v += bv
                vw = cum_pv / cum_v if cum_v > 0 else bc
                cl_r.append(bc)
                vw_r.append(vw)
                lb = sb = False
                if n5 >= need:
                    vb = vw_r[n5 - slope_bars]
                    cb = cl_r[n5 - mom_bars]
                    if cb > 0:
                        mom = bc / cb - 1
                        lb = bc > vw and vw > vb and mom >= mom_min
                        sb = bc < vw and vw < vb and mom <= -mom_min
                if (630 <= c5 < 930 and eng.pos == 0 and trades_today < 4
                        and losses_today < 2):
                    if wait == 0:
                        if lb:
                            wait = 1
                        elif sb:
                            wait = -1
                    elif wait == 1:
                        if not lb:
                            wait = -1 if sb else 0
                        elif bc < bo:
                            go = 1
                    else:
                        if not sb:
                            wait = 1 if lb else 0
                        elif bc > bo:
                            go = -1
                n5 += 1
        if go == 1:
            wait = 0
            sl, tp = l_sl, l_tp
            eng.order(MKT, BUY, None, "L", attach=(sl, tp))
        elif go == -1:
            wait = 0
            sl, tp = s_sl, s_tp
            eng.order(MKT, SHORT, None, "S", attach=(sl, tp))
        if eng.pos == 1:
            eng.order(STOP, XLONG, eng.entry_px - sl, "SL")
            eng.order(LIMIT, XLONG, eng.entry_px + tp, "TP")
        elif eng.pos == -1:
            eng.order(STOP, XSHORT, eng.entry_px + sl, "SL")
            eng.order(LIMIT, XSHORT, eng.entry_px - tp, "TP")
    return eng


def s05_overnight_long(b, tf, i0, i1, p):
    """Mon-Wed: if the signal bar closing 16:00 CT closes below EMA200 of signal bars,
    buy the 17:00 reopen and sell the 08:30 CT open."""
    O, H, L, C, V, T, DW, CA = b.o, b.h, b.l, b.c, b.v, b.hhmm, b.dow, b.cabs
    eng = Engine(CA, p["tick"])
    tfb = TFBars(tf)
    alpha = 2.0 / 201
    ema = None
    nb2 = 0
    t2 = -1
    c5 = 0.0
    for i in range(i0, i1):
        o, h, l, c = O[i], H[i], L[i], C[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        t = T[i]
        closed = tfb.update(CA[i], o, h, l, c, V[i])
        if closed:
            for end, bo, bh, bl, bc, bv in closed:
                nb2 += 1
                ema = bc if ema is None else ema + alpha * (bc - ema)
                t2 = hhmm(end)
                c5 = bc
        pos = eng.pos
        if pos == 0 and t == 1600 and t2 == 1600 and nb2 > 300 and 1 <= DW[i] <= 3 and c5 < ema:
            eng.order(MKT, BUY, None, "L")
        if pos == 1 and 830 <= t < 1700:
            eng.order(MKT, XLONG, None, "LX" if t < 1540 else "Flat")
    return eng


def s06_channel_breakout(b, tf, i0, i1, p):
    """Long when a 1-minute high clears the 5-bar channel high of signal bars + 1 tick;
    exit on a channel-low break or a 2 x ATR14 trailing stop; flat 15:40, no re-entry."""
    O, H, L, C, V, T, CA = b.o, b.h, b.l, b.c, b.v, b.hhmm, b.cabs
    eng = Engine(CA, p["tick"])
    tfb = TFBars(tf)
    tick = p["tick"]
    ha = []
    la = []
    n2 = 0
    atr2 = pc2 = 0.0
    up = dn = atr_lvl = 0.0
    lvl_ok = False
    best_h = stop_px = trail = e_stop = 0.0
    prev_mp = 0
    for i in range(i0, i1):
        o, h, l, c = O[i], H[i], L[i], C[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        t = T[i]
        mp = eng.pos
        if mp != 0 and prev_mp == 0:
            stop_px = eng.entry_px - e_stop
            trail = e_stop
            best_h = eng.entry_px
        if mp == 1:
            if 1540 <= t < 1700:
                eng.order(MKT, XLONG, None, "Flat")
            else:
                if h > best_h:
                    best_h = h
                if best_h - trail > stop_px:
                    stop_px = best_h - trail
                if lvl_ok and l <= dn - tick:
                    eng.order(MKT, XLONG, None, "Ch")
                else:
                    eng.order(STOP, XLONG, stop_px, "SL")
        if (mp == 0 and lvl_ok and h >= up + tick and (t <= 1500 or t >= 1701)
                and atr_lvl > 0):
            e_stop = 2.0 * atr_lvl
            eng.order(MKT, BUY, None, "L")
            eng.order(STOP, XLONG, c - e_stop, "SL")
        closed = tfb.update(CA[i], o, h, l, c, V[i])
        if closed:
            for end, bo, bh, bl, bc, bv in closed:
                n2 += 1
                if n2 == 1:
                    atr2 = bh - bl
                else:
                    tr = max(bh - bl, abs(bh - pc2), abs(bl - pc2))
                    atr2 += (tr - atr2) / 14
                pc2 = bc
                ha.append(bh)
                la.append(bl)
                if len(ha) > 5:
                    del ha[0]
                    del la[0]
                if n2 >= 5:
                    up = max(ha)
                    dn = min(la)
                    lvl_ok = True
                atr_lvl = atr2
        prev_mp = mp
    return eng


def s08_forecast_to_fill(b, tf, i0, i1, p):
    """Forecast-to-Fill trend (arXiv:2511.08571 port): long while EMA(50) of signal bars rises
    (Pbull = sigmoid(2 x slope / StDev14) > 0.5), stop = max(entry - 2 ATR14, highest high since
    entry - 1.5 ATR14), exit on a regime flip or after 30 bars. tf = 0 uses session daily bars
    (17:00-16:00 CT). VolScalar is computed in the original but never sizes the trade, so it is
    left out. p["lucid_flat"]: flat at 15:40 CT and re-open at 17:00 with the same stop state.
    Improvement options (defaults = the original): p["entry_thr"] / p["exit_thr"] enter above /
    exit at or below these Pbull levels (e.g. 0.6 / 0.4); p["slope_norm"] = "atr" divides the EMA
    change by ATR(14) instead of StDev(Close, 14); p["rth_only"] allows entries only on signal bars
    closing 08:31-15:00 CT."""
    import math
    O, H, L, C, V, T, D, CA = b.o, b.h, b.l, b.c, b.v, b.hhmm, b.day, b.cabs
    eng = Engine(CA, p["tick"])
    lucid = p.get("lucid_flat", False)
    thr_in, thr_out = p.get("entry_thr", 0.5), p.get("exit_thr", 0.5)
    norm_atr = p.get("slope_norm", "stdev") == "atr"
    rth_only = p.get("rth_only", False)
    tfb = TFBars(tf) if tf else None
    sk = None
    so = sh = sl_ = sc = 0.0
    live = False
    a_ema = 2.0 / 51
    ema = ema_prev = None
    closes = []
    trs = []
    prev_c = None
    nbar = 0
    in_trade = False
    entry_bar = 0
    entry_px = 0.0
    hh = 0.0
    standing = None
    re_dir = 0
    prev_mp = 0

    def on_bar(bh, bl, bc):
        nonlocal ema, ema_prev, prev_c, nbar, in_trade, entry_bar, entry_px, hh, standing, re_dir
        nbar += 1
        ema_prev = ema
        ema = bc if ema is None else ema + a_ema * (bc - ema)
        closes.append(bc)
        if len(closes) > 14:
            del closes[0]
        trs.append(bh - bl if prev_c is None else max(bh - bl, abs(bh - prev_c), abs(bl - prev_c)))
        if len(trs) > 14:
            del trs[0]
        prev_c = bc
        if ema_prev is None or len(closes) < 14:
            return
        m = sum(closes) / 14
        sd = math.sqrt(sum((x - m) ** 2 for x in closes) / 14)
        atr = sum(trs) / len(trs)
        den = atr if norm_atr else sd
        slope = (ema - ema_prev) / den if den != 0 else 0.0
        pbull = 1.0 / (1.0 + math.exp(-slope * 2.0))
        mp = 1 if (eng.pos == 1 or re_dir == 1) else 0
        entry_ok = not rth_only or 830 < T[i] <= 1500
        if pbull > thr_in and mp == 0 and entry_ok and not (lucid and 1540 <= T[i] < 1600):
            eng.order(MKT, BUY, None, "F2F_LE")
        standing = None
        if mp == 1:
            if not in_trade:
                in_trade = True
                entry_bar = nbar
                entry_px = eng.entry_px
                hh = bh
            hh = max(hh, bh)
            bars_in = nbar - entry_bar
            standing = max(entry_px - 2.0 * atr, hh - 1.5 * atr)
            if pbull <= thr_out or bars_in >= 30:
                eng.order(MKT, XLONG, None, "RegimeExit" if pbull <= thr_out else "TimeOut")
                if eng.pos == 0:            # flat for the Lucid close: drop the 17:00 re-entry
                    re_dir = 0
                    in_trade = False
                    standing = None
        else:
            in_trade = False

    for i in range(i0, i1):
        o, h, l, c = O[i], H[i], L[i], C[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        t = T[i]
        if eng.pos == 0 and prev_mp == 1 and re_dir == 0:
            in_trade = False
            standing = None
        if tfb is not None:
            closed = tfb.update(CA[i], o, h, l, c, V[i])
            if closed:
                for end, bo, bh, bl, bc, bv in closed:
                    on_bar(bh, bl, bc)
        else:
            k = D[i] + (1 if t > 1600 else 0)
            if k != sk:
                if live:
                    on_bar(sh, sl_, sc)
                sk, so, sh, sl_, sc, live = k, o, h, l, c, True
            else:
                sh, sl_, sc = max(sh, h), min(sl_, l), c
            if t == 1600:
                on_bar(sh, sl_, sc)
                live = False
        if lucid:
            if eng.pos == 1 and 1540 <= t < 1700:
                re_dir = 1
                eng.order(MKT, XLONG, None, "Flat")
            elif re_dir == 1 and eng.pos == 0 and (t == 1600 or 1701 <= t < 1800):
                eng.order(MKT, BUY, None, "Re")
            elif eng.pos == 1 and t >= 1701:
                re_dir = 0
        if eng.pos == 1 and standing is not None:
            eng.order(STOP, XLONG, standing, "ATRExit")
        prev_mp = eng.pos
    return eng


def s09_orb(b, tf, i0, i1, p):
    """Opening range = the signal bars from 08:30 to 08:30 + orb_or_min CT (default: the first bar). First signal-bar close
    outside it, up to 14:00 CT, enters at market; stop at the other side of the range, target
    orb_target_r x risk from the signal close (0 = none); orb_max_trades a day (default 1), flat at 15:00 CT."""
    O, H, L, C, V, T, D, CA = b.o, b.h, b.l, b.c, b.v, b.hhmm, b.day, b.cabs
    eng = Engine(CA, p["tick"])
    tfb = TFBars(tf)
    or_end = hhmm(8 * 60 + 30 + int(p.get("orb_or_min", tf)))
    last_entry = int(p.get("orb_last_entry", 1400))
    flat = int(p.get("orb_flat", 1500))
    target_r = float(p.get("orb_target_r", 0))
    shorts = bool(p.get("orb_shorts", 1))
    max_trades = int(p.get("orb_max_trades", 1))
    rng_hi = rng_lo = 0.0
    rng_date = None
    traded = 0
    stop_px = tgt_px = 0.0
    for i in range(i0, i1):
        o, h, l, c = O[i], H[i], L[i], C[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        t = T[i]
        sig = 0
        closed = tfb.update(CA[i], o, h, l, c, V[i])
        if closed:
            for end, bo, bh, bl, bc, bv in closed:
                t2, d2 = hhmm(end), end // 1440
                c2 = bc
                if 830 < t2 <= or_end:
                    if d2 != rng_date:
                        rng_hi, rng_lo, rng_date, traded = bh, bl, d2, 0
                    else:
                        rng_hi, rng_lo = max(rng_hi, bh), min(rng_lo, bl)
                elif d2 == rng_date and or_end < t2 <= last_entry and traded < max_trades:
                    sig = 1 if bc > rng_hi else (-1 if bc < rng_lo and shorts else 0)
        pos = eng.pos
        if pos != 0:
            xa = XLONG if pos == 1 else XSHORT
            if t >= flat or D[i] != rng_date:
                eng.order(MKT, xa, None, "EOD")
            else:
                eng.order(STOP, xa, stop_px, "SL")
                if tgt_px:
                    eng.order(LIMIT, xa, tgt_px, "TP")
        elif sig:
            stop_px = rng_lo if sig == 1 else rng_hi
            tgt_px = c2 + target_r * (c2 - stop_px) if target_r > 0 else 0.0
            xa = XLONG if sig == 1 else XSHORT
            eng.order(MKT, BUY if sig == 1 else SHORT, None, "L" if sig == 1 else "S")
            eng.order(STOP, xa, stop_px, "SL0")
            if tgt_px:
                eng.order(LIMIT, xa, tgt_px, "TP0")
            traded += 1
    return eng


def s10_fabio(b, tf, i0, i1, p):
    """Fabio Valentini model (Institutional Protocol PDF), read on a CT chart: opening range 08:30-09:00 CT
    from the signal bars; long on the first signal-bar close above the range high before 14:00, one
    entry a day; stop at the range low, target fab_tp_r x (close - range low); flat at 14:00 CT.
    The original's delta filter (Upticks - Downticks >= 200) needs tick data: fab_delta sets a
    threshold on a 1-minute proxy, sum of volume x sign(close - open) over the signal bar (off by default)."""
    O, H, L, C, V, T, D, CA = b.o, b.h, b.l, b.c, b.v, b.hhmm, b.day, b.cabs
    eng = Engine(CA, p["tick"])
    tfb = TFBars(tf)
    or_end = hhmm(8 * 60 + 30 + int(p.get("fab_or_min", 30)))
    trade_end = int(p.get("fab_end", 1400))
    tp_r = float(p.get("fab_tp_r", 1.0))
    delta_min = p.get("fab_delta")
    delta = {}
    orb_hi = orb_lo = 0.0
    orb_date = None
    done = False
    sl = tp = 0.0
    for i in range(i0, i1):
        o, h, l, c = O[i], H[i], L[i], C[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        t = T[i]
        if delta_min is not None:
            bk = (CA[i] - 1) // tf
            delta[bk] = delta.get(bk, 0) + (V[i] if c > o else (-V[i] if c < o else 0))
        sig = False
        closed = tfb.update(CA[i], o, h, l, c, V[i])
        if closed:
            for end, bo, bh, bl, bc, bv in closed:
                t2, d2 = hhmm(end), end // 1440
                if 830 < t2 <= or_end:
                    if d2 != orb_date:
                        orb_hi, orb_lo, orb_date, done = bh, bl, d2, False
                    else:
                        orb_hi, orb_lo = max(orb_hi, bh), min(orb_lo, bl)
                elif d2 == orb_date and or_end < t2 < trade_end and not done and bc > orb_hi and orb_lo < bc:
                    ok = True
                    if delta_min is not None:
                        ok = delta.pop(end // tf - 1, 0) >= float(delta_min)
                    if ok:
                        sig, ep = True, bc
            if delta_min is not None and len(delta) > 4:
                for k in sorted(delta)[:-2]:
                    del delta[k]
        if eng.pos == 1:
            if t >= trade_end or D[i] != orb_date:
                eng.order(MKT, XLONG, None, "EOD")
            else:
                eng.order(STOP, XLONG, sl, "SL")
                eng.order(LIMIT, XLONG, tp, "TP")
        elif sig:
            sl, tp = orb_lo, ep + tp_r * (ep - orb_lo)
            eng.order(MKT, BUY, None, "L")
            eng.order(STOP, XLONG, sl, "SL0")
            eng.order(LIMIT, XLONG, tp, "TP0")
            done = True
    return eng


def s21_ivb(b, tf, i0, i1, p):
    """IVB Model (Matteo Conti validation report of Fabio Valentini's long-only ORB, Apr 2026), 1-minute chart, CT.
    Opening range = 1-minute bars 08:30-09:00 CT (09:30-10:00 ET). From the 09:00 close until 14:00 CT a buy stop
    rests at the range high; one long a session. Stop = range low, target = range high + ivb_tp_r x (high - low),
    both computed from the stop level (EP = ORB high), not the fill. Exits are re-armed on every bar while long,
    so (as in the PowerLanguage) they work from the bar after the fill. Flat at market on the first bar at or after
    ivb_end (14:00 CT); on early-close days (12:15 CT) an open long is carried to the 17:00 reopen and flattened
    there, as MultiCharts would. tf is ignored.
    ivb_hol (default 1): no trade on NYSE closures (Globex shuts at 12:00 CT) or 12:15 CT early closes, so no long is
    ever carried into the 17:00 reopen; 0 = trade them like a plain MultiCharts run of the paper.
    Options (off = paper): ivb_or_min (30), ivb_end (1400), ivb_tp_r (1.0), ivb_min_pts / ivb_max_pts (range filter
    in points, 0 = off)."""
    O, H, L, C, T, D, CA = b.o, b.h, b.l, b.c, b.hhmm, b.day, b.cabs
    eng = Engine(CA, p["tick"])
    or_end = hhmm(8 * 60 + 30 + int(p.get("ivb_or_min", 30)))
    t_end = int(p.get("ivb_end", 1400))
    tp_r = float(p.get("ivb_tp_r", 1.0))
    min_pts = float(p.get("ivb_min_pts", 0))
    max_pts = float(p.get("ivb_max_pts", 0))
    skip = set()
    if int(p.get("ivb_hol", 1)):
        cl, ea = nyse_calendar()
        skip = cl | ea
    hi = lo = 0.0
    day = None
    armed = done = False
    sl = tp = 0.0
    for i in range(i0, i1):
        o, h, l, c, t, d = O[i], H[i], L[i], C[i], T[i], D[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        if d != day:                                   # new session: reset the ORB state
            day, armed, done, hi, lo = d, False, False, 0.0, 0.0
        # resting buy stop at the range high (sent on the previous bar's close)
        if armed and eng.pos == 0 and h >= hi:
            eng._open(i, 1, max(o, hi), "ORB-L STP")
            eng.entry_kind = STOP
            armed, done = False, True
            sl, tp = lo, hi + tp_r * (hi - lo)
        if 830 < t <= or_end:                          # build the range
            if hi == 0.0:
                hi, lo = h, l
            else:
                hi, lo = max(hi, h), min(lo, l)
        if eng.pos == 1:
            # t >= t_end also catches the 17:00 reopen after an early (12:15) close, as the PL does
            if t >= t_end or t < 830:
                eng.order(MKT, XLONG, None, "EOD")
            else:
                eng.order(STOP, XLONG, sl, "SL")
                eng.order(LIMIT, XLONG, tp, "TP")
        armed = False
        if (eng.pos == 0 and not done and hi > 0 and or_end <= t < t_end and d not in skip
                and (not min_pts or hi - lo >= min_pts) and (not max_pts or hi - lo <= max_pts)):
            armed = True
    return eng


def s22_orb_fade(b, tf, i0, i1, p):
    """Failed ORB fade (2026-11-08, mean reversion from the IVB Model's stop-outs), NQ, CT.
    Range = 1-minute bars 08:31-09:00. After 09:00 price trades through the range high (low); the first tf-minute
    close back inside the range (close < high, > low) up to fb_last sells (buys) at market next bar.
    Stop = the extreme made since the break + fb_buf ticks; target = fb_tp x range back from the broken edge
    (0.5 = midpoint, 1.0 = other side). One trade a day; flat at market from fb_end. NYSE closures / early closes
    skipped. Options: fb_side (both|short|long), fb_maxrisk (skip if stop distance > x range), fb_minpen /
    fb_maxpen (break extreme beyond the edge, in range units), fb_rng_lo / fb_rng_hi (range / dATR14),
    fb_news ("fomc" or "cpi,nfp,fomc"), fb_vol_lo (dATR >= x * its 250-session median), fb_bias (1 = never fade
    in the direction against the overnight bias: no short on long-bias days, no long on short-bias days;
    bias from the 08:30 open's place in the 00:00-08:30 CT range, >= 0.67 long, <= 0.33 short)."""
    O, H, L, C, V, T, D, CA = b.o, b.h, b.l, b.c, b.v, b.hhmm, b.day, b.cabs
    tick = p["tick"]
    eng = Engine(CA, tick)
    tfb = TFBars(tf)
    side_opt = str(p.get("fb_side", "both"))
    tp_k = float(p.get("fb_tp", 0.5))
    last_t = int(p.get("fb_last", 1300))
    end_t = int(p.get("fb_end", 1400))
    buf = float(p.get("fb_buf", 1)) * tick
    maxrisk = float(p.get("fb_maxrisk", 0))
    minpen, maxpen = float(p.get("fb_minpen", 0)), float(p.get("fb_maxpen", 0))
    rlo, rhi = float(p.get("fb_rng_lo", 0)), float(p.get("fb_rng_hi", 0))
    vol_lo = float(p.get("fb_vol_lo", 0))
    bias_rule = int(p.get("fb_bias", 0))
    cl, ea = nyse_calendar()
    skip = cl | ea
    if p.get("fb_news"):
        import news_calendar
        skip = skip | set(news_calendar.days(p["fb_news"]))
    hi = lo = 0.0
    day = None
    done = False
    up_x = dn_x = None                 # extreme since the break above / below
    rth_h = rth_l = None
    rngs, dat_hist = [], []
    dat = 0.0
    on_h = on_l = None                 # overnight range (00:00-08:30 CT) for the bias
    bias = 0
    sl = tp = 0.0
    for i in range(i0, i1):
        o, h, l, c, t, d = O[i], H[i], L[i], C[i], T[i], D[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        if d != day:
            if rth_h is not None:
                rngs.append(rth_h - rth_l)
                if len(rngs) > 14:
                    del rngs[0]
            dat = sum(rngs) / len(rngs) if len(rngs) >= 14 else 0.0
            if dat:
                dat_hist.append(dat)
                if len(dat_hist) > 250:
                    del dat_hist[0]
            day, done, hi, lo, up_x, dn_x, rth_h, rth_l, on_h, on_l = d, False, 0.0, 0.0, None, None, None, None, None, None
        if t <= 830:
            on_h = h if on_h is None else max(on_h, h)
            on_l = l if on_l is None else min(on_l, l)
        if t == 831 and on_h is not None and on_h > on_l:
            q = (o - on_l) / (on_h - on_l)
            bias = 1 if q >= .67 else (-1 if q <= .33 else 0)
        if 830 < t <= 1500:
            rth_h = h if rth_h is None else max(rth_h, h)
            rth_l = l if rth_l is None else min(rth_l, l)
        if 830 < t <= 900:
            hi = h if hi == 0.0 else max(hi, h)
            lo = l if lo == 0.0 else min(lo, l)
        elif t > 900 and hi > 0 and not done:
            if h > hi:
                up_x = h if up_x is None else max(up_x, h)
            if l < lo:
                dn_x = l if dn_x is None else min(dn_x, l)
        closed = tfb.update(CA[i], o, h, l, c, V[i])
        sig = 0
        if closed and not done and hi > 0 and eng.pos == 0 and 900 <= t < min(last_t, end_t) and d not in skip:
            bc = closed[-1][4]
            rng = hi - lo
            ok = rng > 0
            if ok and (rlo or rhi):
                ok = dat > 0 and (not rlo or rng >= rlo * dat) and (not rhi or rng <= rhi * dat)
            if ok and vol_lo:
                ok = len(dat_hist) >= 60 and dat >= vol_lo * sorted(dat_hist)[len(dat_hist) // 2]
            if ok and up_x is not None and lo < bc < hi and side_opt in ("both", "short"):
                pen = (up_x - hi) / rng
                if (not minpen or pen >= minpen) and (not maxpen or pen <= maxpen) and not (bias_rule and bias == 1):
                    sig, sl, tp = -1, up_x + buf, hi - tp_k * rng
            if ok and not sig and dn_x is not None and lo < bc < hi and side_opt in ("both", "long"):
                pen = (lo - dn_x) / rng
                if (not minpen or pen >= minpen) and (not maxpen or pen <= maxpen) and not (bias_rule and bias == -1):
                    sig, sl, tp = 1, dn_x - buf, lo + tp_k * rng
            if sig and maxrisk and abs(sl - bc) > maxrisk * rng:
                sig = 0
            if sig and ((sig == -1 and tp >= bc) or (sig == 1 and tp <= bc)):
                sig = 0                                       # already at / past the target
        if eng.pos != 0:
            xa = XLONG if eng.pos == 1 else XSHORT
            if t >= end_t or t < 830:
                eng.order(MKT, xa, None, "EOD")
            else:
                eng.order(STOP, xa, sl, "SL")
                eng.order(LIMIT, xa, tp, "TP")
        elif sig:
            xa = XLONG if sig == 1 else XSHORT
            eng.order(MKT, BUY if sig == 1 else SHORT, None, "FadeL" if sig == 1 else "FadeS")
            eng.order(STOP, xa, sl, "SL0")
            eng.order(LIMIT, xa, tp, "TP0")
            done = True
    return eng


def _datr_update(rngs, rth_h, rth_l, n=14):
    if rth_h is not None:
        rngs.append(rth_h - rth_l)
        if len(rngs) > n:
            del rngs[0]
    return sum(rngs) / len(rngs) if len(rngs) >= n else 0.0


def s23_stretch_fade(b, tf, i0, i1, p):
    """Stretch fade (2026-11-08, mean reversion), CT. dATR = mean RTH range of 14 sessions. On each tf-bar close
    between sf_start and sf_last, if the close is >= sf_k x dATR above the anchor (sf_anchor: "vwap" = RTH VWAP
    from 08:30, "open" = today's 08:30 open) -> short at market next bar; mirror long below. Target = back
    sf_tp x the stretch toward the anchor (1.0 = the anchor at signal time); stop = sf_sl x dATR beyond the fill.
    Flat at sf_end. sf_max trades a day (default 1). Filters: sf_gex ("pos" = yesterday's GEX > 0, "rank" =
    yesterday's GEX rank in its 252 days >= sf_gex_r), sf_adx (Wilder ADX(14) on the tf bars of the session must be
    below this), sf_news, sf_vol_hi (dATR <= x * 250-session median), sf_side (both|long|short). NYSE closures and
    early closes skipped."""
    O, H, L, C, V, T, D, CA = b.o, b.h, b.l, b.c, b.v, b.hhmm, b.day, b.cabs
    tick = p["tick"]
    eng = Engine(CA, tick)
    tfb = TFBars(tf)
    anchor = p.get("sf_anchor", "vwap")
    k = float(p.get("sf_k", 0.5))
    t0, t_last, t_end = int(p.get("sf_start", 930)), int(p.get("sf_last", 1330)), int(p.get("sf_end", 1430))
    tp_k, sl_k = float(p.get("sf_tp", 1.0)), float(p.get("sf_sl", 0.5))
    max_n = int(p.get("sf_max", 1))
    gexm, gex_r = p.get("sf_gex", ""), float(p.get("sf_gex_r", 0.5))
    adx_max = float(p.get("sf_adx", 0))
    vol_hi = float(p.get("sf_vol_hi", 0))
    side_opt = p.get("sf_side", "both")
    cl, ea = nyse_calendar()
    skip = cl | ea
    if p.get("sf_news"):
        import news_calendar
        skip |= set(news_calendar.days(str(p["sf_news"]).replace(";", ",")))
    gext = _gex_table() if gexm else None
    day = None
    rngs, dat_hist = [], []
    dat = 0.0
    rth_h = rth_l = None
    pv = vv = 0.0
    d_open = None
    n_today = 0
    day_ok = True
    adx = WilderADX(14) if adx_max else None      # runs across sessions on the RTH tf bars
    sl = tp = 0.0
    for i in range(i0, i1):
        o, h, l, c, t, d = O[i], H[i], L[i], C[i], T[i], D[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        if d != day:
            dat = _datr_update(rngs, rth_h, rth_l)
            if dat:
                dat_hist.append(dat)
                if len(dat_hist) > 250:
                    del dat_hist[0]
            day, rth_h, rth_l, pv, vv, d_open, n_today = d, None, None, 0.0, 0.0, None, 0
            day_ok = d not in skip and dat > 0
            if day_ok and vol_hi and len(dat_hist) >= 60:
                day_ok = dat <= vol_hi * sorted(dat_hist)[len(dat_hist) // 2]
            if day_ok and gext is not None:
                gv = _gex_prev(gext, d)
                if gv is None:
                    day_ok = False
                elif gexm == "pos":
                    day_ok = gv[0] > 0
                elif gexm == "rank":
                    day_ok = gv[1] is not None and gv[1] >= gex_r
        if 830 < t <= 1500:
            if d_open is None:
                d_open = o
            rth_h = h if rth_h is None else max(rth_h, h)
            rth_l = l if rth_l is None else min(rth_l, l)
            pv += (h + l + c) / 3 * V[i]
            vv += V[i]
        closed = tfb.update(CA[i], o, h, l, c, V[i])
        sig = 0
        if closed and 830 < t <= 1500:
            bc = closed[-1][4]
            if adx is not None:
                adx.update(closed[-1][2], closed[-1][3], bc)
            if (day_ok and eng.pos == 0 and n_today < max_n and t0 <= t < t_last and vv > 0):
                ref = pv / vv if anchor == "vwap" else d_open
                st = (bc - ref) / dat
                ok = adx is None or (adx.k >= 28 and adx.adx < adx_max)
                if ok and st >= k and side_opt in ("both", "short"):
                    sig = -1
                elif ok and st <= -k and side_opt in ("both", "long"):
                    sig = 1
                if sig:
                    tp = bc - tp_k * (bc - ref)
                    sl = bc - sig * sl_k * dat
        if eng.pos != 0:
            xa = XLONG if eng.pos == 1 else XSHORT
            if t >= t_end or t < 830:
                eng.order(MKT, xa, None, "EOD")
            else:
                eng.order(STOP, xa, sl, "SL")
                eng.order(LIMIT, xa, tp, "TP")
        elif sig:
            xa = XLONG if sig == 1 else XSHORT
            eng.order(MKT, BUY if sig == 1 else SHORT, None, "SF.L" if sig == 1 else "SF.S")
            eng.order(STOP, xa, sl, "SL0")
            eng.order(LIMIT, xa, tp, "TP0")
            n_today += 1
    return eng


def s24_extreme_reversal(b, tf, i0, i1, p):
    """Extreme-day reversal (2026-11-08, mean reversion, intraday only), CT. Yesterday's RTH bar (08:30-15:00):
    IBS = (close - low) / (high - low), ret = (close - previous RTH close) / dATR14. Long if IBS <= er_ibs_lo (and,
    if er_ret > 0, ret <= -er_ret); short (er_shorts=1) if IBS >= er_ibs_hi (and ret >= er_ret). Market order on the
    er_time bar close (830 = fill at the 08:31 open, i.e. the RTH open). Stop er_sl x dATR (0 = none), target
    er_tp x dATR (0 = none), flat at market after er_exit (1540). Filters: er_trend ("above" = longs only when
    yesterday's close > er_sma-day SMA of RTH closes, shorts only below), er_gex ("pos"), er_news. NYSE closures and
    early closes skipped. tf ignored.
    Improvement options (2026-11-08, all off by default): er_or_ret (also long when yesterday's close-to-close <= -x
    dATR, whatever the IBS), er_or_2d (also long when the last two IBS are both <= x), er_short_trend (1 = shorts only
    when yesterday's close < er_sma SMA; longs unaffected), er_gap_max (skip a long when today's 08:30 open is > x dATR
    above yesterday's close: the rebound already happened overnight), er_entry ("mkt" default; "lim" = buy limit
    er_lim x dATR below the er_time close, valid until er_lim_end; "reclaim" = first 1-minute close above today's 08:30
    open from er_time to er_lim_end), er_trail (from er_trail_t, stop x dATR below the best close since the fill)."""
    O, H, L, C, T, D, CA = b.o, b.h, b.l, b.c, b.hhmm, b.day, b.cabs
    eng = Engine(CA, p["tick"])
    or_ret, or_2d = float(p.get("er_or_ret", 0)), float(p.get("er_or_2d", 0))
    short_trend = int(p.get("er_short_trend", 0))
    gap_max = float(p.get("er_gap_max", 0))
    entry_mode = p.get("er_entry", "mkt")
    lim_k, lim_end = float(p.get("er_lim", 0.2)), int(p.get("er_lim_end", 1100))
    trail_k, trail_t = float(p.get("er_trail", 0)), int(p.get("er_trail_t", 1300))
    pend = 0
    lim_px = 0.0
    best_c = 0.0
    lo_ibs, hi_ibs = float(p.get("er_ibs_lo", 0.2)), float(p.get("er_ibs_hi", 0.8))
    ret_k = float(p.get("er_ret", 0))
    shorts = int(p.get("er_shorts", 0))
    t_in, t_out = int(p.get("er_time", 830)), int(p.get("er_exit", 1540))
    sl_k, tp_k = float(p.get("er_sl", 0)), float(p.get("er_tp", 0))
    trend, sma_n = p.get("er_trend", ""), int(p.get("er_sma", 200))
    gexm = p.get("er_gex", "")
    gapf = p.get("er_gap", "")                      # "down": today's 08:30 open < yesterday's RTH close; "up": >
    conf = int(p.get("er_conf", 0))                 # 1: entry-bar close > 08:30 open (rebound started); -1: <
    vlo, vhi = float(p.get("er_vol_lo", 0)), float(p.get("er_vol_hi", 0))   # dATR vs its 250-session median
    two = float(p.get("er_2d", 0))                  # also the day before yesterday's IBS <= this
    dows = {int(x) for x in str(p.get("er_dow", "")).split(";") if x.strip()}   # weekdays traded, 1=Mon..5=Fri
    cl, ea = nyse_calendar()
    skip = cl | ea
    if p.get("er_news"):
        import news_calendar
        skip |= set(news_calendar.days(str(p["er_news"]).replace(";", ",")))
    gext = _gex_table() if gexm else None
    day = None
    rngs, closes = [], []
    dat = 0.0
    rh = rl = rc = None
    prev = None                 # (ibs, ret) of yesterday
    prev2 = None
    dat_hist = []
    d_open = None
    done = False
    sl = tp = None
    for i in range(i0, i1):
        o, h, l, c, t, d = O[i], H[i], L[i], C[i], T[i], D[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        if d != day:
            if rh is not None and rh > rl:
                ret = (rc - closes[-1]) / dat if closes and dat else 0.0
                prev2 = prev
                prev = ((rc - rl) / (rh - rl), ret)
                closes.append(rc)
                if len(closes) > sma_n + 1:
                    del closes[0]
            dat = _datr_update(rngs, rh, rl)
            if dat:
                dat_hist.append(dat)
                if len(dat_hist) > 250:
                    del dat_hist[0]
            day, rh, rl, rc, done, d_open = d, None, None, None, False, None
        if 830 < t <= 1500:
            if d_open is None:
                d_open = o
            rh = h if rh is None else max(rh, h)
            rl = l if rl is None else min(rl, l)
            rc = c
        if pend and eng.pos == 0 and not eng.orders:
            if t >= lim_end or d != pend_day:
                pend = 0
            elif entry_mode == "lim" and l <= lim_px:
                eng._open(i, 1, min(o, lim_px), "ER.L")
                eng.entry_kind = LIMIT
                pend = 0
        if eng.pos != 0 and eng.entry_i == i:
            sl = eng.entry_px - eng.pos * sl_k * dat if sl_k else None
            tp = eng.entry_px + eng.pos * tp_k * dat if tp_k else None
            best_c = c
        if eng.pos != 0 and trail_k:
            best_c = max(best_c, c) if eng.pos == 1 else min(best_c, c)
            if t >= trail_t:
                ts = best_c - eng.pos * trail_k * dat
                sl = ts if sl is None else (max(sl, ts) if eng.pos == 1 else min(sl, ts))
        if pend and eng.pos == 0 and entry_mode == "reclaim" and t < lim_end and c > d_open:
            eng.order(MKT, BUY, None, "ER.L")
            pend = 0
        if eng.pos != 0:
            xa = XLONG if eng.pos == 1 else XSHORT
            if t >= t_out or t < 830:
                eng.order(MKT, xa, None, "EOD")
            else:
                if sl is not None:
                    eng.order(STOP, xa, sl, "SL")
                if tp is not None:
                    eng.order(LIMIT, xa, tp, "TP")
        elif t == t_in and not done and prev is not None and dat > 0 and d not in skip:
            done = True
            ibs, ret = prev
            sig = 0
            if ibs <= lo_ibs and (not ret_k or ret <= -ret_k):
                sig = 1
            elif or_ret and ret <= -or_ret:
                sig = 1
            elif or_2d and prev2 is not None and ibs <= or_2d and prev2[0] <= or_2d:
                sig = 1
            elif shorts and ibs >= hi_ibs and (not ret_k or ret >= ret_k):
                sig = -1
            if sig == -1 and short_trend and len(closes) >= sma_n and closes[-1] >= sum(closes[-sma_n:]) / sma_n:
                sig = 0
            if sig == 1 and gap_max and closes and d_open is not None and (d_open - closes[-1]) / dat > gap_max:
                sig = 0
            if sig and trend and len(closes) >= sma_n:
                above = closes[-1] > sum(closes[-sma_n:]) / sma_n
                if (sig == 1) != above:
                    sig = 0
            if sig and two and (prev2 is None or prev2[0] > two):
                sig = 0
            if sig and gapf and closes and d_open is not None:
                if (gapf == "down") != (d_open < closes[-1]):
                    sig = 0
            if sig and conf and d_open is not None and (c > d_open) != (conf > 0):
                sig = 0
            if sig and (vlo or vhi) and len(dat_hist) >= 60:
                med = sorted(dat_hist)[len(dat_hist) // 2]
                if (vlo and dat < vlo * med) or (vhi and dat > vhi * med):
                    sig = 0
            if sig and dows and date_dow(d) not in dows:
                sig = 0
            if sig and gext is not None:
                gv = _gex_prev(gext, d)
                if gv is None or (gexm == "pos" and gv[0] <= 0):
                    sig = 0
            if sig == 1 and entry_mode in ("lim", "reclaim"):
                pend, pend_day, lim_px = 1, d, c - lim_k * dat
                if entry_mode == "reclaim" and c > d_open:
                    eng.order(MKT, BUY, None, "ER.L")
                    pend = 0
            elif sig:
                eng.order(MKT, BUY if sig == 1 else SHORT, None, "ER.L" if sig == 1 else "ER.S")
    return eng


def nyse_calendar(y0=2009, y1=2028):
    """NYSE full closures and 13:00 ET early closes as day ordinals, by the rules in the Monday Long
    v2.1 code: New Year (Sun -> Mon, Sat -> none), MLK, Presidents', Good Friday, Memorial,
    Juneteenth (from 2022), July 4, Labor, Thanksgiving, Christmas (Sat -> Fri, Sun -> Mon);
    early closes 3 Jul (Mon-Thu), the day after Thanksgiving, 24 Dec (Mon-Thu)."""
    from datetime import date as _d, timedelta as _td

    def nth_wd(y, m, wd, n):                       # n-th weekday wd (Mon=0) of the month
        d = _d(y, m, 1)
        return d + _td(days=(wd - d.weekday()) % 7 + 7 * (n - 1))

    def observed(d):
        return d - _td(days=1) if d.weekday() == 5 else (d + _td(days=1) if d.weekday() == 6 else d)

    closures, early = set(), set()
    for y in range(y0, y1 + 1):
        ny = _d(y, 1, 1)
        if ny.weekday() != 5:
            closures.add((ny + _td(days=1) if ny.weekday() == 6 else ny).toordinal())
        closures.add(nth_wd(y, 1, 0, 3).toordinal())
        closures.add(nth_wd(y, 2, 0, 3).toordinal())
        a, bb, c = y % 19, y // 100, y % 100
        dd, e, f = bb // 4, bb % 4, (bb + 8) // 25
        g = (bb - f + 1) // 3
        hh = (19 * a + bb - dd - g + 15) % 30
        ii, k = c // 4, c % 4
        ll = (32 + 2 * e + 2 * ii - hh - k) % 7
        m = (a + 11 * hh + 22 * ll) // 451
        closures.add((_d(y, (hh + ll - 7 * m + 114) // 31, (hh + ll - 7 * m + 114) % 31 + 1) - _td(days=2)).toordinal())
        mem = _d(y, 5, 31)
        closures.add((mem - _td(days=mem.weekday())).toordinal())
        if y >= 2022:
            closures.add(observed(_d(y, 6, 19)).toordinal())
        closures.add(observed(_d(y, 7, 4)).toordinal())
        closures.add(nth_wd(y, 9, 0, 1).toordinal())
        tg = nth_wd(y, 11, 3, 4)
        closures.add(tg.toordinal())
        closures.add(observed(_d(y, 12, 25)).toordinal())
        if _d(y, 7, 3).weekday() <= 3:
            early.add(_d(y, 7, 3).toordinal())
        early.add(tg.toordinal() + 1)
        if _d(y, 12, 24).weekday() <= 3:
            early.add(_d(y, 12, 24).toordinal())
    return closures, early


class WilderADX:
    """ADX(n) with Wilder smoothing on bars fed one at a time (MultiCharts' ADX / DirMovement)."""

    def __init__(self, n):
        self.n = n
        self.ph = self.pl = self.pc = None
        self.tr = None
        self.pdm = self.mdm = 0.0
        self.adx = 0.0
        self.pdi = self.mdi = 0.0
        self.k = 0

    def update(self, h, l, c):
        if self.pc is None:
            self.ph, self.pl, self.pc = h, l, c
            return self.adx
        n, pc = self.n, self.pc
        tr = max(h - l, abs(h - pc), abs(l - pc))
        um, dm = h - self.ph, self.pl - l
        pdm = um if um > dm and um > 0 else 0.0
        mdm = dm if dm > um and dm > 0 else 0.0
        if self.tr is None:
            self.tr, self.pdm, self.mdm = tr, pdm, mdm
        else:
            self.tr += (tr - self.tr) / n
            self.pdm += (pdm - self.pdm) / n
            self.mdm += (mdm - self.mdm) / n
        if self.tr > 0:
            self.pdi, self.mdi = 100 * self.pdm / self.tr, 100 * self.mdm / self.tr
            tot = self.pdi + self.mdi
            dx = 100 * abs(self.pdi - self.mdi) / tot if tot > 0 else 0.0
            self.k += 1
            self.adx = dx if self.k == 1 else self.adx + (dx - self.adx) / n
        self.ph, self.pl, self.pc = h, l, c
        return self.adx


def _monday_long(b, tf, i0, i1, p, filt):
    """Monday Long v2.1 (idea 644): on 5m Globex bars, buy at the close of Sunday's 19:00 CT bar and sell
    at the close of Monday's 15:55 bar; 100-point target, no stop; Mondays that are NYSE closures or early
    closes skipped. filt "adx": yesterday's RTH ADX(7) in [10, 50) and DI+ > DI- (NQ version);
    "ema": (close - EMA200 of the 5m closes) / yesterday's RTH Wilder ATR14 in [-0.75, 0.75) (ES version).
    The daily data are the 08:35-15:00 CT bars, close at 15:00 (12:00 on half days), skipped on closures."""
    O, H, L, C, V, CA = b.o, b.h, b.l, b.c, b.v, b.cabs
    eng = Engine(CA, p["tick"])
    tfb = TFBars(tf)
    closures, early = nyse_calendar()
    entry_t, exit_t = int(p.get("ml_entry", 1900)), int(p.get("ml_exit", 1555))
    tgt = float(p.get("ml_target", 100))
    stop = float(p.get("ml_stop", 0))
    adx_len = int(p.get("ml_adx_len", 7))
    adx_min, adx_max = float(p.get("ml_adx_min", 10)), float(p.get("ml_adx_max", 50))
    max_bars = int(p.get("ml_max_bars", 192 if filt == "fri" else 0))
    trade_dow = int(p.get("ml_dow", 1))           # session weekday to trade (1 = Monday, paper)
    # Triple Open v2 options (all off by default = paper rules)
    adx_lt = float(p.get("ml_adx_lt", 0))          # extra: prev RTH ADX(7) < x (0 = off)
    wk_min = p.get("ml_wk_min")                    # extra: (prev close - close 5 RTH days earlier) / ATR >= x
    chase = float(p.get("ml_chase", 0))            # extra: (entry close - session open) / ATR < x (0 = off)
    skip_last = int(p.get("ml_skip_lastmon", 0))   # skip the last Monday of the month
    tp_atr = float(p.get("ml_tp_atr", 0))          # target = x * ATR14 (replaces ml_target; 0 = off)
    lock_t = int(p.get("ml_lock_t", 0))            # from this Monday time, exit at the first bar close
    lock_atr = float(p.get("ml_lock_atr", 0))      #   with open profit >= x * ATR14 (0 = off)
    closes = []
    sess_open = None
    atr_e = 0.0
    ema_len = int(p.get("ml_ema_len", 200))
    dmin, dmax = float(p.get("ml_dist_min", -0.75)), float(p.get("ml_dist_max", 0.75))
    alpha = 2.0 / (ema_len + 1)
    ema = None
    pt = None                                      # previous 5m bar (time, day)
    has830 = has1200 = has1500 = is_hol = False
    first_rth = True
    c1200 = c1500 = rth_h = rth_l = rth_o = 0.0
    prev_close = prev_open = 0.0
    bars_in = 0
    has_prev = False
    atr = 0.0
    atr_n = 0
    prev_atr = 0.0
    prev_rh = prev_rl = 0.0
    trsm = dmusm = dmdsm = 0.0
    dir_n = dx_n = 0
    adxsm = 0.0
    diu = did = 0.0
    prev_adx, prev_didiff = -1.0, 0.0
    for i in range(i0, i1):
        o, h, l, c = O[i], H[i], L[i], C[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        closed = tfb.update(CA[i], o, h, l, c, V[i])
        if closed:
            for end, bo, bh, bl, bc, bv in closed:
                t, d = hhmm(end), end // 1440
                ema = bc if ema is None else ema + alpha * (bc - ema)
                new_sess = pt is not None and t > 1630 and (pt[0] <= 1630 or pt[1] != d)
                if new_sess:
                    if has830 and (has1200 or has1500) and not is_hol and not first_rth:
                        today_close = c1500 if has1500 else c1200
                        trh, trl = rth_h, rth_l
                        if has_prev:
                            trh, trl = max(trh, prev_close), min(trl, prev_close)
                        day_tr = trh - trl
                        atr = day_tr if atr_n == 0 else atr + (day_tr - atr) / 14
                        atr_n += 1
                        dmu = dmd = 0.0
                        if has_prev:
                            upmv, dnmv = rth_h - prev_rh, prev_rl - rth_l
                            if upmv > dnmv and upmv > 0:
                                dmu = upmv
                            if dnmv > upmv and dnmv > 0:
                                dmd = dnmv
                        if dir_n == 0:
                            trsm, dmusm, dmdsm = day_tr, dmu, dmd
                        else:
                            trsm += (day_tr - trsm) / adx_len
                            dmusm += (dmu - dmusm) / adx_len
                            dmdsm += (dmd - dmdsm) / adx_len
                        dir_n += 1
                        valid = False
                        if dir_n >= adx_len and trsm > 0:
                            diu, did = 100 * dmusm / trsm, 100 * dmdsm / trsm
                            if diu + did > 0:
                                dx = 100 * abs(diu - did) / (diu + did)
                                valid = True
                        if valid:
                            adxsm = dx if dx_n == 0 else adxsm + (dx - adxsm) / adx_len
                            dx_n += 1
                        if dx_n >= adx_len:
                            prev_adx, prev_didiff = adxsm, diu - did
                        else:
                            prev_adx = -1.0
                        prev_rh, prev_rl = rth_h, rth_l
                        prev_close, prev_open = today_close, rth_o
                        closes.append(today_close)
                        has_prev = True
                        prev_atr = atr if atr_n >= 14 else 0.0
                    has830 = has1200 = has1500 = is_hol = False
                    first_rth = True
                if new_sess or pt is None:
                    sess_open = bo
                if t == 830:
                    has830 = True
                    is_hol = d in closures
                if 830 < t <= 1500:
                    if first_rth:
                        rth_h, rth_l, rth_o, first_rth = bh, bl, bo, False
                    else:
                        rth_h, rth_l = max(rth_h, bh), min(rth_l, bl)
                if t == 1200:
                    has1200, c1200 = True, bc
                if t == 1500:
                    has1500, c1500 = True, bc
                if t > 1630:
                    sdow, sdate = date_dow(d) + 1, d + 1      # after 16:30 = next day's session
                else:
                    sdow, sdate = date_dow(d), d
                no_trade = sdate in closures or sdate in early
                if t == entry_t and sdow == trade_dow and eng.pos == 0 and not no_trade:
                    if filt == "fri":
                        ok = has_prev and prev_close > prev_open
                    elif filt == "adx":
                        ok = prev_adx >= 0 and adx_min <= prev_adx < adx_max and prev_didiff > 0
                    else:
                        ok = prev_atr > 0 and dmin <= (bc - ema) / prev_atr < dmax
                    if ok and adx_lt > 0:
                        ok = 0 <= prev_adx < adx_lt
                    if ok and wk_min is not None:
                        ok = prev_atr > 0 and len(closes) > 5 and (closes[-1] - closes[-6]) / prev_atr >= float(wk_min)
                    if ok and chase > 0:
                        ok = prev_atr > 0 and sess_open is not None and (bc - sess_open) / prev_atr < chase
                    if ok and skip_last:
                        ok = date.fromordinal(sdate + 7).month == date.fromordinal(sdate).month
                    if ok and (tp_atr > 0 or lock_atr > 0) and prev_atr <= 0:
                        ok = False
                    if ok:
                        atr_e = prev_atr
                        eng._open(i, 1, bc, "MonLong")
                        bars_in = 0
                        pt = (t, d)
                        continue
                if eng.pos != 0:
                    bars_in += 1
                    if exit_t <= t <= 1630:
                        eng._close(i, bc, MKT, "Time.LX")
                    elif lock_atr > 0 and lock_t <= t <= 1630 and bc - eng.entry_px >= lock_atr * atr_e:
                        eng._close(i, bc, MKT, "Lock.LX")
                    elif max_bars > 0 and bars_in >= max_bars:
                        eng._close(i, bc, MKT, "Bars.LX")
                pt = (t, d)
        if eng.pos == 1:
            if tp_atr > 0:
                eng.order(LIMIT, XLONG, eng.entry_px + tp_atr * atr_e, "TP")
            elif tgt > 0:
                eng.order(LIMIT, XLONG, eng.entry_px + tgt, "TP")
            if stop > 0:
                eng.order(STOP, XLONG, eng.entry_px - stop, "SL")
    return eng


def date_dow(day):
    """PowerLanguage DayOfWeek of a day ordinal: 0 = Sunday ... 6 = Saturday."""
    return day % 7


def s11_monday_nq_adx(b, tf, i0, i1, p):
    return _monday_long(b, tf, i0, i1, p, "adx")


def s12_monday_es_ema(b, tf, i0, i1, p):
    return _monday_long(b, tf, i0, i1, p, "ema")


def s16_monday_fri_up(b, tf, i0, i1, p):
    """Triple Open L656ES: Monday Long after an up Friday (last RTH close > its 08:30 open), exit after
    ml_max_bars signal bars (192 = Mon ~11:00 on 5m) or 15:55, 100-pt target, no stop."""
    return _monday_long(b, tf, i0, i1, p, "fri")


def s13_overnight_bias_orb(b, tf, i0, i1, p):
    """Overnight Bias ORB (OFB), NQ 15m Globex bars, CT times. The day starts at midnight CT (Date change);
    overnight range = bars closing up to 08:30; the 08:30 open's place in it sets the bias (>= 0.67 long only,
    <= 0.33 short only, else no trade). OR = 08:30-08:45. Entry on a 15m close beyond the OR in the bias
    direction, 08:45-12:00, ADX(16) >= 20, signal bar range <= 2.5 x the prior 20-bar average, OR size
    <= 2 x its 20-day EMA, max 4 a day. Stop 0.30 x 15-day mean RTH true range from the signal close,
    target 3R, both live from the fill; flat on the next bar after the 14:30 close.
    Improvements (0 = off, the original), as in the final PowerLanguage (IOG off, 1-minute magnifier):
    ob_be_r = on a 15m close, stop to entry once the best price since the fill is ob_be_r R in profit.
    ob_add_r = 2nd contract on a stop order ob_add_r R beyond the first entry, armed from the first 15m close
    after the fill, once per trade; its stop is the tightest of: the first leg's stop, the first entry, and
    ob_add_stop_r R behind its own fill (0 = not used); same target and flat time. ob_add_last = no add after
    this hhmm (0 = any time). ob_lock_r = when the 2nd contract is on, the first leg's stop goes to entry +
    ob_lock_r R (0 = off). The add-on's trades are appended, so they overlap the first leg's.
"""
    O, H, L, C, V, T, D, CA = b.o, b.h, b.l, b.c, b.v, b.hhmm, b.day, b.cabs
    eng = Engine(CA, p["tick"])
    tfb = TFBars(tf)
    sess_start, or_end = int(p.get("ob_start", 830)), int(p.get("ob_or_end", 845))
    last_entry, flat_t, sess_end = int(p.get("ob_last", 1200)), int(p.get("ob_flat", 1430)), int(p.get("ob_end", 1500))
    max_tr = int(p.get("ob_max_trades", 4))
    bias_l, bias_s = float(p.get("ob_bias_long", 0.67)), float(p.get("ob_bias_short", 0.33))
    adx_min = float(p.get("ob_adx_min", 20))
    skip_mult, avg_len = float(p.get("ob_skip_mult", 2.5)), int(p.get("ob_bar_avg", 20))
    min_orx, max_orx, or_days = float(p.get("ob_min_orx", 0)), float(p.get("ob_max_orx", 2)), int(p.get("ob_or_days", 20))
    atr_k, atr_days, rr = float(p.get("ob_atr_k", 0.30)), int(p.get("ob_atr_days", 15)), float(p.get("ob_rr", 3))
    adx = WilderADX(int(p.get("ob_adx_len", 16)))
    rngs = []
    prev_d = None
    or_hi, or_lo, or_done = 0.0, 999999.0, False
    trades_today = 0
    sess_open = 0.0
    on_hi, on_lo = 0.0, 999999.0
    bias = 0
    or_med, or_cnt = 0.0, 0
    regime_ok = True
    stop_px = tgt_px = 0.0
    a_hi, a_lo, a_cl, a_seen, a_prev = 0.0, 999999.0, 0.0, False, 0.0
    tr_buf = []
    atr_ref, atr_ok = 0.0, False
    flat_sent = False
    be_r = float(p.get("ob_be_r", 0))
    add_r, add_stop_r = float(p.get("ob_add_r", 0)), float(p.get("ob_add_stop_r", 0))
    add_last, lock_r = int(p.get("ob_add_last", 0)), float(p.get("ob_lock_r", 0))
    eng2 = Engine(CA, p["tick"]) if add_r else None
    added = armed = False
    s2 = 0.0
    risk = 0.0
    best = None
    for i in range(i0, i1):
        o, h, l, c = O[i], H[i], L[i], C[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        if eng2 is not None:
            if eng2.orders:
                eng2.fill(i, o, h, l)
            if eng.pos == 0 and eng2.pos != 0 and not eng2.orders:
                eng2.order(MKT, XLONG if eng2.pos == 1 else XSHORT, None, "X2")
        if eng.pos == 0:
            flat_sent = False
            best = None
            added = armed = False
        closed = tfb.update(CA[i], o, h, l, c, V[i])
        if closed:
            for end, bo, bh, bl, bc, bv in closed:
                t, d = hhmm(end), end // 1440
                if d != prev_d:
                    if a_seen:
                        tv = a_hi - a_lo
                        if a_prev > 0:
                            tv = max(tv, abs(a_hi - a_prev), abs(a_lo - a_prev))
                        tr_buf.append(tv)
                        if len(tr_buf) > atr_days:
                            del tr_buf[0]
                        a_prev = a_cl
                    a_hi, a_lo, a_cl, a_seen = 0.0, 999999.0, 0.0, False
                    atr_ok = len(tr_buf) >= atr_days
                    atr_ref = sum(tr_buf) / atr_days if atr_ok else 0.0
                    or_hi, or_lo, or_done = 0.0, 999999.0, False
                    trades_today = 0
                    sess_open, bias = 0.0, 0
                    on_hi, on_lo = bh, bl
                    prev_d = d
                elif t <= sess_start:
                    on_hi, on_lo = max(on_hi, bh), min(on_lo, bl)
                if sess_start < t <= sess_end:
                    if not a_seen:
                        a_hi, a_lo, a_seen = bh, bl, True
                    else:
                        a_hi, a_lo = max(a_hi, bh), min(a_lo, bl)
                    a_cl = bc
                if sess_open == 0 and sess_start < t <= or_end:
                    sess_open = bo
                    if on_hi > on_lo:
                        onp = (sess_open - on_lo) / (on_hi - on_lo)
                        bias = 1 if onp >= bias_l else (-1 if onp <= bias_s else 9)
                if sess_start < t <= or_end:
                    or_hi, or_lo = max(or_hi, bh), min(or_lo, bl)
                if not or_done and t > or_end and or_hi > 0:
                    or_done = True
                    regime_ok = True
                    w = or_hi - or_lo
                    if or_med > 0:
                        regime_ok = min_orx * or_med <= w <= max_orx * or_med
                    or_med = w if or_med == 0 else or_med + (2.0 / (or_days + 1)) * (w - or_med)
                    or_cnt += 1
                    if or_cnt < or_days:
                        regime_ok = True
                stop_pts = atr_k * atr_ref
                adx_v = adx.update(bh, bl, bc)
                avg_rng = sum(rngs) / avg_len if len(rngs) >= avg_len else 0.0
                rngs.append(bh - bl)
                if len(rngs) > avg_len:
                    del rngs[0]
                bar_ok = avg_rng == 0 or (bh - bl) <= skip_mult * avg_rng
                can = or_done and regime_ok and adx_v >= adx_min and atr_ok and stop_pts > 0 \
                    and or_end < t <= last_entry and eng.pos == 0 and trades_today < max_tr
                if can:
                    if bc > or_hi:
                        if bar_ok and bias == 1:
                            stop_px, tgt_px = bc - stop_pts, bc + stop_pts * rr
                            risk = stop_pts
                            eng.order(MKT, BUY, None, "ORB_L")
                            eng.order(STOP, XLONG, stop_px, "L-SL")
                            eng.order(LIMIT, XLONG, tgt_px, "L-TP")
                            trades_today += 1
                    elif bc < or_lo:
                        if bar_ok and bias == -1:
                            stop_px, tgt_px = bc + stop_pts, bc - stop_pts * rr
                            risk = stop_pts
                            eng.order(MKT, SHORT, None, "ORB_S")
                            eng.order(STOP, XSHORT, stop_px, "S-SL")
                            eng.order(LIMIT, XSHORT, tgt_px, "S-TP")
                            trades_today += 1
                if eng.pos != 0 and risk > 0 and not flat_sent:
                    sd = eng.pos
                    ext = bh if sd == 1 else bl
                    best = ext if best is None else (max(best, ext) if sd == 1 else min(best, ext))
                    if be_r and (best - eng.entry_px) * sd >= be_r * risk:
                        stop_px = max(stop_px, eng.entry_px) if sd == 1 else min(stop_px, eng.entry_px)
                    if eng2 is not None:
                        armed = True
                        if eng2.pos == sd:
                            if lock_r:
                                lk = eng.entry_px + sd * lock_r * risk
                                stop_px = max(stop_px, lk) if sd == 1 else min(stop_px, lk)
                            cand = [stop_px, eng.entry_px] + ([eng2.entry_px - sd * add_stop_r * risk] if add_stop_r else [])
                            s2 = max(cand) if sd == 1 else min(cand)
                ft = flat_t
                if eng.pos != 0 and t >= ft and not flat_sent:
                    eng.order(MKT, XLONG if eng.pos == 1 else XSHORT, None, "XL" if eng.pos == 1 else "XS")
                    flat_sent = True
        if eng.pos != 0 and not flat_sent:
            sd = eng.pos
            xa = XLONG if sd == 1 else XSHORT
            if eng2 is not None and armed and not added and eng2.pos == 0 and (not add_last or T[i] <= add_last):
                apx = eng._to_tick(STOP, XSHORT if sd == 1 else XLONG, eng.entry_px + sd * add_r * risk)
                if (o - apx) * sd >= 0:
                    eng2._open(i, sd, o, "ADD")
                    added = True
                elif ((h if sd == 1 else l) - apx) * sd >= 0:
                    eng2._open(i, sd, apx, "ADD")
                    added = True
                if added:
                    cand = [stop_px, eng.entry_px] + ([eng2.entry_px - sd * add_stop_r * risk] if add_stop_r else [])
                    s2 = max(cand) if sd == 1 else min(cand)
            eng.order(STOP, xa, stop_px, "SL")
            eng.order(LIMIT, xa, tgt_px, "TP")
            if eng2 is not None and eng2.pos == sd:
                eng2.order(STOP, xa, s2, "SL2")
                eng2.order(LIMIT, xa, tgt_px, "TP2")
        elif eng2 is not None and eng2.pos != 0 and flat_sent and not eng2.orders:
            eng2.order(MKT, XLONG if eng2.pos == 1 else XSHORT, None, "X2")
    if eng2 is not None:
        eng.trades = sorted(eng.trades + eng2.trades)
    return eng


def s14_drift_pullback(b, tf, i0, i1, p):
    """Drift Pullback v2.1 (F. Agnello), NQ: data1 = tf-minute bars (5), data2 = 15m signal bars, CT.
    Session VWAP of the 15m bars closing 08:45-15:00 CT is the anchor, frozen per 15m bar. On each new 15m
    bar: long armed if close > VWAP, VWAP rising and the 4-bar drift >= +0.10% (short mirrored), else
    disarmed. Entry on a down 5m bar (up bar for shorts) while armed, 09:30-14:30 CT, max 4 trades and
    2 losers a day. Exits from the first 5m close in the trade: stop 80 pts (+2 ticks), target 40 long /
    50 short; flat on the next bar after 14:55."""
    O, H, L, C, V, T, D, CA = b.o, b.h, b.l, b.c, b.v, b.hhmm, b.day, b.cabs
    tick = p["tick"]
    eng = Engine(CA, tick)
    t1, t2b = TFBars(tf), TFBars(int(p.get("dp_tf2", 15)))
    drift_len, drift_thr = int(p.get("dp_drift_len", 4)), float(p.get("dp_drift_pct", 0.10))
    pb_win = int(p.get("dp_pb_window", 6))
    lsl, ltp = float(p.get("dp_long_sl", 80)), float(p.get("dp_long_tp", 40))
    ssl, stp = float(p.get("dp_short_sl", 80)), float(p.get("dp_short_tp", 50))
    slip = float(p.get("dp_stop_slip_ticks", 2)) * tick
    longs, shorts = bool(p.get("dp_longs", 1)), bool(p.get("dp_shorts", 1))
    max_tr, max_loss = int(p.get("dp_max_trades", 4)), int(p.get("dp_max_losses", 2))
    s_start, s_end, flat_t = int(p.get("dp_start", 930)), int(p.get("dp_end", 1430)), int(p.get("dp_flat", 1455))
    vw_start, vw_end = int(p.get("dp_vwap_start", 830)), int(p.get("dp_vwap_end", 1500))
    # Revamp options (2026-11-07), defaults = the v2.1 original:
    #  dp_drift_atr = k > 0: drift test in points vs k x Wilder ATR(14) of the 15m bars instead of % (scale-free,
    #                 immune to the back-adjustment, which turns 0.10% into ~0.18% in 2016)
    #  dp_exit_atr = 1: stop / target = dp_sl_atr / dp_tp_atr x the 15m ATR frozen at the signal
    #  dp_tp_off = 1: no target, exit at flat time (or on the stop / the anchor exit)
    #  dp_anchor_exit = 1: exit at market when a 15m bar closes on the wrong side of the anchor
    #  dp_be_pts > 0: move the stop to entry once the trade has been this many points in profit (bar close)
    #  dp_min_day_pts > 0: arm only if |15m close - session open (08:30)| >= this x 15m ATR (day already trending)
    #  dp_dow_skip: weekdays (0=Mon) not traded, e.g. "4"
    drift_atr = float(p.get("dp_drift_atr", 0))
    exit_atr = int(p.get("dp_exit_atr", 0))
    sl_atr, tp_atr = float(p.get("dp_sl_atr", 3.0)), float(p.get("dp_tp_atr", 1.5))
    stp_atr = float(p.get("dp_stp_atr", tp_atr))
    tp_off = int(p.get("dp_tp_off", 0))
    anchor_exit = int(p.get("dp_anchor_exit", 0))
    be_pts = float(p.get("dp_be_pts", 0))
    min_day = float(p.get("dp_min_day_atr", 0))
    dow_skip = {int(x) for x in str(p.get("dp_dow_skip", "")).split(",") if x.strip() != ""}
    atr2 = 0.0
    atr_n = 0
    prev_c2 = None
    day_open = None
    x_sl = x_tp = 0.0
    be_on = False
    d2 = []                                        # completed 15m bars (end, o, h, l, c, v), last 10
    seen2 = 0
    n2 = 0
    prev_d = None
    trades_today = losses_today = 0
    l_arm = s_arm = False
    armed = 0
    prev_mp = 0
    n_closed = 0
    spv = svol = svwap = svl = svp = 0.0
    exit_live = False
    for i in range(i0, i1):
        o, h, l, c = O[i], H[i], L[i], C[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        c2 = t2b.update(CA[i], o, h, l, c, V[i])
        if c2:
            for _e, _o, _h, _l, _c, _v in c2:
                tr = _h - _l if prev_c2 is None else max(_h, prev_c2) - min(_l, prev_c2)
                atr_n += 1
                atr2 = tr if atr_n == 1 else (atr2 + (tr - atr2) / min(atr_n, 14))
                prev_c2 = _c
                if hhmm(_e) == 845:
                    day_open = _o
            d2.extend(c2)
            n2 += len(c2)
            if len(d2) > 10:
                del d2[:-10]
        closed = t1.update(CA[i], o, h, l, c, V[i])
        if closed:
            for end, bo, bh, bl, bc, bv in closed:
                t, d = hhmm(end), end // 1440
                if d != prev_d:
                    trades_today = losses_today = 0
                    l_arm = s_arm = False
                    armed = 0
                    spv = svol = svwap = svl = svp = 0.0
                    prev_d = d
                new2 = n2 != seen2 and len(d2) > 0
                if new2:
                    seen2 = n2
                    svp = svl
                    e2, o2, h2, l2, cl2, v2 = d2[-1]
                    if vw_start < hhmm(e2) <= vw_end:
                        spv += (h2 + l2 + cl2) / 3 * v2
                        svol += v2
                    if svol > 0:
                        svwap = spv / svol
                    svl = svwap
                ma2 = svl
                ma2p = svp if svp > 0 else ma2
                drift = None
                thr = drift_thr
                if len(d2) > drift_len and d2[-1 - drift_len][4] != 0:
                    ref = d2[-1 - drift_len][4]
                    if drift_atr > 0:
                        drift, thr = d2[-1][4] - ref, drift_atr * atr2
                    else:
                        drift = (d2[-1][4] - ref) / ref * 100
                if new2:
                    cl2 = d2[-1][4]
                    if anchor_exit and eng.pos != 0 and ma2 > 0 and (cl2 - ma2) * eng.pos < 0:
                        eng.order(MKT, XLONG if eng.pos == 1 else XSHORT, None, "AnchorX")
                    dok = True
                    if min_day > 0:
                        dok = day_open is not None and abs(cl2 - day_open) >= min_day * atr2
                    if dow_skip and date_dow(d) in dow_skip:
                        dok = False
                    if dok and ma2 > 0 and drift is not None and cl2 > ma2 and ma2 > ma2p and drift >= thr:
                        l_arm, s_arm, armed = True, False, 0
                    elif dok and ma2 > 0 and drift is not None and cl2 < ma2 and ma2 < ma2p and drift <= -thr:
                        s_arm, l_arm, armed = True, False, 0
                    else:
                        l_arm = s_arm = False
                if l_arm or s_arm:
                    armed += 1
                    if armed > pb_win:
                        l_arm = s_arm = False
                if len(eng.trades) > n_closed:
                    lt = eng.trades[-1]
                    if lt[2] * (lt[4] - lt[3]) <= 0:          # PositionProfit(1) < 0 (net of commission)
                        losses_today += 1
                    n_closed = len(eng.trades)
                mp = eng.pos
                if mp != 0 and prev_mp == 0:
                    trades_today += 1
                prev_mp = mp
                if mp == 0 and s_start <= t < s_end and trades_today < max_tr and losses_today < max_loss:
                    if longs and l_arm and bc < bo:
                        eng.order(MKT, BUY, None, "DriftPB.L")
                        l_arm = False
                        x_sl, x_tp, be_on = sl_atr * atr2, tp_atr * atr2, False
                    if shorts and s_arm and bc > bo:
                        eng.order(MKT, SHORT, None, "DriftPB.S")
                        s_arm = False
                        x_sl, x_tp, be_on = sl_atr * atr2, stp_atr * atr2, False
                if mp != 0 and be_pts > 0 and not be_on and (bc - eng.entry_px) * mp >= be_pts:
                    be_on = True
                exit_live = mp != 0
                if mp != 0 and t >= flat_t:
                    eng.order(MKT, XLONG if mp == 1 else XSHORT, None, "Flat")
        if eng.pos != 0 and exit_live:
            ep = eng.entry_px
            if exit_atr:
                a_sl, a_ltp, a_stp = x_sl, x_tp, x_tp
            else:
                a_sl, a_ltp, a_stp = None, ltp, stp
            if eng.pos == 1:
                sl_px = ep - (a_sl if a_sl is not None else lsl) - slip
                if be_on:
                    sl_px = max(sl_px, ep)
                eng.order(STOP, XLONG, sl_px, "L.SL" if not be_on else "L.BE")
                if not tp_off:
                    eng.order(LIMIT, XLONG, ep + a_ltp, "L.TP")
            else:
                sl_px = ep + (a_sl if a_sl is not None else ssl) + slip
                if be_on:
                    sl_px = min(sl_px, ep)
                eng.order(STOP, XSHORT, sl_px, "S.SL" if not be_on else "S.BE")
                if not tp_off:
                    eng.order(LIMIT, XSHORT, ep - a_stp, "S.TP")
        elif eng.pos == 0:
            exit_live = False
    return eng

def s17_drift_revamp(b, tf, i0, i1, p):
    """Drift Pullback, revamped from zero (2026-11-07), NQ, CT, RTH 08:30-15:00. Scale-free: every distance
    is a multiple of dATR = mean RTH range (high-low) of the last rv_atr_n sessions, so the back-adjustment
    does not matter. VWAP = session VWAP of the 1-minute bars from 08:30 (real time).
    Drift (known at each tf-bar close): d = (close - ref) / dATR, ref = today's 08:30 open (rv_ref=open) or
    the previous RTH close (rv_ref=prev, Baltussen et al.'s rest-of-day return). Long setup when d >= rv_k,
    close above VWAP and (rv_slope=1) VWAP higher than rv_slope_n tf bars ago; short mirrored.
    Entry (rv_entry): "bar"  = first tf bar against the drift, market on the next minute (the original trigger);
                      "vwap" = limit at VWAP + rv_pb x dATR (long; mirrored), refreshed each minute while set up;
                      "mkt"  = market as soon as the setup holds;
                      "time" = market at the first bar close >= rv_time if the setup holds then.
    Window rv_start..rv_end (bar close times), at most rv_max entries a day, one side per day (rv_one_side).
    Stop: rv_sl x dATR from the fill (rv_sl_vwap=1: rv_sl x dATR beyond the VWAP at entry instead), plus
    rv_slip ticks; target rv_tp x dATR (0 = none); rv_vx=1: exit at market when a tf bar closes back across
    VWAP; rv_be = move the stop to entry once a bar closes rv_be x dATR in profit (0 = off); flat at market
    on the minute after the rv_flat (14:55) bar close.
    Squeeze options (2026-11-07, off by default): rv_trail = trail the stop rv_trail x dATR behind the best bar
    high/low once the trade is rv_trail_on x dATR up (default rv_be); rv_add = add a 2nd contract (own engine) at
    market when a bar closes rv_add x dATR in profit, before rv_add_last, sharing the first one's stop (which is at
    breakeven or better by then) and exits; rv_news = skip entries on these news days ("cpi,nfp,fomc");
    rv_gap_max = skip days whose |08:30 open - previous close| > this x dATR; rv_vol_lo / rv_vol_hi = trade only
    when dATR / its median of the last 250 sessions is within these bounds; rv_sl_max = stop distance capped at
    this many points; rv_dow = weekdays traded (PowerLanguage 1=Mon..5=Fri, e.g. "1,2,3,4")."""
    O, H, L, C, V, T, D, CA = b.o, b.h, b.l, b.c, b.v, b.hhmm, b.day, b.cabs
    tick = p["tick"]
    eng = Engine(CA, tick)
    tb = TFBars(tf)
    trail = float(p.get("rv_trail", 0))
    trail_on = float(p.get("rv_trail_on", p.get("rv_be", 0)))
    add = float(p.get("rv_add", 0))
    add_last = int(p.get("rv_add_last", 1400))
    eng2 = Engine(CA, tick) if add > 0 else None
    added = False
    news = set()
    if p.get("rv_news"):
        import news_calendar
        news = news_calendar.days(p["rv_news"])
    gap_max = float(p.get("rv_gap_max", 0))
    vol_lo, vol_hi = float(p.get("rv_vol_lo", 0)), float(p.get("rv_vol_hi", 0))
    sl_max = float(p.get("rv_sl_max", 0))
    dows = {int(x) for x in str(p.get("rv_dow", "")).split(",") if x.strip()}
    dat_hist = []
    day_ok = True
    best = None
    k = float(p.get("rv_k", 0.3))
    ref_mode = p.get("rv_ref", "open")
    slope, slope_n = int(p.get("rv_slope", 1)), int(p.get("rv_slope_n", 3))
    need_vw = int(p.get("rv_vwap", 1))
    mode = p.get("rv_entry", "bar")
    pb = float(p.get("rv_pb", 0.05))
    t_at = int(p.get("rv_time", 1400))
    s_start, s_end = int(p.get("rv_start", 930)), int(p.get("rv_end", 1400))
    max_tr = int(p.get("rv_max", 1))
    one_side = int(p.get("rv_one_side", 1))
    sl, tp = float(p.get("rv_sl", 0.35)), float(p.get("rv_tp", 0))
    sl_vwap = int(p.get("rv_sl_vwap", 0))
    slip = float(p.get("rv_slip", 0)) * tick
    vx, be = int(p.get("rv_vx", 0)), float(p.get("rv_be", 0))
    flat_t = int(p.get("rv_flat", 1455))
    atr_n = int(p.get("rv_atr_n", 14))
    longs, shorts = bool(p.get("rv_longs", 1)), bool(p.get("rv_shorts", 1))
    k_short = float(p.get("rv_k_short", k))            # drift threshold for shorts (default = rv_k)
    k_open = float(p.get("rv_k_open", -99))           # also need (close - 08:30 open) / dATR >= this (mirrored)
    rngs = []                                         # last RTH ranges
    d_hi = d_lo = None
    prev_close = None
    last_close = None
    cur_d = None
    d_open = None
    pv = vv = 0.0
    vwap = 0.0
    vw_hist = []
    trades = 0
    side_today = 0
    setup = 0                                         # +1 long / -1 short setup at the last bar close
    want_bar = 0
    stop_px = tgt_px = None
    be_on = False
    lim_px = None
    for i in range(i0, i1):
        o, h, l, c, t, d = O[i], H[i], L[i], C[i], T[i], D[i]
        rth = 830 < t <= 1500
        if eng.orders:
            eng.fill(i, o, h, l)
        if eng2 is not None:
            if eng2.orders:
                eng2.fill(i, o, h, l)
            if eng.pos == 0 and eng2.pos != 0 and not eng2.orders:
                eng2.order(MKT, XLONG if eng2.pos == 1 else XSHORT, None, "X2")
        if lim_px is not None and eng.pos == 0 and rth:
            sd = setup
            if sd == 1 and l <= lim_px:
                eng._open(i, 1, min(o, lim_px), "DPR.L")
                eng.entry_kind = LIMIT
            elif sd == -1 and h >= lim_px:
                eng._open(i, -1, max(o, lim_px), "DPR.S")
                eng.entry_kind = LIMIT
            if eng.pos != 0:
                lim_px = None
                trades += 1
                side_today = eng.pos
                dat = sum(rngs) / len(rngs)
                base = vwap if sl_vwap else eng.entry_px
                stop_px = base - eng.pos * (sl * dat + slip)
                tgt_px = eng.entry_px + eng.pos * tp * dat if tp > 0 else None
                be_on = False
        if eng.pos != 0 and eng.entry_i == i and eng.entry_kind == MKT and stop_px is None:
            dat = sum(rngs) / len(rngs)
            base = vwap if sl_vwap else eng.entry_px
            dist = sl * dat
            if sl_max > 0:
                dist = min(dist, sl_max)
            stop_px = base - eng.pos * (dist + slip)
            best = eng.entry_px
            added = False
            tgt_px = eng.entry_px + eng.pos * tp * dat if tp > 0 else None
            be_on = False
        if not rth:
            if t == 1500 or (t > 1500 and cur_d == d):
                pass
            continue
        if d != cur_d:                                # first RTH minute of a new day
            if d_hi is not None:
                rngs.append(d_hi - d_lo)
                if len(rngs) > atr_n:
                    del rngs[0]
                prev_close = last_close
                if len(rngs) >= atr_n:
                    dat_hist.append(sum(rngs) / len(rngs))
                    if len(dat_hist) > 250:
                        del dat_hist[0]
            day_ok = d not in news and (not dows or date_dow(d) in dows)
            if day_ok and len(rngs) >= atr_n:
                dat0 = sum(rngs) / len(rngs)
                if gap_max > 0 and last_close is not None and abs(o - last_close) > gap_max * dat0:
                    day_ok = False
                if (vol_lo or vol_hi) and len(dat_hist) >= 60:
                    med = sorted(dat_hist)[len(dat_hist) // 2]
                    if vol_lo and dat0 < vol_lo * med:
                        day_ok = False
                    if vol_hi and dat0 > vol_hi * med:
                        day_ok = False
            cur_d = d
            d_hi, d_lo = h, l
            d_open = o
            pv = vv = 0.0
            vw_hist = []
            trades = 0
            side_today = 0
            setup = 0
            lim_px = None
        else:
            d_hi, d_lo = max(d_hi, h), min(d_lo, l)
        last_close = c
        tp_ = (h + l + c) / 3
        pv += tp_ * V[i]
        vv += V[i]
        if vv > 0:
            vwap = pv / vv
        closed = tb.update(CA[i], o, h, l, c, V[i])
        ready = len(rngs) >= atr_n
        if closed and ready:
            for end, bo, bh, bl, bc, bv in closed:
                bt = hhmm(end)
                vw_hist.append(vwap)
                dat = sum(rngs) / len(rngs)
                ref = d_open if ref_mode == "open" else prev_close
                setup = 0
                if ref is not None and dat > 0:
                    dr = (bc - ref) / dat
                    up_s = len(vw_hist) > slope_n and vwap > vw_hist[-1 - slope_n]
                    dn_s = len(vw_hist) > slope_n and vwap < vw_hist[-1 - slope_n]
                    do = (bc - d_open) / dat
                    if dr >= k and do >= k_open and (not need_vw or bc > vwap) and (not slope or up_s) and longs:
                        setup = 1
                    elif dr <= -k_short and do <= -k_open and (not need_vw or bc < vwap) and (not slope or dn_s) and shorts:
                        setup = -1
                    if one_side and side_today and setup != side_today:
                        setup = 0
                # exits on the bar close
                if eng.pos != 0:
                    if vx and (bc - vwap) * eng.pos < 0:
                        eng.order(MKT, XLONG if eng.pos == 1 else XSHORT, None, "VWAPx")
                    if be > 0 and not be_on and (bc - eng.entry_px) * eng.pos >= be * dat:
                        be_on = True
                        stop_px = eng.entry_px if eng.pos == 1 else eng.entry_px
                    sd_ = eng.pos
                    if best is not None:
                        best = max(best, bh) if sd_ == 1 else min(best, bl)
                        if trail > 0 and (best - eng.entry_px) * sd_ >= trail_on * dat and stop_px is not None:
                            tsp = best - sd_ * trail * dat
                            if (tsp - stop_px) * sd_ > 0:
                                stop_px = tsp
                                be_on = True
                    if (eng2 is not None and not added and eng2.pos == 0 and bt < add_last and bt < flat_t
                            and (bc - eng.entry_px) * sd_ >= add * dat):
                        eng2.order(MKT, BUY if sd_ == 1 else SHORT, None, "ADD")
                        added = True
                    if bt >= flat_t:
                        eng.order(MKT, XLONG if eng.pos == 1 else XSHORT, None, "Flat")
                        if eng2 is not None and eng2.pos != 0:
                            eng2.order(MKT, XLONG if eng2.pos == 1 else XSHORT, None, "Flat2")
                # entries
                lim_px = None
                if eng.pos == 0 and setup and day_ok and trades < max_tr and s_start <= bt < s_end:
                    go = (mode == "mkt" or (mode == "bar" and (bc - bo) * setup < 0)
                          or (mode == "time" and bt >= t_at))
                    if go:
                        eng.order(MKT, BUY if setup == 1 else SHORT, None, "DPR.L" if setup == 1 else "DPR.S")
                        trades += 1
                        side_today = setup
                        stop_px = None
                    elif mode == "vwap":
                        lim_px = vwap + setup * pb * dat
                        lim_px = (math.floor(lim_px / tick) if setup == 1 else math.ceil(lim_px / tick)) * tick
                        # a limit only makes sense below the price (long) / above it (short)
                        if (bc - lim_px) * setup <= 0:
                            lim_px = None
        if eng.pos != 0 and stop_px is not None and eng.entry_i < i + 1:
            xa = XLONG if eng.pos == 1 else XSHORT
            eng.order(STOP, xa, stop_px, "SL" if not be_on else "BE")
            if tgt_px is not None:
                eng.order(LIMIT, xa, tgt_px, "TP")
            if eng2 is not None and eng2.pos == eng.pos and eng2.entry_i < i:
                s2 = stop_px
                if be_on is False:
                    s2 = eng2.entry_px - eng.pos * sl * (sum(rngs) / len(rngs))
                eng2.order(STOP, xa, s2, "SL2")
        if eng.pos == 0:
            stop_px = None
    if eng2 is not None:
        eng.trades = sorted(eng.trades + eng2.trades)
    return eng


def s15_gold_asian_breakout(b, tf, i0, i1, p):
    """Gold Asian-range breakout (user's file, 2026-11-02), GC, CT. Range = signal bars (tf, 5m) closing
    20:00-23:55 CT (21:00-01:00 NY); at the 00:00 close a buy stop goes at the range high and a sell stop at
    the range low, first touch wins. Protective stop = asian_stop_frac x range from the fill, no target, flat on
    the next bar after the 10:00 CT close. Revamped 2026-11-02: one trade a day (asian_one=0 restores the
    original code, whose stops stay armed after a stop-out and re-enter until 10:00). Stop entries fill at the level or at the open on a gap;
    if both levels are hit in one minute the intrabar path decides.
    Exit options (2026-11-04, all off by default): asian_trail_r = activate an ATR trail once the trade is
    this many R (R = stop distance) in profit; asian_trail_atr = trail distance in ATRs of the signal bars
    (asian_atr_len, Wilder), ratcheted at each signal-bar close behind the best price since entry;
    asian_tp_r = R-multiple limit target; asian_tp_proj = target at the broken edge +/- this x range width.
    asian_ist=1 (2026-11-04): the user's IST clock. Range 06:30-10:30 IST, exit 19:30 IST (India has no DST),
    i.e. 20:00-00:00 / exit 09:00 CT while the US is on daylight time and 19:00-23:00 / exit 08:00 CT in
    winter. Range = bars closing after the start up to the end, orders arm at the close of the end bar.
    Day filters (2026-11-04, off by default): asian_min_pts = skip ranges under this many points;
    asian_min_rel = skip ranges under this x the last 20 ranges' mean; asian_buf = entry stops this x range
    beyond the edges (stop stays at the opposite edge); asian_trend = N: long only if price at arming is above
    its value N days earlier, short only if below (asian_trend_dir=-1 flips it); asian_entry_mins = stop
    entries expire this many minutes after arming. Volatility regime: asian_reg_pts = trade only when the
    last 20 Asian ranges average at least this many points; asian_reg_ratio = only when that 20-day average is at
    least this x the 250-day average (scale-free, so back-adjustment does not distort it)."""
    O, H, L, C, V, CA = b.o, b.h, b.l, b.c, b.v, b.cabs
    eng = Engine(CA, p["tick"])
    tfb = TFBars(tf)
    r_start, r_end = int(p.get("asian_start", 2000)), int(p.get("asian_end", 0))
    exit_t = int(p.get("asian_exit", 1000))
    frac = float(p.get("asian_stop_frac", 1.0))
    one = bool(int(p.get("asian_one", 1)))       # 1 = one trade a day (revamp); 0 = the original code
    max_rng = float(p.get("asian_max_rng", 0))    # > 0: skip days whose range > this x the last 20 ranges' mean
    max_risk = float(p.get("asian_max_risk", 0))
    cap_stop = int(p.get("asian_cap_stop", 0))
    a_pv = float(p.get("asian_pv", 10.0))
    trail_r = float(p.get("asian_trail_r", 0))
    trail_k = float(p.get("asian_trail_atr", 2.0))
    atr_n = int(p.get("asian_atr_len", 14))
    tp_r = float(p.get("asian_tp_r", 0))
    tp_proj = float(p.get("asian_tp_proj", 0))
    ist = bool(int(p.get("asian_ist", 0)))
    dst_cache = {}

    def us_dst(od):
        """US daylight time on CT calendar day od: 2nd Sunday of March to 1st Sunday of November."""
        y = date.fromordinal(od).year
        if y not in dst_cache:
            m = date(y, 3, 8)
            n = date(y, 11, 1)
            dst_cache[y] = ((m.toordinal() + (6 - m.weekday()) % 7), (n.toordinal() + (6 - n.weekday()) % 7))
        a, z = dst_cache[y]
        return a <= od < z

    min_pts = float(p.get("asian_min_pts", 0))
    min_rel = float(p.get("asian_min_rel", 0))
    buf = float(p.get("asian_buf", 0))
    trend_n = int(p.get("asian_trend", 0))
    trend_dir = int(p.get("asian_trend_dir", 1))
    entry_mins = int(p.get("asian_entry_mins", 0))
    reg_pts = float(p.get("asian_reg_pts", 0))
    reg_ratio = float(p.get("asian_reg_ratio", 0))
    hist = []                                      # every Asian range, for the regime filter
    arm_px = []
    e_hi, e_lo, allow, arm_end = 0.0, 0.0, 0, 0
    atr, pc = 0.0, None
    best, trail, tgt = 0.0, None, None
    rngs = []
    in_prev = False
    r_hi, r_lo, rng, sd = 0.0, 999999.0, 0.0, 0.0
    armed = False
    live = False                                   # stop entries working on the 1-minute bars
    for i in range(i0, i1):
        o, h, l, c = O[i], H[i], L[i], C[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        if live and entry_mins and CA[i] > arm_end + entry_mins:
            live = armed = False
        if live and eng.pos == 0 and not (eng.trades and eng.trades[-1][1] == i):
            up = (o >= e_hi or h >= e_hi) and allow >= 0
            dn = (o <= e_lo or l <= e_lo) and allow <= 0
            side = 0
            if up and dn:
                side = 1 if (o >= e_hi or (o > e_lo and h - o <= o - l)) else -1
            elif up:
                side = 1
            elif dn:
                side = -1
            if side:
                lvl = e_hi if side == 1 else e_lo
                px = o if side * (o - lvl) >= 0 else lvl
                eng._open(i, side, px, "Asia_long" if side == 1 else "Asia_short")
                eng.entry_kind = STOP
                best, trail = px, None
                tgt = None
                if tp_r > 0:
                    tgt = px + side * tp_r * sd
                elif tp_proj > 0:
                    tgt = lvl + side * tp_proj * rng
                if one:
                    armed = live = False
        if eng.pos == 1 and h > best:
            best = h
        elif eng.pos == -1 and (l < best or best == 0):
            best = l
        closed = tfb.update(CA[i], o, h, l, c, V[i])
        if closed:
            for end, bo, bh, bl, bc, bv in closed:
                tr = bh - bl if pc is None else max(bh, pc) - min(bl, pc)
                atr = tr if atr == 0 else atr + (tr - atr) / atr_n
                pc = bc
                if trail_r > 0 and eng.pos != 0 and sd > 0 and eng.pos * (best - eng.entry_px) >= trail_r * sd:
                    ts = best - eng.pos * trail_k * atr
                    if trail is None or eng.pos * (ts - trail) > 0:
                        trail = ts
                t = hhmm(end)
                if ist:
                    r_start, r_end, exit_t = (2000, 0, 900) if us_dst(end // 1440) else (1900, 2300, 800)
                    inw = (r_start < t <= r_end) if r_start < r_end else (t > r_start or t <= r_end)
                else:
                    inw = (r_start <= t < r_end) if r_start < r_end else (t >= r_start or t < r_end)
                if inw and not in_prev:
                    r_hi, r_lo, rng, sd, armed = 0.0, 999999.0, 0.0, 0.0, False
                if inw:
                    r_hi, r_lo = max(r_hi, bh), min(r_lo, bl)
                if ((ist and inw and t == r_end) or (not inw and in_prev)) and rng == 0 and r_hi > 0:
                    rng = r_hi - r_lo
                    sd = (frac + buf) * rng
                    e_hi, e_lo, arm_end = r_hi + buf * rng, r_lo - buf * rng, end
                    armed = rng > 0
                    if rng < min_pts or (min_rel > 0 and (len(rngs) < 20 or rng < min_rel * sum(rngs) / len(rngs))):
                        armed = False
                    if reg_pts or reg_ratio:
                        m20 = sum(hist[-20:]) / 20 if len(hist) >= 20 else 0
                        m250 = sum(hist[-250:]) / 250 if len(hist) >= 250 else 0
                        if (reg_pts and m20 < reg_pts) or (reg_ratio and (not m250 or m20 < reg_ratio * m250)):
                            armed = False
                    hist.append(rng)
                    allow = 0
                    if trend_n:
                        if len(arm_px) < trend_n:
                            armed = False
                        else:
                            allow = trend_dir * (1 if bc > arm_px[-trend_n] else -1)
                        arm_px.append(bc)
                    if max_rng > 0 and (len(rngs) < 20 or rng > max_rng * sum(rngs) / len(rngs)):
                        armed = False
                    # $ risk cap per micro (2026-11-11): asian_max_risk > 0 skips days whose stop distance x asian_pv
                    # (MGC $10/pt) exceeds it; asian_cap_stop=1 instead trades with the stop pulled in to the cap
                    if max_risk > 0 and sd * a_pv > max_risk:
                        if cap_stop:
                            sd = max_risk / a_pv
                        else:
                            armed = False
                    rngs.append(rng)
                    if len(rngs) > 20:
                        del rngs[0]
                past_exit = exit_t <= t < r_start     # between the exit and the next range start
                live = armed and not past_exit
                if past_exit:
                    if eng.pos != 0:
                        eng.order(MKT, XLONG if eng.pos == 1 else XSHORT, None, "ExitL" if eng.pos == 1 else "ExitS")
                    armed = live = False
                in_prev = inw
        if eng.pos != 0 and sd > 0:
            xa = XLONG if eng.pos == 1 else XSHORT
            sl = eng.entry_px - eng.pos * sd
            if trail is not None and eng.pos * (trail - sl) > 0:
                eng.order(STOP, xa, trail, "Trail")
            else:
                eng.order(STOP, xa, sl, "SL")
            if tgt is not None:
                eng.order(LIMIT, xa, tgt, "TP")
    return eng



def s18_gold_session_fade(b, tf, i0, i1, p):
    """Gold failed-breakout reversal. Session = 17:00-16:00 CT. After price trades below the previous
    session's low, a 1-min close back above it buys at market; mirror for shorts at the previous high.
    SL fs_sl / TP fs_tp points (18 / 16 = $1,800 / $1,600 per GC), one trade per side per session,
    entries up to fs_last, flat at fs_flat CT."""
    O, H, L, C, T, D = b.o, b.h, b.l, b.c, b.hhmm, b.day
    eng = Engine(b.cabs, p["tick"])
    sl, tp = float(p.get("fs_sl", 18)), float(p.get("fs_tp", 16))
    last, flat = int(p.get("fs_last", 1500)), int(p.get("fs_flat", 1550))
    one = int(p.get("fs_one", 1))
    sess = None
    ph = pl = None
    ch = cl = 0.0
    below = above = False
    nl = ns = 0
    stop_px = tgt_px = 0.0
    for i in range(i0, i1):
        o, h, l, c, t = O[i], H[i], L[i], C[i], T[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        s = D[i] + (1 if t > 1600 else 0)
        if s != sess:
            if sess is not None:
                ph, pl = ch, cl
            sess, ch, cl = s, h, l
            below = above = False
            nl = ns = 0
        else:
            ch, cl = max(ch, h), min(cl, l)
        sig = 0
        if ph is not None:
            below = below or l < pl
            above = above or h > ph
            if below and c > pl and (nl < 1 or not one):
                sig = 1
            if above and c < ph and (ns < 1 or not one):
                sig = -1 if not sig else 0
        pos = eng.pos
        if pos != 0:
            xa = XLONG if pos == 1 else XSHORT
            if flat <= t <= 1600:
                eng.order(MKT, xa, None, "EOD")
            else:
                eng.order(STOP, xa, stop_px, "SL")
                eng.order(LIMIT, xa, tgt_px, "TP")
        elif sig and not (last < t <= 1700):
            d = 1 if sig == 1 else -1
            stop_px, tgt_px = c - d * sl, c + d * tp
            xa = XLONG if d == 1 else XSHORT
            eng.order(MKT, BUY if d == 1 else SHORT, None, "L" if d == 1 else "S")
            eng.order(STOP, xa, stop_px, "SL0")
            eng.order(LIMIT, xa, tgt_px, "TP0")
            if d == 1:
                nl += 1; below = False
            else:
                ns += 1; above = False
    return eng


def s19_vwap_fade(b, tf, i0, i1, p):
    """VWAP Fade (the user's OFB_VWAPFade_SIG, 2026-11-07): fade the session-VWAP sigma bands. CT clock.
    VWAP / sigma: volume-weighted mean and SD of the 1-minute typical price (h+l+c)/3 since the anchor
    (vf_anchor "globex" = 17:00 CT session start, the file's Mode 3; "rth" = 08:30 CT), read at each tf bar close.
    Original (defaults): close > VWAP + vf_dev sigma -> short next bar at market; close < VWAP - vf_dev sigma -> long;
    take profit = limit at VWAP +/- vf_tp sigma (same side as the entry band, recomputed every tf bar, live during
    the next tf bar); no stop; time exit after vf_maxbars tf bars; entries vf_start <= bar close < vf_end
    (09:30-15:00 ET = 0830-1400 CT); vf_flat=1 = flat at market once a bar closes at or after vf_end; unlimited
    re-entries (vf_max=0).
    Options (off by default): vf_sl = stop vf_sl sigma beyond the entry fill (sigma at entry); vf_sl_atr = stop
    x dATR from the fill (dATR = mean RTH range of vf_atr_n sessions); vf_confirm=1 = enter only when a bar closes
    back inside the band after the previous bar closed outside it (rejection); vf_max = entries a day;
    vf_adx = skip when ADX(14) of the tf bars > this; vf_trend = skip when |close - 08:30 open| / dATR > this
    (trend day); vf_with=1 = only fades in the direction of (close - 08:30 open) (buy dips on up days, sell rips
    on down days), -1 = only against it; vf_slope = skip when |VWAP - VWAP vf_slope_n bars ago| / sigma > this;
    vf_sd_min = skip when sigma < this x dATR; vf_news = skip these news days; vf_vol_lo / vf_vol_hi = dATR vs its
    250-session median; vf_longs / vf_shorts."""
    O, H, L, C, V, T, D, CA = b.o, b.h, b.l, b.c, b.v, b.hhmm, b.day, b.cabs
    tick = p["tick"]
    eng = Engine(CA, tick)
    tb = TFBars(tf)
    anchor = p.get("vf_anchor", "globex")
    dev, tpd = float(p.get("vf_dev", 2.0)), float(p.get("vf_tp", 1.0))
    maxb = int(p.get("vf_maxbars", 60))
    s_start, s_end = int(p.get("vf_start", 830)), int(p.get("vf_end", 1400))
    flat = int(p.get("vf_flat", 1))
    sl_sd, sl_atr = float(p.get("vf_sl", 0)), float(p.get("vf_sl_atr", 0))
    confirm = int(p.get("vf_confirm", 0))
    max_tr = int(p.get("vf_max", 0))
    adx_max, trend_max = float(p.get("vf_adx", 0)), float(p.get("vf_trend", 0))
    with_ = int(p.get("vf_with", 0))
    slope_max, slope_n = float(p.get("vf_slope", 0)), int(p.get("vf_slope_n", 6))
    sd_min = float(p.get("vf_sd_min", 0))
    vol_lo, vol_hi = float(p.get("vf_vol_lo", 0)), float(p.get("vf_vol_hi", 0))
    atr_n = int(p.get("vf_atr_n", 14))
    longs, shorts = bool(int(p.get("vf_longs", 1))), bool(int(p.get("vf_shorts", 1)))
    news = set()
    if p.get("vf_news"):
        import news_calendar
        news = news_calendar.days(p["vf_news"])
    rngs, dat_hist = [], []
    r_hi = r_lo = None
    r_day = None
    d_open = None
    day_ok = True
    sess = None
    pv = pv2 = vv = 0.0
    vwap = sd = 0.0
    vw_hist = []
    prev_out = 0                                      # +1 last tf close above the upper band, -1 below the lower
    trades = 0
    bars_in = 0
    exits = []                                        # exit orders re-sent every minute until the next tf close
    stop_px = None
    an = 14                                           # ADX(14) on tf bars (Wilder)
    pc = ph = pl = None
    tr_s = pdm_s = mdm_s = adx = 0.0
    nadx = 0
    for i in range(i0, i1):
        o, h, l, c, t, d = O[i], H[i], L[i], C[i], T[i], D[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        if eng.pos == 0:
            exits = []
        elif eng.entry_i == i and stop_px is None and (sl_sd > 0 or sl_atr > 0):
            dist = sl_sd * sd if sl_sd > 0 else sl_atr * (sum(rngs) / len(rngs))
            stop_px = eng.entry_px - eng.pos * dist
        s = d + (1 if t > 1600 else 0)
        if anchor == "globex" and s != sess:
            sess = s
            pv = pv2 = vv = 0.0
            vw_hist = []
            prev_out = 0
        rth = 830 < t <= 1500
        if rth and d != r_day:                        # first RTH minute
            if r_hi is not None:
                rngs.append(r_hi - r_lo)
                if len(rngs) > atr_n:
                    del rngs[0]
                if len(rngs) >= atr_n:
                    dat_hist.append(sum(rngs) / len(rngs))
                    if len(dat_hist) > 250:
                        del dat_hist[0]
            r_day, r_hi, r_lo, d_open = d, h, l, o
            trades = 0
            day_ok = d not in news
            if day_ok and (vol_lo or vol_hi) and len(dat_hist) >= 60 and len(rngs) >= atr_n:
                med = sorted(dat_hist)[len(dat_hist) // 2]
                dat0 = sum(rngs) / len(rngs)
                if (vol_lo and dat0 < vol_lo * med) or (vol_hi and dat0 > vol_hi * med):
                    day_ok = False
            if anchor == "rth":
                pv = pv2 = vv = 0.0
                vw_hist = []
                prev_out = 0
        elif rth:
            r_hi, r_lo = max(r_hi, h), min(r_lo, l)
        if anchor == "globex" or rth:
            tp_ = (h + l + c) / 3
            pv += tp_ * V[i]
            pv2 += tp_ * tp_ * V[i]
            vv += V[i]
            if vv > 0:
                vwap = pv / vv
                var = pv2 / vv - vwap * vwap
                sd = math.sqrt(var) if var > 0 else 0.0
        closed = tb.update(CA[i], o, h, l, c, V[i])
        if closed:
            for end, bo, bh, bl, bc, bv in closed:
                bt = hhmm(end)
                if pc is not None:
                    trv = max(bh - bl, abs(bh - pc), abs(bl - pc))
                    up, dn = bh - ph, pl - bl
                    pdm = up if up > dn and up > 0 else 0.0
                    mdm = dn if dn > up and dn > 0 else 0.0
                    tr_s += (trv - tr_s) / an
                    pdm_s += (pdm - pdm_s) / an
                    mdm_s += (mdm - mdm_s) / an
                    if tr_s > 0:
                        pdi, mdi = pdm_s / tr_s, mdm_s / tr_s
                        dx = abs(pdi - mdi) / (pdi + mdi) * 100 if pdi + mdi > 0 else 0.0
                        adx += (dx - adx) / an
                        nadx += 1
                pc, ph, pl = bc, bh, bl
                if vv <= 0 or sd <= 0:
                    continue
                vw_hist.append(vwap)
                up_b, dn_b = vwap + dev * sd, vwap - dev * sd
                out = 1 if bc > up_b else (-1 if bc < dn_b else 0)
                if eng.pos != 0:                      # exits on the bar close
                    bars_in += 1
                    xa = XLONG if eng.pos == 1 else XSHORT
                    exits = [(LIMIT, xa, vwap - eng.pos * tpd * sd, "TP")]
                    if bars_in >= maxb:
                        eng.order(MKT, xa, None, "TimeX")
                    if flat and bt >= s_end:
                        eng.order(MKT, xa, None, "EOD")
                elif s_start <= bt < s_end and day_ok and (not max_tr or trades < max_tr) and len(rngs) >= atr_n:
                    sig = 0
                    if confirm:
                        if prev_out == 1 and out != 1 and bc > vwap:
                            sig = -1
                        elif prev_out == -1 and out != -1 and bc < vwap:
                            sig = 1
                    else:
                        sig = -out
                    dat = sum(rngs) / len(rngs)
                    if (sig == 1 and not longs) or (sig == -1 and not shorts):
                        sig = 0
                    if sig and adx_max and nadx > 2 * an and adx > adx_max:
                        sig = 0
                    if sig and d_open is not None and r_day == d:
                        drift = (bc - d_open) / dat
                        if trend_max and abs(drift) > trend_max:
                            sig = 0
                        if with_ and drift * sig * with_ <= 0:
                            sig = 0
                    if sig and slope_max and len(vw_hist) > slope_n and abs(vwap - vw_hist[-1 - slope_n]) / sd > slope_max:
                        sig = 0
                    if sig and sd_min and sd < sd_min * dat:
                        sig = 0
                    if sig:
                        eng.order(MKT, BUY if sig == 1 else SHORT, None, "FadeLE" if sig == 1 else "FadeSE")
                        trades += 1
                        bars_in = 0
                        stop_px = None
                prev_out = out
        if eng.pos != 0 and eng.entry_i <= i:
            xa = XLONG if eng.pos == 1 else XSHORT
            for kind, act, px, lab in exits:
                eng.order(kind, act, px, lab)
            if stop_px is not None:
                eng.order(STOP, xa, stop_px, "SL")
    return eng


_GEX = {}


def _gex_table():
    """SqueezeMetrics daily GEX / DIX (data/gex_dix.csv: date,price,dix,gex), with each day's GEX and DIX rank
    within the previous 252 values. Cached per process."""
    if "t" not in _GEX:
        import csv, os
        from data import DATA_DIR
        rows = list(csv.DictReader(open(os.path.join(DATA_DIR, "gex_dix.csv"))))
        d = [date.fromisoformat(r["date"]).toordinal() for r in rows]
        g = [float(r["gex"]) for r in rows]
        x = [float(r["dix"]) for r in rows]
        def rank(v):
            out = []
            for i in range(len(v)):
                w = v[max(0, i - 252):i]
                out.append(sum(1 for q in w if q < v[i]) / len(w) if len(w) >= 60 else None)
            return out
        _GEX["t"] = (d, g, rank(g), rank(x))
    return _GEX["t"]


def _gex_prev(t, day, back=0):
    """(gex, gex rank, dix rank, gex `back` sessions earlier) published after the last close BEFORE `day`."""
    from bisect import bisect_left
    d, g, gr, xr = t
    k = bisect_left(d, day) - 1
    if k < 0 or gr[k] is None or xr[k] is None:
        return None
    return g[k], gr[k], xr[k], (g[k - back] if back and k - back >= 0 else None)


def s20_twin_continuation(b, tf, i0, i1, p):
    """Twin Continuation (2026-11-07), NQ, CT, RTH 08:30-15:00. Two continuation forces stacked:
    1) the day's flow: the rest-of-day return (previous RTH close -> decision time) predicts the move into the
       cash close (Baltussen, Da, Lammers, Martens 2021, "Hedging demand and market intraday momentum"; Gao et al.
       2018), driven by short-gamma / leveraged-ETF hedging that is done late in the day;
    2) the regime that makes that flow trend: it only shows when dealers are short gamma (paper Table 7). Without
       options data the proxy is the market sitting below its trend (previous RTH close < tc_sma_n-day SMA of RTH
       closes), where index put open interest dominates.
    Scale-free: distances are multiples of dATR = mean RTH range of the last tc_atr_n sessions.
    Decision at the first 1-minute bar close >= tc_time: drift = (close - ref) / dATR, ref = previous RTH close
    (tc_ref=prev) or today's 08:30 open (tc_ref=open). Long if drift >= tc_k, short if <= -tc_k (tc_k_short).
    Entry tc_entry: "time" = market on the next minute; "brk" = stop at the day's RTH high + 1 tick (long; low -
    1 tick short) until tc_last (Osler 2003: stop-loss orders cluster just beyond extremes and cascade once hit);
    "vwap" = also need the close on the trade side of the session VWAP, then market.
    Filters: tc_regime = below / above / "" (none) vs the SMA; tc_vol_lo / tc_vol_hi = dATR / median of the last
    250 sessions; tc_news = skip these news days; tc_twin = "onfh": the overnight + first half hour return
    (previous close -> 09:00) must have the same sign (Gao et al.'s predictor).
    Exit: stop tc_sl x dATR from the fill (0 = none), breakeven once a bar closes tc_be x dATR up (0 = off), flat at
    market on the minute after the tc_flat bar close (default 14:45; 15:00 = the cash close, as in the paper). Never held overnight: the
    late-day push reverts over the next days (Baltussen, van Bekkum, Da 2019; paper Table 11).
    Defaults = the chosen version (2026-11-07 screen): tc_time 1300, tc_k 0.5, tc_regime below, tc_sma_n 50,
    tc_sl 0.4, tc_news cpi,nfp,fomc, tc_flat 1445, tc_prev against (final 2026-11-08 = strategies/TwinContinuation.pl;
    tc_prev= gives the plain 2026-11-07 version). Paper base: tc_sl=0 tc_news= tc_flat=1500 tc_prev=."""
    O, H, L, C, V, T, D, CA = b.o, b.h, b.l, b.c, b.v, b.hhmm, b.day, b.cabs
    tick = p["tick"]
    eng = Engine(CA, tick)
    t_dec = int(p.get("tc_time", 1300))
    t_last = int(p.get("tc_last", 1430))
    flat_t = int(p.get("tc_flat", 1445))
    k = float(p.get("tc_k", 0.5))
    k_short = float(p.get("tc_k_short", k))
    ref_mode = p.get("tc_ref", "prev")
    mode = p.get("tc_entry", "time")
    regime = p.get("tc_regime", "below")
    sma_n = int(p.get("tc_sma_n", 50))
    vol_lo, vol_hi = float(p.get("tc_vol_lo", 0)), float(p.get("tc_vol_hi", 0))
    twin = p.get("tc_twin", "")
    sl, be = float(p.get("tc_sl", 0.4)), float(p.get("tc_be", 0))
    atr_n = int(p.get("tc_atr_n", 14))
    longs, shorts = bool(int(p.get("tc_longs", 1))), bool(int(p.get("tc_shorts", 1)))
    # 2026-11-08 options (off by default)
    dist_lo, dist_hi = float(p.get("tc_dist_lo", 0)), float(p.get("tc_dist_hi", 0))   # (SMA - prev close) / dATR
    slope_n = int(p.get("tc_slope_n", 0))           # SMA must be lower than slope_n sessions ago
    opex = p.get("tc_opex", "")                     # skip: "day" opex Friday, "week" opex week, "after" week after
    kmax = float(p.get("tc_kmax", 0))               # skip if |drift| > kmax (exhaustion)
    rng_lo = float(p.get("tc_rng_lo", 0))           # today's range so far / dATR >= this
    pos_lo = float(p.get("tc_pos", 0))              # close in the top (long) / bottom (short) part of today's range
    dows = {int(x) for x in str(p.get("tc_dow", "")).split(",") if x.strip()}   # weekdays traded, 1=Mon..5=Fri
    trail = float(p.get("tc_trail", 0))             # trail the stop this x dATR behind the best high / low
    prevf = p.get("tc_prev", "against")             # "against" (final default) / "with" / "": yesterday vs the trade
    sma_hist = []
    prev2_close = None
    # 2026-11-08 short-gamma proxies (off by default)
    eff_lo = float(p.get("tc_eff", 0))              # trend efficiency 08:30->decision: |c - open| / sum |1m changes|
    vexp = float(p.get("tc_vexp", 0))               # mean range of last 5 sessions / last 50 sessions >= this
    gapf = p.get("tc_gap", "")
    gapmin = float(p.get("tc_gapmin", 0))           # gaprev: minimum |overnight gap| in dATR
    # gap reversal entry: tc_entry=gaprev (alone, window tc_time..tc_last) or both (gap reversal from tc_gr_start,
    # then the 13:00 drift rule if no gap reversal fired); tc_gr_k = cross distance beyond yesterday's close
    gr_start = int(p.get("tc_gr_start", 1000))
    gr_k = float(p.get("tc_gr_k", p.get("tc_k", 0.5)))
    gr_prev = p.get("tc_gr_prev", prevf if mode == "gaprev" else "")                      # "with" / "against": overnight gap (08:30 open - prev close) vs side
    rng_all = []
    # dealer gamma (SqueezeMetrics GEX/DIX, data/gex_dix.csv; the value published after the PREVIOUS close is used)
    gex_rmax = float(p.get("tc_gex_rmax", 0))       # skip if yesterday's GEX rank in its last 252 days > this
    gex_neg = int(p.get("tc_gex_neg", 0))           # 1 = only days after a negative-GEX close
    gex_fall = int(p.get("tc_gex_fall", 0))         # n > 0: yesterday's GEX below its value n days earlier
    dix_side = float(p.get("tc_dix", 0))            # longs need DIX rank >= x, shorts <= 1 - x
    open_side = int(p.get("tc_open_side", 0))       # 1 = close on the trade side of today's 08:30 open
    gexf = _gex_table() if (gex_rmax or gex_neg or gex_fall or dix_side) else None
    path = 0.0
    lastc_rth = None
    best = None
    news = set()
    if p.get("tc_news", "cpi,nfp,fomc"):
        import news_calendar
        news = news_calendar.days(p.get("tc_news", "cpi,nfp,fomc"))
    rngs, closes, dat_hist = [], [], []
    cur_d = None
    d_hi = d_lo = d_open = None
    last_close = prev_close = None
    c900 = None
    pv = vv = 0.0
    vwap = None
    decided = False
    arm = 0                      # +1 / -1: breakout stop armed
    day_ok = False
    stop_px = None
    be_on = False
    dat = 0.0
    for i in range(i0, i1):
        o, h, l, c, t, d = O[i], H[i], L[i], C[i], T[i], D[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        rth = 830 < t <= 1500
        if not rth:
            continue
        if d != cur_d:
            if d_hi is not None:
                rng_all.append(d_hi - d_lo)
                if len(rng_all) > 60:
                    del rng_all[0]
                rngs.append(d_hi - d_lo)
                if len(rngs) > atr_n:
                    del rngs[0]
                prev2_close = prev_close
                prev_close = last_close
                closes.append(last_close)
                if len(closes) > 400:
                    del closes[0]
                if len(rngs) >= atr_n:
                    dat_hist.append(sum(rngs) / len(rngs))
                    if len(dat_hist) > 250:
                        del dat_hist[0]
            cur_d = d
            d_hi, d_lo, d_open = h, l, o
            pv = vv = 0.0
            c900 = None
            decided = False
            arm = 0
            best = None
            path = 0.0
            lastc_rth = None
            day_ok = len(rngs) >= atr_n and prev_close is not None and d not in news
            if day_ok:
                dat = sum(rngs) / len(rngs)
                if regime and len(closes) >= sma_n:
                    sma = sum(closes[-sma_n:]) / sma_n
                    if regime == "below" and prev_close >= sma:
                        day_ok = False
                    if regime == "above" and prev_close < sma:
                        day_ok = False
                elif regime:
                    day_ok = False
                if len(closes) >= sma_n:
                    sma_now = sum(closes[-sma_n:]) / sma_n
                    sma_hist.append(sma_now)
                    if len(sma_hist) > 300:
                        del sma_hist[0]
                    dist = (sma_now - prev_close) / dat if dat > 0 else 0
                    if dist_lo and dist < dist_lo:
                        day_ok = False
                    if dist_hi and dist > dist_hi:
                        day_ok = False
                    if slope_n and (len(sma_hist) <= slope_n or sma_now >= sma_hist[-1 - slope_n]):
                        day_ok = False
                if opex:
                    dt = date.fromordinal(d)
                    fr = date(dt.year, dt.month, 1)
                    third = fr.toordinal() + ((4 - fr.weekday()) % 7) + 14      # third Friday
                    if (opex == "day" and d == third) or (opex == "week" and third - 4 <= d <= third) or                        (opex == "after" and third + 3 <= d <= third + 7):
                        day_ok = False
                if dows and date_dow(d) not in dows:
                    day_ok = False
                if vexp and (len(rng_all) < 50 or sum(rng_all[-5:]) / 5 < vexp * sum(rng_all[-50:]) / 50):
                    day_ok = False
                if (vol_lo or vol_hi) and len(dat_hist) >= 60:
                    med = sorted(dat_hist)[len(dat_hist) // 2]
                    if vol_lo and dat < vol_lo * med:
                        day_ok = False
                    if vol_hi and dat > vol_hi * med:
                        day_ok = False
        # breakout stop entry (armed on an earlier bar), filled along this bar
        if arm and eng.pos == 0 and not eng.orders:
            lvl = (d_hi + tick) if arm == 1 else (d_lo - tick)
            if arm == 1 and h >= lvl:
                eng._open(i, 1, max(o, lvl), "TC.L")
                eng.entry_kind = STOP
            elif arm == -1 and l <= lvl:
                eng._open(i, -1, min(o, lvl), "TC.S")
                eng.entry_kind = STOP
            if eng.pos != 0:
                arm = 0
                stop_px = eng.entry_px - eng.pos * sl * dat if sl > 0 else None
                be_on = False
        d_hi, d_lo = max(d_hi, h), min(d_lo, l)
        path += abs(c - (lastc_rth if lastc_rth is not None else o))
        lastc_rth = c
        last_close = c
        tp_ = (h + l + c) / 3
        pv += tp_ * V[i]
        vv += V[i]
        if vv > 0:
            vwap = pv / vv
        if t <= 900:
            c900 = c
        # market entry filled this bar: set its stop
        if eng.pos != 0 and eng.entry_i == i and eng.entry_kind == MKT:
            stop_px = eng.entry_px - eng.pos * sl * dat if sl > 0 else None
            be_on = False
        if arm and t >= t_last:
            arm = 0
        if (mode in ("gaprev", "both") and day_ok and not decided and (gr_start if mode == "both" else t_dec) <= t
                < min(t_last, flat_t) and eng.pos == 0
                and dat > 0 and prev_close is not None):
            # gap reversal (2026-11-08): the overnight gap fails and price crosses back through yesterday's close by
            # tc_k x dATR -> trade the reversal direction (gap traders' stops sit behind the open: Osler 2003)
            g = d_open - prev_close
            if abs(g) >= gapmin * dat and g != 0 and (c - prev_close) * (-1 if g > 0 else 1) >= gr_k * dat:
                s_ = -1 if g > 0 else 1
                ok_ = (s_ == 1 and longs) or (s_ == -1 and shorts)
                if ok_ and gr_prev and prev2_close is not None:
                    pr = prev_close - prev2_close
                    if (gr_prev == "with" and pr * s_ <= 0) or (gr_prev == "against" and pr * s_ >= 0):
                        ok_ = False
                if ok_:
                    decided = True
                    eng.order(MKT, BUY if s_ == 1 else SHORT, None, "GR.L" if s_ == 1 else "GR.S")
        if mode != "gaprev" and day_ok and not decided and t >= t_dec and t < flat_t:
            decided = True
            ref = d_open if ref_mode == "open" else prev_close
            dr = (c - ref) / dat if dat > 0 else 0
            s = 1 if (dr >= k and longs) else (-1 if (dr <= -k_short and shorts) else 0)
            if s and twin == "onfh" and (c900 is None or (c900 - prev_close) * s <= 0):
                s = 0
            if s and mode == "vwap" and (vwap is None or (c - vwap) * s <= 0):
                s = 0
            if s and eff_lo and (path <= 0 or abs(c - d_open) / path < eff_lo or (c - d_open) * s <= 0):
                s = 0
            if s and gapf:
                gp = d_open - prev_close
                if (gapf == "with" and gp * s <= 0) or (gapf == "against" and gp * s >= 0):
                    s = 0
            if s and open_side and (c - d_open) * s <= 0:
                s = 0
            if s and gexf is not None:
                gv = _gex_prev(gexf, d, gex_fall)
                if gv is None:
                    s = 0
                else:
                    g_, gr_, dr_, gold_ = gv
                    if gex_rmax and gr_ > gex_rmax:
                        s = 0
                    if gex_neg and g_ >= 0:
                        s = 0
                    if gex_fall and (gold_ is None or g_ >= gold_):
                        s = 0
                    if dix_side and ((s == 1 and dr_ < dix_side) or (s == -1 and dr_ > 1 - dix_side)):
                        s = 0
            if s and kmax and abs(dr) > kmax:
                s = 0
            if s and rng_lo and (d_hi - d_lo) < rng_lo * dat:
                s = 0
            if s and pos_lo and d_hi > d_lo:
                pp = (c - d_lo) / (d_hi - d_lo)
                if (pp if s == 1 else 1 - pp) < pos_lo:
                    s = 0
            if s and prevf and prev2_close is not None:
                pr = prev_close - prev2_close
                if (prevf == "with" and pr * s <= 0) or (prevf == "against" and pr * s >= 0):
                    s = 0
            if s and eng.pos == 0:
                if mode == "brk":
                    arm = s
                else:
                    eng.order(MKT, BUY if s == 1 else SHORT, None, "TC.L" if s == 1 else "TC.S")
        if eng.pos != 0:
            if trail > 0 and stop_px is not None:
                best = (max(best, h) if eng.pos == 1 else min(best, l)) if (best is not None and eng.entry_i < i) else eng.entry_px
                tsp = best - eng.pos * trail * dat
                if (tsp - stop_px) * eng.pos > 0:
                    stop_px = tsp
            if be > 0 and not be_on and (c - eng.entry_px) * eng.pos >= be * dat:
                be_on = True
                stop_px = eng.entry_px
            xa = XLONG if eng.pos == 1 else XSHORT
            if t >= flat_t:
                eng.order(MKT, xa, None, "Close")
            elif stop_px is not None:
                eng.order(STOP, xa, stop_px, "BE" if be_on else "SL")
    return eng


def _last_sunday(y, m):
    """Ordinal of the last Sunday of month m (m = 3 or 10 here)."""
    d = date(y, m, 31)
    return d.toordinal() - (d.weekday() + 1) % 7


def s25_svp_vah_short(b, tf, i0, i1, p):
    """SVP VAH Short (user, 2026-11-08). Session volume profile from the Tokyo open (09:00 JST = 00:00 UTC) to
    the London open (08:00 UK time), on the CT clock: Tokyo = 18:00 CT (US winter) / 19:00 CT (US summer); London
    = 02:00 CT, or 03:00 CT in the weeks when the US is on daylight time and the UK is not. Profile = 1-minute bars
    closing after the Tokyo open up to the London open; each bar's volume is spread evenly over the ticks from its
    low to its high (svp_row ticks per row). POC = the heaviest row; the value area grows one row at a time from the
    POC (the heavier neighbour first, TradingView style) until it holds svp_va (0.70) of the volume. VAH = top row.
    From the London open bar's close to svp_last a sell limit rests at VAH while the last 1-minute close is below
    VAH (price above VAH: no order until it closes back below; svp_above=skip: no short that day if the London-open
    close is above VAH). Stop svp_sl / target svp_tp points from the fill, from the bar after the fill; flat at
    market from svp_flat; svp_max trades a session (1).
    Defaults by market: NQ (tick 0.25) SL 27 / TP 12, skip Monday and Tuesday sessions (svp_skip=mon,tue), short only
    when the 1H trend is down (svp_trend=ema: last completed 60-minute CT bar's close below its EMA(svp_tlen=50));
    GC (tick 0.10) SL 18 / TP 6, every day, no trend filter. svp_trend: ema | ema2 (EMA(svp_tfast=20) below
    EMA(svp_tlen)) | slope (EMA(svp_tlen) lower than an hour earlier) | none. svp_long_val=1 also buys VAL when the
    1H trend is up (mirror). svp_min_bars (60): skip thin profiles (holidays). tf is ignored."""
    O, H, L, C, V, T, D, CA = b.o, b.h, b.l, b.c, b.v, b.hhmm, b.day, b.cabs
    tick = p["tick"]
    gold = abs(tick - 0.1) < 1e-9
    eng = Engine(CA, tick)
    sl_pts = float(p.get("svp_sl", 18 if gold else 27))
    tp_pts = float(p.get("svp_tp", 6 if gold else 12))
    names = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4}
    skip_s = str(p.get("svp_skip", "" if gold else "mon,tue"))
    skip_d = {names[x.strip().lower()[:3]] for x in skip_s.split(",") if x.strip() and x.strip().lower() != "none"}
    trend = str(p.get("svp_trend", "none" if gold else "ema"))
    tlen, tfast = int(p.get("svp_tlen", 50)), int(p.get("svp_tfast", 20))
    va_pct = float(p.get("svp_va", 0.70))
    row = max(1, int(p.get("svp_row", 1)))
    last_t, flat_t = int(p.get("svp_last", 1400)), int(p.get("svp_flat", 1500))
    min_bars = int(p.get("svp_min_bars", 60))
    above_skip = str(p.get("svp_above", "wait")) == "skip"
    long_val = int(p.get("svp_long_val", 0))
    maxn = int(p.get("svp_max", 1))
    a_s, a_f = 2.0 / (tlen + 1), 2.0 / (tfast + 1)
    tfb = TFBars(60)
    ema_s = ema_f = ema_prev = hc = None
    nh = 0
    dst = {}

    def clocks(sd):
        y = date.fromordinal(sd).year
        if y not in dst:
            m, n = date(y, 3, 8), date(y, 11, 1)
            dst[y] = (m.toordinal() + (6 - m.weekday()) % 7, n.toordinal() + (6 - n.weekday()) % 7,
                      _last_sunday(y, 3), _last_sunday(y, 10))
        us_a, us_z, uk_a, uk_z = dst[y]
        us = 1 if us_a <= sd < us_z else 0
        uk = 1 if uk_a <= sd < uk_z else 0
        return 1800 + 100 * us, 200 + 100 * (us - uk)

    sess = None
    tok = lon = 0
    prof = []
    locked = False
    vah = val = None
    ok_day = False
    n_tr = 0
    arm_s = arm_l = False
    no_short = False
    sl = tp = 0.0
    for i in range(i0, i1):
        o, h, l, c, t = O[i], H[i], L[i], C[i], T[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        sd = D[i] + (1 if t > 1600 else 0)
        if sd != sess:
            sess = sd
            tok, lon = clocks(sd)
            prof, locked, vah, val, n_tr, no_short = [], False, None, None, 0, False
            arm_s = arm_l = False
            ok_day = date.fromordinal(sd).weekday() not in skip_d
        # resting limits sent at the previous bar's close
        if eng.pos == 0 and (arm_s or arm_l) and not (eng.trades and eng.trades[-1][1] == i):
            hit_s = arm_s and h >= vah
            hit_l = arm_l and l <= val
            if hit_s and hit_l:
                hit_s = (vah - o) <= (o - val)
                hit_l = not hit_s
            if hit_s or hit_l:
                side = -1 if hit_s else 1
                px = max(o, vah) if hit_s else min(o, val)
                eng._open(i, side, px, "VAH_S" if hit_s else "VAL_L")
                eng.entry_kind = LIMIT
                sl, tp = px - side * sl_pts, px + side * tp_pts
                n_tr += 1
        arm_s = arm_l = False
        # profile window: bars closing after the Tokyo open up to the London open
        if not locked:
            if (t > 1600 and t > tok) or (t < 1600 and t <= lon):
                prof.append((h, l, V[i]))
            if t < 1600 and t >= lon:
                locked = True
                if len(prof) >= min_bars:
                    rt = row
                    ks = [(int(round(pl / tick)) // rt, int(round(ph / tick)) // rt, pv) for ph, pl, pv in prof]
                    lo_k = min(k[0] for k in ks)
                    n = max(k[1] for k in ks) - lo_k + 1
                    diff = [0.0] * (n + 1)
                    tot = 0.0
                    for a, z, pv in ks:
                        w = pv / (z - a + 1)
                        diff[a - lo_k] += w
                        diff[z - lo_k + 1] -= w
                        tot += pv
                    vol, run = [0.0] * n, 0.0
                    for k in range(n):
                        run += diff[k]
                        vol[k] = run
                    poc = max(range(n), key=vol.__getitem__)
                    top = bot = poc
                    acc = vol[poc]
                    while acc < va_pct * tot and (top < n - 1 or bot > 0):
                        up = vol[top + 1] if top < n - 1 else -1.0
                        dn = vol[bot - 1] if bot > 0 else -1.0
                        if up >= dn:
                            top += 1
                            acc += up
                        else:
                            bot -= 1
                            acc += dn
                    vah = ((lo_k + top) * rt + rt - 1) * tick
                    val = (lo_k + bot) * rt * tick
                    no_short = above_skip and c >= vah
        closed = tfb.update(CA[i], o, h, l, c, V[i])
        if closed:
            for bar in closed:
                hc = bar[4]
                ema_prev = ema_s
                ema_s = hc if ema_s is None else ema_s + a_s * (hc - ema_s)
                ema_f = hc if ema_f is None else ema_f + a_f * (hc - ema_f)
                nh += 1
        if eng.pos != 0:
            xa = XLONG if eng.pos == 1 else XSHORT
            if t >= flat_t or t < lon:
                eng.order(MKT, xa, None, "EOD")
            else:
                eng.order(STOP, xa, sl, "SL")
                eng.order(LIMIT, xa, tp, "TP")
        elif locked and vah is not None and ok_day and n_tr < maxn and lon <= t < min(last_t, flat_t):
            if trend == "none":
                dn_ok = up_ok = True
            elif nh < tlen + 1:
                dn_ok = up_ok = False
            elif trend == "ema2":
                dn_ok, up_ok = ema_f < ema_s, ema_f > ema_s
            elif trend == "slope":
                dn_ok, up_ok = ema_s < ema_prev, ema_s > ema_prev
            else:
                dn_ok, up_ok = hc < ema_s, hc > ema_s
            arm_s = dn_ok and not no_short and c < vah
            arm_l = bool(long_val) and up_ok and c > val
    return eng


def s26_lohi_pullback(b, tf, i0, i1, p):
    """Lo-Hi Pullback (user, 2026-11-08), NQ, CT. 5m signal bars, checked at each close 09:00-14:30 CT (10:00-15:30 ET).
    Long if last 1h close > 1h EMA20 and close > L = highest(lowest(low,12),12): limit buy at L; short mirror at
    S = lowest(highest(high,12),12). Limit re-placed each 5m close, rests to 14:30, fills only when price trades through.
    Stop 0.75 x ATR14 (5m) from fill, target 150 pts, flat 14:59 CT. Max 2 trades/day, 2nd only after a winner,
    no more trades after the day's realized loss reaches lh_dll ($300) at lh_qty (2) contracts incl. costs."""
    O, H, L, C, V, T, D, CA = b.o, b.h, b.l, b.c, b.v, b.hhmm, b.day, b.cabs
    tick = p["tick"]; eng = Engine(CA, tick)
    qty, dll = float(p.get("lh_qty", 2)), float(p.get("lh_dll", 300))
    comm, pv = float(p.get("lh_comm", 0.85)), 2.0
    t5, t60 = TFBars(5), TFBars(60)
    lows, highs, lo12, hi12 = [], [], [], []
    atr = pc = ema = hc = None
    day = None; n = 0; pnl = 0.0; lastwin = True
    side = 0; lvl = 0.0; sl = tp = 0.0; seen = 0
    for i in range(i0, i1):
        o, h, l, c, t = O[i], H[i], L[i], C[i], T[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        if D[i] != day:
            day, n, pnl, lastwin, side = D[i], 0, 0.0, True, 0
        if len(eng.trades) > seen:
            for tr in eng.trades[seen:]:
                g = tr[2] * (tr[4] - tr[3]) * pv * qty - 2 * comm * qty - (tick * pv * qty if tr[6] != LIMIT else 0)
                pnl += g; lastwin = g > 0
            seen = len(eng.trades)
        if side and eng.pos == 0 and not (eng.trades and eng.trades[-1][1] == i):
            if (side == 1 and l < lvl) or (side == -1 and h > lvl):
                px = min(o, lvl) if side == 1 else max(o, lvl)
                eng._open(i, side, px, "LH_L" if side == 1 else "LH_S"); eng.entry_kind = LIMIT
                sl, tp = px - side * 0.75 * atr, px + side * 150
                n += 1
            side = 0 if eng.pos else side
        for bar in t60.update(CA[i], o, h, l, c, V[i]) or []:
            hc = bar[4]; ema = hc if ema is None else ema + (hc - ema) * 2 / 21
        for bar in t5.update(CA[i], o, h, l, c, V[i]) or []:
            _, bo, bh, bl, bc, _ = bar
            tr_ = bh - bl if pc is None else max(bh, pc) - min(bl, pc)
            atr = tr_ if atr is None else atr + (tr_ - atr) / 14
            pc = bc
            lows.append(bl); highs.append(bh)
            lows, highs = lows[-12:], highs[-12:]
            lo12.append(min(lows)); hi12.append(max(highs))
            lo12, hi12 = lo12[-12:], hi12[-12:]
            side = 0
            if (len(lo12) == 12 and ema is not None and eng.pos == 0 and 900 <= t <= 1425
                    and n < 2 and (n == 0 or lastwin) and pnl > -dll):
                L12, S12 = max(lo12), min(hi12)
                if hc > ema and bc > L12:
                    side, lvl = 1, L12
                elif hc < ema and bc < S12:
                    side, lvl = -1, S12
        if t >= 1430:
            side = 0
        if eng.pos:
            xa = XLONG if eng.pos == 1 else XSHORT
            if t >= 1459:
                eng.order(MKT, xa, None, "EOD")
            else:
                eng.order(STOP, xa, sl, "SL"); eng.order(LIMIT, xa, tp, "TP")
    return eng


def _half_days(y0=2009, y1=2028):
    """Morning Momentum half-day skip list: July 3, December 24 and the Friday after Thanksgiving (day ordinals)."""
    out = set()
    for y in range(y0, y1 + 1):
        out.add(date(y, 7, 3).toordinal())
        out.add(date(y, 12, 24).toordinal())
        n1 = date(y, 11, 1)
        thu = n1.toordinal() + (3 - n1.weekday()) % 7 + 21           # 4th Thursday of November
        out.add(thu + 1)
    return out


def s27_swing_momentum(b, tf, i0, i1, p):
    """Swing Breakout + Morning Momentum (user's spec, 2026-11-08), NQ, CT, 1-minute bars. Two setups, one position.
    Bars are stamped at their close, so every bucket uses the bar-open minute (cabs - 1). tf is ignored.
    BO (Swing Breakout): 6h candles anchored at the 17:00 CT session open (17-23, 23-05, 05-11, 11-16; the last is a
    partial candle closed at 16:00). Swing high = candle high >= the 3 candles before and the 3 after (confirmed when
    the 3rd later candle completes). A swing is 'open' while no 15m bar starting after its confirmation has traded
    at/through it (15m high or close >= level; mirror for lows); it is usable only after the first such 15m bar passed.
    At each 15m close while flat, before sm_bo_last (15:30 CT), ATR(14, Wilder, 15m) ready, session not vetoed
    (previous session's range / mean range of the 50 sessions before it > sm_veto = 2.0): buy stop at the latest open
    swing high, stop = latest swing low (must be below); sell stop at the latest open swing low, stop = latest swing
    high (must be above). Both rest (OCO); levels frozen at the 15m close and re-sent every bar until the next 15m
    close. Exits from the bar after the fill: stop at the swing, limit at fill +/- sm_tp_atr (2.0) x ATR, market if the
    close is already beyond the stop, market after the sm_bo_flat (15:45) bar close or at a new session.
    MO (Morning Momentum): clock 10m bars, 24h. basis = EMA21(close) seeded with the first close, range = RMA14(TR),
    raw = (close - basis) / (3 x range) x 100, osc = EMA3(raw). Fresh cross above +100 long / below -100 short on a
    complete 10m bar (10 one-minute bars) ending 08:40-09:30 CT, after 60 bars of warmup, while flat, one per date,
    not on July 3 / Dec 24 / Thanksgiving Friday. Market next bar; it cancels pending BO stops. Stop sm_mo_stop (75)
    points from the fill (from the bar after the fill); market after the sm_mo_flat (14:50) bar close or at a new date.
    Options: sm_bo / sm_mo (1 = on; 0 = run the other setup alone), sm_tp_atr, sm_veto, sm_bo_last, sm_bo_flat,
    sm_mo_stop, sm_mo_flat, sm_bo_once (0; 1 = one BO trade per session).
    Improvement options (2026-11-08, all off by default = the spec):
      sm_lucid=1   LucidPro hours: BO flat after the 15:40 bar (not 15:45); on NYSE closures / early closes every
                   position is flat after the 11:55 bar and no BO orders from 11:45.
      BO: sm_bo_cap (stop capped at x ATR from the fill), sm_bo_win (entry window: on = 17:00-08:30, rth =
          08:30-15:30, asia = 17:00-02:00, london = 02:00-08:30), sm_bo_be (breakeven once a bar closes x ATR up),
          sm_bo_trend=1 (longs only if the previous RTH close > 50-day SMA of RTH closes, shorts only below),
          sm_bo_flat (e.g. 830 = an overnight leg out at the RTH open), sm_veto, sm_tp_atr.
      MO: sm_mo_sl_datr (stop x dATR instead of points; dATR = mean RTH range of 14 sessions), sm_mo_bias (short =
          shorts only on short overnight-bias days, both = never against the bias, long/short same for longs),
          sm_mo_news ("fomc" / "cpi;nfp;fomc"), sm_mo_be (breakeven at x dATR on a bar close), sm_mo_vol_lo (skip if
          dATR < x * its 250-session median), sm_mo_lvl (100), sm_mo_side (both|long|short)."""
    O, H, L, C, T, D, CA = b.o, b.h, b.l, b.c, b.hhmm, b.day, b.cabs
    tick = p["tick"]
    eng = Engine(CA, tick)
    use_bo, use_mo = int(p.get("sm_bo", 1)), int(p.get("sm_mo", 1))
    tp_atr, veto = float(p.get("sm_tp_atr", 2.0)), float(p.get("sm_veto", 2.0))
    bo_last, bo_flat = int(p.get("sm_bo_last", 1530)), int(p.get("sm_bo_flat", 1545))
    mo_stop, mo_flat = float(p.get("sm_mo_stop", 75)), int(p.get("sm_mo_flat", 1450))
    bo_once = int(p.get("sm_bo_once", 0))
    half = _half_days()
    lucid = int(p.get("sm_lucid", 0))
    if lucid:
        bo_flat = min(bo_flat, 1540)
    cl_, ea_ = nyse_calendar()
    short_days = (cl_ | ea_) if lucid else set()
    bo_cap, bo_be = float(p.get("sm_bo_cap", 0)), float(p.get("sm_bo_be", 0))
    bo_maxrisk, bo_pv = float(p.get("sm_bo_maxrisk", 0)), float(p.get("sm_pv", 2.0))
    bo_win, bo_trend = str(p.get("sm_bo_win", "") or ""), int(p.get("sm_bo_trend", 0))
    mo_sl_datr, mo_be = float(p.get("sm_mo_sl_datr", 0)), float(p.get("sm_mo_be", 0))
    mo_bias, mo_vol_lo = str(p.get("sm_mo_bias", "") or ""), float(p.get("sm_mo_vol_lo", 0))
    mo_lvl, mo_side = float(p.get("sm_mo_lvl", 100)), str(p.get("sm_mo_side", "both"))
    news = set()
    if p.get("sm_mo_news"):
        import news_calendar
        news = set(news_calendar.days(str(p["sm_mo_news"]).replace(";", ",")))

    def in_win(x):
        if bo_win == "on":
            return x >= 1700 or x < 830
        if bo_win == "rth":
            return 830 <= x < 1530
        if bo_win == "asia":
            return x >= 1700 or x < 200
        if bo_win == "norlon":
            return not (200 <= x < 830)
        if bo_win == "london":
            return 200 <= x < 830
        return True
    # RTH stats: dATR, its 250-session history, 50-day SMA of RTH closes; overnight bias
    rday = None; rh = rl = rc = None; rngs = []; datr = 0.0; dhist = []; dmed = 0.0; rcl = []; prevc = None; sma = None
    on_rng = {}; bias = 0; be_done = False; bo_atr = 0.0
    # 6h candles and swings
    ck = None; ck_live = False; ch = cl = 0.0; cH, cL = [], []
    sw_hi, sw_lo = [], []          # [level, conf_cabs, state]: state False = awaiting first 15m test, True = open
    last_hi = last_lo = None       # latest confirmed swing levels (any state)
    # sessions
    sess = None; s_hi = s_lo = 0.0; s_rngs = []; vetoed = True; bo_done = False
    # 15m ATR
    t15 = TFBars(15); pc15 = None; atr = 0.0; n_tr = 0; tr_sum = 0.0
    # 10m oscillator
    mk = None; mlive = False; mh = ml = mc = 0.0; mn = 0; nb10 = 0
    basis = rng = osc = prev_osc = pc10 = None; rtr = []
    mo_day = None
    # orders / position
    frz = (None, None)             # BO levels frozen at the last 15m close: (entry, stop, atr) long / short
    arm = (None, None)             # BO stop entries sent on the previous bar
    setup = ""; sl = tp = 0.0; pos_sess = pos_day = None; mo_pending = False

    for i in range(i0, i1):
        o, h, l, c, t, cabs = O[i], H[i], L[i], C[i], T[i], CA[i]
        m = cabs - 1                                   # bar-open minute
        s = (m + 420) // 1440                          # session id: the 17:00 CT open belongs to the next date
        if eng.orders:
            eng.fill(i, o, h, l)
        if mo_pending and eng.pos:                     # MO market entry filled at this open
            setup, pos_day, pos_sess, be_done = "MO", D[i], s, False
            dist = mo_sl_datr * datr if (mo_sl_datr and datr) else mo_stop
            sl = eng._to_tick(STOP, XLONG if eng.pos == 1 else XSHORT, eng.entry_px - eng.pos * dist)
        mo_pending = False
        # resting BO stop entries
        if eng.pos == 0 and (arm[0] or arm[1]):
            al, as_ = arm
            hit_l = al is not None and h >= al[0]
            hit_s = as_ is not None and l <= as_[0]
            if hit_l and hit_s:                        # intrabar path: the extreme nearer the open comes first
                if h - o <= o - l:
                    hit_s = False
                else:
                    hit_l = False
            if hit_l or hit_s:
                a, side = (al, 1) if hit_l else (as_, -1)
                px = max(o, a[0]) if side == 1 else min(o, a[0])
                eng._open(i, side, px, "BO_L" if side == 1 else "BO_S")
                eng.entry_kind = STOP
                setup, sl, bo_atr, be_done = "BO", a[1], a[2], False
                if bo_cap:
                    capd = px - side * bo_cap * a[2]
                    sl = max(sl, capd) if side == 1 else min(sl, capd)
                    sl = eng._to_tick(STOP, XLONG if side == 1 else XSHORT, sl)
                tp = eng._to_tick(LIMIT, XLONG if side == 1 else XSHORT, px + side * tp_atr * a[2])
                pos_sess, pos_day, bo_done = s, D[i], True
                frz = (None, None)                     # the other order is dropped
        arm = (None, None)
        # ---- RTH stats (dATR, SMA of RTH closes) and the overnight bias ----
        if 830 < t <= 1500:
            if D[i] != rday:
                if rday is not None and rh is not None:
                    datr = _datr_update(rngs, rh, rl)
                    if datr:
                        dhist.append(datr); dhist[:] = dhist[-250:]
                        dmed = sorted(dhist)[len(dhist) // 2]
                    rcl.append(rc); rcl[:] = rcl[-50:]
                    prevc = rc
                    sma = sum(rcl) / 50 if len(rcl) == 50 else None
                rday, rh, rl = D[i], h, l
            else:
                rh, rl = max(rh, h), min(rl, l)
            rc = c
        if t > 2345 or t <= 830:
            dd = D[i] + (1 if t > 2345 else 0)
            x = on_rng.get(dd)
            on_rng[dd] = [h, l] if x is None else [max(x[0], h), min(x[1], l)]
        if t == 831:
            x = on_rng.pop(D[i], None)
            bias = 0
            if x and x[0] > x[1]:
                q_ = (o - x[1]) / (x[0] - x[1])
                bias = 1 if q_ >= .67 else (-1 if q_ <= .33 else 0)
            for k_ in [k_ for k_ in on_rng if k_ < D[i]]:
                del on_rng[k_]
        # ---- session bookkeeping and volatility veto ----
        if s != sess:
            if sess is not None:
                s_rngs.append(s_hi - s_lo)
            sess, s_hi, s_lo, bo_done = s, h, l, False
            vetoed = True
            if len(s_rngs) >= 51:
                base = sum(s_rngs[-51:-1]) / 50.0
                vetoed = base <= 0 or s_rngs[-1] / base > veto
            frz = (None, None)
        else:
            s_hi, s_lo = max(s_hi, h), min(s_lo, l)
        # ---- 6h candles (17-23, 23-05, 05-11, 11-16 partial) and fractal swings ----
        sstart = s * 1440 - 420
        idx = (m - sstart) // 360
        done_c = []
        if (s, idx) != ck:
            if ck_live:
                done_c.append((ch, cl))
            ck, ch, cl, ck_live = (s, idx), h, l, True
        else:
            ch, cl = max(ch, h), min(cl, l)
        if ck_live and cabs >= sstart + (1380 if idx >= 3 else (idx + 1) * 360):
            done_c.append((ch, cl)); ck_live = False
        for xh, xl in done_c:
            cH.append(xh); cL.append(xl)
            n = len(cH)
            if n >= 7:
                k = n - 4
                if cH[k] >= max(cH[k - 3:k]) and cH[k] >= max(cH[k + 1:]):
                    sw_hi.append([cH[k], cabs, False]); last_hi = cH[k]
                if cL[k] <= min(cL[k - 3:k]) and cL[k] <= min(cL[k + 1:]):
                    sw_lo.append([cL[k], cabs, False]); last_lo = cL[k]
            if n > 40:
                del cH[:-7]; del cL[:-7]
        # ---- 15m bars: ATR, open-swing test, BO arming ----
        for e15, _, bh, bl, bc, _ in t15.update(cabs, o, h, l, c, 0) or []:
            tr_ = bh - bl if pc15 is None else max(bh, pc15) - min(bl, pc15)
            pc15 = bc
            if n_tr < 14:
                n_tr += 1; tr_sum += tr_; atr = tr_sum / n_tr
            else:
                atr = (atr * 13 + tr_) / 14
            st15 = e15 - 15                            # 15m bar open minute
            sw_hi = [x for x in sw_hi if st15 < x[1] or not (bh >= x[0] or bc >= x[0])]
            sw_lo = [x for x in sw_lo if st15 < x[1] or not (bl <= x[0] or bc <= x[0])]
            for x in sw_hi + sw_lo:
                if st15 >= x[1]:
                    x[2] = True
            fl = fs = None
            if (use_bo and eng.pos == 0 and n_tr >= 14 and not vetoed and not (bo_last <= hhmm(e15) < 1700)
                    and not (bo_once and bo_done)):
                oh = [x for x in sw_hi if x[2]]
                ol = [x for x in sw_lo if x[2]]
                okl = oks = in_win(hhmm(e15)) and not (D[i] in short_days and 1145 <= hhmm(e15) < 1700)
                if bo_trend:
                    okl = okl and sma is not None and prevc > sma
                    oks = oks and sma is not None and prevc < sma
                if okl and oh and last_lo is not None and last_lo < oh[-1][0]:
                    fl = (oh[-1][0], last_lo, atr)
                if oks and ol and last_hi is not None and last_hi > ol[-1][0]:
                    fs = (ol[-1][0], last_hi, atr)
            frz = (fl, fs)
        # ---- 10m oscillator ----
        k10 = m // 10
        bars10 = []
        if k10 != mk:
            if mlive:
                bars10.append((mk * 10 + 10, mh, ml, mc, mn))
            mk, mh, ml, mc, mn, mlive = k10, h, l, c, 1, True
        else:
            mh, ml, mc, mn = max(mh, h), min(ml, l), c, mn + 1
        if mlive and cabs % 10 == 0:
            bars10.append((cabs, mh, ml, mc, mn)); mlive = False
        mo_sig = 0
        for e10, xh, xl, xc, xn in bars10:
            nb10 += 1
            tr_ = xh - xl if pc10 is None else max(xh, pc10) - min(xl, pc10)
            pc10 = xc
            basis = xc if basis is None else basis + (xc - basis) * 2 / 22
            if rng is None:
                rtr.append(tr_)
                if len(rtr) == 14:
                    rng = sum(rtr) / 14
            else:
                rng = (rng * 13 + tr_) / 14
            if rng:
                raw = (xc - basis) / (3 * rng) * 100
                prev_osc = osc
                osc = raw if osc is None else osc + (raw - osc) * 0.5
            if (use_mo and nb10 >= 60 and prev_osc is not None and xn == 10 and e10 == cabs
                    and 840 <= hhmm(e10) <= 930 and eng.pos == 0 and mo_day != D[i] and D[i] not in half):
                if prev_osc <= mo_lvl < osc:
                    mo_sig = 1
                elif prev_osc >= -mo_lvl > osc:
                    mo_sig = -1
                if mo_sig and ((mo_side == "long" and mo_sig < 0) or (mo_side == "short" and mo_sig > 0)):
                    mo_sig = 0
                if mo_sig and D[i] in news:
                    mo_sig = 0
                if mo_sig and mo_vol_lo and (not dmed or datr < mo_vol_lo * dmed):
                    mo_sig = 0
                if mo_sig and mo_sl_datr and not datr:
                    mo_sig = 0
                if mo_sig and mo_bias:
                    if mo_bias == "short" and mo_sig < 0 and bias != -1:
                        mo_sig = 0
                    elif mo_bias == "long" and mo_sig > 0 and bias != 1:
                        mo_sig = 0
                    elif mo_bias == "both" and bias == -mo_sig:
                        mo_sig = 0
                    elif mo_bias == "with" and bias != mo_sig:
                        mo_sig = 0
        # ---- orders for the next bar ----
        if eng.pos:
            xa = XLONG if eng.pos == 1 else XSHORT
            early = D[i] in short_days and 1155 <= t < 1700
            if setup == "BO" and bo_be and not be_done and (c - eng.entry_px) * eng.pos >= bo_be * bo_atr:
                be_done = True
                sl = max(sl, eng.entry_px) if eng.pos == 1 else min(sl, eng.entry_px)
            if setup == "MO" and mo_be and datr and not be_done and (c - eng.entry_px) * eng.pos >= mo_be * datr:
                be_done = True
                sl = max(sl, eng.entry_px) if eng.pos == 1 else min(sl, eng.entry_px)
            if setup == "BO":
                if bo_flat <= t < 1700 or s != pos_sess or early:
                    eng.order(MKT, xa, None, "EOD")
                elif (eng.pos == 1 and c <= sl) or (eng.pos == -1 and c >= sl):
                    eng.order(MKT, xa, None, "GAP")
                else:
                    eng.order(STOP, xa, sl, "SL")
                    eng.order(LIMIT, xa, tp, "TP")
            else:
                if D[i] != pos_day or early:
                    eng.order(MKT, xa, None, "NEWDAY" if not early else "EARLY")
                elif t >= mo_flat:
                    eng.order(MKT, xa, None, "TIME")
                else:
                    eng.order(STOP, xa, sl, "SL")
        elif mo_sig:
            eng.order(MKT, BUY if mo_sig == 1 else SHORT, None, "MO_L" if mo_sig == 1 else "MO_S")
            mo_pending, mo_day = True, D[i]
            frz = (None, None)                         # MO cancels pending BO stops
        elif (not (bo_last <= t < 1700) and not vetoed and in_win(t)
              and not (D[i] in short_days and 1145 <= t < 1700)):
            arm = frz
            if bo_maxrisk > 0:                         # $ risk cap per micro (2026-11-11): drop a side whose stop is too far
                arm = tuple(None if (x is None or abs(x[0] - x[1]) * bo_pv > bo_maxrisk) else x for x in arm)
    return eng


def s28_last_half_hour(b, tf, i0, i1, p):
    """Last-half-hour momentum (2026-11-09; Gao, Han, Li & Zhou 2018, "Market intraday momentum"), CT, 1m bars.
    r1 = (last close at or before lh_t1 (09:00) - previous RTH close (15:00)) / dATR, dATR = mean RTH range (08:31-15:00)
    of the last 14 sessions; r12 = (close at lh_entry - last close at or before lh_t12 (14:00)) / dATR.
    At the first bar closing at/after lh_entry (14:30): lh_mode "r1" = trade the sign of r1 if |r1| >= lh_k;
    "r12" = the sign of r12 if |r12| >= lh_k; "both" = r1 qualifies and r12 has the same sign. Market entry on the next
    minute, one trade a day, lh_side 1 / -1 = longs / shorts only; stop lh_sl x dATR from the fill (0 = none);
    flat at market after the bar closing at lh_exit (1500 = cash close). lh_news = skip these news days."""
    O, H, L, C, T, D, CA = b.o, b.h, b.l, b.c, b.hhmm, b.day, b.cabs
    eng = Engine(CA, p["tick"])
    t1, t12, ent, ex = int(p.get("lh_t1", 900)), int(p.get("lh_t12", 1400)), int(p.get("lh_entry", 1430)), int(p.get("lh_exit", 1500))
    k, mode, side_only = float(p.get("lh_k", 0)), p.get("lh_mode", "r1"), int(p.get("lh_side", 0))
    sl = float(p.get("lh_sl", 0))
    news = set()
    if p.get("lh_news"):
        import news_calendar
        news = news_calendar.days(p["lh_news"])
    rngs, cur, hi, lo, last, prev = [], None, 0.0, 0.0, None, None
    c1 = c12 = None
    done = False
    stop_px = None
    for i in range(i0, i1):
        o, h, l, c, t, d = O[i], H[i], L[i], C[i], T[i], D[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        if eng.pos == 0:
            stop_px = None
        elif stop_px is None and sl > 0 and rngs:
            stop_px = eng.entry_px - eng.pos * sl * sum(rngs[-14:]) / len(rngs[-14:])
        if 830 < t <= 1500:
            if d != cur:
                if cur is not None:
                    rngs.append(hi - lo)
                    prev = last
                cur, hi, lo = d, h, l
                c1 = c12 = None
                done = False
            else:
                hi, lo = max(hi, h), min(lo, l)
            last = c
            if t <= t1:
                c1 = c
            if t <= t12:
                c12 = c
            if not done and t >= ent and t < ex:
                done = True
                if eng.pos == 0 and prev is not None and c1 is not None and len(rngs) >= 14 and d not in news:
                    dat = sum(rngs[-14:]) / 14
                    r1 = (c1 - prev) / dat
                    r12 = (c - c12) / dat if c12 is not None else 0.0
                    sig = 0
                    if mode == "r12":
                        sig = (1 if r12 > 0 else -1) if abs(r12) >= k and r12 != 0 else 0
                    else:
                        sig = (1 if r1 > 0 else -1) if abs(r1) >= k and r1 != 0 else 0
                        if mode == "both" and sig and r12 * sig <= 0:
                            sig = 0
                    if side_only and sig != side_only:
                        sig = 0
                    if sig:
                        eng.order(MKT, BUY if sig == 1 else SHORT, None, "LHM.L" if sig == 1 else "LHM.S")
        if eng.pos != 0:
            xa = XLONG if eng.pos == 1 else XSHORT
            if t >= ex or t < 830:
                eng.order(MKT, xa, None, "Close")
            elif stop_px is not None:
                eng.order(STOP, xa, stop_px, "SL")
    return eng


def s29_gold_day(b, tf, i0, i1, p):
    """Gold day-session breakout (2026-11-09), GC, CT, 1m bars. Range = bars closing after gd_rs up to gd_re (COMEX
    open 07:20 CT -> 07:50). Entry: market on the next minute after the first 1m close beyond the range, up to gd_last;
    one trade a day (gd_one). Stop at the opposite edge (gd_sl x range from the broken edge, 1.0 = opposite side),
    target gd_tp x risk (0 = none), flat at market after the gd_flat bar (12:30 = COMEX close).
    Filters: gd_max = skip if the range > gd_max x mean of the last 20 ranges (0 = off); gd_min likewise below;
    gd_bias = 1: only the side of the overnight move (close at the range end vs the 17:00 session open);
    -1: only against it; gd_side 1 / -1 = longs / shorts only; gd_dow = weekdays traded (1=Mon..5=Fri).
    gd_mode="drift": at the range-end bar trade the sign of (close - last close at/before gd_ds, 02:00 London open) if
    |move| >= gd_k x the mean 20-day range width; stop gd_dsl x that mean, target gd_tp x the stop (0 = none)."""
    O, H, L, C, T, D, CA = b.o, b.h, b.l, b.c, b.hhmm, b.day, b.cabs
    eng = Engine(CA, p["tick"])
    rs, re_, last, flat = int(p.get("gd_rs", 720)), int(p.get("gd_re", 750)), int(p.get("gd_last", 1100)), int(p.get("gd_flat", 1230))
    tp, slf = float(p.get("gd_tp", 0)), float(p.get("gd_sl", 1.0))
    gmax, gmin = float(p.get("gd_max", 0)), float(p.get("gd_min", 0))
    bias, side_only, one = int(p.get("gd_bias", 0)), int(p.get("gd_side", 0)), int(p.get("gd_one", 1))
    dows = {int(x) for x in str(p.get("gd_dow", "")).split(",") if x.strip()}
    mode, ds, dk, dsl = p.get("gd_mode", "orb"), int(p.get("gd_ds", 200)), float(p.get("gd_k", 0)), float(p.get("gd_dsl", 1.0))
    dclose = None
    rngs, cur = [], None
    rhi = rlo = None
    sess_open, prev_t = None, None
    ready = False
    trades = 0
    stop_px = tgt_px = None
    ok = True
    dirn = 0
    for i in range(i0, i1):
        o, h, l, c, t, d = O[i], H[i], L[i], C[i], T[i], D[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        if prev_t is None or (t > 1600 and (prev_t <= 1600 or D[i - 1] != d)):
            sess_open = o                                    # first bar of the 17:00 session
        prev_t = t
        if d != cur and t <= 1600:
            cur, rhi, rlo, ready, trades, ok, dclose = d, None, None, False, 0, True, None
        if rs < t <= re_ and d == cur:
            rhi = h if rhi is None else max(rhi, h)
            rlo = l if rlo is None else min(rlo, l)
        if not ready and t > re_ and rhi is not None and d == cur and t <= 1600:
            ready = True
            w = rhi - rlo
            m20 = sum(rngs[-20:]) / 20 if len(rngs) >= 20 else 0
            if (gmax and (not m20 or w > gmax * m20)) or (gmin and (not m20 or w < gmin * m20)) or w <= 0:
                ok = False
            if dows and (d % 7) not in dows:
                ok = False
            rngs.append(w)
            dirn = (1 if c > sess_open else -1) if sess_open is not None else 0
        if eng.pos == 0:
            stop_px = tgt_px = None
        elif stop_px is None and mode == "drift":
            m20 = sum(rngs[-21:-1]) / 20 if len(rngs) > 20 else (rhi - rlo)
            stop_px = eng.entry_px - eng.pos * dsl * m20
            tgt_px = eng.entry_px + eng.pos * tp * dsl * m20 if tp > 0 else None
        elif stop_px is None:
            risk = None
            if eng.pos == 1:
                stop_px = rhi - slf * (rhi - rlo)
            else:
                stop_px = rlo + slf * (rhi - rlo)
            risk = abs(eng.entry_px - stop_px)
            tgt_px = eng.entry_px + eng.pos * tp * risk if tp > 0 else None
        if mode == "drift" and t <= ds and d == cur:
            dclose = c                                        # last close at/before the drift start (02:00)
        if ready and ok and eng.pos == 0 and not eng.orders and t <= last and (trades < 1 or not one)                 and not (eng.trades and eng.trades[-1][1] == i):
            if mode == "drift":
                m20 = sum(rngs[-21:-1]) / 20 if len(rngs) > 20 else 0
                mv = c - dclose if dclose is not None else 0
                sig = (1 if mv > 0 else -1) if m20 and dclose is not None and abs(mv) >= dk * m20 else 0
                trades += 0 if sig else 1                     # one look per day, at the range end
            else:
                sig = 1 if c > rhi else (-1 if c < rlo else 0)
            if sig and side_only and sig != side_only:
                sig = 0
            if sig and bias and sig != bias * dirn:
                sig = 0
            if sig:
                eng.order(MKT, BUY if sig == 1 else SHORT, None, "GD.L" if sig == 1 else "GD.S")
                trades += 1
        if eng.pos != 0:
            xa = XLONG if eng.pos == 1 else XSHORT
            if t >= flat and t <= 1600:
                eng.order(MKT, xa, None, "Flat")
            else:
                eng.order(STOP, xa, stop_px, "SL")
                if tgt_px is not None:
                    eng.order(LIMIT, xa, tgt_px, "TP")
    return eng


def s30_fast_alpha(b, tf, i0, i1, p):
    """FastAlpha (user's FastAlpha_Optimised.txt, 2026-11-09), NQ/MNQ, CT. Data1 = tf-minute bars (10), Data2 = 5m.
    At the first tf bar closing after 08:30: band = that bar's open +/- fa_band x ATR(fa_atr) of the previous tf bars
    (simple average true range, MultiCharts AvgTrueRange[1]). On a tf close beyond the band while flat (08:30 to
    fa_last) a long / short is armed; it fills at market on the minute after the first 5m bar closing against it
    (down bar for longs), at most fa_max entries a day. Stop and target fa_sl_usd / fa_tp_usd per contract
    ($ / fa_pv points) from the fill, live on the fill bar; flat at market after the 5m bar closing at/after fa_flat."""
    O, H, L, C, V, T, D, CA = b.o, b.h, b.l, b.c, b.v, b.hhmm, b.day, b.cabs
    eng = Engine(CA, p["tick"])
    t1, t2 = TFBars(int(p.get("fa_tf", tf or 10))), TFBars(5)
    band, atr_n = float(p.get("fa_band", 3)), int(p.get("fa_atr", 8))
    pv = float(p.get("fa_pv", 2.0))
    sl, tp = float(p.get("fa_sl_usd", 160)) / pv, float(p.get("fa_tp_usd", 160)) / pv
    mx, last, flat = int(p.get("fa_max", 2)), int(p.get("fa_last", 1400)), int(p.get("fa_flat", 1455))
    longs, shorts = bool(int(p.get("fa_longs", 1))), bool(int(p.get("fa_shorts", 1)))
    # optimisation options (2026-11-09, all off by default = the file)
    sl_atr, tp_atr = float(p.get("fa_sl_atr", 0)), float(p.get("fa_tp_atr", 0))   # exits in x the session ATR instead of $
    bias_on = int(p.get("fa_bias", 0))       # 1 = only the side of Overnight Bias ORB's bias (open's place in 00:00-08:30 range)
    be_atr = float(p.get("fa_be", 0))        # stop to entry after a 5m close this x session ATR in profit
    pull = int(p.get("fa_pull", 1))          # 0 = enter on the next 5m close without needing a contrary bar
    vol_lo = float(p.get("fa_vol_lo", 0))    # skip days whose session ATR < this x its 100-day median
    news = set()
    if p.get("fa_news"):
        import news_calendar
        news = news_calendar.days(p["fa_news"])
    on_hi = on_lo = None
    on_day = None
    bias = 0
    atr_hist = []
    sess_atr = 0.0
    day_ok = True
    be_px = None
    trs, pc = [], None
    sdate, init, up, dn, pend, trades = None, False, 0.0, 0.0, 0, 0
    for i in range(i0, i1):
        o, h, l, c = O[i], H[i], L[i], C[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        if eng.pos == 0:
            be_px = None
        if T[i] <= 830 and D[i] != on_day and T[i] > 0:
            on_day, on_hi, on_lo = D[i], h, l
        elif T[i] <= 830 and D[i] == on_day:
            on_hi, on_lo = max(on_hi, h), min(on_lo, l)
        c1 = t1.update(CA[i], o, h, l, c, V[i])
        if c1:
            for end, bo, bh, bl, bc, bv in c1:
                t, d = hhmm(end), end // 1440
                atr_prev = sum(trs[-atr_n:]) / atr_n if len(trs) >= atr_n else None
                trs.append(bh - bl if pc is None else max(bh, pc) - min(bl, pc))
                pc = bc
                if d != sdate:
                    sdate, init, pend, trades = d, False, 0, 0
                if not init and t > 830 and atr_prev:
                    init, up, dn = True, bo + band * atr_prev, bo - band * atr_prev
                    sess_atr = atr_prev
                    day_ok = d not in news
                    if vol_lo and len(atr_hist) >= 60:
                        med = sorted(atr_hist[-100:])[len(atr_hist[-100:]) // 2]
                        if atr_prev < vol_lo * med:
                            day_ok = False
                    atr_hist.append(atr_prev)
                    bias = 0
                    if on_day == d and on_hi is not None and on_hi > on_lo:
                        x = (bo - on_lo) / (on_hi - on_lo)
                        bias = 1 if x >= 0.67 else (-1 if x <= 0.33 else 0)
                    if not day_ok:
                        init = False
                        up, dn = 1e18, -1e18
                        init = True
                if init and 830 <= t < last and eng.pos == 0:
                    if longs and bc > up:
                        pend = 1
                    elif shorts and bc < dn:
                        pend = -1
        c2 = t2.update(CA[i], o, h, l, c, V[i])
        if c2:
            for end, bo, bh, bl, bc, bv in c2:
                t = hhmm(end)
                if eng.pos == 0:
                    if bias_on and pend and pend != bias:
                        pend = 0
                    s_, t_ = (sl_atr * sess_atr, tp_atr * sess_atr) if sl_atr else (sl, tp)
                    if 830 <= t < last and trades < mx:
                        if pend == 1 and (bc < bo or not pull):
                            eng.order(MKT, BUY, None, "FastAlphaLE", attach=(s_, t_))
                            pend, trades = 0, trades + 1
                        elif pend == -1 and (bc > bo or not pull):
                            eng.order(MKT, SHORT, None, "FastAlphaSE", attach=(s_, t_))
                            pend, trades = 0, trades + 1
                    elif t >= last:
                        pend = 0
                if eng.pos != 0 and be_atr and be_px is None and (bc - eng.entry_px) * eng.pos >= be_atr * sess_atr:
                    be_px = eng.entry_px
                if t >= flat and t <= 1600 and eng.pos != 0:
                    eng.order(MKT, XLONG if eng.pos == 1 else XSHORT, None, "EOD")
                    pend = 0
        if eng.pos != 0 and not any(x[0] == MKT for x in eng.orders):
            ep = eng.entry_px
            xa = XLONG if eng.pos == 1 else XSHORT
            s_, t_ = (sl_atr * sess_atr, tp_atr * sess_atr) if sl_atr else (sl, tp)
            stp = ep - eng.pos * s_
            if be_px is not None:
                stp = max(stp, be_px) if eng.pos == 1 else min(stp, be_px)
            eng.order(STOP, xa, stp, "SL")
            if t_ > 0:
                eng.order(LIMIT, xa, ep + eng.pos * t_, "TP")
    return eng


def s31_noise_area(b, tf, i0, i1, p):
    """NQ Noise-Area Momentum (user's NQ_NoiseArea_Momentum.txt, 2026-11-09; Zarattini, Aziz & Barbon 2024), CT, 15m.
    Per 15m slot of the RTH session (bar closing 08:45 = slot 1), band = today's 08:30 open +/- na_band x the average
    |close - open| of that slot over the last na_lb days (today excluded). Entry at market on the next minute after a
    15m close above the upper band with an up bar (short mirrored), up to na_last, na_max a day; stop na_sl / target
    na_tp points from the fill (live on the fill bar); optional exits back inside the band (na_bandx) or through the
    EMA(na_ema) of 15m closes (na_emax); flat at market after the na_flat bar."""
    O, H, L, C, V, T, D, CA = b.o, b.h, b.l, b.c, b.v, b.hhmm, b.day, b.cabs
    eng = Engine(CA, p["tick"])
    tb = TFBars(15)
    lb, bm = int(p.get("na_lb", 20)), float(p.get("na_band", 1.25))
    sl, tp = float(p.get("na_sl", 50)), float(p.get("na_tp", 100))
    last, flat, mx = int(p.get("na_last", 1415)), int(p.get("na_flat", 1430)), int(p.get("na_max", 2))
    bandx, emax, el = int(p.get("na_bandx", 0)), int(p.get("na_emax", 0)), int(p.get("na_ema", 20))
    longs, shorts = int(p.get("na_longs", 1)), int(p.get("na_shorts", 1))
    # filters (2026-11-09, off by default): na_bias = only the side of the overnight bias (08:30 open in the
    # 00:00-08:30 range, >= 0.67 long / <= 0.33 short); na_vol_lo = skip days whose RTH dATR (14 sessions) is below
    # this x its 250-day median; na_news = skip these news days; na_be = stop to entry after a 15m close na_be pts up
    bias_on, vol_lo, be = int(p.get("na_bias", 0)), float(p.get("na_vol_lo", 0)), float(p.get("na_be", 0))
    news = set()
    if p.get("na_news"):
        import news_calendar
        news = news_calendar.days(p["na_news"])
    on_d, on_h, on_l, bias = None, 0.0, 0.0, 0
    rth_hl, rngs, dhist, day_ok = None, [], [], True
    be_on = False
    hist = {}
    ema = None
    a = 2.0 / (el + 1)
    cur, dopen, trades = None, 0.0, 0
    for i in range(i0, i1):
        o, h, l, c = O[i], H[i], L[i], C[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        if eng.pos == 0:
            be_on = False
        if T[i] <= 830:
            if D[i] != on_d:
                on_d, on_h, on_l = D[i], h, l
            else:
                on_h, on_l = max(on_h, h), min(on_l, l)
        cl = tb.update(CA[i], o, h, l, c, V[i])
        for end, bo, bh, bl, bc, bv in (cl or []):
            t, d = hhmm(end), end // 1440
            ema = bc if ema is None else ema + a * (bc - ema)
            if d != cur:
                if rth_hl:
                    rngs.append(rth_hl[0] - rth_hl[1])
                cur, dopen, trades, rth_hl = d, 0.0, 0, None
            rth = 830 < t <= 1500
            if rth:
                rth_hl = (bh, bl) if rth_hl is None else (max(rth_hl[0], bh), min(rth_hl[1], bl))
            if rth and dopen == 0:
                dopen = bo
                bias = 0
                if on_d == d and on_h > on_l:
                    x = (bo - on_l) / (on_h - on_l)
                    bias = 1 if x >= 0.67 else (-1 if x <= 0.33 else 0)
                day_ok = d not in news
                if len(rngs) >= 14:
                    dat = sum(rngs[-14:]) / 14
                    if vol_lo and len(dhist) >= 60 and dat < vol_lo * sorted(dhist[-250:])[len(dhist[-250:]) // 2]:
                        day_ok = False
                    dhist.append(dat)
            ok, up, dn = False, 0.0, 0.0
            if rth and dopen:
                slot = ((t // 100) * 60 + t % 100 - 510) // 15
                if 1 <= slot <= 29:
                    hs = hist.setdefault(slot, [])
                    if len(hs) >= lb:
                        sig = sum(hs[-lb:]) / lb
                        up, dn, ok = dopen + bm * sig, dopen - bm * sig, sig > 0
                    hs.append(abs(bc - dopen))
                    if len(hs) > lb:
                        del hs[0]
            pos = eng.pos
            if pos != 0 and be and not be_on and (bc - eng.entry_px) * pos >= be:
                be_on = True
            if pos != 0:
                xa = XLONG if pos == 1 else XSHORT
                if t >= flat or not rth:
                    eng.order(MKT, xa, None, "Time")
                elif bandx and ok and ((pos == 1 and bc < up) or (pos == -1 and bc > dn)):
                    eng.order(MKT, xa, None, "Band")
                elif emax and ((pos == 1 and bc < ema) or (pos == -1 and bc > ema)):
                    eng.order(MKT, xa, None, "EMA")
            elif ok and day_ok and t <= last and trades < mx:
                if longs and bc > up and bc > bo and (not bias_on or bias == 1):
                    eng.order(MKT, BUY, None, "NA-L", attach=(sl, tp))
                    trades += 1
                elif shorts and bc < dn and bc < bo and (not bias_on or bias == -1):
                    eng.order(MKT, SHORT, None, "NA-S", attach=(sl, tp))
                    trades += 1
        if eng.pos != 0 and not any(x[0] == MKT for x in eng.orders):
            xa = XLONG if eng.pos == 1 else XSHORT
            stp = eng.entry_px - eng.pos * sl
            if be_on:
                stp = eng.entry_px
            eng.order(STOP, xa, stp, "SL")
            if tp > 0:
                eng.order(LIMIT, xa, eng.entry_px + eng.pos * tp, "TP")
    return eng


def s32_gamma_fade(b, tf, i0, i1, p):
    """Gamma fade (2026-11-09), ES/NQ, CT, 1m RTH. Only on days whose previous-close SqueezeMetrics GEX rank (252 days)
    >= gf_rank (or GEX > 0 with gf_rank < 0). From gf_start to gf_end, the first 1m close at least gf_k x dATR (14-day mean
    RTH range) away from the RTH VWAP is faded at market (gf_side 1 long only / -1 short only); exit at market on the
    first close back through VWAP (or gf_tp x dATR, 0 = VWAP), stop gf_sl x dATR, flat after gf_flat. One trade a day."""
    O, H, L, C, V, T, D, CA = b.o, b.h, b.l, b.c, b.v, b.hhmm, b.day, b.cabs
    eng = Engine(CA, p["tick"])
    k, sl, rk = float(p.get("gf_k", 0.4)), float(p.get("gf_sl", 0.4)), float(p.get("gf_rank", 0.5))
    t0, t1, fl, side_only = int(p.get("gf_start", 1000)), int(p.get("gf_end", 1330)), int(p.get("gf_flat", 1430)), int(p.get("gf_side", 0))
    news = set()
    if p.get("gf_news"):
        import news_calendar
        news = news_calendar.days(p["gf_news"])
    gt = _gex_table()
    rngs, cur, hi, lo, pv, vv, ok, done, stop = [], None, 0, 0, 0.0, 0.0, False, False, None
    for i in range(i0, i1):
        o, h, l, c, t, d = O[i], H[i], L[i], C[i], T[i], D[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        if eng.pos == 0:
            stop = None
        if not (830 < t <= 1500):
            if eng.pos != 0:
                eng.order(MKT, XLONG if eng.pos == 1 else XSHORT, None, "Out")
            continue
        if d != cur:
            if cur is not None:
                rngs.append(hi - lo)
            cur, hi, lo, pv, vv, done = d, h, l, 0.0, 0.0, False
            g = _gex_prev(gt, d)
            ok = g is not None and len(rngs) >= 14 and d not in news and (g[1] >= rk if rk >= 0 else g[0] > 0)
        else:
            hi, lo = max(hi, h), min(lo, l)
        pv += (h + l + c) / 3 * V[i]
        vv += V[i]
        vw = pv / vv if vv else c
        dat = sum(rngs[-14:]) / 14 if len(rngs) >= 14 else 0
        if eng.pos != 0:
            xa = XLONG if eng.pos == 1 else XSHORT
            if stop is None:
                stop = eng.entry_px - eng.pos * sl * dat
            if t >= fl or (c - vw) * eng.pos >= 0:
                eng.order(MKT, xa, None, "VWAP")
            else:
                eng.order(STOP, xa, stop, "SL")
        elif ok and not done and t0 <= t < t1 and dat > 0 and not eng.orders:
            dev = (c - vw) / dat
            sig = -1 if dev >= k else (1 if dev <= -k else 0)
            if sig and (not side_only or sig == side_only):
                eng.order(MKT, BUY if sig == 1 else SHORT, None, "GF")
                done = True
    return eng


def s33_gap_fill(b, tf, i0, i1, p):
    """Gap fill (2026-11-09), ES/NQ, CT. gap = 08:31 open - previous RTH close (15:00), in dATR (14-day mean RTH range).
    If gp_lo <= |gap| <= gp_hi: fade at market at the 08:31 close, target the previous close (limit), stop gp_sl x the gap
    beyond the entry, flat after gp_flat. gp_news = skip these news days; gp_rank = only days with GEX rank >= this."""
    O, H, L, C, T, D, CA = b.o, b.h, b.l, b.c, b.hhmm, b.day, b.cabs
    eng = Engine(CA, p["tick"])
    lo_, hi_, slm, fl = float(p.get("gp_lo", 0.2)), float(p.get("gp_hi", 0.7)), float(p.get("gp_sl", 1.5)), int(p.get("gp_flat", 1100))
    rk = float(p.get("gp_rank", -1))
    news = set()
    if p.get("gp_news"):
        import news_calendar
        news = news_calendar.days(p["gp_news"])
    gt = _gex_table() if rk >= 0 else None
    rngs, cur, hi, lo, last, prev = [], None, 0, 0, None, None
    tgt = stop = None
    for i in range(i0, i1):
        o, h, l, c, t, d = O[i], H[i], L[i], C[i], T[i], D[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        if not (830 < t <= 1500):
            if eng.pos != 0:
                eng.order(MKT, XLONG if eng.pos == 1 else XSHORT, None, "Out")
            continue
        if d != cur:
            if cur is not None:
                rngs.append(hi - lo)
                prev = last
            cur, hi, lo = d, h, l
            if prev is not None and len(rngs) >= 14 and d not in news:
                dat = sum(rngs[-14:]) / 14
                gap = (o - prev) / dat
                okg = True
                if gt is not None:
                    g = _gex_prev(gt, d)
                    okg = g is not None and g[1] >= rk
                if okg and lo_ <= abs(gap) <= hi_:
                    sd = -1 if gap > 0 else 1
                    eng.order(MKT, BUY if sd == 1 else SHORT, None, "GapFill")
                    tgt, stop = prev, None
        else:
            hi, lo = max(hi, h), min(lo, l)
        last = c
        if eng.pos != 0:
            xa = XLONG if eng.pos == 1 else XSHORT
            if stop is None:
                stop = eng.entry_px - eng.pos * slm * abs(eng.entry_px - tgt) if tgt is not None else eng.entry_px
            if t >= fl:
                eng.order(MKT, xa, None, "Flat")
            else:
                eng.order(STOP, xa, stop, "SL")
                if (tgt - eng.entry_px) * eng.pos > 0:
                    eng.order(LIMIT, xa, tgt, "Fill")
    return eng


def s34_pre_fomc(b, tf, i0, i1, p):
    """Pre-FOMC drift (2026-11-09; Lucca & Moench 2015), ES/NQ, CT: on FOMC statement days (news_calendar) buy at market
    at the close of the pf_entry bar and sell at market after the pf_exit bar (12:55, before the 13:00 statement).
    pf_sl = stop in x dATR (14-day mean RTH range), 0 = none; pf_side -1 = short instead (for checking)."""
    import news_calendar
    O, H, L, C, T, D, CA = b.o, b.h, b.l, b.c, b.hhmm, b.day, b.cabs
    eng = Engine(CA, p["tick"])
    fomc = news_calendar.days("fomc")
    ent, ex, sl, sd = int(p.get("pf_entry", 830)), int(p.get("pf_exit", 1255)), float(p.get("pf_sl", 0)), int(p.get("pf_side", 1))
    rngs, cur, hi, lo, done, stop = [], None, 0, 0, False, None
    for i in range(i0, i1):
        o, h, l, c, t, d = O[i], H[i], L[i], C[i], T[i], D[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        if 830 < t <= 1500:
            if d != cur:
                if cur is not None:
                    rngs.append(hi - lo)
                cur, hi, lo, done = d, h, l, False
            else:
                hi, lo = max(hi, h), min(lo, l)
        if eng.pos == 0:
            stop = None
            if d in fomc and not done and t >= ent and t < ex and len(rngs) >= 14:
                eng.order(MKT, BUY if sd == 1 else SHORT, None, "PreFOMC")
                done = True
        else:
            xa = XLONG if eng.pos == 1 else XSHORT
            if stop is None and sl > 0:
                stop = eng.entry_px - eng.pos * sl * sum(rngs[-14:]) / 14
            if t >= ex or t < 830:
                eng.order(MKT, xa, None, "Out")
            elif stop is not None:
                eng.order(STOP, xa, stop, "SL")
    return eng


def s35_halyard(b, tf, i0, i1, p):
    """PropQuantX Halyard MNQ 15min (user's PQXHalyardTradingview.txt, 2026-11-09), CT, 15m signal bars.
    Range = the 15m bar starting 05:00 UTC (23:00 CT under standard time, 00:00 CT under daylight time). The session
    rolls at 18:30 UTC (12:30 CST / 13:30 CDT); a session's weekday is the weekday it ends on. The first 15m close
    beyond the range consumes the session; if the weekday allows that side (hy_mon..hy_fri: B both, L, S, O off;
    default Monday long only) enter at market on the next minute, stop = opposite range edge, target = signal close
    +/- hy_rr x (close - stop) (both from the signal bar's close, as Pine's process_orders_on_close does). Optional
    reversal (hy_rev=1): after a losing first trade, the first later 15m close beyond the other edge enters the other
    way with hy_rev_rr. Flat at market after the session's last bar. hy_min / hy_max: range size gate in points.
    hy_lucid=1 (default): on NYSE closures / early closes flat after the 11:55 CT bar (the Pine carries it over)."""
    O, H, L, C, V, T, D, CA = b.o, b.h, b.l, b.c, b.v, b.hhmm, b.day, b.cabs
    eng = Engine(CA, p["tick"])
    tb = TFBars(15)
    rr, rev, rev_rr = float(p.get("hy_rr", 0.8)), int(p.get("hy_rev", 0)), float(p.get("hy_rev_rr", 1.0))
    mn, mx = float(p.get("hy_min", 0)), float(p.get("hy_max", 0))
    dmode = [str(p.get(k, v)).upper()[:1] for k, v in (("hy_mon", "L"), ("hy_tue", "B"), ("hy_wed", "B"),
                                                         ("hy_thu", "B"), ("hy_fri", "B"))]
    lucid = int(p.get("hy_lucid", 1))
    cl_, ea_ = nyse_calendar()
    short_days = (cl_ | ea_) if lucid else set()
    dst = {}

    def us_dst(od):
        y = date.fromordinal(od).year
        if y not in dst:
            m, n = date(y, 3, 8), date(y, 11, 1)
            dst[y] = (m.toordinal() + (6 - m.weekday()) % 7, n.toordinal() + (6 - n.weekday()) % 7)
        a, z = dst[y]
        return a <= od < z

    def sess_of(d, t):
        end = 1330 if us_dst(d) else 1230
        return d + 1 if t > end else d, end

    sess, rh, rl, state, fdir, ntr = None, None, None, 0, 0, 0
    stop = tgt = psess = None
    for i in range(i0, i1):
        o, h, l, c, t, d = O[i], H[i], L[i], C[i], T[i], D[i]
        if eng.orders:
            n_before = len(eng.trades)
            eng.fill(i, o, h, l)
            if len(eng.trades) > n_before and state == 1:
                tr = eng.trades[-1]
                state = 2 if (tr[4] - tr[3]) * tr[2] < 0 else 3
        s_, end = sess_of(d, t)
        if s_ != sess:
            sess, rh, rl, state, fdir, ntr = s_, None, None, 0, 0, 0
        wd = date.fromordinal(s_).weekday()
        mode = dmode[wd] if wd < 5 else "O"
        hol = s_ in short_days
        cutoff = 1155 if hol else end
        cl = tb.update(CA[i], o, h, l, c, V[i])
        for e_, bo, bh, bl, bc, bv in (cl or []):
            te = hhmm(e_)
            ds, _ = sess_of(e_ // 1440, te)
            if ds != sess:
                continue
            rng_end = 15 if us_dst(e_ // 1440) else 2315
            if te == rng_end:
                rh, rl, state = bh, bl, 0
                continue
            if rh is None or eng.pos != 0 or te >= cutoff:
                continue
            rok = (mn <= 0 or rh - rl >= mn) and (mx <= 0 or rh - rl <= mx)
            if not rok:
                continue
            up, dn = bc > rh, bc < rl
            psess = sess
            if state == 0 and (up or dn):
                state = 3
                if up and mode in "BL":
                    stop, tgt, state, fdir = rl, bc + (bc - rl) * rr, 1, 1
                    eng.order(MKT, BUY, None, "HY-L")
                elif dn and mode in "BS":
                    stop, tgt, state, fdir = rh, bc - (rh - bc) * rr, 1, -1
                    eng.order(MKT, SHORT, None, "HY-S")
            elif state == 2 and rev and mode in "BLS":
                if fdir == -1 and up and mode in "BL":
                    stop, tgt, state = rl, bc + (bc - rl) * rev_rr, 3
                    eng.order(MKT, BUY, None, "HY-RL")
                elif fdir == 1 and dn and mode in "BS":
                    stop, tgt, state = rh, bc - (rh - bc) * rev_rr, 3
                    eng.order(MKT, SHORT, None, "HY-RS")
        pend = any(x[0] == MKT for x in eng.orders)
        if eng.pos != 0 and not pend:
            xa = XLONG if eng.pos == 1 else XSHORT
            if (cutoff <= t <= end) or psess != sess:
                eng.order(MKT, xa, None, "Out")
            else:
                eng.order(STOP, xa, stop, "SL")
                eng.order(LIMIT, xa, tgt, "TP")
    return eng


GOLD_ANCHORS = [((2016, 1, 4), 835.0), ((2019, 1, 2), 766.0), ((2020, 1, 2), 729.0), ((2022, 1, 3), 640.0),
                ((2024, 1, 2), 486.0), ((2025, 1, 2), 336.0), ((2026, 9, 2), 0.0)]


def gold_offset(od):
    """Back-adjustment offset of GC.csv on CT day od (adjusted - real front-month price), linear between anchors
    (adjusted close vs the real GC front month on those dates; error ~1-2% of price). Used for % stops/targets."""
    pts = [(date(*d).toordinal(), v) for d, v in GOLD_ANCHORS]
    if od <= pts[0][0]:
        return pts[0][1]
    for (a, va), (z, vz) in zip(pts, pts[1:]):
        if od <= z:
            return va + (vz - va) * (od - a) / (z - a)
    return 0.0


def _lucid_days():
    cl_, ea_ = nyse_calendar()
    return cl_ | ea_


def s36_gold_donchian(b, tf, i0, i1, p):
    """Gold Donchian breakout (user's spec, 2026-11-09), CT. Channel = highest high / lowest low of the last dc_n
    (175) completed 60m bars, mid = their average. A 1m close above the upper band buys at market next minute (short
    mirrored); stop dc_sl (0.5%) / target dc_tp (1%) of the real price from the fill; once dc_trig (0.5%) in profit a
    trailing stop dc_trail (0.1%) behind the best high (low) since entry. One trade per breakout: a side re-arms only
    after a 1m close back through the mid. One position at a time. dc_lucid=1 (default): flat after the 15:40 CT bar
    (11:55 on NYSE closures / early closes), no entries 15:40-17:00. % use the real price (gold_offset)."""
    O, H, L, C, V, T, D, CA = b.o, b.h, b.l, b.c, b.v, b.hhmm, b.day, b.cabs
    eng = Engine(CA, p["tick"])
    tb = TFBars(60)
    n = int(p.get("dc_n", 175))
    slp, tpp = float(p.get("dc_sl", 0.5)) / 100, float(p.get("dc_tp", 1.0)) / 100
    trig, trail = float(p.get("dc_trig", 0.5)) / 100, float(p.get("dc_trail", 0.1)) / 100
    lucid = int(p.get("dc_lucid", 1))
    # improvement options (2026-11-09, off by default): entry window dc_t0..dc_t1 (CT hhmm), time exit after dc_maxm
    # minutes, trend filter = side of the EMA(dc_ema) of 60m closes, min channel width dc_wmin (% of price), news skip,
    # side (both|long|short), trail mode dc_tmode=close (trail from the best 1m close instead of the high/low)
    t0, t1 = int(p.get("dc_t0", 0)), int(p.get("dc_t1", 2400))
    maxm, ema_n, wmin = int(p.get("dc_maxm", 0)), int(p.get("dc_ema", 0)), float(p.get("dc_wmin", 0)) / 100
    side = str(p.get("dc_side", "both"))
    tclose = str(p.get("dc_tmode", "")) == "close"
    news = set()
    if p.get("dc_news"):
        import news_calendar
        news = news_calendar.days(p["dc_news"])
    ema = None
    ea = 2.0 / (ema_n + 1) if ema_n else 0
    # volatility filters (2026-11-09, off by default). dATR = mean session range (17:00-16:00 CT) of the last 14
    # sessions. dc_vol_lo / dc_vol_hi: trade only if dATR >= lo / <= hi x its 250-session median; dc_volp_lo /
    # dc_volp_hi: dATR as % of the real price; dc_er: efficiency ratio of the last dc_er_n 60m closes >= dc_er;
    # dc_cw_lo / dc_cw_hi: channel width / dATR band
    vlo, vhi = float(p.get("dc_vol_lo", 0)), float(p.get("dc_vol_hi", 0))
    vplo, vphi = float(p.get("dc_volp_lo", 0)), float(p.get("dc_volp_hi", 0))
    er_k, er_n = float(p.get("dc_er", 0)), int(p.get("dc_er_n", 24))
    cwlo, cwhi = float(p.get("dc_cw_lo", 0)), float(p.get("dc_cw_hi", 0))
    srng, sk, shl, dat, dmed = [], None, None, 0.0, 0.0
    c60 = []
    # kill switch (2026-11-09, as in SuperAlgo_Opening.pl): the leg stops for good once its closed-trade equity is
    # dc_kill_dd $ below its peak, or its last dc_kill_n trades sum to <= dc_kill_net $ (per contract, after ~$3.5
    # costs, MGC $10/pt). History 2016-2026 (filtered version): worst DD -$1,041, worst 20-trade sum -$235.
    k_dd, k_n, k_net = float(p.get("dc_kill_dd", 1500)), int(p.get("dc_kill_n", 20)), float(p.get("dc_kill_net", -500))
    pv = float(p.get("dc_pv", 10))
    k_eq = k_pk = 0.0
    k_last, killed, n_tr = [], False, 0
    short_days = _lucid_days() if lucid else set()
    hh, ll = [], []
    up = dn = mid = None
    arm_l = arm_s = True
    stop = tgt = best = None
    offc = {}
    for i in range(i0, i1):
        o, h, l, c, t, d = O[i], H[i], L[i], C[i], T[i], D[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        if len(eng.trades) > n_tr:
            for tr_ in eng.trades[n_tr:]:
                v = tr_[2] * (tr_[4] - tr_[3]) * pv - 3.5
                k_eq += v
                k_pk = max(k_pk, k_eq)
                k_last.append(v)
                if len(k_last) > k_n:
                    del k_last[0]
                if (k_dd and k_pk - k_eq >= k_dd) or (k_n and len(k_last) == k_n and sum(k_last) <= k_net):
                    killed = True
            n_tr = len(eng.trades)
        if d not in offc:
            offc[d] = gold_offset(d)
        P = c - offc[d]
        if eng.pos != 0 and eng.entry_i == i:
            e, s_ = eng.entry_px, eng.pos
            Pe = e - offc[d]
            stop, tgt, best = e - s_ * slp * Pe, e + s_ * tpp * Pe, e
        cl = tb.update(CA[i], o, h, l, c, V[i])
        for _, bo, bh, bl, bc, bv in (cl or []):
            hh.append(bh); ll.append(bl)
            c60.append(bc)
            if len(c60) > er_n + 1:
                del c60[0]
            if ema_n:
                ema = bc if ema is None else ema + ea * (bc - ema)
            if len(hh) > n:
                del hh[0]; del ll[0]
            if len(hh) == n:
                up, dn = max(hh), min(ll)
                mid = (up + dn) / 2
        k_ = d + (1 if t > 1600 else 0)
        if k_ != sk:
            if shl:
                srng.append(shl[0] - shl[1])
                if len(srng) >= 14:
                    dat = sum(srng[-14:]) / 14
                    srng_d = srng[-264:]
                    dl = sorted(sum(srng_d[x - 14:x]) / 14 for x in range(14, len(srng_d) + 1))
                    dmed = dl[len(dl) // 2]
            sk, shl = k_, (h, l)
        else:
            shl = (max(shl[0], h), min(shl[1], l))
        if up is None:
            continue
        if not arm_l and c < mid:
            arm_l = True
        if not arm_s and c > mid:
            arm_s = True
        cut = 1155 if (lucid and d in short_days) else 1540
        late = lucid and (cut <= t < 1700 or (d in short_days and t > cut))
        pend = any(x[0] == MKT for x in eng.orders)
        if eng.pos != 0 and not pend:
            s_ = eng.pos
            xa = XLONG if s_ == 1 else XSHORT
            if lucid and late:
                eng.order(MKT, xa, None, "Out")
                continue
            if maxm and i - eng.entry_i >= maxm:
                eng.order(MKT, xa, None, "Time")
                continue
            hb, lb_ = (c, c) if tclose else (h, l)
            best = max(best, hb) if s_ == 1 else min(best, lb_)
            Pe = eng.entry_px - offc[d]
            if (best - eng.entry_px) * s_ >= trig * Pe:
                ts = best - s_ * trail * Pe
                stop = max(stop, ts) if s_ == 1 else min(stop, ts)
            eng.order(STOP, xa, stop, "SL" if (stop - eng.entry_px) * s_ < 0 else "Trail")
            eng.order(LIMIT, xa, tgt, "TP")
        elif eng.pos == 0 and not pend and not late and not killed:
            ok = t0 <= t <= t1 if t0 <= t1 else (t >= t0 or t <= t1)
            ok = ok and d not in news and (up - dn) >= wmin * P
            if ok and (vlo or vhi or vplo or vphi or cwlo or cwhi):
                if not dat or not dmed:
                    ok = False
                else:
                    ok = ((not vlo or dat >= vlo * dmed) and (not vhi or dat <= vhi * dmed)
                          and (not vplo or dat >= vplo / 100 * P) and (not vphi or dat <= vphi / 100 * P)
                          and (not cwlo or up - dn >= cwlo * dat) and (not cwhi or up - dn <= cwhi * dat))
            if ok and er_k and len(c60) > er_n:
                path = sum(abs(c60[x] - c60[x - 1]) for x in range(1, len(c60)))
                ok = path > 0 and abs(c60[-1] - c60[0]) / path >= er_k
            if arm_l and c > up:
                arm_l = False
                if ok and side != "short" and (not ema_n or (ema is not None and c > ema)):
                    eng.order(MKT, BUY, None, "DC-L", attach=(slp * P, tpp * P))
            elif arm_s and c < dn:
                arm_s = False
                if ok and side != "long" and (not ema_n or (ema is not None and c < ema)):
                    eng.order(MKT, SHORT, None, "DC-S", attach=(slp * P, tpp * P))
    return eng


def s37_gold_atr_candle(b, tf, i0, i1, p):
    """Gold ATR candle breakout (user's spec, 2026-11-09), CT 60m bars. A completed 60m bar whose range > ac_k (2.5)
    x ATR(ac_n = 200, simple mean of true range over the previous 200 bars) and whose close sits in the outer ac_zone
    (25%) of its range on its own side (up bar: top 25% -> long; down bar: bottom 25% -> short) enters at market on
    the next minute; stop ac_sl (0.5%) / target ac_tp (3.5%) of the real price from the signal close. One position at
    a time. ac_lucid=1 (default): flat after the 15:40 CT bar (11:55 on NYSE closures / early closes), no entries
    15:40-17:00."""
    O, H, L, C, V, T, D, CA = b.o, b.h, b.l, b.c, b.v, b.hhmm, b.day, b.cabs
    eng = Engine(CA, p["tick"])
    tb = TFBars(60)
    k, n, zone = float(p.get("ac_k", 2.5)), int(p.get("ac_n", 200)), float(p.get("ac_zone", 0.25))
    slp, tpp = float(p.get("ac_sl", 0.5)) / 100, float(p.get("ac_tp", 3.5)) / 100
    lucid = int(p.get("ac_lucid", 1))
    short_days = _lucid_days() if lucid else set()
    trs, pc = [], None
    stop = tgt = None
    for i in range(i0, i1):
        o, h, l, c, t, d = O[i], H[i], L[i], C[i], T[i], D[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        cut = 1155 if (lucid and d in short_days) else 1540
        late = lucid and (cut <= t < 1700 or (d in short_days and t > cut))
        cl = tb.update(CA[i], o, h, l, c, V[i])
        sig = 0
        for _, bo, bh, bl, bc, bv in (cl or []):
            tr = bh - bl if pc is None else max(bh, pc) - min(bl, pc)
            rng = bh - bl
            if len(trs) >= n and rng > k * (sum(trs[-n:]) / n) and rng > 0:
                if bc > bo and bc >= bh - zone * rng:
                    sig = 1
                elif bc < bo and bc <= bl + zone * rng:
                    sig = -1
                if sig:
                    P = bc - gold_offset(d)
                    stop, tgt = bc - sig * slp * P, bc + sig * tpp * P
            trs.append(tr)
            if len(trs) > n + 5:
                del trs[0]
            pc = bc
        pend = any(x[0] == MKT for x in eng.orders)
        if eng.pos != 0 and not pend:
            xa = XLONG if eng.pos == 1 else XSHORT
            if lucid and late:
                eng.order(MKT, xa, None, "Out")
            else:
                eng.order(STOP, xa, stop, "SL")
                eng.order(LIMIT, xa, tgt, "TP")
        elif eng.pos == 0 and not pend and sig and not late:
            eng.order(MKT, BUY if sig == 1 else SHORT, None, "AC-L" if sig == 1 else "AC-S",
                      attach=(abs(c - stop), abs(tgt - c)))
    return eng



def s38_overnight_drift(b, tf, i0, i1, p):
    """Overnight drift (2026-11-10; Boyarchenko, Larsen & Whelan 2023 "The Overnight Drift"), NQ/ES/GC, CT, 1m.
    Buy at market after the first bar at/after od_entry in the evening (session open side, t > 16:00), sell at market
    after the first bar at/after od_exit in the morning (t <= 08:30). od_prev: previous RTH move (close - prior RTH
    close) / dATR(14) must be <= od_prev (e.g. 0 or -0.5; 99 = every day). od_sl = stop in x dATR (0 = none);
    od_side -1 = short instead (for checking)."""
    O, H, L, C, T, D, CA = b.o, b.h, b.l, b.c, b.hhmm, b.day, b.cabs
    eng = Engine(CA, p["tick"])
    ent, ex = int(p.get("od_entry", 1700)), int(p.get("od_exit", 700))
    thr, sl, side = float(p.get("od_prev", 99)), float(p.get("od_sl", 0)), int(p.get("od_side", 1))
    rngs, closes, cur, hi, lo, last, done, stop = [], [], None, 0.0, 0.0, None, False, None
    for i in range(i0, i1):
        o, h, l, c, t, d = O[i], H[i], L[i], C[i], T[i], D[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        if 830 < t <= 1500:
            if d != cur:
                if cur is not None:
                    rngs.append(hi - lo)
                    closes.append(last)
                cur, hi, lo = d, h, l
            else:
                hi, lo = max(hi, h), min(lo, l)
            last = c
            done = False
        evening = t > 1600 and t >= ent
        if eng.pos == 0:
            stop = None
            if evening and not done and len(rngs) >= 14 and last is not None and len(closes) >= 1:
                datr = sum(rngs[-14:]) / 14
                mv = (last - closes[-1]) / datr if cur is not None else 0.0
                done = True
                if mv <= thr:
                    eng.order(MKT, BUY if side == 1 else SHORT, None, "OD")
        else:
            xa = XLONG if eng.pos == 1 else XSHORT
            if stop is None and sl > 0 and rngs:
                stop = eng.entry_px - eng.pos * sl * sum(rngs[-14:]) / 14
            if t <= 1600 and t >= ex:
                eng.order(MKT, xa, None, "OD_X")
            elif stop is not None:
                eng.order(STOP, xa, stop, "OD_SL")
    return eng


def s39_news_reversal(b, tf, i0, i1, p):
    """News-release reversal (2026-11-10), NQ/ES, CT, 1m: on CPI / NFP days (news_calendar, nr_events) measure the move
    from the close of the nr_t0 bar (07:30 release) to the close of the bar before nr_ent, then enter AGAINST it at
    market on the nr_ent bar's open (nr_mode 1 = with it); out at market at nr_exit. nr_sl = stop in x dATR (14-day
    mean RTH range, 0 = none)."""
    import news_calendar
    O, H, L, C, T, D, CA = b.o, b.h, b.l, b.c, b.hhmm, b.day, b.cabs
    eng = Engine(CA, p["tick"])
    evd = set()
    for e in str(p.get("nr_events", "cpi,nfp")).split(","):
        evd |= news_calendar.days(e.strip())
    t0, ent, ex = int(p.get("nr_t0", 730)), int(p.get("nr_ent", 745)), int(p.get("nr_exit", 1000))
    sl, mode = float(p.get("nr_sl", 0)), int(p.get("nr_mode", -1))
    em = (ent // 100) * 60 + ent % 100 - 1
    ent1 = (em // 60) * 100 + em % 60                   # the bar before the entry bar
    rngs, cur, hi, lo, ref, done, stop = [], None, 0.0, 0.0, None, None, None
    for i in range(i0, i1):
        o, h, l, c, t, d = O[i], H[i], L[i], C[i], T[i], D[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        if 830 < t <= 1500:
            if d != cur:
                if cur is not None:
                    rngs.append(hi - lo)
                cur, hi, lo = d, h, l
            else:
                hi, lo = max(hi, h), min(lo, l)
        if t == t0:
            ref = (d, c)
        if eng.pos == 0:
            stop = None
            if t == ent1 and d in evd and done != d and ref is not None and ref[0] == d and len(rngs) >= 14:
                mv = c - ref[1]
                done = d
                if mv != 0:
                    side = mode * (1 if mv > 0 else -1)
                    eng.order(MKT, BUY if side == 1 else SHORT, None, "NR")
        else:
            xa = XLONG if eng.pos == 1 else XSHORT
            if stop is None and sl > 0:
                stop = eng.entry_px - eng.pos * sl * sum(rngs[-14:]) / 14
            if t >= ex - 1 and t < 1600:
                eng.order(MKT, xa, None, "NR_X")
            elif stop is not None:
                eng.order(STOP, xa, stop, "NR_SL")
    return eng


class _Merged:
    """Trades of several tranche engines, sorted by entry (pos 0 so runners treat it as flat at the end)."""
    def __init__(self, engines):
        self.trades = sorted((t for e in engines for t in e.trades), key=lambda t: (t[0], t[1]))
        self.pos = 0


def _news_set(spec):
    out = set()
    if spec:
        import news_calendar
        for x in str(spec).split(";"):
            out |= news_calendar.days(x)
    return out


def s40_gold_trend_tranches(b, tf, i0, i1, p):
    """Gold Trend Tranches (2026-11-10), GC 1m, CT. Noise-band intraday trend with up to tt_n stacked tranches.
    Reference = the 07:20 CT close (COMEX open, tt_ref=comex) or the 17:00 session open (tt_ref=sess). At each
    checkpoint every tt_step minutes from tt_t0 to tt_t1 (clock-aligned), band = mean |close - ref| at that clock time
    over the last tt_lb sessions. Close > ref + tt_k x band -> add a long tranche (one per checkpoint, at most tt_n,
    next minute at market); mirror for shorts. An opposite signal closes every tranche. Exit at a checkpoint when the
    close is back below max(ref + tt_kx x band, session VWAP) (tt_vwap=1) / ref + tt_kx x band (tt_vwap=0); hard stop
    per tranche tt_sl x dATR (14-session mean session range) from its fill; flat after tt_flat (15:40).
    tt_side both|long|short. tt_vol_lo: skip sessions whose dATR < x its 250-session median. tt_news: skip days.
    tt_only=k returns only tranche k (1-based) for the one-position standard report."""
    O, H, L, C, V, T, D = b.o, b.h, b.l, b.c, b.v, b.hhmm, b.day
    N = int(p.get("tt_n", 3))
    engs = [Engine(b.cabs, p["tick"]) for _ in range(N)]
    ref_mode, step = p.get("tt_ref", "comex"), int(p.get("tt_step", 30))
    t0, t1, flat = int(p.get("tt_t0", 800)), int(p.get("tt_t1", 1200)), int(p.get("tt_flat", 1540))
    k, kx, lb = float(p.get("tt_k", 1.0)), float(p.get("tt_kx", 1.0)), int(p.get("tt_lb", 14))
    use_vwap, sl = int(p.get("tt_vwap", 1)), float(p.get("tt_sl", 0.5))
    side_ok = p.get("tt_side", "both")
    vlo = float(p.get("tt_vol_lo", 0))
    news = _news_set(p.get("tt_news"))
    trend_n = int(p.get("tt_trend", 0))     # >0: trade only the side of prev session close vs SMA(trend_n) closes
    closes, last_c, tdir = [], None, 0
    cps = []
    m = (t0 // 100) * 60 + t0 % 100
    while m <= (t1 // 100) * 60 + t1 % 100:
        cps.append((m // 60) * 100 + m % 60)
        m += step
    cpset = set(cps)
    hist = {c: [] for c in cps}          # |close - ref| per checkpoint, past sessions
    today = {}
    rngs, a14s = [], []
    sopen = ref = shi = slo = datr = None
    pv = vv = 0.0
    ntr, ok = 0, False
    stops = [None] * N
    for i in range(i0, i1):
        o, h, l, c, t, d = O[i], H[i], L[i], C[i], T[i], D[i]
        for e in engs:
            if e.orders:
                e.fill(i, o, h, l)
        if i == i0 or (t > 1600 and (T[i - 1] <= 1600 or D[i - 1] != d)):
            if shi is not None:
                rngs.append(shi - slo)
                closes.append(last_c)
                for cp, v in today.items():
                    hist[cp].append(v)
            if trend_n and len(closes) >= trend_n:
                tdir = 1 if closes[-1] > sum(closes[-trend_n:]) / trend_n else -1
            today = {}
            sopen, ref, shi, slo, pv, vv, ntr = o, None, h, l, 0.0, 0.0, 0
            a14 = sum(rngs[-14:]) / 14 if len(rngs) >= 14 else None
            a14s.append(a14)
            ok, datr = a14 is not None, a14
            if ok and vlo:
                past = [x for x in a14s[-251:-1] if x is not None]
                ok = len(past) >= 100 and a14 >= vlo * sorted(past)[len(past) // 2]
        shi, slo = max(shi, h), min(slo, l)
        if t <= 1600:
            last_c = c
        pv += (h + l + c) / 3 * V[i]
        vv += V[i]
        vwap = pv / vv if vv else c
        if ref_mode == "sess":
            ref = sopen
        elif t == 720 or (ref is None and 720 < t <= 1600):
            ref = c
        if t in cpset and ref is not None and t <= 1600:
            today[t] = abs(c - ref)
        for j, e in enumerate(engs):
            if e.pos == 0:
                stops[j] = None
            elif stops[j] is None:
                stops[j] = e.entry_px - e.pos * sl * datr
        pos = sum(e.pos for e in engs)
        exit_all = bool(pos) and flat <= t <= 1600
        if t in cpset and ref is not None and ok and t <= 1600 and len(hist[t]) >= lb and d not in news:
            band = sum(hist[t][-lb:]) / lb
            sig = 1 if c > ref + k * band else (-1 if c < ref - k * band else 0)
            if (side_ok == "long" and sig < 0) or (side_ok == "short" and sig > 0):
                sig = 0
            if trend_n and sig != tdir:
                sig = 0
            if pos:
                d0 = 1 if pos > 0 else -1
                lvl = ref + d0 * kx * band
                if use_vwap:
                    lvl = max(lvl, vwap) if d0 > 0 else min(lvl, vwap)
                if sig == -d0 or (d0 > 0 and c < lvl) or (d0 < 0 and c > lvl):
                    exit_all = True
            if sig and not exit_all and t < flat and (pos == 0 or sig == (1 if pos > 0 else -1)):
                if pos == 0:
                    ntr = 0
                free = [j for j, e in enumerate(engs) if e.pos == 0 and not e.orders]
                if free and ntr < N:
                    engs[free[0]].order(MKT, BUY if sig > 0 else SHORT, None, "TT%d" % (ntr + 1))
                    ntr += 1
        for j, e in enumerate(engs):
            if e.pos:
                xa = XLONG if e.pos == 1 else XSHORT
                if exit_all:
                    e.order(MKT, xa, None, "TT_X")
                else:
                    e.order(STOP, xa, stops[j], "TT_SL")
    only = int(p.get("tt_only", 0))
    return engs[only - 1] if only else _Merged(engs)


def s41_gold_comex_dip(b, tf, i0, i1, p):
    """Gold COMEX Dip Fade (2026-11-10), GC 1m, CT. dATR = mean session range (17:00-16:00) of the last 14 sessions.
    Anchor (df_ref): comex = 07:20 CT close; chigh = highest high since 07:20 (rolling); shigh = session high since
    17:00. From df_t0 to df_t1 a buy limit rests at anchor - df_k x dATR (one trade a day). Exit: target df_tp x dATR
    above the fill (0 = none), stop df_sl x dATR below, flat after df_flat. df_side=short mirrors (fade a rally,
    anchors = lows). Filters: df_trend=1 only if the previous session close > SMA(df_sma) of session closes (-1 =
    below); df_vol_lo / df_vol_hi = dATR vs its 250-session median; df_news = skip days (cpi;nfp;fomc)."""
    O, H, L, C, T, D = b.o, b.h, b.l, b.c, b.hhmm, b.day
    eng = Engine(b.cabs, p["tick"])
    refm, kk = p.get("df_ref", "chigh"), float(p.get("df_k", 0.5))
    t0, t1, flat = int(p.get("df_t0", 800)), int(p.get("df_t1", 1130)), int(p.get("df_flat", 1540))
    tp, sl = float(p.get("df_tp", 0.3)), float(p.get("df_sl", 0.5))
    side = -1 if p.get("df_side", "long") == "short" else 1
    trend, sma_n = int(p.get("df_trend", 0)), int(p.get("df_sma", 20))
    vlo, vhi = float(p.get("df_vol_lo", 0)), float(p.get("df_vol_hi", 0))
    news = _news_set(p.get("df_news"))
    rngs, closes, a14s = [], [], []
    shi = slo = anc_c = chi = clo = datr = last_c = None
    done, ok = False, False
    stop_px = tgt_px = pend = None
    tick = p["tick"]
    import engine as engine_mod
    for i in range(i0, i1):
        o, h, l, c, t, d = O[i], H[i], L[i], C[i], T[i], D[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        if pend is not None and eng.pos == 0:
            # limit entry (the engine fills only exits): touch, or one tick through with --limit-fill through
            thr = tick if engine_mod.LIMIT_THROUGH else 0.0
            px = None
            if side == 1 and l <= pend - thr:
                px = min(o, pend)
            elif side == -1 and h >= pend + thr:
                px = max(o, pend)
            if px is not None:
                eng._open(i, side, px, "DF")
                eng.entry_kind = LIMIT
                stop_px = eng.entry_px - side * sl * datr
                tgt_px = eng.entry_px + side * tp * datr if tp > 0 else None
                done = True
                if (side == 1 and l <= stop_px) or (side == -1 and h >= stop_px):
                    eng._close(i, stop_px, STOP, "DF_SL")     # worst case: the stop is hit on the fill bar
        pend = None
        if i == i0 or (t > 1600 and (T[i - 1] <= 1600 or D[i - 1] != d)):
            if shi is not None:
                rngs.append(shi - slo)
                closes.append(last_c)
            shi, slo, anc_c, chi, clo, done = h, l, None, None, None, False
            a14 = sum(rngs[-14:]) / 14 if len(rngs) >= 14 else None
            a14s.append(a14)
            ok, datr = a14 is not None, a14
            if ok and (vlo or vhi):
                past = [x for x in a14s[-251:-1] if x is not None]
                med = sorted(past)[len(past) // 2] if len(past) >= 100 else None
                ok = med is not None and (not vlo or a14 >= vlo * med) and (not vhi or a14 <= vhi * med)
            if ok and trend:
                if len(closes) < sma_n:
                    ok = False
                else:
                    up = closes[-1] > sum(closes[-sma_n:]) / sma_n
                    ok = up if trend == 1 else not up
        if t <= 1600:
            last_c = c
        shi, slo = max(shi, h), min(slo, l)
        if anc_c is None and 720 <= t <= 1600:
            anc_c = chi = clo = c
        elif anc_c is not None and t <= 1600:
            chi, clo = max(chi, h), min(clo, l)
        if eng.pos == 0:
            stop_px = tgt_px = None
        if eng.pos == 0 and not done and ok and anc_c is not None and t0 <= t < t1 and d not in news:
            if refm == "comex":
                a = anc_c
            elif refm == "shigh":
                a = shi if side == 1 else slo
            else:
                a = chi if side == 1 else clo
            lim = a - side * kk * datr
            if (side == 1 and c > lim) or (side == -1 and c < lim):
                q = lim / tick
                pend = (math.floor(q + 1e-9) if side == 1 else math.ceil(q - 1e-9)) * tick
        if eng.pos != 0:
            xa = XLONG if eng.pos == 1 else XSHORT
            if flat <= t <= 1600:
                eng.order(MKT, xa, None, "DF_X")
            else:
                eng.order(STOP, xa, stop_px, "DF_SL")
                if tgt_px is not None:
                    eng.order(LIMIT, xa, tgt_px, "DF_TP")
    return eng


def s42_gantline(b, tf, i0, i1, p):
    """Gantline (user's gantline_strategy.py, 2026-11-10), GC, signals on clock-aligned 1h bars built from the 1m
    data, executed on 1m bars. All rule times are New York (ET = CT + 1h). Asia 18:00-02:00 ET sets the range;
    London (02:00-09:30) must close beyond exactly one side and never beyond the other; efficiency of the move from
    the broken edge to London's extreme close (net / sum of |close changes|, first bar at the extreme) >= gl_eff.
    The first 1h bar in 09:30-11:00 ET that comes back to the edge (close back inside or low within gl_tol x ATR(10)
    of 1h true ranges) is the only candidate: entry if it closes beyond the edge, volume <= gl_vol x mean of the
    previous 10 bars at the same clock time, and its close location (2C-H-L)/(H-L) >= gl_flow in the trade's
    direction. Market entry at the next bar's open, stop gl_sl / target gl_tp points from the fill, flat after the
    gl_flat CT bar (15:45 = 16:45 ET). gl_label = start (pandas default: 1h bars stamped by their start) or end
    (stamped by their close) decides which 1h bars fall in each window."""
    O, H, L, C, V, T, D, CA = b.o, b.h, b.l, b.c, b.v, b.hhmm, b.day, b.cabs
    eng = Engine(CA, p["tick"])
    eff_min, flow_min, tol = float(p.get("gl_eff", 0.6)), float(p.get("gl_flow", 0.2)), float(p.get("gl_tol", 0.1))
    vmult, vdays, atr_len = float(p.get("gl_vol", 1.2)), int(p.get("gl_vdays", 10)), int(p.get("gl_atr", 10))
    sl, tp, flat = float(p.get("gl_sl", 6.0)), float(p.get("gl_tp", 4.0)), int(p.get("gl_flat", 1545))
    end_label = p.get("gl_label", "start") == "end"
    side_only = p.get("gl_side", "both")
    vhist, trs = {}, []
    hb = None                    # current 1h bar [o, h, l, c, v, start_cabs]
    prev_hc = None
    top = bot = None
    st = {}
    for i in range(i0, i1):
        o, h, l, c, t = O[i], H[i], L[i], C[i], T[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        if i == i0 or (t > 1600 and (T[i - 1] <= 1600 or D[i - 1] != D[i])):
            top = bot = None     # session day rolls at 17:00 CT = 18:00 ET
            st = dict(up=None, dn=None, pu=0.0, pd=0.0, xu=None, xd=None, eu=0.0, ed=0.0, lc=None, done=False)
        bk = (CA[i] - 1) // 60
        if hb is None or hb[5] != bk:
            hb = [o, h, l, c, V[i], bk]
        else:
            hb[1] = max(hb[1], h); hb[2] = min(hb[2], l); hb[3] = c; hb[4] += V[i]
        complete = i + 1 >= i1 or (CA[i + 1] - 1) // 60 != bk
        if complete:
            ho, hh, hl_, hc, hv = hb[0], hb[1], hb[2], hb[3], hb[4]
            start_ct = (bk * 60) % 1440
            m = (start_ct + 60 + (60 if end_label else 0)) % 1440          # ET minute label of the 1h bar
            tr = hh - hl_ if prev_hc is None else max(hh - hl_, abs(hh - prev_hc), abs(hl_ - prev_hc))
            prev_hc = hc
            trs.append(tr)
            atr = sum(trs[-atr_len:]) / atr_len if len(trs) >= atr_len else None
            past = vhist.setdefault(m, [])
            base = sum(past[-vdays:]) / vdays if len(past) >= vdays else None
            past.append(hv)
            if m >= 1080 or m < 120:
                top = hh if top is None else max(top, hh)
                bot = hl_ if bot is None else min(bot, hl_)
            elif 120 <= m < 570 and top is not None:
                # up side: first close above top, path and extreme close
                if st["up"] is None and hc > top:
                    st["up"], st["pu"], st["xu"], st["eu"] = True, abs(hc - top), hc, abs(hc - top)
                elif st["up"]:
                    st["pu"] += abs(hc - st["lc"])
                    if hc > st["xu"]:
                        st["xu"], st["eu"] = hc, st["pu"]
                if st["dn"] is None and hc < bot:
                    st["dn"], st["pd"], st["xd"], st["ed"] = True, abs(hc - bot), hc, abs(hc - bot)
                elif st["dn"]:
                    st["pd"] += abs(hc - st["lc"])
                    if hc < st["xd"]:
                        st["xd"], st["ed"] = hc, st["pd"]
                st["lc"] = hc
            elif 570 <= m < 660 and top is not None and not st["done"]:
                lng, sht = bool(st["up"]) and not st["dn"], bool(st["dn"]) and not st["up"]
                band = tol * atr if atr is not None else None
                tl = lng and (hc <= top or (band is not None and hl_ <= top + band))
                ts = sht and (hc >= bot or (band is not None and hh >= bot - band))
                cnt = p.get("_cnt")                                     # optional filter funnel counters
                if cnt is not None:
                    cnt["days"] = cnt.get("days", 0) + (m == 600)
                    cnt["one_side"] = cnt.get("one_side", 0) + (m == 600 and (lng or sht))
                if (tl or ts) and cnt is not None:
                    e_ = ((st["xu"] - top) / st["eu"] if st["eu"] else 0) if lng else \
                         ((bot - st["xd"]) / st["ed"] if st["ed"] else 0)
                    c_ = (2 * hc - hh - hl_) / (hh - hl_) if hh > hl_ else -9
                    f = [("touch", True), ("beyond", (lng and hc > top) or (sht and hc < bot)),
                         ("eff", e_ >= eff_min), ("vol", base is not None and hv <= vmult * base),
                         ("clv", (lng and c_ >= flow_min) or (sht and -c_ >= flow_min))]
                    ok_ = True
                    for k, v in f:
                        cnt["solo_" + k] = cnt.get("solo_" + k, 0) + bool(v)
                        ok_ = ok_ and bool(v)
                        cnt["cum_" + k] = cnt.get("cum_" + k, 0) + ok_
                if tl or ts:
                    st["done"] = True                                   # only the first touch counts
                    eff = ((st["xu"] - top) / st["eu"] if st["eu"] else 0) if lng else \
                          ((bot - st["xd"]) / st["ed"] if st["ed"] else 0)
                    clv = (2 * hc - hh - hl_) / (hh - hl_) if hh > hl_ else None
                    gate = eff >= eff_min and base is not None and hv <= vmult * base and clv is not None
                    if gate and eng.pos == 0 and t < flat:
                        if lng and hc > top and clv >= flow_min and side_only != "short":
                            eng.order(MKT, BUY, None, "GL.L", attach=(sl, tp))
                        elif sht and hc < bot and -clv >= flow_min and side_only != "long":
                            eng.order(MKT, SHORT, None, "GL.S", attach=(sl, tp))
        if eng.pos != 0:
            xa = XLONG if eng.pos == 1 else XSHORT
            if flat <= t <= 1600:
                eng.order(MKT, xa, None, "GL_X")
            else:
                eng.order(STOP, xa, eng.entry_px - eng.pos * sl, "GL_SL")
                eng.order(LIMIT, xa, eng.entry_px + eng.pos * tp, "GL_TP")
    return eng

def s43_phase_osc(b, tf, i0, i1, p):
    """Saty Phase Oscillator (user's NQPhaseOscillatorStrategy.cs / ATR_NORMALIZED_PHASE_MOMENTUM v1, 2026-11-10), NQ,
    10m ETH bars clock-aligned in CT. PO = EMA3(100 x (close - EMA21) / (3 x ATR14)), ATR Wilder (simple seed),
    on every 10m bar of the session. A 10m close crossing above +100 (prev <= 100 < now) goes long, below -100 short,
    at market on the next minute. Entries only on bars closing po_t0..po_t1 CT (default 08:30-10:00 = 09:30-11:00 ET,
    the .cs's inclusive window). In a position: the opposite cross reverses inside the window, exits outside it.
    No stop, no target. Flat at market after the po_flat bar (15:00 CT = 16:00 ET); on NYSE closures / early closes
    flat after 11:50 CT. po_sl (pts, 0 = none) optional stop from the fill; po_max = max entries a day (0 = no cap);
    po_htf (0 = off): only trade with the side of the 60m PO sign (higher-time-frame check)."""
    O, H, L, C, V, T, D, CA = b.o, b.h, b.l, b.c, b.v, b.hhmm, b.day, b.cabs
    eng = Engine(CA, p["tick"])
    tf_ = int(p.get("po_tf", 10)) or 10
    tb = TFBars(tf_)
    t0, t1, flat = int(p.get("po_t0", 830)), int(p.get("po_t1", 1000)), int(p.get("po_flat", 1500))
    sl, mx, htf = float(p.get("po_sl", 0)), int(p.get("po_max", 0)), int(p.get("po_htf", 0))
    # revamp options (2026-11-10, off by default): po_lvl = cross level (100); po_bias = "short" (shorts only on short
    # overnight-bias days) / "both" (never against the bias), bias = 08:30 open in the 00:00-08:30 range (>= 0.67 long,
    # <= 0.33 short); po_sl_datr = stop this x dATR (14-session mean RTH range) from the fill; po_vol_lo = skip days
    # whose dATR < this x its 250-session median; po_side = long|short|both; po_noopp = 1: the opposite cross only
    # exits (never reverses)
    lvl, pbias = float(p.get("po_lvl", 100)), str(p.get("po_bias", "") or "")
    sl_d, vlo, pside = float(p.get("po_sl_datr", 0)), float(p.get("po_vol_lo", 0)), str(p.get("po_side", "both"))
    noopp = int(p.get("po_noopp", 0))
    on_d, on_h, on_l, bias_v, rth_d, rth_h, rth_l = None, 0.0, 0.0, 0, None, 0.0, 0.0
    rngs, dhist, dat, day_ok, bias_day = [], [], 0.0, True, None
    cl_, ea_ = nyse_calendar()
    short_days = cl_ | ea_
    a21, a3 = 2.0 / 22, 2.0 / 4

    class _PO:
        def __init__(s):
            s.ema = s.atr = s.po = s.pc = None
            s.n = 0
            s.trs = 0.0

        def up(s, h, l, c):
            s.ema = c if s.ema is None else s.ema + a21 * (c - s.ema)
            tr = h - l if s.pc is None else max(h, s.pc) - min(l, s.pc)
            s.pc = c
            s.n += 1
            if s.n <= 14:
                s.trs += tr
                s.atr = s.trs / s.n
            else:
                s.atr = (s.atr * 13 + tr) / 14
            if s.n < 14 or s.atr <= 0:
                return None, None
            raw = 100.0 * (c - s.ema) / (3.0 * s.atr)
            prev = s.po
            s.po = raw if s.po is None else s.po + a3 * (raw - s.po)
            return prev, s.po

    pos_check = lambda e: e.pos
    po10, po60 = _PO(), _PO()
    tb60 = TFBars(60)
    sign60 = 0
    day_n, cur_d = 0, None
    for i in range(i0, i1):
        o, h, l, c, t, d = O[i], H[i], L[i], C[i], T[i], D[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        hol = d in short_days
        if t <= 830:
            if d != on_d:
                on_d, on_h, on_l = d, h, l
            else:
                on_h, on_l = max(on_h, h), min(on_l, l)
        if 830 < t <= 1500:
            if d != rth_d:
                if rth_d is not None:
                    rngs.append(rth_h - rth_l)
                rth_d, rth_h, rth_l = d, h, l
                bias_v, bias_day = 0, d
                if on_d == d and on_h > on_l:
                    x = (o - on_l) / (on_h - on_l)
                    bias_v = 1 if x >= 0.67 else (-1 if x <= 0.33 else 0)
                day_ok = True
                if len(rngs) >= 14:
                    dat = sum(rngs[-14:]) / 14
                    if vlo and len(dhist) >= 60:
                        hs = sorted(dhist[-250:])
                        day_ok = dat >= vlo * hs[len(hs) // 2]
                    dhist.append(dat)
            else:
                rth_h, rth_l = max(rth_h, h), min(rth_l, l)
        cut = 1150 if hol else flat
        for _, bo, bh, bl, bc, bv in (tb60.update(CA[i], o, h, l, c, V[i]) or []):
            _, v60 = po60.up(bh, bl, bc)
            if v60 is not None:
                sign60 = 1 if v60 > 0 else -1
        pend = any(x[0] == MKT for x in eng.orders)
        for e_, bo, bh, bl, bc, bv in (tb.update(CA[i], o, h, l, c, V[i]) or []):
            te = hhmm(e_)
            prev, now = po10.up(bh, bl, bc)
            if prev is None or now is None or pend:
                continue
            if e_ // 1440 != cur_d:
                cur_d, day_n = e_ // 1440, 0
            up = prev <= lvl < now
            dn = prev >= -lvl > now
            if not (up or dn):
                continue
            win = t0 <= te <= t1 and not (hol and te > 1100)
            sd = 1 if up else -1
            ok_new = win and (not mx or day_n < mx) and (not htf or sign60 == sd) and day_ok
            if pside != "both" and (pside == "long") != (sd == 1):
                ok_new = False
            if pbias and bias_day == e_ // 1440:
                if pbias == "short" and sd == -1 and bias_v != -1:
                    ok_new = False
                if pbias == "both" and bias_v == -sd:
                    ok_new = False
            if noopp and pos_check(eng) == -sd:
                ok_new = False
            pos = eng.pos
            if pos == -sd:
                eng.order(MKT, XLONG if pos == 1 else XSHORT, None, "Opp")
                pend = True
                if ok_new:
                    eng.order(MKT, BUY if sd == 1 else SHORT, None, "PO-L" if sd == 1 else "PO-S")
                    day_n += 1
            elif pos == 0 and ok_new:
                eng.order(MKT, BUY if sd == 1 else SHORT, None, "PO-L" if sd == 1 else "PO-S")
                pend = True
                day_n += 1
        pend = any(x[0] == MKT for x in eng.orders)
        if eng.pos != 0 and not pend:
            xa = XLONG if eng.pos == 1 else XSHORT
            if cut <= t < 1700:
                eng.order(MKT, xa, None, "Close")
            else:
                stp = sl if sl else (sl_d * dat if sl_d and dat else 0)
                if stp:
                    eng.order(STOP, xa, eng.entry_px - eng.pos * stp, "SL")
    return eng


def s44_crosstree(b, tf, i0, i1, p):
    """Crosstree (user's crosstree_gc_10m.py, 2026-11-11), GC 10m bars clock-aligned in CT (ET = CT + 1h).
    Direction: the 08:30 CT bar's open vs the overnight VWAP (HLC3 x volume of 10m bars since the 17:00 CT session
    open) as of the bar before: above = longs only today, below = shorts only. Range = high/low of the 08:30, 08:40 and
    08:50 CT bars. Break: from the bar opening 09:00 CT to the bar opening before ct_last (15:00 CT = 16:00 ET), the
    first close > range +/- 2 ticks on today's side arms; a close beyond the other side first ends the day. Pullback:
    after the break, the first bar whose wick reaches session VWAP (from 08:30 CT) +/- 0.75 x ATR7 (simple), closes
    outside the range on the break side and in the trade's direction; a close beyond the other side first ends the
    day. ATR14 (Wilder) on that bar must be >= 0.75 x its mean over the previous 100 bars, else no trade. Market entry
    at the next bar's open (next minute here); stop 3 / target 1 x ATR21 (Wilder) of the pullback bar from the fill,
    live on the fill bar. Flat after ct_flat (default 15:40 CT for Lucid; 1600 = the file's 17:00 ET session close).
    One setup a day. Options ct_stop/ct_tgt/ct_band/ct_vol/ct_brk (ticks)/ct_side."""
    O, H, L, C, V, T, D, CA = b.o, b.h, b.l, b.c, b.v, b.hhmm, b.day, b.cabs
    eng = Engine(CA, p["tick"])
    tk = p["tick"]
    tb = TFBars(10)
    k_sl, k_tp = float(p.get("ct_stop", 3.0)), float(p.get("ct_tgt", 1.0))
    band_k, vol_k, brk = float(p.get("ct_band", 0.75)), float(p.get("ct_vol", 0.75)), float(p.get("ct_brk", 2)) * tk
    last, flat, sidep = int(p.get("ct_last", 1500)), int(p.get("ct_flat", 1540)), str(p.get("ct_side", "both"))
    # improvement options (2026-11-11, off by default): ct_drift = min |08:30 open - overnight VWAP| in ATR21 units;
    # ct_brk_last = no break after this CT bar open (hhmm); ct_pb_last = no pullback entry after this; ct_trend = n:
    # trade only with the sign of (last session close - mean of the last n session closes); ct_news = skip these days;
    # ct_maxbar = exit after this many minutes
    min_drift, brk_last = float(p.get("ct_drift", 0)), int(p.get("ct_brk_last", 2400))
    pb_last, trend_n, maxm = int(p.get("ct_pb_last", 2400)), int(p.get("ct_trend", 0)), int(p.get("ct_maxbar", 0))
    news = set()
    if p.get("ct_news"):
        import news_calendar
        news = news_calendar.days(p["ct_news"])
    sess_closes, last_close = [], None
    cl_, ea_ = nyse_calendar()
    short_days = cl_ | ea_
    pc = None
    trs7, a14, a21, n_tr = [], None, None, 0
    a14_hist = []
    on_pv = on_v = 0.0
    on_vwap_prev = None
    s_pv = s_v = 0.0
    sess = None
    day_side = 0
    top = bot = None
    stop_px = tgt_px = pend_d = None
    state = 0          # 0 waiting / 1 range building / 2 waiting break / 3 armed / 9 done
    for i in range(i0, i1):
        o, h, l, c, t, d = O[i], H[i], L[i], C[i], T[i], D[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        cut = 1150 if d in short_days else flat
        for e_, bo, bh, bl, bc, bv in (tb.update(CA[i], o, h, l, c, V[i]) or []):
            st = hhmm(e_ - 10)                                   # the 10m bar's open time (CT)
            sday = (e_ - 10) // 1440 + (1 if st >= 1700 else 0)
            tr = bh - bl if pc is None else max(bh, pc) - min(bl, pc)
            pc = bc
            n_tr += 1
            trs7.append(tr)
            if len(trs7) > 7:
                del trs7[0]
            a21 = tr if a21 is None else a21 + (tr - a21) / 21
            a14_prev_mean = sum(a14_hist[-100:]) / 100 if len(a14_hist) >= 100 else None
            a14 = tr if a14 is None else a14 + (tr - a14) / 14
            a14_hist.append(a14)
            if len(a14_hist) > 200:
                del a14_hist[:100]
            if sday != sess:
                if last_close is not None:
                    sess_closes.append(last_close)
                sess, on_pv, on_v, state, day_side = sday, 0.0, 0.0, 0, 0
                on_vwap_prev = None
            typ = (bh + bl + bc) / 3
            last_close = bc
            if st == 830 and state == 0:
                day_side = 0
                if on_vwap_prev is not None:
                    dr = bo - on_vwap_prev
                    day_side = 1 if dr > 0 else (-1 if dr < 0 else 0)
                if sidep != "both" and (sidep == "long") != (day_side == 1):
                    day_side = 0
                if day_side and min_drift and a21 and abs(bo - on_vwap_prev) < min_drift * a21:
                    day_side = 0
                if day_side and trend_n and len(sess_closes) >= trend_n:
                    tm = sum(sess_closes[-trend_n:]) / trend_n
                    if (sess_closes[-1] - tm) * day_side <= 0:
                        day_side = 0
                if day_side and sday in news:
                    day_side = 0
                state = 1 if day_side else 9
                s_pv = s_v = 0.0
                top, bot = bh, bl
            on_pv += typ * bv
            on_v += bv
            on_vwap_prev = on_pv / on_v if on_v > 0 else None
            if state in (1, 2, 3) and st >= 830:
                s_pv += typ * bv
                s_v += bv
            if state == 1:
                if st in (840, 850):
                    top, bot = max(top, bh), min(bot, bl)
                if st == 850:
                    state = 2
                continue
            if state not in (2, 3) or not (900 <= st < last):
                continue
            against = bc < bot if day_side == 1 else bc > top
            if state == 2:
                if st > brk_last:
                    state = 9
                elif (bc > top + brk) if day_side == 1 else (bc < bot - brk):
                    state = 3
                elif against:
                    state = 9
                continue
            vw = s_pv / s_v if s_v > 0 else None
            atr7 = sum(trs7) / 7 if len(trs7) == 7 else None
            if vw is None or atr7 is None:
                continue
            band = band_k * atr7
            if day_side == 1:
                pb = bl <= vw + band and bc > top and bc > bo
            else:
                pb = bh >= vw - band and bc < bot and bc < bo
            if pb or against:
                state = 9
                if pb and a14_prev_mean and a14 >= vol_k * a14_prev_mean and eng.pos == 0 and n_tr > 40 and hhmm(e_) < cut and st <= pb_last:
                    sd_ = max(round(k_sl * a21 / tk) * tk, tk)
                    td_ = max(round(k_tp * a21 / tk) * tk, tk)
                    eng.order(MKT, BUY if day_side == 1 else SHORT, None, "CT-L" if day_side == 1 else "CT-S",
                              attach=(sd_, td_))
                    pend_d = (sd_, td_)
        pend = any(x[0] == MKT for x in eng.orders)
        if eng.pos != 0 and not pend:
            xa = XLONG if eng.pos == 1 else XSHORT
            if cut <= t < 1700 or (maxm and i - eng.entry_i >= maxm):
                eng.order(MKT, xa, None, "Close")
            else:
                if eng.entry_i == i or stop_px is None:
                    sd_, td_ = pend_d
                    stop_px = eng.entry_px - eng.pos * sd_
                    tgt_px = eng.entry_px + eng.pos * td_
                eng.order(STOP, xa, stop_px, "SL")
                eng.order(LIMIT, xa, tgt_px, "TP")
        elif eng.pos == 0:
            stop_px = None
    return eng


def s45_ftm_orb(b, tf, i0, i1, p):
    """FTM ORB (user's FTM_ORB_STrategy.txt = Pine port of FTM_OPENING_RANGE_BREAKOUT_MNQ v1.8 RC3 without the kNN,
    EW warm-up; 2026-11-11). NQ 1-minute, times in CT (ET = CT + 1h). tf is ignored.
    Range = 1m bars 08:31-08:45 CT (09:30-09:45 ET, all 15 must exist). Quarter-hour closes 09:00-14:45 CT scan for a
    close >= range high + 1 tick (<= low - 1 tick); admitted if the trailing 15-bar window has body >= 0.15 and close
    location >= 0.60 (else keep scanning), then needs >= 3 bars of the 15 touching the confirm level (else the day is
    over). Direction tree (no kNN): prior-session return (16:00 ET close vs the 23:00 UTC bar's open) < -300 bps
    against the break flips it; 10:00 ET breaks within 20 bps of RTH VWAP enter directly; weak body (<= 0.20) waits
    1 bar, high-vol ORB (bps > EW q75) with <= 3 touches votes over 3 bars (no progress = flip); stage 2: prior
    session > 100 bps aligned with a non-positive ORB body waits 2 bars and reverses, 30-min return > 25 bps with
    extension <= 0.25 ORB waits 1 bar and reverses if that bar moved the trade's way. Market entry next bar; stop
    1.25 x ORB (2-100 pts), target 3R (1.25R on high-vol ORB days); at each quarter-hour close, once +1.25R (+0.75R
    countertrend) the stop moves to entry (+0.1R countertrend), once; 14:30 CT close outside [0R, 1R) exits;
    flat after the 15:00 CT (16:00 ET) bar. One trade a day. Regime: EW mean/var of ORB bps (alpha 2/121, threshold
    mean + 0.6437 sd), EW trend of 16:00 ET closes (alpha 2/22), trusted after ftm_floor (10) sessions.
    His sizing: $535 risk, max 2, 1 on high-vol or countertrend days; the qty goes in the entry label ("L2"); the
    engine trades 1 contract. Options: ftm_ew (1; 0 = the C# windows: 120-session linear q75 of ORB bps and the
    20-session RTH-close return), ftm_floor, ftm_k, ftm_excl (1 = the file's roll/degraded date lists), ftm_ref (1 =
    skip days without the 23:00 UTC bar), ftm_hol (1 = skip NYSE closures / early closes, Lucid), ftm_flat (1500 CT),
    ftm_last (last decision bar, 1445), ftm_side (both|long|short), ftm_tree (1; 0 = plain breakout side, no tree),
    ftm_tgt / ftm_tgt_hv (3.0 / 1.25 R), ftm_news ("cpi,nfp,fomc" etc.)."""
    O, H, L, C, V, T, D, CA = b.o, b.h, b.l, b.c, b.v, b.hhmm, b.day, b.cabs
    tick = p["tick"]
    pv = float(p.get("ftm_pv", 2.0))
    eng = Engine(CA, tick)
    use_ew = int(p.get("ftm_ew", 1))
    floor_n = int(p.get("ftm_floor", 10))
    ew_k = float(p.get("ftm_k", 0.6437))
    use_excl = int(p.get("ftm_excl", 1))
    req_ref = int(p.get("ftm_ref", 1))
    flat_t = int(p.get("ftm_flat", 1500))
    last_t = int(p.get("ftm_last", 1445))
    side_opt = str(p.get("ftm_side", "both"))
    tree = int(p.get("ftm_tree", 1))
    tgt_base, tgt_hv = float(p.get("ftm_tgt", 3.0)), float(p.get("ftm_tgt_hv", 1.25))
    regs = set(str(p.get("ftm_regs", "base,hv,ctr")).split(","))
    stop_k = float(p.get("ftm_stop", 1.25))
    trig_b, trig_c = float(p.get("ftm_trig", 1.25)), float(p.get("ftm_trig_ctr", 0.75))
    cond_t, cond_lo, cond_hi = int(p.get("ftm_cond_t", 1430)), float(p.get("ftm_cond_lo", 0.0)), float(p.get("ftm_cond_hi", 1.0))
    first_t = int(p.get("ftm_first", 900))
    risk_usd, max_c, def_c = float(p.get("ftm_risk", 535.0)), int(p.get("ftm_max", 2)), int(p.get("ftm_def", 1))
    skip = set()
    if int(p.get("ftm_hol", 1)):
        cl, ea = nyse_calendar()
        skip = cl | ea
    if p.get("ftm_news"):
        import news_calendar
        skip = skip | set(news_calendar.days(p["ftm_news"]))
    excl = set()
    if use_excl:
        for k in (20200311, 20200610, 20200909, 20210609, 20210908, 20220608, 20220907, 20260611,
                  20200227, 20200228, 20200630, 20200701, 20200702, 20211206, 20220103, 20240918, 20240919,
                  20250917, 20250918, 20250924, 20250925, 20251128, 20260316, 20260317, 20260410, 20260525,
                  20260730, 20260731):
            excl.add(date(k // 10000, k // 100 % 100, k % 100).toordinal())
    dstc = {}

    def us_dst(od):
        y = date.fromordinal(od).year
        if y not in dstc:
            m_, n_ = date(y, 3, 8), date(y, 11, 1)
            dstc[y] = (m_.toordinal() + (6 - m_.weekday()) % 7, n_.toordinal() + (6 - n_.weekday()) % 7)
        a_, z_ = dstc[y]
        return a_ <= od < z_

    def bps(num, den):
        return (num / den - 1.0) * 10000.0 if den else 0.0

    def offticks(pts, below):
        x = pts / tick
        return int(math.ceil(x - 0.5) if below else math.floor(x + 0.5))

    A_VOL, A_TR = 2.0 / 121, 2.0 / 22
    ew_mean = ew_var = ew_ema = 0.0
    ew_last = None
    ew_n = 0
    orb_hist, close_hist = [], []
    last_ret = None
    ref_open = ref_cabs = None
    cash = None
    blocked, eligible, used = True, False, False
    ref_ok, ref_px = False, 0.0
    orb_h = orb_l = orb_o = orb_c = 0.0
    orb_bps = None
    orb_n, orb_fin = 0, False
    rth_idx = []
    pv_sum = v_sum = 0.0
    q75_ok, q75 = False, 0.0
    tr_ok, tr_bps = False, 0.0
    ps_ret = 0.0
    stage = pbars = pneed = pside = 0
    pfirst = None
    pbranch = ""
    base_side = 0
    sig_close = f1 = f5 = 0.0
    stop_px = tgt_px = risk_pts = 0.0
    trig_r = lock_r = 0.0
    managed = cond_done = False
    plan = None
    path = ""
    for i in range(i0, i1):
        o, h, l, c, t, d = O[i], H[i], L[i], C[i], T[i], D[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        if plan is not None and eng.entry_i == i:          # entry filled on this bar: bracket from the fill
            s_ticks, t_ticks, trig_r, lock_r = plan
            sd = eng.pos if eng.pos else (1 if eng.trades and eng.trades[-1][2] == 1 else -1)
            stop_px = eng.entry_px - sd * s_ticks * tick
            tgt_px = eng.entry_px + sd * t_ticks * tick
            risk_pts = s_ticks * tick
            managed = cond_done = False
            plan = None
        # 23:00 UTC reference bar (opens 17:00 CST / 18:00 CDT)
        if t == (1801 if us_dst(d) else 1701):
            ref_open, ref_cabs = o, CA[i]
        if t == 831 and d != cash:                          # new cash date (bar opening 09:30 ET)
            cash = d
            ref_ok = ref_open is not None and CA[i] - 1 - (ref_cabs - 1) < 1440
            ref_px = ref_open if ref_ok else 0.0
            dw = date.fromordinal(d).weekday()
            eligible = dw < 5 and d not in excl and d not in skip and (ref_ok or not req_ref)
            blocked = not eligible
            used = False
            orb_n, orb_fin, orb_bps = 0, False, None
            rth_idx = []
            pv_sum = v_sum = 0.0
            stage = 0
            # prior-session context (fixed for the day)
            if use_ew:
                q75_ok = ew_n >= floor_n
                q75 = ew_mean + ew_k * math.sqrt(max(ew_var, 0.0)) if q75_ok else 0.0
                tr_ok = ew_n >= floor_n and ew_last is not None and ew_ema > 0
                tr_bps = (ew_last / ew_ema - 1.0) * 10000.0 if tr_ok else 0.0
            else:
                q75_ok = len(orb_hist) == 120
                if q75_ok:
                    srt = sorted(orb_hist)
                    pos_ = 119 * 0.75
                    lo_, hi_ = int(math.floor(pos_)), int(math.ceil(pos_))
                    q75 = srt[lo_] + (srt[hi_] - srt[lo_]) * (pos_ - lo_)
                tr_ok = len(close_hist) >= 21
                tr_bps = bps(close_hist[-1], close_hist[0]) if tr_ok else 0.0
            ps_ret = last_ret if last_ret is not None else 0.0
        in_cash = cash == d and 831 <= t <= 1500
        if not in_cash:
            if eng.pos and 1500 < t < 1700:                  # never hold past the session (missing 15:00 bar)
                eng.order(MKT, XLONG if eng.pos == 1 else XSHORT, None, "EOD")
            elif eng.pos:
                eng.order(STOP, XLONG if eng.pos == 1 else XSHORT, stop_px, "SL")
                eng.order(LIMIT, XLONG if eng.pos == 1 else XSHORT, tgt_px, "TP")
            continue
        rth_idx.append(i)
        pv_sum += (h + l + c) / 3.0 * V[i]
        v_sum += V[i]
        vwap = pv_sum / v_sum if v_sum > 0 else None
        if t <= 845 and not blocked:                        # opening range 09:30-09:45 ET
            if orb_n == 0:
                orb_o, orb_h, orb_l = o, h, l
            else:
                orb_h, orb_l = max(orb_h, h), min(orb_l, l)
            orb_c = c
            orb_n += 1
            if t == 845:
                if orb_n != 15 or orb_h < orb_l:
                    blocked = True
                else:
                    orb_fin = True
                    mid = (orb_h + orb_l) / 2.0
                    orb_bps = (orb_h - orb_l) / mid * 10000.0 if mid > 0 else 0.0
        cup = orb_h + tick if orb_fin or orb_n else None
        cdn = orb_l - tick if orb_fin or orb_n else None
        mnt = t % 100
        req = 0
        flattened = False
        pos = eng.pos
        if pos and t >= flat_t:
            eng.order(MKT, XLONG if pos == 1 else XSHORT, None, "EOD")
            flattened = True
            blocked = True
        elif pos and t == cond_t and not cond_done and risk_pts > 0:
            cr = pos * (c - eng.entry_px) / risk_pts
            if cr < cond_lo or cr >= cond_hi:
                cond_done = True
                flattened = True
                eng.order(MKT, XLONG if pos == 1 else XSHORT, None, "C1430")
        elif pos and mnt % 15 == 0 and t < flat_t and not managed and risk_pts > 0:
            cr = pos * (c - eng.entry_px) / risk_pts
            if cr >= trig_r:
                prop = eng.entry_px + pos * risk_pts * lock_r
                stop_px = max(stop_px, prop) if pos == 1 else min(stop_px, prop)
                managed = True
        elif not pos and stage > 0 and not blocked:
            if pbars == 0:
                pfirst = o
            pbars += 1
            if pbars >= pneed:
                fs, path = pside, pbranch
                if stage == 1:
                    if pbranch == "hv":
                        frac = pside * (c - pfirst) / (orb_h - orb_l) if orb_h > orb_l else 0.0
                        fs = -pside if frac <= 0.0 else pside
                        path += "hvflip" if frac <= 0.0 else "hvkeep"
                    else:
                        path += "weak"
                    ori = fs * base_side
                    ap, ar = ori * f1, ori * f5
                    rng = orb_h - orb_l
                    dob = fs * (orb_c - orb_o) / rng if rng > 0 else 0.0
                    edge = orb_h if fs == 1 else orb_l
                    sx = fs * (sig_close - edge) / rng if rng > 0 else 0.0
                    psd = ap > 100.0 and dob <= 0.0
                    ic = ar > 25.0 and sx <= 0.25
                    if psd or ic:
                        stage, pbars, pneed, pside, pfirst = 2, 0, (2 if psd else 1), fs, None
                        pbranch = "psd" if psd else "ic"
                        path += ">" + pbranch
                    else:
                        stage = 0
                        req = fs
                else:
                    if pbranch == "psd":
                        fs = -pside
                        path += "rev"
                    else:
                        fs = -pside if pside * (c - pfirst) > 0 else pside
                        path += "rev" if fs != pside else "keep"
                    stage = 0
                    req = fs
        elif (not pos and mnt % 15 == 0 and first_t <= t <= last_t and t < 1500 and orb_fin and not blocked
              and not used and stage == 0):
            lb = c >= cup
            sb = c <= cdn
            if lb or sb:
                bs = 1 if lb else -1
                sh = max(H[i - 14:i + 1])
                sl_ = min(L[i - 14:i + 1])
                so = O[i - 14]
                sr = sh - sl_
                body = bs * (c - so) / sr if sr > 0 else 0.0
                cloc = ((c - sl_) / sr if bs == 1 else (sh - c) / sr) if sr > 0 else 0.0
                if body >= 0.15 and cloc >= 0.60:
                    tu = sum(1 for j in range(i - 14, i + 1) if H[j] >= cup)
                    td = sum(1 for j in range(i - 14, i + 1) if L[j] <= cdn)
                    used = True
                    if (tu if bs == 1 else td) >= 3:
                        base_side = bs
                        sig_close = c
                        f1 = bs * ps_ret
                        f4 = bs * (bps(c, vwap) if vwap else 0.0)
                        tc30 = C[rth_idx[-31]] if len(rth_idx) > 30 else orb_c
                        f5 = bs * bps(c, tc30)
                        el = ((t // 100 * 60 + mnt) - (8 * 60 + 45)) / 15.0
                        ds = -bs if bs * ps_ret < -300.0 else bs
                        path = "pf:" if ds != bs else ""
                        if not (q75_ok and tr_ok):
                            pass
                        elif not tree:
                            req = bs
                            path = "plain"
                        elif el == 1.0 and f4 <= 20.0:
                            req = bs
                            path = "rc1"
                        else:
                            dbody = ds * (c - so) / sr if sr > 0 else 0.0
                            hv = q75_ok and orb_bps > q75
                            dt = tu if ds == 1 else td
                            weak = dbody <= 0.20
                            hvote = hv and dt <= 3
                            if weak or hvote:
                                stage, pbars, pneed, pside, pfirst = 1, 0, (1 if weak else 3), ds, None
                                pbranch = "weak" if weak else "hv"
                            else:
                                ori = ds * bs
                                ap, ar = ori * f1, ori * f5
                                rng = orb_h - orb_l
                                dob = ds * (orb_c - orb_o) / rng if rng > 0 else 0.0
                                edge = orb_h if ds == 1 else orb_l
                                sx = ds * (c - edge) / rng if rng > 0 else 0.0
                                psd = ap > 100.0 and dob <= 0.0
                                ic = ar > 25.0 and sx <= 0.25
                                if psd or ic:
                                    stage, pbars, pneed, pside, pfirst = 2, 0, (2 if psd else 1), ds, None
                                    pbranch = "psd" if psd else "ic"
                                    path += pbranch
                                else:
                                    req = ds
                                    path += "direct"
        if req and t < flat_t and (side_opt == "both" or (side_opt == "long") == (req == 1)):
            raw = max(2.0, min(100.0, (orb_h - orb_l) * stop_k))
            hvp = q75_ok and orb_bps > q75
            ctr = tr_ok and req * tr_bps < 0
            tr_r, tg_r, lk_r = trig_b, tgt_base, 0.0
            if hvp:
                tg_r = tgt_hv
            elif ctr:
                tr_r, lk_r = trig_c, 0.10
            if ("hv" if hvp else "ctr" if ctr else "base") not in regs:
                req = 0
            st = offticks(raw, req == 1)
            tt = offticks(raw * tg_r, req != 1)
            cap = min(max_c, def_c) if (hvp or ctr) else max_c
            per = st * tick * pv + 1 * tick * pv + 2.50
            qty = min(cap, int(math.floor(risk_usd / per))) if per > 0 else 0
            if req and st >= 1 and tt >= 1 and qty >= 1:
                plan = (st, tt, tr_r, lk_r)
                eng.order(MKT, BUY if req == 1 else SHORT, None, ("L" if req == 1 else "S") + str(qty) + "|" + path + "|" + ("hv" if hvp else "ctr" if ctr else "base") + "|" + str(t),
                          attach=(st * tick, tt * tick))
        if eng.pos and not flattened:
            xa = XLONG if eng.pos == 1 else XSHORT
            eng.order(STOP, xa, stop_px, "BE" if managed else "SL")
            eng.order(LIMIT, xa, tgt_px, "TP")
        if t == 1500 and eligible and orb_fin and orb_bps is not None:   # record the session (16:00 ET close)
            if use_ew:
                df_ = orb_bps - ew_mean
                inc = A_VOL * df_
                ew_mean += inc
                ew_var = (1 - A_VOL) * (ew_var + df_ * inc) if ew_n > 0 else 0.0
                ew_ema = c if ew_n == 0 else ew_ema + A_TR * (c - ew_ema)
                ew_last = c
                ew_n += 1
            orb_hist.append(orb_bps)
            if len(orb_hist) > 120:
                del orb_hist[0]
            close_hist.append(c)
            if len(close_hist) > 21:
                del close_hist[0]
            last_ret = bps(c, ref_px) if ref_ok and ref_px > 0 else 0.0
            used = True
            blocked = True
    return eng


def s46_ibs_overnight(b, tf, i0, i1, p):
    """IBS reversion, Lucid-legal (2026-11-11, from the user's IBS card: buy the close when IBS < 0.2, sell the close
    when IBS > 0.8). IBS = (RTH close - RTH low) / (RTH high - RTH low) of the 08:31-15:00 CT session. A day closing
    with IBS < ib_lo opens the trade; while it is open the strategy buys at market at the 17:00 CT reopen (order on the
    16:00 bar) and is flat from ib_flat (15:40 CT) the next day, then buys again at 17:00, until a day closes with IBS >
    ib_hi (no re-entry) or ib_max days have passed. ib_entry = "eve" (17:00 reopen) or "open" (08:30 RTH open, day
    only). No entry the evening before an NYSE closure / early close (those days flat at 11:55 CT). Options: ib_sl
    (stop, x 14-day mean RTH range from the fill, 0 = none), ib_side (1 long, -1 short mirror: IBS > ib_hi opens a short
    closed by IBS < ib_lo), ib_trend (N > 0: longs only when the RTH close is above its N-day mean), ib_news."""
    O, H, L, C, T, D, CA = b.o, b.h, b.l, b.c, b.hhmm, b.day, b.cabs
    eng = Engine(CA, p["tick"])
    lo, hi = float(p.get("ib_lo", 0.2)), float(p.get("ib_hi", 0.8))
    flat_t = int(p.get("ib_flat", 1540))
    mode = str(p.get("ib_entry", "eve"))
    max_d = int(p.get("ib_max", 0))
    sl_k = float(p.get("ib_sl", 0))
    side = int(p.get("ib_side", 1))
    trend_n = int(p.get("ib_trend", 0))
    cl, ea = nyse_calendar()
    short = cl | ea
    news = set()
    if p.get("ib_news"):
        import news_calendar
        news = set(news_calendar.days(p["ib_news"]))
    rday = None
    rh = rl = rc = 0.0
    closes, rngs = [], []
    on, held = False, 0
    stop = 0.0
    for i in range(i0, i1):
        o, h, l, c, t, d = O[i], H[i], L[i], C[i], T[i], D[i]
        if eng.orders:
            eng.fill(i, o, h, l)
        if 830 < t <= 1500:
            if d != rday:
                rday, rh, rl = d, h, l
            else:
                rh, rl = max(rh, h), min(rl, l)
            rc = c
            if t == 1500 or (i + 1 < i1 and (D[i + 1] != d or T[i + 1] > 1500)):
                if rh > rl:                                       # the RTH day is complete: update the trade state
                    ibs = (rc - rl) / (rh - rl)
                    closes.append(rc); rngs.append(rh - rl)
                    if on:
                        held += 1
                        if (side == 1 and ibs > hi) or (side == -1 and ibs < lo) or (max_d and held >= max_d):
                            on = False
                    elif (side == 1 and ibs < lo) or (side == -1 and ibs > hi):
                        ok = True
                        if trend_n and len(closes) >= trend_n:
                            mean_ = sum(closes[-trend_n:]) / trend_n
                            ok = (rc > mean_) if side == 1 else (rc < mean_)
                        elif trend_n:
                            ok = False
                        if ok:
                            on, held = True, 0
                rday = d
        sess_next = d + 1 if t > 1600 else d                      # the session (calendar day of its RTH)
        if eng.pos != 0:
            cut = 1155 if d in short else flat_t
            if t >= cut and t < 1700 and (t <= 1600):
                eng.order(MKT, XLONG if eng.pos == 1 else XSHORT, None, "EOD")
            elif sl_k > 0 and stop:
                eng.order(STOP, XLONG if eng.pos == 1 else XSHORT, stop, "SL")
        elif on:
            nxt = d + 1
            while date.fromordinal(nxt).weekday() >= 5:
                nxt += 1
            send = False
            if mode == "eve" and t == 1600:
                send = nxt not in short and nxt not in news
            elif mode == "open" and t == 830:
                send = d not in short and d not in news
            if send and rngs:
                eng.order(MKT, BUY if side == 1 else SHORT, None, "IBS_L" if side == 1 else "IBS_S")
                dat = sum(rngs[-14:]) / len(rngs[-14:])
                stop = (c - side * sl_k * dat) if sl_k > 0 else 0.0
    return eng


STRATEGIES = {
    "S01": ("ORB + EMA200 + gap filter", s01_orb_ema_gap, True),
    "S02": ("SMA/EMA pullback, 2 legs", s02_sma_ema_pullback, True),
    "S03": ("Monday down-day long", s03_monday_down, False),
    "S04": ("VWAP continuation", s04_vwap_continuation, True),
    "S05": ("Overnight long below EMA200", s05_overnight_long, True),
    "S06": ("Channel breakout + ATR trail", s06_channel_breakout, True),
    "S07": ("MACD / IBS daily mean reversion", s07_macd_ibs, False),
    "S08": ("Forecast-to-Fill trend", s08_forecast_to_fill, True),
    "S09": ("5m opening range breakout", s09_orb, True),
    "S10": ("Fabio Valentini ORB, long 1R", s10_fabio, True),
    "S11": ("Monday long NQ, ADX filter", s11_monday_nq_adx, True),
    "S12": ("Monday long ES, EMA distance filter", s12_monday_es_ema, True),
    "S16": ("Triple Open L656, Monday long after up Friday", s16_monday_fri_up, True),
    "S13": ("Overnight Bias ORB", s13_overnight_bias_orb, True),
    "S14": ("Drift Pullback", s14_drift_pullback, True),
    "S15": ("Gold Asian-range breakout", s15_gold_asian_breakout, True),
    "S17": ("Drift Pullback revamp", s17_drift_revamp, True),
    "S18": ("Gold session high/low failed-breakout fade", s18_gold_session_fade, True),
    "S19": ("VWAP Fade, 2-sigma bands", s19_vwap_fade, True),
    "S20": ("Twin Continuation", s20_twin_continuation, True),
    "S21": ("IVB Model ORB", s21_ivb, True),
    "S22": ("Failed ORB Fade", s22_orb_fade, True),
    "S23": ("Stretch Fade", s23_stretch_fade, True),
    "S24": ("Extreme-day Reversal", s24_extreme_reversal, True),
    "S25": ("SVP VAH Short", s25_svp_vah_short, True),
    "S26": ("Lo-Hi Pullback", s26_lohi_pullback, True),
    "S27": ("Swing Breakout + Morning Momentum", s27_swing_momentum, True),
    "S28": ("Last-half-hour momentum", s28_last_half_hour, True),
    "S29": ("Gold day-session breakout", s29_gold_day, True),
    "S30": ("FastAlpha", s30_fast_alpha, True),
    "S31": ("Noise-Area Momentum", s31_noise_area, True),
    "S32": ("Gamma fade", s32_gamma_fade, True),
    "S33": ("Gap fill", s33_gap_fill, True),
    "S34": ("Pre-FOMC drift", s34_pre_fomc, True),
    "S35": ("Halyard ORB", s35_halyard, True),
    "S36": ("Gold Donchian breakout", s36_gold_donchian, True),
    "S37": ("Gold ATR candle breakout", s37_gold_atr_candle, True),
    "S38": ("Overnight drift", s38_overnight_drift, True),
    "S39": ("News-release reversal", s39_news_reversal, True),
    "S40": ("Gold Trend Tranches", s40_gold_trend_tranches, True),
    "S41": ("Gold COMEX Dip Fade", s41_gold_comex_dip, True),
    "S42": ("Gantline", s42_gantline, True),
    "S43": ("Phase Oscillator", s43_phase_osc, True),
    "S44": ("Crosstree", s44_crosstree, True),
    "S45": ("FTM ORB", s45_ftm_orb, True),
    "S46": ("IBS overnight", s46_ibs_overnight, True),
}
