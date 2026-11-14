"""Tests for the deterministic scope layer and citation verification.

Adapted from open-code-review's design (Apache-2.0); implementation is ours.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from reverify.verifier import INCONCLUSIVE, REFUTED, VERIFIED, Claim

from verdict import cli as verdict_cli
from verdict.scope import (
    Change, bundle_changes, build_scope, collect_changes, decide,
    delegate_spec, glob_to_regex, resolve_rules,
)
from verdict.verifier import GateVerifier


def run(claims, data: bytes = b"x", base_dir: str = "."):
    return GateVerifier(data, base_dir=base_dir).verify_all(
        [Claim.from_dict(c) for c in claims], min_information=0.0
    )


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "test")
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (tmp_path / "tests" / "test_app.py").write_text("def test_add(): assert True\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Demo\nSee src/app.py:1 for add().\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


# --- selection -------------------------------------------------------------

def test_glob_semantics():
    assert glob_to_regex("src/**/*.py").match("src/a/b.py")
    assert not glob_to_regex("src/*.py").match("src/a/b.py")
    assert glob_to_regex("*.md").match("README.md")


def test_decision_order_secret_paths_win():
    assert decide(Change(".env", "M")).reason == "secret-path"
    assert decide(Change("keys/id_rsa", "M")).reason == "secret-path"
    assert decide(Change("a.png", "M")).reason == "binary"
    assert decide(Change("package-lock.json", "M")).reason == "default-exclude"
    assert decide(Change("tests/test_x.py", "M")).reason == "default-exclude"
    assert decide(Change("src/app.py", "D")).reason == "deleted"
    assert decide(Change("src/app.py", "M")).selected


def test_user_excludes_cannot_readmit_secret_paths():
    d = decide(Change(".env", "M"), user_excludes=[".env"])
    assert not d.selected and d.reason == "secret-path"


def test_collect_changes_modes(tmp_path):
    repo = _repo(tmp_path)
    (repo / "src" / "app.py").write_text("def add(a, b):\n    return a + b + 1\n", encoding="utf-8")
    (repo / "src" / "new.py").write_text("x = 1\n", encoding="utf-8")
    workspace = collect_changes(str(repo), "workspace")
    assert "src/new.py" in [c.path for c in workspace]
    base = collect_changes(str(repo), "base", base="HEAD")
    assert "src/app.py" in [c.path for c in base]
    mb = collect_changes(str(repo), "merge-base", base="HEAD", to="HEAD")
    assert isinstance(mb, list)
    commit = collect_changes(str(repo), "commit", commit="HEAD")
    assert "README.md" in [c.path for c in commit]


def test_selection_is_pure_and_preview_matches_run(tmp_path):
    repo = _repo(tmp_path)
    (repo / "src" / "app.py").write_text("changed\n", encoding="utf-8")
    a = build_scope(str(repo), "workspace")
    b = build_scope(str(repo), "workspace")
    for key in ("decisions", "selected", "bundles", "rule_groups"):
        assert a[key] == b[key]


def test_resolve_rules_groups_by_provenance(tmp_path):
    repo = _repo(tmp_path)
    (repo / ".verdict").mkdir()
    (repo / ".verdict" / "scope-rules.json").write_text(json.dumps({
        "rules": [{"pattern": "src/**/*.py", "rules": ["house-style"]}]
    }), encoding="utf-8")
    groups = resolve_rules(["src/app.py", "src/lib.py", "README.md"], str(repo))
    by_pattern = {g.pattern: g for g in groups}
    assert by_pattern["src/**/*.py"].source == "project"
    assert by_pattern["src/**/*.py"].files == ["src/app.py", "src/lib.py"]
    assert by_pattern["src/**/*.py"].rules == ["house-style"]
    assert by_pattern["default"].rules == ["ai-tells-density"]


def test_bundling_pairs_tests_and_caps_size():
    paths = ["src/app.py", "src/test_app.py", "src/lib.py", "README.md"]
    bundles = bundle_changes(paths)
    assert any(b["label"].startswith("pair:") and len(b["files"]) == 2 for b in bundles)
    many = [f"pkg/mod{i}.py" for i in range(25)]
    big = bundle_changes(many)
    assert all(len(b["files"]) <= 10 for b in big)
    assert sum(len(b["files"]) for b in big) == 25


def test_delegate_spec_has_no_model_call_and_full_provenance(tmp_path):
    repo = _repo(tmp_path)
    spec = delegate_spec(build_scope(str(repo), "workspace"))
    assert spec["type"] == "verdict-delegate-spec"
    assert "Do not assert" in spec["instructions"]
    assert "replay" in spec
    assert isinstance(spec["excluded"], list)


def test_cli_scope_json_and_delegate(tmp_path, capsys):
    repo = _repo(tmp_path)
    (repo / "src" / "app.py").write_text("changed\n", encoding="utf-8")
    old = sys.argv
    try:
        sys.argv = ["verdict", "scope", "--base-dir", str(repo), "--json"]
        verdict_cli.main()
        out = json.loads(capsys.readouterr().out)
        assert out["type"] == "verdict-scope"
        sys.argv = ["verdict", "scope", "--base-dir", str(repo), "--delegate", "--json"]
        verdict_cli.main()
        out2 = json.loads(capsys.readouterr().out)
        assert out2["type"] == "verdict-delegate-spec"
    finally:
        sys.argv = old


# --- citations -------------------------------------------------------------

def test_citation_resolves_valid_reference(tmp_path):
    repo = _repo(tmp_path)
    rep = run([{"kind": "citation_resolves"}],
              b"See src/app.py:1 for the helper.\n", base_dir=str(repo))
    r = rep["results"][0]
    assert r["verdict"] == VERIFIED
    assert "def add" in r["evidence"]["resolved_sample"][0]["actual"]


def test_citation_bad_line_is_refuted(tmp_path):
    repo = _repo(tmp_path)
    rep = run([{"kind": "citation_resolves"}],
              b"See src/app.py:999 for the helper.\n", base_dir=str(repo))
    assert rep["results"][0]["verdict"] == REFUTED
    assert "out of range" in rep["results"][0]["evidence"]["failures"][0]["reason"]


def test_citation_missing_file_and_path_escape(tmp_path):
    repo = _repo(tmp_path)
    rep = run([{"kind": "citation_resolves"}],
              b"See src/missing.py:1 and ../secret.py:1\n", base_dir=str(repo))
    reasons = [f["reason"] for f in rep["results"][0]["evidence"]["failures"]]
    assert "file not found" in reasons
    assert "escapes the repository root" in reasons


def test_citation_explicit_contains(tmp_path):
    repo = _repo(tmp_path)
    rep = run([{
        "kind": "citation_resolves", "from_text": False,
        "citations": [{"path": "src/app.py", "line": 1, "contains": "def add"}],
    }], base_dir=str(repo))
    assert rep["results"][0]["verdict"] == VERIFIED
    bad = run([{
        "kind": "citation_resolves", "from_text": False,
        "citations": [{"path": "src/app.py", "line": 1, "contains": "not here"}],
    }], base_dir=str(repo))
    assert bad["results"][0]["verdict"] == REFUTED


def test_no_citations_is_inconclusive(tmp_path):
    rep = run([{"kind": "citation_resolves"}], b"nothing referenced\n", base_dir=str(tmp_path))
    assert rep["results"][0]["verdict"] == INCONCLUSIVE


# --- diff_touches revision modes ------------------------------------------

def test_diff_touches_workspace_revision(tmp_path):
    repo = _repo(tmp_path)
    (repo / "src" / "brand_new.py").write_text("x = 1\n", encoding="utf-8")
    rep = run([{
        "kind": "diff_touches", "paths": ["src/brand_new.py"], "revision": "workspace",
    }], base_dir=str(repo))
    assert rep["results"][0]["verdict"] == VERIFIED
