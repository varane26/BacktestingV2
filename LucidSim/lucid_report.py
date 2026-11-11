"""The user's standard report tables, built from any Lucid report folder (run_lucid.py or
Vaultbreak/scripts/vb_lucid.py). run_lucid.write_outputs() calls build() at the end of every test.

tables.md       per run (strategy x market x timeframe) x period, one row per sizing:
                A. performance and risk, B. trades, C. LucidPro 50K
datasheet.html  settings, key results by period, by year, exit reasons, every equity curve, every
                stats / Lucid field, and the improvement grid if the folder holds improve.json
                (list of {label, <period>: {net, pf, sharpe, dd, n, "3": [6 Lucid values], "4": [...]}})

Usage: python -I LucidSim/lucid_report.py <report folder>
"""
import csv
import html
import json
import os
import sys

INLINE_SVG_LIMIT = 12_000_000      # bytes of charts embedded in the HTML; above this they are linked


def m(v):
    return "–" if v is None else (f"-${abs(v):,.0f}" if v < 0 else f"${v:,.0f}")


def n(v, d=2):
    return "–" if v is None else f"{v:,.{d}f}"


def p(v):
    return "–" if v is None else f"{v:.1f}%"


def n0(v):
    return n(v, 0)


A = [("Net", "net_profit", m), ("Return", "total_return_pct", p), ("CAGR", "cagr_pct", p),
     ("Ann. vol", "annualized_volatility_pct", p), ("Sharpe", "sharpe_ratio", n), ("Sortino", "sortino_ratio", n),
     ("Calmar", "calmar_ratio", n), ("Max DD", "max_drawdown", m), ("Max DD %", "max_drawdown_pct", p),
     ("DD days", "max_drawdown_duration_trading_days", str), ("Recovery", "recovery_factor", n)]
B = [("Trades", "trade_count", lambda v: f"{v:,}"), ("Win %", "win_rate_pct", p), ("PF", "profit_factor", n),
     ("Avg win", "average_winner", m), ("Avg loss", "average_loser", m), ("Payoff", "payoff_ratio", n),
     ("Expect.", "expectancy_per_trade", m), ("Median", "median_trade", m), ("Best", "best_trade", m),
     ("Worst", "worst_trade", m), ("Gross +", "gross_profit", m), ("Gross -", "gross_loss", m),
     ("Max W/L run", ("max_consecutive_wins", "max_consecutive_losses"), None),
     ("Avg bars", "average_holding_bars", n0), ("Avg ct", "average_contracts_per_trade", n)]
C = [("Pass", "evaluation_pass_rate_pct", p), ("≤30d", "pass_within_30_days_pct", p),
     ("≤45d", "pass_within_45_days_pct", p), ("≤60d", "pass_within_60_days_pct", p),
     ("Mean days", "mean_days_to_pass", n0), ("Median days", "median_days_to_pass", n0),
     ("Pass/fail/open", ("evaluation_passed_simulations", "evaluation_failed_simulations",
                         "evaluation_unresolved_simulations"), None),
     ("Payout % evals", "payout_rate_pct_of_evaluations", p),
     ("Payout % passed", "payout_rate_pct_of_passed_evaluations", p),
     ("Payouts/pass", "mean_payouts_per_passed_evaluation", n),
     ("Trader $/pass", "mean_trader_payout_per_passed_evaluation", m),
     ("$ when paid", "mean_trader_payout_when_eligible", m),
     ("Days to 1st payout", "mean_days_to_first_payout_when_eligible", n0),
     ("Funded days to 1st", "mean_funded_days_to_first_payout", n0),
     ("Funded breach", "funded_breach_rate_pct_of_passed", p),
     ("Funded days lived", "mean_funded_days_survived", n0),
     ("Exp $/eval", "expected_trader_payout_per_evaluation", m)]
TABLES = [("A. Performance and risk", "stats", A), ("B. Trades", "stats", B), ("C. LucidPro 50K", "lucidpro_50k", C)]


def cell(d, key, f):
    if isinstance(key, tuple):
        return "/".join(str(d.get(k)) for k in key)
    return f(d.get(key))


def run_id(r):
    return f"{r['strategy']}_{r['market']}_{r['timeframe']}"


def load(out):
    S = json.load(open(os.path.join(out, "summary.json")))
    runs = {}
    for r in S["runs"]:
        runs.setdefault(run_id(r), {}).setdefault(r["period"], []).append(r)
    return S, runs


def md_table(recs, part, cols):
    h = ["| Sizing | " + " | ".join(c[0] for c in cols) + " |", "|---|" + "---:|" * len(cols)]
    for r in recs:
        h.append(f"| {r['sizing']} | " + " | ".join(cell(r[part], k, f) for _, k, f in cols) + " |")
    return "\n".join(h)


