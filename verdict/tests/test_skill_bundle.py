"""The root SKILL.md and the skills/ copy must never drift."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_skill_copies_match():
    root = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    bundled = (ROOT / "skills" / "ai-verdict" / "SKILL.md").read_text(encoding="utf-8")
    assert root == bundled


def test_skill_frontmatter():
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\n")
    front = text.split("---", 2)[1]
    assert "name: ai-verdict" in front
    assert "description:" in front
