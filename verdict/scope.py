"""Deterministic review scope, adapted from open-code-review's pre-dispatch layer.

Design borrowed (not code — that project is Apache-2.0, this one is MIT):
  * one PURE selection pass whose per-file decision is shared by preview and
    the real run, so the two cannot drift (OCR's #782)
  * static gates applied in a fixed order: secret path → binary → user exclude
    → generated/test/lock patterns → deletion → size
  * per-file rule resolution grouped by (source, pattern, rules), so a group's
    provenance is accurate for every file in it
  * deterministic bundling: pair implementation with its tests, pair i18n
    siblings, then group the rest by directory, capped per bundle
  * a structured delegate spec that hands a host agent the scope WITHOUT
    calling any model

verdict keeps no LLM in the verify path. This module produces claims/evidence,
never opinions.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Inspired by OCR's default_exclude_patterns.json, rewritten here deliberately
# smaller and MIT-clean. Generated code, lockfiles, build output and test files
# are noise for a *source* review scope — but note tests_actually_prove still
# looks at test files, so selection is about attention, not about ignoring them.
DEFAULT_EXCLUDES = (
    "**/node_modules/**", "**/.git/**", "**/dist/**", "**/build/**",
    "**/.next/**", "**/.venv/**", "**/__pycache__/**", "**/*.egg-info/**",
    "**/vendor/**", "**/testdata/**", "**/fixtures/**", "**/__snapshots__/**",
    "**/*.snap", "**/*.min.js", "**/*.min.css", "**/*.map",
    "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock",
    "**/*.generated.*", "**/*.gen.*", "**/*.pb.go", "**/*.pb.cc", "**/*.pb.h",
    "test_*.py", "*_test.py", "*.test.ts", "*.spec.ts", "*.test.js", "*.spec.js",
    "*_test.go", "*Test.java", "*Tests.java", "*_test.rs", "*_spec.rb",
    "**/tests/**", "**/test/**", "**/__tests__/**",
)
SECRET_PATH_MARKERS = (
    ".env", ".npmrc", ".pypirc", "id_rsa", "id_ed25519", ".aws/credentials",
    "secrets.", "credentials.json", "service-account",
)
SECRET_PATH_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".keystore")
BINARY_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz",
    ".tar", ".woff", ".woff2", ".ttf", ".so", ".dll", ".dylib", ".exe", ".bin",
    ".pyc", ".wasm", ".mp4", ".mp3",
)
TEXT_EXT_RULES = {
    ".md": ["ai-tells-density"],
    ".mdx": ["ai-tells-density"],
    ".rst": ["ai-tells-density"],
    ".txt": ["ai-tells-density"],
    ".py": ["secrets-pii"],
    ".ts": ["secrets-pii"],
    ".tsx": ["secrets-pii"],
    ".js": ["secrets-pii"],
    ".jsx": ["secrets-pii"],
    ".go": ["secrets-pii"],
    ".java": ["secrets-pii"],
    ".rb": ["secrets-pii"],
    ".rs": ["secrets-pii"],
    ".yml": ["secrets-pii"],
    ".yaml": ["secrets-pii"],
    ".json": ["secrets-pii"],
}
MAX_FILE_BYTES = 1024 * 1024
MAX_FILES_PER_BUNDLE = 10

OK = "ok"
EXCLUDE_SECRET = "secret-path"
EXCLUDE_BINARY = "binary"
EXCLUDE_USER = "user-exclude"
EXCLUDE_DEFAULT = "default-exclude"
EXCLUDE_DELETED = "deleted"
EXCLUDE_TOO_LARGE = "too-large"


@dataclass
class Change:
    path: str
    status: str = "M"
    is_binary: bool = False

    @property
    def is_deleted(self) -> bool:
        return self.status.startswith("D")


@dataclass
class Decision:
    path: str
    selected: bool
    reason: str
    status: str = "M"

    def as_dict(self) -> Dict[str, Any]:
        return {"path": self.path, "selected": self.selected, "reason": self.reason, "status": self.status}


@dataclass
class RuleGroup:
    source: str
    pattern: str
    rules: List[str] = field(default_factory=list)
    files: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {"source": self.source, "pattern": self.pattern, "rules": self.rules, "files": self.files}


def glob_to_regex(glob: str) -> re.Pattern:
    """Small, predictable glob: ** crosses directories, * does not."""
    out, i = [], 0
    while i < len(glob):
        c = glob[i]
        if c == "*":
            if i + 1 < len(glob) and glob[i + 1] == "*":
                # "**/" matches zero or more directory levels, so
                # src/**/*.py also matches src/app.py.
                if i + 2 < len(glob) and glob[i + 2] == "/":
                    out.append("(?:.*/)?")
                    i += 3
                    continue
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
        else:
            out.append(re.escape(c))
        i += 1
    return re.compile("^" + "".join(out) + "$")


def _git(base_dir: str, *args: str) -> str:
    exe = shutil.which("git")
    if exe is None:
        raise RuntimeError("git is not available")
    proc = subprocess.run(
        [exe, "-C", base_dir, *args], shell=False, timeout=30, capture_output=True
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.decode('utf-8', 'replace').strip()[:200]}")
    return proc.stdout.decode("utf-8", "replace")


def collect_changes(
    base_dir: str = ".",
    mode: str = "workspace",
    base: str = "HEAD",
    to: str = "HEAD",
    commit: str = "",
) -> List[Change]:
    """One deterministic change set. Modes: workspace | merge-base | commit | base."""
    out: List[Change] = []
    if mode == "workspace":
        for line in _git(base_dir, "status", "--porcelain=v1").splitlines():
            if len(line) < 4:
                continue
            code, path = line[:2], line[3:].strip()
            if " -> " in path:  # rename
                path = path.split(" -> ", 1)[1]
            status = "D" if "D" in code else ("A" if "?" in code or "A" in code else "M")
            out.append(Change(path, status))
    elif mode == "merge-base":
        sha = _git(base_dir, "merge-base", base, to).strip().splitlines()[-1]
        out = _parse_name_status(_git(base_dir, "diff", "--name-status", sha))
    elif mode == "commit":
        out = _parse_name_status(_git(base_dir, "show", "--name-status", "--format=", commit or base))
    elif mode == "base":
        out = _parse_name_status(_git(base_dir, "diff", "--name-status", base))
    else:
        raise ValueError(f"unknown mode {mode!r} (workspace|merge-base|commit|base)")
    for c in out:
        c.is_binary = os.path.splitext(c.path)[1].lower() in BINARY_SUFFIXES
    return sorted({c.path: c for c in out}.values(), key=lambda c: c.path)


def _parse_name_status(text: str) -> List[Change]:
    out = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            out.append(Change(parts[-1].strip(), parts[0].strip()[:1]))
    return out


def decide(change: Change, base_dir: str = ".", user_excludes: Sequence[str] = ()) -> Decision:
    """Pure per-file decision, applied in a fixed order. No IO except file size."""
    path = change.path.replace("\\", "/")
    lower = path.lower()
    reason = OK
    if any(m in lower for m in SECRET_PATH_MARKERS) or lower.endswith(SECRET_PATH_SUFFIXES):
        reason = EXCLUDE_SECRET
    elif change.is_binary or os.path.splitext(path)[1].lower() in BINARY_SUFFIXES:
        reason = EXCLUDE_BINARY
    elif any(glob_to_regex(g).match(path) or glob_to_regex(g).match(os.path.basename(path)) for g in user_excludes):
        reason = EXCLUDE_USER
    elif any(glob_to_regex(g).match(path) or glob_to_regex(g).match(os.path.basename(path)) for g in DEFAULT_EXCLUDES):
        reason = EXCLUDE_DEFAULT
    elif change.is_deleted:
        reason = EXCLUDE_DELETED
    else:
        full = os.path.join(base_dir, path)
        if os.path.isfile(full) and os.path.getsize(full) > MAX_FILE_BYTES:
            reason = EXCLUDE_TOO_LARGE
    return Decision(path, reason == OK, reason, change.status)


def load_scope_rules(base_dir: str = ".") -> List[Dict[str, Any]]:
    """Optional .verdict/scope-rules.json: per-file glob → rule bundles."""
    path = os.path.join(base_dir, ".verdict", "scope-rules.json")
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    return list(doc.get("rules") or [])


def resolve_rules(paths: Sequence[str], base_dir: str = ".") -> List[RuleGroup]:
    """Group files by (source, pattern, rules), mirroring OCR's RuleGroup."""
    configured = load_scope_rules(base_dir)
    groups: Dict[Tuple[str, str, Tuple[str, ...]], RuleGroup] = {}
    for path in paths:
        source, pattern, rules = "system", "default", TEXT_EXT_RULES.get(os.path.splitext(path)[1].lower(), [])
        for entry in configured:
            if glob_to_regex(str(entry.get("pattern", ""))).match(path):
                source, pattern = "project", str(entry["pattern"])
                rules = [str(r) for r in entry.get("rules") or []]
                break
        key = (source, pattern, tuple(rules))
        groups.setdefault(key, RuleGroup(source, pattern, list(rules))).files.append(path)
    return sorted(groups.values(), key=lambda g: (g.source, g.pattern))


