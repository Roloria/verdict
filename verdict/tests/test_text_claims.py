"""Tests for verdict's text / file gates and its scoring rule set."""

from __future__ import annotations

import json
import os

import pytest

from reverify.verifier import VERIFIED, REFUTED, INCONCLUSIVE, Claim

from verdict.verifier import GateVerifier, gate_weight

REPORT = (
    "The migration finished in 4.2 seconds.\n"
    "It rewrote 31 files under src/legacy/.\n"
    "In today's fast-paced landscape, this is a game changer.\n"
)


def run(claims, data: bytes = REPORT.encode(), base_dir: str = ".", min_information: float = 0.0):
    v = GateVerifier(data, base_dir=base_dir)
    return v.verify_all([Claim.from_dict(c) for c in claims], min_information=min_information)


def test_text_present_verified_and_refuted():
    rep = run([
        {"kind": "text_present", "value": "31 files"},
        {"kind": "text_present", "value": "128 files"},
    ])
    verdicts = [r["verdict"] for r in rep["results"]]
    assert verdicts == [VERIFIED, REFUTED]
    assert rep["verified"] == 1 and rep["refuted"] == 1


def test_text_present_regex_and_count():
    rep = run([
        {"kind": "text_present", "pattern": r"\d+\.\d+ seconds", "regex": True},
        {"kind": "text_present", "value": "src/legacy/", "count": 1},
        {"kind": "text_present", "value": "src/legacy/", "min_count": 3},
    ])
    assert [r["verdict"] for r in rep["results"]] == [VERIFIED, VERIFIED, REFUTED]


def test_text_absent_catches_ai_tell_and_secret():
    clean = run([{"kind": "text_absent", "value": "game changer"}])
    assert clean["results"][0]["verdict"] == REFUTED
    dirty = run([{"kind": "text_absent", "pattern": r"sk-[A-Za-z0-9]{20,}", "regex": True}])
    assert dirty["results"][0]["verdict"] == VERIFIED


def test_file_exists_and_path_escape(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
    rep = run(
        [
            {"kind": "file_exists", "path": "src/app.py", "min_bytes": 5},
            {"kind": "file_exists", "path": "src/missing.py"},
            {"kind": "file_exists", "path": "../etc/passwd"},
        ],
        data=b"x",
        base_dir=str(tmp_path),
    )
    verdicts = [r["verdict"] for r in rep["results"]]
    assert verdicts[0] == VERIFIED
    assert verdicts[1] == REFUTED and "does not exist" in rep["results"][1]["detail"]
    assert verdicts[2] == REFUTED and "escapes" in rep["results"][2]["detail"]


def test_malformed_claim_is_inconclusive_not_crash():
    rep = run([{"kind": "text_present"}, {"kind": "text_present", "pattern": "[unclosed", "regex": True}])
    assert [r["verdict"] for r in rep["results"]] == [INCONCLUSIVE, INCONCLUSIVE]
    assert all("malformed claim" in r["detail"] for r in rep["results"])


def test_unknown_kind_stays_inconclusive():
    rep = run([{"kind": "quantum_vibe_check", "value": "x"}])
    assert rep["results"][0]["verdict"] == INCONCLUSIVE


def test_gate_weights_beat_the_upstream_default():
    base = {"kind": "text_present", "params": {"value": "31 files"}, "evidence": {"occurrences": 1}}
    assert gate_weight(base) > 0.3
    assert gate_weight({**base, "kind": "file_exists", "params": {"path": "a"}}) < gate_weight(base)
    assert gate_weight({**base, "evidence": {"occurrences": 100}}) < gate_weight(base)


def test_rescore_sets_information_and_grounded():
    rep = run(
        [{"kind": "text_present", "value": "31 files"}, {"kind": "text_absent", "value": "sk-abc"}],
        min_information=0.5,
    )
    assert rep["refuted"] == 0
    assert rep["information"] > 0.5
    assert rep["informative"] is True
    assert rep["grounded"] is True
    assert 0.0 < rep["grounded_score"] <= 1.0


def test_thin_evidence_is_not_informative():
    rep = run([{"kind": "file_exists", "path": __file__}], data=b"x", min_information=5.0)
    assert rep["refuted"] == 0
    assert rep["informative"] is False
    assert rep["grounded"] is False


def test_cli_exit_codes(tmp_path, monkeypatch, capsys):
    from verdict import cli as verdict_cli

    claims = tmp_path / "claims.json"
    claims.write_text(
        json.dumps([{"kind": "text_present", "value": "31 files"}]), encoding="utf-8"
    )
    target = tmp_path / "report.md"
    target.write_text(REPORT, encoding="utf-8")

    def call(argv):
        monkeypatch.setattr("sys.argv", ["verdict"] + argv)
        try:
            verdict_cli.main()
            return 0
        except SystemExit as exc:
            return exc.code

    assert call(["check", str(target), "--claims-file", str(claims), "--min-information", "0.2"]) == 0
    assert call(["check", str(target), "--claims-file", str(claims), "--min-information", "99"]) == 3

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([{"kind": "text_present", "value": "Nonexistent claim"}]), encoding="utf-8")
    assert call(["check", str(target), "--claims-file", str(bad)]) == 2


def test_upstream_kinds_still_work_through_gate_verifier():
    """The subclass must not break reverify's own kinds."""
    rep = run([{"kind": "string_present", "value": "src/legacy/"}])
    assert rep["results"][0]["verdict"] == VERIFIED
