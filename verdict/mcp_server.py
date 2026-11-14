"""Minimal MCP server over stdio. No MCP SDK dependency.

Lets an agent gate its own output mid-run instead of only at CI time:

    {"jsonrpc":"2.0","id":1,"method":"tools/call","params":{
      "name":"verify_claims",
      "arguments":{"text":"...", "rules":"ai-tells-density,secrets-pii"}
    }}

Implements initialize / ping / tools/list / tools/call. Notifications (no id)
are ignored. One JSON object per line on stdin, one response per line on stdout.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, List

from reverify.verifier import Claim

from . import __version__
from .i18n import set_lang, translate_detail, verdict_label
from .rules import available, load_many
from .verifier import GateVerifier, TEXT_KINDS

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "verify_claims",
        "description": (
            "Check an AI-produced text against deterministic claims and rule "
            "bundles. Returns VERIFIED / REFUTED per claim, evidence, information "
            "and grounded score. Use before reporting a generated artifact as done."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "the artifact text to gate"},
                "claims": {"type": "array", "items": {"type": "object"}, "description": "claim dicts"},
                "rules": {"type": "string", "description": "comma-separated bundle names"},
                "base_dir": {"type": "string", "description": "repo root for path/diff gates"},
                "min_information": {"type": "number", "description": "evidence threshold", "default": 1.0},
                "lang": {"type": "string", "description": "display language: zh-CN | en | auto"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "list_rules",
        "description": "List available rule bundles and claim kinds.",
        "inputSchema": {"type": "object", "properties": {"base_dir": {"type": "string"}}},
    },
]


def _summarize(report: Dict[str, Any], lang: str = "zh-CN") -> Dict[str, Any]:
    return {
        "lang": lang,
        "total_claims": report["total_claims"],
        "verified": report["verified"],
        "refuted": report["refuted"],
        "inconclusive": report["inconclusive"],
        "invalidated": report["invalidated"],
        "information": report["information"],
        "min_information": report["min_information"],
        "grounded_score": report["grounded_score"],
        "grounded": report["grounded"],
        "results": [
            {
                "kind": r["kind"],
                "verdict": r["verdict"],              # protocol value, never translated
                "verdict_label": verdict_label(r["verdict"], lang),
                "weight": r.get("weight", 0),
                "detail": r.get("detail", ""),        # raw, for scripts
                "detail_display": translate_detail(r.get("detail", ""), lang),
                "note": r.get("note", ""),
            }
            for r in report["results"]
        ],
    }


def call_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    if name == "list_rules":
        base = str(args.get("base_dir", "."))
        payload = {
            "bundles": [{"name": n, "origin": o, "description": d} for n, o, d in available(base)],
            "gate_kinds": list(TEXT_KINDS),
            "upstream_kinds": "bytes_at, string_present, functions_equiv, ...",
        }
        return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}]}
    if name != "verify_claims":
        return {"content": [{"type": "text", "text": f"unknown tool: {name}"}], "isError": True}

    text = str(args.get("text", ""))
    claims_data: List[Dict[str, Any]] = list(args.get("claims") or [])
    weights: Dict[str, float] = {}
    rules = str(args.get("rules") or "")
    if rules:
        extra, weights = load_many(rules, str(args.get("base_dir", ".")))
        claims_data += extra
    if not claims_data:
        return {"content": [{"type": "text", "text": "no claims: pass 'claims' or 'rules'"}], "isError": True}

    base_dir = str(args.get("base_dir", "."))
    lang = set_lang(args.get("lang"), base_dir)
    report = GateVerifier(
        text.encode("utf-8"),
        base_dir=base_dir,
        weight_overrides=weights,
    ).verify_all(
        [Claim.from_dict(c) for c in claims_data],
        min_information=float(args.get("min_information", 1.0)),
    )
    return {"content": [{"type": "text", "text": json.dumps(_summarize(report, lang), ensure_ascii=False, indent=2)}]}


def handle(req: Dict[str, Any]) -> Dict[str, Any]:
    method = req.get("method", "")
    if method == "initialize":
        result: Any = {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "ai-verdict", "version": __version__},
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = req.get("params") or {}
        result = call_tool(str(params.get("name", "")), dict(params.get("arguments") or {}))
    else:
        return {"jsonrpc": "2.0", "id": req.get("id"), "error": {"code": -32601, "message": f"method not found: {method}"}}
    return {"jsonrpc": "2.0", "id": req.get("id"), "result": result}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(req, dict) or "id" not in req:
            continue  # notification
        sys.stdout.write(json.dumps(handle(req), ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
