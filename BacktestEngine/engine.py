"""Bar-by-bar order engine that mimics MultiCharts' backtester on 1-minute bars.

Each bar: orders sent on the previous bar are filled first (market at the open, then
stop / limit exits along the intrabar path), then the strategy runs on the bar's close
and sends orders for the next bar. Orders live for one bar, as in PowerLanguage.

Intrabar path (MultiCharts default): if the open is nearer the high the bar goes
O-H-L-C, otherwise O-L-H-C. Stops and limits that the open has already gapped
through fill at the open. Fill prices are raw; slippage and commission are charged
as dollar costs per side, so EntryPrice-based stops match MultiCharts.
"""

import math

MKT, STOP, LIMIT = 0, 1, 2
BUY, SHORT, XLONG, XSHORT = 1, 2, 3, 4

# Limit fills: False = filled when touched (MultiCharts default); True = price must trade
# one tick through the limit. Set once per process by the runner (--limit-fill through).
LIMIT_THROUGH = False


class Engine:
    def __init__(self, cabs, tick):
        self.cabs = cabs
        self.tick = tick
        self.pos = 0
        self.entry_px = 0.0
        self.entry_i = -1
        self.entry_kind = MKT
        self.entry_lab = ""
        self.orders = []
        # (entry_i, exit_i, side, entry_px, exit_px, entry_kind, exit_kind, entry_lab, exit_lab)
        self.trades = []

    def order(self, kind, act, px=None, lab="", attach=None):
        """attach = (stop_pts, target_pts) placed from the fill price of a market entry
        and live on the fill bar (SetStopLoss / SetProfitTarget)."""
        if kind != MKT:
            px = self._to_tick(kind, act, px)
        self.orders.append((kind, act, px, lab, attach))

    def _to_tick(self, kind, act, px):
        """Round a stop / limit price onto the tick grid, against the trader: a sell stop
        or buy limit rounds down, a buy stop or sell limit rounds up."""
        q = px / self.tick
        down = (kind == STOP) == (act == XLONG)
        return (math.floor(q + 1e-9) if down else math.ceil(q - 1e-9)) * self.tick

    def _open(self, i, side, px, lab):
        self.pos = side
        self.entry_px = px
        self.entry_i = i
        self.entry_kind = MKT
        self.entry_lab = lab

    def _close(self, i, px, kind, lab):
        self.trades.append((self.entry_i, i, self.pos, self.entry_px, px,
                            self.entry_kind, kind, self.entry_lab, lab))
        self.pos = 0

    def fill(self, i, o, h, l):
        orders = self.orders
        self.orders = []
        for kind, act, px, lab, _ in orders:
            if kind == MKT and ((act == XLONG and self.pos == 1) or (act == XSHORT and self.pos == -1)):
                self._close(i, o, MKT, lab)
        for kind, act, px, lab, attach in orders:
            if kind == MKT and self.pos == 0 and (act == BUY or act == SHORT):
                side = 1 if act == BUY else -1
                self._open(i, side, o, lab)
                if attach:
                    sl, tp = attach
                    xa = XLONG if side == 1 else XSHORT
                    orders = list(orders)
                    if sl > 0:
                        orders.append((STOP, xa, self._to_tick(STOP, xa, o - side * sl), "SL", None))
                    if tp > 0:
                        orders.append((LIMIT, xa, self._to_tick(LIMIT, xa, o + side * tp), "TP", None))
        if self.pos == 0:
            return
        if LIMIT_THROUGH:
            # widen the touch test by one tick so a limit needs a trade through its price
            h_lim, l_lim = h - self.tick, l + self.tick
        else:
            h_lim, l_lim = h, l
        stop = limit = None
        slab = llab = ""
        if self.pos == 1:
            for kind, act, px, lab, _ in orders:
                if act == XLONG:
                    if kind == STOP and (stop is None or px > stop):
                        stop, slab = px, lab
                    elif kind == LIMIT and (limit is None or px < limit):
                        limit, llab = px, lab
            if stop is None and limit is None:
                return
            if stop is not None and o <= stop:
                self._close(i, o, STOP, slab)
            elif limit is not None and o >= limit:
                self._close(i, o, LIMIT, llab)
            elif h - o <= o - l:
                if limit is not None and h_lim >= limit:
                    self._close(i, limit, LIMIT, llab)
                elif stop is not None and l <= stop:
                    self._close(i, stop, STOP, slab)
            else:
                if stop is not None and l <= stop:
                    self._close(i, stop, STOP, slab)
                elif limit is not None and h_lim >= limit:
                    self._close(i, limit, LIMIT, llab)
        else:
            for kind, act, px, lab, _ in orders:
                if act == XSHORT:
                    if kind == STOP and (stop is None or px < stop):
                        stop, slab = px, lab
                    elif kind == LIMIT and (limit is None or px > limit):
                        limit, llab = px, lab
            if stop is None and limit is None:
                return
            if stop is not None and o >= stop:
                self._close(i, o, STOP, slab)
            elif limit is not None and o <= limit:
                self._close(i, o, LIMIT, llab)
            elif h - o <= o - l:
                if stop is not None and h >= stop:
                    self._close(i, stop, STOP, slab)
                elif limit is not None and l_lim <= limit:
                    self._close(i, limit, LIMIT, llab)
            else:
                if limit is not None and l_lim <= limit:
                    self._close(i, limit, LIMIT, llab)
                elif stop is not None and h >= stop:
                    self._close(i, stop, STOP, slab)


class TFBars:
    """Clock-aligned bars of `tf` minutes (CT) built from 1-minute bars.

    update() returns the bars that became complete on this 1-minute bar, as tuples
    (end_cabs, open, high, low, close, volume), or None. A bar completes on its last
    minute, or late on the first minute of the next bucket when its last minute
    has no trade (that is when MultiCharts' data2 bar becomes visible on data1).
    """

    def __init__(self, tf):
        self.tf = tf
        self.bk = None
        self.live = False
        self.o = self.h = self.l = self.c = 0.0
        self.v = 0

    def update(self, cabs, o, h, l, c, v):
        tf = self.tf
        out = None
        bk = (cabs - 1) // tf
        if bk != self.bk:
            if self.live:
                out = [(self.bk * tf + tf, self.o, self.h, self.l, self.c, self.v)]
            self.bk = bk
            self.o, self.h, self.l, self.c, self.v = o, h, l, c, v
            self.live = True
        else:
            if h > self.h:
                self.h = h
            if l < self.l:
                self.l = l
            self.c = c
            self.v += v
        if cabs % tf == 0:
            bar = (cabs, self.o, self.h, self.l, self.c, self.v)
            self.live = False
            if out:
                out.append(bar)
            else:
                out = [bar]
        return out


def hhmm(cabs):
    m = cabs % 1440
    return (m // 60) * 100 + m % 60
