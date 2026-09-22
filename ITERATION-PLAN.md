# Iteration plan

Owner: Kevin ｜ Started 2026-09-15 ｜ Upstream: 2akouwu/reverify v0.11.0
Last updated: 2026-09-22 (M1 + M2 landed)

---

## 0. Where we are

| Milestone | Status |
|---|---|
| M0 fork + vertical slice | ✓ 2026-09-15 |
| M1 code-domain gates + ledger | ✓ 2026-09-22 |
| M2 rule bundles + HTML report | ✓ 2026-09-22 |
| M3 CI + distribution | next (9/23–9/28) |
| M4 content vertical + launch | 10/6–10/19 |
| M5 team tier | only after M4 shows pull |

Tests: **345 passed / 55 skipped** (314 upstream + 31 verdict).

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

- [ ] GitHub Action `verdict-gate@v1` (composite: setup-python → `pip install
      verdict-gate` → run → PR annotation). Marketplace listing. **9/23**
- [ ] Rename dist `reverify` → `verdict-gate`, keep the `reverify` console
      scripts for upstream compatibility, publish to PyPI. **9/23**
- [ ] Commit `.verdict/` defaults here so a clone gates itself (own
      `claims.json` + `allowlist.json`). **9/24**
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

1. GitHub Action `verdict-gate@v1` + PyPI rename/publish (9/23)
2. Commit `.verdict/` defaults in this repo (9/24)
3. Pages sample report + MCP server (travel week)
4. Then M4: `citation_resolves`, `number_matches_source`
