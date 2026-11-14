# ai-verdict

[简体中文](README.md) · English

**A quality gate for AI output.** Not another model grading text — every
assertion is bound to a check a deterministic tool can run. The model proposes
claims; tools decide; CI reads the exit code.

> Forked from [reverify](https://github.com/2akouwu/reverify) (MIT, v0.11.0).
> `reverify/` is vendored upstream and never edited; all new code lives in
> `verdict/`, so `git merge upstream/main` stays conflict-free. The original
> upstream README is kept at [README.upstream.md](README.upstream.md).

---

## Why

The industry answer to unreliable AI output is to ask another model to grade it.
A judge that shares the generator's priors gives you a number, not evidence. As
one project in this space puts it:

> LLM judges agree with human slop labels at chance.

verdict asks a different question: **can this sentence be verified by a tool?**
If not, it is prose, not a claim.

One run yields: 37 claims, 34 VERIFIED, 2 REFUTED, 1 INCONCLUSIVE, each with the
observed evidence and a replay command.

## Quick start

```bash
pip install ai-verdict            # before release: pip install -e ".[dev]"
verdict kinds
verdict rules list

verdict init                      # zero-config bootstrap: config + CI + hook
verdict propose report.md --out claims.json   # draft claims, deterministically
verdict check report.md --claims-file claims.json
verdict check report.md --rules ai-tells-density,secrets-pii
verdict check report.md --rules ai-tells-density --report gate.html \
  --sarif findings.sarif        # upload to GitHub code scanning
```

Exit codes: `0` grounded · `2` refuted · `3` thin evidence · `4` inconclusive (`--strict`).

## How it works

| Concept | Meaning |
|---|---|
| claim → tool → evidence | every assertion is decided by a deterministic tool and returns VERIFIED / REFUTED / INCONCLUSIVE with what was actually observed |
| information > pass rate | 30 passing trivial claims are not evidence; claims of the same kind decay 1/N and a thin set exits 3 |
| anti-gaming weights | restated facts, duplicates and self-referential claims get weight 0 |
| evidence ledger | each run appends a JSON line to `.verdict/ledger.jsonl` |
| fail-closed | a tool that could not run is INCONCLUSIVE, never VERIFIED |
| no model in the verify path | an LLM may propose claims, never decide them |

### Gates

| gate | asserts |
|---|---|
| `text_present` / `text_absent` | a literal or regex appears / does not (optionally N times) |
| `slop_density` | fewer than N distinct AI-tell patterns in one paragraph (192 phrases / 59 ids built in) |
| `file_exists` | a claimed file exists, is non-trivial, and cannot escape the repo |
| `command_succeeds` | an allow-listed command exits as expected (argv only, never a shell string) |
| `diff_touches` | claimed paths really appear in the git diff |
| `tests_actually_prove` | no deleted/skipped tests, no code change without a test change |
| `citation_resolves` | every `path:line` reference resolves, with the observed line as evidence |

Plus every reverify kind (`bytes_at`, `string_present`, `functions_equiv`, ...).

### Rule bundles

`ai-tells-density` (low false positives, default), `ai-tells` (strict),
`secrets-pii`, `pr-evidence`. Vendor a team bundle with
`verdict rules add ./house-style.json`.

## Language support

**`zh-CN` and `en` are both supported; adding a language means adding one table
to `verdict/i18n.py`.**

| Method | Example |
|---|---|
| CLI flag | `verdict check ... --lang zh-CN` (also `verdict --lang zh-CN check ...`) |
| env var | `VERDICT_LANG=zh-CN` |
| project config | `.verdict/config.json` → `{"lang": "en"}` (see `config.example.json`) |
| follow locale | `--lang auto` (reads `LC_ALL` / `LANG`) |
| HTML report | one file embeds both languages; the top-right button switches instantly, offline |

Priority: `--lang` > `VERDICT_LANG` > project config > default `zh-CN`.

**Never translated**: protocol values (`VERIFIED` / `REFUTED`), gate names,
`--json` output, JSON evidence keys and claim files. CI, scripts and the upstream
protocol are unaffected; only human-facing prose changes.

## Deterministic review scope (from open-code-review)

```bash
verdict scope --mode workspace --json
verdict scope --mode merge-base --base main --to HEAD --delegate --json
```

Returns an explicit include/exclude reason per changed file, per-file resolved
rule bundles, and bundles that pair implementation with its tests. `--delegate`
produces a structured hand-off for a host agent without calling any model.
Design adapted from [alibaba/open-code-review](https://github.com/alibaba/open-code-review)
(Apache-2.0); no code or data was copied — see [ATTRIBUTION.md](ATTRIBUTION.md).

## CI / agent surfaces

```yaml
- uses: Roloria/verdict@v1
  with:
    target: docs/report.md
    rules: ai-tells-density,secrets-pii
    lang: en
```

- `SKILL.md` / `skills/ai-verdict/SKILL.md` — Agent Skills, `npx skills add Roloria/verdict --skill ai-verdict`
- `ai-verdict-mcp` — stdio MCP server with `verify_claims` / `list_rules`, accepts `lang`
- `.github/workflows/verdict.yml` — this repo gates itself, including a negative test

## Benchmark

`python eval/run.py` → [eval/RESULTS.md](eval/RESULTS.md): 30 injected-defect
cases, precision / recall / F1 = 1.000 / 1.000 / 1.000, 0 false accepts,
0 false alarms, broken down by defect type.

Perfect scores on hand-written cases prove little, so [CALIBRATION.md](eval/CALIBRATION.md)
runs the default bundles against 11 real external open-source READMEs (fetched
at runtime, never committed): **0/11 false alarms**, and **22/22** injected
defects caught. That pass found and fixed a real false positive — an 18-digit
ID regex firing on badge URLs.

## Status

| Item | State |
|---|---|
| Code | complete; 381+ passed / 55 skipped, self-gate 10/10 |
| PyPI / Marketplace | **not published** — package name is `ai-verdict` (the original `verdict-gate` was taken) |
| Preflight | `verdict release-check`: 6✓/2✗; the GitHub `pypi` environment and build deps are ready |
| Next | add a pending publisher on pypi.org → `sh tools/publish.sh` → Marketplace, see [RELEASE.md](RELEASE.md) |

## Docs

[USAGE.md](USAGE.md) · [VISION.md](VISION.md) · [ITERATION-PLAN.md](ITERATION-PLAN.md) · [SKILL.md](SKILL.md) · [RELEASE.md](RELEASE.md) · [ATTRIBUTION.md](ATTRIBUTION.md)

License: MIT. Upstream reverify (MIT) and AI-tell patterns from
FeedHive/ai-slop-detector (MIT) are credited in ATTRIBUTION.md.
