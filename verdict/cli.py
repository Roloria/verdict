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
import hashlib
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

from reverify.cli import load_input_bytes
from reverify.verifier import Claim

from . import __version__
from .report import load_json, render_file
from .rules import add_bundle, available, load as load_bundle, load_many
from .verifier import DEFAULT_ALLOWLIST, GateVerifier, TEXT_KINDS

EXIT_OK = 0
EXIT_REFUTED = 2
EXIT_THIN = 3
EXIT_INCONCLUSIVE = 4


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


def _load_allowlist(args: argparse.Namespace) -> Optional[List[List[str]]]:
    """Explicit --allowlist wins; otherwise .verdict/allowlist.json in the repo."""
    path = args.allowlist
    if path is None:
        candidate = os.path.join(args.base_dir, ".verdict", "allowlist.json")
        path = candidate if os.path.isfile(candidate) else None
    if path is None:
        return None  # None = keep the built-in default allowlist
    with open(path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    allow = doc.get("allow", doc) if isinstance(doc, dict) else doc
    return [list(a) for a in allow]


def _append_ledger(path: str, record: Dict[str, Any]) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def cmd_check(args: argparse.Namespace) -> None:
    claims = _load_claims(args)
    weights: Dict[str, float] = {}
    if getattr(args, "rules", ""):
        bundle_claims, weights = load_many(args.rules, args.base_dir)
        claims = claims + bundle_claims
    if not claims:
        raise SystemExit("verdict check needs --rules, --claims-file or --claim '<json>'")
    data = load_input_bytes(args.target)
    verifier = GateVerifier(
        data,
        base_dir=args.base_dir,
        allowlist=_load_allowlist(args),
        weight_overrides=weights,
    )
    report = verifier.verify_all(
        [Claim.from_dict(c) for c in claims], min_information=args.min_information
    )

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print("=== verdict: AI output gate ===")
        shown = report["results"] if args.verbose else [
            r for r in report["results"] if r["verdict"] not in ("VERIFIED", "OBSERVED")
        ]
        _print(shown)
        hidden = len(report["results"]) - len(shown)
        if hidden:
            print(f"  (+{hidden} passing claim(s) hidden, --verbose lists them)")
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

    if getattr(args, "report", ""):
        render_file(report, args.report, target=args.target, rules=getattr(args, "rules", "") or "")
        if not args.json:
            print(f"report: {args.report}")

    fail_on = {s.strip() for s in str(args.fail_on).split(",") if s.strip()}
    if args.strict:
        fail_on.add("inconclusive")

    code = EXIT_OK
    if (report["refuted"] or report["invalidated"]) and "refuted" in fail_on:
        code = EXIT_REFUTED
    elif not report["informative"] and "thin" in fail_on:
        code = EXIT_THIN
    elif report["inconclusive"] and "inconclusive" in fail_on:
        code = EXIT_INCONCLUSIVE

    if not args.no_ledger:
        _append_ledger(
            args.ledger,
            {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "target": os.path.relpath(args.target, args.base_dir)
                if os.path.exists(args.target)
                else args.target,
                "target_sha256": report["receipt"]["binary_sha256"],
                "claims": report["total_claims"],
                "verified": report["verified"],
                "refuted": report["refuted"],
                "inconclusive": report["inconclusive"],
                "invalidated": report["invalidated"],
                "information": report["information"],
                "min_information": report["min_information"],
                "grounded": report["grounded"],
                "rules": getattr(args, "rules", "") or "",
                "exit": code,
            },
        )
    sys.exit(code)


def cmd_kinds(args: argparse.Namespace) -> None:
    print("verdict gate kinds:")
    for k in TEXT_KINDS:
        print(f"  {k}")
    print("\nplus every reverify kind (bytes_at, string_present, functions_equiv, ...)")


def cmd_scope(args: argparse.Namespace) -> None:
    from .scope import build_scope, delegate_spec

    scope = build_scope(
        base_dir=args.base_dir,
        mode=args.mode,
        base=args.base,
        to=args.to,
        commit=args.commit,
        user_excludes=args.exclude or [],
    )
    out = delegate_spec(scope) if args.delegate else scope
    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(f"mode={scope['mode']} changed={scope['changed']} "
              f"selected={scope['selected_count']} excluded={scope['excluded_count']} "
              f"bundles={len(scope['bundles'])}")
        for b in out.get("bundles", []):
            label = b["label"]
            files = ", ".join(b["files"][:4]) + (" ..." if len(b["files"]) > 4 else "")
            print(f"  [{label}] {files}")
        for d in scope["decisions"]:
            if not d["selected"]:
                print(f"  excluded {d['path']}: {d['reason']}")
        print("(--json for the full structured scope / --delegate for an agent hand-off)")


def cmd_rules(args: argparse.Namespace) -> None:
    if args.rules_cmd == "list":
        rows = available(args.base_dir)
        if not rows:
            print("no bundles found")
            return
        for name, origin, desc in rows:
            print(f"  {name:<16} {origin:<8} {desc}")
    elif args.rules_cmd == "show":
        print(json.dumps(load_bundle(args.name, args.base_dir), indent=2, ensure_ascii=False))
    elif args.rules_cmd == "add":
        print(f"vendored -> {add_bundle(args.src, args.base_dir)}")


def cmd_report(args: argparse.Namespace) -> None:
    print(render_file(load_json(args.report_json), args.out, target=args.target or ""))


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
    c.add_argument("--fail-on", default="refuted,thin",
                   help="comma list of refuted|thin|inconclusive that should fail the run")
    c.add_argument("--rules", help="comma-separated rule bundles (ai-tells, secrets-pii, ...)")
    c.add_argument("--report", help="also write a single-file HTML report here")
    c.add_argument("--allowlist", help="JSON file of allowed command argv prefixes")
    c.add_argument("--ledger", default=".verdict/ledger.jsonl", help="append a run record here")
    c.add_argument("--no-ledger", action="store_true", help="do not write the ledger")
    c.add_argument("--json", action="store_true")
    c.add_argument("--verbose", action="store_true", help="list passing claims too")
    c.set_defaults(func=cmd_check)

    k = sub.add_parser("kinds", help="list claim kinds")
    k.set_defaults(func=cmd_kinds)

    sc = sub.add_parser("scope", help="deterministic review scope: file selection, rules, bundles")
    sc.add_argument("--mode", choices=["workspace", "merge-base", "commit", "base"], default="workspace")
    sc.add_argument("--base", default="HEAD")
    sc.add_argument("--to", default="HEAD")
    sc.add_argument("--commit", default="")
    sc.add_argument("--base-dir", default=".")
    sc.add_argument("--exclude", action="append", default=[], help="extra glob to exclude")
    sc.add_argument("--delegate", action="store_true", help="emit a structured hand-off for a host agent")
    sc.add_argument("--json", action="store_true")
    sc.set_defaults(func=cmd_scope)

    r = sub.add_parser("rules", help="rule bundles")
    rs = r.add_subparsers(dest="rules_cmd", required=True)
    rl = rs.add_parser("list", help="list available bundles")
    rl.add_argument("--base-dir", default=".")
    rl.set_defaults(func=cmd_rules)
    rsh = rs.add_parser("show", help="print a bundle")
    rsh.add_argument("name")
    rsh.add_argument("--base-dir", default=".")
    rsh.set_defaults(func=cmd_rules)
    ra = rs.add_parser("add", help="vendor a bundle file into .verdict/rules/")
    ra.add_argument("src")
    ra.add_argument("--base-dir", default=".")
    ra.set_defaults(func=cmd_rules)

    rp = sub.add_parser("report", help="render an HTML report from a saved JSON run")
    rp.add_argument("report_json")
    rp.add_argument("--out", default="gate.html")
    rp.add_argument("--target", default="")
    rp.set_defaults(func=cmd_report)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