def _test_partner(path: str) -> Optional[str]:
    """Deterministic implementation ↔ test pairing, no model involved."""
    d, name = os.path.split(path)
    stem, ext = os.path.splitext(name)
    candidates = []
    if stem.startswith("test_"):
        candidates = [f"{stem[5:]}{ext}", os.path.join(d, f"{stem[5:]}{ext}")]
    elif stem.endswith("_test"):
        candidates = [f"{stem[:-5]}{ext}", os.path.join(d, f"{stem[:-5]}{ext}")]
    elif ".test." in name or ".spec." in name:
        base = re.sub(r"\.(test|spec)\.", ".", name)
        candidates = [os.path.join(d, base)]
    else:
        candidates = [
            os.path.join(d, f"test_{stem}{ext}"), os.path.join(d, f"{stem}_test{ext}"),
            os.path.join(d, f"{stem}.test{ext}"), os.path.join(d, f"{stem}.spec{ext}"),
        ]
        m = re.match(r"^(.*_)(en|zh|ja|ko|ru)(\.\w+)$", name)
        if m:
            candidates += [os.path.join(d, f"{m.group(1)}{lang}{m.group(3)}")
                           for lang in ("en", "zh", "ja", "ko", "ru") if lang != m.group(2)]
    return candidates[0] if candidates else None


