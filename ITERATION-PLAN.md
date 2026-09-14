# Iteration plan

Owner: Kevin ｜ Started 2026-09-15 ｜ Upstream: 2akouwu/reverify v0.11.0

---

## 0. Where we are (M0, done 2026-09-15)

| Item | Status |
|---|---|
| Fork → `Roloria/verdict`, `upstream` remote wired | ✓ |
| Full upstream suite green on Python 3.13 | ✓ 314 passed / 55 skipped |
| `verdict/` package, zero edits to `reverify/` | ✓ |
| Gate kinds: `text_present`, `text_absent`, `file_exists` | ✓ 11 new tests |
| Own scoring rule set (`gate_weight` / `rescore`) | ✓ |
| `verdict check` CLI + CI exit codes 0/2/3/4 | ✓ |
| End-to-end demo (dirty report → exit 2, fixed → exit 0) | ✓ |

Run it:

```bash
pip install -e ".[dev]"
pytest verdict/tests reverify/tests -q      # 325 passed, 55 skipped
verdict check report.md --claims-file claims.json --base-dir .
```

One environment note: under this IDE's shell, `PYTHONPATH` points at a shim whose
`mkdir` wrapper breaks two upstream rollover tests. Run with
`env -u PYTHONPATH pytest ...` (or plain terminal) to get a clean 325.

---

## 1. Architecture constraints (do not break these)

1. **`reverify/` is read-only.** Extend by subclassing `Verifier`; new gates are
   `_check_<kind>` methods. Upstream merges must stay conflict-free.
2. **No LLM in the verify path.** The judge is a tool, always. An LLM may
   *propose* claims (M4), never decide them.
3. **Every gate emits evidence**, not a boolean. Evidence carries what was
   actually observed, so the report can be replayed.
4. **Information, not pass rate.** A set that verifies but says nothing must fail
   (exit 3). This is the moat; never let it regress.
5. **MIT forever.** Upstream is MIT. No open-core license split — monetisation is
   hosted-only (see VISION.md).

---

## 2. Milestones

### M1 · Code-domain gates + evidence ledger — week 1 (9/15–9/21)

Goal: a gate that can run on a real repo and on a PR.

Tasks
- [ ] `command_succeeds` gate: run an allow-listed command (`pytest`, `tsc`,
      `eslint`, `node --check`) with a timeout; evidence = exit code, stdout
      sha256, wall time. This turns "the AI says tests pass" into a claim.
      - allowlist file `.verdict/allowlist.json`, command must match an entry
        exactly; anything unlisted returns INCONCLUSIVE (never executes).
      - reuse the discipline from `unlazy`: bind cwd + resolved binary path,
        record a definition digest so a changed command invalidates old evidence.
- [ ] `diff_touches` gate: PR diff must touch the paths the AI claims it changed.
      Evidence = the matched file list. (Kills "I refactored X" without X.)
- [ ] `.verdict/ledger.jsonl` — append one line per gate run (ts, target sha256,
      claim count, information, exit code). This is the future product asset.
- [ ] `--fail-on {refuted,thin,inconclusive}` flag so teams choose strictness.

Acceptance
```bash
verdict check . --claims-file .verdict/claims.json --base-dir .   # exit 0
# invert one claim → exit 2 ; remove half the claims → exit 3
cat .verdict/ledger.jsonl | wc -l   # grows by 1 per run
```

### M2 · Rule bundles + HTML report — week 2 (9/22–9/28)

Goal: stop hand-writing claims.json; ship the scorecard page.

Tasks
- [ ] Rule-bundle format `verdict.rules.yaml`: named bundle → list of claims +
      weight overrides. Ship three: `ai-tells`, `secrets-pii`, `pr-evidence`.
- [ ] `verdict check --rules ai-tells,secrets-pii <target>` expands bundles into
      claims; `--list-rules` shows them.
- [ ] `verdict report --out gate.html` — single-file HTML, no CDN: gate list with
      verdict + evidence, information gauge, replay command per claim.
- [ ] `verdict rules add <owner/repo>` — vendor a community bundle into
      `.verdict/rules/` (the anti-slop "meant to be vendored" model).

