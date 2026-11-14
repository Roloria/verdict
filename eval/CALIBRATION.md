# Calibration on real external documents

sources **11/11** reachable · rules `ai-tells-density,secrets-pii` · regenerate: `python eval/calibrate.py`

| metric | value |
|---|---|
| documents with a false alarm | **0 / 11** |
| false-alarm rate | **0.0%** |
| injected defects caught | **22 / 22** |
| recall on real documents | **100.0%** |

Documents are downloaded at runtime into `eval/.cache/` (gitignored);
no third-party prose is committed. A cached copy works offline.

## Per document

| repository / file | bytes | sha256 (12) | clean refuted | secret injection | slop injection |
|---|---:|---|---:|---|---|
| `anthropics/skills/main/README.md` | 5547 | `1fca448ca17c` | 0 | caught | caught |
| `promptfoo/promptfoo/main/README.md` | 4599 | `7fd57809624e` | 0 | caught | caught |
| `fastapi/fastapi/master/README.md` | 22830 | `08b41549d83a` | 0 | caught | caught |
| `expressjs/express/master/Readme.md` | 10375 | `3cf5f3e224db` | 0 | caught | caught |
| `facebook/react/main/README.md` | 5296 | `9b6ac13cb03c` | 0 | caught | caught |
| `microsoft/vscode/main/README.md` | 6728 | `45a411a3b8d4` | 0 | caught | caught |
| `rust-lang/rust/master/README.md` | 3304 | `b3f6ef2fef88` | 0 | caught | caught |
| `python/cpython/main/README.rst` | 8920 | `c13615d8d9d4` | 0 | caught | caught |
| `django/django/main/README.rst` | 2179 | `34c0989b01e1` | 0 | caught | caught |
| `NVIDIA/SkillEvaluator/main/README.md` | 10328 | `7147d629ec9a` | 0 | caught | caught |
| `alibaba/open-code-review/main/README.md` | 14105 | `f39bc505beef` | 0 | caught | caught |

## Why this exists

`eval/RESULTS.md` uses hand-written cases and scores 1.000 — necessary as a
regression tripwire, insufficient as evidence. This report measures the
default bundles against READMEs written by other teams, where false
positives actually happen. It caught one real defect: the 18-digit China
ID regex used to fire on badge URLs in README files; it is now bounded.