def html_table(head, rows):
    return ("<table><thead><tr>" + "".join(f"<th>{html.escape(str(x))}</th>" for x in head) + "</tr></thead><tbody>"
            + "".join("<tr>" + "".join(f"<td>{html.escape(str(x))}</td>" for x in row) + "</tr>" for row in rows)
            + "</tbody></table>")


def has_lucid(S):
    return S.get("lucid", True) and any(r.get("lucidpro_50k") for r in S["runs"])


def costs(S):
    return (f"${S.get('commission_per_side', 0.75)}/side commission + {S.get('slippage_ticks_per_side', 1):g} tick "
            f"slippage per side on market and stop fills; $50,000 account"
            + ("; LucidPro 50K, daily loss limit off, 1,000 block-bootstrap paths" if has_lucid(S) else "; no Lucid sim"))


def tables_md(out, S, runs):
    lines = [f"# {S.get('title', 'Lucid report')}\n", costs(S) + ".\n"]
    for rid, per in runs.items():
        r0 = next(iter(per.values()))[0]
        _t = r0['name'] if (r0['strategy'].replace('_', ' ') == r0['name'] or (r0['strategy'][:1] == 'S' and r0['strategy'][1:].isdigit())) else f"{r0['strategy']} {r0['name']}"
        lines.append(f"## {_t} — {r0['market']} ({r0['contract']}) {r0['timeframe']}\n")
        for plab, recs in per.items():
            s1 = recs[0]["stats"]
            lines.append(f"### {rid} — {plab} ({s1['first_day']} to {s1['last_day']}, {s1['trading_days']} trading days)\n")
            for title, part, cols in TABLES if has_lucid(S) else TABLES[:2]:
                lines.append(f"**{title}**\n\n" + md_table(recs, part, cols) + "\n")
    path = os.path.join(out, "tables.md")
    open(path, "w", encoding="utf-8").write("\n".join(lines))
    return path


def fmt_field(k, v):
    if v is None:
        return "–"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (list, dict, str)):
        return v if isinstance(v, str) else json.dumps(v)
    if "pct" in k:
        return f"{v:.1f}%"
    if isinstance(v, int):
        return f"{v:,}"
    return f"{v:,.2f}"


