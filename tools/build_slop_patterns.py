"""Build verdict/data/slop_patterns.json from the vendored FeedHive pattern list.

Source: FeedHive/ai-slop-detector (MIT), 120 patterns in 9 categories. It is a
human-readable catalogue, not a rule file, so this script extracts only the
phrases that a deterministic checker can actually match. Everything else stays
in tools/vendor/ as reference material for agents and for future rules.

    python tools/build_slop_patterns.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "tools" / "vendor" / "feedhive-patterns.json"
OUT = ROOT / "verdict" / "data" / "slop_patterns.json"

QUOTED = re.compile(r'"([^"]{3,60})"')
WORDLIST_CATEGORIES = {"vocabulary", "stock-phrases", "chatbot-residue"}
NOISE_PREFIXES = (
    "many ", "abstract ", "inflating ", "one sentence", "used everywhere",
    "a single", "several ", "words that", "inflating ", "long ", "short ",
)


def is_phrase(s: str) -> bool:
    if not 3 <= len(s) <= 42:
        return False
    if not re.search(r"[A-Za-z]", s):
        return False
    if re.search(r"\b[XY]\b", s):  # "It's not X. It's Y." templates
        return False
    if s.lower().startswith(NOISE_PREFIXES):
        return False
    if s.count(" ") > 7:
        return False
    # Single words shorter than 5 letters ("deep", "it", "one") are ordinary
    # English, not a tell. They poison a density counter.
    if " " not in s and len(s) < 5:
        return False
    return True


def candidates(pattern: dict, category: str) -> list[str]:
    desc = pattern.get("description") or ""
    # `bad` holds full example sentences — too specific to match anything else,
    # so it is deliberately not mined. Parenthesised glosses go too.
    clean = re.sub(r"\([^)]*\)", "", desc)
    out: list[str] = []
    for raw in QUOTED.findall(clean):
        phrase = raw.strip().strip(".,;:!? ")
        if len(phrase) <= 28 and is_phrase(phrase):
            out.append(phrase)
    if category in WORDLIST_CATEGORIES:
        for part in re.split(r"[,/]", clean):
            phrase = part.strip().strip(".!? ")
            if is_phrase(phrase) and len(phrase) >= 4:
                out.append(phrase)
    return out


def main() -> None:
    doc = json.loads(SRC.read_text(encoding="utf-8"))
    entries: list[dict] = []
    seen: set[str] = set()
    for cat in doc["categories"]:
        for p in cat.get("patterns", []):
            for phrase in candidates(p, cat["id"]):
                key = phrase.lower()
                if key in seen:
                    continue
                seen.add(key)
                entries.append({
                    "id": p["id"],
                    "category": cat["id"],
                    "label": p.get("name", ""),
                    "phrase": phrase,
                    "regex": r"(?<!\w)" + re.escape(phrase) + r"(?!\w)",
                })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "name": "slop-patterns",
        "version": 1,
        "source": "FeedHive/ai-slop-detector (MIT), derived by tools/build_slop_patterns.py",
        "note": "Machine-checkable phrases only; the full 120-pattern catalogue stays in tools/vendor/.",
        "patterns": entries,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(entries)} phrases from {sum(len(c.get('patterns', [])) for c in doc['categories'])} patterns")


if __name__ == "__main__":
    main()
