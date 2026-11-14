"""Release preflight: compress the one-time publishing setup into one command.

It cannot click buttons on pypi.org for you, but it tells you exactly which are
left, and verifies everything that can be verified locally.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .i18n import t

WORKFLOW = ".github/workflows/publish-pypi.yml"


def _pyproject(root: Path) -> Tuple[str, str]:
    path = root / "pyproject.toml"
    if not path.is_file():
        return "", ""
    text = path.read_text(encoding="utf-8")
    name = re.search(r'^name = "([^"]+)"', text, re.M)
    version = re.search(r'^version = "([^"]+)"', text, re.M)
    return (name.group(1) if name else ""), (version.group(1) if version else "")


def _repo_slug(root: Path) -> str:
    """Derive owner/repo from git remote instead of hard-coding this fork."""
    try:
        url = subprocess.run(
            ["git", "-C", str(root), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""
    m = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?$", url)
    return m.group(1) if m else ""


def preflight(base_dir: str = ".", check_pypi: bool = True) -> Dict[str, Any]:
    root = Path(base_dir).resolve()
    name, version = _pyproject(root)
    checks: List[Tuple[str, bool, str]] = []

    checks.append((f"dist name = {name}", name == "ai-verdict", ""))
    init_path = root / "verdict" / "__init__.py"
    init = init_path.read_text(encoding="utf-8") if init_path.is_file() else ""
    m = re.search(r'__version__ = "([^"]+)"', init)
    checks.append((f"__version__ = {version}", bool(m and m.group(1) == version), ""))

    wf = root / WORKFLOW
    wf_ok = wf.is_file() and "id-token: write" in wf.read_text(encoding="utf-8")
    checks.append((f"{WORKFLOW} (OIDC)", wf_ok, ""))

    act = root / "action.yml"
    act_ok = act.is_file() and "ai-verdict" in act.read_text(encoding="utf-8")
    checks.append(("action.yml installs ai-verdict", act_ok, ""))

    tag = f"v{version}"
    try:
        tags = subprocess.run(["git", "-C", str(root), "tag", "-l", tag],
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        tags = ""
    checks.append((f"local tag {tag}", bool(tags), ""))
    build_ok = all(importlib.util.find_spec(m) is not None
                   for m in ("build", "setuptools", "wheel"))
    checks.append(("build backend (build + setuptools + wheel)", build_ok,
                   "pip install build setuptools wheel"))

    pypi_state = "unknown"
    if check_pypi:
        try:
            proc = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                 "--max-time", "8", f"https://pypi.org/pypi/{name}/json"],
                capture_output=True, text=True, timeout=12,
            )
            pypi_state = {"200": "published", "404": "available"}.get(proc.stdout.strip(), "unknown")
        except (OSError, subprocess.TimeoutExpired):
            pypi_state = "unknown"
    # A free name is NOT a failure: with a pending trusted publisher the first
    # OIDC publish claims it. Offline/unknown is informational, not a red cross.
    if check_pypi and pypi_state != "unknown":
        checks.append((f"PyPI {name}: {pypi_state}", True, ""))

    env_state = "unknown"
    slug = _repo_slug(root)
    if slug:
        try:
            proc = subprocess.run(
                ["gh", "api", f"repos/{slug}/environments",
                 "--jq", ".environments[].name"],
                capture_output=True, text=True, timeout=12,
            )
            if proc.returncode == 0:
                env_state = "present" if "pypi" in proc.stdout.split() else "missing"
        except (OSError, subprocess.TimeoutExpired):
            pass
    checks.append((f"GitHub environment pypi: {env_state}", env_state == "present", ""))

    todo: List[str] = []
    if pypi_state != "published":
        todo.append(f"PyPI: create a pending trusted publisher for {name} "
                    f"({slug or 'owner/repo'} / publish-pypi.yml / env pypi)")
    if env_state != "present":
        todo.append("GitHub: create the `pypi` environment")
    if not tags:
        todo.append(f"sh tools/publish.sh  # creates + pushes {tag}, triggers OIDC upload")
    todo.append("Release: tick 'Publish to GitHub Marketplace', then move the v1 tag")

    return {
        "name": name, "version": version, "pypi": pypi_state,
        "repository": slug, "environment": env_state, "checks": checks, "todo": todo,
        "ready": all(ok for _, ok, _ in checks) and not todo,
    }


def print_preflight(result: Dict[str, Any]) -> None:
    print(t("release.title"))
    for item, ok, detail in result["checks"]:
        line = t("release.ok" if ok else "release.missing", item=item)
        print(line + (f" ({detail})" if detail and not ok else ""))
    if result["todo"]:
        print("\n" + t("release.next"))
        for i, item in enumerate(result["todo"], 1):
            print(f"  {i}. {item}")
