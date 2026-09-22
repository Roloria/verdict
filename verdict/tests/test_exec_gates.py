"""Tests for the execution gates: command_succeeds and diff_touches.

These are the gates that can run code, so the tests are mostly about what they
refuse to do.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from reverify.verifier import INCONCLUSIVE, REFUTED, VERIFIED, Claim

from verdict.verifier import GateVerifier


def run(claims, data: bytes = b"x", base_dir: str = ".", allowlist=None, min_information: float = 0.0):
    v = GateVerifier(data, base_dir=base_dir, allowlist=allowlist)
    return v.verify_all([Claim.from_dict(c) for c in claims], min_information=min_information)


PY = [sys.executable, "-c"]


def test_command_succeeds_verified_and_refuted():
    rep = run(
        [
            {"kind": "command_succeeds", "argv": [*PY, "print('ok')"]},
            {"kind": "command_succeeds", "argv": [*PY, "import sys; sys.exit(3)"]},
        ],
        allowlist=[PY],
    )
    verdicts = [r["verdict"] for r in rep["results"]]
    assert verdicts == [VERIFIED, REFUTED]
    assert rep["results"][0]["evidence"]["exit_code"] == 0
    assert rep["results"][0]["evidence"]["stdout_sha256"]
    assert "exit 3" in rep["results"][1]["detail"]


def test_command_not_allowlisted_is_never_executed():
    rep = run(
        [{"kind": "command_succeeds", "argv": ["rm", "-rf", "should-never-run"]}],
        allowlist=[PY],
    )
    r = rep["results"][0]
    assert r["verdict"] == INCONCLUSIVE
    assert "not allow-listed" in r["detail"]
    assert "exit_code" not in r["evidence"]  # proof it did not run


def test_command_rejects_shell_strings():
    rep = run([{"kind": "command_succeeds", "argv": "pytest && rm -rf /"}], allowlist=[PY])
    assert rep["results"][0]["verdict"] == INCONCLUSIVE
    assert "no shell strings" in rep["results"][0]["detail"]


def test_command_expect_stdout_regex():
    rep = run(
        [
            {"kind": "command_succeeds", "argv": [*PY, "print('3 passed')"], "expect_stdout": r"\d+ passed"},
            {"kind": "command_succeeds", "argv": [*PY, "print('0 passed')"], "expect_stdout": r"[1-9]\d* passed"},
        ],
        allowlist=[PY],
    )
    assert [r["verdict"] for r in rep["results"]] == [VERIFIED, REFUTED]


def test_command_cwd_must_stay_inside_the_repo(tmp_path):
    rep = run(
        [{"kind": "command_succeeds", "argv": [*PY, "print(1)"], "cwd": "../.."}],
        base_dir=str(tmp_path),
        allowlist=[PY],
    )
    assert rep["results"][0]["verdict"] == REFUTED
    assert "escapes" in rep["results"][0]["detail"]


def test_default_allowlist_blocks_arbitrary_commands():
    rep = run([{"kind": "command_succeeds", "argv": ["curl", "http://example.com"]}])
    assert rep["results"][0]["verdict"] == INCONCLUSIVE


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def test_diff_touches_verified_refuted_and_directory(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "test")
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("v1\n", encoding="utf-8")
    (src / "other.py").write_text("v1\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    (src / "app.py").write_text("v2\n", encoding="utf-8")  # the change under test

    rep = run(
        [
            {"kind": "diff_touches", "paths": ["src/app.py"], "base": "HEAD"},
            {"kind": "diff_touches", "paths": ["src/other.py"], "base": "HEAD"},
            {"kind": "diff_touches", "paths": ["src"], "base": "HEAD"},
            {"kind": "diff_touches", "paths": ["src/other.py"], "base": "HEAD", "mode": "any"},
        ],
        base_dir=str(tmp_path),
    )
    verdicts = [r["verdict"] for r in rep["results"]]
    assert verdicts == [VERIFIED, REFUTED, VERIFIED, REFUTED]


def test_diff_touches_outside_a_repo_is_inconclusive(tmp_path):
    rep = run([{"kind": "diff_touches", "paths": ["x.py"]}], base_dir=str(tmp_path))
    assert rep["results"][0]["verdict"] == INCONCLUSIVE


def test_ledger_records_the_run(tmp_path):
    from verdict import cli as verdict_cli

    target = tmp_path / "report.md"
    target.write_text("31 files changed\n", encoding="utf-8")
    claims = tmp_path / "claims.json"
    claims.write_text(json.dumps([{"kind": "text_present", "value": "31 files"}]), encoding="utf-8")
    ledger = tmp_path / ".verdict" / "ledger.jsonl"

    import sys as _sys
    argv = _sys.argv
    try:
        _sys.argv = [
            "verdict", "check", str(target), "--claims-file", str(claims),
            "--base-dir", str(tmp_path), "--ledger", str(ledger), "--min-information", "0.2",
        ]
        try:
            verdict_cli.main()
            code = 0
        except SystemExit as exc:
            code = exc.code
    finally:
        _sys.argv = argv

    assert code == 0
    lines = ledger.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["verified"] == 1 and record["exit"] == 0
    assert record["target_sha256"]


def test_fail_on_selects_what_breaks_the_build(tmp_path):
    from verdict import cli as verdict_cli

    target = tmp_path / "report.md"
    target.write_text("31 files changed\n", encoding="utf-8")
    claims = tmp_path / "claims.json"
    claims.write_text(json.dumps([{"kind": "text_present", "value": "31 files"}]), encoding="utf-8")

    def code_for(extra):
        argv = ["verdict", "check", str(target), "--claims-file", str(claims),
                "--base-dir", str(tmp_path), "--no-ledger", *extra]
        old = sys.argv
        try:
            sys.argv = argv
            try:
                verdict_cli.main()
                return 0
            except SystemExit as exc:
                return exc.code
        finally:
            sys.argv = old

    # thin evidence: fails by default, passes when thin is not selected
    assert code_for(["--min-information", "99"]) == 3
    assert code_for(["--min-information", "99", "--fail-on", "refuted"]) == 0
