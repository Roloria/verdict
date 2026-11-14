# Iteration plan

[简体中文](ITERATION-PLAN.md) · English

Owner: Kevin ｜ Started 2026-09-15 ｜ Upstream: 2akouwu/reverify v0.11.0
Last updated: 2026-11-15 (P0 iteration: claim proposal, release preflight, one-command publishing)

---

## 0. Where we are

| Milestone | Status |
|---|---|
| M0 fork + vertical slice | ✓ 2026-09-15 |
| M1 code-domain gates + ledger | ✓ 2026-09-22 |
| M2 rule bundles + HTML report | ✓ 2026-09-22 |
| M3 CI + distribution (code) | ✓ 2026-09-23 — **publishing still pending** |
| M3.5 restart | ✓ 2026-11-14 |
| M4 content vertical + launch | in progress |
| M5 team tier | only after M4 shows pull |

Tests: **407 passed / 55 skipped** (314 upstream + 93 verdict).

**Still the blocker**: nothing is published. `verdict-gate` was taken on PyPI on
11/10, so the package is now `ai-verdict`. The GitHub `pypi` environment exists
and `verdict release-check` is 6/8; only a pending trusted publisher on
pypi.org remains, then `sh tools/publish.sh`. See RELEASE.md.

```bash
pip install -e ".[dev]"
env -u PYTHONPATH pytest verdict/tests reverify/tests -q
verdict check examples/demo-dirty.md --rules ai-tells,secrets-pii --report examples/gate.html
# → 4 REFUTED, exit 2, grounded_score 0.53
verdict check examples/demo-clean.md  --rules ai-tells,secrets-pii
# → 33/33, exit 0, grounded_score 1.00
```

---

## 1. Architecture constraints (do not break these)

1. **`reverify/` is read-only.** Extend by subclassing `Verifier`; new gates are
   `_check_<kind>` methods. Upstream merges must stay conflict-free.
2. **No LLM in the verify path.** The judge is a tool, always. An LLM may
   *propose* claims (M4), never decide them.
3. **Every gate emits evidence**, not a boolean.
4. **Information, not pass rate.** A set that verifies but says nothing must fail
   (exit 3). See §2.5 — this already bit us once and it will again.
5. **MIT forever.** No open-core license split; monetisation is hosted-only.

---

## 2. Milestones

### M0 · Fork + vertical slice — done 2026-09-15

Fork, upstream suite green, `verdict/` package, `text_present` / `text_absent` /
`file_exists`, own scoring rule set, `verdict check` with exit codes.

### M1 · Code-domain gates + evidence ledger — done 2026-09-22

- [x] `command_succeeds`: allow-list only, argv (never a shell string), timeout,
      evidence = exit code + stdout/stderr sha256 + duration. Turns "the AI says
      tests pass" into a claim. Unlisted → INCONCLUSIVE, never executed.
- [x] `diff_touches`: claimed paths must appear in `git diff --name-only <base>`;
      file or directory matching, `mode: all|any`.
- [x] `.verdict/ledger.jsonl`: one JSON line per run (ts, target sha256, counts,
      information, exit).
- [x] `--fail-on {refuted,thin,inconclusive}` so teams pick their strictness.
- [x] `--allowlist` from `.verdict/allowlist.json`, cwd confined to the repo.

### M2 · Rule bundles + HTML report — done 2026-09-22

- [x] Bundle format (JSON): `name`, `version`, `description`, `claims`, `weights`.
      Resolution: `.verdict/rules/` → built-ins → literal path.
- [x] Shipped bundles: `ai-tells` (24 phrases, EN+ZH), `secrets-pii` (9 regexes),
      `pr-evidence` (tests ran, no placeholders).
- [x] `--rules a,b` expands bundles and merges their weight overrides;
      `--rules` + `--claims-file` compose.
- [x] `verdict rules list|show|add` — `add` vendors a team bundle.
- [x] `verdict check --report gate.html` and `verdict report <json> --out`.
      Single-file HTML, no CDN, light/dark, evidence per row, replay command.
