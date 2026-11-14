"""Tests for deterministic claim proposal and release preflight."""

from __future__ import annotations

import json
import sys

from reverify.verifier import Claim

from verdict import cli as verdict_cli
from verdict.propose import build_claims, propose
from verdict.release import preflight
from verdict.verifier import GateVerifier

SAMPLE = """# Report

See src/app.py:12 for the fix and README.md for setup.
Run `pytest -q` to check. All tests pass and there are no secrets.
We rewrote 31 files in 4.2 seconds (https://example.com/changelog).
"""


def test_propose_binds_only_external_evidence():
    claims, skipped = build_claims(SAMPLE)
    kinds = [c["kind"] for c in claims]
    assert "citation_resolves" in kinds
    assert any(c["kind"] == "file_exists" and c["path"] == "README.md" for c in claims)
    assert any(c["kind"] == "command_succeeds" and c["argv"] == ["pytest", "-q"] for c in claims)
    assert "tests_actually_prove" in kinds
    assert any(c["kind"] == "text_absent" for c in claims)
    # numbers are deliberately NOT claims: asserting a doc contains its own
    # number is self-referential
    assert not any(c["kind"] == "text_present" for c in claims)
    assert any(s["kind"] == "number_matches_source" for s in skipped)


def test_propose_is_deterministic_and_url_safe():
    a, b = propose(SAMPLE, "r.md"), propose(SAMPLE, "r.md")
    for doc in (a, b):
        doc.pop("generated")
    assert a == b
    assert not any("example.com" in c.get("path", "") for c in a["claims"] if c["kind"] == "file_exists")
    assert all(not s["reason"].endswith(").") for s in a["skipped"])


def test_proposed_claims_are_consumable(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x = 1\n" * 15, encoding="utf-8")
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    doc = propose("See src/app.py:3 and README.md.\n", "r.md")
    rep = GateVerifier(b"x", base_dir=str(tmp_path)).verify_all(
        [Claim.from_dict(c) for c in doc["claims"]], min_information=0.0
    )
    assert rep["total_claims"] == 2
    assert rep["refuted"] == 0  # both resolve in this fixture


def test_cli_propose_writes_claims_file(tmp_path, monkeypatch, capsys):
    target = tmp_path / "report.md"
    target.write_text("See README.md. Run `pytest -q`.\n", encoding="utf-8")
    out = tmp_path / "claims.json"
    monkeypatch.setattr(sys, "argv", ["verdict", "propose", str(target), "--out", str(out), "--lang", "en"])
    verdict_cli.main()
    printed = capsys.readouterr().out
    assert "extracted" in printed and "draft written" in printed
    claims = json.loads(out.read_text(encoding="utf-8"))
    assert isinstance(claims, list) and any(c["kind"] == "file_exists" for c in claims)


def test_cli_propose_json_without_out(tmp_path, monkeypatch, capsys):
    target = tmp_path / "report.md"
    target.write_text("See README.md.\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["verdict", "propose", str(target)])
    verdict_cli.main()
    doc = json.loads(capsys.readouterr().out)
    assert doc["type"] == "verdict-proposed-claims"


def test_cli_propose_empty_draft_points_to_rules(tmp_path, monkeypatch, capsys):
    target = tmp_path / "report.md"
    target.write_text("We rewrote 31 files in 4.2 seconds.\n", encoding="utf-8")
    out = tmp_path / "claims.json"
    monkeypatch.setattr(sys, "argv", ["verdict", "propose", str(target), "--out", str(out), "--lang", "en"])
    verdict_cli.main()
    printed = capsys.readouterr().out
    assert "extracted 0" in printed
    assert "no externally-verifiable claims" in printed
    assert "--rules ai-tells-density" in printed
    assert json.loads(out.read_text(encoding="utf-8")) == []


def test_release_preflight_offline(tmp_path, capsys):
    result = preflight(str(tmp_path), check_pypi=False)
    assert "checks" in result and "todo" in result
    assert isinstance(result["ready"], bool)


def test_cli_release_check_reports_unfinished_publishing(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(sys, "argv", ["verdict", "release-check", "--base-dir", str(tmp_path),
                                     "--offline", "--lang", "en"])
    try:
        verdict_cli.main()
        code = 0
    except SystemExit as exc:
        code = exc.code
    out = capsys.readouterr().out
    assert "release preflight" in out
    assert code == 1  # nothing is published yet
