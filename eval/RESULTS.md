# verdict benchmark

cases **30** · rules `ai-tells-density,secrets-pii` · gate: any REFUTED ⇒ dirty

| metric | value |
|---|---|
| precision | 1.000 |
| recall (defects caught) | 1.000 |
| F1 | 1.000 |
| false accepts (missed defects) | 0 |
| false alarms (clean flagged) | 0 |
| TP / TN | 15 / 15 |

## By defect type

| defect | cases | caught | false accepts | false alarms |
|---|---:|---:|---:|---:|
| ai-tells-density | 5 | 5 | 0 | 0 |
| none | 15 | 0 | 0 | 0 |
| pii | 2 | 2 | 0 | 0 |
| secret | 6 | 6 | 0 | 0 |
| zh-tells | 2 | 2 | 0 | 0 |

## Cases

| id | expected | predicted | defect | refuted | ✓ |
|---|---|---|---|---|---|
| `clean-01` | clean | clean | none | 0 | ✓ |
| `clean-02` | clean | clean | none | 0 | ✓ |
| `clean-03` | clean | clean | none | 0 | ✓ |
| `clean-04` | clean | clean | none | 0 | ✓ |
| `clean-05` | clean | clean | none | 0 | ✓ |
| `clean-06` | clean | clean | none | 0 | ✓ |
| `clean-07` | clean | clean | none | 0 | ✓ |
| `clean-08` | clean | clean | none | 0 | ✓ |
| `clean-09` | clean | clean | none | 0 | ✓ |
| `clean-10` | clean | clean | none | 0 | ✓ |
| `clean-11` | clean | clean | none | 0 | ✓ |
| `clean-12` | clean | clean | none | 0 | ✓ |
| `clean-13` | clean | clean | none | 0 | ✓ |
| `clean-14` | clean | clean | none | 0 | ✓ |
| `clean-15` | clean | clean | none | 0 | ✓ |
| `dirty-01` | dirty | dirty | ai-tells-density | 1 | ✓ |
| `dirty-02` | dirty | dirty | ai-tells-density | 1 | ✓ |
| `dirty-03` | dirty | dirty | secret | 1 | ✓ |
| `dirty-04` | dirty | dirty | secret | 1 | ✓ |
| `dirty-05` | dirty | dirty | secret | 1 | ✓ |
| `dirty-06` | dirty | dirty | secret | 1 | ✓ |
| `dirty-07` | dirty | dirty | pii | 2 | ✓ |
| `dirty-08` | dirty | dirty | zh-tells | 4 | ✓ |
| `dirty-09` | dirty | dirty | ai-tells-density | 1 | ✓ |
| `dirty-10` | dirty | dirty | secret | 1 | ✓ |
| `dirty-11` | dirty | dirty | ai-tells-density | 1 | ✓ |
| `dirty-12` | dirty | dirty | secret | 1 | ✓ |
| `dirty-13` | dirty | dirty | zh-tells | 1 | ✓ |
| `dirty-14` | dirty | dirty | pii | 1 | ✓ |
| `dirty-15` | dirty | dirty | ai-tells-density | 1 | ✓ |

Regenerate: `python eval/run.py`. This is a regression tripwire, not a
general accuracy claim — extend `cases.jsonl` when a rule changes.
