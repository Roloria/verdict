"""Tests for the stdio MCP server."""

from __future__ import annotations

import json
import subprocess
import sys

from verdict.mcp_server import TOOLS, call_tool, handle


def test_initialize_and_tools_list():
    init = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert init["result"]["serverInfo"]["name"] == "ai-verdict"
    listing = handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert [t["name"] for t in listing["result"]["tools"]] == ["verify_claims", "list_rules"]
    assert handle({"jsonrpc": "2.0", "id": 3, "method": "nope"})["error"]["code"] == -32601


def test_verify_claims_catches_slop_over_mcp():
    out = call_tool("verify_claims", {
        "text": "Let's delve into this pivotal moment. It's worth noting the ever-evolving landscape, a testament to the tapestry of engineering.",
        "rules": "ai-tells-density",
        "min_information": 0.0,
    })
    payload = json.loads(out["content"][0]["text"])
    assert payload["refuted"] >= 1
    assert any(r["verdict"] == "REFUTED" for r in payload["results"])
    assert payload["grounded"] is False


def test_verify_claims_needs_claims_or_rules():
    out = call_tool("verify_claims", {"text": "hello"})
    assert out["isError"] is True


def test_list_rules_tool():
    out = call_tool("list_rules", {})
    payload = json.loads(out["content"][0]["text"])
    assert "ai-tells-density" in [b["name"] for b in payload["bundles"]]
    assert "slop_density" in payload["gate_kinds"]


def test_stdio_end_to_end():
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "verify_claims",
            "arguments": {"text": "clean text", "rules": "secrets-pii", "min_information": 0.0},
        }},
    ]
    proc = subprocess.run(
        [sys.executable, "-m", "verdict.mcp_server"],
        input="\n".join(json.dumps(m) for m in messages) + "\n",
        capture_output=True, text=True, timeout=30,
    )
    lines = [json.loads(x) for x in proc.stdout.strip().splitlines()]
    assert len(lines) == 2
    assert lines[0]["id"] == 1
    assert json.loads(lines[1]["result"]["content"][0]["text"])["refuted"] == 0
