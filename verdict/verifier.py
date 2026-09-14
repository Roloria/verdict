"""Text / file claim handlers layered on top of reverify's verifier.

reverify dispatches a claim by ``getattr(self, "_check_" + kind)``. Adding a gate
is therefore additive: subclass, add methods, done. Nothing under reverify/ is
edited, so ``git merge upstream/main`` stays clean.

Claim kinds added here (v0.1, the document/report vertical):

  text_present  — the output must contain a literal or a regex (optionally N times)
  text_absent   — the output must NOT contain it (AI-tell words, secrets, PII)
  file_exists   — a path the AI says it created exists, is inside the repo, and
                  is at least N bytes

Scoring: reverify's ``summarize`` gives unknown kinds a flat 0.3. ``rescore``
applies verdict's own weight table (this is the product's rule set, so it lives
here, not upstream).
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from reverify.verifier import (
    INCONCLUSIVE,
    INVALIDATED,
    OBSERVED,
    REFUTED,
    VERIFIED,
    Claim,
    ClaimError,
    Verifier,
)

TEXT_KINDS = ("text_present", "text_absent", "file_exists")

# How much a claim says when it verifies. Higher = harder to satisfy by accident.
# Deliberately below the bar for "this file exists" (easy) and above it for
# "this exact claim is absent" (a real constraint on the output).
_GATE_WEIGHTS = {
    "text_present": 0.45,
    "text_absent": 0.40,
    "file_exists": 0.20,
}
_REGEX_BONUS = 0.10
_SPECIFICITY_BONUS = 0.10  # an exact expected count says more than "at least one"

_SCORE_PENALTY = (INVALIDATED, OBSERVED)


def _decode(data: bytes) -> Tuple[str, str]:
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace"), "utf-8/replace"


def _compile(p: Dict[str, Any]) -> Tuple[str, bool]:
    """Return (needle, is_regex) from a claim, validating the regex if any."""
    is_regex = bool(p.get("regex", False)) or "pattern" in p and "value" not in p
    needle = p.get("pattern") if is_regex else p.get("value")
    if needle is None:
        raise ClaimError("needs 'value' (literal) or 'pattern' (regex)")
    needle = str(needle)
    if not needle:
        raise ClaimError("empty value")
    if is_regex:
        try:
            re.compile(needle)
        except re.error as exc:
            raise ClaimError(f"bad regex: {exc}")
    return needle, is_regex


def _count_hits(text: str, needle: str, is_regex: bool) -> Tuple[int, List[int]]:
    if is_regex:
        spans = [m.start() for m in re.finditer(needle, text)]
        return len(spans), spans[:5]
    spans, start = [], 0
    while True:
        i = text.find(needle, start)
        if i < 0:
            break
        spans.append(i)
        start = i + max(1, len(needle))
        if len(spans) >= 1000:
            break
    return len(spans), spans[:5]


def _resolve_path(base_dir: str, raw: str) -> Optional[str]:
    """Resolve a repo-relative path, refusing anything that escapes base_dir."""
    root = os.path.realpath(base_dir)
    candidate = os.path.realpath(os.path.join(root, str(raw)))
    if candidate == root or candidate.startswith(root + os.sep):
        return candidate
    return None


class GateVerifier(Verifier):
    """reverify's Verifier plus gates on text and repository files."""

    def __init__(self, data: bytes, base_dir: str = ".") -> None:
        super().__init__(data)
        self.base_dir = base_dir
        self._text_cache: Optional[str] = None
        self._enc_cache: str = "utf-8"

    def _text(self) -> str:
        if self._text_cache is None:
            self._text_cache, self._enc_cache = _decode(self.data)
        return self._text_cache

    # -- gates --------------------------------------------------------------

    def _check_text_present(self, p: Dict[str, Any]):
        """Claim: the output contains this literal/regex, optionally N times."""
        needle, is_regex = _compile(p)
        text = self._text()
        hits, spans = _count_hits(text, needle, is_regex)
        evidence: Dict[str, Any] = {
            "encoding": self._enc_cache,
            "needle": needle,
            "regex": is_regex,
            "occurrences": hits,
            "at": spans,
            "length": len(text),
        }
        want = p.get("count")
        lo = p.get("min_count")
        hi = p.get("max_count")
        if want is not None:
            lo = hi = want
        if hits == 0:
            return REFUTED, evidence, "not found in the output"
        if lo is not None and hits < int(lo):
            return REFUTED, evidence, f"found {hits}, claim needs at least {lo}"
        if hi is not None and hits > int(hi):
            return REFUTED, evidence, f"found {hits}, claim allows at most {hi}"
        detail = "found" if lo is None and hi is None else f"found {hits}, within the claimed range"
        return VERIFIED, evidence, detail

    def _check_text_absent(self, p: Dict[str, Any]):
        """Claim: the output does NOT contain this literal/regex (tells, secrets)."""
        needle, is_regex = _compile(p)
        text = self._text()
        hits, spans = _count_hits(text, needle, is_regex)
        evidence: Dict[str, Any] = {
            "encoding": self._enc_cache,
            "needle": needle,
            "regex": is_regex,
            "occurrences": hits,
            "at": spans,
            "length": len(text),
        }
        if hits:
            return REFUTED, evidence, f"found {hits} occurrence(s) that must not be there"
        return VERIFIED, evidence, "absent as claimed"

    def _check_file_exists(self, p: Dict[str, Any]):
        """Claim: this repo-relative path exists and is at least min_bytes."""
        raw = p.get("path")
        if raw is None:
            raise ClaimError("file_exists requires 'path'")
        resolved = _resolve_path(self.base_dir, raw)
        evidence: Dict[str, Any] = {"path": str(raw), "base_dir": os.path.realpath(self.base_dir)}
        if resolved is None:
            return (
                REFUTED,
                evidence,
                "path escapes the repository root (or is the root itself)",
            )
        if not os.path.isfile(resolved):
            return REFUTED, evidence, "path does not exist or is not a file"
        size = os.path.getsize(resolved)
        evidence["bytes"] = size
        floor = p.get("min_bytes")
        if floor is not None and size < int(floor):
            return REFUTED, evidence, f"file is {size} bytes, claim needs at least {floor}"
        return VERIFIED, evidence, f"exists ({size} bytes)"

    # -- scoring ------------------------------------------------------------

    def verify_all(
        self,
        claims: List[Claim],
        facts: Optional[Dict[str, Any]] = None,
        min_information: float = 1.0,
    ) -> Dict[str, Any]:
        report = super().verify_all(claims, facts=facts, min_information=min_information)
        return rescore(report, min_information=min_information)


