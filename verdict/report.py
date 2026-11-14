"""Single-file HTML report, in Chinese. No CDN, no JS framework, no build step.

Only the presentation layer is translated. The underlying verdict values
(VERIFIED / REFUTED / ...) and the JSON output stay English so scripts, CI and
the upstream claim protocol keep consuming them unchanged.
"""

from __future__ import annotations

import html
import json
import re
import time
from typing import Any, Dict, List

_BADGE = {
    "VERIFIED": "pass",
    "REFUTED": "fail",
    "INCONCLUSIVE": "warn",
    "OBSERVED": "note",
    "INVALIDATED": "skip",
}
_VERDICT_ZH = {
    "VERIFIED": "已验证",
    "REFUTED": "已驳回",
    "INCONCLUSIVE": "未定论",
    "OBSERVED": "已观察",
    "INVALIDATED": "已失效",
}

# Evidence keys worth a line; everything else is noise in a report.
_SHOW = (
    "occurrences", "at", "bytes", "exit_code", "duration_ms", "stdout_sha256",
    "matched", "missing", "changed_count", "resolved", "allowlisted", "encoding",
    "needle", "regex", "length", "path",
)
_EV_KEY_ZH = {
    "occurrences": "出现次数", "at": "位置", "bytes": "字节数",
    "exit_code": "退出码", "duration_ms": "耗时(ms)", "stdout_sha256": "输出哈希",
    "matched": "已命中", "missing": "缺失", "changed_count": "变更数",
    "resolved": "已解析", "allowlisted": "白名单", "encoding": "编码",
    "needle": "匹配串", "regex": "正则", "length": "长度", "path": "路径",
}

# Gate detail strings are English in the core (they are data, not UI). Translate
# them here, one segment at a time, so combined red-flag messages also localise.
_DETAIL_ZH = [
    (r"unknown claim kind '(.+)'", r"未知的闸门类型「\1」"),
    (r"malformed claim: (.+)", r"断言格式错误：\1"),
    (r"tool error: (.+)", r"工具错误：\1"),
    (r"found (\d+) occurrence\(s\) that must not be there", r"出现 \1 处本不该出现的内容"),
    (r"absent as claimed", r"符合断言：未出现"),
    (r"not found in the output", r"产物中未找到"),
    (r"found (\d+), claim needs at least (\d+)", r"出现 \1 次，断言要求至少 \2 次"),
    (r"found (\d+), claim allows at most (\d+)", r"出现 \1 次，断言上限为 \2 次"),
    (r"found (\d+), within the claimed range", r"出现 \1 次，在断言范围内"),
    (r"^found$", r"已找到"),
    (r"path escapes the repository root(?: \(or is the root itself\))?", r"路径越出仓库根目录"),
    (r"path does not exist or is not a file", r"路径不存在或不是文件"),
    (r"file is (\d+) bytes, claim needs at least (\d+)", r"文件仅 \1 字节，断言要求至少 \2 字节"),
    (r"exists \((\d+) bytes\)", r"文件存在（\1 字节）"),
    (r"cwd escapes the repository root", r"工作目录越出仓库根目录"),
    (r"cwd is not a directory", r"工作目录不是文件夹"),
    (r"command is not allow-listed; refusing to execute.*", r"命令不在白名单，拒绝执行（请加入 .verdict/allowlist.json）"),
    (r"'(.+)' is not on PATH", r"在 PATH 中找不到 \1"),
    (r"timed out after (.+)s", r"执行超时（\1 秒）"),
    (r"could not execute: (.+)", r"无法执行：\1"),
    (r"exit (\d+), expected (\d+)", r"退出码 \1，预期 \2"),
    (r"stdout does not match /(.+)/", r"标准输出不匹配 /\1/"),
    (r"exit (\d+) in (\d+)ms", r"退出码 \1，耗时 \2 毫秒"),
    (r"git is not available", r"git 不可用"),
    (r"git diff failed: (.+)", r"git diff 失败：\1"),
    (r"git diff failed(?: \(not a repo, or bad base\?\))?", r"git diff 失败（不是仓库或基准无效？）"),
    (r"diff touches (\d+) of the claimed paths", r"差异触及 \1 个声明的路径"),
    (r"diff touches none of the claimed paths", r"差异未触及任何声明的路径"),
    (r"claimed paths absent from the diff: (.+)", r"差异中缺少声明的路径：\1"),
    (r"diff touches all (\d+) claimed path\(s\)", r"差异触及全部 \1 个声明路径"),
    (r"(\d+) distinct AI-tell patterns in one paragraph \(limit (\d+)\)", r"单段命中 \1 个不同 AI 味模式（阈值 \2）"),
    (r"max (\d+) distinct patterns in a paragraph, below (\d+)", r"单段最多命中 \1 个模式，低于阈值 \2"),
    (r"nothing changed against the base ref", r"与基准相比没有任何改动"),
    (r"deleted test file\(s\): (.+)", r"删除了测试文件：\1"),
    (r"(\d+) new skip/\.only marker\(s\) in the diff", r"差异中新增 \1 处跳过/仅运行标记"),
    (r"code changed with no test file changed", r"修改了代码但没有任何测试文件变动"),
    (r"(\d+) test file\(s\) changed, no tampering markers", r"\1 个测试文件有变动，未发现篡改标记"),
    (r"no path:line citations found in the output", r"产物中未发现 path:line 形式的引用"),
    (r"(\d+) of (\d+) cited location\(s\) do not resolve", r"\2 处引用中有 \1 处无效"),
    (r"all (\d+) cited location\(s\) resolve with observed line content", r"\1 处引用均有效，已返回实际行内容"),
    (r"escapes the repository root", r"越出仓库根目录"),
    (r"file not found", r"文件不存在"),
    (r"line out of range \(file has (\d+) lines\)", r"行号越界（文件共 \1 行）"),
    (r"line content mismatch", r"行内容与断言不符"),
]
_DETAIL_ZH = [(re.compile(p), r) for p, r in _DETAIL_ZH]


