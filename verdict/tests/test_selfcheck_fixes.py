"""Regression tests for issues found in the 2026-11-15 self-check."""

from __future__ import annotations

import json
import subprocess
import sys

from reverify.verifier import Claim

from verdict import cli as verdict_cli
from verdict.i18n import set_lang
from verdict.init import WORKFLOW
from verdict.release import _repo_slug, preflight
from verdict.sarif import build_sarif
from verdict.verifier import GateVerifier


def test_report_rejects_a_claims_array_with_a_clear_message(tmp_path, monkeypatch, capsys):
    claims = tmp_path / "claims.json"
    claims.write_text(json.dumps([{"kind": "text_present", "value": "x"}]), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["verdict", "report", str(claims), "--lang", "en"])
    try:
        verdict_cli.main()
        raised = None
    except SystemExit as exc:
        raised = str(exc.code)
    assert raised and "not a verdict run report" in raised


def test_report_still_renders_a_real_run(tmp_path, monkeypatch, capsys):
    rep = GateVerifier(b"x").verify_all(
        [Claim.from_dict({"kind": "text_present", "value": "x"})], min_information=0.0
    )
    src = tmp_path / "run.json"
    src.write_text(json.dumps(rep), encoding="utf-8")
    out = tmp_path / "gate.html"
    monkeypatch.setattr(sys, "argv", ["verdict", "report", str(src), "--out", str(out), "--lang", "en"])
    verdict_cli.main()
    assert out.is_file()


def test_sarif_line_comes_from_evidence_offset():
    text = "line1\nline2\nBAD\n"
    rep = GateVerifier(text.encode()).verify_all(
        [Claim.from_dict({"kind": "text_absent", "value": "BAD"})], min_information=0.0
    )
    finding = build_sarif(rep, target="r.md", text=text)["runs"][0]["results"][0]
    assert finding["locations"][0]["physicalLocation"]["region"]["startLine"] == 3
    # without the text the offset cannot be mapped, so it falls back safely
    assert build_sarif(rep, target="r.md")["runs"][0]["results"][0][
        "locations"][0]["physicalLocation"]["region"]["startLine"] == 1


def test_sarif_line_comes_from_citation_failure(tmp_path):
    (tmp_path / "a.py").write_text("one\n", encoding="utf-8")
    rep = GateVerifier(b"See a.py:9\n", base_dir=str(tmp_path)).verify_all(
        [Claim.from_dict({"kind": "citation_resolves"})], min_information=0.0
    )
    finding = build_sarif(rep, target="r.md")["runs"][0]["results"][0]
    assert finding["locations"][0]["physicalLocation"]["region"]["startLine"] == 9


def test_init_workflow_creates_the_sarif_it_uploads():
    assert "--sarif verdict.sarif" in WORKFLOW
    assert "sarif_file: verdict.sarif" in WORKFLOW


def test_release_uses_git_remote_not_a_hardcoded_fork(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-C", str(tmp_path), "remote", "add", "origin",
                    "https://github.com/someone/their-fork.git"], check=True)
    assert _repo_slug(tmp_path) == "someone/their-fork"
    result = preflight(str(tmp_path), check_pypi=False)
    assert "repository" in result
    assert any("setuptools" in item for item, _, _ in result["checks"])


def test_release_check_does_not_flag_a_free_pypi_name(monkeypatch):
    import verdict.release as release_mod

    real_run = release_mod.subprocess.run

    def fake_run(cmd, *args, **kwargs):
        if cmd and cmd[0] == "curl":
            return subprocess.CompletedProcess(cmd, 0, stdout="404", stderr="")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(release_mod.subprocess, "run", fake_run)
    result = preflight(".", check_pypi=True)
    assert result["pypi"] == "available"
    pypi = [ok for item, ok, _ in result["checks"] if item.startswith("PyPI ")]
    assert pypi == [True]  # free name + pending publisher is a normal state
