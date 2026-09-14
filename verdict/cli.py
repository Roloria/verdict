"""verdict CLI — run a claim set against one artifact and gate on the result.

Exit codes (CI-friendly):
  0  every claim verified and the set is informative enough
  2  at least one claim was REFUTED or INVALIDATED
  3  nothing refuted, but the verified set is not informative enough (thin evidence)
  4  something was INCONCLUSIVE (only with --strict)
  1  usage / IO error
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List

from reverify.cli import load_input_bytes
from reverify.verifier import Claim

from . import __version__
from .verifier import GateVerifier, TEXT_KINDS


def _load_claims(args: argparse.Namespace) -> List[Dict[str, Any]]:
    if args.claims_file:
        with open(args.claims_file, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        return loaded if isinstance(loaded, list) else [loaded]
    out: List[Dict[str, Any]] = []
    for raw in args.claim or []:
        loaded = json.loads(raw)
        out.extend(loaded if isinstance(loaded, list) else [loaded])
    return out


def _print(results: List[Dict[str, Any]]) -> None:
    for r in results:
        mark = {"VERIFIED": "PASS", "REFUTED": "FAIL", "INCONCLUSIVE": "????",
                "OBSERVED": "note", "INVALIDATED": "skip"}.get(r["verdict"], r["verdict"])
        line = f"  [{mark}] {r['kind']:<14} w={r['weight']:<5} {r['detail']}"
        if r.get("note"):
            line += f"  ({r['note']})"
        print(line)


def cmd_check(args: argparse.Namespace) -> None:
    claims = _load_claims(args)
    if not claims:
        raise SystemExit("verdict check needs --claims-file or --claim '<json>'")
    data = load_input_bytes(args.target)
    verifier = GateVerifier(data, base_dir=args.base_dir)
    report = verifier.verify_all(
        [Claim.from_dict(c) for c in claims], min_information=args.min_information
    )

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print("=== verdict: AI output gate ===")
        _print(report["results"])
        print(
            f"\nverified {report['verified']}/{report['total_claims']} "
            f"(refuted {report['refuted']}, inconclusive {report['inconclusive']}, "
            f"invalidated {report['invalidated']})\n"
            f"information {report['information']} / min {report['min_information']}   "
            f"grounded_score {report['grounded_score']}\n"
            f"trustworthy {report['trustworthy']}  informative {report['informative']}  "
            f"GROUNDED {report['grounded']}"
        )
        if report["gate_kinds"]:
            print(f"gate kinds: {', '.join(report['gate_kinds'])}")

    if report["refuted"] or report["invalidated"]:
        sys.exit(2)
    if not report["informative"]:
        sys.exit(3)
    if args.strict and report["inconclusive"]:
        sys.exit(4)


def cmd_kinds(args: argparse.Namespace) -> None:
    print("verdict gate kinds:")
    for k in TEXT_KINDS:
        print(f"  {k}")
    print("\nplus every reverify kind (bytes_at, string_present, functions_equiv, ...)")


def main() -> None:
    ap = argparse.ArgumentParser(prog="verdict", description="Deterministic gates for AI output.")
    ap.add_argument("--version", action="version", version=f"verdict {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="verify a claim set against a target")
    c.add_argument("target")
    c.add_argument("--claims-file")
    c.add_argument("--claim", action="append")
    c.add_argument("--base-dir", default=".", help="repo root for file_exists paths")
    c.add_argument("--min-information", type=float, default=1.0)
    c.add_argument("--strict", action="store_true", help="fail on INCONCLUSIVE too")
    c.add_argument("--json", action="store_true")
    c.set_defaults(func=cmd_check)

    k = sub.add_parser("kinds", help="list claim kinds")
    k.set_defaults(func=cmd_kinds)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
