"""Text / file claim handlers layered on top of reverify's verifier.

reverify dispatches a claim by ``getattr(self, "_check_" + kind)``. Adding a gate
is therefore additive: subclass, add methods, done. Nothing under reverify/ is
edited, so ``git merge upstream/main`` stays clean.

Claim kinds added here (v0.1, the document/report vertical):

  text_present  — the output must contain a literal or a regex (optionally N times)
  text_absent   — the output must NOT contain it (AI-tell words, secrets, PII)
  file_exists   — a path the AI says it created exists, is inside the repo, and
                  is at least N bytes
  command_succeeds — an allow-listed command must exit 0 (never shells out to
                  anything unlisted; unlisted means INCONCLUSIVE, never executed)
  diff_touches  — the paths the AI says it changed must actually appear in the
                  git diff against a base ref
  slop_density  — a paragraph must NOT hit N distinct AI-tell patterns; one
                  phrase is normal, three in one paragraph is slop
  tests_actually_prove — the AI must not make tests green by deleting/skipping
                  them, or by changing code with no test change at all

Scoring: reverify's ``summarize`` gives unknown kinds a flat 0.3. ``rescore``
applies verdict's own weight table (this is the product's rule set, so it lives
here, not upstream).
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

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

TEXT_KINDS = (
    "text_present",
    "text_absent",
    "file_exists",
    "command_succeeds",
    "diff_touches",
    "slop_density",
    "tests_actually_prove",
)

# How much a claim says when it verifies. Higher = harder to satisfy by accident.
# Deliberately below the bar for "this file exists" (easy) and above it for
# "this exact claim is absent" (a real constraint on the output).
_GATE_WEIGHTS = {
    "text_present": 0.45,
    "text_absent": 0.40,
    "file_exists": 0.20,
    "command_succeeds": 0.60,  # a test really ran; the strongest everyday claim
    "diff_touches": 0.50,
    "slop_density": 0.65,       # density, not a single word: low false-positive rate
    "tests_actually_prove": 0.70,
}

DEFAULT_TEST_GLOBS = (
    "test_*.py", "*_test.py", "*.test.ts", "*.spec.ts", "*.test.js", "*.spec.js",
    "*_test.go", "*Test.java", "tests/*", "__tests__/*", "*.feature",
)
SKIP_MARKERS = re.compile(
    r"\.skip\(|\.only\(|\bxit\(|\bxdescribe\(|@pytest\.mark\.skip|it\.skip|"
    r"test\.skip|--no-verify|core\.hooksPath|\bTODO:\s*skip\b"
)


def _is_test_path(path: str, globs: Sequence[str]) -> bool:
    base = os.path.basename(path)
    return any(fnmatch.fnmatch(path, g) or fnmatch.fnmatch(base, g) for g in globs)


def _load_slop_preset(name: str) -> List[Dict[str, Any]]:
    if name != "slop-120":
        raise ClaimError(f"unknown slop preset {name!r} (available: slop-120)")
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "slop_patterns.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["patterns"]

# Commands verdict will execute out of the box. Anything else is INCONCLUSIVE
# until a team allow-lists it. Entries are argv prefixes.
DEFAULT_ALLOWLIST: Sequence[Sequence[str]] = (
    ("pytest",),
    ("python", "-m", "pytest"),
    ("node", "--check"),
    ("npx", "tsc"),
    ("tsc", "--noEmit"),
    ("eslint",),
    ("ruff",),
    ("git", "diff"),
)
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


def _path_touched(claimed: str, changed: List[str]) -> bool:
    """True when a claimed path (file or directory) appears in the changed set."""
    c = str(claimed).strip().rstrip("/")
    if not c:
        return False
    return any(ch == c or ch.startswith(c + "/") or c.startswith(ch + "/") for ch in changed)


class GateVerifier(Verifier):
    """reverify's Verifier plus gates on text and repository files."""

    def __init__(
        self,
        data: bytes,
        base_dir: str = ".",
        allowlist: Optional[Sequence[Sequence[str]]] = None,
        weight_overrides: Optional[Dict[str, float]] = None,
    ) -> None:
        super().__init__(data)
        self.base_dir = base_dir
        self.allowlist = list(DEFAULT_ALLOWLIST) if allowlist is None else [list(a) for a in allowlist]
        self.weight_overrides = dict(weight_overrides or {})
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

    # -- execution gates (the dangerous ones) --------------------------------

    def _allowlisted(self, argv: List[str]) -> bool:
        return any(list(argv[: len(entry)]) == list(entry) for entry in self.allowlist)

    def _check_command_succeeds(self, p: Dict[str, Any]):
        """Claim: this allow-listed command exits as expected.

        Turns "the AI says the tests pass" into a claim with an exit code as
        evidence. Never shells out: argv only, and anything not allow-listed is
        INCONCLUSIVE rather than executed.
        """
        argv = p.get("argv")
        if argv is None:
            raise ClaimError("command_succeeds requires 'argv'")
        if isinstance(argv, str):
            raise ClaimError("argv must be a list of arguments (no shell strings)")
        argv = [str(a) for a in argv]
        if not argv:
            raise ClaimError("argv is empty")

        cwd_raw = str(p.get("cwd", "."))
        cwd = _resolve_path(self.base_dir, cwd_raw)
        timeout = float(p.get("timeout", 120))
        want_exit = int(p.get("expect_exit", 0))
        digest = hashlib.sha256(repr([argv, cwd_raw, timeout, want_exit]).encode()).hexdigest()[:16]
        evidence: Dict[str, Any] = {
            "argv": argv,
            "cwd": cwd_raw,
            "definition_digest": digest,
            "allowlisted": self._allowlisted(argv),
            "timeout": timeout,
        }
        if cwd is None:
            return REFUTED, evidence, "cwd escapes the repository root"
        if not os.path.isdir(cwd):
            return INCONCLUSIVE, evidence, "cwd is not a directory"
        if not self._allowlisted(argv):
            return (
                INCONCLUSIVE,
                evidence,
                "command is not allow-listed; refusing to execute "
                "(add it to .verdict/allowlist.json)",
            )
        exe = shutil.which(argv[0])
        evidence["resolved"] = exe
        if exe is None:
            return INCONCLUSIVE, evidence, f"{argv[0]!r} is not on PATH"

        started = time.time()
        try:
            proc = subprocess.run(
                argv, cwd=cwd, shell=False, timeout=timeout, capture_output=True
            )
        except subprocess.TimeoutExpired:
            return INCONCLUSIVE, evidence, f"timed out after {timeout}s"
        except OSError as exc:
            return INCONCLUSIVE, evidence, f"could not execute: {exc}"
        out = proc.stdout.decode("utf-8", "replace")
        err = proc.stderr.decode("utf-8", "replace")
        evidence.update(
            {
                "exit_code": proc.returncode,
                "duration_ms": int((time.time() - started) * 1000),
                "stdout_sha256": hashlib.sha256(out.encode()).hexdigest(),
                "stderr_sha256": hashlib.sha256(err.encode()).hexdigest(),
                "stdout_head": out[:400],
                "stderr_head": err[:400],
            }
        )
        if proc.returncode != want_exit:
            return REFUTED, evidence, f"exit {proc.returncode}, expected {want_exit}"
        want_out = p.get("expect_stdout")
        if want_out and not re.search(str(want_out), out):
            return REFUTED, evidence, f"stdout does not match /{want_out}/"
        return VERIFIED, evidence, f"exit {proc.returncode} in {evidence['duration_ms']}ms"

    def _check_diff_touches(self, p: Dict[str, Any]):
        """Claim: the git diff against ``base`` really touches these paths."""
        paths = p.get("paths")
        if paths is None and "path" in p:
            paths = [p["path"]]
        if not paths:
            raise ClaimError("diff_touches requires 'paths'")
        paths = [str(x) for x in paths]
        base = str(p.get("base", "HEAD"))
        mode = str(p.get("mode", "all"))
        git = shutil.which("git")
        evidence: Dict[str, Any] = {"claimed": paths, "base": base, "mode": mode}
        if git is None:
            return INCONCLUSIVE, evidence, "git is not available"
        try:
            proc = subprocess.run(
                [git, "-C", self.base_dir, "diff", "--name-only", base],
                shell=False,
                timeout=30,
                capture_output=True,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            return INCONCLUSIVE, evidence, f"git diff failed: {exc}"
        if proc.returncode != 0:
            evidence["stderr_head"] = proc.stderr.decode("utf-8", "replace")[:200]
            return INCONCLUSIVE, evidence, "git diff failed (not a repo, or bad base?)"

        changed = [l.strip() for l in proc.stdout.decode("utf-8", "replace").splitlines() if l.strip()]
        matched = [c for c in paths if _path_touched(c, changed)]
        missing = [c for c in paths if c not in matched]
        evidence.update({"changed_count": len(changed), "changed_sample": changed[:20],
                         "matched": matched, "missing": missing})
        if mode == "any":
            if matched:
                return VERIFIED, evidence, f"diff touches {len(matched)} of the claimed paths"
            return REFUTED, evidence, "diff touches none of the claimed paths"
        if missing:
            return REFUTED, evidence, f"claimed paths absent from the diff: {', '.join(missing)}"
        return VERIFIED, evidence, f"diff touches all {len(paths)} claimed path(s)"

    # -- density and anti-laziness gates -------------------------------------

    def _check_slop_density(self, p: Dict[str, Any]):
        """Claim: no paragraph hits >= min_hits distinct AI-tell patterns.

        A single "delve" is normal prose. Three different tells in one paragraph
        is what actually reads as generated. Hits are counted by pattern id, so
        several phrases from the same catalogue entry only count once.
        """
        preset = p.get("preset")
        if preset:
            entries = _load_slop_preset(str(preset))
        else:
            raw = p.get("patterns") or []
            entries = [{"id": f"P-{i}", "regex": str(x)} for i, x in enumerate(raw)]
        if not entries:
            raise ClaimError("slop_density needs 'preset' or a non-empty 'patterns' list")
        min_hits = int(p.get("min_hits", 3))
        if min_hits < 1:
            raise ClaimError("min_hits must be >= 1")

        compiled: List[Tuple[str, Any]] = []
        for e in entries:
            try:
                compiled.append((str(e.get("id", "?")), re.compile(str(e["regex"]), re.I)))
            except (re.error, KeyError) as exc:
                raise ClaimError(f"bad slop pattern {e.get('id', '?')}: {exc}")

        paragraphs = re.split(r"\n\s*\n", self._text())
        findings = []
        for i, para in enumerate(paragraphs):
            ids = sorted({pid for pid, rx in compiled if rx.search(para)})
            if ids:
                findings.append({
                    "index": i,
                    "hits": len(ids),
                    "ids": ids[:12],
                    "excerpt": para.strip()[:120],
                })
        worst = max((f["hits"] for f in findings), default=0)
        evidence: Dict[str, Any] = {
            "preset": str(preset) if preset else "custom",
            "patterns": len(compiled),
            "paragraphs": len(paragraphs),
            "min_hits": min_hits,
            "max_hits": worst,
            "findings": findings[:5],
        }
        if worst >= min_hits:
            return REFUTED, evidence, f"{worst} distinct AI-tell patterns in one paragraph (limit {min_hits})"
        return VERIFIED, evidence, f"max {worst} distinct patterns in a paragraph, below {min_hits}"

    def _check_tests_actually_prove(self, p: Dict[str, Any]):
        """Claim: tests were not made green by tampering or by going untouched.

        Red flags, from the git diff against ``base``: a deleted test file, a
        newly added skip/.only marker, or code changed with no test file changed.
        """
        base = str(p.get("base", "HEAD"))
        require = bool(p.get("require_test_change", True))
        globs = list(p.get("test_globs") or DEFAULT_TEST_GLOBS)
        git = shutil.which("git")
        evidence: Dict[str, Any] = {"base": base, "require_test_change": require}
        if git is None:
            return INCONCLUSIVE, evidence, "git is not available"

        def diff(*extra: str):
            return subprocess.run(
                [git, "-C", self.base_dir, "diff", *extra, base],
                shell=False, timeout=30, capture_output=True,
            )

        try:
            named = diff("--name-status")
            patch = diff("-U0")
        except (subprocess.TimeoutExpired, OSError) as exc:
            return INCONCLUSIVE, evidence, f"git diff failed: {exc}"
        if named.returncode != 0 or patch.returncode != 0:
            return INCONCLUSIVE, evidence, "git diff failed (not a repo, or bad base?)"

        changed: List[Tuple[str, str]] = []
        for line in named.stdout.decode("utf-8", "replace").splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                changed.append((parts[0].strip(), parts[-1].strip()))
        deleted_tests = [f for s, f in changed if s.startswith("D") and _is_test_path(f, globs)]
        tests_changed = [f for s, f in changed if not s.startswith("D") and _is_test_path(f, globs)]
        code_changed = [f for s, f in changed if not _is_test_path(f, globs)]
        skip_hits = [
            {"line": m.group(1).strip()[:120]}
            for m in re.finditer(r"^\+(?!\+\+)(.*)$", patch.stdout.decode("utf-8", "replace"), re.M)
            if SKIP_MARKERS.search(m.group(1))
        ]
        evidence.update({
            "changed_count": len(changed),
            "code_changed": code_changed[:20],
            "tests_changed": tests_changed[:20],
            "deleted_tests": deleted_tests,
            "skip_markers": skip_hits[:10],
        })
        if not changed:
            return INCONCLUSIVE, evidence, "nothing changed against the base ref"

        flags = []
        if deleted_tests:
            flags.append(f"deleted test file(s): {', '.join(deleted_tests)}")
        if skip_hits:
            flags.append(f"{len(skip_hits)} new skip/.only marker(s) in the diff")
        if require and code_changed and not tests_changed:
            flags.append("code changed with no test file changed")
        if flags:
            return REFUTED, evidence, "; ".join(flags)
        return VERIFIED, evidence, f"{len(tests_changed)} test file(s) changed, no tampering markers"

    # -- scoring ------------------------------------------------------------

    def verify_all(
        self,
        claims: List[Claim],
        facts: Optional[Dict[str, Any]] = None,
        min_information: float = 1.0,
    ) -> Dict[str, Any]:
        report = super().verify_all(claims, facts=facts, min_information=min_information)
        return rescore(report, min_information=min_information, overrides=self.weight_overrides)


def gate_weight(result: Dict[str, Any], overrides: Optional[Dict[str, float]] = None) -> float:
    """verdict's own weight table for the kinds it owns."""
    kind = result["kind"]
    p = result.get("params", {}) or {}
    ev = result.get("evidence", {}) or {}
    if ev.get("self_referential"):
        return 0.0
    base = float((overrides or {}).get(kind, _GATE_WEIGHTS.get(kind, 0.3)))
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


def rescore(
    report: Dict[str, Any],
    min_information: float = 1.0,
    overrides: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Re-apply verdict's weights to the gate kinds and refresh the summary."""
    results = report.get("results", [])
    for r in results:
        if r["kind"] not in TEXT_KINDS:
            continue
        if r["verdict"] in _SCORE_PENALTY or r.get("duplicate") or r.get("trivial") or r.get("echoed") or r.get("known"):
            r["weight"] = 0.0
        else:
            r["weight"] = gate_weight(r, overrides)

    # Marginal decay inside a kind. Without it, a 33-claim bundle that all pass
    # scores as "informative" no matter how little it actually said — the exact
    # gaming the information metric exists to prevent. The Nth claim of a kind
    # counts for 1/N (harmonic): 10 claims of a kind score like ~3, not like 10.
    seen: Dict[str, int] = {}
    for r in sorted(results, key=lambda x: -(x.get("weight") or 0.0)):
        # Only VERIFIED claims decay: a REFUTED claim keeps its full weight so a
        # failure still reads as "this rule matters", not as a small number.
        if r["kind"] not in TEXT_KINDS or not r["weight"] or r["verdict"] != VERIFIED:
            continue
        i = seen.get(r["kind"], 0)
        seen[r["kind"]] = i + 1
        r["weight_raw"] = r["weight"]
        r["weight"] = round(r["weight"] / (i + 1), 3)

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
