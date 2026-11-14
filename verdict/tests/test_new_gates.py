"""Tests for slop_density, tests_actually_prove, and the v2 bundles."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from reverify.verifier import INCONCLUSIVE, REFUTED, VERIFIED, Claim

import verdict
from verdict.rules import load, load_many
from verdict.verifier import GateVerifier

SLOPPY = (
    "Let's delve into this pivotal moment. It's worth noting the ever-evolving "
    "landscape, a testament to the tapestry of modern engineering.\n"
)
CLEAN = "The migration rewrote 31 files. Rollback uses `migrate --undo`.\n"


def run(claims, data: bytes = CLEAN.encode(), base_dir: str = ".", min_information: float = 0.0):
    v = GateVerifier(data, base_dir=base_dir)
    return v.verify_all([Claim.from_dict(c) for c in claims], min_information=min_information)


def test_preset_loads_and_has_many_distinct_ids():
    from verdict.verifier import _load_slop_preset

    entries = _load_slop_preset("slop-120")
    assert len(entries) > 100
    assert len({e["id"] for e in entries}) >= 40
    assert all("regex" in e for e in entries)


def test_slop_density_catches_a_dense_paragraph():
    rep = run([{"kind": "slop_density", "preset": "slop-120", "min_hits": 3}], SLOPPY.encode())
    r = rep["results"][0]
    assert r["verdict"] == REFUTED
    assert r["evidence"]["max_hits"] >= 3
    assert r["evidence"]["findings"][0]["ids"]


def test_slop_density_ignores_clean_prose():
    rep = run([{"kind": "slop_density", "preset": "slop-120", "min_hits": 3}])
    assert rep["results"][0]["verdict"] == VERIFIED


def test_same_catalogue_id_only_counts_once():
    # delve / dive into / deep dive all belong to V-01: one id, not three hits
    text = "We delve, then dive into it, then take a deep dive.\n"
    rep = run([{"kind": "slop_density", "preset": "slop-120", "min_hits": 2}], text.encode())
    r = rep["results"][0]
    assert r["verdict"] == VERIFIED
    assert r["evidence"]["max_hits"] == 1


def test_custom_patterns_and_bad_regex():
    rep = run([{"kind": "slop_density", "patterns": ["synergy", "leverage"], "min_hits": 2}],
              b"synergy and leverage\n")
    assert rep["results"][0]["verdict"] == REFUTED
    bad = run([{"kind": "slop_density", "patterns": ["[broken"]}], b"x")
    assert bad["results"][0]["verdict"] == INCONCLUSIVE


def test_ai_tells_density_bundle_discriminates():
    claims, weights = load_many("ai-tells-density")
    dirty = GateVerifier(SLOPPY.encode(), weight_overrides=weights).verify_all(
        [Claim.from_dict(c) for c in claims], min_information=0.0
    )
    clean = GateVerifier(CLEAN.encode(), weight_overrides=weights).verify_all(
        [Claim.from_dict(c) for c in claims], min_information=0.0
    )
    assert dirty["refuted"] >= 1
    assert clean["refuted"] == 0


def test_ai_tells_v2_has_density_claim():
    doc = load("ai-tells")
    assert doc["version"] == 2
    assert any(c["kind"] == "slop_density" for c in doc["claims"])


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _make_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "test")
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "app.py").write_text("v1\n", encoding="utf-8")
    (tmp_path / "tests" / "test_app.py").write_text("def test_ok(): assert True\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def test_code_change_without_test_change_is_refuted(tmp_path):
    repo = _make_repo(tmp_path)
    (repo / "src" / "app.py").write_text("v2\n", encoding="utf-8")
    rep = run([{"kind": "tests_actually_prove", "base": "HEAD"}], base_dir=str(repo))
    r = rep["results"][0]
    assert r["verdict"] == REFUTED
    assert "no test file changed" in r["detail"]


def test_code_and_test_together_pass(tmp_path):
    repo = _make_repo(tmp_path)
    (repo / "src" / "app.py").write_text("v2\n", encoding="utf-8")
    (repo / "tests" / "test_app.py").write_text("def test_ok(): assert 2 == 2\n", encoding="utf-8")
    rep = run([{"kind": "tests_actually_prove", "base": "HEAD"}], base_dir=str(repo))
    assert rep["results"][0]["verdict"] == VERIFIED


def test_deleted_test_is_refuted(tmp_path):
    repo = _make_repo(tmp_path)
    (repo / "src" / "app.py").write_text("v2\n", encoding="utf-8")
    (repo / "tests" / "test_app.py").unlink()
    rep = run([{"kind": "tests_actually_prove", "base": "HEAD"}], base_dir=str(repo))
    assert "deleted test" in rep["results"][0]["detail"]


def test_new_skip_marker_is_refuted(tmp_path):
    repo = _make_repo(tmp_path)
    (repo / "src" / "app.py").write_text("v2\n", encoding="utf-8")
    (repo / "tests" / "test_app.py").write_text(
        "import pytest\n@pytest.mark.skip\ndef test_ok(): assert True\n", encoding="utf-8"
    )
    rep = run([{"kind": "tests_actually_prove", "base": "HEAD"}], base_dir=str(repo))
    r = rep["results"][0]
    assert r["verdict"] == REFUTED
    assert r["evidence"]["skip_markers"]


def test_not_a_repo_is_inconclusive(tmp_path):
    rep = run([{"kind": "tests_actually_prove"}], base_dir=str(tmp_path))
    assert rep["results"][0]["verdict"] == INCONCLUSIVE


def test_version_matches_pyproject():
    pyproject = (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text(encoding="utf-8")
    declared = re.search(r'^version = "([^"]+)"', pyproject, re.M).group(1)
    assert verdict.__version__ == declared