Acceptance: run against this repo, open `gate.html`, every FAIL row shows the
observed evidence and a copy-pasteable replay command.

### M3 · CI + distribution — week 3 (9/29–10/5, travel week, low intensity)

Goal: it installs and fails a build without anyone holding its hand.

Tasks
- [ ] GitHub Action `verdict-gate@v1` (composite: setup-python → pipx → run →
      annotate). Publish to Marketplace.
- [ ] Rename dist to `verdict-gate`, publish to PyPI. Keep `reverify` entry
      points intact for upstream compatibility.
- [ ] MCP server: expose `verify_claims` so Claude Code / Codex can gate their
      own output mid-run (mirror `reverify/mcp_server.py`).
- [ ] SKILL.md for the skills.sh ecosystem — the CLI and the skill are the same
      rule set, which no competitor has.

Note: travel week — keep to release plumbing and docs, no large refactors.

### M4 · Content vertical + launch — week 4–5 (10/6–10/19)

Goal: prove the second vertical (docs/reports) and get distribution.

Tasks
- [ ] `citation_resolves` gate: every `path:line` or URL in a report must resolve
      in-repo. The single highest-value fact-check gate for generated docs.
- [ ] `number_matches_source` gate: a figure quoted in prose must appear in the
      named source file. (Prototype: regex + file read + evidence excerpt.)
- [ ] AI-tell lexicon v1: self-authored, with the research notes from
      `sepia` / `hallmark` / `ponytail` read as input, not copied.
- [ ] Launch post: lead with "LLM judges agree with slop labels at chance" +
      the demo GIF (dirty → exit 2, fixed → exit 0). Post to HN, r/LocalLLaMA,
      and the skills.sh ecosystem.

### M5 · Team tier — week 6+ (only after M4 shows pull)

- Rule sync (private bundles), report history off `ledger.jsonl`, SSO, audit
  export (PDF/CSV of evidence per gate run).
- Pricing ¥199 / ¥499 / ¥999. Do not build this before 20 outside stars or 3
  teams asking.

---

## 3. Open decisions (need your call before M2)

| # | Decision | Options | Lean |
|---|---|---|---|
| 1 | Default strictness | fail on refuted only vs also on thin evidence | also fail on thin (exit 3) — it is the differentiator, but it will annoy people on day 1 |
| 2 | Rule bundle source of truth | vendored files in repo vs registry | vendored first, registry in M5 |
| 3 | `command_succeeds` allowlist | shipped default allowlist vs user-authored only | ship a minimal default (`pytest`, `tsc`, `eslint`, `node --check`) and let teams extend |
| 4 | Talk to upstream? | silent fork vs open an issue declaring intent | open the issue — cheap, polite, and 2akouwu may point at overlap in their ROADMAP §5 |

---

## 4. Risks

| Risk | Why it matters | Mitigation |
|---|---|---|
| Upstream ships the same thing | reverify ROADMAP §5 already says "toward verified coding" | Our layer is output quality (content, compliance, evidence); theirs is behavioural equivalence. Posture: different vertical, and we say so publicly. |
| `command_succeeds` is a footgun | executing commands from a claim file is RCE-shaped | allowlist + INCONCLUSIVE on no match + no shell (`shell=False`, argv list) + timeout + cwd bind. Never auto-approve. |
| Exit 3 (thin evidence) false positives | teams disable the gate entirely | ship bundles that comfortably clear the bar; make `min_information` configurable and show the number in the report |
| Star-chasing skills beat us | ponytail 138k on vibes alone | we are not competing for skill installs; the CLI + CI + report is a different product surface |
| Maintenance while travelling | 9/25–10/5 low bandwidth | M3 is deliberately release plumbing only |

---

## 5. Immediate next actions (this week)

- [x] Fork, tests green, vertical slice
- [ ] `command_succeeds` + allowlist + tests (M1 first task, ~half day)
- [ ] `diff_touches` (M1, ~2h — needs `git diff --name-only` against merge-base)
- [ ] `.verdict/ledger.jsonl` write path (M1, ~1h)
- [ ] Decide #1 and #4 in §3
