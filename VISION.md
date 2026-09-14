# verdict — the gate AI output has to walk through

## The problem

AI produces a lot. None of it is falsifiable.

The industry's answer is to ask another model to grade it. That is the whole
category: promptfoo, deepeval, LLM-as-a-judge rubrics. It feels rigorous and it
is not — a judge that shares the generator's priors gives you a number, not
evidence. One of the small projects in this space states the finding plainly:

> LLM judges agree with human slop labels at chance.

A score you cannot falsify is a score you cannot gate on.

## The bet

**Every assertion in an AI output must be bound to a check that a deterministic
tool can run.** If it cannot be checked, it is not a claim — it is prose.

Not "the model says this report is 8/10".
Instead: 37 claims, 34 VERIFIED, 2 REFUTED, 1 INCONCLUSIVE, here is the command
that reproduces each one.

This is the same protocol reverify uses for binaries (`model proposes, tools
decide`), aimed at what AI actually ships: reports, docs, diffs, generated code.

## What makes it a gate and not a linter

1. **Evidence, not opinion.** Each claim returns what the tool actually observed.
2. **Thin evidence fails too.** A claim set can verify and still be worthless —
   asserting `file exists` five times says nothing. verdict scores *information*,
   not pass rate, and exits 3 when the verified set is too thin. This is
   inherited from reverify and it is the anti-gaming property that matters.
3. **Fail-closed in CI.** Non-zero exit on REFUTED (2), thin evidence (3), or —
   with `--strict` — anything INCONCLUSIVE (4).
4. **Rules are data.** A rule set is a claim bundle you can vendor, fork, and
   extend. That is what makes a rule market possible later.

## What it is not

- Not an AI code reviewer. CodeRabbit / Greptile / pr-agent own that; they review
  code, they do not gate claims.
- Not an eval framework. promptfoo / deepeval own that; they score, they do not
  fail builds on falsifiable evidence.
- Not AI-text detection. "Was this written by a model" is a guessing game and
  verdict does not play it. "Does this output contain a `sk-` key" is checkable,
  and that is the kind of question verdict asks.

## Non-negotiable architectural rule

`reverify/` is never edited. All verdict code lives in `verdict/` and extends by
subclassing (`getattr(self, "_check_" + kind)` dispatch). Consequence:
`git merge upstream/main` stays clean, and upstream's hardening work (sandbox,
parser fuzzing, zero-false-accept benchmark) keeps landing in our tree for free.

## Business shape

Upstream is MIT, so the fork is MIT. There is no open-core license split
available — the paid layer has to be a hosted service, not a license:

| Layer | Model |
|---|---|
| CLI + built-in rule bundles + local report | free, MIT, forever |
| Team rule sync, report history, SSO, audit export | hosted, ¥199–999/mo |

The open-source asset is the **evidence ledger**: JSONL + hashes. It is the only
thing a team will pay to keep, search, and prove to an auditor.
