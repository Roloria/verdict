"""Tests for zero-config onboarding and SARIF export."""

from __future__ import annotations

import json
import sys

from reverify.verifier import Claim

from verdict import cli as verdict_cli
from verdict.init import detect_test_command, initialize, starter_claims
from verdict.sarif import build_sarif, write_sarif
from verdict.verifier import GateVerifier


def _report():
    claims = [
        {"kind": "text_present", "value": "31 files"},
        {"kind": "text_absent", "value": "31 files"},
    ]
    return GateVerifier(b"31 files changed\n").verify_all(
        [Claim.from_dict(c) for c in claims], min_information=0.0
    )


def test_init_creates_a_working_project(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    result = initialize(str(tmp_path), lang="zh-CN")
    assert len(result["created"]) == 6
    assert result["test_command"] == ["pytest", "-q"]
    for rel in result["created"]:
        assert (tmp_path / rel).is_file(), rel
    cfg = json.loads((tmp_path / ".verdict/config.json").read_text(encoding="utf-8"))
    assert cfg["lang"] == "zh-CN"
    claims = json.loads((tmp_path / ".verdict/claims.json").read_text(encoding="utf-8"))
    assert any(c["kind"] == "command_succeeds" and c["argv"] == ["pytest", "-q"] for c in claims)
    allow = json.loads((tmp_path / ".verdict/allowlist.json").read_text(encoding="utf-8"))
    assert ["pytest"] in allow["allow"]


def test_init_detects_other_stacks(tmp_path):
    assert detect_test_command(str(tmp_path)) == ([], [])
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    assert detect_test_command(str(tmp_path))[0] == ["npm", "test"]
    (tmp_path / "package.json").unlink()
    (tmp_path / "Cargo.toml").write_text("", encoding="utf-8")
    assert detect_test_command(str(tmp_path))[0] == ["cargo", "test"]


def test_init_does_not_overwrite_unless_forced(tmp_path):
    initialize(str(tmp_path))
    (tmp_path / ".verdict/config.json").write_text('{"lang":"en"}', encoding="utf-8")
    again = initialize(str(tmp_path), lang="en")
    assert ".verdict/config.json" in again["skipped"]
    assert json.loads((tmp_path / ".verdict/config.json").read_text(encoding="utf-8"))["lang"] == "en"
    forced = initialize(str(tmp_path), lang="zh-CN", force=True)
    assert ".verdict/config.json" in forced["created"]


def test_generated_claims_are_consumable(tmp_path):
    (tmp_path / "README.md").write_text("# Demo\nClean short doc.\n", encoding="utf-8")
    initialize(str(tmp_path))
    claims = json.loads((tmp_path / ".verdict/claims.json").read_text(encoding="utf-8"))
    rep = GateVerifier((tmp_path / "README.md").read_bytes(), base_dir=str(tmp_path)).verify_all(
        [Claim.from_dict(c) for c in claims], min_information=0.0
    )
    assert rep["refuted"] == 0  # starter config must not be red on a clean repo


def test_cli_init_lang_switch(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["verdict", "init", "--base-dir", str(tmp_path), "--lang", "en"])
    verdict_cli.main()
    out = capsys.readouterr().out
    assert "created" in out and "detected test command" in out


def test_sarif_structure():
    sarif = build_sarif(_report(), target="report.md")
    assert sarif["version"] == "2.1.0"
    run = sarif["runs"][0]
    assert run["tool"]["driver"]["name"] == "ai-verdict"
    assert len(run["results"]) == 1  # only the REFUTED claim
    finding = run["results"][0]
    assert finding["level"] == "error"
    assert finding["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "report.md"
    assert finding["partialFingerprints"]["verdictClaim"]
    assert len(run["tool"]["driver"]["rules"]) == 2


def test_sarif_marks_inconclusive_as_warning():
    rep = GateVerifier(b"x").verify_all(
        [Claim.from_dict({"kind": "quantum_vibe_check", "value": "x"})], min_information=0.0
    )
    finding = build_sarif(rep)["runs"][0]["results"][0]
    assert finding["level"] == "warning"


def test_cli_writes_sarif(tmp_path, monkeypatch, capsys):
    target = tmp_path / "r.md"
    target.write_text("31 files\n", encoding="utf-8")
    claims = tmp_path / "c.json"
    claims.write_text(json.dumps([
        {"kind": "text_present", "value": "31 files"},
        {"kind": "text_present", "value": "MISSING"},
    ]), encoding="utf-8")
    out = tmp_path / "findings.sarif"
    monkeypatch.setattr(sys, "argv", [
        "verdict", "check", str(target), "--claims-file", str(claims),
        "--base-dir", str(tmp_path), "--no-ledger", "--sarif", str(out), "--lang", "en",
    ])
    try:
        verdict_cli.main()
    except SystemExit as exc:
        assert exc.code == 2
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["version"] == "2.1.0"
    assert len(doc["runs"][0]["results"]) == 1
