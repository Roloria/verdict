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

License: MIT (see LICENSE).
