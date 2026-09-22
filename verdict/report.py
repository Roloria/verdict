"""Single-file HTML report. No CDN, no JS framework, no build step.

The report is the thing a human looks at, so it leads with the verdict and the
number that matters (information), and it shows the evidence behind every row.
"""

from __future__ import annotations

import html
import json
import time
from typing import Any, Dict, List

_BADGE = {
    "VERIFIED": "pass",
    "REFUTED": "fail",
    "INCONCLUSIVE": "warn",
    "OBSERVED": "note",
    "INVALIDATED": "skip",
}

# Evidence keys worth a line; everything else is noise in a report.
_SHOW = (
    "occurrences", "at", "bytes", "exit_code", "duration_ms", "stdout_sha256",
    "matched", "missing", "changed_count", "resolved", "allowlisted", "encoding",
    "needle", "regex", "length", "path",
)


def _evidence_line(ev: Any) -> str:
    if not isinstance(ev, dict):
        return ""
    parts = []
    for k in _SHOW:
        if k in ev:
            v = ev[k]
            if isinstance(v, list):
                v = ", ".join(str(x) for x in v[:8]) + (" ..." if len(v) > 8 else "")
            elif isinstance(v, str) and len(v) > 60:
                v = v[:57] + "..."
            parts.append(f"{k}={v}")
    return "  ".join(parts)


def _card(label: str, value: Any, tone: str = "") -> str:
    return (
        f'<div class="card {tone}"><div class="k">{html.escape(str(label))}</div>'
        f'<div class="v">{html.escape(str(value))}</div></div>'
    )


def render(report: Dict[str, Any], target: str = "", rules: str = "") -> str:
    results: List[Dict[str, Any]] = report.get("results", [])
    receipt = report.get("receipt", {})
    replay = receipt.get("replay", "verdict check <target> --claims-file <claims.json>")
    generated = receipt.get("generated") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    rows = []
    for r in results:
        badge = _BADGE.get(r.get("verdict"), "warn")
        rows.append(
            "<tr>"
            f'<td><span class="b {badge}">{html.escape(str(r.get("verdict", "")))}</span></td>'
            f'<td class="mono">{html.escape(str(r.get("kind", "")))}</td>'
            f'<td class="num">{r.get("weight", 0)}</td>'
            f'<td>{html.escape(str(r.get("note") or ""))}'
            f'<div class="detail">{html.escape(str(r.get("detail", "")))}</div>'
            f'<div class="ev">{html.escape(_evidence_line(r.get("evidence")))}</div></td>'
            "</tr>"
        )

    tone = "ok" if report.get("grounded") else "bad"
    cards = (
        _card("verified", f"{report.get('verified', 0)} / {report.get('total_claims', 0)}",
              "ok" if report.get("refuted", 0) == 0 else "bad")
        + _card("refuted", report.get("refuted", 0), "bad" if report.get("refuted", 0) else "")
        + _card("inconclusive", report.get("inconclusive", 0),
                "warn" if report.get("inconclusive", 0) else "")
        + _card("information", f"{report.get('information', 0)} / {report.get('min_information', 1)}",
                "ok" if report.get("informative") else "warn")
        + _card("grounded score", report.get("grounded_score", 0))
        + _card("gate", "GROUNDED" if report.get("grounded") else "NOT GROUNDED", tone)
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>verdict gate report</title>
<style>
:root {{ --bg:#fbfaf8; --fg:#1c1c1a; --mut:#6b6b66; --line:#e4e2dc; --card:#f2f0eb;
  --ok:#0f6e56; --bad:#a32d2d; --warn:#854f0b; --note:#5f5e5a; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#161615; --fg:#eceae5; --mut:#9a978f; --line:#2e2e2b; --card:#1f1f1d;
    --ok:#5dcaa5; --bad:#f09595; --warn:#ef9f27; --note:#b4b2a9; }} }}
* {{ box-sizing:border-box }}
body {{ margin:0; padding:32px 24px; background:var(--bg); color:var(--fg);
  font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif; }}
.wrap {{ max-width:960px; margin:0 auto }}
h1 {{ font-size:18px; font-weight:500; margin:0 0 4px }}
.sub {{ color:var(--mut); font-size:13px; margin-bottom:24px }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:12px; margin-bottom:28px }}
.card {{ background:var(--card); border-radius:10px; padding:12px 14px }}
.card .k {{ color:var(--mut); font-size:12px }}
.card .v {{ font-size:20px; font-weight:500; margin-top:2px }}
.card.ok .v {{ color:var(--ok) }} .card.bad .v {{ color:var(--bad) }} .card.warn .v {{ color:var(--warn) }}
table {{ width:100%; border-collapse:collapse; font-size:13px }}
th {{ text-align:left; color:var(--mut); font-weight:500; padding:8px 10px; border-bottom:1px solid var(--line) }}
td {{ padding:10px; border-bottom:1px solid var(--line); vertical-align:top }}
.mono {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px }}
.num {{ font-variant-numeric:tabular-nums; color:var(--mut) }}
.b {{ display:inline-block; padding:1px 8px; border-radius:999px; font-size:11px; font-weight:500 }}
.b.pass {{ background:var(--ok); color:#fff }} .b.fail {{ background:var(--bad); color:#fff }}
.b.warn {{ background:var(--warn); color:#fff }} .b.note,.b.skip {{ background:var(--note); color:#fff }}
.detail {{ color:var(--fg); margin-top:2px }}
.ev {{ color:var(--mut); font-family:ui-monospace,Menlo,monospace; font-size:11px; margin-top:4px; word-break:break-all }}
footer {{ margin-top:28px; color:var(--mut); font-size:12px }}
code {{ background:var(--card); padding:2px 6px; border-radius:4px }}
</style></head><body><div class="wrap">
<h1>verdict · gate report</h1>
<div class="sub">{html.escape(target or 'artifact')} · {html.escape(generated)}
{f' · rules: {html.escape(rules)}' if rules else ''}</div>
<div class="cards">{cards}</div>
<table><thead><tr><th>verdict</th><th>gate</th><th>weight</th><th>claim</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<footer>
<div>replay: <code>{html.escape(replay)}</code></div>
<div>artifact sha256: <code>{html.escape(str(receipt.get('binary_sha256', '')))}</code></div>
<div>verdict {html.escape(str(receipt.get('reverify', '')))} · python {html.escape(str(receipt.get('python', '')))}</div>
</footer>
</div></body></html>
"""


def render_file(report: Dict[str, Any], out_path: str, target: str = "", rules: str = "") -> str:
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(render(report, target=target, rules=rules))
    return out_path


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
