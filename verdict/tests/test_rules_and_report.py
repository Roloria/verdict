"""Tests for rule bundles and the HTML report."""

from __future__ import annotations

import json
import os
import sys

import pytest

from reverify.verifier import REFUTED, VERIFIED, Claim

from verdict import cli as verdict_cli
from verdict.report import render, render_file
from verdict.rules import add_bundle, available, load, load_many, resolve
from verdict.verifier import GateVerifier

DIRTY = "Migration done. In today's fast-paced landscape this is a game changer.\n"
CLEAN = "Migration done. It rewrote 31 files.\n"


def test_builtin_bundles_are_discoverable():
    names = {n for n, _, _ in available()}
    assert {"ai-tells", "secrets-pii", "pr-evidence"} <= names


def test_load_many_merges_claims_and_weights():
    claims, weights = load_many("ai-tells,secrets-pii")
    assert len(claims) >= 20
    assert weights["text_absent"] == 0.55  # secrets-pii overrides ai-tells' 0.4
    assert all("kind" in c for c in claims)


def test_local_bundle_shadows_builtin(tmp_path):
    d = tmp_path / ".verdict" / "rules"
    d.mkdir(parents=True)
    (d / "ai-tells.json").write_text(
        json.dumps({"name": "ai-tells", "claims": [{"kind": "text_absent", "value": "only-mine"}]}),
        encoding="utf-8",
    )
    assert resolve("ai-tells", str(tmp_path)) == str(d / "ai-tells.json")
    assert load("ai-tells", str(tmp_path))["claims"][0]["value"] == "only-mine"


def test_add_bundle_vendors_a_file(tmp_path):
    src = tmp_path / "mine.json"
    src.write_text(json.dumps({"name": "mine", "claims": [{"kind": "text_absent", "value": "x"}]}), encoding="utf-8")
    dest = add_bundle(str(src), str(tmp_path))
    assert os.path.isfile(dest)
    assert load("mine", str(tmp_path))["claims"]


def test_missing_bundle_raises():
    with pytest.raises(FileNotFoundError):
        load("does-not-exist")


def test_weight_override_reaches_the_score():
    run = GateVerifier(CLEAN.encode())
    plain = run.verify_all([Claim.from_dict({"kind": "text_absent", "value": "game changer"})], min_information=0.0)
    boosted = GateVerifier(CLEAN.encode(), weight_overrides={"text_absent": 0.9})
    boosted_report = boosted.verify_all(
        [Claim.from_dict({"kind": "text_absent", "value": "game changer"})], min_information=0.0
    )
    assert boosted_report["results"][0]["weight"] > plain["results"][0]["weight"]


def test_repeated_claims_of_one_kind_decay():
    """A bundle of 10 easy claims must not score like 10 pieces of evidence."""
    v = GateVerifier(CLEAN.encode())
    rep = v.verify_all(
        [Claim.from_dict({"kind": "text_absent", "value": f"needle-{i}"}) for i in range(10)],
        min_information=0.0,
    )
    weights = [r["weight"] for r in rep["results"]]
    assert weights[0] > weights[-1]
    assert sum(weights) < 10 * weights[0]
    assert rep["information"] < 2.0


def test_rules_flag_catches_ai_tells(tmp_path):
    target = tmp_path / "report.md"
    target.write_text(DIRTY, encoding="utf-8")
    old = sys.argv
    try:
        sys.argv = ["verdict", "check", str(target), "--rules", "ai-tells",
                    "--base-dir", str(tmp_path), "--no-ledger", "--min-information", "0.2"]
        try:
            verdict_cli.main()
            code = 0
        except SystemExit as exc:
            code = exc.code
    finally:
        sys.argv = old
    assert code == 2  # at least "game changer" and "fast-paced landscape" refuted


def test_clean_output_passes_the_same_rules(tmp_path):
    target = tmp_path / "report.md"
    target.write_text(CLEAN, encoding="utf-8")
    old = sys.argv
    try:
        sys.argv = ["verdict", "check", str(target), "--rules", "ai-tells",
                    "--base-dir", str(tmp_path), "--no-ledger", "--min-information", "0.2"]
        try:
            verdict_cli.main()
            code = 0
        except SystemExit as exc:
            code = exc.code
    finally:
        sys.argv = old
    assert code == 0


def test_report_renders_and_escapes(tmp_path):
    v = GateVerifier(DIRTY.encode())
    report = v.verify_all(
        [Claim.from_dict({"kind": "text_absent", "value": "game changer", "note": "a <script> tell"})],
        min_information=0.0,
    )
    out = tmp_path / "gate.html"
    render_file(report, str(out), target="report.md", rules="ai-tells")
    html = out.read_text(encoding="utf-8")
    assert "verdict · 输出质量闸门报告" in html
    assert "已驳回" in html
    assert "闸门结论" in html
    assert "复现命令：" in html
    assert "gate report" not in html
    assert ">REFUTED<" not in html
    assert "<script>" not in html  # escaped
    assert "&lt;script&gt;" in html
    assert "https://" not in html  # no external resources


def test_report_from_saved_json(tmp_path):
    v = GateVerifier(CLEAN.encode())
    report = v.verify_all([Claim.from_dict({"kind": "text_present", "value": "31 files"})], min_information=0.0)
    src = tmp_path / "run.json"
    src.write_text(json.dumps(report), encoding="utf-8")
    old = sys.argv
    try:
        sys.argv = ["verdict", "report", str(src), "--out", str(tmp_path / "g.html")]
        verdict_cli.main()
    finally:
        sys.argv = old
    assert (tmp_path / "g.html").is_file()


def test_report_translates_gate_details():
    from verdict.report import render, _display_detail

    assert _display_detail("found 2 occurrence(s) that must not be there") == "出现 2 处本不该出现的内容"
    assert _display_detail("absent as claimed") == "符合断言：未出现"
    combined = _display_detail("deleted test file(s): a.py; code changed with no test file changed")
    assert "删除了测试文件" in combined and "修改了代码但没有" in combined and "；" in combined

    page = render({
        "results": [{
            "kind": "text_absent", "verdict": "REFUTED", "weight": 0.4, "note": "测试",
            "detail": "found 1 occurrence(s) that must not be there",
            "evidence": {"occurrences": 1, "needle": "game changer"},
        }],
        "receipt": {"replay": "verdict check x", "generated": "2026-11-15T00:00:00Z"},
        "verified": 0, "total_claims": 1, "refuted": 1, "inconclusive": 0,
        "information": 0, "min_information": 1, "grounded_score": 0,
        "informative": False, "grounded": False,
    }, target="报告.md", rules="ai-tells")
    assert "出现 1 处本不该出现的内容" in page
    assert "出现次数=1" in page
    assert "未通过" in page
    assert "规则包：ai-tells" in page
    assert "found 1 occurrence" not in page
