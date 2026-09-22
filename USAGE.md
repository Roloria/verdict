# Usage

```bash
pip install verdict-gate            # from PyPI
# or, from a checkout:
pip install -e ".[dev]"
pytest verdict/tests reverify/tests -q     # 345 passed, 55 skipped
```

## 1. Gate one artifact against a claim file

```bash
verdict check report.md --claims-file claims.json --base-dir .
```

`claims.json` is a list of claims. Flat form is fine — every key that is not
`kind` / `id` / `note` / `depends_on` / `observe` becomes a parameter:

```json
[
  {"kind": "text_present", "value": "31 files", "note": "the number must be real"},
  {"kind": "text_absent",  "pattern": "sk-[A-Za-z0-9]{20,}", "regex": true},
  {"kind": "file_exists",  "path": "src/app.py", "min_bytes": 10},
  {"kind": "command_succeeds", "argv": ["pytest", "-q"], "timeout": 300},
  {"kind": "diff_touches", "paths": ["src/app.py"], "base": "origin/main"}
]
```

## 2. Gate against a rule bundle

```bash
verdict rules list                                  # what is available
verdict check report.md --rules ai-tells,secrets-pii --report gate.html
verdict rules add ./our-house-style.json            # vendor a team bundle
```

Bundles resolve in this order: `.verdict/rules/<name>.json` (yours, wins) →
built-ins in `verdict/rules/` → a literal file path. A bundle may override
weights:

```json
{"name": "house-style", "weights": {"text_absent": 0.5},
 "claims": [{"kind": "text_absent", "value": "synergy"}]}
```

Shipped: `ai-tells` (24 phrases), `secrets-pii` (9 regexes), `pr-evidence`
(tests ran, no placeholders).

## 3. In CI

```yaml
- uses: Roloria/verdict-gate@v1
  with:
    target: docs/report.md
    rules: ai-tells,secrets-pii
    min-information: "2"          # bundles land near 2.5; tune to your rule count
    report: gate.html             # optional
```

Outputs: `exit-code`, `information`, `grounded`. The run is also written to the
job summary as a table.

Or plain CLI:

```yaml
- run: pipx install verdict-gate
- run: verdict check report.md --rules ai-tells,secrets-pii --base-dir .
```

Exit codes:

| code | meaning |
|---|---|
| 0 | grounded: nothing refuted and the evidence is thick enough |
| 2 | a claim was REFUTED or INVALIDATED |
| 3 | nothing refuted, but the verified set is too thin (`--min-information`) |
| 4 | something was INCONCLUSIVE (`--strict`, or `--fail-on inconclusive`) |

`--fail-on refuted,thin,inconclusive` picks which of those break the build
(default `refuted,thin`).

## Gates

| kind | asserts | key params |
|---|---|---|
| `text_present` | output contains a literal or regex | `value` / `pattern`+`regex`, `count`, `min_count`, `max_count` |
| `text_absent` | output does **not** contain it | same |
| `file_exists` | a repo-relative path exists | `path`, `min_bytes` |
| `command_succeeds` | an allow-listed command exits as expected | `argv` (list, no shell), `cwd`, `timeout`, `expect_exit`, `expect_stdout` |
| `diff_touches` | the git diff touches the claimed paths | `paths`, `base`, `mode` (`all`/`any`) |

Plus every reverify kind (`bytes_at`, `string_present`, `functions_equiv`, ...).

## Safety: `command_succeeds`

- argv only; a string `argv` is rejected with "no shell strings".
- Default allowlist: `pytest`, `python -m pytest`, `node --check`, `npx tsc`,
  `tsc --noEmit`, `eslint`, `ruff`, `git diff` (argv prefix match).
- Anything unlisted is **INCONCLUSIVE and never executed**. Extend with
  `.verdict/allowlist.json`:

```json
{"allow": [["pytest"], ["npm", "test"], ["go", "test", "./..."]]}
```

- `cwd` must resolve inside `--base-dir`; a `cwd` that escapes is REFUTED.

## Scoring, and why

Two numbers, both in every report:

- **information** — sum of the weights of the VERIFIED claims. This is what
  `--min-information` gates on.
- **grounded_score** — information / total weight of everything scored.

Repeated claims of the same kind decay harmonically (the Nth one counts 1/N).
Without that, a 33-claim bundle where everything passes scores 19 and the
"thin evidence" gate can never fire — the exact gaming the metric exists to
stop. With it, the same run scores 2.5, and a clean vs dirty artifact reads
1.0 vs 0.53 on grounded_score.

REFUTED claims keep their full weight: a failure should read as "this rule
matters", not as a small number.

## Ledger and report

- Every run appends one JSON line to `.verdict/ledger.jsonl` (`--no-ledger` to
  skip). That file is the asset a team eventually pays to keep and audit.
- `--report gate.html` writes a single-file HTML report — no CDN, no JS
  dependencies. `verdict report run.json --out gate.html` re-renders a saved run.