- [x] `--verbose` / default hides passing rows (33-claim runs were unreadable).

### M2.5 · Design defect found and fixed — 2026-09-22

Running a 33-claim bundle scored `information = 19`. Everything passed, so the
"thin evidence" gate could never fire: **many easy claims were worth more than a
few hard ones**, the opposite of what the metric exists to prevent.

Fix: harmonic decay inside a claim kind — the Nth verified claim of a kind counts
`1/N`. Same run now scores 2.5. REFUTED claims keep full weight so a failure
still reads as "this rule matters".

Carry forward: **`--min-information` is bundle-size sensitive.** Shipped bundles
land around 2.5 against the default `1.0`; a team writing 100 claims must raise
it. Document it, do not "fix" it by inflating weights.

### M3 · CI + distribution — 9/23–9/28 (travel starts 9/25: front-load)

Two clear days, then low bandwidth. Order by what unblocks strangers:

- [x] `action.yml` — composite action: setup-python → `pip install ai-verdict`
      → run → job-summary table + `exit-code` / `information` / `grounded`
      outputs. **9/23** (Marketplace listing still needs a tag, see RELEASE.md)
- [x] dist renamed `reverify` → `ai-verdict` (v0.12.0). `reverify` /
      `reverify-mcp` console scripts kept for upstream compatibility.
      `publish-pypi.yml` added (OIDC trusted publishing, no token in repo).
      **9/23** — actual upload needs the PyPI publisher configured once.
- [x] `.verdict/claims.json` + `allowlist.json` committed; this repo now gates
      itself (`verdict.yml` workflow: clean sample must pass, sloppy sample must
      exit 2, own docs gated, both test suites green). **9/23**
- [ ] MCP server exposing `verify_claims` (mirror `reverify/mcp_server.py`) so
      agents can gate their own output mid-run. Travel week.
- [ ] `SKILL.md` for the skills.sh ecosystem: same rule set, agent surface.
      Travel week.
- [ ] GitHub Pages: publish `examples/gate.html` as a live sample report. Cheap,
      high leverage for the launch post.

### M4 · Content vertical + launch — 10/6–10/19

- [ ] `citation_resolves`: every `path:line` or URL in a generated report must
      resolve in-repo. Highest-value fact-check gate for docs.
- [ ] `number_matches_source`: a figure quoted in prose must appear in the named
      source file (regex + file read + evidence excerpt).
- [ ] AI-tell lexicon v2, informed by (not copied from) `sepia` / `hallmark` /
      `ponytail`, with a false-positive note per entry.
- [ ] Launch post: "LLM judges agree with slop labels at chance" + the dirty vs
      clean demo. HN, r/LocalLLaMA, skills.sh ecosystem.

### M5 · Team tier — week 6+ (only after M4 shows pull)

Rule sync, report history off `ledger.jsonl`, SSO, audit export. ¥199/499/999.
Do not build before ~20 outside stars or 3 teams asking.

---

## 3. Decisions

| # | Decision | Outcome |
|---|---|---|
| 1 | Fail on thin evidence by default? | **Yes** (default `--fail-on refuted,thin`). It is the differentiator; teams that hate it pass `--fail-on refuted`. |
| 2 | Bundle source of truth | Vendored files in `.verdict/rules/`; registry deferred to M5 |
| 3 | `command_succeeds` allowlist | Minimal shipped default + team extension. Never auto-approve. |
| 4 | Talk to upstream? | **Not yet.** Revisit when we publish: an issue explaining the fork (and the overlap with their ROADMAP §5) is worth more once there is something to look at. |

---

## 4. Risks