def bundle_changes(paths: Sequence[str]) -> List[Dict[str, Any]]:
    """Pair obvious siblings, then group the rest by directory, capped at 10."""
    remaining = sorted(set(paths))
    bundles: List[Dict[str, Any]] = []
    used: set[str] = set()
    for path in remaining:
        if path in used:
            continue
        partner = _test_partner(path)
        if partner and partner in remaining and partner not in used:
            used.update({path, partner})
            bundles.append({"label": f"pair: {os.path.basename(path)}", "files": sorted([path, partner])})
    rest = [p for p in remaining if p not in used]
    by_dir: Dict[str, List[str]] = {}
    for path in rest:
        by_dir.setdefault(os.path.dirname(path) or ".", []).append(path)
    for d in sorted(by_dir):
        files = sorted(by_dir[d])
        for i in range(0, len(files), MAX_FILES_PER_BUNDLE):
            chunk = files[i:i + MAX_FILES_PER_BUNDLE]
            bundles.append({"label": d, "files": chunk})
    return bundles


def build_scope(
    base_dir: str = ".",
    mode: str = "workspace",
    base: str = "HEAD",
    to: str = "HEAD",
    commit: str = "",
    user_excludes: Sequence[str] = (),
) -> Dict[str, Any]:
    """One pure selection pass shared by `verdict scope` and every gate that
    consumes it — preview and real run cannot disagree."""
    changes = collect_changes(base_dir, mode, base, to, commit)
    decisions = [decide(c, base_dir, user_excludes) for c in changes]
    selected = [d.path for d in decisions if d.selected]
    return {
        "type": "verdict-scope",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base_dir": os.path.realpath(base_dir),
        "mode": mode,
        "base": base,
        "to": to,
        "commit": commit,
        "changed": len(changes),
        "selected_count": len(selected),
        "excluded_count": len(decisions) - len(selected),
        "decisions": [d.as_dict() for d in decisions],
        "selected": selected,
        "rule_groups": [g.as_dict() for g in resolve_rules(selected, base_dir)],
        "bundles": bundle_changes(selected),
    }


def delegate_spec(scope: Dict[str, Any]) -> Dict[str, Any]:
    """Structured hand-off for a host agent. No model is called here."""
    return {
        "type": "verdict-delegate-spec",
        "generated": scope["generated"],
        "mode": scope["mode"],
        "instructions": (
            "For each bundle below, read the listed files and write claims as JSON. "
            "Then run: verdict check <bundle-file> --claims-file <claims.json>. "
            "Do not assert anything you did not check. A claim that cannot be "
            "checked is INCONCLUSIVE, never VERIFIED."
        ),
        "bundles": [
            {
                "label": b["label"],
                "files": b["files"],
                "rules": next((g["rules"] for g in scope["rule_groups"] if any(f in g["files"] for f in b["files"])), []),
            }
            for b in scope["bundles"]
        ],
        "excluded": [
            {"path": d["path"], "reason": d["reason"]}
            for d in scope["decisions"] if not d["selected"]
        ],
        "replay": f"verdict scope --mode {scope['mode']} --base {scope['base']} --json",
    }
