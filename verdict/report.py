"""Single-file bilingual HTML report. No CDN, no JS framework, no build step.

The page embeds BOTH languages and switches them client-side with a small
inline script, so a saved report can be opened offline and still be toggled.
Server-side language selection comes from i18n (`--lang`, VERDICT_LANG,
.verdict/config.json, locale) and decides which language is visible on load.

Protocol values (VERIFIED / REFUTED / ...), claim kinds and --json output are
never translated — only human-facing prose is.
"""

from __future__ import annotations

import html as _html
import json
import time
from typing import Any, Dict, List, Optional

from .i18n import evidence_line, get_lang, set_lang, t, translate_detail, verdict_label

_BADGE = {
    "VERIFIED": "pass",
    "REFUTED": "fail",
    "INCONCLUSIVE": "warn",
    "OBSERVED": "note",
    "INVALIDATED": "skip",
}
_SHOW = (
    "occurrences", "at", "bytes", "exit_code", "duration_ms", "stdout_sha256",
    "matched", "missing", "changed_count", "resolved", "allowlisted", "encoding",
    "needle", "regex", "length", "path",
)


def _span(zh: str, en: str, lang: str) -> str:
    """A text node carrying both languages for the client-side switch."""
    return (
        '<span class="tr" '
        f'data-zh="{_html.escape(zh)}" data-en="{_html.escape(en)}">'
        f'{_html.escape(zh if lang == "zh-CN" else en)}</span>'
    )


def _both(key: str, lang: str, **kwargs: Any) -> str:
    return _span(t(key, "zh-CN", **kwargs), t(key, "en", **kwargs), lang)


def _card(label_zh: str, label_en: str, value_zh: Any, value_en: Any, lang: str, tone: str = "") -> str:
    return (
        f'<div class="card {tone}"><div class="k">{_span(label_zh, label_en, lang)}</div>'
        f'<div class="v">{_span(str(value_zh), str(value_en), lang)}</div></div>'
    )


def _display_detail(detail: Any, lang: Optional[str] = None) -> str:
    """Kept for callers/tests that used report.py's local helper."""
    return translate_detail(detail, lang or get_lang())


