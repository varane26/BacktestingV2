"""Load the 1-minute CSVs into compact arrays, cached as binary files.

Bars are converted from the CSV's US Eastern bar-close stamps to US Central
(exchange) time, because the strategies are written in Chicago time.
CT is always ET - 60 minutes (both zones switch DST on the same dates).
"""
import os
from array import array
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
CACHE_DIR = os.path.join(ROOT, "cache")

# name -> typecode. cabs = CT absolute minute of the bar close (day ordinal * 1440 + minute).
FIELDS = [("cabs", "i"), ("day", "i"), ("hhmm", "h"), ("dow", "b"),
          ("o", "f"), ("h", "f"), ("l", "f"), ("c", "f"), ("v", "i")]


class Bars:
    """Parallel arrays, one entry per 1-minute bar, CT time."""

    def __init__(self, symbol, cols):
        self.symbol = symbol
        for name, _ in FIELDS:
            setattr(self, name, cols[name])
        self.n = len(self.c)


def _build(symbol):
    cols = {name: array(tc) for name, tc in FIELDS}
    ord_cache = {}
    with open(os.path.join(DATA_DIR, symbol + ".csv"), "r") as fh:
        fh.readline()
        for line in fh:
            p = line.split(",")
            if len(p) < 7:
                continue
            d = p[0]
            t = p[1].zfill(6)
            od = ord_cache.get(d)
            if od is None:
                od = date(int(d[:4]), int(d[4:6]), int(d[6:8])).toordinal()
                ord_cache[d] = od
            cabs = od * 1440 + int(t[:2]) * 60 + int(t[2:4]) - 60
            day, mod = divmod(cabs, 1440)
            cols["cabs"].append(cabs)
            cols["day"].append(day)
            cols["hhmm"].append((mod // 60) * 100 + mod % 60)
            # PowerLanguage DayOfWeek: 0 = Sunday ... 6 = Saturday
            cols["dow"].append((date.fromordinal(day).weekday() + 1) % 7)
            cols["o"].append(float(p[2]))
            cols["h"].append(float(p[3]))
            cols["l"].append(float(p[4]))
            cols["c"].append(float(p[5]))
            cols["v"].append(int(float(p[6])))
    os.makedirs(CACHE_DIR, exist_ok=True)
    for name, _ in FIELDS:
        with open(os.path.join(CACHE_DIR, f"{symbol}.{name}.bin"), "wb") as out:
            cols[name].tofile(out)
    return cols


def load(symbol):
    first = os.path.join(CACHE_DIR, f"{symbol}.cabs.bin")
    src = os.path.join(DATA_DIR, symbol + ".csv")
    if not os.path.exists(first) or os.path.getmtime(first) < os.path.getmtime(src):
        return Bars(symbol, _build(symbol))
    cols = {}
    for name, tc in FIELDS:
        path = os.path.join(CACHE_DIR, f"{symbol}.{name}.bin")
        a = array(tc)
        with open(path, "rb") as fh:
            a.frombytes(fh.read())
        cols[name] = a
    return Bars(symbol, cols)


def eth_session(bars):
    """Keep only the CME equity ETH template the strategies use (17:00-16:00 CT):
    drops bars closing after 16:00 and up to 17:00 CT, which the data has on some days."""
    keep = [i for i in range(bars.n) if not (1600 < bars.hhmm[i] <= 1700)]
    cols = {name: array(tc, (getattr(bars, name)[i] for i in keep)) for name, tc in FIELDS}
    return Bars(bars.symbol, cols)


if __name__ == "__main__":
    import sys
    for sym in sys.argv[1:]:
        b = load(sym)
        print(sym, b.n, "bars cached")
