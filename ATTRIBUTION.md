# Attribution

`verdict` started as a fork of **reverify** — https://github.com/2akouwu/reverify
by **2akouwu**, licensed **MIT**, forked at v0.11.0 (`f32ea84`, 2026-09-07).

Everything under `reverify/` remains upstream code and stays MIT with its
original copyright. It is treated as a **vendored upstream**: verdict never edits
it, so `git fetch upstream && git merge upstream/main` stays conflict-free.

What verdict adds lives entirely in `verdict/`:

- the document / report / repository claim kinds (`text_present`, `text_absent`,
  `file_exists`, ...)
- verdict's own scoring rule set (`verdict/verifier.py::gate_weight`)
- the `verdict` CLI and its CI exit-code contract

Upstream's contribution here is the part that matters and is not ours: the
**claim → deterministic tool → evidence** protocol, the dependency invalidation
model, and the weighting that refuses to let restated facts count as evidence.
verdict reuses all of it through subclassing.

If upstream ever wants any of the `verdict/` layer, it is theirs to take — MIT,
no strings.

## AI-tell patterns

`tools/vendor/feedhive-patterns.json` is the 120-pattern catalogue from
**FeedHive/ai-slop-detector** (MIT). `verdict/data/slop_patterns.json` is a
derived work built by `tools/build_slop_patterns.py`: it keeps only the phrases
a deterministic checker can match, grouped by the original pattern id, and is
used for density scoring (one phrase is normal, several distinct patterns in a
paragraph is not). The catalogue itself is kept verbatim for reference; no
catalogue text is presented as verdict's own research.

## Design borrowed from alibaba/open-code-review

`verdict/scope.py` and `citation_resolves` adapt **design ideas** from
**alibaba/open-code-review** (Apache-2.0, https://github.com/alibaba/open-code-review):

- one pure pre-dispatch selection pass whose per-file decision is shared by
  preview and the real run (their #782 drift bug);
- static gates in a fixed order — secret path → binary → user exclude →
  generated/test/lock patterns → deletion → size — each with an explicit reason;
- per-file rule resolution grouped by (source, pattern, rules) so a group's
  provenance is accurate for every member (`delegate/rulegroup.go`);
- deterministic bundling of related files and a structured delegate spec that
  hands a host agent the scope without calling a model;
- independent location/reflection checking of references (`citation_resolves`).

**No Apache-2.0 code or data is copied.** The exclusion list, glob engine,
bundling and rule groups are independent MIT implementations; OCR's
`default_exclude_patterns.json`, `rule.json` and Go sources are neither vendored
nor reproduced. They remain Apache-2.0 and are not part of this distribution.

verdict deliberately does **not** adopt their LLM reviewer, provider config,
prompt templates or session resume — the verify path here stays model-free.

License: MIT (see LICENSE).