def render(
    report: Dict[str, Any],
    target: str = "",
    rules: str = "",
    lang: Optional[str] = None,
) -> str:
    lang = set_lang(lang) if lang else get_lang()
    results: List[Dict[str, Any]] = report.get("results", [])
    receipt = report.get("receipt", {})
    replay = receipt.get("replay", "verdict check <target> --claims-file <claims.json>")
    generated = receipt.get("generated") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    rows = []
    for r in results:
        verdict = str(r.get("verdict", ""))
        badge = _BADGE.get(verdict, "warn")
        detail = r.get("detail", "")
        ev = r.get("evidence")
        rows.append(
            "<tr>"
            f'<td><span class="b {badge} tr" '
            f'data-zh="{_html.escape(verdict_label(verdict, "zh-CN"))}" '
            f'data-en="{_html.escape(verdict_label(verdict, "en"))}">'
            f'{_html.escape(verdict_label(verdict, lang))}</span></td>'
            f'<td class="mono">{_html.escape(str(r.get("kind", "")))}</td>'
            f'<td class="num">{r.get("weight", 0)}</td>'
            f'<td>{_html.escape(str(r.get("note") or ""))}'
            f'<div class="detail">{_span(translate_detail(detail, "zh-CN"), translate_detail(detail, "en"), lang)}</div>'
            f'<div class="ev">{_span(evidence_line(ev, "zh-CN", _SHOW), evidence_line(ev, "en", _SHOW), lang)}</div></td>'
            "</tr>"
        )

    tone = "ok" if report.get("grounded") else "bad"
    cards = (
        _card(t("card.verified", "zh-CN"), t("card.verified", "en"),
              f"{report.get('verified', 0)} / {report.get('total_claims', 0)}",
              f"{report.get('verified', 0)} / {report.get('total_claims', 0)}", lang,
              "ok" if report.get("refuted", 0) == 0 else "bad")
        + _card(t("card.refuted", "zh-CN"), t("card.refuted", "en"),
                report.get("refuted", 0), report.get("refuted", 0), lang,
                "bad" if report.get("refuted", 0) else "")
        + _card(t("card.inconclusive", "zh-CN"), t("card.inconclusive", "en"),
                report.get("inconclusive", 0), report.get("inconclusive", 0), lang,
                "warn" if report.get("inconclusive", 0) else "")
        + _card(t("card.information", "zh-CN"), t("card.information", "en"),
                f"{report.get('information', 0)} / {report.get('min_information', 1)}",
                f"{report.get('information', 0)} / {report.get('min_information', 1)}", lang,
                "ok" if report.get("informative") else "warn")
        + _card(t("card.grounded_score", "zh-CN"), t("card.grounded_score", "en"),
                report.get("grounded_score", 0), report.get("grounded_score", 0), lang)
        + _card(t("card.gate", "zh-CN"), t("card.gate", "en"),
                t("gate.pass" if report.get("grounded") else "gate.fail", "zh-CN"),
                t("gate.pass" if report.get("grounded") else "gate.fail", "en"), lang, tone)
    )

    return f"""<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_html.escape(t('report.title', lang))}</title>
<style>
:root {{ --bg:#fbfaf8; --fg:#1c1c1a; --mut:#6b6b66; --line:#e4e2dc; --card:#f2f0eb;
  --ok:#0f6e56; --bad:#a32d2d; --warn:#854f0b; --note:#5f5e5a; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#161615; --fg:#eceae5; --mut:#9a978f; --line:#2e2e2b; --card:#1f1f1d;
    --ok:#5dcaa5; --bad:#f09595; --warn:#ef9f27; --note:#b4b2a9; }} }}
* {{ box-sizing:border-box }}
body {{ margin:0; padding:32px 24px; background:var(--bg); color:var(--fg);
  font:14px/1.6 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei","Segoe UI",system-ui,sans-serif; }}
.wrap {{ max-width:960px; margin:0 auto }}
.top {{ display:flex; align-items:flex-start; justify-content:space-between; gap:12px }}
h1 {{ font-size:18px; font-weight:500; margin:0 0 4px }}
.sub {{ color:var(--mut); font-size:13px; margin-bottom:24px }}
.langbtn {{ background:transparent; color:var(--fg); border:0.5px solid var(--line);
  border-radius:8px; padding:6px 12px; cursor:pointer; font:inherit; font-size:12px; white-space:nowrap }}
.langbtn:hover {{ border-color:var(--mut) }}
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
<div class="top"><div>
<h1>{_span(t('report.title','zh-CN'), t('report.title','en'), lang)}</h1>
<div class="sub">{_html.escape(target or t('report.artifact', lang))} · {_html.escape(generated)}
{f' · {_both("report.rules", lang, rules=rules)}' if rules else ''}</div>
</div><button class="langbtn" id="langbtn" data-current="{lang}" type="button">{_html.escape(t('report.lang_switch', lang))}</button></div>
<div class="cards">{cards}</div>
<table><thead><tr>
<th>{_both('table.verdict', lang)}</th><th>{_both('table.gate', lang)}</th>
<th>{_both('table.weight', lang)}</th><th>{_both('table.claim', lang)}</th>
</tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<footer>
<div>{_both('footer.replay', lang)} <code>{_html.escape(replay)}</code></div>
<div>{_both('footer.sha', lang)} <code>{_html.escape(str(receipt.get('binary_sha256', '')))}</code></div>
<div>{_both('footer.version', lang, version=str(receipt.get('reverify','')), python=str(receipt.get('python','')))}</div>
</footer>
</div>
<script>
(function () {{
  var btn = document.getElementById('langbtn');
  function setLang(l) {{
    document.documentElement.lang = l;
    document.querySelectorAll('.tr').forEach(function (el) {{
      el.textContent = el.getAttribute(l === 'zh-CN' ? 'data-zh' : 'data-en');
    }});
    btn.textContent = l === 'zh-CN' ? 'English' : '中文';
    btn.setAttribute('data-current', l);
    var h1 = document.querySelector('h1 .tr');
    if (h1) document.title = h1.textContent;
  }}
  btn.addEventListener('click', function () {{
    setLang(btn.getAttribute('data-current') === 'zh-CN' ? 'en' : 'zh-CN');
  }});
}})();
</script>
</body></html>
"""


def render_file(
    report: Dict[str, Any],
    out_path: str,
    target: str = "",
    rules: str = "",
    lang: Optional[str] = None,
) -> str:
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(render(report, target=target, rules=rules, lang=lang))
    return out_path


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