| Risk | Why | Mitigation |
|---|---|---|
| Upstream ships the same thing | reverify ROADMAP §5 says "toward verified coding" | Theirs is behavioural equivalence; ours is output quality (content, compliance, evidence). Say so publicly. |
| `command_succeeds` is RCE-shaped | executing commands from a claim file | argv-only, allowlist, no shell, INCONCLUSIVE when unlisted, cwd confined, timeout |
| `--min-information` confuses teams | the right value depends on bundle size | print the number and the threshold on every run; documented in USAGE.md |
| AI-tell lexicon false positives | "值得注意的是" appears in normal Chinese prose | bundles are vendored and editable; ship conservative, document as opinionated |
| Thin bandwidth 9/25–10/5 | travel | M3 front-loaded; travel week is MCP + SKILL.md + Pages only |

---

## 5. Next actions, in order

1. **Needs you (one-time, ~10 min):** claim `ai-verdict` on PyPI + add the
   trusted publisher, then `git tag v0.12.0 && git push origin v0.12.0`.
   Steps in [RELEASE.md](RELEASE.md). Without it the action cannot install.
2. Publish the release to Marketplace and move the `v1` floating tag.
3. Travel week (9/25–10/5): MCP server (`verify_claims`), SKILL.md for
   skills.sh, GitHub Pages sample report.
4. Then M4: `citation_resolves`, `number_matches_source`, lexicon v2, launch.

## 6. Self-gate (this repo gates itself)

```bash
verdict check ITERATION-PLAN.md --claims-file .verdict/claims.json --base-dir .
# 18/18 verified, information 2.394, grounded_score 1.0, exit 0
```

Claims: the docs, SKILL.md, benchmark results and slop preset exist; no
key-shaped strings in tracked docs; the gate suite and the benchmark both really
run. Also enforced in CI (`.github/workflows/verdict.yml`), including a negative
test — the sloppy sample must exit 2.

---

## 7. Restart, 2026-11-14

Triggered by: 7 weeks idle, `verdict-gate` name taken, and NVIDIA / Alibaba /
Cloudflare moving into verification and quality gates.

- [x] **Rename** to `ai-verdict` (pyproject, action, USAGE, RELEASE, plan).
      Repo stays `Roloria/verdict`; CLI stays `verdict`.
- [x] **Version fix**: `verdict/__init__.py` 0.1.0 → 0.12.0, asserted by a test.
- [x] **`slop_density` gate** — 192 machine-checkable phrases / 59 ids derived
      from FeedHive's 120 patterns (MIT), vendored in `tools/vendor/` with a
      rebuild script. Counts distinct pattern ids per paragraph; one phrase is
      normal, `min_hits` (default 3) in one paragraph is REFUTED.
- [x] **`ai-tells-density` bundle** — low-false-positive default. `ai-tells` v2
      keeps the strict exact-phrase list plus a density claim.
- [x] **`tests_actually_prove` gate** — red flags on deleted tests, new
      `.skip` / `.only` / `@pytest.mark.skip` markers, and code changed with no
      test change. The sharpest anti-laziness check so far.
- [x] **`SKILL.md`** — Agent Skills bundle at repo root for skills.sh.
- [x] **MCP server** — `ai-verdict-mcp`, stdio JSON-RPC, tools
      `verify_claims` / `list_rules`, no SDK dependency.
- [x] **Benchmark** — 30 injected-defect cases, `eval/run.py` →
      `eval/RESULTS.md`. precision 1.000 / recall 1.000 / F1 1.000, 0 false
      accepts, 0 false alarms. A regression tripwire, not a general accuracy
      claim.
- [x] **Pages workflow** — publishes `examples/gate.html` as a live sample.
- [x] Self-gate extended to 9 claims.

### Remaining, in order

1. **Needs Kevin (~10 min)**: claim `ai-verdict` on PyPI, add trusted
   publisher, `git tag v0.12.0 && git push origin v0.12.0`, Marketplace release,
   move `v1`. See RELEASE.md.
2. `npx skills add Roloria/verdict --skill ai-verdict` — verify the skill
   installs (needs the repo public, which it is).
3. `citation_resolves` / `number_matches_source` — the docs vertical.
4. Launch post with the demo + benchmark numbers.
5. Team tier — only after pull.