def gate_weight(result: Dict[str, Any]) -> float:
    """verdict's own weight table for the kinds it owns."""
    kind = result["kind"]
    p = result.get("params", {}) or {}
    ev = result.get("evidence", {}) or {}
    if ev.get("self_referential"):
        return 0.0
    base = _GATE_WEIGHTS.get(kind, 0.3)
    if p.get("regex") or "pattern" in p and "value" not in p:
        base += _REGEX_BONUS
    if kind == "text_present" and any(k in p for k in ("count", "min_count", "max_count")):
        base += _SPECIFICITY_BONUS
    if kind == "file_exists" and "min_bytes" in p:
        base += _SPECIFICITY_BONUS
    # A needle that matches everywhere in the text says little; rarity wins.
    occ = max(1, int(ev.get("occurrences", 1) or 1))
    rarity = (1.0 / occ) ** 0.5 if kind == "text_present" else 1.0
    return round(min(1.0, base) * rarity, 3)


def rescore(report: Dict[str, Any], min_information: float = 1.0) -> Dict[str, Any]:
    """Re-apply verdict's weights to the gate kinds and refresh the summary."""
    results = report.get("results", [])
    for r in results:
        if r["kind"] not in TEXT_KINDS:
            continue
        if r["verdict"] in _SCORE_PENALTY or r.get("duplicate") or r.get("trivial") or r.get("echoed") or r.get("known"):
            r["weight"] = 0.0
        else:
            r["weight"] = gate_weight(r)

    scored = [r for r in results if r["verdict"] in (VERIFIED, REFUTED, INCONCLUSIVE)]
    counted = [r for r in scored if not (r.get("duplicate") or r.get("trivial") or r.get("echoed") or r.get("known"))]
    information = round(sum(r["weight"] for r in results if r["verdict"] == VERIFIED), 3)
    weighted_total = round(sum(r["weight"] for r in counted if r["weight"]), 3)

    report["information"] = information
    report["weighted_total"] = weighted_total
    report["grounded_score"] = round(information / weighted_total, 4) if weighted_total else 0.0
    report["min_information"] = float(min_information)
    report["informative"] = information >= float(min_information)
    report["grounded"] = bool(report.get("trustworthy")) and report["informative"]
    report["gate_kinds"] = sorted({r["kind"] for r in results if r["kind"] in TEXT_KINDS})
    return report
