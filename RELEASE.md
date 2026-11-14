# Release

Nothing here runs automatically. Both surfaces need a one-time setup, then a tag.

## 0. Why the name is `ai-verdict`

The original `verdict-gate` was taken on PyPI on 2026-11-10 by an unrelated
project in the same space. Package name is now **`ai-verdict`**; the GitHub repo
stays `Roloria/verdict`, and the CLI command stays `verdict`.

`ai-verdict` was verified free on PyPI on 2026-11-14.

## 1. PyPI: `pip install ai-verdict`

One-time, on pypi.org:

1. Create a *pending trusted publisher* for `ai-verdict` (no manual first
   upload needed), or upload once to claim the name.
2. Project → Publishing → Add a trusted publisher:
   - owner `Roloria`, repo `verdict`, workflow `publish-pypi.yml`,
     environment `pypi`.
3. Create the GitHub environment `pypi` (Settings → Environments). No secret is
   needed — the workflow uses OIDC (`id-token: write`).

Then, per release:

```bash
python -m pip install --upgrade build twine
python -m build
python -m twine check dist/*
git tag v0.12.0 && git push origin v0.12.0   # triggers publish-pypi.yml
```

Sanity check after it lands:

```bash
pipx install ai-verdict && verdict --version && verdict rules list
```

## 2. GitHub Marketplace: `Roloria/verdict@v1`

`action.yml` sits at the repo root, which is what Marketplace reads. The `uses:`
reference is the **repository** name, not the PyPI package name.

1. Tag and release `v0.12.0` first (so the action has something to install from
   PyPI — the action installs the published package, not the repo checkout).
2. Create a Release for that tag, tick **Publish this release to the GitHub
   Marketplace**, accept the terms, category = Continuous integration.
3. Move the floating major tag so `uses: Roloria/verdict@v1` tracks it:

```bash
git tag -f v1 v0.12.0 && git push -f origin v1
```

## 3. Version policy

Dist version follows upstream (`0.11.0` → `0.12.0`) so the fork line stays
readable. Upstream bumps do not force a release here; a verdict-layer change does.

Both distributions stay import-compatible with upstream: the `reverify` /
`reverify-mcp` console scripts and the `reverify` package are untouched.

`verdict/__init__.py::__version__` must stay in sync with `pyproject.toml`; the
self-gate asserts it.

## 4. Pre-release checklist

- [ ] `pytest verdict/tests reverify/tests -q` green
- [ ] `verdict check ITERATION-PLAN.md --claims-file .verdict/claims.json` → exit 0
- [ ] `python -m twine check dist/*` clean
- [ ] `ai-verdict` is available on PyPI before tagging (the action pip-installs it)
- [ ] `examples/gate.html` regenerated against the current templates
- [ ] `eval/run.py` results committed to `eval/RESULTS.md`

## 5. Usage once published

```yaml
- uses: Roloria/verdict@v1
  with:
    target: docs/report.md
    rules: ai-tells,secrets-pii
    min-information: "2"
```