def _display_detail(detail: Any) -> str:
    def one(segment: str) -> str:
        for pattern, repl in _DETAIL_ZH:
            m = pattern.match(segment)
            if m:
                return m.expand(repl)
        return segment
    return "；".join(one(part) for part in str(detail or "").split("; "))


def _evidence_line(ev: Any) -> str:
    if not isinstance(ev, dict):
        return ""
    parts = []
    for k in _SHOW:
        if k in ev:
            v = ev[k]
            if isinstance(v, bool):
                v = "是" if v else "否"
            elif isinstance(v, list):
                if not v:
                    continue
                v = ", ".join(str(x) for x in v[:8]) + (" ..." if len(v) > 8 else "")
            elif isinstance(v, str) and len(v) > 60:
                v = v[:57] + "..."
            parts.append(f"{_EV_KEY_ZH.get(k, k)}={v}")
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
        verdict = str(r.get("verdict", ""))
        badge = _BADGE.get(verdict, "warn")
        rows.append(
            "<tr>"
            f'<td><span class="b {badge}">{html.escape(_VERDICT_ZH.get(verdict, verdict))}</span></td>'
            f'<td class="mono">{html.escape(str(r.get("kind", "")))}</td>'
            f'<td class="num">{r.get("weight", 0)}</td>'
            f'<td>{html.escape(str(r.get("note") or ""))}'
            f'<div class="detail">{html.escape(_display_detail(r.get("detail")))}</div>'
            f'<div class="ev">{html.escape(_evidence_line(r.get("evidence")))}</div></td>'
            "</tr>"
        )

    tone = "ok" if report.get("grounded") else "bad"
    cards = (
        _card("已验证", f"{report.get('verified', 0)} / {report.get('total_claims', 0)}",
              "ok" if report.get("refuted", 0) == 0 else "bad")
        + _card("已驳回", report.get("refuted", 0), "bad" if report.get("refuted", 0) else "")
        + _card("未定论", report.get("inconclusive", 0),
                "warn" if report.get("inconclusive", 0) else "")
        + _card("信息量", f"{report.get('information', 0)} / {report.get('min_information', 1)}",
                "ok" if report.get("informative") else "warn")
        + _card("证据覆盖度", report.get("grounded_score", 0))
        + _card("闸门结论", "通过" if report.get("grounded") else "未通过", tone)
    )

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>verdict · 输出质量闸门报告</title>
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
<h1>verdict · 输出质量闸门报告</h1>
<div class="sub">{html.escape(target or '产物')} · {html.escape(generated)}
{f' · 规则包：{html.escape(rules)}' if rules else ''}</div>
<div class="cards">{cards}</div>
<table><thead><tr><th>结论</th><th>闸门</th><th>权重</th><th>断言</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<footer>
<div>复现命令：<code>{html.escape(replay)}</code></div>
<div>产物 SHA-256：<code>{html.escape(str(receipt.get('binary_sha256', '')))}</code></div>
<div>verdict {html.escape(str(receipt.get('reverify', '')))} · Python {html.escape(str(receipt.get('python', '')))}</div>
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
