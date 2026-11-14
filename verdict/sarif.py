"""SARIF 2.1.0 output so GitHub code scanning (and any audit tool) can read a run.

Only REFUTED / INCONCLUSIVE claims become findings; VERIFIED claims are evidence,
not alerts. Upload with github/codeql-action/upload-sarif in CI.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List

from . import __version__

SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
INFO_URI = "https://github.com/Roloria/verdict"


def _evidence_summary(evidence: Any) -> str:
    if not isinstance(evidence, dict):
        return ""
    parts = []
    for key in ("occurrences", "exit_code", "max_hits", "missing", "deleted_tests",
                "failures", "path", "bytes", "changed_count"):
        if key in evidence:
            parts.append(f"{key}={str(evidence[key])[:120]}")
    return " ".join(parts)


def _line_for(result: Dict[str, Any], text: str) -> int:
    """Locate a finding from observed evidence, not a hard-coded line 1."""
    ev = result.get("evidence") or {}
    for failure in ev.get("failures") or []:
        if isinstance(failure, dict) and isinstance(failure.get("line"), int):
            return max(1, failure["line"])
    at = ev.get("at") or []
    if isinstance(at, list) and at and isinstance(at[0], int) and text:
        return text[: at[0]].count("\n") + 1
    return 1


def build_sarif(report: Dict[str, Any], target: str = "", text: str = "") -> Dict[str, Any]:
    rules: List[Dict[str, Any]] = []
    index: Dict[str, int] = {}
    findings: List[Dict[str, Any]] = []

    for r in report.get("results", []):
        kind = str(r.get("kind", "unknown"))
        if kind not in index:
            index[kind] = len(rules)
            rules.append({
                "id": f"verdict/{kind}",
                "name": kind,
                "shortDescription": {"text": f"verdict gate: {kind}"},
                "defaultConfiguration": {"level": "warning"},
                "helpUri": INFO_URI,
            })
        verdict = str(r.get("verdict", ""))
        if verdict not in ("REFUTED", "INCONCLUSIVE"):
            continue
        evidence = r.get("evidence")
        fingerprint = hashlib.sha256(
            repr([kind, r.get("params"), r.get("detail")]).encode("utf-8")
        ).hexdigest()[:16]
        findings.append({
            "ruleId": f"verdict/{kind}",
            "ruleIndex": index[kind],
            "level": "error" if verdict == "REFUTED" else "warning",
            "message": {"text": f"[{verdict}] {r.get('detail', '')}"},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": target or "artifact"},
                    "region": {"startLine": _line_for(r, text)},
                }
            }],
            "partialFingerprints": {"verdictClaim": fingerprint},
            "properties": {
                "verdict": verdict,
                "weight": r.get("weight", 0),
                "evidence": _evidence_summary(evidence),
                "information": report.get("information", 0),
            },
        })

    return {
        "version": "2.1.0",
        "$schema": SARIF_SCHEMA,
        "runs": [{
            "tool": {"driver": {
                "name": "ai-verdict",
                "version": __version__,
                "informationUri": INFO_URI,
                "rules": rules,
            }},
            "results": findings,
        }],
    }


def write_sarif(report: Dict[str, Any], path: str, target: str = "", text: str = "") -> str:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(build_sarif(report, target, text), f, indent=2, ensure_ascii=False)
        f.write("\n")
    return path
