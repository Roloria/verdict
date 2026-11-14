---
name: ai-verdict
description: Gate AI output on evidence instead of opinion. Use when asked to verify, check, audit or prove an AI-generated report, document, diff or file; when a task must not be reported done without evidence; or when CI needs a deterministic quality gate. Runs claim → tool → evidence checks and returns VERIFIED / REFUTED with a non-zero exit code on failure.
license: MIT
metadata:
  author: Roloria
  version: "0.12.0"
  repo: https://github.com/Roloria/verdict
---

# ai-verdict

Do not say "done" on a generated artifact until its claims have been checked by
a tool. A confident summary is not evidence.

## When to use

- You produced a report, doc, migration note, PR description or release note.
- Someone asks "did it actually work / is this real / prove it".
- A CI job must fail on slop, secrets, untruthful claims or unproven work.
- You are about to claim tests pass, files were created, or paths were changed.

## Do not use

- To guess whether a human or a model wrote a text. verdict does not detect
  authorship; it checks assertions.
- To grade output with another LLM. The judge here is always a deterministic
  tool.

## Install

```bash
pip install ai-verdict          # or: pip install -e . from a checkout
verdict kinds
verdict rules list
```

## Workflow

1. **Write the artifact** to a file. verdict checks files, not chat messages.
2. **Run a rule bundle**, or write claim JSON for the specific assertions:

```bash
verdict check report.md --rules ai-tells-density,secrets-pii --base-dir .
verdict check report.md --claims-file claims.json --report gate.html
```

3. **Read the exit code before reporting success**:

| code | meaning | action |
|---|---|---|
| 0 | grounded | report done, with the numbers |
| 2 | REFUTED | fix the artifact, run again |
| 3 | thin evidence | add real claims; do not pad with easy ones |
| 4 | INCONCLUSIVE (`--strict`) | a tool could not decide; do not assert it |

4. **Quote the evidence**, not the vibe: "37 claims, 34 VERIFIED, 2 REFUTED,
   information 2.5 / min 1.0, grounded_score 0.88".

## Claim kinds

| kind | asserts |
|---|---|
| `text_present` | literal or regex appears (optionally N times) |
| `text_absent` | literal or regex does not appear (secrets, house style) |
| `slop_density` | no paragraph hits N distinct AI-tell patterns |
| `file_exists` | a repo-relative path exists and is non-trivial |
| `command_succeeds` | an allow-listed command exits as expected |
| `diff_touches` | the git diff actually touches the claimed paths |
| `tests_actually_prove` | tests were not deleted, skipped or left untouched |
| `text_present` / reverify kinds | every upstream kind still works |

Flat form is fine:

```json
[
  {"kind": "text_present", "value": "31 files", "note": "the number is real"},
  {"kind": "slop_density", "preset": "slop-120", "min_hits": 3},
  {"kind": "command_succeeds", "argv": ["pytest", "-q"]},
  {"kind": "tests_actually_prove", "base": "origin/main"}
]
```

## Rules that matter

- `command_succeeds` only runs allow-listed argv. A shell string is rejected.
  Anything unlisted returns INCONCLUSIVE and is never executed.
- Verified claims of the same kind decay harmonically. Passing 30 trivial rules
  is not "more evidence" than passing 3 hard ones.
- `--min-information` is bundle-size sensitive. Shipped bundles land near 2.5.
- `reverify/` is vendored upstream and must never be edited.

## Team rules

```bash
verdict rules add ./our-house-style.json    # vendors into .verdict/rules/
verdict check doc.md --rules ai-tells-density,our-house-style
```
