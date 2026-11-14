"""Language support: resolution, CLI switching and bilingual reports."""

from __future__ import annotations

import json
import os
import sys

import pytest

from verdict import cli as verdict_cli
from verdict.i18n import LANGS, from_locale, normalize, resolve, set_lang, t, translate_detail
from verdict.report import render


@pytest.fixture(autouse=True)
def reset_lang():
    yield
    set_lang("zh-CN", ".")


def test_language_table_is_complete():
    from verdict.i18n import MESSAGES

    assert set(LANGS) == {"zh-CN", "en"}
    for key, variants in MESSAGES.items():
        assert set(variants) == set(LANGS), f"{key} is missing a language"


def test_normalize_aliases():
    assert normalize("zh") == "zh-CN"
    assert normalize("ZH_CN") == "zh-CN"
    assert normalize("en-US") == "en"
    assert normalize("auto") == "auto"
    assert normalize("klingon") is None


def test_resolution_priority(monkeypatch, tmp_path):
    (tmp_path / ".verdict").mkdir()
    (tmp_path / ".verdict" / "config.json").write_text(json.dumps({"lang": "en"}), encoding="utf-8")
    monkeypatch.setenv("VERDICT_LANG", "en")
    assert resolve(None, str(tmp_path)) == "en"              # env
    assert resolve("zh-CN", str(tmp_path)) == "zh-CN"        # explicit wins
    monkeypatch.delenv("VERDICT_LANG")
    assert resolve(None, str(tmp_path)) == "en"              # config
    (tmp_path / ".verdict" / "config.json").write_text(json.dumps({"lang": "auto"}), encoding="utf-8")
    monkeypatch.setenv("LANG", "zh_CN.UTF-8")
    assert resolve(None, str(tmp_path)) == "zh-CN"           # auto + locale
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    assert resolve(None, str(tmp_path)) == "en"


def test_t_and_detail_translation():
    assert t("card.gate", "zh-CN") == "闸门结论"
    assert t("card.gate", "en") == "gate"
    zh = translate_detail("found 2 occurrence(s) that must not be there", "zh-CN")
    en = translate_detail("found 2 occurrence(s) that must not be there", "en")
    assert zh == "出现 2 处本不该出现的内容"
    assert en == "found 2 occurrence(s) that must not be there"


def test_bilingual_report_embeds_both_languages():
    report = {
        "results": [{
            "kind": "text_absent", "verdict": "REFUTED", "weight": 0.4, "note": "",
            "detail": "found 1 occurrence(s) that must not be there",
            "evidence": {"occurrences": 1},
        }],
        "receipt": {"replay": "verdict check x"},
        "verified": 0, "total_claims": 1, "refuted": 1, "inconclusive": 0,
        "information": 0, "min_information": 1, "grounded_score": 0,
        "informative": False, "grounded": False,
    }
    zh = render(report, lang="zh-CN")
    en = render(report, lang="en")
    assert '<html lang="zh-CN">' in zh and '<html lang="en">' in en
    assert '<title>verdict · 输出质量闸门报告</title>' in zh
    assert '<title>verdict · gate report</title>' in en
    assert 'data-en="verdict · gate report"' in zh   # both embedded for the switch
    assert "已驳回" in zh and ">REFUTED<" in en
    assert 'data-zh="已驳回"' in en and 'data-en="REFUTED"' in zh
    assert 'id="langbtn"' in zh and 'data-current="en"' in en
    assert "https://" not in zh  # still fully offline


def _run_cli(argv, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["verdict", *argv])
    try:
        verdict_cli.main()
        code = 0
    except SystemExit as exc:
        code = exc.code
    return capsys.readouterr().out, code


def test_cli_lang_switch(tmp_path, monkeypatch, capsys):
    target = tmp_path / "report.md"
    target.write_text("31 files\n", encoding="utf-8")
    claims = tmp_path / "claims.json"
    claims.write_text(json.dumps([{"kind": "text_present", "value": "31 files"}]), encoding="utf-8")
    base = ["check", str(target), "--claims-file", str(claims), "--base-dir",
            str(tmp_path), "--no-ledger", "--min-information", "0.2"]

    zh, zh_code = _run_cli([*base, "--lang", "zh-CN"], monkeypatch, capsys)
    assert "AI 输出质量闸门" in zh and "已验证" in zh
    assert zh_code == 0

    en, en_code = _run_cli([*base, "--lang", "en"], monkeypatch, capsys)
    assert "AI output gate" in en and "verified 1/1" in en
    assert en_code == 0

    # global option position also works: verdict --lang en check ...
    en2, _ = _run_cli(["--lang", "en", *base], monkeypatch, capsys)
    assert "AI output gate" in en2


def test_verdict_env_lang(monkeypatch, tmp_path, capsys):
    target = tmp_path / "r.md"
    target.write_text("x\n", encoding="utf-8")
    claims = tmp_path / "c.json"
    claims.write_text(json.dumps([{"kind": "text_present", "value": "x"}]), encoding="utf-8")
    monkeypatch.setenv("VERDICT_LANG", "en")
    out, _ = _run_cli(
        ["check", str(target), "--claims-file", str(claims), "--base-dir", str(tmp_path),
         "--no-ledger", "--min-information", "0.2"], monkeypatch, capsys,
    )
    assert "AI output gate" in out


def test_report_subcommand_lang(tmp_path, monkeypatch, capsys):
    src = tmp_path / "run.json"
    src.write_text(json.dumps({
        "results": [], "receipt": {}, "verified": 0, "total_claims": 0,
        "refuted": 0, "inconclusive": 0, "information": 0, "min_information": 1,
        "grounded_score": 0, "informative": False, "grounded": False,
    }), encoding="utf-8")
    out = tmp_path / "out.html"
    _run_cli(["report", str(src), "--out", str(out), "--lang", "en"], monkeypatch, capsys)
    assert '<html lang="en">' in out.read_text(encoding="utf-8")
