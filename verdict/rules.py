"""Rule bundles: named, vendored, forkable claim sets.

A bundle is a JSON file:

    {
      "name": "ai-tells",
      "version": 1,
      "description": "...",
      "weights": {"text_absent": 0.5},
      "claims": [{"kind": "text_absent", "value": "game changer"}]
    }

Resolution order for a rule name: .verdict/rules/<name>.json (yours, wins),
then the built-ins shipped in verdict/rules/, then a literal file path.
"""

from __future__ import annotations

import json
import os
import shutil
from typing import Any, Dict, List, Optional, Tuple

BUNDLE_DIRNAME = os.path.join(".verdict", "rules")


def builtin_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules")


def _read(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    if not isinstance(doc, dict) or "claims" not in doc:
        raise ValueError(f"{path}: a bundle needs a 'claims' list")
    if not isinstance(doc["claims"], list):
        raise ValueError(f"{path}: 'claims' must be a list")
    return doc


def resolve(name: str, base_dir: str = ".") -> Optional[str]:
    """Find the file backing a rule name, or None."""
    local = os.path.join(base_dir, BUNDLE_DIRNAME, f"{name}.json")
    if os.path.isfile(local):
        return local
    builtin = os.path.join(builtin_dir(), f"{name}.json")
    if os.path.isfile(builtin):
        return builtin
    return name if os.path.isfile(name) else None


def load(name: str, base_dir: str = ".") -> Dict[str, Any]:
    path = resolve(name, base_dir)
    if path is None:
        raise FileNotFoundError(f"rule bundle {name!r} not found (looked in .verdict/rules/, built-ins, and as a path)")
    doc = _read(path)
    doc.setdefault("name", os.path.splitext(os.path.basename(path))[0])
    doc.setdefault("weights", {})
    doc["source"] = path
    return doc


def load_many(names: str, base_dir: str = ".") -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    """Expand "a,b" into (claims, weight overrides)."""
    claims: List[Dict[str, Any]] = []
    weights: Dict[str, float] = {}
    for raw in str(names or "").split(","):
        name = raw.strip()
        if not name:
            continue
        bundle = load(name, base_dir)
        for c in bundle["claims"]:
            claim = dict(c)
            claim.setdefault("note", bundle.get("name", name))
            claims.append(claim)
        for k, v in (bundle.get("weights") or {}).items():
            weights[str(k)] = float(v)
    return claims, weights


def available(base_dir: str = ".") -> List[Tuple[str, str, str]]:
    """(name, origin, description) for every discoverable bundle."""
    out: List[Tuple[str, str, str]] = []
    seen = set()

    def add(path: str, origin: str) -> None:
        name = os.path.splitext(os.path.basename(path))[0]
        if name in seen:
            return
        try:
            doc = _read(path)
        except (ValueError, json.JSONDecodeError):
            return
        seen.add(name)
        out.append((name, origin, str(doc.get("description", ""))))

    local_dir = os.path.join(base_dir, BUNDLE_DIRNAME)
    if os.path.isdir(local_dir):
        for f in sorted(os.listdir(local_dir)):
            if f.endswith(".json"):
                add(os.path.join(local_dir, f), "local")
    bdir = builtin_dir()
    if os.path.isdir(bdir):
        for f in sorted(os.listdir(bdir)):
            if f.endswith(".json"):
                add(os.path.join(bdir, f), "builtin")
    return out


def add_bundle(src: str, base_dir: str = ".") -> str:
    """Vendor a bundle file into .verdict/rules/ so a team can edit it."""
    doc = _read(src)
    name = str(doc.get("name") or os.path.splitext(os.path.basename(src))[0])
    dest_dir = os.path.join(base_dir, BUNDLE_DIRNAME)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, f"{name}.json")
    shutil.copyfile(src, dest)
    return dest
