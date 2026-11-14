"""Deterministically turn an AI artifact into a DRAFT claim set.

This is the missing half of reverify's "model proposes, tools decide" protocol:
the *agent* used to have to hand-write claims.json. propose extracts only
assertions that can be bound to EXTERNAL evidence:

  path:line reference  -> citation_resolves   (evidence: the observed line)
  repo-relative path   -> file_exists         (evidence: filesystem)
  allow-listed command -> command_succeeds    (evidence: exit code)
  "tests pass" claim   -> tests_actually_prove / command_succeeds
  "no secrets" claim   -> text_absent         (evidence: the text)

Numbers, percentages and "we improved X" are DELIBERATELY skipped: asserting
that a document contains its own number is self-referential and says nothing.
They need a named source file (a future `number_matches_source` gate), which a
deterministic extractor cannot guess.

No LLM, no network, no filesystem reads — the same text always yields the same
draft. Generated claims are a starting point, not a verdict.
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Sequence, Tuple

from .verifier import CITATION_RE, DEFAULT_ALLOWLIST

KNOWN_EXTS = {
    ".md", ".mdx", ".rst", ".txt", ".py", ".ts", ".tsx", ".js", ".jsx",
    ".json", ".yml", ".yaml", ".toml", ".sh", ".go", ".rs", ".java", ".rb",
    ".html", ".css", ".sql", ".c", ".h", ".cpp", ".svg", ".png", ".jpg",
    ".lock", ".cfg", ".ini", ".env",
}
KNOWN_NAMES = {"README", "CHANGELOG", "LICENSE", "Makefile", "Dockerfile", "SKILL"}
PATH_RE = re.compile(r"(?<![\w@./-])([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\.[A-Za-z0-9]{1,8})(?![\w])")
CODE_SPAN = re.compile(r"`([^`\n]{2,100})`")
CMD_LINE = re.compile(r"^\s*\$\s+(.+)$", re.M)
NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:files|seconds|ms|%|points|cases|tests|次|个|秒|毫秒)\b")
TESTS_ASSERTION = re.compile(
    r"\b(?:all )?tests (?:pass|passed|are green)\b|\btest suite (?:is green|passes)\b|"
    r"测试(?:全部|已)?通过|全部通过|用例全部通过", re.I,
)
SECRETS_ASSERTION = re.compile(r"\bno (?:secrets?|credentials?|keys?)\b|无密钥|没有密钥|不含密钥", re.I)
MAX_CLAIMS = 40

SECRET_PATTERN = "".join(["sk-", "[A-Za-z0-9]{20,}"])


def _is_path(candidate: str) -> bool:
    if candidate.startswith(("http://", "https://", "www.")):
        return False
    if "://" in candidate or ".." in candidate or candidate.startswith("/"):
        return False
    base = candidate.rsplit("/", 1)[-1]
    if "." in base:
        ext = "." + base.rsplit(".", 1)[-1].lower()
        return ext in KNOWN_EXTS
    return base in KNOWN_NAMES


def _allowlisted(argv: List[str]) -> bool:
    return any(argv[: len(entry)] == list(entry) for entry in DEFAULT_ALLOWLIST)


def _commands(text: str) -> List[List[str]]:
    out: List[List[str]] = []
    candidates = [m.group(1).strip() for m in CODE_SPAN.finditer(text)]
    candidates += [m.group(1).strip() for m in CMD_LINE.finditer(text)]
    for raw in candidates:
        argv = raw.split()
        if not argv or not _allowlisted(argv):
            continue
        if argv not in out:
            out.append(argv)
    return out


def build_claims(text: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """Return (claims, skipped) — pure and deterministic."""
    claims: List[Dict[str, Any]] = []
    skipped: List[Dict[str, str]] = []
    seen: set[str] = set()

    def add(claim: Dict[str, Any]) -> None:
        key = repr(sorted(claim.items(), key=lambda kv: kv[0]))
        if key not in seen and len(claims) < MAX_CLAIMS:
            seen.add(key)
            claims.append(claim)

    # 1. explicit path:line references -> one citation_resolves claim
    citations = []
    for m in CITATION_RE.finditer(text):
        item = {"path": m.group(1), "line": int(m.group(2))}
        if item not in citations:
            citations.append(item)
    if citations:
        add({"kind": "citation_resolves", "from_text": False,
             "citations": citations[:25], "note": "proposed: references really resolve"})

    # 2. repo-relative paths -> file_exists
    for m in PATH_RE.finditer(text):
        candidate = m.group(1)
        if not _is_path(candidate):
            continue
        if any(c["path"] == candidate for c in citations):
            continue
        add({"kind": "file_exists", "path": candidate, "min_bytes": 1,
             "note": "proposed: the claimed file exists"})

    # 3. allow-listed commands -> command_succeeds
    for argv in _commands(text):
        add({"kind": "command_succeeds", "argv": argv, "timeout": 300,
             "note": "proposed: the command really exits 0"})

    # 4. explicit prose assertions
    if TESTS_ASSERTION.search(text):
        add({"kind": "tests_actually_prove", "base": "HEAD",
             "note": "proposed: tests were not skipped or ignored"})
    if SECRETS_ASSERTION.search(text):
        add({"kind": "text_absent", "pattern": SECRET_PATTERN, "regex": True,
             "note": "proposed: no credential-shaped strings"})

    numbers = NUMBER_RE.findall(text)
    if numbers:
        skipped.append({
            "kind": "number_matches_source",
            "reason": f"{len(numbers)} numeric statement(s) are self-referential; bind them to a named source file manually",
        })
    for m in re.finditer(r"https?://[^\s)>\]]+", text):
        skipped.append({"kind": "url_resolves", "reason": f"URL {m.group(0)[:60]} needs a network verifier"})
    return claims, skipped


def propose(text: str, source: str = "") -> Dict[str, Any]:
    claims, skipped = build_claims(text)
    return {
        "type": "verdict-proposed-claims",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": source,
        "claims": claims,
        "skipped": skipped,
        "note": "Draft only. Review before gating: a proposed claim is not a verified claim.",
    }
