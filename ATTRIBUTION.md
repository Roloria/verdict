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

License: MIT (see LICENSE).