def datasheet(out, S, runs):
    eq = os.path.join(out, "equity")
    files = [f for f in S.get("charts", []) if os.path.exists(os.path.join(eq, f))]
    inline = sum(os.path.getsize(os.path.join(eq, f)) for f in files) <= INLINE_SVG_LIMIT

    def chart(fn):
        if fn not in files:
            return ""
        if inline:
            return f"<div class=card>{open(os.path.join(eq, fn), encoding='utf-8').read()}</div>"
        return f'<div class=card><img src="equity/{html.escape(fn)}" alt="{html.escape(fn)}"></div>'

    sizings = list(S["sizings"])
    periods = [x[0] for x in S["periods"]]
    o = [f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lucid Data Sheet</title><style>
body{{font:13px/1.45 Segoe UI,Arial,sans-serif;margin:0;padding:16px;background:#f8fafc;color:#111}}
h1{{font-size:22px}}h2{{font-size:18px;margin-top:32px;border-bottom:2px solid #2563eb}}h3{{font-size:15px;margin-top:22px}}
.card{{background:#fff;border:1px solid #e5e7eb;padding:10px;margin:10px 0;overflow-x:auto}}
table{{border-collapse:collapse;font-variant-numeric:tabular-nums}}th,td{{padding:3px 8px;border-bottom:1px solid #e5e7eb;text-align:right;white-space:nowrap}}
th{{background:#f1f5f9}}td:first-child,th:first-child{{text-align:left}}svg,img{{max-width:100%;height:auto}}
details{{margin:6px 0}}summary{{cursor:pointer;font-weight:600}}nav a{{margin-right:12px}}p.mut{{color:#555}}</style></head><body>
<h1>{html.escape(S.get('title', 'Lucid report'))}</h1><p class=mut>{html.escape(costs(S))}. Fixed sizes and balance schemes:
evaluation and funded account at that size. Market schemes: day paths replayed at the sizes traded.</p><nav>"""
         + "".join(f'<a href="#{rid}">{html.escape(rid)}</a>' for rid in runs) + "</nav>"]
    o.append("<h2>Settings</h2><div class=card>" + html_table(
        ["run", "settings"], [[rid, json.dumps(next(iter(per.values()))[0].get("settings", {}))] for rid, per in runs.items()])
        + "</div>")
    o.append("<h2>Sizing rules</h2><div class=card>" + html_table(["sizing", "rule"], list(S["sizings"].items())) + "</div>")
    key = [("Net", "stats", "net_profit", m), ("PF", "stats", "profit_factor", n), ("Sharpe", "stats", "sharpe_ratio", n),
           ("Sortino", "stats", "sortino_ratio", n), ("Max DD", "stats", "max_drawdown", m),
           ("Trades", "stats", "trade_count", str), ("Pass", "lucidpro_50k", "evaluation_pass_rate_pct", p),
           ("≤45d", "lucidpro_50k", "pass_within_45_days_pct", p), ("Mean days", "lucidpro_50k", "mean_days_to_pass", n0),
           ("Payout", "lucidpro_50k", "payout_rate_pct_of_evaluations", p),
           ("Funded breach", "lucidpro_50k", "funded_breach_rate_pct_of_passed", p),
           ("Exp $/eval", "lucidpro_50k", "expected_trader_payout_per_evaluation", m)]
    if not has_lucid(S):
        key = [k for k in key if k[1] == "stats"]
    o.append("<h2>Key results by period</h2>")
    for plab in periods:
        rows = [[rid, r["sizing"]] + [f(r[part].get(k)) for _, part, k, f in key]
                for rid, per in runs.items() for r in per.get(plab, [])]
        o.append(f"<h3>{plab}</h3><div class=card>" + html_table(["run", "sizing"] + [x[0] for x in key], rows) + "</div>")
    by = os.path.join(out, "by_year.csv")
    if os.path.exists(by):
        rows = [[r["run"], r["year"], r["trades"], f"{float(r['win_rate_pct']):.1f}%", m(float(r["net_1ct"])),
                 r["profit_factor"] and f"{float(r['profit_factor']):.2f}"] for r in csv.DictReader(open(by))]
        o.append("<h2>By year, 1 contract</h2><div class=card>"
                 + html_table(["run", "year", "trades", "win %", "net", "PF"], rows) + "</div>")
    if S.get("exit_counts"):
        o.append("<h2>Exit reasons (whole window)</h2><div class=card>" + html_table(
            ["run", "exits"], [[k, json.dumps(v)] for k, v in S["exit_counts"].items()]) + "</div>")
    for rid, per in runs.items():
        o.append(f'<h2 id="{html.escape(rid)}">{html.escape(rid)}</h2>')
        for plab, recs in per.items():
            o.append(f"<h3>{html.escape(rid)} — {plab}</h3>")
            for part in ("sizes", "balance_schemes", "market_schemes"):
                o.append(chart(f"{rid}_{plab}_{part}.svg"))
            for title, part in (("stats.csv fields", "stats"), ("lucid.csv fields", "lucidpro_50k"))[:2 if has_lucid(S) else 1]:
                keys = list(recs[0][part])
                rows = [[k] + [fmt_field(k, r[part].get(k)) for r in recs] for k in keys]
                o.append(f"<details><summary>{title} — {html.escape(rid)} {plab}</summary><div class=card>"
                         + html_table(["field"] + [r["sizing"] for r in recs], rows) + "</div></details>")
    imp_path = os.path.join(out, "improve.json")
    if os.path.exists(imp_path):
        imp = json.load(open(imp_path))
        o.append('<h2 id="imp">Candidate improvements, by period</h2><p class=mut>1-contract account stats; LucidPro at 3 '
                 'and 4 contracts fixed: pass %, pass within 45 days %, mean days to pass, payout % of evaluations, funded '
                 'breach % of passed, expected trader payout per evaluation.</p>')
        for plab in [x for x in periods if x in imp[0]]:
            head = ["variant", "Net", "PF", "Sharpe", "Max DD", "Trades"] + [
                f"{q}ct {h}" for q in ("3", "4") for h in ("pass", "≤45d", "days", "payout", "breach", "exp $")]
            rows = []
            for r in imp:
                x = r[plab]
                row = [r["label"], m(x["net"]), n(x["pf"]), n(x["sharpe"]), m(x["dd"]), x["n"]]
                for q in ("3", "4"):
                    t = x[q]
                    row += [p(t[0]), p(t[1]), n0(t[2]), p(t[3]), p(t[4]), m(t[5])]
                rows.append(row)
            o.append(f"<h3>{plab}</h3><div class=card>" + html_table(head, rows) + "</div>")
    o.append("</body></html>")
    path = os.path.join(out, "datasheet.html")
    open(path, "w", encoding="utf-8").write("\n".join(o))
    return path


def build(out):
    S, runs = load(out)
    return tables_md(out, S, runs), datasheet(out, S, runs)


if __name__ == "__main__":
    for path in build(sys.argv[1]):
        print(path)
