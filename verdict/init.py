"""Zero-config onboarding for a new repository.

`verdict init` writes a working .verdict/ setup, detects the project's test
command, and drops in a CI workflow. It never overwrites existing files unless
--force is given, and it never modifies .git/ (a pre-commit hook is offered as
a script the user installs explicitly).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .i18n import t
from .verifier import DEFAULT_ALLOWLIST

WORKFLOW = """name: verdict gate

on:
  push:
    branches: [main]
  pull_request:

jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python -m pip install ai-verdict
      - name: gate docs and reports
        run: verdict check README.md --claims-file .verdict/claims.json --base-dir . --no-ledger
      - name: upload SARIF
        if: always()
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: verdict.sarif
        continue-on-error: true
"""

HOOK = """#!/bin/sh
# Install with: cp .verdict/pre-commit.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
set -e
verdict check README.md --claims-file .verdict/claims.json --base-dir . --no-ledger
"""


def detect_test_command(base_dir: str) -> Tuple[List[str], List[List[str]]]:
    """Return (test argv or [], extra allowlist entries)."""
    p = Path(base_dir)
    if (p / "pyproject.toml").is_file() or (p / "pytest.ini").is_file() or (p / "requirements.txt").is_file():
        return ["pytest", "-q"], [["pytest"]]
    if (p / "package.json").is_file():
        return ["npm", "test"], [["npm", "test"]]
    if (p / "Cargo.toml").is_file():
        return ["cargo", "test"], [["cargo", "test"]]
    if (p / "go.mod").is_file():
        return ["go", "test", "./..."], [["go", "test"]]
    return [], []


def starter_claims(test_argv: List[str]) -> List[Dict[str, Any]]:
    claims: List[Dict[str, Any]] = [
        {"kind": "slop_density", "preset": "slop-120", "min_hits": 3, "note": "AI 味密度"},
        {"kind": "text_absent", "pattern": "".join(["sk-", "[A-Za-z0-9]{20,}"]),
         "regex": True, "note": "no credential-shaped strings"},
        {"kind": "file_exists", "path": "README.md", "min_bytes": 20, "note": "docs present"},
    ]
    if test_argv:
        claims.append({"kind": "command_succeeds", "argv": test_argv, "timeout": 300,
                       "note": "detected test command"})
    return claims


def initialize(base_dir: str = ".", lang: str = "zh-CN", force: bool = False) -> Dict[str, Any]:
    root = Path(base_dir).resolve()
    vdir = root / ".verdict"
    vdir.mkdir(parents=True, exist_ok=True)
    test_argv, extra_allow = detect_test_command(str(root))
    allow = [list(a) for a in DEFAULT_ALLOWLIST] + extra_allow

    files: Dict[str, Any] = {
        ".verdict/config.json": {"lang": lang},
        ".verdict/claims.json": starter_claims(test_argv),
        ".verdict/allowlist.json": {"allow": allow},
        ".verdict/scope-rules.json": {
            "rules": [{"pattern": "src/**/*", "rules": ["secrets-pii"]}]
        },
    }
    text_files = {
        ".github/workflows/verdict.yml": WORKFLOW,
        ".verdict/pre-commit.sh": HOOK,
    }

    created, skipped = [], []
    for rel, payload in files.items():
        path = root / rel
        if path.exists() and not force:
            skipped.append(rel)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        created.append(rel)
    for rel, payload in text_files.items():
        path = root / rel
        if path.exists() and not force:
            skipped.append(rel)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
        created.append(rel)

    return {
        "base_dir": str(root),
        "lang": lang,
        "test_command": test_argv,
        "created": created,
        "skipped": skipped,
        "next": ["verdict check README.md --claims-file .verdict/claims.json",
                 "verdict scope --mode workspace --json"],
    }


def print_init(result: Dict[str, Any]) -> None:
    for rel in result["created"]:
        print(t("init.created", path=rel))
    for rel in result["skipped"]:
        print(t("init.skipped", path=rel))
    print(t("init.detected", command=" ".join(result["test_command"]) or "-"))
    print(t("init.next", first=result["next"][0]))
