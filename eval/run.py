"""Small public benchmark: does verdict catch injected defects without flagging prose?

    python eval/run.py            # writes eval/RESULTS.md, exits 1 if quality drops

Method: each case is one text artifact. `expected=dirty` means a known defect was
injected (AI-tell density, a secret, a PII shape, or high-confidence ZH tells).
The gate under test is `ai-tells-density,secrets-pii` — the low-false-positive
bundle pair. A case is predicted dirty when anything is REFUTED.

This is deliberately small and legible. It is not a claim of general accuracy;
it is a regression tripwire, in the spirit of Alibaba's AACR-Bench.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from reverify.verifier import Claim

from verdict.rules import load_many
from verdict.verifier import GateVerifier

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CASES = ROOT / "eval" / "cases.jsonl"
OUT = ROOT / "eval" / "RESULTS.md"
RULES = "ai-tells-density,secrets-pii"


def main() -> int:
    cases = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line.strip()]
    claims, weights = load_many(RULES, str(ROOT))
    rows = []
    for c in cases:
        # `parts` keeps token-shaped fixtures out of the tracked file (GitHub
        # push protection would reject them); they are assembled here only.
        text = c.get("text") or "".join(c.get("parts", []))
        report = GateVerifier(text.encode("utf-8"), base_dir=str(ROOT), weight_overrides=weights).verify_all(
            [Claim.from_dict(x) for x in claims], min_information=0.0
        )
        predicted = "dirty" if report["refuted"] else "clean"
        rows.append({
            "id": c["id"],
            "expected": c["expected"],
            "predicted": predicted,
            "defect": c["defect"],
            "refuted": report["refuted"],
            "correct": predicted == c["expected"],
        })

    tp = sum(1 for r in rows if r["expected"] == "dirty" and r["predicted"] == "dirty")
    fn = sum(1 for r in rows if r["expected"] == "dirty" and r["predicted"] == "clean")
    fp = sum(1 for r in rows if r["expected"] == "clean" and r["predicted"] == "dirty")
    tn = sum(1 for r in rows if r["expected"] == "clean" and r["predicted"] == "clean")
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    lines = [
        "# verdict benchmark",
        "",
        f"cases **{len(rows)}** · rules `{RULES}` · gate: any REFUTED ⇒ dirty",
        "",
        "| metric | value |",
        "|---|---|",
        f"| precision | {precision:.3f} |",
        f"| recall (defects caught) | {recall:.3f} |",
        f"| F1 | {f1:.3f} |",
        f"| false accepts (missed defects) | {fn} |",
        f"| false alarms (clean flagged) | {fp} |",
        f"| TP / TN | {tp} / {tn} |",
        "",
        "## Cases",
        "",
        "| id | expected | predicted | defect | refuted | ✓ |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| `{r['id']}` | {r['expected']} | {r['predicted']} | {r['defect']} | "
            f"{r['refuted']} | {'✓' if r['correct'] else '✗'} |"
        )
    lines += [
        "",
        "Regenerate: `python eval/run.py`. This is a regression tripwire, not a",
        "general accuracy claim — extend `cases.jsonl` when a rule changes.",
        "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"precision={precision:.3f} recall={recall:.3f} f1={f1:.3f} fn={fn} fp={fp} -> {OUT}")
    bad = [r for r in rows if not r["correct"]]
    if bad:
        print("misclassified:", ", ".join(r["id"] for r in bad))
    return 1 if fn or fp else 0


if __name__ == "__main__":
    raise SystemExit(main())