---

## 8. open-code-review fusion, 2026-11-14

Researched the repo (1405 files, Apache-2.0) and its `internal/agent/selection.go`,
`grouping.go`, `internal/delegate/rulegroup.go`, `.opencodereview/rule.json` and
`ASSURANCE_CASE.md`.

**Borrowed (design only, no Apache code or data copied)**:

| OCR capability | verdict implementation |
|---|---|
| Pure pre-dispatch selection shared by preview and run (their #782 drift bug) | `scope.build_scope()` — one pass, deterministic decisions |
| Static gates in fixed order + explicit `ExcludeReason` | `scope.decide()` — secret → binary → user → default → deleted → too-large |
| Per-file rule resolution grouped by (source, pattern, text) | `scope.resolve_rules()` — same triple key, project config in `.verdict/scope-rules.json` |
| Smart bundling / i18n + test pairing, ≤10 files per group | `scope.bundle_changes()` — fully deterministic, no LLM grouping |
| Delegate mode (structured hand-off, no model needed) | `verdict scope --delegate` → `verdict-delegate-spec`; MCP server already covers the agent side |
| External positioning / reflection modules | `citation_resolves` gate — verifies file + line, returns observed line as evidence |
| Multi-mode review (workspace / branch range / commit / scan) | `scope.collect_changes()` four modes; `diff_touches` gained `revision` |
| Public benchmark with precision/recall framing | `eval/RESULTS.md` now breaks metrics down by defect type |

**Deliberately not adopted**: LLM reviewer, provider/model config, prompt
templates, token budgets, session resume, IDE plugins. verdict's verify path
stays model-free — that is the product's core constraint.

Files added/changed: `verdict/scope.py`, `verdict/verifier.py` (citation_resolves
+ diff_touches revisions), `verdict/cli.py` (`verdict scope`), three new test
modules, USAGE / SKILL (both copies) / ATTRIBUTION / eval results.

Tests: **67 verdict tests pass**; benchmark still 1.000 / 1.000 / 1.000.

---

## 9. Bilingual support + README rewrite, 2026-11-15

- **i18n architecture** (`verdict/i18n.py`): language table, detail-translation
  rules, evidence-key map. Add a language = add one table; no caller changes.
  Resolution: `--lang` > `VERDICT_LANG` > `.verdict/config.json` > `--lang auto`
  (locale) > default `zh-CN`.
- **HTML report**: embeds BOTH languages in one offline file and switches with a
  top-right button (small inline script, no CDN). Server-side `--lang` decides
  which is visible on load. `gate.html` (zh) and `gate.en.html` (en) samples.
- **CLI**: every human-facing string localised (header, marks, summary, scope,
  rules, kinds); `--lang` works before or after the subcommand. `--json`,
  protocol values, gate names and claim files stay English.
- **MCP**: `verify_claims` accepts `lang`, returns `verdict_label` +
  `detail_display` alongside the raw values.
- **Action**: new `lang` input.
- **README**: rewritten in Chinese with an English twin (`README.en.md`),
  language switch links, current capability/status tables. Upstream README
  archived as `README.upstream.md` (420 lines, unmodified).
- `.verdict/config.example.json`, USAGE and both SKILL.md copies updated.
- Tests: 76 verdict tests (new `test_i18n.py`), bilingual report + CLI + MCP
  switching covered.

---

## 10. Value review + adoption work, 2026-11-15

**Verdict: the feature set is comprehensive; the value is not there yet.**
Value ≈ real adoption × credible evidence. Both were near zero: 0 stars, nothing
published, no external users; a hand-written 30-case benchmark scoring 1.000;
onboarding required writing `claims.json` by hand; CI could only fail a build,
not feed code scanning.

**Landed this round (highest leverage first):**

| Gap | Fix |
|---|---|
| credibility | `eval/calibrate.py` → `eval/CALIBRATION.md`: 11 real external OSS READMEs, fetched at runtime (never committed), **0/11 false alarms, 22/22 injected defects caught** |
| real quality bug | that calibration found the 18-digit China-ID regex firing on badge URLs in FastAPI / promptfoo READMEs; bounded the pattern in `secrets-pii`, re-ran both suites |
| onboarding friction | `verdict init` — detects Python/Node/Rust/Go test commands, writes `.verdict/` config + claims + allowlist + scope rules + GitHub Actions workflow + pre-commit script, never overwrites without `--force` |
| CI/audit depth | `--sarif` → SARIF 2.1.0 with `partialFingerprints`, only REFUTED/INCONCLUSIVE become findings; `init` workflow uploads it |

Tests: **85 verdict tests** (`test_init_sarif.py`, `test_i18n.py`, dual-language
self-gate 12/12, benchmark unchanged).

**Remaining, ordered by leverage:**

| # | Task | Why |
|---|---|---|
| P0 | Publish (needs Kevin): PyPI trusted publisher → `v0.12.0` → Marketplace | nothing else compounds until `pip install ai-verdict` works |
| P0 | `verdict propose` — deterministically extract verifiable assertions (numbers, paths, API names, command output) from an artifact into a claims draft | completes the missing half of reverify's protocol: an agent may PROPOSE claims, never decide them. Kills the claims.json hand-authoring friction |
| P1 | PR annotations + diff-only mode (check added lines only) | avoids blocking on historical debt; makes the gate usable on mature repos |
| P1 | `verdict ledger` query + audit export | turns `.verdict/ledger.jsonl` from a log into the asset a team pays for |
| P2 | Team tier: private rule sync, report history, SSO | only after pull from P0/P1 |

---

## 11. P0 iteration, 2026-11-15 04:00

**P0 #2 `verdict propose` — done.** The missing half of reverify's "model
proposes, tools decide" protocol: claim files no longer have to be hand-written.
Deterministic extraction only (no LLM / network / filesystem read), and only
assertions that can bind to EXTERNAL evidence become claims:

| in the artifact | generated claim |
|---|---|
| `src/app.py:12` | `citation_resolves` with explicit citations |
| `README.md` | `file_exists` |
| `` `pytest -q` `` (allow-listed) | `command_succeeds` |
| "all tests pass" | `tests_actually_prove` |
| "no secrets" | `text_absent` (credential shape) |

Numbers, percentages and URLs are **deliberately skipped** and reported in
`skipped`: asserting that a document contains its own number is self-referential.
`--out` writes a claims.json that `verdict check` consumes directly. Same input
always yields the same draft.

**P0 #1 publishing — everything automatable is done:**
- Created the GitHub `pypi` environment via the API (no secret needed, OIDC).
- `verdict release-check`: preflight over dist name, version sync, workflow,
  action tag, local tag, build backend, PyPI state and environment. Now 6✓ / 2✗.
- `tools/publish.sh`: idempotent one-command tag+push; refuses a dirty tree,
  never force-pushes.
- Installed `build` so the local wheel path is checkable.
- RELEASE.md rewritten around: `verdict release-check` → one PyPI web action →
  `sh tools/publish.sh` → Marketplace.

**Still requires Kevin (cannot be done from this machine):** add a *pending
trusted publisher* at https://pypi.org/manage/account/publishing/ for
`ai-verdict` (Roloria / verdict / publish-pypi.yml / pypi). I did **not** push a
`v0.12.0` tag: without that publisher the release workflow would just fail.
After he does it, `sh tools/publish.sh` finishes the release.

Tests: **92 verdict tests**, self-gate extended, benchmark and calibration
unchanged.

**Next after release:** PR annotation + diff-only, `verdict ledger` query/audit
export, then the team tier.

---

## 12. Bilingual plan documents, 2026-11-15 04:46

The Chinese edition is now the primary [ITERATION-PLAN.md](ITERATION-PLAN.md);
this file is the English edition, matching the README convention. Both link to
each other at the top. The self-gate target remains the Chinese file.
