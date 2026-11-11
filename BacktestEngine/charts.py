"""Equity-curve charts as standalone SVG (no plotting library needed).

equity_svg() draws end-of-day equity for one or more series (e.g. 1 and 2 contracts) with the
drawdown from the running peak in a pane underneath. gallery_html() links a folder of charts.
"""
import html
from datetime import date

COLORS = ["#2563eb", "#d97706", "#059669", "#db2777"]
W, H = 960, 520
L, R = 78, 20
TOP, MID, BOT = 46, 330, 470          # equity pane TOP..MID, drawdown pane MID+30..BOT


def _ticks(lo, hi, n=5):
    if hi <= lo:
        hi = lo + 1
    raw = (hi - lo) / n
    mag = 10 ** len(str(int(raw))) / 10 if raw >= 1 else 1
    step = min((s * mag for s in (1, 2, 2.5, 5, 10) if s * mag >= raw), default=raw)
    start = (lo // step) * step
    out = []
    v = start
    while v <= hi + step * 0.001:
        if v >= lo - step * 0.001:
            out.append(v)
        v += step
    return out


def _money(v):
    return f"-${abs(v):,.0f}" if v < 0 else f"${v:,.0f}"


def equity_svg(days, series, title, subtitle, path, initial):
    """days: list of day ordinals; series: {label: [equity per day]}."""
    n = len(days)
    if n < 2:
        return
    allv = [v for s in series.values() for v in s] + [initial]
    lo, hi = min(allv), max(allv)
    pad = (hi - lo) * 0.05 or 1
    lo, hi = lo - pad, hi + pad
    dds = {}
    for lab, s in series.items():
        peak = s[0]
        dd = []
        for v in s:
            peak = max(peak, v)
            dd.append(v - peak)
        dds[lab] = dd
    dlo = min(min(d) for d in dds.values()) or -1
    d0 = days[0]
    span = days[-1] - d0 or 1

    def x(d):
        return L + (d - d0) / span * (W - L - R)

    def y(v):
        return MID - (v - lo) / (hi - lo) * (MID - TOP)

    def yd(v):
        return MID + 30 + (v / dlo) * (BOT - MID - 30)

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
         f'font-family="Segoe UI, Arial, sans-serif" font-size="12">',
         f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
         f'<text x="{L}" y="22" font-size="16" font-weight="600" fill="#111">{html.escape(title)}</text>',
         f'<text x="{L}" y="39" fill="#555">{html.escape(subtitle)}</text>']
    for v in _ticks(lo, hi):
        o.append(f'<line x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="#e5e7eb"/>')
        o.append(f'<text x="{L - 6}" y="{y(v) + 4:.1f}" text-anchor="end" fill="#555">{_money(v)}</text>')
    o.append(f'<line x1="{L}" x2="{W - R}" y1="{y(initial):.1f}" y2="{y(initial):.1f}" '
             f'stroke="#9ca3af" stroke-dasharray="4 4"/>')
    for v in _ticks(dlo, 0, 3):
        if v <= 0:
            o.append(f'<line x1="{L}" x2="{W - R}" y1="{yd(v):.1f}" y2="{yd(v):.1f}" stroke="#e5e7eb"/>')
            o.append(f'<text x="{L - 6}" y="{yd(v) + 4:.1f}" text-anchor="end" fill="#555">{_money(v)}</text>')
    o.append(f'<text x="{L}" y="{MID + 22}" fill="#555">Drawdown from peak</text>')
    y0 = date.fromordinal(d0).year
    y1 = date.fromordinal(days[-1]).year
    for yr in range(y0, y1 + 1):
        d = date(yr, 1, 1).toordinal()
        if d0 <= d <= days[-1]:
            o.append(f'<line x1="{x(d):.1f}" x2="{x(d):.1f}" y1="{TOP}" y2="{BOT}" stroke="#f1f5f9"/>')
            o.append(f'<text x="{x(d):.1f}" y="{BOT + 18}" text-anchor="middle" fill="#555">{yr}</text>')
    step = max(1, n // 1500)
    for k, (lab, s) in enumerate(series.items()):
        col = COLORS[k % len(COLORS)]
        pts = " ".join(f"{x(days[i]):.1f},{y(s[i]):.1f}" for i in range(0, n, step))
        o.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="1.6"/>')
        dpts = " ".join(f"{x(days[i]):.1f},{yd(dds[lab][i]):.1f}" for i in range(0, n, step))
        o.append(f'<polyline points="{x(days[0]):.1f},{yd(0):.1f} {dpts} {x(days[-1]):.1f},{yd(0):.1f}" '
                 f'fill="{col}" fill-opacity="0.18" stroke="{col}" stroke-width="1"/>')
        lx = W - R - 230 + k * 115
        o.append(f'<rect x="{lx}" y="12" width="12" height="3" fill="{col}"/>')
        o.append(f'<text x="{lx + 16}" y="17" fill="#111">{html.escape(lab)}: {_money(s[-1] - initial)}</text>')
    o.append("</svg>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(o))


def gallery_html(folder, entries, title):
    """entries: list of (svg filename, caption) -> index.html in folder."""
    cards = "\n".join(
        f'<figure><img src="{html.escape(f)}" alt="{html.escape(c)}"><figcaption>{html.escape(c)}</figcaption></figure>'
        for f, c in entries)
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;margin:16px;background:#f8fafc;color:#111}}
figure{{margin:0 0 20px;background:#fff;border:1px solid #e5e7eb;padding:8px;max-width:980px}}
img{{width:100%;height:auto}}figcaption{{color:#555;font-size:13px}}</style></head>
<body><h1>{html.escape(title)}</h1>{cards}</body></html>"""
    with open(f"{folder}/index.html", "w", encoding="utf-8") as fh:
        fh.write(page)


MULTI_COLORS = ["#2563eb", "#d97706", "#059669", "#db2777", "#7c3aed", "#0891b2", "#65a30d", "#dc2626"]


def equity_multi_svg(days, series, title, sub, path, initial):
    """Like equity_svg, for up to 8 series with a 3-column legend (sizes and sizing schemes)."""
    ACCOUNT = initial
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
        c = MULTI_COLORS[k % len(MULTI_COLORS)]
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
